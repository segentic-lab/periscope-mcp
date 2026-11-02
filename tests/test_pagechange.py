"""pagechange: url/dom/network change detection around an action."""
import asyncio

import pagechange


class FakePage:
    """Minimal page double: `url` attribute, `evaluate` returning scripted DOM hashes."""

    def __init__(self, url, hashes):
        self.url = url
        self._hashes = list(hashes)

    async def evaluate(self, _js):
        return self._hashes.pop(0)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_diff_reports_each_change_kind():
    page = FakePage(url="http://a/", hashes=[1, 2])
    before = run(pagechange.snapshot(page, network_log=[]))
    page.url = "http://a/next"
    d = run(pagechange.diff(page, before, network_log=[{"url": "x"}]))
    assert d == {"changed": True, "change": ["url", "dom", "network"]}


def test_diff_no_change():
    page = FakePage(url="http://a/", hashes=[7, 7])
    before = run(pagechange.snapshot(page, network_log=[]))
    assert run(pagechange.diff(page, before, network_log=[])) == {"changed": False, "change": []}


def test_snapshot_without_network_log():
    page = FakePage(url="http://a/", hashes=[3, 3])
    before = run(pagechange.snapshot(page))
    assert before["net_count"] == 0
    assert run(pagechange.diff(page, before)) == {"changed": False, "change": []}
