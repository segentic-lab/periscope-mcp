"""observe param (issue #21): action tools let the caller choose what comes back
— screenshot (default/back-compat), none (cheapest), map, or checks — instead of
a forced screenshot on every call."""


def test_default_is_screenshot_backcompat(run, handlers, session):
    # No observe arg == historical behavior: a screenshot_path, no map/checks.
    r = run(handlers["click_element"]({"session_id": session, "selector": "#btn"}))
    assert r.get("screenshot_path"), r
    assert "page_map" not in r and "checks" not in r


def test_observe_none_skips_the_screenshot(run, handlers, session):
    r = run(handlers["click_element"]({
        "session_id": session, "selector": "#btn", "observe": "none"}))
    # Structured result still present (proves the action ran) …
    assert r.get("url")
    # … but no image was captured — the round-trip/token cost is gone.
    assert "screenshot_path" not in r
    assert "page_map" not in r and "checks" not in r


def test_observe_map_bundles_the_page_map(run, handlers, session):
    r = run(handlers["click_element"]({
        "session_id": session, "selector": "#btn", "observe": "map"}))
    assert "screenshot_path" not in r
    pm = r.get("page_map")
    assert pm and isinstance(pm.get("nodes"), list) and pm["nodes"], pm
    # same shape get_page_map returns standalone
    assert "total" in pm and "returned" in pm


def test_observe_checks_bundles_check_output(run, handlers, session):
    r = run(handlers["click_element"]({
        "session_id": session, "selector": "#btn", "observe": "checks"}))
    ch = r.get("checks")
    assert ch and "issues" in ch and "issue_count" in ch, ch


def test_unknown_observe_warns_not_crashes(run, handlers, session):
    r = run(handlers["click_element"]({
        "session_id": session, "selector": "#btn", "observe": "bogus"}))
    assert "observe_warning" in r and "bogus" in r["observe_warning"]
    assert "screenshot_path" not in r


def test_observe_applies_to_navigate_and_scroll(run, handlers, session):
    # the param is shared across the action-tool set, not just click
    r = run(handlers["navigate_session"]({
        "session_id": session, "action": "reload", "observe": "none"}))
    assert r["success"] and "screenshot_path" not in r
    r = run(handlers["scroll_into_view"]({
        "session_id": session, "selector": "#btn", "observe": "map"}))
    assert r["success"] and r.get("page_map", {}).get("nodes")
