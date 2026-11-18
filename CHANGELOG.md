# Changelog

All notable changes to Periscope are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). The version is
defined once in [`_version.py`](_version.py) and reported to MCP clients during the
initialize handshake.

## [0.12.0] - 2026-11-18

Hardening release: the server now speaks the 2.x `mcp` SDK, and a full
independent bug hunt (2 critical, 18 important, 12 minor findings, most
reproduced by running code) is fixed, each with a failing-first test.

### Changed
- **Ported to the `mcp` Python SDK 2.x** (1.x still supported). SDK 2.0 removed
  the low-level decorator API, so every fresh install broke; `server.py` now
  registers its handlers through the 2.x `Server` constructor and falls back to
  the 1.x decorators. Requirement is `mcp>=1.0.0,<3`; CI runs both lines, and a
  real stdio round-trip test (initialize → list tools → call tool) guards it.
- Numeric tool arguments sent as strings are coerced from each tool's schema —
  the server no longer depends on SDK-side validation for types.
- **Project names** must be 1-80 characters of letters, digits, `.`, `_`, `-`
  (they become path components). Existing projects keep working.
- A `project` argument that names no project is now an error instead of
  silently running in a fresh, logged-out context.
- Text/URL/title assertions require a non-empty `expected` (an omitted one used
  to pass, since "" is contained in everything).

### Fixed — security and data safety
- **`delete_project` could delete directories that were not Periscope's**: a
  pre-existing folder inside a custom `screenshot_dir` that shared the project
  name, or — for a project named `..` — the whole data directory. Deletion is
  now confined to strict children of the base, and a custom directory is only
  removed when Periscope created it (marker file).
- **`get_report` could read any JSON file**, including `projects.json` (stored
  passwords) and saved login sessions. It now reads only reports inside the
  reports directory.
- **The call journal / `session_report` leaked secrets** it claimed to redact:
  values typed into password-like fields, `set_local_storage` entries,
  credentials embedded in URLs, and the results of `get_cookies`,
  `get_local_storage` and `get_response_body`. All are masked now.
- A malformed `projects.json` (not an object, an entry without a name, a field
  from a newer version) no longer prevents the server from starting.

### Fixed — wrong verdicts
- **`login_project` reported "already authenticated" when the login URL merely
  redirected to another login path** (SSO, `/login` → `/accounts/sign-in`), so
  crawls audited the login wall as a clean run. A landing page with a visible
  password field is a login page: the login is performed there, and failures
  are reported as failures.
- Login-redirect detection compares host, path (locale prefixes count), and —
  for hash- or query-routed apps — the login route itself. Hash/query-router
  apps no longer flag every page as `auth_lost`.
- **The crawler found one page** when `base_url`'s host differed from the real
  one in case, default port, or by redirect (apex → www): hosts are normalized
  and the crawl adopts the host the site actually answers on (`crawl_scope`).
  Redirecting URLs are recorded once, as their target. Gzipped sitemaps work.
- A `select_option` step whose selection failed reported success; it now fails
  the step. A custom dropdown with no value/label/index no longer clicks the
  first option.
- `get_page_map` / `find_element` / `auto_fill_form` fallback selectors were
  cut at five levels and could resolve to a *different* element; they are now
  anchored at `body` or a unique id.
- `check_color_contrast` silently skipped `oklch()`, `oklab()`, `color-mix()`
  and other modern colour syntaxes (the Tailwind v4 default), so a page could
  report zero failures unchecked. Colours are resolved through a canvas;
  anything still unreadable is counted in `unparsed_count`.
- Accessibility check false errors: named anchors without `href`, and
  links/buttons named by a descendant's `aria-label`.
- `visual_check` / `compare_pages` treated `max_diff_percent=0` as the default.
- Checks on iframe sessions reported every link "unreachable" and
  `test_keyboard_navigation` crashed (a Frame was used as a Page).
- robots.txt / llms.txt were cached for the life of the process, failures
  included — a fix was invisible until restart. Now a 60 s TTL, failures not
  cached.
- `get_table_data` dropped cells under repeated or empty headers.
- `run_lighthouse` treats a Lighthouse `runtimeError` as a failed run and kills
  the whole process tree on timeout; the median ignores runs without an LCP.
- `network_summary`: first-party means same registrable site (a CDN subdomain
  is not third-party); 304s are not sized from `Content-Length`.

### Fixed — found by driving all 79 tools through the live server
- `nav_generation` counted fragment changes and same-URL `history.replaceState`
  (scroll-spy sites inflated it by a dozen per screenshot). It now counts new
  documents and SPA route changes only.
