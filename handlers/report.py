"""session_report: render the tool-call journal as a human-readable HTML (+PDF)
dossier — every call, verdicts, timings, and screenshots, in chronological order."""
import base64
import html as html_mod
import io
import os
import time
from datetime import datetime

import config
import journal
from _version import __version__
from runtime import get_tester

from .registry import tool

_MAX_EMBEDDED_SHOTS = 40      # thumbnails embedded; beyond this, linked only
_THUMB_MAX_W = 880


def _thumb_data_uri(path: str) -> str | None:
    """Downscaled JPEG data URI so the report (and its PDF) stays small."""
    try:
        from PIL import Image
        img = Image.open(path).convert("RGB")
        if img.width > _THUMB_MAX_W:
            img = img.resize((_THUMB_MAX_W, int(img.height * _THUMB_MAX_W / img.width)))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=72)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def _esc(s) -> str:
    return html_mod.escape(str(s if s is not None else ""))


def _render(title: str, notes: str, include_screenshots: bool) -> str:
    ents = journal.entries
    failures = [e for e in ents if not e["success"]]
    sessions = sorted({e["session_id"] for e in ents if e["session_id"]})
    span = ""
    if ents:
        t0, t1 = ents[0]["ts"], ents[-1]["ts"]
        span = (f"{datetime.fromtimestamp(t0).strftime('%H:%M:%S')} – "
                f"{datetime.fromtimestamp(t1).strftime('%H:%M:%S')} "
                f"({round(t1 - t0)}s)")
    shots_total = sum(len(e["screenshots"]) for e in ents)

    parts = [f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>{_esc(title)}</title><style>
 body{{font:14px/1.55 system-ui,-apple-system,'Segoe UI',sans-serif;color:#1c2733;margin:0;background:#f4f6f8}}
 .wrap{{max-width:960px;margin:0 auto;padding:32px 20px 60px}}
 h1{{font-size:24px;margin:0 0 4px}} .sub{{color:#5c6d7d;font-size:13px;margin:0 0 18px}}
 .stats{{display:flex;flex-wrap:wrap;gap:10px;margin:0 0 22px}}
 .stat{{background:#fff;border:1px solid #dde4ea;border-radius:8px;padding:8px 14px;font-size:13px}}
 .stat b{{font-size:17px;display:block;font-variant-numeric:tabular-nums}}
 .stat.bad b{{color:#c0392b}}
 .notes{{background:#fff;border:1px solid #dde4ea;border-left:4px solid #2a7de1;border-radius:8px;
   padding:12px 16px;margin:0 0 22px;white-space:pre-wrap}}
 .call{{background:#fff;border:1px solid #dde4ea;border-radius:10px;margin:0 0 10px;padding:12px 16px;
   page-break-inside:avoid}}
 .call.fail{{border-left:4px solid #c0392b}}
 .head{{display:flex;flex-wrap:wrap;gap:8px;align-items:baseline}}
 .idx{{color:#8494a3;font-variant-numeric:tabular-nums;font-size:12px}}
 .tool{{font-weight:650;font-family:ui-monospace,Menlo,Consolas,monospace}}
 .badge{{font-size:11px;border-radius:99px;padding:1px 9px;font-weight:600}}
 .ok{{background:#e5f5ec;color:#1e7a45}} .err{{background:#fbe9e7;color:#c0392b}}
 .meta{{color:#8494a3;font-size:12px;margin-left:auto;font-variant-numeric:tabular-nums}}
 .sid{{font-size:11px;background:#eef2f6;border-radius:99px;padding:1px 8px;color:#4a5a68;
   font-family:ui-monospace,Menlo,monospace}}
 .errline{{color:#c0392b;font-size:13px;margin:6px 0 0;white-space:pre-wrap}}
 details{{margin-top:6px}} summary{{cursor:pointer;color:#4a5a68;font-size:12px}}
 pre{{background:#f6f8fa;border:1px solid #e4e9ee;border-radius:6px;padding:8px 10px;font-size:11.5px;
   overflow-x:auto;white-space:pre-wrap;word-break:break-word;margin:4px 0 0}}
 .shot{{margin-top:8px}} .shot img{{max-width:100%;border:1px solid #dde4ea;border-radius:6px}}
 .shot .cap{{font-size:11px;color:#8494a3;word-break:break-all}}
 @media print{{body{{background:#fff}} .call{{border-color:#ccc}}}}
</style></head><body><div class="wrap">
<h1>{_esc(title)}</h1>
<p class="sub">Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · periscope {__version__} ·
journal since {datetime.fromtimestamp(journal.started_at).strftime('%Y-%m-%d %H:%M:%S')}</p>
<div class="stats">
 <div class="stat"><b>{len(ents)}</b>tool calls</div>
 <div class="stat {'bad' if failures else ''}"><b>{len(failures)}</b>failed</div>
 <div class="stat"><b>{len(sessions)}</b>browser sessions</div>
 <div class="stat"><b>{shots_total}</b>screenshots</div>
 <div class="stat"><b>{_esc(span) or '—'}</b>time span</div>
</div>"""]
    if journal.dropped:
        parts.append(f'<p class="sub">⚠ {journal.dropped} oldest calls were dropped '
                     f'(journal cap {journal.MAX_ENTRIES}).</p>')
    if notes:
        parts.append(f'<div class="notes"><b>Agent notes</b><br>{_esc(notes)}</div>')

    embedded = 0
    for i, e in enumerate(ents):
        cls = "call" + ("" if e["success"] else " fail")
        badge = '<span class="badge ok">ok</span>' if e["success"] else '<span class="badge err">failed</span>'
        sid = f'<span class="sid">{_esc(e["session_id"])}</span>' if e["session_id"] else ""
        when = datetime.fromtimestamp(e["ts"]).strftime("%H:%M:%S")
        parts.append(f'<div class="{cls}"><div class="head">'
                     f'<span class="idx">#{i + 1}</span>'
                     f'<span class="tool">{_esc(e["tool"])}</span>{badge}{sid}'
                     f'<span class="meta">{when} · {e["duration_ms"]} ms</span></div>')
        if e["error"]:
            parts.append(f'<div class="errline">{_esc(e["error"])}</div>')
        parts.append(f'<details><summary>arguments</summary><pre>{_esc(e["args_preview"])}</pre></details>')
        if e["result_preview"]:
            parts.append(f'<details><summary>result</summary><pre>{_esc(e["result_preview"])}</pre></details>')
        if include_screenshots:
            for shot in e["screenshots"]:
                if not os.path.exists(shot):
                    continue
                if embedded < _MAX_EMBEDDED_SHOTS:
                    uri = _thumb_data_uri(shot)
                    if uri:
                        embedded += 1
                        parts.append(f'<div class="shot"><img src="{uri}" alt="screenshot">'
                                     f'<div class="cap">{_esc(shot)}</div></div>')
                        continue
                parts.append(f'<div class="shot"><div class="cap">🖼 {_esc(shot)}</div></div>')
        parts.append('</div>')

    if not ents:
        parts.append('<p class="sub">No tool calls recorded yet — the journal starts '
                     'when the server starts and records every call.</p>')
    parts.append('</div></body></html>')
    return "".join(parts)


@tool("session_report")
async def handle_session_report(args: dict) -> dict:
        """Render everything the agent did — every tool call with arguments
        (secrets redacted), verdicts, timings, errors, and screenshots — as a
        self-contained HTML report plus a PDF, for the user to review."""
        title = args.get("title") or "Periscope session report"
        notes = args.get("notes") or ""
        include_screenshots = args.get("include_screenshots", True)

        html = _render(title, notes, include_screenshots)
        os.makedirs(config.REPORTS_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        html_path = os.path.join(config.REPORTS_DIR, f"session_report_{stamp}.html")
        with open(html_path, "w") as f:
            f.write(html)

        result = {
            "success": True,
            "html_path": html_path,
            "tool_calls": len(journal.entries),
            "failed_calls": sum(1 for e in journal.entries if not e["success"]),
            "screenshots": sum(len(e["screenshots"]) for e in journal.entries),
        }

        # PDF via our own Chromium; the report must not fail if the browser can't.
        if args.get("pdf", True):
            try:
                t = await get_tester()
                ctx = await t.new_ephemeral_context()
                try:
                    page = await ctx.new_page()
                    # set_content, not file:// — sandboxed system Chromiums
                    # (snap) can't read arbitrary paths; the HTML is
                    # self-contained (data-URI images) so no files are needed.
                    await page.set_content(html, wait_until="load")
                    pdf_path = html_path[:-5] + ".pdf"
                    await page.pdf(path=pdf_path, format="A4",
                                   margin={"top": "12mm", "bottom": "12mm",
                                           "left": "10mm", "right": "10mm"})
                    result["pdf_path"] = pdf_path
                finally:
                    await ctx.close()
            except Exception as e:
                result["pdf_error"] = f"PDF generation unavailable: {e}"

        if args.get("clear"):
            journal.clear()
            result["journal_cleared"] = True
        result["note"] = ("Give the user both paths. The HTML is self-contained "
                          "(screenshots embedded as thumbnails, originals linked).")
        return result
