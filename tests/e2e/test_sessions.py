"""Session lifecycle against the real browser."""
import pytest


def test_open_screenshot_navigate_close(run, handlers, good_site):
    r = run(handlers["open_session"]({"url": f"{good_site}/app.html"}))
    assert r["success"] and r["title"] == "Periscope E2E Application Fixture"
    sid = r["session_id"]

    shot = run(handlers["screenshot_session"]({"session_id": sid}))
    assert shot["success"] and shot["screenshot_path"].endswith(".png")

    # navigate away, then back/forward/reload through the merged tool
    run(handlers["interact_and_test"]({
        "session_id": sid,
        "steps": [{"action": "navigate", "url": f"{good_site}/kbd.html"}],
        "screenshot_after": False,
    }))
    r = run(handlers["navigate_session"]({"session_id": sid, "action": "back"}))
    assert r["success"] and "app.html" in r["url"]
    r = run(handlers["navigate_session"]({"session_id": sid, "action": "forward"}))
    assert r["success"] and "kbd.html" in r["url"]
    r = run(handlers["navigate_session"]({"session_id": sid, "action": "reload"}))
    assert r["success"] and "kbd.html" in r["url"]
    r = run(handlers["navigate_session"]({"session_id": sid, "action": "sideways"}))
    assert r["success"] is False and "Unknown action" in r["error"]

    assert run(handlers["close_session"]({"session_id": sid}))["success"]


def test_failed_open_does_not_leak_session(run, handlers):
    from runtime import session_manager
    before = len(session_manager.sessions)
    with pytest.raises(Exception):
        run(handlers["open_session"]({"url": "http://127.0.0.1:1/nope"}))
    assert len(session_manager.sessions) == before


def test_expired_session_id_gives_clear_error(run, handlers):
    with pytest.raises(KeyError, match="not found or expired"):
        run(handlers["screenshot_session"]({"session_id": "deadbeef0000"}))
