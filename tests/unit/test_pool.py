"""T2 候选池解析测试（fixtures 驱动，零网络）。"""

from pathlib import Path

import pytest

from openmind.compliance import Compliance
from openmind.pool import DOMAINS, parse_wikitext

FIXTURE = Path(__file__).parent.parent / "fixtures" / "ga_sample.wiki"


@pytest.fixture()
def comp(tmp_path: Path) -> Compliance:
    for name in ("denylist_topics.txt", "denylist_domains.txt", "allowlist_domains.txt"):
        (tmp_path / name).write_text("", encoding="utf-8")
    return Compliance.load(tmp_path)


@pytest.fixture()
def entries(comp):
    return parse_wikitext(FIXTURE.read_text(encoding="utf-8"), lang="en", comp=comp)


class TestParse:
    def test_extracts_titles(self, entries):
        titles = {e.canonical_title for e in entries}
        assert "Bioacoustics" in titles
        assert "Photosynthesis" in titles
        assert "Byzantine Empire" in titles

    def test_every_entry_has_domain_in_12(self, entries):
        assert len(entries) > 10
        for e in entries:
            assert e.domain in DOMAINS
            assert e.canonical_title
            assert e.lang == "en"

    def test_domain_mapping_correct(self, entries):
        by_title = {e.canonical_title: e.domain for e in entries}
        assert by_title["Game theory"] == "数学"
        assert by_title["Byzantine Empire"] == "历史"
        assert by_title["Great Barrier Reef"] == "地理"
        assert by_title["Jazz"] == "艺术"
        assert by_title["Antibiotic resistance"] == "医学健康"
        assert by_title["Contract theory"] == "社会"

    def test_fiction_section_excluded(self, entries):
        titles = {e.canonical_title for e in entries}
        assert "Elden Ring" not in titles
        assert "Minecraft" not in titles

    def test_fiction_title_in_reality_section_excluded(self, entries):
        titles = {e.canonical_title for e in entries}
        assert "Dune (novel)" not in titles
        assert "Novel" in titles

    def test_piped_link_uses_target(self, comp):
        entries = parse_wikitext(
            "==Mathematics==\n* [[Topology|topological spaces]]\n", lang="en", comp=comp
        )
        assert entries[0].canonical_title == "Topology"

    def test_no_duplicates(self, comp):
        text = "==Mathematics==\n* [[Game theory]]\n* [[Game theory]]\n"
        entries = parse_wikitext(text, lang="en", comp=comp)
        assert len(entries) == 1

    def test_empty_text_yields_empty(self, comp):
        assert parse_wikitext("", lang="en", comp=comp) == []

    def test_all_sources_failed_keeps_existing_pool(self, tmp_path, monkeypatch):
        import json
        import time

        from openmind import pool as pool_mod

        existing = {
            "built_at": time.time(),
            "entries": [
                {
                    "canonical_title": "Bioacoustics",
                    "lang": "en",
                    "domain": "自然科学",
                    "section": "x",
                }
            ],
        }
        (tmp_path / "pool.json").write_text(json.dumps(existing), encoding="utf-8")
        for name in ("denylist_topics.txt", "denylist_domains.txt", "allowlist_domains.txt"):
            (tmp_path / name).write_text("", encoding="utf-8")

        def boom(*a, **k):
            raise RuntimeError("network down")

        monkeypatch.setattr(pool_mod, "_crawl", boom)
        monkeypatch.setattr(pool_mod.time, "sleep", lambda s: None)
        result = pool_mod.build_pool(tmp_path, refresh=True)
        assert [e.canonical_title for e in result] == ["Bioacoustics"]
        on_disk = json.loads((tmp_path / "pool.json").read_text(encoding="utf-8"))
        assert on_disk["entries"] == existing["entries"]

    def test_zh_sections_map(self, comp):
        text = "==数学==\n* [[博弈论]]\n==历史==\n* [[拜占庭帝国]]\n"
        entries = parse_wikitext(text, lang="zh", comp=comp)
        by_title = {e.canonical_title: e.domain for e in entries}
        assert by_title["博弈论"] == "数学"
        assert by_title["拜占庭帝国"] == "历史"
        assert all(e.lang == "zh" for e in entries)
