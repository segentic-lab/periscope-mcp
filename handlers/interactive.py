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


async def _open_ephemeral_page(t, project_name: str, url: str):
    """Create a page in the project context and navigate; close it if goto fails
    so failed navigations don't leak live pages into the shared context."""
    context = await t.get_context(project_name)
    page = await context.new_page()
    page.set_default_timeout(config.TIMEOUT)
    try:
        await page.goto(url, wait_until=config.WAIT_UNTIL)
    except Exception:
        await page.close()
        raise
    return page


@tool("click_element")
async def handle_click_element(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        result = await interactions.click_element(
            session.page, args["selector"], force=args.get("force", False)
        )
        session.url = result["url"]
        screenshot_path = await interactions.take_screenshot(
            session.page, session.project_name, "after_click", screenshot_dir=session.screenshot_dir)
        result["screenshot_path"] = screenshot_path
        return result


@tool("fill_form")
async def handle_fill_form(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        result = await interactions.fill_form(
            session.page,
            args["fields"],
            args.get("submit_selector"),
        )
        if result.get("submitted"):
            session.url = result.get("url", session.url)
        screenshot_path = await interactions.take_screenshot(
            session.page, session.project_name, "after_fill", screenshot_dir=session.screenshot_dir)
        result["screenshot_path"] = screenshot_path
        return result


@tool("interact_and_test")
async def handle_interact_and_test(args: dict) -> dict:
        t = await get_tester()
        project_name = args.get("project", "default")
        session_id = args.get("session_id")
        url = args.get("url")
        steps = args["steps"]
        run_checks = args.get("run_checks")
        screenshot_after = args.get("screenshot_after", True)
        continue_on_error = args.get("continue_on_error", False)

        ephemeral = False
        session = None
        if session_id:
            session = session_manager.get_session(session_id)
            page = session.page
            shot_dir = session.screenshot_dir
        elif url:
            page = await _open_ephemeral_page(t, project_name, url)
            ephemeral = True
            proj_obj = project_manager.get(project_name)
            shot_dir = proj_obj.screenshot_dir if proj_obj else None
        else:
            return {"success": False, "error": "Provide either 'url' or 'session_id'"}

        touch = (lambda: setattr(session, "last_accessed", time.time())) if session else None
        try:
            result = await interactions.execute_steps(
                page, steps, project_name, continue_on_error, screenshot_dir=shot_dir,
                touch=touch,
            )

            if screenshot_after:
                path = await interactions.take_screenshot(page, project_name, "after_steps", screenshot_dir=shot_dir)
                result["screenshot_path"] = path

            if run_checks and result["success"]:
                from checks.visual import check_visual
                from checks.accessibility import check_accessibility
                from checks.functionality import check_functionality, check_seo, get_performance_metrics

                all_issues = []
                if "visual" in run_checks:
                    all_issues.extend(await check_visual(page))
                if "accessibility" in run_checks:
                    all_issues.extend(await check_accessibility(page))
                if "functionality" in run_checks:
                    all_issues.extend(await check_functionality(page))
                if "seo" in run_checks:
                    all_issues.extend(await check_seo(page))
                if "performance" in run_checks:
                    result["performance"] = await get_performance_metrics(page)

                result["issues"] = all_issues
                result["issue_count"] = len(all_issues)

            if session_id:
                session.url = page.url

            return result
        finally:
            if ephemeral:
                await page.close()


@tool("get_page_elements")
async def handle_get_page_elements(args: dict) -> dict:
        t = await get_tester()
        project_name = args.get("project", "default")
        session_id = args.get("session_id")
        url = args.get("url")
        max_results = args.get("max_results", 50)

        ephemeral = False
        if session_id:
            session = session_manager.get_session(session_id)
            page = session.page
        elif url:
            page = await _open_ephemeral_page(t, project_name, url)
            ephemeral = True
        else:
            return {"success": False, "error": "Provide either 'url' or 'session_id'"}

        try:
            elements = await interactions.get_elements(page, args["selector"], max_results)
            return {
                "selector": args["selector"],
                "count": len(elements),
                "elements": elements,
                "url": page.url,
            }
        finally:
            if ephemeral:
                await page.close()


@tool("extract_text")
async def handle_extract_text(args: dict) -> dict:
        t = await get_tester()
        project_name = args.get("project", "default")
        session_id = args.get("session_id")
        url = args.get("url")

        ephemeral = False
        if session_id:
            session = session_manager.get_session(session_id)
            page = session.page
        elif url:
            page = await _open_ephemeral_page(t, project_name, url)
            ephemeral = True
        else:
            return {"success": False, "error": "Provide either 'url' or 'session_id'"}

        try:
            texts = await page.evaluate("""(selector) => {
                const els = document.querySelectorAll(selector);
                return Array.from(els).map(el => ({
                    tag: el.tagName.toLowerCase(),
                    text: el.textContent.trim(),
                    id: el.id || null,
                    class: el.className || null,
                }));
            }""", args["selector"])
            return {
                "selector": args["selector"],
                "count": len(texts),
                "elements": texts,
                "url": page.url,
            }
        finally:
            if ephemeral:
                await page.close()


@tool("get_attribute")
async def handle_get_attribute(args: dict) -> dict:
        t = await get_tester()
        project_name = args.get("project", "default")
        session_id = args.get("session_id")
        url = args.get("url")
        max_results = args.get("max_results", 50)
        attributes = args["attributes"]

        ephemeral = False
        if session_id:
            session = session_manager.get_session(session_id)
            page = session.page
        elif url:
            page = await _open_ephemeral_page(t, project_name, url)
            ephemeral = True
        else:
            return {"success": False, "error": "Provide either 'url' or 'session_id'"}

        try:
            elements = await page.evaluate("""(args) => {
                const [selector, attrs, maxResults] = args;
                const els = document.querySelectorAll(selector);
                const results = [];
                for (let i = 0; i < Math.min(els.length, maxResults); i++) {
                    const el = els[i];
                    const entry = {
                        tag: el.tagName.toLowerCase(),
                        index: i,
                    };
                    for (const attr of attrs) {
                        entry[attr] = el.getAttribute(attr);
                    }
                    // Always include identifying info
                    entry.id = el.id || null;
                    entry.text = (el.textContent || '').trim().substring(0, 80);
                    results.push(entry);
                }
                return results;
            }""", [args["selector"], attributes, max_results])
            return {
                "selector": args["selector"],
                "attributes_requested": attributes,
                "count": len(elements),
                "elements": elements,
                "url": page.url,
            }
        finally:
            if ephemeral:
                await page.close()


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


@tool("wait_for_network")
async def handle_wait_for_network(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        url_pattern = args["url_pattern"]
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


@tool("force_fill")
async def handle_force_fill(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        await interactions.force_fill(session.page, args["selector"], args["value"])
        screenshot_path = await interactions.take_screenshot(
            session.page, session.project_name, "after_force_fill", screenshot_dir=session.screenshot_dir)
        return {
            "success": True,
            "selector": args["selector"],
            "value": args["value"],
            "screenshot_path": screenshot_path,
        }


@tool("scroll_into_view")
async def handle_scroll_into_view(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        locator = session.page.locator(args["selector"]).first
        await locator.scroll_into_view_if_needed(timeout=10000)
        screenshot_path = await interactions.take_screenshot(
            session.page, session.project_name, "after_scroll", screenshot_dir=session.screenshot_dir)
        return {
            "success": True,
            "selector": args["selector"],
            "screenshot_path": screenshot_path,
        }


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
        )
        screenshot_path = await interactions.take_screenshot(
            session.page, session.project_name, "after_select_option", screenshot_dir=session.screenshot_dir)
        result["screenshot_path"] = screenshot_path
        return result
