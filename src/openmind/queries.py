"""查询扩展廉价版（SPEC §5.3，无 LLM 路径）。

别名来自维基 redirects + 跨语言中文标题；关键术语取首段名词短语；
产出精确 / 概念 / 中文 2–3 组差异化查询。LLM 增强在 T16 接线。
"""

from __future__ import annotations

import re

from openmind.sources.base import Query
from openmind.wiki import ArticleInfo

_STOPWORDS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "of",
    "in",
    "on",
    "and",
    "or",
    "to",
    "for",
    "with",
    "by",
    "as",
    "at",
    "from",
    "that",
    "this",
    "it",
    "its",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "not",
    "study",
    "studies",
    "research",
    "field",
    "branch",
    "type",
    "kind",
    "form",
    "used",
    "using",
    "use",
    "known",
    "also",
    "which",
    "who",
    "whom",
    "whose",
    "can",
    "may",
    "often",
    "usually",
    "between",
    "among",
    "about",
    "into",
}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z-]{3,}")


def _keywords(extract: str, title: str, limit: int = 4) -> list[str]:
    title_words = {w.lower() for w in title.split()}
    seen: list[str] = []
    for m in _WORD_RE.finditer(extract):
        w = m.group(0).lower()
        if w in _STOPWORDS or w in title_words or w in seen:
            continue
        seen.append(w)
        if len(seen) >= limit:
            break
    return seen


def build_queries(info: ArticleInfo) -> Query:
    aliases: list[str] = []
    if info.zh_title and info.zh_title != info.title:
        aliases.append(info.zh_title)
    for a in info.aliases:
        if a != info.title and a not in aliases:
            aliases.append(a)

    groups: dict[str, str] = {"exact": f'"{info.title}" review'}

    kws = _keywords(info.extract, info.title)
    if kws:
        groups["concept"] = " ".join(kws[:3]) + " research"

    if info.zh_title:
        groups["zh"] = f"{info.zh_title} 研究 科普"

    return Query(title=info.title, lang=info.lang, aliases=aliases, groups=groups)
