"""0.11: check_pwa — manifest validation, service-worker state, installability."""


def test_check_pwa_fixture_passes(run, handlers, good_site):
    r = run(handlers["check_pwa"]({"url": f"{good_site}/pwa.html"}))
    assert r["success"], r
    m = r["manifest"]
    assert m["found"] is True and m["url"].endswith("/manifest.webmanifest"), m
    assert m["name"] == "Periscope PWA Fixture" and m["display"] == "standalone", m
    assert len(m["icons"]) == 2 and m["problems"] == [], m
    sw = r["service_worker"]
    assert sw["registered"] is True and sw["scope"].endswith("/"), sw
    assert r["installability"]["source"] in ("cdp", "unavailable"), r["installability"]
    assert r["before_install_prompt_fired"] in (True, False), r
    assert r["issues"] == [] or all(i["type"] == "pwa" for i in r["issues"]), r["issues"]


def test_check_pwa_plain_page(run, handlers, good_site):
    r = run(handlers["check_pwa"]({"url": f"{good_site}/app.html"}))
    assert r["success"], r
    assert r["manifest"]["found"] is False and r["service_worker"]["registered"] is False, r
    msgs = [i["message"] for i in r["issues"]]
    assert any("manifest" in m.lower() for m in msgs), msgs
    assert all(i["type"] == "pwa" for i in r["issues"])


def test_check_pwa_on_session(run, handlers, good_site):
    s = run(handlers["open_session"]({"url": f"{good_site}/pwa.html"}))
    assert s["success"], s
    try:
        run(handlers["interact_and_test"]({"session_id": s["session_id"], "screenshot_after": False,
                                           "steps": [{"action": "wait_for_text", "text": "registered"}]}))
        r = run(handlers["check_pwa"]({"session_id": s["session_id"]}))
        assert r["success"] and r["manifest"]["found"] and r["service_worker"]["registered"], r
        assert r["before_install_prompt_fired"] is None  # only observable in url mode
    finally:
        run(handlers["close_session"]({"session_id": s["session_id"]}))


def test_check_pwa_flags_bad_manifest(run, handlers, bad_site):
    # the "bad" origin serves the same files; use a manifest-less page with an
    # inline bad manifest via data: URL is not possible, so validate problems
    # through the pure validator on the handler module instead.
    from handlers.pwa import validate_manifest
    problems = validate_manifest({"name": "", "start_url": "/outside", "scope": "/app/",
                                  "display": "browser", "icons": [{"src": "a.png", "sizes": "96x96"}]},
                                 manifest_url=f"{bad_site}/manifest.webmanifest")
    joined = " | ".join(problems)
    assert "name" in joined and "192" in joined and "512" in joined, joined
    assert "display" in joined and "scope" in joined and "theme_color" in joined, joined
