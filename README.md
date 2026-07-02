# periscope-mcp

An MCP (Model Context Protocol) server that gives Claude Code AI-powered website testing tools. It uses Playwright with headless Chrome to crawl websites, take screenshots, run automated checks, and interactively test web applications. 70 tools covering static analysis, interactive testing, responsive testing, network mocking, accessibility audits, and more.

## Architecture

```
Claude Code  -->  MCP Server (stdio)  -->  Playwright (Headless Chrome)
                       |                         |
                       +-- Projects (JSON)       +-- Persistent Sessions
                       +-- Screenshots (PNG)     +-- Network Interception
                       +-- Reports (JSON)        +-- Device Emulation
                       +-- Videos (WebM)
```

**How it works:** Claude Code connects to this MCP server over stdio. The server exposes 70 tools that Claude Code can call to create projects, configure authentication, crawl websites, run static checks, and interactively test web applications using persistent browser sessions. Results (JSON + screenshots + videos) are returned to Claude Code for analysis.

## Project Structure

```
periscope-mcp/
├── server.py              # MCP server entry point (stdio wiring + dispatch)
├── tool_schemas.py        # All 70 MCP tool definitions (schemas)
├── runtime.py             # Shared singletons (project store, sessions, browser)
├── coercion.py            # Argument coercion for MCP clients with stale schemas
├── handlers/              # Tool handlers, grouped by category
│   ├── registry.py        # @tool(name) decorator + HANDLERS registry
│   ├── projects.py        # create/list/get/delete project
│   ├── auth.py            # form login, basic auth, cookies, copy_auth
│   ├── static_testing.py  # test_url, crawl, test_project, reports, responsive
│   ├── session_tools.py   # open/close/list sessions, viewport, history
│   ├── interactive.py     # click, fill, steps, element queries, dialogs
│   ├── analysis.py        # forms, links, keyboard nav, tables, toasts, contrast
│   ├── advanced.py        # network mocking, storage, iframes, emulation, recording
│   ├── agent_speed.py     # assertions, smart find, auto-fill, snapshots
│   ├── web.py             # web_search, web_fetch
│   └── discovery.py       # describe_tools catalog
├── tester.py              # Playwright browser control + test orchestration
├── crawler.py             # Page discovery (BFS crawl, same-domain only)
├── projects.py            # Project CRUD + auth config storage
├── auth.py                # Authentication handlers (form, basic, cookies)
├── sessions.py            # SessionManager + PageSession — persistent page lifecycle
├── interactions.py        # Interaction primitives (click, fill, execute_steps)
├── utils.py               # Screenshot comparison (Pillow pixel diff)
├── config.py              # Global settings (timeouts, paths, session limits)
├── checks/
│   ├── visual.py          # Broken images, favicon, overflow, small text
│   ├── accessibility.py   # Alt text, labels, headings, lang, ARIA, keyboard nav
│   └── functionality.py   # Broken links, forms, SEO, performance, link checker
├── tests/                 # Unit tests (pytest, no browser required)
├── data/                  # Created at runtime (gitignored — contains credentials)
├── Dockerfile
├── docker-compose.yml
└── .mcp.json.example      # Claude Code MCP registration template (copy to .mcp.json)
```

## Prerequisites

- Python 3.11+
- Playwright + Chromium browser

## Installation (Local)

```bash
# Clone the repo
cd periscope-mcp

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Chromium for Playwright
playwright install chromium
```

## Installation (Docker)

```bash
docker compose up -d
```

