"""Session lifecycle tools (open/close/list, viewport, history, screenshots)."""
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
        own_context = None
        try:
            if project:
                context = await t.get_context(project, headed=headed)
            else:
                own_context = await t.new_ephemeral_context(headed=headed)
                context = own_context
        except RuntimeError as e:
            return {"success": False, "error": str(e)}
        try:
            session = await session_manager.create_session(
                context, args["url"], project_name, screenshot_dir=proj_screenshot_dir)
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
        device_presets = {
            "mobile_sm": {"width": 320, "height": 568},    # iPhone SE
            "mobile": {"width": 375, "height": 812},        # iPhone 12
            "mobile_lg": {"width": 428, "height": 926},     # iPhone 14 Pro Max
            "tablet": {"width": 768, "height": 1024},       # iPad
            "tablet_lg": {"width": 1024, "height": 1366},   # iPad Pro
            "laptop": {"width": 1366, "height": 768},       # Common laptop
            "desktop": {"width": 1920, "height": 1080},     # Full HD
            "desktop_lg": {"width": 2560, "height": 1440},  # QHD
        }
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
        result = {
            "success": True,
            "viewport": {"width": width, "height": height},
            "device": device,
            "url": session.url,
        }
        return await interactions.attach_observation(
            session, result, args, f"viewport_{width}x{height}")


@tool("screenshot_session")
async def handle_screenshot_session(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        full_page = args.get("full_page", True)
        selector = args.get("selector")
        _meta = {}
        if selector:
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
        return {
            "success": True,
            "screenshot_path": screenshot_path,
            "url": session.url,
            "title": await session.page.title(),
            **({"capture_prep": _meta["capture_prep"]} if _meta.get("capture_prep") else {}),
            "view": _meta.get("view") or await interactions.read_view(session.page),
        }


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
            cl, ce, nl, rb = entry["captures"]
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
            except Exception:
                if armed is not None:
                    armed.cancel()
                raise
            if downgraded:
                result["wait_downgraded"] = "load"
            result["status_code"] = response.status if response is not None else None
            result["served_by_service_worker"] = from_service_worker(response)
            session.served_by_service_worker = result["served_by_service_worker"]
            if args.get("wait_for"):
                await session.page.locator(args["wait_for"]).first.wait_for(
                    state="visible", timeout=int(args.get("timeout") or 10000))
                result["waited_for"] = args["wait_for"]
            if armed is not None:
                matched = await armed
                result["matched_url"] = matched.url
                result["matched_status"] = matched.status
        elif action == "clear_site_data":
            # Fresh-deploy mode: drop service workers + CacheStorage (and,
            # opt-in, local/session storage + IndexedDB) for this origin.
            # Cookies are NEVER touched — that would log a project session out.
            from urllib.parse import urlparse
            parts = urlparse(page.url)
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
        else:
            return {"success": False, "error":
                    f"Unknown action '{action}'. Valid: back, forward, reload, goto, clear_site_data"}
        session.url = page.url
        result["url"] = session.url
        result["title"] = await session.page.title()
        return await interactions.attach_observation(session, result, args, f"after_{action}")
