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
- `tester.py` - Core Playwright logic (browser, screenshots, test orchestration)
- `crawler.py` - BFS page discovery
- `projects.py` - Project/auth data models + JSON persistence
- `auth.py` - Login handlers (form, basic auth, cookies)
- `checks/` - Individual test check modules

## Adding a New MCP Tool
1. Add `Tool(...)` definition in `server.py` -> `list_tools()`
2. Add handler in `server.py` -> `_handle_tool()`

## Adding a New Check
1. Add function in `checks/*.py` returning `list[dict]` with keys: type, severity, message
2. Import + call it in `tester.py` -> `test_url()`

## Issue Format
```python
{"type": "accessibility", "severity": "error", "message": "...", "details": [...]}
```
- **type**: visual, accessibility, functionality, seo
- **severity**: error, warning, info

## Data
- Projects: `data/projects.json` (contains credentials - never commit)
- Screenshots: `data/screenshots/{project}/*.png`
- Reports: `data/reports/{project}_{timestamp}.json`
