"""站点渲染（SPEC §5.7）：今日页 / 归档页 / 按月索引 / RSS。

- Jinja2 autoescape 全开；模板不含脚本，无埋点、无推荐位（硬约束由测试保证）。
- 相同输入字节级一致：不读取系统时钟，时间戳全部来自 Issue。
- 归档索引从磁盘已有 archive/<date>.html 扫描重建，天然幂等。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from openmind.brief import EntryBrief
from openmind.sources.base import Candidate

KIND_LABELS = {
    "article": "文章",
    "video": "视频",
    "paper": "论文",
    "discussion": "讨论",
    "wechat": "公众号",
}
FEED_MAX_ITEMS = 30
_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.html$")
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"


@dataclass
class Issue:
    date: str
    briefs: list[EntryBrief]
    items: dict[str, list[Candidate]]
    generated_at: str
    sources_ok: int = 0
    sources_total: int = 12
    base_url: str = ""
    extra: dict = field(default_factory=dict)


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    return env


def _rfc822(date_iso: str) -> str:
    dt = datetime.fromisoformat(date_iso).replace(hour=0, tzinfo=UTC)  # 北京 08:00 发布
    return format_datetime(dt)


def _render_daily(env: Environment, issue: Issue, in_archive: bool) -> str:
    cards = [{"brief": b, "items": issue.items.get(b.title, [])} for b in issue.briefs]
    return env.get_template("daily.html").render(
        issue=issue,
        cards=cards,
        kind_labels=KIND_LABELS,
        sources_ok=issue.sources_ok,
        sources_total=issue.sources_total,
        generated_at=issue.generated_at,
        feed_href="../feed.xml" if in_archive else "feed.xml",
        archive_href="index.html" if in_archive else "archive/index.html",
    )


def _scan_dates(site_dir: Path) -> list[str]:
    archive = site_dir / "archive"
    dates = []
    if archive.is_dir():
        for f in archive.iterdir():
            m = _DATE_RE.match(f.name)
            if m:
                dates.append(m.group(1))
    return sorted(dates, reverse=True)


def _render_archive_index(env: Environment, site_dir: Path, issue: Issue) -> str:
    dates = _scan_dates(site_dir)
    months: list[dict] = []
    for d in dates:
        month = d[:7]
        if not months or months[-1]["month"] != month:
            months.append({"month": month, "dates": []})
        months[-1]["dates"].append(d)
    return env.get_template("archive_index.html").render(
        months=months,
        sources_ok=issue.sources_ok,
        sources_total=issue.sources_total,
        generated_at=issue.generated_at,
        feed_href="../feed.xml",
        archive_href="index.html",
    )


def _render_feed(env: Environment, site_dir: Path, issue: Issue) -> str:
    # 重建最近 N 期：当期用内存数据，历史期从已渲染 HTML 无法还原简介，
    # 故 feed 条目描述用当期数据 + 历史期标题占位（日期链接仍可点）。
    dates = _scan_dates(site_dir)[:FEED_MAX_ITEMS]
    entries = []
    for d in dates:
        if d == issue.date:
            titles = " / ".join(b.zh_title or b.title for b in issue.briefs)
            desc = "\n".join(f"【{b.zh_title or b.title}】{b.brief}" for b in issue.briefs)
        else:
            titles = d
            desc = f"{d} 期归档，点击查看当日词条与信源。"
        entries.append(
            {
                "date": d,
                "titles": titles,
                "description": desc,
                "pub_date": _rfc822(d),
            }
        )
    return env.get_template("feed.xml").render(
        base_url=issue.base_url.rstrip("/"),
        build_date=_rfc822(issue.date),
        entries=entries,
    )


def render_issue(issue: Issue, site_dir: Path) -> None:
    site_dir = Path(site_dir)
    (site_dir / "archive").mkdir(parents=True, exist_ok=True)
    env = _env()

    daily_root = _render_daily(env, issue, in_archive=False)
    daily_archive = _render_daily(env, issue, in_archive=True)
    (site_dir / "index.html").write_text(daily_root, encoding="utf-8")
    (site_dir / "archive" / f"{issue.date}.html").write_text(daily_archive, encoding="utf-8")
    (site_dir / "archive" / "index.html").write_text(
        _render_archive_index(env, site_dir, issue), encoding="utf-8"
    )
    (site_dir / "feed.xml").write_text(_render_feed(env, site_dir, issue), encoding="utf-8")
