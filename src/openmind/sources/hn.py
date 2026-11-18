"""HN Algolia 信源（SPEC §5.4，无 key）：技术讨论与长文。"""

from __future__ import annotations

import logging

import httpx

from openmind.sources.base import Candidate, Query
from openmind.sources.http_util import TIMEOUT, UA

log = logging.getLogger(__name__)

HN_API = "https://hn.algolia.com/api/v1/search"
MAX_RESULTS = 10


class HnSource:
    name = "hn"
    needs_key = False

    def search(self, query: Query) -> list[Candidate]:
        try:
            resp = httpx.get(
                HN_API,
                params={
                    "query": query.title,
                    "tags": "story",
                    "hitsPerPage": MAX_RESULTS,
                },
                timeout=TIMEOUT,
                headers={"User-Agent": UA},
            )
            resp.raise_for_status()
            out: list[Candidate] = []
            for hit in resp.json().get("hits", []):
                title = hit.get("title") or ""
                oid = hit.get("objectID") or ""
                if not title or not oid:
                    continue
                discussion_url = f"https://news.ycombinator.com/item?id={oid}"
                url = hit.get("url") or discussion_url
                out.append(
                    Candidate(
                        url=url,
                        title=title,
                        kind="article" if hit.get("url") else "discussion",
                        source=self.name,
                        snippet=(hit.get("story_text") or "")[:300],
                        lang="en",
                        published=(hit.get("created_at") or "")[:10],
                        meta={
                            "points": hit.get("points", 0),
                            "comments": hit.get("num_comments", 0),
                            "discussion_url": discussion_url,
                        },
                    )
                )
            return out
        except Exception as exc:
            log.warning("hn failed for %s: %s", query.title, exc)
            return []
