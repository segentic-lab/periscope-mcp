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
from sessions import SessionManager
import interactions
import config

# Initialize
server = Server("website-tester")
project_manager = ProjectManager()
tester: WebsiteTester = None
auth_handler = AuthHandler()
session_manager = SessionManager()


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
        ),

        # ==================== Interactive Testing ====================

        # Session Management
        Tool(
            name="open_session",
            description="Open a persistent browser session for interactive testing. The session stays alive across tool calls so you can observe, click, fill forms, and decide next actions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to open"},
                    "project": {"type": "string", "description": "Project name (optional, uses 'default')"}
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="close_session",
            description="Close a persistent browser session and free its resources.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID to close"}
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="list_sessions",
            description="List all active browser sessions with their URLs and idle times.",
            inputSchema={"type": "object", "properties": {}}
        ),

        # Interactive Tools
        Tool(
            name="click_element",
            description="Click an element in a session page. Returns a screenshot and the new URL/title after click. Use force=true to bypass actionability checks (useful when overlays intercept pointer events).",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "selector": {"type": "string", "description": "CSS selector of element to click"},
                    "force": {"type": "boolean", "description": "Bypass actionability checks (default: false). Use when overlays intercept clicks."}
                },
                "required": ["session_id", "selector"]
            }
        ),
        Tool(
            name="fill_form",
            description="Fill form fields in a session page and optionally submit.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "fields": {
                        "type": "array",
                        "description": "Fields to fill: [{selector, value}]",
                        "items": {
                            "type": "object",
                            "properties": {
                                "selector": {"type": "string", "description": "CSS selector for the field"},
                                "value": {"type": "string", "description": "Value to fill"}
                            },
                            "required": ["selector", "value"]
                        }
                    },
                    "submit_selector": {"type": "string", "description": "CSS selector for submit button (optional)"}
                },
                "required": ["session_id", "fields"]
            }
        ),
        Tool(
            name="interact_and_test",
            description="Execute a multi-step interaction workflow. Supports 19 actions: click, force_click, fill, type, select, wait, wait_for, wait_for_text, screenshot, navigate, hover, press_key, check, uncheck, scroll_to, scroll_within, evaluate_js, drag, right_click. Can work on an existing session or create an ephemeral page.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to open (creates ephemeral page if no session_id)"},
                    "session_id": {"type": "string", "description": "Existing session ID (alternative to url)"},
                    "steps": {
                        "type": "array",
                        "description": "Steps to execute. Each step has 'action' and action-specific fields.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": ["click", "force_click", "fill", "type", "select", "wait", "wait_for", "wait_for_text", "screenshot", "navigate", "hover", "press_key", "check", "uncheck", "scroll_to", "scroll_within", "evaluate_js", "drag", "right_click"],
                                    "description": "Action to perform"
                                },
                                "selector": {"type": "string", "description": "CSS selector (for click, fill, type, select, hover, check, uncheck, wait_for, scroll_to, scroll_within, force_click, drag, right_click, wait_for_text container)"},
                                "value": {"type": "string", "description": "Value (for fill, select)"},
                                "text": {"type": "string", "description": "Text to type (for type action), or text to wait for (for wait_for_text)"},
                                "target": {"type": "string", "description": "CSS selector of drop target (for drag action)"},
                                "key": {"type": "string", "description": "Key to press (for press_key, e.g. 'Enter', 'Tab')"},
                                "url": {"type": "string", "description": "URL (for navigate)"},
                                "timeout": {"type": "integer", "description": "Timeout in ms (for wait, wait_for)"},
                                "state": {"type": "string", "description": "State to wait for (for wait_for: visible, hidden, attached, detached)"},
                                "label": {"type": "string", "description": "Label for screenshot filename"},
                                "force": {"type": "boolean", "description": "Bypass actionability checks on click (default: false)"},
                                "script": {"type": "string", "description": "JavaScript to evaluate (for evaluate_js)"},
                                "direction": {"type": "string", "enum": ["up", "down", "left", "right"], "description": "Scroll direction (for scroll_within)"},
                                "amount": {"type": "integer", "description": "Scroll amount in pixels (for scroll_within, default: 300)"}
                            },
                            "required": ["action"]
                        }
                    },
                    "project": {"type": "string", "description": "Project name (optional)"},
                    "run_checks": {
                        "type": "array",
                        "description": "Checks to run after steps complete (visual, accessibility, functionality, seo, performance)",
                        "items": {"type": "string", "enum": ["visual", "accessibility", "functionality", "seo", "performance"]}
                    },
                    "screenshot_after": {"type": "boolean", "description": "Take a screenshot after all steps complete (default: true)"},
                    "continue_on_error": {"type": "boolean", "description": "Continue executing steps even if one fails (default: false)"}
                },
                "required": ["steps"]
            }
        ),
        Tool(
            name="get_page_elements",
            description="List elements matching a CSS selector with their attributes (tag, text, id, class, href, value, visible, enabled, aria_label, role). Works on a session or a URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector to match elements"},
                    "session_id": {"type": "string", "description": "Session ID (use this or url)"},
                    "url": {"type": "string", "description": "URL to open (use this or session_id)"},
                    "project": {"type": "string", "description": "Project name (optional)"},
                    "max_results": {"type": "integer", "description": "Max elements to return (default: 50)"}
                },
                "required": ["selector"]
            }
        ),

        # Phase 2: Medium Priority
        Tool(
            name="test_form_validation",
            description="Analyze forms on a page: find all forms, check required fields, collect validation messages from :invalid fields and custom error elements.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to test (use this or session_id)"},
                    "session_id": {"type": "string", "description": "Session ID (use this or url)"},
                    "project": {"type": "string", "description": "Project name (optional)"},
                    "form_selector": {"type": "string", "description": "CSS selector to target specific form(s) (default: 'form')"}
                }
            }
        ),
        Tool(
            name="compare_screenshots",
            description="Compare two screenshots pixel-by-pixel. Returns difference percentage and a diff image highlighting changes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "screenshot1": {"type": "string", "description": "Path to first screenshot"},
                    "screenshot2": {"type": "string", "description": "Path to second screenshot"},
                    "threshold": {"type": "number", "description": "Color difference threshold 0-255 (default: 10)"}
                },
                "required": ["screenshot1", "screenshot2"]
            }
        ),
        Tool(
            name="test_responsive",
            description="Test a URL at multiple viewport sizes (mobile, tablet, desktop). Takes screenshots at each size and optionally runs checks.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to test"},
                    "project": {"type": "string", "description": "Project name (optional)"},
                    "viewports": {
                        "type": "array",
                        "description": "Custom viewports [{name, width, height}]. Default: mobile (375x812), tablet (768x1024), desktop (1920x1080)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "width": {"type": "integer"},
                                "height": {"type": "integer"}
                            },
                            "required": ["name", "width", "height"]
                        }
                    },
                    "run_checks": {
                        "type": "array",
                        "description": "Checks to run at each viewport",
                        "items": {"type": "string", "enum": ["visual", "accessibility", "functionality", "seo", "performance"]}
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="check_links",
            description="Comprehensive link checker. Finds all links on a page and checks their status. Can check external links too.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to check (use this or session_id)"},
                    "session_id": {"type": "string", "description": "Session ID (use this or url)"},
                    "project": {"type": "string", "description": "Project name (optional)"},
                    "check_external": {"type": "boolean", "description": "Also check external links (default: false)"},
                    "max_links": {"type": "integer", "description": "Max links to check (default: 100)"}
                }
            }
        ),
        Tool(
            name="measure_interaction",
            description="Click an element and measure time until a condition is met (networkidle or a selector appears). Returns timing in ms.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "selector": {"type": "string", "description": "CSS selector of element to click"},
                    "wait_for": {"type": "string", "description": "CSS selector to wait for (default: waits for networkidle)"}
                },
                "required": ["session_id", "selector"]
            }
        ),

        # Phase 3: Nice-to-Have
        Tool(
            name="record_session",
            description="Record a workflow as video. Executes steps while recording with Playwright's built-in video capture.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to open"},
                    "steps": {
                        "type": "array",
                        "description": "Steps to execute (same format as interact_and_test)",
                        "items": {"type": "object"}
                    },
                    "project": {"type": "string", "description": "Project name (optional)"}
                },
                "required": ["url", "steps"]
            }
        ),
        Tool(
            name="test_keyboard_navigation",
            description="Tab through a page and track focus order. Checks for visible focus indicators and reports the tab sequence.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to test (use this or session_id)"},
                    "session_id": {"type": "string", "description": "Session ID (use this or url)"},
                    "project": {"type": "string", "description": "Project name (optional)"},
                    "max_tabs": {"type": "integer", "description": "Max Tab presses (default: 50)"}
                }
            }
        ),
        Tool(
            name="extract_text",
            description="Extract text content from elements matching a CSS selector.",
            inputSchema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector to match elements"},
                    "url": {"type": "string", "description": "URL to open (use this or session_id)"},
                    "session_id": {"type": "string", "description": "Session ID (use this or url)"},
                    "project": {"type": "string", "description": "Project name (optional)"}
                },
                "required": ["selector"]
            }
        ),
        Tool(
            name="check_console_during_interaction",
            description="Execute interaction steps and capture all console output (logs, warnings, errors) that occur during the workflow.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "steps": {
                        "type": "array",
                        "description": "Steps to execute (same format as interact_and_test)",
                        "items": {"type": "object"}
                    }
                },
                "required": ["session_id", "steps"]
            }
        ),
        Tool(
            name="get_console_errors",
            description="Get all console errors and logs captured on a session since it was opened (or since last call to this tool). Useful for passive monitoring without running steps.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "clear": {"type": "boolean", "description": "Clear the console buffers after reading (default: true)"}
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="copy_auth",
            description="Copy authentication config from one project to another. Useful when multiple projects share the same domain/credentials.",
            inputSchema={
                "type": "object",
                "properties": {
                    "from_project": {"type": "string", "description": "Source project name to copy auth from"},
                    "to_project": {"type": "string", "description": "Target project name to copy auth to"}
                },
                "required": ["from_project", "to_project"]
            }
        ),
        Tool(
            name="get_attribute",
            description="Get specific attribute values from elements matching a selector. Returns any HTML attribute (data-*, aria-*, style, etc.).",
            inputSchema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector to match elements"},
                    "attributes": {
                        "type": "array",
                        "description": "Attribute names to extract (e.g. ['data-id', 'aria-expanded', 'style'])",
                        "items": {"type": "string"}
                    },
                    "session_id": {"type": "string", "description": "Session ID (use this or url)"},
                    "url": {"type": "string", "description": "URL to open (use this or session_id)"},
                    "project": {"type": "string", "description": "Project name (optional)"},
                    "max_results": {"type": "integer", "description": "Max elements to return (default: 50)"}
                },
                "required": ["selector", "attributes"]
            }
        ),
        Tool(
            name="set_viewport",
            description="Change the viewport size of a session page to test at different screen sizes. Use device presets or custom width/height. Takes a screenshot after resizing.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "width": {"type": "integer", "description": "Viewport width in pixels (custom size)"},
                    "height": {"type": "integer", "description": "Viewport height in pixels (custom size)"},
                    "device": {
                        "type": "string",
                        "enum": [
                            "mobile_sm", "mobile", "mobile_lg",
                            "tablet", "tablet_lg",
                            "laptop", "desktop", "desktop_lg"
                        ],
                        "description": "Device preset: mobile_sm (320x568 iPhone SE), mobile (375x812 iPhone 12), mobile_lg (428x926 iPhone 14 Pro Max), tablet (768x1024 iPad), tablet_lg (1024x1366 iPad Pro), laptop (1366x768), desktop (1920x1080), desktop_lg (2560x1440)"
                    }
                },
                "required": ["session_id"]
            }
        ),
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

    # ==================== Interactive Testing ====================

    # Session Management
    elif name == "open_session":
        t = await get_tester()
        project_name = args.get("project", "default")
        context = await t.get_context(project_name)
        session = await session_manager.create_session(context, args["url"], project_name)
        screenshot_path = await interactions.take_screenshot(
            session.page, project_name, "session_open"
        )
        return {
            "success": True,
            "session_id": session.session_id,
            "url": session.url,
            "title": await session.page.title(),
            "screenshot_path": screenshot_path,
        }

    elif name == "close_session":
        closed = await session_manager.close_session(args["session_id"])
        if closed:
            return {"success": True, "message": f"Session '{args['session_id']}' closed"}
        return {"success": False, "error": f"Session '{args['session_id']}' not found"}

    elif name == "list_sessions":
        sessions = session_manager.list_sessions()
        return {"sessions": sessions, "count": len(sessions)}

    # Interactive Tools
    elif name == "click_element":
        session = session_manager.get_session(args["session_id"])
        result = await interactions.click_element(
            session.page, args["selector"], force=args.get("force", False)
        )
        session.url = result["url"]
        screenshot_path = await interactions.take_screenshot(
            session.page, session.project_name, "after_click"
        )
        result["screenshot_path"] = screenshot_path
        return result

    elif name == "fill_form":
        session = session_manager.get_session(args["session_id"])
        result = await interactions.fill_form(
            session.page,
            args["fields"],
            args.get("submit_selector"),
        )
        if result.get("submitted"):
            session.url = result.get("url", session.url)
        screenshot_path = await interactions.take_screenshot(
            session.page, session.project_name, "after_fill"
        )
        result["screenshot_path"] = screenshot_path
        return result

    elif name == "interact_and_test":
        t = await get_tester()
        project_name = args.get("project", "default")
        session_id = args.get("session_id")
        url = args.get("url")
        steps = args["steps"]
        run_checks = args.get("run_checks")
        screenshot_after = args.get("screenshot_after", True)
        continue_on_error = args.get("continue_on_error", False)

        ephemeral = False
        if session_id:
            session = session_manager.get_session(session_id)
            page = session.page
        elif url:
            context = await t.get_context(project_name)
            page = await context.new_page()
            page.set_default_timeout(config.TIMEOUT)
            await page.goto(url, wait_until="networkidle")
            ephemeral = True
        else:
            return {"success": False, "error": "Provide either 'url' or 'session_id'"}

        try:
            result = await interactions.execute_steps(
                page, steps, project_name, continue_on_error
            )

            if screenshot_after:
                path = await interactions.take_screenshot(page, project_name, "after_steps")
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

    elif name == "get_page_elements":
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
            context = await t.get_context(project_name)
            page = await context.new_page()
            page.set_default_timeout(config.TIMEOUT)
            await page.goto(url, wait_until="networkidle")
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

    # Phase 2: Medium Priority
    elif name == "test_form_validation":
        t = await get_tester()
        project_name = args.get("project", "default")
        session_id = args.get("session_id")
        url = args.get("url")
        form_selector = args.get("form_selector")

        ephemeral = False
        if session_id:
            session = session_manager.get_session(session_id)
            page = session.page
        elif url:
            context = await t.get_context(project_name)
            page = await context.new_page()
            page.set_default_timeout(config.TIMEOUT)
            await page.goto(url, wait_until="networkidle")
            ephemeral = True
        else:
            return {"success": False, "error": "Provide either 'url' or 'session_id'"}

        try:
            result = await interactions.test_form_validation(page, form_selector)
            result["url"] = page.url
            return result
        finally:
            if ephemeral:
                await page.close()

    elif name == "compare_screenshots":
        from utils import compare_screenshots as do_compare
        result = do_compare(
            args["screenshot1"],
            args["screenshot2"],
            threshold=args.get("threshold", 10),
        )
        return result

    elif name == "test_responsive":
        t = await get_tester()
        result = await t.test_responsive(
            url=args["url"],
            project_name=args.get("project", "default"),
            viewports=args.get("viewports"),
            checks=args.get("run_checks"),
        )
        return result

    elif name == "check_links":
        from checks.functionality import check_all_links

        t = await get_tester()
        project_name = args.get("project", "default")
        session_id = args.get("session_id")
        url = args.get("url")

        ephemeral = False
        if session_id:
            session = session_manager.get_session(session_id)
            page = session.page
        elif url:
            context = await t.get_context(project_name)
            page = await context.new_page()
            page.set_default_timeout(config.TIMEOUT)
            await page.goto(url, wait_until="networkidle")
            ephemeral = True
        else:
            return {"success": False, "error": "Provide either 'url' or 'session_id'"}

        try:
            result = await check_all_links(
                page,
                page.url,
                check_external=args.get("check_external", False),
                max_links=args.get("max_links", 100),
            )
            return result
        finally:
            if ephemeral:
                await page.close()

    elif name == "measure_interaction":
        session = session_manager.get_session(args["session_id"])
        result = await interactions.measure_interaction_timing(
            session.page,
            args["selector"],
            wait_for=args.get("wait_for"),
        )
        session.url = result["url"]
        screenshot_path = await interactions.take_screenshot(
            session.page, session.project_name, "after_measure"
        )
        result["screenshot_path"] = screenshot_path
        return result

    # Phase 3: Nice-to-Have
    elif name == "record_session":
        t = await get_tester()
        project_name = args.get("project", "default")
        video_dir = os.path.join(config.DATA_DIR, "videos", project_name)
        os.makedirs(video_dir, exist_ok=True)

        context = await t.browser.new_context(
            viewport={"width": config.VIEWPORT_WIDTH, "height": config.VIEWPORT_HEIGHT},
            record_video_dir=video_dir,
        )
        page = await context.new_page()
        page.set_default_timeout(config.TIMEOUT)

        try:
            await page.goto(args["url"], wait_until="networkidle")
            result = await interactions.execute_steps(
                page, args["steps"], project_name
            )
            # Close page to finalize video
            video_path = await page.video.path()
            await page.close()
            await context.close()
            result["video_path"] = video_path
            return result
        except Exception as e:
            await page.close()
            await context.close()
            return {"success": False, "error": str(e)}

    elif name == "test_keyboard_navigation":
        from checks.accessibility import check_keyboard_navigation

        t = await get_tester()
        project_name = args.get("project", "default")
        session_id = args.get("session_id")
        url = args.get("url")
        max_tabs = args.get("max_tabs", 50)

        ephemeral = False
        if session_id:
            session = session_manager.get_session(session_id)
            page = session.page
        elif url:
            context = await t.get_context(project_name)
            page = await context.new_page()
            page.set_default_timeout(config.TIMEOUT)
            await page.goto(url, wait_until="networkidle")
            ephemeral = True
        else:
            return {"success": False, "error": "Provide either 'url' or 'session_id'"}

        try:
            result = await check_keyboard_navigation(page, max_tabs)
            result["url"] = page.url
            return result
        finally:
            if ephemeral:
                await page.close()

    elif name == "extract_text":
        t = await get_tester()
        project_name = args.get("project", "default")
        session_id = args.get("session_id")
        url = args.get("url")

        ephemeral = False
        if session_id:
            session = session_manager.get_session(session_id)
            page = session.page
        elif url:
            context = await t.get_context(project_name)
            page = await context.new_page()
            page.set_default_timeout(config.TIMEOUT)
            await page.goto(url, wait_until="networkidle")
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

    elif name == "check_console_during_interaction":
        session = session_manager.get_session(args["session_id"])
        # Clear existing console buffers
        pre_log_count = len(session.console_log)
        pre_error_count = len(session.console_errors)

        result = await interactions.execute_steps(
            session.page, args["steps"], session.project_name
        )
        session.url = session.page.url

        # Capture console output that occurred during steps
        new_logs = session.console_log[pre_log_count:]
        new_errors = session.console_errors[pre_error_count:]

        result["console_log"] = new_logs
        result["console_errors"] = new_errors
        result["console_log_count"] = len(new_logs)
        result["console_error_count"] = len(new_errors)
        return result

    elif name == "get_console_errors":
        session = session_manager.get_session(args["session_id"])
        clear = args.get("clear", True)

        result = {
            "session_id": session.session_id,
            "url": session.url,
            "console_log": list(session.console_log),
            "console_errors": list(session.console_errors),
            "console_log_count": len(session.console_log),
            "console_error_count": len(session.console_errors),
        }

        if clear:
            session.console_log.clear()
            session.console_errors.clear()

        return result

    elif name == "copy_auth":
        source = project_manager.get(args["from_project"])
        if not source:
            return {"success": False, "error": f"Source project '{args['from_project']}' not found"}
        target = project_manager.get(args["to_project"])
        if not target:
            return {"success": False, "error": f"Target project '{args['to_project']}' not found"}
        if not source.auth or not source.auth.method:
            return {"success": False, "error": f"Source project '{args['from_project']}' has no auth configured"}

        import copy
        target.auth = copy.deepcopy(source.auth)
        target.is_logged_in = False
        project_manager._save()

        # Also copy browser context cookies if source is logged in
        if source.is_logged_in:
            t = await get_tester()
            if source.name in t.contexts:
                source_ctx = t.contexts[source.name]
                cookies = await source_ctx.cookies()
                target_ctx = await t.get_context(target.name)
                await target_ctx.add_cookies(cookies)
                target.is_logged_in = True
                project_manager._save()

        return {
            "success": True,
            "message": f"Auth copied from '{args['from_project']}' to '{args['to_project']}'",
            "method": target.auth.method,
            "session_copied": target.is_logged_in,
        }

    elif name == "get_attribute":
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
            context = await t.get_context(project_name)
            page = await context.new_page()
            page.set_default_timeout(config.TIMEOUT)
            await page.goto(url, wait_until="networkidle")
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

    elif name == "set_viewport":
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
        if device and device in device_presets:
            width = device_presets[device]["width"]
            height = device_presets[device]["height"]
        else:
            width = args.get("width", config.VIEWPORT_WIDTH)
            height = args.get("height", config.VIEWPORT_HEIGHT)

        await session.page.set_viewport_size({"width": width, "height": height})
        screenshot_path = await interactions.take_screenshot(
            session.page, session.project_name, f"viewport_{width}x{height}"
        )
        return {
            "success": True,
            "viewport": {"width": width, "height": height},
            "device": device,
            "screenshot_path": screenshot_path,
            "url": session.url,
        }

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
