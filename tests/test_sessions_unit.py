"""SessionManager behavior that needs no browser: removal-reason reporting."""
import time

import pytest

from sessions import PageSession, SessionManager


def _make(sid: str) -> PageSession:
    now = time.time()
    return PageSession(
        session_id=sid, project_name="default", page=object(), url="u",
        created_at=now, last_accessed=now,
    )


def test_browser_restart_reason_reported():
    m = SessionManager()
    m.sessions["abc123"] = _make("abc123")
    m.clear_all("browser restarted")
    with pytest.raises(KeyError) as e:
        m.get_session("abc123")
    assert "browser crashed" in str(e.value)
    assert "login_project" in str(e.value)


def test_eviction_reason_reported():
    m = SessionManager()
    m.sessions["old111"] = _make("old111")
    m.sessions["old111"].last_accessed -= 100
    m.sessions["new222"] = _make("new222")
    m._evict_oldest()
    with pytest.raises(KeyError) as e:
        m.get_session("old111")
    assert "MAX_SESSIONS" in str(e.value)
    assert "evicted" in str(e.value)


def test_unknown_id_reason():
    m = SessionManager()
    with pytest.raises(KeyError) as e:
        m.get_session("never-existed")
    assert "unknown session id" in str(e.value)


def test_expiry_reason_reported(monkeypatch):
    import config
    m = SessionManager()
    m.sessions["idle99"] = _make("idle99")
    m.sessions["idle99"].last_accessed -= config.SESSION_TIMEOUT + 1
    with pytest.raises(KeyError) as e:
        m.get_session("idle99")
    assert "idle-expired" in str(e.value)
