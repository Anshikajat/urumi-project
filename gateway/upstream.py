import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

import db

TIMEOUT_SECONDS = 10        # for discovering tools
CALL_TIMEOUT_SECONDS = 30   # for running one tool


def _auth_headers(credential):
    """If the server has a stored credential, send it as a Bearer token.
    Servers that do not need one simply ignore the header."""
    if credential:
        return {"Authorization": f"Bearer {credential}"}
    return None


# ---------- discovery ----------

async def _list_tools(url, credential=None):
    async with streamablehttp_client(url, headers=_auth_headers(credential)) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "inputSchema": t.inputSchema,
                }
                for t in result.tools
            ]


async def discover_tools(url, credential=None):
    """Connects to one upstream MCP server and returns its tools.
    Raises asyncio.TimeoutError if it takes longer than TIMEOUT_SECONDS."""
    return await asyncio.wait_for(_list_tools(url, credential), timeout=TIMEOUT_SECONDS)


async def discover_one(server):
    """Asks one upstream for its tools. Never raises: failures become status 'down'."""
    try:
        credential = db.get_server_credential(server["name"])
        tools = await discover_tools(server["url"], credential)
        return {"server": server["name"], "status": "up", "tools": tools, "error": None}
    except asyncio.TimeoutError:
        error = f"timed out after {TIMEOUT_SECONDS} seconds"
    except Exception as e:
        error = f"{type(e).__name__}: {str(e)[:200]}"
    return {"server": server["name"], "status": "down", "tools": [], "error": error}


async def collect_tools():
    """Asks all enabled upstreams at the same time.
    Returns (servers, tools) with tool names prefixed like woo__list_orders."""
    enabled = [s for s in db.list_servers() if s["enabled"]]
    results = await asyncio.gather(*[discover_one(s) for s in enabled])

    servers = []
    tools = []
    for r in results:
        servers.append(
            {
                "server": r["server"],
                "status": r["status"],
                "tool_count": len(r["tools"]),
                "error": r["error"],
            }
        )
        for t in r["tools"]:
            tools.append(
                {
                    "name": f"{r['server']}__{t['name']}",
                    "server": r["server"],
                    "original_name": t["name"],
                    "description": t["description"],
                    "inputSchema": t["inputSchema"],
                }
            )
    return servers, tools


# ---------- calling a tool ----------

async def _call_tool(url, tool_name, arguments, credential=None):
    async with streamablehttp_client(url, headers=_auth_headers(credential)) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(tool_name, arguments)


async def call_tool(url, tool_name, arguments, credential=None):
    """Runs one tool on one upstream.
    Raises asyncio.TimeoutError if it takes longer than CALL_TIMEOUT_SECONDS."""
    return await asyncio.wait_for(
        _call_tool(url, tool_name, arguments, credential), timeout=CALL_TIMEOUT_SECONDS
    )