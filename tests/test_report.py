"""Journal capture (redaction, dispatch hook) and session_report rendering."""
import asyncio
import json
import os

import journal
import server
from handlers import HANDLERS


def run(coro):
    return asyncio.run(coro)


def setup_function(_):
    journal.clear()


def test_dispatch_records_and_redacts_secrets():
    r = run(server.call_tool("set_form_login", {
        "project": "nope-missing", "login_url": "http://x/login",
        "username": "u@example.com", "password": "SuperSecret123",
    }))
    assert len(journal.entries) == 1
    e = journal.entries[0]
    assert e["tool"] == "set_form_login"
    assert "SuperSecret123" not in e["args_preview"]
    assert "•••" in e["args_preview"]
    assert "u@example.com" in e["args_preview"]  # non-secrets stay readable
    # response payload itself is unaffected by journaling
    assert "SuperSecret123" not in json.dumps(journal.entries)
    assert isinstance(json.loads(r[0].text), dict)


def test_failed_calls_are_recorded_as_failures():
    run(server.call_tool("get_project", {"name": "definitely-missing"}))
    run(server.call_tool("no_such_tool", {}))
    assert len(journal.entries) == 2
    assert all(not e["success"] for e in journal.entries)
    assert journal.entries[1]["error"].startswith("Unknown tool")


def test_report_renders_calls_notes_and_failures():
    run(server.call_tool("list_projects", {}))
    run(server.call_tool("get_project", {"name": "missing"}))
    r = run(HANDLERS["session_report"]({
        "pdf": False, "notes": "Two findings: A and B.", "title": "Unit run"}))
    assert r["success"] and r["tool_calls"] == 2 and r["failed_calls"] == 1
    html = open(r["html_path"]).read()
    assert "Unit run" in html
    assert "list_projects" in html and "get_project" in html
    assert "Two findings: A and B." in html
    assert 'class="badge err"' in html  # the failure is visibly marked


def test_report_clear_resets_journal():
    run(server.call_tool("list_projects", {}))
    r = run(HANDLERS["session_report"]({"pdf": False, "clear": True}))
    assert r["journal_cleared"] is True
    assert journal.entries == []  # next report starts fresh
