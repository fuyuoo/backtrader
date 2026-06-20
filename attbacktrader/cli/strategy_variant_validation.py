"""Compare baseline and strategy-variant market-type summaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_strategy_variant_validation,
    render_strategy_variant_validation_markdown_zh,
    safe_strategy_variant_validation_dir_name,
    write_strategy_variant_validation,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    validation = build_strategy_variant_validation(args.baseline_summary, args.variant_summary)
    output_dir = Path(args.output_dir) if args.output_dir is not None else _default_output_dir(args)
    json_path, markdown_path = write_strategy_variant_validation(validation, output_dir=output_dir)
    payload = {
        "schema": validation["schema"],
        "market_type_count": validation["market_type_count"],
        "validation_warning_count": len(validation["validation_warnings"]),
        "artifacts": {
            "strategy_variant_validation_json_path": str(json_path),
            "strategy_variant_validation_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_strategy_variant_validation_markdown_zh(validation))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare strategy variant market-type summaries")
    parser.add_argument("--baseline-summary", required=True, help="Path to baseline market_type_summary.json")
    parser.add_argument("--variant-summary", required=True, help="Path to variant market_type_summary.json")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--print-markdown", action="store_true")
    return parser.parse_args(argv)


def _default_output_dir(args: argparse.Namespace) -> Path:
    return Path("reports") / safe_strategy_variant_validation_dir_name(args.variant_summary)


if __name__ == "__main__":
    raise SystemExit(main())
