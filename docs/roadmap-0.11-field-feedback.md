# Periscope 0.11 roadmap — from the klimacar + Vibrant Longevity field feedback

Written 2026-11-02 after a full read of the codebase (0.10.4, commit 6e3380e) and
of the two field reports at the repo root:

- `FEEDBACK-klimacar-session.md` — Astro + Cloudflare Workers, Stripe checkout, PWAs (Aug–Sep 2026)
- `IDEJE-ORODJA-AgenticWP-Periscope.md` — WordPress/Elementor/WPML, staging→live (Oct 2026)

Nothing has shipped since 0.10.4 (last commit 2026-07-19), so every item below is
still open. The repo is healthy: 39 unit tests and all 88 e2e tests pass on
Python 3.14 with the snap Chromium (2026-11-02).

## 1. What the feedback asks for, mapped onto the code

| # | Ask | Source | What exists today | Gap | Size |
|---|-----|--------|-------------------|-----|------|
| A1 | Click that "succeeds" but changes nothing → hint or auto-escalate | klimacar 1, 8 | `interactions._click_with_overlay_fallback` only escalates on *"intercepts pointer events"*, and escalates to `dispatch_event` — a **synthetic** click that hosted payment pages ignore. The `drag` step already has a DOM-hash "no observable change" detector. | No change detection on click/fill; the one fallback that exists is the wrong one for Stripe (synthetic, not trusted). | S |
| A2 | TLS override for broken certs | klimacar 2 | Every browser context is created with `ignore_https_errors=True` (`tester.py:102,150`, `advanced.py:29`, `auth.py:212`). `web_fetch(verify_ssl=false)` exists for the static path. | **Already works**; the agent didn't know. Static `web_fetch` fails with a raw httpx error instead of saying "retry with verify_ssl=false or render=true". Docs don't mention that sessions ignore cert errors. | XS (docs + error text) |
| A3 | Fresh-deploy mode: hard reload, SW/cache purge, "served by service worker" flag | klimacar 3 | `navigate_session` has back/forward/reload only. Project-less sessions get a fresh context (no cache) but project sessions share a long-lived context. Playwright exposes `Response.from_service_worker` (verified). | No hard reload, no site-data purge, no SW visibility. | S–M |
| A4 | PWA/manifest inspection + device/UA presets | klimacar 4, ideje 4 | `set_viewport` presets are viewport-only (no UA, no touch). Playwright ships 143 device descriptors (verified). | No `check_pwa`; no real device emulation; `open_session` can't take a viewport/device, forcing open → set_viewport → reload. | M |
| A5 | Download assertion: disposition, content-type | klimacar 5 | `download_file` captures path/size/sha256/text_head. | Missing `content_type`, `content_disposition`, and whether the browser *navigated* instead of downloading. | XS |
| A6 | Iframe ergonomics (list frames, Stripe recipe) | klimacar 6 | `select_iframe(selector)` works cross-origin (Playwright frames aren't same-origin-restricted). `get_page_map` ignores frames. | No frame inventory; no recipe in SKILL.md/AGENTS.md. | S |
| A7 | Session staleness self-diagnosis | klimacar 7 | Most results carry `url`/`title`. Selectors are re-resolved per call (no cached refs), so "stale element ref" can't happen here. | A navigation counter per session (`nav_generation`) in every result is cheap; the "stale ref" half of the ask doesn't apply. | XS |
| A8 | `navigate_session` goto + wait_until | klimacar 8 | `navigate_session` cannot navigate to a URL at all; agents use an `interact_and_test` navigate step. | Add `action="goto"` with `url`, `wait_for` (selector) and `wait_for_network`. | S |
| A9 | Screenshot results with scroll + viewport | klimacar 8 | Not returned. | Add `viewport` + `scroll` to screenshot results. | XS |
| B1 | Realistic mouse hover (steps, warm-up) | ideje 1 | `hover` step = `locator.hover()` (one move). `_mouse_drag` already does stepped moves. | SmartMenus-style menus need several `mousemove`s. | XS–S |
| B2 | Lighthouse: `runs`, `warmup`, summary (LCP element + phases, KB by domain, TTFB warning) | ideje 2 | `run_lighthouse` runs once and returns scores/metrics/failed audits; full JSON saved. | Multi-run median, warm-up visit, and the summary are JSON post-processing on data Lighthouse already emits (`largest-contentful-paint-element`, `network-requests`, `server-response-time`). | M |
| B3 | Long-page screenshots: tiles / max_height | ideje 3 | Full-page is the default everywhere; an 11 000 px page becomes an unreadable thumbnail. | `screenshot_session(mode="tiles", tile_height=1600)` → N files; and/or `max_height`. | S |
| B4 | `open_session(device/viewport)` | ideje 4 | see A4 | see A4 | (A4) |
| B5 | `network_summary`: KB per domain/type, biggest files, before/after an interaction | ideje 5 | `network_log` stores url/status/method/type/timestamp — **no sizes**. | Capture sizes (in-page `performance.getEntriesByType('resource')` has `transferSize`; `response.request.sizes()` for the rest) and aggregate. | M |
| B6 | Consent helper (`consent: accept\|deny`) | ideje 6 | Nothing. | A CMP selector table (Complianz, Cookiebot, CookieYes, OneTrust, Borlabs, Usercentrics, Didomi, Osano, Iubenda, Klaro, WP cookie plugins) as a tool, a step action, and an `open_session(consent=...)` convenience. | S–M |
| B7 | Compare two URLs (staging vs live) | ideje 7 | `compare_screenshots`, `test_url`, `page_state diff` exist as pieces. | A `compare_pages(url_a, url_b, …)` tool that runs the same steps on both, diffs screenshots, title/meta/H1/text, performance numbers, and network weight. | M |
| C1 | Change-log line per tool result | skupno | `session_report` journals everything. | Low priority; a `journal_line` on result objects is trivial once the rest exists. | XS |

Sizes: XS < 1 h, S ≈ half a day, M ≈ 1–2 days including e2e fixtures.

## 2. Findings from reading the code that the feedback didn't mention

- **The Stripe trap is the overlay fallback itself.** When Playwright's actionability
  check times out (5 s) the code dispatches a synthetic `click` event and returns
  success with `click_method: "js_dispatch"`. Hosted payment pages check
  `isTrusted`, so that path can never work for them, yet it reports success.
  `force=true` *is* a trusted CDP pointer click at coordinates. A1 should make the
  chain `pointer → force pointer → js_dispatch`, and always report whether the
  page changed.
- **`describe_tools` is stale** in places: `web_fetch` is listed as `url, max_length?,
  raw_html?, verify_ssl?`; `navigate_session` doesn't mention `observe`; the "new"
  category still says 0.10. Every release should refresh it (make it part of the
  release checklist, or generate it from `tool_schemas.py`).
- **`network_log` has no timing or size**, which blocks B5 and makes
  `get_network_log` weaker than the console equivalent.
- **`set_viewport` doesn't reload**, so JS-driven responsive layouts (Elementor
  breakpoints) stay in the old state; that's why the ideje author reloaded by hand.
  A4 should offer `reload=true`.
