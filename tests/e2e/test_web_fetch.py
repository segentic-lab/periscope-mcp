"""Featured web_fetch: readable markdown, conditional contains, save, and the
JS-render path (headless Chromium runs JS before extraction)."""
import os

import pytest


def test_markdown_is_readable_and_strips_boilerplate(run, handlers, good_site):
    r = run(handlers["web_fetch"]({"url": f"{good_site}/article.html", "format": "markdown"}))
    assert r.get("extraction") == "trafilatura", r
    c = r["content"]
    # structure preserved …
    assert "# Understanding the Cascade" in c or "Understanding the Cascade" in c
    assert "## Specificity" in c
    assert "[MDN specificity guide]" in c  # link kept as markdown
    assert "color: blue" in c              # code block kept
    # … boilerplate dropped
    assert "Cookie preferences" not in c
    assert "Sign up" not in c


def test_contains_gates_the_content(run, handlers, good_site):
    hit = run(handlers["web_fetch"]({
        "url": f"{good_site}/article.html", "contains": ["specificity", "cascade"], "contains_mode": "all"}))
    assert hit["matched"] is True and "content" in hit
    miss = run(handlers["web_fetch"]({
        "url": f"{good_site}/article.html", "contains": "nonexistent-term-zzz"}))
    assert miss["matched"] is False
    assert miss.get("content_omitted") is True and "content" not in miss  # token-saving


def test_contains_matches_boilerplate_even_in_reading_mode(run, handlers, good_site):
    # "Cookie preferences" lives in the footer, which readable markdown strips.
    # The conditional match must still find it (matches full page text), while
    # the returned content stays clean (footer omitted).
    r = run(handlers["web_fetch"]({
        "url": f"{good_site}/article.html", "format": "markdown",
        "contains": "Cookie preferences"}))
    assert r["matched"] is True and r.get("match_scope") == "full_text", r
    assert "Cookie preferences" not in r["content"]  # output still readable


def test_save_writes_full_artifact(run, handlers, good_site, tmp_path):
    dest = str(tmp_path / "cascade.md")
    r = run(handlers["web_fetch"]({
        "url": f"{good_site}/article.html", "format": "markdown", "save_path": dest}))
    assert r["saved_path"] == dest and os.path.exists(dest)
    saved = open(dest, encoding="utf-8").read()
    assert "Understanding the Cascade" in saved


def test_static_fetch_misses_js_content(run, handlers, good_site):
    # static (no render): the JS-injected token is absent from the served HTML
    r = run(handlers["web_fetch"]({
        "url": f"{good_site}/js_content.html", "readable": False}))
    assert r["rendered"] is False
    assert "sentinel-xyzzy" not in r["content"]


def test_render_true_runs_js_then_extracts(run, handlers, good_site):
    # render=true loads it in headless Chromium, so the JS-injected content appears
    r = run(handlers["web_fetch"]({
        "url": f"{good_site}/js_content.html", "render": True, "readable": False}))
    assert r["rendered"] is True
    assert "sentinel-xyzzy" in r["content"]
    assert "Rendered Heading" in r["content"]


def test_html_format_returns_raw(run, handlers, good_site):
    r = run(handlers["web_fetch"]({"url": f"{good_site}/article.html", "format": "html"}))
    assert r["extraction"] == "raw-html"
    assert "<article>" in r["content"]
