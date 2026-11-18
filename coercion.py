"""Argument coercion for MCP clients that serialize array/bool args as JSON strings."""
import json

# Args that are structured (arrays/objects) per the tool schemas. Only these get
# JSON-string coercion — free-text args like intercept_network's 'body' or a fill
# 'value' must NEVER be parsed, even if they look like JSON.
_STRUCTURED_ARGS = {
    "steps", "fields", "checks", "run_checks", "cookies", "viewports",
    "files", "keys", "attributes", "properties", "entries", "overrides",
    "categories", "assertions", "contains", "viewport",
}
# Structured args whose items are plain strings — a bare string like
# "seo,performance" is accepted as a comma-separated list.
_CSV_ARGS = {"checks", "run_checks", "files", "keys", "attributes", "properties", "categories", "contains"}
# Boolean args per the tool schemas.
_BOOL_ARGS = {
    "force", "check_external", "clear", "clear_first", "once", "submit",
    "full_page", "screenshot_after", "continue_on_error", "raw_html", "verify_ssl",
    "capture_console", "full_text", "headed", "apply", "include_hidden", "pdf", "include_screenshots",
    "use_sitemap", "raw", "readable", "render", "save", "meta", "save_md",
    "hard", "include_storage", "reload", "include_frames", "warmup",
}


_numeric_cache: dict = {}


def _numeric_params(tool: str) -> dict:
    """{param: int|float} for a tool's integer/number schema properties."""
    if tool not in _numeric_cache:
        out = {}
        try:
            from tool_schemas import TOOLS
            for t in TOOLS:
                if t.name != tool:
                    continue
                schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None) or {}
                for key, prop in (schema.get("properties") or {}).items():
                    types = prop.get("type")
                    types = types if isinstance(types, list) else [types]
                    if "integer" in types:
                        out[key] = int
                    elif "number" in types:
                        out[key] = float
        except Exception:
            out = {}
        _numeric_cache[tool] = out
    return _numeric_cache[tool]


def coerce_args(args: dict, tool: str = None):
    """Coerce JSON-string args in place: MCP clients with stale schemas may
    serialize array/bool parameters as JSON strings. With `tool`, numeric
    parameters (per that tool's schema) sent as strings become numbers — the
    server does not rely on SDK-side schema validation to guarantee types."""
    if tool:
        for key, cast in _numeric_params(tool).items():
            val = args.get(key)
            if isinstance(val, str) and val.strip():
                try:
                    args[key] = cast(float(val)) if cast is int and float(val).is_integer() else cast(val)
                except ValueError:
                    pass  # leave it; the handler reports the bad value
    for key, val in list(args.items()):
        if not isinstance(val, str):
            continue
        if key in _STRUCTURED_ARGS:
            if len(val) > 1 and val[0] in ('[', '{'):
                try:
                    args[key] = json.loads(val)
                except json.JSONDecodeError:
                    pass
            elif key in _CSV_ARGS and val:
                args[key] = [s.strip() for s in val.split(",") if s.strip()]
        elif key in _BOOL_ARGS and val.lower() in ('true', 'false'):
            args[key] = val.lower() == 'true'
