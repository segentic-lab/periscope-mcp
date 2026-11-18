"""Periscope MCP server — stdio entry point.

Tool schemas live in tool_schemas.py, handlers in handlers/, shared state in runtime.py.

Speaks both lines of the official `mcp` Python SDK:
- 2.x (primary): handlers are passed to the low-level `Server` constructor
  (`on_list_tools` / `on_call_tool`) and return result models.
- 1.x (fallback): the `@server.list_tools()` / `@server.call_tool()` decorators.
`call_tool(name, arguments)` below is the single SDK-neutral dispatch both use.

Copyright (C) 2026 Sebastijan Bandur
Licensed under the GNU Affero General Public License v3.0 (see LICENSE).
"""
import asyncio
import inspect
import json
import time

from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

try:  # 2.x and late 1.x expose the low-level server here
    from mcp.server.lowlevel import Server
except ImportError:  # early 1.x
    from mcp.server import Server

import journal
from _version import __version__
from coercion import coerce_args
from handlers import HANDLERS
from tool_schemas import TOOLS

# 2.x takes request handlers as constructor arguments; 1.x registers them
# with decorators. Detect by signature, not by version string.
_SDK2 = "on_call_tool" in inspect.signature(Server.__init__).parameters


async def list_tools() -> list[Tool]:
    return TOOLS


async def call_tool(name: str, arguments: dict | None) -> list[TextContent]:
    """Dispatch one tool call: coerce args, run the handler, journal the call.
    Never raises — failures come back as {"success": false, "error": ...}."""
    arguments = arguments if isinstance(arguments, dict) else {}
    start = time.time()
    try:
        coerce_args(arguments, name)
        handler = HANDLERS.get(name)
        if handler is None:
            result = {"success": False, "error": f"Unknown tool: {name}"}
        else:
            result = await handler(arguments)
        journal.record(name, arguments, result, round((time.time() - start) * 1000))
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except Exception as e:
        # str(KeyError) wraps the message in repr quotes — unwrap via args.
        message = e.args[0] if isinstance(e, KeyError) and e.args else str(e)
        journal.record(name, arguments, None, round((time.time() - start) * 1000), error=str(message))
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(message)}))]


def _build_server() -> Server:
    if _SDK2:
        from mcp.types import CallToolResult, ListToolsResult

        async def on_list_tools(_ctx, _params):
            return ListToolsResult(tools=TOOLS)

        async def on_call_tool(_ctx, params):
            return CallToolResult(content=await call_tool(params.name, params.arguments))

        return Server("periscope", version=__version__,
                      on_list_tools=on_list_tools, on_call_tool=on_call_tool)

    srv = Server("periscope", version=__version__)
    srv.list_tools()(list_tools)
    # validate_input=False: coerce_args accepts JSON-string arrays/bools from
    # clients with stale schemas, which strict schema validation would reject.
    try:
        srv.call_tool(validate_input=False)(call_tool)
    except TypeError:  # older 1.x without the validate_input switch
        srv.call_tool()(call_tool)
    return srv


server = _build_server()


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
