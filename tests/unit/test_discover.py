"""T5 discover 调度测试：并发聚合、故障隔离、health.json 产出。"""

import json

from openmind.discover import discover
from openmind.sources.base import Candidate, Query


class GoodSource:
    name = "good_test"
    needs_key = False

    def search(self, query: Query) -> list[Candidate]:
        return [
            Candidate(
                url=f"https://good.example/{query.title}",
                title=query.title,
                kind="article",
                source=self.name,
            )
        ]


class BadSource:
    name = "bad_test"
    needs_key = False

    def search(self, query: Query) -> list[Candidate]:
        raise RuntimeError("boom")


class KeySource:
    name = "key_test"
    needs_key = True

    def search(self, query: Query) -> list[Candidate]:
        return [Candidate(url="https://key.example/x", title="x", kind="article", source=self.name)]


class TestDiscover:
    def test_aggregates_candidates(self):
        q = Query(title="Bioacoustics", lang="en", groups={"exact": '"Bioacoustics"'})
        result = discover([q], sources=[GoodSource()], available_keys=set())
        assert len(result.candidates["Bioacoustics"]) == 1

    def test_bad_source_isolated(self):
        q = Query(title="X", lang="en")
        result = discover([q], sources=[GoodSource(), BadSource()], available_keys=set())
        assert len(result.candidates["X"]) == 1
        health = {h["source"]: h for h in result.health}
        assert health["bad_test"]["ok"] is False
        assert health["good_test"]["ok"] is True

    def test_key_source_skipped_without_key(self):
        q = Query(title="X", lang="en")
        result = discover([q], sources=[KeySource()], available_keys=set())
        assert result.candidates["X"] == []
        h = result.health[0]
        assert h["status"] == "skipped_no_key"

    def test_key_source_runs_with_key(self):
        q = Query(title="X", lang="en")
        result = discover([q], sources=[KeySource()], available_keys={"key_test"})
        assert len(result.candidates["X"]) == 1

    def test_health_json_serializable(self):
        q = Query(title="X", lang="en")
        result = discover([q], sources=[GoodSource(), BadSource()], available_keys=set())
        text = json.dumps(result.health, ensure_ascii=False)
        assert "good_test" in text

    def test_multiple_queries_multiple_titles(self):
        qs = [Query(title="A", lang="en"), Query(title="B", lang="en")]
        result = discover(qs, sources=[GoodSource()], available_keys=set())
        assert set(result.candidates) == {"A", "B"}
