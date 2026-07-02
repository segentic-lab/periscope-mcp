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
            if screenshot_dir:
                os.makedirs(os.path.join(screenshot_dir, args["name"]), exist_ok=True)
            project = project_manager.create(
                name=args["name"],
                base_url=args["base_url"],
                max_pages=args.get("max_pages", 20),
                max_depth=args.get("max_depth", 3),
                screenshot_dir=screenshot_dir
            )
            return {
                "success": True,
                "message": f"Project '{project.name}' created",
                "project": project.to_dict()
            }
        except ValueError as e:
            return {"success": False, "error": str(e)}


@tool("list_projects")
async def handle_list_projects(args: dict) -> dict:
        projects = project_manager.list_all()
        return {"projects": projects, "count": len(projects)}


@tool("get_project")
async def handle_get_project(args: dict) -> dict:
        project = project_manager.get(args["name"])
        if project:
            return {"success": True, "project": project.to_dict()}
        return {"success": False, "error": f"Project '{args['name']}' not found"}


@tool("delete_project")
async def handle_delete_project(args: dict) -> dict:
        if project_manager.delete(args["name"]):
            return {"success": True, "message": f"Project '{args['name']}' deleted"}
        return {"success": False, "error": f"Project '{args['name']}' not found"}
