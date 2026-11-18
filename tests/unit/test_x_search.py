"""T15 X Recent Search 信源测试（fixtures 回放，零网络）。"""

import json
from pathlib import Path

import httpx
import pytest

from openmind.sources.base import Query
from openmind.sources.x_search import XSearchSource

FIX = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def mock_api(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "tok")
    seen = {}

    def fake_get(url, **kwargs):
        seen["headers"] = kwargs.get("headers", {})
        seen["params"] = kwargs.get("params", {})
        return httpx.Response(
            200,
            json=json.loads((FIX / "x_recent.json").read_text(encoding="utf-8")),
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    return seen


class TestApiPath:
    def test_candidates_discussion(self, mock_api):
        cands = XSearchSource().search(Query(title="Bioacoustics", lang="en"))
        assert len(cands) == 2
        assert all(c.kind == "discussion" and c.source == "x_search" for c in cands)
        assert cands[0].url == "https://x.com/sci_researcher/status/1700000000000000001"
        assert cands[0].meta["likes"] == 120
        assert cands[0].published == "2024-02-01"

    def test_bearer_header_and_no_retweets(self, mock_api):
        XSearchSource().search(Query(title="Bioacoustics", lang="en"))
        assert mock_api["headers"]["Authorization"] == "Bearer tok"
        assert "-is:retweet" in mock_api["params"]["query"]

    def test_429_returns_empty(self, monkeypatch):
        monkeypatch.setenv("X_BEARER_TOKEN", "tok")
        monkeypatch.setattr(
            httpx,
            "get",
            lambda url, **k: httpx.Response(429, request=httpx.Request("GET", url)),
        )
        assert XSearchSource().search(Query(title="X", lang="en")) == []

    def test_403_returns_empty(self, monkeypatch):
        monkeypatch.setenv("X_BEARER_TOKEN", "tok")
        monkeypatch.setattr(
            httpx,
            "get",
            lambda url, **k: httpx.Response(403, request=httpx.Request("GET", url)),
        )
        assert XSearchSource().search(Query(title="X", lang="en")) == []

    def test_failure_returns_empty(self, monkeypatch):
        monkeypatch.setenv("X_BEARER_TOKEN", "tok")

        def boom(*a, **k):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(httpx, "get", boom)
        assert XSearchSource().search(Query(title="X", lang="en")) == []


class TestDdgFallback:
    def test_no_token_uses_ddg_site_query(self, monkeypatch):
        monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
        from openmind.sources import duckduckgo

        calls = []

        def fake_search(q, n):
            calls.append(q)
            return [
                {
                    "title": "post on X",
                    "href": "https://x.com/user/status/123",
                    "body": "thread",
                },
                {"title": "not x", "href": "https://example.org/x", "body": ""},
            ]

        monkeypatch.setattr(duckduckgo, "_text_search", fake_search)
        cands = XSearchSource().search(Query(title="Bioacoustics", lang="en"))
        assert calls == ["Bioacoustics site:x.com"]
        assert len(cands) == 1  # 非 x.com 域名剔除
        assert cands[0].kind == "discussion"
        assert cands[0].meta["origin"] == "ddg_fallback"

    def test_ddg_failure_returns_empty(self, monkeypatch):
        monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
        from openmind.sources import duckduckgo

        def boom(q, n):
            raise RuntimeError("Ratelimit")

        monkeypatch.setattr(duckduckgo, "_text_search", boom)
        assert XSearchSource().search(Query(title="X", lang="en")) == []

    def test_needs_no_key_flag(self):
        # 无 token 有降级路径，discover 不应 skip
        assert XSearchSource.needs_key is False
