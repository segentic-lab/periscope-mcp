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
