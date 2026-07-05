"""MCP tool definitions (schemas only — handlers live in handlers/)."""
from mcp.types import Tool

TOOLS: list[Tool] = [
        # Project Management
        Tool(
            name="create_project",
            description="Create a persistent testing project: a named website/web-app target with its base URL and crawl limits, saved to disk and reused by crawl_project, test_project, and authenticated sessions. Returns the stored project config. Create this first, then attach auth (set_form_login / set_basic_auth / set_cookies) and run tests.",
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
            description="List all saved testing projects with their base URL, crawl limits, and configured auth type. Returns an array of project configs (empty if none exist). Use it to discover the project names the other project/auth/testing tools expect.",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="get_project",
            description="Get one project's saved configuration: base URL, max_pages/max_depth, screenshot directory, and which auth (form/basic/cookies) is set up. Returns {success, project}. Use it to confirm setup before crawling, testing, or logging in.",
            inputSchema={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Project name"}},
                "required": ["name"]
            }
        ),
        Tool(
            name="delete_project",
            description="Permanently delete a project and its saved configuration and auth. Returns {success}. Irreversible; afterwards the name is free to reuse. Does not remove screenshots/reports already written to disk.",
            inputSchema={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Project name"}},
                "required": ["name"]
            }
        ),

        # Authentication
        Tool(
            name="set_form_login",
            description="Configure username/password form login for a project (stored, not executed yet). For standard HTML login forms; field/submit selectors are auto-detected but can be overridden. Returns {success}. Call login_project afterwards to actually log in. For 2FA/SSO/CAPTCHA use interactive_login instead.",
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
            description="Configure HTTP Basic Auth credentials for a project — the browser sends them on every request in that project's context. Stored, not executed: call login_project to apply, then pass `project` to your sessions. Returns {success}. Use for browser Basic-Auth prompts, not HTML login forms (use set_form_login for those).",
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
            description="Seed a project with session cookies to skip an interactive login (e.g. cookies copied from a logged-in browser). Each cookie needs name+value+domain (path defaults to '/'). Stored, not executed: call login_project to inject them. Returns {success}.",
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
            description="Execute a project's configured login — submit the form, apply Basic Auth, or inject cookies — and persist the resulting authenticated session (storage_state) for reuse. Requires set_form_login / set_basic_auth / set_cookies first. Returns {success} with login details. Re-run it when auth expires mid-test.",
            inputSchema={
                "type": "object",
                "properties": {"project": {"type": "string", "description": "Project name"}},
                "required": ["project"]
            }
        ),
        Tool(
            name="interactive_login",
            description="Open a VISIBLE browser window for a human to log in by hand — the way to authenticate flows that can't be automated (2FA/MFA, SSO/OAuth redirects, CAPTCHA, magic links, device confirmation). After you finish logging in, call save_login to capture the session; future headless sessions on the project reuse it. Requires a display on the server (DISPLAY set).",
            inputSchema={
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project name (must exist)"},
                    "login_url": {"type": "string", "description": "URL to open (optional; defaults to the project's configured login URL or base_url)"}
                },
                "required": ["project"]
            }
        ),
        Tool(
            name="save_login",
            description="Capture the authenticated session (cookies + localStorage) from an in-progress interactive_login, save it to the project, and close the visible window. The project then opens authenticated sessions headlessly. Re-run interactive_login when the session expires.",
            inputSchema={
                "type": "object",
                "properties": {"project": {"type": "string", "description": "Project name with an interactive_login in progress"}},
                "required": ["project"]
            }
        ),

        # Testing
        Tool(
            name="test_url",
            description="Screenshot and audit a single URL in one shot (opens then closes a throwaway page). Runs the selected checks — visual, accessibility, functionality, seo, performance, geo — and returns {status, title, screenshot path, issues[]} where each issue has type/severity/message; never-idle pages come back flagged (wait_downgraded), not as errors. Pass `project` for authenticated pages. For multi-step flows or repeated checks on one page, use a session instead.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to test"},
                    "project": {"type": "string", "description": "Project name (optional). With a project: runs in its shared, authenticated context. Without: runs in an isolated context (no shared cookies/login)."},
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
            description="Discover a project's pages by breadth-first crawling internal links from its base URL, bounded by max_pages/max_depth (overridable per call). Returns the list of discovered URLs (also cached for test_project). Runs in the project's authenticated context. Discovery only — use test_project to crawl and audit together.",
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
            description="Full-site audit: crawl every page (up to max_pages) and run the selected checks on each, saving a timestamped JSON report. Returns per-page issues plus site-wide findings (e.g. duplicate titles/descriptions) and an auth_check; pages that bounce to the login page come back as auth_lost, never as fake success. Reload the saved report with get_report.",
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
            description="Get the saved screenshot file path for a URL previously tested in a project. Returns {success, url, screenshot_path}. Locates the PNG on disk after test_url/test_project — it does not capture a new image (use screenshot_session for that).",
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
            description="List saved test reports (the JSON files test_project writes), for one project or all projects. Returns each report's path and timestamp, newest first. Pass a path to get_report to read one.",
            inputSchema={
                "type": "object",
                "properties": {"project": {"type": "string", "description": "Project name (optional, lists all if not specified)"}}
            }
        ),
        Tool(
            name="get_report",
            description="Load a saved test report by file path and return its full contents — per-page issues, site-wide findings, and run metadata. Returns {success, report}. Get valid paths from list_reports.",
            inputSchema={
                "type": "object",
                "properties": {
                    "report_path": {"type": "string", "description": "Path to the report file"}
                },
                "required": ["report_path"]
            }
        ),

        Tool(
            name="session_report",
            description="Generate a human-readable dossier of EVERYTHING done this server run — every tool call in chronological order with arguments (secrets redacted), pass/fail verdicts, timings, error messages, and embedded screenshot thumbnails — as a self-contained HTML file plus a PDF. Made for handing to your user to review the whole session; add your findings via 'notes' so the report opens with your summary. The journal records automatically from server start; clear=true resets it after reporting (e.g. between test rounds).",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Report title (default: 'Periscope session report')"},
                    "notes": {"type": "string", "description": "Your summary/findings narrative — rendered as an 'Agent notes' panel at the top"},
                    "include_screenshots": {"type": ["boolean", "string"], "description": "Embed screenshot thumbnails (default: true; originals are always linked)"},
                    "pdf": {"type": ["boolean", "string"], "description": "Also render a PDF via headless Chromium (default: true)"},
                    "clear": {"type": "boolean", "description": "Reset the journal after generating (default: false)"}
                },
                "required": []
            }
        ),

        # ==================== Interactive Testing ====================

        # Session Management
        Tool(
            name="open_session",
            description="Open a persistent browser session and return {session_id, url, title, screenshot}. The page stays alive across tool calls so you can explore, click, fill, debug, and accumulate console/network logs — the main workflow for anything multi-step. Pass `project` to share its authenticated context; headed=true opens a visible window. Sessions expire after idle timeout, so close_session when done.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to open"},
                    "project": {"type": "string", "description": "Project name (optional). With a project: runs in its shared, authenticated context. Without: runs in an isolated context (no shared cookies/login)."},
                    "headed": {"type": ["boolean", "string"], "description": "Open a VISIBLE browser window instead of headless (default: false). Requires a display on the server. Use when you want to watch or hand-drive the session."}
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="close_session",
            description="Close a browser session and free its resources (page, context, captured logs). Returns {success}. Call it when finished; using a closed or expired id returns a 'session not found' error that explains why (idle-expired, evicted, or crashed).",
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
            description="List active browser sessions with their session_id, current URL, and idle time. Returns an array (empty if none open). Use it to recover a session id or spot sessions nearing the idle-timeout or the concurrency cap.",
            inputSchema={"type": "object", "properties": {}}
        ),

        # Interactive Tools
        Tool(
            name="click_element",
            description="Click an element in a session page. Returns a screenshot and the new URL/title after click. If a full-screen portal overlay (Radix/shadcn dialogs & menus) intercepts the pointer, automatically falls back to an element-level JS click and flags click_method='js_dispatch' — no workaround needed. Use force=true to bypass actionability checks for other cases (hidden/animating elements).",
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
                                "url_pattern": {"type": "string", "description": "Required for wait_for_network: plain substring of the request URL (not a regex)"},
                                "method": {"type": "string", "description": "For wait_for_network: HTTP method filter (e.g. 'POST'). For drag: 'auto' (default, Playwright drag_to) or 'mouse' (stepped manual drag — use when auto had no effect, e.g. @hello-pangea/dnd-style libraries)"},
                                "index": {"type": "integer", "description": "Option index (for select_option)"},
                                "element_index": {"type": "integer", "description": "Which match of 'selector' to target, 0-based (for select_option; default: 0)"}
                            },
                            "required": ["action"]
                        }
                    },
                    "project": {"type": "string", "description": "Project name (optional). With a project: runs in its shared, authenticated context. Without: runs in an isolated context (no shared cookies/login)."},
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
            description="List elements matching a CSS selector with their attributes (tag, text, id, class, href, value, visible, enabled, aria_label, role). Pass 'attributes' for extra HTML attributes (data-*, aria-*, style, ...) and 'full_text' for complete text content instead of the 80-char preview. Works on a session or a URL. Standard CSS selectors only — Playwright-specific pseudo-classes (:has-text, :visible) are not supported here.",
            inputSchema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector to match elements"},
                    "session_id": {"type": "string", "description": "Session ID (use this or url)"},
                    "url": {"type": "string", "description": "URL to open (use this or session_id)"},
                    "project": {"type": "string", "description": "Project name (optional). With a project: runs in its shared, authenticated context. Without: runs in an isolated context (no shared cookies/login)."},
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
            description="Audit a page's form validation: locate forms, list their required fields, and collect messages from :invalid fields and custom error elements. Returns the per-form field/validation details. Use to verify client-side validation behaves as intended. Works on a session or a URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to test (use this or session_id)"},
                    "session_id": {"type": "string", "description": "Session ID (use this or url)"},
                    "project": {"type": "string", "description": "Project name (optional). With a project: runs in its shared, authenticated context. Without: runs in an isolated context (no shared cookies/login)."},
                    "form_selector": {"type": "string", "description": "CSS selector to target specific form(s) (default: 'form')"}
                }
            }
        ),
        Tool(
            name="compare_screenshots",
            description="Pixel-diff two screenshot files. Returns the percentage of differing pixels and writes a diff image highlighting the changed regions (path in the result). Use for visual-regression checks — capture with test_url/screenshot_session, then compare. `threshold` sets per-channel color tolerance.",
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
            name="visual_check",
            description="Named visual-regression baselines — no screenshot-path bookkeeping. action='set' captures the session page (or one element via selector) as the baseline for 'name'; action='check' captures again and returns a hard verdict: passed (diff_percentage vs max_diff_percent, default 0.5%), plus a diff image with changed pixels highlighted. Baselines are stored per project+name. If a check fails on an intended change, re-baseline with action='set'. Prefer selector-scoped baselines for components — full pages flake more (animations, dynamic content).",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "name": {"type": "string", "description": "Baseline name, e.g. 'dashboard-desktop' (letters, digits, . _ -)"},
                    "action": {"type": "string", "enum": ["set", "check"], "description": "set = capture/replace the baseline; check = compare current state against it (default: check)"},
                    "selector": {"type": "string", "description": "Scope the baseline to one element (recommended for components)"},
                    "full_page": {"type": "boolean", "description": "Full scrollable page vs viewport when no selector (default: true)"},
                    "max_diff_percent": {"type": "number", "description": "Max % of differing pixels to still pass (default: 0.5)"},
                    "threshold": {"type": "number", "description": "Per-channel color tolerance 0-255 before a pixel counts as different (default: 10)"}
                },
                "required": ["session_id", "name"]
            }
        ),
        Tool(
            name="test_responsive",
            description="Load a URL at several viewport sizes (default mobile 375x812, tablet 768x1024, desktop 1920x1080) and screenshot each, optionally running checks per size. Returns each viewport's screenshot path and any issues. Catches layout breakage across breakpoints in one call. Pass custom viewports as [{name,width,height}].",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to test"},
                    "project": {"type": "string", "description": "Project name (optional). With a project: runs in its shared, authenticated context. Without: runs in an isolated context (no shared cookies/login)."},
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
            description="Crawl all links on a page and report each one's URL, status code, and OK/broken result — catching 404s and dead anchors. External links are skipped unless check_external=true. Returns the per-link results plus a broken-link summary. Works on a session or a URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to check (use this or session_id)"},
                    "session_id": {"type": "string", "description": "Session ID (use this or url)"},
                    "project": {"type": "string", "description": "Project name (optional). With a project: runs in its shared, authenticated context. Without: runs in an isolated context (no shared cookies/login)."},
                    "check_external": {"type": "boolean", "description": "Also check external links (default: false)"},
                    "max_links": {"type": "integer", "description": "Max links to check (default: 100)"}
                }
            }
        ),
        Tool(
            name="measure_interaction",
            description="Click an element and measure how long until the result settles. Returns elapsed_ms, a 'measures' note stating exactly what was timed, and the click's real interaction_to_next_paint_ms when measurable. Three modes: wait_for_network (URL substring) measures until that response completes — use this for buttons whose handler fires a request asynchronously, where plain network-idle settles early and under-measures; wait_for (selector) measures until it appears; default measures to the first network-idle window.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "selector": {"type": "string", "description": "CSS selector of element to click"},
                    "wait_for": {"type": "string", "description": "CSS selector to wait for (optional)"},
                    "wait_for_network": {"type": "string", "description": "URL substring — measure until the matching response completes (armed before the click, so fast responses aren't missed). Plain substring, not a regex. Prefer this for async submit/save buttons."}
                },
                "required": ["session_id", "selector"]
            }
        ),

        # Phase 3: Nice-to-Have
        Tool(
            name="record_session",
            description="Run a sequence of steps while recording a video of the browser (Playwright video capture). Returns the saved .webm file path. Steps use the same format as interact_and_test. Use it to produce a visual artifact or repro of a workflow; for assertions/checks use interact_and_test instead.",
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
                                "url_pattern": {"type": "string", "description": "Required for wait_for_network: plain substring of the request URL (not a regex)"},
                                "method": {"type": "string", "description": "For wait_for_network: HTTP method filter (e.g. 'POST'). For drag: 'auto' (default, Playwright drag_to) or 'mouse' (stepped manual drag — use when auto had no effect, e.g. @hello-pangea/dnd-style libraries)"},
                                "index": {"type": "integer", "description": "Option index (for select_option)"},
                                "element_index": {"type": "integer", "description": "Which match of 'selector' to target, 0-based (for select_option; default: 0)"}
                            },
                            "required": ["action"]
                        }
                    },
                    "project": {"type": "string", "description": "Project name (optional). With a project: runs in its shared, authenticated context. Without: runs in an isolated context (no shared cookies/login)."}
                },
                "required": ["url", "steps"]
            }
        ),
        Tool(
            name="test_keyboard_navigation",
            description="Tab through a page from the top and record the focus order, flagging any stop with no visible focus indicator. Returns total_tab_stops, the focus_order sequence, and issues[]. Accessibility audit for keyboard operability. Works on a session or a URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to test (use this or session_id)"},
                    "session_id": {"type": "string", "description": "Session ID (use this or url)"},
                    "project": {"type": "string", "description": "Project name (optional). With a project: runs in its shared, authenticated context. Without: runs in an isolated context (no shared cookies/login)."},
                    "max_tabs": {"type": "integer", "description": "Max Tab presses (default: 50)"}
                }
            }
        ),
        Tool(
            name="get_console_errors",
            description="Return browser console output (errors, warnings, logs) captured passively on a session since it opened or since the last read; clears the buffer by default. Returns the buffered entries. First stop when debugging a broken page — no steps required.",
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
            description="Copy auth configuration and, when possible, the live login session (cookies + localStorage via storage_state) from one project to another on the same domain. Returns {success, session_copied}; session_copied is false when only the config/cookies could transfer. Use to reuse a login across related projects.",
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
            description="Resize a session's viewport to a device preset or custom width/height, then screenshot. Returns the new size and screenshot. Persists for later actions in the session — use this to test responsive layouts inside an ongoing session (unlike test_responsive, which opens throwaway pages).",
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
            description="Screenshot the session's current page as-is — no actions performed. Returns the image path (full-page by default; full_page=false captures just the viewport). Use to grab state at a point in a workflow; interactive tools already return screenshots, so don't call this after every step.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "full_page": {"type": "boolean", "description": "Capture full scrollable page (default: true)"},
                    "selector": {"type": "string", "description": "Clip to one element: screenshot just the first match (for citing evidence). Overrides full_page."}
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="select_page",
            description="Adopt a popup or new tab this session opened (window.open, target=_blank, OAuth/payment windows) as a NEW session id you can drive with every normal tool — clicks, assertions, logs. Console/network recording attaches the instant the driver sees the popup open, so early traffic is captured (requests firing in the popup's first milliseconds can precede any driver's visibility — a browser-automation limit, not a periscope one). Returns {session_id, url, title}; with several popups open, call without index to list them first. The parent session keeps working for the original tab.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Root session that opened the popup"},
                    "index": {"type": "integer", "description": "Which open popup to adopt, 0-based (omit when only one is open, or to list them)"}
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="navigate_session",
            description="Browser history/reload on a session: back, forward, or reload. Returns the new URL/title and a screenshot. Reload tests state persistence and caching; back/forward exercise SPA history.",
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
            description="Run the audit checks (visual/accessibility/functionality/seo/performance/geo) against a session's CURRENT page — after your interactions, without opening a new page (unlike test_url). Returns the same {issues[], per-check results} structure as test_url. Use to audit a state you reached by clicking/filling.",
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
            description="Arm a one-shot handler for the NEXT JavaScript dialog (alert/confirm/prompt) on a session — accept or dismiss, with optional prompt text. Returns {success}. Must be called BEFORE the action that triggers the dialog, otherwise the dialog blocks the page and times out.",
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
            description="Set file(s) on an <input type='file'> element by path, without the OS file picker. Returns {success}. Provide absolute paths that exist on the server. For a picker opened by a button, target the underlying file input's selector.",
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
            name="flow",
            description="Save and re-run named step sequences — define a workflow once (login, checkout, smoke path), replay it in any session. action='save' stores steps (interact_and_test's exact format, all 25 actions); action='run' executes a saved flow on a session via the same engine as interact_and_test; action='list' shows saved flows; action='delete' removes one. Deliberately minimal: verify outcomes by following a run with assert_all or visual_check. Flows persist in data/flows/ across sessions and server restarts.",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["save", "run", "list", "delete"], "description": "What to do (default: list)"},
                    "name": {"type": "string", "description": "Flow name, e.g. 'login' (letters, digits, . _ -). Required except for list."},
                    "steps": {
                        "type": ["array", "string"],
                        "description": "For save: steps in interact_and_test's format",
                        "items": {"type": "object", "properties": {"action": {"type": "string"}}, "required": ["action"]}
                    },
                    "description": {"type": "string", "description": "For save: optional human note about what the flow does"},
                    "session_id": {"type": "string", "description": "For run: session to execute on"},
                    "continue_on_error": {"type": "boolean", "description": "For run: keep executing after a failed step (default: false)"}
                },
                "required": []
            }
        ),
        Tool(
            name="wait_for_network",
            description="Block until a network request whose URL contains the given substring completes (optionally filtered by HTTP method), up to timeout. url_pattern is required and is a plain substring match against the full URL including query string — not a regex or glob. Returns the matched request's URL/status/method, or times out. To catch a request fired by a click, run the click and this as consecutive steps in one interact_and_test call; after the fact, read get_response_body/get_network_log instead.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "url_pattern": {"type": "string", "description": "Required. Plain substring of the full request URL incl. query string (e.g. '/api/tasks', 'graphql') — not a regex; anchors ($) and wildcards (.*) never match."},
                    "method": {"type": "string", "description": "HTTP method filter (optional, e.g. 'POST', 'GET')"},
                    "timeout": {"type": "integer", "description": "Max wait time in ms (default: 30000)"}
                },
                "required": ["session_id", "url_pattern"]
            }
        ),

        # Advanced Testing Tools
        Tool(
            name="intercept_network",
            description="Mock matching API responses on a session — return a custom status/body/content-type for requests whose URL contains a substring. Returns {success}. Use it to force error, empty, or loading states without a real backend; call BEFORE the triggering action, and clear_intercepts to remove. once=true intercepts only the first match.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "url_pattern": {"type": "string", "description": "Plain substring of the full URL to match (e.g. '/api/tasks', 'graphql') — not a regex or glob."},
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
            description="Remove network mocks created by intercept_network — all of them, or only those registered with a given URL pattern. Returns {success}. Use to restore real backend responses after testing mocked states.",
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
            description="Read a session page's localStorage (or sessionStorage) — all entries, or specific keys. Returns the key/value pairs as an object. Use to inspect client-side state (tokens, flags, cached data) when debugging.",
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
            description="Write key/value entries to a session page's localStorage (or sessionStorage), optionally clearing existing entries first. Returns {success}. Use to seed client state (feature flags, tokens, cached data) to reproduce a specific app state; reload if the app reads storage only at load time.",
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
            name="download_file",
            description="Click a trigger and capture the file it downloads — the honest way to verify exports (CSV, PDF, invoices). The download waiter is armed BEFORE the click so fast downloads aren't missed, and the click uses the same overlay-fallback as click_element (export buttons inside Radix menus work). Returns the saved path, size, sha256, source URL, and for small text files a text_head preview so content can be asserted without another call. Files land in data/downloads/.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "selector": {"type": "string", "description": "CSS selector of the element whose click starts the download"},
                    "timeout": {"type": "integer", "description": "Max ms to wait for the download to start (default: 30000)"}
                },
                "required": ["session_id", "selector"]
            }
        ),
        Tool(
            name="select_iframe",
            description="Switch into an iframe and return a NEW session id scoped to that frame's content — use it like a normal session for elements inside the iframe, and keep the parent id for page-level actions. Close the returned session when done. Needed because cross-frame content isn't reachable through the parent session's selectors.",
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
            description="Read the actual rendered CSS values (after stylesheets and inheritance) for the requested properties on matching elements. Returns per-element property→value maps. Use to verify colors, fonts, spacing, display, or opacity programmatically instead of eyeballing a screenshot.",
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
            description="Throttle a session's network to a preset — slow_3g, fast_3g, offline, or reset. Returns {success}. Persists across navigations until reset. Use to test loading spinners, skeleton states, offline fallbacks, and timeout handling.",
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
            description="Emulate prefers-color-scheme (dark or light) on a session and screenshot the result. Returns the screenshot. Use to verify a site's dark/light theming without touching OS settings; the emulation persists for later actions in the session.",
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
            description="Assert a condition on the current page and get a hard pass/fail plus the actual value — no screenshot to interpret. Supports text_contains, text_equals, element_exists, element_visible, element_count, url_contains, title_contains, attribute_equals. Returns {passed, actual, expected}. The verification primitive — prefer it over screenshot-squinting.",
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
            name="assert_all",
            description="Batch assertions: evaluate MANY conditions in one call and get every verdict — no early abort, so the response is the complete pass/fail picture (overall passed, failed_count, per-assertion results with actual values). Each item takes the same fields as assert_condition. Prefer this over sequential assert_condition calls when verifying a state with 2+ expectations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "assertions": {
                        "type": ["array", "string"],
                        "description": "Assertions to evaluate — each an object like assert_condition's arguments",
                        "items": {
                            "type": "object",
                            "properties": {
                                "assertion": {"type": "string", "enum": ["text_contains", "text_equals", "element_exists", "element_visible", "element_count", "url_contains", "title_contains", "attribute_equals"], "description": "Type of assertion"},
                                "selector": {"type": "string", "description": "CSS selector (element-based assertions)"},
                                "expected": {"type": "string", "description": "Expected value"},
                                "attribute": {"type": "string", "description": "Attribute name (attribute_equals)"}
                            },
                            "required": ["assertion"]
                        }
                    }
                },
                "required": ["session_id", "assertions"]
            }
        ),
        Tool(
            name="get_page_map",
            description="Semantic page map in ONE call: every interactive element (links, buttons, inputs, custom controls) plus landmarks and headings, in document order — each with its ARIA role, accessible name, live state (disabled/checked/expanded/value), and a ready-to-use CSS selector. The fastest way to answer 'what can I do on this page?' — use it to orient before clicking instead of multiple get_page_elements calls. Interactive elements with no accessible name are flagged unnamed (an accessibility finding in itself). Output is compact: only truthy state fields, capped at max_nodes with an explicit truncated flag.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "max_nodes": {"type": "integer", "description": "Max nodes to return (default: 150); 'total' reports how many exist"},
                    "include_hidden": {"type": ["boolean", "string"], "description": "Include invisible elements, flagged hidden (default: false)"}
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="find_element",
            description="Find elements by text content, tag, ARIA role, and/or proximity to another element, ranked by match quality. Returns {found, elements} with the best CSS selector for each. Use it to get a reliable selector from what you can see (e.g. a button's text) instead of guessing.",
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
            description="Detect a form's fields, infer each type (email/phone/name/address/date…), fill realistic test data, and optionally submit — one call replacing 5-10. Returns which fields were filled and with what. Use overrides={selector: value} for specific values and submit=true to submit.",
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
            description="Return the network requests captured on a session — each with URL, HTTP method, status, resource type, and size. Optionally filter by URL substring; clear=true empties the log after reading. Returns the request list. Use to see which API calls fired and their status when debugging.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "url_filter": {"type": "string", "description": "Optional plain-substring filter against the full URL incl. query string (e.g. '/api/') — not a regex or glob."},
                    "clear": {"type": "boolean", "description": "Clear the log after reading (default: false)"}
                },
                "required": ["session_id"]
            }
        ),
        Tool(
            name="get_cookies",
            description="Read all cookies from a session's browser context (optionally filtered by domain). Returns {cookies, total} with each cookie's name/value/domain/path/flags. Essential for debugging auth/session issues — confirm the expected session cookie is present and scoped correctly.",
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
            name="get_interaction_log",
            description="Export the real INP (Interaction to Next Paint) time series for a session — one record per interaction Periscope drove (click/typing), each with its input-to-next-paint latency, event type, target, timestamp, and URL. Saves a JSON (for graphing) or CSV file and returns percentile stats (p50/p75/p90/p98/worst). Use after driving interactions (interact_and_test, click_element, fill_form…) — ideal for a long interactive test where you want to see all INP times, not just the worst. Unlike Lighthouse (which can't measure INP in lab mode and falls back to TBT), this is measured from actual Event Timing entries.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "format": {"type": "string", "enum": ["json", "csv"], "description": "Export format (default: json). JSON is easiest to graph; CSV for spreadsheets."},
                    "clear": {"type": ["boolean", "string"], "description": "Reset the recorded interactions after exporting (default: false)"}
                },
                "required": ["session_id"]
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
            description="Check WCAG color contrast ratios for text elements on the page. Samples one element per unique text style (color/background/size), so repeated nav items don't exhaust the budget — 'checked' counts style groups, 'elements_represented' the elements they cover. Reports failures against AA or AAA thresholds.",
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
            description="Scroll an element into the viewport without clicking it. Returns {success}. Use to trigger lazy-loaded content/images or to bring a section into view before screenshotting.",
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
            description="Block until an element disappears — removed from the DOM or hidden — up to timeout. Returns {success} once it's gone, or times out. Use to wait for a modal/dialog to close or a loading spinner to vanish before the next step.",
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
            description="Return the raw outerHTML of matching elements, or the full page HTML if no selector, truncated to max_length. Returns the HTML string(s). Use to inspect component/markup structure — e.g. head meta tags for SEO, or a widget's DOM. Standard CSS selectors only.",
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
            description="Parse an HTML table into structured data, mapping header cells to each row's values. Returns {headers, rows, total_rows} where rows are header→value objects. Use instead of scraping table markup by hand when verifying tabular content.",
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
            description="Capture currently-visible toast/notification/alert text on a session — checks common patterns ([role=alert], [role=status], [aria-live], .toast, .notification, Toastify, Sonner, Radix) or your own selector. Returns the messages found. Set wait_ms to let a toast animate in first. Use to verify success/error notifications after an action.",
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
            description="Select an option from a native <select> or a custom dropdown (Radix/shadcn combobox), auto-detecting which. Choose by value, label, or index. Returns {success} and the resulting selection. For custom dropdowns it opens the menu and clicks the matching option — use this rather than click+click. When a page has several attribute-less <select> elements, pass element_index to target the Nth match of the selector (Playwright '>>' syntax is not supported).",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "selector": {"type": "string", "description": "CSS selector for the <select> or combobox trigger (plain CSS only — no Playwright '>>' syntax)"},
                    "value": {"type": "string", "description": "Option value to select"},
                    "label": {"type": "string", "description": "Option label text to select"},
                    "index": {"type": "integer", "description": "Option index to select (0-based)"},
                    "element_index": {"type": "integer", "description": "Which match of 'selector' to target, 0-based (default: 0). Use for the 2nd/3rd attribute-less <select> on a page."}
                },
                "required": ["session_id", "selector"]
            }
        ),
        Tool(
            name="get_response_body",
            description="Return the captured response body text for a request whose URL contains a substring (optionally filtered by method). Matching is a plain substring test against the full URL incl. query string — not a regex or glob. On a miss it lists the captured candidate URLs so you can adjust the pattern in one round-trip. Bodies are captured automatically for fetch/xhr/document requests, making this the fastest way to diagnose a 400/500 — no setup before the request.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID"},
                    "url_pattern": {"type": "string", "description": "Plain substring of the full URL incl. query string (e.g. '/api/quotes', 'graphql') — not a regex; anchors ($) and wildcards (.*) never match."},
                    "method": {"type": "string", "description": "HTTP method filter (optional, e.g. 'POST', 'GET')"}
                },
                "required": ["session_id", "url_pattern"]
            }
        ),

        # Web Search & Fetch
        Tool(
            name="web_search",
            description="Search DuckDuckGo and return result titles, URLs, and snippets (up to max_results). Use to look up documentation, verify external facts, or research during a testing workflow.",
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
            description="Fetch a URL over HTTP (no browser) and return its readable text content, or raw HTML with raw_html=true, up to max_length. TLS is verified by default — set verify_ssl=false for self-signed dev certs. Use to read docs or verify external link content without opening a session.",
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

        # System
        Tool(
            name="periscope_system",
            description="Install status, self-update, and the current agent guide — Periscope's self-maintenance tool. action='status' (read-only): running version vs on-disk version, git commit, install type, capabilities (Node/Lighthouse, display for headed, Chromium), active session count, and whether an update is available. action='agents_md' (read-only): returns the CURRENT AGENTS.md so you can refresh a stale pasted copy of your operating guide. action='update': dry-run by default (commits behind + incoming changes); apply=true runs the updater (git pull + deps, data/ untouched) — new code loads only after the MCP server restarts, and the response says so explicitly. Managed installs (Docker, no .git) refuse update with guidance.",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["status", "update", "agents_md"],
                               "description": "status = install/version/capabilities report (default); update = check or apply an update; agents_md = fetch the current agent guide"},
                    "apply": {"type": ["boolean", "string"], "description": "For action='update': actually run the update instead of the dry-run check (default: false)"},
                    "force": {"type": ["boolean", "string"], "description": "For action='update' with apply=true: auto-stash local modifications first (update.sh --force)"}
                },
                "required": []
            }
        ),

        # Discovery
        Tool(
            name="describe_tools",
            description="Return a structured catalog of Periscope's tools grouped by category, with parameters, workflow examples, and tips — optionally filtered to one category. Returns the guide as structured JSON. Call this first if you're new to the server, to plan a testing workflow.",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["all", "new", "project", "auth", "static_testing", "results", "sessions", "interactive", "analysis", "workflow", "advanced", "recording", "agent_speed", "web", "system"],
                        "description": "Filter by category (default: 'all')"
                    }
                },
                "required": []
            }
        ),
]
