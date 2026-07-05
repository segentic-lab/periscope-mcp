import asyncio
import os
import time
import hashlib
from datetime import datetime
from urllib.parse import urlparse
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
import config
from nav import resilient_goto
from checks.visual import check_visual
from checks.accessibility import check_accessibility
from checks.functionality import check_functionality, check_seo, get_performance_metrics
from checks.geo import check_geo


def redirected_to_login(current_url: str, login_url: str) -> bool:
    """True when a page load ended up on the project's configured login page —
    the telltale of expired/lost auth (issue #11)."""
    if not login_url or not current_url:
        return False
    return urlparse(current_url).path.rstrip("/") == urlparse(login_url).path.rstrip("/")


class WebsiteTester:
    def __init__(self):
        self.playwright = None
        self.browser: Browser = None            # headless (default)
        self.headed_browser: Browser = None     # visible; launched on demand
        self.contexts: dict[str, BrowserContext] = {}         # headless: project_name -> context
        self.headed_contexts: dict[str, BrowserContext] = {}  # headed: project_name -> context
        self._pending_logins: dict = {}          # project_name -> (context, page) during interactive_login

    def _launch_kwargs(self, headless: bool) -> dict:
        kwargs = {"headless": headless}
        if config.CHROMIUM_PATH:
            kwargs["executable_path"] = config.CHROMIUM_PATH
        return kwargs

    async def start(self):
        """Initialize Playwright and launch the headless browser."""
        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                pass
        # Contexts/browsers from a previous (possibly crashed) browser are unusable
        self.contexts.clear()
        self.headed_contexts.clear()
        self._pending_logins.clear()
        self.headed_browser = None
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(**self._launch_kwargs(config.HEADLESS))
        if not config.HEADLESS and config.STARTUP_PAUSE > 0:
            await asyncio.sleep(config.STARTUP_PAUSE)

    async def get_browser(self, headed: bool = False) -> Browser:
        """Return the headless browser, or a lazily-launched visible one.

        Playwright's headless flag is fixed at launch, so a visible browser is a
        separate instance launched on demand. Requires a display (DISPLAY)."""
        if not headed:
            return self.browser
        if self.headed_browser is None or not self.headed_browser.is_connected():
            try:
                self.headed_browser = await self.playwright.chromium.launch(**self._launch_kwargs(False))
            except Exception as e:
                raise RuntimeError(
                    f"Could not open a visible browser ({e}). A display is required — set DISPLAY "
                    f"or run on a machine with a screen."
                ) from e
        return self.headed_browser

    async def stop(self):
        """Close browsers and cleanup."""
        for ctx in list(self.contexts.values()) + list(self.headed_contexts.values()):
            try:
                await ctx.close()
            except Exception:
                pass
        self.contexts.clear()
        self.headed_contexts.clear()
        for browser in (self.browser, self.headed_browser):
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
        if self.playwright:
            await self.playwright.stop()

    async def _new_context(self, browser: Browser, project_name, seed_state=None) -> BrowserContext:
        """Create a context, seeded with a project's login session if any.

        seed_state (live storage_state from a sibling context) wins over the
        persisted sessions/<project>.json file — login_project authenticates
        the RUNNING context without writing that file, so a context created
        later in the other mode must inherit the live cookies (issue #20).
        """
        kwargs = {
            "viewport": {"width": config.VIEWPORT_WIDTH, "height": config.VIEWPORT_HEIGHT},
            "ignore_https_errors": True,
        }
        if seed_state:
            kwargs["storage_state"] = seed_state
        elif project_name:
            import runtime  # deferred: runtime imports tester at module load
            state = runtime.project_manager.load_session_state(project_name)
            if state:
                kwargs["storage_state"] = state
        return await browser.new_context(**kwargs)

    async def get_context(self, project_name: str = "default", headed: bool = False) -> BrowserContext:
        """Get or create a browser context for a project (headless or visible)."""
        contexts = self.headed_contexts if headed else self.contexts
        if project_name not in contexts:
            browser = await self.get_browser(headed)
            # The same project's context in the OTHER mode holds the freshest
            # auth (cookies live there after login_project) — carry it over so
            # headed and headless sessions are interchangeable (issue #20).
            sibling = (self.contexts if headed else self.headed_contexts).get(project_name)
            seed_state = None
            if sibling:
                try:
                    seed_state = await sibling.storage_state()
                except Exception:
                    pass
            contexts[project_name] = await self._new_context(browser, project_name, seed_state=seed_state)
        return contexts[project_name]

    async def close_context(self, project_name: str):
        """Close a project's browser context (both headless and visible)."""
        for contexts in (self.contexts, self.headed_contexts):
            if project_name in contexts:
                try:
                    await contexts[project_name].close()
                except Exception:
                    pass
                del contexts[project_name]

    async def new_ephemeral_context(self, headed: bool = False) -> BrowserContext:
        """Isolated context for a project-less call — the caller must close it.

        Project-less tools must not share one persistent context: an external
        link check visiting linkedin.com would leave cookies that a later,
        unrelated session sees (issue #8)."""
        browser = await self.get_browser(headed)
        return await browser.new_context(
            viewport={"width": config.VIEWPORT_WIDTH, "height": config.VIEWPORT_HEIGHT},
            ignore_https_errors=True,
        )

    async def launch_interactive_login(self, project_name: str, url: str):
        """Open a visible browser at a login page for the user to log in by hand.
        Held open until capture_login() saves the resulting session."""
        # Fresh visible context (seeded with any existing session, e.g. for re-auth)
        if project_name in self.headed_contexts:
            await self.close_context(project_name)
        context = await self.get_context(project_name, headed=True)
        page = await context.new_page()
        page.set_default_timeout(config.TIMEOUT)
        await page.goto(url, wait_until="domcontentloaded")
        self._pending_logins[project_name] = (context, page)

    async def capture_login(self, project_name: str) -> dict:
        """Capture storage_state from an in-progress interactive login, then close
        the visible window. Raises KeyError if no login is in progress."""
        context, page = self._pending_logins.pop(project_name)
        state = await context.storage_state()
        try:
            await page.close()
        finally:
            await self.close_context(project_name)
        return state

    async def open_page(self, project_name, url: str):
        """Open a navigated page for a one-shot call. Returns (page, cleanup).

        With a project: page lives in the project's shared (authenticated)
        context. Without: a fresh ephemeral context, fully isolated. cleanup()
        closes the page and, when ephemeral, the context — call it in finally.
        """
        own_ctx = None
        if project_name:
            context = await self.get_context(project_name)
        else:
            own_ctx = await self.new_ephemeral_context()
            context = own_ctx
        page = await context.new_page()
        page.set_default_timeout(config.TIMEOUT)
        from interactions import INP_INIT_SCRIPT  # capture INP if the one-shot drives interactions
        await page.add_init_script(INP_INIT_SCRIPT)
        try:
            await resilient_goto(page, url)
        except Exception:
            await page.close()
            if own_ctx:
                await own_ctx.close()
            raise

        async def cleanup():
            try:
                await page.close()
            finally:
                if own_ctx:
                    await own_ctx.close()

        return page, cleanup

    def _url_to_filename(self, url: str) -> str:
        """Convert URL to a safe filename."""
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        parsed = urlparse(url)
        path_part = parsed.path.replace("/", "_")[:30] or "index"
        return f"{parsed.netloc}_{path_part}_{url_hash}.png"

    def _get_screenshot_path(self, project_name: str, url: str, screenshot_dir: str = None) -> str:
        """Get screenshot path for a URL in a project."""
        base_dir = screenshot_dir if screenshot_dir else config.SCREENSHOT_DIR
        project_dir = os.path.join(base_dir, project_name)
        os.makedirs(project_dir, exist_ok=True)
        filename = self._url_to_filename(url)
        return os.path.join(project_dir, filename)

    async def test_url(
        self,
        url: str,
        project_name: str = None,
        checks: list[str] = None,
        screenshot_dir: str = None,
        login_url: str = None,
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
            checks = ["visual", "accessibility", "functionality", "seo", "performance", "geo"]
        valid = {"visual", "accessibility", "functionality", "seo", "performance", "geo"}
        unknown_checks = [c for c in checks if c not in valid]

        # Project-less calls get an isolated context (no cookie bleed);
        # screenshots still file under "default" so get_screenshot finds them.
        own_ctx = None
        if project_name:
            context = await self.get_context(project_name)
        else:
            own_ctx = await self.new_ephemeral_context()
            context = own_ctx
            project_name = "default"
        page = await context.new_page()
        page.set_default_timeout(config.TIMEOUT)

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        try:
            start_time = time.time()
            response, wait_downgraded = await resilient_goto(page, url)
            load_time = int((time.time() - start_time) * 1000)

            # Take screenshot
            screenshot_path = self._get_screenshot_path(project_name, url, screenshot_dir=screenshot_dir)
            await page.screenshot(path=screenshot_path, full_page=True)

            # Get page info
            title = await page.title()
            meta_description = await page.evaluate(
                """() => document.querySelector('meta[name="description"]')?.content || null"""
            )

            # Auth loss must never masquerade as a clean result: landing on the
            # configured login page is an error finding, not a tested page.
            auth_redirected = redirected_to_login(page.url, login_url)

            # Run checks
            all_issues = []
            if auth_redirected:
                all_issues.append({
                    "type": "functionality",
                    "severity": "error",
                    "message": "Page redirected to the login page — project authentication "
                               "has expired or been lost. Run login_project and re-test.",
                })
            if unknown_checks:
                # A typo'd check name must not silently pass as "no issues found"
                all_issues.append({
                    "type": "functionality",
                    "severity": "warning",
                    "message": f"Unknown check name(s) ignored: {unknown_checks}. "
                               f"Valid: visual, accessibility, functionality, seo, performance, geo",
                })

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
                issues = await check_seo(page, response)
                all_issues.extend(issues)

            if "geo" in checks:
                issues = await check_geo(page, response)
                all_issues.extend(issues)

            # Get performance metrics
            performance = {}
            if "performance" in checks:
                performance = await get_performance_metrics(page)

            # Add console errors as issues (they're functionality findings, so
            # respect the caller's check selection)
            if console_errors and "functionality" in checks:
                all_issues.append({
                    "type": "functionality",
                    "severity": "error",
                    "message": f"{len(console_errors)} console errors",
                    "details": console_errors[:5]
                })

            return {
                "url": url,
                "status": "auth_lost" if auth_redirected else "success",
                **({"wait_downgraded": "load"} if wait_downgraded else {}),
                **({"final_url": page.url} if auth_redirected else {}),
                "status_code": response.status if response else None,
                "title": title,
                "meta_description": meta_description,
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
            if own_ctx:
                await own_ctx.close()

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
        checks: list[str] = None,
        screenshot_dir: str = None,
        login_url: str = None,
    ) -> dict:
        """Test multiple URLs and return aggregated results."""
        results = []
        for url in urls:
            result = await self.test_url(url, project_name, checks,
                                         screenshot_dir=screenshot_dir, login_url=login_url)
            results.append(result)

        # Aggregate results
        total = len(results)
        successful = sum(1 for r in results if r.get("status") == "success")
        auth_lost_pages = [r["url"] for r in results if r.get("status") == "auth_lost"]
        all_issues = []
        for r in results:
            for issue in r.get("issues", []):
                all_issues.append({**issue, "url": r["url"]})

        # Site-wide SEO: duplicate titles/descriptions across pages hurt
        # rankings and are only detectable with the whole crawl in hand.
        site_issues = []
        if checks is None or "seo" in checks:
            site_issues = self._find_duplicate_meta(results)
            all_issues.extend(site_issues)

        now = datetime.now()
        return {
            "project": project_name,
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "timestamp": now.isoformat(),
            "pages_tested": total,
            "successful": successful,
            "failed": total - successful,
            **({"auth_lost_pages": auth_lost_pages} if auth_lost_pages else {}),
            "total_issues": len(all_issues),
            "issues_by_severity": self._count_by_key(all_issues, "severity"),
            "issues_by_type": self._count_by_key(all_issues, "type"),
            "site_issues": site_issues,
            "pages": results,
            "all_issues": all_issues
        }

    def _find_duplicate_meta(self, results: list[dict]) -> list[dict]:
        """Flag titles/meta descriptions shared by more than one page."""
        titles, descriptions = {}, {}
        for r in results:
            if r.get("status") != "success":
                continue
            title = (r.get("title") or "").strip()
            if title:
                titles.setdefault(title, []).append(r["url"])
            desc = (r.get("meta_description") or "").strip()
            if desc:
                descriptions.setdefault(desc, []).append(r["url"])

        issues = []
        for kind, bucket in (("title", titles), ("meta description", descriptions)):
            for text, urls in bucket.items():
                if len(urls) > 1:
                    issues.append({
                        "type": "seo",
                        "severity": "warning",
                        "message": f"{len(urls)} pages share the same {kind}: '{text[:60]}'",
                        "details": urls[:10],
                        "url": "(site-wide)",
                    })
        return issues

    async def test_responsive(
        self,
        url: str,
        project_name: str = None,
        viewports: list[dict] = None,
        checks: list[str] = None,
        screenshot_dir: str = None,
    ) -> dict:
        """Test a URL at multiple viewport sizes.

        Args:
            url: URL to test
            project_name: Project name for screenshots
            viewports: List of {name, width, height} dicts. Defaults to mobile/tablet/desktop.
            checks: Check types to run at each viewport (optional)

        Returns dict with results per viewport.
        """
        if viewports is None:
            viewports = [
                {"name": "mobile", "width": 375, "height": 812},
                {"name": "tablet", "width": 768, "height": 1024},
                {"name": "desktop", "width": 1920, "height": 1080},
            ]

        own_ctx = None
        if project_name:
            context = await self.get_context(project_name)
        else:
            own_ctx = await self.new_ephemeral_context()
            context = own_ctx
            project_name = "default"
        page = await context.new_page()
        page.set_default_timeout(config.TIMEOUT)

        results_list = []
        try:
            for vp in viewports:
                await page.set_viewport_size(
                    {"width": vp["width"], "height": vp["height"]}
                )
                _, vp_downgraded = await resilient_goto(page, url)

                # Screenshot
                base_dir = screenshot_dir if screenshot_dir else config.SCREENSHOT_DIR
                project_dir = os.path.join(base_dir, project_name)
                os.makedirs(project_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = os.path.join(
                    project_dir,
                    f"responsive_{vp['name']}_{vp['width']}x{vp['height']}_{timestamp}.png"
                )
                await page.screenshot(path=screenshot_path, full_page=True)

                vp_result = {
                    "viewport": vp,
                    "screenshot_path": screenshot_path,
                    "title": await page.title(),
                }
                if vp_downgraded:
                    vp_result["wait_downgraded"] = "load"

                # Run checks if requested
                if checks:
                    all_issues = []
                    if "visual" in checks:
                        all_issues.extend(await check_visual(page))
                    if "accessibility" in checks:
                        all_issues.extend(await check_accessibility(page))
                    if "functionality" in checks:
                        all_issues.extend(await check_functionality(page))
                    if "seo" in checks:
                        all_issues.extend(await check_seo(page))
                    if "geo" in checks:
                        all_issues.extend(await check_geo(page))
                    if "performance" in checks:
                        vp_result["performance"] = await get_performance_metrics(page)

                    vp_result["issues"] = all_issues
                    vp_result["issue_count"] = len(all_issues)

                results_list.append(vp_result)

            return {
                "url": url,
                "viewports_tested": len(results_list),
                "results": results_list,
            }
        finally:
            await page.close()
            if own_ctx:
                await own_ctx.close()

    async def save_report(self, results: dict, project_name: str) -> str:
        """Save test results to a JSON report file."""
        import json
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{project_name}_{timestamp}.json"
        filepath = os.path.join(config.REPORTS_DIR, filename)

        with open(filepath, "w") as f:
            json.dump(results, f, indent=2)

        return filepath
