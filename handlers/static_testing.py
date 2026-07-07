"""Static testing + results tools (test_url, crawl, reports, responsive, screenshot diff)."""
import asyncio
import json
import os
import re
import time
from urllib.parse import urlparse

import config
import interactions
from crawler import Crawler
from runtime import auth_handler, get_tester, project_manager, session_manager
from sessions import real_page

from .registry import tool
from nav import resilient_goto
from tester import redirected_to_login


def _as_bool(v) -> bool:
    """Interpret a bool arg that an MCP client may have sent as a string."""
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes")
    return bool(v)


def _url_slug(url: str) -> str:
    """Filesystem-safe filename stem for a page URL (used for saved .md files)."""
    p = urlparse(url)
    slug = (p.path or "").strip("/").replace("/", "_") or "index"
    if p.query:
        slug += "_" + re.sub(r"\W+", "-", p.query)[:40]
    return re.sub(r"[^A-Za-z0-9_.-]", "_", slug)[:120]


def _coverage_fields(crawl: dict, tested: bool) -> dict:
    """Flatten the crawler's coverage report onto a handler result. `tested`
    picks the noun (pages_not_tested for test_project, pages_not_crawled for
    crawl_project) so the response reads honestly for each tool."""
    noun = "tested" if tested else "crawled"
    fields = {
        "discovered_total": crawl["discovered_total"],
        f"pages_not_{noun}": crawl["not_crawled"],
        f"pages_not_{noun}_count": crawl["not_crawled_count"],
        f"pages_not_{noun}_truncated": crawl["not_crawled_truncated"],
        "crawl_sources": crawl["sources"],
    }
    if crawl["ceiling_hit"]:
        fields["ceiling_hit"] = True
        fields["ceiling"] = config.MAX_PAGES_CEILING
    return fields


def _latest_report_urls(project_name: str):
    """The set of page URLs from this project's most recent saved report, plus
    the report's filename — for the coverage delta. None if no prior report."""
    try:
        files = [f for f in os.listdir(config.REPORTS_DIR)
                 if f.startswith(project_name + "_") and f.endswith(".json")]
    except OSError:
        return None
    if not files:
        return None
    latest = max((os.path.join(config.REPORTS_DIR, f) for f in files), key=os.path.getmtime)
    try:
        with open(latest) as fh:
            report = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    urls = {p.get("url") for p in report.get("pages", []) if p.get("url")}
    return urls, os.path.basename(latest)


def _form_login_url(project) -> str | None:
    """The configured login URL for form-login projects, else None."""
    if project and project.auth and project.auth.method == "form" and project.auth.form_login:
        return project.auth.form_login.login_url
    return None


async def _preflight_auth(t, project) -> dict | None:
    """Verify a form-login project's context is still authenticated before a
    crawl/audit; re-login once if not (issue #11: auth can silently expire —
    e.g. refresh-token rotation — and a crawl of login pages must not pass as
    a successful audit). Returns an auth_check dict, or None if not applicable.
    """
    login_url = _form_login_url(project)
    if not login_url:
        return None
    context = await t.get_context(project.name)

    async def lands_on_login() -> bool:
        page = await context.new_page()
        page.set_default_timeout(config.TIMEOUT)
        try:
            await resilient_goto(page, project.base_url)
            return redirected_to_login(page.url, login_url)
        finally:
            await page.close()

    if not await lands_on_login():
        return {"authenticated": True}

    relogin = await auth_handler.login(context, project)
    if relogin.get("success") and not await lands_on_login():
        project_manager.mark_logged_in(project.name, True)
        return {"authenticated": True, "relogged_in": True}
    project_manager.mark_logged_in(project.name, False)
    return {
        "authenticated": False,
        "relogin_error": relogin.get("error") or "re-login succeeded but base_url still redirects to login",
    }


@tool("test_url")
async def handle_test_url(args: dict) -> dict:
        t = await get_tester()
        project_name = args.get("project")  # None -> isolated ephemeral context
        checks = args.get("checks")
        proj_obj = project_manager.get(project_name) if project_name else None
        proj_screenshot_dir = proj_obj.screenshot_dir if proj_obj else None

        result = await t.test_url(
            url=args["url"],
            project_name=project_name,
            checks=checks,
            screenshot_dir=proj_screenshot_dir,
            login_url=_form_login_url(proj_obj),
        )
        return result


