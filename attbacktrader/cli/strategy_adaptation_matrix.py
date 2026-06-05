"""Build a strategy adaptation matrix from known market-type run artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_market_type_summary,
    build_strategy_adaptation_matrix,
    render_strategy_adaptation_matrix_markdown_zh,
    safe_strategy_adaptation_matrix_dir_name,
    write_strategy_adaptation_matrix,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    matrix = _build_matrix(args)
    output_dir = Path(args.output_dir) if args.output_dir is not None else _default_output_dir(args)
    json_path, markdown_path = write_strategy_adaptation_matrix(matrix, output_dir=output_dir)
    payload = {
        "schema": matrix["schema"],
        "source_summary_path": matrix["source_summary_path"],
        "market_type_count": matrix["market_type_count"],
        "segment_count": matrix["segment_count"],
        "trade_count": matrix["trade_count"],
        "artifacts": {
            "strategy_adaptation_matrix_json_path": str(json_path),
            "strategy_adaptation_matrix_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_strategy_adaptation_matrix_markdown_zh(matrix))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a strategy adaptation matrix")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--market-type-summary", default=None, help="Path to market_type_summary.json")
    source.add_argument("--manifest", default=None, help="market_segment_run_manifest.json; summary is built in memory")
    parser.add_argument("--report-root", default="reports", help="Root containing run artifact directories")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--min-segment-trades", type=int, default=5)
    parser.add_argument("--min-factor-trades", type=int, default=3)
    parser.add_argument("--preferred-win-rate", type=float, default=0.55)
    parser.add_argument("--avoid-win-rate", type=float, default=0.45)
    parser.add_argument("--top-factors", type=int, default=12)
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


def _build_matrix(args: argparse.Namespace) -> dict:
    if args.market_type_summary is not None:
        source = Path(args.market_type_summary)
    else:
        source = build_market_type_summary(
            args.manifest,
            report_root=args.report_root,
            min_segment_trades=args.min_segment_trades,
        )
    return build_strategy_adaptation_matrix(
        source,
        min_factor_trades=args.min_factor_trades,
        preferred_win_rate=args.preferred_win_rate,
        avoid_win_rate=args.avoid_win_rate,
        top_factors=args.top_factors,
    )


def _default_output_dir(args: argparse.Namespace) -> Path:
    source_path = args.market_type_summary or args.manifest
    return Path(args.report_root) / safe_strategy_adaptation_matrix_dir_name(source_path)


if __name__ == "__main__":
    raise SystemExit(main())
