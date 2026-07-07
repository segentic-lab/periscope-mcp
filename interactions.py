import os
import time
from datetime import datetime
from playwright.async_api import Page
import config
from nav import resilient_goto


# Injected before page scripts so it captures every interaction across a
# session. Records the worst interaction latency (input -> next paint) per
# interactionId from the Event Timing API — a REAL INP for the interactions
# Periscope drives (Playwright clicks/typing fire trusted events the API sees),
# not the TBT lab proxy Lighthouse falls back to.
# Records one entry per real interaction (input -> next paint) from the Event
# Timing API, with target/type/timestamp, so a long interactive test yields a
# graphable INP time series. add_init_script runs this as raw source, so it
# must be a self-invoking IIFE. CAP bounds memory on very long runs (oldest
# interactions drop). Playwright's clicks/typing fire trusted events that get a
# real interactionId — so this is a REAL INP, not the TBT lab proxy.
INP_INIT_SCRIPT = """(() => {
    if (window.__periscope_inp) return;
    const CAP = %d;
    const byId = new Map();  // interactionId -> {id, ts, epoch_ms, dur, type, target, url}
    window.__periscope_inp = byId;
    const sel = (el) => {
        if (!el || !el.tagName) return null;
        let s = el.tagName.toLowerCase();
        if (el.id) return s + '#' + el.id;
        if (el.className && typeof el.className === 'string') {
            const c = el.className.trim().split(/\\s+/)[0];
            if (c) s += '.' + c;
        }
        return s;
    };
    try {
        const po = new PerformanceObserver((list) => {
            for (const e of list.getEntries()) {
                if (!e.interactionId) continue;                 // real interactions only
                let rec = byId.get(e.interactionId);
                if (!rec) {
                    rec = { id: e.interactionId, ts: Math.round(e.startTime),
                            epoch_ms: Math.round(performance.timeOrigin + e.startTime),
                            dur: 0, type: e.name, target: sel(e.target), url: location.href };
                    byId.set(e.interactionId, rec);
                    if (byId.size > CAP) byId.delete(byId.keys().next().value);
                }
                if (e.duration > rec.dur) rec.dur = e.duration;
                // prefer the semantic trigger over pointer/mouse noise
                if (e.name === 'click' || e.name === 'keydown' || e.name === 'keyup') rec.type = e.name;
            }
        });
        po.observe({ type: 'event', durationThreshold: 16, buffered: true });
    } catch (e) { /* Event Timing unsupported */ }
})();""" % config.MAX_INTERACTION_LOG


async def _flush_and_read_interactions(page) -> list:
    """Return the recorded interaction records, flushing pending entries first."""
    try:
        return await page.evaluate(
            """() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(() => {
                const m = window.__periscope_inp;
                r(m ? Array.from(m.values()) : []);
            }, 0))))"""
        ) or []
    except Exception:
        return []


async def read_inp(page) -> dict | None:
    """Session INP so far: worst interaction latency (ms) + count, or None if
    no measurable interaction has happened yet."""
    log = await _flush_and_read_interactions(page)
    if not log:
        return None
    return {"inp_ms": round(max(r["dur"] for r in log)), "interaction_count": len(log)}


async def read_interaction_log(page) -> list:
    """Full per-interaction INP records (sorted by time) for export/graphing."""
    log = await _flush_and_read_interactions(page)
    return sorted(log, key=lambda r: r["ts"])


async def clear_interaction_log(page):
    try:
        await page.evaluate("() => { if (window.__periscope_inp) window.__periscope_inp.clear(); }")
    except Exception:
        pass


async def _click_with_overlay_fallback(page: Page, selector: str, force: bool = False) -> str:
    """Click, falling back to an element-level dispatch when a full-screen
    overlay intercepts the pointer (Radix/shadcn portals — issue #15).

    Playwright's pointer click hit-tests at coordinates, so a `fixed inset-0`
    portal overlay swallows it (force=True doesn't help: it skips the check and
    the overlay still receives the pointer). dispatch_event('click') fires the
    event directly on the element, bypassing the hit-test entirely.

    Returns the click method used: 'pointer' or 'js_dispatch'.
    """
    locator = page.locator(selector).first
    try:
        await locator.click(force=force, timeout=5000)
        return "pointer"
    except Exception as e:
        if "intercepts pointer events" not in str(e):
            raise
        await locator.dispatch_event("click")
        return "js_dispatch"


