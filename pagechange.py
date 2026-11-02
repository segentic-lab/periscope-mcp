"""Page-change detection around an action (click, fill, hover, drag).

An action that "succeeds" but changes nothing is the most expensive lie a
browser tool can tell an agent (hosted checkouts ignoring synthetic clicks,
framework-controlled inputs discarding typed text). Snapshot before, diff
after: url, a cheap DOM fingerprint, and the network-log length.
"""

# Cheap in-page DOM fingerprint — a 32-bit rolling hash of body.innerHTML.
DOM_HASH_JS = """() => {
    let h = 0;
    const s = document.body ? document.body.innerHTML : '';
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
    return h;
}"""

NO_CHANGE_HINT = ("no page change detected (url/dom/network unchanged) — if the element "
                  "is a real control, retry with force=true (trusted pointer click) or "
                  "strategy='auto'")


async def snapshot(page, network_log: list | None = None) -> dict:
    """Capture {url, dom_hash, net_count} for a later diff()."""
    try:
        dom_hash = await page.evaluate(DOM_HASH_JS)
    except Exception:
        dom_hash = None
    return {"url": page.url, "dom_hash": dom_hash, "net_count": len(network_log or [])}


async def diff(page, before: dict, network_log: list | None = None) -> dict:
    """Compare the page against a snapshot → {changed, change: [url|dom|network]}."""
    change = []
    if page.url != before.get("url"):
        change.append("url")
    try:
        dom_hash = await page.evaluate(DOM_HASH_JS)
    except Exception:
        dom_hash = None
    if dom_hash != before.get("dom_hash"):
        change.append("dom")
    if len(network_log or []) != before.get("net_count", 0):
        change.append("network")
    return {"changed": bool(change), "change": change}
