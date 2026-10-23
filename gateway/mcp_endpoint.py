import asyncio
import contextvars
import time

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.responses import JSONResponse

import db
import upstream

# Holds the logged-in user for the current request (used for the audit log)
current_user_var = contextvars.ContextVar("current_user", default=None)

mcp_server = Server("urumi-gateway")


@mcp_server.list_tools()
async def handle_list_tools():
    _servers, tools = await upstream.collect_tools()
    return [
        types.Tool(
            name=t["name"],
            description=t["description"],
            inputSchema=t["inputSchema"],
        )
        for t in tools
    ]


def audit(user, name, server_name, status, started, error=None):
    """Writes one audit row. A logging problem must never break the tool call."""
    try:
        duration_ms = int((time.monotonic() - started) * 1000)
        db.add_audit(user, name, server_name, status, duration_ms, error)
    except Exception as e:
        print(f"audit log write failed: {type(e).__name__}", flush=True)


def root_cause(e):
    """Unwraps grouped errors so the log shows the real cause, e.g. ConnectError."""
    while getattr(e, "exceptions", None):
        e = e.exceptions[0]
    return type(e).__name__


async def execute_tool(user, name, arguments):
    """Runs one prefixed tool (like woo__list_products) as the given user.
    Used by both the MCP endpoint and the chat agent. Raises on failure."""
    started = time.monotonic()

    if "__" not in name:
        audit(user, name, None, "error", started, "unknown tool")
        raise ValueError(f"Unknown tool: {name}")

    # Server names contain only lowercase letters and digits, so the first "__" is the split point
    server_name, tool_name = name.split("__", 1)

    row = next((s for s in db.list_servers() if s["name"] == server_name), None)
    if row is None or not row["enabled"]:
        audit(user, name, server_name, "error", started, "server not available")
        raise ValueError(f"Server '{server_name}' is not available")

    try:
        result = await upstream.call_tool(
            row["url"],
            tool_name,
            arguments or {},
            db.get_server_credential(server_name),
        )
    except asyncio.TimeoutError:
        audit(user, name, server_name, "error", started, "timeout")
        raise RuntimeError(
            f"Server '{server_name}' timed out after {upstream.CALL_TIMEOUT_SECONDS} seconds"
        )
    except Exception as e:
        cause = root_cause(e)
        audit(user, name, server_name, "error", started, cause)
        raise RuntimeError(f"Server '{server_name}' failed: {cause}")

    if result.isError:
        audit(user, name, server_name, "error", started, "upstream tool error")
        text = " ".join(c.text for c in result.content if getattr(c, "text", None))
        raise RuntimeError(text or "The upstream tool returned an error")

    audit(user, name, server_name, "ok", started)
    return list(result.content)


@mcp_server.call_tool()
async def handle_call_tool(name, arguments):
    return await execute_tool(current_user_var.get(), name, arguments)


# One session manager handles all MCP connections. Stateless = no sessions to remember.
session_manager = StreamableHTTPSessionManager(
    app=mcp_server,
    stateless=True,
    json_response=True,
)


class McpAuthApp:
    """Checks the API key, then hands the request to the MCP session manager."""

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return

        headers = dict(scope["headers"])
        auth = headers.get(b"authorization", b"").decode()

        if not auth.startswith("Bearer "):
            response = JSONResponse({"detail": "Missing API key"}, status_code=401)
            await response(scope, receive, send)
            return

        user = db.find_user_by_key(auth[len("Bearer "):])
        if user is None:
            response = JSONResponse({"detail": "Invalid API key"}, status_code=401)
            await response(scope, receive, send)
            return

        token = current_user_var.set(user)
        try:
            await session_manager.handle_request(scope, receive, send)
        finally:
            current_user_var.reset(token)