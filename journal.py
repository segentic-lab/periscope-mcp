"""Tool-call journal: the record session_report renders.

server.py records every dispatched tool call here (the single chokepoint),
so the report covers everything the agent did — including failed calls.
Journaling must never break a tool call: record() swallows its own errors.
"""
import json
import time

MAX_ENTRIES = 2000          # hard cap; oldest dropped, drop count kept
_ARGS_PREVIEW = 1500        # chars of pretty-printed args per entry
_RESULT_PREVIEW = 3000      # chars of pretty-printed result per entry

_SECRET_KEY_PARTS = ("password", "token", "secret", "authorization", "api_key", "apikey")

entries: list[dict] = []
dropped = 0
started_at = time.time()


def _redact(obj, parent_key: str = ""):
    """Mask credential-ish values; cookie values are bearer credentials too."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            kl = str(k).lower()
            if any(p in kl for p in _SECRET_KEY_PARTS):
                out[k] = "•••"
            elif kl == "value" and parent_key == "cookies":
                out[k] = "•••"
            else:
                out[k] = _redact(v, parent_key=kl if isinstance(v, list) else parent_key)
        return out
    if isinstance(obj, list):
        return [_redact(x, parent_key=parent_key) for x in obj]
    return obj


def _preview(obj, limit: int) -> str:
    try:
        text = json.dumps(obj, indent=1, ensure_ascii=False, default=str)
    except Exception:
        text = str(obj)
    return text if len(text) <= limit else text[:limit] + f"\n… [truncated, {len(text)} chars total]"


def _screenshots_of(result) -> list[str]:
    """Collect any *path values that look like image files, wherever they sit."""
    found = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and "path" in str(k).lower() and v.endswith((".png", ".jpg", ".jpeg")):
                    found.append(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(result)
    return found


def record(tool: str, args: dict, result, duration_ms: int, error: str = None):
    """Append one call record. Never raises."""
    global dropped
    try:
        ok = error is None and not (isinstance(result, dict) and result.get("success") is False)
        entry = {
            "ts": time.time(),
            "tool": tool,
            "session_id": args.get("session_id"),
            "duration_ms": duration_ms,
            "success": ok,
            "args_preview": _preview(_redact(dict(args)), _ARGS_PREVIEW),
            "result_preview": _preview(result, _RESULT_PREVIEW) if error is None else None,
            "error": error or (result.get("error") if isinstance(result, dict) else None),
            "screenshots": _screenshots_of(result) if error is None else [],
        }
        entries.append(entry)
        if len(entries) > MAX_ENTRIES:
            entries.pop(0)
            dropped += 1
    except Exception:
        pass  # the journal must never take a tool call down with it


def clear():
    global dropped, started_at
    entries.clear()
    dropped = 0
    started_at = time.time()
