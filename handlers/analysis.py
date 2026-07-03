"""Analysis tools (forms, links, keyboard nav, tables, toasts, contrast, checks)."""
import asyncio
import json
import os
import time

import config
import interactions
from crawler import Crawler
from runtime import auth_handler, get_tester, project_manager, session_manager
from sessions import real_page

from .registry import tool


@tool("test_form_validation")
async def handle_test_form_validation(args: dict) -> dict:
        t = await get_tester()
        session_id = args.get("session_id")
        url = args.get("url")
        form_selector = args.get("form_selector")

        cleanup = None
        if session_id:
            session = session_manager.get_session(session_id)
            page = session.page
        elif url:
            page, cleanup = await t.open_page(args.get("project"), url)
        else:
            return {"success": False, "error": "Provide either 'url' or 'session_id'"}

        try:
            result = await interactions.test_form_validation(page, form_selector)
            result["url"] = page.url
            return result
        finally:
            if cleanup:
                await cleanup()


@tool("check_links")
async def handle_check_links(args: dict) -> dict:
        from checks.functionality import check_all_links

        t = await get_tester()
        session_id = args.get("session_id")
        url = args.get("url")

        cleanup = None
        if session_id:
            session = session_manager.get_session(session_id)
            page = session.page
        elif url:
            page, cleanup = await t.open_page(args.get("project"), url)
        else:
            return {"success": False, "error": "Provide either 'url' or 'session_id'"}

        try:
            result = await check_all_links(
                page,
                page.url,
                check_external=args.get("check_external", False),
                max_links=args.get("max_links", 100),
            )
            return result
        finally:
            if cleanup:
                await cleanup()


