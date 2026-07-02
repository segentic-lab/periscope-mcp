"""MCP tool definitions (schemas only — handlers live in handlers/)."""
from mcp.types import Tool

TOOLS: list[Tool] = [
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
                        "description": "List of cookies with name, value, domain (and optionally path, defaults to '/'). Playwright requires a domain+path pair to inject them.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "value": {"type": "string"},
                                "domain": {"type": "string"},
                                "path": {"type": "string", "description": "Cookie path (default: '/')"}
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
            description="Test a single URL. Takes screenshot and runs checks for visual issues, accessibility, functionality, SEO, performance, and GEO (AI/agentic search readiness: robots.txt AI-crawler access, llms.txt, WebMCP, JSON-LD).",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to test"},
                    "project": {"type": "string", "description": "Project name (optional, uses 'default' if not specified)"},
                    "checks": {
                        "type": ["array", "string"],
                        "description": "Types of checks to run (visual, accessibility, functionality, seo, performance, geo). Default: all",
                        "items": {"type": "string", "enum": ["visual", "accessibility", "functionality", "seo", "performance", "geo"]}
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
                        "items": {"type": "string", "enum": ["visual", "accessibility", "functionality", "seo", "performance", "geo"]}
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
            description="Fill form fields in a session page and optionally submit. Use force=true to bypass actionability checks when overlays or dialogs block the inputs.",
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
                    "submit_selector": {"type": "string", "description": "CSS selector for submit button (optional)"},
                    "force": {"type": ["boolean", "string"], "description": "Bypass actionability checks — fill even when overlays/dialogs block the inputs (default: false)"}
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
                                "timeout": {"type": "integer", "description": "Timeout in ms (for wait — default 1000; wait_for — default 10000; wait_for_text, wait_for_network — default 30000)"},
                                "state": {"type": "string", "description": "State to wait for (for wait_for: visible, hidden, attached, detached)"},
                                "label": {"type": "string", "description": "Label for screenshot filename (screenshot action), or option label text (select_option action)"},
                                "force": {"type": ["boolean", "string"], "description": "Bypass actionability checks on click (default: false)"},
                                "script": {"type": "string", "description": "JavaScript to evaluate (for evaluate_js)"},
                                "direction": {"type": "string", "enum": ["up", "down", "left", "right"], "description": "Scroll direction (for scroll_within)"},
                                "amount": {"type": "integer", "description": "Scroll amount in pixels (for scroll_within, default: 300)"},
                                "files": {"type": "array", "items": {"type": "string"}, "description": "File paths (for upload_file)"},
                                "url_pattern": {"type": "string", "description": "URL substring to match (for wait_for_network)"},
                                "method": {"type": "string", "description": "For wait_for_network: HTTP method filter (e.g. 'POST'). For drag: 'auto' (default, Playwright drag_to) or 'mouse' (stepped manual drag — use when auto had no effect, e.g. @hello-pangea/dnd-style libraries)"},
                                "index": {"type": "integer", "description": "Option index (for select_option)"}
                            },
                            "required": ["action"]
                        }
                    },
                    "project": {"type": "string", "description": "Project name (optional)"},
                    "run_checks": {
                        "type": ["array", "string"],
                        "description": "Checks to run after steps complete (visual, accessibility, functionality, seo, performance, geo)",
                        "items": {"type": "string", "enum": ["visual", "accessibility", "functionality", "seo", "performance", "geo"]}
                    },
                    "screenshot_after": {"type": "boolean", "description": "Take a screenshot after all steps complete (default: true)"},
                    "continue_on_error": {"type": "boolean", "description": "Continue executing steps even if one fails (default: false)"},
                    "capture_console": {"type": ["boolean", "string"], "description": "Capture console output/errors emitted during the steps and include them in the result (default: false)"}
                },
                "required": ["steps"]
            }
        ),
        Tool(
            name="get_page_elements",
            description="List elements matching a CSS selector with their attributes (tag, text, id, class, href, value, visible, enabled, aria_label, role). Pass 'attributes' for extra HTML attributes (data-*, aria-*, style, ...) and 'full_text' for complete text content instead of the 80-char preview. Works on a session or a URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector to match elements"},
                    "session_id": {"type": "string", "description": "Session ID (use this or url)"},
                    "url": {"type": "string", "description": "URL to open (use this or session_id)"},
                    "project": {"type": "string", "description": "Project name (optional)"},
                    "max_results": {"type": "integer", "description": "Max elements to return (default: 50)"},
                    "attributes": {
                        "type": ["array", "string"],
                        "description": "Extra HTML attribute values to include per element (e.g. data-testid, aria-expanded, style)",
                        "items": {"type": "string"}
                    },
                    "full_text": {"type": ["boolean", "string"], "description": "Return full text content instead of an 80-char preview (default: false)"}
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
                        "items": {"type": "string", "enum": ["visual", "accessibility", "functionality", "seo", "performance", "geo"]}
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
                                "timeout": {"type": "integer", "description": "Timeout in ms (for wait — default 1000; wait_for — default 10000; wait_for_text, wait_for_network — default 30000)"},
                                "state": {"type": "string", "description": "State to wait for (visible, hidden, attached, detached)"},
                                "label": {"type": "string", "description": "Label for screenshot"},
                                "force": {"type": ["boolean", "string"], "description": "Bypass actionability checks"},
                                "script": {"type": "string", "description": "JavaScript to evaluate"},
                                "direction": {"type": "string", "enum": ["up", "down", "left", "right"], "description": "Scroll direction"},
                                "amount": {"type": "integer", "description": "Scroll amount in pixels"},
                                "files": {"type": "array", "items": {"type": "string"}, "description": "File paths (for upload_file)"},
                                "url_pattern": {"type": "string", "description": "URL pattern (for wait_for_network)"},
                                "method": {"type": "string", "description": "For wait_for_network: HTTP method filter (e.g. 'POST'). For drag: 'auto' (default, Playwright drag_to) or 'mouse' (stepped manual drag — use when auto had no effect, e.g. @hello-pangea/dnd-style libraries)"},
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
            name="navigate_session",
            description="Browser history navigation on a session: go back, go forward, or reload the page. Returns new URL/title + screenshot. Reload is useful for testing state persistence.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "action": {"type": "string", "enum": ["back", "forward", "reload"], "description": "History action to perform"}
                },
                "required": ["session_id", "action"]
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
                        "items": {"type": "string", "enum": ["visual", "accessibility", "functionality", "seo", "performance", "geo"]}
                    }
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
            name="page_state",
            description="Named page-state checkpoints. action=snapshot saves URL + cookies + storage + DOM signature under a name; action=restore navigates back to it and restores cookies/storage; action=diff compares the current DOM against the snapshot (added/removed/changed elements + tag count changes). Enables testing multiple paths from the same starting point.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "action": {"type": "string", "enum": ["snapshot", "restore", "diff"], "description": "snapshot = save, restore = return to it, diff = compare current DOM vs it"},
                    "name": {"type": "string", "description": "Checkpoint name"}
                },
                "required": ["session_id", "action", "name"]
            }
        ),
        Tool(
            name="run_lighthouse",
            description="Run a real Google Lighthouse audit against a URL. Returns 0-100 category scores, Core Web Vitals lab metrics (LCP, TBT, CLS, Speed Index), and the failed audits, and saves the full JSON report. Requires Node.js — finds it on PATH or auto-detects nvm installs (~/.nvm); if none exists, returns the exact nvm install commands. Launches its own headless Chrome: no session or project auth state applies.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to audit"},
                    "categories": {
                        "type": ["array", "string"],
                        "description": "Categories to audit (default: all four)",
                        "items": {"type": "string", "enum": ["performance", "accessibility", "best-practices", "seo"]}
                    },
                    "device": {"type": "string", "enum": ["mobile", "desktop"], "description": "Emulation preset (default: mobile, like Lighthouse's default)"},
                    "timeout": {"type": "integer", "description": "Max seconds to wait (default: 180)"}
                },
                "required": ["url"]
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
