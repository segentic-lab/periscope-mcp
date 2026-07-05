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


def test_update_apply_refuses_dirty_tree_and_names_files(tmp_path, monkeypatch):
    """Issue-class: never force away local modifications silently."""
    import subprocess
    from pathlib import Path
    import handlers.system as system

    repo = tmp_path / "repo"
    repo.mkdir()
    g = ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(g[:3] + ["init", "-q"], check=True)
    (repo / "tracked.py").write_text("original\n")
    subprocess.run(g + ["add", "tracked.py"], check=True)
    subprocess.run(g + ["commit", "-qm", "init"], check=True)
    (repo / "tracked.py").write_text("locally modified\n")  # dirty

    monkeypatch.setattr(system, "REPO_ROOT", Path(repo))
    r = run(system.handle_periscope_system({"action": "update", "apply": True}))
    assert not r["success"]
    assert r["modified_files"] == ["tracked.py"], r
    assert "force=true" in " ".join(r["options"])
    assert "stashed" in " ".join(r["options"])  # says changes would be stashed, not lost
