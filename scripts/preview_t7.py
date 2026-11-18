"""T7 人工浏览预览：用真实池抽 3 词条 + 真实维基摘要渲染 demo 站点。

不写入正式 site/ 与 state/，输出到 .preview-t7/（gitignore）。
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from openmind.brief import make_brief  # noqa: E402
from openmind.pool import PoolEntry  # noqa: E402
from openmind.render import Issue, render_issue  # noqa: E402
from openmind.sample import sample  # noqa: E402
from openmind.sources.base import Candidate  # noqa: E402
from openmind.sources.wiki_links import classify_url  # noqa: E402
from openmind.wiki import fetch_article, fetch_external_links  # noqa: E402


def main() -> None:
    data = json.loads((ROOT / "state" / "pool.json").read_text("utf-8"))
    pool = [PoolEntry(**e) for e in data["entries"]]
    date = datetime.now(UTC).date().isoformat()
    picked = sample(pool, date, served=[], domains={})[:3]

    briefs, items = [], {}
    for e in picked:
        info = fetch_article(e.canonical_title, e.lang)
        b = make_brief(info, domain=e.domain)
        briefs.append(b)
        urls = fetch_external_links(e.canonical_title, e.lang)[:12]
        cs = []
        for u in urls:
            kind = classify_url(u)
            cs.append(
                Candidate(
                    url=u,
                    title=u.split("/")[-1][:60] or u,
                    kind=kind,
                    source="wiki_links",
                    score=6.0,
                    reason="维基外链 · 预览样例",
                )
            )
        items[e.canonical_title] = cs[:10]

    issue = Issue(
        date=date,
        briefs=briefs,
        items=items,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        sources_ok=1,
        sources_total=12,
        base_url="https://lightai1235.github.io/news",
    )
    out = ROOT / ".preview-t7"
    render_issue(issue, out)
    print(f"preview rendered: {out / 'index.html'}")
    for b in briefs:
        print(f"  - {b.zh_title or b.title} [{b.domain}] zh_absent={b.zh_absent}")


if __name__ == "__main__":
    main()
