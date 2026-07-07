"""Full-page screenshot preparation for sticky/reveal pages (issue #23).

Playwright stitches full-page shots from viewport slices, which double-paints
sticky headers and captures scroll-reveal sections pre-animation. Periscope now
neutralizes stickiness, disables animations, emulates reduced motion, and scrolls
to fire reveals before capture — then restores the page. raw=true opts out.
"""
import os

import pytest


@pytest.fixture()
def sticky_session(run, handlers, good_site):
    r = run(handlers["open_session"]({"url": f"{good_site}/sticky_reveal.html"}))
    assert r["success"], r
    yield r["session_id"]
    run(handlers["close_session"]({"session_id": r["session_id"]}))


def test_fullpage_capture_is_prepared_and_reported(run, handlers, sticky_session):
    r = run(handlers["screenshot_session"]({"session_id": sticky_session, "full_page": True}))
    assert r["success"] and os.path.exists(r["screenshot_path"])
    prep = r.get("capture_prep")
    assert prep, "full-page capture should report capture_prep"
    # the page has a position:sticky header and scroll-reveal sections
    assert "sticky_neutralized" in prep, prep
    assert "reveals_forced" in prep, prep
    assert "reduced_motion" in prep and "animations_disabled" in prep, prep


def test_prep_is_restored_after_capture(run, handlers, sticky_session):
    # capture (which neutralizes the sticky header to static) …
    run(handlers["screenshot_session"]({"session_id": sticky_session, "full_page": True}))
    # … then the header's real position must be back to sticky, not left static.
    r = run(handlers["get_computed_style"]({
        "session_id": sticky_session, "selector": "#nav", "properties": ["position"]}))
    assert r["elements"][0]["position"] == "sticky", r


def test_reveal_becomes_visible_after_prep(run, handlers, sticky_session):
    # the reveal band starts opacity:0; forcing reveals should leave it visible
    run(handlers["screenshot_session"]({"session_id": sticky_session, "full_page": True}))
    r = run(handlers["get_computed_style"]({
        "session_id": sticky_session, "selector": "#band", "properties": ["opacity"]}))
    assert float(r["elements"][0]["opacity"]) == 1.0, r


def test_raw_true_skips_preparation(run, handlers, sticky_session):
    r = run(handlers["screenshot_session"]({
        "session_id": sticky_session, "full_page": True, "raw": True}))
    assert r["success"] and os.path.exists(r["screenshot_path"])
    assert "capture_prep" not in r, "raw capture must not report prep"


def test_viewport_capture_is_never_prepped(run, handlers, sticky_session):
    # viewport (full_page=false) shots capture exactly what's on screen — no prep
    r = run(handlers["screenshot_session"]({"session_id": sticky_session, "full_page": False}))
    assert r["success"] and "capture_prep" not in r