- **`auth.py` form-login success heuristic** is `url changed and "/login" not in
  url`. Works, but WordPress uses `/wp-login.php` and WPML adds language prefixes;
  not a reported bug, just a fragile spot to watch for the WP-heavy use case.
- `.claude/settings.local.json` still allowlists `mcp__website-tester__*` tools
  (old server name). Harmless, dead config.
- The venv is on Python 3.14; CI tests 3.11–3.13. Unit tests pass on 3.14, so a
  3.14 CI entry is cheap insurance.

## 3. Proposed release plan

### 0.11.0 — "Honest actions" (the klimacar batch, all small)

Theme: an action never reports success for something that visibly didn't happen,
and the common paper cuts go away. Every item reuses existing machinery.

1. **A1 change detection + escalation** (`interactions.py`)
   - Before any click/fill: snapshot `(url, dom_hash, network_log length, focused element)`.
   - After: compare → `changed: true|false`, `change: ["url","dom","network"]`.
   - Fallback chain for a click that doesn't change anything or isn't actionable:
     `pointer → pointer(force=True) → dispatch_event`, reported as `click_method`
     plus `attempts: [...]`. Opt-in `strategy: "auto"` on `click_element` and the
     `click` step retries through the chain; default behaviour stays single-attempt
     but adds `hint: "no page change detected — retry with force=true or
     strategy='auto'"`.
   - Same for `fill`: after filling, read back `el.value`; if it differs, retry
     with the native setter + input/change events (the date-input path already
     does this) and report `fill_method`.
2. **A8 `navigate_session(action="goto", url, wait_for?, wait_for_network?)`**
   folds navigate → wait → map into one call. Also `wait_until` override per call.
3. **A3 fresh-deploy mode**
   - `navigate_session(action="reload", hard=true)` → CDP `Network.setCacheDisabled`
     + `Network.clearBrowserCache` before reload.
   - `navigate_session(action="clear_site_data")` → unregister service workers,
     delete `caches.*`, clear storage for the origin, then reload.
   - `served_by_service_worker: true` on `open_session`/`goto`/`reload` results when
     the main document response has `from_service_worker`.
