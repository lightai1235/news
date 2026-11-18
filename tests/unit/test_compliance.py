"""T2 合规/虚构过滤测试。

注：话题级政治过滤只测机制（denylist 命中/未命中），涉政边界样本暂不编写
（2026-11-18 用户指示）；话题词条由用户自行维护。
"""

from pathlib import Path

import pytest

from openmind.compliance import Compliance


@pytest.fixture()
def comp(tmp_path: Path) -> Compliance:
    (tmp_path / "denylist_topics.txt").write_text("# 用户维护\n", encoding="utf-8")
    (tmp_path / "denylist_domains.txt").write_text(
        "spamfarm.example\njunkseo.example\n", encoding="utf-8"
    )
    (tmp_path / "allowlist_domains.txt").write_text("arxiv.org\nnature.com\n", encoding="utf-8")
    return Compliance.load(tmp_path)


class TestFictionFilter:
    @pytest.mark.parametrize(
        "title",
        [
            "Harry Potter",
            "The Lord of the Rings",
            "Genshin Impact",
            "Naruto",
            "Elden Ring",
            "Sherlock Holmes",
            "Middle-earth",
            "The Matrix",
            "Pokémon Red and Blue",
            "Dune (novel)",
            "One Piece",
            "Devdas (2002 Hindi film)",
            "Breaking Bad (TV series)",
        ],
    )
    def test_fiction_titles_rejected(self, comp, title):
        ok, reason = comp.check_entry(title, categories=["Novels", "Fictional characters"])
        assert not ok
        assert reason

    @pytest.mark.parametrize(
        "title",
        [
            "Bioacoustics",
            "Novel",
            "Video game industry",
            "Dream of the Red Chamber studies",
            "Game theory",
            "Photosynthesis",
            "Byzantine Empire",
            "Topology",
            "Jazz",
            "Great Barrier Reef",
            "Immunology",
        ],
    )
    def test_nonfiction_titles_accepted(self, comp, title):
        ok, reason = comp.check_entry(title, categories=["Science", "History"])
        assert ok
        assert reason == ""

    def test_category_alone_can_reject(self, comp):
        ok, reason = comp.check_entry("Some obscure work", categories=["Video games", "Anime"])
        assert not ok
        assert "category" in reason.lower() or "虚构" in reason

    def test_reality_category_does_not_reject(self, comp):
        ok, _ = comp.check_entry(
            "Video game industry", categories=["Video game industry", "Economy"]
        )
        assert ok


class TestListAndDisambiguation:
    def test_list_page_rejected(self, comp):
        ok, _ = comp.check_entry("List of tallest buildings", categories=["Lists"])
        assert not ok

    def test_disambiguation_rejected(self, comp):
        ok, _ = comp.check_entry("Mercury (disambiguation)", categories=["Disambiguation pages"])
        assert not ok


class TestDomainFilter:
    def test_denylisted_domain_rejected(self, comp):
        ok, reason = comp.check_url("https://spamfarm.example/article/1")
        assert not ok
        assert reason

    def test_subdomain_of_denylisted_rejected(self, comp):
        ok, _ = comp.check_url("https://www.spamfarm.example/x")
        assert not ok

    def test_clean_domain_accepted(self, comp):
        ok, reason = comp.check_url("https://www.bbc.com/news/science")
        assert ok
        assert reason == ""

    def test_allowlist_boost_flag(self, comp):
        assert comp.is_authoritative("https://arxiv.org/abs/2201.00001")
        assert comp.is_authoritative("https://www.nature.com/articles/x")
        assert not comp.is_authoritative("https://random-blog.example/x")

    def test_lookalike_domain_not_allowlisted(self, comp):
        assert not comp.is_authoritative("https://arxiv.org.evil.example/x")


class TestTopicDenylistMechanism:
    def test_user_maintained_topic_hit(self, tmp_path):
        (tmp_path / "denylist_topics.txt").write_text("某用户自定义词条\n", encoding="utf-8")
        (tmp_path / "denylist_domains.txt").write_text("", encoding="utf-8")
        (tmp_path / "allowlist_domains.txt").write_text("", encoding="utf-8")
        c = Compliance.load(tmp_path)
        ok, reason = c.check_entry("某用户自定义词条", categories=[])
        assert not ok
        assert "topic" in reason.lower() or "话题" in reason

    def test_comment_and_blank_lines_ignored(self, tmp_path):
        (tmp_path / "denylist_topics.txt").write_text("# 注释\n\n  \n词条A\n", encoding="utf-8")
        (tmp_path / "denylist_domains.txt").write_text("", encoding="utf-8")
        (tmp_path / "allowlist_domains.txt").write_text("", encoding="utf-8")
        c = Compliance.load(tmp_path)
        assert c.check_entry("词条A", categories=[])[0] is False
        assert c.check_entry("词条B", categories=[])[0] is True
