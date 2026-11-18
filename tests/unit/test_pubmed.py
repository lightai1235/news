"""T9 PubMed 信源测试（fixtures 回放，零网络）。"""

import json
from pathlib import Path

import httpx
import pytest

from openmind.sources.base import Query
from openmind.sources.pubmed import PubmedSource

FIX = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def mock_api(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if "esearch" in url:
            return httpx.Response(
                200,
                json=json.loads((FIX / "pubmed_esearch.json").read_text(encoding="utf-8")),
                request=httpx.Request("GET", url),
            )
        return httpx.Response(
            200,
            json=json.loads((FIX / "pubmed_esummary.json").read_text(encoding="utf-8")),
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    return calls


class TestPubmed:
    def test_candidates_kind_paper(self, mock_api):
        cands = PubmedSource().search(Query(title="Ventricle", lang="en", domain="医学健康"))
        assert len(cands) == 2
        assert all(c.kind == "paper" and c.source == "pubmed" for c in cands)
        assert cands[0].url == "https://pubmed.ncbi.nlm.nih.gov/12345678/"
        assert cands[0].title == "Ventricle regeneration in zebrafish"  # 尾点剥离

    def test_pages_and_year_metadata(self, mock_api):
        cands = PubmedSource().search(Query(title="Ventricle", lang="en", domain="医学健康"))
        assert cands[0].meta["pages"] == 13  # 1123-1135
        assert cands[0].published == "2023"
        assert cands[1].meta["pages"] == 13  # e100-e112 电子页码同样计算

    def test_only_medical_domains_trigger(self, mock_api):
        assert PubmedSource().search(Query(title="X", lang="en", domain="历史")) == []
        assert PubmedSource().search(Query(title="X", lang="en", domain="艺术")) == []
        assert mock_api == []  # 未发起任何请求

    def test_unknown_domain_still_searches(self, mock_api):
        # domain 缺席（旧数据兼容）不拦截
        cands = PubmedSource().search(Query(title="Ventricle", lang="en"))
        assert len(cands) == 2

    def test_empty_ids_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            httpx, "get", lambda url, **k: httpx.Response(
                200, json={"esearchresult": {"idlist": []}}, request=httpx.Request("GET", url)
            )
        )
        assert PubmedSource().search(Query(title="X", lang="en", domain="医学健康")) == []

    def test_failure_returns_empty(self, monkeypatch):
        def boom(*a, **k):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(httpx, "get", boom)
        assert PubmedSource().search(Query(title="X", lang="en", domain="医学健康")) == []

    def test_needs_no_key(self):
        assert PubmedSource.needs_key is False
