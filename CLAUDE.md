# WebsiteTesterAI - Project Guide

## What This Is
MCP server that gives Claude Code tools to test websites using Playwright + headless Chrome.

## How to Run
```bash
source venv/bin/activate
python server.py  # Runs as MCP stdio server (not a web server)
```

## Key Files
- `server.py` - MCP tool definitions + routing (start here)
- `tester.py` - Core Playwright logic (browser, screenshots, test orchestration, responsive testing)
- `crawler.py` - BFS page discovery
- `projects.py` - Project/auth data models + JSON persistence
- `auth.py` - Login handlers (form, basic auth, cookies)
- `sessions.py` - `SessionManager` + `PageSession` — persistent page lifecycle for interactive testing
- `interactions.py` - Interaction primitives: click, fill, get_elements, execute_steps, measure timing
- `utils.py` - Screenshot comparison (Pillow-based pixel diff)
- `config.py` - Global settings (timeouts, viewport, paths, crawl limits, session limits)
- `requirements.txt` - Python dependencies
- `checks/` - Individual test check modules

## Adding a New MCP Tool
1. Add `Tool(...)` definition in `server.py` -> `list_tools()`
2. Add handler in `server.py` -> `_handle_tool()`

## Adding a New Check
1. Add function in `checks/*.py` returning `list[dict]` with keys: type, severity, message
2. Import + call it in `tester.py` -> `test_url()`

Note: `check_seo()` and `get_performance_metrics()` live in `checks/functionality.py`, not separate files.

## Issue Format
```python
{"type": "accessibility", "severity": "error", "message": "...", "details": [...]}
```
- **type**: visual, accessibility, functionality, seo
- **severity**: error, warning, info

## Interactive Testing (Session-Based)

Sessions keep browser pages alive across tool calls, enabling multi-step workflows.

### Session Workflow
```
open_session(url) → session_id
get_page_elements(session_id, "button") → see what's clickable
click_element(session_id, "#submit-btn") → screenshot after click
fill_form(session_id, fields=[...]) → fill and submit
close_session(session_id)
```

### Session Tools
- `open_session(url, project?)` — Create persistent session, returns session_id + screenshot
- `close_session(session_id)` — Close session and free resources
- `list_sessions()` — List all active sessions with URLs/idle times

### Interactive Tools
- `click_element(session_id, selector)` — Click element, return screenshot + new URL/title
- `fill_form(session_id, fields[], submit_selector?)` — Fill fields, optionally submit
- `interact_and_test(url|session_id, steps[], run_checks?[], ...)` — Multi-step workflow (click/fill/type/select/wait/navigate/hover/press_key/check/uncheck)
- `get_page_elements(selector, url|session_id, max_results?)` — List matching elements with attributes

### Analysis Tools
- `test_form_validation(url|session_id, form_selector?)` — Analyze form validation
- `compare_screenshots(screenshot1, screenshot2, threshold?)` — Pixel diff using Pillow
- `test_responsive(url, viewports?[], run_checks?[])` — Test at mobile/tablet/desktop viewports
- `check_links(url|session_id, check_external?, max_links?)` — Comprehensive link checker
- `measure_interaction(session_id, selector, wait_for?)` — Measure click-to-result timing

### Advanced Tools
- `record_session(url, steps[], project?)` — Record workflow as video
- `test_keyboard_navigation(url|session_id, max_tabs?)` — Tab-order and focus indicator audit
- `extract_text(selector, url|session_id)` — Get text content from elements
- `check_console_during_interaction(session_id, steps[])` — Capture console output during workflow

### Session Config (`config.py`)
- `MAX_SESSIONS = 10` — Max concurrent sessions
- `SESSION_TIMEOUT = 300` — Auto-expire after 300s idle

## Data
- Projects: `data/projects.json` (contains credentials - never commit)
- Screenshots: `data/screenshots/{project}/*.png`
- Reports: `data/reports/{project}_{timestamp}.json`
- Videos: `data/videos/{project}/*.webm`
- Diffs: `data/diffs/*.png`
