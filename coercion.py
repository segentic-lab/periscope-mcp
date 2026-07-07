"""Argument coercion for MCP clients that serialize array/bool args as JSON strings."""
import json

# Args that are structured (arrays/objects) per the tool schemas. Only these get
# JSON-string coercion — free-text args like intercept_network's 'body' or a fill
# 'value' must NEVER be parsed, even if they look like JSON.
_STRUCTURED_ARGS = {
    "steps", "fields", "checks", "run_checks", "cookies", "viewports",
    "files", "keys", "attributes", "properties", "entries", "overrides",
    "categories", "assertions", "contains",
}
# Structured args whose items are plain strings — a bare string like
# "seo,performance" is accepted as a comma-separated list.
_CSV_ARGS = {"checks", "run_checks", "files", "keys", "attributes", "properties", "categories", "contains"}
# Boolean args per the tool schemas.
_BOOL_ARGS = {
    "force", "check_external", "clear", "clear_first", "once", "submit",
    "full_page", "screenshot_after", "continue_on_error", "raw_html", "verify_ssl",
    "capture_console", "full_text", "headed", "apply", "include_hidden", "pdf", "include_screenshots",
    "use_sitemap", "raw", "readable", "render", "save",
}


def coerce_args(args: dict):
    """Coerce JSON-string args in place: MCP clients with stale schemas may
    serialize array/bool parameters as JSON strings."""
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
