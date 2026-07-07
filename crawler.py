import re
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree
from playwright.async_api import Page, BrowserContext
import config
from nav import resilient_goto


class Crawler:
    """Crawl a website to discover pages.

    Discovery is DETERMINISTIC: links are sorted before the max_pages cap is
    applied, so the same site yields the same page subset on every run (issue
    #22 — otherwise set-iteration order shuffled which pages fell in the window
    and findings silently appeared/vanished between reports). When a sitemap is
    present it seeds the queue first (sorted), matching what search engines index.
    """

    def __init__(self):
        self.visited = set()
        self.to_visit = []
        # Every distinct in-scope URL we became aware of (crawled or not) — lets
        # crawl() report exactly which pages the cap left untested.
        self.known = set()

    def _normalize_url(self, url: str) -> str:
        """Normalize URL by removing fragments and trailing slashes.
        Query strings are kept — /items?page=2 and /items?page=3 are distinct pages."""
        parsed = urlparse(url)
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
        normalized = normalized or f"{parsed.scheme}://{parsed.netloc}"
        if parsed.query:
            normalized += f"?{parsed.query}"
        return normalized

    def _is_same_domain(self, url: str, base_url: str) -> bool:
        """Check if URL is on the same domain as base URL."""
        return urlparse(url).netloc == urlparse(base_url).netloc

    def _is_valid_url(self, url: str) -> bool:
        """Check if URL is valid for crawling."""
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            return False

        # Skip common non-page resources
        skip_extensions = (
            ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
            ".css", ".js", ".ico", ".woff", ".woff2", ".ttf", ".eot",
            ".mp4", ".webm", ".mp3", ".wav", ".zip", ".tar", ".gz",
            ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"
        )
        if parsed.path.lower().endswith(skip_extensions):
            return False

        return True

    async def extract_links(self, page: Page, base_url: str) -> list[str]:
        """Extract valid same-domain links from a page, sorted deterministically."""
        links = await page.evaluate("""() => {
            const anchors = document.querySelectorAll('a[href]');
            return Array.from(anchors).map(a => a.href);
        }""")

        valid_links = set()
        for link in links:
            absolute_url = urljoin(base_url, link)
            normalized = self._normalize_url(absolute_url)

            if (self._is_valid_url(normalized) and
                self._is_same_domain(normalized, base_url) and
                normalized not in self.visited):
                valid_links.add(normalized)

        # SORTED, not set-order: this is what makes the crawl reproducible.
        return sorted(valid_links)

    async def _fetch_sitemap_urls(self, context: BrowserContext, base_url: str) -> list[str]:
        """Discover in-scope URLs from robots.txt Sitemap: lines and the usual
        sitemap locations. Follows one level of sitemap-index nesting. Best-effort:
        any fetch/parse failure just yields fewer URLs, never an error. Sorted."""
        parsed = urlparse(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        candidates = [
            f"{origin}/sitemap.xml",
            f"{origin}/sitemap_index.xml",
            f"{origin}/sitemap-index.xml",
        ]

        # robots.txt may point at sitemaps in non-standard locations.
        try:
            resp = await context.request.get(f"{origin}/robots.txt", timeout=8000)
            if resp.ok:
                for line in (await resp.text()).splitlines():
                    m = re.match(r"\s*Sitemap:\s*(\S+)", line, re.IGNORECASE)
                    if m:
                        candidates.append(m.group(1).strip())
        except Exception:
            pass

        found: set[str] = set()
        seen_sitemaps: set[str] = set()
        # cap sitemap fetches so a giant index can't stall discovery
        queue = list(dict.fromkeys(candidates))
        fetches = 0
        while queue and fetches < 50:
            sm_url = queue.pop(0)
            if sm_url in seen_sitemaps:
                continue
            seen_sitemaps.add(sm_url)
            fetches += 1
            try:
                resp = await context.request.get(sm_url, timeout=8000)
                if not resp.ok:
                    continue
                body = await resp.body()
                root = ElementTree.fromstring(body)
            except Exception:
                continue
            tag = root.tag.rsplit("}", 1)[-1]  # strip XML namespace
            for loc in root.iter():
                if loc.tag.rsplit("}", 1)[-1] != "loc" or not (loc.text or "").strip():
                    continue
                raw = loc.text.strip()
                url = self._normalize_url(raw)
                if tag == "sitemapindex":
                    queue.append(raw)  # child sitemap
                elif self._is_valid_url(url) and self._is_same_domain(url, base_url):
                    found.add(url)

        return sorted(found)

    async def crawl(
        self,
        context: BrowserContext,
        start_url: str,
        max_pages: int = None,
        max_depth: int = None,
        use_sitemap: bool = True,
    ) -> dict:
        """
        Crawl a website starting from start_url.

        max_pages: cap on pages to CRAWL. 0 == unbounded ("test all"), which still
                   stops at config.MAX_PAGES_CEILING and flags it. None -> default.
        use_sitemap: seed discovery from sitemap.xml/robots.txt when present.

        Returns a dict:
          crawled: list[str]            — URLs actually visited (ordered)
          discovered_total: int         — distinct in-scope URLs we became aware of
          not_crawled: list[str]        — known URLs the cap/ceiling left untested (<=100)
          not_crawled_count: int        — full count of untested known URLs
          not_crawled_truncated: bool   — True when the list above was capped
          sources: list[str]            — 'sitemap' and/or 'links'
          ceiling_hit: bool             — unbounded run stopped at the safety ceiling
        """
        default_cap = config.MAX_PAGES if max_pages is None else max_pages
        max_depth = config.MAX_DEPTH if max_depth is None else max_depth
        unbounded = default_cap == 0
        cap = config.MAX_PAGES_CEILING if unbounded else default_cap

        start_url = self._normalize_url(start_url)
        self.visited = set()
        self.known = {start_url}
        discovered = []
        sources = []

        # Seed order: start_url, then sitemap URLs (sorted), then link discovery.
        self.to_visit = [(start_url, 0)]
        if use_sitemap:
            sitemap_urls = await self._fetch_sitemap_urls(context, start_url)
            if sitemap_urls:
                sources.append("sitemap")
                for u in sitemap_urls:
                    if u != start_url:
                        self.known.add(u)
                        self.to_visit.append((u, 0))

        page = await context.new_page()
        page.set_default_timeout(config.TIMEOUT)

        ceiling_hit = False
        try:
            while self.to_visit and len(discovered) < cap:
                url, depth = self.to_visit.pop(0)

                if url in self.visited:
                    continue

                self.visited.add(url)

                # Only count pages we can actually reach
                try:
                    await resilient_goto(page, url)
                except Exception:
                    continue

                discovered.append(url)

                if depth >= max_depth:
                    continue

                try:
                    links = await self.extract_links(page, url)
                except Exception:
                    continue

                if links and "links" not in sources:
                    sources.append("links")
                for link in links:  # already sorted -> deterministic queue order
                    self.known.add(link)
                    if link not in self.visited:
                        self.to_visit.append((link, depth + 1))

            if unbounded and len(discovered) >= cap and self.to_visit:
                ceiling_hit = True
        finally:
            await page.close()

        crawled_set = set(discovered)
        not_crawled = sorted(u for u in self.known if u not in crawled_set)
        listed = config.MAX_NOT_CRAWLED_LISTED
        return {
            "crawled": discovered,
            "discovered_total": len(self.known),
            "not_crawled": not_crawled[:listed],
            "not_crawled_count": len(not_crawled),
            "not_crawled_truncated": len(not_crawled) > listed,
            "sources": sources,
            "ceiling_hit": ceiling_hit,
        }
