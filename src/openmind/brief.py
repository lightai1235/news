"""中文简介（SPEC §5.7 零密钥模板版）。

中文维基摘要优先（经 langlinks 跨语言取 zh 摘要）；zh 原生条目直接用自身摘要；
无中文摘要时回退英文并置 zh_absent 标记，页面显示「暂无中文摘要」。
LLM 导读版在 T16 接线，本模块保持纯函数可测。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from urllib.parse import quote

from openmind.wiki import ArticleInfo

log = logging.getLogger(__name__)

MAX_BRIEF_CHARS = 600


@dataclass
class EntryBrief:
    title: str
    zh_title: str
    domain: str
    lang: str
    brief: str
    zh_absent: bool
    wiki_url: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> EntryBrief:
        return cls(**json.loads(text))


def _wiki_url(title: str, lang: str) -> str:
    return f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"


def _default_fetch_zh(zh_title: str) -> str:
    from openmind.wiki import fetch_article

    return fetch_article(zh_title, lang="zh").extract


def _truncate(text: str) -> str:
    text = text.strip()
    if len(text) <= MAX_BRIEF_CHARS:
        return text
    return text[: MAX_BRIEF_CHARS - 2].rstrip() + "……"


def make_brief(
    info: ArticleInfo,
    domain: str,
    fetch_zh: Callable[[str], str] | None = None,
) -> EntryBrief:
    fetch = fetch_zh or _default_fetch_zh
    zh_title = info.zh_title or (info.title if info.lang == "zh" else "")
    brief = ""
    zh_absent = True

    if info.lang == "zh" and info.extract:
        brief = info.extract
        zh_absent = False
    elif zh_title:
        try:
            zh_extract = fetch(zh_title)
        except Exception as exc:
            log.warning("brief fetch zh %s failed: %s", zh_title, exc)
            zh_extract = ""
        if zh_extract:
            brief = zh_extract
            zh_absent = False

    if zh_absent:
        brief = info.extract

    return EntryBrief(
        title=info.title,
        zh_title=zh_title,
        domain=domain,
        lang=info.lang,
        brief=_truncate(brief),
        zh_absent=zh_absent,
        wiki_url=_wiki_url(info.title, info.lang),
    )
