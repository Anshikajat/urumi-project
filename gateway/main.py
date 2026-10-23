import sqlite3
from contextlib import asynccontextmanager
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from starlette.routing import Route

import chat
import db
import mcp_endpoint
import upstream

bearer = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    if db.count_users() == 0:
        admin = db.create_user("admin", "admin")
        print("=" * 60, flush=True)
        print("FIRST ADMIN CREATED. Save this key now, it is shown only once:", flush=True)
        print(admin["api_key"], flush=True)
        print("=" * 60, flush=True)
    async with mcp_endpoint.session_manager.run():
        yield


app = FastAPI(title="Urumi MCP Gateway", lifespan=lifespan)

# The one MCP endpoint for all clients: http://localhost:9000/mcp
app.router.routes.append(Route("/mcp", endpoint=mcp_endpoint.McpAuthApp()))


# ---------- authentication ----------

def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    if creds is None:
        raise HTTPException(status_code=401, detail="Missing API key")
    user = db.find_user_by_key(creds.credentials)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user


def require_admin(user: dict = Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


# ---------- request bodies ----------

class NewUser(BaseModel):
    name: str
    role: Literal["admin", "member"] = "member"


class NewServer(BaseModel):
    # lowercase letters and digits only, so tool names like woo__list_orders stay unambiguous
    name: str = Field(pattern=r"^[a-z][a-z0-9]{0,30}$")
    url: str = Field(pattern=r"^https?://.+")


class ServerUpdate(BaseModel):
    name: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9]{0,30}$")
    url: str | None = Field(default=None, pattern=r"^https?://.+")
    # An empty string clears the credential
    credential: str | None = Field(default=None, max_length=2000)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)


# ---------- basic endpoints ----------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/me")
def me(user: dict = Depends(current_user)):
    return user


@app.post("/me/key")
def rotate_my_key(user: dict = Depends(current_user)):
    """Any user can issue themselves a new key. The old key stops working at once."""
    key = db.rotate_own_key(user["id"])
    if key is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return {"api_key": key}


# ---------- users (admin only) ----------

@app.get("/users")
def get_users(admin: dict = Depends(require_admin)):
    return db.list_users()


@app.post("/users")
def add_user(body: NewUser, admin: dict = Depends(require_admin)):
    try:
        return db.create_user(body.name, body.role)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="A user with that name already exists")


@app.post("/users/{user_id}/revoke")
def revoke_user(user_id: int, admin: dict = Depends(require_admin)):
    result = db.revoke_user(user_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="User not found")
    if result == "last_admin":
        raise HTTPException(status_code=409, detail="Cannot revoke the last active admin")
    return {"revoked": user_id}


# ---------- upstream MCP servers ----------

@app.get("/servers")
def get_servers(user: dict = Depends(current_user)):
    return db.list_servers()


@app.post("/servers")
def add_server(body: NewServer, admin: dict = Depends(require_admin)):
    try:
        return db.create_server(body.name, body.url)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="A server with that name already exists")


@app.post("/servers/{server_id}/enable")
def enable_server(server_id: int, admin: dict = Depends(require_admin)):
    if not db.set_server_enabled(server_id, True):
        raise HTTPException(status_code=404, detail="Server not found")
    return db.get_server(server_id)


@app.post("/servers/{server_id}/disable")
def disable_server(server_id: int, admin: dict = Depends(require_admin)):
    if not db.set_server_enabled(server_id, False):
        raise HTTPException(status_code=404, detail="Server not found")
    return db.get_server(server_id)


@app.patch("/servers/{server_id}")
def edit_server(server_id: int, body: ServerUpdate, admin: dict = Depends(require_admin)):
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    try:
        server = db.update_server(server_id, changes)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="A server with that name already exists")
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")
    return server


@app.delete("/servers/{server_id}")
def remove_server(server_id: int, admin: dict = Depends(require_admin)):
    if not db.delete_server(server_id):
        raise HTTPException(status_code=404, detail="Server not found")
    return {"deleted": server_id}


# ---------- tool discovery (REST view, same data as the MCP endpoint) ----------

@app.get("/tools")
async def get_tools(user: dict = Depends(current_user)):
    servers, tools = await upstream.collect_tools()
    return {"servers": servers, "tools": tools}


# ---------- audit log (admin only) ----------

@app.get("/audit")
def get_audit(limit: int = 100, admin: dict = Depends(require_admin)):
    limit = max(1, min(limit, 500))
    return db.list_audit(limit)


# ---------- chat agent (acts as the logged-in user) ----------

@app.post("/chat")
async def chat_endpoint(body: ChatRequest, user: dict = Depends(current_user)):
    if body.messages[-1].role != "user":
        raise HTTPException(status_code=422, detail="The last message must be from the user")
    try:
        reply, calls = await chat.run_chat(user, [m.model_dump() for m in body.messages])
    except chat.ChatNotConfigured:
        raise HTTPException(
            status_code=503,
            detail="Chat is not configured: the gateway has no Gemini API key",
        )
    except chat.ChatError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Could not reach the Gemini API")
    return {"reply": reply, "tool_calls": calls}