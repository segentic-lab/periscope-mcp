"""Periscope MCP server — stdio entry point.

Tool schemas live in tool_schemas.py, handlers in handlers/, shared state in runtime.py.

Copyright (C) 2026 Sebastijan Bandur
Licensed under the GNU Affero General Public License v3.0 (see LICENSE).
"""
import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from _version import __version__
from coercion import coerce_args
from handlers import HANDLERS
from tool_schemas import TOOLS

server = Server("periscope", version=__version__)


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    import time as _time
    import journal
    start = _time.time()
    try:
        coerce_args(arguments)
        handler = HANDLERS.get(name)
        if handler is None:
            result = {"success": False, "error": f"Unknown tool: {name}"}
        else:
            result = await handler(arguments)
        journal.record(name, arguments, result, round((_time.time() - start) * 1000))
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        # str(KeyError) wraps the message in repr quotes — unwrap via args.
        message = e.args[0] if isinstance(e, KeyError) and e.args else str(e)
        journal.record(name, arguments, None, round((_time.time() - start) * 1000), error=message)
        return [TextContent(type="text", text=json.dumps({"success": False, "error": message}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
