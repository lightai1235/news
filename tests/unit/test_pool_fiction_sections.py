"""真实运行复现：1910s films 分区漏进池（A Free Ride 被抽中）。

SPEC 要求排除虚构作品本体（电影/电视剧/小说/游戏），但电影史、
视频游戏史等现实研究主题保留。分区级规则必须区分这两类。
"""

from pathlib import Path

import pytest

from openmind.compliance import Compliance
from openmind.pool import parse_wikitext


@pytest.fixture()
def comp(tmp_path: Path) -> Compliance:
    for name in ("denylist_topics.txt", "denylist_domains.txt", "allowlist_domains.txt"):
        (tmp_path / name).write_text("", encoding="utf-8")
    return Compliance.load(tmp_path)


class TestFictionWorkSections:
    def test_decade_films_section_excluded(self, comp):
        text = "=1910s films=\n* [[A Free Ride]]\n* [[The Great Train Robbery (1903 film)]]\n"
        assert parse_wikitext(text, lang="en", comp=comp) == []

    def test_year_range_films_section_excluded(self, comp):
        text = "= 2010 to 2014 films =\n* [[Inception]]\n"
        assert parse_wikitext(text, lang="en", comp=comp) == []

    def test_pre_1910s_films_excluded(self, comp):
        text = "=Pre-1910s films=\n* [[Some Old Film]]\n"
        assert parse_wikitext(text, lang="en", comp=comp) == []

    def test_tv_series_and_episodes_excluded(self, comp):
        text = (
            "=Other television series, 2010s debuts=\n* [[Breaking Bad]]\n"
            "==Episodes of television==\n* [[Ozymandias (Breaking Bad)]]\n"
            "==Television shows==\n* [[Some Show]]\n"
        )
        assert parse_wikitext(text, lang="en", comp=comp) == []

    def test_named_franchise_sections_excluded(self, comp):
        text = (
            "=''Law & Order'' series=\n* [[Law & Order: SVU]]\n"
            "=''Parks and Recreation''=\n* [[Parks and Recreation season 1]]\n"
            "==''Kingdom Hearts'' characters==\n* [[Sora (Kingdom Hearts)]]\n"
        )
        assert parse_wikitext(text, lang="en", comp=comp) == []

    def test_fictional_characters_sections_excluded(self, comp):
        text = (
            "==Fictional characters (literature and theatre)==\n* [[Hamlet (character)]]\n"
            "==Media fictional characters==\n* [[Some Character]]\n"
        )
        assert parse_wikitext(text, lang="en", comp=comp) == []

    def test_zh_fiction_sections_excluded(self, comp):
        text = (
            "==流行音樂歌曲==\n[[某歌曲]]\n"
            "==流行音樂專輯==\n[[某專輯]]\n"
            "==傳播媒體虛構元素==\n[[某虛構元素]]\n"
            "==虚构文学==\n[[某小说]]\n"
            "==欧美文学和文學作品==\n[[某作品]]\n"
            "==其他傳播媒體作品==\n[[某媒體作品]]\n"
        )
        assert parse_wikitext(text, lang="zh", comp=comp) == []


class TestRealitySectionsKept:
    def test_film_history_and_production_kept(self, comp):
        text = (
            "==Film franchises, overview articles and production articles==\n"
            "* [[History of film]]\n* [[Film noir]]\n"
        )
        entries = parse_wikitext(text, lang="en", comp=comp)
        assert {e.canonical_title for e in entries} == {"History of film", "Film noir"}

    def test_video_game_history_kept(self, comp):
        # 真实结构：父分区 Engineering and technology 提供领域映射
        text = (
            "==Engineering and technology==\n"
            "===Video game history and development===\n* [[History of video games]]\n"
        )
        entries = parse_wikitext(text, lang="en", comp=comp)
        assert [e.canonical_title for e in entries] == ["History of video games"]
        assert entries[0].domain == "技术工程"

    def test_tv_networks_overview_kept(self, comp):
        text = "==Media==\n===Television networks and overview articles===\n* [[BBC]]\n"
        entries = parse_wikitext(text, lang="en", comp=comp)
        assert [e.canonical_title for e in entries] == ["BBC"]

    def test_music_theory_and_people_kept(self, comp):
        text = (
            "==Music==\n"
            "===Musical theory, musical instruments, and music techniques===\n* [[Counterpoint]]\n"
            "===Music genres, music styles, music eras===\n* [[Jazz]]\n"
        )
        entries = parse_wikitext(text, lang="en", comp=comp)
        assert {e.canonical_title for e in entries} == {"Counterpoint", "Jazz"}

    def test_theatre_opera_overview_kept(self, comp):
        text = "==Theatre, musical theatre, dance, and opera==\n* [[Opera]]\n"
        entries = parse_wikitext(text, lang="en", comp=comp)
        assert [e.canonical_title for e in entries] == ["Opera"]

    def test_classical_music_works_kept(self, comp):
        # 古典乐曲是非虚构艺术条目（乐谱/研究），与流行歌曲/专辑区分
        text = "==Classical music works==\n* [[Symphony No. 9 (Beethoven)]]\n"
        entries = parse_wikitext(text, lang="en", comp=comp)
        assert len(entries) == 1

    def test_zh_game_hardware_culture_kept(self, comp):
        text = "==電子遊戲硬體、服務與文化==\n[[任天堂]]\n"
        entries = parse_wikitext(text, lang="zh", comp=comp)
        assert [e.canonical_title for e in entries] == ["任天堂"]

    def test_zh_nonfiction_literature_kept(self, comp):
        text = "==非文學作品==\n[[某非虚构]]\n==非虚构类文学==\n[[某纪实]]\n"
        entries = parse_wikitext(text, lang="zh", comp=comp)
        assert len(entries) == 2

    def test_law_and_order_case_law_not_confused(self, comp):
        # "Law & Order" 剧集分区排除，但 Case law 真实法律分区不受影响
        text = "=Case law and litigation=\n* [[Roe v. Wade]]\n"
        entries = parse_wikitext(text, lang="en", comp=comp, default_section="Law")
        assert [e.canonical_title for e in entries] == ["Roe v. Wade"]

    def test_child_of_fiction_section_excluded(self, comp):
        # FA 真实结构：====20th Century==== 本身无关键词，父分区 ===Films=== 是作品区
        text = (
            "==Media==\n===Films===\n====20th Century (1900–1999)====\n"
            "* [[Blade Runner]]\n===Media biographies===\n* [[Some Director]]\n"
        )
        entries = parse_wikitext(text, lang="en", comp=comp)
        assert [e.canonical_title for e in entries] == ["Some Director"]
