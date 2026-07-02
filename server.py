import asyncio
import json
import os
import time
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from tester import WebsiteTester
from crawler import Crawler
from projects import ProjectManager
from auth import AuthHandler
from sessions import SessionManager, real_page
import interactions
import config

# Initialize
server = Server("website-tester")
project_manager = ProjectManager()
tester: WebsiteTester = None
auth_handler = AuthHandler()
session_manager = SessionManager()


async def get_tester() -> WebsiteTester:
    """Get or create the tester instance, restarting if the browser crashed."""
    global tester
    if tester is None or tester.browser is None or not tester.browser.is_connected():
        if tester is None:
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
                    "max_depth": {"type": "integer", "description": "Max crawl depth (default: 3)", "default": 3},
                    "screenshot_dir": {"type": "string", "description": "Absolute path to save screenshots (e.g. '/home/user/myproject/e2e_testing'). Defaults to built-in data/screenshots/ if omitted."}
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
                        "type": ["array", "string"],
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
                        "type": ["array", "string"],
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
                        "type": ["array", "string"],
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
                    "force": {"type": ["boolean", "string"], "description": "Bypass actionability checks (default: false). Use when overlays intercept clicks."}
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
                        "type": ["array", "string"],
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
            description="Execute a multi-step interaction workflow. Supports 25 actions: click, force_click, fill, force_fill, type, select, select_option, wait, wait_for, wait_for_text, screenshot, navigate, hover, press_key, check, uncheck, scroll_to, scroll_within, evaluate_js, drag, right_click, go_back, go_forward, upload_file, wait_for_network. Can work on an existing session or create an ephemeral page.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to open (creates ephemeral page if no session_id)"},
                    "session_id": {"type": "string", "description": "Existing session ID (alternative to url)"},
                    "steps": {
                        "type": ["array", "string"],
                        "description": "Steps to execute. Each step has 'action' and action-specific fields.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": ["click", "force_click", "fill", "force_fill", "type", "select", "select_option", "wait", "wait_for", "wait_for_text", "screenshot", "navigate", "hover", "press_key", "check", "uncheck", "scroll_to", "scroll_within", "evaluate_js", "drag", "right_click", "go_back", "go_forward", "upload_file", "wait_for_network"],
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
                                "label": {"type": "string", "description": "Label for screenshot filename (screenshot action), or option label text (select_option action)"},
                                "force": {"type": ["boolean", "string"], "description": "Bypass actionability checks on click (default: false)"},
                                "script": {"type": "string", "description": "JavaScript to evaluate (for evaluate_js)"},
                                "direction": {"type": "string", "enum": ["up", "down", "left", "right"], "description": "Scroll direction (for scroll_within)"},
                                "amount": {"type": "integer", "description": "Scroll amount in pixels (for scroll_within, default: 300)"},
                                "files": {"type": "array", "items": {"type": "string"}, "description": "File paths (for upload_file)"},
                                "url_pattern": {"type": "string", "description": "URL substring to match (for wait_for_network)"},
                                "index": {"type": "integer", "description": "Option index (for select_option)"}
                            },
                            "required": ["action"]
                        }
                    },
                    "project": {"type": "string", "description": "Project name (optional)"},
                    "run_checks": {
                        "type": ["array", "string"],
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
                        "type": ["array", "string"],
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
                        "type": ["array", "string"],
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
                        "type": ["array", "string"],
                        "description": "Steps to execute (same format as interact_and_test).",
                        "items": {
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": ["click", "force_click", "fill", "force_fill", "type", "select", "select_option", "wait", "wait_for", "wait_for_text", "screenshot", "navigate", "hover", "press_key", "check", "uncheck", "scroll_to", "scroll_within", "evaluate_js", "drag", "right_click", "go_back", "go_forward", "upload_file", "wait_for_network"],
                                    "description": "Action to perform"
                                },
                                "selector": {"type": "string", "description": "CSS selector"},
                                "value": {"type": "string", "description": "Value (for fill, select)"},
                                "text": {"type": "string", "description": "Text to type or wait for"},
                                "target": {"type": "string", "description": "Drop target selector (for drag)"},
                                "key": {"type": "string", "description": "Key to press (for press_key)"},
                                "url": {"type": "string", "description": "URL (for navigate)"},
                                "timeout": {"type": "integer", "description": "Timeout in ms (for wait, wait_for)"},
                                "state": {"type": "string", "description": "State to wait for (visible, hidden, attached, detached)"},
                                "label": {"type": "string", "description": "Label for screenshot"},
                                "force": {"type": ["boolean", "string"], "description": "Bypass actionability checks"},
                                "script": {"type": "string", "description": "JavaScript to evaluate"},
                                "direction": {"type": "string", "enum": ["up", "down", "left", "right"], "description": "Scroll direction"},
                                "amount": {"type": "integer", "description": "Scroll amount in pixels"},
                                "files": {"type": "array", "items": {"type": "string"}, "description": "File paths (for upload_file)"},
                                "url_pattern": {"type": "string", "description": "URL pattern (for wait_for_network)"},
                                "index": {"type": "integer", "description": "Option index (for select_option)"}
                            },
                            "required": ["action"]
                        }
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
                        "type": ["array", "string"],
                        "description": "Steps to execute (same format as interact_and_test).",
                        "items": {
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": ["click", "force_click", "fill", "force_fill", "type", "select", "select_option", "wait", "wait_for", "wait_for_text", "screenshot", "navigate", "hover", "press_key", "check", "uncheck", "scroll_to", "scroll_within", "evaluate_js", "drag", "right_click", "go_back", "go_forward", "upload_file", "wait_for_network"],
                                    "description": "Action to perform"
                                },
                                "selector": {"type": "string", "description": "CSS selector"},
                                "value": {"type": "string", "description": "Value (for fill, select)"},
                                "text": {"type": "string", "description": "Text to type or wait for"},
                                "key": {"type": "string", "description": "Key to press (for press_key)"},
                                "url": {"type": "string", "description": "URL (for navigate)"},
                                "timeout": {"type": "integer", "description": "Timeout in ms (for wait, wait_for)"},
                                "state": {"type": "string", "description": "State to wait for"},
                                "force": {"type": ["boolean", "string"], "description": "Bypass actionability checks"},
                                "script": {"type": "string", "description": "JavaScript to evaluate"},
                                "direction": {"type": "string", "enum": ["up", "down", "left", "right"], "description": "Scroll direction"},
                                "amount": {"type": "integer", "description": "Scroll amount in pixels"},
                                "url_pattern": {"type": "string", "description": "URL pattern (for wait_for_network)"}
                            },
                            "required": ["action"]
                        }
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
                        "type": ["array", "string"],
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

        # Workflow Speed Tools
        Tool(
            name="screenshot_session",
            description="Take a screenshot of the current session page state. No actions performed — just captures what's on screen.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "full_page": {"type": "boolean", "description": "Capture full scrollable page (default: true)"}
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="run_checks_on_session",
            description="Run visual/accessibility/functionality/seo/performance checks on an active session page. Unlike test_url, this doesn't open a new page — it checks the current state after interactions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "checks": {
                        "type": ["array", "string"],
                        "description": "Check types to run (default: all)",
                        "items": {"type": "string", "enum": ["visual", "accessibility", "functionality", "seo", "performance"]}
                    }
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="go_back",
            description="Navigate back in session browser history. Like clicking the browser back button.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"}
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="go_forward",
            description="Navigate forward in session browser history.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"}
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="handle_dialog",
            description="Set up handling for JavaScript dialogs (alert, confirm, prompt) on a session. Must be called BEFORE the action that triggers the dialog.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "action": {"type": "string", "enum": ["accept", "dismiss"], "description": "Accept or dismiss the dialog"},
                    "prompt_text": {"type": "string", "description": "Text to enter for prompt() dialogs (optional)"}
                },
                "required": ["session_id", "action"]
            }
        ),
        Tool(
            name="upload_file",
            description="Set file(s) on a file input element. Works with <input type='file'> elements.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "selector": {"type": "string", "description": "CSS selector for the file input"},
                    "files": {
                        "type": ["array", "string"],
                        "description": "File paths to upload",
                        "items": {"type": "string"}
                    }
                },
                "required": ["session_id", "selector", "files"]
            }
        ),
        Tool(
            name="wait_for_network",
            description="Wait for a specific network request to complete. Use URL pattern matching (substring) to wait for API calls instead of blind timeouts.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "url_pattern": {"type": "string", "description": "Substring to match in request URL (e.g. '/api/tasks', 'graphql')"},
                    "method": {"type": "string", "description": "HTTP method filter (optional, e.g. 'POST', 'GET')"},
                    "timeout": {"type": "integer", "description": "Max wait time in ms (default: 30000)"}
                },
                "required": ["session_id", "url_pattern"]
            }
        ),

        # Advanced Testing Tools
        Tool(
            name="intercept_network",
            description="Mock API responses on a session. Intercept requests matching a URL pattern and return custom responses. Use to test error states, empty states, loading states without needing the real backend. Call BEFORE the action that triggers the request.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "url_pattern": {"type": "string", "description": "URL substring to match (e.g. '/api/tasks', 'graphql')"},
                    "status": {"type": "integer", "description": "HTTP status code to return (default: 200)"},
                    "body": {"type": "string", "description": "Response body (JSON string or plain text)"},
                    "content_type": {"type": "string", "description": "Content-Type header (default: 'application/json')"},
                    "method": {"type": "string", "description": "HTTP method filter (optional, e.g. 'GET', 'POST')"},
                    "once": {"type": "boolean", "description": "Only intercept the first matching request (default: false)"}
                },
                "required": ["session_id", "url_pattern"]
            }
        ),
        Tool(
            name="clear_intercepts",
            description="Remove network mocks set by intercept_network. Clears all intercepts on the session, or only those matching a URL pattern.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "url_pattern": {"type": "string", "description": "Only remove intercepts registered with this exact pattern (optional — omit to clear all)"}
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="get_local_storage",
            description="Read localStorage or sessionStorage from a session page. Returns all entries or specific keys.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "storage": {"type": "string", "enum": ["local", "session"], "description": "Storage type (default: 'local')"},
                    "keys": {
                        "type": ["array", "string"],
                        "description": "Specific keys to read (optional, reads all if omitted)",
                        "items": {"type": "string"}
                    }
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="set_local_storage",
            description="Write to localStorage or sessionStorage on a session page.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "storage": {"type": "string", "enum": ["local", "session"], "description": "Storage type (default: 'local')"},
                    "entries": {
                        "type": "object",
                        "description": "Key-value pairs to set (e.g. {\"theme\": \"dark\", \"token\": \"abc\"})"
                    },
                    "clear_first": {"type": "boolean", "description": "Clear all entries before setting new ones (default: false)"}
                },
                "required": ["session_id", "entries"]
            }
        ),
        Tool(
            name="select_iframe",
            description="Switch into an iframe to interact with embedded content. Returns a new session scoped to the iframe. Use close_session on the returned session when done.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Parent session ID"},
                    "selector": {"type": "string", "description": "CSS selector for the iframe element"}
                },
                "required": ["session_id", "selector"]
            }
        ),
        Tool(
            name="reload_page",
            description="Reload the current session page. Useful for testing if state persists after refresh.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"}
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="get_computed_style",
            description="Get actual rendered CSS property values for elements matching a selector. Verify colors, fonts, spacing, display, opacity programmatically.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "selector": {"type": "string", "description": "CSS selector"},
                    "properties": {
                        "type": ["array", "string"],
                        "description": "CSS properties to read (e.g. ['color', 'font-size', 'display', 'opacity', 'background-color'])",
                        "items": {"type": "string"}
                    },
                    "max_results": {"type": "integer", "description": "Max elements to check (default: 10)"}
                },
                "required": ["session_id", "selector", "properties"]
            }
        ),
        Tool(
            name="emulate_network",
            description="Throttle network speed on a session to simulate slow connections. Use to test loading spinners, offline fallbacks, timeout handling.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "preset": {
                        "type": "string",
                        "enum": ["slow_3g", "fast_3g", "offline", "reset"],
                        "description": "Network preset: slow_3g (500kbps/400ms), fast_3g (1.5Mbps/150ms), offline (no network), reset (back to normal)"
                    }
                },
                "required": ["session_id", "preset"]
            }
        ),
        Tool(
            name="test_dark_mode",
            description="Toggle prefers-color-scheme between light and dark on a session. Takes a screenshot showing the result.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "mode": {"type": "string", "enum": ["dark", "light"], "description": "Color scheme to emulate"}
                },
                "required": ["session_id", "mode"]
            }
        ),

        # AI Agent Speed Tools
        Tool(
            name="assert_condition",
            description="Programmatic assertion — check a condition on the page and return pass/fail instantly without needing a screenshot. Supports: text_contains, text_equals, element_exists, element_visible, element_count, url_contains, title_contains, attribute_equals.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "assertion": {
                        "type": "string",
                        "enum": ["text_contains", "text_equals", "element_exists", "element_visible", "element_count", "url_contains", "title_contains", "attribute_equals"],
                        "description": "Type of assertion"
                    },
                    "selector": {"type": "string", "description": "CSS selector (for element-based assertions)"},
                    "expected": {"type": "string", "description": "Expected value (text, count as string, URL substring, attribute value)"},
                    "attribute": {"type": "string", "description": "Attribute name (for attribute_equals)"}
                },
                "required": ["session_id", "assertion"]
            }
        ),
        Tool(
            name="find_element",
            description="Smart element finder — search by text content, role, or partial match. Returns the best CSS selector to use. Saves the agent from guessing selectors.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "text": {"type": "string", "description": "Text content to search for (partial match)"},
                    "tag": {"type": "string", "description": "HTML tag filter (e.g. 'button', 'a', 'input')"},
                    "role": {"type": "string", "description": "ARIA role filter (e.g. 'button', 'link', 'textbox')"},
                    "near": {"type": "string", "description": "CSS selector of a nearby element (find elements near this one)"},
                    "max_results": {"type": "integer", "description": "Max results (default: 5)"}
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="auto_fill_form",
            description="Auto-detect all form fields, infer their types (email, phone, name, address, etc.), fill with smart test data, and optionally submit. Replaces 5-10 tool calls with one.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "form_selector": {"type": "string", "description": "CSS selector for the form (default: first form on page)"},
                    "overrides": {
                        "type": "object",
                        "description": "Override auto-detected values: {selector: value} (e.g. {\"#email\": \"custom@test.com\"})"
                    },
                    "submit": {"type": "boolean", "description": "Submit the form after filling (default: false)"}
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="get_network_log",
            description="Get all network requests/responses captured during a session. See what API calls were made, status codes, methods, and response sizes. Optionally filter by URL pattern.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "url_filter": {"type": "string", "description": "URL substring filter (optional, e.g. '/api/')"},
                    "clear": {"type": "boolean", "description": "Clear the log after reading (default: false)"}
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="snapshot_page_state",
            description="Save the current page state (URL, cookies, localStorage, sessionStorage) as a named checkpoint. Use restore_page_state to return to it later. Enables testing multiple paths from the same starting point.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "name": {"type": "string", "description": "Name for this snapshot (e.g. 'before_submit', 'logged_in')"}
                },
                "required": ["session_id", "name"]
            }
        ),
        Tool(
            name="restore_page_state",
            description="Restore a previously saved page state snapshot. Navigates to the saved URL and restores cookies, localStorage, and sessionStorage.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "name": {"type": "string", "description": "Name of the snapshot to restore"}
                },
                "required": ["session_id", "name"]
            }
        ),
        Tool(
            name="diff_page_state",
            description="Compare the current DOM state with a previous snapshot. Shows elements added, removed, and changed. Much more precise than screenshot diff for understanding what an action changed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "name": {"type": "string", "description": "Snapshot name to compare against (from snapshot_page_state)"}
                },
                "required": ["session_id", "name"]
            }
        ),
        Tool(
            name="get_cookies",
            description="Read all cookies from a session. Essential for debugging auth issues.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "domain_filter": {"type": "string", "description": "Filter by domain (optional)"}
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="check_color_contrast",
            description="Check WCAG color contrast ratios for text elements on the page. Reports elements that fail AA or AAA standards.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "selector": {"type": "string", "description": "CSS selector to check (default: all text elements)"},
                    "level": {"type": "string", "enum": ["AA", "AAA"], "description": "WCAG level to check against (default: AA)"},
                    "max_results": {"type": "integer", "description": "Max elements to check (default: 50)"}
                },
                "required": ["session_id"]
            }
        ),

        # New Tools — Friction Reducers
        Tool(
            name="force_fill",
            description="Fill an input bypassing actionability checks. Uses Playwright's force=True. Useful when overlays or dialogs block normal fill.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "selector": {"type": "string", "description": "CSS selector for the input"},
                    "value": {"type": "string", "description": "Value to fill"}
                },
                "required": ["session_id", "selector", "value"]
            }
        ),
        Tool(
            name="scroll_into_view",
            description="Scroll an element into the viewport without clicking it. Useful for lazy-loaded content or scrolling to a section.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "selector": {"type": "string", "description": "CSS selector of element to scroll to"}
                },
                "required": ["session_id", "selector"]
            }
        ),
        Tool(
            name="wait_for_gone",
            description="Wait for an element to disappear (removed from DOM or hidden). Useful for waiting for modals/dialogs/spinners to close.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "selector": {"type": "string", "description": "CSS selector of element to wait for disappearance"},
                    "timeout": {"type": "integer", "description": "Max wait time in ms (default: 30000)"}
                },
                "required": ["session_id", "selector"]
            }
        ),
        Tool(
            name="get_page_html",
            description="Return raw outerHTML of matching elements, or full page HTML if no selector. Useful for inspecting component structure.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "selector": {"type": "string", "description": "CSS selector (optional — omit for full page HTML)"},
                    "max_length": {"type": "integer", "description": "Max characters to return (default: 50000)"}
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="get_table_data",
            description="Parse an HTML table into structured JSON with headers mapped to cell values. Returns {headers, rows, total_rows}.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "selector": {"type": "string", "description": "CSS selector for the table (default: 'table')"},
                    "max_rows": {"type": "integer", "description": "Max rows to return (default: 100)"}
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="get_toast_messages",
            description="Capture visible toast/notification/alert messages on page. Checks common toast selectors ([role=alert], [role=status], [aria-live], .toast, .notification, Toastify, Sonner, Radix).",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "wait_ms": {"type": "integer", "description": "Wait this many ms before capturing (lets toast animate in, default: 0)"},
                    "selector": {"type": "string", "description": "Override default toast selectors with a custom CSS selector"}
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="select_option",
            description="Select from native <select> or custom dropdown (Radix/shadcn combobox). Auto-detects type. For custom dropdowns: clicks to open, then finds option by text cascade.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "selector": {"type": "string", "description": "CSS selector for the <select> or combobox trigger"},
                    "value": {"type": "string", "description": "Option value to select"},
                    "label": {"type": "string", "description": "Option label text to select"},
                    "index": {"type": "integer", "description": "Option index to select (0-based)"}
                },
                "required": ["session_id", "selector"]
            }
        ),
        Tool(
            name="get_response_body",
            description="Get the actual API response body text for a request matching a URL pattern. Critical for diagnosing 400/500 errors. Response bodies are captured automatically for fetch/xhr/document requests.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "url_pattern": {"type": "string", "description": "URL substring to match (e.g. '/api/quotes', 'graphql')"},
                    "method": {"type": "string", "description": "HTTP method filter (optional, e.g. 'POST', 'GET')"}
                },
                "required": ["session_id", "url_pattern"]
            }
        ),

        # Web Search & Fetch
        Tool(
            name="web_search",
            description="Search DuckDuckGo and return titles, URLs, and snippets. Useful for looking up documentation, verifying external content, or researching during testing workflows.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Max results to return (default: 10)", "default": 10}
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="web_fetch",
            description="Fetch a URL and extract readable text content. Use to read documentation pages, verify external link content, or inspect page text without a browser.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                    "max_length": {"type": "integer", "description": "Max content length in characters (default: 50000)", "default": 50000},
                    "raw_html": {"type": "boolean", "description": "Return raw HTML instead of extracted text (default: false)", "default": False},
                    "verify_ssl": {"type": "boolean", "description": "Verify TLS certificates (default: true). Set false for self-signed certs on local/dev servers.", "default": True}
                },
                "required": ["url"]
            }
        ),

        # Discovery
        Tool(
            name="describe_tools",
            description="Get a structured guide to all available tools — grouped by category, with workflow examples and tips. Call this first if you've never used this server before.",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["all", "new", "project", "auth", "static_testing", "results", "sessions", "interactive", "analysis", "workflow", "advanced", "recording", "agent_speed", "web"],
                        "description": "Filter by category (default: 'all')"
                    }
                },
                "required": []
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