@tool("crawl_project")
async def handle_crawl_project(args: dict) -> dict:
        project = project_manager.get(args["project"])
        if not project:
            return {"success": False, "error": f"Project '{args['project']}' not found"}

        t = await get_tester()
        auth_check = await _preflight_auth(t, project)
        if auth_check and not auth_check["authenticated"]:
            return {
                "success": False,
                "error": "Project authentication is no longer valid — base_url redirects to the "
                         "login page and automatic re-login failed. Run login_project and retry.",
                "auth_check": auth_check,
            }
        context = await t.get_context(project.name)
        crawler = Crawler()

        # Optional per-page enrichment, captured DURING the crawl (authenticated,
        # post-JS) — no second navigation. meta = title + description;
        # save_md = save each page as readable markdown.
        want_meta = _as_bool(args.get("meta"))
        save_md = _as_bool(args.get("save_md")) or bool(args.get("save_dir"))
        pages_meta = []
        md_dir = None
        if save_md:
            md_dir = args.get("save_dir") or os.path.join(config.DATA_DIR, "fetches", project.name)
            os.makedirs(md_dir, exist_ok=True)

        on_page = None
        if want_meta or save_md:
            from handlers.web import extract_readable

            async def on_page(url, page):
                entry = {"url": url}
                rp = real_page(page)
                if want_meta:
                    entry["title"] = await rp.title()
                    entry["description"] = await rp.evaluate(
                        "() => document.querySelector('meta[name=\"description\"]')?.content || "
                        "document.querySelector('meta[property=\"og:description\"]')?.content || ''")
                if save_md:
                    content, _ = extract_readable(await rp.content(), rp.url, "markdown")
                    slug = _url_slug(url) + ".md"
                    fpath = os.path.join(md_dir, slug)
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.write(content)
                    entry["saved_path"] = fpath
                pages_meta.append(entry)

        crawl = await crawler.crawl(
            context=context,
            start_url=project.base_url,
            max_pages=args.get("max_pages", project.max_pages),
            max_depth=args.get("max_depth", project.max_depth),
            use_sitemap=args.get("use_sitemap", True),
            on_page=on_page,
        )

        result = {
            "project": project.name,
            "base_url": project.base_url,
            "pages_found": len(crawl["crawled"]),
            "urls": crawl["crawled"],
            **_coverage_fields(crawl, tested=False),
        }
        if pages_meta:
            result["pages"] = pages_meta
        if save_md:
            result["saved_dir"] = md_dir
            result["saved_count"] = sum(1 for p in pages_meta if p.get("saved_path"))
        if auth_check:
            result["auth_check"] = auth_check
        return result


@tool("test_project")
async def handle_test_project(args: dict) -> dict:
        project = project_manager.get(args["project"])
        if not project:
            return {"success": False, "error": f"Project '{args['project']}' not found"}

        t = await get_tester()
        auth_check = await _preflight_auth(t, project)
        if auth_check and not auth_check["authenticated"]:
            return {
                "success": False,
                "error": "Project authentication is no longer valid — base_url redirects to the "
                         "login page and automatic re-login failed. Run login_project and retry.",
                "auth_check": auth_check,
            }
        context = await t.get_context(project.name)

        # Crawl first (deterministic order + sitemap-seeded — issue #22)
        crawler = Crawler()
        crawl = await crawler.crawl(
            context=context,
            start_url=project.base_url,
            max_pages=args.get("max_pages", project.max_pages),
            max_depth=project.max_depth,
            use_sitemap=args.get("use_sitemap", True),
        )
        urls = crawl["crawled"]

        # Coverage delta vs the previous saved report — READ BEFORE we save the
        # new one, so a shifted crawl window is visible instead of silent.
        prior = _latest_report_urls(project.name)

        # Test all pages — flagging any that land on the login page mid-run
        checks = args.get("checks", project.test_types)
        results = await t.test_multiple(urls, project.name, checks,
                                        screenshot_dir=project.screenshot_dir,
                                        login_url=_form_login_url(project))
        results.update(_coverage_fields(crawl, tested=True))
        if prior is not None:
            prior_set, prior_name = prior
            cur = set(urls)
            results["coverage"] = {
                "compared_to": prior_name,
                "pages_added": sorted(cur - prior_set),
                "pages_dropped": sorted(prior_set - cur),
            }
        if auth_check:
            results["auth_check"] = auth_check

        # Save report
        report_path = await t.save_report(results, project.name)
        results["report_path"] = report_path

        # Update project
        project_manager.update_last_tested(project.name)

        return results


@tool("get_screenshot")
async def handle_get_screenshot(args: dict) -> dict:
        t = await get_tester()
        proj_obj = project_manager.get(args["project"])
        proj_screenshot_dir = proj_obj.screenshot_dir if proj_obj else None
        screenshot_path = t._get_screenshot_path(args["project"], args["url"], screenshot_dir=proj_screenshot_dir)

        if os.path.exists(screenshot_path):
            return {
                "success": True,
                "screenshot_path": screenshot_path,
                "url": args["url"]
            }
        return {
            "success": False,
            "error": "Screenshot not found. Run test_url or test_project first."
        }


