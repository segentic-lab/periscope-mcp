import os
import time
from datetime import datetime
from playwright.async_api import Page
import config


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
    await locator.click(force=force)
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    return {"url": page.url, "title": await page.title()}


async def fill_field(page: Page, selector: str, value: str):
    """Fill a single form field."""
    locator = page.locator(selector).first
    await locator.wait_for(state="visible", timeout=10000)
    await locator.click()
    await locator.fill(value)


async def fill_form(page: Page, fields: list[dict], submit_selector: str = None) -> dict:
    """Fill form fields and optionally submit.

    Args:
        page: Playwright page
        fields: List of {"selector": str, "value": str}
        submit_selector: Optional CSS selector for submit button

    Returns dict with result info.
    """
    filled = []
    for f in fields:
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


async def get_elements(page: Page, selector: str, max_results: int = 50) -> list[dict]:
    """Get matching elements with their attributes."""
    elements = await page.evaluate("""(args) => {
        const [selector, maxResults] = args;
        const els = document.querySelectorAll(selector);
        const results = [];
        for (let i = 0; i < Math.min(els.length, maxResults); i++) {
            const el = els[i];
            const rect = el.getBoundingClientRect();
            results.push({
                tag: el.tagName.toLowerCase(),
                text: (el.textContent || '').trim().substring(0, 100),
                id: el.id || null,
                class: el.className || null,
                href: el.getAttribute('href') || null,
                value: el.value || null,
                type: el.getAttribute('type') || null,
                name: el.getAttribute('name') || null,
                visible: rect.width > 0 && rect.height > 0,
                enabled: !el.disabled,
                aria_label: el.getAttribute('aria-label') || null,
                role: el.getAttribute('role') || null,
                placeholder: el.getAttribute('placeholder') || null,
            });
        }
        return results;
    }""", [selector, max_results])
    return elements


async def take_screenshot(page: Page, project_name: str, label: str = "") -> str:
    """Take a screenshot and save it. Returns the file path."""
    project_dir = os.path.join(config.SCREENSHOT_DIR, project_name)
    os.makedirs(project_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    suffix = f"_{label}" if label else ""
    filename = f"interactive_{timestamp}{suffix}.png"
    filepath = os.path.join(project_dir, filename)
    await page.screenshot(path=filepath, full_page=True)
    return filepath


async def execute_steps(
    page: Page,
    steps: list[dict],
    project_name: str = "default",
    continue_on_error: bool = False
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
        drag: {action: "drag", selector: str, target: str} — drag element to target
        right_click: {action: "right_click", selector: str} — right-click / context menu
        wait_for_text: {action: "wait_for_text", text: str, selector?: str, timeout?: int} — wait for text to appear

    Returns dict with step results and screenshots.
    """
    results = []
    screenshots = []

    for i, step in enumerate(steps):
        action = step.get("action")
        step_result = {"step": i, "action": action, "success": True}

        try:
            if action == "click":
                force = step.get("force", False)
                locator = page.locator(step["selector"]).first
                if not force:
                    await locator.wait_for(state="visible", timeout=10000)
                await locator.click(force=force)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                step_result["url"] = page.url

            elif action == "force_click":
                locator = page.locator(step["selector"]).first
                await locator.click(force=True)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                step_result["url"] = page.url

            elif action == "fill":
                locator = page.locator(step["selector"]).first
                await locator.wait_for(state="visible", timeout=10000)
                await locator.click()
                await locator.fill(step["value"])

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
                path = await take_screenshot(page, project_name, label)
                screenshots.append(path)
                step_result["screenshot_path"] = path

            elif action == "navigate":
                await page.goto(step["url"], wait_until="networkidle")
                step_result["url"] = page.url

            elif action == "hover":
                locator = page.locator(step["selector"]).first
                await locator.wait_for(state="visible", timeout=10000)
                await locator.hover()

            elif action == "press_key":
                await page.keyboard.press(step["key"])

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
                    if (el) el.scrollBy(dx, dy);
                }""", [step["selector"], dx, dy])

            elif action == "evaluate_js":
                result = await page.evaluate(step["script"])
                step_result["result"] = result

            elif action == "drag":
                source = page.locator(step["selector"]).first
                target = page.locator(step["target"]).first
                await source.drag_to(target)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass

            elif action == "right_click":
                locator = page.locator(step["selector"]).first
                force = step.get("force", False)
                if not force:
                    await locator.wait_for(state="visible", timeout=10000)
                await locator.click(button="right", force=force)

            elif action == "wait_for_text":
                text = step["text"]
                container = step.get("selector", "body")
                timeout = step.get("timeout", 30000)
                locator = page.locator(container).locator(f"text={text}").first
                await locator.wait_for(state="visible", timeout=timeout)

            else:
                step_result["success"] = False
                step_result["error"] = f"Unknown action: {action}"

        except Exception as e:
            step_result["success"] = False
            step_result["error"] = str(e)
            results.append(step_result)
            if not continue_on_error:
                return {
                    "completed": i + 1,
                    "total_steps": len(steps),
                    "success": False,
                    "error": f"Step {i} ({action}) failed: {e}",
                    "steps": results,
                    "screenshots": screenshots,
                }

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
        validation = await page.evaluate("""(formIndex) => {
            const form = document.querySelectorAll('form')[formIndex];
            if (!form) return [];
            const invalids = form.querySelectorAll(':invalid');
            return Array.from(invalids).map(el => ({
                tag: el.tagName.toLowerCase(),
                name: el.name || el.id || null,
                type: el.type || null,
                validationMessage: el.validationMessage || '',
                required: el.required,
            }));
        }""", form_info["index"])

        # Look for custom error elements near the form
        custom_errors = await page.evaluate("""(formIndex) => {
            const form = document.querySelectorAll('form')[formIndex];
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
        }""", form_info["index"])

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
    page: Page, selector: str, wait_for: str = None
) -> dict:
    """Click an element and measure time until condition is met.

    Args:
        page: Playwright page
        selector: Element to click
        wait_for: Optional selector to wait for appearing, or None for networkidle

    Returns timing info in ms.
    """
    locator = page.locator(selector).first
    await locator.wait_for(state="visible", timeout=10000)

    start = time.time()
    await locator.click()

    if wait_for:
        target = page.locator(wait_for).first
        await target.wait_for(state="visible", timeout=30000)
    else:
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass

    elapsed_ms = round((time.time() - start) * 1000)

    return {
        "clicked": selector,
        "waited_for": wait_for or "networkidle",
        "elapsed_ms": elapsed_ms,
        "url": page.url,
        "title": await page.title(),
    }
