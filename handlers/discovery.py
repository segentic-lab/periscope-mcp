"""Tool catalog / discovery (describe_tools)."""
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
from tool_schemas import TOOLS


@tool("describe_tools")
async def handle_describe_tools(args: dict) -> dict:
        category = args.get("category", "all")

        catalog = {
            "new": {
                "name": "New Tools (Latest Release)",
                "description": "The 0.10 batch: semantic page map, batch assertions, popup/new-tab adoption, file downloads, visual-regression baselines, saved flows, and element-clip screenshots.",
                "tools": {
                    "get_page_map": {"params": "session_id, max_nodes?, include_hidden?", "note": "NEW — Orient in ONE call: interactive elements + landmarks with role, accessible name, state, ready-to-use selector. unnamed flags = a11y findings."},
                    "assert_all": {"params": "session_id, assertions[]", "note": "NEW — Batch assertions, every verdict in one call (no early abort). Prefer over sequential assert_condition."},
                    "select_page": {"params": "session_id, index?", "note": "NEW — Adopt a popup/new tab (OAuth, target=_blank) as a new drivable session; console/network capture attaches at the popup event."},
                    "download_file": {"params": "session_id, selector, timeout?", "note": "NEW — Click a trigger, capture the downloaded file: path, size, sha256, text preview. Honest capture_method flag."},
                    "visual_check": {"params": "session_id, name, action(set|check), selector?", "note": "NEW — Named visual baselines: set once, check → hard pass/fail + diff image. Element-scoped baselines flake less."},
                    "flow": {"params": "action(save|run|list|delete), name?, steps?, session_id?", "note": "NEW — Save named step sequences, replay in any session. Verify with assert_all after."},
                    "screenshot_session (selector)": {"params": "session_id, selector", "note": "NEW — selector param clips the screenshot to one element (evidence citing)."},
                    "session_report": {"params": "title?, notes?, pdf?, clear?", "note": "NEW — HTML+PDF dossier of the whole run for your user: every call, verdicts, timings, screenshots."},
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
                    "describe_tools": {"params": "category?", "note": "This catalog — structured tool reference with workflows and tips"},
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
                    "interactive_login": {"params": "project, login_url?", "note": "Open a VISIBLE window to log in by hand (2FA/SSO/CAPTCHA); then save_login. Needs a display."},
                    "save_login": {"params": "project", "note": "Capture the manual-login session into the project; future sessions run authenticated + headless"},
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
                    "session_report": {"params": "title?, notes?, pdf?, clear?", "note": "HTML+PDF dossier of every tool call this run (redacted args, verdicts, screenshots). notes = your findings summary."},
                },
            },
            "sessions": {
                "name": "Session Management",
                "description": "Persistent browser sessions that survive across tool calls. Required for interactive testing.",
                "tools": {
                    "open_session": {"params": "url, project?, headed?", "note": "Create session — returns session_id + screenshot. headed=true opens a visible window (needs a display)."},
                    "close_session": {"params": "session_id", "note": "Close session and free resources"},
                    "list_sessions": {"params": "(none)", "note": "All active sessions with idle times"},
                    "set_viewport": {"params": "session_id, width?, height?, device?", "note": "Switch viewport. Presets: mobile_sm, mobile, mobile_lg, tablet, tablet_lg, laptop, desktop, desktop_lg"},
                    "select_page": {"params": "session_id, index?", "note": "Adopt a popup/new tab as a new session (captured from birth)"},
                },
            },
            "interactive": {
                "name": "Interactive Actions",
                "description": "Click, type, fill forms, and query elements on a session page.",
                "tools": {
                    "click_element": {"params": "session_id, selector, force?", "note": "Click and get screenshot. Auto-falls-back to a JS dispatch click when a portal overlay (Radix/shadcn) intercepts the pointer (flagged click_method='js_dispatch')."},
                    "fill_form": {"params": "session_id, fields[{selector,value}], submit_selector?", "note": "Fill fields, optionally submit. Auto-handles date/time inputs for React compatibility."},
                    "interact_and_test": {"params": "url|session_id, steps[], run_checks?[], capture_console?", "note": "Multi-step scripted workflow (25 actions incl. force_fill, select_option). fill/force_fill auto-handle date inputs. capture_console=true returns console output from the steps."},
                    "select_option": {"params": "session_id, selector, value?, label?, index?, element_index?", "note": "Native <select> or custom dropdown (Radix/shadcn). element_index targets the Nth match of the selector (attribute-less selects)"},
                    "scroll_into_view": {"params": "session_id, selector", "note": "Scroll element into viewport without clicking"},
                    "get_page_elements": {"params": "selector, url|session_id, max_results?, attributes?[], full_text?", "note": "List elements with attributes; attributes[] adds data-*/aria-* values, full_text returns complete text"},
                    "flow": {"params": "action, name?, steps?, session_id?", "note": "Save/run/list/delete named step sequences"},
                },
            },
            "analysis": {
                "name": "Analysis & Validation",
                "description": "Deep checks on forms, links, responsiveness, screenshots, and timing.",
                "tools": {
                    "test_form_validation": {"params": "url|session_id, form_selector?", "note": "Submit empty forms, collect validation messages"},
                    "visual_check": {"params": "session_id, name, action(set|check), selector?", "note": "Named visual baselines with hard pass/fail"},
                    "compare_screenshots": {"params": "screenshot1, screenshot2, threshold?", "note": "Pixel diff — returns % changed + diff image"},
                    "test_responsive": {"params": "url, viewports?[], run_checks?[]", "note": "Test at mobile/tablet/desktop viewports"},
                    "run_lighthouse": {"params": "url, categories?[], device?, timeout?", "note": "Real Google Lighthouse audit: 0-100 scores + Core Web Vitals + failed audits. Needs Node.js."},
                    "get_interaction_log": {"params": "session_id, format?(json|csv), clear?", "note": "Export real INP time series (one record per driven interaction) as JSON/CSV + percentile stats. For long interactive tests."},
                    "check_links": {"params": "url|session_id, check_external?, max_links?", "note": "Comprehensive link status checker"},
                    "measure_interaction": {"params": "session_id, selector, wait_for?, wait_for_network?", "note": "Measure click-to-result timing (ms) + real INP. Pass wait_for_network (URL substring) for handlers that fire requests asynchronously — plain networkidle settles early and under-measures."},
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
                    "navigate_session": {"params": "session_id, action(back|forward|reload)", "note": "Browser history navigation + reload"},
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
                    "intercept_network": {"params": "session_id, url_pattern, status?, body?, content_type?, method?, once?", "note": "Mock API responses"},
                    "clear_intercepts": {"params": "session_id, url_pattern?", "note": "Remove network mocks (all, or by pattern)"},
                    "get_local_storage": {"params": "session_id, storage?, keys?", "note": "Read localStorage or sessionStorage"},
                    "set_local_storage": {"params": "session_id, entries, storage?, clear_first?", "note": "Write to localStorage or sessionStorage"},
                    "download_file": {"params": "session_id, selector, timeout?", "note": "Click trigger, capture downloaded file (path, sha256, preview)"},
                    "select_iframe": {"params": "session_id, selector", "note": "Enter iframe — returns new session_id"},
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
                    "interact_and_test (capture_console)": {"params": "session_id, steps[], capture_console=true", "note": "Console output captured during steps"},
                    "get_console_errors": {"params": "session_id, clear?", "note": "All console errors/logs since session opened"},
                },
            },
            "agent_speed": {
                "name": "AI Agent Speed Tools",
                "description": "Assertions, smart finders, auto-fill, network log, snapshots, cookies, contrast checks. Designed to replace multiple tool calls with one.",
                "tools": {
                    "assert_all": {"params": "session_id, assertions[]", "note": "Batch assertions: every verdict in one call"},
                    "get_page_map": {"params": "session_id, max_nodes?", "note": "Semantic page map: roles, names, states + ready selectors"},
                    "assert_condition": {"params": "session_id, assertion, selector?, expected?, attribute?", "note": "Instant pass/fail: text_contains, text_equals, element_exists, element_visible, element_count, url_contains, title_contains, attribute_equals"},
                    "find_element": {"params": "session_id, text?, tag?, role?, near?, max_results?", "note": "Smart finder — search by text, tag, role, or proximity"},
                    "auto_fill_form": {"params": "session_id, form_selector?, overrides?, submit?", "note": "Auto-detect fields, infer types, fill with test data. Date/time inputs filled with React-compatible events."},
                    "get_network_log": {"params": "session_id, url_filter?, clear?", "note": "All network requests (URL, status, method, type)"},
                    "page_state": {"params": "session_id, action(snapshot|restore|diff), name", "note": "Named checkpoints: save URL + cookies + storage + DOM, restore, or diff current DOM against one"},
                                                            "get_cookies": {"params": "session_id, domain_filter?", "note": "Read all session cookies"},
                    "check_color_contrast": {"params": "session_id, selector?, level?, max_results?", "note": "WCAG AA/AAA contrast ratio checks"},
                    "get_response_body": {"params": "session_id, url_pattern, method?", "note": "Get actual API response body text (url_pattern = plain substring, not regex; diagnose 400/500 errors)"},
                },
            },
            "web": {
                "name": "Web Search & Fetch",
                "description": "Search the internet and fetch page content.",
                "tools": {
                    "web_search": {"params": "query, max_results?", "note": "Search DuckDuckGo, returns titles + URLs + snippets"},
                    "web_fetch": {"params": "url, max_length?, raw_html?, verify_ssl?", "note": "Fetch URL and extract readable text content"},
                },
            },
            "system": {
                "name": "System & Self-Maintenance",
                "description": "Install status, self-update, and the current agent guide.",
                "tools": {
                    "periscope_system": {"params": "action (status|update|agents_md), apply?, force?", "note": "status = version/commit/capabilities/update-check; agents_md = fetch the CURRENT agent guide to refresh a stale pasted copy; update = dry-run by default, apply=true runs git pull + deps (restart required to load new code)"},
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
            "total_tools": len(TOOLS),
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
                "page_state(session_id, 'snapshot', 'before')",
                "click_element / fill_form / etc.",
                "page_state(session_id, 'diff', 'before') → see what changed",
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
                "fill_form(session_id, fields=[{selector:'#name', value:'John'}], force=true) — fill even if overlay blocks",
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
            "First time on this install, or a long-running one? periscope_system(action='status') reports the version you're driving and whether an update exists (apply only with user approval); action='agents_md' returns the CURRENT operating guide if your pasted copy may be stale.",
            "Tools accepting 'url|session_id': pass session_id to reuse an open page, or url for ephemeral (one-shot) testing.",
            "Use find_element before click_element to discover the right selector.",
            "Use auto_fill_form instead of multiple fill_form calls — it infers field types.",
            "Use assert_condition instead of screenshots when you just need pass/fail.",
            "Use page_state snapshot + diff to detect exactly what changed after an action.",
            "Use handle_dialog BEFORE the action that triggers the dialog.",
            "Network log is captured automatically — call get_network_log anytime to see API calls.",
            "force=true on click_element bypasses overlay interception (cookie banners, modals).",
            "Use fill_form with force=true when overlays or dialogs block inputs.",
            "Use select_option for custom dropdowns (Radix, shadcn) — no more evaluate_js hacks.",
            "Use get_table_data to parse tables into {headers, rows[]} instead of reading raw element text.",
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
