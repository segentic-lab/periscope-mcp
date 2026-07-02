"""Handler registry: maps tool names to their async handler functions."""
HANDLERS = {}


def tool(name: str):
    """Register an async handler for an MCP tool name."""
    def deco(fn):
        HANDLERS[name] = fn
        return fn
    return deco
