"""T4 查询扩展廉价版测试（无 LLM，纯逻辑）。"""

from openmind.queries import build_queries
from openmind.wiki import ArticleInfo


def info(**kw) -> ArticleInfo:
    base = dict(title="Bioacoustics", lang="en", extract="", zh_title="", aliases=[])
    base.update(kw)
    return ArticleInfo(**base)


class TestBuildQueries:
    def test_produces_two_to_three_groups(self):
        q = build_queries(info(extract="Bioacoustics is the study of sound in animals."))
        assert 2 <= len(q.groups) <= 3
        assert "exact" in q.groups

    def test_exact_group_quotes_title(self):
        q = build_queries(info())
        assert '"Bioacoustics"' in q.groups["exact"]

    def test_aliases_from_redirects_and_zh(self):
        q = build_queries(info(zh_title="生物声学", aliases=["Animal acoustics"]))
        assert "生物声学" in q.aliases
        assert "Animal acoustics" in q.aliases

    def test_zh_group_uses_zh_title(self):
        q = build_queries(info(zh_title="生物声学"))
        assert "zh" in q.groups
        assert "生物声学" in q.groups["zh"]

    def test_no_zh_title_no_zh_group(self):
        q = build_queries(info())
        assert "zh" not in q.groups

    def test_concept_group_from_extract_keywords(self):
        q = build_queries(
            info(extract="Bioacoustics is the study of sound production and reception in animals.")
        )
        assert "concept" in q.groups
        assert "sound" in q.groups["concept"]

    def test_deterministic(self):
        i = info(extract="Bioacoustics is the study of sound in animals.", zh_title="生物声学")
        assert build_queries(i).to_json() == build_queries(i).to_json()

    def test_json_roundtrip(self):
        from openmind.sources.base import Query

        q = build_queries(info(zh_title="生物声学"))
        assert Query.from_json(q.to_json()) == q
