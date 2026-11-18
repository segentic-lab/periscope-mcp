"""0.12 bug-hunt fixes that need a real browser."""
import pytest


@pytest.fixture()
def hunt(run, handlers, good_site):
    r = run(handlers["open_session"]({"url": f"{good_site}/hunt.html"}))
    assert r["success"], r
    yield r["session_id"]
    run(handlers["close_session"]({"session_id": r["session_id"]}))


def _js(run, handlers, sid, script):
    r = run(handlers["interact_and_test"]({"session_id": sid, "screenshot_after": False,
                                           "steps": [{"action": "evaluate_js", "script": script}]}))
    assert r["success"], r
    return r["steps"][0]["result"]


def _project(run, handlers, name, base_url):
    assert run(handlers["create_project"]({"name": name, "base_url": base_url}))["success"]


# --- C2: a login URL that bounces to another login path is NOT "already authenticated"

def test_login_redirecting_to_another_login_path_really_logs_in(run, handlers, good_site):
    p = "ssoproj"
    try:
        _project(run, handlers, p, f"{good_site}/app")
        run(handlers["set_form_login"]({"project": p, "login_url": f"{good_site}/sso-login",
                                        "username": "u", "password": "pw"}))
        r = run(handlers["login_project"]({"project": p}))
        assert r["success"] and not r.get("already_authenticated"), r
        s = run(handlers["open_session"]({"url": f"{good_site}/app", "project": p}))
        try:
            assert s["url"].endswith("/app"), s
        finally:
            run(handlers["close_session"]({"session_id": s["session_id"]}))
        again = run(handlers["login_project"]({"project": p}))
        assert again["success"] and again.get("already_authenticated") is True, again
    finally:
        run(handlers["delete_project"]({"name": p}))


def test_wrong_password_on_bounced_login_is_a_failure(run, handlers, good_site):
    p = "ssobad"
    try:
        _project(run, handlers, p, f"{good_site}/app")
        run(handlers["set_form_login"]({"project": p, "login_url": f"{good_site}/sso-login",
                                        "username": "u", "password": "WRONG"}))
        r = run(handlers["login_project"]({"project": p}))
        assert r["success"] is False, r
    finally:
        run(handlers["delete_project"]({"name": p}))


# --- I4 / M1: crawl scope follows the real host; redirects are not double-counted

def test_crawl_follows_canonical_host_after_redirect(run, handlers, good_site):
    port = good_site.rsplit(":", 1)[1]
    p = "hostproj"
    try:
        _project(run, handlers, p, f"http://localhost:{port}/redir-host")
        r = run(handlers["crawl_project"]({"project": p, "max_pages": 10, "max_depth": 1, "use_sitemap": False}))
        assert r["pages_found"] >= 3, r
        assert r["crawl_scope"].startswith("127.0.0.1"), r
    finally:
        run(handlers["delete_project"]({"name": p}))


def test_crawl_base_url_host_case_insensitive_and_redirects_deduped(run, handlers, good_site):
    port = good_site.rsplit(":", 1)[1]
    p = "caseproj"
    try:
        _project(run, handlers, p, f"http://LOCALHOST:{port}/hub.html")
        r = run(handlers["crawl_project"]({"project": p, "max_pages": 10, "max_depth": 1, "use_sitemap": False}))
        urls = r["urls"]
        assert r["pages_found"] >= 3, r
        assert not any(u.endswith("/old-page") for u in urls), urls
        assert sum(1 for u in urls if u.endswith("/article.html")) == 1, urls
    finally:
        run(handlers["delete_project"]({"name": p}))


def test_basic_auth_host_case_insensitive(run, handlers, good_site):
    port = good_site.rsplit(":", 1)[1]
    p = "basiccase"
    try:
        _project(run, handlers, p, f"http://LOCALHOST:{port}/basic")
        run(handlers["set_basic_auth"]({"project": p, "username": "u", "password": "p"}))
        assert run(handlers["login_project"]({"project": p}))["success"]
        r = run(handlers["test_url"]({"url": f"http://localhost:{port}/basic", "project": p, "checks": ["seo"]}))
        assert r["status"] == "success" and r["title"] == "Basic OK", r
    finally:
        run(handlers["delete_project"]({"name": p}))


# --- I5: copy_auth of a saved-session project

