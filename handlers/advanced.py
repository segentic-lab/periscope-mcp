"""Advanced tools (network mocking, storage, iframes, CSS, emulation, recording, console)."""
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


@tool("record_session")
async def handle_record_session(args: dict) -> dict:
        t = await get_tester()
        project_name = args.get("project", "default")
        proj_obj = project_manager.get(project_name)
        proj_screenshot_dir = proj_obj.screenshot_dir if proj_obj else None
        video_dir = os.path.join(config.DATA_DIR, "videos", project_name)
        os.makedirs(video_dir, exist_ok=True)

        context_kwargs = dict(
            viewport={"width": config.VIEWPORT_WIDTH, "height": config.VIEWPORT_HEIGHT},
            record_video_dir=video_dir,
            ignore_https_errors=True,
        )
        # Video recording needs a fresh context, so carry over the project
        # context's cookies/storage — otherwise authenticated flows record logged-out.
        if proj_obj and proj_obj.is_logged_in and project_name in t.contexts:
            context_kwargs["storage_state"] = await t.contexts[project_name].storage_state()
        context = await t.browser.new_context(**context_kwargs)
        page = await context.new_page()
        page.set_default_timeout(config.TIMEOUT)

        video = page.video
        result, error = None, None
        try:
            await page.goto(args["url"], wait_until=config.WAIT_UNTIL)
            result = await interactions.execute_steps(
                page, args["steps"], project_name, screenshot_dir=proj_screenshot_dir
            )
        except Exception as e:
            error = str(e)
        finally:
            # Closing finalizes the video file even when steps failed
            try:
                await page.close()
            finally:
                await context.close()

        video_path = await video.path() if video else None
        if error:
            return {"success": False, "error": error, "video_path": video_path}
        result["video_path"] = video_path
        return result


