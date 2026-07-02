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
                    "intercept_network": {"params": "session_id, url_pattern, status?, body?, content_type?, method?, once?", "note": "Mock API responses"},
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
                    "find_element": {"params": "session_id, text?, tag?, role?, near?, max_results?", "note": "Smart finder — search by text, tag, role, or proximity"},
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
                    "web_fetch": {"params": "url, max_length?, raw_html?, verify_ssl?", "note": "Fetch URL and extract readable text content"},
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
