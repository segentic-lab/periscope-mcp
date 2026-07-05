<!-- Copy everything below this line into your agent's system prompt to teach
     it how to use the Periscope MCP tools effectively. -->

# Website & Web-App Testing with Periscope

You have access to Periscope, an MCP server exposing 74 Playwright/Chrome tools
for testing websites and web apps (static sites, SPAs, and apps behind a login).
Call `describe_tools(category?)` anytime for the full catalog with parameters
and workflows.

## Core model

- **Sessions are your main workflow.** `open_session(url)` returns a
  `session_id` and keeps a real browser page alive across tool calls — state,
  cookies, console output, and network traffic accumulate. Multi-step work
  (login, forms, SPA flows, debugging) belongs in a session. One-shot tools
  that take a bare `url` open and close a throwaway page each call; use them
  only for single lookups.
- **Isolation:** calls without a `project` run in private, isolated browser
  contexts — no cookies or login state are shared between them. Pass
  `project` when you *want* shared state (authenticated testing).
- Sessions expire after 300s idle and there is a 20-session cap (both
  env-overridable). Close sessions with `close_session` when done. A
  "session not found" error names *why* it's gone — idle-expired, evicted at
  the cap, or the browser crashed/restarted (that one also drops login state,
  so re-run `login_project`). Reopen with `open_session` and continue; don't
  retry the dead id.
- Every tool returns JSON. Failures come back as `{"success": false, "error":
  ...}` — read the error, they are written to tell you the fix (wrong selector,
  expired session, missing argument).

## Standard workflows

**Explore then act.** Orient with ONE call: `get_page_map(session_id)` —
every interactive element and landmark with its role, accessible name, state,
and a ready-to-use selector, in document order (interactive elements with no
accessible name come back flagged `unnamed`: an accessibility finding).
For targeted lookups, `get_page_elements(session_id, "button")` lists matches
for a selector and `find_element(session_id, text="Submit")` finds the best
selector by text. Never guess selectors.

**Static audit of a site:**
`create_project(name, base_url)` → `test_project(project)` (crawls and runs
visual/accessibility/functionality/seo/performance/geo checks on every page,
saves a JSON report) → `get_report(path)`. For one page: `test_url(url)`.
The `geo` check covers AI/agentic-search readiness: robots.txt access for AI
crawlers, llms.txt compliance, WebMCP form annotations, and JSON-LD presence.

**Authenticated testing:** configure once with `set_form_login` /
`set_basic_auth` / `set_cookies`, then `login_project(project)`. Pass
`project` to `open_session` so the session shares the logged-in context.
`copy_auth(from, to)` moves auth between projects on the same domain.
Auth can expire mid-run (token rotation, short sessions) — Periscope detects
it rather than masking it: `test_project`/`crawl_project` preflight the auth
and re-login automatically (see `auth_check` in the response), pages that land
on the login page come back as `status: "auth_lost"` with an error issue (never
plain success), and `open_session` warns when it lands on the login page. On
any of those signals, run `login_project` again.

**Logins you can't automate** (2FA/MFA, SSO/OAuth redirects, CAPTCHA, magic
links): call `interactive_login(project)` — it opens a **visible** browser
window (requires a display on the server); the user logs in by hand, then you
call `save_login(project)` to capture the session. The project then opens
authenticated sessions **headlessly** with the saved login. To simply watch or
hand-drive any session, use `open_session(url, headed=true)`.

**Multi-step flows:** batch steps into one `interact_and_test` call instead of
many single calls — it supports 25 actions (click, fill, select, wait_for,
wait_for_text, wait_for_network, navigate, hover, press_key, upload_file,
evaluate_js, drag, scroll…), takes a screenshot at the end, and can run checks
via `run_checks`. Use `continue_on_error=true` when later steps make sense
even if one fails.

**Form testing:** `auto_fill_form(session_id)` detects fields, infers
realistic test data, and fills everything in one call (use `overrides` for
specific values, `submit=true` to submit). `test_form_validation` audits
validation behavior.

**Verification:** prefer assertions over screenshot-squinting — hard
`passed: true/false` plus the actual value. With 2+ expectations, batch them
in one `assert_all(session_id, assertions=[...])` call (every assertion is
evaluated — the response is the complete verdict picture); for a single check
use `assert_condition` (text_contains, element_exists, element_visible,
element_count, url_contains, title_contains, attribute_equals…).
For visual regressions, `visual_check(session_id, name, action="set")`
baselines the page or one element, and later `action="check"` returns a hard
pass/fail with a diff image — prefer element-scoped baselines (selector=…),
full pages flake more.

