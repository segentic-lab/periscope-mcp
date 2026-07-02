"""AI-agent speed tools (assertions, smart find, auto-fill, snapshots, network log)."""
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


@tool("assert_condition")
async def handle_assert_condition(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        assertion = args["assertion"]
        selector = args.get("selector", "body")
        expected = args.get("expected", "")
        attribute = args.get("attribute", "")
        page = session.page

        passed = False
        actual = None

        if assertion == "text_contains":
            actual = await page.locator(selector).first.text_content() or ""
            passed = expected in actual

        elif assertion == "text_equals":
            actual = (await page.locator(selector).first.text_content() or "").strip()
            passed = actual == expected

        elif assertion == "element_exists":
            count = await page.locator(selector).count()
            actual = count
            passed = count > 0

        elif assertion == "element_visible":
            try:
                visible = await page.locator(selector).first.is_visible()
                actual = visible
                passed = visible
            except Exception:
                actual = False
                passed = False

        elif assertion == "element_count":
            try:
                expected_count = int(expected)
            except (TypeError, ValueError):
                return {
                    "success": False,
                    "error": f"element_count needs an integer 'expected', got {expected!r}",
                    "assertion": assertion,
                }
            count = await page.locator(selector).count()
            actual = count
            passed = count == expected_count

        elif assertion == "url_contains":
            actual = page.url
            passed = expected in actual

        elif assertion == "title_contains":
            actual = await page.title()
            passed = expected in actual

        elif assertion == "attribute_equals":
            if not attribute:
                return {
                    "success": False,
                    "error": "attribute_equals requires the 'attribute' argument",
                    "assertion": assertion,
                }
            actual = await page.locator(selector).first.get_attribute(attribute)
            passed = actual == expected

        else:
            # Unknown assertion must not read as a failed-but-valid assertion
            return {
                "success": False,
                "error": f"Unknown assertion '{assertion}'. Valid: text_contains, text_equals, "
                         f"element_exists, element_visible, element_count, url_contains, "
                         f"title_contains, attribute_equals",
            }

        return {
            "assertion": assertion,
            "selector": selector,
            "expected": expected,
            "actual": actual if not isinstance(actual, str) or len(str(actual)) < 200 else str(actual)[:200] + "...",
            "passed": passed,
        }


@tool("find_element")
async def handle_find_element(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        text = args.get("text", "")
        tag = args.get("tag", "")
        role = args.get("role", "")
        near = args.get("near", "")
        max_results = args.get("max_results", 5)

        results = await session.page.evaluate("""(args) => {
            const [text, tag, role, near, maxResults] = args;
            let candidates = [];

            // Start with all elements or filtered by tag
            const selector = tag || '*';
            const allEls = document.querySelectorAll(selector);

            // If near is specified, get nearby element's bounding box
            let nearRect = null;
            if (near) {
                const nearEl = document.querySelector(near);
                if (nearEl) nearRect = nearEl.getBoundingClientRect();
            }

            let matched = [];
            for (const el of allEls) {
                // Filter by role
                if (role && el.getAttribute('role') !== role) continue;

                // Filter by text
                const elText = (el.textContent || '').trim();
                if (text && !elText.toLowerCase().includes(text.toLowerCase())) continue;

                // Skip invisible
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) continue;

                matched.push(el);
            }

            // Text matches every ancestor of the target (html, body, wrappers all
            // contain the text) — keep only innermost matches so the returned
            // selector points at the actual element, not a container.
            if (text) {
                matched = matched.filter(el => !matched.some(other => other !== el && el.contains(other)));
            }

            for (const el of matched) {
                const elText = (el.textContent || '').trim();
                const rect = el.getBoundingClientRect();

                // Build best selector
                let bestSelector = el.tagName.toLowerCase();
                if (el.id) {
                    bestSelector = '#' + el.id;
                } else if (el.getAttribute('data-testid')) {
                    bestSelector = `[data-testid="${el.getAttribute('data-testid')}"]`;
                } else if (el.name) {
                    bestSelector = `${el.tagName.toLowerCase()}[name="${el.name}"]`;
                } else if (el.className && typeof el.className === 'string' && el.className.trim()) {
                    bestSelector = el.tagName.toLowerCase() + '.' + el.className.trim().split(/\\s+/).join('.');
                }

                let distance = 0;
                if (nearRect) {
                    const cx = rect.x + rect.width / 2;
                    const cy = rect.y + rect.height / 2;
                    const nx = nearRect.x + nearRect.width / 2;
                    const ny = nearRect.y + nearRect.height / 2;
                    distance = Math.sqrt((cx - nx) ** 2 + (cy - ny) ** 2);
                }

                candidates.push({
                    selector: bestSelector,
                    text: elText.substring(0, 60),
                    role: el.getAttribute('role') || null,
                    aria_label: el.getAttribute('aria-label') || null,
                    distance: nearRect ? Math.round(distance) : null,
                });
            }

            // Sort: nearest first if near is specified, otherwise by DOM order
            if (nearRect) {
                candidates.sort((a, b) => a.distance - b.distance);
            }

            return candidates.slice(0, maxResults);
        }""", [text, tag, role, near, max_results])

        return {
            "found": len(results),
            "elements": results,
        }


@tool("auto_fill_form")
async def handle_auto_fill_form(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        form_selector = args.get("form_selector", "form")
        overrides = args.get("overrides", {})
        submit = args.get("submit", False)

        # Detect fields and infer types
        fields = await session.page.evaluate("""(formSelector) => {
            const form = document.querySelector(formSelector);
            if (!form) return [];
            const inputs = form.querySelectorAll('input, select, textarea');
            return Array.from(inputs).map(el => {
                const name = (el.name || el.id || '').toLowerCase();
                const type = el.type || el.tagName.toLowerCase();
                const placeholder = (el.placeholder || '').toLowerCase();
                const label_el = el.id ? document.querySelector(`label[for="${el.id}"]`) : el.closest('label');
                const label = label_el ? label_el.textContent.trim().toLowerCase() : '';
                const all_hints = name + ' ' + placeholder + ' ' + label;

                // Build best selector
                let selector = el.tagName.toLowerCase();
                if (el.id) selector = '#' + el.id;
                else if (el.name) selector = `${el.tagName.toLowerCase()}[name="${el.name}"]`;

                return {
                    selector: selector,
                    type: type,
                    name: el.name || null,
                    id: el.id || null,
                    required: el.required,
                    hints: all_hints,
                    tag: el.tagName.toLowerCase(),
                    options: el.tagName === 'SELECT' ? Array.from(el.options).map(o => o.value).filter(v => v) : null,
                };
            }).filter(f => f.type !== 'hidden' && f.type !== 'submit' && f.type !== 'button');
        }""", form_selector)

        if not fields:
            return {"success": False, "error": f"No form fields found in '{form_selector}'"}

        # Infer values based on field type and hints
        test_data = {
            "email": "test@example.com",
            "password": "TestPassword123!",
            "tel": "+1234567890",
            "url": "https://example.com",
            "number": "42",
            "date": "2025-01-15",
            "time": "10:30",
            "datetime-local": "2025-01-15T10:30",
            "month": "2025-01",
            "week": "2025-W03",
            "color": "#3366cc",
            "range": "50",
            "search": "test search",
        }
        name_hints = {
            # semantic hints first — a type="text" field named "email"/"phone"
            # must still get plausible data, not "Test input"
            "email": "test@example.com", "e-mail": "test@example.com",
            "phone": "+1234567890", "mobile": "+1234567890", "tel": "+1234567890",
            "website": "https://example.com", "url": "https://example.com",
            "username": "testuser",  # before "name" — 'username' contains 'name'
            "first": "John", "last": "Doe", "name": "John Doe",
            "company": "Test Corp", "organization": "Test Corp", "org": "Test Corp",
            "address": "123 Test Street", "street": "123 Test Street",
            "city": "San Francisco", "state": "CA", "zip": "94105", "postal": "94105",
            "country": "US", "user": "testuser",
            "comment": "This is a test comment.", "message": "This is a test message.",
            "description": "Test description for automated testing.",
            "title": "Test Title", "subject": "Test Subject",
            "age": "30", "quantity": "1", "amount": "100",
        }

        filled = []
        handled_radio_groups = set()
        for f in fields:
            selector = f["selector"]

            # Check for override
            if selector in overrides:
                value = overrides[selector]
            elif f["type"] in test_data:
                value = test_data[f["type"]]
            else:
                # Infer from name/placeholder/label hints
                value = "Test input"
                for hint_key, hint_value in name_hints.items():
                    if hint_key in f["hints"]:
                        value = hint_value
                        break

            try:
                if f["tag"] == "select" and f["options"]:
                    # Pick first non-empty option
                    await session.page.locator(selector).first.select_option(f["options"][0])
                    filled.append({"selector": selector, "value": f["options"][0]})
                elif f["type"] == "checkbox":
                    await session.page.locator(selector).first.check()
                    filled.append({"selector": selector, "value": "checked"})
                elif f["type"] == "radio":
                    # Check one radio per group, not every radio (later checks would undo earlier ones)
                    group = f.get("name") or selector
                    if group in handled_radio_groups:
                        filled.append({"selector": selector, "value": "skipped (group already selected)"})
                    else:
                        await session.page.locator(selector).first.check()
                        handled_radio_groups.add(group)
                        filled.append({"selector": selector, "value": "checked"})
                elif f["type"] == "file":
                    filled.append({"selector": selector, "value": "skipped"})
                elif f["type"] in interactions._DATE_TYPES:
                    await interactions._fill_date_input(session.page, selector, str(value))
                    filled.append({"selector": selector, "value": str(value)})
                else:
                    locator = session.page.locator(selector).first
                    await locator.click()
                    await locator.fill(str(value))
                    filled.append({"selector": selector, "value": str(value)})
            except Exception as e:
                filled.append({"selector": selector, "error": str(e)[:100]})

        result = {"success": True, "fields_filled": filled, "submitted": False}

        if submit:
            try:
                submit_btn = session.page.locator(f"{form_selector} [type='submit'], {form_selector} button:not([type='button'])").first
                await submit_btn.click()
                try:
                    await session.page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                result["submitted"] = True
                result["url"] = session.page.url
                result["title"] = await session.page.title()
            except Exception as e:
                result["submit_error"] = str(e)

        return result


@tool("get_network_log")
async def handle_get_network_log(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        url_filter = args.get("url_filter", "")
        clear = args.get("clear", False)

        log = session.network_log
        if url_filter:
            log = [entry for entry in log if url_filter in entry["url"]]

        # Return everything that matched — the buffer itself is already capped
        # at MAX_NETWORK_LOG, and the schema promises "all requests".
        result = {
            "total_requests": len(session.network_log),
            "filtered_count": len(log),
            "requests": [
                {
                    "url": e["url"] if len(e["url"]) <= 120 else "..." + e["url"][-117:],
                    "status": e["status"],
                    "method": e["method"],
                    "resource_type": e["resource_type"],
                }
                for e in log
            ],
        }

        if clear:
            session.network_log.clear()
            result["cleared"] = True

        return result


@tool("snapshot_page_state")
async def handle_snapshot_page_state(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        snap_name = args["name"]

        state = await session.page.evaluate("""() => {
            const ls = {};
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                ls[key] = localStorage.getItem(key);
            }
            const ss = {};
            for (let i = 0; i < sessionStorage.length; i++) {
                const key = sessionStorage.key(i);
                ss[key] = sessionStorage.getItem(key);
            }
            // Capture a DOM signature for diff (all elements, up to 1000)
            const elements = document.querySelectorAll('*');
            const domSig = [];
            for (let i = 0; i < Math.min(elements.length, 1000); i++) {
                const el = elements[i];
                const cls = el.className && typeof el.className === 'string'
                    ? el.className.trim().split(/\\s+/).slice(0, 2).join(' ') : null;
                domSig.push({
                    tag: el.tagName.toLowerCase(),
                    id: el.id || el.getAttribute('data-testid') || null,
                    cls: cls || null,
                    text: el.children.length === 0 ? (el.textContent || '').trim().substring(0, 40) : null,
                });
            }
            return { localStorage: ls, sessionStorage: ss, domSignature: domSig };
        }""")

        cookies = await real_page(session.page).context.cookies()

        session.snapshots[snap_name] = {
            "url": session.page.url,
            "title": await session.page.title(),
            "cookies": cookies,
            "localStorage": state["localStorage"],
            "sessionStorage": state["sessionStorage"],
            "domSignature": state["domSignature"],
            "timestamp": time.time(),
        }

        return {
            "success": True,
            "name": snap_name,
            "url": session.page.url,
            "snapshot_count": len(session.snapshots),
        }


@tool("restore_page_state")
async def handle_restore_page_state(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        snap_name = args["name"]

        if snap_name not in session.snapshots:
            return {"success": False, "error": f"Snapshot '{snap_name}' not found. Available: {list(session.snapshots.keys())}"}

        snap = session.snapshots[snap_name]
        # Operate on the session's own scope: for iframe sessions the snapshot
        # was taken from the frame, so navigation/storage must target the frame
        # too — using the parent Page would navigate the top-level page to the
        # iframe URL and write storage into the wrong origin.
        page = session.page
        context = real_page(session.page).context

        # Restore cookies
        await context.clear_cookies()
        if snap["cookies"]:
            await context.add_cookies(snap["cookies"])

        # Navigate to saved URL
        await page.goto(snap["url"], wait_until=config.WAIT_UNTIL)

        # Restore storage
        await page.evaluate("""(state) => {
            localStorage.clear();
            for (const [k, v] of Object.entries(state.localStorage || {})) {
                localStorage.setItem(k, v);
            }
            sessionStorage.clear();
            for (const [k, v] of Object.entries(state.sessionStorage || {})) {
                sessionStorage.setItem(k, v);
            }
        }""", snap)

        # Reload so the app actually boots with the restored cookies + storage —
        # without this, an SPA that read storage on startup keeps its old state.
        # Frames have no reload(); a repeat goto serves the same purpose there.
        if hasattr(page, "reload"):
            await page.reload(wait_until=config.WAIT_UNTIL)
        else:
            await page.goto(snap["url"], wait_until=config.WAIT_UNTIL)

        session.url = page.url
        return {
            "success": True,
            "name": snap_name,
            "restored_url": page.url,
            "title": await page.title(),
        }


@tool("diff_page_state")
async def handle_diff_page_state(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        snap_name = args["name"]

        if snap_name not in session.snapshots:
            return {"success": False, "error": f"Snapshot '{snap_name}' not found. Available: {list(session.snapshots.keys())}"}

        snap = session.snapshots[snap_name]
        old_dom = snap["domSignature"]

        # Get current DOM signature
        current_dom = await session.page.evaluate("""() => {
            const elements = document.querySelectorAll('*');
            const domSig = [];
            for (let i = 0; i < Math.min(elements.length, 1000); i++) {
                const el = elements[i];
                const cls = el.className && typeof el.className === 'string'
                    ? el.className.trim().split(/\\s+/).slice(0, 2).join(' ') : null;
                domSig.push({
                    tag: el.tagName.toLowerCase(),
                    id: el.id || el.getAttribute('data-testid') || null,
                    cls: cls || null,
                    text: el.children.length === 0 ? (el.textContent || '').trim().substring(0, 40) : null,
                });
            }
            return domSig;
        }""")

        # Build index by id for comparison
        old_by_id = {e["id"]: e for e in old_dom if e.get("id")}
        new_by_id = {e["id"]: e for e in current_dom if e.get("id")}

        added_ids = set(new_by_id.keys()) - set(old_by_id.keys())
        removed_ids = set(old_by_id.keys()) - set(new_by_id.keys())
        common_ids = set(old_by_id.keys()) & set(new_by_id.keys())

        changed = []
        for eid in common_ids:
            old_e = old_by_id[eid]
            new_e = new_by_id[eid]
            diffs = {}
            for key in ["tag", "cls", "text"]:
                if old_e.get(key) != new_e.get(key):
                    diffs[key] = {"old": old_e.get(key), "new": new_e.get(key)}
            if diffs:
                changed.append({"id": eid, "changes": diffs})

        # Also compare counts by tag
        from collections import Counter
        old_tags = Counter(e["tag"] for e in old_dom)
        new_tags = Counter(e["tag"] for e in current_dom)
        tag_diffs = {}
        for tag in set(list(old_tags.keys()) + list(new_tags.keys())):
            if old_tags.get(tag, 0) != new_tags.get(tag, 0):
                tag_diffs[tag] = {"old": old_tags.get(tag, 0), "new": new_tags.get(tag, 0)}

        return {
            "success": True,
            "snapshot_name": snap_name,
            "url_changed": snap["url"] != session.page.url,
            "old_url": snap["url"],
            "current_url": session.page.url,
            "elements_added_ids": list(added_ids)[:20],
            "elements_removed_ids": list(removed_ids)[:20],
            "elements_changed": changed[:20],
            "tag_count_changes": tag_diffs,
            "old_element_count": len(old_dom),
            "new_element_count": len(current_dom),
        }


@tool("get_cookies")
async def handle_get_cookies(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        domain_filter = args.get("domain_filter", "")

        cookies = await real_page(session.page).context.cookies()

        if domain_filter:
            cookies = [c for c in cookies if domain_filter in c.get("domain", "")]

        return {
            "total": len(cookies),
            "cookies": cookies,
        }


@tool("get_response_body")
async def handle_get_response_body(args: dict) -> dict:
        session = session_manager.get_session(args["session_id"])
        url_pattern = args["url_pattern"]
        method_filter = args.get("method")

        matching = [
            entry for entry in session.response_bodies
            if url_pattern in entry["url"]
            and (not method_filter or entry["method"].upper() == method_filter.upper())
        ]

        if not matching:
            return {
                "success": False,
                "error": f"No response bodies found matching '{url_pattern}'",
                "url_pattern": url_pattern,
                "total_captured": len(session.response_bodies),
            }

        # Return the last matching entry
        last = matching[-1]
        url = last["url"]
        return {
            "success": True,
            "url": url if len(url) <= 120 else "..." + url[-117:],
            "status": last["status"],
            "method": last["method"],
            "content_type": last["content_type"],
            "body_text": last["body_text"],
        }
