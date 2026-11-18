"""lighthouse_summary: pure post-processing of Lighthouse JSON (LH 13 insight
shape + the older largest-contentful-paint-element shape)."""
import copy
import json
import os

import pytest

import lighthouse_summary as ls

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "lighthouse_min.json")


@pytest.fixture()
def report():
    with open(FIXTURE) as f:
        return json.load(f)


def test_summarize_lcp_and_ttfb(report):
    s = ls.summarize(report)
    assert s["lcp_element"]["selector"] == "body > section#band > h1#cta"
    assert s["lcp_element"]["snippet"]
    assert s["lcp_phases"]["ttfb_ms"] == 6 and s["lcp_phases"]["render_delay_ms"] == 653
    assert s["lcp_phases"]["load_delay_ms"] is None and s["lcp_phases"]["load_time_ms"] is None
    assert s["ttfb_ms"] == 2500 and s["ttfb_warning"] is True


def test_bytes_by_domain_sorted_and_third_party(report):
    s = ls.summarize(report)
    domains = [d["domain"] for d in s["bytes_by_domain"]]
    assert domains[0] == "player.vimeo.com" and s["bytes_by_domain"][0]["bytes"] == 385000
    assert s["bytes_by_domain"][0]["third_party"] is True
    first = next(d for d in s["bytes_by_domain"] if d["domain"] == "site.test")
    assert first["third_party"] is False and first["requests"] == 2 and first["bytes"] == 130611
    assert s["third_party_bytes"] == 475000 and s["bytes_total"] == 605611


def test_opportunities_top_by_savings(report):
    s = ls.summarize(report)
    assert [o["id"] for o in s["opportunities"]] == ["image-delivery-insight", "render-blocking-insight"]
    assert s["opportunities"][0]["savings_ms"] == 1200 and s["opportunities"][0]["title"]


def test_summarize_legacy_lcp_element_shape(report):
    legacy = copy.deepcopy(report)
    legacy["audits"].pop("lcp-breakdown-insight")
    legacy["audits"]["largest-contentful-paint-element"] = {"details": {"type": "list", "items": [
        {"type": "table", "items": [{"node": {"selector": "div#hero > img", "snippet": "<img src=hero.jpg>"}}]},
        {"type": "table", "items": [
            {"phase": "TTFB", "timing": 400.2}, {"phase": "Load Delay", "timing": 100},
            {"phase": "Load Time", "timing": 250}, {"phase": "Render Delay", "timing": 50}]},
    ]}}
    s = ls.summarize(legacy)
    assert s["lcp_element"]["selector"] == "div#hero > img"
    assert s["lcp_phases"] == {"ttfb_ms": 400, "load_delay_ms": 100, "load_time_ms": 250, "render_delay_ms": 50}


def test_summarize_tolerates_missing_audits():
    s = ls.summarize({"audits": {}})
    assert s["lcp_element"] is None and s["lcp_phases"] is None and s["ttfb_ms"] is None
    assert s["ttfb_warning"] is False and s["bytes_by_domain"] == [] and s["opportunities"] == []


def _fake(lcp, fcp=None, score=0.9):
    return {"categories": {"performance": {"score": score}},
            "audits": {"largest-contentful-paint": {"numericValue": lcp},
                       "first-contentful-paint": {"numericValue": fcp if fcp is not None else lcp / 2}}}


def test_median_run_picks_middle_lcp():
    reports = [_fake(1000, score=0.8), _fake(3000, score=0.6), _fake(2000, score=0.7)]
    median, spread = ls.median_run(reports)
    assert median["audits"]["largest-contentful-paint"]["numericValue"] == 2000
    assert spread["largest-contentful-paint"] == {"min": 1000, "median": 2000, "max": 3000}
    assert spread["first-contentful-paint"]["median"] == 1000
    assert spread["scores"]["performance"] == {"min": 60, "median": 70, "max": 80}


def test_median_run_single_report():
    median, spread = ls.median_run([_fake(1500)])
    assert median["audits"]["largest-contentful-paint"]["numericValue"] == 1500
    assert spread["largest-contentful-paint"] == {"min": 1500, "median": 1500, "max": 1500}
