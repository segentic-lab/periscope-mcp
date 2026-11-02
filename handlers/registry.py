"""Handler registry: maps tool names to their async handler functions."""
import functools

HANDLERS = {}


def tool(name: str):
    """Register an async handler for an MCP tool name. The registered callable
    stamps `nav_generation` (the session's main-frame navigation count) onto
    every dict result for a live session_id, so an agent can notice "I'm not
    on the page I think I am" without an extra call."""
    def deco(fn):
        @functools.wraps(fn)
        async def wrapped(args: dict) -> dict:
            result = await fn(args)
            _stamp_session_generation(args, result)
            return result
        HANDLERS[name] = wrapped
        return wrapped
    return deco


def _stamp_session_generation(args, result) -> None:
    """Never raises — a bookkeeping field must not take a tool call down."""
    try:
        sid = args.get("session_id") if isinstance(args, dict) else None
        if not sid or not isinstance(result, dict) or "nav_generation" in result:
            return
        from runtime import session_manager
        session = session_manager.sessions.get(sid)
        if session is None:
            return
        # Iframe sessions hold a Frame: the owning page session carries the count.
        if session.parent_session_id and not hasattr(session.page, "main_frame"):
            parent = session_manager.sessions.get(session.parent_session_id)
            if parent is not None:
                session = parent
        result["nav_generation"] = session.nav_generation
    except Exception:
        pass
