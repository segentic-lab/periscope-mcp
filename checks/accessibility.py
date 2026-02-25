from playwright.async_api import Page


async def check_accessibility(page: Page) -> list[dict]:
    """
    Run accessibility checks on a page.
    Returns list of issues found.
    """
    issues = []

    # Check for images missing alt text
    images_no_alt = await page.evaluate("""() => {
        const imgs = document.querySelectorAll('img');
        const missing = [];
        imgs.forEach(img => {
            if (!img.hasAttribute('alt') || img.alt.trim() === '') {
                missing.push(img.src || 'inline image');
            }
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

    # Check for empty links
    empty_links = await page.evaluate("""() => {
        const links = document.querySelectorAll('a');
        let count = 0;
        links.forEach(a => {
            const text = a.textContent.trim();
            const hasImg = a.querySelector('img[alt]');
            const ariaLabel = a.getAttribute('aria-label');
            if (!text && !hasImg && !ariaLabel) {
                count++;
            }
        });
        return count;
    }""")
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
            const hasAriaLabel = input.getAttribute('aria-label');
            const hasAriaLabelledBy = input.getAttribute('aria-labelledby');
            const hasPlaceholder = input.placeholder;
            const wrappedInLabel = input.closest('label');

            if (!hasLabel && !hasAriaLabel && !hasAriaLabelledBy && !wrappedInLabel) {
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
        const buttons = document.querySelectorAll('button, [role="button"]');
        let count = 0;
        buttons.forEach(btn => {
            const text = btn.textContent.trim();
            const ariaLabel = btn.getAttribute('aria-label');
            const hasImg = btn.querySelector('img[alt]');
            if (!text && !ariaLabel && !hasImg) {
                count++;
            }
        });
        return count;
    }""")
    if buttons_no_name > 0:
        issues.append({
            "type": "accessibility",
            "severity": "error",
            "message": f"{buttons_no_name} buttons without accessible names"
        })

    # Check for missing skip link
    has_skip_link = await page.evaluate("""() => {
        const firstLink = document.querySelector('a');
        if (!firstLink) return true;  // No links at all
        const href = firstLink.getAttribute('href') || '';
        const text = firstLink.textContent.toLowerCase();
        return href.startsWith('#') && (
            text.includes('skip') ||
            text.includes('main') ||
            text.includes('content')
        );
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
