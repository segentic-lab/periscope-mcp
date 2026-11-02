"""web_fetch: a TLS certificate failure must name the fix (no network needed)."""
import asyncio

import httpx
import pytest

from handlers import HANDLERS


class _FailingClient:
    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
                                 "certificate has expired (_ssl.c:1000)")


def test_tls_failure_is_actionable(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _FailingClient)
    r = asyncio.new_event_loop().run_until_complete(
        HANDLERS["web_fetch"]({"url": "https://docs.example.test/page"}))
    assert r["success"] is False and r["tls_error"] is True, r
    assert "docs.example.test" in r["error"] and "verify_ssl=false" in r["error"] and "render=true" in r["error"], r
