"""跨运行持久状态（SPEC §5.9）：served.json（180 天窗口）+ domains.json（领域加权）。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

WINDOW_DAYS = 180


@dataclass
class State:
    served: list[dict] = field(default_factory=list)
    domains: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, state_dir: Path) -> State:
        served: list[dict] = []
        domains: dict[str, str] = {}
        sp = state_dir / "served.json"
        if sp.exists():
            served = json.loads(sp.read_text(encoding="utf-8")).get("served", [])
        dp = state_dir / "domains.json"
        if dp.exists():
            domains = json.loads(dp.read_text(encoding="utf-8")).get("domains", {})
        return cls(served=served, domains=domains)

    def recent_titles(self, today: date, window_days: int = WINDOW_DAYS) -> set[str]:
        cutoff = (today - timedelta(days=window_days)).isoformat()
        return {e["title"] for e in self.served if e["date"] >= cutoff}

    def append_served(self, items: list[tuple[str, str]], today: date) -> None:
        iso = today.isoformat()
        for title, domain in items:
            self.served.append({"title": title, "date": iso, "domain": domain})
            self.domains[domain] = iso

    def save(self, state_dir: Path, today: date | None = None) -> None:
        state_dir.mkdir(parents=True, exist_ok=True)
        served = self.served
        if today is not None:
            cutoff = (today - timedelta(days=WINDOW_DAYS)).isoformat()
            served = [e for e in served if e["date"] >= cutoff]
            self.served = served
        (state_dir / "served.json").write_text(
            json.dumps({"version": 1, "served": served}, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        (state_dir / "domains.json").write_text(
            json.dumps({"domains": self.domains}, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
