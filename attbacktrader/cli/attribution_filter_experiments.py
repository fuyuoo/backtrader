"""Generate attribution-filter experiment run plans from a matrix file."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from attbacktrader.config import RunPlan


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    generated_paths = generate_attribution_filter_experiment_configs(
        matrix_path=Path(args.matrix),
        output_dir=Path(args.output_dir),
    )
    print(
        json.dumps(
            {"generated_configs": [str(path) for path in generated_paths]},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def generate_attribution_filter_experiment_configs(
    *,
    matrix_path: Path,
    output_dir: Path,
) -> tuple[Path, ...]:
    matrix = _load_yaml_mapping(matrix_path)
    base_config_path = _resolve(matrix_path.parent, Path(str(matrix["base_config"])))
    base_config = _load_yaml_mapping(base_config_path)
    variants = matrix.get("variants")
    if not isinstance(variants, Sequence) or isinstance(variants, (str, bytes)) or not variants:
        raise ValueError("experiment matrix variants must be a non-empty sequence")

    output_dir.mkdir(parents=True, exist_ok=True)
    generated_paths: list[Path] = []
    for raw_variant in variants:
        if not isinstance(raw_variant, Mapping):
            raise ValueError("each experiment variant must be a mapping")
        variant = dict(raw_variant)
        config = _experiment_config(base_config, variant)
        RunPlan.from_mapping(config)
        path = output_dir / f"{_safe_filename(str(config['run']['id']))}.yaml"
        path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
        generated_paths.append(path)

    return tuple(generated_paths)


def _experiment_config(base_config: Mapping[str, Any], variant: Mapping[str, Any]) -> dict[str, Any]:
    config = copy.deepcopy(dict(base_config))
    name = str(variant.get("name") or "").strip()
    if not name:
        raise ValueError("experiment variant name is required")

    run = dict(config.get("run") or {})
    base_run_id = str(run.get("id") or "run")
    run["id"] = str(variant.get("run_id") or f"{base_run_id}-{name}")
    config["run"] = run

    analysis = dict(config.get("analysis") or {})
    entry_attribution = dict(analysis.get("entry_attribution") or {})
    entry_attribution["enabled"] = bool(variant.get("enabled", entry_attribution.get("enabled", True)))

    require_checks = tuple(str(check) for check in variant.get("require_checks") or ())
    entry_filter = dict(entry_attribution.get("entry_filter") or {})
    entry_filter["enabled"] = bool(variant.get("entry_filter_enabled", True))
    entry_filter["require_checks"] = list(require_checks)
    entry_filter["missing_policy"] = str(variant.get("missing_policy", entry_filter.get("missing_policy", "block")))
    entry_attribution["entry_filter"] = entry_filter

    if "market_fast_period" in variant:
        entry_attribution["market_fast_period"] = int(variant["market_fast_period"])
    if "market_slow_period" in variant:
        entry_attribution["market_slow_period"] = int(variant["market_slow_period"])
    if "industry_kdj_threshold" in variant:
        entry_attribution["industry_kdj_threshold"] = float(variant["industry_kdj_threshold"])

    factors = list(entry_attribution.get("factors") or [])
    for check in require_checks:
        if check not in factors:
            factors.append(check)
    entry_attribution["factors"] = factors
    analysis["entry_attribution"] = entry_attribution
    config["analysis"] = analysis
    return config


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate attribution-filter experiment run plans")
    parser.add_argument("--matrix", required=True, help="Experiment matrix YAML path")
    parser.add_argument("--output-dir", required=True, help="Directory for generated YAML configs")
    return parser.parse_args(argv)


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return raw


def _resolve(base_dir: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    return base_dir / path


def _safe_filename(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in value.strip())
    return safe or "run"


if __name__ == "__main__":
    raise SystemExit(main())
