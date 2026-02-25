from playwright.async_api import Page
from urllib.parse import urljoin, urlparse


async def check_functionality(page: Page) -> list[dict]:
    """
    Run functionality checks on a page.
    Returns list of issues found.
    """
    issues = []

    # Check for broken internal links
    base_url = page.url
    broken_links = await _check_links(page, base_url)
    if broken_links:
        issues.append({
            "type": "functionality",
            "severity": "error",
            "message": f"{len(broken_links)} broken links found",
            "details": broken_links[:5]
        })

    # Check for forms without action
    forms_no_action = await page.evaluate("""() => {
        const forms = document.querySelectorAll('form');
        let count = 0;
        forms.forEach(form => {
            const action = form.getAttribute('action');
            if (!action || action === '' || action === '#') {
                // Check if it has a submit handler
                const hasSubmitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
                if (!hasSubmitBtn) {
                    count++;
                }
            }
        });
        return count;
    }""")
    if forms_no_action > 0:
        issues.append({
            "type": "functionality",
            "severity": "warning",
            "message": f"{forms_no_action} forms without action or submit button"
        })

    # Check for buttons outside forms without onclick
    orphan_buttons = await page.evaluate("""() => {
        const buttons = document.querySelectorAll('button:not([type="submit"]):not([type="reset"])');
        let count = 0;
        buttons.forEach(btn => {
            const inForm = btn.closest('form');
            const hasOnclick = btn.hasAttribute('onclick') || btn.hasAttribute('data-action');
            const hasAriaExpanded = btn.hasAttribute('aria-expanded');
            const hasType = btn.getAttribute('type');
            if (!inForm && !hasOnclick && !hasAriaExpanded && hasType !== 'button') {
                count++;
            }
        });
        return count;
    }""")
    if orphan_buttons > 0:
        issues.append({
            "type": "functionality",
            "severity": "info",
            "message": f"{orphan_buttons} buttons outside forms (may be handled by JS)"
        })

    # Check for external links without target="_blank"
    external_no_blank = await page.evaluate("""(baseHost) => {
        const links = document.querySelectorAll('a[href]');
        let count = 0;
        links.forEach(a => {
            const href = a.getAttribute('href');
            if (href && href.startsWith('http')) {
                try {
                    const url = new URL(href);
                    if (url.host !== baseHost && a.target !== '_blank') {
                        count++;
                    }
                } catch {}
            }
        });
        return count;
    }""", urlparse(base_url).netloc)
    if external_no_blank > 0:
        issues.append({
            "type": "functionality",
            "severity": "info",
            "message": f"{external_no_blank} external links without target='_blank'"
        })

    # Check for required inputs without validation messages
    required_no_msg = await page.evaluate("""() => {
        const required = document.querySelectorAll('input[required], select[required], textarea[required]');
        let count = 0;
        required.forEach(input => {
            const form = input.closest('form');
            if (form) {
                const name = input.name || input.id;
                const hasErrorSpan = form.querySelector(`[data-error="${name}"], .${name}-error, #${name}-error`);
                // Just count required fields, harder to check for validation messages
            }
        });
        return required.length;
    }""")
    if required_no_msg > 0:
        issues.append({
            "type": "functionality",
            "severity": "info",
            "message": f"Page has {required_no_msg} required form fields"
        })

    # Check for inputs with autocomplete off (can be intentional)
    autocomplete_off = await page.evaluate("""() => {
        const inputs = document.querySelectorAll('input[autocomplete="off"]');
        return inputs.length;
    }""")
    if autocomplete_off > 3:  # Only flag if many
        issues.append({
            "type": "functionality",
            "severity": "info",
            "message": f"{autocomplete_off} inputs have autocomplete disabled"
        })

    return issues


async def _check_links(page: Page, base_url: str) -> list[str]:
    """Check for broken links on the page."""
    links = await page.evaluate("""() => {
        const anchors = document.querySelectorAll('a[href]');
        return Array.from(anchors)
            .map(a => a.href)
            .filter(href => href && !href.startsWith('javascript:') && !href.startsWith('mailto:') && !href.startsWith('tel:'));
    }""")

    broken = []
    checked = set()

    # Only check internal links and limit to first 20
    for link in links[:20]:
        if link in checked:
            continue
        checked.add(link)

        # Only check same-domain links
        if urlparse(link).netloc != urlparse(base_url).netloc:
            continue

        try:
            response = await page.context.request.head(link, timeout=5000)
            if response.status >= 400:
                broken.append(f"{link} ({response.status})")
        except Exception:
            # Timeout or error, might be broken
            pass

    return broken


