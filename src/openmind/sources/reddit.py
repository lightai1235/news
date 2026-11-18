"""Reddit .json 信源（SPEC §5.4，无 key，非官方 ≤1 req/s）：社区讨论。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from openmind.sources.base import Candidate, Query
from openmind.sources.http_util import TIMEOUT, UA, RateLimiter

log = logging.getLogger(__name__)

REDDIT_SEARCH = "https://www.reddit.com/search.json"
MAX_RESULTS = 10
_LIMITER = RateLimiter(min_interval=1.0)


class RedditSource:
    name = "reddit"
    needs_key = False

    def search(self, query: Query) -> list[Candidate]:
        try:
            _LIMITER.acquire()
            resp = httpx.get(
                REDDIT_SEARCH,
                params={"q": query.title, "limit": MAX_RESULTS, "sort": "relevance"},
                timeout=TIMEOUT,
                headers={"User-Agent": UA},
                follow_redirects=True,
            )
            resp.raise_for_status()
            out: list[Candidate] = []
            for child in resp.json().get("data", {}).get("children", []):
                d = child.get("data", {})
                title = d.get("title") or ""
                permalink = d.get("permalink") or ""
                if not title or not permalink:
                    continue
                discussion_url = f"https://www.reddit.com{permalink}"
                is_self = d.get("is_self", False)
                url = discussion_url if is_self else (d.get("url") or discussion_url)
                ts = d.get("created_utc") or 0
                published = (
                    datetime.fromtimestamp(ts, UTC).date().isoformat() if ts else ""
                )
                out.append(
                    Candidate(
                        url=url,
                        title=title,
                        kind="discussion" if is_self else "article",
                        source=self.name,
                        snippet=(d.get("selftext") or "")[:300],
                        lang="en",
                        published=published,
                        meta={
                            "score": d.get("score", 0),
                            "comments": d.get("num_comments", 0),
                            "subreddit": d.get("subreddit", ""),
                            "discussion_url": discussion_url,
                        },
                    )
                )
            return out
        except Exception as exc:
            log.warning("reddit failed for %s: %s", query.title, exc)
            return []
