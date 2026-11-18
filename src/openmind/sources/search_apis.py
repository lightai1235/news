"""T12 统一 SearchPort：Serper / Brave / Tavily 三实现同一接口（SPEC §5.4）。

有 key 才启用（needs_key=True，discover 缺 key 记 skipped_no_key）；
任一可用即可，多个可用时全部参与（去重交给评分段）。
Serper 每词条 2 次（精确组 + 概念组），Brave/Tavily 各 1 次，控制配额消耗。
"""

from __future__ import annotations

import logging
import os

import httpx

from openmind.sources.base import Candidate, Query
from openmind.sources.http_util import TIMEOUT
from openmind.sources.wiki_links import classify_url

log = logging.getLogger(__name__)

MAX_RESULTS = 10


def _candidate(
    source: str, url: str, title: str, snippet: str, lang: str, published: str = ""
) -> Candidate:
    return Candidate(
        url=url,
        title=title,
        kind=classify_url(url),
        source=source,
        snippet=snippet[:300],
        lang=lang,
        published=published[:10],
    )


class SerperSource:
    name = "serper"
    needs_key = True

    def search(self, query: Query) -> list[Candidate]:
        key = os.environ.get("SERPER_API_KEY", "")
        if not key:
            return []
        groups = [query.groups.get("exact") or query.title]
        if query.groups.get("concept"):
            groups.append(query.groups["concept"])
        out: list[Candidate] = []
        seen: set[str] = set()
        for q in groups:
            try:
                resp = httpx.post(
                    "https://google.serper.dev/search",
                    json={"q": q, "num": MAX_RESULTS},
                    headers={"X-API-KEY": key, "Content-Type": "application/json"},
                    timeout=TIMEOUT,
                )
                resp.raise_for_status()
                for r in resp.json().get("organic", []):
                    url, title = r.get("link", ""), r.get("title", "")
                    if not url or not title or url in seen:
                        continue
                    seen.add(url)
                    out.append(
                        _candidate(
                            self.name, url, title, r.get("snippet", ""), query.lang,
                            r.get("date", ""),
                        )
                    )
            except Exception as exc:
                log.warning("serper failed for %r: %s", q, exc)
        return out


class BraveSource:
    name = "brave"
    needs_key = True

    def search(self, query: Query) -> list[Candidate]:
        key = os.environ.get("BRAVE_API_KEY", "")
        if not key:
            return []
        try:
            resp = httpx.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query.groups.get("exact") or query.title, "count": MAX_RESULTS},
                headers={"X-Subscription-Token": key, "Accept": "application/json"},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            out: list[Candidate] = []
            for r in resp.json().get("web", {}).get("results", []):
                url, title = r.get("url", ""), r.get("title", "")
                if not url or not title:
                    continue
                out.append(
                    _candidate(
                        self.name, url, title, r.get("description", ""), query.lang,
                        r.get("page_age", ""),
                    )
                )
            return out
        except Exception as exc:
            log.warning("brave failed for %s: %s", query.title, exc)
            return []


class TavilySource:
    name = "tavily"
    needs_key = True

    def search(self, query: Query) -> list[Candidate]:
        key = os.environ.get("TAVILY_API_KEY", "")
        if not key:
            return []
        try:
            resp = httpx.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": key,
                    "query": query.groups.get("exact") or query.title,
                    "max_results": MAX_RESULTS,
                },
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            out: list[Candidate] = []
            for r in resp.json().get("results", []):
                url, title = r.get("url", ""), r.get("title", "")
                if not url or not title:
                    continue
                out.append(
                    _candidate(
                        self.name, url, title, r.get("content", ""), query.lang,
                        r.get("published_date", ""),
                    )
                )
            return out
        except Exception as exc:
            log.warning("tavily failed for %s: %s", query.title, exc)
            return []
