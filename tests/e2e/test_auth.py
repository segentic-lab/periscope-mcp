"""Auth config honesty + copy_auth state transfer (issues #6, #7),
auth-expiry detection (issue #11), and interactive-login sessions."""
import os

import pytest


def test_saved_session_authenticates_headless(run, handlers, good_site):
    # Option B core value: a saved storage_state seeds a fresh project's
    # HEADLESS sessions as authenticated — no display needed to verify this.
    import runtime
    src, dst = "sessrc", "sesdst"
    try:
        run(handlers["create_project"]({"name": src, "base_url": f"{good_site}/app"}))
        run(handlers["create_project"]({"name": dst, "base_url": f"{good_site}/app"}))
        # authenticate src via the form-login fixture
        run(handlers["set_form_login"]({
            "project": src, "login_url": f"{good_site}/login.html",
            "username": "u", "password": "pw",
        }))
        assert run(handlers["login_project"]({"project": src}))["success"]
        # capture the authenticated storage_state and save it onto dst
        state = run(runtime.tester.contexts[src].storage_state())
        assert runtime.project_manager.set_session_state(dst, state)
        assert runtime.project_manager.get(dst).auth.method == "session"

        # dst now opens authenticated headless sessions with no login step
        s = run(handlers["open_session"]({"url": f"{good_site}/app", "project": dst}))
        assert "/app" in s["url"] and "login" not in s["url"], s
        assert s["title"] == "Protected App Area Page"
        cookies = run(handlers["get_cookies"]({"session_id": s["session_id"]}))
        assert any(c["name"] == "sid" for c in cookies["cookies"])
        run(handlers["close_session"]({"session_id": s["session_id"]}))
        # login_project on a session-method project is a no-op success
        assert run(handlers["login_project"]({"project": dst}))["success"]
    finally:
        run(handlers["delete_project"]({"name": src}))
        run(handlers["delete_project"]({"name": dst}))


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="headed browser needs a display")
def test_interactive_login_visible_then_headless_reuse(run, handlers, good_site):
    # Full option-B path incl. the VISIBLE window (runs only where DISPLAY is set)
    import runtime
    p = "interactiveproj"
    try:
        run(handlers["create_project"]({"name": p, "base_url": f"{good_site}/app"}))
        r = run(handlers["interactive_login"]({"project": p, "login_url": f"{good_site}/login.html"}))
        assert r["success"], r
        # stand in for the human logging in, on the visible page
        _, page = runtime.tester._pending_logins[p]
        run(page.fill("input[name=username]", "u"))
        run(page.fill("input[name=password]", "pw"))
        run(page.click("button[type=submit]"))
        run(page.wait_for_load_state("load"))

        r = run(handlers["save_login"]({"project": p}))
        assert r["success"] and r["cookies_saved"] >= 1, r
        # visible window/context is gone after capture
        assert p not in runtime.tester._pending_logins

        s = run(handlers["open_session"]({"url": f"{good_site}/app", "project": p}))
        assert "/app" in s["url"] and "login" not in s["url"], s
        run(handlers["close_session"]({"session_id": s["session_id"]}))
    finally:
        run(handlers["delete_project"]({"name": p}))


def test_save_login_without_pending_errors(run, handlers, good_site):
    p = "nopending"
    try:
        run(handlers["create_project"]({"name": p, "base_url": good_site}))
        r = run(handlers["save_login"]({"project": p}))
        assert r["success"] is False and "interactive_login" in r["error"]
    finally:
        run(handlers["delete_project"]({"name": p}))


