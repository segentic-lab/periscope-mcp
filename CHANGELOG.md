# Changelog

All notable changes to Periscope are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). The version is
defined once in [`_version.py`](_version.py) and reported to MCP clients during the
initialize handshake.

## [0.10.2] - 2026-07-07

Cross-server lesson from the glovebox-mcp sibling (its `observe`/`settle_ms`
pattern is "cleaner than periscope's separate screenshot-after"). Issue #21.

### Added
- **`observe` param on the action tools** (`click_element`, `fill_form`,
  `select_option`, `scroll_into_view`, `navigate_session`, `set_viewport`).
  The caller now chooses what comes back per call: `screenshot` (default,
  unchanged), `none` (structured result only — no forced image), `map`
  (bundles the `get_page_map` semantic map), or `checks` (bundles
  `run_checks_on_session`). A multi-step flow can run `observe="none"` through
  setup steps and `observe="map"` on the step that matters — fewer image
  tokens, no extra round-trip. Default preserves the historical
  `screenshot_path`, so nothing breaks.

## [0.10.1] - 2026-07-05

Third test-agent batch: issue #20, filed while observing authenticated flows
on a real Next.js app.

### Fixed
- **#20 — Headed sessions now inherit project auth.** `login_project`
  authenticates the *running* context without writing the persisted session
  file, so a headed context created later started with zero cookies and
  bounced to the login page. Contexts now seed from the sibling mode's live
  `storage_state` (headless↔headed, symmetric), falling back to the persisted
  file — headed and headless sessions are interchangeable for a logged-in
  project.
- **#20 note — re-running `login_project` when already authenticated** used to
  time out hunting for a password field the redirect had skipped past; it now
  returns `already_authenticated: true` with the redirect target.
- e2e login fixture now mirrors real apps (authenticated visitors are
  redirected away from the login page).

## [0.10.0] - 2026-07-06

Capability release — seven new tools + one new parameter, closing the gaps a
tooling audit ranked by real agent friction. 74 tools now. Designed lean:
every new tool reuses existing machinery (the step executor, the assertion
evaluator, the screenshot compare, the overlay-fallback click).

### Added
- **`get_page_map`** — semantic page map in one call: every interactive
  element + landmark/heading in document order, with ARIA role, accessible
  name, live state, and a ready-to-use selector. Replaces multi-call
  get_page_elements orientation; `unnamed` interactive elements are flagged
  (an accessibility finding in itself). Compact by design: truthy-only state
  fields, node cap with an explicit `truncated` flag.
- **`select_page`** — adopt popups/new tabs (window.open, target=_blank,
  OAuth/payment windows) as new drivable sessions. Popups are captured the
  moment they open with console/network recording already attached, so their
  initial load traffic is never lost. Unblocks a whole class of previously
  untestable flows.
- **`download_file`** — click a trigger and capture the downloaded file:
  path, size, sha256, source URL, and a text preview for small text files.
  Waiter armed before the click; the click handles portal overlays. When the
  browser artifact comes back empty (a system-Chromium quirk), the file is
  refetched over the session's cookies and flagged
  `capture_method: "context_refetch"` — stated, never silent.
- **`assert_all`** — batch assertions: every condition evaluated (no early
  abort), per-item verdicts + overall `passed`/`failed_count` in one
  round-trip. Same fields per item as assert_condition, same evaluator.
- **`visual_check`** — named visual-regression baselines per project:
  `set` captures the page or one element, `check` returns a hard pass/fail
  against `max_diff_percent` plus a diff image. No screenshot-path
  bookkeeping.
- **`flow`** — save/run/list/delete named step sequences (interact_and_test's
  exact format, same executor). Define login/smoke paths once, replay in any
  session; verify with assert_all / visual_check after.
- **`screenshot_session` gains `selector`** — clip the screenshot to one
  element for evidence citing.
- **`session_report`** — a self-contained HTML + PDF dossier of the whole
  server run for the *user*: every tool call in chronological order with
  arguments (secrets redacted at the journal layer — passwords, tokens,
  cookie values), pass/fail verdicts, timings, error messages, and embedded
  screenshot thumbnails; the agent's findings go in `notes` and open the
  report. Calls are journaled automatically at the dispatch chokepoint
  (failed calls included; journaling can never break a tool call), and the
  PDF renders through Periscope's own Chromium.

### Fixed
- e2e fixture server now sends Content-Length (downloads need it to
  finalize).

## [0.9.6] - 2026-07-05

Hardening of `periscope_system` from live-testing the self-update loop
(isolated clone, real `update.sh` runs — not mocks).

### Fixed
- **Commit-based change detection.** `updated`/`restart_required` now compare
  HEAD before/after the pull (`commit_before`/`commit_after` in the response)
  instead of version strings — an update that pulls commits without a version
  bump was misreported as `updated: false`. `status` likewise detects a
  pending restart by comparing the current HEAD to the commit captured when
  the process loaded.
- Dirty-file parsing: the porcelain status column was sliced off after output
  stripping, mangling reported filenames.

### Changed
- **Transparent handling of local modifications.** `update` with `apply=true`
  on a dirty tree now stops *before* the updater and names the modified files
  (`modified_files`), with both options spelled out. With `force=true`,
  changes are stashed by `update.sh` (recoverable — never deleted) and the
  response now says exactly that: `stashed_files[]` plus the recovery command,
  with an instruction to relay it to the user. AGENTS.md documents the policy:
  never force away changes silently.

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

[0.10.1]: https://github.com/segentic-lab/periscope-mcp/compare/v0.10.0...v0.10.1
[0.10.0]: https://github.com/segentic-lab/periscope-mcp/compare/v0.9.6...v0.10.0
[0.9.6]: https://github.com/segentic-lab/periscope-mcp/compare/v0.9.5...v0.9.6
[0.9.5]: https://github.com/segentic-lab/periscope-mcp/compare/v0.9.4...v0.9.5
[0.9.4]: https://github.com/segentic-lab/periscope-mcp/compare/v0.9.3...v0.9.4
[0.9.3]: https://github.com/segentic-lab/periscope-mcp/compare/v0.9.2...v0.9.3
[0.9.2]: https://github.com/segentic-lab/periscope-mcp/compare/v0.9.1...v0.9.2
[0.9.1]: https://github.com/segentic-lab/periscope-mcp/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/segentic-lab/periscope-mcp/releases/tag/v0.9.0
