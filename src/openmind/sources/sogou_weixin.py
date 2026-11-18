"""搜狗微信信源（SPEC §5.4，非官方无 key，≤1 req/s）：公众号文章索引。

只取标题+摘要+链接，不抓正文（正文在微信内读）；
风控/验证码/重定向到 antispider 一律返回 []。
"""

from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from openmind.sources.base import Candidate, Query
from openmind.sources.http_util import TIMEOUT, UA, RateLimiter, strip_html

log = logging.getLogger(__name__)

SEARCH_URL = "https://weixin.sogou.com/weixin"
MAX_RESULTS = 10
_LIMITER = RateLimiter(min_interval=1.0)
# 结果块：<h3><a href="...">标题</a></h3> ... <p class="txt-info">摘要</p>
_ITEM_RE = re.compile(
    r"<h3>\s*<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>\s*</h3>"
    r"(?:.*?<p class=\"txt-info\">(.*?)</p>)?",
    re.DOTALL,
)


def _resolve_link(href: str) -> str:
    """搜狗跳转 /link?url=... → 真实 mp.weixin.qq.com 地址；直链原样。"""
    if href.startswith("/link?"):
        qs = parse_qs(urlparse(href).query)
        target = unquote((qs.get("url") or [""])[0])
        return target if target.startswith("http") else ""
    if href.startswith("http"):
        return href
    return ""


class SogouWeixinSource:
    name = "sogou_weixin"
    needs_key = False

    def search(self, query: Query) -> list[Candidate]:
        zh_query = query.groups.get("zh")
        if not zh_query:
            return []
        keyword = query.aliases[0] if query.aliases else query.title
        try:
            _LIMITER.acquire()
            resp = httpx.get(
                SEARCH_URL,
                params={"type": "2", "query": keyword},
                timeout=TIMEOUT,
                headers={"User-Agent": UA},
                follow_redirects=True,
            )
            resp.raise_for_status()
            if "antispider" in str(resp.url) or "验证码" in resp.text[:2000]:
                log.info("sogou risk-control for %s", query.title)
                return []
            out: list[Candidate] = []
            seen: set[str] = set()
            for m in _ITEM_RE.finditer(resp.text):
                url = _resolve_link(m.group(1))
                title = strip_html(m.group(2))
                snippet = strip_html(m.group(3) or "")
                if not url or not title or url in seen:
                    continue
                seen.add(url)
                out.append(
                    Candidate(
                        url=url,
                        title=title,
                        kind="wechat",
                        source=self.name,
                        snippet=snippet[:300],
                        lang="zh",
                    )
                )
                if len(out) >= MAX_RESULTS:
                    break
            return out
        except Exception as exc:
            log.warning("sogou_weixin failed for %s: %s", query.title, exc)
            return []
