"""WebsiteTesterAI MCP server — stdio entry point.

Tool schemas live in tool_schemas.py, handlers in handlers/, shared state in runtime.py.
"""
import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from coercion import coerce_args
from handlers import HANDLERS
from tool_schemas import TOOLS

server = Server("website-tester")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        coerce_args(arguments)
        handler = HANDLERS.get(name)
        if handler is None:
            result = {"error": f"Unknown tool: {name}"}
        else:
            result = await handler(arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
