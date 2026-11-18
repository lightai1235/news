"""T2 修复复现 2：三种真实页面格式——FA 模板包裹链接、中文行内链接、中文分类转录。"""

from pathlib import Path

import pytest

from openmind.compliance import Compliance
from openmind.pool import extract_transclusions, parse_wikitext

FIX = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def comp(tmp_path: Path) -> Compliance:
    for name in ("denylist_topics.txt", "denylist_domains.txt", "allowlist_domains.txt"):
        (tmp_path / name).write_text("", encoding="utf-8")
    return Compliance.load(tmp_path)


def test_fa_real_parses_thousands(comp):
    entries = parse_wikitext(
        (FIX / "fa_real.wiki").read_text(encoding="utf-8"), lang="en", comp=comp
    )
    titles = {e.canonical_title for e in entries}
    assert len(entries) > 3000
    assert "Ai-Khanoum" in titles
    assert "Acra (fortress)" in titles


def test_fa_video_gaming_section_excluded(comp):
    entries = parse_wikitext(
        (FIX / "fa_real.wiki").read_text(encoding="utf-8"), lang="en", comp=comp
    )
    sections = {e.section for e in entries}
    assert not any("video gaming" in s.lower() for s in sections)


def test_zh_fa_inline_links_parse(comp):
    entries = parse_wikitext(
        (FIX / "zh_fa_real.wiki").read_text(encoding="utf-8"), lang="zh", comp=comp
    )
    titles = {e.canonical_title for e in entries}
    assert len(entries) > 300
    assert "蒙山大佛" in titles
    assert "拉斐尔" in titles


def test_zh_fa_noteTA_variant_link_uses_target(comp):
    text = (
        "== 藝術和建築 ==\n[[弗里曼特尔监狱|-{zh-cn:弗里曼特尔;zh-hk:費里曼圖}-监狱]]－[[独乐寺]]\n"
    )
    entries = parse_wikitext(text, lang="zh", comp=comp)
    assert {e.canonical_title for e in entries} == {"弗里曼特尔监狱", "独乐寺"}


def test_zh_ga_transclusions_extracted(comp):
    subs = extract_transclusions((FIX / "zh_ga_real.wiki").read_text(encoding="utf-8"))
    assert "Wikipedia:优良条目/分类/地理" in subs
    assert "Wikipedia:优良条目/分类/历史" in subs
    assert len(subs) >= 10
    assert not any("noteTA" in s or "/header" in s for s in subs)


def test_namespace_links_never_become_entries(comp):
    text = (
        "==History==\n* [[Wikipedia:Manual of Style]]\n* [[File:Example.png]]\n"
        "* [[#History|nav]]\n* [[Real article]]\n"
    )
    entries = parse_wikitext(text, lang="en", comp=comp)
    assert [e.canonical_title for e in entries] == ["Real article"]
