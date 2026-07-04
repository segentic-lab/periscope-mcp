"""Regression tests for issues #15-#19 (second test-agent batch)."""
import pytest


@pytest.fixture()
def overlay_session(run, handlers, good_site):
    r = run(handlers["open_session"]({"url": f"{good_site}/overlay.html"}))
    assert r["success"], r
    yield r["session_id"]
    run(handlers["close_session"]({"session_id": r["session_id"]}))


def test_overlay_click_falls_back_to_js_dispatch(run, handlers, overlay_session):
    # Issue #15: a fixed inset-0 portal overlay intercepts the pointer — the
    # click must fall back to element-level dispatch instead of timing out.
    r = run(handlers["click_element"]({"session_id": overlay_session, "selector": "#covered-btn"}))
    assert "error" not in r, r
    assert r.get("click_method") == "js_dispatch", r
    assert r.get("overlay_bypassed") is True, r
    a = run(handlers["assert_condition"]({
        "session_id": overlay_session, "assertion": "text_contains",
        "selector": "#status", "expected": "CLICKED"}))
    assert a["passed"], a


def test_unblocked_click_stays_pointer_based(run, handlers, overlay_session):
    # The fallback must not kick in for ordinary clicks.
    r = run(handlers["click_element"]({"session_id": overlay_session, "selector": "#plain-btn"}))
    assert "error" not in r, r
    assert "click_method" not in r, r


def test_select_option_element_index(run, handlers, overlay_session):
    # Issue #16: target the 2nd of three attribute-less <select> elements.
    r = run(handlers["select_option"]({
        "session_id": overlay_session, "selector": "select",
        "element_index": 1, "label": "Beta2"}))
    assert r["success"], r
    els = run(handlers["get_page_elements"]({
        "session_id": overlay_session, "selector": "select"}))
    values = [e.get("value") for e in els["elements"]]
    assert values[1] == "b2", values          # the targeted 2nd select changed
    assert values[0] != "b2" and values[2] != "b2", values  # neighbours untouched


def test_select_option_rejects_playwright_syntax(run, handlers, overlay_session):
    r = run(handlers["select_option"]({
        "session_id": overlay_session, "selector": "select >> nth=1", "label": "Beta2"}))
    assert not r["success"]
    assert "element_index" in r["error"], r["error"]


def test_select_option_element_index_out_of_range(run, handlers, overlay_session):
    r = run(handlers["select_option"]({
        "session_id": overlay_session, "selector": "select",
        "element_index": 7, "label": "Beta2"}))
    assert not r["success"]
    assert "out of range" in r["error"] and "3" in r["error"], r["error"]


def test_measure_interaction_binds_to_async_network(run, handlers, overlay_session):
    # Issue #17: the save handler fires its fetch ~400ms after the click.
    # Plain networkidle would settle early; wait_for_network must measure
    # through the actual response.
    r = run(handlers["measure_interaction"]({
        "session_id": overlay_session, "selector": "#save",
        "wait_for_network": "/api/items"}))
    assert r["elapsed_ms"] >= 350, r
    assert "/api/items" in r["matched_url"], r
    assert r["matched_status"] == 200, r
    assert "network response" in r["measures"], r
    assert "interaction_to_next_paint_ms" in r  # may be None for a trivial handler


def test_get_response_body_miss_lists_candidates(run, handlers, overlay_session):
    # Issue #18: a regex-style pattern must fail with substring semantics
    # spelled out and the captured URLs echoed for one-round-trip debugging.
    run(handlers["click_element"]({"session_id": overlay_session, "selector": "#save"}))
    run(handlers["wait_for_network"]({
        "session_id": overlay_session, "url_pattern": "/api/items", "timeout": 5000}))
    # body capture runs on the response event — give it a beat to land
    run(handlers["interact_and_test"]({
        "session_id": overlay_session, "screenshot_after": False,
        "steps": [{"action": "wait", "timeout": 400}]}))
    r = run(handlers["get_response_body"]({
        "session_id": overlay_session, "url_pattern": "api/items$"}))
    assert not r["success"]
    assert "substring" in r["error"], r["error"]
    assert any("/api/items" in u for u in r["captured_urls"]), r


def test_wait_for_network_step_missing_pattern_is_actionable(run, handlers, overlay_session):
    # Issue #19: omitting url_pattern must not surface a bare KeyError.
    r = run(handlers["interact_and_test"]({
        "session_id": overlay_session, "screenshot_after": False,
        "steps": [{"action": "wait_for_network", "timeout": 1000}]}))
    assert not r["success"]
    assert "missing required field 'url_pattern'" in r["error"], r["error"]
    assert "wait_for_network" in r["error"], r["error"]


def test_wait_for_network_tool_missing_pattern_is_actionable(run, handlers, overlay_session):
    r = run(handlers["wait_for_network"]({"session_id": overlay_session}))
    assert not r["success"]
    assert "url_pattern" in r["error"] and "substring" in r["error"], r["error"]
