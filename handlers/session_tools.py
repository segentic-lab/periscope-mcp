"""Session lifecycle tools (open/close/list, viewport, history, screenshots)."""
import asyncio
import json
import os
import time

import config
import devices
import interactions
from crawler import Crawler
from runtime import auth_handler, get_tester, project_manager, session_manager
from sessions import real_page

from .registry import tool


@tool("open_session")
async def handle_open_session(args: dict) -> dict:
        t = await get_tester()
        project = args.get("project")
        project_name = project or "default"
        headed = args.get("headed", False)
        proj_obj = project_manager.get(project) if project else None
        proj_screenshot_dir = proj_obj.screenshot_dir if proj_obj else None

        # With a project: share its (authenticated) context. Without: a private
        # context per session, so unrelated targets never see each other's
        # cookies (issue #8). Closed together with the session.
        # headed=true opens a real visible window (needs a display).
        # Device emulation: a size preset only resizes the page; a full
        # descriptor (UA/DPR/touch) needs its own context, seeded with the
        # project's login state so auth is preserved.
        device = args.get("device")
        viewport = None
        descriptor = None
        if device:
            try:
                kind, resolved = devices.resolve_device(device, t.playwright.devices if t.playwright else {})
            except ValueError as e:
                return {"success": False, "error": str(e)}
            if kind == "viewport":
                viewport = resolved
            else:
                descriptor = resolved
        if args.get("width") or args.get("height"):
            viewport = {"width": int(args.get("width") or config.VIEWPORT_WIDTH),
                        "height": int(args.get("height") or config.VIEWPORT_HEIGHT)}

        own_context = None
        try:
            if descriptor is not None:
                if viewport:
                    descriptor = {**descriptor, "viewport": viewport}
                own_context = await t.new_device_context(project, descriptor, headed=headed)
                context = own_context
            elif project:
                context = await t.get_context(project, headed=headed)
            else:
                own_context = await t.new_ephemeral_context(headed=headed)
                context = own_context
        except RuntimeError as e:
            return {"success": False, "error": str(e)}
        try:
            session = await session_manager.create_session(
                context, args["url"], project_name, screenshot_dir=proj_screenshot_dir,
                viewport=viewport if descriptor is None else None)
        except Exception:
            if own_context is not None:
                await own_context.close()
            raise
        session.own_context = own_context
        screenshot_path = await interactions.take_screenshot(
            session.page, project_name, "session_open", screenshot_dir=proj_screenshot_dir
        )
        result = {
            "success": True,
            "session_id": session.session_id,
            "url": session.url,
            "title": await session.page.title(),
            "screenshot_path": screenshot_path,
        }
        if headed:
            result["headed"] = True
        if args.get("consent"):
            import consent
            try:
                result["consent"] = await consent.apply(session.page, args["consent"])
            except Exception as e:  # the session is already open — report, don't lose it
                result["consent"] = {"success": False, "action": args["consent"],
                                     "error": f"consent handling failed: {str(e)[:200]}"}
        if device:
            result["device"] = device
        if descriptor is not None:
            result["user_agent"] = descriptor.get("user_agent")
            result["viewport"] = descriptor.get("viewport")
            result["device_context"] = ("private context emulating the device, seeded with the "
                                        "project's login state; cookies set here stay in this session")
        elif viewport:
            result["viewport"] = viewport
        result["served_by_service_worker"] = session.served_by_service_worker
        if session.wait_downgraded:
            result["wait_downgraded"] = ("networkidle never settled (busy widget like Turnstile/"
                                         "websockets) — navigation completed with 'load' instead")
        # Landing on the project's login page usually means auth expired (issue #11)
        from tester import redirected_to_login
        if (proj_obj and proj_obj.auth and proj_obj.auth.method == "form"
                and proj_obj.auth.form_login
                and redirected_to_login(session.url, proj_obj.auth.form_login.login_url)):
            result["warning"] = ("Session landed on the project's login page — authentication "
                                 "has likely expired. Run login_project and reopen.")
        return result


@tool("close_session")
async def handle_close_session(args: dict) -> dict:
        closed = await session_manager.close_session(args["session_id"])
        if closed:
            return {"success": True, "message": f"Session '{args['session_id']}' closed"}
        return {"success": False, "error": f"Session '{args['session_id']}' not found"}


