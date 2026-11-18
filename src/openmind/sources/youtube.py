"""YouTube Data API 信源（SPEC §5.4，key）：search.list 长视频 + videos.list 时长元数据。

每词条 search.list 1 次（videoDuration=long）+ videos.list 1 次批量取时长；
缺 key 由 discover 记 skipped，降级走维基外链视频 + DDG site:youtube.com。
"""

from __future__ import annotations

import logging
import os
import re

import httpx

from openmind.sources.base import Candidate, Query
from openmind.sources.http_util import TIMEOUT, UA

log = logging.getLogger(__name__)

SEARCH_API = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_API = "https://www.googleapis.com/youtube/v3/videos"
MAX_RESULTS = 5
_ISO_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def parse_duration_minutes(iso: str) -> float:
    m = _ISO_DURATION_RE.fullmatch(iso or "")
    if not m:
        return 0.0
    h, mnt, s = (int(g) if g else 0 for g in m.groups())
    return round(h * 60 + mnt + s / 60, 1)


class YoutubeSource:
    name = "youtube"
    needs_key = True

    def search(self, query: Query) -> list[Candidate]:
        key = os.environ.get("YOUTUBE_API_KEY", "")
        if not key:
            return []
        try:
            resp = httpx.get(
                SEARCH_API,
                params={
                    "part": "snippet",
                    "q": query.title,
                    "type": "video",
                    "videoDuration": "long",
                    "maxResults": MAX_RESULTS,
                    "key": key,
                },
                timeout=TIMEOUT,
                headers={"User-Agent": UA},
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            vids = [i["id"]["videoId"] for i in items if i.get("id", {}).get("videoId")]
            if not vids:
                return []
            details: dict[str, dict] = {}
            try:
                resp = httpx.get(
                    VIDEOS_API,
                    params={
                        "part": "contentDetails,statistics",
                        "id": ",".join(vids),
                        "key": key,
                    },
                    timeout=TIMEOUT,
                    headers={"User-Agent": UA},
                )
                resp.raise_for_status()
                details = {v["id"]: v for v in resp.json().get("items", [])}
            except Exception as exc:
                log.info("youtube videos.list failed (metadata degraded): %s", exc)
            out: list[Candidate] = []
            for i in items:
                vid = i.get("id", {}).get("videoId")
                sn = i.get("snippet", {})
                if not vid or not sn.get("title"):
                    continue
                d = details.get(vid, {})
                minutes = parse_duration_minutes(
                    d.get("contentDetails", {}).get("duration", "")
                )
                views = int(d.get("statistics", {}).get("viewCount", 0) or 0)
                out.append(
                    Candidate(
                        url=f"https://www.youtube.com/watch?v={vid}",
                        title=sn["title"],
                        kind="video",
                        source=self.name,
                        snippet=(sn.get("description") or "")[:300],
                        lang=query.lang,
                        published=(sn.get("publishedAt") or "")[:10],
                        meta={
                            "duration_min": minutes,
                            "views": views,
                            "channel": sn.get("channelTitle", ""),
                        },
                    )
                )
            return out
        except Exception as exc:
            log.warning("youtube failed for %s: %s", query.title, exc)
            return []
