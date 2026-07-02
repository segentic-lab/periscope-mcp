# periscope-mcp - Project Guide

## What This Is
MCP server that gives Claude Code tools to test websites using Playwright + headless Chrome.

## How to Run
```bash
source venv/bin/activate
python server.py  # Runs as MCP stdio server (not a web server)
```

First-time setup: `./install.sh` (automated on Debian/Ubuntu; prints per-OS commands elsewhere).

## Key Files
- `server.py` - MCP entry point: stdio wiring + dispatch (44 lines — start in handlers/ instead)
- `tool_schemas.py` - All 71 MCP `Tool(...)` schema definitions
- `handlers/` - Tool handlers grouped by category (projects, auth, static_testing, session_tools, interactive, analysis, advanced, agent_speed, web, discovery); `registry.py` holds the `@tool(name)` decorator
- `runtime.py` - Shared singletons: `project_manager`, `session_manager`, `auth_handler`, `get_tester()`
- `coercion.py` - JSON-string arg coercion (whitelist-based; never touches free-text args)
- `tester.py` - Core Playwright logic (browser, screenshots, test orchestration, responsive testing)
- `crawler.py` - BFS page discovery
- `projects.py` - Project/auth data models + JSON persistence
- `auth.py` - Login handlers (form, basic auth, cookies)
- `sessions.py` - `SessionManager` + `PageSession` + `real_page()` — persistent page lifecycle
- `interactions.py` - Interaction primitives: click, fill, get_elements, execute_steps, measure timing
- `utils.py` - Screenshot comparison (Pillow-based pixel diff)
- `config.py` - Global settings (timeouts, viewport, paths, crawl limits, session limits)
- `checks/` - Individual test check modules
- `tests/` - Unit tests (`pytest`, no browser needed); `tests/local/` is gitignored for personal e2e scripts

## Adding a New MCP Tool
1. Add `Tool(...)` definition in `tool_schemas.py`
2. Add handler in the matching `handlers/<category>.py`:
   ```python
   @tool("my_tool")
   async def handle_my_tool(args: dict) -> dict:
       ...
   ```
3. If it takes array/bool args, add them to the whitelists in `coercion.py`
4. `pytest` — `tests/test_registry.py` fails if schemas and handlers drift

## Adding a New Check
1. Add function in `checks/*.py` returning `list[dict]` with keys: type, severity, message
2. Import + call it in `tester.py` -> `test_url()`

Note: `check_seo()` and `get_performance_metrics()` live in `checks/functionality.py`, not separate files. `checks/geo.py` holds the GEO/agentic-search check (`check_geo`) plus the shared robots.txt parser the SEO check reuses.

## Issue Format
```python
{"type": "accessibility", "severity": "error", "message": "...", "details": [...]}
```
- **type**: visual, accessibility, functionality, seo, geo
- **severity**: error, warning, info

## Project & Static Testing Tools

- `create_project(name, base_url, max_pages?, max_depth?, screenshot_dir?)` / `list_projects()` / `get_project(name)` / `delete_project(name)`
- `set_form_login(project, login_url, username, password, selectors?)` / `set_basic_auth(project, username, password)` / `set_cookies(project, cookies[])` — configure auth, then `login_project(project)` to execute
- `test_url(url, project?, checks?[])` — Screenshot + checks for one URL
- `crawl_project(project, max_pages?, max_depth?)` — BFS page discovery
- `test_project(project, checks?[])` — Crawl + test all pages, saves JSON report
- `get_screenshot(project, url)` / `list_reports(project?)` / `get_report(report_path)`
- `describe_tools(category?)` — Structured tool catalog with workflows and tips

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
- `set_viewport(session_id, width?, height?, device?)` — Switch viewport size. Presets: `mobile_sm` (320x568), `mobile` (375x812), `mobile_lg` (428x926), `tablet` (768x1024), `tablet_lg` (1024x1366), `laptop` (1366x768), `desktop` (1920x1080), `desktop_lg` (2560x1440)

