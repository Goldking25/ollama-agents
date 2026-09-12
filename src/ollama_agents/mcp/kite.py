"""MCP integration for Zerodha Kite — standalone async prototype.

Credentials are read from environment variables. Set them before running:
    $env:KITE_API_KEY    = "your_key"
    $env:KITE_API_SECRET = "your_secret"
"""

import asyncio
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run_mcp_kite_agent() -> None:
    api_key = os.environ.get("KITE_API_KEY")
    api_secret = os.environ.get("KITE_API_SECRET")

    if not api_key or not api_secret:
        raise EnvironmentError(
            "KITE_API_KEY and KITE_API_SECRET must be set as environment variables."
        )

    server_params = StdioServerParameters(
        command="go",
        args=["run", "main.go"],  # or path to pre-built kite-mcp-server binary
        env={
            "KITE_API_KEY": api_key,
            "KITE_API_SECRET": api_secret,
        },
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. Discover all tools provided by the Kite MCP server dynamically
            tools_list = await session.list_tools()
            print(f"Available Kite MCP Tools: {[t.name for t in tools_list.tools]}")

            # 2. Call an MCP tool directly through the standard interface
            quote = await session.call_tool(
                "get_ltp",
                arguments={"instruments": ["NSE:TATASTEEL"]},
            )
            print("LTP Result:", quote.content)


if __name__ == "__main__":
    asyncio.run(run_mcp_kite_agent())