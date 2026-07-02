import asyncio
from playwright.async_api import Page


async def check_keyboard_navigation(page: Page, max_tabs: int = 50) -> dict:
    """Tab through a page and track focus order.

    Args:
        page: Playwright page
        max_tabs: Maximum number of Tab presses

    Returns dict with focus order and issues found.
    """
    # Click body first to ensure we start from the top, and reset the
    # visited-set used for cycle detection (element identity, not selectors —
    # identically-styled elements must not terminate the audit early).
    await page.evaluate("document.body.focus(); window.__periscope_kbd_seen = new WeakSet();")

    focus_order = []
    issues = []

    for i in range(max_tabs):
        await page.keyboard.press("Tab")
        await asyncio.sleep(0.1)

        element_info = await page.evaluate("""() => {
            const el = document.activeElement;
            if (!el || el === document.body) return null;

            const seen = window.__periscope_kbd_seen;
            if (seen && seen.has(el)) return { cycled: true };
            if (seen) seen.add(el);

            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);

            // Check for visible focus indicator
            const outlineStyle = style.outline;
            const outlineWidth = parseFloat(style.outlineWidth);
            const boxShadow = style.boxShadow;
            const hasFocusIndicator = (
                (outlineWidth > 0 && style.outlineStyle !== 'none') ||
                (boxShadow && boxShadow !== 'none')
            );

            // Build a selector-like identifier
            let selector = el.tagName.toLowerCase();
            if (el.id) selector += '#' + el.id;
            else if (el.className && typeof el.className === 'string')
                selector += '.' + el.className.trim().split(/\\s+/).join('.');

            return {
                tag: el.tagName.toLowerCase(),
                text: (el.textContent || '').trim().substring(0, 80),
                id: el.id || null,
                role: el.getAttribute('role') || null,
                aria_label: el.getAttribute('aria-label') || null,
                href: el.getAttribute('href') || null,
                type: el.getAttribute('type') || null,
                tabindex: el.getAttribute('tabindex'),
                visible: rect.width > 0 && rect.height > 0,
                has_focus_indicator: hasFocusIndicator,
                selector: selector,
                position: {x: Math.round(rect.x), y: Math.round(rect.y)},
            };
        }""")

        if element_info is None:
            # Focus returned to body or beyond, we've cycled through
            break
        if element_info.get("cycled"):
            # Focus landed on an already-visited element — full cycle done
            break

        selector_key = element_info.get("selector", "")
        element_info["tab_index_position"] = i + 1
        focus_order.append(element_info)

        # Check for issues
        if not element_info.get("visible"):
            issues.append({
                "type": "accessibility",
                "severity": "warning",
                "message": f"Tab stop #{i+1} focuses a non-visible element: {selector_key}",
            })
        if not element_info.get("has_focus_indicator"):
            issues.append({
                "type": "accessibility",
                "severity": "warning",
                "message": f"Tab stop #{i+1} has no visible focus indicator: {selector_key}",
            })

    return {
        "focus_order": focus_order,
        "total_tab_stops": len(focus_order),
        "issues": issues,
        "issue_count": len(issues),
    }


