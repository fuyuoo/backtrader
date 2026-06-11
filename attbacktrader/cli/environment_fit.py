"""Build a persisted-run environment fit and profit contribution report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    DEFAULT_ENVIRONMENT_FIELDS,
    build_environment_fit_report_from_wide_samples,
    build_environment_fit_report_from_run_dir,
    load_attribution_field_index,
    load_attribution_wide_samples,
    render_environment_fit_markdown_zh,
    write_environment_fit_report,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.wide_samples is not None:
        wide_samples = load_attribution_wide_samples(args.wide_samples)
        field_index = (
            load_attribution_field_index(args.field_index)
            if args.field_index is not None
            else wide_samples.get("field_index")
        )
        report = build_environment_fit_report_from_wide_samples(
            wide_samples,
            field_index=field_index,
            environment_fields=_environment_fields(args, wide_samples=wide_samples, field_index=field_index),
            pair_whitelist=_pair_whitelist(args, wide_samples=wide_samples, field_index=field_index),
            min_sample_count=args.min_sample_count,
        )
        json_path, markdown_path = write_environment_fit_report(
            report,
            output_dir=args.output_dir,
            artifact_stem="environment_fit.enriched",
        )
    else:
        run_dir = _resolve_run_dir(args)
        report = build_environment_fit_report_from_run_dir(
            run_dir,
            environment_fields=args.environment_field or DEFAULT_ENVIRONMENT_FIELDS,
            min_sample_count=args.min_sample_count,
        )
        json_path, markdown_path = write_environment_fit_report(report, output_dir=args.output_dir)
    payload = {
        "schema": report["schema"],
        "run_id": report["run_id"],
        "source_dir": report["source_dir"],
        "trade_count": report["trade_count"],
        "contribution_available_count": report["contribution_available_count"],
        "single_factor_summary_count": len(report["single_factor_summaries"]),
        "combination_summary_count": len(report["combination_summaries"]),
        "artifacts": {
            "environment_fit_json_path": str(json_path),
            "environment_fit_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_environment_fit_markdown_zh(report))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a persisted-run environment fit report")
    parser.add_argument("--run-dir", default=None, help="Persisted run artifact directory")
    parser.add_argument("--report-root", default="reports")
    parser.add_argument("--run-id", default=None, help="Run id under report root")
    parser.add_argument(
        "--environment-field",
        action="append",
        default=None,
        help="Repeatable entry environment field. Defaults to the built-in market/industry/symbol factors.",
    )
    parser.add_argument("--wide-samples", default=None, help="attribution_wide_samples.json or its output directory")
    parser.add_argument("--field-index", default=None, help="attribution_field_index.json or its output directory")
    parser.add_argument(
        "--field",
        action="append",
        default=[],
        help="Append an enriched environment field when --wide-samples is used.",
    )
    parser.add_argument(
        "--pair",
        action="append",
        default=[],
        help="Append a two-field enriched combination, format field_a,field_b.",
    )
    parser.add_argument(
        "--replace-default-fields",
        action="store_true",
        help="With --wide-samples, use only --field values instead of appending to field-index defaults.",
    )
    parser.add_argument("--min-sample-count", type=int, default=5)
    parser.add_argument("--output-dir", default=None, help="Output directory; defaults to run dir")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


def _resolve_run_dir(args: argparse.Namespace) -> Path:
    if args.run_dir is not None:
        return Path(args.run_dir)
    if args.run_id is not None:
        return Path(args.report_root) / args.run_id
    raise ValueError("--run-dir or --run-id is required")


def _environment_fields(
    args: argparse.Namespace,
    *,
    wide_samples,
    field_index,
) -> list[str] | None:
    configured = list(args.environment_field or []) + list(args.field or [])
    if args.replace_default_fields:
        return configured
    defaults = list((field_index or {}).get("environment_fit_default_fields") or wide_samples.get("environment_fit_default_fields") or [])
    return _dedupe(defaults + configured)


def _pair_whitelist(
    args: argparse.Namespace,
    *,
    wide_samples,
    field_index,
) -> list[list[str]] | None:
    pairs = [
        [str(part) for part in pair]
        for pair in ((field_index or {}).get("environment_fit_pair_whitelist") or wide_samples.get("environment_fit_pair_whitelist") or [])
    ]
    for raw in args.pair:
        parts = [part.strip() for part in str(raw).split(",") if part.strip()]
        if len(parts) != 2:
            raise ValueError(f"--pair must use field_a,field_b: {raw}")
        pairs.append(parts)
    return _dedupe_pairs(pairs)


def _dedupe(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _dedupe_pairs(values: list[list[str]]) -> list[list[str]]:
    result = []
    seen = set()
    for pair in values:
        if len(pair) != 2:
            continue
        key = tuple(pair)
        if key in seen:
            continue
        seen.add(key)
        result.append(pair)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