async def check_all_links(
    page: Page,
    base_url: str,
    check_external: bool = False,
    max_links: int = 100,
) -> dict:
    """Comprehensive link checker.

    Args:
        page: Playwright page
        base_url: Base URL for determining internal vs external
        check_external: Also check external links
        max_links: Maximum links to check

    Returns dict with link status results.
    """
    links = await page.evaluate("""() => {
        const anchors = document.querySelectorAll('a[href]');
        return Array.from(anchors).map(a => ({
            href: a.href,
            text: (a.textContent || '').trim().substring(0, 100),
        })).filter(l => l.href && !l.href.startsWith('javascript:') && !l.href.startsWith('mailto:') && !l.href.startsWith('tel:'));
    }""")

    base_netloc = urlparse(base_url).netloc
    checked = set()
    internal_results = []
    external_results = []

    for link_info in links:
        href = link_info["href"]
        if href in checked or len(checked) >= max_links:
            continue
        checked.add(href)

        is_internal = urlparse(href).netloc == base_netloc

        if not is_internal and not check_external:
            continue

        try:
            response = await page.context.request.head(href, timeout=10000)
            status = response.status
        except Exception as e:
            status = f"error: {str(e)[:60]}"

        entry = {
            "url": href,
            "text": link_info["text"],
            "status": status,
            "ok": isinstance(status, int) and status < 400,
        }

        if is_internal:
            internal_results.append(entry)
        else:
            external_results.append(entry)

    broken_internal = [r for r in internal_results if not r["ok"]]
    broken_external = [r for r in external_results if not r["ok"]]

    return {
        "url": base_url,
        "total_links_found": len(links),
        "links_checked": len(checked),
        "internal": {
            "total": len(internal_results),
            "broken": len(broken_internal),
            "results": internal_results,
        },
        "external": {
            "total": len(external_results),
            "broken": len(broken_external),
            "results": external_results,
        },
        "broken_count": len(broken_internal) + len(broken_external),
    }


async def check_seo(page: Page) -> list[dict]:
    """
    Run SEO checks on a page.
    Returns list of issues found.
    """
    issues = []

    # Check for title
    title = await page.title()
    if not title:
        issues.append({
            "type": "seo",
            "severity": "error",
            "message": "Missing page title"
        })
    elif len(title) > 60:
        issues.append({
            "type": "seo",
            "severity": "warning",
            "message": f"Page title is too long ({len(title)} chars, recommended < 60)"
        })

    # Check for meta description
    meta_desc = await page.evaluate("""() => {
        const meta = document.querySelector('meta[name="description"]');
        return meta ? meta.content : null;
    }""")
    if not meta_desc:
        issues.append({
            "type": "seo",
            "severity": "warning",
            "message": "Missing meta description"
        })
    elif len(meta_desc) > 160:
        issues.append({
            "type": "seo",
            "severity": "info",
            "message": f"Meta description is long ({len(meta_desc)} chars, recommended < 160)"
        })

    # Check for viewport meta
    has_viewport = await page.evaluate("""() => {
        return !!document.querySelector('meta[name="viewport"]');
    }""")
    if not has_viewport:
        issues.append({
            "type": "seo",
            "severity": "warning",
            "message": "Missing viewport meta tag"
        })

    # Check for canonical URL
    has_canonical = await page.evaluate("""() => {
        return !!document.querySelector('link[rel="canonical"]');
    }""")
    if not has_canonical:
        issues.append({
            "type": "seo",
            "severity": "info",
            "message": "Missing canonical URL"
        })

    # Check for Open Graph tags
    has_og = await page.evaluate("""() => {
        return !!document.querySelector('meta[property^="og:"]');
    }""")
    if not has_og:
        issues.append({
            "type": "seo",
            "severity": "info",
            "message": "Missing Open Graph meta tags"
        })

    # Check for robots meta
    robots_noindex = await page.evaluate("""() => {
        const meta = document.querySelector('meta[name="robots"]');
        return meta && meta.content.includes('noindex');
    }""")
    if robots_noindex:
        issues.append({
            "type": "seo",
            "severity": "warning",
            "message": "Page is set to noindex (won't appear in search results)"
        })

    return issues


async def get_performance_metrics(page: Page) -> dict:
    """Get page performance metrics using Navigation Timing Level 2 API."""
    metrics = await page.evaluate("""() => {
        const [nav] = performance.getEntriesByType('navigation');
        const paint = performance.getEntriesByType('paint');
        const resources = performance.getEntriesByType('resource');

        // Calculate total page size
        let totalSize = 0;
        resources.forEach(r => {
            if (r.transferSize) totalSize += r.transferSize;
        });

        return {
            dom_content_loaded_ms: nav ? Math.round(nav.domContentLoadedEventEnd) : null,
            load_complete_ms: nav ? Math.round(nav.loadEventEnd) : null,
            first_paint_ms: paint.find(p => p.name === 'first-paint')?.startTime || null,
            first_contentful_paint_ms: paint.find(p => p.name === 'first-contentful-paint')?.startTime || null,
            resource_count: resources.length,
            total_size_bytes: totalSize,
            total_size_kb: Math.round(totalSize / 1024)
        };
    }""")
    return metrics
