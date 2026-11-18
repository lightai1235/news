"""T5 wiki_links 信源测试：外链分类为 article/video/paper，fixtures 驱动。"""

from openmind.sources.base import Query
from openmind.sources.wiki_links import WikiLinksSource, classify_url


class TestClassify:
    def test_youtube_is_video(self):
        assert classify_url("https://www.youtube.com/watch?v=abc") == "video"
        assert classify_url("https://youtu.be/abc") == "video"
        assert classify_url("https://www.bilibili.com/video/BV1xx") == "video"

    def test_arxiv_is_paper(self):
        assert classify_url("https://arxiv.org/abs/2201.00001") == "paper"
        assert classify_url("https://pubmed.ncbi.nlm.nih.gov/12345/") == "paper"
        assert classify_url("https://doi.org/10.1000/xyz") == "paper"

    def test_wechat_is_wechat(self):
        assert classify_url("https://mp.weixin.qq.com/s/abc") == "wechat"

    def test_default_article(self):
        assert classify_url("https://www.example.org/review") == "article"


class TestWikiLinksSource:
    def test_search_returns_classified_candidates(self, monkeypatch):
        from openmind.sources import wiki_links

        monkeypatch.setattr(
            wiki_links,
            "fetch_external_links",
            lambda title, lang="en": [
                "https://arxiv.org/abs/2201.00001",
                "https://www.youtube.com/watch?v=abc",
                "https://www.example.org/review",
            ],
        )
        monkeypatch.setattr(wiki_links, "fetch_reference_links", lambda t, lang="en": [])
        src = WikiLinksSource()
        cands = src.search(Query(title="Bioacoustics", lang="en"))
        assert len(cands) == 3
        kinds = {c.kind for c in cands}
        assert kinds == {"paper", "video", "article"}
        assert all(c.source == "wiki_links" for c in cands)

    def test_failure_returns_empty(self, monkeypatch):
        from openmind.sources import wiki_links

        def boom(*a, **k):
            raise RuntimeError("down")

        monkeypatch.setattr(wiki_links, "fetch_external_links", boom)
        monkeypatch.setattr(wiki_links, "fetch_reference_links", boom)
        assert WikiLinksSource().search(Query(title="X", lang="en")) == []

    def test_references_fallback_when_no_extlinks(self, monkeypatch):
        # 真实运行复现：部分词条 externallinks 为空，参考文献应兜底
        from openmind.sources import wiki_links

        monkeypatch.setattr(wiki_links, "fetch_external_links", lambda t, lang="en": [])
        monkeypatch.setattr(
            wiki_links,
            "fetch_reference_links",
            lambda t, lang="en": [
                "https://doi.org/10.1000/ref1",
                "https://www.example.org/ref2",
            ],
        )
        cands = WikiLinksSource().search(Query(title="心室", lang="zh"))
        assert len(cands) == 2
        assert {c.kind for c in cands} == {"paper", "article"}
        assert all(c.meta.get("origin") == "wiki_reference" for c in cands)

    def test_extlinks_and_references_merged_deduped(self, monkeypatch):
        from openmind.sources import wiki_links

        monkeypatch.setattr(
            wiki_links,
            "fetch_external_links",
            lambda t, lang="en": ["https://arxiv.org/abs/1", "https://example.org/a"],
        )
        monkeypatch.setattr(
            wiki_links,
            "fetch_reference_links",
            lambda t, lang="en": ["https://arxiv.org/abs/1", "https://example.org/b"],
        )
        cands = WikiLinksSource().search(Query(title="X", lang="en"))
        urls = [c.url for c in cands]
        assert len(urls) == len(set(urls)) == 3

    def test_needs_no_key(self):
        assert WikiLinksSource.needs_key is False
