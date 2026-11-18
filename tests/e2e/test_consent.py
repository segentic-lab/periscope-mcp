"""0.11: consent helper — vendor table, generic multilingual fallback,
no-banner success, open_session(consent=) and the 'consent' step."""
import pytest


def _open(run, handlers, url, **kw):
    r = run(handlers["open_session"]({"url": url, **kw}))
    assert r["success"], r
    return r


def _state(run, handlers, sid):
    r = run(handlers["interact_and_test"]({
        "session_id": sid, "screenshot_after": False,
        "steps": [{"action": "evaluate_js",
                   "script": "document.getElementById('consent-state').textContent"}]}))
    return r["steps"][0]["result"]


def test_consent_accept_complianz(run, handlers, good_site):
    s = _open(run, handlers, f"{good_site}/consent.html")
    try:
        r = run(handlers["handle_consent"]({"session_id": s["session_id"], "action": "accept"}))
        assert r["success"] and r["found"] is True and r["cmp"] == "complianz", r
        assert r["banner_gone"] is True and r["clicked"], r
        assert _state(run, handlers, s["session_id"]) == "accepted"
    finally:
        run(handlers["close_session"]({"session_id": s["session_id"]}))


def test_consent_deny_generic_slovenian(run, handlers, good_site):
    s = _open(run, handlers, f"{good_site}/consent.html?cmp=generic")
    try:
        r = run(handlers["handle_consent"]({"session_id": s["session_id"], "action": "deny"}))
        assert r["success"] and r["found"] is True and r["cmp"] == "generic", r
        assert _state(run, handlers, s["session_id"]) == "denied"
    finally:
        run(handlers["close_session"]({"session_id": s["session_id"]}))


def test_consent_no_banner_is_success_not_found(run, handlers, session):
    r = run(handlers["handle_consent"]({"session_id": session, "action": "accept"}))
    assert r["success"] is True and r["found"] is False and r["cmp"] is None, r


def test_open_session_consent_param(run, handlers, good_site):
    s = _open(run, handlers, f"{good_site}/consent.html", consent="deny")
    try:
        assert s["consent"]["found"] is True and s["consent"]["action"] == "deny", s
        assert _state(run, handlers, s["session_id"]) == "denied"
    finally:
        run(handlers["close_session"]({"session_id": s["session_id"]}))


def test_consent_step_in_interact_and_test(run, handlers, good_site):
    s = _open(run, handlers, f"{good_site}/consent.html")
    try:
        r = run(handlers["interact_and_test"]({
            "session_id": s["session_id"], "screenshot_after": False,
            "steps": [{"action": "consent", "value": "accept"}]}))
        assert r["success"] and r["steps"][0]["cmp"] == "complianz", r
        assert _state(run, handlers, s["session_id"]) == "accepted"
    finally:
        run(handlers["close_session"]({"session_id": s["session_id"]}))


def test_open_session_consent_failure_keeps_session(run, handlers, good_site, monkeypatch):
    import consent

    async def boom(page, action):
        raise RuntimeError("cmp exploded")
    monkeypatch.setattr(consent, "apply", boom)
    s = run(handlers["open_session"]({"url": f"{good_site}/consent.html", "consent": "accept"}))
    assert s["success"] and s["session_id"], s
    try:
        assert s["consent"]["success"] is False and "cmp exploded" in s["consent"]["error"], s
    finally:
        run(handlers["close_session"]({"session_id": s["session_id"]}))
