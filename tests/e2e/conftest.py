"""E2E fixtures: a shared event loop, the real browser, and two local HTTP
servers serving the fixture pages — one GEO/SEO-compliant origin, one hostile.

Requires a Chromium: Playwright's bundled build (CI installs it) or a system
one via CHROMIUM_PATH.
"""
import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

GOOD_ROBOTS = "User-agent: *\nDisallow: /admin/\n"
BAD_ROBOTS = """User-agent: GPTBot
Disallow: /

User-agent: ClaudeBot
Disallow: /

User-agent: PerplexityBot
Disallow: /

User-agent: Googlebot
Disallow: /

User-agent: *
Disallow: /admin/
"""
GOOD_LLMS = "# Fixture Site\n\n> Pages for Periscope's e2e tests.\n\n## Docs\n- [App](/app.html)\n"
BAD_LLMS = "just some text without any heading\n"


class _FixtureHandler(BaseHTTPRequestHandler):
    """Serves tests/e2e/fixtures plus origin files and a small JSON API."""
    mode = "good"

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/robots.txt":
            return self._text(GOOD_ROBOTS if self.mode == "good" else BAD_ROBOTS)
        if path == "/llms.txt":
            return self._text(GOOD_LLMS if self.mode == "good" else BAD_LLMS)
        if path == "/api/items":
            return self._text(json.dumps({"items": [1, 2, 3]}), "application/json")
        if path == "/submit":
            return self._text("<html><body>submitted</body></html>", "text/html")

        # --- form-login protected area (auth expiry / issue #11 tests) ------
        if path in ("/app", "/app/page2"):
            if "sid=ok" not in (self.headers.get("Cookie") or ""):
                self.send_response(302)
                self.send_header("Location", f"/login.html?callbackUrl={path}")
                self.end_headers()
                return
            link = '<a href="/app/page2">Page 2</a>' if path == "/app" else ""
            return self._text(
                f'<html lang="en"><head><title>Protected App Area Page</title></head>'
                f'<body><h1>App</h1>{link}</body></html>', "text/html")
        if path == "/do-login":
            from urllib.parse import parse_qs, urlparse as _up
            params = parse_qs(_up(self.path).query)
            if params.get("password", [""])[0] == "pw":
                self.send_response(302)
                self.send_header("Set-Cookie", "sid=ok; Path=/")
                self.send_header("Location", "/app")
            else:
                self.send_response(302)
                self.send_header("Location", "/login.html?error=1")
            self.end_headers()
            return
        file_path = os.path.join(FIXTURES, path.lstrip("/"))
        if os.path.isfile(file_path):
            import mimetypes
            with open(file_path, "rb") as f:
                body = f.read()
            ctype = mimetypes.guess_type(file_path)[0] or "text/html"
            self.send_response(200)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8" if ctype.startswith("text/") else ctype)
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_HEAD(self):
        # Mirror GET's notion of existence — a blanket 200 would hide 404s
        # from checks that verify resources via HEAD (e.g. lazy images).
        path = self.path.split("?")[0]
        known = {"/robots.txt", "/llms.txt", "/api/items", "/submit", "/app", "/app/page2", "/do-login"}
        if path in known or os.path.isfile(os.path.join(FIXTURES, path.lstrip("/"))):
            self.send_response(200)
        else:
            self.send_response(404)
        self.end_headers()

    def _text(self, body: str, content_type: str = "text/plain"):
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        # Downloads need a correct Content-Length for Chromium to finalize the
        # artifact (without it the download "completes" with a missing file).
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def _start_server(mode: str):
    handler = type(f"Handler_{mode}", (_FixtureHandler,), {"mode": mode})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture(scope="session")
def good_site():
    server = _start_server("good")
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="session")
def bad_site():
    server = _start_server("bad")
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="session")
def loop():
    loop = asyncio.new_event_loop()
    yield loop
    import runtime
    if runtime.tester is not None:
        loop.run_until_complete(runtime.tester.stop())
    loop.close()


@pytest.fixture(scope="session")
def run(loop):
    """Run a coroutine on the shared session loop (the browser lives on it)."""
    return loop.run_until_complete


@pytest.fixture(scope="session")
def handlers():
    from handlers import HANDLERS
    return HANDLERS


@pytest.fixture()
def session(run, handlers, good_site):
    """A fresh session on the app fixture page, closed after the test."""
    r = run(handlers["open_session"]({"url": f"{good_site}/app.html"}))
    assert r["success"], r
    yield r["session_id"]
    run(handlers["close_session"]({"session_id": r["session_id"]}))
