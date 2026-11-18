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
