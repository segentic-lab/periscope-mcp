"""compare_pages: the same steps on two URLs (staging vs live, before vs
after), then side-by-side screenshots + pixel diff, structured facts diff,
visible-text diff, performance and network-weight deltas."""
import difflib
import os
import time
from datetime import datetime

import config
import interactions
from nav import resilient_goto
from runtime import get_tester, project_manager
from sessions import real_page
from utils import compare_screenshots

from .registry import tool

_FACTS_JS = """() => {
    const q = (s) => document.querySelector(s);
    const meta = (n) => { const m = q('meta[name="' + n + '"]'); return m ? m.content : null; };
    return {
        title: document.title || null,
        meta_description: meta('description'),
        canonical: q('link[rel="canonical"]') ? q('link[rel="canonical"]').href : null,
        h1: Array.from(document.querySelectorAll('h1')).map(h => (h.textContent || '').trim()),
        hreflang: Array.from(document.querySelectorAll('link[rel="alternate"][hreflang]'))
            .map(l => ({ lang: l.getAttribute('hreflang'), href: l.href })),
        lang: document.documentElement.getAttribute('lang'),
        robots: meta('robots'),
        og_title: (q('meta[property="og:title"]') || {}).content || null,
        og_image: (q('meta[property="og:image"]') || {}).content || null,
        links: document.querySelectorAll('a[href]').length,
        images: document.images.length,
        forms: document.forms.length,
        text: (document.body ? document.body.innerText : '') || '',
        weight_bytes: performance.getEntriesByType('resource').reduce((n, r) => n + (r.transferSize || 0), 0)
            + ((performance.getEntriesByType('navigation')[0] || {}).transferSize || 0),
    };
}"""

_FACT_KEYS = ("title", "meta_description", "canonical", "h1", "hreflang", "lang", "robots",
              "og_title", "og_image", "links", "images", "forms")


