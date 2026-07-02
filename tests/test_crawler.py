"""Crawler URL normalization and filtering (no browser)."""
from crawler import Crawler


def test_normalize_strips_fragment_and_trailing_slash():
    c = Crawler()
    assert c._normalize_url("https://a.com/page/#top") == "https://a.com/page"
    assert c._normalize_url("https://a.com/") == "https://a.com"


def test_same_domain():
    c = Crawler()
    assert c._is_same_domain("https://a.com/x", "https://a.com")
    assert not c._is_same_domain("https://b.com/x", "https://a.com")


def test_valid_url_schemes_and_extensions():
    c = Crawler()
    assert c._is_valid_url("https://a.com/page")
    assert not c._is_valid_url("mailto:x@a.com")
    assert not c._is_valid_url("https://a.com/file.pdf")
    assert not c._is_valid_url("https://a.com/style.css")
