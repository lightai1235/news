"""T7 render 测试：卡片结构、禁词硬约束、归档索引、RSS 可解析、确定性。"""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from openmind.brief import EntryBrief
from openmind.render import Issue, render_issue
from openmind.sources.base import Candidate

FORBIDDEN = ("更多", "相关推荐", "猜你喜欢")


def make_issue(date: str = "2026-11-19") -> Issue:
    briefs = [
        EntryBrief(
            title="Bioacoustics",
            zh_title="生物声学",
            domain="生物",
            lang="en",
            brief="生物声学是研究动物声音的学科。",
            zh_absent=False,
            wiki_url="https://en.wikipedia.org/wiki/Bioacoustics",
        ),
        EntryBrief(
            title="Obscure history",
            zh_title="",
            domain="历史",
            lang="en",
            brief="English only extract.",
            zh_absent=True,
            wiki_url="https://en.wikipedia.org/wiki/Obscure_history",
        ),
        EntryBrief(
            title="拓扑学",
            zh_title="拓扑学",
            domain="数学",
            lang="zh",
            brief="拓扑学研究空间在连续变形下不变的性质。",
            zh_absent=False,
            wiki_url="https://zh.wikipedia.org/wiki/拓扑学",
        ),
    ]
    items = {
        "Bioacoustics": [
            Candidate(
                url="https://arxiv.org/abs/1234.5678",
                title="Bioacoustics survey",
                kind="paper",
                source="wiki_links",
                score=7.4,
                reason="权威域名 · 论文 · 相关度1.0",
            ),
            Candidate(
                url="https://www.youtube.com/watch?v=abc",
                title="Animal sounds explained",
                kind="video",
                source="wiki_links",
                score=5.2,
                reason="视频 · 相关度0.8",
            ),
        ],
        "Obscure history": [],
        "拓扑学": [
            Candidate(
                url="https://mp.weixin.qq.com/s/xyz",
                title="拓扑学入门",
                kind="wechat",
                source="wiki_links",
                score=4.1,
                reason="相关度0.9",
            )
        ],
    }
    return Issue(
        date=date,
        briefs=briefs,
        items=items,
        generated_at="2026-11-19T06:05:00+08:00",
        sources_ok=3,
        sources_total=12,
        base_url="https://lightai1235.github.io/news",
    )


@pytest.fixture()
def site(tmp_path: Path) -> tuple[Path, Issue]:
    issue = make_issue()
    render_issue(issue, tmp_path)
    return tmp_path, issue


class TestRenderFiles:
    def test_files_created(self, site):
        root, issue = site
        assert (root / "index.html").exists()
        assert (root / "archive" / f"{issue.date}.html").exists()
        assert (root / "archive" / "index.html").exists()
        assert (root / "feed.xml").exists()

    def test_index_equals_daily_modulo_nav_paths(self, site):
        # 根目录与 archive/ 深度不同，导航相对路径合法差异，正文必须一致
        root, issue = site
        idx = (root / "index.html").read_text(encoding="utf-8")
        arc = (root / "archive" / f"{issue.date}.html").read_text(encoding="utf-8")
        assert (
            idx.replace('href="feed.xml"', 'href="../feed.xml"').replace(
                'href="archive/index.html"', 'href="index.html"'
            )
            == arc
        )


class TestPageContent:
    def test_three_cards_with_domains(self, site):
        root, _ = site
        html = (root / "index.html").read_text(encoding="utf-8")
        assert html.count('class="card"') == 3
        for domain in ("生物", "历史", "数学"):
            assert domain in html

    def test_badges_and_reasons(self, site):
        root, _ = site
        html = (root / "index.html").read_text(encoding="utf-8")
        assert "论文" in html and "视频" in html and "公众号" in html
        assert "权威域名" in html
        assert "https://arxiv.org/abs/1234.5678" in html

    def test_zh_absent_marked(self, site):
        root, _ = site
        html = (root / "index.html").read_text(encoding="utf-8")
        assert "暂无中文摘要" in html

    def test_few_sources_marked(self, site):
        root, _ = site
        html = (root / "index.html").read_text(encoding="utf-8")
        assert "来源较少" in html  # Obscure history 0 条

    def test_footer_health(self, site):
        root, _ = site
        html = (root / "index.html").read_text(encoding="utf-8")
        assert "本期信源：3/12 可用" in html

    def test_generated_at_shown(self, site):
        root, _ = site
        html = (root / "index.html").read_text(encoding="utf-8")
        assert "生成于" in html and "2026-11-19" in html

    def test_no_forbidden_words(self, site):
        root, _ = site
        for f in root.rglob("*.html"):
            html = f.read_text(encoding="utf-8")
            for word in FORBIDDEN:
                assert word not in html, f"{f} 含禁词 {word}"

    def test_no_tracking_or_infinite_scroll(self, site):
        root, _ = site
        html = (root / "index.html").read_text(encoding="utf-8")
        assert "<script" not in html.lower()
        assert "analytics" not in html.lower()


class TestArchiveIndex:
    def test_month_grouping(self, tmp_path):
        render_issue(make_issue("2026-11-19"), tmp_path)
        render_issue(make_issue("2026-11-18"), tmp_path)
        render_issue(make_issue("2026-10-31"), tmp_path)
        html = (tmp_path / "archive" / "index.html").read_text(encoding="utf-8")
        assert "2026-11" in html and "2026-10" in html
        assert html.index("2026-11") < html.index("2026-10")  # 新月在前
        assert html.index("2026-11-19") < html.index("2026-11-18")  # 新日在前
        assert 'href="2026-10-31.html"' in html

    def test_rerender_same_date_no_duplicate(self, tmp_path):
        render_issue(make_issue("2026-11-19"), tmp_path)
        render_issue(make_issue("2026-11-19"), tmp_path)
        html = (tmp_path / "archive" / "index.html").read_text(encoding="utf-8")
        assert html.count('href="2026-11-19.html"') == 1


class TestFeed:
    def test_rss_parses(self, site):
        root, _ = site
        tree = ET.parse(root / "feed.xml")
        rss = tree.getroot()
        assert rss.tag == "rss"
        assert rss.get("version") == "2.0"
        items = rss.findall("./channel/item")
        assert len(items) == 1  # 每期一个 item，内含 3 词条摘要

    def test_feed_item_links_and_content(self, site):
        root, _ = site
        tree = ET.parse(root / "feed.xml")
        items = tree.getroot().findall("./channel/item")
        first = items[0]
        assert first.findtext("title")
        desc = first.findtext("description") or ""
        for name in ("生物声学", "Obscure history", "拓扑学"):
            assert name in desc  # 3 词条摘要都在同一 item 内
        assert first.findtext("link", "").endswith("archive/2026-11-19.html")
        assert first.findtext("guid")

    def test_feed_escaped_urls(self, site):
        root, _ = site
        raw = (root / "feed.xml").read_text(encoding="utf-8")
        assert "拓扑学" in raw  # 中文标题合法
        ET.fromstring(raw)  # 无未转义 & 等


class TestDeterminism:
    def test_same_input_same_bytes(self, tmp_path):
        a, b = tmp_path / "a", tmp_path / "b"
        render_issue(make_issue(), a)
        render_issue(make_issue(), b)
        for name in ("index.html", "feed.xml", "archive/index.html"):
            assert (a / name).read_bytes() == (b / name).read_bytes()
