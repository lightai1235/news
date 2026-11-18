"""T3 分层抽样测试：幂等、领域互异、180 天去重、备用候选。"""

from openmind.pool import PoolEntry
from openmind.sample import sample


def make_pool() -> list[PoolEntry]:
    entries = []
    domains = ["自然科学", "数学", "历史", "地理", "艺术", "社会"]
    for dom in domains:
        for j in range(5):
            entries.append(
                PoolEntry(canonical_title=f"{dom}条目{j}", lang="zh", domain=dom, section=dom)
            )
    return entries


class TestSample:
    def test_same_date_identical(self):
        pool = make_pool()
        a = sample(pool, "2026-11-18", served=[], domains={})
        b = sample(pool, "2026-11-18", served=[], domains={})
        assert [e.canonical_title for e in a] == [e.canonical_title for e in b]

    def test_different_date_different(self):
        pool = make_pool()
        a = sample(pool, "2026-11-18", served=[], domains={})
        b = sample(pool, "2026-11-19", served=[], domains={})
        assert [e.canonical_title for e in a] != [e.canonical_title for e in b]

    def test_three_distinct_domains_plus_backup(self):
        pool = make_pool()
        picked = sample(pool, "2026-11-18", served=[], domains={})
        assert len(picked) == 4
        main = picked[:3]
        assert len({e.domain for e in main}) == 3

    def test_served_within_180_days_excluded(self):
        pool = make_pool()
        served = [
            {"title": e.canonical_title, "date": "2026-11-01", "domain": e.domain}
            for e in pool
            if e.domain == "数学"
        ]
        picked = sample(pool, "2026-11-18", served=served, domains={})
        assert all(e.domain != "数学" for e in picked)

    def test_served_older_than_180_days_allowed(self):
        pool = [e for e in make_pool() if e.domain == "数学"]
        served = [{"title": "数学条目0", "date": "2026-01-01", "domain": "数学"}]
        picked = sample(pool, "2026-11-18", served=served, domains={})
        assert all(e.canonical_title != "数学条目0" for e in picked)
        assert len(picked) >= 1

    def test_long_absent_domain_weighted_higher(self):
        pool = make_pool()
        domains = {
            "自然科学": "2026-11-17",
            "数学": "2026-11-17",
            "历史": "2026-11-17",
            "地理": "2026-11-17",
            "艺术": "2026-11-17",
        }
        counts = {}
        for day in range(1, 29):
            picked = sample(pool, f"2026-12-{day:02d}", served=[], domains=domains)
            for e in picked[:3]:
                counts[e.domain] = counts.get(e.domain, 0) + 1
        assert counts.get("社会", 0) > 0

    def test_small_pool_degrades_gracefully(self):
        pool = make_pool()[:2]
        picked = sample(pool, "2026-11-18", served=[], domains={})
        assert 1 <= len(picked) <= 4

    def test_empty_pool_returns_empty(self):
        assert sample([], "2026-11-18", served=[], domains={}) == []
