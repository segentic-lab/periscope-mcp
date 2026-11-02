"""devices: viewport presets vs full device descriptors."""
import pytest

import devices

FAKE_PW = {"iPhone 13": {"user_agent": "Mozilla/5.0 (iPhone ...)", "viewport": {"width": 390, "height": 844},
                         "device_scale_factor": 3, "is_mobile": True, "has_touch": True,
                         "default_browser_type": "webkit"}}


def test_preset_resolves_to_viewport_only():
    kind, kw = devices.resolve_device("mobile", FAKE_PW)
    assert kind == "viewport" and kw == {"width": 375, "height": 812}


def test_playwright_name_resolves_to_descriptor_without_browser_type():
    kind, kw = devices.resolve_device("iPhone 13", FAKE_PW)
    assert kind == "descriptor"
    assert kw["user_agent"].startswith("Mozilla") and kw["is_mobile"] is True
    assert "default_browser_type" not in kw


def test_custom_samsung_internet_descriptor():
    kind, kw = devices.resolve_device("samsung_internet", FAKE_PW)
    assert kind == "descriptor" and "SamsungBrowser" in kw["user_agent"]
    assert kw["viewport"] == {"width": 412, "height": 915} and kw["has_touch"] is True


def test_unknown_device_lists_options():
    with pytest.raises(ValueError) as e:
        devices.resolve_device("nokia 3310", FAKE_PW)
    msg = str(e.value)
    assert "mobile_sm" in msg and "iPhone 14" in msg and "samsung_internet" in msg