- `page_state diff` could not see changes on elements without an id (a toggled
  `aria-checked`, a re-texted list item) — the usual case. The signature is now
  path-keyed with state attributes: `changed`, `changed_count`,
  `changed_elements[]` with selectors, plus added/removed elements.
- A click that opens a popup/new tab reported "no page change"; `popup` is now
  a change kind.
- Console "Failed to load resource" errors carry the failing URL.
- `get_page_map`: `header`/`footer` inside a section are not landmarks, and
  containers are named only by an explicit label (not their whole text).
- `check_pwa` no longer reports Periscope's own `in-incognito` state, and a
  site with neither manifest nor service worker gets one informational note
  (`is_pwa: false`) instead of three defects.
- `auto_fill_form` skips fields a user cannot reach (honeypots) and understands
  Slovenian/German field hints (e-pošta, geslo, telefon, …).
- `check_links` verifies same-page `#anchors` against the DOM and requests each
  document once, instead of re-fetching the page per fragment.
- `check_color_contrast` skips empty elements; `test_form_validation` lists
  controls, not their fieldsets; `wait_for_gone` reports `was_present`;
  `get_network_log` returns the sizes its description promised;
  `select_iframe` also returns `session_id`; `open_session(consent=…)` handles
  the banner before the opening screenshot; redirect aliases are no longer
  listed as uncrawled pages; the unknown-project error suggests the closest
  name instead of listing every project.

### Fixed — behaviour
- A default full-page screenshot reset the page scroll to the top; the scroll
  position is restored after capture.
- `intercept_network` with a method filter bypassed other mocks for the same
  URL (and the project's basic-auth route); the basic-auth route no longer
  swallows mocks either.
- Reload / back / forward and `set_viewport(reload=true)` timed out after 30 s
  on never-idle pages; they downgrade like navigation does, and a session
  already known to be busy skips the wait.
- `page_state restore` cleared cookies for the whole shared project context;
  it now touches only the snapshot page's cookies.
- `copy_auth` of an interactive-login project copies the saved session;
  `login_project` on such a project without a saved session is an error.
- `record_session` honours basic auth and saved login sessions.
- Popups and adopted tabs are closed with the session that opened them.
- `clear_site_data` refuses non-http pages; navigation from an iframe session
  no longer crashes; `compare_pages` validates its device up front and closes
  the page of a side that failed to load; `check_pwa` fails cleanly when the
  page can't load; frame selectors are correct across different parents;
  saved-Markdown filenames no longer collide; report lists no longer mix
  `shop` with `shop_staging`; the update check compares against the branch
  that will actually be pulled.

## [0.11.0] - 2026-11-02

Field-feedback release: every ask from two real engagements — the klimacar.si
build (Astro + Cloudflare Workers, Stripe hosted checkout, installable PWAs) and
the Vibrant Longevity WordPress migration (Elementor/WPML, staging → live) —
plus the design flaw those reports exposed. 79 tools now.

### Fixed
- **The Stripe trap: a click could report success for a click the page
  ignored.** When Playwright's actionability check failed, the overlay fallback
  dispatched a *synthetic* click and returned ok — hosted payment pages check
  `isTrusted`, so that click never worked. Every click now reports `changed`,
  `change` (`url`/`dom`/`network`), `click_method` (`pointer` | `pointer_force` |
  `js_dispatch`) and `attempts`; a click that changed nothing carries a `hint`
  (and names `isTrusted` when the synthetic path was taken). `strategy="auto"`
  escalates pointer → forced pointer → js_dispatch and stops at the first
  attempt that changes the page (never re-clicks after a change). Unstable
  (animating) elements now take the fallback instead of raising.
- **Fills are verified.** Every fill reads the value back; framework-controlled
  inputs that discard typed text get a native-setter retry. Results carry
  `verified`, `fill_method`, `actual` (per field in `fill_form.fields[]`, inline
  on `fill`/`force_fill` steps).
- **click + wait_for_network as consecutive steps can no longer miss a fast
  response** — the response waiter is armed before the click.
- Change detection counts requests *started* (a per-session monotonic
  counter, immune to the network-log cap), so a slow POST fired by a click is
  a change while still in flight — `strategy="auto"` never re-fires it. A
  click that shows no change yet gets one 750 ms quiet window for late
  handlers before the "no change" verdict. A selector that matches nothing
  fails fast with a clear error instead of walking the escalation chain.
- Fill verification goes through the locator (shadow DOM, contenteditable
  keep working); the native-setter retry only targets input/textarea.
- Popup sessions count their navigations; iframe sessions report their owning
  page's `nav_generation` and share its console/network capture (a checkout
  iframe is no longer "silent" to change detection or `network_summary`).
