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
        proj_obj = project_manager.get(project) if project else None
        proj_screenshot_dir = proj_obj.screenshot_dir if proj_obj else None

        # With a project: share its (authenticated) context. Without: a private
        # context per session, so unrelated targets never see each other's
        # cookies (issue #8). Closed together with the session.
        own_context = None
        if project:
            context = await t.get_context(project)
        else:
            own_context = await t.new_ephemeral_context()
            context = own_context
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
        return {
            "success": True,
            "session_id": session.session_id,
            "url": session.url,
            "title": await session.page.title(),
            "screenshot_path": screenshot_path,
        }


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
        screenshot_path = await interactions.take_screenshot(
            session.page, session.project_name, f"viewport_{width}x{height}", screenshot_dir=session.screenshot_dir)
        return {
            "success": True,
            "viewport": {"width": width, "height": height},
            "device": device,
            "screenshot_path": screenshot_path,
            "url": session.url,
        }


@tool("screenshot_session")
async def handle_screenshot_session(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        full_page = args.get("full_page", True)
        if full_page:
            screenshot_path = await interactions.take_screenshot(
                session.page, session.project_name, "session_state", screenshot_dir=session.screenshot_dir)
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
        screenshot_path = await interactions.take_screenshot(
            session.page, session.project_name, f"after_{action}", screenshot_dir=session.screenshot_dir)
        return {
            "success": True,
            "action": action,
            "url": session.url,
            "title": await session.page.title(),
            "screenshot_path": screenshot_path,
        }
