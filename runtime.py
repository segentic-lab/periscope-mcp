"""Shared singletons for the MCP server: project store, sessions, auth, browser."""
import asyncio
import sys

from auth import AuthHandler
from projects import ProjectManager
from sessions import SessionManager
from tester import WebsiteTester

project_manager = ProjectManager()
auth_handler = AuthHandler()
session_manager = SessionManager()
tester: WebsiteTester | None = None
_tester_lock = asyncio.Lock()


async def get_tester() -> WebsiteTester:
    """Get or create the tester instance, restarting if the browser crashed."""
    global tester
    async with _tester_lock:  # concurrent calls after a crash must not double-launch
        if tester is None or tester.browser is None or not tester.browser.is_connected():
            restarted = tester is not None
            if tester is None:
                tester = WebsiteTester()
            await tester.start()
            if restarted:
                # Every held Page belonged to the dead browser — drop them so
                # session tools return "session not found" instead of "Target closed".
                dropped = len(session_manager.sessions)
                session_manager.clear_all("browser restarted")
                project_manager.reset_login_flags()
                # stderr only: stdout is the MCP protocol channel
                print(f"periscope: browser crashed/disconnected — restarted; "
                      f"{dropped} session(s) dropped, login flags reset", file=sys.stderr)
        return tester


def unknown_project_error(name) -> str | None:
    """Error text when a `project` argument names no project — a typo must
    not silently run in a fresh, logged-out context."""
    if not name or name == "default" or project_manager.get(name) is not None:
        return None
    import difflib
    names = sorted(project_manager.projects)
    close = difflib.get_close_matches(name, names, n=3, cutoff=0.6)
    shown = close + [n for n in names if n not in close][: max(0, 8 - len(close))]
    more = len(names) - len(shown)
    known = (", ".join(shown) + (f" and {more} more (list_projects shows all)" if more > 0
                                 else "")) if names else "none yet (see list_projects)"
    hint = f" Did you mean '{close[0]}'?" if close else ""
    return (f"Project '{name}' not found.{hint} Create it with create_project first, or omit "
            f"'project' for an isolated one-off context. Existing projects: {known}. "
            "list_projects shows them all.")
