"""T10 Reddit 信源测试（fixtures 回放，零网络）。"""

import json
from pathlib import Path

import httpx
import pytest

from openmind.sources.base import Query
from openmind.sources.reddit import RedditSource

FIX = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def mock_api(monkeypatch):
    seen = {}

    def fake_get(url, **kwargs):
        seen["url"] = url
        seen["headers"] = kwargs.get("headers", {})
        return httpx.Response(
            200,
            json=json.loads((FIX / "reddit_search.json").read_text(encoding="utf-8")),
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    return seen


class TestReddit:
    def test_link_post_is_article(self, mock_api):
        cands = RedditSource().search(Query(title="Bioacoustics", lang="en"))
        assert len(cands) == 2
        assert cands[0].kind == "article"
        assert cands[0].url == "https://www.example.org/reddit-guide"
        assert cands[0].meta["discussion_url"].startswith("https://www.reddit.com/r/")

    def test_self_post_is_discussion(self, mock_api):
        cands = RedditSource().search(Query(title="Bioacoustics", lang="en"))
        assert cands[1].kind == "discussion"
        assert "reddit.com" in cands[1].url
        assert "hydrophone" in cands[1].snippet

    def test_ua_and_endpoint(self, mock_api):
        RedditSource().search(Query(title="Bioacoustics", lang="en"))
        assert mock_api["url"].endswith("/search.json")
        assert "OpenMind" in mock_api["headers"].get("User-Agent", "")

    def test_published_from_utc(self, mock_api):
        cands = RedditSource().search(Query(title="Bioacoustics", lang="en"))
        assert cands[0].published == "2023-11-14"

    def test_failure_returns_empty(self, monkeypatch):
        def boom(*a, **k):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(httpx, "get", boom)
        assert RedditSource().search(Query(title="X", lang="en")) == []

    def test_blocked_403_returns_empty(self, monkeypatch):
        def blocked(url, **k):
            return httpx.Response(403, request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "get", blocked)
        assert RedditSource().search(Query(title="X", lang="en")) == []

    def test_needs_no_key(self):
        assert RedditSource.needs_key is False
