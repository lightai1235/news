"""T8 pipeline 测试：七段串联、幂等跳过、--force、断点 --stage、产物落盘。

全部网络调用以 fake 注入，验证编排逻辑而非外部 API。
"""

import json
from datetime import date
from pathlib import Path

import pytest

from openmind import pipeline
from openmind.pool import PoolEntry
from openmind.sources.base import Candidate
from openmind.wiki import ArticleInfo


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    state = tmp_path / "state"
    state.mkdir()
    for name in ("denylist_topics.txt", "denylist_domains.txt", "allowlist_domains.txt"):
        (state / name).write_text("", encoding="utf-8")
    entries = [
        {"canonical_title": f"Topic {i}", "lang": "en", "domain": dom, "section": "s"}
        for i, dom in enumerate(["自然科学", "历史", "数学", "艺术"])
    ]
    (state / "pool.json").write_text(
        json.dumps({"built_at": 9e12, "entries": entries}), encoding="utf-8"
    )  # built_at 远未来 → 永不过期
    return tmp_path


@pytest.fixture()
def fakes(monkeypatch):
    """把 wiki / discover / score 的网络面全部换成确定性 fake。"""
    calls = {"discover": 0, "score": 0, "brief_zh": 0}

    def fake_fetch_article(title, lang="en"):
        zh = f"中文{title}" if lang == "en" else title
        return ArticleInfo(title=title, lang=lang, extract=f"{title} is a topic.", zh_title=zh)

    def fake_fetch_aliases(title, lang="en"):
        return [f"{title} alias"]

    def fake_fetch_zh(zh_title):
        calls["brief_zh"] += 1
        return f"{zh_title}的中文简介。"

    def fake_discover(queries, sources, available_keys):
        from openmind.discover import DiscoverResult

        calls["discover"] += 1
        result = DiscoverResult(candidates={}, health=[])
        for q in queries:
            result.candidates[q.title] = [
                Candidate(
                    url=f"https://arxiv.org/abs/{q.title.replace(' ', '')}",
                    title=q.title,
                    kind="paper",
                    source="fake",
                )
            ]
            result.health.append(
                {
                    "title": q.title,
                    "source": "fake",
                    "ok": True,
                    "status": "ok",
                    "candidates": 1,
                    "error": "",
                    "elapsed_ms": 1,
                }
            )
        return result

    def fake_score(cands, topic, comp, fetch_text=None):
        calls["score"] += 1
        for c in cands:
            c.score = 7.0
            c.reason = "fake · 相关度1.0"
        return cands, []

    monkeypatch.setattr(pipeline, "fetch_article", fake_fetch_article)
    monkeypatch.setattr(pipeline, "fetch_aliases", fake_fetch_aliases)
    monkeypatch.setattr(pipeline, "fetch_fulltext", lambda title, lang="en": f"{title} full body.")
    monkeypatch.setattr(pipeline, "fetch_zh_extract", fake_fetch_zh)
    monkeypatch.setattr(pipeline, "discover", fake_discover)
    monkeypatch.setattr(pipeline, "score_candidates", fake_score)
    return calls