### Interactive Tools
- `click_element(session_id, selector, force?)` — Click element, return screenshot + new URL/title. `force=true` bypasses overlay interception.
- `fill_form(session_id, fields[], submit_selector?)` — Fill fields, optionally submit
- `force_fill(session_id, selector, value)` — Fill input bypassing actionability checks (overlays, dialogs behind inputs)
- `select_option(session_id, selector, value?, label?, index?)` — Select from native `<select>` or custom dropdown (Radix/shadcn combobox). Auto-detects type.
- `interact_and_test(url|session_id, steps[], run_checks?[], ...)` — Multi-step workflow with 25 actions: click, force_click, fill, force_fill, type, select, select_option, wait, wait_for, wait_for_text, screenshot, navigate, hover, press_key, check, uncheck, scroll_to, scroll_within, evaluate_js, drag, right_click, go_back, go_forward, upload_file, wait_for_network
- `get_page_elements(selector, url|session_id, max_results?)` — List matching elements with attributes
- `get_attribute(selector, attributes[], url|session_id)` — Get specific HTML attribute values (data-*, aria-*, style, etc.)

### Analysis Tools
- `test_form_validation(url|session_id, form_selector?)` — Analyze form validation
- `compare_screenshots(screenshot1, screenshot2, threshold?)` — Pixel diff using Pillow
- `test_responsive(url, viewports?[], run_checks?[])` — Test at mobile/tablet/desktop viewports
- `check_links(url|session_id, check_external?, max_links?)` — Comprehensive link checker
- `measure_interaction(session_id, selector, wait_for?)` — Measure click-to-result timing
- `get_table_data(session_id, selector?, max_rows?)` — Parse HTML table into structured JSON with headers mapped to cell values
- `get_toast_messages(session_id, wait_ms?, selector?)` — Capture visible toast/notification messages (checks role=alert, role=status, aria-live, .toast, Toastify, Sonner, Radix)
- `run_lighthouse(url, categories?[], device?, timeout?)` — Real Google Lighthouse audit: 0-100 scores, Core Web Vitals, failed audits, full report saved to data/reports/. Requires Node.js (`npm i -g lighthouse` or npx). Runs its own Chrome — no session/auth state.

### Advanced Tools
- `record_session(url, steps[], project?)` — Record workflow as video
- `test_keyboard_navigation(url|session_id, max_tabs?)` — Tab-order and focus indicator audit
- `extract_text(selector, url|session_id)` — Get text content from elements
- `check_console_during_interaction(session_id, steps[])` — Capture console output during workflow
- `get_console_errors(session_id, clear?)` — Get all console errors/logs since session opened (or last read). Passive monitoring, no steps needed.

### Workflow Speed Tools
- `screenshot_session(session_id, full_page?)` — Quick screenshot of current page state, no actions performed
- `run_checks_on_session(session_id, checks?[])` — Run checks on active session page (no new page opened)
- `go_back(session_id)` / `go_forward(session_id)` — Browser history navigation
- `handle_dialog(session_id, action, prompt_text?)` — Accept/dismiss JS alert/confirm/prompt (call BEFORE triggering)
- `upload_file(session_id, selector, files[])` — Set files on `<input type="file">`
- `wait_for_network(session_id, url_pattern, method?, timeout?)` — Wait for specific API request to complete
- `wait_for_gone(session_id, selector, timeout?)` — Wait for element to disappear (modal close, spinner gone)
- `scroll_into_view(session_id, selector)` — Scroll element into viewport without clicking
- `get_page_html(session_id, selector?, max_length?)` — Get raw outerHTML of elements or full page HTML

### Advanced Testing Tools
- `intercept_network(session_id, url_pattern, status?, body?, content_type?, once?)` — Mock API responses to test error/empty/loading states
- `clear_intercepts(session_id, url_pattern?)` — Remove network mocks set by intercept_network (all, or by pattern)
- `get_local_storage(session_id, storage?, keys?)` / `set_local_storage(session_id, entries, storage?, clear_first?)` — Read/write localStorage or sessionStorage
- `select_iframe(session_id, selector)` — Switch into iframe, returns new session scoped to iframe content
- `reload_page(session_id)` — Refresh page, test state persistence
- `get_computed_style(session_id, selector, properties[])` — Get actual rendered CSS values (color, font-size, display, etc.)
- `emulate_network(session_id, preset)` — Throttle network: `slow_3g`, `fast_3g`, `offline`, `reset`
- `test_dark_mode(session_id, mode)` — Toggle `prefers-color-scheme` to `dark` or `light`

