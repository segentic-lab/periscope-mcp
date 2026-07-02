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


@tool("test_url")
async def handle_test_url(args: dict) -> dict:
        t = await get_tester()
        project_name = args.get("project", "default")
        checks = args.get("checks")
        proj_obj = project_manager.get(project_name)
        proj_screenshot_dir = proj_obj.screenshot_dir if proj_obj else None

        result = await t.test_url(
            url=args["url"],
            project_name=project_name,
            checks=checks,
            screenshot_dir=proj_screenshot_dir
        )
        return result


@tool("crawl_project")
async def handle_crawl_project(args: dict) -> dict:
        project = project_manager.get(args["project"])
        if not project:
            return {"success": False, "error": f"Project '{args['project']}' not found"}

        t = await get_tester()
        context = await t.get_context(project.name)
        crawler = Crawler()

        urls = await crawler.crawl(
            context=context,
            start_url=project.base_url,
            max_pages=args.get("max_pages", project.max_pages),
            max_depth=args.get("max_depth", project.max_depth)
        )

        return {
            "project": project.name,
            "base_url": project.base_url,
            "pages_found": len(urls),
            "urls": urls
        }


@tool("test_project")
async def handle_test_project(args: dict) -> dict:
        project = project_manager.get(args["project"])
        if not project:
            return {"success": False, "error": f"Project '{args['project']}' not found"}

        t = await get_tester()
        context = await t.get_context(project.name)

        # Crawl first
        crawler = Crawler()
        urls = await crawler.crawl(
            context=context,
            start_url=project.base_url,
            max_pages=args.get("max_pages", project.max_pages),
            max_depth=project.max_depth
        )

        # Test all pages
        checks = args.get("checks", project.test_types)
        results = await t.test_multiple(urls, project.name, checks, screenshot_dir=project.screenshot_dir)

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
        project_name = args.get("project", "default")
        proj_obj = project_manager.get(project_name)
        result = await t.test_responsive(
            url=args["url"],
            project_name=project_name,
            viewports=args.get("viewports"),
            checks=args.get("run_checks"),
            screenshot_dir=proj_obj.screenshot_dir if proj_obj else None,
        )
        return result
