"""Navigation with graceful networkidle degradation (issue #14).

Widgets like Cloudflare Turnstile, reCAPTCHA, analytics beacons, and
websockets keep network activity alive forever, so the default
'networkidle' wait times out on perfectly healthy pages. Instead of
failing those pages (or forcing a global NAV_WAIT_UNTIL=load), retry the
navigation with 'load' plus a short settle beat, per page.
"""
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import config

# How long to let late DOM work settle after a downgraded 'load' navigation
SETTLE_MS = 1500


async def resilient_goto(page, url: str, wait_until: str = None, timeout: int = None):
    """page.goto that downgrades networkidle timeouts to 'load'.

    Returns (response, downgraded). Raises only when even 'load' fails —
    that's a genuinely broken page, not a busy widget.
    """
    wait_until = wait_until or config.WAIT_UNTIL
    timeout = timeout or config.TIMEOUT
    try:
        response = await page.goto(url, wait_until=wait_until, timeout=timeout)
        return response, False
    except PlaywrightTimeoutError:
        if wait_until == "load":
            raise
        response = await page.goto(url, wait_until="load", timeout=timeout)
        await page.wait_for_timeout(SETTLE_MS)
        return response, True
