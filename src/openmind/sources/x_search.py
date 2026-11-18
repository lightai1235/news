"""T15 X Recent Search 信源（SPEC §5.4）。

有 X_BEARER_TOKEN 走 API v2 recent search；无 token 由 DDG site:x.com 顶替；
只索引不抓正文（X 内容在 X 内读）；429/403 返回 []。
"""

from __future__ import annotations

import logging
import os

import httpx

from openmind.sources.base import Candidate, Query
from openmind.sources.http_util import TIMEOUT, UA

log = logging.getLogger(__name__)

RECENT_API = "https://api.twitter.com/2/tweets/search/recent"
MAX_RESULTS = 10


class XSearchSource:
    name = "x_search"
    needs_key = False  # 无 token 有 DDG 降级路径，discover 不 skip

    def search(self, query: Query) -> list[Candidate]:
        token = os.environ.get("X_BEARER_TOKEN", "")
        if token:
            return self._api_search(query, token)
        return self._ddg_fallback(query)

    def _api_search(self, query: Query, token: str) -> list[Candidate]:
        try:
            resp = httpx.get(
                RECENT_API,
                params={
                    "query": f'"{query.title}" -is:retweet lang:en',
                    "max_results": MAX_RESULTS,
                    "tweet.fields": "created_at,public_metrics,author_id",
                    "expansions": "author_id",
                    "user.fields": "username",
                },
                headers={"Authorization": f"Bearer {token}", "User-Agent": UA},
                timeout=TIMEOUT,
            )
            if resp.status_code in (403, 429):
                log.info("x api %s for %s", resp.status_code, query.title)
                return []
            resp.raise_for_status()
            data = resp.json()
            users = {
                u["id"]: u.get("username", "") for u in data.get("includes", {}).get("users", [])
            }
            out: list[Candidate] = []
            for t in data.get("data", []):
                tid = t.get("id") or ""
                text = t.get("text") or ""
                if not tid or not text:
                    continue
                username = users.get(t.get("author_id", ""), "i")
                out.append(
                    Candidate(
                        url=f"https://x.com/{username}/status/{tid}",
                        title=text[:80],
                        kind="discussion",
                        source=self.name,
                        snippet=text[:300],
                        lang="en",
                        published=(t.get("created_at") or "")[:10],
                        meta={
                            "likes": t.get("public_metrics", {}).get("like_count", 0),
                            "author": username,
                        },
                    )
                )
            return out
        except Exception as exc:
            log.warning("x_search failed for %s: %s", query.title, exc)
            return []

    def _ddg_fallback(self, query: Query) -> list[Candidate]:
        from openmind.sources.duckduckgo import _LIMITER, _text_search

        try:
            _LIMITER.acquire()
            results = _text_search(f"{query.title} site:x.com", MAX_RESULTS)
        except Exception as exc:
            log.warning("x ddg fallback failed for %s: %s", query.title, exc)
            return []
        out: list[Candidate] = []
        for r in results or []:
            url = r.get("href") or r.get("url") or ""
            title = r.get("title") or ""
            if not url or not title or "x.com" not in url:
                continue
            out.append(
                Candidate(
                    url=url,
                    title=title,
                    kind="discussion",
                    source=self.name,
                    snippet=(r.get("body") or "")[:300],
                    lang=query.lang,
                    meta={"origin": "ddg_fallback"},
                )
            )
        return out
