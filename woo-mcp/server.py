import os
import httpx
from mcp.server.fastmcp import FastMCP

# Settings come from environment variables, never from the code
STORE_URL = os.environ["STORE_URL"].rstrip("/")
WC_KEY = os.environ["WC_KEY"]
WC_SECRET = os.environ["WC_SECRET"]
PORT = int(os.environ.get("PORT", "8000"))
# Optional: send this Host header to the store (e.g. store.localhost)
STORE_HOST_HEADER = os.environ.get("STORE_HOST_HEADER", "")

mcp = FastMCP("woocommerce", host="0.0.0.0", port=PORT)


async def wc(method, path, **kwargs):
    """Call the WooCommerce REST API and return the JSON."""
    headers = {}
    if STORE_HOST_HEADER:
        headers["Host"] = STORE_HOST_HEADER
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.request(
            method,
            f"{STORE_URL}/wp-json/wc/v3{path}",
            auth=(WC_KEY, WC_SECRET),
            headers=headers,
            **kwargs,
        )
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def list_products(search: str = "", per_page: int = 20) -> list:
    """List products in the store, optionally filtered by a search word."""
    data = await wc("GET", "/products", params={"search": search, "per_page": per_page})
    return [
        {"id": p["id"], "name": p["name"], "price": p["price"], "status": p["status"]}
        for p in data
    ]


@mcp.tool()
async def create_product(name: str, regular_price: str, description: str = "") -> dict:
    """Create and publish a new product. Price is a string such as '499'."""
    p = await wc("POST", "/products", json={
        "name": name,
        "regular_price": regular_price,
        "description": description,
        "status": "publish",
    })
    return {"id": p["id"], "name": p["name"], "price": p["price"], "status": p["status"]}


@mcp.tool()
async def list_orders(status: str = "any", after: str = "", per_page: int = 20) -> list:
    """List orders. 'after' is an ISO date like 2026-10-13T00:00:00 to get recent orders."""
    params = {"status": status, "per_page": per_page}
    if after:
        params["after"] = after
    data = await wc("GET", "/orders", params=params)
    return [
        {"id": o["id"], "status": o["status"], "total": o["total"],
         "date": o["date_created"],
         "customer": f'{o["billing"]["first_name"]} {o["billing"]["last_name"]}'.strip()}
        for o in data
    ]


@mcp.tool()
async def get_order(order_id: int) -> dict:
    """Get full details of one order, including its line items."""
    o = await wc("GET", f"/orders/{order_id}")
    return {
        "id": o["id"], "status": o["status"], "total": o["total"],
        "date": o["date_created"], "payment_method": o["payment_method_title"],
        "items": [{"name": i["name"], "quantity": i["quantity"], "total": i["total"]}
                  for i in o["line_items"]],
    }


@mcp.tool()
async def update_order_status(order_id: int, status: str) -> dict:
    """Change an order's status (for example processing, completed, cancelled)."""
    o = await wc("PUT", f"/orders/{order_id}", json={"status": status})
    return {"id": o["id"], "status": o["status"]}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")