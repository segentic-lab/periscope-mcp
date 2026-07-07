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


@tool("navigate_session")
async def handle_navigate_session(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        action = args["action"]
        page = real_page(session.page)
        if action == "back":
            await page.go_back(wait_until=config.WAIT_UNTIL)
        elif action == "forward":
            await page.go_forward(wait_until=config.WAIT_UNTIL)
        elif action == "reload":
            await page.reload(wait_until=config.WAIT_UNTIL)
        else:
            return {"success": False, "error": f"Unknown action '{action}'. Valid: back, forward, reload"}
        session.url = page.url
        result = {
            "success": True,
            "action": action,
            "url": session.url,
            "title": await session.page.title(),
        }
        return await interactions.attach_observation(session, result, args, f"after_{action}")
