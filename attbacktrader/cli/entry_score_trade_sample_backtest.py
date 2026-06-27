"""Build a fixed entry-score trade-sample backtest from persisted factor evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_entry_score_trade_sample_backtest,
    render_entry_score_trade_sample_backtest_markdown_zh,
    safe_entry_score_trade_sample_backtest_dir_name,
    write_entry_score_trade_sample_backtest,
)
from attbacktrader.reports.writer import to_jsonable


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    environment_fit_path = _resolve_environment_fit_path(args.environment_fit)
    output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir(environment_fit_path, args.year, args.report_root)
    report = build_entry_score_trade_sample_backtest(
        environment_fit_path,
        year=args.year,
        min_entry_score=args.min_entry_score,
        sample_limit=args.sample_limit,
    )
    _, _, payload = write_entry_score_trade_sample_backtest(report, output_dir=output_dir)
    if args.print_markdown:
        print(render_entry_score_trade_sample_backtest_markdown_zh(payload))
    else:
        print(
            json.dumps(
                to_jsonable(
                    {
                        "schema": payload["schema"],
                        "run_id": payload.get("run_id"),
                        "year": payload.get("year"),
                        "score_gate": payload.get("score_gate"),
                        "funnel": payload.get("funnel"),
                        "summary": payload.get("summary"),
                        "artifacts": payload.get("artifacts"),
                    }
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a fixed entry-score trade-sample backtest")
    parser.add_argument(
        "--environment-fit",
        required=True,
        help="Path to environment_fit.enriched.json/environment_fit.json, or a directory containing one",
    )
    parser.add_argument("--year", type=int, default=2024, help="Entry year to validate")
    parser.add_argument("--min-entry-score", type=float, default=4.0, help="Minimum score required for entry")
    parser.add_argument("--sample-limit", type=int, default=30, help="Sample rows per Markdown section")
    parser.add_argument("--output-dir", help="Output directory for entry score backtest artifacts")
    parser.add_argument("--report-root", default="reports", help="Default report root when --output-dir is omitted")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown report instead of JSON summary")
    return parser.parse_args(argv)


def _resolve_environment_fit_path(value: str) -> Path:
    path = Path(value)
    if path.is_dir():
        enriched = path / "environment_fit.enriched.json"
        if enriched.exists():
            return enriched
        full_entry_scope = path / "full_entry_scope_environment_fit_review" / "environment_fit.enriched.json"
        if full_entry_scope.exists():
            return full_entry_scope
        plain = path / "environment_fit.json"
        if plain.exists():
            return plain
        raise FileNotFoundError(f"no environment_fit.enriched.json or environment_fit.json under {path}")
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def _default_output_dir(environment_fit_path: Path, year: int, report_root: str) -> Path:
    return Path(report_root) / safe_entry_score_trade_sample_backtest_dir_name(environment_fit_path, year=year)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
