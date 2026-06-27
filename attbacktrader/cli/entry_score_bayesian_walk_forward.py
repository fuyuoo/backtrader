"""Run Bayesian walk-forward tuning for completed-trade entry-score weights."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_entry_score_bayesian_walk_forward,
    render_entry_score_bayesian_walk_forward_markdown_zh,
    safe_entry_score_bayesian_walk_forward_dir_name,
    write_entry_score_bayesian_walk_forward,
)
from attbacktrader.reports.writer import to_jsonable


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    environment_fit_path = _resolve_environment_fit_path(args.environment_fit)
    output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir(environment_fit_path, args.report_root)
    report = build_entry_score_bayesian_walk_forward(
        environment_fit_path,
        first_train_year=args.first_train_year,
        last_test_year=args.last_test_year,
        train_years=args.train_years,
        n_trials=args.n_trials,
        seed=args.seed,
        min_train_pass_rate=args.min_train_pass_rate,
        min_train_sample_count=args.min_train_sample_count,
        min_train_yearly_pass_count=args.min_train_yearly_pass_count,
        optimizer=args.optimizer,
        sample_limit=args.sample_limit,
    )
    _, _, payload = write_entry_score_bayesian_walk_forward(report, output_dir=output_dir)
    if args.print_markdown:
        print(render_entry_score_bayesian_walk_forward_markdown_zh(payload))
    else:
        print(
            json.dumps(
                to_jsonable(
                    {
                        "schema": payload["schema"],
                        "run_id": payload.get("run_id"),
                        "configuration": payload.get("configuration"),
                        "aggregate_oos": payload.get("aggregate_oos"),
                        "fold_count": len(payload.get("folds", [])),
                        "artifacts": payload.get("artifacts"),
                    }
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Bayesian walk-forward tuning for entry-score weights")
    parser.add_argument(
        "--environment-fit",
        required=True,
        help="Path to environment_fit.enriched.json/environment_fit.json, or a directory containing one",
    )
    parser.add_argument("--first-train-year", type=int, default=2015)
    parser.add_argument("--last-test-year", type=int, default=2024)
    parser.add_argument("--train-years", type=int, default=5)
    parser.add_argument("--n-trials", type=int, default=80, help="Trials per fold")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-train-pass-rate", type=float, default=0.20)
    parser.add_argument("--min-train-sample-count", type=int, default=300)
    parser.add_argument("--min-train-yearly-pass-count", type=int, default=0)
    parser.add_argument("--optimizer", choices=["optuna", "random"], default="optuna")
    parser.add_argument("--sample-limit", type=int, default=30, help="Sample rows per Markdown section")
    parser.add_argument("--output-dir", help="Output directory for walk-forward artifacts")
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


def _default_output_dir(environment_fit_path: Path, report_root: str) -> Path:
    return Path(report_root) / safe_entry_score_bayesian_walk_forward_dir_name(environment_fit_path)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