See [Docker Deployment](#docker-deployment) section below.

## Connecting to Claude Code

### Option 1: Project-level config (recommended)

Copy the template and adjust the paths, then open Claude Code in this directory:

```bash
cp .mcp.json.example .mcp.json
```

```json
{
  "mcpServers": {
    "periscope": {
      "command": "/path/to/periscope-mcp/venv/bin/python",
      "args": ["/path/to/periscope-mcp/server.py"]
    }
  }
}
```

### Option 2: Global config

Add to `~/.claude.json` under the project's `mcpServers` key:

```json
"mcpServers": {
  "periscope": {
    "command": "/path/to/periscope-mcp/venv/bin/python",
    "args": ["/path/to/periscope-mcp/server.py"]
  }
}
```

After configuring, restart Claude Code.

## MCP Tools Reference (70 tools)

### Project Management (4 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `create_project` | Create a new testing project | `name`, `base_url` |
| `list_projects` | List all projects | _(none)_ |
| `get_project` | Get project details | `name` |
| `delete_project` | Delete project + data | `name` |

### Authentication (5 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `set_form_login` | Configure username/password form login | `project`, `login_url`, `username`, `password` |
| `set_basic_auth` | Configure HTTP Basic Auth | `project`, `username`, `password` |
| `set_cookies` | Inject session cookies | `project`, `cookies` (array) |
| `login_project` | Execute login using configured auth | `project` |
| `copy_auth` | Copy auth config + session cookies between projects | `from_project`, `to_project` |

### Static Testing (3 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `test_url` | Test a single URL (screenshot + checks) | `url` |
| `crawl_project` | Discover all pages from base URL | `project` |
| `test_project` | Full audit: crawl + test all pages | `project` |

### Results (3 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `get_screenshot` | Get screenshot file path | `project`, `url` |
| `list_reports` | List saved test reports | _(optional: `project`)_ |
| `get_report` | Read a report file | `report_path` |

### Session Management (4 tools)

Sessions keep browser pages alive across tool calls, enabling multi-step interactive workflows.

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `open_session` | Open persistent browser session | `url` |
| `close_session` | Close session and free resources | `session_id` |
| `list_sessions` | List all active sessions | _(none)_ |
| `set_viewport` | Switch viewport size (8 device presets or custom w/h) | `session_id` |

`set_viewport` presets: `mobile_sm` (320x568), `mobile` (375x812), `mobile_lg` (428x926), `tablet` (768x1024), `tablet_lg` (1024x1366), `laptop` (1366x768), `desktop` (1920x1080), `desktop_lg` (2560x1440)

### Interactive Actions (9 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `click_element` | Click element (`force=true` bypasses overlays) | `session_id`, `selector` |
| `fill_form` | Fill form fields, optionally submit | `session_id`, `fields` |
| `force_fill` | Fill input bypassing actionability checks (overlays, dialogs) | `session_id`, `selector`, `value` |
| `select_option` | Native `<select>` or custom dropdown (Radix/shadcn) — auto-detects | `session_id`, `selector` |
| `interact_and_test` | Multi-step workflow with 25 actions (see below) | `steps` |
| `get_page_elements` | List matching elements with attributes | `selector` |
| `get_attribute` | Get specific HTML attribute values (data-*, aria-*, style, etc.) | `selector`, `attributes` |
| `extract_text` | Get text content from matching elements | `selector` |
| `scroll_into_view` | Scroll element into viewport without clicking | `session_id`, `selector` |

**`interact_and_test` supports 25 step actions:**
`click`, `force_click`, `fill`, `force_fill`, `type`, `select`, `select_option`, `wait`, `wait_for`, `wait_for_text`, `screenshot`, `navigate`, `hover`, `press_key`, `check`, `uncheck`, `scroll_to`, `scroll_within`, `evaluate_js`, `drag`, `right_click`, `go_back`, `go_forward`, `upload_file`, `wait_for_network`

### Analysis (7 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `test_form_validation` | Analyze form validation messages | _(url or session_id)_ |
| `compare_screenshots` | Pixel diff between two screenshots | `screenshot1`, `screenshot2` |
| `test_responsive` | Test at mobile/tablet/desktop viewports | `url` |
| `check_links` | Comprehensive link checker (internal + external) | _(url or session_id)_ |
| `measure_interaction` | Measure click-to-result timing | `session_id`, `selector` |
| `get_table_data` | Parse HTML table into structured JSON (headers → cell values) | `session_id` |
| `get_toast_messages` | Capture visible toast/notification messages | `session_id` |

### Workflow Speed (9 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `screenshot_session` | Quick screenshot of current page state | `session_id` |
| `run_checks_on_session` | Run checks on active session (no new page) | `session_id` |
| `go_back` | Browser back button | `session_id` |
| `go_forward` | Browser forward button | `session_id` |
| `handle_dialog` | Accept/dismiss JS alert/confirm/prompt (call BEFORE trigger) | `session_id`, `action` |
| `upload_file` | Set file(s) on `<input type="file">` | `session_id`, `selector`, `files` |
| `wait_for_network` | Wait for specific API URL pattern to complete | `session_id`, `url_pattern` |
| `wait_for_gone` | Wait for element to disappear (modal close, spinner gone) | `session_id`, `selector` |
| `get_page_html` | Raw outerHTML of elements, or full page HTML | `session_id` |

### Advanced Testing (9 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `intercept_network` | Mock API responses (test error/empty/loading states) | `session_id`, `url_pattern` |
| `clear_intercepts` | Remove network mocks (all, or by pattern) | `session_id` |
| `get_local_storage` | Read localStorage or sessionStorage | `session_id` |
| `set_local_storage` | Write to localStorage or sessionStorage | `session_id`, `entries` |
| `select_iframe` | Switch into iframe content (returns new session) | `session_id`, `selector` |
| `reload_page` | Refresh page, test state persistence | `session_id` |
| `get_computed_style` | Get actual rendered CSS values | `session_id`, `selector`, `properties` |
| `emulate_network` | Throttle network: `slow_3g`, `fast_3g`, `offline`, `reset` | `session_id`, `preset` |
| `test_dark_mode` | Toggle `prefers-color-scheme` dark/light | `session_id`, `mode` |

### Recording & Console (4 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `record_session` | Record workflow as video | `url`, `steps` |
| `test_keyboard_navigation` | Tab-order and focus indicator audit | _(url or session_id)_ |
| `check_console_during_interaction` | Capture console output during workflow | `session_id`, `steps` |
| `get_console_errors` | Get all console errors/logs (passive monitoring) | `session_id` |

### AI Agent Speed Tools (10 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `assert_condition` | Programmatic pass/fail: text_contains, element_exists, url_contains, etc. | `session_id`, `assertion` |
| `find_element` | Smart finder by text, tag, role, or proximity to another element | `session_id` |
| `auto_fill_form` | Auto-detect fields, infer types, fill with test data. One call = many fills. | `session_id` |
| `get_network_log` | All captured network requests (URL, status, method, type) | `session_id` |
| `get_response_body` | Actual API response body text (diagnose 400/500 errors) | `session_id`, `url_pattern` |
| `snapshot_page_state` | Save URL + cookies + storage + DOM as named checkpoint | `session_id`, `name` |
| `restore_page_state` | Restore a previously saved snapshot | `session_id`, `name` |
| `diff_page_state` | Compare current DOM vs snapshot: added/removed/changed elements | `session_id`, `name` |
| `get_cookies` | Read all cookies from session | `session_id` |
| `check_color_contrast` | WCAG AA/AAA contrast ratio checks on text elements | `session_id` |

### Web & Discovery (3 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `web_search` | Search DuckDuckGo: titles + URLs + snippets | `query` |
| `web_fetch` | Fetch URL, extract readable text (or raw HTML); TLS verified by default | `url` |
| `describe_tools` | Structured catalog of all tools with workflows and tips | _(none)_ |

## Test Checks

### Visual (`checks/visual.py`)
- Broken images (incomplete load or 0 natural width)
- Missing favicon
- Horizontal overflow / layout issues
- Very small text (< 12px)
- Missing body background color
- Images without explicit width/height dimensions

### Accessibility (`checks/accessibility.py`)
- Images missing `alt` text
- Links without accessible text (no text, no aria-label)
- Form inputs without associated labels
- Heading hierarchy (missing H1, multiple H1, skipped levels)
- Missing `lang` attribute on `<html>`
- Buttons without accessible names
- Missing skip navigation link
- Elements with `tabindex > 0`
- Keyboard navigation audit (tab order, visible focus indicators) — via `test_keyboard_navigation` tool

### Functionality (`checks/functionality.py`)
- Broken internal links (HTTP HEAD check, up to 20 links in `check_functionality`)
- Comprehensive link checker with external link support (up to 100 links) — via `check_links` tool
- Forms without action or submit button
- Orphan buttons outside forms
- External links missing `target="_blank"`
- Required form field count
- Autocomplete disabled inputs

### SEO (`checks/functionality.py` -> `check_seo`)
- Missing or too-long page title (> 60 chars)
- Missing or too-long meta description (> 160 chars)
- Missing viewport meta tag
- Missing canonical URL
- Missing Open Graph tags
- `noindex` robots meta

### Performance (`checks/functionality.py` -> `get_performance_metrics`)
- DOM content loaded time (ms)
- Full page load time (ms)
- First paint / first contentful paint (ms)
- Resource count
- Total transfer size (bytes / KB)

## Test Output Format

Each `test_url` call returns:

```json
{
  "url": "https://example.com",
  "status": "success",
  "status_code": 200,
  "title": "Page Title",
  "screenshot_path": "/path/to/screenshot.png",
  "load_time_ms": 1500,
  "issues": [
    {
      "type": "accessibility",
      "severity": "error",
      "message": "3 images missing alt text",
      "details": ["img1.png", "img2.png", "img3.png"]
    }
  ],
  "issue_count": 5,
  "issues_by_severity": {"error": 1, "warning": 2, "info": 2},
  "issues_by_type": {"accessibility": 2, "seo": 2, "visual": 1},
  "performance": {
    "dom_content_loaded_ms": 120,
    "load_complete_ms": 1500,
    "first_paint_ms": 140,
    "first_contentful_paint_ms": 140,
    "resource_count": 25,
    "total_size_bytes": 512000,
    "total_size_kb": 500
  },
  "console_errors": []
}
```

`test_project` returns an aggregated report with per-page results + summary.

## Usage Examples

### Basic test (no auth)
```
User: "Test https://example.com for issues"

Claude Code calls:
1. create_project(name="example", base_url="https://example.com")
2. test_project(project="example")
3. Analyzes results and reports findings
```

### Test with login
```
User: "Test https://myapp.com, login is admin/password123"

Claude Code calls:
1. create_project(name="myapp", base_url="https://myapp.com")
2. set_form_login(project="myapp", login_url="https://myapp.com/login",
                  username="admin", password="password123")
3. login_project(project="myapp")
4. test_project(project="myapp")
```

### Test with Basic Auth
```
User: "Test https://staging.example.com, it uses basic auth admin/secret"

Claude Code calls:
1. create_project(name="staging", base_url="https://staging.example.com")
2. set_basic_auth(project="staging", username="admin", password="secret")
3. login_project(project="staging")
4. test_project(project="staging")
```

### Test with cookies
```
User: "Test myapp using this session cookie: session=abc123"

Claude Code calls:
1. set_cookies(project="myapp", cookies=[
     {"name": "session", "value": "abc123", "domain": "myapp.com"}
   ])
2. test_project(project="myapp")
```

### Interactive testing (session-based)
```
User: "Go to myapp.com, click the login button, fill in the form, and check what happens"

Claude Code calls:
1. open_session(url="https://myapp.com") → session_id
2. get_page_elements(session_id=..., selector="button, a") → see clickable elements
3. click_element(session_id=..., selector="#login-btn") → screenshot after click
4. fill_form(session_id=..., fields=[
     {"selector": "#email", "value": "user@test.com"},
     {"selector": "#password", "value": "test123"}
   ], submit_selector="button[type='submit']")
5. Analyzes screenshot to see result
6. close_session(session_id=...)
```

### Scripted multi-step workflow (no session needed)
```
User: "Test the checkout flow on myshop.com"

Claude Code calls:
1. interact_and_test(
     url="https://myshop.com/products/1",
     steps=[
       {"action": "click", "selector": "#add-to-cart"},
       {"action": "wait", "timeout": 1000},
       {"action": "click", "selector": "#checkout-btn"},
       {"action": "fill", "selector": "#email", "value": "test@test.com"},
       {"action": "screenshot", "label": "checkout_form"},
       {"action": "click", "selector": "#submit-order"}
     ],
     run_checks=["visual", "accessibility"]
   )
```

### Responsive testing
```
User: "Check how example.com looks on mobile, tablet, and desktop"

Claude Code calls:
1. test_responsive(url="https://example.com", run_checks=["visual"])
→ Returns screenshots at 375x812, 768x1024, and 1920x1080
```

### Switch viewport during a session
```
User: "Show me how this page looks on mobile"

Claude Code calls:
1. set_viewport(session_id=..., device="mobile")
→ Returns screenshot at 375x812
```

### Test error handling by mocking an API
```
User: "What happens when the API returns a 500 error?"

Claude Code calls:
1. intercept_network(session_id=..., url_pattern="/api/tasks", status=500,
     body='{"error": "Internal server error"}')
2. reload_page(session_id=...)
3. screenshot_session(session_id=...)
→ Shows how the app handles the error state
```

### Test dark mode
```
User: "Does this site support dark mode?"

Claude Code calls:
1. open_session(url="https://example.com") → session_id
2. test_dark_mode(session_id=..., mode="dark")
→ Screenshot shows the page with prefers-color-scheme: dark
```

### Wait for dynamic content
```
User: "Submit this form and wait for the success message"

Claude Code calls:
1. fill_form(session_id=..., fields=[...], submit_selector="#submit")
2. wait_for_network(session_id=..., url_pattern="/api/submit")
3. screenshot_session(session_id=...)
```

### Test on slow network
```
User: "How does this page load on a slow connection?"

Claude Code calls:
1. emulate_network(session_id=..., preset="slow_3g")
2. reload_page(session_id=...)
3. screenshot_session(session_id=...)
4. emulate_network(session_id=..., preset="reset")
```

## Configuration

Edit `config.py` to change defaults (env-overridable settings note the variable):

| Setting | Default | Description |
|---------|---------|-------------|
| `HEADLESS` | `True` | Run Chrome in headless mode (env: `HEADLESS=false`) |
| `STARTUP_PAUSE` | `10` | Seconds to wait after a non-headless browser opens (env: `STARTUP_PAUSE`) |
| `TIMEOUT` | `30000` | Page load timeout (ms) |
| `VIEWPORT_WIDTH` | `1920` | Browser viewport width |
| `VIEWPORT_HEIGHT` | `1080` | Browser viewport height |
| `CHROMIUM_PATH` | unset | Path to a system Chromium binary (env: `CHROMIUM_PATH`); unset = Playwright's bundled build |
| `WAIT_UNTIL` | `networkidle` | Navigation wait strategy (env: `NAV_WAIT_UNTIL=load` for sites with websockets/polling) |
| `MAX_PAGES` | `20` | Default max pages to crawl |
| `MAX_DEPTH` | `3` | Default max crawl depth |
| `MAX_SESSIONS` | `20` | Max concurrent interactive sessions |
| `SESSION_TIMEOUT` | `300` | Auto-expire idle sessions after N seconds (env: `SESSION_TIMEOUT`) |
| `MAX_RESPONSE_BODY_SIZE` | `512000` | Max bytes captured per response body |
| `MAX_RESPONSE_BODIES` | `100` | Max captured response bodies kept per session |
| `MAX_CONSOLE_LOG` | `500` | Max console entries kept per session |
| `MAX_NETWORK_LOG` | `1000` | Max network log entries kept per session |

## Data Storage

All data is stored in the `data/` directory:

- **`data/projects.json`** - Project configs (name, URL, auth, settings). Auth credentials are stored in plaintext - do not commit this file.
- **`data/screenshots/{project}/`** - PNG screenshots per project. Filenames are `{domain}_{path}_{hash}.png` for static tests, `interactive_{timestamp}_{label}.png` for session screenshots.
- **`data/reports/{project}_{timestamp}.json`** - Full test reports with all findings.
- **`data/videos/{project}/`** - Recorded session videos (WebM format from Playwright).
- **`data/diffs/`** - Screenshot comparison diff images.

## Docker Deployment

### Build and run

```bash
docker compose up -d
```

### Connect Claude Code to Docker container

Update `.mcp.json`:

```json
{
  "mcpServers": {
    "periscope": {
      "command": "docker",
      "args": ["exec", "-i", "periscope", "python", "/app/server.py"]
    }
  }
}
```

### Persist data

The `docker-compose.yml` mounts `./data` as a volume so screenshots, reports, and project configs survive container restarts.

## Key Design Decisions

1. **Per-project browser contexts** - Each project gets its own Playwright BrowserContext. This keeps sessions (cookies, auth) isolated between projects.

2. **Lazy browser init** - The Playwright browser is only launched on the first tool call, not at server startup. If the browser crashes or fails to launch, it re-creates on the next call.

3. **BFS crawling** - The crawler uses breadth-first search with depth tracking. It stays on the same domain and skips non-page resources (images, PDFs, etc.).

4. **Check modularity** - Each check category is a separate module in `checks/`. Add new checks by creating a function that takes a Playwright `Page` and returns `list[dict]`.

5. **JSON storage** - Projects are stored in a single `projects.json` file. No database needed for the expected scale (dozens of projects, not thousands).

6. **Persistent sessions** - Interactive testing uses a `SessionManager` that keeps Playwright pages alive in a dict keyed by session ID. Sessions auto-expire after idle timeout and are capped at a configurable maximum to prevent resource leaks.

7. **Ephemeral vs session mode** - Tools like `get_page_elements`, `interact_and_test`, and `check_links` accept either a `session_id` (reuses an existing page) or a `url` (creates a temporary page that's closed after use). This makes them flexible for both interactive and one-shot use.

## Adding New Checks

1. Create a function in the appropriate `checks/*.py` file:

```python
async def check_something(page: Page) -> list[dict]:
    # Run your check
    result = await page.evaluate("() => { ... }")

    issues = []
    if result:
        issues.append({
            "type": "your_category",   # visual, accessibility, seo, etc.
            "severity": "error",       # error, warning, info
            "message": "Description",
            "details": []              # optional
        })
    return issues
```

2. Import and call it in `tester.py` inside `test_url()`.

## Known Limitations

- No JavaScript SPA routing support (relies on `<a href>` for crawling)
- Default `check_functionality` link checking limited to 20 internal links (use `check_links` tool for up to 100 with external support)
- Form login detection uses CSS selectors, may need customization for non-standard forms
- No parallel page testing (pages are tested sequentially)
- Interactive sessions auto-expire after 300s idle (configurable via `SESSION_TIMEOUT`)
- Max 20 concurrent sessions (configurable via `MAX_SESSIONS`)
- Drag and drop doesn't work via Playwright automation with some libraries (known limitation with `@hello-pangea/dnd` and similar React DnD libs — not a bug in this tool)
- Date/time inputs are filled with React-compatible synthetic events automatically (`fill`, `force_fill`, `auto_fill_form`)

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Executable doesn't exist` | Run `playwright install chromium` |
| `'NoneType' has no attribute 'new_context'` | Browser failed to launch. Check Chromium is installed. Server will auto-retry on next call. |
| Login not working | Try providing explicit CSS selectors via `username_selector`, `password_selector`, `submit_selector` |
| Timeout on page load | Increase `TIMEOUT` in `config.py` or check if site requires VPN/auth |
| Docker can't reach website | Ensure the container has network access. Use `network_mode: host` if testing localhost |

## Development

```bash
pip install -r requirements-dev.txt
pytest            # unit tests, no browser required
```

Adding a new tool: define its schema in `tool_schemas.py`, then add a handler in the
matching `handlers/<category>.py` decorated with `@tool("your_tool_name")`. The
registry test (`tests/test_registry.py`) fails if schemas and handlers drift apart.

## License

GNU AGPL-3.0 — see [LICENSE](LICENSE).