async def check_accessibility(page: Page) -> list[dict]:
    """
    Run accessibility checks on a page.
    Returns list of issues found.
    """
    issues = []

    # Check for images missing alt text.
    # Decorative images are exempt: an explicit alt="" is the correct WCAG
    # technique, as are role="presentation"/"none" and aria-hidden.
    images_no_alt = await page.evaluate("""() => {
        const imgs = document.querySelectorAll('img');
        const missing = [];
        imgs.forEach(img => {
            if (img.hasAttribute('alt')) return;  // alt="" = intentionally decorative
            const role = img.getAttribute('role');
            if (role === 'presentation' || role === 'none') return;
            if (img.getAttribute('aria-hidden') === 'true' || img.closest('[aria-hidden="true"]')) return;
            if (img.getAttribute('aria-label') || img.getAttribute('aria-labelledby')) return;
            missing.push(img.src || 'inline image');
        });
        return missing;
    }""")
    if images_no_alt:
        issues.append({
            "type": "accessibility",
            "severity": "error",
            "message": f"{len(images_no_alt)} images missing alt text",
            "details": images_no_alt[:5]
        })

    # Accessible-name computation shared by the link and button checks:
    # text content, aria-label, resolvable aria-labelledby, title attribute,
    # non-decorative img alt, or an svg <title>.
    _HAS_NAME_JS = """
        const hasName = (el) => {
            if (el.textContent.trim()) return true;
            if ((el.getAttribute('aria-label') || '').trim()) return true;
            const lb = el.getAttribute('aria-labelledby');
            if (lb && lb.split(/\\s+/).some(id => {
                const ref = document.getElementById(id);
                return ref && ref.textContent.trim();
            })) return true;
            if ((el.getAttribute('title') || '').trim()) return true;
            if (el.querySelector('img[alt]') && el.querySelector('img[alt]').alt.trim()) return true;
            const svgTitle = el.querySelector('svg title');
            if (svgTitle && svgTitle.textContent.trim()) return true;
            return false;
        };
    """

    # Check for empty links (aria-hidden links are exempt — not exposed to AT)
    empty_links = await page.evaluate("""() => {
        %s
        const links = document.querySelectorAll('a');
        let count = 0;
        links.forEach(a => {
            if (a.getAttribute('aria-hidden') === 'true' || a.closest('[aria-hidden="true"]')) return;
            if (!hasName(a)) count++;
        });
        return count;
    }""" % _HAS_NAME_JS)
    if empty_links > 0:
        issues.append({
            "type": "accessibility",
            "severity": "error",
            "message": f"{empty_links} links without accessible text"
        })

    # Check for form inputs without labels
    inputs_no_labels = await page.evaluate("""() => {
        const inputs = document.querySelectorAll('input, select, textarea');
        let count = 0;
        inputs.forEach(input => {
            if (input.type === 'hidden' || input.type === 'submit' || input.type === 'button') {
                return;
            }
            const id = input.id;
            const hasLabel = id && document.querySelector(`label[for="${id}"]`);
            const hasAriaLabel = (input.getAttribute('aria-label') || '').trim();
            const hasAriaLabelledBy = input.getAttribute('aria-labelledby');
            const hasTitle = (input.getAttribute('title') || '').trim();
            const wrappedInLabel = input.closest('label');

            if (!hasLabel && !hasAriaLabel && !hasAriaLabelledBy && !hasTitle && !wrappedInLabel) {
                count++;
            }
        });
        return count;
    }""")
    if inputs_no_labels > 0:
        issues.append({
            "type": "accessibility",
            "severity": "error",
            "message": f"{inputs_no_labels} form inputs without labels"
        })

    # Check heading hierarchy
    heading_issues = await page.evaluate("""() => {
        const headings = document.querySelectorAll('h1, h2, h3, h4, h5, h6');
        const levels = Array.from(headings).map(h => parseInt(h.tagName[1]));
        const issues = [];

        // Check for missing H1
        const h1Count = levels.filter(l => l === 1).length;
        if (h1Count === 0) {
            issues.push('missing_h1');
        } else if (h1Count > 1) {
            issues.push('multiple_h1');
        }

        // Check for skipped levels
        for (let i = 1; i < levels.length; i++) {
            if (levels[i] > levels[i-1] + 1) {
                issues.push('skipped_level');
                break;
            }
        }

        return issues;
    }""")
    if 'missing_h1' in heading_issues:
        issues.append({
            "type": "accessibility",
            "severity": "warning",
            "message": "Missing H1 heading"
        })
    if 'multiple_h1' in heading_issues:
        issues.append({
            "type": "accessibility",
            "severity": "info",
            "message": "Multiple H1 headings (consider using only one)"
        })
    if 'skipped_level' in heading_issues:
        issues.append({
            "type": "accessibility",
            "severity": "warning",
            "message": "Heading levels are skipped (e.g., H1 to H3)"
        })

    # Check for missing lang attribute
    has_lang = await page.evaluate("""() => {
        return document.documentElement.hasAttribute('lang');
    }""")
    if not has_lang:
        issues.append({
            "type": "accessibility",
            "severity": "warning",
            "message": "Missing lang attribute on <html> element"
        })

    # Check for buttons without accessible names
    buttons_no_name = await page.evaluate("""() => {
        %s
        const buttons = document.querySelectorAll('button, [role="button"]');
        let count = 0;
        buttons.forEach(btn => {
            if (btn.getAttribute('aria-hidden') === 'true' || btn.closest('[aria-hidden="true"]')) return;
            if (!hasName(btn)) count++;
        });
        return count;
    }""" % _HAS_NAME_JS)
    if buttons_no_name > 0:
        issues.append({
            "type": "accessibility",
            "severity": "error",
            "message": f"{buttons_no_name} buttons without accessible names"
        })

    # Check for duplicate IDs — they silently break label[for] and aria-* refs
    duplicate_ids = await page.evaluate("""() => {
        const counts = {};
        document.querySelectorAll('[id]').forEach(el => {
            if (el.id) counts[el.id] = (counts[el.id] || 0) + 1;
        });
        return Object.entries(counts)
            .filter(([, c]) => c > 1)
            .map(([id, c]) => `#${id} (${c}x)`);
    }""")
    if duplicate_ids:
        issues.append({
            "type": "accessibility",
            "severity": "warning",
            "message": f"{len(duplicate_ids)} duplicate id values (breaks label/aria references)",
            "details": duplicate_ids[:5]
        })

    # Basic ARIA validity: unknown role values + aria-* references to missing ids
    aria_problems = await page.evaluate("""() => {
        const validRoles = new Set([
            'alert','alertdialog','application','article','banner','blockquote','button',
            'caption','cell','checkbox','code','columnheader','combobox','complementary',
            'contentinfo','definition','deletion','dialog','directory','document','emphasis',
            'feed','figure','form','generic','grid','gridcell','group','heading','img',
            'insertion','link','list','listbox','listitem','log','main','marquee','math',
            'menu','menubar','menuitem','menuitemcheckbox','menuitemradio','meter',
            'navigation','none','note','option','paragraph','presentation','progressbar',
            'radio','radiogroup','region','row','rowgroup','rowheader','scrollbar','search',
            'searchbox','separator','slider','spinbutton','status','strong','subscript',
            'superscript','switch','tab','table','tablist','tabpanel','term','textbox',
            'time','timer','toolbar','tooltip','tree','treegrid','treeitem'
        ]);
        const unknownRoles = [];
        document.querySelectorAll('[role]').forEach(el => {
            // role supports space-separated fallbacks; valid if any token is known
            const tokens = el.getAttribute('role').trim().toLowerCase().split(/\\s+/);
            if (tokens.length && !tokens.some(t => validRoles.has(t))) {
                unknownRoles.push(`<${el.tagName.toLowerCase()} role="${el.getAttribute('role')}">`);
            }
        });
        const refAttrs = ['aria-labelledby', 'aria-describedby', 'aria-controls', 'aria-owns', 'aria-activedescendant'];
        const brokenRefs = [];
        refAttrs.forEach(attr => {
            document.querySelectorAll('[' + attr + ']').forEach(el => {
                const missing = el.getAttribute(attr).split(/\\s+/)
                    .filter(id => id && !document.getElementById(id));
                if (missing.length) brokenRefs.push(`${attr} -> missing #${missing.join(', #')}`);
            });
        });
        return { unknownRoles, brokenRefs };
    }""")
    if aria_problems["unknownRoles"]:
        issues.append({
            "type": "accessibility",
            "severity": "warning",
            "message": f"{len(aria_problems['unknownRoles'])} elements with unknown ARIA role",
            "details": aria_problems["unknownRoles"][:5]
        })
    if aria_problems["brokenRefs"]:
        issues.append({
            "type": "accessibility",
            "severity": "warning",
            "message": f"{len(aria_problems['brokenRefs'])} ARIA references to non-existent ids",
            "details": aria_problems["brokenRefs"][:5]
        })

    # Check for missing skip link — scan the first few links, not just the
    # very first (cookie banners and logos commonly precede it)
    has_skip_link = await page.evaluate("""() => {
        const links = Array.from(document.querySelectorAll('a'));
        if (links.length === 0) return true;  // No links at all
        return links.slice(0, 5).some(a => {
            const href = a.getAttribute('href') || '';
            if (!href.startsWith('#')) return false;
            const text = (a.textContent + ' ' + (a.getAttribute('aria-label') || '') + ' ' + a.className).toLowerCase();
            return text.includes('skip') || text.includes('main') || text.includes('content');
        });
    }""")
    if not has_skip_link:
        issues.append({
            "type": "accessibility",
            "severity": "info",
            "message": "No skip navigation link found"
        })

    # Check for tabindex > 0
    bad_tabindex = await page.evaluate("""() => {
        const elements = document.querySelectorAll('[tabindex]');
        let count = 0;
        elements.forEach(el => {
            const tabindex = parseInt(el.getAttribute('tabindex'));
            if (tabindex > 0) count++;
        });
        return count;
    }""")
    if bad_tabindex > 0:
        issues.append({
            "type": "accessibility",
            "severity": "warning",
            "message": f"{bad_tabindex} elements with tabindex > 0 (disrupts natural tab order)"
        })

    return issues
