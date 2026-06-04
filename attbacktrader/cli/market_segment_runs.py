"""Generate validation run plans from manually curated market segments."""

from __future__ import annotations

import argparse
from collections import Counter
import copy
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from attbacktrader.config import RunPlan


MARKET_SEGMENT_RUN_MANIFEST_SCHEMA = "attbacktrader.market_segment_run_manifest.v1"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    manifest_path, markdown_path, yaml_paths = generate_market_segment_run_configs(
        catalog_path=Path(args.catalog),
        base_config_path=Path(args.base_config),
        output_dir=Path(args.output_dir),
        run_id_prefix=args.run_id_prefix,
    )
    print(
        json.dumps(
            {
                "schema": MARKET_SEGMENT_RUN_MANIFEST_SCHEMA,
                "manifest_path": str(manifest_path),
                "markdown_path": str(markdown_path),
                "generated_run_plan_paths": [str(path) for path in yaml_paths],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def generate_market_segment_run_configs(
    *,
    catalog_path: Path,
    base_config_path: Path,
    output_dir: Path,
    run_id_prefix: str | None = None,
) -> tuple[Path, Path, tuple[Path, ...]]:
    """Generate legal RunPlan YAMLs from manual market segment definitions."""

    catalog = _load_yaml_mapping(catalog_path)
    base_config = _load_yaml_mapping(base_config_path)
    market_types = _market_types(catalog)
    market_type_by_id = {str(market_type["market_type_id"]): market_type for market_type in market_types}
    segments = _segments(catalog, market_type_by_id=market_type_by_id)
    _validate_market_type_sample_counts(segments, market_types)
    output_dir.mkdir(parents=True, exist_ok=True)
    _remove_stale_generated_run_plans(output_dir)

    generated_segments: list[dict[str, Any]] = []
    yaml_paths: list[Path] = []
    for segment in segments:
        config = _segment_config(base_config, segment, run_id_prefix=run_id_prefix)
        RunPlan.from_mapping(config)
        run_id = str(config["run"]["id"])
        yaml_path = output_dir / f"{_safe_filename(run_id)}.run.yaml"
        yaml_path.write_text(
            _run_plan_yaml_with_header(config, segment),
            encoding="utf-8",
        )
        yaml_paths.append(yaml_path)
        generated_segments.append(
            {
                "segment_id": segment["segment_id"],
                "label_zh": segment.get("label_zh"),
                "market_type_id": segment.get("market_type_id"),
                "market_type_label_zh": _market_type_label(segment, market_type_by_id),
                "validation_role": segment.get("validation_role"),
                "from_date": segment["from_date"],
                "to_date": segment["to_date"],
                "anchor_dates": segment.get("anchor_dates", []),
                "run_id": run_id,
                "run_plan_path": str(yaml_path),
                "manual_similarity_thesis_zh": segment.get("manual_similarity_thesis_zh"),
                "source_refs": segment.get("source_refs", []),
            }
        )

    manifest = {
        "schema": MARKET_SEGMENT_RUN_MANIFEST_SCHEMA,
        "catalog_path": str(catalog_path),
        "base_config_path": str(base_config_path),
        "base_run_id": _base_run_id(base_config),
        "generated_count": len(generated_segments),
        "market_types": market_types,
        "segments": generated_segments,
        "ai_usage_rules": [
            "这些行情段来自人工资料整理，不是代码自动识别的市场状态。",
            "生成器只改 RunPlan 的 run.id、run.from_date 和 run.to_date，并校验 YAML 合法。",
            "先比较同一行情类型下的多个样本，再跨类型比较 environment_fit 和 strategy_environment_profile。",
            "如果某个行情段交易样本不足，应标记为不确定，而不是补默认值或扩大解释。",
        ],
    }
    manifest_path = output_dir / "market_segment_run_manifest.json"
    markdown_path = output_dir / "market_segment_run_manifest.zh.md"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_render_manifest_markdown_zh(manifest), encoding="utf-8")
    return manifest_path, markdown_path, tuple(yaml_paths)


def _segment_config(
    base_config: Mapping[str, Any],
    segment: Mapping[str, Any],
    *,
    run_id_prefix: str | None,
) -> dict[str, Any]:
    config = copy.deepcopy(dict(base_config))
    run = dict(config.get("run") or {})
    prefix = run_id_prefix or _base_run_id(base_config)
    run["id"] = f"{prefix}-market-segment-{segment['segment_id']}"
    run["from_date"] = str(segment["from_date"])
    run["to_date"] = str(segment["to_date"])
    config["run"] = run
    return config


def _run_plan_yaml_with_header(config: Mapping[str, Any], segment: Mapping[str, Any]) -> str:
    source_lines = []
    for source in _as_sequence(segment.get("source_refs")):
        source_map = _as_mapping(source)
        title = source_map.get("title") or "-"
        url = source_map.get("url") or "-"
        source_lines.append(f"# - {title}: {url}")
    header = [
        "# Generated from a manually curated market segment.",
        f"# segment_id: {segment.get('segment_id')}",
        f"# label_zh: {segment.get('label_zh')}",
        f"# market_type_id: {segment.get('market_type_id') or '-'}",
        f"# validation_role: {segment.get('validation_role')}",
        "# source_refs:",
        *(source_lines or ["# - -"]),
        "# The YAML below is a legal RunPlan; segment metadata is stored in the manifest.",
        "",
    ]
    return "\n".join(header) + yaml.safe_dump(dict(config), allow_unicode=True, sort_keys=False)


def _render_manifest_markdown_zh(manifest: Mapping[str, Any]) -> str:
    lines = [
        "# 人工行情段验证 Run 草稿",
        "",
        f"- schema: `{manifest.get('schema')}`",
        f"- base_run_id: `{manifest.get('base_run_id')}`",
        f"- generated_count: `{manifest.get('generated_count')}`",
        "",
        "## 使用规则",
    ]
    for rule in _as_sequence(manifest.get("ai_usage_rules")):
        lines.append(f"- {rule}")
    market_types = [_as_mapping(market_type) for market_type in _as_sequence(manifest.get("market_types"))]
    if market_types:
        lines.extend(
            [
                "",
                "## 行情类型",
                "",
                "| 类型 | 切换作用 | 人工选择规则 | 样本数 |",
                "|---|---|---|---|",
            ]
        )
        for market_type in market_types:
            market_type_id = str(market_type.get("market_type_id") or "")
            lines.append(
                "| "
                f"{_escape_cell(market_type.get('label_zh'))} | "
                f"{_escape_cell(market_type.get('strategy_switching_use_zh'))} | "
                f"{_escape_cell(market_type.get('selection_rule_zh'))} | "
                f"{_market_type_sample_count(manifest, market_type_id)} |"
            )
    lines.extend(["", "## 行情段", ""])
    if market_types:
        for market_type in market_types:
            market_type_id = str(market_type.get("market_type_id") or "")
            lines.extend(["", f"### {_escape_cell(market_type.get('label_zh'))}", ""])
            _append_segment_table(
                lines,
                [
                    segment
                    for segment in _as_sequence(manifest.get("segments"))
                    if _as_mapping(segment).get("market_type_id") == market_type_id
                ],
            )
    else:
        _append_segment_table(lines, _as_sequence(manifest.get("segments")))
    lines.append("")
    return "\n".join(lines)


def _append_segment_table(lines: list[str], segments: Sequence[Any]) -> None:
    lines.extend(
        [
            "| 行情段 | 日期 | 作用 | RunPlan | 人工相似理由 | 来源 |",
            "|---|---|---|---|---|---|",
        ]
    )
    for segment in segments:
        segment_map = _as_mapping(segment)
        lines.append(
            "| "
            f"{_escape_cell(segment_map.get('label_zh'))} | "
            f"{segment_map.get('from_date')} 至 {segment_map.get('to_date')} | "
            f"{_escape_cell(segment_map.get('validation_role'))} | "
            f"`{segment_map.get('run_plan_path')}` | "
            f"{_escape_cell(segment_map.get('manual_similarity_thesis_zh'))} | "
            f"{_escape_cell(_source_summary(segment_map.get('source_refs')))} |"
        )


def _source_summary(source_refs: Any) -> str:
    parts = []
    for source in _as_sequence(source_refs):
        source_map = _as_mapping(source)
        title = source_map.get("title")
        url = source_map.get("url")
        if title and url:
            parts.append(f"{title} {url}")
        elif title:
            parts.append(str(title))
    return "；".join(parts) if parts else "-"


def _segments(
    catalog: Mapping[str, Any],
    *,
    market_type_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    raw_segments = catalog.get("segments")
    if not isinstance(raw_segments, Sequence) or isinstance(raw_segments, (str, bytes)) or not raw_segments:
        raise ValueError("catalog.segments must be a non-empty sequence")

    segments: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_segment in raw_segments:
        if not isinstance(raw_segment, Mapping):
            raise ValueError("each segment must be a mapping")
        segment = dict(raw_segment)
        segment_id = str(segment.get("segment_id") or "").strip()
        if not segment_id:
            raise ValueError("segment_id is required")
        if segment_id in seen_ids:
            raise ValueError(f"duplicate segment_id: {segment_id}")
        seen_ids.add(segment_id)
        market_type_id = str(segment.get("market_type_id") or "").strip()
        if market_type_by_id:
            if not market_type_id:
                raise ValueError(f"{segment_id}.market_type_id is required")
            market_type_id = _safe_filename(market_type_id)
            if market_type_id not in market_type_by_id:
                raise ValueError(f"{segment_id}.market_type_id is unknown: {market_type_id}")
            segment["market_type_id"] = market_type_id
        for field in ("from_date", "to_date"):
            if not str(segment.get(field) or "").strip():
                raise ValueError(f"{segment_id}.{field} is required")
        if not _as_sequence(segment.get("source_refs")):
            raise ValueError(f"{segment_id}.source_refs must be non-empty")
        segment["segment_id"] = _safe_filename(segment_id)
        segments.append(segment)
    return tuple(segments)


def _market_types(catalog: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    raw_market_types = catalog.get("market_types")
    if raw_market_types is None:
        return ()
    if not isinstance(raw_market_types, Sequence) or isinstance(raw_market_types, (str, bytes)) or not raw_market_types:
        raise ValueError("catalog.market_types must be a non-empty sequence when present")

    market_types: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_market_type in raw_market_types:
        if not isinstance(raw_market_type, Mapping):
            raise ValueError("each market_type must be a mapping")
        market_type = dict(raw_market_type)
        market_type_id = _safe_filename(str(market_type.get("market_type_id") or "").strip())
        if not market_type_id:
            raise ValueError("market_type_id is required")
        if market_type_id in seen_ids:
            raise ValueError(f"duplicate market_type_id: {market_type_id}")
        if not str(market_type.get("label_zh") or "").strip():
            raise ValueError(f"{market_type_id}.label_zh is required")
        seen_ids.add(market_type_id)
        market_type["market_type_id"] = market_type_id
        market_types.append(market_type)
    return tuple(market_types)


def _validate_market_type_sample_counts(
    segments: Sequence[Mapping[str, Any]],
    market_types: Sequence[Mapping[str, Any]],
) -> None:
    if not market_types:
        return
    counts = Counter(str(segment.get("market_type_id") or "") for segment in segments)
    for market_type in market_types:
        market_type_id = str(market_type.get("market_type_id") or "")
        if counts[market_type_id] < 3:
            raise ValueError(f"{market_type_id} must have at least 3 segments")


def _market_type_label(
    segment: Mapping[str, Any],
    market_type_by_id: Mapping[str, Mapping[str, Any]],
) -> str | None:
    market_type_id = str(segment.get("market_type_id") or "")
    if not market_type_id:
        return None
    return str(market_type_by_id.get(market_type_id, {}).get("label_zh") or market_type_id)


def _market_type_sample_count(manifest: Mapping[str, Any], market_type_id: str) -> int:
    return sum(
        1
        for segment in _as_sequence(manifest.get("segments"))
        if _as_mapping(segment).get("market_type_id") == market_type_id
    )


def _remove_stale_generated_run_plans(output_dir: Path) -> None:
    for path in output_dir.glob("*.run.yaml"):
        try:
            head = path.read_text(encoding="utf-8")[:128]
        except UnicodeDecodeError:
            continue
        if head.startswith("# Generated from a manually curated market segment."):
            path.unlink()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate RunPlan YAMLs from manual market segments")
    parser.add_argument("--catalog", required=True, help="Manual market segment catalog YAML")
    parser.add_argument("--base-config", required=True, help="Base RunPlan YAML to copy")
    parser.add_argument("--output-dir", required=True, help="Directory for generated run YAMLs and manifest")
    parser.add_argument("--run-id-prefix", default=None, help="Optional generated run id prefix")
    return parser.parse_args(argv)


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return raw


def _base_run_id(base_config: Mapping[str, Any]) -> str:
    return str(_as_mapping(base_config.get("run")).get("id") or "run")


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _as_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _escape_cell(value: Any) -> str:
    if value is None:
        return "-"
    return " ".join(str(value).replace("|", "/").split())


def _safe_filename(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in value.strip())
    return safe or "segment"


if __name__ == "__main__":
    raise SystemExit(main())
