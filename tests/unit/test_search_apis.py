"""T12 Serper/Brave/Tavily 统一 SearchPort 测试（fixtures 回放，零网络）。"""

import json
from pathlib import Path

import httpx

from openmind.sources.base import Query
from openmind.sources.search_apis import BraveSource, SerperSource, TavilySource

FIX = Path(__file__).parent.parent / "fixtures"
Q = Query(
    title="Bioacoustics",
    lang="en",
    groups={"exact": '"Bioacoustics" review', "concept": "animal sound research"},
)


def _resp(fixture, url):
    return httpx.Response(
        200,
        json=json.loads((FIX / fixture).read_text(encoding="utf-8")),
        request=httpx.Request("POST", url),
    )


class TestSerper:
    def test_two_query_groups(self, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "k")
        calls = []

        def fake_post(url, **kwargs):
            calls.append(kwargs["json"]["q"])
            assert kwargs["headers"]["X-API-KEY"] == "k"
            return _resp("serper_search.json", url)

        monkeypatch.setattr(httpx, "post", fake_post)
        cands = SerperSource().search(Q)
        assert calls == ['"Bioacoustics" review', "animal sound research"]
        assert len(cands) == 2  # 两组结果相同 URL 去重
        assert cands[0].source == "serper"

    def test_kind_and_date(self, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "k")
        monkeypatch.setattr(httpx, "post", lambda url, **k: _resp("serper_search.json", url))
        cands = SerperSource().search(Q)
        assert cands[0].kind == "article"
        assert cands[1].kind == "video"
        assert cands[0].published == "2024-01-15"

    def test_no_key_returns_empty(self, monkeypatch):
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        assert SerperSource().search(Q) == []

    def test_failure_returns_empty(self, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "k")

        def boom(*a, **k):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(httpx, "post", boom)
        assert SerperSource().search(Q) == []


class TestBrave:
    def test_candidates(self, monkeypatch):
        monkeypatch.setenv("BRAVE_API_KEY", "k")

        def fake_get(url, **kwargs):
            assert kwargs["headers"]["X-Subscription-Token"] == "k"
            return _resp("brave_search.json", url)

        monkeypatch.setattr(httpx, "get", fake_get)
        cands = BraveSource().search(Q)
        assert len(cands) == 2
        assert cands[0].source == "brave"
        assert cands[1].kind == "paper"
        assert cands[0].published == "2023-09-01"

    def test_no_key_returns_empty(self, monkeypatch):
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)
        assert BraveSource().search(Q) == []

    def test_failure_returns_empty(self, monkeypatch):
        monkeypatch.setenv("BRAVE_API_KEY", "k")

        def boom(*a, **k):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(httpx, "get", boom)
        assert BraveSource().search(Q) == []


class TestTavily:
    def test_candidates(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "k")

        def fake_post(url, **kwargs):
            assert kwargs["json"]["api_key"] == "k"
            return _resp("tavily_search.json", url)

        monkeypatch.setattr(httpx, "post", fake_post)
        cands = TavilySource().search(Q)
        assert len(cands) == 2
        assert cands[0].source == "tavily"
        assert cands[1].kind == "video"
        assert cands[0].published == "2024-05-01"

    def test_no_key_returns_empty(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        assert TavilySource().search(Q) == []

    def test_failure_returns_empty(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "k")

        def boom(*a, **k):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(httpx, "post", boom)
        assert TavilySource().search(Q) == []


class TestUnifiedContract:
    def test_all_need_key(self):
        assert all(s.needs_key for s in (SerperSource, BraveSource, TavilySource))

    def test_names_match_key_mapping(self):
        names = {s.name for s in (SerperSource(), BraveSource(), TavilySource())}
        assert names == {"serper", "brave", "tavily"}
