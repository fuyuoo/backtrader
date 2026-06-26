"""Build a score-gate counterfactual funnel from persisted factor evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_score_gate_counterfactual_funnel,
    render_score_gate_counterfactual_funnel_markdown_zh,
    safe_score_gate_counterfactual_funnel_dir_name,
    write_score_gate_counterfactual_funnel,
)
from attbacktrader.reports.writer import to_jsonable


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    environment_fit_path = _resolve_environment_fit_path(args.environment_fit)
    matrix_path = _resolve_matrix_path(args.factor_matrix)
    output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir(matrix_path, args.report_root)
    report = build_score_gate_counterfactual_funnel(
        environment_fit_path,
        matrix_path,
        min_positive_sample_count=args.min_positive_sample_count,
        min_positive_years=args.min_positive_years,
        min_positive_average_return_pct=args.min_positive_average_return_pct,
        min_positive_win_rate=args.min_positive_win_rate,
        min_positive_max_loss_pct=args.min_positive_max_loss_pct,
        min_positive_hits=args.min_positive_hits,
        min_risk_sample_count=args.min_risk_sample_count,
        risk_average_return_ceiling_pct=args.risk_average_return_ceiling_pct,
        risk_win_rate_ceiling=args.risk_win_rate_ceiling,
        risk_max_loss_ceiling_pct=args.risk_max_loss_ceiling_pct,
        max_risk_hits=args.max_risk_hits,
        excluded_field_prefixes=args.exclude_field_prefix,
        gate_candidate_limit=args.gate_candidate_limit,
        sample_limit=args.sample_limit,
    )
    _, _, payload = write_score_gate_counterfactual_funnel(report, output_dir=output_dir)
    if args.print_markdown:
        print(render_score_gate_counterfactual_funnel_markdown_zh(payload))
    else:
        print(
            json.dumps(
                to_jsonable(
                    {
                        "schema": payload["schema"],
                        "run_id": payload.get("run_id"),
                        "funnel": payload.get("funnel"),
                        "positive_gate_candidate_count": len(
                            (payload.get("factor_screen") or {}).get("positive_gate_candidates") or []
                        ),
                        "risk_gate_candidate_count": len(
                            (payload.get("factor_screen") or {}).get("risk_gate_candidates") or []
                        ),
                        "artifacts": payload.get("artifacts"),
                    }
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a score-gate counterfactual funnel")
    parser.add_argument(
        "--environment-fit",
        required=True,
        help="Path to environment_fit.enriched.json/environment_fit.json, or a directory containing one",
    )
    parser.add_argument(
        "--factor-matrix",
        required=True,
        help="Path to segmented_factor_contribution_matrix.json, or a directory containing one",
    )
    parser.add_argument("--output-dir", help="Output directory for score_gate_counterfactual_funnel artifacts")
    parser.add_argument("--report-root", default="reports", help="Default report root when --output-dir is omitted")
    parser.add_argument("--min-positive-sample-count", type=int, default=300)
    parser.add_argument("--min-positive-years", type=int, default=8)
    parser.add_argument("--min-positive-average-return-pct", type=float, default=0.015)
    parser.add_argument("--min-positive-win-rate", type=float, default=0.49)
    parser.add_argument("--min-positive-max-loss-pct", type=float, default=-0.40)
    parser.add_argument("--min-positive-hits", type=int, default=1)
    parser.add_argument("--min-risk-sample-count", type=int, default=300)
    parser.add_argument("--risk-average-return-ceiling-pct", type=float, default=0.0)
    parser.add_argument("--risk-win-rate-ceiling", type=float, default=0.42)
    parser.add_argument("--risk-max-loss-ceiling-pct", type=float)
    parser.add_argument("--max-risk-hits", type=int, default=0)
    parser.add_argument(
        "--exclude-field-prefix",
        action="append",
        default=["industry.", "entry.universe."],
        help="Field prefix excluded from gate candidates; repeatable",
    )
    parser.add_argument("--gate-candidate-limit", type=int, default=30)
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown report instead of JSON summary")
    return parser.parse_args(argv)


def _resolve_environment_fit_path(value: str) -> Path:
    path = Path(value)
    if path.is_dir():
        enriched = path / "environment_fit.enriched.json"
        if enriched.exists():
            return enriched
        plain = path / "environment_fit.json"
        if plain.exists():
            return plain
        raise FileNotFoundError(f"no environment_fit.enriched.json or environment_fit.json under {path}")
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def _resolve_matrix_path(value: str) -> Path:
    path = Path(value)
    if path.is_dir():
        matrix = path / "segmented_factor_contribution_matrix.json"
        if matrix.exists():
            return matrix
        raise FileNotFoundError(f"no segmented_factor_contribution_matrix.json under {path}")
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def _default_output_dir(matrix_path: Path, report_root: str) -> Path:
    return Path(report_root) / safe_score_gate_counterfactual_funnel_dir_name(matrix_path)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
