"""0.12: rough edges found by driving every tool through the live MCP server."""
import pytest


@pytest.fixture()
def hunt(run, handlers, good_site):
    r = run(handlers["open_session"]({"url": f"{good_site}/hunt.html"}))
    assert r["success"], r
    yield r["session_id"]
    run(handlers["close_session"]({"session_id": r["session_id"]}))


def _js(run, handlers, sid, script):
    r = run(handlers["interact_and_test"]({"session_id": sid, "screenshot_after": False,
                                           "steps": [{"action": "evaluate_js", "script": script}]}))
    assert r["success"], r
    return r


def test_nav_generation_ignores_fragment_and_same_url_history_noise(run, handlers, session):
    g0 = run(handlers["get_cookies"]({"session_id": session}))["nav_generation"]
    r = _js(run, handlers, session,
            "history.replaceState({}, '', '#a'); location.hash = 'b'; history.replaceState({}, '', location.href); 1")
    run(handlers["screenshot_session"]({"session_id": session}))          # scroll-spy style churn
    assert run(handlers["get_cookies"]({"session_id": session}))["nav_generation"] == g0
    run(handlers["click_element"]({"session_id": session, "selector": "#spa-nav", "observe": "none"}))
    _js(run, handlers, session, "new Promise(r => setTimeout(r, 300))")
    g1 = run(handlers["get_cookies"]({"session_id": session}))["nav_generation"]
    assert g1 == g0 + 1, (g0, g1)                                          # SPA route change counts
    run(handlers["navigate_session"]({"session_id": session, "action": "goto",
                                      "url": run(handlers["get_cookies"]({"session_id": session})) and
                                      __import__("runtime").session_manager.sessions[session].page.url.replace("/spa-page", "/app.html"),
                                      "observe": "none"}))
    assert run(handlers["get_cookies"]({"session_id": session}))["nav_generation"] == g1 + 1


def test_page_state_diff_sees_changes_on_idless_elements(run, handlers, hunt):
    run(handlers["page_state"]({"session_id": hunt, "action": "snapshot", "name": "s"}))
    _js(run, handlers, hunt, "document.querySelector('#plain li:nth-child(2)').textContent = 'TWO!'; 1")
    run(handlers["click_element"]({"session_id": hunt, "selector": "#tog", "observe": "none"}))
    d = run(handlers["page_state"]({"session_id": hunt, "action": "diff", "name": "s"}))
    assert d["changed"] is True and d["changed_count"] >= 2, d
    blob = str(d["changed_elements"])
    assert "TWO!" in blob and "aria-checked" in blob, d["changed_elements"]
    same = run(handlers["page_state"]({"session_id": hunt, "action": "snapshot", "name": "t"}))
    d2 = run(handlers["page_state"]({"session_id": hunt, "action": "diff", "name": "t"}))
    assert d2["changed"] is False and d2["changed_count"] == 0, d2


def test_click_that_opens_a_popup_is_a_change(run, handlers, good_site):
    s = run(handlers["open_session"]({"url": f"{good_site}/popup.html"}))
    try:
        r = run(handlers["click_element"]({"session_id": s["session_id"], "selector": "#open", "observe": "none"}))
        assert r["changed"] is True and "popup" in r["change"] and "hint" not in r, r
    finally:
        run(handlers["close_session"]({"session_id": s["session_id"]}))


def test_redirect_alias_is_not_listed_as_uncrawled(run, handlers, good_site):
    p = "aliasproj"
    try:
        assert run(handlers["create_project"]({"name": p, "base_url": f"{good_site}/hub.html"}))["success"]
        r = run(handlers["crawl_project"]({"project": p, "max_pages": 10, "max_depth": 1, "use_sitemap": False}))
        assert r["pages_not_crawled"] == [] and r["discovered_total"] == r["pages_found"], r
    finally:
        run(handlers["delete_project"]({"name": p}))


