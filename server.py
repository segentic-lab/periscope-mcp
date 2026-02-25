import asyncio
import json
import os
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from tester import WebsiteTester
from crawler import Crawler
from projects import ProjectManager
from auth import AuthHandler
import config

# Initialize
server = Server("website-tester")
project_manager = ProjectManager()
tester: WebsiteTester = None
auth_handler = AuthHandler()


async def get_tester() -> WebsiteTester:
    """Get or create the tester instance."""
    global tester
    if tester is None or tester.browser is None:
        tester = WebsiteTester()
        await tester.start()
    return tester


# ============================================================================
# TOOL DEFINITIONS
# ============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # Project Management
        Tool(
            name="create_project",
            description="Create a new website testing project. Each project represents a website to test.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Unique project name (e.g., 'mysite')"},
                    "base_url": {"type": "string", "description": "Base URL of the website (e.g., 'https://example.com')"},
                    "max_pages": {"type": "integer", "description": "Max pages to crawl (default: 20)", "default": 20},
                    "max_depth": {"type": "integer", "description": "Max crawl depth (default: 3)", "default": 3}
                },
                "required": ["name", "base_url"]
            }
        ),
        Tool(
            name="list_projects",
            description="List all testing projects.",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="get_project",
            description="Get details of a specific project.",
            inputSchema={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Project name"}},
                "required": ["name"]
            }
        ),
        Tool(
            name="delete_project",
            description="Delete a project and its associated data.",
            inputSchema={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Project name"}},
                "required": ["name"]
            }
        ),

        # Authentication
        Tool(
            name="set_form_login",
            description="Configure form-based login for a project. Use this for sites with username/password forms.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project name"},
                    "login_url": {"type": "string", "description": "URL of the login page"},
                    "username": {"type": "string", "description": "Login username or email"},
                    "password": {"type": "string", "description": "Login password"},
                    "username_selector": {"type": "string", "description": "CSS selector for username field (optional)"},
                    "password_selector": {"type": "string", "description": "CSS selector for password field (optional)"},
                    "submit_selector": {"type": "string", "description": "CSS selector for submit button (optional)"}
                },
                "required": ["project", "login_url", "username", "password"]
            }
        ),
        Tool(
            name="set_basic_auth",
            description="Configure HTTP Basic Auth for a project.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project name"},
                    "username": {"type": "string", "description": "Basic auth username"},
                    "password": {"type": "string", "description": "Basic auth password"}
                },
                "required": ["project", "username", "password"]
            }
        ),
        Tool(
            name="set_cookies",
            description="Set session cookies for a project. Use this to bypass login with existing session.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project name"},
                    "cookies": {
                        "type": "array",
                        "description": "List of cookies with name, value, domain",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "value": {"type": "string"},
                                "domain": {"type": "string"}
                            },
                            "required": ["name", "value", "domain"]
                        }
                    }
                },
                "required": ["project", "cookies"]
            }
        ),
        Tool(
            name="login_project",
            description="Execute login for a project using configured credentials. Must call set_form_login, set_basic_auth, or set_cookies first.",
            inputSchema={
                "type": "object",
                "properties": {"project": {"type": "string", "description": "Project name"}},
                "required": ["project"]
            }
        ),

        # Testing
        Tool(
            name="test_url",
            description="Test a single URL. Takes screenshot and runs checks for visual issues, accessibility, functionality, SEO, and performance.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to test"},
                    "project": {"type": "string", "description": "Project name (optional, uses 'default' if not specified)"},
                    "checks": {
                        "type": "array",
                        "description": "Types of checks to run (visual, accessibility, functionality, seo, performance). Default: all",
                        "items": {"type": "string", "enum": ["visual", "accessibility", "functionality", "seo", "performance"]}
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="crawl_project",
            description="Discover all pages in a project by crawling from the base URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project name"},
                    "max_pages": {"type": "integer", "description": "Override max pages for this crawl"},
                    "max_depth": {"type": "integer", "description": "Override max depth for this crawl"}
                },
                "required": ["project"]
            }
        ),
        Tool(
            name="test_project",
            description="Full project test: crawls all pages and runs all checks. Returns comprehensive report.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project name"},
                    "max_pages": {"type": "integer", "description": "Override max pages"},
                    "checks": {
                        "type": "array",
                        "description": "Types of checks to run",
                        "items": {"type": "string", "enum": ["visual", "accessibility", "functionality", "seo", "performance"]}
                    }
                },
                "required": ["project"]
            }
        ),

        # Results
        Tool(
            name="get_screenshot",
            description="Get the file path to a screenshot for a tested URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project name"},
                    "url": {"type": "string", "description": "URL that was tested"}
                },
                "required": ["project", "url"]
            }
        ),
        Tool(
            name="list_reports",
            description="List all test reports for a project.",
            inputSchema={
                "type": "object",
                "properties": {"project": {"type": "string", "description": "Project name (optional, lists all if not specified)"}}
            }
        ),
        Tool(
            name="get_report",
            description="Get the contents of a specific test report.",
            inputSchema={
                "type": "object",
                "properties": {
                    "report_path": {"type": "string", "description": "Path to the report file"}
                },
                "required": ["report_path"]
            }
        )
    ]


