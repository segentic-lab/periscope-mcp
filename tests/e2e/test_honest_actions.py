"""0.11: actions never report success for something that visibly didn't happen
(click change detection + strategy escalation, verified fills, stepped hover)."""
import pytest


@pytest.fixture()
def trusted_session(run, handlers, good_site):
    r = run(handlers["open_session"]({"url": f"{good_site}/trusted_click.html"}))
    assert r["success"], r
    yield r["session_id"]
    run(handlers["close_session"]({"session_id": r["session_id"]}))


def _click(run, handlers, sid, selector, **kw):
    return run(handlers["click_element"]({"session_id": sid, "selector": selector,
                                          "observe": "none", **kw}))


def _status(run, handlers, sid):
    return run(handlers["assert_condition"]({
        "session_id": sid, "assertion": "text_equals", "selector": "#status", "expected": "TRUSTED"}))


def test_noop_click_reports_no_change_with_hint(run, handlers, trusted_session):
    r = _click(run, handlers, trusted_session, "#noop")
    assert r["changed"] is False and r["change"] == [], r
    assert "hint" in r and r["click_method"] == "pointer", r


def test_click_network_only_change_counts(run, handlers, trusted_session):
    r = _click(run, handlers, trusted_session, "#net-only")
    assert r["changed"] is True and "network" in r["change"], r
    assert "hint" not in r, r


def test_trusted_click_changes_dom(run, handlers, trusted_session):
    r = _click(run, handlers, trusted_session, "#trusted-only")
    assert r["changed"] is True and "dom" in r["change"], r
    assert r["click_method"] == "pointer" and r["attempts"] == ["pointer"], r


def test_js_dispatch_ignored_gets_trusted_hint(run, handlers, trusted_session):
    # Unstable trusted-only control: single strategy ends in js_dispatch,
    # which the page ignores — the result must say so, not claim success.
    r = _click(run, handlers, trusted_session, "#jittery")
    assert r["click_method"] == "js_dispatch", r
    assert r["changed"] is False and "isTrusted" in r["hint"], r
    assert not _status(run, handlers, trusted_session)["passed"]


def test_auto_strategy_escalates_to_force(run, handlers, trusted_session):
    r = _click(run, handlers, trusted_session, "#jittery", strategy="auto")
    assert r["click_method"] == "pointer_force" and r["changed"] is True, r
    assert r["attempts"] == ["pointer", "pointer_force"], r
    assert _status(run, handlers, trusted_session)["passed"]


def test_auto_strategy_stops_after_first_change(run, handlers, trusted_session):
    r = _click(run, handlers, trusted_session, "#trusted-only", strategy="auto")
    assert r["attempts"] == ["pointer"], r


def test_click_step_carries_change_fields(run, handlers, trusted_session):
    r = run(handlers["interact_and_test"]({
        "session_id": trusted_session, "screenshot_after": False,
        "steps": [{"action": "click", "selector": "#noop"},
                  {"action": "click", "selector": "#jittery", "strategy": "auto"}]}))
    assert r["success"], r
    assert r["steps"][0]["changed"] is False and "hint" in r["steps"][0], r["steps"][0]
    assert r["steps"][1]["click_method"] == "pointer_force", r["steps"][1]


def test_fill_controlled_input_retries_native(run, handlers, trusted_session):
    r = run(handlers["fill_form"]({"session_id": trusted_session, "observe": "none",
                                   "fields": [{"selector": "#controlled", "value": "hello"}]}))
    f = r["fields"][0]
    assert f["verified"] is True and f["fill_method"] == "native_setter", r
    assert f["actual"] == "hello", r


def test_fill_plain_input_is_verified_first_try(run, handlers, trusted_session):
    r = run(handlers["fill_form"]({"session_id": trusted_session, "observe": "none",
                                   "fields": [{"selector": "#plain-input", "value": "x"}]}))
    assert r["fields"][0] == {"selector": "#plain-input", "verified": True,
                              "fill_method": "fill", "actual": "x"}, r
    assert r["fields_filled"] == ["#plain-input"]