def test_page_map_landmarks(run, handlers, hunt):
    m = run(handlers["get_page_map"]({"session_id": hunt, "max_nodes": 300}))
    by_sel = {n["selector"]: n for n in m["nodes"]}
    assert "#sec-head" not in by_sel or by_sel["#sec-head"]["role"] != "banner", by_sel.get("#sec-head")
    assert by_sel["#nav1"]["name"] == "Main menu"
    assert "name" not in by_sel["#nav2"] or by_sel["#nav2"]["name"] == "", by_sel["#nav2"]


def test_contrast_skips_elements_without_text(run, handlers, hunt):
    r = run(handlers["check_color_contrast"]({"session_id": hunt, "selector": "#empty-li"}))
    assert r["checked"] == 0 and r["fail_count"] == 0, r


def test_form_validation_lists_controls_not_fieldsets(run, handlers, hunt):
    r = run(handlers["test_form_validation"]({"session_id": hunt, "form_selector": "#vf"}))
    tags = [f["tag"] for f in r["results"][0]["invalid_fields"]]
    assert tags == ["input"], tags


def test_console_errors_name_the_failing_url(run, handlers, hunt):
    _js(run, handlers, hunt, "fetch('/nope404-resource').then(() => 1)")
    c = run(handlers["get_console_errors"]({"session_id": hunt}))
    assert any("/nope404-resource" in e for e in c["console_errors"]), c


def test_network_log_reports_sizes(run, handlers, hunt):
    log = run(handlers["get_network_log"]({"session_id": hunt}))
    assert all("content_length" in e and "from_service_worker" in e for e in log["requests"]), log["requests"][:2]


def test_check_pwa_plain_site_is_informational(run, handlers, good_site):
    r = run(handlers["check_pwa"]({"url": f"{good_site}/app.html"}))
    assert r["is_pwa"] is False and {i["severity"] for i in r["issues"]} == {"info"}, r["issues"]
    assert "in-incognito" not in str(r), r["installability"]


def test_wait_for_gone_says_when_never_present(run, handlers, hunt):
    r = run(handlers["wait_for_gone"]({"session_id": hunt, "selector": ".never-here", "timeout": 500}))
    assert r["success"] is True and r["was_present"] is False, r
    r = run(handlers["wait_for_gone"]({"session_id": hunt, "selector": "#top-h", "timeout": 300}))
    assert r["success"] is False and r["was_present"] is True, r


def test_auto_fill_understands_slovenian_and_skips_honeypots(run, handlers, hunt):
    r = run(handlers["auto_fill_form"]({"session_id": hunt, "form_selector": "#vf"}))
    vals = {f["selector"]: f["value"] for f in r["fields_filled"]}
    assert vals["input[name=\"mail\"]"] == "test@example.com", vals
    assert vals["input[name=\"geslo\"]"] == "TestPassword123!", vals
    assert "skipped" in vals["input[name=\"website\"]"], vals
    hp = _js(run, handlers, hunt, "document.querySelector('#vf [name=website]').value")
    assert hp["steps"][0]["result"] == ""


def test_select_iframe_returns_session_id(run, handlers, good_site):
    s = run(handlers["open_session"]({"url": f"{good_site}/frames.html"}))
    try:
        f = run(handlers["select_iframe"]({"session_id": s["session_id"], "selector": "#inner"}))
        assert f["session_id"] == f["iframe_session_id"], f
    finally:
        run(handlers["close_session"]({"session_id": s["session_id"]}))


def test_check_links_verifies_same_page_anchors_once(run, handlers, hunt):
    r = run(handlers["check_links"]({"session_id": hunt}))
    by = {x["url"].split("hunt.html")[-1]: x for x in r["internal"]["results"]}
    assert by["#top-h"]["ok"] is True and by["#top-h"]["status"] == "anchor found", by["#top-h"]
    assert by["#x1"]["ok"] is False and "anchor" in str(by["#x1"]["status"]), by["#x1"]
