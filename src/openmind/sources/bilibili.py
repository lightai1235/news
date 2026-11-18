"""bilibili 搜索信源（SPEC §5.4，非官方无 key，≤1 req/s）：中文视频。

风控/验证码/接口变更一律返回 []；仅中文词条（有 zh 查询组）触发。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from openmind.sources.base import Candidate, Query
from openmind.sources.http_util import TIMEOUT, UA, RateLimiter, strip_html

log = logging.getLogger(__name__)

SEARCH_API = "https://api.bilibili.com/x/web-interface/search/type"
MAX_RESULTS = 10
_LIMITER = RateLimiter(min_interval=1.0)


def parse_duration(text: str) -> float:
    """'42:10' / '1:05:30' → 分钟。"""
    parts = (text or "").split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return 0.0
    if len(nums) == 2:
        return round(nums[0] + nums[1] / 60, 1)
    if len(nums) == 3:
        return round(nums[0] * 60 + nums[1] + nums[2] / 60, 1)
    return 0.0


class BilibiliSource:
    name = "bilibili"
    needs_key = False

    def search(self, query: Query) -> list[Candidate]:
        zh_query = query.groups.get("zh")
        if not zh_query:
            return []  # 中文源只服务中文查询组
        keyword = query.aliases[0] if query.aliases else query.title
        try:
            _LIMITER.acquire()
            resp = httpx.get(
                SEARCH_API,
                params={"search_type": "video", "keyword": keyword, "page": 1},
                timeout=TIMEOUT,
                headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                log.info("bilibili risk-control code=%s for %s", data.get("code"), query.title)
                return []
            out: list[Candidate] = []
            for r in (data.get("data", {}).get("result") or [])[:MAX_RESULTS]:
                bvid = r.get("bvid") or ""
                title = strip_html(r.get("title") or "")
                if not bvid or not title:
                    continue
                ts = r.get("pubdate") or 0
                out.append(
                    Candidate(
                        url=f"https://www.bilibili.com/video/{bvid}",
                        title=title,
                        kind="video",
                        source=self.name,
                        snippet=(r.get("description") or "")[:300],
                        lang="zh",
                        published=(
                            datetime.fromtimestamp(ts, UTC).date().isoformat() if ts else ""
                        ),
                        meta={
                            "duration_min": parse_duration(r.get("duration", "")),
                            "views": r.get("play", 0),
                            "channel": r.get("author", ""),
                        },
                    )
                )
            return out
        except Exception as exc:
            log.warning("bilibili failed for %s: %s", query.title, exc)
            return []
