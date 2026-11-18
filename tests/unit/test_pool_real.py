"""T2 修复复现：真实 Good articles/all 页面是转录索引页，直接解析得 0 条（bug）。"""

from pathlib import Path

import pytest

from openmind.compliance import Compliance
from openmind.pool import extract_transclusions, parse_wikitext

REAL = Path(__file__).parent.parent / "fixtures" / "ga_real.wiki"


@pytest.fixture()
def comp(tmp_path: Path) -> Compliance:
    for name in ("denylist_topics.txt", "denylist_domains.txt", "allowlist_domains.txt"):
        (tmp_path / name).write_text("", encoding="utf-8")
    return Compliance.load(tmp_path)


def test_real_index_page_yields_zero_directly(comp):
    entries = parse_wikitext(REAL.read_text(encoding="utf-8"), lang="en", comp=comp)
    assert entries == []


def test_extract_transclusions_finds_topic_subpages():
    subs = extract_transclusions(REAL.read_text(encoding="utf-8"))
    assert "Wikipedia:Good articles/Agriculture, food and drink" in subs
    assert "Wikipedia:Good articles/Mathematics" in subs
    assert len(subs) >= 9


def test_extract_transclusions_ignores_non_topic_templates():
    subs = extract_transclusions(REAL.read_text(encoding="utf-8"))
    assert not any("Summary" in s or "Tab header" in s or "plainlist" in s for s in subs)


def test_transcluded_topic_page_parses(comp):
    topic_page = (
        "==Agriculture, food and drink==\n"
        "===Agriculture===\n"
        "{{Wikipedia:Good articles/Agriculture, food and drink/Agriculture}}\n"
    )
    subs = extract_transclusions(topic_page)
    assert subs == ["Wikipedia:Good articles/Agriculture, food and drink/Agriculture"]


def test_leaf_list_with_section_context(comp):
    leaf = "* [[Bioacoustics]]\n* [[Compost]]\n"
    entries = parse_wikitext(
        leaf, lang="en", comp=comp, default_section="Agriculture, food and drink"
    )
    assert {e.canonical_title for e in entries} == {"Bioacoustics", "Compost"}
    assert all(e.domain == "自然科学" for e in entries)
