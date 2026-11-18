"""Third-party detection compares registrable sites, not exact hosts."""
from handlers.agent_speed import same_site


def test_subdomains_of_one_site_are_first_party():
    assert same_site("cdn.example.com", "www.example.com")
    assert same_site("example.com", "shop.example.com")
    assert same_site("static.shop.example.co.uk", "www.example.co.uk")


def test_different_sites_are_third_party():
    assert not same_site("www.google-analytics.com", "www.example.com")
    assert not same_site("example.org", "example.com")
    assert not same_site("evil.co.uk", "example.co.uk")


def test_ips_and_localhost_compare_exactly_including_port():
    assert same_site("127.0.0.1:8000", "127.0.0.1:8000")
    assert not same_site("127.0.0.1:8001", "127.0.0.1:8000")
    assert not same_site("localhost:3000", "localhost:4000")
