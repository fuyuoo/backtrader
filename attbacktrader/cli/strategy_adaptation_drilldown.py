"""Drill down a strategy adaptation matrix factor into review samples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_strategy_adaptation_drilldown,
    render_strategy_adaptation_drilldown_markdown_zh,
    safe_strategy_adaptation_drilldown_dir_name,
    write_strategy_adaptation_drilldown,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    drilldown = build_strategy_adaptation_drilldown(
        args.matrix,
        market_type_id=args.market_type_id,
        market_type_label_zh=args.market_type_label_zh,
        section=args.section,
        factor_key=args.factor_key,
        factor_value=args.factor_value,
        factor_rank=args.factor_rank,
        report_root=args.report_root,
        limit=args.limit,
        context_limit=args.context_limit,
    )
    output_dir = Path(args.output_dir) if args.output_dir is not None else _default_output_dir(args)
    json_path, markdown_path = write_strategy_adaptation_drilldown(drilldown, output_dir=output_dir)
    payload = {
        "schema": drilldown["schema"],
        "market_type_id": drilldown["lookup"]["market_type_id"],
        "section": drilldown["lookup"]["section"],
        "factor_key": drilldown["lookup"]["factor_key"],
        "factor_value": drilldown["lookup"]["factor_value"],
        "sample_count": drilldown["sample_count"],
        "artifacts": {
            "strategy_adaptation_drilldown_json_path": str(json_path),
            "strategy_adaptation_drilldown_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_strategy_adaptation_drilldown_markdown_zh(drilldown))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Drill down one strategy adaptation matrix factor")
    parser.add_argument("--matrix", required=True, help="Path to strategy_adaptation_matrix.json")
    parser.add_argument("--market-type-id", default=None)
    parser.add_argument("--market-type-label-zh", default=None)
    parser.add_argument(
        "--section",
        default="entry_factor_summaries",
        choices=[
            "entry_factor_summaries",
            "winning_entry_factors",
            "losing_entry_factors",
            "sold_too_early_entry_factors",
        ],
    )
    parser.add_argument("--factor-key", default=None)
    parser.add_argument("--factor-value", default=None)
    parser.add_argument("--factor-rank", type=int, default=1)
    parser.add_argument("--report-root", default="reports")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--context-limit", type=int, default=20)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--print-markdown", action="store_true")
    return parser.parse_args(argv)


def _default_output_dir(args: argparse.Namespace) -> Path:
    return Path(args.report_root) / safe_strategy_adaptation_drilldown_dir_name(
        args.matrix,
        market_type_id=args.market_type_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