def test_fill_step_reports_verification(run, handlers, trusted_session):
    r = run(handlers["interact_and_test"]({
        "session_id": trusted_session, "screenshot_after": False,
        "steps": [{"action": "fill", "selector": "#controlled", "value": "abc"}]}))
    assert r["success"], r
    assert r["steps"][0]["verified"] is True and r["steps"][0]["fill_method"] == "native_setter", r


@pytest.fixture()
def menu_session(run, handlers, good_site):
    r = run(handlers["open_session"]({"url": f"{good_site}/menu_hover.html"}))
    assert r["success"], r
    yield r["session_id"]
    run(handlers["close_session"]({"session_id": r["session_id"]}))


def _submenu_visible(run, handlers, sid):
    return run(handlers["assert_condition"]({
        "session_id": sid, "assertion": "element_visible", "selector": "#submenu"}))["passed"]


def test_hover_element_opens_mousemove_menu(run, handlers, menu_session):
    r = run(handlers["hover_element"]({"session_id": menu_session, "selector": "#trigger",
                                       "observe": "none"}))
    assert r["success"] and r["steps"] == 8 and r["moves"] == 11, r
    assert r["changed"] is True and "dom" in r["change"], r
    assert _submenu_visible(run, handlers, menu_session)


def test_hover_step_default_is_stepped(run, handlers, menu_session):
    r = run(handlers["interact_and_test"]({
        "session_id": menu_session, "screenshot_after": False,
        "steps": [{"action": "hover", "selector": "#trigger"}]}))
    assert r["success"], r
    assert r["steps"][0]["moves"] >= 3, r["steps"][0]
    assert _submenu_visible(run, handlers, menu_session)


# --- review fixes: slow requests, delayed DOM, missing selectors ------------

def _slow_hits(run, handlers, sid):
    r = run(handlers["interact_and_test"]({"session_id": sid, "screenshot_after": False,
                                           "steps": [{"action": "evaluate_js",
                                                      "script": "fetch('/api/slow-count').then(r => r.json()).then(j => j.count)"}]}))
    return r["steps"][0]["result"]


def test_slow_request_counts_as_change_single(run, handlers, trusted_session):
    r = _click(run, handlers, trusted_session, "#slow-post")
    assert r["changed"] is True and "network" in r["change"] and "hint" not in r, r


def test_auto_never_reclicks_slow_post(run, handlers, trusted_session):
    before = _slow_hits(run, handlers, trusted_session)
    r = run(handlers["interact_and_test"]({
        "session_id": trusted_session, "screenshot_after": False,
        "steps": [{"action": "click", "selector": "#slow-post", "strategy": "auto"},
                  {"action": "wait", "timeout": 1200}]}))
    assert r["success"] and r["steps"][0]["attempts"] == ["pointer"], r["steps"][0]
    assert _slow_hits(run, handlers, trusted_session) == before + 1


def test_auto_waits_for_delayed_dom_change(run, handlers, trusted_session):
    r = _click(run, handlers, trusted_session, "#delayed-dom", strategy="auto")
    assert r["attempts"] == ["pointer"] and r["changed"] is True and "dom" in r["change"], r


def test_missing_selector_fails_fast_and_clearly(run, handlers, trusted_session):
    import time
    t0 = time.time()
    r = _click(run, handlers, trusted_session, "#does-not-exist", strategy="auto")
    assert time.time() - t0 < 4, "must not walk the whole escalation chain for a missing element"
    assert r.get("success") is False and "no element matches" in r["error"], r


def test_fill_contenteditable_and_shadow_input(run, handlers, trusted_session):
    r = run(handlers["fill_form"]({"session_id": trusted_session, "observe": "none",
                                   "fields": [{"selector": "#ed", "value": "rich text"},
                                              {"selector": "#sh input", "value": "shadowed"}]}))
    assert r["all_verified"] is True, r
    assert r["fields"][0]["actual"] == "rich text" and r["fields"][1]["actual"] == "shadowed", r
