import os
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

PORT = int(os.environ.get("PORT", "8000"))
mcp = FastMCP("notes", host="0.0.0.0", port=PORT)

# In memory on purpose: the demo server needs no database
NOTES = []


@mcp.tool()
def add_note(text: str) -> dict:
    """Save a short note and return it with its id."""
    note = {
        "id": len(NOTES) + 1,
        "text": text,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    NOTES.append(note)
    return note


@mcp.tool()
def list_notes() -> list:
    """List all saved notes."""
    return NOTES


@mcp.tool()
def search(query: str) -> list:
    """Search saved notes for a word or phrase."""
    q = query.lower()
    return [n for n in NOTES if q in n["text"].lower()]


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
