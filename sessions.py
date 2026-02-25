import time
import uuid
from dataclasses import dataclass, field
from playwright.async_api import Page, BrowserContext
import config


@dataclass
class PageSession:
    session_id: str
    project_name: str
    page: Page
    url: str
    created_at: float
    last_accessed: float
    console_log: list = field(default_factory=list)
    console_errors: list = field(default_factory=list)
    network_log: list = field(default_factory=list)
    snapshots: dict = field(default_factory=dict)


class SessionManager:
    """Manages persistent browser page sessions for interactive testing."""

    def __init__(self):
        self.sessions: dict[str, PageSession] = {}

    async def create_session(
        self, context: BrowserContext, url: str, project_name: str = "default"
    ) -> PageSession:
        """Create a new persistent page session."""
        self._cleanup_expired()

        if len(self.sessions) >= config.MAX_SESSIONS:
            self._evict_oldest()

        session_id = uuid.uuid4().hex[:12]
        page = await context.new_page()
        page.set_default_timeout(config.TIMEOUT)

        console_log = []
        console_errors = []
        network_log = []

        def on_console(msg):
            if msg.type == "error":
                console_errors.append(msg.text)
            else:
                console_log.append(msg.text)

        def on_response(response):
            network_log.append({
                "url": response.url,
                "status": response.status,
                "method": response.request.method,
                "resource_type": response.request.resource_type,
                "timestamp": time.time(),
            })

        page.on("console", on_console)
        page.on("pageerror", lambda err: console_errors.append(str(err)))
        page.on("response", on_response)

        await page.goto(url, wait_until="networkidle")

        now = time.time()
        session = PageSession(
            session_id=session_id,
            project_name=project_name,
            page=page,
            url=page.url,
            created_at=now,
            last_accessed=now,
            console_log=console_log,
            console_errors=console_errors,
            network_log=network_log,
        )
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> PageSession:
        """Get a session by ID, updating last_accessed. Raises KeyError if not found or expired."""
        self._cleanup_expired()
        if session_id not in self.sessions:
            raise KeyError(f"Session '{session_id}' not found or expired")
        session = self.sessions[session_id]
        session.last_accessed = time.time()
        return session

    async def close_session(self, session_id: str) -> bool:
        """Close a session and free its resources. Returns True if found."""
        if session_id in self.sessions:
            session = self.sessions.pop(session_id)
            try:
                await session.page.close()
            except Exception:
                pass
            return True
        return False

    def list_sessions(self) -> list[dict]:
        """Return summary info for all active sessions."""
        self._cleanup_expired()
        now = time.time()
        result = []
        for s in self.sessions.values():
            result.append({
                "session_id": s.session_id,
                "project_name": s.project_name,
                "url": s.url,
                "created_at": s.created_at,
                "idle_seconds": round(now - s.last_accessed),
                "console_errors": len(s.console_errors),
            })
        return result

    def _cleanup_expired(self):
        """Remove sessions that have been idle longer than SESSION_TIMEOUT."""
        now = time.time()
        expired = [
            sid for sid, s in self.sessions.items()
            if now - s.last_accessed > config.SESSION_TIMEOUT
        ]
        for sid in expired:
            session = self.sessions.pop(sid)
            try:
                # Schedule close but don't await — we're in a sync method
                import asyncio
                asyncio.get_event_loop().create_task(session.page.close())
            except Exception:
                pass

    def _evict_oldest(self):
        """Evict the oldest (least recently accessed) session to make room."""
        if not self.sessions:
            return
        oldest_id = min(self.sessions, key=lambda sid: self.sessions[sid].last_accessed)
        session = self.sessions.pop(oldest_id)
        try:
            import asyncio
            asyncio.get_event_loop().create_task(session.page.close())
        except Exception:
            pass