@tool("measure_interaction")
async def handle_measure_interaction(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        result = await interactions.measure_interaction_timing(
            session.page,
            args["selector"],
            wait_for=args.get("wait_for"),
        )
        session.url = result["url"]
        screenshot_path = await interactions.take_screenshot(
            session.page, session.project_name, "after_measure", screenshot_dir=session.screenshot_dir)
        result["screenshot_path"] = screenshot_path
        return result


@tool("test_keyboard_navigation")
async def handle_test_keyboard_navigation(args: dict) -> dict:
        from checks.accessibility import check_keyboard_navigation

        t = await get_tester()
        session_id = args.get("session_id")
        url = args.get("url")
        max_tabs = args.get("max_tabs", 50)

        cleanup = None
        if session_id:
            session = session_manager.get_session(session_id)
            page = session.page
        elif url:
            page, cleanup = await t.open_page(args.get("project"), url)
        else:
            return {"success": False, "error": "Provide either 'url' or 'session_id'"}

        try:
            result = await check_keyboard_navigation(page, max_tabs)
            result["url"] = page.url
            return result
        finally:
            if cleanup:
                await cleanup()


@tool("run_checks_on_session")
async def handle_run_checks_on_session(args: dict) -> dict:
        from checks.visual import check_visual
        from checks.accessibility import check_accessibility
        from checks.functionality import check_functionality, check_seo, get_performance_metrics
        from checks.geo import check_geo

        session = session_manager.get_session(args["session_id"])
        checks = args.get("checks", ["visual", "accessibility", "functionality", "seo", "performance", "geo"])
        page = session.page

        all_issues = []
        performance = {}

        if "visual" in checks:
            all_issues.extend(await check_visual(page))
        if "accessibility" in checks:
            all_issues.extend(await check_accessibility(page))
        if "functionality" in checks:
            all_issues.extend(await check_functionality(page))
        if "seo" in checks:
            all_issues.extend(await check_seo(page))
        if "geo" in checks:
            all_issues.extend(await check_geo(page))
        if "performance" in checks:
            performance = await get_performance_metrics(page)

        screenshot_path = await interactions.take_screenshot(
            page, session.project_name, "after_checks", screenshot_dir=session.screenshot_dir)

        issues_by_severity = {}
        issues_by_type = {}
        for issue in all_issues:
            sev = issue.get("severity", "unknown")
            typ = issue.get("type", "unknown")
            issues_by_severity[sev] = issues_by_severity.get(sev, 0) + 1
            issues_by_type[typ] = issues_by_type.get(typ, 0) + 1

        return {
            "url": session.url,
            "title": await page.title(),
            "issues": all_issues,
            "issue_count": len(all_issues),
            "issues_by_severity": issues_by_severity,
            "issues_by_type": issues_by_type,
            "performance": performance,
            "screenshot_path": screenshot_path,
        }


def _find_lighthouse_cmd():
    """Locate the Lighthouse CLI (or npx to bootstrap it).

    Searches PATH first, then nvm installs (~/.nvm or $NVM_DIR) — MCP server
    processes are often spawned without nvm's PATH. Returns (cmd, bin_dir,
    note); cmd is None when no Node toolchain exists at all.
    """
    import glob
    import re
    import shutil

    npm_tip = "Tip: 'npm install -g lighthouse' makes runs start faster than npx."

    lh = shutil.which("lighthouse")
    if lh:
        return [lh], os.path.dirname(lh), None
    npx = shutil.which("npx")
    if npx:
        return [npx, "--yes", "lighthouse"], os.path.dirname(npx), npm_tip

    # nvm installs, newest Node version first
    nvm_dir = os.environ.get("NVM_DIR", os.path.expanduser("~/.nvm"))
    def _ver(path):
        m = re.search(r"/v(\d+)\.(\d+)\.(\d+)/", path + "/")
        return tuple(int(g) for g in m.groups()) if m else (0, 0, 0)
    for bin_dir in sorted(glob.glob(os.path.join(nvm_dir, "versions/node/*/bin")), key=_ver, reverse=True):
        lh = os.path.join(bin_dir, "lighthouse")
        if os.path.exists(lh):
            return [lh], bin_dir, None
        npx = os.path.join(bin_dir, "npx")
        if os.path.exists(npx):
            return [npx, "--yes", "lighthouse"], bin_dir, npm_tip

    return None, None, None


@tool("get_interaction_log")
async def handle_get_interaction_log(args: dict) -> dict:
        from datetime import datetime
        session = session_manager.get_session(args["session_id"])
        fmt = args.get("format", "json")
        if fmt not in ("json", "csv"):
            return {"success": False, "error": "format must be 'json' or 'csv'"}

        log = await interactions.read_interaction_log(session.page)
        if not log:
            return {"success": True, "interaction_count": 0,
                    "message": "No interactions recorded yet. INP is measured for the "
                               "interactions Periscope drives (clicks, typing); drive some first."}

        durs = sorted(round(r["dur"]) for r in log)

        def pct(p):
            return durs[min(len(durs) - 1, int(round((p / 100) * (len(durs) - 1))))]

        summary = {
            "interaction_count": len(log),
            "inp_ms": {"p50": pct(50), "p75": pct(75), "p90": pct(90), "p98": pct(98), "worst": durs[-1]},
        }
        # Real-INP percentile: Google's INP is roughly the 98th percentile of
        # interaction latencies (worst for small counts).
        summary["inp_ms_representative"] = summary["inp_ms"]["p98"] if len(log) >= 50 else summary["inp_ms"]["worst"]

        rows = [{"t_ms": r["ts"], "epoch_ms": r["epoch_ms"], "inp_ms": round(r["dur"]),
                 "type": r["type"], "target": r["target"], "url": r["url"]} for r in log]

        os.makedirs(config.REPORTS_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(config.REPORTS_DIR, f"interactions_{session.project_name}_{ts}.{fmt}")
        if fmt == "csv":
            import csv, io
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
            with open(path, "w") as f:
                f.write(buf.getvalue())
        else:
            with open(path, "w") as f:
                json.dump({"summary": summary, "interactions": rows}, f, indent=2)

        if args.get("clear"):
            await interactions.clear_interaction_log(session.page)

        # Small inline sample (first 3 + worst 3) — the file has everything
        worst3 = sorted(rows, key=lambda r: r["inp_ms"], reverse=True)[:3]
        return {
            "success": True,
            **summary,
            "format": fmt,
            "report_path": path,
            "sample_first": rows[:3],
            "sample_worst": worst3,
            "message": f"{len(rows)} interactions saved to {path}. "
                       f"For graphing: plot inp_ms over t_ms (per-page) or epoch_ms (absolute).",
        }


@tool("run_lighthouse")
async def handle_run_lighthouse(args: dict) -> dict:
        from datetime import datetime

        url = args["url"]
        categories = args.get("categories") or ["performance", "accessibility", "best-practices", "seo"]
        device = args.get("device", "mobile")
        timeout_s = int(args.get("timeout", 180))

        cmd, node_bin_dir, note = _find_lighthouse_cmd()
        if cmd is None:
            return {
                "success": False,
                "error": "Lighthouse requires Node.js, and none was found (checked PATH and ~/.nvm). "
                         "Install it with nvm, then re-run this tool:",
                "install_commands": [
                    "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash",
                    '\\. "$HOME/.nvm/nvm.sh"',
                    "nvm install --lts",
                    "npm install -g lighthouse",
                ],
            }

        cmd += [
            url,
            "--output=json",
            "--output-path=stdout",
            "--quiet",
            "--chrome-flags=--headless=new --no-sandbox --disable-gpu",
            f"--only-categories={','.join(categories)}",
        ]
        if device == "desktop":
            cmd.append("--preset=desktop")

        env = dict(os.environ)
        # The lighthouse/npx launchers are '#!/usr/bin/env node' scripts — the
        # subprocess must be able to find node even when it came from ~/.nvm.
        if node_bin_dir:
            env["PATH"] = node_bin_dir + os.pathsep + env.get("PATH", "")
        if config.CHROMIUM_PATH:
            env["CHROME_PATH"] = config.CHROMIUM_PATH  # lighthouse's chrome-launcher honors this

        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            return {"success": False, "error": f"Lighthouse timed out after {timeout_s}s"}

        try:
            report = json.loads(stdout.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {
                "success": False,
                "error": f"Lighthouse failed (exit {proc.returncode}): {stderr.decode(errors='replace')[-500:]}",
            }

        scores = {
            key: round(cat["score"] * 100) if cat.get("score") is not None else None
            for key, cat in report.get("categories", {}).items()
        }
        audits = report.get("audits", {})
        metric_ids = [
            "first-contentful-paint", "largest-contentful-paint", "total-blocking-time",
            "cumulative-layout-shift", "speed-index", "interactive",
        ]
        metrics = {
            mid: {
                "value": audits[mid].get("numericValue"),
                "display": audits[mid].get("displayValue"),
                "score": audits[mid].get("score"),
            }
            for mid in metric_ids if mid in audits
        }
        failed = [
            {"id": aid, "title": a.get("title"), "score": a["score"], "display": a.get("displayValue")}
            for aid, a in audits.items()
            if a.get("score") is not None and a["score"] < 0.9
            and a.get("scoreDisplayMode") in ("binary", "numeric", "metricSavings")
        ]
        failed.sort(key=lambda a: a["score"])

        # Persist the full report next to Periscope's own reports
        os.makedirs(config.REPORTS_DIR, exist_ok=True)
        report_path = os.path.join(
            config.REPORTS_DIR, f"lighthouse_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        result_note = {"note": note} if note else {}
        return {
            "success": True,
            **result_note,
            "url": report.get("finalDisplayedUrl") or report.get("finalUrl") or url,
            "device": device,
            "lighthouse_version": report.get("lighthouseVersion"),
            "scores": scores,
            "metrics": metrics,
            "failed_audits": failed[:40],
            "failed_audit_count": len(failed),
            "report_path": report_path,
        }


@tool("check_color_contrast")
async def handle_check_color_contrast(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        selector = args.get("selector", "p, span, a, li, td, th, h1, h2, h3, h4, h5, h6, label, button")
        level = args.get("level", "AA")
        max_results = args.get("max_results", 50)

        # Get computed colors for text elements
        elements = await session.page.evaluate("""(args) => {
            const [selector, maxResults] = args;
            const els = document.querySelectorAll(selector);
            const results = [];

            function parseColor(color) {
                // Parse rgb/rgba string to [r, g, b]
                const match = color.match(/rgba?\\(([\\d.]+),\\s*([\\d.]+),\\s*([\\d.]+)/);
                if (match) return [parseFloat(match[1]), parseFloat(match[2]), parseFloat(match[3])];
                return null;
            }

            function luminance(r, g, b) {
                const [rs, gs, bs] = [r, g, b].map(c => {
                    c = c / 255;
                    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
                });
                return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
            }

            function contrastRatio(l1, l2) {
                const lighter = Math.max(l1, l2);
                const darker = Math.min(l1, l2);
                return (lighter + 0.05) / (darker + 0.05);
            }

            // Dedupe by style signature (issue #4 follow-up): contrast is a
            // property of the color combination, not the element. 60 nav items
            // sharing one style consume ONE slot, so the budget reaches the
            // table headers / buttons further down instead of filling up on
            // the first repeated style in DOM order.
            const styleGroups = new Map();  // signature -> result index
            let truncatedGroups = 0;
            for (const el of els) {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;

                const style = window.getComputedStyle(el);
                const fg = parseColor(style.color);
                if (!fg) continue;

                // Most text elements have a transparent background and inherit
                // the effective one from an ancestor — walk up to find it.
                function isTransparent(colorStr) {
                    const a = colorStr.match(/rgba\\([^,]+,[^,]+,[^,]+,\\s*([\\d.]+)/);
                    return colorStr === 'transparent' || (a && parseFloat(a[1]) < 0.1);
                }
                let bgEl = el;
                let bgColor = style.backgroundColor;
                while (bgEl && isTransparent(bgColor)) {
                    bgEl = bgEl.parentElement;
                    bgColor = bgEl ? window.getComputedStyle(bgEl).backgroundColor : 'rgb(255, 255, 255)';
                }
                if (!bgEl) bgColor = 'rgb(255, 255, 255)';  // default page background
                const bg = parseColor(bgColor);
                if (!bg) continue;

                const fgLum = luminance(fg[0], fg[1], fg[2]);
                const bgLum = luminance(bg[0], bg[1], bg[2]);
                const ratio = contrastRatio(fgLum, bgLum);
                const fontSize = parseFloat(style.fontSize);
                const fontWeight = parseInt(style.fontWeight) || 400;
                const isLargeText = fontSize >= 24 || (fontSize >= 18.66 && fontWeight >= 700);

                const signature = style.color + '|' + bgColor + '|' + (isLargeText ? 'L' : 'N');
                if (styleGroups.has(signature)) {
                    results[styleGroups.get(signature)].elements_with_style++;
                    continue;
                }
                if (results.length >= maxResults) { truncatedGroups++; continue; }

                let selector_str = el.tagName.toLowerCase();
                if (el.id) selector_str = '#' + el.id;
                else if (el.className && typeof el.className === 'string')
                    selector_str += '.' + el.className.trim().split(/\\s+/)[0];

                styleGroups.set(signature, results.length);
                results.push({
                    selector: selector_str,
                    text: (el.textContent || '').trim().substring(0, 40),
                    ratio: Math.round(ratio * 100) / 100,
                    large: isLargeText,
                    foreground: style.color,
                    background: bgColor,
                    elements_with_style: 1,
                });
            }
            return { results, truncatedGroups };
        }""", [selector, max_results])
        truncated_groups = elements["truncatedGroups"]
        elements = elements["results"]

        # Evaluate against WCAG thresholds
        aa_normal = 4.5
        aa_large = 3.0
        aaa_normal = 7.0
        aaa_large = 4.5

        failures = []
        for el in elements:
            ratio = el["ratio"]
            is_large = el["large"]
            threshold = (aa_large if is_large else aa_normal) if level == "AA" else (aaa_large if is_large else aaa_normal)
            if ratio < threshold:
                el["required"] = threshold
                failures.append(el)

        return {
            "level": level,
            "checked": len(elements),  # unique text-style combinations sampled
            "elements_represented": sum(e["elements_with_style"] for e in elements),
            "style_groups_skipped": truncated_groups,
            "fail_count": len(failures),
            "failures": failures[:30],
            "failures_truncated": len(failures) > 30,
        }


@tool("get_page_html")
async def handle_get_page_html(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        selector = args.get("selector")
        max_length = args.get("max_length", 50000)

        if selector:
            try:
                elements = await session.page.evaluate("""(args) => {
                const [selector, maxLen] = args;
                const stripBase64 = html => html.replace(/(<[^>]+(?:src|href|data|style)=["'])data:[^;]+;base64,[^"']+/gi, '$1[base64-removed]');
                const els = document.querySelectorAll(selector);
                const results = [];
                let totalLen = 0;
                for (const el of els) {
                    const html = stripBase64(el.outerHTML);
                    if (totalLen + html.length > maxLen) {
                        results.push({
                            tag: el.tagName.toLowerCase(),
                            id: el.id || null,
                            outer_html: html.substring(0, maxLen - totalLen) + '... [truncated]',
                        });
                        break;
                    }
                    results.push({
                        tag: el.tagName.toLowerCase(),
                        id: el.id || null,
                        outer_html: html,
                    });
                    totalLen += html.length;
                }
                return results;
            }""", [selector, max_length])
            except Exception as e:
                if "not a valid selector" in str(e) or "SyntaxError" in str(e):
                    return {
                        "success": False,
                        "error": f"Invalid CSS selector '{selector}'. This tool accepts standard "
                                 f"CSS only — Playwright pseudo-classes like :has-text() and "
                                 f":visible are not supported here.",
                    }
                raise
            return {
                "selector": selector,
                "count": len(elements),
                "elements": elements,
            }
        else:
            html = await session.page.content()
            import re
            html = re.sub(r'(<[^>]+(?:src|href|data|style)=["\'])data:[^;]+;base64,[^"\']+', r'\1[base64-removed]', html, flags=re.IGNORECASE)
            truncated = len(html) > max_length
            return {
                "html": html[:max_length] + ("... [truncated]" if truncated else ""),
                "truncated": truncated,
                "full_length": len(html),
            }


@tool("get_table_data")
async def handle_get_table_data(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        selector = args.get("selector", "table")
        max_rows = args.get("max_rows", 100)

        table_data = await session.page.evaluate("""(args) => {
            const [selector, maxRows] = args;
            const table = document.querySelector(selector);
            if (!table) return null;

            // Extract headers
            let headers = [];
            const thead = table.querySelector('thead');
            if (thead) {
                const headerRow = thead.querySelector('tr');
                if (headerRow) {
                    headers = Array.from(headerRow.querySelectorAll('th, td')).map(
                        cell => cell.textContent.trim()
                    );
                }
            }

            // If no thead, use first row as headers
            if (headers.length === 0) {
                const firstRow = table.querySelector('tr');
                if (firstRow) {
                    headers = Array.from(firstRow.querySelectorAll('th, td')).map(
                        cell => cell.textContent.trim()
                    );
                }
            }

            // Extract body rows
            const rows = [];
            const tbody = table.querySelector('tbody') || table;
            const trs = tbody.querySelectorAll('tr');
            const startIdx = (!thead && trs.length > 0) ? 1 : 0;  // skip header row if no thead

            for (let i = startIdx; i < trs.length && rows.length < maxRows; i++) {
                const cells = trs[i].querySelectorAll('td, th');
                if (cells.length === 0) continue;
                const row = {};
                for (let j = 0; j < cells.length; j++) {
                    const key = j < headers.length ? headers[j] : `col_${j}`;
                    row[key] = cells[j].textContent.trim();
                }
                rows.push(row);
            }

            // Total rows count
            const allBodyRows = tbody.querySelectorAll('tr');
            const totalRows = allBodyRows.length - ((!thead && allBodyRows.length > 0) ? 1 : 0);

            return { headers, rows, total_rows: totalRows };
        }""", [selector, max_rows])

        if table_data is None:
            return {"success": False, "error": f"No table found matching '{selector}'"}

        return {
            "success": True,
            "selector": selector,
            "headers": table_data["headers"],
            "rows": table_data["rows"],
            "rows_returned": len(table_data["rows"]),
            "total_rows": table_data["total_rows"],
        }


@tool("get_toast_messages")
async def handle_get_toast_messages(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        wait_ms = args.get("wait_ms", 0)
        custom_selector = args.get("selector")

        if wait_ms > 0:
            await asyncio.sleep(wait_ms / 1000)

        if custom_selector:
            toast_selectors = [custom_selector]
        else:
            toast_selectors = [
                '[role="alert"]', '[role="status"]',
                '[aria-live="polite"]', '[aria-live="assertive"]',
                '.toast', '.notification',
                '[data-sonner-toast]', '[data-radix-toast-announce]',
                '.Toastify__toast',
                '[class*="toast"]', '[class*="notification"]', '[class*="snackbar"]',
            ]

        messages = await session.page.evaluate("""(selectors) => {
            const seen = new Set();
            const results = [];
            for (const sel of selectors) {
                try {
                    const els = document.querySelectorAll(sel);
                    for (const el of els) {
                        const text = el.textContent.trim();
                        if (!text || seen.has(text)) continue;
                        seen.add(text);
                        const rect = el.getBoundingClientRect();
                        results.push({
                            text: text.substring(0, 500),
                            selector_matched: sel,
                            role: el.getAttribute('role') || null,
                            visible: rect.width > 0 && rect.height > 0,
                        });
                    }
                } catch(e) {}
            }
            return results;
        }""", toast_selectors)

        return {
            "count": len(messages),
            "messages": messages,
        }