def test_copy_auth_copies_saved_session_and_login_fails_without_one(run, handlers, good_site):
    import runtime
    src, dst, empty = "sesssrc", "sessdst", "sessempty"
    try:
        for n in (src, dst, empty):
            _project(run, handlers, n, f"{good_site}/app")
        runtime.project_manager.set_session_state(src, {"cookies": [
            {"name": "sid", "value": "ok", "domain": "127.0.0.1", "path": "/"}], "origins": []})
        runtime.project_manager.reset_login_flags()          # as after a server restart
        r = run(handlers["copy_auth"]({"from_project": src, "to_project": dst}))
        assert r["success"] and r["session_copied"] is True, r
        s = run(handlers["open_session"]({"url": f"{good_site}/app", "project": dst}))
        try:
            assert s["url"].endswith("/app"), s
        finally:
            run(handlers["close_session"]({"session_id": s["session_id"]}))
        # a "session" project with no saved state cannot claim a successful login
        runtime.project_manager.get(empty).auth = runtime.project_manager.get(src).auth
        bad = run(handlers["login_project"]({"project": empty}))
        assert bad["success"] is False and "interactive_login" in bad["error"], bad
    finally:
        for n in (src, dst, empty):
            run(handlers["delete_project"]({"name": n}))


# --- I6: record_session honours project auth

def test_record_session_uses_basic_auth_and_saved_session(run, handlers, good_site):
    import runtime
    b, s = "recbasic", "recsess"
    try:
        _project(run, handlers, b, f"{good_site}/basic")
        run(handlers["set_basic_auth"]({"project": b, "username": "u", "password": "p"}))
        assert run(handlers["login_project"]({"project": b}))["success"]
        r = run(handlers["record_session"]({"url": f"{good_site}/basic", "project": b,
                                            "steps": [{"action": "evaluate_js", "script": "document.title"}]}))
        assert r.get("success") and r["steps"][0]["result"] == "Basic OK", r

        _project(run, handlers, s, f"{good_site}/app")
        runtime.project_manager.set_session_state(s, {"cookies": [
            {"name": "sid", "value": "ok", "domain": "127.0.0.1", "path": "/"}], "origins": []})
        r = run(handlers["record_session"]({"url": f"{good_site}/whoami", "project": s,
                                            "steps": [{"action": "evaluate_js",
                                                       "script": "document.getElementById('c').textContent"}]}))
        assert "sid=ok" in r["steps"][0]["result"], r
    finally:
        run(handlers["delete_project"]({"name": b}))
        run(handlers["delete_project"]({"name": s}))


# --- I7: an observation must not move the page

def test_default_screenshot_keeps_scroll_position(run, handlers, good_site):
    s = run(handlers["open_session"]({"url": f"{good_site}/long.html"}))
    sid = s["session_id"]
    try:
        _js(run, handlers, sid, "window.scrollTo(0, 5000)")
        run(handlers["screenshot_session"]({"session_id": sid}))
        assert _js(run, handlers, sid, "Math.round(window.scrollY)") == 5000
        r = run(handlers["scroll_into_view"]({"session_id": sid, "selector": "section:nth-of-type(9)"}))
        assert r["success"] and _js(run, handlers, sid, "Math.round(window.scrollY)") > 6000
    finally:
        run(handlers["close_session"]({"session_id": sid}))


# --- I8 / M8: select failures are failures

def test_select_option_step_failure_fails_the_step(run, handlers, hunt):
    r = run(handlers["interact_and_test"]({"session_id": hunt, "screenshot_after": False,
                                           "steps": [{"action": "select_option", "selector": "#sel", "label": "Nope"}]}))
    assert r["success"] is False and r["steps"][0]["success"] is False, r
    r = run(handlers["interact_and_test"]({"session_id": hunt, "screenshot_after": False,
                                           "steps": [{"action": "select_option", "selector": "#missing", "label": "A"}]}))
    assert r["success"] is False, r
    ok = run(handlers["interact_and_test"]({"session_id": hunt, "screenshot_after": False,
                                            "steps": [{"action": "select_option", "selector": "#sel", "label": "B"}]}))
    assert ok["success"] is True, ok


