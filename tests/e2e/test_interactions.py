"""Interactive behaviors: network waits, console capture, dialogs, drag, force fill."""


def _order(run, handlers, sid):
    r = run(handlers["get_page_elements"]({"session_id": sid, "selector": "#list li"}))
    return [e["text"] for e in r["elements"]]


def test_wait_for_network_filters_by_pattern(run, handlers, session):
    # click + wait in one steps call so a fast response can't be missed
    r = run(handlers["interact_and_test"]({
        "session_id": session,
        "steps": [
            {"action": "click", "selector": "#btn"},
            {"action": "wait_for_network", "url_pattern": "/api/items", "timeout": 5000},
        ],
        "screenshot_after": False,
    }))
    assert r["success"], r
    assert "/api/items" in r["steps"][1]["matched_url"]
    assert r["steps"][1]["status"] == 200

    # a pattern that never matches must time out, not match the first response
    r = run(handlers["wait_for_network"]({
        "session_id": session, "url_pattern": "/definitely-not-there", "timeout": 1200,
    }))
    assert r["success"] is False


def test_response_body_capture(run, handlers, session):
    run(handlers["click_element"]({"session_id": session, "selector": "#btn"}))
    r = run(handlers["get_response_body"]({"session_id": session, "url_pattern": "/api/items"}))
    assert r["success"] and '"items"' in r["body_text"]


def test_capture_console(run, handlers, session):
    r = run(handlers["interact_and_test"]({
        "session_id": session,
        "steps": [{"action": "click", "selector": "#errbtn"}],
        "capture_console": True,
        "screenshot_after": False,
    }))
    assert r["success"], r
    assert any("boom" in e for e in r["console_errors"]), r["console_errors"]
    assert any("clicked-err" in l for l in r["console_log"]), r["console_log"]


def test_handle_dialog_before_trigger(run, handlers, session):
    r = run(handlers["handle_dialog"]({"session_id": session, "action": "accept"}))
    assert r["success"]
    run(handlers["click_element"]({"session_id": session, "selector": "#alerty"}))
    r = run(handlers["assert_condition"]({
        "session_id": session, "assertion": "text_equals",
        "selector": "#dialog-result", "expected": "accepted",
    }))
    assert r["passed"], r


def test_drag_auto_noop_mouse_works(run, handlers, good_site):
    r = run(handlers["open_session"]({"url": f"{good_site}/dnd.html"}))
    sid = r["session_id"]
    try:
        assert _order(run, handlers, sid) == ["Alpha", "Beta", "Gamma"]

        # default drag: pointer-tracking DnD ignores it (documented silent no-op)
        r = run(handlers["interact_and_test"]({
            "session_id": sid, "screenshot_after": False,
            "steps": [{"action": "drag", "selector": "#a", "target": "#c"}],
        }))
        assert r["success"] and _order(run, handlers, sid) == ["Alpha", "Beta", "Gamma"]

        # method:"mouse" crosses the drag-start threshold and actually reorders
        r = run(handlers["interact_and_test"]({
            "session_id": sid, "screenshot_after": False,
            "steps": [{"action": "drag", "selector": "#a", "target": "#c", "method": "mouse"}],
        }))
        assert r["success"] and _order(run, handlers, sid) == ["Beta", "Gamma", "Alpha"]
    finally:
        run(handlers["close_session"]({"session_id": sid}))


def test_fill_form_force_bypasses_overlay(run, handlers, session):
    r = run(handlers["fill_form"]({
        "session_id": session,
        "fields": [{"selector": "#covered", "value": "forced-in"}],
        "force": True,
    }))
    assert r["fields_filled"] == ["#covered"]
    # input .value is a property, not an attribute — verify via JS
    r = run(handlers["interact_and_test"]({
        "session_id": session, "screenshot_after": False,
        "steps": [{"action": "evaluate_js", "script": "document.querySelector('#covered').value"}],
    }))
    assert r["steps"][0]["result"] == "forced-in"
