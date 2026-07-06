"""Interactive action tools (click, fill, steps, element queries, dialogs, uploads)."""
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


@tool("click_element")
async def handle_click_element(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        result = await interactions.click_element(
            session.page, args["selector"], force=args.get("force", False)
        )
        session.url = result["url"]
        return await interactions.attach_observation(session, result, args, "after_click")


@tool("fill_form")
async def handle_fill_form(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        result = await interactions.fill_form(
            session.page,
            args["fields"],
            args.get("submit_selector"),
            force=args.get("force", False),
        )
        if result.get("submitted"):
            session.url = result.get("url", session.url)
        return await interactions.attach_observation(session, result, args, "after_fill")


@tool("interact_and_test")
async def handle_interact_and_test(args: dict) -> dict:
        t = await get_tester()
        project = args.get("project")  # None -> isolated ephemeral context in url mode
        project_name = project or "default"
        session_id = args.get("session_id")
        url = args.get("url")
        steps = args["steps"]
        run_checks = args.get("run_checks")
        screenshot_after = args.get("screenshot_after", True)
        continue_on_error = args.get("continue_on_error", False)
        capture_console = args.get("capture_console", False)

        cleanup = None
        session = None
        if session_id:
            session = session_manager.get_session(session_id)
            page = session.page
            shot_dir = session.screenshot_dir
        elif url:
            page, cleanup = await t.open_page(project, url)
            proj_obj = project_manager.get(project) if project else None
            shot_dir = proj_obj.screenshot_dir if proj_obj else None
        else:
            return {"success": False, "error": "Provide either 'url' or 'session_id'"}

        touch = (lambda: setattr(session, "last_accessed", time.time())) if session else None

        # Optional console capture via temporary listeners — immune to the
        # session buffers' front-trimming caps.
        new_logs, new_errors = [], []
        listen_page = real_page(page)

        def on_console(msg):
            (new_errors if msg.type == "error" else new_logs).append(msg.text)

        def on_pageerror(err):
            new_errors.append(str(err))

        if capture_console:
            listen_page.on("console", on_console)
            listen_page.on("pageerror", on_pageerror)

        try:
            result = await interactions.execute_steps(
                page, steps, project_name, continue_on_error, screenshot_dir=shot_dir,
                touch=touch,
            )
            if capture_console:
                result["console_log"] = new_logs
                result["console_errors"] = new_errors
                result["console_log_count"] = len(new_logs)
                result["console_error_count"] = len(new_errors)

            if screenshot_after:
                path = await interactions.take_screenshot(page, project_name, "after_steps", screenshot_dir=shot_dir)
                result["screenshot_path"] = path

            # Real INP for the interactions these steps just drove (None if none)
            inp = await interactions.read_inp(page)
            if inp:
                result["interaction_to_next_paint_ms"] = inp["inp_ms"]
                result["inp_interaction_count"] = inp["interaction_count"]

            if run_checks and result["success"]:
                from checks.visual import check_visual
                from checks.accessibility import check_accessibility
                from checks.functionality import check_functionality, check_seo, get_performance_metrics
                from checks.geo import check_geo

                all_issues = []
                if "visual" in run_checks:
                    all_issues.extend(await check_visual(page))
                if "accessibility" in run_checks:
                    all_issues.extend(await check_accessibility(page))
                if "functionality" in run_checks:
                    all_issues.extend(await check_functionality(page))
                if "seo" in run_checks:
                    all_issues.extend(await check_seo(page))
                if "geo" in run_checks:
                    all_issues.extend(await check_geo(page))
                if "performance" in run_checks:
                    result["performance"] = await get_performance_metrics(page)

                result["issues"] = all_issues
                result["issue_count"] = len(all_issues)

            if session_id:
                session.url = page.url

            return result
        finally:
            if capture_console:
                listen_page.remove_listener("console", on_console)
                listen_page.remove_listener("pageerror", on_pageerror)
            if cleanup:
                await cleanup()


@tool("get_page_elements")
async def handle_get_page_elements(args: dict) -> dict:
        t = await get_tester()
        session_id = args.get("session_id")
        url = args.get("url")
        max_results = args.get("max_results", 50)
        attributes = args.get("attributes")
        full_text = args.get("full_text", False)

        cleanup = None
        if session_id:
            session = session_manager.get_session(session_id)
            page = session.page
        elif url:
            page, cleanup = await t.open_page(args.get("project"), url)
        else:
            return {"success": False, "error": "Provide either 'url' or 'session_id'"}

        try:
            try:
                elements = await interactions.get_elements(
                    page, args["selector"], max_results, attributes=attributes, full_text=full_text
                )
            except Exception as e:
                if "not a valid selector" in str(e) or "SyntaxError" in str(e):
                    return {
                        "success": False,
                        "error": f"Invalid CSS selector '{args['selector']}'. This tool accepts "
                                 f"standard CSS only — Playwright pseudo-classes like :has-text() "
                                 f"and :visible are not supported here.",
                    }
                raise
            result = {
                "selector": args["selector"],
                "count": len(elements),
                "elements": elements,
                "url": page.url,
            }
            if attributes:
                result["attributes_requested"] = attributes
            return result
        finally:
            if cleanup:
                await cleanup()


# Per-session pending dialog handler and info captured when the last dialog fired.
# Keyed by session_id so repeated handle_dialog calls replace (not stack) handlers.
_pending_dialog = {}
_last_dialog = {}


@tool("handle_dialog")
async def handle_handle_dialog(args: dict) -> dict:
        session_id = args["session_id"]
        session = session_manager.get_session(session_id)
        dialog_page = real_page(session.page)
        action = args["action"]
        prompt_text = args.get("prompt_text")

        # Replace any still-pending handler from a previous call — stacked
        # handlers would all fire on the next dialog and double-handle it.
        prev = _pending_dialog.pop(session_id, None)
        if prev is not None:
            try:
                dialog_page.remove_listener("dialog", prev)
            except Exception:
                pass

        async def handle(dialog):
            _last_dialog[session_id] = {
                "type": dialog.type,
                "message": dialog.message,
                "default_value": dialog.default_value,
                "action_taken": action,
            }
            _pending_dialog.pop(session_id, None)
            if action == "accept":
                if prompt_text is not None:
                    await dialog.accept(prompt_text)
                else:
                    await dialog.accept()
            else:
                await dialog.dismiss()

        _pending_dialog[session_id] = handle
        dialog_page.once("dialog", handle)

        return {
            "success": True,
            "message": f"Dialog handler set: will {action} next dialog",
            "prompt_text": prompt_text,
            "last_dialog": _last_dialog.get(session_id),
        }


@tool("upload_file")
async def handle_upload_file(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        locator = session.page.locator(args["selector"]).first
        files = args["files"]

        # Verify files exist
        missing = [f for f in files if not os.path.exists(f)]
        if missing:
            return {"success": False, "error": f"Files not found: {missing}"}

        await locator.set_input_files(files)
        screenshot_path = await interactions.take_screenshot(
            session.page, session.project_name, "after_upload", screenshot_dir=session.screenshot_dir)
        return {
            "success": True,
            "files_set": files,
            "screenshot_path": screenshot_path,
        }


@tool("flow")
async def handle_flow(args: dict) -> dict:
        """Named, saved step sequences — define a workflow once (login, checkout,
        smoke path), re-run it any session. Deliberately minimal: verification
        composes via assert_all / visual_check after the run, and the runner is
        interact_and_test's own executor — same 25 actions, same semantics."""
        import re as _re

        action = args.get("action", "list")
        flows_dir = os.path.join(config.DATA_DIR, "flows")
        os.makedirs(flows_dir, exist_ok=True)

        def flow_path(name):
            if not name or not _re.fullmatch(r"[A-Za-z0-9._-]{1,80}", name):
                return None
            return os.path.join(flows_dir, f"{name}.json")

        if action == "list":
            flows = []
            for f in sorted(os.listdir(flows_dir)):
                if f.endswith(".json"):
                    try:
                        d = json.load(open(os.path.join(flows_dir, f)))
                        flows.append({"name": f[:-5], "steps": len(d.get("steps", [])),
                                      "description": d.get("description")})
                    except Exception:
                        flows.append({"name": f[:-5], "error": "unreadable"})
            return {"success": True, "flows": flows, "count": len(flows)}

        name = args.get("name", "")
        path = flow_path(name)
        if path is None:
            return {"success": False, "error":
                    "flow requires 'name': 1-80 chars of letters, digits, . _ - "
                    "(e.g. 'login', 'checkout-smoke')."}

        if action == "save":
            steps = args.get("steps")
            if not isinstance(steps, list) or not steps:
                return {"success": False, "error":
                        "flow save requires 'steps': a non-empty array in "
                        "interact_and_test's step format."}
            replaced = os.path.exists(path)
            with open(path, "w") as f:
                json.dump({"name": name, "steps": steps,
                           "description": args.get("description")}, f, indent=2)
            return {"success": True, "action": "save", "name": name,
                    "steps": len(steps), "replaced": replaced}

        if action == "delete":
            if not os.path.exists(path):
                return {"success": False, "error": f"No flow named '{name}'."}
            os.remove(path)
            return {"success": True, "action": "delete", "name": name}

        if action == "run":
            if not os.path.exists(path):
                return {"success": False, "error":
                        f"No flow named '{name}' — see action='list'."}
            flow_def = json.load(open(path))
            session = session_manager.get_session(args["session_id"])
            result = await interactions.execute_steps(
                session.page, flow_def["steps"],
                project_name=session.project_name,
                continue_on_error=bool(args.get("continue_on_error")),
                screenshot_dir=session.screenshot_dir,
                touch=lambda: session_manager.get_session(session.session_id),
            )
            session.url = real_page(session.page).url
            return {"flow": name, **result}

        return {"success": False,
                "error": f"Unknown action '{action}' — use 'save', 'run', 'list', or 'delete'."}


@tool("wait_for_network")
async def handle_wait_for_network(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        url_pattern = args.get("url_pattern")
        if not url_pattern:
            return {"success": False, "error":
                    "wait_for_network requires 'url_pattern' — a plain substring of the "
                    "request URL to wait for (e.g. '/api/tasks'), not a regex. To wait for "
                    "general quiet instead, use a 'wait' step or wait_for_gone on a spinner."}
        method_filter = args.get("method")
        timeout = args.get("timeout", 30000)

        # Must be a plain function: Playwright calls predicates synchronously,
        # and a coroutine object is always truthy (filter would never apply).
        def match_request(response):
            if url_pattern not in response.url:
                return False
            if method_filter and response.request.method.upper() != method_filter.upper():
                return False
            return True

        try:
            response = await real_page(session.page).wait_for_event(
                "response",
                predicate=match_request,
                timeout=timeout,
            )
            return {
                "success": True,
                "matched_url": response.url,
                "method": response.request.method,
                "status": response.status,
                "url_pattern": url_pattern,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Timeout waiting for network request matching '{url_pattern}': {e}",
                "url_pattern": url_pattern,
                "timeout_ms": timeout,
            }


@tool("scroll_into_view")
async def handle_scroll_into_view(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        locator = session.page.locator(args["selector"]).first
        await locator.scroll_into_view_if_needed(timeout=10000)
        result = {"success": True, "selector": args["selector"]}
        return await interactions.attach_observation(session, result, args, "after_scroll")


@tool("wait_for_gone")
async def handle_wait_for_gone(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        timeout = args.get("timeout", 30000)
        start = time.time()
        try:
            locator = session.page.locator(args["selector"]).first
            await locator.wait_for(state="hidden", timeout=timeout)
            elapsed_ms = round((time.time() - start) * 1000)
            return {
                "success": True,
                "selector": args["selector"],
                "elapsed_ms": elapsed_ms,
            }
        except Exception as e:
            elapsed_ms = round((time.time() - start) * 1000)
            return {
                "success": False,
                "selector": args["selector"],
                "elapsed_ms": elapsed_ms,
                "error": str(e),
            }


@tool("select_option")
async def handle_select_option(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        result = await interactions.select_option(
            session.page,
            args["selector"],
            value=args.get("value"),
            label=args.get("label"),
            index=args.get("index"),
            element_index=int(args.get("element_index") or 0),
        )
        return await interactions.attach_observation(session, result, args, "after_select_option")