def test_custom_dropdown_without_criteria_is_an_error(run, handlers, hunt):
    r = run(handlers["select_option"]({"session_id": hunt, "selector": "#combo", "observe": "none"}))
    assert r["success"] is False and "value, label, or index" in r["error"], r
    assert _js(run, handlers, hunt, "document.getElementById('picked').textContent") == "none"


# --- I9: advertised selectors resolve to exactly the advertised element

def test_page_map_and_find_element_selectors_are_unique(run, handlers, hunt):
    m = run(handlers["get_page_map"]({"session_id": hunt}))
    for name in ("x2", "y2"):
        sel = next(n["selector"] for n in m["nodes"] if n.get("name") == name)
        got = _js(run, handlers, hunt,
                  f"Array.from(document.querySelectorAll({sel!r})).map(e => e.textContent)")
        assert got == [name], (sel, got)
    f = run(handlers["find_element"]({"session_id": hunt, "text": "y2"}))
    sel = f["elements"][0]["selector"]
    assert _js(run, handlers, hunt, f"document.querySelector({sel!r}).textContent") == "y2"


# --- I10: a method-filtered mock must not bypass the other mocks

def test_intercepts_with_method_filters_compose(run, handlers, session):
    run(handlers["intercept_network"]({"session_id": session, "url_pattern": "/api/items",
                                       "method": "GET", "status": 500, "body": "GETMOCK"}))
    run(handlers["intercept_network"]({"session_id": session, "url_pattern": "/api/items",
                                       "method": "POST", "status": 400, "body": "POSTMOCK"}))
    got = _js(run, handlers, session, """Promise.all([
        fetch('/api/items').then(async r => [r.status, await r.text()]),
        fetch('/api/items', {method: 'POST'}).then(async r => [r.status, await r.text()])])""")
    assert got == [[500, "GETMOCK"], [400, "POSTMOCK"]], got


# --- I11: checks on an iframe session

def test_checks_work_on_iframe_sessions(run, handlers, good_site):
    s = run(handlers["open_session"]({"url": f"{good_site}/frames.html"}))
    try:
        f = run(handlers["select_iframe"]({"session_id": s["session_id"], "selector": "#inner"}))
        fid = f["iframe_session_id"]
        links = run(handlers["check_links"]({"session_id": fid}))
        assert not any(str(x["status"]).startswith("error") for x in links["internal"]["results"]), links
        kb = run(handlers["test_keyboard_navigation"]({"session_id": fid, "max_tabs": 3}))
        assert "focus_order" in kb, kb
        chk = run(handlers["run_checks_on_session"]({"session_id": fid, "checks": ["functionality", "visual"]}))
        assert not any("unreachable" in str(i.get("details")) for i in chk["issues"]), chk["issues"]
    finally:
        run(handlers["close_session"]({"session_id": s["session_id"]}))


# --- I12: modern colour syntaxes are measured, not skipped

def test_color_contrast_handles_oklch_and_color_mix(run, handlers, hunt):
    r = run(handlers["check_color_contrast"]({"session_id": hunt, "selector": "#c1, #c2, #c3"}))
    assert r["checked"] == 3 and r["unparsed_count"] == 0, r
    failing = {f["text"][:10] for f in r["failures"]}
    assert r["fail_count"] == 2 and "dark oklch" not in failing, r


# --- I13: accessibility false positives

def test_named_anchors_and_aria_labelled_children_are_not_errors(run, handlers, hunt):
    r = run(handlers["run_checks_on_session"]({"session_id": hunt, "checks": ["accessibility"]}))
    msgs = [i["message"] for i in r["issues"]]
    assert not any("links without accessible text" in m for m in msgs), msgs
    assert not any("buttons without accessible names" in m for m in msgs), msgs


# --- I14: an explicit 0 tolerance is honoured

def test_visual_check_zero_tolerance(run, handlers, hunt):
    run(handlers["visual_check"]({"session_id": hunt, "name": "strict", "action": "set", "selector": "#top-h"}))
    _js(run, handlers, hunt, "document.getElementById('top-h').textContent = 'Hunt fixturE'")
    r = run(handlers["visual_check"]({"session_id": hunt, "name": "strict", "action": "check",
                                      "selector": "#top-h", "max_diff_percent": 0}))
    assert r["max_diff_percent"] == 0 and r["diff_percentage"] > 0 and r["passed"] is False, r


