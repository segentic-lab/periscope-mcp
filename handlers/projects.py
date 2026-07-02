"""Project management tools (create/list/get/delete)."""
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


@tool("create_project")
async def handle_create_project(args: dict) -> dict:
        try:
            screenshot_dir = args.get("screenshot_dir")
            project = project_manager.create(
                name=args["name"],
                base_url=args["base_url"],
                max_pages=args.get("max_pages", 20),
                max_depth=args.get("max_depth", 3),
                screenshot_dir=screenshot_dir
            )
        except ValueError as e:
            return {"success": False, "error": str(e)}
        if screenshot_dir:
            try:
                os.makedirs(os.path.join(screenshot_dir, args["name"]), exist_ok=True)
            except OSError as e:
                # Don't keep a project whose screenshot dir can't be created
                project_manager.delete(args["name"])
                return {"success": False, "error": f"Cannot create screenshot_dir: {e}"}
        return {
            "success": True,
            "message": f"Project '{project.name}' created",
            "project": project.to_dict()
        }


@tool("list_projects")
async def handle_list_projects(args: dict) -> dict:
        projects = project_manager.list_all()
        return {"projects": projects, "count": len(projects)}


@tool("get_project")
async def handle_get_project(args: dict) -> dict:
        project = project_manager.get(args["name"])
        if not project:
            return {"success": False, "error": f"Project '{args['name']}' not found"}
        data = project.to_dict()
        # Redact stored credentials — config visibility doesn't need secret values
        auth = data.get("auth")
        if auth:
            for key in ("form_login", "basic_auth"):
                if auth.get(key) and auth[key].get("password"):
                    auth[key]["password"] = "***"
            if auth.get("cookie_auth", {}) and auth["cookie_auth"].get("cookies"):
                auth["cookie_auth"] = {"cookies": [
                    {**c, "value": "***"} if isinstance(c, dict) else c
                    for c in auth["cookie_auth"]["cookies"]
                ]}
        return {"success": True, "project": data}


@tool("delete_project")
async def handle_delete_project(args: dict) -> dict:
        name = args["name"]
        if not project_manager.delete(name):
            return {"success": False, "error": f"Project '{name}' not found"}
        # Free live browser state too: a recreated project with the same name
        # must not inherit the old context's cookies/auth routes or sessions.
        for s in list(session_manager.sessions.values()):
            if s.project_name == name:
                await session_manager.close_session(s.session_id)
        import runtime
        if runtime.tester is not None:
            try:
                await runtime.tester.close_context(name)
            except Exception:
                pass
        return {"success": True, "message": f"Project '{name}' deleted"}
