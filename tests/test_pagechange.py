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


def test_request_counter_beats_capped_log():
    """A log that hit its cap stays the same length; a monotonic request
    counter still registers new (even in-flight) requests as a change."""
    from sessions import RequestCounter
    page = FakePage(url="http://a/", hashes=[5, 5])
    counter = RequestCounter()
    counter.n = 1000
    capped_log = [{}] * 1000
    before = run(pagechange.snapshot(page, network_log=capped_log, request_counter=counter))
    counter.n += 1  # request started, no response yet, log length unchanged
    d = run(pagechange.diff(page, before, network_log=capped_log, request_counter=counter))
    assert d == {"changed": True, "change": ["network"]}
