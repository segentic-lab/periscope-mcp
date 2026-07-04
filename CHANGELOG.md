# Changelog

All notable changes to Periscope are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). The version is
defined once in [`_version.py`](_version.py) and reported to MCP clients during the
initialize handshake.

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

[0.9.2]: https://github.com/segentic-lab/periscope-mcp/compare/v0.9.1...v0.9.2
[0.9.1]: https://github.com/segentic-lab/periscope-mcp/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/segentic-lab/periscope-mcp/releases/tag/v0.9.0
