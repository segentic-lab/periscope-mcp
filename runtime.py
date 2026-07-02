"""Shared singletons for the MCP server: project store, sessions, auth, browser."""
from auth import AuthHandler
from projects import ProjectManager
from sessions import SessionManager
from tester import WebsiteTester

project_manager = ProjectManager()
auth_handler = AuthHandler()
session_manager = SessionManager()
tester: WebsiteTester | None = None


async def get_tester() -> WebsiteTester:
    """Get or create the tester instance, restarting if the browser crashed."""
    global tester
    if tester is None or tester.browser is None or not tester.browser.is_connected():
        if tester is None:
            tester = WebsiteTester()
        await tester.start()
    return tester
