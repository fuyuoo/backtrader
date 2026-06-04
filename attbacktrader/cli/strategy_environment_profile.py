"""Build a strategy environment profile from persisted environment-fit artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_strategy_environment_profile_from_artifacts,
    build_strategy_environment_profile_from_run_dir,
    render_strategy_environment_profile_markdown_zh,
    write_strategy_environment_profile,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    profile = _build_profile(args)
    output_dir = Path(args.output_dir) if args.output_dir is not None else _default_output_dir(args, profile)
    json_path, markdown_path = write_strategy_environment_profile(profile, output_dir=output_dir)
    payload = {
        "schema": profile["schema"],
        "run_id": profile["run_id"],
        "trade_count": profile["trade_count"],
        "preferred_count": profile["profile_summary"]["preferred_count"],
        "avoid_count": profile["profile_summary"]["avoid_count"],
        "uncertain_count": profile["profile_summary"]["uncertain_count"],
        "artifacts": {
            "strategy_environment_profile_json_path": str(json_path),
            "strategy_environment_profile_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_strategy_environment_profile_markdown_zh(profile))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a strategy environment profile")
    parser.add_argument("--run-dir", default=None, help="Persisted run artifact directory")
    parser.add_argument("--report-root", default="reports")
    parser.add_argument("--run-id", default=None, help="Run id under report root")
    parser.add_argument("--environment-fit", default=None, help="Path to environment_fit.json")
    parser.add_argument(
        "--environment-fit-comparison",
        default=None,
        help="Optional path to environment_fit_comparison.json",
    )
    parser.add_argument("--top", type=int, default=20, help="Maximum candidates per conclusion bucket")
    parser.add_argument("--output-dir", default=None, help="Output directory; defaults to run dir or environment-fit parent")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


def _build_profile(args: argparse.Namespace) -> dict:
    comparison = Path(args.environment_fit_comparison) if args.environment_fit_comparison is not None else None
    if args.environment_fit is not None:
        environment_fit_path = Path(args.environment_fit)
        return build_strategy_environment_profile_from_artifacts(
            environment_fit=json.loads(environment_fit_path.read_text(encoding="utf-8")),
            environment_fit_comparison=(
                json.loads(comparison.read_text(encoding="utf-8")) if comparison is not None else None
            ),
            source_dir=str(environment_fit_path.parent),
            environment_fit_path=str(environment_fit_path),
            environment_fit_comparison_path=str(comparison) if comparison is not None else None,
            top=args.top,
        )
    return build_strategy_environment_profile_from_run_dir(
        _resolve_run_dir(args),
        environment_fit_comparison=comparison,
        top=args.top,
    )


def _resolve_run_dir(args: argparse.Namespace) -> Path:
    if args.run_dir is not None:
        return Path(args.run_dir)
    if args.run_id is not None:
        return Path(args.report_root) / args.run_id
    raise ValueError("--run-dir, --run-id, or --environment-fit is required")


def _default_output_dir(args: argparse.Namespace, profile: dict) -> Path:
    if args.environment_fit is not None:
        return Path(args.environment_fit).parent
    source_dir = profile.get("source_dir")
    if source_dir is not None:
        return Path(str(source_dir))
    return _resolve_run_dir(args)


if __name__ == "__main__":
    raise SystemExit(main())
