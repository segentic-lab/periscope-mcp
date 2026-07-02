"""Check modules against known-good and known-bad fixture pages."""


def _messages(issues):
    return [i["message"] for i in issues]


def test_seo_bad_page(run, handlers, bad_site):
    r = run(handlers["test_url"]({"url": f"{bad_site}/seo_bad.html", "checks": ["seo"]}))
    msgs = " | ".join(_messages(r["issues"]))
    assert "title is very short" in msgs
    assert "Missing meta description" in msgs
    assert "2 H1 headings" in msgs
    assert "Incomplete Open Graph" in msgs
    assert "og:image is not an absolute URL" in msgs
    assert "invalid JSON" in msgs
    assert "search engine crawlers" in msgs  # bad robots.txt blocks Googlebot


def test_seo_good_page(run, handlers, good_site):
    r = run(handlers["test_url"]({"url": f"{good_site}/seo_good.html", "checks": ["seo"]}))
    assert r["issues"] == [], _messages(r["issues"])


def test_geo_bad_site(run, handlers, bad_site):
    r = run(handlers["test_url"]({"url": f"{bad_site}/seo_bad.html", "checks": ["geo"]}))
    msgs = " | ".join(_messages(r["issues"]))
    assert "llms.txt exists but is not compliant" in msgs
    assert "AI crawlers" in msgs
    blocked = next(i for i in r["issues"] if "AI crawlers" in i["message"])
    assert set(blocked["details"]) == {"GPTBot", "ClaudeBot", "PerplexityBot"}
    # seo_bad.html has a (syntactically invalid) JSON-LD block, so the geo
    # presence check stays silent — validity is the SEO check's job


def test_geo_good_site(run, handlers, good_site):
    r = run(handlers["test_url"]({"url": f"{good_site}/seo_good.html", "checks": ["geo"]}))
    assert r["issues"] == [], _messages(r["issues"])


def test_accessibility_bad_page(run, handlers, good_site):
    r = run(handlers["test_url"]({"url": f"{good_site}/a11y_bad.html", "checks": ["accessibility"]}))
    msgs = " | ".join(_messages(r["issues"]))
    assert "images missing alt text" in msgs
    assert "links without accessible text" in msgs
    assert "form inputs without labels" in msgs
    assert "buttons without accessible names" in msgs
    assert "duplicate id values" in msgs
    assert "unknown ARIA role" in msgs
    assert "ARIA references to non-existent ids" in msgs
    assert "Heading levels are skipped" in msgs
    assert "Missing lang attribute" in msgs


def test_accessibility_good_page(run, handlers, good_site):
    r = run(handlers["test_url"]({"url": f"{good_site}/a11y_good.html", "checks": ["accessibility"]}))
    assert r["issues"] == [], _messages(r["issues"])


def test_core_web_vitals(run, handlers, good_site):
    r = run(handlers["open_session"]({"url": f"{good_site}/cwv.html"}))
    sid = r["session_id"]
    try:
        run(handlers["interact_and_test"]({
            "session_id": sid, "screenshot_after": False,
            "steps": [{"action": "wait", "timeout": 500}],
        }))
        r = run(handlers["run_checks_on_session"]({"session_id": sid, "checks": ["performance"]}))
        perf = r["performance"]
        assert perf["largest_contentful_paint_ms"] is not None
        assert perf["cumulative_layout_shift"] > 0        # the late-inserted block
        assert perf["total_blocking_time_ms"] > 0          # the 120ms long task
        assert perf["long_task_count"] >= 1
    finally:
        run(handlers["close_session"]({"session_id": sid}))


def test_keyboard_navigation_identity_cycle(run, handlers, good_site):
    # 5 identically-classed stops — selector-based cycle detection would stop at 2
    r = run(handlers["test_keyboard_navigation"]({"url": f"{good_site}/kbd.html", "max_tabs": 20}))
    assert r["total_tab_stops"] == 5, r["focus_order"]
    assert all(s["has_focus_indicator"] for s in r["focus_order"])
    assert r["issues"] == []


def test_color_contrast_skips_hidden_without_burning_budget(run, handlers, good_site):
    # Issue #4: 60 hidden spans precede the visible table — the sweep must
    # still reach and check the visible text, not report checked: 1
    r = run(handlers["open_session"]({"url": f"{good_site}/app.html"}))
    sid = r["session_id"]
    try:
        r = run(handlers["check_color_contrast"]({"session_id": sid}))
        assert r["checked"] >= 10, r
    finally:
        run(handlers["close_session"]({"session_id": sid}))


def test_skip_link_language_independent(run, handlers, good_site):
    # Issue #5: "Preskoči na vsebino" -> #main must count as a skip link
    r = run(handlers["test_url"]({"url": f"{good_site}/a11y_good.html", "checks": ["accessibility"]}))
    assert not any("skip navigation" in m for m in _messages(r["issues"])), _messages(r["issues"])


def test_unknown_check_name_warns(run, handlers, good_site):
    r = run(handlers["test_url"]({"url": f"{good_site}/seo_good.html", "checks": ["acessibility"]}))
    assert any("Unknown check name" in m for m in _messages(r["issues"]))
