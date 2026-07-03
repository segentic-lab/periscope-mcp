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


def _replaced_method_warning(project_name: str, new_method: str) -> dict:
    """Extra response keys when a set_* auth call replaces a different method.

    A project has exactly one auth config — silently flipping method=basic to
    method=cookies surprised agents (issue #6). Still allowed, but announced.
    """
    project = project_manager.get(project_name)
    prev = project.auth.method if project and project.auth else None
    if prev and prev != new_method:
        return {
            "replaced_auth_method": prev,
            "warning": f"This replaced the project's previous '{prev}' auth config — "
                       f"a project holds one auth method at a time.",
        }
    return {}


@tool("set_form_login")
async def handle_set_form_login(args: dict) -> dict:
        extra = _replaced_method_warning(args["project"], "form")
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
            return {"success": True,
                    "message": f"Form login configured — call login_project('{args['project']}') to execute it",
                    **extra}
        return {"success": False, "error": f"Project '{args['project']}' not found"}


@tool("set_basic_auth")
async def handle_set_basic_auth(args: dict) -> dict:
        extra = _replaced_method_warning(args["project"], "basic")
        success = project_manager.set_basic_auth(
            name=args["project"],
            username=args["username"],
            password=args["password"]
        )
        if success:
            return {"success": True,
                    "message": f"HTTP Basic Auth configured — call login_project('{args['project']}') to apply it",
                    **extra}
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

        extra = _replaced_method_warning(args["project"], "cookies")
        success = project_manager.set_cookies(
            name=args["project"],
            cookies=cookies
        )
        if success:
            # "Set N cookies" implied they were live — they're only stored
            # config until login_project injects them (issue #6).
            return {"success": True,
                    "message": f"Stored {len(cookies)} cookies for project '{args['project']}' — "
                               f"call login_project('{args['project']}') to inject them into the browser",
                    **extra}
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


@tool("interactive_login")
async def handle_interactive_login(args: dict) -> dict:
        project = project_manager.get(args["project"])
        if not project:
            return {"success": False, "error": f"Project '{args['project']}' not found"}

        # Where to land: explicit login_url, else the form-login URL, else base_url
        url = args.get("login_url")
        if not url and project.auth and project.auth.method == "form" and project.auth.form_login:
            url = project.auth.form_login.login_url
        url = url or project.base_url

        t = await get_tester()
        try:
            await t.launch_interactive_login(project.name, url)
        except RuntimeError as e:
            return {"success": False, "error": str(e)}
        return {
            "success": True,
            "project": project.name,
            "login_url": url,
            "message": f"A visible browser opened at {url}. Complete the login by hand "
                       f"(password, 2FA, SSO, CAPTCHA — whatever the site needs), then call "
                       f"save_login('{project.name}') to save the session. Future sessions on "
                       f"this project run headlessly with the saved login.",
        }


@tool("save_login")
async def handle_save_login(args: dict) -> dict:
        project = project_manager.get(args["project"])
        if not project:
            return {"success": False, "error": f"Project '{args['project']}' not found"}

        t = await get_tester()
        try:
            state = await t.capture_login(project.name)
        except KeyError:
            return {
                "success": False,
                "error": f"No interactive login in progress for '{project.name}'. "
                         f"Call interactive_login('{project.name}') first.",
            }
        project_manager.set_session_state(project.name, state)
        # Re-seed any cached contexts so subsequent sessions pick up the login
        await t.close_context(project.name)

        return {
            "success": True,
            "project": project.name,
            "cookies_saved": len(state.get("cookies", [])),
            "origins_saved": len(state.get("origins", [])),
            "message": f"Saved login session for '{project.name}'. Open sessions or run "
                       f"test_project on it and they'll be authenticated headlessly. Re-run "
                       f"interactive_login when the session expires.",
        }


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

        # Carry over live login state if the source is logged in. SPAs keep
        # auth tokens in localStorage as often as in cookies (issue #7), so a
        # cookie-only copy can silently produce a logged-out "copy".
        session_copied = False
        copied = []
        note = None
        if source.is_logged_in:
            t = await get_tester()
            if target.auth.method == "basic":
                # Basic auth lives in a context route, not cookies — install it
                # on the target context by performing the login there.
                target_ctx = await t.get_context(target.name)
                result = await auth_handler.login(target_ctx, target)
                if result.get("success"):
                    session_copied = True
                    copied = ["basic-auth route"]
            elif source.name in t.contexts:
                source_ctx = t.contexts[source.name]
                state = await source_ctx.storage_state()
                if target.name not in t.contexts:
                    # Full transfer: create the target context pre-seeded with
                    # the source's cookies AND localStorage.
                    t.contexts[target.name] = await t.browser.new_context(
                        viewport={"width": config.VIEWPORT_WIDTH, "height": config.VIEWPORT_HEIGHT},
                        ignore_https_errors=True,
                        storage_state=state,
                    )
                    session_copied = True
                    copied = ["cookies", "localStorage"]
                else:
                    # Target context already exists — Playwright can only add
                    # cookies to it. Be honest: apps holding tokens in
                    # localStorage will NOT be logged in.
                    await t.contexts[target.name].add_cookies(state.get("cookies", []))
                    copied = ["cookies"]
                    session_copied = False
                    note = ("target context already existed, so only cookies were transferred "
                            "(not localStorage) — run login_project if the app doesn't "
                            "authenticate from cookies alone")
            if session_copied:
                target.is_logged_in = True
                project_manager._save()

        result = {
            "success": True,
            "message": f"Auth copied from '{args['from_project']}' to '{args['to_project']}'",
            "method": target.auth.method,
            "session_copied": session_copied,
            "copied": copied,
        }
        if note:
            result["note"] = note
        if not session_copied:
            result["message"] += f" — run login_project('{args['to_project']}') to authenticate"
        return result
