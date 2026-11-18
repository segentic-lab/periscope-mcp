"""0.11: compare_pages — staging vs live in one call."""
import os


def test_compare_identical_pages_same(run, handlers, good_site):
    r = run(handlers["compare_pages"]({"url_a": f"{good_site}/app.html", "url_b": f"{good_site}/app.html"}))
    assert r["success"], r
    assert r["same"] is True and r["screenshot_diff"]["diff_percentage"] == 0.0, r
    assert r["facts_diff"] == {} and r["text_diff"]["similarity"] == 1.0, r
    assert r["a"]["title"] == r["b"]["title"] and r["a"]["status_code"] == 200
    assert os.path.exists(r["a"]["screenshot_path"]) and os.path.exists(r["screenshot_diff"]["diff_image_path"])
    assert "performance_delta" in r and "weight_delta_kb" in r


def test_compare_different_pages_reports_facts_and_text(run, handlers, good_site):
    r = run(handlers["compare_pages"]({"url_a": f"{good_site}/seo_good.html", "url_b": f"{good_site}/seo_bad.html"}))
    assert r["success"] and r["same"] is False, r
    fd = r["facts_diff"]
    assert fd["title"] == {"a": "A Perfectly Sized Page Title For Testing", "b": "Hi"}, fd
    assert "h1" in fd and fd["h1"]["b"] == ["One", "Two"], fd
    assert "canonical" in fd and fd["canonical"]["b"] is None, fd
    assert r["text_diff"]["similarity"] < 0.98 and r["text_diff"]["removed"], r["text_diff"]
    assert r["screenshot_diff"]["diff_percentage"] > 0  # tiny pages stay under the 1% tolerance


def test_compare_with_steps_and_checks(run, handlers, good_site):
    r = run(handlers["compare_pages"]({
        "url_a": f"{good_site}/app.html", "url_b": f"{good_site}/app.html",
        "steps": [{"action": "click", "selector": "#btn"}], "run_checks": ["seo"]}))
    assert r["success"], r
    assert r["a"]["steps_ok"] is True and r["b"]["steps_ok"] is True, r
    assert isinstance(r["a"]["issues"], list) and r["a"]["issue_count"] == r["b"]["issue_count"], r


def test_compare_one_side_fails(run, handlers, good_site):
    r = run(handlers["compare_pages"]({"url_a": f"{good_site}/app.html", "url_b": "http://127.0.0.1:1/"}))
    assert r["success"] is True and r["same"] is False, r
    assert r["a"]["title"] and "error" in r["b"], r
    assert r["screenshot_diff"] is None and r["note"], r
