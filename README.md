# WebsiteTesterAI

An MCP (Model Context Protocol) server that gives Claude Code AI-powered website testing tools. It uses Playwright with headless Chrome to crawl websites, take screenshots, and run automated checks for visual issues, accessibility, SEO, performance, and functionality.

## Architecture

```
Claude Code  -->  MCP Server (stdio)  -->  Playwright (Headless Chrome)
                       |
                       +-- Projects (JSON storage)
                       +-- Screenshots (PNG files)
                       +-- Reports (JSON files)
```

**How it works:** Claude Code connects to this MCP server over stdio. The server exposes tools that Claude Code can call to create projects, configure authentication, crawl websites, and run tests. Results (JSON + screenshots) are returned to Claude Code for analysis.

## Project Structure

```
WebsiteTesterAI/
├── server.py              # MCP server entry point + tool definitions
├── tester.py              # Playwright browser control + test orchestration
├── crawler.py             # Page discovery (BFS crawl, same-domain only)
├── projects.py            # Project CRUD + auth config storage
├── auth.py                # Authentication handlers (form, basic, cookies)
├── config.py              # Global settings (timeouts, paths, defaults)
├── requirements.txt       # Python dependencies
├── checks/
│   ├── __init__.py
│   ├── visual.py          # Broken images, favicon, overflow, small text
│   ├── accessibility.py   # Alt text, labels, headings, lang, ARIA
│   └── functionality.py   # Broken links, forms, SEO, performance metrics
├── data/                  # Created at runtime
│   ├── projects.json      # Project configurations
│   ├── screenshots/       # Per-project screenshot directories
│   └── reports/           # JSON test reports
├── Dockerfile
├── docker-compose.yml
└── .mcp.json              # Claude Code MCP server registration
```

## Prerequisites

- Python 3.11+
- Playwright + Chromium browser

## Installation (Local)

```bash
# Clone the repo
cd WebsiteTesterAI

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

The `.mcp.json` file in the project root registers the server. Just open Claude Code in this directory:

```json
{
  "mcpServers": {
    "website-tester": {
      "command": "/path/to/WebsiteTesterAI/venv/bin/python",
      "args": ["/path/to/WebsiteTesterAI/server.py"]
    }
  }
}
```

### Option 2: Global config

Add to `~/.claude.json` under the project's `mcpServers` key:

```json
"mcpServers": {
  "website-tester": {
    "command": "/path/to/WebsiteTesterAI/venv/bin/python",
    "args": ["/path/to/WebsiteTesterAI/server.py"]
  }
}
```

After configuring, restart Claude Code.

## MCP Tools Reference

### Project Management

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `create_project` | Create a new testing project | `name`, `base_url` |
| `list_projects` | List all projects | _(none)_ |
| `get_project` | Get project details | `name` |
| `delete_project` | Delete project + data | `name` |

### Authentication

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `set_form_login` | Configure username/password form login | `project`, `login_url`, `username`, `password` |
| `set_basic_auth` | Configure HTTP Basic Auth | `project`, `username`, `password` |
| `set_cookies` | Inject session cookies | `project`, `cookies` (array) |
| `login_project` | Execute login using configured auth | `project` |

### Testing

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `test_url` | Test a single URL (screenshot + checks) | `url` |
| `crawl_project` | Discover all pages from base URL | `project` |
| `test_project` | Full audit: crawl + test all pages | `project` |

### Results

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `get_screenshot` | Get screenshot file path | `project`, `url` |
| `list_reports` | List saved test reports | _(optional: `project`)_ |
| `get_report` | Read a report file | `report_path` |

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

### Functionality (`checks/functionality.py`)
- Broken internal links (HTTP HEAD check, up to 20 links)
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

### Test with cookies
```
User: "Test myapp using this session cookie: session=abc123"

Claude Code calls:
1. set_cookies(project="myapp", cookies=[
     {"name": "session", "value": "abc123", "domain": "myapp.com"}
   ])
2. test_project(project="myapp")
```

## Configuration

Edit `config.py` to change defaults:

| Setting | Default | Description |
|---------|---------|-------------|
| `HEADLESS` | `True` | Run Chrome in headless mode |
| `TIMEOUT` | `30000` | Page load timeout (ms) |
| `VIEWPORT_WIDTH` | `1920` | Browser viewport width |
| `VIEWPORT_HEIGHT` | `1080` | Browser viewport height |
| `MAX_PAGES` | `20` | Default max pages to crawl |
| `MAX_DEPTH` | `3` | Default max crawl depth |

## Data Storage

All data is stored in the `data/` directory:

- **`data/projects.json`** - Project configs (name, URL, auth, settings). Auth credentials are stored in plaintext - do not commit this file.
- **`data/screenshots/{project}/`** - PNG screenshots per project. Filenames are `{domain}_{path}_{hash}.png`.
- **`data/reports/{project}_{timestamp}.json`** - Full test reports with all findings.

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
    "website-tester": {
      "command": "docker",
      "args": ["exec", "-i", "website-tester", "python", "/app/server.py"]
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
- Performance metrics use deprecated `performance.timing` API
- No color contrast ratio checking (would need computed styles analysis)
- Link checking limited to 20 links per page to avoid rate limiting
- Form login detection uses CSS selectors, may need customization for non-standard forms
- No parallel page testing (pages are tested sequentially)

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Executable doesn't exist` | Run `playwright install chromium` |
| `'NoneType' has no attribute 'new_context'` | Browser failed to launch. Check Chromium is installed. Server will auto-retry on next call. |
| Login not working | Try providing explicit CSS selectors via `username_selector`, `password_selector`, `submit_selector` |
| Timeout on page load | Increase `TIMEOUT` in `config.py` or check if site requires VPN/auth |
| Docker can't reach website | Ensure the container has network access. Use `network_mode: host` if testing localhost |
