"""0.12 bug-hunt fixes that need no browser."""
import asyncio
import json
import os

import pytest

import config
import journal
from projects import ProjectManager
from tester import redirected_to_login


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_FILE", str(tmp_path / "projects.json"))
    monkeypatch.setattr(config, "SCREENSHOT_DIR", str(tmp_path / "screenshots"))
    monkeypatch.setattr(config, "SESSIONS_DIR", str(tmp_path / "sessions"))
    os.makedirs(config.SCREENSHOT_DIR, exist_ok=True)
    return ProjectManager()


# --- C1 / I17: project names and deletion safety ---------------------------

@pytest.mark.parametrize("bad", ["..", ".", "", "client/site", "a\\b", "../x", "x" * 81, " lead", "né"])
def test_create_rejects_unsafe_names(manager, bad):
    with pytest.raises(ValueError) as e:
        manager.create(bad, "https://example.com")
    assert "name" in str(e.value).lower()


def test_create_accepts_ordinary_names(manager):
    for ok in ("shop", "client-site_2", "v1.2", "A"):
        manager.create(ok, "https://example.com")


def test_delete_never_removes_a_preexisting_custom_dir(manager, tmp_path):
    custom = tmp_path / "home"
    (custom / "Documents").mkdir(parents=True)
    (custom / "Documents" / "precious.txt").write_text("keep me")
    manager.create("Documents", "https://example.com", screenshot_dir=str(custom))
    assert manager.delete("Documents") is True
    assert (custom / "Documents" / "precious.txt").read_text() == "keep me"


def test_delete_removes_a_dir_periscope_created(manager, tmp_path):
    custom = tmp_path / "shots"
    custom.mkdir()
    manager.create("mine", "https://example.com", screenshot_dir=str(custom))
    manager.claim_screenshot_dir("mine")           # what create_project does
    (custom / "mine" / "a.png").write_bytes(b"x")
    assert manager.delete("mine") is True
    assert not (custom / "mine").exists()


def test_delete_legacy_dotdot_project_cannot_escape(manager, tmp_path):
    from projects import Project
    (tmp_path / "canary.txt").write_text("alive")
    manager.projects[".."] = Project(name="..", base_url="https://example.com")   # pre-validation store
    manager.delete("..")
    assert (tmp_path / "canary.txt").read_text() == "alive"
    assert os.path.isdir(config.SCREENSHOT_DIR)


# --- M7: a malformed store must not stop the server ------------------------

@pytest.mark.parametrize("content", [
    "[]",
    json.dumps({"a": {"base_url": "https://x"}}),
    json.dumps({"ok": {"name": "ok", "base_url": "https://x"},
                "odd": {"name": "odd", "base_url": "https://x",
                        "auth": {"method": "form", "form_login": {"login_url": "u", "username": "a",
                                                                   "password": "b", "from_the_future": 1}}}}),
])
def test_malformed_store_does_not_crash(tmp_path, monkeypatch, content):
    monkeypatch.setattr(config, "PROJECTS_FILE", str(tmp_path / "projects.json"))
    (tmp_path / "projects.json").write_text(content)
    m = ProjectManager()          # must not raise
    assert isinstance(m.projects, dict)


def test_unknown_auth_keys_are_ignored_not_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_FILE", str(tmp_path / "projects.json"))
    (tmp_path / "projects.json").write_text(json.dumps({
        "odd": {"name": "odd", "base_url": "https://x",
                "auth": {"method": "form", "form_login": {"login_url": "u", "username": "a",
                                                           "password": "b", "from_the_future": 1}}}}))
    m = ProjectManager()
    assert m.get("odd").auth.form_login.username == "a"


# --- I1: login-redirect detection -------------------------------------------

@pytest.mark.parametrize("current,login,expected", [
    ("https://x/login", "https://x/login", True),
    ("https://x/login/", "https://x/login?next=/a", True),
    ("https://x/login?next=%2Fapp", "https://x/login", True),
    ("https://x/en/login?next=/a", "https://x/login", True),           # locale prefix
    ("https://app.x/#/dashboard", "https://app.x/#/login", False),      # hash router
    ("https://app.x/#/login", "https://app.x/#/login", True),
    ("https://app.x/#/login?next=x", "https://app.x/#/login", True),
    ("https://x/index.php?page=home", "https://x/index.php?page=login", False),   # query router
    ("https://x/index.php?page=login&r=1", "https://x/index.php?page=login", True),
    ("https://other.com/login", "https://x/login", False),              # different host
    ("https://X/login", "https://x/login", True),
    ("https://x/dashboard", "https://x/login", False),
    ("https://x/blogin", "https://x/login", False),
    ("", "https://x/login", False),
    ("https://x/", "", False),
])
def test_redirected_to_login(current, login, expected):
    assert redirected_to_login(current, login) is expected


# --- I2: journal redaction ---------------------------------------------------

def _preview(tool, args, result=None):
    journal.clear()
    journal.record(tool, args, result if result is not None else {"success": True}, 1)
    return journal.entries[0]


