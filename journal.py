"""Tool-call journal: the record session_report renders.

server.py records every dispatched tool call here (the single chokepoint),
so the report covers everything the agent did — including failed calls.
Journaling must never break a tool call: record() swallows its own errors.
"""
import json
import re
import time

MAX_ENTRIES = 2000          # hard cap; oldest dropped, drop count kept
_ARGS_PREVIEW = 1500        # chars of pretty-printed args per entry
_RESULT_PREVIEW = 3000      # chars of pretty-printed result per entry

_SECRET_KEY_PARTS = ("password", "token", "secret", "authorization", "api_key", "apikey")

entries: list[dict] = []
dropped = 0
started_at = time.time()


_SECRET_SELECTOR = re.compile(r"pass|pwd|secret|token|otp|cvc|cvv|card|iban|ssn|pin\b", re.I)
_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/@\s:]+:[^/@\s]+@")
_MASK = "•••"
# Tools whose RESULT carries credentials by nature: the report must not copy them.
_VALUE_RESULT_TOOLS = {"get_cookies", "get_local_storage"}
_BODY_RESULT_TOOLS = {"get_response_body"}
# Free-form maps whose values are opaque app state (tokens live here).
_OPAQUE_MAPS = ("entries",)


def _scrub(text: str) -> str:
    """Strip credentials embedded in URLs (scheme://user:pass@host)."""
    return _USERINFO.sub(lambda m: m.group(1) + _MASK + "@", text)


def _redact(obj, parent_key: str = ""):
    """Mask credential-ish values: by key name, cookie values, values typed
    into password-like fields, opaque storage maps, and URL userinfo."""
    if isinstance(obj, dict):
        out = {}
        # A {selector|name, value|text} pair typed into a secret-looking field
        target = " ".join(str(obj.get(k) or "") for k in ("selector", "name", "label"))
        secret_field = bool(_SECRET_SELECTOR.search(target))
        for k, v in obj.items():
            kl = str(k).lower()
            if any(p in kl for p in _SECRET_KEY_PARTS):
                out[k] = _MASK
            elif kl == "value" and parent_key == "cookies":
                out[k] = _MASK
            elif kl in ("value", "text") and secret_field:
                out[k] = _MASK
            elif kl in _OPAQUE_MAPS and isinstance(v, dict):
                out[k] = {kk: _MASK for kk in v}
            else:
                out[k] = _redact(v, parent_key=kl if isinstance(v, list) else parent_key)
        return out
    if isinstance(obj, list):
        return [_redact(x, parent_key=parent_key) for x in obj]
    if isinstance(obj, str):
        return _scrub(obj)
    return obj


def _redact_result(tool: str, result):
    """Results are redacted too — the report is shared with humans."""
    red = _redact(result)
    if isinstance(red, dict):
        if tool in _BODY_RESULT_TOOLS and "body_text" in red:
            red = {**red, "body_text": f"[{len(str(result.get('body_text') or ''))} chars — omitted from the journal]"}
    return red


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
            "result_preview": _preview(_redact_result(tool, result), _RESULT_PREVIEW) if error is None else None,
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
