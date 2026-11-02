"""0.11: navigate_session goto / hard reload / clear_site_data, service-worker
visibility, nav_generation on results, view on screenshots."""
import pytest


@pytest.fixture()
def sw_session(run, handlers, good_site):
    r = run(handlers["open_session"]({"url": f"{good_site}/sw.html"}))
    assert r["success"], r
    yield r["session_id"]
    run(handlers["close_session"]({"session_id": r["session_id"]}))


def _nav(run, handlers, sid, **kw):
    return run(handlers["navigate_session"]({"session_id": sid, "observe": "none", **kw}))


def test_goto_with_wait_for(run, handlers, session, good_site):
    r = _nav(run, handlers, session, action="goto", url=f"{good_site}/overlay.html", wait_for="#status")
    assert r["success"], r
    assert r["url"].endswith("/overlay.html") and "Overlay" in r["title"], r
    assert r["status_code"] == 200 and r["served_by_service_worker"] is False, r


def test_goto_requires_url(run, handlers, session):
    r = _nav(run, handlers, session, action="goto")
    assert r["success"] is False and "url" in r["error"], r


def test_goto_wait_for_network_armed_before_navigation(run, handlers, session, good_site):
    r = _nav(run, handlers, session, action="goto", url=f"{good_site}/app.html",
             wait_for_network="/app.html")
    assert r["success"] and r["matched_url"].endswith("/app.html") and r["matched_status"] == 200, r


def test_second_visit_served_by_service_worker(run, handlers, sw_session, good_site):
    run(handlers["interact_and_test"]({"session_id": sw_session, "screenshot_after": False,
                                       "steps": [{"action": "wait_for_text", "text": "registered"},
                                                 {"action": "wait", "timeout": 500}]}))
    r = _nav(run, handlers, sw_session, action="goto", url=f"{good_site}/sw.html?v=2")
    assert r["success"] and r["served_by_service_worker"] is True, r


def test_clear_site_data_removes_sw_and_keeps_cookies(run, handlers, sw_session, good_site):
    run(handlers["interact_and_test"]({"session_id": sw_session, "screenshot_after": False,
                                       "steps": [{"action": "wait_for_text", "text": "registered"},
                                                 {"action": "wait", "timeout": 500},
                                                 {"action": "evaluate_js", "script": "document.cookie = 'keep=me; path=/'"}]}))
    r = _nav(run, handlers, sw_session, action="clear_site_data")
    assert r["success"], r
    assert r["service_workers_unregistered"] >= 1 and "service_workers" in r["cleared"], r
    assert "cookies" not in r["cleared"]
    # The reload clear_site_data performs is a network load (SW gone) — the
    # page then re-registers its SW, as any real PWA would.
    assert r["served_by_service_worker"] is False, r
    cookies = run(handlers["get_cookies"]({"session_id": sw_session}))
    assert any(c["name"] == "keep" for c in cookies["cookies"]), cookies


def test_hard_reload_flag(run, handlers, session):
    r = _nav(run, handlers, session, action="reload", hard=True)
    assert r["success"] and r["hard"] is True and r["action"] == "reload", r


def test_nav_generation_increments_on_goto(run, handlers, session, good_site):
    before = run(handlers["assert_condition"]({"session_id": session, "assertion": "element_exists",
                                               "selector": "body"}))
    r = _nav(run, handlers, session, action="goto", url=f"{good_site}/overlay.html")
    assert r["nav_generation"] == before["nav_generation"] + 1, (before, r)
    after = run(handlers["get_page_map"]({"session_id": session}))
    assert after["nav_generation"] == r["nav_generation"]


def test_screenshot_result_has_view(run, handlers, session):
    r = run(handlers["screenshot_session"]({"session_id": session}))
    assert r["view"]["viewport"] == {"width": 1920, "height": 1080}, r
    assert r["view"]["scroll"] == {"x": 0, "y": 0} and r["view"]["page_height"] > 0, r
    c = run(handlers["click_element"]({"session_id": session, "selector": "#btn"}))
    assert "view" in c and c["view"]["viewport"]["width"] == 1920, c
