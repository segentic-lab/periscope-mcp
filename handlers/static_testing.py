"""Static testing + results tools (test_url, crawl, reports, responsive, screenshot diff)."""
import asyncio
import json
import os
import time

import config
import interactions
from crawler import Crawler
from runtime import auth_handler, get_tester, project_manager, session_manager
from sessions import real_page

from .registry import tool
from tester import redirected_to_login


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
            await page.goto(project.base_url, wait_until=config.WAIT_UNTIL)
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

        urls = await crawler.crawl(
            context=context,
            start_url=project.base_url,
            max_pages=args.get("max_pages", project.max_pages),
            max_depth=args.get("max_depth", project.max_depth)
        )

        result = {
            "project": project.name,
            "base_url": project.base_url,
            "pages_found": len(urls),
            "urls": urls
        }
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

        # Crawl first
        crawler = Crawler()
        urls = await crawler.crawl(
            context=context,
            start_url=project.base_url,
            max_pages=args.get("max_pages", project.max_pages),
            max_depth=project.max_depth
        )

        # Test all pages — flagging any that land on the login page mid-run
        checks = args.get("checks", project.test_types)
        results = await t.test_multiple(urls, project.name, checks,
                                        screenshot_dir=project.screenshot_dir,
                                        login_url=_form_login_url(project))
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