# --- I15: reload on a never-idle page downgrades instead of timing out

def test_reload_and_set_viewport_reload_on_busy_page(run, handlers, good_site):
    import time
    s = run(handlers["open_session"]({"url": f"{good_site}/busy.html"}))
    sid = s["session_id"]
    try:
        t0 = time.time()
        r = run(handlers["navigate_session"]({"session_id": sid, "action": "reload", "observe": "none"}))
        assert r["success"] and r.get("wait_downgraded"), r
        v = run(handlers["set_viewport"]({"session_id": sid, "device": "mobile", "reload": True, "observe": "none"}))
        assert v["success"], v
        assert time.time() - t0 < 25
    finally:
        run(handlers["close_session"]({"session_id": sid}))


# --- I16: page_state restore must not wipe other sites' cookies in the shared context

def test_page_state_restore_keeps_other_origin_cookies(run, handlers, good_site, bad_site):
    import runtime
    p = "stateproj"
    try:
        _project(run, handlers, p, good_site)
        a = run(handlers["open_session"]({"url": f"{good_site}/app.html", "project": p}))
        try:
            run(handlers["page_state"]({"session_id": a["session_id"], "action": "snapshot", "name": "s0"}))
            ctx = runtime.tester.contexts[p]
            other_host = bad_site.split("//")[1].split(":")[0]
            run(ctx.add_cookies([{"name": "other", "value": "KEEP", "url": "http://example.org/"},
                                 {"name": "mine", "value": "DROP", "url": f"{good_site}/"}]))
            r = run(handlers["page_state"]({"session_id": a["session_id"], "action": "restore", "name": "s0"}))
            assert r["success"], r
            names = {c["name"] for c in run(ctx.cookies(["http://example.org/", f"{good_site}/"]))}
            assert "other" in names and "mine" not in names, names
        finally:
            run(handlers["close_session"]({"session_id": a["session_id"]}))
    finally:
        run(handlers["delete_project"]({"name": p}))


# --- I18: popups die with their opener session

def test_closing_a_session_closes_its_popups(run, handlers, good_site):
    import runtime
    p = "popproj"
    try:
        _project(run, handlers, p, good_site)
        run(handlers["test_url"]({"url": f"{good_site}/app.html", "project": p, "checks": ["seo"]}))
        ctx = runtime.tester.contexts[p]
        before = len(ctx.pages)
        for _ in range(2):
            s = run(handlers["open_session"]({"url": f"{good_site}/popup.html", "project": p}))
            run(handlers["click_element"]({"session_id": s["session_id"], "selector": "#open", "observe": "none"}))
            run(handlers["select_page"]({"session_id": s["session_id"]}))
            run(handlers["close_session"]({"session_id": s["session_id"]}))
        assert len(ctx.pages) == before, [pg.url for pg in ctx.pages]
    finally:
        run(handlers["delete_project"]({"name": p}))


# --- M4 / M5 / M6

def test_table_with_repeated_and_empty_headers_keeps_every_cell(run, handlers, hunt):
    r = run(handlers["get_table_data"]({"session_id": hunt, "selector": "#t"}))
    row = r["rows"][0]
    assert sorted(row.values()) == ["Ann", "Delete", "Edit", "Second"], row
    assert len(set(r["headers"])) == 4, r["headers"]


def test_text_assertions_require_expected(run, handlers, hunt):
    for a in ("text_contains", "text_equals", "url_contains", "title_contains"):
        r = run(handlers["assert_condition"]({"session_id": hunt, "assertion": a, "selector": "body"}))
        assert r.get("success") is False and "expected" in r["error"], (a, r)
    all_ = run(handlers["assert_all"]({"session_id": hunt, "assertions": [{"assertion": "text_contains"}]}))
    assert all_["passed"] is False


def test_unknown_project_is_an_error_not_an_anonymous_context(run, handlers, good_site):
    r = run(handlers["test_url"]({"url": f"{good_site}/app.html", "project": "sm-typo", "checks": ["seo"]}))
    assert r.get("status") == "error" and "not found" in r["error"], r
    r = run(handlers["open_session"]({"url": f"{good_site}/app.html", "project": "sm-typo"}))
    assert r["success"] is False and "sm-typo" in r["error"] and "create_project" in r["error"], r
