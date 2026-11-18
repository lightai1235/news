"""CLI 入口：python -m openmind {pool,run}。"""

from __future__ import annotations

import argparse
import logging
from datetime import date


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openmind", description="拓界 OpenMind 每日随机知识站")
    sub = parser.add_subparsers(dest="command", required=True)

    p_pool = sub.add_parser("pool", help="构建/刷新候选池")
    p_pool.add_argument("--refresh", action="store_true", help="强制重新抓取维基列表")

    p_run = sub.add_parser("run", help="生成一期")
    p_run.add_argument("--date", default=None, help="日期 YYYY-MM-DD（即随机种子），默认今天")
    p_run.add_argument("--force", action="store_true", help="覆盖当日已有产物")
    p_run.add_argument(
        "--stage",
        choices=["sample", "wiki", "queries", "discover", "score", "brief", "render"],
        help="只跑到指定段（断点调试）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from openmind import pipeline

    root = pipeline.project_root()
    if args.command == "pool":
        from openmind.pool import build_pool

        entries = build_pool(root / "state", refresh=args.refresh)
        print(f"[openmind] pool: {len(entries)} entries")
        return 0
    date_iso = args.date or date.today().isoformat()
    return pipeline.run(root, date_iso, force=args.force, stage=args.stage)


if __name__ == "__main__":
    raise SystemExit(main())
