"""T13 YouTube Data API 信源测试（fixtures 回放，零网络）。"""

import json
from pathlib import Path

import httpx
import pytest

from openmind.sources.base import Query
from openmind.sources.youtube import YoutubeSource, parse_duration_minutes

FIX = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def mock_api(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs.get("params", {})))
        fixture = "youtube_search.json" if url.endswith("/search") else "youtube_videos.json"
        return httpx.Response(
            200,
            json=json.loads((FIX / fixture).read_text(encoding="utf-8")),
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    return calls


class TestDuration:
    def test_minutes_seconds(self):
        assert parse_duration_minutes("PT42M10S") == 42.2

    def test_hours(self):
        assert parse_duration_minutes("PT1H5M30S") == 65.5

    def test_invalid(self):
        assert parse_duration_minutes("") == 0.0
        assert parse_duration_minutes("garbage") == 0.0


class TestYoutube:
    def test_search_long_videos_once(self, mock_api):
        cands = YoutubeSource().search(Query(title="Bioacoustics", lang="en"))
        search_calls = [c for c in mock_api if c[0].endswith("/search")]
        assert len(search_calls) == 1
        assert search_calls[0][1]["videoDuration"] == "long"
        assert len(cands) == 2
        assert all(c.kind == "video" and c.source == "youtube" for c in cands)
        assert cands[0].url == "https://www.youtube.com/watch?v=yt001"

    def test_duration_and_views_metadata(self, mock_api):
        cands = YoutubeSource().search(Query(title="Bioacoustics", lang="en"))
        assert cands[0].meta["duration_min"] == 42.2
        assert cands[0].meta["views"] == 150000
        assert cands[0].meta["channel"] == "Science Channel"
        assert cands[1].meta["duration_min"] == 65.5
        assert cands[0].published == "2023-04-01"

    def test_videos_list_failure_degrades(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_API_KEY", "k")

        def fake_get(url, **kwargs):
            if url.endswith("/search"):
                return httpx.Response(
                    200,
                    json=json.loads((FIX / "youtube_search.json").read_text(encoding="utf-8")),
                    request=httpx.Request("GET", url),
                )
            raise httpx.ConnectError("down")

        monkeypatch.setattr(httpx, "get", fake_get)
        cands = YoutubeSource().search(Query(title="X", lang="en"))
        assert len(cands) == 2  # 元数据缺失仍出候选
        assert cands[0].meta["duration_min"] == 0.0

    def test_no_key_returns_empty(self, monkeypatch):
        monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
        assert YoutubeSource().search(Query(title="X", lang="en")) == []

    def test_failure_returns_empty(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_API_KEY", "k")

        def boom(*a, **k):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(httpx, "get", boom)
        assert YoutubeSource().search(Query(title="X", lang="en")) == []

    def test_needs_key(self):
        assert YoutubeSource.needs_key is True
