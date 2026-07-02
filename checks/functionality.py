from playwright.async_api import Page
from urllib.parse import urljoin, urlparse

from checks.geo import SEARCH_CRAWLERS, fetch_origin_file, is_blocked, parse_robots


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
            status = response.status
            if status in (405, 501):  # server rejects HEAD, retry with GET
                response = await page.context.request.get(link, timeout=5000)
                status = response.status
            if status >= 400:
                broken.append(f"{link} ({status})")
        except Exception:
            broken.append(f"{link} (unreachable)")

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
            text: (a.textContent || '').trim().substring(0, 40),
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
            if status in (405, 501):  # server rejects HEAD, retry with GET
                response = await page.context.request.get(href, timeout=10000)
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


async def check_seo(page: Page, response=None) -> list[dict]:
    """
    Run SEO checks on a page.

    Args:
        page: Playwright Page (or Frame for iframe sessions)
        response: Optional navigation Response — enables the X-Robots-Tag
                  header check without re-requesting the page.

    Returns list of issues found.
    """
    issues = []

    # Title: presence + length band (recommended ~30-60 chars)
    title = (await page.title() or "").strip()
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
    elif len(title) < 15:
        issues.append({
            "type": "seo",
            "severity": "info",
            "message": f"Page title is very short ({len(title)} chars, recommended 30-60)"
        })

    # Meta description: presence + length band (recommended ~50-160 chars)
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
    elif len(meta_desc) < 50:
        issues.append({
            "type": "seo",
            "severity": "info",
            "message": f"Meta description is very short ({len(meta_desc)} chars, recommended 50-160)"
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

    # H1: exactly one per page is the SEO convention
    h1_count = await page.evaluate("() => document.querySelectorAll('h1').length")
    if h1_count == 0:
        issues.append({
            "type": "seo",
            "severity": "warning",
            "message": "Missing H1 heading"
        })
    elif h1_count > 1:
        issues.append({
            "type": "seo",
            "severity": "info",
            "message": f"{h1_count} H1 headings (recommended: one per page)"
        })

    # Open Graph: presence, completeness of the core tags, absolute og:image
    og = await page.evaluate("""() => {
        const tags = {};
        document.querySelectorAll('meta[property^="og:"]').forEach(m => {
            tags[m.getAttribute('property')] = m.getAttribute('content') || '';
        });
        const tw = document.querySelector('meta[name="twitter:card"]');
        return { tags, twitterCard: tw ? tw.content : null };
    }""")
    og_tags = og["tags"]
    if not og_tags:
        issues.append({
            "type": "seo",
            "severity": "info",
            "message": "Missing Open Graph meta tags"
        })
    else:
        core = ["og:title", "og:description", "og:image", "og:url"]
        missing = [t for t in core if not og_tags.get(t)]
        if missing:
            issues.append({
                "type": "seo",
                "severity": "info",
                "message": f"Incomplete Open Graph tags (missing: {', '.join(missing)})"
            })
        og_image = og_tags.get("og:image", "")
        if og_image and not og_image.startswith(("http://", "https://")):
            issues.append({
                "type": "seo",
                "severity": "info",
                "message": "og:image is not an absolute URL (social platforms require one)"
            })
        if not og["twitterCard"]:
            issues.append({
                "type": "seo",
                "severity": "info",
                "message": "Missing twitter:card meta tag (use 'summary_large_image' for rich previews)"
            })

    # JSON-LD structured data: presence + parseability
    jsonld = await page.evaluate("""() => {
        const scripts = document.querySelectorAll('script[type="application/ld+json"]');
        let invalid = 0;
        const types = [];
        scripts.forEach(s => {
            try {
                const data = JSON.parse(s.textContent);
                const collect = (d) => {
                    if (Array.isArray(d)) d.forEach(collect);
                    else if (d && d['@type']) types.push(String(d['@type']));
                };
                collect(data && data['@graph'] ? data['@graph'] : data);
            } catch { invalid++; }
        });
        return { count: scripts.length, invalid, types: types.slice(0, 10) };
    }""")
    if jsonld["count"] == 0:
        issues.append({
            "type": "seo",
            "severity": "info",
            "message": "No JSON-LD structured data found"
        })
    elif jsonld["invalid"]:
        issues.append({
            "type": "seo",
            "severity": "warning",
            "message": f"{jsonld['invalid']} JSON-LD block(s) contain invalid JSON",
            "details": [f"valid types found: {jsonld['types']}"] if jsonld["types"] else []
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

    # X-Robots-Tag header — the other way pages get de-indexed, invisible in
    # the DOM. Use the navigation response when available; otherwise probe
    # with a cheap HEAD request in the same context.
    robots_header = None
    try:
        if response is not None:
            robots_header = (response.headers or {}).get("x-robots-tag")
        else:
            ctx = getattr(page, "context", None)
            if ctx is not None and page.url.startswith(("http://", "https://")):
                head = await ctx.request.head(page.url, timeout=5000)
                robots_header = head.headers.get("x-robots-tag")
    except Exception:
        pass
    if robots_header and "noindex" in robots_header.lower():
        issues.append({
            "type": "seo",
            "severity": "warning",
            "message": f"X-Robots-Tag header sets noindex (won't appear in search results): '{robots_header}'"
        })

    # robots.txt: search engine crawlers must be allowed to crawl the site
    robots_txt, origin = await fetch_origin_file(page, "/robots.txt")
    if origin is not None:
        if robots_txt is None:
            issues.append({
                "type": "seo",
                "severity": "info",
                "message": "No robots.txt found"
            })
        else:
            groups = parse_robots(robots_txt)
            blocked = [ua for ua in SEARCH_CRAWLERS if is_blocked(groups, ua)]
            if blocked:
                issues.append({
                    "type": "seo",
                    "severity": "error" if len(blocked) == len(SEARCH_CRAWLERS) else "warning",
                    "message": f"robots.txt blocks {len(blocked)} search engine crawlers"
                               f"{' — site is invisible to search engines' if len(blocked) == len(SEARCH_CRAWLERS) else ''}",
                    "details": blocked,
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
