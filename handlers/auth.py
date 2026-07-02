"""Authentication tools (form login, basic auth, cookies, copy)."""
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


@tool("set_form_login")
async def handle_set_form_login(args: dict) -> dict:
        success = project_manager.set_form_login(
            name=args["project"],
            login_url=args["login_url"],
            username=args["username"],
            password=args["password"],
            username_selector=args.get("username_selector"),
            password_selector=args.get("password_selector"),
            submit_selector=args.get("submit_selector")
        )
        if success:
            return {"success": True, "message": "Form login configured"}
        return {"success": False, "error": f"Project '{args['project']}' not found"}


@tool("set_basic_auth")
async def handle_set_basic_auth(args: dict) -> dict:
        success = project_manager.set_basic_auth(
            name=args["project"],
            username=args["username"],
            password=args["password"]
        )
        if success:
            return {"success": True, "message": "HTTP Basic Auth configured"}
        return {"success": False, "error": f"Project '{args['project']}' not found"}


@tool("set_cookies")
async def handle_set_cookies(args: dict) -> dict:
        cookies = args["cookies"]
        if not isinstance(cookies, list) or not all(isinstance(c, dict) for c in cookies):
            return {
                "success": False,
                "error": "cookies must be an array of objects like "
                         '{"name": ..., "value": ..., "domain": ..., "path": "/"}',
            }
        for c in cookies:
            missing = [k for k in ("name", "value", "domain") if not c.get(k)]
            if missing:
                return {"success": False, "error": f"Cookie missing required field(s) {missing}: {c}"}
            # Playwright's add_cookies requires url or a domain+path pair
            c.setdefault("path", "/")

        success = project_manager.set_cookies(
            name=args["project"],
            cookies=cookies
        )
        if success:
            return {"success": True, "message": f"Set {len(cookies)} cookies"}
        return {"success": False, "error": f"Project '{args['project']}' not found"}


@tool("login_project")
async def handle_login_project(args: dict) -> dict:
        project = project_manager.get(args["project"])
        if not project:
            return {"success": False, "error": f"Project '{args['project']}' not found"}

        t = await get_tester()
        context = await t.get_context(project.name)
        result = await auth_handler.login(context, project)

        if result["success"]:
            project_manager.mark_logged_in(project.name, True)

        return result


@tool("copy_auth")
async def handle_copy_auth(args: dict) -> dict:
        source = project_manager.get(args["from_project"])
        if not source:
            return {"success": False, "error": f"Source project '{args['from_project']}' not found"}
        target = project_manager.get(args["to_project"])
        if not target:
            return {"success": False, "error": f"Target project '{args['to_project']}' not found"}
        if not source.auth or not source.auth.method:
            return {"success": False, "error": f"Source project '{args['from_project']}' has no auth configured"}

        import copy
        target.auth = copy.deepcopy(source.auth)
        target.is_logged_in = False
        project_manager._save()

        # Also carry over live login state if the source is logged in
        if source.is_logged_in:
            t = await get_tester()
            target_ctx = await t.get_context(target.name)
            if target.auth.method == "basic":
                # Basic auth lives in a context route, not cookies — install it
                # on the target context by performing the login there.
                result = await auth_handler.login(target_ctx, target)
                if result.get("success"):
                    target.is_logged_in = True
                    project_manager._save()
            elif source.name in t.contexts:
                source_ctx = t.contexts[source.name]
                cookies = await source_ctx.cookies()
                await target_ctx.add_cookies(cookies)
                target.is_logged_in = True
                project_manager._save()

        return {
            "success": True,
            "message": f"Auth copied from '{args['from_project']}' to '{args['to_project']}'",
            "method": target.auth.method,
            "session_copied": target.is_logged_in,
        }
