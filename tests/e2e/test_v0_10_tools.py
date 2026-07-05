"""E2E for the 0.10.0 batch: page map, assert_all, popups, downloads,
visual baselines, flows, element-clip screenshots."""
import os

import pytest


@pytest.fixture()
def overlay_session(run, handlers, good_site):
    r = run(handlers["open_session"]({"url": f"{good_site}/overlay.html"}))
    assert r["success"], r
    yield r["session_id"]
    run(handlers["close_session"]({"session_id": r["session_id"]}))


@pytest.fixture()
def popup_session(run, handlers, good_site):
    r = run(handlers["open_session"]({"url": f"{good_site}/popup.html"}))
    assert r["success"], r
    yield r["session_id"]
    run(handlers["close_session"]({"session_id": r["session_id"]}))


def test_get_page_map_semantic_nodes(run, handlers, overlay_session):
    m = run(handlers["get_page_map"]({"session_id": overlay_session}))
    assert m["returned"] > 0 and m["total"] >= m["returned"]
    roles = {n["role"] for n in m["nodes"]}
    assert "button" in roles and "combobox" in roles and "heading" in roles, roles
    assert all(n.get("selector") for n in m["nodes"])
    # every advertised selector must resolve on the page
    sel = next(n["selector"] for n in m["nodes"] if n["role"] == "button")
    r = run(handlers["assert_condition"]({
        "session_id": overlay_session, "assertion": "element_exists", "selector": sel}))
    assert r["passed"], (sel, r)


def test_assert_all_full_verdict_no_abort(run, handlers, overlay_session):
    r = run(handlers["assert_all"]({"session_id": overlay_session, "assertions": [
        {"assertion": "url_contains", "expected": "overlay"},
        {"assertion": "element_exists", "selector": "#save"},
        {"assertion": "text_contains", "selector": "#status", "expected": "NOPE"},
        {"assertion": "element_count", "selector": "select", "expected": "3"},
    ]}))
    assert r["total"] == 4 and r["failed_count"] == 1 and r["passed"] is False
    verdicts = [x["passed"] for x in r["results"]]
    assert verdicts == [True, True, False, True], r["results"]


def test_assert_all_requires_array(run, handlers, overlay_session):
    r = run(handlers["assert_all"]({"session_id": overlay_session, "assertions": []}))
    assert not r["success"] and "non-empty array" in r["error"]


def test_screenshot_element_clip(run, handlers, overlay_session):
    r = run(handlers["screenshot_session"]({
        "session_id": overlay_session, "selector": "#status"}))
    assert r["success"] and os.path.exists(r["screenshot_path"])
    assert "element_" in os.path.basename(r["screenshot_path"])


def test_visual_check_set_pass_then_fail_on_change(run, handlers, overlay_session):
    name = "e2e-status"
    r = run(handlers["visual_check"]({
        "session_id": overlay_session, "name": name, "action": "set", "selector": "#status"}))
    assert r["success"] and os.path.exists(r["baseline_path"])

    r = run(handlers["visual_check"]({
        "session_id": overlay_session, "name": name, "selector": "#status"}))
    assert r["passed"] is True, r

    run(handlers["interact_and_test"]({
        "session_id": overlay_session, "screenshot_after": False,
        "steps": [{"action": "evaluate_js",
                   "script": "document.getElementById('status').textContent='CHANGED CONTENT'"}]}))
    r = run(handlers["visual_check"]({
        "session_id": overlay_session, "name": name, "selector": "#status"}))
    assert r["passed"] is False and r["diff_percentage"] > 0, r
    assert os.path.exists(r["diff_image_path"])


def test_visual_check_missing_baseline_is_actionable(run, handlers, overlay_session):
    r = run(handlers["visual_check"]({
        "session_id": overlay_session, "name": "never-set-baseline"}))
    assert not r["success"] and "action='set'" in r["error"]


def test_flow_save_run_list_delete(run, handlers, overlay_session):
    save = run(handlers["flow"]({"action": "save", "name": "e2e-plain-click",
                                 "steps": [{"action": "click", "selector": "#plain-btn"}]}))
    assert save["success"], save
    listing = run(handlers["flow"]({"action": "list"}))
    assert any(f["name"] == "e2e-plain-click" for f in listing["flows"])

    r = run(handlers["flow"]({"action": "run", "name": "e2e-plain-click",
                              "session_id": overlay_session}))
    assert r["success"] and r["flow"] == "e2e-plain-click", r
    a = run(handlers["assert_condition"]({
        "session_id": overlay_session, "assertion": "text_contains",
        "selector": "#status", "expected": "PLAIN"}))
    assert a["passed"], a

    assert run(handlers["flow"]({"action": "delete", "name": "e2e-plain-click"}))["success"]
    listing = run(handlers["flow"]({"action": "list"}))
    assert not any(f["name"] == "e2e-plain-click" for f in listing["flows"])


def test_select_page_adopts_popup_with_capture_from_birth(run, handlers, popup_session):
    run(handlers["click_element"]({"session_id": popup_session, "selector": "#open"}))
    r = run(handlers["select_page"]({"session_id": popup_session}))
    assert r["success"], r
    child = r["session_id"]
    assert child != popup_session and "popup_child" in r["url"]

    a = run(handlers["assert_condition"]({
        "session_id": child, "assertion": "text_contains",
        "selector": "#msg", "expected": "CHILD READY"}))
    assert a["passed"], a

    # capture-from-open: the fetch the child fired shortly after load was
    # recorded by listeners attached at the popup event
    run(handlers["interact_and_test"]({
        "session_id": child, "screenshot_after": False,
        "steps": [{"action": "wait", "timeout": 600}]}))
    body = run(handlers["get_response_body"]({
        "session_id": child, "url_pattern": "from=child"}))
    assert body["success"], body
    assert "items" in body["body_text"]

    # idempotent re-select returns the same adopted session
    again = run(handlers["select_page"]({"session_id": popup_session}))
    assert again["session_id"] == child
    run(handlers["close_session"]({"session_id": child}))


def test_select_page_without_popups_is_actionable(run, handlers, overlay_session):
    r = run(handlers["select_page"]({"session_id": overlay_session}))
    assert not r["success"] and "No open popups" in r["error"]


def test_download_file_captures_and_previews(run, handlers, popup_session):
    r = run(handlers["download_file"]({"session_id": popup_session, "selector": "#dl"}))
    assert r["success"], r
    assert r["filename"] == "items.json"
    assert r["size_bytes"] > 0 and len(r["sha256"]) == 64
    assert os.path.exists(r["path"])
    assert "items" in r.get("text_head", ""), r
