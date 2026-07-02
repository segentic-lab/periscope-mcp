"""Auth config honesty + copy_auth state transfer (issues #6, #7)."""


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
