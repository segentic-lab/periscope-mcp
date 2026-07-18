---
name: periscope
description: >-
  Drive the Periscope MCP server (74 Playwright + headless-Chrome tools) to
  test, audit, and debug websites and web apps — static sites, SPAs, and apps
  behind a login. Use this skill whenever the user wants to test a website or
  web app, run an E2E or interactive flow, audit accessibility/SEO/GEO/
  performance, measure Core Web Vitals or real INP, debug a broken page
  (console errors, network traffic, API 400/500s), take screenshots, run
  responsive or visual-regression checks, test forms, dropdowns, dialogs, file
  uploads/downloads, capture a whole site as Markdown, or read a JS-rendered or
  login-protected page — even if they never say "Periscope". If
  mcp__periscope__* tools are available in the session, consult this skill
  before driving them.
testing_types:
  - e2e
  - functional
  - accessibility          # WCAG checks, color contrast, keyboard navigation
  - seo
  - geo                    # AI/agentic-search readiness: AI-crawler robots access, llms.txt, WebMCP, JSON-LD
  - performance            # lab LCP/CLS/TBT + real INP + Lighthouse
  - visual-regression
  - responsive
  - forms
  - api-mocking            # intercept_network: error/empty/loading states
  - authenticated          # form login, basic auth, cookies, interactive 2FA/SSO login
frameworks:
  - playwright             # the underlying engine
  - react
  - next.js
  - astro
  - vue
  - svelte
  - radix-ui / shadcn      # portal overlays and custom dropdowns handled natively
  - any-static-site        # framework-agnostic: it tests the rendered browser reality
---

# Testing the web with Periscope

Periscope gives you the **browser's reality**, not the server's HTML: JS
executed, styles computed, network captured, real input latency measured. A
text fetch shows `<div hidden>`; Periscope shows you that author CSS overrode
`hidden` and the banner is actually visible. Prefer it over raw fetching
whenever the question is "what does this page actually do/look like".

## First moves

1. `describe_tools(category?)` — full catalog with parameters, workflows, tips.
2. For a long engagement, one `periscope_system(action="status")` call gives
   the exact version + commit for your report and flags available updates.
3. This skill is the distilled guide. The **authoritative, always-current**
   full guide ships with the install: `periscope_system(action="agents_md")`.
   Fetch it if this copy might predate the running server version.

## Pick the workflow

| You want to… | Do this |
|---|---|
| Audit one page | `test_url(url, checks?)` → read `issues[]` |
| Audit a whole site | `create_project(name, base_url)` → `test_project(project)` → `get_report(path)` |
| Test literally every page | `test_project(project, max_pages=0)` — unbounded, stops at a 2000-page ceiling with `ceiling_hit` |
| Capture a site as Markdown | `crawl_project(project, meta=true, save_md=true)` — titles+descriptions, one `.md` per page; works behind login and post-JS |
| Drive an interactive flow | `open_session(url)` → `get_page_map(session_id)` → act → `assert_all` |
| Batch many steps | one `interact_and_test(session_id, steps=[...])` call (25 action types) instead of many single calls |
| Test behind a login | `set_form_login`/`set_basic_auth`/`set_cookies` → `login_project` → pass `project` to `open_session` |
| Login you can't script (2FA/SSO/CAPTCHA) | `interactive_login(project)` (visible window, user logs in) → `save_login(project)` → headless authenticated after |
| Debug a broken page | `get_console_errors` → `get_network_log` → `get_response_body(url_pattern)` — the response body is the fastest 400/500 diagnosis |
| Reproduce error/empty/loading UI | `intercept_network(url_pattern, status=500, body=...)` → trigger → assert → `clear_intercepts` |
| Verify without squinting | `assert_all(session_id, assertions=[...])` — hard pass/fail + actual values, every assertion evaluated |
| Visual regression | `visual_check(name, action="set", selector?)` … later `action="check"` → pass/fail + diff image (element-scoped flakes less) |
| Responsive | `test_responsive(url)` one-shot, or `set_viewport(device=...)` inside a session |
| Real performance | `performance` check = lab LCP/CLS/TBT + **real INP**; `run_lighthouse(url)` for official scores (needs Node, no login state) |
| Fill a form fast | `auto_fill_form(session_id, overrides?, submit=true)` — detects fields, infers realistic data |
| Read an external page | `web_fetch(url)` → readable Markdown; `render=true` for SPA/JS pages; `project=` to read behind a login; `save=true` for a `.md` artifact |
| Deliver the results | `session_report(notes=...)` — HTML+PDF dossier of every call, secrets redacted |

## Core model

- **Sessions are the main workflow.** `open_session` keeps a real page alive
  across calls — state, console, and network accumulate. Bare-`url` tools open
  and close a throwaway page; use them only for one-shot lookups.
- **Isolation is deliberate:** project-less calls share no cookies with
  anything. Pass `project` when you *want* the logged-in context.
- Sessions idle-expire (300s) and cap at 20 (oldest evicted). A "session not
  found" error names *why* it died — if the browser restarted, login state is
  gone too: re-run `login_project`. Reopen; never retry a dead id.
- **Errors tell you the fix.** Every failure is `{"success": false, "error":
  ...}` written to be actionable — read it before retrying anything.
