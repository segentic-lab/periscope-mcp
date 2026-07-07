"""Deterministic, sitemap-seeded crawl + honest coverage reporting (issue #22).

Serves its own tiny linked site (6 pages + sitemap.xml + robots.txt) so the
crawl behavior is fully controlled and isolated from the shared good/bad fixtures.
"""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

# / links to a,b,c; a->d, b->e; c,d,e are leaves. Sitemap lists all six.
PAGES = {
    "/": '<a href="/a">a</a><a href="/b">b</a><a href="/c">c</a>',
    "/a": '<a href="/d">d</a>',
    "/b": '<a href="/e">e</a>',
    "/c": "<h1>c</h1>",
    "/d": "<h1>d</h1>",
    "/e": "<h1>e</h1>",
}
SITEMAP_PATHS = ["/", "/a", "/b", "/c", "/d", "/e"]


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        origin = f"http://{self.headers.get('Host')}"
        if path == "/robots.txt":
            return self._send(f"User-agent: *\nSitemap: {origin}/sitemap.xml\n", "text/plain")
        if path == "/sitemap.xml":
            locs = "".join(f"<url><loc>{origin}{p}</loc></url>" for p in SITEMAP_PATHS)
            return self._send(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                f"{locs}</urlset>", "application/xml")
        if path in PAGES:
            return self._send(
                f"<!doctype html><html lang=en><head><title>{path}</title></head>"
                f"<body>{PAGES[path]}</body></html>", "text/html")
        self.send_response(404)
        self.end_headers()

    def _send(self, body: str, ctype: str):
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def crawl_site():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _project(run, handlers, name, base_url):
    run(handlers["create_project"]({"name": name, "base_url": base_url}))


def test_crawl_is_deterministic_and_reports_uncrawled(run, handlers, crawl_site):
    _project(run, handlers, "crawldet", crawl_site)
    try:
        r1 = run(handlers["crawl_project"]({"project": "crawldet", "max_pages": 3}))
        r2 = run(handlers["crawl_project"]({"project": "crawldet", "max_pages": 3}))
        # Exact, reproducible subset+order — the fix for the shuffling window.
        assert r1["urls"] == [crawl_site, f"{crawl_site}/a", f"{crawl_site}/b"], r1["urls"]
        assert r1["urls"] == r2["urls"]
        # sitemap surfaced the whole site even though only 3 were crawled
        assert "sitemap" in r1["crawl_sources"]
        assert r1["discovered_total"] >= 6
        assert r1["pages_not_crawled_count"] >= 3
        assert r1["pages_not_crawled"]  # the skipped URLs are listed, not silent
    finally:
        run(handlers["delete_project"]({"name": "crawldet"}))


def test_max_pages_zero_tests_the_whole_site(run, handlers, crawl_site):
    _project(run, handlers, "crawlall", crawl_site)
    try:
        r = run(handlers["crawl_project"]({"project": "crawlall", "max_pages": 0}))
        assert len(r["urls"]) == 6
        assert r["pages_not_crawled_count"] == 0
        assert r.get("ceiling_hit") is not True
    finally:
        run(handlers["delete_project"]({"name": "crawlall"}))


def test_use_sitemap_false_is_pure_link_crawl(run, handlers, crawl_site):
    _project(run, handlers, "crawlnosm", crawl_site)
    try:
        r = run(handlers["crawl_project"]({
            "project": "crawlnosm", "max_pages": 0, "use_sitemap": False}))
        assert "sitemap" not in r["crawl_sources"]
        # link discovery from / still reaches every reachable page
        assert set(r["urls"]) == {crawl_site} | {f"{crawl_site}/{p}" for p in "abcde"}
    finally:
        run(handlers["delete_project"]({"name": "crawlnosm"}))


def test_test_project_reports_coverage_delta(run, handlers, crawl_site):
    _project(run, handlers, "crawlcov", crawl_site)
    try:
        run(handlers["test_project"]({
            "project": "crawlcov", "max_pages": 3, "checks": ["functionality"]}))
        r2 = run(handlers["test_project"]({
            "project": "crawlcov", "max_pages": 3, "checks": ["functionality"]}))
        # Deterministic crawl → identical page set → empty delta (the whole point:
        # findings can't silently vanish between runs anymore).
        assert "coverage" in r2, r2.keys()
        assert r2["coverage"]["pages_added"] == []
        assert r2["coverage"]["pages_dropped"] == []
        assert r2["pages_not_tested_count"] >= 3
    finally:
        run(handlers["delete_project"]({"name": "crawlcov"}))
