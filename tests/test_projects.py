"""ProjectManager CRUD + persistence round-trip against a temp store."""
import json
import os

import pytest

import config
import projects as projects_mod
from projects import Project, ProjectManager


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_FILE", str(tmp_path / "projects.json"))
    monkeypatch.setattr(config, "SCREENSHOT_DIR", str(tmp_path / "screenshots"))
    monkeypatch.setattr(config, "SESSIONS_DIR", str(tmp_path / "sessions"))
    return ProjectManager()


def test_session_state_roundtrip_and_delete(manager, tmp_path):
    import os
    manager.create("s1", "https://example.com")
    state = {"cookies": [{"name": "sid", "value": "abc"}], "origins": []}
    assert manager.set_session_state("s1", state) is True
    # persisted owner-only, marks the project session-authed
    path = manager._session_path("s1")
    assert os.path.exists(path)
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    assert manager.get("s1").auth.method == "session"
    assert manager.get("s1").is_logged_in is True
    assert manager.load_session_state("s1") == state
    # unknown project / missing file
    assert manager.set_session_state("nope", state) is False
    assert manager.load_session_state("nope") is None
    # delete removes the session file too
    manager.delete("s1")
    assert not os.path.exists(path)


def test_create_adds_scheme_and_strips_slash(manager):
    p = manager.create("demo", "example.com/")
    assert p.base_url == "https://example.com"


def test_create_duplicate_raises(manager):
    manager.create("demo", "https://example.com")
    with pytest.raises(ValueError):
        manager.create("demo", "https://example.com")


def test_persistence_round_trip(manager):
    manager.create("demo", "https://example.com", screenshot_dir="/tmp/shots")
    manager.set_form_login("demo", "https://example.com/login", "user", "pass")

    reloaded = ProjectManager()
    p = reloaded.get("demo")
    assert p is not None
    assert p.screenshot_dir == "/tmp/shots"
    assert p.auth.method == "form"
    assert p.auth.form_login.username == "user"


def test_delete_removes_custom_screenshot_dir(manager, tmp_path):
    custom = tmp_path / "custom"
    (custom / "demo").mkdir(parents=True)
    manager.create("demo", "https://example.com", screenshot_dir=str(custom))
    assert manager.delete("demo") is True
    assert not (custom / "demo").exists()
    assert manager.get("demo") is None


def test_delete_missing_returns_false(manager):
    assert manager.delete("nope") is False


def test_auth_not_serialized_when_absent(manager):
    manager.create("demo", "https://example.com")
    data = Project.from_dict(manager.get("demo").to_dict())
    assert data.auth is None