async def _capture(t, label: str, url: str, project, args: dict, shot_dir: str) -> dict:
    """Load one side, run the shared steps, capture everything comparable."""
    from checks.functionality import get_performance_metrics
    descriptor, viewport = args.get("_descriptor"), args.get("_viewport")

    own_ctx = None
    page = None
    try:
        if descriptor is not None:
            own_ctx = await t.new_device_context(project, descriptor)
            context = own_ctx
        elif project:
            context = await t.get_context(project)
        else:
            own_ctx = await t.new_ephemeral_context()
            context = own_ctx
        page = await context.new_page()
        page.set_default_timeout(config.TIMEOUT)
        if viewport:
            await page.set_viewport_size(viewport)
        await page.add_init_script(interactions.INP_INIT_SCRIPT)
        t0 = time.time()
        response, downgraded = await resilient_goto(page, url)
        load_ms = round((time.time() - t0) * 1000)
    except Exception as e:
        # Close the page too: in a project's shared context nothing else would.
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass
        if own_ctx is not None:
            try:
                await own_ctx.close()
            except Exception:
                pass
        return {"url": url, "error": f"failed to load: {e}"}

    try:
        side = {"url": url, "final_url": page.url, "status_code": response.status if response else None,
                "load_time_ms": load_ms}
        if downgraded:
            side["wait_downgraded"] = "load"
        if args.get("consent"):
            import consent
            try:
                side["consent"] = await consent.apply(page, args["consent"])
            except Exception as e:
                side["consent"] = {"success": False, "error": f"consent handling failed: {str(e)[:200]}"}
        if args.get("steps"):
            from sessions import attach_request_counter
            steps = await interactions.execute_steps(page, args["steps"], "compare",
                                                     continue_on_error=False, screenshot_dir=shot_dir,
                                                     request_counter=attach_request_counter(page))
            side["steps_ok"] = bool(steps.get("success"))
            if not steps.get("success"):
                side["steps_error"] = steps.get("error")
        os.makedirs(shot_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        side["screenshot_path"] = os.path.join(shot_dir, f"compare_{label}_{stamp}.png")
        side["capture_prep"] = await interactions.capture_full_page(page, side["screenshot_path"])
        facts = await page.evaluate(_FACTS_JS)
        side["_text"] = facts.pop("text", "")
        side["weight_kb"] = round((facts.pop("weight_bytes", 0) or 0) / 1024, 1)
        side["title"] = facts.get("title")
        side["facts"] = {k: facts.get(k) for k in _FACT_KEYS}
        try:
            side["performance"] = await get_performance_metrics(page)
        except Exception:
            side["performance"] = {}
        if args.get("run_checks"):
            from handlers.analysis import run_session_checks

            class _S:  # minimal session-like for run_session_checks
                pass
            s = _S()
            s.page, s.url, s.project_name, s.screenshot_dir = page, page.url, "compare", shot_dir
            checks = await run_session_checks(s, args["run_checks"])
            side["issues"] = checks["issues"]
            side["issue_count"] = checks["issue_count"]
        return side
    except Exception as e:
        return {"url": url, "error": f"capture failed: {e}"}
    finally:
        try:
            await page.close()
        except Exception:
            pass
        if own_ctx is not None:
            try:
                await own_ctx.close()
            except Exception:
                pass


def _text_diff(a: str, b: str) -> dict:
    la, lb = [l.strip() for l in a.splitlines() if l.strip()], [l.strip() for l in b.splitlines() if l.strip()]
    sm = difflib.SequenceMatcher(None, la, lb, autojunk=False)
    added, removed = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ("delete", "replace"):
            removed.extend(la[i1:i2])
        if op in ("insert", "replace"):
            added.extend(lb[j1:j2])
    return {"similarity": round(sm.ratio(), 3), "added": added[:40], "removed": removed[:40],
            "added_count": len(added), "removed_count": len(removed)}


@tool("compare_pages")
async def handle_compare_pages(args: dict) -> dict:
        url_a, url_b = args.get("url_a"), args.get("url_b")
        if not url_a or not url_b:
            return {"success": False, "error": "compare_pages requires url_a and url_b "
                                               "(e.g. staging and live versions of the same page)."}
        t = await get_tester()
        # Resolve the device once, up front: an unknown name is an input
        # error for the whole call, not a per-side crash.
        args = dict(args)
        if args.get("device"):
            import devices
            try:
                kind, resolved = devices.resolve_device(
                    args["device"], t.playwright.devices if t.playwright else {})
            except ValueError as e:
                return {"success": False, "error": str(e)}
            args["_descriptor" if kind == "descriptor" else "_viewport"] = resolved
        project_a = args.get("project")
        project_b = args.get("project_b") or project_a
        proj = project_manager.get(project_a) if project_a else None
        shot_dir = os.path.join(proj.screenshot_dir if proj and proj.screenshot_dir else config.SCREENSHOT_DIR,
                                "compare")

        a = await _capture(t, "a", url_a, project_a, args, shot_dir)
        b = await _capture(t, "b", url_b, project_b, args, shot_dir)
        text_a, text_b = a.pop("_text", ""), b.pop("_text", "")

        result = {"success": True, "a": a, "b": b}
        if "error" in a or "error" in b:
            failed = [s for s, side in (("a", a), ("b", b)) if "error" in side]
            result.update({"same": False, "screenshot_diff": None, "facts_diff": None,
                           "text_diff": None, "performance_delta": None, "weight_delta_kb": None,
                           "note": f"side {' and '.join(failed)} could not be captured — see its error; "
                                   "the other side's capture is complete"})
            return result

        max_diff = float(args.get("max_diff_percent") or 1.0)
        cmp = compare_screenshots(a["screenshot_path"], b["screenshot_path"],
                                  threshold=int(args.get("threshold") or 10))
        shot = {"diff_percentage": cmp.get("diff_percentage"), "diff_image_path": cmp.get("diff_image_path"),
                "dimensions": cmp.get("dimensions"), "max_diff_percent": max_diff,
                "passed": cmp.get("success", False) and cmp.get("diff_percentage", 100) <= max_diff}
        facts_diff = {k: {"a": a["facts"].get(k), "b": b["facts"].get(k)}
                      for k in _FACT_KEYS if a["facts"].get(k) != b["facts"].get(k)}
        text = _text_diff(text_a, text_b)
        perf_delta = {}
        for k, va in (a.get("performance") or {}).items():
            vb = (b.get("performance") or {}).get(k)
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)) and not isinstance(va, bool):
                perf_delta[k] = round(vb - va, 3)
        result.update({
            "screenshot_diff": shot,
            "facts_diff": facts_diff,
            "text_diff": text,
            "performance_delta": perf_delta,
            "weight_delta_kb": round(b["weight_kb"] - a["weight_kb"], 1),
            "load_time_delta_ms": b["load_time_ms"] - a["load_time_ms"],
            "same": bool(shot["passed"] and not facts_diff and text["similarity"] >= 0.98),
        })
        if args.get("run_checks"):
            result["issue_count_delta"] = b.get("issue_count", 0) - a.get("issue_count", 0)
        return result
