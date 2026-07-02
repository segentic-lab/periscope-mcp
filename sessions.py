import asyncio
import time
import uuid
from dataclasses import dataclass, field
from playwright.async_api import Page, BrowserContext
import config


@dataclass
class PageSession:
    session_id: str
    project_name: str
    page: Page  # a Page, or a Frame for iframe sessions (see real_page())
    url: str
    created_at: float
    last_accessed: float
    console_log: list = field(default_factory=list)
    console_errors: list = field(default_factory=list)
    network_log: list = field(default_factory=list)
    response_bodies: list = field(default_factory=list)
    snapshots: dict = field(default_factory=dict)
    screenshot_dir: str = None
    intercepts: list = field(default_factory=list)  # active intercept routes: {matcher, handler, pattern}
    cdp_session: object = None  # cached CDP session for network emulation
    parent_session_id: str = None  # set on iframe sessions: the page session owning the frame
    own_context: object = None  # set on project-less sessions: their private context, closed with them


def real_page(page_or_frame) -> Page:
    """Return the owning Page. Iframe sessions store a Frame in .page;
    Page-level APIs (screenshot, context, history, routing) need the real Page."""
    return page_or_frame if isinstance(page_or_frame, Page) else page_or_frame.page


def _capped_append(buf: list, item, cap: int):
    buf.append(item)
    if len(buf) > cap:
        del buf[: len(buf) - cap]


