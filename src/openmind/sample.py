"""分层抽样（SPEC §5.2）：sha256 日期种子 + 领域加权 + 3 主选 1 备用。"""

from __future__ import annotations

import hashlib
import random
from datetime import date

from openmind.pool import PoolEntry

MAIN_COUNT = 3
BACKUP_COUNT = 1
NEVER_SEEN_DAYS = 365


def _seed_rng(date_iso: str) -> random.Random:
    return random.Random(int(hashlib.sha256(date_iso.encode("utf-8")).hexdigest(), 16))


def _domain_weight(last_seen: str | None, today: date) -> float:
    if not last_seen:
        return float(NEVER_SEEN_DAYS)
    days = (today - date.fromisoformat(last_seen)).days
    return float(max(days, 1))


def sample(
    pool: list[PoolEntry],
    date_iso: str,
    served: list[dict],
    domains: dict[str, str],
) -> list[PoolEntry]:
    """返回最多 3 主选 + 1 备用；主选领域互异。池不足时按实际数降级。"""
    if not pool:
        return []
    today = date.fromisoformat(date_iso)
    cutoff = today.toordinal() - 180
    recent = {e["title"] for e in served if date.fromisoformat(e["date"]).toordinal() >= cutoff}
    candidates = [e for e in pool if e.canonical_title not in recent]
    if not candidates:
        return []

    rng = _seed_rng(date_iso)
    by_domain: dict[str, list[PoolEntry]] = {}
    for e in candidates:
        by_domain.setdefault(e.domain, []).append(e)

    wanted = MAIN_COUNT + BACKUP_COUNT
    picked: list[PoolEntry] = []
    remaining = dict(by_domain)
    while remaining and len(picked) < wanted:
        doms = list(remaining)
        weights = [_domain_weight(domains.get(d), today) for d in doms]
        dom = rng.choices(doms, weights=weights, k=1)[0]
        entries = remaining.pop(dom)
        picked.append(rng.choice(entries))
    return picked
