"""合规与虚构过滤（SPEC §5.5，三层，可配置可审计）。

- 话题级：denylist_topics.txt 纯文本关键词/条目名，由用户自行维护，命中即排除。
- 条目级：虚构作品本体（小说/游戏/动漫/虚构角色等）排除；现实研究主题保留。
- 来源级：denylist_domains.txt 一票否决；allowlist_domains.txt 供评分加权。

所有判定返回 (ok, reason)，reason 为空表示通过；拒绝必须带可审计理由。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger(__name__)

FICTION_TITLE_PATTERNS = [
    r"\(novel\)",
    r"\(video game\)",
    r"\(film\)",
    r"\(\d{4}[^)]*film\)",
    r"\(TV series\)",
    r"\(\d{4}[^)]*TV series\)",
    r"\(anime\)",
    r"\(manga\)",
    r"\(comics\)",
    r"\(character\)",
    r"\(fictional",
    r"\bHarry Potter\b",
    r"\bLord of the Rings\b",
    r"\bMiddle-earth\b",
    r"\bNaruto\b",
    r"\bOne Piece\b",
    r"\bGenshin Impact\b",
    r"\bElden Ring\b",
    r"\bMinecraft\b",
    r"\bSherlock Holmes\b",
    r"\bThe Matrix\b",
    r"\bPokémon\b",
]

FICTION_CATEGORY_KEYWORDS = [
    "novel",
    "fictional",
    "video game",
    "anime",
    "manga",
    "comics character",
    "fantasy world",
    "fictional character",
    "fictional location",
    "television series",
    "television episodes",
    "film series",
    "light novel",
    "concert film",
    "concert films",
    "albums",
    "songs",
    "films",
]

REALITY_CATEGORY_HINTS = [
    "industry",
    "studies",
    "theory",
    "history of",
    "criticism",
    "genre",
    "business",
    "development",
    "culture",
    "research",
]

EXCLUDE_CATEGORY_KEYWORDS = ["disambiguation", "lists of", "set indices"]


@dataclass
class Compliance:
    topic_denylist: list[str]
    domain_denylist: set[str]
    domain_allowlist: set[str]

    @classmethod
    def load(cls, state_dir: Path) -> Compliance:
        def read_lines(name: str) -> list[str]:
            p = state_dir / name
            if not p.exists():
                return []
            return [
                ln.strip()
                for ln in p.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.strip().startswith("#")
            ]

        return cls(
            topic_denylist=read_lines("denylist_topics.txt"),
            domain_denylist={d.lower() for d in read_lines("denylist_domains.txt")},
            domain_allowlist={d.lower() for d in read_lines("allowlist_domains.txt")},
        )

    def check_entry(self, title: str, categories: list[str]) -> tuple[bool, str]:
        low_title = title.lower()
        for topic in self.topic_denylist:
            # 不区分大小写（2026-11-18）：用户维护的词条大小写不定；中文无大小写不受影响
            if topic and topic.lower() in low_title:
                reason = f"话题级 denylist 命中: {topic}"
                log.info("entry rejected %r: %s", title, reason)
                return False, reason

        if "(disambiguation)" in low_title or low_title.startswith("list of "):
            reason = "列表页/消歧义页排除"
            log.info("entry rejected %r: %s", title, reason)
            return False, reason

        for pat in FICTION_TITLE_PATTERNS:
            if re.search(pat, title, re.IGNORECASE):
                reason = f"虚构作品标题模式命中: {pat}"
                log.info("entry rejected %r: %s", title, reason)
                return False, reason

        cats_low = [c.lower() for c in categories]
        if any(any(k in c for k in EXCLUDE_CATEGORY_KEYWORDS) for c in cats_low):
            reason = "category 命中列表/消歧义排除"
            log.info("entry rejected %r: %s", title, reason)
            return False, reason

        reality = any(any(h in c for h in REALITY_CATEGORY_HINTS) for c in cats_low)
        if not reality:
            for c in cats_low:
                for k in FICTION_CATEGORY_KEYWORDS:
                    if k in c:
                        reason = f"虚构 category 命中: {c}"
                        log.info("entry rejected %r: %s", title, reason)
                        return False, reason
        return True, ""

    def check_fulltext(self, title: str, text: str) -> tuple[bool, str]:
        """全文复核（2026-11-18 用户要求）：标题干净但正文夹带 denylist 关键词也要拦。

        只对最终要推出的 3 条调用（效率约束）；不区分大小写，与话题级一致。
        """
        haystack = f"{title}\n{text}".lower()
        for topic in self.topic_denylist:
            if topic and topic.lower() in haystack:
                reason = f"全文复核 denylist 命中: {topic}"
                log.info("entry fulltext rejected %r: %s", title, reason)
                return False, reason
        return True, ""

    def check_url(self, url: str) -> tuple[bool, str]:
        host = (urlparse(url).hostname or "").lower()
        for bad in self.domain_denylist:
            if host == bad or host.endswith("." + bad):
                reason = f"来源级域名黑名单命中: {bad}"
                log.info("url rejected %r: %s", url, reason)
                return False, reason
        return True, ""

    def is_authoritative(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return any(host == good or host.endswith("." + good) for good in self.domain_allowlist)
