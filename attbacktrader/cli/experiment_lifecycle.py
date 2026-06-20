"""Build an experiment lifecycle view from persisted artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attbacktrader.reports import (
    build_experiment_lifecycle,
    render_experiment_lifecycle_markdown_zh,
    safe_experiment_lifecycle_dir_name,
    write_experiment_lifecycle,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    sources = _selected_sources(args)
    lifecycle = build_experiment_lifecycle(**sources)
    output_dir = Path(args.output_dir) if args.output_dir is not None else Path("reports") / safe_experiment_lifecycle_dir_name()
    json_path, markdown_path = write_experiment_lifecycle(lifecycle, output_dir=output_dir)
    payload = {
        "schema": lifecycle["schema"],
        "item_count": lifecycle["item_count"],
        "chain_count": lifecycle["chain_count"],
        "stage_counts": lifecycle["stage_counts"],
        "status_counts": lifecycle["status_counts"],
        "artifacts": {
            "experiment_lifecycle_json_path": str(json_path),
            "experiment_lifecycle_chinese_markdown_path": str(markdown_path),
        },
    }
    if args.print_markdown:
        print(render_experiment_lifecycle_markdown_zh(lifecycle))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an experiment lifecycle view from persisted artifacts")
    parser.add_argument("--candidate", action="append", default=None, help="Review experiment candidates JSON")
    parser.add_argument("--drafts", action="append", default=None, help="Review or strategy variant drafts JSON")
    parser.add_argument("--confirmation", action="append", default=None, help="Confirmed review experiment JSON")
    parser.add_argument("--variant-manifest", action="append", default=None, help="Strategy variant run manifest JSON")
    parser.add_argument("--validation", action="append", default=None, help="Comparison or validation JSON")
    parser.add_argument("--attribution", action="append", default=None, help="Strategy variant attribution JSON")
    parser.add_argument("--decision", action="append", default=None, help="Experiment decision records JSON")
    parser.add_argument("--run-catalog", default=None, help="Run catalog JSON")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--no-default-sources", action="store_true")
    parser.add_argument("--print-markdown", action="store_true", help="Print Chinese Markdown instead of JSON")
    return parser.parse_args(argv)


def _selected_sources(args: argparse.Namespace) -> dict[str, object]:
    defaults = _default_sources() if not args.no_default_sources else {}
    return {
        "candidates": _merge_sources(defaults.get("candidates"), args.candidate),
        "drafts": _merge_sources(defaults.get("drafts"), args.drafts),
        "confirmations": _merge_sources(defaults.get("confirmations"), args.confirmation),
        "variant_manifests": _merge_sources(defaults.get("variant_manifests"), args.variant_manifest),
        "validations": _merge_sources(defaults.get("validations"), args.validation),
        "attributions": _merge_sources(defaults.get("attributions"), args.attribution),
        "decisions": _merge_sources(defaults.get("decisions"), args.decision),
        "run_catalog": args.run_catalog or defaults.get("run_catalog"),
    }


def _merge_sources(defaults: object, explicit: list[str] | None) -> tuple[str, ...]:
    merged = [str(path) for path in (defaults or ())]
    merged.extend(explicit or [])
    return tuple(merged)


def _default_sources() -> dict[str, object]:
    review_root = Path("reports/tushare-expanded-add-on-2023-2024")
    generated_review_root = Path("examples/generated-review-experiments/tushare-expanded-add-on-2023-2024")
    strategy_variant_drafts = Path("reports/strategy-variant-drafts-tushare-market-type-add-on/strategy_variant_drafts.json")
    variant_manifest = Path("examples/generated-strategy-variant-runs/tushare-market-type-add-on/strategy_variant_run_manifest.json")
    variant_validation = Path("reports/strategy-variant-validation-tushare-market-type-add-on/strategy_variant_validation.json")
    experiment_decisions = Path("reports/experiment-decisions/experiment_decisions.json")
    run_catalog = Path("reports/run-catalog/run_catalog.json")
    return {
        "candidates": _existing((review_root / "review_experiment_candidates.all.json",)),
        "drafts": _existing((generated_review_root / "review_experiment_drafts.all.json", strategy_variant_drafts)),
        "confirmations": tuple(str(path) for path in sorted((generated_review_root / "confirmed").glob("review_experiment_confirmed*.json"))),
        "variant_manifests": _existing((variant_manifest,)),
        "validations": _existing((variant_validation,)),
        "attributions": tuple(str(path) for path in sorted(Path("reports").glob("strategy-variant-attribution-*/strategy_variant_attribution.json"))),
        "decisions": _existing((experiment_decisions,)),
        "run_catalog": str(run_catalog) if run_catalog.exists() else None,
    }


def _existing(paths: tuple[Path, ...]) -> tuple[str, ...]:
    return tuple(str(path) for path in paths if path.exists())


if __name__ == "__main__":
    raise SystemExit(main())
