import asyncio
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = os.environ.get("GW_URL", "http://localhost:9000/mcp")


async def main():
    key = os.environ.get("GW_KEY", "")
    headers = {"Authorization": f"Bearer {key}"}

    async with streamablehttp_client(URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("TOOLS SEEN THROUGH THE GATEWAY:")
            for t in tools.tools:
                print("  -", t.name)

            print()
            print("CALLING woo__list_products ...")
            result = await session.call_tool("woo__list_products", {})
            for item in result.content:
                print(getattr(item, "text", item)[:600])


asyncio.run(main())