class TestRun:
    def test_full_run_produces_issue(self, root, fakes):
        code = pipeline.run(root, "2026-11-19")
        assert code == 0
        site = root / "site"
        assert (site / "index.html").exists()
        assert (site / "archive" / "2026-11-19.html").exists()
        assert (site / "feed.xml").exists()
        html = (site / "index.html").read_text(encoding="utf-8")
        assert html.count('class="card"') == 3
        assert "中文Topic" in html  # 中文摘要生效

    def test_artifacts_written(self, root, fakes):
        pipeline.run(root, "2026-11-19")
        data = root / "data" / "2026-11-19"
        for name in (
            "sampled.json",
            "wiki.json",
            "queries.json",
            "candidates.json",
            "scored.json",
            "brief.json",
            "health.json",
        ):
            assert (data / name).exists(), name

    def test_state_updated(self, root, fakes):
        pipeline.run(root, "2026-11-19")
        served = json.loads((root / "state" / "served.json").read_text(encoding="utf-8"))
        assert len(served["served"]) == 3
        assert all(e["date"] == "2026-11-19" for e in served["served"])
        domains = json.loads((root / "state" / "domains.json").read_text(encoding="utf-8"))
        assert len(domains["domains"]) == 3

    def test_second_run_skips(self, root, fakes):
        pipeline.run(root, "2026-11-19")
        n_discover = fakes["discover"]
        code = pipeline.run(root, "2026-11-19")
        assert code == 0
        assert fakes["discover"] == n_discover  # 未重跑信源
        served = json.loads((root / "state" / "served.json").read_text(encoding="utf-8"))
        assert len(served["served"]) == 3  # 未重复追加

    def test_force_reruns(self, root, fakes):
        pipeline.run(root, "2026-11-19")
        n = fakes["discover"]
        pipeline.run(root, "2026-11-19", force=True)
        assert fakes["discover"] > n
        served = json.loads((root / "state" / "served.json").read_text(encoding="utf-8"))
        assert len(served["served"]) == 3  # force 覆盖当日而非追加

    def test_next_day_dedupes(self, root, fakes):
        pipeline.run(root, "2026-11-19")
        pipeline.run(root, "2026-11-20")
        served = json.loads((root / "state" / "served.json").read_text(encoding="utf-8"))
        titles = [e["title"] for e in served["served"]]
        assert len(titles) == len(set(titles))  # 池只有 4 条，两天 6 抽必然去重后 ≤4
        assert (root / "site" / "archive" / "2026-11-20.html").exists()

    def test_stage_sample_stops_early(self, root, fakes):
        code = pipeline.run(root, "2026-11-19", stage="sample")
        assert code == 0
        assert (root / "data" / "2026-11-19" / "sampled.json").exists()
        assert not (root / "data" / "2026-11-19" / "candidates.json").exists()
        assert not (root / "site" / "index.html").exists()
        assert fakes["discover"] == 0
        # 未出页不得写 served
        assert not (root / "state" / "served.json").exists()

    def test_stage_resume_from_disk(self, root, fakes):
        pipeline.run(root, "2026-11-19", stage="queries")
        assert (root / "data" / "2026-11-19" / "queries.json").exists()
        pipeline.run(root, "2026-11-19", stage="render")
        assert (root / "site" / "index.html").exists()
        assert fakes["discover"] == 1  # 只补跑了缺失段

    def test_same_date_same_sample(self, root, fakes):
        pipeline.run(root, "2026-11-19", stage="sample")
        a = (root / "data" / "2026-11-19" / "sampled.json").read_bytes()
        pipeline.run(root, "2026-11-19", stage="sample", force=True)
        b = (root / "data" / "2026-11-19" / "sampled.json").read_bytes()
        assert a == b

    def test_empty_pool_returns_nonzero(self, root, fakes):
        (root / "state" / "pool.json").write_text(
            json.dumps({"built_at": 9e12, "entries": []}), encoding="utf-8"
        )
        code = pipeline.run(root, "2026-11-19")
        assert code != 0
        assert not (root / "site" / "index.html").exists()


class TestComplianceSwap:
    def test_fiction_entry_swapped_to_backup(self, root, fakes, monkeypatch):
        # 主选之一被类目复核否决 → 备用顶替，仍出 3 卡片
        real_fetch = pipeline.fetch_article

        def fetch_with_cats(title, lang="en"):
            info = real_fetch(title, lang=lang)
            if title == "Topic 0":
                info.categories = ["2015 concert films"]
            return info

        monkeypatch.setattr(pipeline, "fetch_article", fetch_with_cats)
        code = pipeline.run(root, "2026-11-19")
        assert code == 0
        served = json.loads((root / "state" / "served.json").read_text(encoding="utf-8"))
        titles = [e["title"] for e in served["served"]]
        assert "Topic 0" not in titles
        assert len(titles) == 3
        html = (root / "site" / "index.html").read_text(encoding="utf-8")
        assert html.count('class="card"') == 3

    def test_all_rejected_returns_nonzero(self, root, fakes, monkeypatch):
        def fetch_all_fiction(title, lang="en"):
            from openmind.wiki import ArticleInfo

            return ArticleInfo(title=title, lang=lang, extract="x", categories=["video games"])

        monkeypatch.setattr(pipeline, "fetch_article", fetch_all_fiction)
        code = pipeline.run(root, "2026-11-19")
        assert code != 0
        assert not (root / "site" / "index.html").exists()


class TestPoolExpiry:
    def test_stale_pool_triggers_refresh(self, root, fakes, monkeypatch):
        stale = json.loads((root / "state" / "pool.json").read_text(encoding="utf-8"))
        stale["built_at"] = 0  # 1970 → 必然过期
        (root / "state" / "pool.json").write_text(json.dumps(stale), encoding="utf-8")
        called = []

        def fake_build(state_dir, refresh=False):
            called.append(refresh)
            return [PoolEntry(**e) for e in stale["entries"]]

        monkeypatch.setattr(pipeline, "build_pool", fake_build)
        pipeline.run(root, "2026-11-19")
        assert called == [True]

    def test_fresh_pool_no_refresh(self, root, fakes, monkeypatch):
        called = []
        monkeypatch.setattr(pipeline, "build_pool", lambda *a, **k: called.append(1) or [])
        pipeline.run(root, "2026-11-19")
        assert called == []


