"""维基外链信源（SPEC §5.4 L1 层，无 key，永远可用的降级底座）。"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from openmind.sources.base import Candidate, Query
from openmind.wiki import fetch_external_links, fetch_reference_links

log = logging.getLogger(__name__)

_VIDEO_HOSTS = ("youtube.com", "youtu.be", "bilibili.com", "vimeo.com", "ted.com")
_PAPER_HOSTS = (
    "arxiv.org",
    "pubmed.ncbi.nlm.nih.gov",
    "doi.org",
    "biorxiv.org",
    "medrxiv.org",
    "ssrn.com",
    "jstor.org",
    "nature.com",
    "science.org",
    "pnas.org",
    "cell.com",
    "thelancet.com",
    "nejm.org",
    "bmj.com",
)


def classify_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if any(host == h or host.endswith("." + h) for h in _VIDEO_HOSTS):
        return "video"
    if "mp.weixin.qq.com" in host:
        return "wechat"
    if any(host == h or host.endswith("." + h) for h in _PAPER_HOSTS):
        return "paper"
    return "article"


class WikiLinksSource:
    name = "wiki_links"
    needs_key = False

    def search(self, query: Query) -> list[Candidate]:
        try:
            links = fetch_external_links(query.title, lang=query.lang)
            refs = fetch_reference_links(query.title, lang=query.lang)
            out: list[Candidate] = []
            seen: set[str] = set()
            for url, origin in [(u, "wiki_externallink") for u in links] + [
                (u, "wiki_reference") for u in refs
            ]:
                if url in seen:
                    continue
                seen.add(url)
                out.append(
                    Candidate(
                        url=url,
                        title=query.title,
                        kind=classify_url(url),
                        source=self.name,
                        lang=query.lang,
                        meta={"origin": origin},
                    )
                )
            return out
        except Exception as exc:
            log.warning("wiki_links failed for %s: %s", query.title, exc)
            return []
