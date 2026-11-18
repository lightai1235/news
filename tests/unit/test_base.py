"""T1 数据契约测试：Candidate / Query 可 JSON 序列化往返，SourcePort 注册表可用。"""

import json

from openmind.sources.base import Candidate, Query, SourcePort, register, registry


class TestCandidate:
    def test_json_roundtrip_preserves_all_fields(self):
        c = Candidate(
            url="https://arxiv.org/abs/2201.00001",
            title="Bioacoustics of whales",
            snippet="A study of whale sound communication.",
            kind="paper",
            source="arxiv",
            lang="en",
            published="2022-01-01",
            meta={"pages": 42},
        )
        restored = Candidate.from_json(c.to_json())
        assert restored == c

    def test_json_roundtrip_is_stable_text(self):
        c = Candidate(url="https://a.example/x", title="T", kind="article", source="hn")
        assert c.to_json() == Candidate.from_json(c.to_json()).to_json()
        json.loads(c.to_json())

    def test_defaults_are_conservative(self):
        c = Candidate(url="https://a.example/x", title="T", kind="article", source="hn")
        assert c.snippet == ""
        assert c.lang == "en"
        assert c.published == ""
        assert c.meta == {}
        assert c.score is None
        assert c.reason == ""

    def test_kind_must_be_known(self):
        import pytest

        with pytest.raises(ValueError):
            Candidate(url="https://a.example/x", title="T", kind="poem", source="hn")


class TestQuery:
    def test_json_roundtrip_preserves_groups(self):
        q = Query(
            title="Bioacoustics",
            lang="en",
            aliases=["生物声学"],
            groups={
                "exact": '"Bioacoustics" review',
                "concept": "animal sound research",
                "zh": "生物声学 研究",
            },
        )
        assert Query.from_json(q.to_json()) == q

    def test_groups_default_empty(self):
        q = Query(title="X", lang="en")
        assert q.aliases == []
        assert q.groups == {}


class TestRegistry:
    def test_register_and_lookup(self):
        class DummySource:
            name = "dummy_test_source"
            needs_key = False

            def search(self, query: Query) -> list[Candidate]:
                return []

        register(DummySource())
        assert "dummy_test_source" in registry()
        src = registry()["dummy_test_source"]
        assert isinstance(src, SourcePort)
        assert src.search(Query(title="X", lang="en")) == []

    def test_duplicate_registration_rejected(self):
        import pytest

        class Dup:
            name = "dup_test_source"
            needs_key = False

            def search(self, query: Query) -> list[Candidate]:
                return []

        register(Dup())
        with pytest.raises(ValueError):
            register(Dup())
