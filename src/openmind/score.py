"""两级评分漏斗（SPEC §5.6）：粗排元数据 → 前 20 精排抓正文 → Top-10。

score = 3.0×域名权威 + 2.0×内容深度 + 1.5×主题相关度 + 1.0×时效性 − ∞×黑名单
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from openmind.compliance import Compliance
from openmind.sources.base import Candidate

log = logging.getLogger(__name__)

COARSE_LIMIT = 20
TOP_N = 10
PER_DOMAIN_CAP = 3
# 非权威域名理论最高分 = 2.0 + 1.5 + 1.0 = 4.5，门槛须低于该值，
# 否则优质非权威内容永远无法入选（2026-11-19 修正设计矛盾）。
SCORE_THRESHOLD = 3.0
_TRACKING_PREFIXES = ("utm_", "spm", "fbclid", "gclid", "ref", "share")
_WORD_RE = re.compile(r"[a-z0-9\u4e00-\u9fff]+")


def normalize_url(url: str) -> str:
    p = urlparse(url)
    query = [
        (k, v)
        for k, v in parse_qsl(p.query)
        if not any(k.lower().startswith(t) for t in _TRACKING_PREFIXES)
    ]
    return urlunparse(
        (p.scheme, p.netloc.lower(), p.path.rstrip("/") or "/", "", urlencode(query), "")
    )


def dedupe(cands: list[Candidate]) -> list[Candidate]:
    seen: set[str] = set()
    out: list[Candidate] = []
    for c in cands:
        key = normalize_url(c.url)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _tokens(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _relevance(c: Candidate, topic: str) -> float:
    topic_toks = _tokens(topic)
    if not topic_toks:
        return 0.0
    title_toks = _tokens(c.title)
    overlap = len(topic_toks & title_toks) / len(topic_toks)
    snippet_toks = _tokens(c.snippet)
    mention = len(topic_toks & snippet_toks) / len(topic_toks)
    return min(1.0, overlap + 0.5 * mention)


def _depth(c: Candidate, text: str) -> float:
    if c.kind == "video":
        minutes = float(c.meta.get("duration_min", 0) or 0)
        return min(1.0, minutes / 30)
    if c.kind == "paper":
        pages = float(c.meta.get("pages", 0) or 0)
        if pages:
            return min(1.0, pages / 20)
        return 0.6
    words = len(text.split()) if text else 0
    return min(1.0, words / 2000)


def _recency(c: Candidate) -> float:
    year = (c.published or "")[:4]
    if not year.isdigit():
        return 0.5
    age = 2026 - int(year)
    return 1.0 if age <= 5 else 0.5


def _coarse_score(c: Candidate, topic: str, comp: Compliance) -> float:
    authority = 1.0 if comp.is_authoritative(c.url) else 0.0
    return 3.0 * authority + 1.5 * _relevance(c, topic) + 1.0 * _recency(c)


def _default_fetch(url: str) -> str:
    import httpx

    resp = httpx.get(
        url, timeout=10.0, follow_redirects=True, headers={"User-Agent": "OpenMind/0.1"}
    )
    resp.raise_for_status()
    text = re.sub(r"<[^>]+>", " ", resp.text)
    return text[:20000]


def score_candidates(
    cands: list[Candidate],
    topic: str,
    comp: Compliance,
    fetch_text: Callable[[str], str] | None = None,
) -> tuple[list[Candidate], list[dict]]:
    fetch = fetch_text or _default_fetch
    rejected: list[dict] = []

    allowed: list[Candidate] = []
    for c in dedupe(cands):
        ok, reason = comp.check_url(c.url)
        if not ok:
            rejected.append({"url": c.url, "reason": reason})
            continue
        allowed.append(c)

    coarse = sorted(allowed, key=lambda c: _coarse_score(c, topic, comp), reverse=True)
    finalists = coarse[:COARSE_LIMIT]

    def fine(c: Candidate) -> Candidate | None:
        text = ""
        if c.kind in ("article", "discussion", "wechat"):
            try:
                text = fetch(c.url)
            except Exception as exc:
                log.info("fine-rank fetch failed %s: %s", c.url, exc)
                return None
        authority = 1.0 if comp.is_authoritative(c.url) else 0.0
        score = (
            3.0 * authority + 2.0 * _depth(c, text) + 1.5 * _relevance(c, topic) + 1.0 * _recency(c)
        )
        c.score = round(score, 2)
        parts = []
        if authority:
            parts.append("权威域名")
        if c.kind == "paper":
            parts.append("论文")
        elif c.kind == "video":
            parts.append("视频")
        if c.published:
            parts.append(c.published[:4])
        parts.append(f"相关度{_relevance(c, topic):.1f}")
        c.reason = " · ".join(parts)
        return c

    with ThreadPoolExecutor(max_workers=4) as pool:
        scored = [c for c in pool.map(fine, finalists) if c is not None]

    scored = [c for c in scored if c.score is not None and c.score >= SCORE_THRESHOLD]
    scored.sort(key=lambda c: c.score or 0.0, reverse=True)

    per_domain: dict[str, int] = {}
    top: list[Candidate] = []
    for c in scored:
        host = (urlparse(c.url).hostname or "").lower()
        if per_domain.get(host, 0) >= PER_DOMAIN_CAP:
            continue
        per_domain[host] = per_domain.get(host, 0) + 1
        top.append(c)
        if len(top) >= TOP_N:
            break
    return top, rejected