def test_journal_masks_typed_secrets_and_userinfo():
    e = _preview("fill_form", {"session_id": "s", "fields": [
        {"selector": "#password", "value": "hunter2"}, {"selector": "#email", "value": "a@b.c"}]})
    assert "hunter2" not in e["args_preview"] and "a@b.c" in e["args_preview"]
    e = _preview("interact_and_test", {"steps": [{"action": "fill", "selector": "input[name=pwd]", "value": "s3cr3t"},
                                                 {"action": "navigate", "url": "http://bob:pw123@host/x"}]})
    assert "s3cr3t" not in e["args_preview"] and "pw123" not in e["args_preview"], e["args_preview"]
    e = _preview("set_local_storage", {"session_id": "s", "entries": {"jwt": "eyJhbGciOi", "theme": "dark"}})
    assert "eyJhbGciOi" not in e["args_preview"] and "dark" not in e["args_preview"]
    e = _preview("open_session", {"url": "https://user:topsecret@example.com/"})
    assert "topsecret" not in e["args_preview"] and "example.com" in e["args_preview"]


def test_journal_masks_secret_bearing_results():
    e = _preview("get_cookies", {"session_id": "s"},
                 {"total": 1, "cookies": [{"name": "sid", "value": "SESSIONSECRET", "domain": "x"}]})
    assert "SESSIONSECRET" not in e["result_preview"] and "sid" in e["result_preview"]
    e = _preview("get_local_storage", {"session_id": "s"}, {"entries": {"token": "abc.def", "k": "PRIVATE"}})
    assert "abc.def" not in e["result_preview"] and "PRIVATE" not in e["result_preview"]
    e = _preview("get_response_body", {"session_id": "s", "url_pattern": "/api"},
                 {"success": True, "body_text": '{"access_token":"LEAK"}'})
    assert "LEAK" not in e["result_preview"]


# --- I2: get_report confinement / M3 report prefix ---------------------------

def test_get_report_only_reads_reports_dir(tmp_path, monkeypatch):
    from handlers import HANDLERS
    reports = tmp_path / "reports"
    reports.mkdir()
    monkeypatch.setattr(config, "REPORTS_DIR", str(reports))
    secret = tmp_path / "projects.json"
    secret.write_text(json.dumps({"p": {"password": "TOPSECRET"}}))
    r = asyncio.new_event_loop().run_until_complete(HANDLERS["get_report"]({"report_path": str(secret)}))
    assert r["success"] is False and "TOPSECRET" not in json.dumps(r)
    r = asyncio.new_event_loop().run_until_complete(
        HANDLERS["get_report"]({"report_path": str(reports / ".." / "projects.json")}))
    assert r["success"] is False
    good = reports / "shop_20260101_101010.json"
    good.write_text(json.dumps({"ok": 1}))
    r = asyncio.new_event_loop().run_until_complete(HANDLERS["get_report"]({"report_path": str(good)}))
    assert r["success"] is True and r["report"] == {"ok": 1}


def test_reports_of_similarly_named_projects_do_not_mix(tmp_path, monkeypatch):
    from handlers import HANDLERS
    from handlers.static_testing import _latest_report_urls
    monkeypatch.setattr(config, "REPORTS_DIR", str(tmp_path))
    (tmp_path / "shop_staging_20260101_101010.json").write_text(json.dumps({"pages": [{"url": "s"}]}))
    assert _latest_report_urls("shop") is None
    r = asyncio.new_event_loop().run_until_complete(HANDLERS["list_reports"]({"project": "shop"}))
    assert r["count"] == 0
    (tmp_path / "shop_20260102_101010.json").write_text(json.dumps({"pages": [{"url": "u"}]}))
    assert _latest_report_urls("shop")[0] == {"u"}


# --- I4 / M1 / M2: crawler scoping helpers -----------------------------------

def test_crawler_same_domain_is_case_and_default_port_insensitive():
    from crawler import Crawler
    c = Crawler()
    assert c._is_same_domain("http://localhost:8000/a", "http://LocalHost:8000")
    assert c._is_same_domain("https://example.com:443/a", "https://EXAMPLE.com/")
    assert c._is_same_domain("http://example.com:80/a", "http://example.com")
    assert not c._is_same_domain("http://example.com:8080/a", "http://example.com")
    assert c._normalize_url("HTTP://Example.COM:80/A/?q=1#frag") == "http://example.com/A?q=1"


def test_sitemap_body_is_gunzipped():
    import gzip
    from crawler import decode_sitemap_body
    xml = b"<urlset><url><loc>http://x/a</loc></url></urlset>"
    assert decode_sitemap_body(gzip.compress(xml)) == xml
    assert decode_sitemap_body(xml) == xml


# --- M11: saved-markdown filename collisions ---------------------------------

def test_url_slugs_do_not_collide():
    from handlers.static_testing import unique_slug
    used = set()
    a = unique_slug("https://x/a/b", used)
    b = unique_slug("https://x/a_b", used)
    assert a != b and a == "a_b" and b.startswith("a_b_")


# --- schema-driven numeric coercion (no SDK-side validation any more) --------

def test_numeric_strings_are_coerced_from_the_schema():
    from coercion import coerce_args
    args = {"session_id": "s", "max_nodes": "25", "include_hidden": "true"}
    coerce_args(args, "get_page_map")
    assert args["max_nodes"] == 25 and args["include_hidden"] is True
    args = {"url_a": "a", "url_b": "b", "max_diff_percent": "0"}
    coerce_args(args, "compare_pages")
    assert args["max_diff_percent"] == 0.0
    args = {"session_id": "s", "selector": "12345", "steps": "8"}        # a selector stays a string
    coerce_args(args, "hover_element")
    assert args["selector"] == "12345" and args["steps"] == 8
    args = {"session_id": "s", "max_nodes": "lots"}                      # garbage is left for the handler
    coerce_args(args, "get_page_map")
    assert args["max_nodes"] == "lots"
