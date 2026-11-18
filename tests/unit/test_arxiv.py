"""T9 arXiv 信源测试（fixtures 回放，零网络）。"""

from pathlib import Path

import httpx
import pytest

from openmind.sources.arxiv import ArxivSource
from openmind.sources.base import Query

FIX = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def mock_api(monkeypatch):
    def fake_get(url, **kwargs):
        return httpx.Response(
            200,
            text=(FIX / "arxiv_atom.xml").read_text(encoding="utf-8"),
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)


class TestArxiv:
    def test_candidates_kind_paper(self, mock_api):
        cands = ArxivSource().search(Query(title="Bioacoustics", lang="en"))
        assert len(cands) == 2
        assert all(c.kind == "paper" and c.source == "arxiv" for c in cands)
        assert cands[0].url == "https://arxiv.org/abs/2201.00001v1"
        assert cands[0].title == "A Survey of Bioacoustics Methods"

    def test_year_and_pages_metadata(self, mock_api):
        cands = ArxivSource().search(Query(title="Bioacoustics", lang="en"))
        assert cands[0].published == "2022-01-01"
        assert cands[0].meta["pages"] == 25
        assert "pages" not in cands[1].meta  # 无 comment 不硬造

    def test_snippet_from_summary(self, mock_api):
        cands = ArxivSource().search(Query(title="Bioacoustics", lang="en"))
        assert "bioacoustics" in cands[0].snippet.lower()

    def test_failure_returns_empty(self, monkeypatch):
        def boom(*a, **k):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(httpx, "get", boom)
        assert ArxivSource().search(Query(title="X", lang="en")) == []

    def test_bad_xml_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            httpx,
            "get",
            lambda url, **k: httpx.Response(
                200, text="not xml", request=httpx.Request("GET", url)
            ),
        )
        assert ArxivSource().search(Query(title="X", lang="en")) == []

    def test_needs_no_key(self):
        assert ArxivSource.needs_key is False


class TestRateLimit:
    def test_limiter_acquired_before_request(self, monkeypatch):
        from openmind.sources import arxiv

        waits = []

        class FakeLimiter:
            def acquire(self):
                waits.append(1)

        monkeypatch.setattr(arxiv, "_LIMITER", FakeLimiter())
        monkeypatch.setattr(
            httpx,
            "get",
            lambda url, **k: httpx.Response(
                200,
                text=(FIX / "arxiv_atom.xml").read_text(encoding="utf-8"),
                request=httpx.Request("GET", url),
            ),
        )
        ArxivSource().search(Query(title="X", lang="en"))
        assert waits == [1]

    def test_interval_at_least_3s(self):
        from openmind.sources.arxiv import _LIMITER

        assert _LIMITER.min_interval >= 3.0