@tool("list_sessions")
async def handle_list_sessions(args: dict) -> dict:
        sessions = session_manager.list_sessions()
        result = {"sessions": sessions, "count": len(sessions)}
        if session_manager.recent_removals:
            result["recently_removed"] = session_manager.recent_removals
        return result


@tool("set_viewport")
async def handle_set_viewport(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        device_presets = devices.VIEWPORT_PRESETS
        device = args.get("device")
        if device:
            if device not in device_presets:
                return {
                    "success": False,
                    "error": f"Unknown device preset '{device}'. "
                             f"Valid: {', '.join(device_presets)}",
                }
            width = device_presets[device]["width"]
            height = device_presets[device]["height"]
        else:
            width = args.get("width", config.VIEWPORT_WIDTH)
            height = args.get("height", config.VIEWPORT_HEIGHT)

        await real_page(session.page).set_viewport_size({"width": width, "height": height})
        reloaded = bool(args.get("reload"))
        if reloaded:
            # JS-driven breakpoints (Elementor, slider libs) only re-evaluate on load.
            await real_page(session.page).reload(wait_until=config.WAIT_UNTIL)
        result = {
            "success": True,
            "viewport": {"width": width, "height": height},
            "device": device,
            "reloaded": reloaded,
            "url": session.url,
        }
        return await interactions.attach_observation(
            session, result, args, f"viewport_{width}x{height}")


@tool("screenshot_session")
async def handle_screenshot_session(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        full_page = args.get("full_page", True)
        selector = args.get("selector")
        mode = args.get("mode")
        if mode and mode not in ("full", "viewport", "tiles", "element"):
            return {"success": False, "error":
                    f"Unknown mode '{mode}' — use full (default), viewport, tiles (full-page split "
                    "into tile_height px images), or element (with selector)."}
        if mode == "viewport":
            full_page = False
        elif mode == "element" and not selector:
            return {"success": False, "error": "mode='element' needs 'selector'."}
        tiles = None
        _meta = {}
        if mode == "tiles":
            from utils import split_tiles
            tile_height = int(args.get("tile_height") or 1600)
            screenshot_path = await interactions.take_screenshot(
                session.page, session.project_name, "session_tiles", screenshot_dir=session.screenshot_dir,
                prepare=not args.get("raw", False), meta=_meta)
            tiles = split_tiles(screenshot_path, tile_height)
        elif selector:
            # Element clip: screenshot just the matching element (evidence citing)
            base_dir = session.screenshot_dir if session.screenshot_dir else config.SCREENSHOT_DIR
            project_dir = os.path.join(base_dir, session.project_name)
            os.makedirs(project_dir, exist_ok=True)
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            screenshot_path = os.path.join(project_dir, f"element_{timestamp}.png")
            locator = session.page.locator(selector).first
            await locator.wait_for(state="visible", timeout=10000)
            await locator.screenshot(path=screenshot_path)
        elif full_page:
            screenshot_path = await interactions.take_screenshot(
                session.page, session.project_name, "session_state", screenshot_dir=session.screenshot_dir,
                prepare=not args.get("raw", False), meta=_meta)
        else:
            base_dir = session.screenshot_dir if session.screenshot_dir else config.SCREENSHOT_DIR
            project_dir = os.path.join(base_dir, session.project_name)
            os.makedirs(project_dir, exist_ok=True)
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            screenshot_path = os.path.join(project_dir, f"interactive_{timestamp}_viewport.png")
            await real_page(session.page).screenshot(path=screenshot_path, full_page=False)
        view = _meta.get("view") or await interactions.read_view(session.page)
        result = {
            "success": True,
            "mode": mode or ("element" if selector else "full" if full_page else "viewport"),
            "screenshot_path": screenshot_path,
            "url": session.url,
            "title": await session.page.title(),
            **({"capture_prep": _meta["capture_prep"]} if _meta.get("capture_prep") else {}),
            "view": view,
        }
        page_height = (view or {}).get("page_height") or 0
        if tiles is not None:
            result.update({"tiles": tiles, "tile_count": len(tiles), "tile_height": tile_height,
                           "page_height": page_height})
        elif result["mode"] == "full" and page_height > 6000:
            result["note"] = (f"page is {page_height} px tall — a full-page image this size is unreadable "
                              "when downscaled; pass mode='tiles' (tile_height=1600) for legible images")
        return result


@tool("select_page")
async def handle_select_page(args: dict) -> dict:
        """Adopt a popup / new tab opened by this session (window.open,
        target=_blank, OAuth windows) as a NEW session you can drive with every
        normal tool. Console/network capture has been running since the popup
        opened, so nothing from its initial load is lost. With several popups
        open, call without 'index' to list them, then pass the index."""
        import time as _time
        import uuid as _uuid
        from sessions import PageSession

        session = session_manager.get_session(args["session_id"])
        if session.parent_session_id:
            return {"success": False, "error":
                    "select_page works on the root session — pass the parent session id "
                    f"('{session.parent_session_id}'), not a derived one."}

        live = [e for e in session.popups if not e["page"].is_closed()]
        if not live:
            # The popup event can land a beat after the triggering click
            # returns — poll briefly before declaring there is none.
            for _ in range(10):
                await asyncio.sleep(0.2)
                live = [e for e in session.popups if not e["page"].is_closed()]
                if live:
                    break
        if not live:
            return {"success": False, "error":
                    "No open popups/new tabs for this session. Popups are captured "
                    "automatically when the page opens one (window.open, target=_blank); "
                    "trigger the opener first, then call select_page."}

        index = args.get("index")
        if index is None and len(live) > 1:
            return {"success": True, "action_needed": "pick_index",
                    "pages": [{"index": i, "url": e["page"].url,
                               "already_adopted": bool(e.get("adopted_session_id"))}
                              for i, e in enumerate(live)],
                    "note": "Several popups are open — call again with 'index'."}
        entry = live[int(index or 0)] if int(index or 0) < len(live) else None
        if entry is None:
            return {"success": False, "error":
                    f"index {index} out of range — {len(live)} open popup(s) (0-based)."}

        if entry.get("adopted_session_id") and entry["adopted_session_id"] in session_manager.sessions:
            popup_session_id = entry["adopted_session_id"]  # idempotent re-select
        else:
            page = entry["page"]
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:
                pass
            popup_session_id = _uuid.uuid4().hex[:12]
            now = _time.time()
            cl, ce, nl, rb, rc = entry["captures"]
            popup_session = PageSession(
                session_id=popup_session_id,
                project_name=session.project_name,
                page=page,
                url=page.url,
                created_at=now,
                last_accessed=now,
                console_log=cl, console_errors=ce,
                network_log=nl, response_bodies=rb,
                screenshot_dir=session.screenshot_dir,
                parent_session_id=session.session_id,
                request_counter=rc,
            )
            session_manager.register_session(popup_session)
            entry["adopted_session_id"] = popup_session_id

        popup_page = entry["page"]
        return {
            "success": True,
            "session_id": popup_session_id,
            "url": popup_page.url,
            "title": await popup_page.title(),
            "parent_session_id": session.session_id,
            "note": "Drive this like any session (click, assert, logs…); close_session "
                    "when done. The parent session id keeps working for the original tab.",
        }


async def _cdp(session):
    """One CDP session per page (shared with emulate_network)."""
    if session.cdp_session is None:
        cdp_page = real_page(session.page)
        session.cdp_session = await cdp_page.context.new_cdp_session(cdp_page)
    return session.cdp_session


@tool("navigate_session")
async def handle_navigate_session(args: dict) -> dict:
        from nav import from_service_worker, resilient_goto

        session = session_manager.get_session(args["session_id"])
        action = args["action"]
        page = real_page(session.page)
        wait_until = args.get("wait_until") or config.WAIT_UNTIL
        result = {"success": True, "action": action}

        if action == "back":
            await page.go_back(wait_until=wait_until)
        elif action == "forward":
            await page.go_forward(wait_until=wait_until)
        elif action == "reload":
            hard = bool(args.get("hard"))
            if hard:
                # Bypass the HTTP cache for this load: a redeploy must not be
                # masked by a cached document/asset.
                cdp = await _cdp(session)
                await cdp.send("Network.enable")  # setCacheDisabled is a no-op without it
                await cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
                try:
                    await cdp.send("Network.clearBrowserCache")
                except Exception:
                    pass
            try:
                response = await page.reload(wait_until=wait_until)
            finally:
                if hard:
                    try:
                        await cdp.send("Network.setCacheDisabled", {"cacheDisabled": False})
                    except Exception:
                        pass
            result["hard"] = hard
            result["served_by_service_worker"] = from_service_worker(response)
            session.served_by_service_worker = result["served_by_service_worker"]
            if response is not None:
                result["status_code"] = response.status
        elif action == "goto":
            url = args.get("url")
            if not url:
                return {"success": False, "error":
                        "navigate_session action='goto' requires 'url' (the address to load). "
                        "Optional: wait_for (CSS selector to wait for), wait_for_network "
                        "(URL substring, armed before navigation), wait_until (load|domcontentloaded|networkidle)."}
            armed = None
            if args.get("wait_for_network"):
                import asyncio as _asyncio
                from interactions import _network_predicate
                armed = _asyncio.ensure_future(page.wait_for_event(
                    "response", predicate=_network_predicate(args["wait_for_network"]),
                    timeout=int(args.get("timeout") or 30000)))
            try:
                response, downgraded = await resilient_goto(page, url, wait_until=wait_until)
                if downgraded:
                    result["wait_downgraded"] = "load"
                result["status_code"] = response.status if response is not None else None
                result["served_by_service_worker"] = from_service_worker(response)
                session.served_by_service_worker = result["served_by_service_worker"]
                if args.get("wait_for"):
                    await page.locator(args["wait_for"]).first.wait_for(
                        state="visible", timeout=int(args.get("timeout") or 10000))
                    result["waited_for"] = args["wait_for"]
                if armed is not None:
                    matched = await armed
                    armed = None
                    result["matched_url"] = matched.url
                    result["matched_status"] = matched.status
            finally:
                if armed is not None and not armed.done():
                    armed.cancel()
        elif action == "clear_site_data":
            # Fresh-deploy mode: drop service workers + CacheStorage (and,
            # opt-in, local/session storage + IndexedDB) for this origin.
            # Cookies are NEVER touched — that would log a project session out.
            from urllib.parse import urlparse
            parts = urlparse(page.url)
            if parts.scheme not in ("http", "https") or not parts.netloc:
                return {"success": False, "error":
                        f"clear_site_data needs an http(s) page — this session is on '{page.url}'. "
                        "Navigate to the site first (navigate_session action='goto'), then clear."}
            origin = f"{parts.scheme}://{parts.netloc}"
            try:
                sw_count = await page.evaluate(
                    "async () => (await navigator.serviceWorker.getRegistrations()).length")
            except Exception:
                sw_count = 0
            types = ["service_workers", "cache_storage"]
            if args.get("include_storage"):
                types += ["local_storage", "indexeddb"]
            cdp = await _cdp(session)
            await cdp.send("Storage.clearDataForOrigin",
                           {"origin": origin, "storageTypes": ",".join(types)})
            try:
                await cdp.send("Network.clearBrowserCache")
            except Exception:
                pass
            response = await page.reload(wait_until=wait_until)
            result.update({"origin": origin, "cleared": types + ["http_cache"],
                           "service_workers_unregistered": sw_count,
                           "served_by_service_worker": from_service_worker(response)})
            session.served_by_service_worker = result["served_by_service_worker"]
        else:
            return {"success": False, "error":
                    f"Unknown action '{action}'. Valid: back, forward, reload, goto, clear_site_data"}
        session.url = page.url
        result["url"] = session.url
        # Title from the owning Page: an iframe session's Frame is detached by
        # a top-level navigation and would raise here.
        result["title"] = await page.title()
        if session.parent_session_id and not hasattr(session.page, "main_frame"):
            result["frame_note"] = ("this is an iframe session and the top-level page navigated — its "
                                    "frame is gone; continue with the parent session id (or select_iframe again)")
            return result
        return await interactions.attach_observation(session, result, args, f"after_{action}")
