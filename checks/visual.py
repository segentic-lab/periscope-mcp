from playwright.async_api import Page


async def check_visual(page: Page) -> list[dict]:
    """
    Run visual checks on a page.
    Returns list of issues found.
    """
    issues = []

    # Check for broken images. Definitively broken = load finished with no
    # pixels (complete && naturalWidth === 0). Images that haven't STARTED
    # loading (!complete — typically loading="lazy" below the fold) are NOT
    # broken (issue #12); verify those over the network instead of flagging.
    img_status = await page.evaluate("""() => {
        const imgs = document.querySelectorAll('img');
        const failed = [], pending = [];
        imgs.forEach(img => {
            const src = img.currentSrc || img.src;
            if (!src) return;  // no source at all — nothing to load
            if (img.complete && img.naturalWidth === 0) failed.push(src);
            else if (!img.complete) pending.push(src);
        });
        return { failed, pending };
    }""")
    broken_images = list(img_status["failed"])
    try:
        ctx = page.context if hasattr(page, "context") else page.page.context
    except Exception:
        ctx = None
    if ctx is not None:
        for src in img_status["pending"][:10]:
            if not src.startswith(("http://", "https://")):
                continue
            try:
                resp = await ctx.request.head(src, timeout=5000)
                status = resp.status
                if status in (405, 501):  # server rejects HEAD
                    resp = await ctx.request.get(src, timeout=5000)
                    status = resp.status
                if status >= 400:
                    broken_images.append(f"{src} ({status})")
            except Exception:
                broken_images.append(f"{src} (unreachable)")
    if broken_images:
        issues.append({
            "type": "visual",
            "severity": "error",
            "message": f"{len(broken_images)} broken images",
            "details": broken_images[:5]  # Limit to first 5
        })

    # Check for missing favicon
    has_favicon = await page.evaluate("""() => {
        return !!document.querySelector('link[rel*="icon"]');
    }""")
    if not has_favicon:
        issues.append({
            "type": "visual",
            "severity": "warning",
            "message": "Missing favicon"
        })

    # Check for horizontal overflow (layout issues)
    has_overflow = await page.evaluate("""() => {
        return document.documentElement.scrollWidth > document.documentElement.clientWidth;
    }""")
    if has_overflow:
        issues.append({
            "type": "visual",
            "severity": "warning",
            "message": "Page has horizontal overflow (possible layout issue)"
        })

    # Check for very small text
    small_text = await page.evaluate("""() => {
        const elements = document.querySelectorAll('p, span, li, td, th, label');
        let count = 0;
        elements.forEach(el => {
            const style = window.getComputedStyle(el);
            const fontSize = parseFloat(style.fontSize);
            if (fontSize < 12 && el.textContent.trim().length > 0) {
                count++;
            }
        });
        return count;
    }""")
    if small_text > 0:
        issues.append({
            "type": "visual",
            "severity": "info",
            "message": f"{small_text} elements with very small text (< 12px)"
        })

    # Check for missing background on body
    has_bg = await page.evaluate("""() => {
        const body = document.body;
        const style = window.getComputedStyle(body);
        const bg = style.backgroundColor;
        // rgba(0, 0, 0, 0) is transparent
        return bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent';
    }""")
    if not has_bg:
        issues.append({
            "type": "visual",
            "severity": "info",
            "message": "Body has no background color set"
        })

    # Check for images without dimensions
    images_no_dims = await page.evaluate("""() => {
        const imgs = document.querySelectorAll('img');
        let count = 0;
        imgs.forEach(img => {
            if (!img.hasAttribute('width') && !img.hasAttribute('height') &&
                !img.style.width && !img.style.height) {
                count++;
            }
        });
        return count;
    }""")
    if images_no_dims > 0:
        issues.append({
            "type": "visual",
            "severity": "info",
            "message": f"{images_no_dims} images without explicit dimensions (can cause layout shift)"
        })

    return issues
