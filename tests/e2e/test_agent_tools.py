"""Agent-speed tools: find, assert, auto-fill, page_state, element queries."""


def test_find_element_returns_innermost(run, handlers, session):
    r = run(handlers["find_element"]({"session_id": session, "text": "Click me"}))
    assert r["elements"][0]["selector"] == "#btn", r


def test_assert_condition_variants(run, handlers, session):
    ok = run(handlers["assert_condition"]({
        "session_id": session, "assertion": "text_contains",
        "selector": ".msg", "expected": "hello",
    }))
    assert ok["passed"] is True

    count = run(handlers["assert_condition"]({
        "session_id": session, "assertion": "element_count",
        "selector": "#f input", "expected": "3",
    }))
    assert count["passed"] is True

    bad_expected = run(handlers["assert_condition"]({
        "session_id": session, "assertion": "element_count",
        "selector": "#f input", "expected": "many",
    }))
    assert bad_expected["success"] is False and "integer" in bad_expected["error"]

    unknown = run(handlers["assert_condition"]({"session_id": session, "assertion": "nope"}))
    assert unknown["success"] is False and "Unknown assertion" in unknown["error"]


def test_auto_fill_form_semantic_hints(run, handlers, session):
    r = run(handlers["auto_fill_form"]({"session_id": session, "form_selector": "#f"}))
    values = {f["selector"]: f.get("value") for f in r["fields_filled"]}
    assert values['input[name="email"]'] == "test@example.com"
    assert values['input[name="phone"]'] == "+1234567890"
    assert values['input[name="username"]'] == "testuser"


def test_page_state_snapshot_diff_restore(run, handlers, session):
    r = run(handlers["page_state"]({"session_id": session, "action": "snapshot", "name": "s1"}))
    assert r["success"]

    run(handlers["interact_and_test"]({
        "session_id": session, "screenshot_after": False,
        "steps": [{"action": "evaluate_js",
                   "script": "document.querySelector('.msg').textContent = 'changed'"}],
    }))
    diff = run(handlers["page_state"]({"session_id": session, "action": "diff", "name": "s1"}))
    assert diff["success"]
    assert diff["new_element_count"] > 0

    r = run(handlers["page_state"]({"session_id": session, "action": "restore", "name": "s1"}))
    assert r["success"]

    r = run(handlers["page_state"]({"session_id": session, "action": "teleport", "name": "s1"}))
    assert r["success"] is False and "Unknown action" in r["error"]

    r = run(handlers["page_state"]({"session_id": session, "action": "restore", "name": "ghost"}))
    assert r["success"] is False and "not found" in r["error"]


def test_get_page_elements_attributes_and_full_text(run, handlers, session):
    r = run(handlers["get_page_elements"]({
        "session_id": session, "selector": "#btn", "attributes": ["data-testid"],
    }))
    assert r["attributes_requested"] == ["data-testid"]
    assert r["elements"][0]["data-testid"] == "fetch-button"

    preview = run(handlers["get_page_elements"]({"session_id": session, "selector": "#long"}))
    full = run(handlers["get_page_elements"]({
        "session_id": session, "selector": "#long", "full_text": True,
    }))
    assert len(preview["elements"][0]["text"]) == 80
    assert len(full["elements"][0]["text"]) > 80
    assert full["elements"][0]["text"].endswith("preview limit used by default.")


def test_intercept_network_substring_with_query_chars(run, handlers, session):
    r = run(handlers["intercept_network"]({
        "session_id": session, "url_pattern": "items?page=",  # glob metachar in pattern
        "status": 503, "body": '{"error":"mocked"}',
    }))
    assert r["success"]
    run(handlers["click_element"]({"session_id": session, "selector": "#btn"}))
    body = run(handlers["get_response_body"]({"session_id": session, "url_pattern": "/api/items"}))
    assert body["status"] == 503 and "mocked" in body["body_text"]
    r = run(handlers["clear_intercepts"]({"session_id": session}))
    assert r["removed_count"] == 1
