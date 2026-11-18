"""T14 搜狗微信信源测试（fixtures 回放，零网络）。"""

from pathlib import Path

import httpx
import pytest

from openmind.sources.base import Query
from openmind.sources.sogou_weixin import SogouWeixinSource

FIX = Path(__file__).parent.parent / "fixtures"
ZH_Q = Query(title="Bioacoustics", lang="en", aliases=["生物声学"], groups={"zh": "生物声学 研究"})


@pytest.fixture()
def mock_api(monkeypatch):
    def fake_get(url, **kwargs):
        return httpx.Response(
            200,
            text=(FIX / "sogou_weixin.html").read_text(encoding="utf-8"),
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)


class TestSogouWeixin:
    def test_candidates_wechat_kind(self, mock_api):
        cands = SogouWeixinSource().search(ZH_Q)
        assert len(cands) == 2
        assert all(c.kind == "wechat" and c.lang == "zh" for c in cands)
        assert cands[0].title == "生物声学：倾听动物的语言"
        assert "生物声学" in cands[0].snippet

    def test_sogou_redirect_resolved(self, mock_api):
        cands = SogouWeixinSource().search(ZH_Q)
        assert cands[0].url == "https://mp.weixin.qq.com/s/abc123"
        assert cands[1].url == "https://mp.weixin.qq.com/s/def456"

    def test_no_zh_group_skips(self):
        assert SogouWeixinSource().search(Query(title="X", lang="en")) == []

    def test_antispider_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            httpx,
            "get",
            lambda url, **k: httpx.Response(
                200,
                text="请输入验证码",
                request=httpx.Request("GET", "https://weixin.sogou.com/antispider/"),
            ),
        )
        assert SogouWeixinSource().search(ZH_Q) == []

    def test_failure_returns_empty(self, monkeypatch):
        def boom(*a, **k):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(httpx, "get", boom)
        assert SogouWeixinSource().search(ZH_Q) == []

    def test_needs_no_key(self):
        assert SogouWeixinSource.needs_key is False
