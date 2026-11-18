"""Cookie-consent banner helper: accept / deny / dismiss the CMP on a page.

Vendor table first (stable selectors per consent-management platform), then a
language-aware generic fallback (button text inside cookie/consent-looking
containers). "No banner" is a success with found=False, never an error — a
page without a CMP is a perfectly good page.
"""
import re

# Each entry: detect = CSS of the banner root; accept/deny/dismiss = ordered
# candidate selectors for the buttons. Playwright CSS pierces shadow DOM, so
# Usercentrics' shadow-root buttons are reachable with plain selectors.
CMPS = [
    {"name": "complianz", "detect": "#cmplz-cookiebanner-container, .cmplz-cookiebanner",
     "accept": [".cmplz-accept", "button.cmplz-btn.cmplz-accept"],
     "deny": [".cmplz-deny", "button.cmplz-btn.cmplz-deny"],
     "dismiss": [".cmplz-close"]},
    {"name": "cookiebot", "detect": "#CybotCookiebotDialog",
     "accept": ["#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll", "#CybotCookiebotDialogBodyButtonAccept"],
     "deny": ["#CybotCookiebotDialogBodyButtonDecline", "#CybotCookiebotDialogBodyLevelButtonLevelOptinDeclineAll"],
     "dismiss": ["#CybotCookiebotDialogBodyButtonDecline"]},
    {"name": "cookieyes", "detect": ".cky-consent-container, .cky-popup-center",
     "accept": [".cky-btn-accept"], "deny": [".cky-btn-reject"], "dismiss": [".cky-banner-btn-close"]},
    {"name": "onetrust", "detect": "#onetrust-banner-sdk, #onetrust-consent-sdk",
     "accept": ["#onetrust-accept-btn-handler"], "deny": ["#onetrust-reject-all-handler"],
     "dismiss": ["#onetrust-close-btn-container button", ".onetrust-close-btn-handler"]},
    {"name": "borlabs", "detect": "#BorlabsCookieBox, .brlbs-cmpnt-container",
     "accept": ["a[data-cookie-accept-all]", "button[data-cookie-accept-all]", ".brlbs-cmpnt-btn-accept-all"],
     "deny": ["a[data-cookie-refuse]", "button[data-cookie-refuse]", ".brlbs-cmpnt-btn-refuse"],
     "dismiss": ["a[data-cookie-refuse]"]},
    {"name": "usercentrics", "detect": "#usercentrics-root, #usercentrics-cmp-ui",
     "accept": ["#usercentrics-root [data-testid='uc-accept-all-button']", "#usercentrics-cmp-ui #accept"],
     "deny": ["#usercentrics-root [data-testid='uc-deny-all-button']", "#usercentrics-cmp-ui #deny"],
     "dismiss": ["#usercentrics-root [data-testid='uc-deny-all-button']"]},
    {"name": "didomi", "detect": "#didomi-host, #didomi-notice",
     "accept": ["#didomi-notice-agree-button"], "deny": ["#didomi-notice-disagree-button"],
     "dismiss": ["#didomi-notice-disagree-button"]},
    {"name": "osano", "detect": ".osano-cm-window, .osano-cm-dialog",
     "accept": [".osano-cm-accept-all", ".osano-cm-accept"], "deny": [".osano-cm-denyAll", ".osano-cm-deny"],
     "dismiss": [".osano-cm-dialog__close"]},
    {"name": "iubenda", "detect": "#iubenda-cs-banner",
     "accept": [".iubenda-cs-accept-btn"], "deny": [".iubenda-cs-reject-btn"], "dismiss": [".iubenda-cs-close-btn"]},
    {"name": "klaro", "detect": ".klaro .cookie-notice, .klaro .cookie-modal",
     "accept": [".klaro .cm-btn-accept-all", ".klaro .cm-btn-accept"],
     "deny": [".klaro .cm-btn-decline", ".klaro .cm-btn-danger"], "dismiss": [".klaro .cm-btn-decline"]},
    {"name": "cookie_notice", "detect": "#cookie-notice",
     "accept": ["#cn-accept-cookie"], "deny": ["#cn-refuse-cookie"], "dismiss": ["#cn-close-notice"]},
    {"name": "cookie_law_info", "detect": "#cookie-law-info-bar, .cli-modal",
     "accept": ["#cookie_action_close_header", ".cli_action_button[data-cli_action='accept']"],
     "deny": ["#cookie_action_close_header_reject", ".cli_action_button[data-cli_action='reject']"],
     "dismiss": [".cli_action_button[data-cli_action='close']"]},
    {"name": "moove_gdpr", "detect": "#moove_gdpr_cookie_info_bar",
     "accept": [".moove-gdpr-infobar-allow-all"], "deny": [".moove-gdpr-infobar-reject-btn"],
     "dismiss": [".moove-gdpr-infobar-close-btn"]},
    {"name": "quantcast", "detect": ".qc-cmp2-container",
     "accept": [".qc-cmp2-summary-buttons button[mode='primary']"],
     "deny": [".qc-cmp2-summary-buttons button[mode='secondary']"],
     "dismiss": [".qc-cmp2-summary-buttons button[mode='secondary']"]},
    {"name": "termly", "detect": "#termly-code-snippet-support, .t-consent-banner",
     "accept": [".t-acceptAllButton", "[data-tid='banner-accept']"],
     "deny": [".t-declineAllButton", "[data-tid='banner-decline']"], "dismiss": [".t-closeButton"]},
    {"name": "hubspot", "detect": "#hs-eu-cookie-confirmation",
     "accept": ["#hs-eu-confirmation-button"], "deny": ["#hs-eu-decline-button"], "dismiss": ["#hs-eu-decline-button"]},
]

