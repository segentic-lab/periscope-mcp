from playwright.async_api import Page


async def check_visual(page: Page) -> list[dict]:
    """
    Run visual checks on a page.
    Returns list of issues found.
    """
    issues = []

    # Check for broken images
    broken_images = await page.evaluate("""() => {
        const imgs = document.querySelectorAll('img');
        const broken = [];
        imgs.forEach(img => {
            if (!img.complete || img.naturalWidth === 0) {
                broken.push(img.src || img.outerHTML.substring(0, 100));
            }
        });
        return broken;
    }""")
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
