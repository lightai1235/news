"""T4 维基 API 封装测试（fixtures 回放，零网络）。"""

import json
from pathlib import Path

import httpx
import pytest

from openmind import wiki

FIX = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def mock_api(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        action = params.get("action")
        if action == "query":
            prop = params.get("prop", "")
            if "externallinks" in prop:
                return httpx.Response(
                    200, json=json.loads((FIX / "wiki_extlinks.json").read_text(encoding="utf-8"))
                )
            if params.get("list") == "backlinks":
                return httpx.Response(
                    200, json=json.loads((FIX / "wiki_redirects.json").read_text(encoding="utf-8"))
                )
            if "extracts" in prop:
                return httpx.Response(
                    200, json=json.loads((FIX / "wiki_summary.json").read_text(encoding="utf-8"))
                )
            if "langlinks" in prop:
                return httpx.Response(
                    200, json=json.loads((FIX / "wiki_langlinks.json").read_text(encoding="utf-8"))
                )
        return httpx.Response(400, json={"error": "unexpected"})

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def factory(*a, **k):
        k["transport"] = transport
        return real_client(*a, **k)

    monkeypatch.setattr(wiki.httpx, "Client", factory)


class TestWiki:
    def test_summary_returns_extract(self, mock_api):
        info = wiki.fetch_article("Bioacoustics", lang="en")
        assert info.title == "Bioacoustics"
        assert "sound" in info.extract.lower()

    def test_langlinks_zh_title(self, mock_api):
        info = wiki.fetch_article("Bioacoustics", lang="en")
        assert info.zh_title == "生物声学"

    def test_external_links(self, mock_api):
        links = wiki.fetch_external_links("Bioacoustics", lang="en")
        assert "https://www.example.org/bioacoustics-review" in links
        assert len(links) >= 2

    def test_redirects_aliases(self, mock_api):
        aliases = wiki.fetch_aliases("Bioacoustics", lang="en")
        assert "Animal acoustics" in aliases

    def test_reference_links_extracted_and_filtered(self, monkeypatch):
        html = (
            '<ref><a href="https://doi.org/10.1000/xyz">doi</a></ref>'
            '<ref><a href="https://www.jstor.org/stable/123">J</a></ref>'
            '<a href="https://en.wikipedia.org/wiki/X">internal</a>'
            '<img src="https://upload.wikimedia.org/x.png"/>'
            "<ref>https://example.org/paper.pdf.</ref>"
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"parse": {"title": "X", "text": html}})

        real_client = httpx.Client
        transport = httpx.MockTransport(handler)
        monkeypatch.setattr(
            wiki.httpx,
            "Client",
            lambda *a, **k: real_client(*a, **{**k, "transport": transport}),
        )
        urls = wiki.fetch_reference_links("X", lang="en")
        assert "https://doi.org/10.1000/xyz" in urls
        assert "https://www.jstor.org/stable/123" in urls
        assert "https://example.org/paper.pdf" in urls  # 尾部句点剥离
        assert not any("wikipedia.org" in u or "wikimedia.org" in u for u in urls)

    def test_reference_links_ignore_non_ref_body(self, monkeypatch):
        # A 方案：只取 <ref> 块内 URL；正文信息框/坐标/导航噪声一律不收
        html = (
            '<div class="infobox"><a href="https://geohack.toolforge.org/geohack.php?x=1">geo</a>'
            '<a href="https://www.fcc.gov/设施数据库">fcc</a></div>'
            '<a xmlns="http://www.w3.org/1998/Math/MathML">m</a>'
            '<ref><a href="https://example.org/cited">cited</a></ref>'
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"parse": {"title": "X", "text": html}})

        real_client = httpx.Client
        transport = httpx.MockTransport(handler)
        monkeypatch.setattr(
            wiki.httpx,
            "Client",
            lambda *a, **k: real_client(*a, **{**k, "transport": transport}),
        )
        urls = wiki.fetch_reference_links("X", lang="en")
        assert urls == ["https://example.org/cited"]

    def test_reference_links_named_and_selfclosed_refs(self, monkeypatch):
        html = (
            '<ref name="a"><a href="https://example.org/one">1</a></ref>'
            '<ref name="a" />'  # 复用引用不重复贡献 URL
            '<ref name="b" group="note"><a href="https://example.org/two">2</a></ref>'
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"parse": {"title": "X", "text": html}})

        real_client = httpx.Client
        transport = httpx.MockTransport(handler)
        monkeypatch.setattr(
            wiki.httpx,
            "Client",
            lambda *a, **k: real_client(*a, **{**k, "transport": transport}),
        )
        urls = wiki.fetch_reference_links("X", lang="en")
        assert urls == ["https://example.org/one", "https://example.org/two"]

    def test_reference_links_exclude_wikidata_and_infra(self, monkeypatch):
        html = (
            '<ref><a href="https://www.wikidata.org/wiki/Q42">wd</a></ref>'
            '<ref><a href="https://www.wikidata.org/entity/Q42">wd2</a></ref>'
            '<ref><a href="https://geohack.toolforge.org/geohack.php">geo</a></ref>'
            '<ref><a href="http://www.w3.org/1999/xhtml">ns</a></ref>'
            '<ref><a href="https://example.org/ok">ok</a></ref>'
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"parse": {"title": "X", "text": html}})

        real_client = httpx.Client
        transport = httpx.MockTransport(handler)
        monkeypatch.setattr(
            wiki.httpx,
            "Client",
            lambda *a, **k: real_client(*a, **{**k, "transport": transport}),
        )
        assert wiki.fetch_reference_links("X", lang="en") == ["https://example.org/ok"]

    def test_reference_links_archive_dedup_prefers_original(self, monkeypatch):
        # C 方案：存档链接还原为原始 URL；原始与存档同现只留一条
        html = (
            '<ref><a href="https://web.archive.org/web/20200101000000/'
            'https://example.org/page">arch</a></ref>'
            '<ref><a href="https://example.org/page">orig</a></ref>'
            '<ref><a href="http://web.archive.org/web/2015id_/http://other.org/x">arch2</a></ref>'
            '<ref><a href="https://archive.org/details/somebook">ia</a></ref>'
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"parse": {"title": "X", "text": html}})

        real_client = httpx.Client
        transport = httpx.MockTransport(handler)
        monkeypatch.setattr(
            wiki.httpx,
            "Client",
            lambda *a, **k: real_client(*a, **{**k, "transport": transport}),
        )
        urls = wiki.fetch_reference_links("X", lang="en")
        # archive.org/details 是独立资源，保留
        assert urls == [
            "https://example.org/page",
            "http://other.org/x",
            "https://archive.org/details/somebook",
        ]

    def test_reference_links_archive_only_keeps_unwrapped(self, monkeypatch):
        html = (
            '<ref><a href="https://web.archive.org/web/2020/https://a.org/p">a</a></ref>'
            '<ref><a href="https://web.archive.org/web/2021/https://a.org/p">a2</a></ref>'
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"parse": {"title": "X", "text": html}})

        real_client = httpx.Client
        transport = httpx.MockTransport(handler)
        monkeypatch.setattr(
            wiki.httpx,
            "Client",
            lambda *a, **k: real_client(*a, **{**k, "transport": transport}),
        )
        # 不同时间戳的同一原始 URL 归一为一条
        assert wiki.fetch_reference_links("X", lang="en") == ["https://a.org/p"]

    def test_reference_links_failure_returns_empty(self, monkeypatch):
        def boom(*a, **k):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(wiki.httpx, "Client", boom)
        assert wiki.fetch_reference_links("X", lang="en") == []

    def test_failure_returns_empty_not_raise(self, monkeypatch):
        def boom(*a, **k):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(wiki.httpx, "Client", boom)
        info = wiki.fetch_article("X", lang="en")
        assert info.extract == ""
        assert wiki.fetch_external_links("X", lang="en") == []
        assert wiki.fetch_aliases("X", lang="en") == []