- Device sessions for basic-auth projects carry the credentials; a consent
  failure during `open_session` is reported in `consent` without losing the
  session; a `goto` whose `wait_for` times out cancels its armed waiter.
- `web_fetch` names the fix on a TLS certificate failure (`verify_ssl=false`,
  or `render=true` — browser sessions already ignore certificate errors) and
  flags `tls_error`.
- `describe_tools` catalog refreshed (it had drifted: `web_fetch` params,
  `navigate_session` `observe`); a unit test now fails when a registered tool
  is missing from the catalog.

### Added
- **`navigate_session`** gained `goto` (with `wait_for` selector and
  `wait_for_network` substring armed *before* the load, per-call `wait_until`),
  `reload` with `hard=true` (HTTP cache bypass), and `clear_site_data`
  (unregister service workers + purge CacheStorage for the origin, then reload;
  `include_storage=true` adds local/session storage + IndexedDB; cookies are
  never touched). Every navigation and `open_session` report
  `served_by_service_worker` — the instant explanation for "I'm still seeing
  the pre-deploy page".
- **`nav_generation`** (main-frame navigation count) on every session result,
  stamped at the handler registry — notice when you are no longer on the page
  you think you are. Screenshot results carry `view` (viewport, scroll,
  page_height).
- **`hover_element`** tool and a stepped `hover` step: a realistic pointer path
  (warm-up move + 8 intermediate `mousemove`s) that opens hover-intent menus
  (SmartMenus/Elementor) a single synthetic hover never did.
- **`open_session(device, width, height, consent)`** — open already sized, or
  emulating a real device (any Playwright device name such as `"iPhone 14"`,
  `"Galaxy S9+"`, plus `samsung_internet`): user agent, DPR and touch in a
  private context seeded with the project's login state. `set_viewport(reload=true)`
  re-evaluates JS breakpoints.
- **`handle_consent(action=accept|deny|dismiss)`** — cookie-banner helper with
  a CMP table (Complianz, Cookiebot, CookieYes, OneTrust, Borlabs, Usercentrics,
  Didomi, Osano, Iubenda, Klaro, Cookie Notice, Cookie Law Info, Moove GDPR,
  Quantcast, Termly, HubSpot) and a generic en/sl/de/hr/it/es/fr button-text
  fallback. No banner = success with `found: false`. Also a `consent` step and
  the `open_session(consent=…)` / `compare_pages(consent=…)` parameters.
- **`check_pwa(url|session_id)`** — manifest fetch + validation (name,
  short_name, 192/512 icons, display, start_url within scope, colours),
  service-worker registration/state, Chrome's installability errors via CDP,
  `beforeinstallprompt` observation in url mode. Issues typed `pwa`.
- **`get_page_map(include_frames=true)`** — iframe inventory (selector, url,
  name, cross_origin) with ready `select_iframe` selectors; `frame_count` is
  always returned. The way into Stripe card fields.
- **`download_file`** reports `content_type` and `content_disposition`, and
  `navigated_instead: true` (with `final_url`) when the click opened the file
  instead of downloading it.
- **`screenshot_session(mode="tiles", tile_height=1600)`** splits a long page
  into legible images (`tiles[]`); full-page shots of pages over 6000 px get a
  note suggesting it. `mode` also accepts `full|viewport|element`.
- **`network_summary(session_id, since=open|clear|<epoch ms>)`** — bytes and
  requests by domain (third-party flagged) and by resource type, heaviest
  requests, third-party share, service-worker hits. Sizes from Resource Timing
  with `Content-Length` fallback, unknowns counted. `get_network_log` entries
  now carry `content_length` and `from_service_worker`.
- **`run_lighthouse(runs=N, warmup=true)`** — median-LCP run plus min/median/max
  spread across runs, a cache-priming GET before the runs, and a `summary`:
  LCP element + phase breakdown (TTFB / load delay / load time / render delay),
  TTFB with a > 2 s warning, bytes by domain with third-party share, top
  opportunities by savings. Handles Lighthouse 13 insight audits and the older
  `largest-contentful-paint-element` shape.
- **`compare_pages(url_a, url_b, steps?, consent?, device?, run_checks?)`** —
  staging vs live in one call: side-by-side full-page screenshots + pixel diff,
  facts diff (title, meta description, canonical, H1s, hreflang, lang, robots,
  og tags, link/image/form counts), visible-text diff, performance and
  transfer-weight deltas, `same`. A side that fails to load is reported with its
  error while the other side is captured in full.
