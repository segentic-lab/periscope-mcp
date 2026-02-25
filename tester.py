import asyncio
import os
import time
import hashlib
from datetime import datetime
from urllib.parse import urlparse
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
import config
from checks.visual import check_visual
from checks.accessibility import check_accessibility
from checks.functionality import check_functionality, check_seo, get_performance_metrics


class WebsiteTester:
    def __init__(self):
        self.playwright = None
        self.browser: Browser = None
        self.contexts: dict[str, BrowserContext] = {}  # project_name -> context

    async def start(self):
        """Initialize Playwright and launch browser."""
        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                pass
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=config.HEADLESS)

    async def stop(self):
        """Close browser and cleanup."""
        for ctx in self.contexts.values():
            await ctx.close()
        self.contexts.clear()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def get_context(self, project_name: str = "default") -> BrowserContext:
        """Get or create a browser context for a project."""
        if project_name not in self.contexts:
            self.contexts[project_name] = await self.browser.new_context(
                viewport={"width": config.VIEWPORT_WIDTH, "height": config.VIEWPORT_HEIGHT}
            )
        return self.contexts[project_name]

    async def close_context(self, project_name: str):
        """Close a project's browser context."""
        if project_name in self.contexts:
            await self.contexts[project_name].close()
            del self.contexts[project_name]

    def _url_to_filename(self, url: str) -> str:
        """Convert URL to a safe filename."""
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        parsed = urlparse(url)
        path_part = parsed.path.replace("/", "_")[:30] or "index"
        return f"{parsed.netloc}_{path_part}_{url_hash}.png"

    def _get_screenshot_path(self, project_name: str, url: str) -> str:
        """Get screenshot path for a URL in a project."""
        project_dir = os.path.join(config.SCREENSHOT_DIR, project_name)
        os.makedirs(project_dir, exist_ok=True)
        filename = self._url_to_filename(url)
        return os.path.join(project_dir, filename)

    async def test_url(
        self,
        url: str,
        project_name: str = "default",
        checks: list[str] = None
    ) -> dict:
        """
        Test a single URL and return results.

        Args:
            url: The URL to test
            project_name: Project name for context/screenshots
            checks: List of check types to run (visual, accessibility, functionality, seo, performance)
                   If None, runs all checks.

        Returns dict with test results.
        """
        if checks is None:
            checks = ["visual", "accessibility", "functionality", "seo", "performance"]

        context = await self.get_context(project_name)
        page = await context.new_page()
        page.set_default_timeout(config.TIMEOUT)

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        try:
            start_time = time.time()
            response = await page.goto(url, wait_until="networkidle")
            load_time = int((time.time() - start_time) * 1000)

            # Take screenshot
            screenshot_path = self._get_screenshot_path(project_name, url)
            await page.screenshot(path=screenshot_path, full_page=True)

            # Get page info
            title = await page.title()

            # Run checks
            all_issues = []

            if "visual" in checks:
                issues = await check_visual(page)
                all_issues.extend(issues)

            if "accessibility" in checks:
                issues = await check_accessibility(page)
                all_issues.extend(issues)

            if "functionality" in checks:
                issues = await check_functionality(page)
                all_issues.extend(issues)

            if "seo" in checks:
                issues = await check_seo(page)
                all_issues.extend(issues)

            # Get performance metrics
            performance = {}
            if "performance" in checks:
                performance = await get_performance_metrics(page)

            # Add console errors as issues
            if console_errors:
                all_issues.append({
                    "type": "visual",
                    "severity": "error",
                    "message": f"{len(console_errors)} console errors",
                    "details": console_errors[:5]
                })

            return {
                "url": url,
                "status": "success",
                "status_code": response.status if response else None,
                "title": title,
                "screenshot_path": screenshot_path,
                "load_time_ms": load_time,
                "issues": all_issues,
                "issue_count": len(all_issues),
                "issues_by_severity": self._count_by_key(all_issues, "severity"),
                "issues_by_type": self._count_by_key(all_issues, "type"),
                "performance": performance,
                "console_errors": console_errors
            }

        except Exception as e:
            return {
                "url": url,
                "status": "error",
                "error": str(e),
                "console_errors": console_errors
            }
        finally:
            await page.close()

    def _count_by_key(self, items: list[dict], key: str) -> dict:
        """Count items by a key value."""
        counts = {}
        for item in items:
            val = item.get(key, "unknown")
            counts[val] = counts.get(val, 0) + 1
        return counts

    async def test_multiple(
        self,
        urls: list[str],
        project_name: str = "default",
        checks: list[str] = None
    ) -> dict:
        """Test multiple URLs and return aggregated results."""
        results = []
        for url in urls:
            result = await self.test_url(url, project_name, checks)
            results.append(result)

        # Aggregate results
        total = len(results)
        successful = sum(1 for r in results if r.get("status") == "success")
        all_issues = []
        for r in results:
            for issue in r.get("issues", []):
                all_issues.append({**issue, "url": r["url"]})

        return {
            "project": project_name,
            "pages_tested": total,
            "successful": successful,
            "failed": total - successful,
            "total_issues": len(all_issues),
            "issues_by_severity": self._count_by_key(all_issues, "severity"),
            "issues_by_type": self._count_by_key(all_issues, "type"),
            "pages": results,
            "all_issues": all_issues
        }

    async def save_report(self, results: dict, project_name: str) -> str:
        """Save test results to a JSON report file."""
        import json
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{project_name}_{timestamp}.json"
        filepath = os.path.join(config.REPORTS_DIR, filename)

        with open(filepath, "w") as f:
            json.dump(results, f, indent=2)

        return filepath
