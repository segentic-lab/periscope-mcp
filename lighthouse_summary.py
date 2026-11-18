"""Post-processing of Lighthouse JSON reports: the summary an agent otherwise
computes by hand (LCP element + phases, TTFB, bytes by domain, top
opportunities) and median selection across repeated runs.

Handles both the Lighthouse ≥13 insight audits (`lcp-breakdown-insight`) and
the older `largest-contentful-paint-element` audit shape. Pure functions, no
I/O — unit-tested against tests/fixtures/lighthouse_min.json.
"""
from statistics import median as _median
from urllib.parse import urlparse

METRIC_IDS = ["first-contentful-paint", "largest-contentful-paint", "total-blocking-time",
              "cumulative-layout-shift", "speed-index", "interactive"]
TTFB_WARN_MS = 2000

# LH13 lcp-breakdown subpart → our key; legacy phase label → our key
_SUBPARTS = {"timeToFirstByte": "ttfb_ms", "resourceLoadDelay": "load_delay_ms",
             "resourceLoadDuration": "load_time_ms", "elementRenderDelay": "render_delay_ms"}
_LEGACY_PHASES = {"ttfb": "ttfb_ms", "load delay": "load_delay_ms",
                  "load time": "load_time_ms", "render delay": "render_delay_ms"}


def _round(v):
    try:
        return round(float(v))
    except (TypeError, ValueError):
        return None


def _node_info(node: dict) -> dict:
    return {"selector": node.get("selector"), "snippet": node.get("snippet"),
            "label": node.get("nodeLabel")}


def _lcp(audits: dict) -> tuple[dict | None, dict | None]:
    """(lcp_element, lcp_phases) from whichever audit shape is present."""
    element, phases = None, None
    insight = audits.get("lcp-breakdown-insight") or {}
    for item in (insight.get("details") or {}).get("items") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "node":
            element = _node_info(item)
        elif item.get("type") == "table":
            phases = {k: None for k in _SUBPARTS.values()}
            for row in item.get("items") or []:
                key = _SUBPARTS.get(row.get("subpart"))
                if key:
                    phases[key] = _round(row.get("duration"))
    if element or phases:
        return element, phases

    legacy = audits.get("largest-contentful-paint-element") or {}
    for item in (legacy.get("details") or {}).get("items") or []:
        if not isinstance(item, dict):
            continue
        for row in item.get("items") or []:
            if isinstance(row.get("node"), dict) and element is None:
                element = _node_info(row["node"])
            elif "phase" in row:
                phases = phases or {k: None for k in _LEGACY_PHASES.values()}
                key = _LEGACY_PHASES.get(str(row["phase"]).strip().lower())
                if key:
                    phases[key] = _round(row.get("timing"))
    return element, phases


def _bytes_by_domain(audits: dict, page_host: str | None) -> tuple[list, int, int]:
    rows = ((audits.get("network-requests") or {}).get("details") or {}).get("items") or []
    by = {}
    total = 0
    for r in rows:
        url = r.get("url") or ""
        size = r.get("transferSize") or 0
        host = urlparse(url).netloc
        if not host:
            continue
        d = by.setdefault(host, {"domain": host, "requests": 0, "bytes": 0,
                                 "third_party": bool(page_host) and host != page_host})
        d["requests"] += 1
        d["bytes"] += size
        total += size
    ordered = sorted(by.values(), key=lambda d: d["bytes"], reverse=True)
    third = sum(d["bytes"] for d in ordered if d["third_party"])
    return ordered, total, third


def _opportunities(audits: dict, top: int = 5) -> list[dict]:
    out = []
    for aid, a in audits.items():
        if not isinstance(a, dict):
            continue
        savings = (a.get("details") or {}).get("overallSavingsMs")
        if not savings:
            ms = a.get("metricSavings") or {}
            savings = max((v or 0) for v in ms.values()) if ms else 0
        if savings and savings > 0:
            out.append({"id": aid, "title": a.get("title"), "savings_ms": _round(savings),
                        "score": a.get("score"), "display": a.get("displayValue")})
    out.sort(key=lambda o: o["savings_ms"], reverse=True)
    return out[:top]


def summarize(report: dict) -> dict:
    """The human-level summary of one Lighthouse report."""
    audits = report.get("audits") or {}
    final_url = report.get("finalDisplayedUrl") or report.get("finalUrl") or ""
    page_host = urlparse(final_url).netloc or None
    element, phases = _lcp(audits)
    srt = (audits.get("server-response-time") or {}).get("numericValue")
    ttfb = _round(srt) if srt is not None else (phases or {}).get("ttfb_ms")
    by_domain, total, third = _bytes_by_domain(audits, page_host)
    return {
        "lcp_element": element,
        "lcp_phases": phases,
        "ttfb_ms": ttfb,
        "ttfb_warning": bool(ttfb is not None and ttfb > TTFB_WARN_MS),
        "bytes_total": total,
        "bytes_by_domain": by_domain[:10],
        "third_party_bytes": third,
        "opportunities": _opportunities(audits),
    }


def _metric(report: dict, mid: str):
    return ((report.get("audits") or {}).get(mid) or {}).get("numericValue")


def median_run(reports: list[dict]) -> tuple[dict, dict]:
    """Pick the report whose LCP is the median (upper median for even counts)
    and compute min/median/max spread per metric and per category score."""
    if not reports:
        raise ValueError("median_run needs at least one report")
    # Runs without an LCP (failed load, NO_LCP) must not become "the median":
    # rank only the runs that measured one; fall back to the first run.
    measured = [r for r in reports if _metric(r, "largest-contentful-paint") is not None]
    ranked = sorted(measured, key=lambda r: _metric(r, "largest-contentful-paint"))
    chosen = ranked[len(ranked) // 2] if ranked else reports[0]
    spread = {}
    for mid in METRIC_IDS:
        vals = [v for v in (_metric(r, mid) for r in reports) if v is not None]
        if vals:
            spread[mid] = {"min": _round(min(vals)), "median": _round(_median(vals)), "max": _round(max(vals))}
    scores = {}
    for cat in (reports[0].get("categories") or {}):
        vals = [(r.get("categories") or {}).get(cat, {}).get("score") for r in reports]
        vals = [v * 100 for v in vals if v is not None]
        if vals:
            scores[cat] = {"min": _round(min(vals)), "median": _round(_median(vals)), "max": _round(max(vals))}
    spread["scores"] = scores
    return chosen, spread


def runtime_error(report: dict) -> str | None:
    """'CODE: message' when Lighthouse itself failed to audit the page."""
    rt = (report or {}).get("runtimeError") or {}
    code = rt.get("code")
    if not code or code == "NO_ERROR":
        return None
    return f"{code}: {rt.get('message') or ''}".strip().rstrip(":")