# Args that are structured (arrays/objects) per the tool schemas. Only these get
# JSON-string coercion — free-text args like intercept_network's 'body' or a fill
# 'value' must NEVER be parsed, even if they look like JSON.
_STRUCTURED_ARGS = {
    "steps", "fields", "checks", "run_checks", "cookies", "viewports",
    "files", "keys", "attributes", "properties", "entries", "overrides",
}
# Structured args whose items are plain strings — a bare string like
# "seo,performance" is accepted as a comma-separated list.
_CSV_ARGS = {"checks", "run_checks", "files", "keys", "attributes", "properties"}
# Boolean args per the tool schemas.
_BOOL_ARGS = {
    "force", "check_external", "clear", "clear_first", "once", "submit",
    "full_page", "screenshot_after", "continue_on_error", "raw_html", "verify_ssl",
}


def _coerce_args(args: dict):
    """Coerce JSON-string args in place: MCP clients with stale schemas may
    serialize array/bool parameters as JSON strings."""
    for key, val in list(args.items()):
        if not isinstance(val, str):
            continue
        if key in _STRUCTURED_ARGS:
            if len(val) > 1 and val[0] in ('[', '{'):
                try:
                    args[key] = json.loads(val)
                except json.JSONDecodeError:
                    pass
            elif key in _CSV_ARGS and val:
                args[key] = [s.strip() for s in val.split(",") if s.strip()]
        elif key in _BOOL_ARGS and val.lower() in ('true', 'false'):
            args[key] = val.lower() == 'true'


