"""T14 bilibili 信源测试（fixtures 回放，零网络）。"""

import json
from pathlib import Path

import httpx
import pytest

from openmind.sources.base import Query
from openmind.sources.bilibili import BilibiliSource, parse_duration

FIX = Path(__file__).parent.parent / "fixtures"
ZH_Q = Query(title="Bioacoustics", lang="en", aliases=["生物声学"], groups={"zh": "生物声学 研究"})


@pytest.fixture()
def mock_api(monkeypatch):
    seen = {}

    def fake_get(url, **kwargs):
        seen["params"] = kwargs.get("params", {})
        return httpx.Response(
            200,
            json=json.loads((FIX / "bilibili_search.json").read_text(encoding="utf-8")),
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    return seen


class TestDuration:
    def test_mm_ss(self):
        assert parse_duration("42:10") == 42.2

    def test_hh_mm_ss(self):
        assert parse_duration("1:05:30") == 65.5

    def test_invalid(self):
        assert parse_duration("") == 0.0
        assert parse_duration("abc") == 0.0


class TestBilibili:
    def test_candidates_video_zh(self, mock_api):
        cands = BilibiliSource().search(ZH_Q)
        assert len(cands) == 2
        assert all(c.kind == "video" and c.lang == "zh" for c in cands)
        assert cands[0].url == "https://www.bilibili.com/video/BV1bili001"
        assert cands[0].meta["duration_min"] == 42.2
        assert cands[1].meta["duration_min"] == 65.5
        assert cands[0].meta["views"] == 120000

    def test_uses_zh_alias_keyword(self, mock_api):
        BilibiliSource().search(ZH_Q)
        assert mock_api["params"]["keyword"] == "生物声学"

    def test_no_zh_group_skips(self, mock_api):
        assert BilibiliSource().search(Query(title="X", lang="en")) == []
        assert mock_api == {}  # 未发请求

    def test_risk_control_code_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            httpx,
            "get",
            lambda url, **k: httpx.Response(
                200, json={"code": -412, "message": "risk"}, request=httpx.Request("GET", url)
            ),
        )
        assert BilibiliSource().search(ZH_Q) == []

    def test_failure_returns_empty(self, monkeypatch):
        def boom(*a, **k):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(httpx, "get", boom)
        assert BilibiliSource().search(ZH_Q) == []

    def test_rate_limiter_used(self, monkeypatch):
        from openmind.sources import bilibili

        waits = []

        class FakeLimiter:
            def acquire(self):
                waits.append(1)

        monkeypatch.setattr(bilibili, "_LIMITER", FakeLimiter())
        monkeypatch.setattr(
            httpx,
            "get",
            lambda url, **k: httpx.Response(
                200, json={"code": 0, "data": {"result": []}}, request=httpx.Request("GET", url)
            ),
        )
        BilibiliSource().search(ZH_Q)
        assert waits == [1]

    def test_needs_no_key(self):
        assert BilibiliSource.needs_key is False
