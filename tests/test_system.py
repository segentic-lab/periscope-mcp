"""periscope_system: status, agents_md, and update dry-run (no browser needed)."""
import asyncio

from _version import __version__
from handlers import HANDLERS


def run(coro):
    return asyncio.run(coro)


def test_status_reports_running_version_and_capabilities():
    r = run(HANDLERS["periscope_system"]({"action": "status"}))
    assert r["success"]
    assert r["version_running"] == __version__
    assert r["version_on_disk"] == __version__  # no pending update in a test checkout
    assert r["install_type"] == "git"
    assert r["commit"]
    assert set(r["capabilities"]) == {"node_for_lighthouse", "display_for_headed", "chromium"}
    assert isinstance(r["sessions_active"], int)
    assert "update" in r  # present even when the network check fails


def test_status_is_default_action():
    r = run(HANDLERS["periscope_system"]({}))
    assert r["success"] and r["version_running"] == __version__


def test_agents_md_returns_current_guide():
    r = run(HANDLERS["periscope_system"]({"action": "agents_md"}))
    assert r["success"]
    assert "Periscope" in r["content"]
    assert "periscope_system" in r["content"]  # the guide documents this tool
    assert "CURRENT" in r["note"]


def test_update_defaults_to_dry_run():
    r = run(HANDLERS["periscope_system"]({"action": "update"}))
    assert r["success"]
    assert r["mode"] == "dry_run"
    # offline CI is fine — the check reports it instead of failing
    assert r.get("checked") in (True, False)
    assert "apply=true" in r["note"]


def test_unknown_action_is_actionable():
    r = run(HANDLERS["periscope_system"]({"action": "restart"}))
    assert not r["success"]
    assert "status" in r["error"] and "agents_md" in r["error"]
