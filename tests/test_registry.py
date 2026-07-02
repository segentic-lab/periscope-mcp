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