4. **A5** `download_file` adds `content_type`, `content_disposition`, `navigated_instead: bool`.
5. **A6** `get_page_map(include_frames=true)` → `frames: [{selector, url, name,
   cross_origin, session_hint}]`; SKILL.md + AGENTS.md get a "Stripe / hosted
   checkout" recipe (frames, `force`, trusted clicks, `wait_for_network`).
6. **A7 + A9** `nav_generation` on every session result; `viewport` + `scroll` on
   screenshot results.
7. **A2** docs + a friendlier SSL error in static `web_fetch`.
8. **B1** `hover` step/tool: stepped mouse path (default 8 steps from the current
   pointer position, small settle), `steps` override. Zero-risk default change.
9. Refresh `describe_tools`, AGENTS.md, SKILL.md, CHANGELOG; e2e fixtures:
   `stripe_like.html` (click that only reacts to trusted events), `sw.html`
   (service-worker page), `menu_hover.html` (menu that needs N mousemoves).

### 0.11.1 — "Sessions that start right" (device + consent)

1. **A4/B4 `open_session(device?, width?, height?, consent?)`**
   - `device` = Playwright descriptor name (`"iPhone 14"`, `"Galaxy S9+"`, …) or the
     existing presets. A device needs its own context (UA, DPR, touch), so the
     session gets a private context **seeded with the project's `storage_state`**
     (the pattern `record_session` already uses) — auth is preserved.
   - `set_viewport(reload=true)` for JS-breakpoint layouts.
   - Samsung Internet: add a custom descriptor (UA + client hints) to a small
     `devices.py` so the klimacar install-bug class is reproducible.
2. **B6 consent helper**: `handle_consent(session_id, action="accept"|"deny"|"dismiss")`
   with a CMP table (selector + button text per vendor, incl. Slovenian/German
   labels), returned as `{cmp: "complianz", action, found: true}`. Exposed as a
   step action and as `open_session(consent=...)`.
3. **A4 `check_pwa(url|session_id)`**: manifest fetch + validation (name, icons
   ≥192/512, `display`, `start_url` in scope, theme colour), SW registration
   state + scope, `beforeinstallprompt` observed within N s, CDP
   `Page.getInstallabilityErrors` when available.

### 0.12.0 — "Measure and compare" (the Vibrant Longevity batch)

1. **B5 sizes in the network log + `network_summary`**: capture `transferSize`
   (in-page resource timing merged by URL, fallback `request.sizes()`), then
   `network_summary(session_id, since="open"|"last_clear"|timestamp)` → bytes by
   domain, by resource type, top-N heaviest, third-party share, requests
   before/after a marker. Doubles as the "did Deny really block GA/Meta/Vimeo?" check.
2. **B2 Lighthouse upgrades**: `runs: N` (median of each metric, min/max spread),
   `warmup: true` (one discarded visit), and a `summary` block: LCP element +
   phases (TTFB / load delay / load time / render delay), bytes by domain, TTFB
   with a warning above 2 s, top 5 opportunities with savings.
3. **B3 tiled screenshots**: `screenshot_session(mode="tiles", tile_height=1600)`
   returns `tiles: [paths]`; full-page results over 6 000 px get a note
   suggesting tiles. `test_url` keeps full-page (reports need one image).
4. **B7 `compare_pages(url_a, url_b, steps?, viewport?, consent?, checks?)`**:
   same steps on both, side-by-side screenshots + pixel diff, structured diff of
   title/meta/canonical/H1/hreflang, visible-text diff, performance deltas,
   network-weight deltas. This is the staging→live tool the WP workflow was missing.

### Deferred / not planned

- C1 journal line per result — add when `compare_pages` lands; by then the
  shape is obvious.
- "Trusted CDP events as the force path" — already the case for `force=true`;
  no separate work.
- Stale element refs (A7 second half) — not applicable to a selector-based API.

## 4. Open decisions for the owner

1. **Default click behaviour**: keep single-attempt + hint (safe, no double
   submits) or make `strategy="auto"` the default? I recommend the hint as
   default and `auto` opt-in, because an auto-retried "Pay" click is a real risk.
2. **Where device sessions live**: a private context per device session (my
   recommendation) means cookies set *during* that session don't flow back into
   the project's shared context. Acceptable?
3. **`network_summary` size source**: in-page resource timing is free but only
   covers the current document; `request.sizes()` is complete but costs an extra
   round-trip per response. I'd start with resource timing and fall back.
4. **Release cadence**: three releases as above, or one bigger 0.11 with everything?

## 5. Suggested order of work (first session)

A1 → A8 → A3 → B1 → A5/A6/A7/A9 → A2 docs → refresh describe_tools/AGENTS/SKILL →
release 0.11.0. Each item: failing e2e fixture test first, then the change,
`pytest` (unit) + `pytest tests/e2e` green, CHANGELOG entry.