def test_auth_expiry_detected_not_silently_passed(run, handlers, good_site):
    # Issue #11: after auth loss, test_project must not audit login pages and
    # call them success — preflight re-login, per-page flags, loud failure.
    p = "formproj"
    try:
        assert run(handlers["create_project"]({"name": p, "base_url": f"{good_site}/app"}))["success"]
        run(handlers["set_form_login"]({
            "project": p, "login_url": f"{good_site}/login.html",
            "username": "u", "password": "pw",
        }))
        r = run(handlers["login_project"]({"project": p}))
        assert r["success"], r

        # healthy run: preflight passes, protected pages crawled and tested
        r = run(handlers["test_project"]({"project": p, "checks": ["functionality"]}))
        assert r["auth_check"]["authenticated"] is True
        assert r["pages_tested"] == 2 and r["successful"] == 2, r
        assert "auth_lost_pages" not in r

        # simulate revocation (rotated/invalidated session cookie)
        import runtime
        run(runtime.tester.contexts[p].clear_cookies())

        # per-page detection (test_url has no preflight): flagged, not success
        r = run(handlers["test_url"]({
            "url": f"{good_site}/app", "project": p, "checks": ["functionality"],
        }))
        assert r["status"] == "auth_lost", r
        assert any("login page" in i["message"] for i in r["issues"])

        # test_project preflight auto re-login: recovers and audits for real
        run(runtime.tester.contexts[p].clear_cookies())
        r = run(handlers["test_project"]({"project": p, "checks": ["functionality"]}))
        assert r["auth_check"] == {"authenticated": True, "relogged_in": True}, r
        assert r["successful"] == 2

        # break the credentials too: preflight must fail LOUDLY
        run(handlers["set_form_login"]({
            "project": p, "login_url": f"{good_site}/login.html",
            "username": "u", "password": "wrong",
        }))
        run(runtime.tester.contexts[p].clear_cookies())
        r = run(handlers["test_project"]({"project": p, "checks": ["functionality"]}))
        assert r["success"] is False and "login_project" in r["error"], r
        assert r["auth_check"]["authenticated"] is False

        # and open_session warns when it lands on the login page
        s = run(handlers["open_session"]({"url": f"{good_site}/app", "project": p}))
        assert "login page" in s.get("warning", ""), s
        run(handlers["close_session"]({"session_id": s["session_id"]}))
    finally:
        run(handlers["delete_project"]({"name": p}))


def test_cookie_auth_flow_and_copy_auth_state_transfer(run, handlers, good_site):
    src, dst = "authsrc", "authdst"
    try:
        assert run(handlers["create_project"]({"name": src, "base_url": good_site}))["success"]
        assert run(handlers["create_project"]({"name": dst, "base_url": good_site}))["success"]

        # set_basic_auth first, then replace with cookies: must warn (issue #6)
        r = run(handlers["set_basic_auth"]({"project": src, "username": "u", "password": "p"}))
        assert r["success"] and "login_project" in r["message"]
        r = run(handlers["set_cookies"]({
            "project": src,
            "cookies": [{"name": "tok", "value": "abc123", "domain": "127.0.0.1"}],
        }))
        assert r["success"]
        # message must not claim the cookies are live (issue #6)
        assert "login_project" in r["message"]
        assert r["replaced_auth_method"] == "basic"

        # cookies are inert until login_project injects them
        r = run(handlers["login_project"]({"project": src}))
        assert r["success"], r

        s = run(handlers["open_session"]({"url": f"{good_site}/app.html", "project": src}))
        sid = s["session_id"]
        cookies = run(handlers["get_cookies"]({"session_id": sid}))
        assert any(c["name"] == "tok" for c in cookies["cookies"])
        # put a token in localStorage — the part cookie-only copies lose (issue #7)
        run(handlers["set_local_storage"]({
            "session_id": sid, "entries": {"auth_token": "xyz789"},
        }))
        run(handlers["close_session"]({"session_id": sid}))

        # copy to a project with no live context yet -> full storage_state transfer
        r = run(handlers["copy_auth"]({"from_project": src, "to_project": dst}))
        assert r["success"]
        assert r["session_copied"] is True, r
        assert "localStorage" in r["copied"], r

        s2 = run(handlers["open_session"]({"url": f"{good_site}/app.html", "project": dst}))
        sid2 = s2["session_id"]
        cookies = run(handlers["get_cookies"]({"session_id": sid2}))
        assert any(c["name"] == "tok" for c in cookies["cookies"]), "cookie not transferred"
        stored = run(handlers["get_local_storage"]({"session_id": sid2, "keys": ["auth_token"]}))
        assert stored["entries"]["auth_token"] == "xyz789", "localStorage not transferred"
        run(handlers["close_session"]({"session_id": sid2}))

        # copying again now that the target context exists -> honest partial
        r = run(handlers["copy_auth"]({"from_project": src, "to_project": dst}))
        assert r["session_copied"] is False
        assert r["copied"] == ["cookies"]
        assert "login_project" in r.get("note", "") or "login_project" in r["message"]
    finally:
        run(handlers["delete_project"]({"name": src}))
        run(handlers["delete_project"]({"name": dst}))