# ============================================================================
# TOOL HANDLERS
# ============================================================================

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = await _handle_tool(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def _handle_tool(name: str, args: dict) -> dict:
    """Route tool calls to handlers."""

    # Project Management
    if name == "create_project":
        try:
            project = project_manager.create(
                name=args["name"],
                base_url=args["base_url"],
                max_pages=args.get("max_pages", 20),
                max_depth=args.get("max_depth", 3)
            )
            return {
                "success": True,
                "message": f"Project '{project.name}' created",
                "project": project.to_dict()
            }
        except ValueError as e:
            return {"success": False, "error": str(e)}

    elif name == "list_projects":
        projects = project_manager.list_all()
        return {"projects": projects, "count": len(projects)}

    elif name == "get_project":
        project = project_manager.get(args["name"])
        if project:
            return {"success": True, "project": project.to_dict()}
        return {"success": False, "error": f"Project '{args['name']}' not found"}

    elif name == "delete_project":
        if project_manager.delete(args["name"]):
            return {"success": True, "message": f"Project '{args['name']}' deleted"}
        return {"success": False, "error": f"Project '{args['name']}' not found"}

    # Authentication
    elif name == "set_form_login":
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
            return {"success": True, "message": "Form login configured"}
        return {"success": False, "error": f"Project '{args['project']}' not found"}

    elif name == "set_basic_auth":
        success = project_manager.set_basic_auth(
            name=args["project"],
            username=args["username"],
            password=args["password"]
        )
        if success:
            return {"success": True, "message": "HTTP Basic Auth configured"}
        return {"success": False, "error": f"Project '{args['project']}' not found"}

    elif name == "set_cookies":
        success = project_manager.set_cookies(
            name=args["project"],
            cookies=args["cookies"]
        )
        if success:
            return {"success": True, "message": f"Set {len(args['cookies'])} cookies"}
        return {"success": False, "error": f"Project '{args['project']}' not found"}

    elif name == "login_project":
        project = project_manager.get(args["project"])
        if not project:
            return {"success": False, "error": f"Project '{args['project']}' not found"}

        t = await get_tester()
        context = await t.get_context(project.name)
        result = await auth_handler.login(context, project)

        if result["success"]:
            project_manager.mark_logged_in(project.name, True)

        return result

    # Testing
    elif name == "test_url":
        t = await get_tester()
        project_name = args.get("project", "default")
        checks = args.get("checks")

        result = await t.test_url(
            url=args["url"],
            project_name=project_name,
            checks=checks
        )
        return result

    elif name == "crawl_project":
        project = project_manager.get(args["project"])
        if not project:
            return {"success": False, "error": f"Project '{args['project']}' not found"}

        t = await get_tester()
        context = await t.get_context(project.name)
        crawler = Crawler()

        urls = await crawler.crawl(
            context=context,
            start_url=project.base_url,
            max_pages=args.get("max_pages", project.max_pages),
            max_depth=args.get("max_depth", project.max_depth)
        )

        return {
            "project": project.name,
            "base_url": project.base_url,
            "pages_found": len(urls),
            "urls": urls
        }

    elif name == "test_project":
        project = project_manager.get(args["project"])
        if not project:
            return {"success": False, "error": f"Project '{args['project']}' not found"}

        t = await get_tester()
        context = await t.get_context(project.name)

        # Crawl first
        crawler = Crawler()
        urls = await crawler.crawl(
            context=context,
            start_url=project.base_url,
            max_pages=args.get("max_pages", project.max_pages),
            max_depth=project.max_depth
        )

        # Test all pages
        checks = args.get("checks", project.test_types)
        results = await t.test_multiple(urls, project.name, checks)

        # Save report
        report_path = await t.save_report(results, project.name)
        results["report_path"] = report_path

        # Update project
        project_manager.update_last_tested(project.name)

        return results

    # Results
    elif name == "get_screenshot":
        t = await get_tester()
        screenshot_path = t._get_screenshot_path(args["project"], args["url"])

        if os.path.exists(screenshot_path):
            return {
                "success": True,
                "screenshot_path": screenshot_path,
                "url": args["url"]
            }
        return {
            "success": False,
            "error": "Screenshot not found. Run test_url or test_project first."
        }

    elif name == "list_reports":
        project_filter = args.get("project")
        reports = []

        for filename in os.listdir(config.REPORTS_DIR):
            if filename.endswith(".json"):
                if project_filter and not filename.startswith(project_filter + "_"):
                    continue
                filepath = os.path.join(config.REPORTS_DIR, filename)
                stat = os.stat(filepath)
                reports.append({
                    "filename": filename,
                    "path": filepath,
                    "size_bytes": stat.st_size,
                    "modified": stat.st_mtime
                })

        reports.sort(key=lambda x: x["modified"], reverse=True)
        return {"reports": reports, "count": len(reports)}

    elif name == "get_report":
        report_path = args["report_path"]
        if os.path.exists(report_path):
            with open(report_path, "r") as f:
                report = json.load(f)
            return {"success": True, "report": report}
        return {"success": False, "error": "Report not found"}

    else:
        return {"error": f"Unknown tool: {name}"}


# ============================================================================
# MAIN
# ============================================================================

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
