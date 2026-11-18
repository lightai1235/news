"""T11 DuckDuckGo ddgs 信源测试（mock ddgs 调用，零网络）。"""

import pytest

from openmind.sources.base import Query
from openmind.sources.duckduckgo import DuckDuckGoSource


@pytest.fixture()
def mock_ddgs(monkeypatch):
    calls = []

    def fake_search(q, max_results):
        calls.append(q)
        if "site:youtube.com" in q:
            return [
                {
                    "title": "Bioacoustics documentary",
                    "href": "https://www.youtube.com/watch?v=ddg1",
                    "body": "A long documentary about animal sounds.",
                }
            ]
        return [
            {
                "title": "Bioacoustics review",
                "href": "https://www.example.org/ddg-review",
                "body": "An overview of the field.",
            },
            {
                "title": "Bioacoustics paper",
                "href": "https://arxiv.org/abs/2201.99999",
                "body": "Paper abstract.",
            },
        ]

    from openmind.sources import duckduckgo

    monkeypatch.setattr(duckduckgo, "_text_search", fake_search)
    return calls


class TestDuckDuckGo:
    def test_general_and_video_queries(self, mock_ddgs):
        q = Query(title="Bioacoustics", lang="en", groups={"exact": '"Bioacoustics" review'})
        cands = DuckDuckGoSource().search(q)
        assert mock_ddgs == ['"Bioacoustics" review', "Bioacoustics site:youtube.com"]
        assert len(cands) == 3

    def test_kind_classified_by_url(self, mock_ddgs):
        cands = DuckDuckGoSource().search(Query(title="Bioacoustics", lang="en"))
        kinds = {c.kind for c in cands}
        assert kinds == {"article", "paper", "video"}
        assert all(c.source == "duckduckgo" for c in cands)

    def test_dedupe_across_queries(self, monkeypatch):
        from openmind.sources import duckduckgo

        monkeypatch.setattr(
            duckduckgo,
            "_text_search",
            lambda q, n: [{"title": "same", "href": "https://example.org/x", "body": ""}],
        )
        cands = DuckDuckGoSource().search(Query(title="X", lang="en"))
        assert len(cands) == 1

    def test_rate_limit_one_per_second(self, monkeypatch):
        from openmind.sources import duckduckgo

        waits = []

        class FakeLimiter:
            def acquire(self):
                waits.append(1)

        monkeypatch.setattr(duckduckgo, "_LIMITER", FakeLimiter())
        monkeypatch.setattr(duckduckgo, "_text_search", lambda q, n: [])
        DuckDuckGoSource().search(Query(title="X", lang="en"))
        assert len(waits) == 2  # 每次调用前都限速

    def test_block_returns_empty_not_raise(self, monkeypatch):
        from openmind.sources import duckduckgo

        def boom(q, n):
            raise RuntimeError("Ratelimit")

        monkeypatch.setattr(duckduckgo, "_text_search", boom)
        assert DuckDuckGoSource().search(Query(title="X", lang="en")) == []

    def test_partial_failure_keeps_other_query(self, monkeypatch):
        from openmind.sources import duckduckgo

        def half(q, n):
            if "site:" in q:
                raise RuntimeError("Ratelimit")
            return [{"title": "t", "href": "https://example.org/ok", "body": ""}]

        monkeypatch.setattr(duckduckgo, "_text_search", half)
        cands = DuckDuckGoSource().search(Query(title="X", lang="en"))
        assert len(cands) == 1

    def test_needs_no_key(self):
        assert DuckDuckGoSource.needs_key is False
