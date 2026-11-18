"""信源调度（SPEC §5.4）：并发调用 adapter，故障隔离，产出候选与 health 记录。"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from openmind.sources.base import Candidate, Query, SourcePort

log = logging.getLogger(__name__)

MAX_WORKERS = 4


@dataclass
class DiscoverResult:
    candidates: dict[str, list[Candidate]] = field(default_factory=dict)
    health: list[dict] = field(default_factory=list)


def _run_one(source: SourcePort, query: Query, available_keys: set[str]) -> tuple[dict, list]:
    started = time.monotonic()
    if source.needs_key and source.name not in available_keys:
        return (
            {
                "title": query.title,
                "source": source.name,
                "ok": False,
                "status": "skipped_no_key",
                "candidates": 0,
                "error": "",
                "elapsed_ms": 0,
            },
            [],
        )
    try:
        cands = source.search(query)
        return (
            {
                "title": query.title,
                "source": source.name,
                "ok": True,
                "status": "ok",
                "candidates": len(cands),
                "error": "",
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            },
            cands,
        )
    except Exception as exc:
        log.warning("source %s failed for %s: %s", source.name, query.title, exc)
        return (
            {
                "title": query.title,
                "source": source.name,
                "ok": False,
                "status": "error",
                "candidates": 0,
                "error": str(exc)[:200],
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            },
            [],
        )


def discover(
    queries: list[Query],
    sources: list[SourcePort],
    available_keys: set[str],
) -> DiscoverResult:
    result = DiscoverResult(candidates={q.title: [] for q in queries})
    jobs = [(s, q) for q in queries for s in sources]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(_run_one, s, q, available_keys) for s, q in jobs]
        for (_s, q), fut in zip(jobs, futures, strict=True):
            health, cands = fut.result()
            result.health.append(health)
            result.candidates[q.title].extend(cands)
    return result