- E2E fixtures for all of the above (`trusted_click`, `sw`, `menu_hover`,
  `consent`, `frames`, `long`, `weighty`, `pwa`) and a Lighthouse 13 unit
  fixture.

## [0.10.4] - 2026-07-07

### Changed
- **`web_fetch` returns readable Markdown by default** and gained real teeth.
  Extraction now uses trafilatura: structure preserved (headings, lists, links,
  code, tables), page boilerplate (nav/footer/cookie bars) stripped — ~60% fewer
  tokens than the old flat text dump, and the content starts at the actual
  content instead of the nav mega-menu. `format=text|markdown|html` (raw_html is
  an alias); `readable=false` restores the whole-page dump.

### Added
- **`web_fetch(render=true)`** — load the page in headless Chromium and run JS
  before extracting, for client-rendered/SPA pages a static fetch returns empty
  for. With `project=...`, renders in that project's authenticated context —
  reads pages **behind a login** (host fetch tools can't).
- **`web_fetch(contains=[…], contains_mode=any|all)`** — conditional fetch: only
  returns the content if the page contains the term(s), else omits it (token
  saving) — cheap "which of these URLs mention X" checks.
- **`web_fetch(save=true | save_path=…)`** — write the full (un-truncated)
  content to `data/fetches/` (or a given path) and return `saved_path`.
- `web_fetch` now sends a real User-Agent and returns graceful `{success:false}`
  errors (with `status_code`) instead of raising on HTTP errors.
- **`web_fetch(contains=…)` matches the full page text**, not the readable-
  extracted output — so a term in stripped nav/footer/boilerplate is no longer a
  false miss in reading mode (the output stays readable; only the match haystack
  is the whole page). Flagged `match_scope: "full_text"`.
- **`crawl_project` can capture pages, not just list URLs.** `meta=true` adds each
  crawled page's title + meta description; `save_md=true` saves every crawled
  page as readable Markdown to `data/fetches/<project>/` (returns `pages[]` with
  `saved_path`, plus `saved_dir`/`saved_count`). Capture happens *during* the
  crawl on the loaded page, so it works for behind-login and JS-rendered pages
  with no second navigation.

## [0.10.3] - 2026-07-07

Dogfooding batch — issues #22 and #23, filed while auditing real Astro sites.

### Fixed
- **#23 — Full-page screenshots misrendered sticky/reveal elements.** Playwright
  stitches a full-page shot from viewport slices, which double-painted
  `position: sticky`/`fixed` headers mid-image and captured scroll-reveal
  sections at their pre-animation (`opacity:0`) state — whole bands looked blank,
  and the artifacts flowed into `session_report` thumbnails. Full-page captures
  are now **prepared**: sticky/fixed elements neutralized to `static`, animations
  disabled, `prefers-reduced-motion: reduce` emulated, and the page scrolled to
  fire IntersectionObserver reveals — then everything is restored exactly. The
  applied steps are reported as `capture_prep`; `screenshot_session(raw=true)`
  opts out. Covers `screenshot_session`, the `observe="screenshot"` action path,
  `test_url`, `test_project`, and `test_responsive`. Viewport and element-clip
  shots are untouched (they capture exactly what's on screen).
- **#22 — Non-deterministic crawl order made re-tests incomparable.** With
  `max_pages` smaller than the site, consecutive crawls picked a *different*
  page subset each run (set-iteration order), so per-page findings silently
  appeared/vanished between reports and a page that merely fell out of the
  window looked "fixed." The crawl is now **deterministic**: links are sorted
  before the cap, so the same site yields the same subset every time.

### Added
- **Sitemap-seeded crawl.** When `sitemap.xml` (or a `sitemap_index.xml` /
  robots.txt `Sitemap:` line) exists, the page list is seeded from it (sorted),
  matching what search engines index; falls back to link discovery for the rest.
  `use_sitemap=false` forces a pure link-crawl. Results flag `crawl_sources`.
- **Honest coverage reporting.** `crawl_project`/`test_project` now return
  `discovered_total` and `pages_not_crawled[]`/`pages_not_tested[]` (≤100, else
  a count + `truncated` flag) — a hit cap is never silent.
- **`max_pages=0` = test the whole site** — explicit opt-in to an unbounded
  crawl, stopping at a 2000-page safety ceiling (`config.MAX_PAGES_CEILING`,
  env-overridable) and flagging `ceiling_hit` rather than truncating silently.
- **Coverage delta.** `test_project` returns a `coverage` block
  (`pages_added`/`pages_dropped`, `compared_to`) vs the project's previous
  report, so a shifted crawl window is visible even when it does shift.

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
