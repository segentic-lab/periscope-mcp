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
