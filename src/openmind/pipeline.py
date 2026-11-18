"""七段流水线编排（SPEC §5.1/§5.9）：sample → wiki → queries → discover → score → brief → render。

- 幂等：当日 archive 已存在且无 force → 跳过（exit 0）。
- 断点：--stage 只跑到指定段；中间产物落盘 data/<date>/，重跑从磁盘续。
- 状态一致性：served.json 只在 render 成功后追加（git commit 由 workflow 统一做）。
- 所有外部调用降级不抛：缺 key / 网络失败 → 空产物继续，exit 0 优先。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

from openmind.brief import make_brief
from openmind.compliance import Compliance
from openmind.discover import discover
from openmind.pool import PoolEntry, build_pool
from openmind.queries import build_queries
from openmind.render import Issue, render_issue
from openmind.sample import sample
from openmind.score import score_candidates
from openmind.sources.base import Candidate, Query
from openmind.sources.wiki_links import WikiLinksSource
from openmind.state import State
from openmind.wiki import ArticleInfo, fetch_aliases, fetch_article

log = logging.getLogger(__name__)

STAGES = ("sample", "wiki", "queries", "discover", "score", "brief", "render")
POOL_MAX_AGE_DAYS = 7


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def fetch_zh_extract(zh_title: str) -> str:
    return fetch_article(zh_title, lang="zh").extract


def _dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sources() -> list:
    return [WikiLinksSource()]


def _available_keys() -> set[str]:
    import os

    mapping = {
        "serper": "SERPER_API_KEY",
        "brave": "BRAVE_API_KEY",
        "tavily": "TAVILY_API_KEY",
        "youtube": "YOUTUBE_API_KEY",
        "x_search": "X_BEARER_TOKEN",
        "llm": "LLM_API_KEY",
    }
    return {name for name, env in mapping.items() if os.environ.get(env)}


def _load_pool(root: Path) -> list[PoolEntry]:
    pool_path = root / "state" / "pool.json"
    if pool_path.exists():
        data = _load(pool_path)
        age_days = (time.time() - data.get("built_at", 0)) / 86400
        if age_days <= POOL_MAX_AGE_DAYS:
            # 池存在且未到期：即使为空也不触发重建（空池是合法状态，报错交由抽样段）
            return [PoolEntry(**e) for e in data.get("entries", [])]
        log.info("pool stale (%.1f days), refreshing", age_days)
        return build_pool(root / "state", refresh=True)
    return build_pool(root / "state", refresh=True)


def run(
    root: Path,
    date_iso: str,
    force: bool = False,
    stage: str | None = None,
) -> int:
    root = Path(root)
    state_dir = root / "state"
    data_dir = root / "data" / date_iso
    site_dir = root / "site"
    stop_at = stage or STAGES[-1]
    today = date.fromisoformat(date_iso)

    daily_page = site_dir / "archive" / f"{date_iso}.html"
    if daily_page.exists() and not force and stop_at == "render":
        log.info("issue %s already exists; skip (use --force to regenerate)", date_iso)
        return 0
    if force:
        # 覆盖重跑：清除当日全部中间产物，防止旧段产物污染新抽样
        if data_dir.exists():
            for f in data_dir.glob("*.json"):
                f.unlink()

    comp = Compliance.load(state_dir)
    state = State.load(state_dir)
    if force:
        # 同日重抽不应被自己当日已 served 的条目挡住：抽样窗口剔除当日记录
        state.served = [e for e in state.served if e["date"] != date_iso]

    # ---- sample + wiki（类目复核可能触发备用替换，两段联动）----
    sampled_path = data_dir / "sampled.json"
    wiki_path = data_dir / "wiki.json"
    if force or not sampled_path.exists() or not wiki_path.exists():
        pool = _load_pool(root)
        if not pool:
            log.error("pool empty; cannot sample")
            return 1
        picked = sample(pool, date_iso, served=state.served, domains=state.domains)
        if not picked:
            log.error("no candidates after dedupe window; cannot sample")
            return 1
        # 条目级类目复核：分区现实但条目本身是虚构作品（如演唱会电影落在音乐商业分区）
        # 命中则用备用候选顶替；备用也违规则顺延重抽
        mains: list[PoolEntry] = []
        infos: list[ArticleInfo] = []
        used_titles = {e["title"] for e in state.served}
        for e in picked:
            if len(mains) >= 3:
                break
            info = fetch_article(e.canonical_title, e.lang)
            ok, reason = comp.check_entry(e.canonical_title, info.categories)
            used_titles.add(e.canonical_title)
            if not ok:
                log.info("entry swapped out %s: %s", e.canonical_title, reason)
                continue
            info.aliases = fetch_aliases(e.canonical_title, e.lang)
            mains.append(e)
            infos.append(info)
        # 备用不足时从池里按同日期种子补抽
        while len(mains) < 3:
            extra = sample(
                [p for p in pool if p.canonical_title not in used_titles],
                date_iso,
                served=state.served,
                domains=state.domains,
            )
            if not extra:
                break
            progressed = False
            for e in extra:
                if len(mains) >= 3:
                    break
                if e.canonical_title in used_titles:
                    continue
                info = fetch_article(e.canonical_title, e.lang)
                ok, reason = comp.check_entry(e.canonical_title, info.categories)
                if not ok:
                    log.info("entry swapped out %s: %s", e.canonical_title, reason)
                    used_titles.add(e.canonical_title)
                    continue
                info.aliases = fetch_aliases(e.canonical_title, e.lang)
                mains.append(e)
                infos.append(info)
                used_titles.add(e.canonical_title)
                progressed = True
            if not progressed:
                break
        if not mains:
            log.error("all sampled entries rejected by compliance")
            return 1
        _dump(sampled_path, [asdict(e) for e in mains])
        _dump(wiki_path, [asdict(i) for i in infos])
    picked = [PoolEntry(**e) for e in _load(sampled_path)]
    mains = picked[:3]
    if stop_at == "sample":
        return 0
    infos = [ArticleInfo(**d) for d in _load(wiki_path)]
    if stop_at == "wiki":
        return 0

    # ---- queries ----
    queries_path = data_dir / "queries.json"
    if force or not queries_path.exists():
        _dump(queries_path, [asdict(build_queries(i)) for i in infos])
    queries = [Query(**d) for d in _load(queries_path)]
    if stop_at == "queries":
        return 0

    # ---- discover ----
    cand_path = data_dir / "candidates.json"
    health_path = data_dir / "health.json"
    if force or not cand_path.exists():
        result = discover(queries, _sources(), _available_keys())
        _dump(cand_path, {t: [asdict(c) for c in cs] for t, cs in result.candidates.items()})
        _dump(health_path, result.health)
    raw = {t: [Candidate(**d) for d in cs] for t, cs in _load(cand_path).items()}
    health = _load(health_path)
    if stop_at == "discover":
        return 0

    # ---- score ----
    scored_path = data_dir / "scored.json"
    if force or not scored_path.exists():
        scored: dict[str, list] = {}
        rejected: list[dict] = []
        for e, info in zip(mains, infos, strict=True):
            topic = info.zh_title or info.title
            top, rej = score_candidates(raw.get(e.canonical_title, []), topic, comp)
            scored[e.canonical_title] = [asdict(c) for c in top]
            rejected.extend(rej)
        _dump(scored_path, {"items": scored, "rejected": rejected})
    scored_data = _load(scored_path)
    items = {t: [Candidate(**d) for d in cs] for t, cs in scored_data["items"].items()}
    if stop_at == "score":
        return 0

    # ---- brief ----
    brief_path = data_dir / "brief.json"
    if force or not brief_path.exists():
        briefs = []
        for e, info in zip(mains, infos, strict=True):
            b = make_brief(info, domain=e.domain, fetch_zh=fetch_zh_extract)
            briefs.append(json.loads(b.to_json()))
        _dump(brief_path, briefs)
    from openmind.brief import EntryBrief

    briefs = [EntryBrief.from_json(json.dumps(d, ensure_ascii=False)) for d in _load(brief_path)]
    if stop_at == "brief":
        return 0

    # ---- render ----
    sources_ok = len({h["source"] for h in health if h.get("ok")})
    issue = Issue(
        date=date_iso,
        briefs=briefs,
        items=items,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        sources_ok=sources_ok,
        sources_total=len(_sources()) + 11,  # V1 规划 12 信源，T9–T15 逐个接线
        base_url="https://lightai1235.github.io/news",
    )
    render_issue(issue, site_dir)

    # 状态追加：force 重跑先移除当日旧记录，避免重复
    state.served = [e for e in state.served if e["date"] != date_iso]
    state.append_served([(b.title, b.domain) for b in briefs], today)
    state.save(state_dir, today=today)
    log.info("issue %s rendered: %d entries", date_iso, len(briefs))
    return 0