@tool("check_console_during_interaction")
async def handle_check_console_during_interaction(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        # Capture via temporary listeners: the session buffers are front-trimmed
        # at their cap, so len()-offset slicing loses output on chatty pages.
        listen_page = real_page(session.page)
        new_logs, new_errors = [], []

        def on_console(msg):
            (new_errors if msg.type == "error" else new_logs).append(msg.text)

        def on_pageerror(err):
            new_errors.append(str(err))

        listen_page.on("console", on_console)
        listen_page.on("pageerror", on_pageerror)
        try:
            result = await interactions.execute_steps(
                session.page, args["steps"], session.project_name,
                screenshot_dir=session.screenshot_dir
            )
        finally:
            listen_page.remove_listener("console", on_console)
            listen_page.remove_listener("pageerror", on_pageerror)
        session.url = session.page.url

        result["console_log"] = new_logs
        result["console_errors"] = new_errors
        result["console_log_count"] = len(new_logs)
        result["console_error_count"] = len(new_errors)
        return result


@tool("get_console_errors")
async def handle_get_console_errors(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        clear = args.get("clear", True)

        # Return the full buffers (already capped at MAX_CONSOLE_LOG) — clearing
        # after returning only a tail would silently discard the rest.
        result = {
            "console_errors": list(session.console_errors),
            "console_log": list(session.console_log),
            "error_count": len(session.console_errors),
            "log_count": len(session.console_log),
        }

        if clear:
            session.console_log.clear()
            session.console_errors.clear()

        return result


@tool("intercept_network")
async def handle_intercept_network(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        route_page = real_page(session.page)
        url_pattern = args["url_pattern"]
        status = args.get("status", 200)
        body = args.get("body", "")
        if not isinstance(body, str):
            body = json.dumps(body)  # defensive: a dict/list still becomes a valid response body
        content_type = args.get("content_type", "application/json")
        method_filter = args.get("method")
        once = args.get("once", False)

        # A callable matcher gives true substring semantics — a glob like
        # f"**{pattern}**" breaks on metachars common in URLs (?, [], *).
        def matcher(url, _pat=url_pattern):
            return _pat in url

        async def handle_route(route):
            if method_filter and route.request.method.upper() != method_filter.upper():
                await route.continue_()
                return
            await route.fulfill(
                status=status,
                body=body,
                content_type=content_type,
            )
            if once:
                await route_page.unroute(matcher, handle_route)
                session.intercepts = [i for i in session.intercepts if i["handler"] is not handle_route]

        await route_page.route(matcher, handle_route)
        session.intercepts.append({"matcher": matcher, "handler": handle_route, "pattern": url_pattern})

        return {
            "success": True,
            "message": f"Intercepting requests matching '{url_pattern}' → {status}",
            "url_pattern": url_pattern,
            "status": status,
            "once": once,
            "active_intercepts": [i["pattern"] for i in session.intercepts],
        }


@tool("clear_intercepts")
async def handle_clear_intercepts(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        route_page = real_page(session.page)
        pattern_filter = args.get("url_pattern")

        removed, remaining = [], []
        for entry in session.intercepts:
            if pattern_filter and entry["pattern"] != pattern_filter:
                remaining.append(entry)
                continue
            try:
                await route_page.unroute(entry["matcher"], entry["handler"])
            except Exception:
                pass
            removed.append(entry["pattern"])
        session.intercepts = remaining

        return {
            "success": True,
            "removed": removed,
            "removed_count": len(removed),
            "active_intercepts": [i["pattern"] for i in remaining],
        }


@tool("get_local_storage")
async def handle_get_local_storage(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        storage_type = args.get("storage", "local")
        keys = args.get("keys")

        storage_obj = "localStorage" if storage_type == "local" else "sessionStorage"

        if keys:
            data = await session.page.evaluate(f"""(keys) => {{
                const result = {{}};
                for (const key of keys) {{
                    result[key] = {storage_obj}.getItem(key);
                }}
                return result;
            }}""", keys)
        else:
            data = await session.page.evaluate(f"""() => {{
                const result = {{}};
                for (let i = 0; i < {storage_obj}.length; i++) {{
                    const key = {storage_obj}.key(i);
                    result[key] = {storage_obj}.getItem(key);
                }}
                return result;
            }}""")

        return {
            "storage": storage_type,
            "entries": data,
            "count": len(data),
        }


@tool("set_local_storage")
async def handle_set_local_storage(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        storage_type = args.get("storage", "local")
        entries = args["entries"]
        clear_first = args.get("clear_first", False)

        storage_obj = "localStorage" if storage_type == "local" else "sessionStorage"

        if clear_first:
            await session.page.evaluate(f"{storage_obj}.clear()")

        await session.page.evaluate(f"""(entries) => {{
            for (const [key, value] of Object.entries(entries)) {{
                {storage_obj}.setItem(key, value);
            }}
        }}""", entries)

        return {
            "success": True,
            "storage": storage_type,
            "keys_set": list(entries.keys()),
            "cleared_first": clear_first,
        }


@tool("select_iframe")
async def handle_select_iframe(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])

        # Get the actual Frame: Locator.content_frame is a FrameLocator property,
        # so we must go through an ElementHandle for the awaitable content_frame().
        iframe_element = session.page.locator(args["selector"]).first
        await iframe_element.wait_for(state="attached", timeout=10000)
        handle = await iframe_element.element_handle()
        content_frame = await handle.content_frame() if handle else None

        if not content_frame:
            return {"success": False, "error": f"Could not access iframe content for '{args['selector']}'"}

        # Create a new session entry pointing to the iframe's frame as a page-like object
        import uuid
        iframe_session_id = uuid.uuid4().hex[:12]
        from sessions import PageSession
        now = time.time()

        # The frame object supports most Page methods (evaluate, locator, etc.)
        iframe_session = PageSession(
            session_id=iframe_session_id,
            project_name=session.project_name,
            page=content_frame,
            url=content_frame.url,
            created_at=now,
            last_accessed=now,
            screenshot_dir=session.screenshot_dir,
            parent_session_id=session.session_id,
        )
        session_manager.register_session(iframe_session)

        return {
            "success": True,
            "iframe_session_id": iframe_session_id,
            "parent_session_id": session.session_id,
            "iframe_url": content_frame.url,
            "selector": args["selector"],
        }


@tool("get_computed_style")
async def handle_get_computed_style(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        css_props = args["properties"]
        max_results = args.get("max_results", 10)

        elements = await session.page.evaluate("""(args) => {
            const [selector, props, maxResults] = args;
            const els = document.querySelectorAll(selector);
            const results = [];
            for (let i = 0; i < Math.min(els.length, maxResults); i++) {
                const el = els[i];
                const style = window.getComputedStyle(el);
                const entry = {
                    index: i,
                    tag: el.tagName.toLowerCase(),
                    id: el.id || null,
                    text: (el.textContent || '').trim().substring(0, 60),
                };
                for (const prop of props) {
                    entry[prop] = style.getPropertyValue(prop);
                }
                results.push(entry);
            }
            return results;
        }""", [args["selector"], css_props, max_results])

        return {
            "selector": args["selector"],
            "properties_requested": css_props,
            "count": len(elements),
            "elements": elements,
        }


@tool("emulate_network")
async def handle_emulate_network(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        preset = args["preset"]

        # Reuse one CDP session per page — creating a new one per call leaks them
        if session.cdp_session is None:
            cdp_page = real_page(session.page)
            session.cdp_session = await cdp_page.context.new_cdp_session(cdp_page)
        cdp = session.cdp_session

        if preset == "offline":
            await cdp.send("Network.emulateNetworkConditions", {
                "offline": True,
                "downloadThroughput": 0,
                "uploadThroughput": 0,
                "latency": 0,
            })
        elif preset == "slow_3g":
            await cdp.send("Network.emulateNetworkConditions", {
                "offline": False,
                "downloadThroughput": 500 * 1024 // 8,
                "uploadThroughput": 500 * 1024 // 8,
                "latency": 400,
            })
        elif preset == "fast_3g":
            await cdp.send("Network.emulateNetworkConditions", {
                "offline": False,
                "downloadThroughput": 1500 * 1024 // 8,
                "uploadThroughput": 750 * 1024 // 8,
                "latency": 150,
            })
        elif preset == "reset":
            await cdp.send("Network.emulateNetworkConditions", {
                "offline": False,
                "downloadThroughput": -1,
                "uploadThroughput": -1,
                "latency": 0,
            })

        return {
            "success": True,
            "preset": preset,
            "message": f"Network emulation set to '{preset}'",
        }


@tool("test_dark_mode")
async def handle_test_dark_mode(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        mode = args["mode"]

        await real_page(session.page).emulate_media(color_scheme=mode)
        # Give page a moment to re-render
        await asyncio.sleep(0.3)

        screenshot_path = await interactions.take_screenshot(
            session.page, session.project_name, f"dark_mode_{mode}", screenshot_dir=session.screenshot_dir)
        return {
            "mode": mode,
            "screenshot_path": screenshot_path,
            "url": session.url,
        }
