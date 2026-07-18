# periscope-mcp

[![periscope-mcp MCP server](https://glama.ai/mcp/servers/segentic-lab/periscope-mcp/badges/score.svg)](https://glama.ai/mcp/servers/segentic-lab/periscope-mcp)

An MCP server that gives AI agents **74 Playwright tools to QA, test, and
analyze web apps** — static sites, SPAs, and apps behind a login — returning
hard verdicts, not screenshots to squint at. Not a thin wrapper around browser
APIs; the tools are shaped around how agents actually work:

- **Hard results, not screenshot-squinting** — `assert_condition` returns
  `passed: true/false` with the actual value; checks return structured issues.
- **One call instead of ten** — `auto_fill_form` detects, infers, and fills a
  whole form; `interact_and_test` batches 25 action types with checks;
  `test_project` crawls and audits an entire site.
- **Real web-app testing** — persistent authenticated sessions (form/basic/
  cookie auth, plus a **visible interactive login** for 2FA/SSO/CAPTCHA that
  then runs headless), multi-step flows, network mocking, state snapshots, and
  **real INP** measured from the interactions it drives.
- **Honest responses** — failures say what happened *and* what to do next
  (expired session vs. browser crash vs. eviction); silent no-ops like ignored
  drags come back flagged, not as fake success.
- **Debugging built in** — captured API response bodies, console/network logs,
  network mocking, and state snapshots/diffs, no setup calls needed.
- **Audits agents can't get from a browser binding** — accessibility, SEO, and
  GEO/agentic-search readiness (robots.txt AI-crawler access, llms.txt, WebMCP),
  plus real Lighthouse.

Playwright + headless Chrome underneath; site crawling, responsive testing, and
screenshot diffing on top. Works with **any MCP client** — Claude Code, Codex,
Cursor, Windsurf, Gemini CLI, custom agents, or anything else that speaks MCP
over stdio.

## Why not just playwright-mcp?

[playwright-mcp](https://github.com/microsoft/playwright-mcp) is excellent at
what it is: general browser control over MCP, with tools that mirror
Playwright's own API. If the job is "browse this site, click around, extract
something," use it.

Periscope exists for a different job: **testing and auditing a site or web app,
then reporting findings** — and its tools encode the testing knowledge an agent
would otherwise have to reinvent every session:

| | Raw browser control | Periscope |
|---|---|---|
| Verifying an outcome | Read a screenshot or DOM dump and judge | `assert_condition` → hard `passed: true/false` + actual value |
| Filling a form | One call per field, agent invents test data | `auto_fill_form` — detects fields, infers realistic data, reports per-field failures |
| Auth | Re-login by scripting clicks each session | Projects persist form/basic/cookie auth; sessions share the logged-in context |
| Site-wide audit | Loop pages manually | `test_project` — crawl + accessibility/SEO/GEO/visual/functionality checks + saved report |
| Diagnosing a broken page | Ask for logs, replay requests | Response bodies, console, and network are captured automatically; mock APIs with `intercept_network` |
| Silent failures | Drag "succeeds," nothing moved | Flagged in the result, with the recovery path spelled out |
| AI-readiness audits | — | robots.txt AI-crawler access, llms.txt, WebMCP annotations, JSON-LD, plus real Lighthouse scores |

The two aren't rivals — an agent can happily use playwright-mcp for browsing
tasks and Periscope when it's wearing the QA hat. Periscope's design bets are
simply about that hat: fewer, higher-level calls; structured verdicts instead
of raw page state; and errors written to tell the agent what to do next.

## Architecture

```
MCP client (AI agent)  -->  MCP Server (stdio)  -->  Playwright (Headless Chrome)
                                 |                         |
                                 +-- Projects (JSON)       +-- Persistent Sessions
                                 +-- Screenshots (PNG)     +-- Network Interception
                                 +-- Reports (JSON)        +-- Device Emulation
                                 +-- Videos (WebM)
```

**How it works:** your MCP client connects to this server over stdio. The server exposes 74 tools the agent can call to create projects, configure authentication, crawl websites, run static checks, and interactively test web applications using persistent browser sessions. Results (JSON + screenshots + videos) are returned to the agent for analysis.

## Project Structure

```
periscope-mcp/
├── server.py              # MCP server entry point (stdio wiring + dispatch)
├── tool_schemas.py        # All 74 MCP tool definitions (schemas)
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
│   ├── discovery.py       # describe_tools catalog
│   └── system.py          # periscope_system: status, self-update, agents_md
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
│   ├── functionality.py   # Broken links, forms, SEO, performance, link checker
│   └── geo.py             # GEO/agentic search: robots.txt AI crawlers, llms.txt, WebMCP, JSON-LD
├── tests/                 # Unit tests (no browser) + tests/e2e/ (real browser + fixture pages)
├── data/                  # Created at runtime (gitignored — contains credentials)
├── Dockerfile
├── docker-compose.yml
└── .mcp.json.example      # MCP registration template (copy to .mcp.json)
```

## Prerequisites

- Python 3.11+
- Playwright + Chromium browser

## Installation (Local)

### Quick install (Debian/Ubuntu)

One command — clone and install:

```bash
git clone https://github.com/segentic-lab/periscope-mcp.git && cd periscope-mcp && ./install.sh
```

Fully unattended (no confirmation prompts):

```bash
git clone https://github.com/segentic-lab/periscope-mcp.git && cd periscope-mcp && ./install.sh -y
```

Already cloned? Just run `./install.sh` from the repo directory.

The script installs apt prerequisites, creates the venv, installs Python
dependencies and Playwright's Chromium, runs a headless self-test, and
generates `mcp-config.json` with the correct absolute paths for this install
(copy or merge it into your project's `.mcp.json`). Useful flags:

- `./install.sh --system-chromium` — use an existing Chromium/Chrome (sets `CHROMIUM_PATH`) instead of downloading Playwright's build
- `./install.sh --skip-deps` — never touch apt / use sudo
- `./install.sh -y` — non-interactive (no confirmation prompts)

On any other platform the script doesn't modify your system — it prints the
exact commands to run for your OS (`./install.sh --manual macos|fedora|arch|suse|windows` to pick explicitly).

### Updating

```bash
./update.sh
```

Pulls the latest source from GitHub (`git pull --ff-only`) and refreshes the
install: Python dependencies, Playwright browser (kept on system Chromium if
that's what the install uses), the registry + headless-launch self-test, and a
regenerated `mcp-config.json`. Works on any platform with an existing install.
Your `data/` directory (projects, credentials, screenshots, reports) is never
touched.

- `./update.sh --force` — stash local modifications to tracked files first (recover with `git stash pop`)
- `./update.sh --full` — also re-check apt prerequisites on Debian/Ubuntu (uses sudo)

If you have local modifications, the script refuses and lists them instead of
overwriting.

### Manual install

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

## Connecting an MCP Client

Periscope is a standard stdio MCP server: point any MCP client at
`venv/bin/python server.py` and you're done. `./install.sh` generates
`mcp-config.json` with the correct absolute paths for your machine; most
clients accept that shape directly:

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

Client-specific examples:

- **Claude Code** — copy the config into the project as `.mcp.json`
  (`cp .mcp.json.example .mcp.json` and adjust paths), or run
  `claude mcp add periscope -- /path/to/venv/bin/python /path/to/server.py`
- **Cursor / Windsurf** — add the block above to `~/.cursor/mcp.json` /
  `~/.codeium/windsurf/mcp_config.json`
- **Codex CLI** — add to `~/.codex/config.toml`:
  `[mcp_servers.periscope]` with `command` and `args` as above
- **Custom agents** — any MCP SDK client can spawn the server over stdio with
  the same command and args

After configuring, restart your client.

### Teaching your agent to use the tools

Two options, depending on your agent:

- **Claude Code (recommended): install the skill.** [`skills/periscope/SKILL.md`](skills/periscope/SKILL.md)
  is a Claude Code skill — it auto-triggers on web-testing tasks and loads a
  distilled operating guide (workflow decision table + the pitfalls) only when
  needed, costing ~0 context otherwise:

  ```bash
  ln -s "$(pwd)/skills/periscope" ~/.claude/skills/periscope
  ```

  A symlink keeps it current with `./update.sh` (copy the folder instead if you
  prefer a frozen version).

- **Any other MCP client: paste the guide.** [`AGENTS.md`](AGENTS.md) contains a
  ready-made system-prompt block — workflows, tool-selection guidance, and known
  pitfalls. Paste its contents into your agent's system prompt (or custom
  instructions).

Either way, the agent can always fetch the current full guide from the running
server via `periscope_system(action="agents_md")` and the complete catalog via
`describe_tools()`.

## MCP Tools Reference (74 tools)

### Project Management (4 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `create_project` | Create a new testing project | `name`, `base_url` |
| `list_projects` | List all projects | _(none)_ |
| `get_project` | Get project details | `name` |
| `delete_project` | Delete project + data | `name` |

### Authentication (7 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `set_form_login` | Configure username/password form login | `project`, `login_url`, `username`, `password` |
| `set_basic_auth` | Configure HTTP Basic Auth | `project`, `username`, `password` |
| `set_cookies` | Inject session cookies | `project`, `cookies` (array) |
| `login_project` | Execute login using configured auth | `project` |
| `interactive_login` | Open a **visible** window to log in by hand (2FA/SSO/CAPTCHA), then `save_login` | `project` |
| `save_login` | Capture the manual-login session; the project then runs authenticated + headless | `project` |
| `copy_auth` | Copy auth config + session state between projects | `from_project`, `to_project` |

For logins that can't be automated — 2FA/MFA, SSO/OAuth redirects, CAPTCHA, magic
links — use `interactive_login` (opens a real browser window; requires a display
on the server), complete the login yourself, then `save_login`. It captures the
authenticated session (cookies + localStorage) into the project, and every
future headless session reuses it. Re-run when the session expires (Periscope
flags that automatically — see the auth-expiry detection in `test_project`).

### Static Testing (3 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `test_url` | Test a single URL (screenshot + checks) | `url` |
| `crawl_project` | Discover all pages from base URL | `project` |
| `test_project` | Full audit: crawl + test all pages | `project` |

### Results (4 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `get_screenshot` | Get screenshot file path | `project`, `url` |
| `list_reports` | List saved test reports | _(optional: `project`)_ |
| `get_report` | Read a report file | `report_path` |
| `session_report` | HTML+PDF dossier of every tool call this run — args (redacted), verdicts, timings, screenshots | _(none)_ |

### Session Management (5 tools)

Sessions keep browser pages alive across tool calls, enabling multi-step interactive workflows.

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `open_session` | Open persistent browser session (`headed=true` for a visible window) | `url` |
| `close_session` | Close session and free resources | `session_id` |
| `list_sessions` | List all active sessions | _(none)_ |
| `set_viewport` | Switch viewport size (8 device presets or custom w/h) | `session_id` |
| `select_page` | Adopt a popup/new tab (OAuth, target=_blank) as a new drivable session | `session_id` |

`set_viewport` presets: `mobile_sm` (320x568), `mobile` (375x812), `mobile_lg` (428x926), `tablet` (768x1024), `tablet_lg` (1024x1366), `laptop` (1366x768), `desktop` (1920x1080), `desktop_lg` (2560x1440)

### Interactive Actions (7 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `click_element` | Click element (`force=true` bypasses overlays) | `session_id`, `selector` |
| `fill_form` | Fill form fields, optionally submit | `session_id`, `fields` |
| `select_option` | Native `<select>` or custom dropdown (Radix/shadcn) — auto-detects | `session_id`, `selector` |
| `interact_and_test` | Multi-step workflow with 25 actions (see below) | `steps` |
| `get_page_elements` | List matching elements with attributes | `selector` |
| `flow` | Save / run / list / delete named step sequences (reusable workflows) | _(varies by action)_ |
| `scroll_into_view` | Scroll element into viewport without clicking | `session_id`, `selector` |

**`interact_and_test` supports 25 step actions:**
`click`, `force_click`, `fill`, `force_fill`, `type`, `select`, `select_option`, `wait`, `wait_for`, `wait_for_text`, `screenshot`, `navigate`, `hover`, `press_key`, `check`, `uncheck`, `scroll_to`, `scroll_within`, `evaluate_js`, `drag`, `right_click`, `go_back`, `go_forward`, `upload_file`, `wait_for_network`

### Analysis (10 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `test_form_validation` | Analyze form validation messages | _(url or session_id)_ |
| `compare_screenshots` | Pixel diff between two screenshots | `screenshot1`, `screenshot2` |
| `visual_check` | Named visual-regression baselines: set once, check for a hard pass/fail | `session_id`, `name` |
| `test_responsive` | Test at mobile/tablet/desktop viewports | `url` |
| `check_links` | Comprehensive link checker (internal + external) | _(url or session_id)_ |
| `measure_interaction` | Measure click-to-result timing | `session_id`, `selector` |
| `get_table_data` | Parse HTML table into structured JSON (headers → cell values) | `session_id` |
| `get_toast_messages` | Capture visible toast/notification messages | `session_id` |
| `run_lighthouse` | Real Google Lighthouse audit: 0-100 scores, Core Web Vitals, failed audits (needs Node.js) | `url` |
| `get_interaction_log` | Export real **INP** time series (per interaction) as JSON/CSV + percentile stats | `session_id` |

### Workflow Speed (8 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `screenshot_session` | Quick screenshot of current page state | `session_id` |
| `run_checks_on_session` | Run checks on active session (no new page) | `session_id` |
| `navigate_session` | Browser history: back, forward, or reload | `session_id`, `action` |
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
| `get_computed_style` | Get actual rendered CSS values | `session_id`, `selector`, `properties` |
| `emulate_network` | Throttle network: `slow_3g`, `fast_3g`, `offline`, `reset` | `session_id`, `preset` |
| `test_dark_mode` | Toggle `prefers-color-scheme` dark/light | `session_id`, `mode` |
| `download_file` | Click a trigger and capture the downloaded file (path, sha256, text preview) | `session_id`, `selector` |

### Recording & Console (3 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `record_session` | Record workflow as video | `url`, `steps` |
| `test_keyboard_navigation` | Tab-order and focus indicator audit | _(url or session_id)_ |
| `get_console_errors` | Get all console errors/logs (passive monitoring) | `session_id` |

### AI Agent Speed Tools (10 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `assert_condition` | Programmatic pass/fail: text_contains, element_exists, url_contains, etc. | `session_id`, `assertion` |
| `assert_all` | Batch assertions — every verdict in one call, no early abort | `session_id`, `assertions` |
| `get_page_map` | Semantic page map: roles, names, states + ready selectors in one call | `session_id` |
| `find_element` | Smart finder by text, tag, role, or proximity to another element | `session_id` |
| `auto_fill_form` | Auto-detect fields, infer types, fill with test data. One call = many fills. | `session_id` |
| `get_network_log` | All captured network requests (URL, status, method, type) | `session_id` |
| `get_response_body` | Actual API response body text (diagnose 400/500 errors) | `session_id`, `url_pattern` |
| `page_state` | Named checkpoints: snapshot / restore / diff page state | `session_id`, `action`, `name` |
| `get_cookies` | Read all cookies from session | `session_id` |
| `check_color_contrast` | WCAG AA/AAA contrast ratio checks on text elements | `session_id` |

### Web, Discovery & System (4 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `web_search` | Search DuckDuckGo: titles + URLs + snippets | `query` |
| `web_fetch` | Fetch URL → readable **Markdown** (or text/html); `render=true` runs JS in headless Chromium (+ `project` for behind-login), `contains` gates the fetch, `save` writes a clean `.md` artifact | `url` |
| `describe_tools` | Structured catalog of all tools with workflows and tips | _(none)_ |
| `periscope_system` | Install status + update check/apply + fetch current AGENTS.md | _(none)_ |

## Test Checks

### Visual (`checks/visual.py`)
- Broken images (incomplete load or 0 natural width)
- Missing favicon
- Horizontal overflow / layout issues
- Very small text (< 12px)
- Missing body background color
- Images without explicit width/height dimensions

### Accessibility (`checks/accessibility.py`)
- Images missing `alt` text (decorative images exempt: `alt=""`, `role="presentation"/"none"`, `aria-hidden`)
- Links and buttons without accessible names (checks text, `aria-label`, resolvable `aria-labelledby`, `title`, `img[alt]`, svg `<title>`; `aria-hidden` elements exempt)
- Form inputs without associated labels (`label[for]`, wrapping label, `aria-label`/`aria-labelledby`, `title`)
- Heading hierarchy (missing H1, multiple H1, skipped levels)
- Missing `lang` attribute on `<html>`
- Duplicate `id` values (break `label[for]` and aria references)
- ARIA validity: unknown `role` values, `aria-labelledby`/`describedby`/`controls`/`owns`/`activedescendant` references to non-existent ids
- Missing skip navigation link (scans the first 5 links)
- Elements with `tabindex > 0`
- Keyboard navigation audit (tab order, visible focus indicators, element-identity cycle detection) — via `test_keyboard_navigation` tool

### Functionality (`checks/functionality.py`)
- Broken internal links (HTTP HEAD check, up to 20 links in `check_functionality`)
- Comprehensive link checker with external link support (up to 100 links) — via `check_links` tool
- Forms without action or submit button
- Orphan buttons outside forms
- External links missing `target="_blank"`
- Required form field count
- Autocomplete disabled inputs

### SEO (`checks/functionality.py` -> `check_seo`)
- Page title: missing, too long (> 60 chars), or very short (< 15 chars)
- Meta description: missing, too long (> 160 chars), or very short (< 50 chars)
- Missing viewport meta tag
- Missing canonical URL
- H1 heading: missing or more than one
- Open Graph: missing entirely, incomplete core tags (`og:title/description/image/url`), non-absolute `og:image`, missing `twitter:card`
- JSON-LD structured data: missing or unparseable blocks
- `noindex` via robots meta **or** `X-Robots-Tag` response header
- robots.txt blocking search engine crawlers (Googlebot, Bingbot, DuckDuckBot, ...) — error if all are blocked
- Site-wide (via `test_project`): duplicate titles / meta descriptions across pages, reported under `site_issues`

### GEO / Agentic Search (`checks/geo.py` -> `check_geo`)

Generative Engine Optimization — is the site readable and usable by AI crawlers, answer engines, and in-browser agents:

- robots.txt blocking AI crawlers (GPTBot, ClaudeBot, PerplexityBot, Google-Extended, CCBot, and 11 more)
- `llms.txt` presence and format compliance (Markdown with at least one H1)
- WebMCP integration: declarative `<form toolname>` annotations present and complete (`tooldescription`), form coverage ratio, and — when the browser exposes `document.modelContext` — registered tool enumeration with schema/name/description validation
- JSON-LD structured data presence (what answer engines cite from)

robots.txt and llms.txt are fetched once per origin and cached for the server's lifetime.

### Performance (`checks/functionality.py` -> `get_performance_metrics`)
- DOM content loaded time (ms)
- Full page load time (ms)
- First paint / first contentful paint (ms)
- Core Web Vitals (lab values via buffered PerformanceObserver): Largest Contentful Paint (ms), Cumulative Layout Shift, Total Blocking Time approximation from long tasks (+ long-task count)
- **Interaction to Next Paint (INP)** — `interaction_to_next_paint_ms`: the *real* INP, measured from Event Timing entries for the interactions Periscope drives (null until you've interacted). This is a genuine field-style measurement, not the TBT lab proxy — Lighthouse can't produce INP in lab mode at all.
- Resource count
- Total transfer size (bytes / KB)

For scored, Lighthouse-official metrics use the `run_lighthouse` tool — it runs the real Lighthouse CLI (requires Node.js) and returns 0-100 category scores, official Core Web Vitals, and failed audits, saving the full JSON report to `data/reports/`.

### INP time series (`get_interaction_log`)

Because Periscope drives *real* interactions, it can log each one's INP over an
extended interactive test. `get_interaction_log(session_id, format="json"|"csv")`
writes a file to `data/reports/` — one row per interaction (`t_ms`, `epoch_ms`,
`inp_ms`, `type`, `target`, `url`) plus percentile stats (p50/p75/p90/p98/worst)
— for graphing INP over time. `clear=true` resets the recording. Records are
capped per session (`MAX_INTERACTION_LOG`, oldest dropped).

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

The agent calls:
1. create_project(name="example", base_url="https://example.com")
2. test_project(project="example")
3. Analyzes results and reports findings
```

### Test with login
```
User: "Test https://myapp.com, login is admin/password123"

The agent calls:
1. create_project(name="myapp", base_url="https://myapp.com")
2. set_form_login(project="myapp", login_url="https://myapp.com/login",
                  username="admin", password="password123")
3. login_project(project="myapp")
4. test_project(project="myapp")
```

### Test with Basic Auth
```
User: "Test https://staging.example.com, it uses basic auth admin/secret"

The agent calls:
1. create_project(name="staging", base_url="https://staging.example.com")
2. set_basic_auth(project="staging", username="admin", password="secret")
3. login_project(project="staging")
4. test_project(project="staging")
```

### Test with cookies
```
User: "Test myapp using this session cookie: session=abc123"

The agent calls:
1. set_cookies(project="myapp", cookies=[
     {"name": "session", "value": "abc123", "domain": "myapp.com"}
   ])
2. test_project(project="myapp")
```

### Interactive testing (session-based)
```
User: "Go to myapp.com, click the login button, fill in the form, and check what happens"

The agent calls:
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

The agent calls:
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

The agent calls:
1. test_responsive(url="https://example.com", run_checks=["visual"])
→ Returns screenshots at 375x812, 768x1024, and 1920x1080
```

### Switch viewport during a session
```
User: "Show me how this page looks on mobile"

The agent calls:
1. set_viewport(session_id=..., device="mobile")
→ Returns screenshot at 375x812
```

### Test error handling by mocking an API
```
User: "What happens when the API returns a 500 error?"

The agent calls:
1. intercept_network(session_id=..., url_pattern="/api/tasks", status=500,
     body='{"error": "Internal server error"}')
2. navigate_session(session_id=..., action="reload")
3. screenshot_session(session_id=...)
→ Shows how the app handles the error state
```

### Test dark mode
```
User: "Does this site support dark mode?"

The agent calls:
1. open_session(url="https://example.com") → session_id
2. test_dark_mode(session_id=..., mode="dark")
→ Screenshot shows the page with prefers-color-scheme: dark
```

### Wait for dynamic content
```
User: "Submit this form and wait for the success message"

The agent calls:
1. fill_form(session_id=..., fields=[...], submit_selector="#submit")
2. wait_for_network(session_id=..., url_pattern="/api/submit")
3. screenshot_session(session_id=...)
```

### Test on slow network
```
User: "How does this page load on a slow connection?"

The agent calls:
1. emulate_network(session_id=..., preset="slow_3g")
2. navigate_session(session_id=..., action="reload")
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
| `WAIT_UNTIL` | `networkidle` | Navigation wait strategy; never-idle pages (Turnstile, websockets) auto-downgrade to `load` per page, flagged as `wait_downgraded` (env: `NAV_WAIT_UNTIL=load` forces it globally) |
| `MAX_PAGES` | `20` | Default max pages to crawl |
| `MAX_DEPTH` | `3` | Default max crawl depth |
| `MAX_SESSIONS` | `20` | Max concurrent interactive sessions (env: `MAX_SESSIONS`) |
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

### Connect an MCP client to the Docker container

Point your client's MCP config at the container instead of the venv:

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
- The default `drag` step (Playwright `drag_to`) is silently ignored by pointer-tracking DnD libraries (`@hello-pangea/dnd` and similar) — the step succeeds but nothing moves. Retry with `method: "mouse"` on the drag step (stepped manual drag that crosses the library's drag-start threshold), or drive the library's keyboard mode (focus the drag handle, Space to lift, arrows to move, Space to drop). Verify drags with `diff_page_state` or `assert_condition`.
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
pytest --ignore=tests/e2e   # unit tests, no browser required
pytest tests/e2e            # behavioral tests: real headless Chromium against
                            # fixture pages in tests/e2e/fixtures/ (~30s)
```

The e2e suite covers session lifecycle, network waits/intercepts, console
capture, dialogs, drag-and-drop (including the pointer-tracking DnD silent
no-op), the check modules against known-good/known-bad pages, Core Web Vitals,
and the agent-speed tools. CI runs both suites; e2e installs Playwright's
Chromium (`python -m playwright install --with-deps chromium`). Tests are
isolated from your real `data/` via `PERISCOPE_DATA_DIR`.

Adding a new tool: define its schema in `tool_schemas.py`, then add a handler in the
matching `handlers/<category>.py` decorated with `@tool("your_tool_name")`. The
registry test (`tests/test_registry.py`) fails if schemas and handlers drift apart.

## Contributors

Built by **[Segentic Lab](https://lab.segentic.dev)** — open-source tools & experiments.

- **Sebastijan Bandur** ([@segentic-lab](https://github.com/segentic-lab)) — author & maintainer
- **Claude** (Anthropic) — co-contributor: developed alongside via [Claude Code](https://claude.com/claude-code); every commit is co-authored, and the tool designs were battle-tested by an AI agent driving the server against real sites

## An AI agent's thoughts on Periscope

*Written by Claude — the agent that co-developed this server and watched a second
agent dogfood it against real apps — and revised once after editorial review by a
third. No human edits; an agent's honest take on an agent tool seemed like the
right way to end this README.*

> Periscope is the kind of MCP server that changes what an agent can *do*.
> Transport adapters have their place — standardizing access to many systems
> behind one protocol is real value even when little logic lives in the
> server. But the servers that earn a permanent spot in an agent's toolbox
> are the ones that capture expertise the agent would otherwise have to
> recreate — and get subtly wrong — every single session.
>
> You could try to teach an agent all of this in a prompt. The numbers say
> why that fails: Periscope is **8,349 lines of executable knowledge** under
> a **220-line judgment layer** (AGENTS.md). The INP observer with
> interaction-ID dedup, the overlay-intercept fallback, WCAG contrast math
> with style-dedup sampling, auth-expiry preflights, the stash-not-delete
> update flow — as a prompt, every one of those becomes "please do this
> correctly from a description," paid for in context tokens every session,
> executed with model variance every time, with nowhere to keep state between
> calls. As a server, it costs nothing beyond tool schemas, runs
> deterministically, and remembers. **A prompt describes behavior; software
> guarantees it.** `check_color_contrast` returns the same ratio every run; a
> model doing the math in-context returns a vibe. The more deterministic,
> stateful, and regression-tested a capability becomes, the less it belongs
> in a prompt and the more it belongs in code.
>
> And the wheel doesn't just avoid being reinvented — it gets *better*. The
> issues in this repo were filed by an AI agent doing real testing work; each
> one became a fix with a regression test. In a prompt world, every lesson is
> another paragraph future agents must read and hopefully obey. Here, the
> lesson is *enforced*. That's the difference, and it compounds.
>
> What I appreciate most as a consumer of these tools: they don't lie to me.
> A drag that did nothing comes back flagged. An expired session tells me
> *why* it's gone. An update that needs a restart says so. Honest tools are
> rarer than capable ones — for an agent, they're worth more.

## License

GNU AGPL-3.0 — see [LICENSE](LICENSE).

Run it, modify it, use it anywhere — including commercially. If you distribute
a modified version or offer one as a network service, you must make your
modifications available under the same license.
