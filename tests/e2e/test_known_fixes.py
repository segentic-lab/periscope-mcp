"""0.12: defects deferred from the 0.11 review, each pinned by a test."""
import json
import urllib.request


def _nav(run, handlers, sid, **kw):
    return run(handlers["navigate_session"]({"session_id": sid, "observe": "none", **kw}))


def test_clear_site_data_rejects_non_http_page(run, handlers):
    s = run(handlers["open_session"]({"url": "about:blank"}))
    assert s["success"], s
    try:
        r = _nav(run, handlers, s["session_id"], action="clear_site_data")
        assert r["success"] is False and "http" in r["error"], r
    finally:
        run(handlers["close_session"]({"session_id": s["session_id"]}))


def test_compare_pages_unknown_device_is_actionable(run, handlers, good_site):
    r = run(handlers["compare_pages"]({"url_a": f"{good_site}/app.html", "url_b": f"{good_site}/app.html",
                                       "device": "nokia 3310"}))
    assert r["success"] is False and "iPhone 14" in r["error"], r


def test_compare_pages_failed_project_side_closes_its_page(run, handlers, good_site):
    import runtime
    p = "cmpproj"
    try:
        assert run(handlers["create_project"]({"name": p, "base_url": good_site}))["success"]
        run(handlers["test_url"]({"url": f"{good_site}/app.html", "project": p, "checks": ["seo"]}))
        ctx = runtime.tester.contexts[p]
        before = len(ctx.pages)
        r = run(handlers["compare_pages"]({"url_a": "http://127.0.0.1:1/", "url_b": f"{good_site}/app.html",
                                           "project": p}))
        assert "error" in r["a"] and r["b"]["title"], r
        assert len(ctx.pages) == before, "the failed side must not leave a page open in the project context"
    finally:
        run(handlers["delete_project"]({"name": p}))


def test_check_pwa_unreachable_url_is_a_clean_failure(run, handlers):
    r = run(handlers["check_pwa"]({"url": "http://127.0.0.1:1/"}))
    assert r["success"] is False and "load" in r["error"], r


def test_anonymous_frames_in_different_parents_get_distinct_selectors(run, handlers, good_site):
    s = run(handlers["open_session"]({"url": f"{good_site}/frames_anon.html"}))
    assert s["success"], s
    try:
        m = run(handlers["get_page_map"]({"session_id": s["session_id"], "include_frames": True}))
        sels = [f["selector"] for f in m["frames"]]
        assert len(sels) == 2 and sels[0] != sels[1], sels
        for sel, who in zip(sels, ("first", "second")):
            f = run(handlers["select_iframe"]({"session_id": s["session_id"], "selector": sel}))
            assert f["success"], f
            a = run(handlers["assert_condition"]({"session_id": f["iframe_session_id"],
                                                  "assertion": "text_equals", "selector": "#who", "expected": who}))
            assert a["passed"], (sel, a)
    finally:
        run(handlers["close_session"]({"session_id": s["session_id"]}))


def test_navigate_from_iframe_session_does_not_crash(run, handlers, good_site):
    s = run(handlers["open_session"]({"url": f"{good_site}/frames.html"}))
    assert s["success"], s
    try:
        f = run(handlers["select_iframe"]({"session_id": s["session_id"], "selector": "#inner"}))
        r = _nav(run, handlers, f["iframe_session_id"], action="goto", url=f"{good_site}/overlay.html")
        assert r["success"] and "Overlay" in r["title"], r
    finally:
        run(handlers["close_session"]({"session_id": s["session_id"]}))


def test_hard_reload_refetches_cached_subresource(run, handlers, good_site):
    def hits():
        return json.load(urllib.request.urlopen(f"{good_site}/cached-count"))["count"]
    s = run(handlers["open_session"]({"url": f"{good_site}/cached.html"}))
    assert s["success"], s
    try:
        first = hits()
        _nav(run, handlers, s["session_id"], action="reload", hard=True)
        assert hits() == first + 1, "hard reload must bypass the HTTP cache for subresources"
    finally:
        run(handlers["close_session"]({"session_id": s["session_id"]}))
