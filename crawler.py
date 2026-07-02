from urllib.parse import urljoin, urlparse
from playwright.async_api import Page, BrowserContext
import config


class Crawler:
    """Crawl a website to discover pages."""

    def __init__(self):
        self.visited = set()
        self.to_visit = []

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
        """Extract all valid same-domain links from a page."""
        links = await page.evaluate("""() => {
            const anchors = document.querySelectorAll('a[href]');
            return Array.from(anchors).map(a => a.href);
        }""")

        valid_links = []
        for link in links:
            absolute_url = urljoin(base_url, link)
            normalized = self._normalize_url(absolute_url)

            if (self._is_valid_url(normalized) and
                self._is_same_domain(normalized, base_url) and
                normalized not in self.visited):
                valid_links.append(normalized)

        return list(set(valid_links))

    async def crawl(
        self,
        context: BrowserContext,
        start_url: str,
        max_pages: int = None,
        max_depth: int = None
    ) -> list[str]:
        """
        Crawl a website starting from start_url.

        Args:
            context: Browser context to use
            start_url: Starting URL
            max_pages: Maximum pages to discover
            max_depth: Maximum link depth to follow

        Returns list of discovered URLs.
        """
        max_pages = config.MAX_PAGES if max_pages is None else max_pages
        max_depth = config.MAX_DEPTH if max_depth is None else max_depth

        start_url = self._normalize_url(start_url)
        self.visited = set()
        self.to_visit = [(start_url, 0)]
        discovered = []

        page = await context.new_page()
        page.set_default_timeout(config.TIMEOUT)

        try:
            while self.to_visit and len(discovered) < max_pages:
                url, depth = self.to_visit.pop(0)

                if url in self.visited:
                    continue

                self.visited.add(url)

                # Only count pages we can actually reach
                try:
                    await page.goto(url, wait_until=config.WAIT_UNTIL, timeout=config.TIMEOUT)
                except Exception:
                    continue

                discovered.append(url)

                if depth >= max_depth:
                    continue

                try:
                    links = await self.extract_links(page, url)
                except Exception:
                    continue

                for link in links:
                    if link not in self.visited:
                        self.to_visit.append((link, depth + 1))

        finally:
            await page.close()

        return discovered
