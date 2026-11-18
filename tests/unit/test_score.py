"""T6 评分漏斗测试：黑名单否决、粗排截断、精排、去重、同域名限额、Top-10。"""

from pathlib import Path

import pytest

from openmind.compliance import Compliance
from openmind.score import dedupe, normalize_url, score_candidates
from openmind.sources.base import Candidate


@pytest.fixture()
def comp(tmp_path: Path) -> Compliance:
    (tmp_path / "denylist_topics.txt").write_text("", encoding="utf-8")
    (tmp_path / "denylist_domains.txt").write_text("spamfarm.example\n", encoding="utf-8")
    (tmp_path / "allowlist_domains.txt").write_text("arxiv.org\n", encoding="utf-8")
    return Compliance.load(tmp_path)


def cand(
    url: str, title: str = "Bioacoustics review", kind: str = "article", source: str = "test", **kw
) -> Candidate:
    return Candidate(url=url, title=title, kind=kind, source=source, **kw)


class TestNormalizeUrl:
    def test_strips_tracking_params(self):
        assert (
            normalize_url("https://a.example/x?utm_source=rss&id=7") == "https://a.example/x?id=7"
        )

    def test_strips_fragment(self):
        assert normalize_url("https://a.example/x#sec") == "https://a.example/x"

    def test_lowercases_host(self):
        assert normalize_url("https://A.EXAMPLE/x") == "https://a.example/x"


class TestDedupe:
    def test_same_url_different_tracking_merged(self):
        cs = [cand("https://a.example/x?utm_source=a"), cand("https://a.example/x")]
        assert len(dedupe(cs)) == 1

    def test_different_urls_kept(self):
        cs = [cand("https://a.example/x"), cand("https://b.example/y")]
        assert len(dedupe(cs)) == 2


class TestScore:
    def test_denylisted_rejected(self, comp):
        cs = [
            cand("https://spamfarm.example/x"),
            cand("https://good.example/x", title="Bioacoustics"),
        ]
        scored, rejected = score_candidates(
            cs, "Bioacoustics", comp, fetch_text=lambda u: "bioacoustics " * 2000
        )
        assert len(scored) == 1
        assert len(rejected) == 1
        assert rejected[0]["url"].startswith("https://spamfarm.example")

    def test_top10_cap(self, comp):
        cs = [cand(f"https://d{i}.example/x") for i in range(25)]
        scored, _ = score_candidates(cs, "Bioacoustics", comp, fetch_text=lambda u: "word " * 500)
        assert len(scored) <= 10

    def test_same_domain_max3(self, comp):
        cs = [cand(f"https://same.example/p{i}") for i in range(8)]
        scored, _ = score_candidates(cs, "Bioacoustics", comp, fetch_text=lambda u: "word " * 500)
        assert len(scored) <= 3

    def test_authority_boosts_score(self, comp):
        cs = [
            cand("https://arxiv.org/abs/1", kind="paper", title="Bioacoustics"),
            cand("https://blog.example/x", title="Bioacoustics"),
        ]
        scored, _ = score_candidates(
            cs, "Bioacoustics", comp, fetch_text=lambda u: "bioacoustics " * 2000
        )
        by_url = {c.url: c.score for c in scored}
        assert by_url["https://arxiv.org/abs/1"] > by_url["https://blog.example/x"]

    def test_reason_and_score_present(self, comp):
        cs = [cand("https://arxiv.org/abs/1", kind="paper", published="2022-01-01")]
        scored, _ = score_candidates(cs, "Bioacoustics", comp, fetch_text=lambda u: "")
        assert scored[0].score is not None
        assert scored[0].reason

    def test_low_score_filtered(self, comp):
        cs = [cand("https://unknown.example/x", title="完全无关的标题")]
        scored, _ = score_candidates(cs, "Bioacoustics", comp, fetch_text=lambda u: "")
        assert scored == []

    def test_coarse_rank_limits_fetch(self, comp):
        calls = []

        def fetch(u):
            calls.append(u)
            return "bioacoustics " * 300

        cs = [cand(f"https://d{i}.example/bioacoustics") for i in range(40)]
        score_candidates(cs, "Bioacoustics", comp, fetch_text=fetch)
        assert len(calls) <= 20

    def test_dead_link_dropped_in_fine_rank(self, comp):
        def fetch(u):
            if "dead" in u:
                raise RuntimeError("404")
            return "bioacoustics sound " * 200

        cs = [
            cand("https://dead.example/x", title="Bioacoustics"),
            cand("https://live.example/x", title="Bioacoustics"),
        ]
        scored, _ = score_candidates(cs, "Bioacoustics", comp, fetch_text=fetch)
        assert all("dead" not in c.url for c in scored)
