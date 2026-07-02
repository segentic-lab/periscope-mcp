"""Shared singletons for the MCP server: project store, sessions, auth, browser."""
import asyncio

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
                session_manager.clear_all("browser restarted")
                project_manager.reset_login_flags()
        return tester
