"""T7 brief 测试：中文摘要优先、缺席标注、纯函数确定性。"""

from openmind.brief import EntryBrief, make_brief
from openmind.wiki import ArticleInfo


class TestMakeBrief:
    def test_zh_extract_preferred(self):
        info = ArticleInfo(
            title="Bioacoustics", lang="en", extract="English intro.", zh_title="生物声学"
        )
        b = make_brief(info, domain="生物", fetch_zh=lambda t: "生物声学是研究动物声音的学科。")
        assert b.zh_title == "生物声学"
        assert b.brief == "生物声学是研究动物声音的学科。"
        assert b.zh_absent is False
        assert b.domain == "生物"

    def test_zh_entry_uses_own_extract(self):
        info = ArticleInfo(title="生物声学", lang="zh", extract="中文原生摘要。")
        b = make_brief(info, domain="生物", fetch_zh=lambda t: "不应被调用")
        assert b.brief == "中文原生摘要。"
        assert b.zh_absent is False
        assert b.zh_title == "生物声学"

    def test_no_zh_falls_back_english_with_flag(self):
        info = ArticleInfo(title="Obscure topic", lang="en", extract="English only.")
        b = make_brief(info, domain="历史", fetch_zh=lambda t: "")
        assert b.brief == "English only."
        assert b.zh_absent is True

    def test_no_zh_title_no_fetch(self):
        info = ArticleInfo(title="X", lang="en", extract="E.")
        called = []
        b = make_brief(info, domain="历史", fetch_zh=lambda t: called.append(t) or "")
        assert called == []
        assert b.zh_absent is True

    def test_fetch_failure_degrades(self):
        def boom(t):
            raise RuntimeError("network down")

        info = ArticleInfo(title="X", lang="en", extract="E.", zh_title="某条目")
        b = make_brief(info, domain="历史", fetch_zh=boom)
        assert b.brief == "E."
        assert b.zh_absent is True

    def test_long_extract_truncated(self):
        info = ArticleInfo(title="X", lang="zh", extract="字" * 1000)
        b = make_brief(info, domain="历史")
        assert len(b.brief) <= 600
        assert b.brief.endswith("……")

    def test_json_roundtrip(self):
        b = EntryBrief(
            title="Bioacoustics",
            zh_title="生物声学",
            domain="生物",
            lang="en",
            brief="简介。",
            zh_absent=False,
            wiki_url="https://en.wikipedia.org/wiki/Bioacoustics",
        )
        assert EntryBrief.from_json(b.to_json()) == b

    def test_deterministic(self):
        info = ArticleInfo(title="X", lang="en", extract="E.", zh_title="某")
        b1 = make_brief(info, domain="历史", fetch_zh=lambda t: "中文。")
        b2 = make_brief(info, domain="历史", fetch_zh=lambda t: "中文。")
        assert b1.to_json() == b2.to_json()