class TestHealthSummary:
    def test_sources_ok_counts_distinct_ok_sources(self, root, fakes):
        pipeline.run(root, "2026-11-19")
        health = json.loads(
            (root / "data" / "2026-11-19" / "health.json").read_text(encoding="utf-8")
        )
        assert len(health) == 3  # 3 词条 × 1 fake 源
        html = (root / "site" / "index.html").read_text(encoding="utf-8")
        assert "本期信源：1/" in html


class TestCli:
    def test_run_wired(self, root, fakes, monkeypatch):
        from openmind.__main__ import main

        monkeypatch.setattr(pipeline, "project_root", lambda: root)
        assert main(["run", "--date", "2026-11-19"]) == 0
        assert (root / "site" / "index.html").exists()

    def test_run_default_date_today(self, root, fakes, monkeypatch):
        from openmind.__main__ import main

        monkeypatch.setattr(pipeline, "project_root", lambda: root)
        assert main(["run"]) == 0
        today = date.today().isoformat()
        assert (root / "site" / "archive" / f"{today}.html").exists()


class TestFulltextReview:
    """2026-11-18 用户要求：最终 3 条推出前全文复核，防正文夹带；只查要推出的条目。"""

    def test_buried_keyword_swaps_entry(self, root, fakes, monkeypatch):
        (root / "state" / "denylist_topics.txt").write_text("BadKeyword\n", encoding="utf-8")

        def fulltext(title, lang="en"):
            if title == "Topic 0":
                return "正常开头……中间夹带 badkeyword 内容……正常结尾。"
            return f"{title} clean body."

        monkeypatch.setattr(pipeline, "fetch_fulltext", fulltext)
        code = pipeline.run(root, "2026-11-19")
        assert code == 0
        served = json.loads((root / "state" / "served.json").read_text(encoding="utf-8"))
        titles = [e["title"] for e in served["served"]]
        assert "Topic 0" not in titles  # 标题干净但正文夹带 → 被顶替
        assert len(titles) == 3

    def test_zh_version_also_reviewed(self, root, fakes, monkeypatch):
        (root / "state" / "denylist_topics.txt").write_text("违禁词\n", encoding="utf-8")

        def fulltext(title, lang="en"):
            if lang == "zh" and title == "中文Topic 0":
                return "中文版正文夹带违禁词。"
            return f"{title} clean body."

        monkeypatch.setattr(pipeline, "fetch_fulltext", fulltext)
        code = pipeline.run(root, "2026-11-19")
        assert code == 0
        served = json.loads((root / "state" / "served.json").read_text(encoding="utf-8"))
        titles = [e["title"] for e in served["served"]]
        assert "Topic 0" not in titles  # 英文干净、中文夹带也要拦

    def test_fulltext_fetch_failure_falls_back_to_intro(self, root, fakes, monkeypatch):
        (root / "state" / "denylist_topics.txt").write_text("BadKeyword\n", encoding="utf-8")
        monkeypatch.setattr(pipeline, "fetch_fulltext", lambda t, lang="en": "")

        def article_with_intro(title, lang="en"):
            info = ArticleInfo(
                title=title, lang=lang, extract=f"{title} is a topic.", zh_title=f"中文{title}"
            )
            if title == "Topic 0":
                info.extract = "首段即含 badkeyword。"
            return info

        monkeypatch.setattr(pipeline, "fetch_article", article_with_intro)
        code = pipeline.run(root, "2026-11-19")
        assert code == 0  # 抓取失败降级首段复核，不阻断出页
        served = json.loads((root / "state" / "served.json").read_text(encoding="utf-8"))
        assert "Topic 0" not in [e["title"] for e in served["served"]]

    def test_only_final_entries_reviewed(self, root, fakes, monkeypatch):
        calls = []

        def fulltext(title, lang="en"):
            calls.append((title, lang))
            return f"{title} clean."

        monkeypatch.setattr(pipeline, "fetch_fulltext", fulltext)
        pipeline.run(root, "2026-11-19")
        en_calls = [t for t, lang in calls if lang == "en"]
        assert len(en_calls) == 3  # 只对最终 3 条做英文全文复核，无多余调用
