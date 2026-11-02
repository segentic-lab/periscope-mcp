"""Device presets and descriptors for sessions.

Two kinds:
- VIEWPORT_PRESETS: size-only names (mobile, tablet, ...) — applied to the
  existing page, no new context.
- descriptors: Playwright device names ("iPhone 14", "Galaxy S9+", ...) plus
  CUSTOM_DEVICES — carry user agent, DPR, touch and mobile flags, so they need
  their own browser context (created seeded with the project's login state).
"""

VIEWPORT_PRESETS = {
    "mobile_sm": {"width": 320, "height": 568},    # iPhone SE
    "mobile": {"width": 375, "height": 812},        # iPhone 12
    "mobile_lg": {"width": 428, "height": 926},     # iPhone 14 Pro Max
    "tablet": {"width": 768, "height": 1024},       # iPad
    "tablet_lg": {"width": 1024, "height": 1366},   # iPad Pro
    "laptop": {"width": 1366, "height": 768},       # Common laptop
    "desktop": {"width": 1920, "height": 1080},     # Full HD
    "desktop_lg": {"width": 2560, "height": 1440},  # QHD
}

# Browsers Playwright doesn't ship a descriptor for but that real users (and
# real install-prompt bugs) live on.
CUSTOM_DEVICES = {
    "samsung_internet": {
        "user_agent": ("Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) SamsungBrowser/26.0 Chrome/122.0.0.0 Mobile Safari/537.36"),
        "viewport": {"width": 412, "height": 915},
        "device_scale_factor": 3,
        "is_mobile": True,
        "has_touch": True,
    },
}

# Keys of a Playwright descriptor that are valid new_context kwargs.
_CONTEXT_KEYS = ("user_agent", "viewport", "device_scale_factor", "is_mobile", "has_touch",
                 "screen", "locale", "timezone_id", "color_scheme")

_EXAMPLES = "'iPhone 14', 'iPhone 13', 'Pixel 7', 'Galaxy S9+', 'iPad Pro 11'"


def resolve_device(name: str, playwright_devices: dict) -> tuple[str, dict]:
    """Resolve a device name → ("viewport", {width, height}) for size presets
    or ("descriptor", new_context kwargs) for full devices.

    Raises ValueError (listing the options) for an unknown name.
    """
    if name in VIEWPORT_PRESETS:
        return "viewport", dict(VIEWPORT_PRESETS[name])
    if name in CUSTOM_DEVICES:
        return "descriptor", dict(CUSTOM_DEVICES[name])
    desc = playwright_devices.get(name) if playwright_devices else None
    if desc is None and playwright_devices:
        # tolerate case differences ("iphone 13")
        lower = {k.lower(): k for k in playwright_devices}
        key = lower.get(name.lower())
        desc = playwright_devices.get(key) if key else None
    if desc is not None:
        return "descriptor", {k: v for k, v in desc.items() if k in _CONTEXT_KEYS}
    raise ValueError(
        f"Unknown device '{name}'. Use a viewport preset ({', '.join(VIEWPORT_PRESETS)}), "
        f"a custom device ({', '.join(CUSTOM_DEVICES)}), or any Playwright device name "
        f"(e.g. {_EXAMPLES}) — the latter emulate user agent, DPR and touch too."
    )