- **Never guess selectors.** `get_page_map` returns every interactive element
  with role, name, state, and a ready-to-use selector in one call;
  `find_element(text=...)` finds the best selector by visible text.

## Spend tokens deliberately

- The action tools (`click_element`, `fill_form`, `select_option`,
  `scroll_into_view`, `navigate_session`, `set_viewport`) take
  `observe: "none" | "screenshot" | "map" | "checks"`. Run setup steps with
  `observe="none"` (no image cost), then `"map"` or `"screenshot"` on the one
  step whose outcome you actually need.
- Don't screenshot after every step — tools already return screenshots where
  useful. Prefer `get_page_map` (text) over images for orientation.
- `web_fetch(contains=["term"], contains_mode="any"|"all")` checks many URLs
  cheaply: content is returned only when the term is present. The match runs
  against the **full page text** (boilerplate included), so a footer-only term
  still matches even though the readable output strips the footer.

## Pitfalls that waste turns (read once, save many)

**Selectors and patterns**
- Every `url_pattern`/`url_filter` is a **plain substring** of the full URL —
  never regex/glob; `$` and `.*` silently never match. On a miss,
  `get_response_body` lists the captured URLs so you can fix the pattern in
  one step.
- Playwright syntax (`>>`, `:has-text()`, `:visible`) is **not supported** —
  plain CSS only. For the Nth attribute-less `<select>`, pass
  `element_index` (0-based) to `select_option`.

**Clicking and inputs**
- Portal overlays (Radix/shadcn) that swallow clicks are handled
  automatically — the result is flagged `click_method: "js_dispatch"`. Don't
  build `evaluate_js` workarounds. For *fills* blocked by overlays, use
  `fill_form(force=true)`.
- Custom dropdowns: `select_option` (auto-detects native vs combobox), never
  click + click.
- `handle_dialog` must run **before** the action that triggers the
  alert/confirm/prompt — it arms a one-shot handler.
- **Drag-and-drop fails silently** with pointer-tracking libraries: the step
  "succeeds", nothing moves (the result carries a `warning` when the DOM
  didn't change). Verify every drag (`assert_condition` or `page_state`
  snapshot/diff); escalate: retry with `method: "mouse"` → keyboard mode
  (focus handle, Space, arrows, Space) → report the widget untestable.

**Timing**
- To catch a click-triggered request, put `click` + `wait_for_network` as
  consecutive steps in ONE `interact_and_test` call — a separate call can
  miss a fast response. After the fact, `get_response_body` reads
  already-captured traffic (fetch/xhr/document bodies are captured
  automatically, last 100, ≤500KB each).
- `measure_interaction` on an async submit handler: pass `wait_for_network`,
  or network-idle can settle early and report a misleadingly tiny time.
- Never-idle pages (Turnstile, websockets, polling) auto-downgrade the
  navigation wait and flag `wait_downgraded` — expect a slower first load,
  not an error. Only a page failing even `load` is genuinely broken.

**Frames, popups, auth**
- `select_iframe` returns a **new** session id scoped to the frame; keep the
  parent id for page-level actions. `select_page` (popup adoption) works only
  on the **root** session id.
- Landing on the login page is **never** a pass: results say
  `status: "auth_lost"` (test tools), or carry a warning (`open_session`).
  `test_project`/`crawl_project` preflight auth and re-login once
  automatically (`auth_check` in the response). On any auth-lost signal:
  `login_project`, then retry.
- A project holds ONE auth method (setting another replaces it, with a
  warning), and `set_cookies` only stores config — cookies go live at
  `login_project`.

**Trusting the output**
- Full-page screenshots are **prepared** (sticky headers neutralized,
  animations off, scroll-reveals forced), then the page is restored — the
  steps applied are listed in `capture_prep`. Trust the image; `raw=true`
  gives the unprepared stitch. Viewport/element shots are always as-is.
- The crawl is **deterministic and sitemap-seeded** — same site, same page
  subset, every run. Skipped pages are listed in `pages_not_tested[]` and
  `test_project` returns a `coverage` delta vs the previous report, so a
  finding can't silently vanish because the crawl window moved.
- INP is measured from the interactions **you drive** — it is `null` until
  you interact. `get_interaction_log(format="json"|"csv")` exports the full
  time series with percentiles.

## Finish the job

- Prefer assertions over screenshots as evidence; report what you tested,
  what passed, what failed — with the actual values, response bodies, and
  repro steps. Distinguish site bugs from test-setup problems.
- End a testing run with `session_report(notes=<your findings>)` — a
  self-contained HTML+PDF dossier of every call (auto-journaled, secrets
  redacted) the user can review and share.
- If a **Periscope tool itself** misbehaves (response contradicts the page),
  that's a tool bug: capture tool + args + raw JSON + version from
  `periscope_system(action="status")` and file it at
  https://github.com/segentic-lab/periscope-mcp/issues — verified reports are
  how this server improves.

## Going deeper

- `describe_tools(category?)` — all 74 tool signatures, recommended
  workflows, and tips, served by the running install (never stale).
- `periscope_system(action="agents_md")` — the complete current operating
  guide (superset of this skill); prefer it on any version mismatch.
- `periscope_system(action="update", apply=true)` — self-update (dry-run by
  default; new code loads after server restart). Only with user approval.
