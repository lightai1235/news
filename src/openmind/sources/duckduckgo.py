"""DuckDuckGo ddgs 信源（SPEC §5.4，无 key，≤1 req/s）：全网文章 + site: 定向。

每词条 2 次调用：通用组 + 视频定向（site:youtube.com）；
中文词条的中文组由 bilibili/搜狗消费，X 定向由 x_search 无 token 降级消费。
风控/超时一律返回 []，不向流水线抛异常。
"""

from __future__ import annotations

import logging

from openmind.sources.base import Candidate, Query
from openmind.sources.http_util import RateLimiter
from openmind.sources.wiki_links import classify_url

log = logging.getLogger(__name__)

MAX_RESULTS = 10
_LIMITER = RateLimiter(min_interval=1.0)


def _text_search(q: str, max_results: int) -> list[dict]:
    from ddgs import DDGS

    return DDGS().text(q, max_results=max_results)


class DuckDuckGoSource:
    name = "duckduckgo"
    needs_key = False

    def search(self, query: Query) -> list[Candidate]:
        queries = [query.groups.get("exact") or query.title]
        queries.append(f"{query.title} site:youtube.com")
        out: list[Candidate] = []
        seen: set[str] = set()
        for q in queries:
            try:
                _LIMITER.acquire()
                results = _text_search(q, MAX_RESULTS)
            except Exception as exc:
                log.warning("ddgs failed for %r: %s", q, exc)
                continue
            for r in results or []:
                url = r.get("href") or r.get("url") or ""
                title = r.get("title") or ""
                if not url or not title or url in seen:
                    continue
                seen.add(url)
                out.append(
                    Candidate(
                        url=url,
                        title=title,
                        kind=classify_url(url),
                        source=self.name,
                        snippet=(r.get("body") or "")[:300],
                        lang=query.lang,
                    )
                )
        return out