async def _handle_tool(name: str, args: dict) -> dict:
    """Route tool calls to handlers."""

    _coerce_args(args)

    # Project Management
    if name == "create_project":
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
        proj_obj = project_manager.get(project_name)
        proj_screenshot_dir = proj_obj.screenshot_dir if proj_obj else None

        result = await t.test_url(
            url=args["url"],
            project_name=project_name,
            checks=checks,
            screenshot_dir=proj_screenshot_dir
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
        results = await t.test_multiple(urls, project.name, checks, screenshot_dir=project.screenshot_dir)

        # Save report
        report_path = await t.save_report(results, project.name)
        results["report_path"] = report_path

        # Update project
        project_manager.update_last_tested(project.name)

        return results

    # Results
    elif name == "get_screenshot":
        t = await get_tester()
        proj_obj = project_manager.get(args["project"])
        proj_screenshot_dir = proj_obj.screenshot_dir if proj_obj else None
        screenshot_path = t._get_screenshot_path(args["project"], args["url"], screenshot_dir=proj_screenshot_dir)

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
        proj_obj = project_manager.get(project_name)
        proj_screenshot_dir = proj_obj.screenshot_dir if proj_obj else None
        session = await session_manager.create_session(context, args["url"], project_name, screenshot_dir=proj_screenshot_dir)
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

    elif name == "close_session":
        closed = await session_manager.close_session(args["session_id"])
        if closed:
            return {"success": True, "message": f"Session '{args['session_id']}' closed"}
        return {"success": False, "error": f"Session '{args['session_id']}' not found"}

    elif name == "list_sessions":
        sessions = session_manager.list_sessions()
        result = {"sessions": sessions, "count": len(sessions)}
        if session_manager.recent_removals:
            result["recently_removed"] = session_manager.recent_removals
        return result

    # Interactive Tools
    elif name == "click_element":
        session = session_manager.get_session(args["session_id"])
        result = await interactions.click_element(
            session.page, args["selector"], force=args.get("force", False)
        )
        session.url = result["url"]
        screenshot_path = await interactions.take_screenshot(
            session.page, session.project_name, "after_click", screenshot_dir=session.screenshot_dir)
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
            session.page, session.project_name, "after_fill", screenshot_dir=session.screenshot_dir)
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
            shot_dir = session.screenshot_dir
        elif url:
            context = await t.get_context(project_name)
            page = await context.new_page()
            page.set_default_timeout(config.TIMEOUT)
            await page.goto(url, wait_until=config.WAIT_UNTIL)
            ephemeral = True
            proj_obj = project_manager.get(project_name)
            shot_dir = proj_obj.screenshot_dir if proj_obj else None
        else:
            return {"success": False, "error": "Provide either 'url' or 'session_id'"}

        try:
            result = await interactions.execute_steps(
                page, steps, project_name, continue_on_error, screenshot_dir=shot_dir
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
            await page.goto(url, wait_until=config.WAIT_UNTIL)
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
            await page.goto(url, wait_until=config.WAIT_UNTIL)
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
        project_name = args.get("project", "default")
        proj_obj = project_manager.get(project_name)
        result = await t.test_responsive(
            url=args["url"],
            project_name=project_name,
            viewports=args.get("viewports"),
            checks=args.get("run_checks"),
            screenshot_dir=proj_obj.screenshot_dir if proj_obj else None,
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
            await page.goto(url, wait_until=config.WAIT_UNTIL)
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
            session.page, session.project_name, "after_measure", screenshot_dir=session.screenshot_dir)
        result["screenshot_path"] = screenshot_path
        return result

    # Phase 3: Nice-to-Have
    elif name == "record_session":
        t = await get_tester()
        project_name = args.get("project", "default")
        proj_obj = project_manager.get(project_name)
        proj_screenshot_dir = proj_obj.screenshot_dir if proj_obj else None
        video_dir = os.path.join(config.DATA_DIR, "videos", project_name)
        os.makedirs(video_dir, exist_ok=True)

        context = await t.browser.new_context(
            viewport={"width": config.VIEWPORT_WIDTH, "height": config.VIEWPORT_HEIGHT},
            record_video_dir=video_dir,
            ignore_https_errors=True,
        )
        page = await context.new_page()
        page.set_default_timeout(config.TIMEOUT)

        try:
            await page.goto(args["url"], wait_until=config.WAIT_UNTIL)
            result = await interactions.execute_steps(
                page, args["steps"], project_name, screenshot_dir=proj_screenshot_dir
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
            await page.goto(url, wait_until=config.WAIT_UNTIL)
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
            await page.goto(url, wait_until=config.WAIT_UNTIL)
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
        # Record buffer offsets so only console output from these steps is reported
        pre_log_count = len(session.console_log)
        pre_error_count = len(session.console_errors)

        result = await interactions.execute_steps(
            session.page, args["steps"], session.project_name,
            screenshot_dir=session.screenshot_dir
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
            "console_errors": list(session.console_errors)[-50:],
            "console_log": list(session.console_log)[-100:],
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
            await page.goto(url, wait_until=config.WAIT_UNTIL)
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

    # Workflow Speed Tools
    elif name == "screenshot_session":
        session = session_manager.get_session(args["session_id"])
        full_page = args.get("full_page", True)
        screenshot_path = await interactions.take_screenshot(
            session.page, session.project_name, "session_state", screenshot_dir=session.screenshot_dir)
        if not full_page:
            # Retake as viewport-only screenshot
            base_dir = session.screenshot_dir if session.screenshot_dir else config.SCREENSHOT_DIR
            project_dir = os.path.join(base_dir, session.project_name)
            os.makedirs(project_dir, exist_ok=True)
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            screenshot_path = os.path.join(project_dir, f"interactive_{timestamp}_viewport.png")
            await real_page(session.page).screenshot(path=screenshot_path, full_page=False)
        return {
            "screenshot_path": screenshot_path,
            "url": session.url,
            "title": await session.page.title(),
        }

    elif name == "run_checks_on_session":
        from checks.visual import check_visual
        from checks.accessibility import check_accessibility
        from checks.functionality import check_functionality, check_seo, get_performance_metrics

        session = session_manager.get_session(args["session_id"])
        checks = args.get("checks", ["visual", "accessibility", "functionality", "seo", "performance"])
        page = session.page

        all_issues = []
        performance = {}

        if "visual" in checks:
            all_issues.extend(await check_visual(page))
        if "accessibility" in checks:
            all_issues.extend(await check_accessibility(page))
        if "functionality" in checks:
            all_issues.extend(await check_functionality(page))
        if "seo" in checks:
            all_issues.extend(await check_seo(page))
        if "performance" in checks:
            performance = await get_performance_metrics(page)

        screenshot_path = await interactions.take_screenshot(
            page, session.project_name, "after_checks", screenshot_dir=session.screenshot_dir)

        issues_by_severity = {}
        issues_by_type = {}
        for issue in all_issues:
            sev = issue.get("severity", "unknown")
            typ = issue.get("type", "unknown")
            issues_by_severity[sev] = issues_by_severity.get(sev, 0) + 1
            issues_by_type[typ] = issues_by_type.get(typ, 0) + 1

        return {
            "url": session.url,
            "title": await page.title(),
            "issues": all_issues,
            "issue_count": len(all_issues),
            "issues_by_severity": issues_by_severity,
            "issues_by_type": issues_by_type,
            "performance": performance,
            "screenshot_path": screenshot_path,
        }

    elif name == "go_back":
        session = session_manager.get_session(args["session_id"])
        page = real_page(session.page)
        await page.go_back(wait_until=config.WAIT_UNTIL)
        session.url = page.url
        screenshot_path = await interactions.take_screenshot(
            session.page, session.project_name, "after_back", screenshot_dir=session.screenshot_dir)
        return {
            "url": session.url,
            "title": await session.page.title(),
            "screenshot_path": screenshot_path,
        }

    elif name == "go_forward":
        session = session_manager.get_session(args["session_id"])
        page = real_page(session.page)
        await page.go_forward(wait_until=config.WAIT_UNTIL)
        session.url = page.url
        screenshot_path = await interactions.take_screenshot(
            session.page, session.project_name, "after_forward", screenshot_dir=session.screenshot_dir)
        return {
            "url": session.url,
            "title": await session.page.title(),
            "screenshot_path": screenshot_path,
        }

    elif name == "handle_dialog":
        session = session_manager.get_session(args["session_id"])
        dialog_page = real_page(session.page)
        action = args["action"]
        prompt_text = args.get("prompt_text")

        dialog_info = {}

        def on_dialog(dialog):
            dialog_info["type"] = dialog.type
            dialog_info["message"] = dialog.message
            dialog_info["default_value"] = dialog.default_value

        async def handle(dialog):
            on_dialog(dialog)
            if action == "accept":
                if prompt_text is not None:
                    await dialog.accept(prompt_text)
                else:
                    await dialog.accept()
            else:
                await dialog.dismiss()

        dialog_page.once("dialog", handle)

        return {
            "success": True,
            "message": f"Dialog handler set: will {action} next dialog",
            "prompt_text": prompt_text,
        }

    elif name == "upload_file":
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

    elif name == "wait_for_network":
        session = session_manager.get_session(args["session_id"])
        url_pattern = args["url_pattern"]
        method_filter = args.get("method")
        timeout = args.get("timeout", 30000)

        async def match_request(response):
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

    # Advanced Testing Tools
    elif name == "intercept_network":
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

        # ** crosses path separators, so this is true substring matching —
        # '**/*x*' would fail to match '/x/anything/after'
        glob = f"**{url_pattern}**"

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
                await route_page.unroute(glob, handle_route)
                session.intercepts = [i for i in session.intercepts if i["handler"] is not handle_route]

        await route_page.route(glob, handle_route)
        session.intercepts.append({"glob": glob, "handler": handle_route, "pattern": url_pattern})

        return {
            "success": True,
            "message": f"Intercepting requests matching '{url_pattern}' → {status}",
            "url_pattern": url_pattern,
            "status": status,
            "once": once,
            "active_intercepts": [i["pattern"] for i in session.intercepts],
        }

    elif name == "clear_intercepts":
        session = session_manager.get_session(args["session_id"])
        route_page = real_page(session.page)
        pattern_filter = args.get("url_pattern")

        removed, remaining = [], []
        for entry in session.intercepts:
            if pattern_filter and entry["pattern"] != pattern_filter:
                remaining.append(entry)
                continue
            try:
                await route_page.unroute(entry["glob"], entry["handler"])
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

    elif name == "get_local_storage":
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

    elif name == "set_local_storage":
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

    elif name == "select_iframe":
        session = session_manager.get_session(args["session_id"])
        frame_locator = session.page.frame_locator(args["selector"])

        # Get the actual frame from the page
        iframe_element = session.page.locator(args["selector"]).first
        await iframe_element.wait_for(state="attached", timeout=10000)
        content_frame = await iframe_element.content_frame()

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
        )
        session_manager.sessions[iframe_session_id] = iframe_session

        return {
            "success": True,
            "iframe_session_id": iframe_session_id,
            "parent_session_id": session.session_id,
            "iframe_url": content_frame.url,
            "selector": args["selector"],
        }

    elif name == "reload_page":
        session = session_manager.get_session(args["session_id"])
        page = real_page(session.page)
        await page.reload(wait_until=config.WAIT_UNTIL)
        session.url = page.url
        screenshot_path = await interactions.take_screenshot(
            session.page, session.project_name, "after_reload", screenshot_dir=session.screenshot_dir)
        return {
            "url": session.url,
            "title": await session.page.title(),
            "screenshot_path": screenshot_path,
        }

    elif name == "get_computed_style":
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

    elif name == "emulate_network":
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

    elif name == "test_dark_mode":
        session = session_manager.get_session(args["session_id"])
        mode = args["mode"]

        await session.page.emulate_media(color_scheme=mode)
        # Give page a moment to re-render
        import asyncio as _asyncio
        await _asyncio.sleep(0.3)

        screenshot_path = await interactions.take_screenshot(
            session.page, session.project_name, f"dark_mode_{mode}", screenshot_dir=session.screenshot_dir)
        return {
            "mode": mode,
            "screenshot_path": screenshot_path,
            "url": session.url,
        }

    # ------------------------------------------------------------------
    # AI Agent Speed Tools
    # ------------------------------------------------------------------

    elif name == "assert_condition":
        session = session_manager.get_session(args["session_id"])
        assertion = args["assertion"]
        selector = args.get("selector", "body")
        expected = args.get("expected", "")
        attribute = args.get("attribute", "")
        page = session.page

        passed = False
        actual = None

        if assertion == "text_contains":
            actual = await page.locator(selector).first.text_content() or ""
            passed = expected in actual

        elif assertion == "text_equals":
            actual = (await page.locator(selector).first.text_content() or "").strip()
            passed = actual == expected

        elif assertion == "element_exists":
            count = await page.locator(selector).count()
            actual = count
            passed = count > 0

        elif assertion == "element_visible":
            try:
                visible = await page.locator(selector).first.is_visible()
                actual = visible
                passed = visible
            except Exception:
                actual = False
                passed = False

        elif assertion == "element_count":
            count = await page.locator(selector).count()
            actual = count
            passed = count == int(expected)

        elif assertion == "url_contains":
            actual = page.url
            passed = expected in actual

        elif assertion == "title_contains":
            actual = await page.title()
            passed = expected in actual

        elif assertion == "attribute_equals":
            actual = await page.locator(selector).first.get_attribute(attribute)
            passed = actual == expected

        return {
            "assertion": assertion,
            "selector": selector,
            "expected": expected,
            "actual": actual if not isinstance(actual, str) or len(str(actual)) < 200 else str(actual)[:200] + "...",
            "passed": passed,
        }

    elif name == "find_element":
        session = session_manager.get_session(args["session_id"])
        text = args.get("text", "")
        tag = args.get("tag", "")
        role = args.get("role", "")
        near = args.get("near", "")
        max_results = args.get("max_results", 5)

        results = await session.page.evaluate("""(args) => {
            const [text, tag, role, near, maxResults] = args;
            let candidates = [];

            // Start with all elements or filtered by tag
            const selector = tag || '*';
            const allEls = document.querySelectorAll(selector);

            // If near is specified, get nearby element's bounding box
            let nearRect = null;
            if (near) {
                const nearEl = document.querySelector(near);
                if (nearEl) nearRect = nearEl.getBoundingClientRect();
            }

            for (const el of allEls) {
                // Filter by role
                if (role && el.getAttribute('role') !== role) continue;

                // Filter by text
                const elText = (el.textContent || '').trim();
                if (text && !elText.toLowerCase().includes(text.toLowerCase())) continue;

                // Skip invisible
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) continue;

                // Build best selector
                let bestSelector = el.tagName.toLowerCase();
                if (el.id) {
                    bestSelector = '#' + el.id;
                } else if (el.getAttribute('data-testid')) {
                    bestSelector = `[data-testid="${el.getAttribute('data-testid')}"]`;
                } else if (el.name) {
                    bestSelector = `${el.tagName.toLowerCase()}[name="${el.name}"]`;
                } else if (el.className && typeof el.className === 'string' && el.className.trim()) {
                    bestSelector = el.tagName.toLowerCase() + '.' + el.className.trim().split(/\\s+/).join('.');
                }

                let distance = 0;
                if (nearRect) {
                    const cx = rect.x + rect.width / 2;
                    const cy = rect.y + rect.height / 2;
                    const nx = nearRect.x + nearRect.width / 2;
                    const ny = nearRect.y + nearRect.height / 2;
                    distance = Math.sqrt((cx - nx) ** 2 + (cy - ny) ** 2);
                }

                candidates.push({
                    selector: bestSelector,
                    text: elText.substring(0, 60),
                    role: el.getAttribute('role') || null,
                    aria_label: el.getAttribute('aria-label') || null,
                    distance: nearRect ? Math.round(distance) : null,
                });
            }

            // Sort: nearest first if near is specified, otherwise by DOM order
            if (nearRect) {
                candidates.sort((a, b) => a.distance - b.distance);
            }

            return candidates.slice(0, maxResults);
        }""", [text, tag, role, near, max_results])

        return {
            "found": len(results),
            "elements": results,
        }

    elif name == "auto_fill_form":
        session = session_manager.get_session(args["session_id"])
        form_selector = args.get("form_selector", "form")
        overrides = args.get("overrides", {})
        submit = args.get("submit", False)

        # Detect fields and infer types
        fields = await session.page.evaluate("""(formSelector) => {
            const form = document.querySelector(formSelector);
            if (!form) return [];
            const inputs = form.querySelectorAll('input, select, textarea');
            return Array.from(inputs).map(el => {
                const name = (el.name || el.id || '').toLowerCase();
                const type = el.type || el.tagName.toLowerCase();
                const placeholder = (el.placeholder || '').toLowerCase();
                const label_el = el.id ? document.querySelector(`label[for="${el.id}"]`) : el.closest('label');
                const label = label_el ? label_el.textContent.trim().toLowerCase() : '';
                const all_hints = name + ' ' + placeholder + ' ' + label;

                // Build best selector
                let selector = el.tagName.toLowerCase();
                if (el.id) selector = '#' + el.id;
                else if (el.name) selector = `${el.tagName.toLowerCase()}[name="${el.name}"]`;

                return {
                    selector: selector,
                    type: type,
                    name: el.name || null,
                    id: el.id || null,
                    required: el.required,
                    hints: all_hints,
                    tag: el.tagName.toLowerCase(),
                    options: el.tagName === 'SELECT' ? Array.from(el.options).map(o => o.value).filter(v => v) : null,
                };
            }).filter(f => f.type !== 'hidden' && f.type !== 'submit' && f.type !== 'button');
        }""", form_selector)

        if not fields:
            return {"success": False, "error": f"No form fields found in '{form_selector}'"}

        # Infer values based on field type and hints
        test_data = {
            "email": "test@example.com",
            "password": "TestPassword123!",
            "tel": "+1234567890",
            "phone": "+1234567890",
            "url": "https://example.com",
            "number": "42",
            "date": "2025-01-15",
            "time": "10:30",
            "datetime-local": "2025-01-15T10:30",
            "month": "2025-01",
            "week": "2025-W03",
            "color": "#3366cc",
            "range": "50",
            "search": "test search",
        }
        name_hints = {
            "first": "John", "last": "Doe", "name": "John Doe",
            "company": "Test Corp", "organization": "Test Corp", "org": "Test Corp",
            "address": "123 Test Street", "street": "123 Test Street",
            "city": "San Francisco", "state": "CA", "zip": "94105", "postal": "94105",
            "country": "US", "username": "testuser", "user": "testuser",
            "comment": "This is a test comment.", "message": "This is a test message.",
            "description": "Test description for automated testing.",
            "title": "Test Title", "subject": "Test Subject",
            "age": "30", "quantity": "1", "amount": "100",
        }

        filled = []
        handled_radio_groups = set()
        for f in fields:
            selector = f["selector"]

            # Check for override
            if selector in overrides:
                value = overrides[selector]
            elif f["type"] in test_data:
                value = test_data[f["type"]]
            else:
                # Infer from name/placeholder/label hints
                value = "Test input"
                for hint_key, hint_value in name_hints.items():
                    if hint_key in f["hints"]:
                        value = hint_value
                        break

            try:
                if f["tag"] == "select" and f["options"]:
                    # Pick first non-empty option
                    await session.page.locator(selector).first.select_option(f["options"][0])
                    filled.append({"selector": selector, "value": f["options"][0]})
                elif f["type"] == "checkbox":
                    await session.page.locator(selector).first.check()
                    filled.append({"selector": selector, "value": "checked"})
                elif f["type"] == "radio":
                    # Check one radio per group, not every radio (later checks would undo earlier ones)
                    group = f.get("name") or selector
                    if group in handled_radio_groups:
                        filled.append({"selector": selector, "value": "skipped (group already selected)"})
                    else:
                        await session.page.locator(selector).first.check()
                        handled_radio_groups.add(group)
                        filled.append({"selector": selector, "value": "checked"})
                elif f["type"] == "file":
                    filled.append({"selector": selector, "value": "skipped"})
                elif f["type"] in interactions._DATE_TYPES:
                    await interactions._fill_date_input(session.page, selector, str(value))
                    filled.append({"selector": selector, "value": str(value)})
                else:
                    locator = session.page.locator(selector).first
                    await locator.click()
                    await locator.fill(str(value))
                    filled.append({"selector": selector, "value": str(value)})
            except Exception as e:
                filled.append({"selector": selector, "error": str(e)[:100]})

        result = {"success": True, "fields_filled": filled, "submitted": False}

        if submit:
            try:
                submit_btn = session.page.locator(f"{form_selector} [type='submit'], {form_selector} button:not([type='button'])").first
                await submit_btn.click()
                try:
                    await session.page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                result["submitted"] = True
                result["url"] = session.page.url
                result["title"] = await session.page.title()
            except Exception as e:
                result["submit_error"] = str(e)

        return result

    elif name == "get_network_log":
        session = session_manager.get_session(args["session_id"])
        url_filter = args.get("url_filter", "")
        clear = args.get("clear", False)

        log = session.network_log
        if url_filter:
            log = [entry for entry in log if url_filter in entry["url"]]

        capped = log[-100:]
        result = {
            "total_requests": len(session.network_log),
            "filtered_count": len(log),
            "requests": [
                {
                    "url": e["url"] if len(e["url"]) <= 120 else "..." + e["url"][-117:],
                    "status": e["status"],
                    "method": e["method"],
                    "resource_type": e["resource_type"],
                }
                for e in capped
            ],
        }

        if clear:
            session.network_log.clear()
            result["cleared"] = True

        return result

    elif name == "snapshot_page_state":
        session = session_manager.get_session(args["session_id"])
        snap_name = args["name"]

        state = await session.page.evaluate("""() => {
            const ls = {};
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                ls[key] = localStorage.getItem(key);
            }
            const ss = {};
            for (let i = 0; i < sessionStorage.length; i++) {
                const key = sessionStorage.key(i);
                ss[key] = sessionStorage.getItem(key);
            }
            // Capture a DOM signature for diff (all elements, up to 1000)
            const elements = document.querySelectorAll('*');
            const domSig = [];
            for (let i = 0; i < Math.min(elements.length, 1000); i++) {
                const el = elements[i];
                const cls = el.className && typeof el.className === 'string'
                    ? el.className.trim().split(/\\s+/).slice(0, 2).join(' ') : null;
                domSig.push({
                    tag: el.tagName.toLowerCase(),
                    id: el.id || el.getAttribute('data-testid') || null,
                    cls: cls || null,
                    text: el.children.length === 0 ? (el.textContent || '').trim().substring(0, 40) : null,
                });
            }
            return { localStorage: ls, sessionStorage: ss, domSignature: domSig };
        }""")

        cookies = await real_page(session.page).context.cookies()

        session.snapshots[snap_name] = {
            "url": session.page.url,
            "title": await session.page.title(),
            "cookies": cookies,
            "localStorage": state["localStorage"],
            "sessionStorage": state["sessionStorage"],
            "domSignature": state["domSignature"],
            "timestamp": time.time(),
        }

        return {
            "success": True,
            "name": snap_name,
            "url": session.page.url,
            "snapshot_count": len(session.snapshots),
        }

    elif name == "restore_page_state":
        session = session_manager.get_session(args["session_id"])
        snap_name = args["name"]

        if snap_name not in session.snapshots:
            return {"success": False, "error": f"Snapshot '{snap_name}' not found. Available: {list(session.snapshots.keys())}"}

        snap = session.snapshots[snap_name]
        page = real_page(session.page)

        # Restore cookies
        await page.context.clear_cookies()
        if snap["cookies"]:
            await page.context.add_cookies(snap["cookies"])

        # Navigate to saved URL
        await page.goto(snap["url"], wait_until=config.WAIT_UNTIL)

        # Restore storage
        await page.evaluate("""(state) => {
            localStorage.clear();
            for (const [k, v] of Object.entries(state.localStorage || {})) {
                localStorage.setItem(k, v);
            }
            sessionStorage.clear();
            for (const [k, v] of Object.entries(state.sessionStorage || {})) {
                sessionStorage.setItem(k, v);
            }
        }""", snap)

        # Reload so the app actually boots with the restored cookies + storage —
        # without this, an SPA that read storage on startup keeps its old state.
        await page.reload(wait_until=config.WAIT_UNTIL)

        session.url = page.url
        return {
            "success": True,
            "name": snap_name,
            "restored_url": page.url,
            "title": await page.title(),
        }

    elif name == "diff_page_state":
        session = session_manager.get_session(args["session_id"])
        snap_name = args["name"]

        if snap_name not in session.snapshots:
            return {"success": False, "error": f"Snapshot '{snap_name}' not found. Available: {list(session.snapshots.keys())}"}

        snap = session.snapshots[snap_name]
        old_dom = snap["domSignature"]

        # Get current DOM signature
        current_dom = await session.page.evaluate("""() => {
            const elements = document.querySelectorAll('*');
            const domSig = [];
            for (let i = 0; i < Math.min(elements.length, 1000); i++) {
                const el = elements[i];
                const cls = el.className && typeof el.className === 'string'
                    ? el.className.trim().split(/\\s+/).slice(0, 2).join(' ') : null;
                domSig.push({
                    tag: el.tagName.toLowerCase(),
                    id: el.id || el.getAttribute('data-testid') || null,
                    cls: cls || null,
                    text: el.children.length === 0 ? (el.textContent || '').trim().substring(0, 40) : null,
                });
            }
            return domSig;
        }""")

        # Build index by id for comparison
        old_by_id = {e["id"]: e for e in old_dom if e.get("id")}
        new_by_id = {e["id"]: e for e in current_dom if e.get("id")}

        added_ids = set(new_by_id.keys()) - set(old_by_id.keys())
        removed_ids = set(old_by_id.keys()) - set(new_by_id.keys())
        common_ids = set(old_by_id.keys()) & set(new_by_id.keys())

        changed = []
        for eid in common_ids:
            old_e = old_by_id[eid]
            new_e = new_by_id[eid]
            diffs = {}
            for key in ["tag", "cls", "text"]:
                if old_e.get(key) != new_e.get(key):
                    diffs[key] = {"old": old_e.get(key), "new": new_e.get(key)}
            if diffs:
                changed.append({"id": eid, "changes": diffs})

        # Also compare counts by tag
        from collections import Counter
        old_tags = Counter(e["tag"] for e in old_dom)
        new_tags = Counter(e["tag"] for e in current_dom)
        tag_diffs = {}
        for tag in set(list(old_tags.keys()) + list(new_tags.keys())):
            if old_tags.get(tag, 0) != new_tags.get(tag, 0):
                tag_diffs[tag] = {"old": old_tags.get(tag, 0), "new": new_tags.get(tag, 0)}

        return {
            "snapshot_name": snap_name,
            "url_changed": snap["url"] != session.page.url,
            "old_url": snap["url"],
            "current_url": session.page.url,
            "elements_added_ids": list(added_ids)[:20],
            "elements_removed_ids": list(removed_ids)[:20],
            "elements_changed": changed[:20],
            "tag_count_changes": tag_diffs,
            "old_element_count": len(old_dom),
            "new_element_count": len(current_dom),
        }

    elif name == "get_cookies":
        session = session_manager.get_session(args["session_id"])
        domain_filter = args.get("domain_filter", "")

        cookies = await real_page(session.page).context.cookies()

        if domain_filter:
            cookies = [c for c in cookies if domain_filter in c.get("domain", "")]

        return {
            "total": len(cookies),
            "cookies": cookies,
        }

    elif name == "check_color_contrast":
        session = session_manager.get_session(args["session_id"])
        selector = args.get("selector", "p, span, a, li, td, th, h1, h2, h3, h4, h5, h6, label, button")
        level = args.get("level", "AA")
        max_results = args.get("max_results", 50)

        # Get computed colors for text elements
        elements = await session.page.evaluate("""(args) => {
            const [selector, maxResults] = args;
            const els = document.querySelectorAll(selector);
            const results = [];

            function parseColor(color) {
                // Parse rgb/rgba string to [r, g, b]
                const match = color.match(/rgba?\\(([\\d.]+),\\s*([\\d.]+),\\s*([\\d.]+)/);
                if (match) return [parseFloat(match[1]), parseFloat(match[2]), parseFloat(match[3])];
                return null;
            }

            function luminance(r, g, b) {
                const [rs, gs, bs] = [r, g, b].map(c => {
                    c = c / 255;
                    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
                });
                return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
            }

            function contrastRatio(l1, l2) {
                const lighter = Math.max(l1, l2);
                const darker = Math.min(l1, l2);
                return (lighter + 0.05) / (darker + 0.05);
            }

            for (let i = 0; i < Math.min(els.length, maxResults); i++) {
                const el = els[i];
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;

                const style = window.getComputedStyle(el);
                const fg = parseColor(style.color);
                const bg = parseColor(style.backgroundColor);

                if (!fg || !bg) continue;
                // Skip transparent backgrounds (alpha check)
                const bgAlpha = style.backgroundColor.match(/rgba\\([^,]+,[^,]+,[^,]+,\\s*([\\d.]+)/);
                if (bgAlpha && parseFloat(bgAlpha[1]) < 0.1) continue;

                const fgLum = luminance(fg[0], fg[1], fg[2]);
                const bgLum = luminance(bg[0], bg[1], bg[2]);
                const ratio = contrastRatio(fgLum, bgLum);
                const fontSize = parseFloat(style.fontSize);
                const fontWeight = parseInt(style.fontWeight) || 400;
                const isLargeText = fontSize >= 24 || (fontSize >= 18.66 && fontWeight >= 700);

                let selector_str = el.tagName.toLowerCase();
                if (el.id) selector_str = '#' + el.id;
                else if (el.className && typeof el.className === 'string')
                    selector_str += '.' + el.className.trim().split(/\\s+/)[0];

                results.push({
                    selector: selector_str,
                    text: (el.textContent || '').trim().substring(0, 40),
                    ratio: Math.round(ratio * 100) / 100,
                    large: isLargeText,
                    foreground: style.color,
                    background: style.backgroundColor,
                });
            }
            return results;
        }""", [selector, max_results])

        # Evaluate against WCAG thresholds
        aa_normal = 4.5
        aa_large = 3.0
        aaa_normal = 7.0
        aaa_large = 4.5

        failures = []
        for el in elements:
            ratio = el["ratio"]
            is_large = el["large"]
            threshold = (aa_large if is_large else aa_normal) if level == "AA" else (aaa_large if is_large else aaa_normal)
            if ratio < threshold:
                el["required"] = threshold
                failures.append(el)

        return {
            "level": level,
            "checked": len(elements),
            "fail_count": len(failures),
            "failures": failures[:30],
        }

    # ------------------------------------------------------------------
    # New Tools — Friction Reducers
    # ------------------------------------------------------------------

    elif name == "force_fill":
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

    elif name == "scroll_into_view":
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

    elif name == "wait_for_gone":
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

    elif name == "get_page_html":
        session = session_manager.get_session(args["session_id"])
        selector = args.get("selector")
        max_length = args.get("max_length", 50000)

        if selector:
            elements = await session.page.evaluate("""(args) => {
                const [selector, maxLen] = args;
                const stripBase64 = html => html.replace(/(<[^>]+(?:src|href|data|style)=["'])data:[^;]+;base64,[^"']+/gi, '$1[base64-removed]');
                const els = document.querySelectorAll(selector);
                const results = [];
                let totalLen = 0;
                for (const el of els) {
                    const html = stripBase64(el.outerHTML);
                    if (totalLen + html.length > maxLen) {
                        results.push({
                            tag: el.tagName.toLowerCase(),
                            id: el.id || null,
                            outer_html: html.substring(0, maxLen - totalLen) + '... [truncated]',
                        });
                        break;
                    }
                    results.push({
                        tag: el.tagName.toLowerCase(),
                        id: el.id || null,
                        outer_html: html,
                    });
                    totalLen += html.length;
                }
                return results;
            }""", [selector, max_length])
            return {
                "selector": selector,
                "count": len(elements),
                "elements": elements,
            }
        else:
            html = await session.page.content()
            import re
            html = re.sub(r'(<[^>]+(?:src|href|data|style)=["\'])data:[^;]+;base64,[^"\']+', r'\1[base64-removed]', html, flags=re.IGNORECASE)
            truncated = len(html) > max_length
            return {
                "html": html[:max_length] + ("... [truncated]" if truncated else ""),
                "truncated": truncated,
                "full_length": len(html),
            }

    elif name == "get_table_data":
        session = session_manager.get_session(args["session_id"])
        selector = args.get("selector", "table")
        max_rows = args.get("max_rows", 100)

        table_data = await session.page.evaluate("""(args) => {
            const [selector, maxRows] = args;
            const table = document.querySelector(selector);
            if (!table) return null;

            // Extract headers
            let headers = [];
            const thead = table.querySelector('thead');
            if (thead) {
                const headerRow = thead.querySelector('tr');
                if (headerRow) {
                    headers = Array.from(headerRow.querySelectorAll('th, td')).map(
                        cell => cell.textContent.trim()
                    );
                }
            }

            // If no thead, use first row as headers
            if (headers.length === 0) {
                const firstRow = table.querySelector('tr');
                if (firstRow) {
                    headers = Array.from(firstRow.querySelectorAll('th, td')).map(
                        cell => cell.textContent.trim()
                    );
                }
            }

            // Extract body rows
            const rows = [];
            const tbody = table.querySelector('tbody') || table;
            const trs = tbody.querySelectorAll('tr');
            const startIdx = (!thead && trs.length > 0) ? 1 : 0;  // skip header row if no thead

            for (let i = startIdx; i < trs.length && rows.length < maxRows; i++) {
                const cells = trs[i].querySelectorAll('td, th');
                if (cells.length === 0) continue;
                const row = {};
                for (let j = 0; j < cells.length; j++) {
                    const key = j < headers.length ? headers[j] : `col_${j}`;
                    row[key] = cells[j].textContent.trim();
                }
                rows.push(row);
            }

            // Total rows count
            const allBodyRows = tbody.querySelectorAll('tr');
            const totalRows = allBodyRows.length - ((!thead && allBodyRows.length > 0) ? 1 : 0);

            return { headers, rows, total_rows: totalRows };
        }""", [selector, max_rows])

        if table_data is None:
            return {"success": False, "error": f"No table found matching '{selector}'"}

        return {
            "success": True,
            "selector": selector,
            "headers": table_data["headers"],
            "rows": table_data["rows"],
            "rows_returned": len(table_data["rows"]),
            "total_rows": table_data["total_rows"],
        }

    elif name == "get_toast_messages":
        session = session_manager.get_session(args["session_id"])
        wait_ms = args.get("wait_ms", 0)
        custom_selector = args.get("selector")

        if wait_ms > 0:
            await asyncio.sleep(wait_ms / 1000)

        if custom_selector:
            toast_selectors = [custom_selector]
        else:
            toast_selectors = [
                '[role="alert"]', '[role="status"]',
                '[aria-live="polite"]', '[aria-live="assertive"]',
                '.toast', '.notification',
                '[data-sonner-toast]', '[data-radix-toast-announce]',
                '.Toastify__toast',
                '[class*="toast"]', '[class*="notification"]', '[class*="snackbar"]',
            ]

        messages = await session.page.evaluate("""(selectors) => {
            const seen = new Set();
            const results = [];
            for (const sel of selectors) {
                try {
                    const els = document.querySelectorAll(sel);
                    for (const el of els) {
                        const text = el.textContent.trim();
                        if (!text || seen.has(text)) continue;
                        seen.add(text);
                        const rect = el.getBoundingClientRect();
                        results.push({
                            text: text.substring(0, 500),
                            selector_matched: sel,
                            role: el.getAttribute('role') || null,
                            visible: rect.width > 0 && rect.height > 0,
                        });
                    }
                } catch(e) {}
            }
            return results;
        }""", toast_selectors)

        return {
            "count": len(messages),
            "messages": messages,
        }

    elif name == "select_option":
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

    elif name == "get_response_body":
        session = session_manager.get_session(args["session_id"])
        url_pattern = args["url_pattern"]
        method_filter = args.get("method")

        matching = [
            entry for entry in session.response_bodies
            if url_pattern in entry["url"]
            and (not method_filter or entry["method"].upper() == method_filter.upper())
        ]

        if not matching:
            return {
                "success": False,
                "error": f"No response bodies found matching '{url_pattern}'",
                "url_pattern": url_pattern,
                "total_captured": len(session.response_bodies),
            }

        # Return the last matching entry
        last = matching[-1]
        url = last["url"]
        return {
            "success": True,
            "url": url if len(url) <= 120 else "..." + url[-117:],
            "status": last["status"],
            "method": last["method"],
            "content_type": last["content_type"],
            "body_text": last["body_text"],
        }

    # ------------------------------------------------------------------
    # Web Search & Fetch
    # ------------------------------------------------------------------

    elif name == "web_search":
        from ddgs import DDGS
        query = args["query"]
        max_results = args.get("max_results", 10)
        results = DDGS().text(query, max_results=max_results)
        formatted = []
        for r in results:
            formatted.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            })
        return {
            "query": query,
            "results": formatted,
            "count": len(formatted),
        }

    elif name == "web_fetch":
        import httpx
        from bs4 import BeautifulSoup
        url = args["url"]
        max_length = args.get("max_length", 50000)
        raw_html = args.get("raw_html", False)
        verify_ssl = args.get("verify_ssl", True)
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0, verify=verify_ssl) as client:
            response = await client.get(url)
            response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""
        if raw_html:
            content = html[:max_length]
        else:
            for tag in soup(["script", "style", "img", "svg", "picture", "video", "audio", "canvas", "iframe", "source", "noscript"]):
                tag.decompose()
            content = soup.get_text(separator="\n", strip=True)[:max_length]
        return {
            "url": str(response.url),
            "title": title,
            "content": content,
            "length": len(content),
            "content_type": content_type,
        }

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    elif name == "describe_tools":
        category = args.get("category", "all")

        catalog = {
            "new": {
                "name": "New Tools (Latest Release)",
                "description": "8 new tools + 2 new interact_and_test actions added to reduce friction in interactive testing. Addresses: custom dropdowns, API response body inspection, overlay-blocked inputs, table parsing, toast capture, element waiting, HTML inspection, and scrolling.",
                "tools": {
                    "force_fill": {"params": "session_id, selector, value", "note": "NEW — Fill input bypassing actionability checks. Use when overlays/dialogs block normal fill."},
                    "select_option": {"params": "session_id, selector, value?, label?, index?", "note": "NEW — Native <select> or custom dropdown (Radix/shadcn combobox). Auto-detects type, clicks to open custom dropdowns."},
                    "get_table_data": {"params": "session_id, selector?, max_rows?", "note": "NEW — Parse HTML table into structured JSON {headers, rows[]}. No more concatenated text."},
                    "get_response_body": {"params": "session_id, url_pattern, method?", "note": "NEW — Get actual API response body text. Critical for diagnosing 400/500 errors."},
                    "get_toast_messages": {"params": "session_id, wait_ms?, selector?", "note": "NEW — Capture visible toast/notification messages (role=alert, Toastify, Sonner, Radix, etc.)"},
                    "wait_for_gone": {"params": "session_id, selector, timeout?", "note": "NEW — Wait for element to disappear (modal close, spinner gone). Returns elapsed_ms."},
                    "get_page_html": {"params": "session_id, selector?, max_length?", "note": "NEW — Get raw outerHTML of elements or full page HTML for component inspection."},
                    "scroll_into_view": {"params": "session_id, selector", "note": "NEW — Scroll element into viewport without clicking. Good for lazy-loaded content."},
                },
            },
            "project": {
                "name": "Project Management",
                "description": "Create and manage testing projects. Each project represents a website.",
                "tools": {
                    "create_project": {"params": "name, base_url, max_pages?, max_depth?", "note": "Start here — creates a project for a website"},
                    "list_projects": {"params": "(none)", "note": "See all projects"},
                    "get_project": {"params": "name", "note": "Project details and config"},
                    "delete_project": {"params": "name", "note": "Remove project and data"},
                },
            },
            "auth": {
                "name": "Authentication",
                "description": "Configure login for protected sites. Set credentials first, then call login_project.",
                "tools": {
                    "set_form_login": {"params": "project, login_url, username, password, selectors?", "note": "For sites with login forms"},
                    "set_basic_auth": {"params": "project, username, password", "note": "For HTTP Basic Auth"},
                    "set_cookies": {"params": "project, cookies[]", "note": "Bypass login with session cookies"},
                    "login_project": {"params": "project", "note": "Execute login using configured credentials"},
                    "copy_auth": {"params": "from_project, to_project", "note": "Copy auth config between projects on same domain"},
                },
            },
            "static_testing": {
                "name": "Static Testing",
                "description": "Crawl and test pages without interaction. Good for broad site audits.",
                "tools": {
                    "test_url": {"params": "url, project?, checks?[]", "note": "Test a single URL (screenshot + checks)"},
                    "crawl_project": {"params": "project, max_depth?, max_pages?", "note": "Discover all pages from base URL"},
                    "test_project": {"params": "project, checks?[], max_pages?", "note": "Full crawl + test all pages"},
                },
            },
            "results": {
                "name": "Results & Reports",
                "description": "Retrieve screenshots and test reports.",
                "tools": {
                    "get_screenshot": {"params": "project, url", "note": "Get screenshot path for a tested URL"},
                    "list_reports": {"params": "project?", "note": "List all test reports"},
                    "get_report": {"params": "report_path", "note": "Read a specific report"},
                },
            },
            "sessions": {
                "name": "Session Management",
                "description": "Persistent browser sessions that survive across tool calls. Required for interactive testing.",
                "tools": {
                    "open_session": {"params": "url, project?", "note": "Create session — returns session_id + screenshot"},
                    "close_session": {"params": "session_id", "note": "Close session and free resources"},
                    "list_sessions": {"params": "(none)", "note": "All active sessions with idle times"},
                    "set_viewport": {"params": "session_id, width?, height?, device?", "note": "Switch viewport. Presets: mobile_sm, mobile, mobile_lg, tablet, tablet_lg, laptop, desktop, desktop_lg"},
                },
            },
            "interactive": {
                "name": "Interactive Actions",
                "description": "Click, type, fill forms, and query elements on a session page.",
                "tools": {
                    "click_element": {"params": "session_id, selector, force?", "note": "Click and get screenshot. force=true bypasses overlays."},
                    "fill_form": {"params": "session_id, fields[{selector,value}], submit_selector?", "note": "Fill fields, optionally submit. Auto-handles date/time inputs for React compatibility."},
                    "interact_and_test": {"params": "url|session_id, steps[], run_checks?[]", "note": "Multi-step scripted workflow (25 actions incl. force_fill, select_option). fill/force_fill auto-handle date inputs."},
                    "force_fill": {"params": "session_id, selector, value", "note": "Fill input bypassing actionability checks (overlays, dialogs). Auto-handles date/time inputs for React compatibility."},
                    "select_option": {"params": "session_id, selector, value?, label?, index?", "note": "Native <select> or custom dropdown (Radix/shadcn)"},
                    "scroll_into_view": {"params": "session_id, selector", "note": "Scroll element into viewport without clicking"},
                    "get_page_elements": {"params": "selector, url|session_id, max_results?", "note": "List elements with attributes"},
                    "get_attribute": {"params": "selector, attributes[], url|session_id", "note": "Read specific HTML attributes"},
                    "extract_text": {"params": "selector, url|session_id", "note": "Get text content from elements"},
                },
            },
            "analysis": {
                "name": "Analysis & Validation",
                "description": "Deep checks on forms, links, responsiveness, screenshots, and timing.",
                "tools": {
                    "test_form_validation": {"params": "url|session_id, form_selector?", "note": "Submit empty forms, collect validation messages"},
                    "compare_screenshots": {"params": "screenshot1, screenshot2, threshold?", "note": "Pixel diff — returns % changed + diff image"},
                    "test_responsive": {"params": "url, viewports?[], run_checks?[]", "note": "Test at mobile/tablet/desktop viewports"},
                    "check_links": {"params": "url|session_id, check_external?, max_links?", "note": "Comprehensive link status checker"},
                    "measure_interaction": {"params": "session_id, selector, wait_for?", "note": "Measure click-to-result timing (ms)"},
                    "get_table_data": {"params": "session_id, selector?, max_rows?", "note": "Parse HTML table into structured JSON with headers"},
                    "get_toast_messages": {"params": "session_id, wait_ms?, selector?", "note": "Capture visible toast/notification messages"},
                },
            },
            "workflow": {
                "name": "Workflow Speed Tools",
                "description": "Quick actions to speed up testing workflows.",
                "tools": {
                    "screenshot_session": {"params": "session_id, full_page?", "note": "Quick screenshot, no actions"},
                    "run_checks_on_session": {"params": "session_id, checks?[]", "note": "Run checks on active session page"},
                    "go_back": {"params": "session_id", "note": "Browser back button"},
                    "go_forward": {"params": "session_id", "note": "Browser forward button"},
                    "handle_dialog": {"params": "session_id, action, prompt_text?", "note": "Accept/dismiss JS dialogs (call BEFORE triggering)"},
                    "upload_file": {"params": "session_id, selector, files[]", "note": "Set files on <input type=file>"},
                    "wait_for_network": {"params": "session_id, url_pattern, method?, timeout?", "note": "Wait for specific API request"},
                    "wait_for_gone": {"params": "session_id, selector, timeout?", "note": "Wait for element to disappear (modal/spinner close)"},
                    "get_page_html": {"params": "session_id, selector?, max_length?", "note": "Get raw outerHTML of elements or full page HTML"},
                },
            },
            "advanced": {
                "name": "Advanced Testing",
                "description": "Network mocking, storage manipulation, iframes, CSS inspection, device emulation.",
                "tools": {
                    "intercept_network": {"params": "session_id, url_pattern, status?, body?, content_type?, once?", "note": "Mock API responses"},
                    "clear_intercepts": {"params": "session_id, url_pattern?", "note": "Remove network mocks (all, or by pattern)"},
                    "get_local_storage": {"params": "session_id, storage?, keys?", "note": "Read localStorage or sessionStorage"},
                    "set_local_storage": {"params": "session_id, entries, storage?, clear_first?", "note": "Write to localStorage or sessionStorage"},
                    "select_iframe": {"params": "session_id, selector", "note": "Enter iframe — returns new session_id"},
                    "reload_page": {"params": "session_id", "note": "Refresh page"},
                    "get_computed_style": {"params": "session_id, selector, properties[]", "note": "Get rendered CSS values"},
                    "emulate_network": {"params": "session_id, preset", "note": "Throttle: slow_3g, fast_3g, offline, reset"},
                    "test_dark_mode": {"params": "session_id, mode", "note": "Toggle prefers-color-scheme dark/light"},
                },
            },
            "recording": {
                "name": "Recording & Console",
                "description": "Record video, audit keyboard navigation, capture console output.",
                "tools": {
                    "record_session": {"params": "url, steps[], project?", "note": "Record workflow as video (.webm)"},
                    "test_keyboard_navigation": {"params": "url|session_id, max_tabs?", "note": "Tab-order + focus indicator audit"},
                    "check_console_during_interaction": {"params": "session_id, steps[]", "note": "Console output captured during steps"},
                    "get_console_errors": {"params": "session_id, clear?", "note": "All console errors/logs since session opened"},
                },
            },
            "agent_speed": {
                "name": "AI Agent Speed Tools",
                "description": "Assertions, smart finders, auto-fill, network log, snapshots, cookies, contrast checks. Designed to replace multiple tool calls with one.",
                "tools": {
                    "assert_condition": {"params": "session_id, assertion, selector?, expected?, attribute?", "note": "Instant pass/fail: text_contains, text_equals, element_exists, element_visible, element_count, url_contains, title_contains, attribute_equals"},
                    "find_element": {"params": "session_id, text?, tag?, role?, near?", "note": "Smart finder — search by text, tag, role, or proximity"},
                    "auto_fill_form": {"params": "session_id, form_selector?, overrides?, submit?", "note": "Auto-detect fields, infer types, fill with test data. Date/time inputs filled with React-compatible events."},
                    "get_network_log": {"params": "session_id, url_filter?, clear?", "note": "All network requests (URL, status, method, type)"},
                    "snapshot_page_state": {"params": "session_id, name", "note": "Save URL + cookies + storage + DOM as checkpoint"},
                    "restore_page_state": {"params": "session_id, name", "note": "Restore a saved snapshot"},
                    "diff_page_state": {"params": "session_id, name", "note": "Compare current DOM vs snapshot"},
                    "get_cookies": {"params": "session_id, domain_filter?", "note": "Read all session cookies"},
                    "check_color_contrast": {"params": "session_id, selector?, level?, max_results?", "note": "WCAG AA/AAA contrast ratio checks"},
                    "get_response_body": {"params": "session_id, url_pattern, method?", "note": "Get actual API response body text (diagnose 400/500 errors)"},
                },
            },
            "web": {
                "name": "Web Search & Fetch",
                "description": "Search the internet and fetch page content.",
                "tools": {
                    "web_search": {"params": "query, max_results?", "note": "Search DuckDuckGo, returns titles + URLs + snippets"},
                    "web_fetch": {"params": "url, max_length?, raw_html?", "note": "Fetch URL and extract readable text content"},
                },
            },
        }

        # Filter by category
        if category != "all" and category in catalog:
            filtered = {category: catalog[category]}
        else:
            filtered = catalog

        # Build response
        result = {
            "total_tools": len(await list_tools()),
            "categories": len(catalog),
        }

        # Add workflow guide
        result["recommended_workflows"] = {
            "quick_static_audit": [
                "create_project(name, base_url)",
                "test_project(project) — crawl + test all pages",
                "list_reports(project) → get_report(path)",
            ],
            "interactive_testing": [
                "open_session(url) → session_id",
                "find_element(session_id, text='Login') → get selector",
                "click_element(session_id, selector)",
                "auto_fill_form(session_id, submit=true)",
                "assert_condition(session_id, 'url_contains', expected='/dashboard')",
                "close_session(session_id)",
            ],
            "regression_testing": [
                "open_session(url) → session_id",
                "snapshot_page_state(session_id, 'before')",
                "click_element / fill_form / etc.",
                "diff_page_state(session_id, 'before') → see what changed",
                "assert_condition(session_id, ...) → verify expected state",
            ],
            "responsive_testing": [
                "open_session(url) → session_id",
                "screenshot_session(session_id) — desktop",
                "set_viewport(session_id, device='mobile')",
                "screenshot_session(session_id) — mobile",
                "set_viewport(session_id, device='tablet')",
                "screenshot_session(session_id) — tablet",
            ],
            "api_mocking": [
                "open_session(url) → session_id",
                "intercept_network(session_id, '/api/data', status=500, body='{\"error\":\"fail\"}')",
                "click_element(session_id, '#load-btn') — triggers the mocked API",
                "assert_condition(session_id, 'element_visible', '.error-message')",
            ],
            "form_with_custom_dropdowns": [
                "open_session(url) → session_id",
                "force_fill(session_id, '#name', 'John') — fill even if overlay blocks",
                "select_option(session_id, '[role=combobox]', label='Option A') — custom dropdown",
                "click_element(session_id, '#submit')",
                "get_toast_messages(session_id, wait_ms=1000) — capture success/error toast",
                "get_response_body(session_id, '/api/submit') — see actual API response if error",
            ],
            "table_data_extraction": [
                "open_session(url) → session_id",
                "get_table_data(session_id, 'table.orders') — structured {headers, rows[]}",
                "assert_condition(session_id, 'element_count', 'tbody tr', expected='10')",
            ],
        }

        result["tips"] = [
            "Tools accepting 'url|session_id': pass session_id to reuse an open page, or url for ephemeral (one-shot) testing.",
            "Use find_element before click_element to discover the right selector.",
            "Use auto_fill_form instead of multiple fill_form calls — it infers field types.",
            "Use assert_condition instead of screenshots when you just need pass/fail.",
            "Use snapshot_page_state + diff_page_state to detect exactly what changed after an action.",
            "Use handle_dialog BEFORE the action that triggers the dialog.",
            "Network log is captured automatically — call get_network_log anytime to see API calls.",
            "force=true on click_element bypasses overlay interception (cookie banners, modals).",
            "Use force_fill instead of fill_form when overlays or dialogs block inputs.",
            "Use select_option for custom dropdowns (Radix, shadcn) — no more evaluate_js hacks.",
            "Use get_table_data to parse tables into {headers, rows[]} instead of extract_text.",
            "Use get_response_body after form submissions to see the actual 400/500 error body.",
            "Use get_toast_messages with wait_ms to capture toasts that animate in after actions.",
            "Use wait_for_gone to wait for modals/spinners to close before next action.",
            "force_fill and select_option are also available as interact_and_test step actions.",
            "Date/time inputs (date, time, datetime-local, month, week) are auto-handled in fill, force_fill, fill_form, and auto_fill_form — no evaluate_js needed.",
            "Use web_search to find documentation or examples, then web_fetch to read the full page content.",
        ]

        result["catalog"] = {}
        for cat_key, cat_data in filtered.items():
            result["catalog"][cat_key] = {
                "name": cat_data["name"],
                "description": cat_data["description"],
                "tool_count": len(cat_data["tools"]),
                "tools": cat_data["tools"],
            }

        return result

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
