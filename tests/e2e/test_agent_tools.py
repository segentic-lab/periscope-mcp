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


def test_find_element_tailwind_classes_yield_valid_selector(run, handlers, session):
    # Issue #3: hover:bg-accent / [&_svg]:size-4 must never appear in the selector
    r = run(handlers["find_element"]({"session_id": session, "text": "Tailwind Btn"}))
    sel = r["elements"][0]["selector"]
    # the advertised selector must be valid CSS and resolve to the element
    check = run(handlers["get_page_elements"]({"session_id": session, "selector": sel}))
    assert check["count"] == 1, (sel, check)
    assert check["elements"][0]["text"] == "Tailwind Btn"


def test_find_element_prefers_visible_and_implicit_roles(run, handlers, session):
    # Issue #10: a visibility:hidden duplicate precedes the visible copy
    r = run(handlers["find_element"]({"session_id": session, "text": "Nadzorna plošča"}))
    assert r["found"] >= 1
    top = r["elements"][0]
    assert top["visible"] is True, r["elements"]
    # returned selector must resolve to the visible copy
    check = run(handlers["interact_and_test"]({
        "session_id": session, "screenshot_after": False,
        "steps": [{"action": "evaluate_js",
                   "script": "document.querySelector(" + repr(top["selector"]) + ").closest('a') !== null"}],
    }))
    assert check["steps"][0]["result"] is True, top

    # implicit role: <a href> is a link without role="link"
    r = run(handlers["find_element"]({
        "session_id": session, "text": "Nadzorna plošča", "role": "link",
    }))
    assert r["found"] == 1, r
    assert r["elements"][0]["role"] == "link"


def test_get_page_elements_friendly_dialect_error(run, handlers, session):
    r = run(handlers["get_page_elements"]({"session_id": session, "selector": "button:visible"}))
    assert r["success"] is False
    assert "standard CSS only" in r["error"], r


def test_auto_fill_form_placeholder_aria_and_path_selectors(run, handlers, session):
    # Issue #2: id/name-less fields must get unambiguous selectors and fill fast
    import time
    start = time.time()
    r = run(handlers["auto_fill_form"]({"session_id": session, "form_selector": "#g"}))
    assert time.time() - start < 15, "auto_fill_form stalled on per-field timeouts"
    assert r["success"] is True, r["fields_failed"]
    assert r["failed_count"] == 0
    values = {f["selector"]: f.get("value") for f in r["fields_filled"]}
    assert len(values) == 3
    # placeholder hint carried e-mail inference; selectors are not bare 'input'
    assert all(sel != "input" for sel in values)
    filled = run(handlers["interact_and_test"]({
        "session_id": session, "screenshot_after": False,
        "steps": [{"action": "evaluate_js",
                   "script": "Array.from(document.querySelectorAll('#g input')).map(i => i.value)"}],
    }))
    assert all(v for v in filled["steps"][0]["result"]), filled["steps"][0]["result"]


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


# --- 0.11: network_summary ---------------------------------------------------

def test_network_summary_bytes_by_domain_and_type(run, handlers, good_site, bad_site):
    r = run(handlers["open_session"]({"url": f"{good_site}/weighty.html?third={bad_site}"}))
    assert r["success"], r
    sid = r["session_id"]
    try:
        run(handlers["interact_and_test"]({"session_id": sid, "screenshot_after": False,
                                           "steps": [{"action": "wait", "timeout": 500}]}))
        s = run(handlers["network_summary"]({"session_id": sid}))
        assert s["success"] and s["requests"] >= 4, s
        assert s["bytes_total"] > 0 and s["bytes_known_for"] >= 1, s
        assert sum(d["requests"] for d in s["by_domain"]) == s["requests"], s["by_domain"]
        domains = {d["domain"]: d for d in s["by_domain"]}
        third_host = bad_site.split("//")[1]
        assert domains[third_host]["third_party"] is True and domains[third_host]["requests"] == 1, domains
        first_host = good_site.split("//")[1]
        assert domains[first_host]["third_party"] is False
        types = {t["type"] for t in s["by_type"]}
        assert {"document", "image", "script", "fetch"} <= types, types
        bytes_list = [x["bytes"] or 0 for x in s["largest"]]
        assert bytes_list == sorted(bytes_list, reverse=True), s["largest"]
        assert 0 <= s["third_party_share"] <= 1

        # since="clear": only requests after get_network_log(clear=true)
        run(handlers["get_network_log"]({"session_id": sid, "clear": True}))
        run(handlers["interact_and_test"]({"session_id": sid, "screenshot_after": False,
                                           "steps": [{"action": "click", "selector": "#more"},
                                                     {"action": "wait_for_network", "url_pattern": "from=click"}]}))
        s2 = run(handlers["network_summary"]({"session_id": sid, "since": "clear"}))
        assert s2["requests"] == 1 and s2["since"] == "clear", s2
        assert s2["largest"][0]["url"].endswith("from=click"), s2
    finally:
        run(handlers["close_session"]({"session_id": sid}))
