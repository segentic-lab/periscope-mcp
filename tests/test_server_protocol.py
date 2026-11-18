"""Real MCP round trip over stdio: spawn server.py, initialize, list tools,
call a tool. Runs against whichever mcp SDK is installed (1.x or 2.x) — this
is the test that catches an SDK line the server can't speak."""
import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def _roundtrip(tmp_data: str):
    params = StdioServerParameters(
        command=sys.executable, args=[os.path.join(ROOT, "server.py")],
        env={**os.environ, "PERISCOPE_DATA_DIR": tmp_data})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            ok = await session.call_tool("describe_tools", {"category": "system"})
            bad = await session.call_tool("no_such_tool", {})
            coerced = await session.call_tool("flow", {"action": "list"})
            return tools, ok, bad, coerced


def test_stdio_roundtrip(tmp_path):
    tools, ok, bad, coerced = asyncio.run(asyncio.wait_for(_roundtrip(str(tmp_path)), 60))
    names = {t.name for t in tools.tools}
    assert len(names) >= 79 and {"open_session", "compare_pages", "describe_tools"} <= names
    schema = tools.tools[0].model_dump(by_alias=True)["inputSchema"]
    assert schema.get("type") == "object"

    payload = json.loads(ok.content[0].text)
    assert payload["total_tools"] == len(names) and "system" in payload["catalog"]

    err = json.loads(bad.content[0].text)
    assert err["success"] is False and "Unknown tool" in err["error"]

    assert json.loads(coerced.content[0].text)["success"] is True