@tool("list_reports")
async def handle_list_reports(args: dict) -> dict:
        project_filter = args.get("project")
        reports = []

        for filename in os.listdir(config.REPORTS_DIR):
            if filename.endswith(".json"):
                if project_filter and not filename.startswith(project_filter + "_"):
                    continue
                filepath = os.path.join(config.REPORTS_DIR, filename)
                stat = os.stat(filepath)
                reports.append({
                    "filename": filename,
                    "path": filepath,
                    "size_bytes": stat.st_size,
                    "modified": stat.st_mtime
                })

        reports.sort(key=lambda x: x["modified"], reverse=True)
        return {"reports": reports, "count": len(reports)}


@tool("get_report")
async def handle_get_report(args: dict) -> dict:
        report_path = args["report_path"]
        if os.path.exists(report_path):
            with open(report_path, "r") as f:
                report = json.load(f)
            return {"success": True, "report": report}
        return {"success": False, "error": "Report not found"}


@tool("compare_screenshots")
async def handle_compare_screenshots(args: dict) -> dict:
        from utils import compare_screenshots as do_compare
        result = do_compare(
            args["screenshot1"],
            args["screenshot2"],
            threshold=args.get("threshold", 10),
        )
        return result


@tool("visual_check")
async def handle_visual_check(args: dict) -> dict:
        """Named visual-regression baselines. action='set' captures the current
        session page (or element) as the baseline; action='check' captures it
        again and compares — pass/fail against max_diff_percent. Baselines are
        stored per project+name, so the agent never bookkeeps screenshot paths."""
        import re as _re
        from utils import compare_screenshots as do_compare

        session = session_manager.get_session(args["session_id"])
        action = args.get("action", "check")
        name = args.get("name", "")
        if not name or not _re.fullmatch(r"[A-Za-z0-9._-]{1,80}", name):
            return {"success": False, "error":
                    "visual_check requires 'name': 1-80 chars of letters, digits, . _ - "
                    "(it identifies the baseline, e.g. 'dashboard-desktop')."}

        baseline_dir = os.path.join(config.DATA_DIR, "baselines", session.project_name)
        os.makedirs(baseline_dir, exist_ok=True)
        baseline_path = os.path.join(baseline_dir, f"{name}.png")

        async def capture(path):
            selector = args.get("selector")
            if selector:
                locator = session.page.locator(selector).first
                await locator.wait_for(state="visible", timeout=10000)
                await locator.screenshot(path=path)
            else:
                await real_page(session.page).screenshot(
                    path=path, full_page=args.get("full_page", True))

        if action == "set":
            replaced = os.path.exists(baseline_path)
            await capture(baseline_path)
            return {"success": True, "action": "set", "name": name,
                    "baseline_path": baseline_path, "replaced": replaced}

        if action == "check":
            if not os.path.exists(baseline_path):
                return {"success": False, "error":
                        f"No baseline named '{name}' for project "
                        f"'{session.project_name}' — capture one first with action='set'."}
            current_path = baseline_path[:-4] + ".current.png"
            await capture(current_path)
            cmp = do_compare(baseline_path, current_path,
                             threshold=args.get("threshold", 10))
            if cmp.get("success") is False:
                return cmp
            max_diff = float(args.get("max_diff_percent") or 0.5)
            diff_pct = cmp.get("diff_percentage", 100.0)
            return {
                "success": True, "action": "check", "name": name,
                "passed": diff_pct <= max_diff,
                "diff_percentage": diff_pct, "max_diff_percent": max_diff,
                "baseline_path": baseline_path, "current_path": current_path,
                "diff_image_path": cmp.get("diff_image_path"),
                "note": None if diff_pct <= max_diff else
                        "Inspect diff_image_path (changed pixels in red). If the change "
                        "is intended, re-baseline with action='set'.",
            }

        return {"success": False,
                "error": f"Unknown action '{action}' — use 'set' or 'check'."}


@tool("test_responsive")
async def handle_test_responsive(args: dict) -> dict:
        t = await get_tester()
        project_name = args.get("project")  # None -> isolated ephemeral context
        proj_obj = project_manager.get(project_name) if project_name else None
        result = await t.test_responsive(
            url=args["url"],
            project_name=project_name,
            viewports=args.get("viewports"),
            checks=args.get("run_checks"),
            screenshot_dir=proj_obj.screenshot_dir if proj_obj else None,
        )
        return result
