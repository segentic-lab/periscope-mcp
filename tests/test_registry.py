"""Every tool schema has a handler and vice versa."""
from handlers import HANDLERS
from tool_schemas import TOOLS


def test_schema_handler_parity():
    schema_names = {t.name for t in TOOLS}
    handler_names = set(HANDLERS)
    assert schema_names == handler_names, (
        f"schema-only: {sorted(schema_names - handler_names)}, "
        f"handler-only: {sorted(handler_names - schema_names)}"
    )


def test_no_duplicate_tool_names():
    names = [t.name for t in TOOLS]
    assert len(names) == len(set(names))


def test_all_schemas_have_descriptions():
    for t in TOOLS:
        assert t.description, f"{t.name} has no description"
        assert t.inputSchema.get("type") == "object", t.name


def test_catalog_mentions_every_tool():
    """describe_tools must not drift: every registered tool appears in the catalog."""
    import asyncio
    from handlers import HANDLERS
    cat = asyncio.new_event_loop().run_until_complete(HANDLERS["describe_tools"]({}))
    listed = set()
    for c in cat["catalog"].values():
        for name in c["tools"]:
            listed.add(name.split(" ")[0])
    missing = sorted(set(HANDLERS) - listed)
    assert not missing, f"tools missing from describe_tools catalog: {missing}"
    assert cat["total_tools"] == len(HANDLERS)