async def click_element(page: Page, selector: str, force: bool = False) -> dict:
    """Click an element and return post-click state.

    Args:
        page: Playwright page
        selector: CSS selector
        force: If True, bypass actionability checks (useful for overlays)
    """
    locator = page.locator(selector).first
    if not force:
        await locator.wait_for(state="visible", timeout=10000)
    method = await _click_with_overlay_fallback(page, selector, force)
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    # SPA routers often push the new URL slightly after the network settles —
    # without this beat the reported URL/screenshot are pre-navigation (issue #9).
    await page.wait_for_timeout(250)
    result = {"url": page.url, "title": await page.title()}
    if method != "pointer":
        result["click_method"] = method
        result["overlay_bypassed"] = True
    return result


_DATE_TYPES = {"date", "time", "datetime-local", "month", "week"}


def _owner_page(page) -> Page:
    """Unwrap a Frame (iframe session) to its owning Page for Page-only APIs."""
    return page if hasattr(page, "keyboard") else page.page


def _as_bool(val) -> bool:
    """Interpret step-level bool fields that MCP clients may send as strings."""
    if isinstance(val, str):
        return val.lower() not in ("false", "0", "")
    return bool(val)


def _q(text: str) -> str:
    """Escape a string for embedding in a double-quoted Playwright selector."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


async def _mouse_drag(page: Page, source_sel: str, target_sel: str):
    """Manual stepped-mouse drag for pointer-tracking DnD libraries.

    drag_to()'s fast synthetic sequence is ignored by libraries that track the
    pointer themselves with a drag-start threshold and animation-frame pacing
    (@hello-pangea/dnd and similar): the threshold crossing and paced moves
    below are what make them recognize a drag.
    """
    owner = _owner_page(page)
    source = page.locator(source_sel).first
    target = page.locator(target_sel).first
    await source.wait_for(state="visible", timeout=10000)
    await target.wait_for(state="visible", timeout=10000)
    await source.scroll_into_view_if_needed()
    sb = await source.bounding_box()
    tb = await target.bounding_box()
    if not sb or not tb:
        raise Exception(f"Could not resolve bounding boxes for drag ('{source_sel}' -> '{target_sel}')")
    sx, sy = sb["x"] + sb["width"] / 2, sb["y"] + sb["height"] / 2
    tx, ty = tb["x"] + tb["width"] / 2, tb["y"] + tb["height"] / 2

    mouse = owner.mouse
    await mouse.move(sx, sy)
    await mouse.down()
    await mouse.move(sx + 8, sy + 8, steps=2)   # cross the drag-start threshold
    await owner.wait_for_timeout(100)           # let the library register the lift
    await mouse.move(tx, ty, steps=15)          # paced travel
    await owner.wait_for_timeout(100)
    await mouse.move(tx, ty)                    # final move event over the target
    await owner.wait_for_timeout(50)
    await mouse.up()


async def _get_input_type(page: Page, selector: str) -> str | None:
    """Get the type attribute of an input element."""
    return await page.evaluate("""(selector) => {
        const el = document.querySelector(selector);
        return el ? el.type : null;
    }""", selector)


async def _fill_date_input(page: Page, selector: str, value: str):
    """Fill a date/datetime input and trigger React-compatible change events."""
    await page.evaluate("""([selector, value]) => {
        const el = document.querySelector(selector);
        if (!el) throw new Error('Element not found: ' + selector);
        const nativeSetter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
        ).set;
        nativeSetter.call(el, value);
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }""", [selector, value])


async def force_fill(page: Page, selector: str, value: str):
    """Fill an input bypassing actionability checks. Uses force=True."""
    input_type = await _get_input_type(page, selector)
    if input_type in _DATE_TYPES:
        await _fill_date_input(page, selector, value)
    else:
        locator = page.locator(selector).first
        await locator.fill(value, force=True)


async def fill_field(page: Page, selector: str, value: str):
    """Fill a single form field."""
    input_type = await _get_input_type(page, selector)
    if input_type in _DATE_TYPES:
        await _fill_date_input(page, selector, value)
    else:
        locator = page.locator(selector).first
        await locator.wait_for(state="visible", timeout=10000)
        await locator.click()
        await locator.fill(value)


async def fill_form(page: Page, fields: list[dict], submit_selector: str = None, force: bool = False) -> dict:
    """Fill form fields and optionally submit.

    Args:
        page: Playwright page
        fields: List of {"selector": str, "value": str}
        submit_selector: Optional CSS selector for submit button
        force: Bypass actionability checks (overlays/dialogs blocking inputs)

    Returns dict with result info.
    """
    filled = []
    for f in fields:
        if force:
            await force_fill(page, f["selector"], f["value"])
        else:
            await fill_field(page, f["selector"], f["value"])
        filled.append(f["selector"])

    result = {"fields_filled": filled, "submitted": False}

    if submit_selector:
        submit = page.locator(submit_selector).first
        await submit.wait_for(state="visible", timeout=10000)
        await submit.click()
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        result["submitted"] = True
        result["url"] = page.url
        result["title"] = await page.title()

    return result


async def select_option(
    page: Page, selector: str, value: str = None, label: str = None, index: int = None,
    element_index: int = 0,
) -> dict:
    """Select from native <select> or custom dropdown (Radix/shadcn combobox).

    Detection: checks el.tagName == 'SELECT' vs role='combobox' / aria-haspopup.
    Native: uses locator.select_option().
    Custom: clicks to open, then finds option via cascade of selectors.

    Args:
        element_index: which match of `selector` to target (0-based) — for pages
            with multiple attribute-less <select> elements (issue #16).
    """
    if ">>" in selector:
        return {"success": False, "error":
                "Playwright locator syntax ('>>') is not supported — use a plain CSS "
                "selector plus element_index to target the Nth match "
                "(e.g. selector='select', element_index=1 for the second <select>)."}

    el_info = await page.evaluate("""(args) => {
        const [selector, idx] = args;
        const els = document.querySelectorAll(selector);
        const el = els[idx];
        if (!el) return { found: null, total: els.length };
        return { found: {
            tagName: el.tagName.toLowerCase(),
            role: el.getAttribute('role'),
            ariaHasPopup: el.getAttribute('aria-haspopup'),
        }, total: els.length };
    }""", [selector, element_index])

    if not el_info["found"]:
        if el_info["total"]:
            return {"success": False, "error":
                    f"element_index {element_index} out of range: '{selector}' matches "
                    f"{el_info['total']} element(s) (0-based)"}
        return {"success": False, "error": f"Element not found: {selector}"}
    el_info = el_info["found"]

    locator = page.locator(selector).nth(element_index)

    # Native <select>
    if el_info["tagName"] == "select":
        if value is not None:
            await locator.select_option(value=value)
        elif label is not None:
            await locator.select_option(label=label)
        elif index is not None:
            await locator.select_option(index=index)
        else:
            return {"success": False, "error": "Provide value, label, or index"}
        return {"success": True, "method": "native_select"}

    # Custom dropdown (combobox, radix, shadcn, etc.)
    await locator.click()
    await page.wait_for_timeout(300)  # let dropdown animate open

    search_text = label or value or ""
    if not search_text and index is not None:
        # Try to pick by index from visible options
        option = page.locator('[role="option"]').nth(index)
        try:
            await option.wait_for(state="visible", timeout=5000)
            await option.click()
            return {"success": True, "method": "custom_dropdown", "matched_by": "index"}
        except Exception:
            return {"success": False, "error": f"Could not find option at index {index}"}

    # Cascade of selectors for finding the option by text
    option_selectors = [
        f'[role="option"]:has-text("{_q(search_text)}")',
        f'[role="menuitem"]:has-text("{_q(search_text)}")',
        f'li:has-text("{_q(search_text)}")',
        f'[data-value="{_q(value)}"]' if value else None,
        f'text="{_q(search_text)}"',
    ]

    for opt_sel in option_selectors:
        if not opt_sel:
            continue
        try:
            option = page.locator(opt_sel).first
            await option.wait_for(state="visible", timeout=3000)
            await option.click()
            return {"success": True, "method": "custom_dropdown", "matched_by": opt_sel}
        except Exception:
            continue

    # Fallback failed — close dropdown by pressing Escape
    await page.keyboard.press("Escape")
    return {"success": False, "error": f"Could not find option matching '{search_text}' in custom dropdown"}


async def get_elements(
    page: Page, selector: str, max_results: int = 50,
    attributes: list = None, full_text: bool = False,
) -> list[dict]:
    """Get matching elements with their attributes.

    Args:
        attributes: extra HTML attributes to include per element (data-*, aria-*, style, ...)
        full_text: return complete text content instead of the 80-char preview
    """
    elements = await page.evaluate("""(args) => {
        const [selector, maxResults, extraAttrs, fullText] = args;
        const els = document.querySelectorAll(selector);
        const results = [];
        for (let i = 0; i < Math.min(els.length, maxResults); i++) {
            const el = els[i];
            const rect = el.getBoundingClientRect();
            const cls = el.className && typeof el.className === 'string'
                ? el.className.trim().split(/\\s+/).slice(0, 3).join(' ') : null;
            const text = (el.textContent || '').trim();
            const entry = {
                tag: el.tagName.toLowerCase(),
                index: i,
                text: fullText ? text : text.substring(0, 80),
                id: el.id || null,
                class: cls || null,
                href: el.getAttribute('href') || null,
                value: el.value || null,
                type: el.getAttribute('type') || null,
                name: el.getAttribute('name') || null,
                visible: rect.width > 0 && rect.height > 0,
                enabled: !el.disabled,
                aria_label: el.getAttribute('aria-label') || null,
                role: el.getAttribute('role') || null,
                placeholder: el.getAttribute('placeholder') || null,
            };
            for (const attr of (extraAttrs || [])) {
                entry[attr] = el.getAttribute(attr);
            }
            results.push(entry);
        }
        return results;
    }""", [selector, max_results, attributes, full_text])
    return elements


# Full-page capture preparation (issue #23). Playwright stitches a full-page
# screenshot from viewport-height slices, which double-paints sticky/fixed
# headers mid-image and captures scroll-triggered reveal sections at their
# pre-animation (opacity:0 / translated) state — whole bands look blank. We
# prepare the page for a faithful capture, then restore it exactly.
_CAP_STYLE = ("*,*::before,*::after{animation:none!important;transition:none!important;"
              "scroll-behavior:auto!important;animation-duration:0s!important}")

_STICKY_APPLY_JS = """() => {
    let n = 0;
    for (const el of document.querySelectorAll('body *')) {
        const pos = getComputedStyle(el).position;
        if (pos === 'sticky' || pos === 'fixed') {
            el.setAttribute('data-periscope-pos', el.style.position || '');
            el.style.setProperty('position', 'static', 'important');
            n++;
        }
    }
    return n;
}"""

_STICKY_RESTORE_JS = """() => {
    for (const el of document.querySelectorAll('[data-periscope-pos]')) {
        const orig = el.getAttribute('data-periscope-pos');
        el.style.removeProperty('position');
        if (orig) el.style.position = orig;
        el.removeAttribute('data-periscope-pos');
    }
}"""

_STYLE_APPLY_JS = """(css) => {
    let s = document.getElementById('periscope-cap-style');
    if (!s) { s = document.createElement('style'); s.id = 'periscope-cap-style';
              s.textContent = css; document.head.appendChild(s); }
}"""

_STYLE_REMOVE_JS = "() => { const s = document.getElementById('periscope-cap-style'); if (s) s.remove(); }"

# Scroll through the whole page (then back to top) so IntersectionObserver-driven
# reveals fire before capture. Bounded steps; short waits keep it quick.
_REVEAL_SCROLL_JS = """async () => {
    const h = document.body.scrollHeight;
    const step = Math.max(200, window.innerHeight);
    for (let y = 0; y <= h; y += step) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 30)); }
    window.scrollTo(0, 0);
    await new Promise(r => setTimeout(r, 30));
}"""


async def _apply_capture_prep(page: Page) -> list[str]:
    """Prepare a page for a faithful full-page screenshot. Returns the list of
    preparations actually applied (for honest `capture_prep` reporting)."""
    prep = []
    try:
        await page.emulate_media(reduced_motion="reduce")
        prep.append("reduced_motion")
    except Exception:
        pass
    try:
        await page.evaluate(_STYLE_APPLY_JS, _CAP_STYLE)
        prep.append("animations_disabled")
    except Exception:
        pass
    try:
        if await page.evaluate(_STICKY_APPLY_JS):
            prep.append("sticky_neutralized")
    except Exception:
        pass
    try:
        await page.evaluate(_REVEAL_SCROLL_JS)
        prep.append("reveals_forced")
    except Exception:
        pass
    return prep


async def _restore_capture_prep(page: Page) -> None:
    """Undo _apply_capture_prep — restore positions, styles, and media emulation."""
    for js in (_STICKY_RESTORE_JS, _STYLE_REMOVE_JS):
        try:
            await page.evaluate(js)
        except Exception:
            pass
    try:
        await page.emulate_media(reduced_motion="no-preference")
    except Exception:
        pass


async def capture_full_page(page, path: str, prepare: bool = True) -> list[str]:
    """Full-page screenshot to `path`. With prepare=True (default), neutralizes
    sticky/fixed elements + disables animations + emulates reduced motion +
    scrolls to fire reveals, then restores the page. Returns capture_prep list.
    Accepts a Page or Frame (frames capture via their owning Page)."""
    owner = _owner_page(page)
    prep = await _apply_capture_prep(owner) if prepare else []
    try:
        await owner.screenshot(path=path, full_page=True)
    finally:
        if prepare:
            await _restore_capture_prep(owner)
    return prep


async def take_screenshot(page: Page, project_name: str, label: str = "", screenshot_dir: str = None,
                          prepare: bool = True, meta: dict = None) -> str:
    """Take a full-page screenshot and save it. Returns the file path.

    prepare=True (default) prepares the page for a faithful capture (see
    capture_full_page); pass prepare=False for a raw stitch. When `meta` is
    given, the applied preparations are recorded as meta['capture_prep'].
    Accepts a Page or a Frame (iframe sessions) — Frames capture via their owning Page.
    """
    base_dir = screenshot_dir if screenshot_dir else config.SCREENSHOT_DIR
    project_dir = os.path.join(base_dir, project_name)
    os.makedirs(project_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    suffix = f"_{label}" if label else ""
    filename = f"interactive_{timestamp}{suffix}.png"
    filepath = os.path.join(project_dir, filename)
    prep = await capture_full_page(page, filepath, prepare=prepare)
    if meta is not None:
        meta["capture_prep"] = prep
    return filepath


async def attach_observation(session, result: dict, args: dict, label: str) -> dict:
    """Bundle the caller-chosen post-action observation into `result`.

    observe: "screenshot" (default, == legacy behavior) | "none" | "map" | "checks"

    Keeps the action surface opt-out: multi-step flows pass observe="none" through
    setup steps (no image tokens, no round-trip), then "map"/"screenshot"/"checks"
    on the step that matters. Default preserves the historical screenshot_path.
    Imports the map/checks builders lazily to avoid a handlers<->interactions cycle.
    """
    observe = args.get("observe", "screenshot")
    if observe == "none":
        return result
    if observe == "screenshot":
        result["screenshot_path"] = await take_screenshot(
            session.page, session.project_name, label, screenshot_dir=session.screenshot_dir,
            prepare=not args.get("raw", False), meta=result)
    elif observe == "map":
        from handlers.agent_speed import build_page_map
        result["page_map"] = await build_page_map(session, args)
    elif observe == "checks":
        from handlers.analysis import run_session_checks
        result["checks"] = await run_session_checks(session, args.get("checks"))
    else:
        result["observe_warning"] = (
            f"unknown observe={observe!r}; skipped (use none|screenshot|map|checks)")
    return result


async def execute_steps(
    page: Page,
    steps: list[dict],
    project_name: str = "default",
    continue_on_error: bool = False,
    screenshot_dir: str = None,
    touch=None,
) -> dict:
    """Execute a sequence of interaction steps.

    Supported step actions:
        click: {action: "click", selector: str, force: bool?}
        force_click: {action: "force_click", selector: str} — click bypassing actionability checks
        fill: {action: "fill", selector: str, value: str}
        type: {action: "type", selector: str, text: str}
        select: {action: "select", selector: str, value: str}
        wait: {action: "wait", timeout: int (ms)}
        wait_for: {action: "wait_for", selector: str, state: str (visible|hidden|attached|detached)}
        screenshot: {action: "screenshot", label: str?}
        navigate: {action: "navigate", url: str}
        hover: {action: "hover", selector: str}
        press_key: {action: "press_key", key: str}
        check: {action: "check", selector: str}
        uncheck: {action: "uncheck", selector: str}
        scroll_to: {action: "scroll_to", selector: str} — scroll element into view
        scroll_within: {action: "scroll_within", selector: str, direction: "up"|"down"|"left"|"right", amount: int?}
        evaluate_js: {action: "evaluate_js", script: str} — run JS snippet, result stored in step_result
        drag: {action: "drag", selector: str, target: str, method?: "auto"|"mouse"} — drag element to target;
            "mouse" does a stepped manual drag for pointer-tracking DnD libs that ignore drag_to
        right_click: {action: "right_click", selector: str} — right-click / context menu
        wait_for_text: {action: "wait_for_text", text: str, selector?: str, timeout?: int} — wait for text to appear
        go_back: {action: "go_back"} — browser back button
        go_forward: {action: "go_forward"} — browser forward button
        upload_file: {action: "upload_file", selector: str, files: [str]} — set files on file input
        wait_for_network: {action: "wait_for_network", url_pattern: str, method?: str, timeout?: int}
        force_fill: {action: "force_fill", selector: str, value: str} — fill bypassing actionability checks
        select_option: {action: "select_option", selector: str, value?: str, label?: str, index?: int} — native or custom dropdown

    Returns dict with step results and screenshots.
    """
    results = []
    screenshots = []

    for i, step in enumerate(steps):
        action = step.get("action")
        step_result = {"step": i, "action": action, "success": True}

        if touch:
            touch()  # keep the owning session from idle-expiring during long runs

        try:
            if action == "click":
                force = _as_bool(step.get("force", False))
                locator = page.locator(step["selector"]).first
                if not force:
                    await locator.wait_for(state="visible", timeout=10000)
                method = await _click_with_overlay_fallback(page, step["selector"], force)
                if method != "pointer":
                    step_result["click_method"] = method
                    step_result["overlay_bypassed"] = True
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                step_result["url"] = page.url

            elif action == "force_click":
                method = await _click_with_overlay_fallback(page, step["selector"], force=True)
                if method != "pointer":
                    step_result["click_method"] = method
                    step_result["overlay_bypassed"] = True
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                step_result["url"] = page.url

            elif action == "fill":
                await fill_field(page, step["selector"], step["value"])

            elif action == "type":
                locator = page.locator(step["selector"]).first
                await locator.wait_for(state="visible", timeout=10000)
                await locator.type(step["text"])

            elif action == "select":
                locator = page.locator(step["selector"]).first
                await locator.wait_for(state="visible", timeout=10000)
                await locator.select_option(step["value"])

            elif action == "wait":
                import asyncio
                await asyncio.sleep(step.get("timeout", 1000) / 1000)

            elif action == "wait_for":
                state = step.get("state", "visible")
                locator = page.locator(step["selector"]).first
                await locator.wait_for(state=state, timeout=step.get("timeout", 10000))

            elif action == "screenshot":
                label = step.get("label", f"step_{i}")
                path = await take_screenshot(page, project_name, label, screenshot_dir=screenshot_dir)
                screenshots.append(path)
                step_result["screenshot_path"] = path

            elif action == "navigate":
                _, downgraded = await resilient_goto(page, step["url"])
                if downgraded:
                    step_result["wait_downgraded"] = "load"
                step_result["url"] = page.url

            elif action == "hover":
                locator = page.locator(step["selector"]).first
                await locator.wait_for(state="visible", timeout=10000)
                await locator.hover()

            elif action == "press_key":
                await _owner_page(page).keyboard.press(step["key"])

            elif action == "check":
                locator = page.locator(step["selector"]).first
                await locator.wait_for(state="visible", timeout=10000)
                await locator.check()

            elif action == "uncheck":
                locator = page.locator(step["selector"]).first
                await locator.wait_for(state="visible", timeout=10000)
                await locator.uncheck()

            elif action == "scroll_to":
                locator = page.locator(step["selector"]).first
                await locator.scroll_into_view_if_needed(timeout=10000)

            elif action == "scroll_within":
                direction = step.get("direction", "down")
                amount = step.get("amount", 300)
                dx, dy = 0, 0
                if direction == "down":
                    dy = amount
                elif direction == "up":
                    dy = -amount
                elif direction == "right":
                    dx = amount
                elif direction == "left":
                    dx = -amount
                await page.evaluate("""(args) => {
                    const [selector, dx, dy] = args;
                    const el = document.querySelector(selector);
                    if (!el) { window.scrollBy(dx, dy); return; }
                    // Fall back to window.scrollBy for body/html or non-scrollable elements
                    const tag = el.tagName.toLowerCase();
                    const style = getComputedStyle(el);
                    const overflowY = style.overflowY;
                    const overflowX = style.overflowX;
                    const scrollableY = el.scrollHeight > el.clientHeight && (overflowY === 'scroll' || overflowY === 'auto' || overflowY === 'overlay');
                    const scrollableX = el.scrollWidth > el.clientWidth && (overflowX === 'scroll' || overflowX === 'auto' || overflowX === 'overlay');
                    const isWindow = tag === 'body' || tag === 'html';
                    if (isWindow || (!scrollableY && dy !== 0) || (!scrollableX && dx !== 0)) {
                        window.scrollBy(dx, dy);
                    } else {
                        el.scrollBy(dx, dy);
                    }
                }""", [step["selector"], dx, dy])

            elif action == "evaluate_js":
                result = await page.evaluate(step["script"])
                step_result["result"] = result

            elif action == "drag":
                # Cheap in-page DOM fingerprint: DnD failures are silent
                # (pointer-tracking and HTML5-native pipelines ignore synthetic
                # drags), so flag drags that changed nothing (issue #9).
                _dom_hash = """() => {
                    let h = 0;
                    const s = document.body.innerHTML;
                    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
                    return h;
                }"""
                before_hash = await page.evaluate(_dom_hash)
                if step.get("method") == "mouse":
                    await _mouse_drag(page, step["selector"], step["target"])
                else:
                    source = page.locator(step["selector"]).first
                    target = page.locator(step["target"]).first
                    await source.drag_to(target)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                if await page.evaluate(_dom_hash) == before_hash:
                    step_result["warning"] = (
                        "drag produced no observable DOM change — the widget may use "
                        "pointer-tracking or native HTML5 DnD that ignores synthetic drags; "
                        "verify with an assertion, retry with method:'mouse', or use the "
                        "keyboard fallback (focus handle, Space, arrows, Space)"
                    )

            elif action == "right_click":
                locator = page.locator(step["selector"]).first
                force = _as_bool(step.get("force", False))
                if not force:
                    await locator.wait_for(state="visible", timeout=10000)
                await locator.click(button="right", force=force)

            elif action == "wait_for_text":
                text = step["text"]
                container = step.get("selector", "body")
                timeout = step.get("timeout", 30000)
                locator = page.locator(container).get_by_text(text).first
                await locator.wait_for(state="visible", timeout=timeout)

            elif action == "go_back":
                await _owner_page(page).go_back(wait_until=config.WAIT_UNTIL)
                step_result["url"] = page.url

            elif action == "go_forward":
                await _owner_page(page).go_forward(wait_until=config.WAIT_UNTIL)
                step_result["url"] = page.url

            elif action == "upload_file":
                locator = page.locator(step["selector"]).first
                await locator.set_input_files(step["files"])

            elif action == "wait_for_network":
                url_pattern = step["url_pattern"]
                method_filter = step.get("method")
                timeout = step.get("timeout", 30000)

                # Must be a plain function: Playwright calls predicates
                # synchronously, and a coroutine object is always truthy.
                def match_request(response, _pat=url_pattern, _meth=method_filter):
                    if _pat not in response.url:
                        return False
                    if _meth and response.request.method.upper() != _meth.upper():
                        return False
                    return True

                response = await _owner_page(page).wait_for_event(
                    "response", predicate=match_request, timeout=timeout
                )
                step_result["matched_url"] = response.url
                step_result["status"] = response.status

            elif action == "force_fill":
                await force_fill(page, step["selector"], step["value"])

            elif action == "select_option":
                result = await select_option(
                    page, step["selector"],
                    value=step.get("value"),
                    label=step.get("label"),
                    index=step.get("index"),
                    element_index=int(step.get("element_index") or 0),
                )
                step_result["select_result"] = result

            else:
                step_result["success"] = False
                step_result["error"] = f"Unknown action: {action}"

        except Exception as e:
            # A KeyError here is a missing step field (step["url_pattern"] etc.) —
            # str(KeyError) is just "'url_pattern'", which is cryptic (issue #19).
            if isinstance(e, KeyError) and e.args:
                message = (f"missing required field '{e.args[0]}' for action '{action}' "
                           f"(see the interact_and_test steps schema for per-action fields)")
            else:
                message = str(e)
            step_result["success"] = False
            step_result["error"] = message
            results.append(step_result)
            if not continue_on_error:
                return {
                    "completed": i + 1,
                    "total_steps": len(steps),
                    "success": False,
                    "error": f"Step {i} ({action}) failed: {message}",
                    "steps": results,
                    "screenshots": screenshots,
                }
            continue  # already recorded — don't append the failed step twice

        results.append(step_result)

    return {
        "completed": len(steps),
        "total_steps": len(steps),
        "success": all(r["success"] for r in results),
        "steps": results,
        "screenshots": screenshots,
        "final_url": page.url,
        "final_title": await page.title(),
    }


async def test_form_validation(page: Page, form_selector: str = None) -> dict:
    """Find forms, submit empty, and collect validation messages."""
    selector = form_selector or "form"
    forms_data = await page.evaluate("""(selector) => {
        const forms = document.querySelectorAll(selector);
        return Array.from(forms).map((form, idx) => ({
            index: idx,
            action: form.action || '',
            method: form.method || 'get',
            id: form.id || null,
            fields: Array.from(form.querySelectorAll('input, select, textarea')).map(f => ({
                tag: f.tagName.toLowerCase(),
                type: f.type || null,
                name: f.name || null,
                id: f.id || null,
                required: f.required,
                pattern: f.getAttribute('pattern') || null,
            })).filter(f => f.type !== 'hidden' && f.type !== 'submit' && f.type !== 'button')
        }));
    }""", selector)

    results = []
    for form_info in forms_data:
        # Try submitting the form empty to trigger validation
        validation = await page.evaluate("""([selector, formIndex]) => {
            const form = document.querySelectorAll(selector)[formIndex];
            if (!form) return [];
            const invalids = form.querySelectorAll(':invalid');
            return Array.from(invalids).map(el => ({
                tag: el.tagName.toLowerCase(),
                name: el.name || el.id || null,
                type: el.type || null,
                validationMessage: el.validationMessage || '',
                required: el.required,
            }));
        }""", [selector, form_info["index"]])

        # Look for custom error elements near the form
        custom_errors = await page.evaluate("""([selector, formIndex]) => {
            const form = document.querySelectorAll(selector)[formIndex];
            if (!form) return [];
            const errorSelectors = [
                '.error', '.field-error', '.form-error', '.invalid-feedback',
                '[class*="error"]', '[class*="invalid"]', '[role="alert"]'
            ];
            const errors = [];
            for (const sel of errorSelectors) {
                form.querySelectorAll(sel).forEach(el => {
                    const text = el.textContent.trim();
                    if (text) errors.push(text);
                });
            }
            return [...new Set(errors)];
        }""", [selector, form_info["index"]])

        results.append({
            "form": form_info,
            "invalid_fields": validation,
            "custom_errors": custom_errors,
        })

    return {
        "forms_found": len(forms_data),
        "results": results,
    }


async def measure_interaction_timing(
    page: Page, selector: str, wait_for: str = None, wait_for_network: str = None,
) -> dict:
    """Click an element and measure time until condition is met.

    Args:
        page: Playwright page
        selector: Element to click
        wait_for: Optional selector to wait for appearing
        wait_for_network: Optional URL substring — measure until the matching
            response completes. Use this for handlers that fire a request
            asynchronously after the click: plain networkidle can settle on an
            early idle window *before* the request even starts and report a
            misleadingly tiny time (issue #17).

    Returns timing info in ms, plus the real INP of the click when measurable.
    """
    locator = page.locator(selector).first
    await locator.wait_for(state="visible", timeout=10000)

    start = time.time()
    start_epoch_ms = start * 1000
    matched = {}

    if wait_for_network:
        owner = _owner_page(page)
        # Arm the waiter BEFORE clicking — a fast response would otherwise be missed.
        async with owner.expect_response(
            lambda r: wait_for_network in r.url, timeout=30000
        ) as resp_info:
            await locator.click()
        response = await resp_info.value
        matched = {"matched_url": response.url, "matched_status": response.status}
        waited = f"network response matching '{wait_for_network}'"
    elif wait_for:
        await locator.click()
        target = page.locator(wait_for).first
        await target.wait_for(state="visible", timeout=30000)
        waited = wait_for
    else:
        await locator.click()
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        waited = "networkidle"

    elapsed_ms = round((time.time() - start) * 1000)

    # Real INP of this click, from Event Timing entries recorded since start.
    inp_ms = None
    records = [r for r in await read_interaction_log(page)
               if r.get("epoch_ms", 0) >= start_epoch_ms - 50]
    if records:
        inp_ms = round(max(r["dur"] for r in records))

    result = {
        "clicked": selector,
        "waited_for": waited,
        "elapsed_ms": elapsed_ms,
        "measures": "click to " + (
            "matching network response" if wait_for_network
            else "selector visible" if wait_for
            else "first network-idle window (may under-measure async handlers — "
                 "pass wait_for_network to bind to a specific request)"),
        "interaction_to_next_paint_ms": inp_ms,
        "url": page.url,
        "title": await page.title(),
    }
    result.update(matched)
    return result
