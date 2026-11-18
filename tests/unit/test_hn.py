"""T10 HN Algolia 信源测试（fixtures 回放，零网络）。"""

import json
from pathlib import Path

import httpx
import pytest

from openmind.sources.base import Query
from openmind.sources.hn import HnSource

FIX = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def mock_api(monkeypatch):
    def fake_get(url, **kwargs):
        return httpx.Response(
            200,
            json=json.loads((FIX / "hn_algolia.json").read_text(encoding="utf-8")),
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)


class TestHn:
    def test_link_story_is_article(self, mock_api):
        cands = HnSource().search(Query(title="Bioacoustics", lang="en"))
        assert len(cands) == 2
        assert cands[0].kind == "article"
        assert cands[0].url == "https://www.example.org/bioacoustics-ai"
        assert cands[0].meta["discussion_url"].endswith("id=30000001")

    def test_ask_hn_is_discussion(self, mock_api):
        cands = HnSource().search(Query(title="Bioacoustics", lang="en"))
        assert cands[1].kind == "discussion"
        assert cands[1].url == "https://news.ycombinator.com/item?id=30000002"
        assert "field recording" in cands[1].snippet

    def test_metadata_and_date(self, mock_api):
        cands = HnSource().search(Query(title="Bioacoustics", lang="en"))
        assert cands[0].meta["points"] == 210
        assert cands[0].meta["comments"] == 87
        assert cands[0].published == "2024-03-01"
        assert all(c.source == "hn" for c in cands)

    def test_failure_returns_empty(self, monkeypatch):
        def boom(*a, **k):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(httpx, "get", boom)
        assert HnSource().search(Query(title="X", lang="en")) == []

    def test_needs_no_key(self):
        assert HnSource.needs_key is False
