"""T3 状态管理测试：served 180 天窗口、domains 更新、JSON 往返。"""

import json
from datetime import date

from openmind.state import State


class TestState:
    def test_load_missing_files_defaults(self, tmp_path):
        s = State.load(tmp_path)
        assert s.served == []
        assert s.domains == {}

    def test_append_served_and_save(self, tmp_path):
        s = State.load(tmp_path)
        s.append_served([("Bioacoustics", "自然科学")], date(2026, 11, 18))
        s.save(tmp_path)
        s2 = State.load(tmp_path)
        assert s2.served == [{"title": "Bioacoustics", "date": "2026-11-18", "domain": "自然科学"}]

    def test_recent_titles_within_window(self, tmp_path):
        s = State.load(tmp_path)
        s.append_served([("A", "数学")], date(2026, 11, 1))
        s.append_served([("B", "历史")], date(2026, 1, 1))
        recent = s.recent_titles(date(2026, 11, 18), window_days=180)
        assert "A" in recent
        assert "B" not in recent

    def test_domains_updated_on_append(self, tmp_path):
        s = State.load(tmp_path)
        s.append_served([("A", "数学"), ("B", "历史")], date(2026, 11, 18))
        assert s.domains == {"数学": "2026-11-18", "历史": "2026-11-18"}
        s.append_served([("C", "数学")], date(2026, 11, 19))
        assert s.domains["数学"] == "2026-11-19"
        assert s.domains["历史"] == "2026-11-18"

    def test_save_is_stable_json(self, tmp_path):
        s = State.load(tmp_path)
        s.append_served([("A", "数学")], date(2026, 11, 18))
        s.save(tmp_path)
        first = (tmp_path / "served.json").read_text(encoding="utf-8")
        s.save(tmp_path)
        assert (tmp_path / "served.json").read_text(encoding="utf-8") == first
        json.loads(first)

    def test_prune_old_served_on_save(self, tmp_path):
        s = State.load(tmp_path)
        s.append_served([("Old", "数学")], date(2025, 1, 1))
        s.append_served([("New", "历史")], date(2026, 11, 18))
        s.save(tmp_path, today=date(2026, 11, 18))
        s2 = State.load(tmp_path)
        assert [e["title"] for e in s2.served] == ["New"]