### AI Agent Speed Tools
- `assert_condition(session_id, assertion, selector?, expected?, attribute?)` — Programmatic pass/fail assertions: `text_contains`, `text_equals`, `element_exists`, `element_visible`, `element_count`, `url_contains`, `title_contains`, `attribute_equals`
- `find_element(session_id, text?, tag?, role?, near?, max_results?)` — Smart element finder by text/role/proximity. Returns best CSS selectors.
- `auto_fill_form(session_id, form_selector?, overrides?, submit?)` — Auto-detect fields, infer types (email/phone/name/etc.), fill with test data. One call replaces 5-10.
- `get_network_log(session_id, url_filter?, clear?)` — All network requests captured during session (URL, status, method, type)
- `snapshot_page_state(session_id, name)` — Save URL + cookies + storage + DOM as named checkpoint
- `restore_page_state(session_id, name)` — Restore a saved snapshot (navigate + cookies + storage)
- `diff_page_state(session_id, name)` — Compare current DOM vs snapshot: added/removed/changed elements + tag count changes
- `get_cookies(session_id, domain_filter?)` — Read all cookies from session context
- `check_color_contrast(session_id, selector?, level?, max_results?)` — WCAG AA/AAA contrast ratio checks on text elements
- `get_response_body(session_id, url_pattern, method?)` — Get actual API response body text. Critical for diagnosing 400/500 errors. Bodies captured automatically for fetch/xhr/document requests.

### Web Tools
- `web_search(query, max_results?)` — Search DuckDuckGo, returns titles + URLs + snippets
- `web_fetch(url, max_length?, raw_html?, verify_ssl?)` — Fetch URL and extract readable text content (or raw HTML). TLS verified by default; `verify_ssl=false` for self-signed dev servers.

### Utility Tools
- `copy_auth(from_project, to_project)` — Copy auth config + session cookies between projects on same domain

### Session Config (`config.py`)
- `MAX_SESSIONS = 20` — Max concurrent sessions
- `SESSION_TIMEOUT = 300` — Auto-expire after 300s idle (env-overridable: `SESSION_TIMEOUT=600`)
- `MAX_RESPONSE_BODY_SIZE = 512000` — Max response body capture size (500KB)
- `MAX_RESPONSE_BODIES = 100` — Max captured response bodies kept per session
- `MAX_CONSOLE_LOG = 500` / `MAX_NETWORK_LOG = 1000` — Per-session log caps (oldest entries dropped)
- `WAIT_UNTIL = "networkidle"` — Navigation wait strategy; set `NAV_WAIT_UNTIL=load` for sites with websockets/polling that never reach networkidle

## Social / SEO Preview Validation

The `seo` check now covers the basics automatically: OG core-tag completeness (`og:title/description/image/url`), absolute `og:image`, `twitter:card` presence, JSON-LD parseability, H1 count, `noindex` (meta + `X-Robots-Tag` header), and — in `test_project` — duplicate titles/descriptions across pages. For content-level validation beyond presence/parsing, inspect the DOM via `get_page_html(session_id, selector="head")`:
- **Open Graph:** `<meta property="og:title|og:description|og:image|og:url|og:type">` — title ≤60 chars, description ≤200, image absolute URL + 1.91:1 ratio (1200x630 ideal)
- **Twitter Card:** `<meta name="twitter:card|twitter:title|twitter:description|twitter:image">` — `card` should be `summary_large_image` for rich previews
- **JSON-LD:** `<script type="application/ld+json">` — validate Product/Service/Organization schemas

### Manual validator references
Platform-side rendering (image caches, crop ratios, SERP appearance) can only be verified on the platform itself. These require login/manual use — cannot automate reliably:
- LinkedIn Post Inspector — https://www.linkedin.com/post-inspector/ (OG rendering, LinkedIn cache refresh)
- Facebook Sharing Debugger — https://developers.facebook.com/tools/debug/ (OG tags + FB cache scrape)
- Google Rich Results Test — https://search.google.com/test/rich-results (Product/Service/FAQ schema validation, SERP preview)
- Twitter Card Validator — https://cards-dev.twitter.com/validator (deprecated 2023; Twitter/X no longer provides a working validator)

## Known Limitations
- Default drag (`drag_to`) is ignored by pointer-tracking DnD libs (`@hello-pangea/dnd` etc.) — the step succeeds but nothing moves. Retry the drag step with `method: "mouse"` (stepped manual drag), or use the library's keyboard mode (focus handle → Space → arrows → Space). Verify with `diff_page_state`/`assert_condition`.

## Data
- Projects: `data/projects.json` (contains credentials - never commit)
- Screenshots: `data/screenshots/{project}/*.png`
- Reports: `data/reports/{project}_{timestamp}.json`
- Videos: `data/videos/{project}/*.webm`
- Diffs: `data/diffs/*.png`