class SessionManager:
    """Manages persistent browser page sessions for interactive testing."""

    def __init__(self):
        self.sessions: dict[str, PageSession] = {}
        self.recent_removals: list[dict] = []  # last few evicted/expired sessions, for debugging
        self._pending_closes: set = set()

    def _record_removal(self, session: PageSession, reason: str):
        self.recent_removals.append({
            "session_id": session.session_id,
            "url": session.url,
            "reason": reason,
            "at": time.time(),
        })
        # Keep enough history that a busy agent can still learn why an older
        # session id stopped working.
        del self.recent_removals[:-20]

    def _schedule_close(self, session: PageSession):
        """Fire-and-forget page close from sync context, holding a task ref so it isn't GC'd."""
        close = getattr(session.page, "close", None)  # Frame (iframe session) has no close()
        own_context = session.own_context
        if close is None and own_context is None:
            return
        async def _close():
            try:
                if close is not None:
                    await close()
            except Exception:
                pass
            if own_context is not None:
                try:
                    await own_context.close()
                except Exception:
                    pass
        try:
            task = asyncio.get_running_loop().create_task(_close())
            self._pending_closes.add(task)
            task.add_done_callback(self._pending_closes.discard)
        except RuntimeError:
            pass

    async def create_session(
        self, context: BrowserContext, url: str, project_name: str = "default", screenshot_dir: str = None
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
        response_bodies = []

        def on_console(msg):
            if msg.type == "error":
                _capped_append(console_errors, msg.text, config.MAX_CONSOLE_LOG)
            else:
                _capped_append(console_log, msg.text, config.MAX_CONSOLE_LOG)

        async def on_response(response):
            _capped_append(network_log, {
                "url": response.url,
                "status": response.status,
                "method": response.request.method,
                "resource_type": response.request.resource_type,
                "timestamp": time.time(),
            }, config.MAX_NETWORK_LOG)
            # Capture response bodies for fetch/xhr/document requests
            if response.request.resource_type in ("fetch", "xhr", "document"):
                try:
                    body = await response.text()
                    if len(body) > config.MAX_RESPONSE_BODY_SIZE:
                        body = body[:config.MAX_RESPONSE_BODY_SIZE] + "... [truncated]"
                    content_type = response.headers.get("content-type", "")
                    response_bodies.append({
                        "url": response.url,
                        "status": response.status,
                        "method": response.request.method,
                        "content_type": content_type,
                        "body_text": body,
                        "timestamp": time.time(),
                    })
                    if len(response_bodies) > config.MAX_RESPONSE_BODIES:
                        response_bodies.pop(0)
                except Exception:
                    pass

        page.on("console", on_console)
        page.on("pageerror", lambda err: _capped_append(console_errors, str(err), config.MAX_CONSOLE_LOG))
        page.on("response", on_response)

        try:
            await page.goto(url, wait_until=config.WAIT_UNTIL)
        except Exception:
            # Not yet registered in self.sessions — close it or it leaks in the context.
            await page.close()
            raise

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
            response_bodies=response_bodies,
            screenshot_dir=screenshot_dir,
        )
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> PageSession:
        """Get a session by ID, updating last_accessed. Raises KeyError if not found or expired."""
        self._cleanup_expired()
        if session_id not in self.sessions:
            # Tell the caller what actually happened — "expired" was a lie for
            # evictions and browser restarts and sent agents down wrong paths.
            removal = next(
                (r for r in reversed(self.recent_removals) if r["session_id"] == session_id),
                None,
            )
            if removal is None:
                detail = "unknown session id"
            elif removal["reason"] == "expired":
                detail = f"it idle-expired (limit: {config.SESSION_TIMEOUT}s, env-overridable via SESSION_TIMEOUT)"
            elif removal["reason"] == "browser restarted":
                detail = ("the browser crashed and was restarted — all sessions and login "
                          "state were lost; re-run login_project if the project needs auth")
            else:
                detail = f"it was removed: {removal['reason']} (session cap: {config.MAX_SESSIONS}, env-overridable via MAX_SESSIONS)"
            raise KeyError(
                f"Session '{session_id}' not found — {detail}. "
                f"Open a new one with open_session."
            )
        session = self.sessions[session_id]
        session.last_accessed = time.time()
        # Using an iframe session must keep its owning page session alive too.
        if session.parent_session_id and session.parent_session_id in self.sessions:
            self.sessions[session.parent_session_id].last_accessed = session.last_accessed
        return session

    def register_session(self, session: PageSession):
        """Register an externally built session (e.g. an iframe scope from
        select_iframe), enforcing the same limits as create_session."""
        self._cleanup_expired()
        if len(self.sessions) >= config.MAX_SESSIONS:
            self._evict_oldest()
        self.sessions[session.session_id] = session

    async def close_session(self, session_id: str) -> bool:
        """Close a session and free its resources. Returns True if found."""
        if session_id in self.sessions:
            session = self.sessions.pop(session_id)
            self._remove_children(session_id, "parent session closed")
            try:
                await session.page.close()
            except Exception:
                pass
            if session.own_context is not None:
                try:
                    await session.own_context.close()
                except Exception:
                    pass
            return True
        return False

    def clear_all(self, reason: str = "browser restarted"):
        """Drop all sessions without closing pages — used after a browser
        crash/restart, when every held Page belongs to the dead browser."""
        for sid in list(self.sessions):
            self._record_removal(self.sessions.pop(sid), reason)

    def _remove_children(self, parent_id: str, reason: str):
        """Drop iframe sessions scoped to a removed parent — their Frame dies with it."""
        for sid, child in list(self.sessions.items()):
            if child.parent_session_id == parent_id:
                self._record_removal(self.sessions.pop(sid), reason)

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
            session = self.sessions.pop(sid, None)
            if session is None:  # already removed as a child of an earlier expiry
                continue
            self._record_removal(session, "expired")
            self._remove_children(sid, "parent session expired")
            self._schedule_close(session)

    def _evict_oldest(self):
        """Evict the oldest (least recently accessed) session to make room."""
        if not self.sessions:
            return
        oldest_id = min(self.sessions, key=lambda sid: self.sessions[sid].last_accessed)
        session = self.sessions.pop(oldest_id)
        self._record_removal(session, "evicted (MAX_SESSIONS reached)")
        self._remove_children(oldest_id, "parent session evicted")
        self._schedule_close(session)