# Generic fallback: button text in en/sl/de/hr/it/es/fr. Deny patterns are
# tested first in the generic path so "Samo nujni" never reads as accept.
GENERIC_TEXT = {
# Leading word boundary only: stems must match inflected forms ("akzeptieren",
# "Samo nujni", "accepted").
    "accept": re.compile(r"\b(accept|allow|agree|sprejmi|sprejmem|strinjam|dovoli|akzeptier|zustimm|"
                         r"prihvati|slažem|accetta|aceptar|accepter|j'accepte|ok\b)", re.I),
    "deny": re.compile(r"\b(reject|decline|deny|refuse|only necessary|essential only|zavrni|zavrnem|"
                       r"samo nujn|samo potrebn|ablehn|nur notwendig|nur erforderlich|odbij|rifiuta|"
                       r"solo necessari|rechazar|solo necesarias|refuser|uniquement nécessaires)", re.I),
}

_GENERIC_CONTAINER = ("[id*='cookie' i], [class*='cookie' i], [id*='consent' i], [class*='consent' i], "
                      "[aria-label*='cookie' i], [id*='gdpr' i], [class*='gdpr' i], [class*='cmp' i]")
_BUTTONS = "button, a[role='button'], [role='button'], input[type='button'], a.button, a.btn"

VALID_ACTIONS = ("accept", "deny", "dismiss")


async def _first_visible(page, selectors: list) -> str | None:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() and await loc.is_visible():
                return sel
        except Exception:
            continue
    return None


async def _click(page, selector: str) -> None:
    loc = page.locator(selector).first
    try:
        await loc.click(timeout=3000)
    except Exception:
        await loc.click(force=True, timeout=3000)


async def _gone(page, detect: str, timeout_ms: int = 3000) -> bool:
    try:
        await page.locator(detect).first.wait_for(state="hidden", timeout=timeout_ms)
        return True
    except Exception:
        return False


async def _generic(page, action: str) -> dict | None:
    """Find a cookie/consent-looking container and a button whose text matches
    the action's regex. Returns {selector, text} or None."""
    pattern = GENERIC_TEXT["accept" if action == "accept" else "deny"]
    other = GENERIC_TEXT["deny" if action == "accept" else "accept"]
    candidates = await page.evaluate("""([containerSel, buttonSel]) => {
        const out = [];
        const containers = document.querySelectorAll(containerSel);
        let i = 0;
        for (const c of containers) {
            const r = c.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) continue;
            for (const b of c.querySelectorAll(buttonSel)) {
                const br = b.getBoundingClientRect();
                if (br.width === 0 || br.height === 0) continue;
                const text = (b.textContent || b.value || b.getAttribute('aria-label') || '').trim();
                if (!text) continue;
                const id = 'periscope-consent-' + (i++);
                b.setAttribute('data-periscope-consent', id);
                out.push({ selector: "[data-periscope-consent='" + id + "']", text });
            }
        }
        return out;
    }""", [_GENERIC_CONTAINER, _BUTTONS])
    for c in candidates:
        if pattern.search(c["text"]) and not other.search(c["text"]):
            return c
    return None


async def apply(page, action: str) -> dict:
    """Accept/deny/dismiss the consent banner on `page`.

    Returns {success, found, cmp, action, clicked, banner_gone}. A page without
    a detectable banner → success with found=False.
    """
    if action not in VALID_ACTIONS:
        return {"success": False, "error":
                f"consent action must be one of accept, deny, dismiss (got {action!r})"}
    for cmp in CMPS:
        try:
            root = page.locator(cmp["detect"]).first
            if not await root.count() or not await root.is_visible():
                continue
        except Exception:
            continue
        chosen = await _first_visible(page, cmp[action]) or (
            await _first_visible(page, cmp["deny"]) if action == "dismiss" else None)
        if not chosen:
            return {"success": True, "found": True, "cmp": cmp["name"], "action": action,
                    "clicked": None, "banner_gone": False,
                    "note": f"{cmp['name']} banner detected but no '{action}' control is visible — "
                            "it may be a two-step dialog; use get_page_map to find the control"}
        await _click(page, chosen)
        return {"success": True, "found": True, "cmp": cmp["name"], "action": action,
                "clicked": chosen, "banner_gone": await _gone(page, cmp["detect"])}

    generic = await _generic(page, action)
    if generic:
        await _click(page, generic["selector"])
        return {"success": True, "found": True, "cmp": "generic", "action": action,
                "clicked": generic["selector"], "clicked_text": generic["text"],
                "banner_gone": await _gone(page, generic["selector"], 2000)}
    return {"success": True, "found": False, "cmp": None, "action": action, "clicked": None,
            "banner_gone": True, "note": "no consent banner detected on this page"}
