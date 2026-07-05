"""session_report end-to-end: real dispatch, real screenshots, real PDF."""
import json
import os

import journal
import server


def _call(run, name, args):
    out = run(server.call_tool(name, args))
    return json.loads(out[0].text)


def test_session_report_full_dossier(run, good_site):
    journal.clear()
    s = _call(run, "open_session", {"url": f"{good_site}/overlay.html"})
    sid = s["session_id"]
    try:
        _call(run, "click_element", {"session_id": sid, "selector": "#plain-btn"})
        _call(run, "screenshot_session", {"session_id": sid, "selector": "#status"})
        _call(run, "wait_for_network", {"session_id": sid})  # deliberate failure
        r = _call(run, "session_report", {
            "title": "E2E dossier", "notes": "Clicked the plain button; status turned PLAIN."})
    finally:
        _call(run, "close_session", {"session_id": sid})

    assert r["success"], r
    assert r["tool_calls"] == 4 and r["failed_calls"] == 1
    assert r["screenshots"] >= 3  # open + click + element clip

    html = open(r["html_path"]).read()
    for tool in ("open_session", "click_element", "screenshot_session",
                 "wait_for_network", "E2E dossier"):
        assert tool in html
    assert "data:image/jpeg;base64," in html      # thumbnails embedded
    assert 'class="badge err"' in html            # the failed call is marked
    assert "status turned PLAIN" in html          # agent notes present

    assert "pdf_path" in r, r.get("pdf_error")
    assert os.path.getsize(r["pdf_path"]) > 5000  # a real multi-element PDF