**Reusable workflows:** `flow(action="save", name, steps=[...])` stores a step
sequence (same format as interact_and_test); `flow(action="run", name,
session_id)` replays it in any session. Define login/smoke paths once, then
run + `assert_all` each session instead of re-scripting.

**Popups and new tabs** (OAuth windows, target=_blank, window.open): the
session captures them the moment they open — console/network recording starts
at birth. `select_page(session_id)` adopts the popup as a NEW session id you
drive with every normal tool; the parent id keeps working for the original
tab. With several popups open, call it without `index` to list them.

**File downloads** (exports: CSV, PDF, invoices): `download_file(session_id,
selector)` clicks the trigger and captures the file — path, size, sha256, and
a text preview for small text files. The waiter is armed before the click and
the click handles portal overlays. If the response says
`capture_method: "context_refetch"`, the browser artifact was empty and the
file was refetched over the session's cookies — same URL, stated honestly.

## Debugging a broken page

1. `get_console_errors(session_id)` — JS errors since open (clears by default).
2. `get_network_log(session_id, url_filter?)` — every request with status/method.
3. `get_response_body(session_id, url_pattern)` — the actual API response body;
   this is the fastest way to diagnose a 400/500. Bodies are captured
   automatically for fetch/xhr/document requests; no setup needed.
4. `interact_and_test(session_id, steps, capture_console=true)` — console
   output scoped to specific actions.

To *reproduce* failure states: `intercept_network(session_id, url_pattern,
status=500, body=...)` mocks API responses (test error/empty/loading UI),
`clear_intercepts` removes them; `emulate_network(session_id, "slow_3g" |
"offline" | "reset")` throttles. `set_local_storage` / `get_local_storage`
and `get_cookies` manipulate state directly.

**Branching exploration:** `page_state(session_id, "snapshot", name)` checkpoints
URL+cookies+storage+DOM; `action: "restore"` returns to it; `action: "diff"`
shows what changed since — useful for "did this action actually change
anything?".

## Visual and responsive

- `screenshot_session(session_id)` for current state; `set_viewport` with
  presets `mobile_sm|mobile|mobile_lg|tablet|tablet_lg|laptop|desktop|desktop_lg`.
- `test_responsive(url)` tests mobile/tablet/desktop in one call.
- `compare_screenshots(path1, path2)` returns a pixel-diff percentage and a
  highlighted diff image.
- `test_dark_mode(session_id, "dark")` toggles prefers-color-scheme.
- Accessibility: `check_color_contrast` (WCAG AA/AAA ratios),
  `test_keyboard_navigation` (tab order + focus indicators).
- `run_lighthouse(url)` runs a real Google Lighthouse audit (0-100 scores,
  official Core Web Vitals, failed audits). Requires Node.js on the server;
  it launches its own Chrome, so session/login state does not apply — use it
  for public pages, and Periscope's own checks for authenticated ones. The
  `performance` check also reports lab LCP/CLS/TBT natively, no Node needed.
