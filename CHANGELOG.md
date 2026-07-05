# Changelog

All notable changes to Periscope are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). The version is
defined once in [`_version.py`](_version.py) and reported to MCP clients during the
initialize handshake.

## [0.9.5] - 2026-07-05

### Added
- **`periscope_system` — self-maintenance tool** (67th tool, new "system"
  category). One tool, three actions:
  - `status` (read-only): running vs on-disk version, git commit, install type
    (git / managed), capabilities (Node for Lighthouse, display for headed
    sessions, Chromium), active session count, and an update-availability
    check — everything a bug report or a "what am I running?" needs, with no
    shell access to the install required.
  - `agents_md` (read-only): returns the **current** AGENTS.md so an agent can
    refresh a stale pasted copy of its operating guide after an update.
  - `update`: dry-run by default (commits behind + incoming changes);
    `apply=true` wraps `update.sh` (git pull + deps, `data/` untouched).
    Honest about process semantics: new code loads only after the MCP server
    restarts (`restart_required`), and managed/Docker installs refuse in-place
    update with rebuild guidance.
- AGENTS.md gains a "Keeping Periscope and this guide current" section; the
  bug-report flow now gets version+commit from `periscope_system` instead of
  requiring shell access.

## [0.9.4] - 2026-07-05

Second test-agent batch: five issues (#15-#19) filed by the AI agent driving
Periscope against a real authenticated Next.js app — all fixed with
regression tests (9 new e2e tests against a new overlay/select fixture).

### Fixed
- **#15 — Portal overlays no longer block clicks.** When a Radix/shadcn
  full-screen portal overlay (`fixed inset-0`) intercepts the pointer,
  `click_element` and `interact_and_test` click steps automatically fall back
  to an element-level JS dispatch click and flag the result
  (`click_method: "js_dispatch"`, `overlay_bypassed: true`). This was ~30% of
  interactions on Radix apps needing an `evaluate_js` workaround.
- **#17 — `measure_interaction` no longer under-measures async handlers.**
  New `wait_for_network` (URL substring) binds the measurement to that
  response's completion (armed before the click, so fast responses aren't
  missed); the result now states exactly what was measured (`measures`) and
  includes the click's real `interaction_to_next_paint_ms`.
- **#19 — Missing step fields now fail with an actionable message.** A step
  lacking a required field (e.g. `wait_for_network` without `url_pattern`)
  reports `missing required field 'url_pattern' for action 'wait_for_network'`
  instead of a bare KeyError; the standalone tool validates up front.

### Added
- **#16 — `element_index` on `select_option`** (tool + step): target the Nth
  match of a selector for pages with multiple attribute-less `<select>`
  elements; Playwright `>>` syntax is rejected with a pointer to
  `element_index`, and out-of-range indexes report the match count.

### Changed
- **#18 — `url_pattern`/`url_filter` semantics documented everywhere**: plain
  substring against the full URL incl. query string — never regex/glob. On a
  miss, `get_response_body` now returns the captured candidate URLs
  (`captured_urls`) and `get_network_log` adds a semantics note, so pattern
  debugging takes one round-trip.

## [0.9.3] - 2026-07-04

### Changed
- **Search-positioning copy** aligned across every listing surface — registry
  `server.json` description, GitHub About/topics, and the README opening line —
  leading with the "web-app QA / testing / analysis" framing and quantified
  capability nouns (66 tools, 25 step actions, 6 audits) that directory search
  actually matches on. No code changes.

## [0.9.2] - 2026-07-04

### Changed
- **Enriched all tool descriptions** — rewrote 56 of 66 tool definitions to
  state, per tool: what it does, what it **returns** (fields/shape), and when to
  use it / caveats. Clearer definitions help any MCP client's agent pick and call
  the right tool (and lift Glama's tool-definition quality score). Tool schemas
  (parameters, types, enums) are unchanged — only descriptions.
- Registry `server.json` description refreshed to the current 66-tool count and
  the "website & web-app" framing, and the publish workflow now syncs the
  registry version from the release tag automatically.

## [0.9.1] - 2026-07-04

### Added
- **Interactive login** (`interactive_login` / `save_login`) for auth flows that
  can't be scripted — 2FA/MFA, SSO/OAuth redirects, CAPTCHA, magic links: opens a
  visible browser window for the user to log in by hand, captures the session, then
  runs authenticated **headlessly**. Plus on-demand headed sessions via
  `open_session(url, headed=true)`.
- **Real INP** (Interaction to Next Paint) measured from actual Event Timing
  entries for the interactions Periscope drives — something Lighthouse can't do in
  lab mode. Surfaced inline on `interact_and_test` and the `performance` check, and
  exportable as a graphable per-interaction time series (JSON/CSV) with percentile
  stats via `get_interaction_log`.
- **Explicit version reporting** — the server now reports its own version to MCP
  clients (previously it fell back to the `mcp` SDK's package version). Single
  source of truth in `_version.py`.
- MCP Registry `server.json` + OIDC publish workflow.
- Glama listing metadata: `glama.json` (maintainers) and a score badge in the README.

### Changed
- Reframed throughout as **website *and* web-app testing** (static sites, SPAs, and
  apps behind a login) rather than just static websites.
- Attribution: link [Segentic Lab](https://lab.segentic.dev); set the repo homepage.
- Documentation audit — synced `CLAUDE.md` and `AGENTS.md` with the actual codebase.

### Fixed
- **Docker**: use `playwright install --with-deps` so the bundled Chromium can
  actually launch — the previous hand-listed system libraries were missing
  dependencies (e.g. `libXfixes`), leaving the container unable to start a browser.

## [0.9.0] - 2026-07-03

First public release after four months of private development and continuous
testing by an AI agent driving the server against real sites. Agent-first tool
ergonomics (hard assertions, one-call workflows, honest responses), persistent
authenticated sessions, built-in debugging, and a full audit suite (accessibility,
SEO, GEO/agentic-search readiness, Core Web Vitals, Lighthouse). See the
[release notes](https://github.com/segentic-lab/periscope-mcp/releases/tag/v0.9.0).

[0.9.5]: https://github.com/segentic-lab/periscope-mcp/compare/v0.9.4...v0.9.5
[0.9.4]: https://github.com/segentic-lab/periscope-mcp/compare/v0.9.3...v0.9.4
[0.9.3]: https://github.com/segentic-lab/periscope-mcp/compare/v0.9.2...v0.9.3
[0.9.2]: https://github.com/segentic-lab/periscope-mcp/compare/v0.9.1...v0.9.2
[0.9.1]: https://github.com/segentic-lab/periscope-mcp/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/segentic-lab/periscope-mcp/releases/tag/v0.9.0
