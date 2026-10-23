import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.environ.get("DB_PATH", "gateway.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'member')),
            key_hash TEXT UNIQUE NOT NULL,
            key_prefix TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            url TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            user_id INTEGER,
            user_name TEXT NOT NULL,
            tool TEXT NOT NULL,
            server TEXT,
            status TEXT NOT NULL,
            duration_ms INTEGER NOT NULL,
            error TEXT
        )
        """
    )
    # Upgrade older databases: add the credential column if it is missing
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(servers)").fetchall()]
    if "credential" not in cols:
        conn.execute("ALTER TABLE servers ADD COLUMN credential TEXT")
    conn.commit()
    conn.close()


# ---------- users ----------

def generate_key():
    return "urumi_" + secrets.token_urlsafe(32)


def hash_key(key):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def count_users():
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return n


def create_user(name, role):
    """Creates a user. Returns a dict that includes the real api_key (shown once)."""
    key = generate_key()
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO users (name, role, key_hash, key_prefix, active, created_at) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            (name, role, hash_key(key), key[:10], now()),
        )
        conn.commit()
        user_id = cur.lastrowid
    finally:
        conn.close()
    return {"id": user_id, "name": name, "role": role, "api_key": key}


def find_user_by_key(key):
    """Returns the user (as a dict) if the key is valid and the user is active, else None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, name, role FROM users WHERE key_hash = ? AND active = 1",
        (hash_key(key),),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_users():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, role, key_prefix, active, created_at FROM users ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def rotate_own_key(user_id):
    """Issues a new API key for an active user and invalidates the old one.
    Returns the new key (shown once), or None if the user is not active."""
    key = generate_key()
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE users SET key_hash = ?, key_prefix = ? WHERE id = ? AND active = 1",
            (hash_key(key), key[:10], user_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
    finally:
        conn.close()
    return key


def revoke_user(user_id):
    """Returns 'ok', 'not_found' or 'last_admin'."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT role, active FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return "not_found"
        if row["role"] == "admin" and row["active"]:
            n = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1"
            ).fetchone()[0]
            if n <= 1:
                return "last_admin"
        conn.execute("UPDATE users SET active = 0 WHERE id = ?", (user_id,))
        conn.commit()
        return "ok"
    finally:
        conn.close()


# ---------- upstream MCP servers ----------

# The credential itself is never selected here, only a true/false flag.
_SERVER_COLS = (
    "id, name, url, enabled, created_at, "
    "(credential IS NOT NULL AND credential != '') AS has_credential"
)


def _server_dict(row):
    d = dict(row)
    d["has_credential"] = bool(d["has_credential"])
    return d


def create_server(name, url):
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO servers (name, url, enabled, created_at) VALUES (?, ?, 1, ?)",
            (name, url, now()),
        )
        conn.commit()
        server_id = cur.lastrowid
    finally:
        conn.close()
    return get_server(server_id)


def get_server(server_id):
    conn = get_conn()
    row = conn.execute(
        f"SELECT {_SERVER_COLS} FROM servers WHERE id = ?", (server_id,)
    ).fetchone()
    conn.close()
    return _server_dict(row) if row else None


def list_servers():
    conn = get_conn()
    rows = conn.execute(f"SELECT {_SERVER_COLS} FROM servers ORDER BY id").fetchall()
    conn.close()
    return [_server_dict(r) for r in rows]


def set_server_enabled(server_id, enabled):
    """Returns True if a server was changed, False if the id does not exist."""
    conn = get_conn()
    cur = conn.execute(
        "UPDATE servers SET enabled = ? WHERE id = ?",
        (1 if enabled else 0, server_id),
    )
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed


def delete_server(server_id):
    """Returns True if a server was deleted, False if the id does not exist."""
    conn = get_conn()
    cur = conn.execute("DELETE FROM servers WHERE id = ?", (server_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def update_server(server_id, changes):
    """changes may hold name, url, credential. An empty credential clears it.
    Returns the updated server, or None if the id does not exist."""
    sets, vals = [], []
    for key in ("name", "url", "credential"):
        if key in changes:
            value = changes[key]
            if key == "credential" and value == "":
                value = None
            sets.append(f"{key} = ?")
            vals.append(value)
    if sets:
        conn = get_conn()
        try:
            cur = conn.execute(
                f"UPDATE servers SET {', '.join(sets)} WHERE id = ?",
                (*vals, server_id),
            )
            conn.commit()
            if cur.rowcount == 0:
                return None
        finally:
            conn.close()
    return get_server(server_id)


def get_server_credential(name):
    """Internal use only (upstream calls). Never return this to a client."""
    conn = get_conn()
    row = conn.execute(
        "SELECT credential FROM servers WHERE name = ?", (name,)
    ).fetchone()
    conn.close()
    return row["credential"] if row and row["credential"] else None


# ---------- audit log ----------

def add_audit(user, tool, server, status, duration_ms, error=None):
    """Records one tool call. Never stores arguments or results."""
    conn = get_conn()
    conn.execute(
        "INSERT INTO audit_log (ts, user_id, user_name, tool, server, status, duration_ms, error) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            now(),
            user["id"] if user else None,
            user["name"] if user else "unknown",
            tool,
            server,
            status,
            duration_ms,
            error,
        ),
    )
    conn.commit()
    conn.close()


def list_audit(limit=100):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, ts, user_name, tool, server, status, duration_ms, error "
        "FROM audit_log ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]