- **Real INP** (Interaction to Next Paint): unlike Lighthouse (which can't
  measure INP in lab mode), Periscope measures it from the actual interactions
  you drive. `interact_and_test` results and the `performance` check include
  `interaction_to_next_paint_ms` (null until you've interacted). For a long
  interactive test, `get_interaction_log(session_id, format="json"|"csv")`
  exports every interaction's INP as a graphable time series + percentile
  stats — plot `inp_ms` over `t_ms`.

## Ordering rules and pitfalls

- `handle_dialog(session_id, action)` must be called **before** the action
  that triggers the alert/confirm/prompt — it arms a one-shot handler.
- To catch a request triggered by a click, put `click` and `wait_for_network`
  as consecutive steps in one `interact_and_test` call; a standalone
  `wait_for_network` call after the click may miss a fast response. For
  after-the-fact inspection, `get_response_body` reads already-captured
  traffic instead.
- Portal overlays (Radix/shadcn dialogs & menus) that intercept clicks are
  handled automatically: the click falls back to an element-level JS dispatch
  and the result is flagged `click_method: "js_dispatch"` — no `evaluate_js`
  workaround needed. For fills blocked by overlays, use `fill_form` with
  `force=true` after a normal attempt fails.
- Custom dropdowns (Radix/shadcn): use `select_option`, not `click` + `click`.
- Several attribute-less `<select>` elements on one page: pass
  `element_index` to `select_option` to target the Nth match of the selector
  (0-based). Playwright `>>` locator syntax is not supported in selectors.
- Every `url_pattern`/`url_filter` is a **plain substring** of the full URL
  (including query string) — never a regex or glob: anchors (`$`) and
  wildcards (`.*`) silently never match. On a miss, `get_response_body`
  lists the captured URLs so you can correct the pattern in one step.
- Timing a button whose handler fires the request asynchronously (submit →
  `fetch` a tick later): pass `wait_for_network` (URL substring) to
  `measure_interaction` — the default network-idle mode can settle on an
  early idle window and report a misleadingly tiny time. The result also
  carries the click's real `interaction_to_next_paint_ms`.
- `select_iframe(session_id, selector)` returns a **new** session id scoped to
  the iframe; use it like a normal session, and keep using the parent id for
  page-level actions.
- **Drag-and-drop fails silently** — pointer-tracking DnD libraries
  (`@hello-pangea/dnd`, react-beautiful-dnd) ignore the default drag: the step
  reports success but nothing moves. Always verify a drag had an effect
  (`assert_condition` on the new order, or `page_state` snapshot before /
  diff after). If nothing changed, escalate in order:
  1. Retry the same drag step with `method: "mouse"` (stepped manual drag —
     handles most pointer-tracking libraries).
  2. Use the library's keyboard mode: focus the drag handle
     (`evaluate_js`: `document.querySelector(...).focus()`), then `press_key`
     `" "` to lift, `ArrowDown`/`ArrowUp` to move, `" "` to drop.
  3. If both fail, report drag-and-drop as untestable for this widget rather
     than claiming it works or is broken.
- Never-idle pages (Cloudflare Turnstile, websockets, polling) are handled
  automatically: navigation retries with `load` and the result carries a
  `wait_downgraded` flag — expect slower first loads on such pages, not
  errors. Only a page that fails even the `load` wait is genuinely broken.
- Don't screenshot after every step — interactive tools already return
  screenshots where useful. Ask for extra screenshots only when you need to
  *see* something.

## Reporting results

When testing on behalf of a user: state what you tested, what passed, and what
failed with the concrete evidence (assertion values, console errors, response
bodies, screenshot paths). Distinguish site bugs from test-setup problems
(expired session, wrong selector). Include reproduction steps for every bug.

At the end of a testing run, generate `session_report(notes=...)` — a
self-contained HTML + PDF dossier of every tool call you made (arguments with
secrets redacted, verdicts, timings, screenshots) so your user can review the
whole session. Put your findings summary in `notes`; it opens the report.
Everything is journaled automatically — failed calls included.

## Keeping Periscope and this guide current

`periscope_system` is the self-maintenance tool:

- `action="status"` (read-only) — running version, on-disk version, git commit,
  install type, capabilities (Node/Lighthouse, display for headed sessions,
  Chromium), active session count, and whether an update is available.
- `action="agents_md"` (read-only) — returns the CURRENT version of this guide
  from the install. If this pasted copy might be stale (a status check shows a
  newer version than you expected), fetch it and prefer its instructions.
- `action="update"` — dry-run by default (commits behind + incoming changes);
  `apply=true` runs the updater (git pull + dependencies; the user's data/ is
  untouched). **New code loads only after the MCP server restarts** — the
  response says so; tell your user to restart the server/session, and re-fetch
  `agents_md` afterwards so your context matches the new code. Only apply an
  update when your user asked for it or approved it.
- **Local modifications** to tracked files block the update, and the error
  names the files. `force=true` proceeds by **stashing** them (`git stash` —
  recoverable, never deleted); the response then lists `stashed_files` and the
  recovery command. Always relay that to your user — never force away changes
  silently, and prefer asking the user to commit their changes instead.

## Reporting Periscope bugs

If a **Periscope tool itself** misbehaves — its response contradicts what the
page actually shows, a success is reported for something that visibly didn't
happen, a returned selector doesn't parse, a check flags something you can
verify is correct — that's a tool bug, not a site bug. Don't silently work
around it:

1. Capture the evidence: tool name, exact arguments, the raw JSON response,
   what you expected, the page/framework context, and the install's version +
   commit (`periscope_system(action="status")` returns both — no shell needed).
2. File it at https://github.com/segentic-lab/periscope-mcp/issues (the bug
   template asks for exactly these fields). If you can't create GitHub
   issues, put the same details in your report so your user can file it.

Verified tool-bug reports with raw responses are how most of this server's
fixes happened — they are genuinely welcome.
