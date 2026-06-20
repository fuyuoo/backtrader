"""Strategy adaptation matrix from known market-type run artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

import yaml

from attbacktrader.config import RunPlan
from attbacktrader.reports.ai_review import build_review_sample
from attbacktrader.strategies.attribution import entry_attribution_declaration_by_key


STRATEGY_ADAPTATION_MATRIX_SCHEMA = "attbacktrader.strategy_adaptation_matrix.v1"
STRATEGY_ADAPTATION_DRILLDOWN_SCHEMA = "attbacktrader.strategy_adaptation_drilldown.v1"
STRATEGY_VARIANT_DRAFTS_SCHEMA = "attbacktrader.strategy_variant_drafts.v1"
STRATEGY_VARIANT_RUN_MANIFEST_SCHEMA = "attbacktrader.strategy_variant_run_manifest.v1"
RUN_PLAN_TOP_LEVEL_KEYS = ("run", "data", "strategy", "constraints", "broker", "execution", "output", "analysis")

_ATTRIBUTION_DECLARATIONS = entry_attribution_declaration_by_key()


def build_strategy_adaptation_matrix(
    market_type_summary_or_path: Mapping[str, Any] | str | Path,
    *,
    min_factor_trades: int = 3,
    preferred_win_rate: float = 0.55,
    avoid_win_rate: float = 0.45,
    top_factors: int = 12,
) -> dict[str, Any]:
    """Build a strategy adaptation matrix from persisted market-type runs.

    The matrix treats market types as upstream/manual input. It reads completed
    run artifacts, reverses from each completed trade into entry-time evidence,
    and aggregates those factors by market type.
    """

    if min_factor_trades <= 0:
        raise ValueError("min_factor_trades must be greater than 0")
    if not 0 <= avoid_win_rate <= preferred_win_rate <= 1:
        raise ValueError("win-rate thresholds must satisfy 0 <= avoid <= preferred <= 1")
    if top_factors <= 0:
        raise ValueError("top_factors must be greater than 0")

    summary, summary_path = _load_summary(market_type_summary_or_path)
    segment_details = [
        _segment_detail(segment)
        for segment in _as_sequence(summary.get("segments"))
    ]
    market_types = [
        _market_type_matrix_row(
            market_type,
            segment_details,
            min_factor_trades=min_factor_trades,
            preferred_win_rate=preferred_win_rate,
            avoid_win_rate=avoid_win_rate,
            top_factors=top_factors,
        )
        for market_type in _as_sequence(summary.get("market_types"))
    ]
    return {
        "schema": STRATEGY_ADAPTATION_MATRIX_SCHEMA,
        "source_summary_path": str(summary_path) if summary_path is not None else None,
        "source_schema": summary.get("schema"),
        "base_run_id": summary.get("base_run_id"),
        "market_type_count": len(market_types),
        "segment_count": len(segment_details),
        "trade_count": sum(_optional_int(row.get("trade_count")) or 0 for row in segment_details),
        "thresholds": {
            "min_factor_trades": min_factor_trades,
            "preferred_win_rate": preferred_win_rate,
            "avoid_win_rate": avoid_win_rate,
            "top_factors": top_factors,
        },
        "market_types": market_types,
        "segments": segment_details,
        "rules": [
            "market_type 来自已生成的市场类型汇总；本矩阵不识别牛市、震荡市或熊市。",
            "每笔样本从 trade_lifecycle.json 的完成交易反查入场事件和入场证据。",
            "卖出后 5 天结果只从 post_exit_analysis.json 按交易主键反查，不按 post_exit 的本地排序编号硬对齐。",
            "只统计已落盘的 entry checks、entry categories、entry method 和 entry reason，不重算指标、不补默认值。",
            "适配判断是验证矩阵中的候选结论，不是自动调参指令，也不是实盘交易建议。",
        ],
    }


def render_strategy_adaptation_matrix_markdown_zh(matrix: Mapping[str, Any], *, limit: int = 12) -> str:
    """Render the strategy adaptation matrix as Chinese Markdown."""

    lines = [
        "# 策略适配矩阵",
        "",
        "## 概览",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
        f"| schema | `{matrix.get('schema')}` |",
        f"| base_run_id | `{matrix.get('base_run_id')}` |",
        f"| 市场类型 | {matrix.get('market_type_count')} |",
        f"| 行情段 | {matrix.get('segment_count')} |",
        f"| 交易样本 | {matrix.get('trade_count')} |",
    ]

    lines.extend(["", "## 使用规则"])
    for rule in _as_sequence(matrix.get("rules")):
        lines.append(f"- {rule}")

    lines.extend(
        [
            "",
            "## 矩阵",
            "",
            "| 类型 | 适配判断 | 段数 | 交易 | 盈利段 | 平均段收益 | 平均回撤 | 加权胜率 | 平均单笔收益 | 卖飞率 | 样本风险 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in _as_sequence(matrix.get("market_types")):
        item = _as_mapping(row)
        metrics = _as_mapping(item.get("metrics"))
        lines.append(
            "| "
            f"{_escape_cell(item.get('market_type_label_zh'))} | "
            f"{_escape_cell(item.get('adaptation_label_zh'))} | "
            f"{metrics.get('segment_count')} | "
            f"{metrics.get('trade_count')} | "
            f"{metrics.get('profitable_segment_count')} | "
            f"{_format_optional_percent(metrics.get('average_segment_return'))} | "
            f"{_format_optional_percent(metrics.get('average_max_drawdown'))} | "
            f"{_format_optional_percent(metrics.get('weighted_win_rate'))} | "
            f"{_format_optional_percent(metrics.get('average_trade_return_pct'))} | "
            f"{_format_optional_percent(metrics.get('sold_too_early_rate_5d'))} | "
            f"{_escape_cell(_risk_labels(item.get('risk_flags')))} |"
        )

    for row in _as_sequence(matrix.get("market_types")):
        item = _as_mapping(row)
        lines.extend(
            [
                "",
                f"## {item.get('market_type_label_zh') or item.get('market_type_id')}",
                "",
                f"- 适配判断：{item.get('adaptation_label_zh')}。{item.get('reason_zh')}",
                f"- 样本引用：`market_types[].entry_factor_summaries[].sample_refs` 可反查到 run_id 和 trade_index。",
            ]
        )
        lines.extend(_factor_section("### 盈利入场因子", item.get("winning_entry_factors"), limit=limit))
        lines.extend(_factor_section("### 亏损入场因子", item.get("losing_entry_factors"), limit=limit))
        lines.extend(_factor_section("### 卖飞入场因子", item.get("sold_too_early_entry_factors"), limit=limit))

    lines.append("")
    return "\n".join(lines)


def write_strategy_adaptation_matrix(
    matrix: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Write strategy adaptation matrix JSON and Chinese Markdown."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "strategy_adaptation_matrix.json"
    markdown_path = output_path / "strategy_adaptation_matrix.zh.md"
    json_path.write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_strategy_adaptation_matrix_markdown_zh(matrix), encoding="utf-8")
    return json_path, markdown_path


def build_strategy_adaptation_drilldown(
    matrix_or_path: Mapping[str, Any] | str | Path,
    *,
    market_type_id: str | None = None,
    market_type_label_zh: str | None = None,
    section: str = "entry_factor_summaries",
    factor_key: str | None = None,
    factor_value: str | None = None,
    factor_rank: int = 1,
    report_root: str | Path = "reports",
    limit: int = 5,
    context_limit: int = 20,
) -> dict[str, Any]:
    """Expand one matrix factor into review-sample packets.

    This is the AI drill-down bridge from a market-type factor summary to the
    original per-trade evidence packet. It reads persisted run artifacts only.
    """

    if section not in {
        "entry_factor_summaries",
        "winning_entry_factors",
        "losing_entry_factors",
        "sold_too_early_entry_factors",
    }:
        raise ValueError(f"unsupported matrix factor section: {section}")
    if factor_rank <= 0:
        raise ValueError("factor_rank must be greater than 0")
    if limit <= 0:
        raise ValueError("limit must be greater than 0")
    if context_limit <= 0:
        raise ValueError("context_limit must be greater than 0")

    matrix, matrix_path = _load_matrix(matrix_or_path)
    market_type = _select_market_type(
        matrix,
        market_type_id=market_type_id,
        market_type_label_zh=market_type_label_zh,
    )
    factor = _select_factor(
        market_type,
        section=section,
        factor_key=factor_key,
        factor_value=factor_value,
        factor_rank=factor_rank,
    )
    run_dirs = _run_dirs_by_run_id(matrix, report_root=Path(report_root))
    sample_refs = [_as_mapping(ref) for ref in _as_sequence(factor.get("sample_refs"))[:limit]]
    sample_packets = []
    sample_summaries = []
    for ref in sample_refs:
        run_id = str(ref.get("run_id") or "")
        trade_index = _optional_int(ref.get("trade_index"))
        if not run_id or trade_index is None:
            raise ValueError(f"matrix sample_ref must include run_id and trade_index: {ref}")
        run_dir = run_dirs.get(run_id, Path(report_root) / run_id)
        packet = build_review_sample(
            run_dir,
            kind="trade",
            trade_index=trade_index,
            context_limit=context_limit,
        )
        sample_packets.append(packet)
        sample_summaries.append(_sample_summary_from_packet(packet, matrix_ref=ref))

    return {
        "schema": STRATEGY_ADAPTATION_DRILLDOWN_SCHEMA,
        "source_matrix": str(matrix_path) if matrix_path is not None else None,
        "base_run_id": matrix.get("base_run_id"),
        "lookup": {
            "market_type_id": market_type.get("market_type_id"),
            "market_type_label_zh": market_type.get("market_type_label_zh"),
            "section": section,
            "factor_key": factor.get("factor_key"),
            "factor_value": factor.get("factor_value"),
            "factor_rank": factor_rank,
            "limit": limit,
            "context_limit": context_limit,
        },
        "selected_factor": factor,
        "sample_count": len(sample_packets),
        "sample_summaries": sample_summaries,
        "sample_packets": sample_packets,
        "rules": [
            "该下钻只从 strategy_adaptation_matrix.json 的 sample_refs 回到原始 run artifact。",
            "每个样本必须引用 run_id 和 trade_index。",
            "样本包由 review_sample 生成；不得重跑策略、重算指标或补默认值。",
            "矩阵因子只能作为复盘线索，不直接变成买卖规则。",
        ],
    }


def render_strategy_adaptation_drilldown_markdown_zh(drilldown: Mapping[str, Any]) -> str:
    """Render a strategy adaptation drill-down packet in Chinese Markdown."""

    lookup = _as_mapping(drilldown.get("lookup"))
    factor = _as_mapping(drilldown.get("selected_factor"))
    lines = [
        "# 策略适配矩阵下钻",
        "",
        f"- schema: `{drilldown.get('schema')}`",
        f"- source_matrix: `{drilldown.get('source_matrix')}`",
        f"- 市场类型: {lookup.get('market_type_label_zh')} (`{lookup.get('market_type_id')}`)",
        f"- section: `{lookup.get('section')}`",
        f"- factor: `{lookup.get('factor_key')}={lookup.get('factor_value')}`",
        f"- sample_count: `{drilldown.get('sample_count')}`",
        "",
        "## 因子汇总",
        "",
        "| 因子 | 值 | 样本 | 胜率 | 平均收益 | 卖飞率 |",
        "|---|---|---:|---:|---:|---:|",
        "| "
        f"{_escape_cell(factor.get('factor_label_zh'))} | "
        f"{_escape_cell(factor.get('factor_value_label_zh'))} | "
        f"{factor.get('sample_count')} | "
        f"{_format_optional_percent(factor.get('win_rate'))} | "
        f"{_format_optional_percent(factor.get('average_trade_return_pct'))} | "
        f"{_format_optional_percent(factor.get('sold_too_early_rate_5d'))} |",
        "",
        "## 样本",
        "",
        "| run_id | trade_index | 股票 | 结果 | 入场 | 退出 | 收益 | 卖飞 |",
        "|---|---:|---|---|---|---|---:|---|",
    ]
    for sample in _as_sequence(drilldown.get("sample_summaries")):
        item = _as_mapping(sample)
        ref = _as_mapping(item.get("sample_ref"))
        row = _as_mapping(item.get("sample"))
        lines.append(
            "| "
            f"`{ref.get('run_id')}` | "
            f"{ref.get('trade_index')} | "
            f"{_escape_cell(row.get('symbol'))} | "
            f"{_escape_cell(row.get('outcome'))} | "
            f"{row.get('entry_date')} | "
            f"{row.get('exit_date')} | "
            f"{_format_optional_percent(row.get('return_pct'))} | "
            f"{_format_bool(row.get('sold_too_early'))} |"
        )

    lines.extend(["", "## AI 使用规则"])
    for rule in _as_sequence(drilldown.get("rules")):
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def write_strategy_adaptation_drilldown(
    drilldown: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Write a matrix factor drill-down JSON and Chinese Markdown."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "strategy_adaptation_drilldown.json"
    markdown_path = output_path / "strategy_adaptation_drilldown.zh.md"
    json_path.write_text(json.dumps(drilldown, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_strategy_adaptation_drilldown_markdown_zh(drilldown), encoding="utf-8")
    return json_path, markdown_path


def build_strategy_variant_drafts(
    matrix_or_path: Mapping[str, Any] | str | Path,
    *,
    base_config_path: str | Path | None = None,
    top_factor_refs: int = 3,
) -> dict[str, Any]:
    """Build manually confirmable strategy variant drafts from a matrix."""

    if top_factor_refs <= 0:
        raise ValueError("top_factor_refs must be greater than 0")
    matrix, matrix_path = _load_matrix(matrix_or_path)
    base_config = _load_yaml_mapping(base_config_path)
    base_run_id = (
        _as_mapping(base_config.get("run")).get("id")
        or matrix.get("base_run_id")
        or "strategy-adaptation"
    )
    drafts = [
        _variant_draft(
            market_type,
            base_run_id=str(base_run_id),
            base_config_path=base_config_path,
            top_factor_refs=top_factor_refs,
        )
        for market_type in _as_sequence(matrix.get("market_types"))
    ]
    return {
        "schema": STRATEGY_VARIANT_DRAFTS_SCHEMA,
        "source_matrix": str(matrix_path) if matrix_path is not None else None,
        "base_run_id": base_run_id,
        "base_config_path": str(base_config_path) if base_config_path is not None else None,
        "draft_count": len(drafts),
        "drafts": drafts,
        "rules": [
            "这些草案只用于下一轮验证设计，不是已采纳策略。",
            "市场类型仍然来自人工分段；草案不实现自动市场识别或自动策略切换。",
            "run_plan_patch 中的 review_candidate 是复盘元数据，不能直接作为合法 RunPlan 顶层字段执行。",
            "执行前必须人工确认样本范围、市场类型分段和具体策略变体。",
        ],
    }


def render_strategy_variant_drafts_markdown_zh(drafts: Mapping[str, Any]) -> str:
    """Render strategy variant drafts as Chinese Markdown."""

    lines = [
        "# 策略变体验证草案",
        "",
        f"- schema: `{drafts.get('schema')}`",
        f"- source_matrix: `{drafts.get('source_matrix')}`",
        f"- base_run_id: `{drafts.get('base_run_id')}`",
        f"- draft_count: `{drafts.get('draft_count')}`",
        "",
        "## 规则",
    ]
    for rule in _as_sequence(drafts.get("rules")):
        lines.append(f"- {rule}")
    for draft in _as_sequence(drafts.get("drafts")):
        item = _as_mapping(draft)
        lines.extend(
            [
                "",
                f"## {item.get('title_zh')}",
                "",
                f"- draft_id: `{item.get('draft_id')}`",
                f"- 市场类型: {item.get('market_type_label_zh')} (`{item.get('market_type_id')}`)",
                f"- 适配判断: {item.get('adaptation_label_zh')}",
                f"- purpose: {item.get('purpose_zh')}",
                f"- validation: {item.get('validation_plan_zh')}",
                "",
                "```yaml",
                yaml.safe_dump(item, allow_unicode=True, sort_keys=False).strip(),
                "```",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def write_strategy_variant_drafts(
    drafts: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path, tuple[Path, ...]]:
    """Write strategy variant draft manifest and individual YAML draft files."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "strategy_variant_drafts.json"
    markdown_path = output_path / "strategy_variant_drafts.zh.md"
    json_path.write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_strategy_variant_drafts_markdown_zh(drafts), encoding="utf-8")
    yaml_paths = []
    for draft in _as_sequence(drafts.get("drafts")):
        item = _as_mapping(draft)
        path = output_path / f"{item.get('draft_id')}.yaml"
        path.write_text(yaml.safe_dump(item, allow_unicode=True, sort_keys=False), encoding="utf-8")
        yaml_paths.append(path)
    return json_path, markdown_path, tuple(yaml_paths)


def build_strategy_variant_run_manifest(
    drafts_or_path: Mapping[str, Any] | str | Path,
    market_segment_manifest_or_path: Mapping[str, Any] | str | Path,
    *,
    reuse_snapshots: bool = True,
) -> dict[str, Any]:
    """Build legal RunPlan payloads for each matching market segment variant."""

    drafts, drafts_path = _load_variant_drafts(drafts_or_path)
    segment_manifest, segment_manifest_path = _load_json_mapping(market_segment_manifest_or_path)
    drafts_by_market_type = {
        str(_as_mapping(draft).get("market_type_id")): _as_mapping(draft)
        for draft in _as_sequence(drafts.get("drafts"))
        if _as_mapping(draft).get("market_type_id")
    }
    generated_segments = []
    for segment in _as_sequence(segment_manifest.get("segments")):
        segment_map = _as_mapping(segment)
        market_type_id = str(segment_map.get("market_type_id") or "")
        draft = drafts_by_market_type.get(market_type_id)
        if draft is None:
            continue
        generated_segments.append(
            _variant_run_segment(
                segment_map,
                draft=draft,
                reuse_snapshots=reuse_snapshots,
            )
        )

    return {
        "schema": STRATEGY_VARIANT_RUN_MANIFEST_SCHEMA,
        "source_strategy_variant_drafts": str(drafts_path) if drafts_path is not None else None,
        "source_market_segment_manifest": str(segment_manifest_path) if segment_manifest_path is not None else None,
        "base_run_id": segment_manifest.get("base_run_id"),
        "reuse_snapshots": reuse_snapshots,
        "market_types": segment_manifest.get("market_types", []),
        "generated_count": len(generated_segments),
        "segments": generated_segments,
        "rules": [
            "每个 YAML 都由原始 market segment RunPlan 合并对应市场类型的 strategy variant patch 得到。",
            "只合并合法 RunPlan 顶层字段；review_candidate 等元数据保留在 manifest，不写入可执行 YAML。",
            "市场类型仍来自人工 manifest；本生成器不识别行情、不自动切换策略。",
            "生成的 RunPlan 已通过 RunPlan.from_mapping 校验；执行前仍需人工确认样本范围。",
        ],
    }


def render_strategy_variant_run_manifest_markdown_zh(manifest: Mapping[str, Any]) -> str:
    """Render generated strategy variant run manifest in Chinese Markdown."""

    lines = [
        "# 策略变体 RunPlan Manifest",
        "",
        f"- schema: `{manifest.get('schema')}`",
        f"- base_run_id: `{manifest.get('base_run_id')}`",
        f"- generated_count: `{manifest.get('generated_count')}`",
        f"- reuse_snapshots: `{manifest.get('reuse_snapshots')}`",
        "",
        "## 规则",
    ]
    for rule in _as_sequence(manifest.get("rules")):
        lines.append(f"- {rule}")
    lines.extend(
        [
            "",
            "## RunPlan",
            "",
            "| 市场类型 | 行情段 | 变体 | run_id | YAML |",
            "|---|---|---|---|---|",
        ]
    )
    for segment in _as_sequence(manifest.get("segments")):
        item = _as_mapping(segment)
        lines.append(
            "| "
            f"{_escape_cell(item.get('market_type_label_zh'))} | "
            f"{_escape_cell(item.get('segment_label_zh'))} | "
            f"{_escape_cell(item.get('draft_id'))} | "
            f"`{item.get('run_id')}` | "
            f"`{item.get('run_plan_path')}` |"
        )
    lines.append("")
    return "\n".join(lines)


def write_strategy_variant_run_manifest(
    manifest: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path, tuple[Path, ...]]:
    """Write variant run manifest and legal RunPlan YAML files."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    yaml_paths = []
    segments = []
    for segment in _as_sequence(manifest.get("segments")):
        item = dict(_as_mapping(segment))
        run_plan = _as_mapping(item.pop("run_plan"))
        path = output_path / f"{item.get('run_id')}.run.yaml"
        item["run_plan_path"] = str(path)
        path.write_text(yaml.safe_dump(run_plan, allow_unicode=True, sort_keys=False), encoding="utf-8")
        yaml_paths.append(path)
        segments.append(item)

    payload = dict(manifest)
    payload["segments"] = segments
    json_path = output_path / "strategy_variant_run_manifest.json"
    markdown_path = output_path / "strategy_variant_run_manifest.zh.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_strategy_variant_run_manifest_markdown_zh(payload), encoding="utf-8")
    return json_path, markdown_path, tuple(yaml_paths)


def safe_strategy_adaptation_matrix_dir_name(source_path: str | Path) -> str:
    path = Path(source_path)
    if path.name == "market_type_summary.json" and path.parent.name:
        stem = path.parent.name.replace("market-type-summary-", "")
    else:
        stem = path.parent.name if path.parent.name else path.stem
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem.strip())
    return f"strategy-adaptation-matrix-{safe or 'runs'}"


def safe_strategy_adaptation_drilldown_dir_name(matrix_path: str | Path, *, market_type_id: str | None = None) -> str:
    stem = _matrix_safe_stem(matrix_path)
    market = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(market_type_id or "factor").strip())
    return f"strategy-adaptation-drilldown-{stem}-{market or 'factor'}"


def safe_strategy_variant_drafts_dir_name(matrix_path: str | Path) -> str:
    return f"strategy-variant-drafts-{_matrix_safe_stem(matrix_path)}"


def safe_strategy_variant_run_manifest_dir_name(drafts_path: str | Path) -> str:
    value = Path(drafts_path)
    stem = value.parent.name.replace("strategy-variant-drafts-", "") if value.parent.name else value.stem
    return f"generated-strategy-variant-runs-{_safe_token(stem)}"


def _load_matrix(source: Mapping[str, Any] | str | Path) -> tuple[Mapping[str, Any], Path | None]:
    if isinstance(source, Mapping):
        return source, None
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"missing strategy adaptation matrix: {path}")
    return _as_mapping(json.loads(path.read_text(encoding="utf-8"))), path


def _load_variant_drafts(source: Mapping[str, Any] | str | Path) -> tuple[Mapping[str, Any], Path | None]:
    if isinstance(source, Mapping):
        return source, None
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"missing strategy variant drafts: {path}")
    return _as_mapping(json.loads(path.read_text(encoding="utf-8"))), path


def _load_json_mapping(source: Mapping[str, Any] | str | Path) -> tuple[Mapping[str, Any], Path | None]:
    if isinstance(source, Mapping):
        return source, None
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"missing JSON mapping: {path}")
    return _as_mapping(json.loads(path.read_text(encoding="utf-8"))), path


def _select_market_type(
    matrix: Mapping[str, Any],
    *,
    market_type_id: str | None,
    market_type_label_zh: str | None,
) -> Mapping[str, Any]:
    rows = [_as_mapping(row) for row in _as_sequence(matrix.get("market_types"))]
    if not rows:
        raise ValueError("matrix.market_types must be non-empty")
    if market_type_id is None and market_type_label_zh is None:
        return rows[0]
    for row in rows:
        if market_type_id is not None and row.get("market_type_id") == market_type_id:
            return row
        if market_type_label_zh is not None and row.get("market_type_label_zh") == market_type_label_zh:
            return row
    raise ValueError(f"market type not found: {market_type_id or market_type_label_zh}")


def _select_factor(
    market_type: Mapping[str, Any],
    *,
    section: str,
    factor_key: str | None,
    factor_value: str | None,
    factor_rank: int,
) -> Mapping[str, Any]:
    rows = [_as_mapping(row) for row in _as_sequence(market_type.get(section))]
    if not rows:
        raise ValueError(f"market type section has no factors: {section}")
    if factor_key is not None:
        matches = [
            row
            for row in rows
            if row.get("factor_key") == factor_key
            and (factor_value is None or str(row.get("factor_value")) == str(factor_value))
        ]
        if not matches:
            raise ValueError(f"factor not found: {factor_key}={factor_value}")
        return matches[0]
    index = factor_rank - 1
    if index >= len(rows):
        raise ValueError(f"factor_rank {factor_rank} is out of range for {section}")
    return rows[index]


def _run_dirs_by_run_id(matrix: Mapping[str, Any], *, report_root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for segment in _as_sequence(matrix.get("segments")):
        item = _as_mapping(segment)
        run_id = item.get("run_id")
        report_dir = item.get("report_dir")
        if run_id:
            result[str(run_id)] = Path(str(report_dir)) if report_dir else report_root / str(run_id)
    return result


def _sample_summary_from_packet(packet: Mapping[str, Any], *, matrix_ref: Mapping[str, Any]) -> dict[str, Any]:
    related = _as_mapping(packet.get("related"))
    post_exit = _as_mapping(related.get("post_exit_observation"))
    sample = _as_mapping(packet.get("sample"))
    return {
        "sample_id": packet.get("sample_id"),
        "sample_kind": packet.get("sample_kind"),
        "sample_ref": dict(matrix_ref),
        "sample": _drop_none(
            {
                "trade_index": sample.get("trade_index"),
                "symbol": sample.get("symbol"),
                "outcome": sample.get("outcome"),
                "entry_date": sample.get("entry_date"),
                "exit_date": sample.get("exit_date"),
                "exit_reason": sample.get("exit_reason"),
                "return_pct": sample.get("return_pct"),
                "sold_too_early": sample.get("sold_too_early"),
                "max_high_return_pct": sample.get("max_high_return_pct"),
            }
        ),
        "related_summary": {
            "post_exit_observation": _drop_none(
                {
                    "sold_too_early": post_exit.get("sold_too_early"),
                    "max_high_return_pct": post_exit.get("max_high_return_pct"),
                    "primary_window_close_return_pct": post_exit.get("primary_window_close_return_pct"),
                }
            ),
            "signal_intent_match_count": related.get("signal_intent_match_count"),
            "execution_event_match_count": related.get("execution_event_match_count"),
            "drill_down_hints": related.get("drill_down_hints", []),
        },
    }


def _variant_draft(
    market_type: Any,
    *,
    base_run_id: str,
    base_config_path: str | Path | None,
    top_factor_refs: int,
) -> dict[str, Any]:
    item = _as_mapping(market_type)
    market_type_id = str(item.get("market_type_id") or "market_type")
    adaptation = str(item.get("adaptation") or "uncertain")
    draft_id = _variant_draft_id(market_type_id, adaptation)
    evidence_factors = _variant_evidence_factors(item, adaptation=adaptation, top=top_factor_refs)
    return {
        "draft_id": draft_id,
        "status": "draft_requires_manual_confirmation",
        "market_type_id": market_type_id,
        "market_type_label_zh": item.get("market_type_label_zh"),
        "adaptation": adaptation,
        "adaptation_label_zh": item.get("adaptation_label_zh"),
        "title_zh": _variant_title_zh(item, adaptation),
        "purpose_zh": _variant_purpose_zh(item, adaptation),
        "base_config_path": str(base_config_path) if base_config_path is not None else None,
        "suggested_run_id": f"{base_run_id}__strategy_variant__{draft_id}",
        "metrics": item.get("metrics", {}),
        "evidence_factors": evidence_factors,
        "sample_refs": _unique_refs_from_factors(evidence_factors, limit=top_factor_refs * 3),
        "suggested_change": _variant_suggested_change(adaptation),
        "validation_plan_zh": _variant_validation_plan_zh(item, adaptation),
        "manual_steps": _variant_manual_steps(adaptation),
        "run_plan_patch": _variant_run_plan_patch(base_run_id, draft_id, item, adaptation),
        "not_runnable_until": "人工确认 run_plan_patch，并只把合法 RunPlan 顶层字段合入配置后再执行。",
    }


def _variant_draft_id(market_type_id: str, adaptation: str) -> str:
    suffix = {
        "preferred": "let_winners_run",
        "conditional": "range_no_add_on_fast_review",
        "avoid": "defensive_sizing",
        "defensive": "defensive_sizing",
        "uncertain": "sample_stability_review",
    }.get(adaptation, "sample_stability_review")
    return _safe_token(f"{market_type_id}_{suffix}")


def _variant_title_zh(market_type: Mapping[str, Any], adaptation: str) -> str:
    label = market_type.get("market_type_label_zh") or market_type.get("market_type_id")
    return {
        "preferred": f"{label}：放宽过早止盈验证",
        "conditional": f"{label}：去加仓快进快出验证",
        "avoid": f"{label}：防守仓位验证",
        "defensive": f"{label}：防守仓位验证",
        "uncertain": f"{label}：样本稳定性验证",
    }.get(adaptation, f"{label}：样本稳定性验证")


def _variant_purpose_zh(market_type: Mapping[str, Any], adaptation: str) -> str:
    if adaptation == "preferred":
        return "验证当前策略在该市场类型下是否因为止盈过快而损失趋势段收益。"
    if adaptation == "conditional":
        return "验证该市场类型下是否应减少加仓暴露，保留更快的进出节奏。"
    if adaptation in {"avoid", "defensive"}:
        return "验证该市场类型下是否应降仓、停用加仓，或只作为防守观察样本。"
    return "验证当前适配判断是否只是样本不足或分段波动导致。"


def _variant_evidence_factors(market_type: Mapping[str, Any], *, adaptation: str, top: int) -> list[dict[str, Any]]:
    if adaptation == "preferred":
        sections = ("sold_too_early_entry_factors", "winning_entry_factors")
    elif adaptation in {"avoid", "defensive"}:
        sections = ("losing_entry_factors", "sold_too_early_entry_factors")
    elif adaptation == "conditional":
        sections = ("winning_entry_factors", "losing_entry_factors", "sold_too_early_entry_factors")
    else:
        sections = ("entry_factor_summaries",)
    factors: list[dict[str, Any]] = []
    seen = set()
    for section in sections:
        for factor in _as_sequence(market_type.get(section)):
            item = dict(_as_mapping(factor))
            key = (item.get("factor_key"), item.get("factor_value"))
            if key in seen:
                continue
            seen.add(key)
            item["source_section"] = section
            factors.append(item)
            if len(factors) >= top:
                return factors
    return factors


def _unique_refs_from_factors(factors: Sequence[Mapping[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    refs = []
    seen = set()
    for factor in factors:
        for ref in _as_sequence(factor.get("sample_refs")):
            item = _as_mapping(ref)
            key = (item.get("run_id"), item.get("trade_index"))
            if key in seen:
                continue
            seen.add(key)
            refs.append(dict(item))
            if len(refs) >= limit:
                return refs
    return refs


def _variant_suggested_change(adaptation: str) -> dict[str, Any]:
    if adaptation == "preferred":
        return {
            "direction": "let_winners_run",
            "change_zh": "用趋势弱化退出替代 KDJ 过热止盈，验证是否减少牛市卖飞。",
            "not_allowed": ["不要直接调 KDJ 阈值寻找最优参数", "不要把卖飞样本当成止盈必然错误"],
        }
    if adaptation == "conditional":
        return {
            "direction": "reduce_add_on_exposure",
            "change_zh": "关闭加仓，保留当前 KDJ 入场和过热退出，验证震荡市是否更适合快进快出。",
            "not_allowed": ["不要扩大加仓次数", "不要因为单段盈利就把震荡市当成优先环境"],
        }
    if adaptation in {"avoid", "defensive"}:
        return {
            "direction": "defensive_sizing",
            "change_zh": "关闭加仓并降低单票/总仓位暴露，验证熊市是否应少做或降仓。",
            "not_allowed": ["不要在没有市场切换层前实现自动停用", "不要用防守草案当成完整风控系统"],
        }
    return {
        "direction": "sample_stability",
        "change_zh": "不改策略，先扩大同类行情样本验证适配判断。",
        "not_allowed": ["不要基于不确定样本调参"],
    }


def _variant_validation_plan_zh(market_type: Mapping[str, Any], adaptation: str) -> str:
    label = market_type.get("market_type_label_zh") or market_type.get("market_type_id")
    if adaptation == "preferred":
        return f"只在已知 {label} 分段上比较原策略与放宽止盈变体，重点看累计收益、回撤、卖飞率和代表 trade_index。"
    if adaptation == "conditional":
        return f"只在已知 {label} 分段上比较原策略与关闭加仓变体，重点看胜率、平均单笔收益和回撤是否改善。"
    if adaptation in {"avoid", "defensive"}:
        return f"只在已知 {label} 分段上比较原策略与防守仓位变体，重点看亏损是否收敛以及是否仍有稳定盈利因子。"
    return f"继续补充已知 {label} 分段样本，不修改策略参数，验证矩阵结论稳定性。"


def _variant_manual_steps(adaptation: str) -> list[str]:
    common = [
        "读取 strategy_adaptation_matrix.json 中对应 market_type 的 metrics 和 evidence_factors。",
        "用 att-strategy-adaptation-drilldown 下钻 sample_refs，确认代表交易证据完整。",
        "人工确认只在相同市场类型分段上运行变体，不进行跨类型混合评价。",
    ]
    if adaptation == "preferred":
        return common + ["比较卖飞率和趋势段收益是否改善，再决定是否进入切换规则草案。"]
    if adaptation == "conditional":
        return common + ["比较关闭加仓后的回撤和平均单笔收益，不用单段结果直接决定策略。"]
    if adaptation in {"avoid", "defensive"}:
        return common + ["比较防守仓位是否减少亏损；如果仍亏损，优先记录为停用候选而非继续调参。"]
    return common + ["样本不足时先扩大人工行情段，不新增策略变体。"]


def _variant_run_plan_patch(
    base_run_id: str,
    draft_id: str,
    market_type: Mapping[str, Any],
    adaptation: str,
) -> dict[str, Any]:
    patch: dict[str, Any] = {
        "run": {"id": f"{base_run_id}__strategy_variant__{draft_id}"},
        "review_candidate": {
            "manual_confirmation_required": True,
            "source": "strategy_adaptation_matrix",
            "market_type_id": market_type.get("market_type_id"),
            "market_type_label_zh": market_type.get("market_type_label_zh"),
            "adaptation": adaptation,
            "validation_plan_zh": _variant_validation_plan_zh(market_type, adaptation),
        },
    }
    if adaptation == "preferred":
        patch["strategy"] = {"profit_taking_method": "ma_macd_weakening_exit"}
    elif adaptation == "conditional":
        patch["strategy"] = {"add_on_method": "none", "add_on_params": {}}
    elif adaptation in {"avoid", "defensive"}:
        patch["strategy"] = {
            "add_on_method": "none",
            "add_on_params": {},
            "sizing_params": {
                "max_holding_count": 3,
                "max_position_percent": 0.08,
                "max_total_exposure_percent": 0.3,
                "max_risk_group_exposure_percent": 0.15,
                "cash_reserve_percent": 0.5,
            },
        }
    else:
        patch["review_candidate"]["inspect_artifacts"] = [
            "strategy_adaptation_matrix.json",
            "market_type_summary.json",
        ]
    return patch


def _variant_run_segment(
    segment: Mapping[str, Any],
    *,
    draft: Mapping[str, Any],
    reuse_snapshots: bool,
) -> dict[str, Any]:
    base_path = Path(str(segment.get("run_plan_path") or ""))
    if not base_path.exists():
        raise FileNotFoundError(f"missing base segment RunPlan: {base_path}")
    base_run_plan = _load_yaml_mapping(base_path)
    draft_id = str(draft.get("draft_id") or "variant")
    base_run_id = str(segment.get("run_id") or _as_mapping(base_run_plan.get("run")).get("id") or "segment")
    variant_run_id = f"{base_run_id}__variant__{draft_id}"
    patch, omitted_patch_keys = _legal_run_plan_patch(_as_mapping(draft.get("run_plan_patch")))
    run_plan = _deep_merge_mapping(base_run_plan, patch)
    run_plan.setdefault("run", {})
    _as_mapping(run_plan["run"])
    run_plan["run"] = dict(_as_mapping(run_plan["run"]))
    run_plan["run"]["id"] = variant_run_id
    if segment.get("from_date") is not None:
        run_plan["run"]["from_date"] = segment.get("from_date")
    if segment.get("to_date") is not None:
        run_plan["run"]["to_date"] = segment.get("to_date")
    if reuse_snapshots:
        run_plan.setdefault("data", {})
        run_plan["data"] = dict(_as_mapping(run_plan["data"]))
        run_plan["data"]["refresh_snapshots"] = False
    RunPlan.from_mapping(dict(run_plan))
    return {
        "segment_id": segment.get("segment_id"),
        "segment_label_zh": segment.get("label_zh") or segment.get("segment_label_zh"),
        "market_type_id": segment.get("market_type_id"),
        "market_type_label_zh": segment.get("market_type_label_zh"),
        "from_date": segment.get("from_date"),
        "to_date": segment.get("to_date"),
        "baseline_run_id": segment.get("run_id"),
        "baseline_run_plan_path": segment.get("run_plan_path"),
        "draft_id": draft_id,
        "adaptation": draft.get("adaptation"),
        "adaptation_label_zh": draft.get("adaptation_label_zh"),
        "run_id": variant_run_id,
        "omitted_patch_keys": omitted_patch_keys,
        "run_plan_patch": patch,
        "run_plan": run_plan,
    }


def _legal_run_plan_patch(patch: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    legal = {key: patch[key] for key in RUN_PLAN_TOP_LEVEL_KEYS if key in patch}
    omitted = [str(key) for key in patch if key not in RUN_PLAN_TOP_LEVEL_KEYS]
    return legal, omitted


def _deep_merge_mapping(base: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(base, ensure_ascii=False, default=str))
    for key, value in patch.items():
        if isinstance(value, Mapping) and not value:
            merged[key] = {}
        elif isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge_mapping(_as_mapping(merged.get(key)), value)
        else:
            merged[key] = json.loads(json.dumps(value, ensure_ascii=False, default=str))
    return merged


def _load_yaml_mapping(path: str | Path | None) -> Mapping[str, Any]:
    if path is None:
        return {}
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return payload if isinstance(payload, Mapping) else {}


def _matrix_safe_stem(path: str | Path) -> str:
    value = Path(path)
    if value.name == "strategy_adaptation_matrix.json" and value.parent.name:
        stem = value.parent.name.replace("strategy-adaptation-matrix-", "")
    else:
        stem = value.parent.name if value.parent.name else value.stem
    return _safe_token(stem)


def _safe_token(value: Any) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
    return safe or "item"


def _segment_detail(segment: Any) -> dict[str, Any]:
    item = _as_mapping(segment)
    run_id = str(item.get("run_id") or "")
    if not run_id:
        raise ValueError("market type segment run_id is required")

    report_dir_value = item.get("report_dir")
    if not report_dir_value:
        raise ValueError(f"market type segment report_dir is required: {run_id}")
    report_dir = Path(str(report_dir_value))
    lifecycle = _read_json(report_dir / "trade_lifecycle.json")
    post_exit = _read_optional_json(report_dir / "post_exit_analysis.json")
    evidence_validation = _read_optional_json(report_dir / "evidence_validation.json")
    post_exit_by_key = _post_exit_by_trade_key(post_exit)
    trades = [
        _trade_sample(
            lifecycle_item,
            run_id=run_id,
            segment=item,
            post_exit=post_exit_by_key.get(_trade_key(lifecycle_item)),
        )
        for lifecycle_item in _as_sequence(lifecycle.get("lifecycles"))
    ]
    return _drop_none(
        {
            "segment_id": item.get("segment_id"),
            "segment_label_zh": item.get("segment_label_zh"),
            "market_type_id": item.get("market_type_id"),
            "market_type_label_zh": item.get("market_type_label_zh"),
            "from_date": item.get("from_date"),
            "to_date": item.get("to_date"),
            "run_id": run_id,
            "report_dir": str(report_dir),
            "cumulative_return": _optional_float(item.get("cumulative_return")),
            "max_drawdown": _optional_float(item.get("max_drawdown")),
            "trade_count": len(trades),
            "win_rate": _rate(sum(1 for trade in trades if trade.get("outcome") == "win"), len(trades)),
            "average_trade_return_pct": _mean_present([_optional_float(trade.get("return_pct")) for trade in trades]),
            "sold_too_early_rate_5d": _rate(
                sum(1 for trade in trades if trade.get("sold_too_early") is True),
                sum(1 for trade in trades if trade.get("sold_too_early") is not None),
            ),
            "evidence_validation_status": _as_mapping(evidence_validation).get("status"),
            "trades": trades,
        }
    )


def _trade_sample(
    lifecycle_item: Any,
    *,
    run_id: str,
    segment: Mapping[str, Any],
    post_exit: Mapping[str, Any] | None,
) -> dict[str, Any]:
    trade = _as_mapping(lifecycle_item)
    entry_event = _event_by_type(trade, "entry")
    entry_factors = _entry_factors(entry_event)
    return _drop_none(
        {
            "run_id": run_id,
            "segment_id": segment.get("segment_id"),
            "segment_label_zh": segment.get("segment_label_zh"),
            "market_type_id": segment.get("market_type_id"),
            "market_type_label_zh": segment.get("market_type_label_zh"),
            "trade_index": _optional_int(trade.get("trade_index")),
            "symbol": trade.get("symbol"),
            "outcome": trade.get("outcome"),
            "entry_date": trade.get("entry_date"),
            "exit_date": trade.get("exit_date"),
            "exit_reason": trade.get("exit_reason"),
            "return_pct": _optional_float(trade.get("return_pct")),
            "entry_method_name": entry_event.get("method_name"),
            "entry_reason_code": entry_event.get("reason_code"),
            "entry_checks": dict(_as_mapping(entry_event.get("checks"))),
            "entry_categories": dict(_as_mapping(entry_event.get("categories"))),
            "entry_values": _selected_entry_values(entry_event.get("values")),
            "entry_factors": entry_factors,
            "add_on_count": _add_on_count(trade),
            "sold_too_early": _optional_bool(_as_mapping(post_exit).get("sold_too_early")),
            "max_high_return_pct_5d": _optional_float(_as_mapping(post_exit).get("max_high_return_pct")),
            "window_close_return_pct_5d": _optional_float(
                _as_mapping(post_exit).get("primary_window_close_return_pct")
            ),
        }
    )


def _market_type_matrix_row(
    market_type: Any,
    segment_details: Sequence[Mapping[str, Any]],
    *,
    min_factor_trades: int,
    preferred_win_rate: float,
    avoid_win_rate: float,
    top_factors: int,
) -> dict[str, Any]:
    item = _as_mapping(market_type)
    market_type_id = str(item.get("market_type_id") or "")
    segments = [segment for segment in segment_details if segment.get("market_type_id") == market_type_id]
    trades = [
        _as_mapping(trade)
        for segment in segments
        for trade in _as_sequence(segment.get("trades"))
    ]
    metrics = _market_type_metrics(item, segments, trades)
    risk_flags = _market_type_risk_flags(metrics)
    adaptation = _adaptation_classification(
        metrics,
        risk_flags=risk_flags,
        preferred_win_rate=preferred_win_rate,
        avoid_win_rate=avoid_win_rate,
    )
    factor_summaries = _factor_summaries(trades, min_factor_trades=min_factor_trades)
    return {
        "market_type_id": market_type_id,
        "market_type_label_zh": item.get("market_type_label_zh"),
        "strategy_switching_use_zh": item.get("strategy_switching_use_zh"),
        "selection_rule_zh": item.get("selection_rule_zh"),
        "adaptation": adaptation,
        "adaptation_label_zh": _adaptation_label_zh(adaptation),
        "reason_zh": _adaptation_reason_zh(adaptation, metrics, risk_flags),
        "risk_flags": risk_flags,
        "metrics": metrics,
        "winning_entry_factors": _top_winning_factors(factor_summaries, top=top_factors),
        "losing_entry_factors": _top_losing_factors(factor_summaries, top=top_factors),
        "sold_too_early_entry_factors": _top_sold_too_early_factors(factor_summaries, top=top_factors),
        "entry_factor_count": len(factor_summaries),
        "entry_factor_summaries": factor_summaries,
        "sample_refs": [_sample_ref(trade) for trade in trades[:20]],
    }


def _market_type_metrics(
    market_type: Mapping[str, Any],
    segments: Sequence[Mapping[str, Any]],
    trades: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    returns = [_optional_float(segment.get("cumulative_return")) for segment in segments]
    drawdowns = [_optional_float(segment.get("max_drawdown")) for segment in segments]
    trade_returns = [_optional_float(trade.get("return_pct")) for trade in trades]
    observed_post_exit = [trade for trade in trades if trade.get("sold_too_early") is not None]
    return _drop_none(
        {
            "segment_count": len(segments),
            "trade_count": len(trades),
            "profitable_segment_count": _optional_int(market_type.get("profitable_segment_count")),
            "loss_segment_count": _optional_int(market_type.get("loss_segment_count")),
            "low_sample_segment_count": _optional_int(market_type.get("low_sample_segment_count")),
            "average_segment_return": _optional_float(market_type.get("average_return_pct")) or _mean_present(returns),
            "average_max_drawdown": _optional_float(market_type.get("average_max_drawdown")) or _mean_present(drawdowns),
            "weighted_win_rate": _optional_float(market_type.get("weighted_win_rate")) or _trade_win_rate(trades),
            "average_trade_return_pct": _mean_present(trade_returns),
            "win_count": sum(1 for trade in trades if trade.get("outcome") == "win"),
            "loss_count": sum(1 for trade in trades if trade.get("outcome") == "loss"),
            "flat_count": sum(1 for trade in trades if trade.get("outcome") == "flat"),
            "sold_too_early_observed_count": len(observed_post_exit),
            "sold_too_early_count": sum(1 for trade in observed_post_exit if trade.get("sold_too_early") is True),
            "sold_too_early_rate_5d": _rate(
                sum(1 for trade in observed_post_exit if trade.get("sold_too_early") is True),
                len(observed_post_exit),
            ),
            "average_max_high_return_pct_5d": _mean_present(
                [_optional_float(trade.get("max_high_return_pct_5d")) for trade in observed_post_exit]
            ),
        }
    )


def _market_type_risk_flags(metrics: Mapping[str, Any]) -> list[str]:
    flags: list[str] = []
    if (_optional_int(metrics.get("segment_count")) or 0) < 3:
        flags.append("low_segment_count")
    if (_optional_int(metrics.get("low_sample_segment_count")) or 0) > 0:
        flags.append("low_sample_segments")
    if (_optional_int(metrics.get("trade_count")) or 0) <= 0:
        flags.append("no_trades")
    if metrics.get("weighted_win_rate") is None or metrics.get("average_segment_return") is None:
        flags.append("missing_market_type_metrics")
    return flags


def _adaptation_classification(
    metrics: Mapping[str, Any],
    *,
    risk_flags: Sequence[str],
    preferred_win_rate: float,
    avoid_win_rate: float,
) -> str:
    if "no_trades" in risk_flags or "missing_market_type_metrics" in risk_flags:
        return "uncertain"

    segment_count = _optional_int(metrics.get("segment_count")) or 0
    profitable_count = _optional_int(metrics.get("profitable_segment_count")) or 0
    loss_count = _optional_int(metrics.get("loss_segment_count")) or 0
    average_return = _optional_float(metrics.get("average_segment_return"))
    win_rate = _optional_float(metrics.get("weighted_win_rate"))
    if average_return is None or win_rate is None:
        return "uncertain"

    mostly_profitable = profitable_count >= max(1, segment_count - 1)
    mostly_loss = loss_count >= max(1, segment_count - 1)
    if average_return > 0 and win_rate >= preferred_win_rate and mostly_profitable:
        return "preferred"
    if average_return < 0 and win_rate <= avoid_win_rate and mostly_loss:
        return "avoid"
    if average_return > 0:
        return "conditional"
    if average_return < 0:
        return "defensive"
    return "uncertain"


def _factor_summaries(
    trades: Sequence[Mapping[str, Any]],
    *,
    min_factor_trades: int,
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    factor_meta: dict[tuple[str, str], Mapping[str, Any]] = {}
    for trade in trades:
        seen: set[tuple[str, str]] = set()
        for factor in _as_sequence(trade.get("entry_factors")):
            factor_map = _as_mapping(factor)
            key = str(factor_map.get("factor_key") or "")
            value = str(factor_map.get("factor_value") or "")
            if not key:
                continue
            bucket_key = (key, value)
            if bucket_key in seen:
                continue
            seen.add(bucket_key)
            buckets.setdefault(bucket_key, []).append(trade)
            factor_meta.setdefault(bucket_key, factor_map)

    summaries = [
        _factor_summary(factor_meta[key], bucket_trades, min_factor_trades=min_factor_trades)
        for key, bucket_trades in buckets.items()
    ]
    return sorted(summaries, key=_factor_sort_key)


def _factor_summary(
    factor: Mapping[str, Any],
    trades: Sequence[Mapping[str, Any]],
    *,
    min_factor_trades: int,
) -> dict[str, Any]:
    win_count = sum(1 for trade in trades if trade.get("outcome") == "win")
    loss_count = sum(1 for trade in trades if trade.get("outcome") == "loss")
    flat_count = sum(1 for trade in trades if trade.get("outcome") == "flat")
    observed_post_exit = [trade for trade in trades if trade.get("sold_too_early") is not None]
    trade_returns = [_optional_float(trade.get("return_pct")) for trade in trades]
    sold_count = sum(1 for trade in observed_post_exit if trade.get("sold_too_early") is True)
    sample_count = len(trades)
    return _drop_none(
        {
            "factor_key": factor.get("factor_key"),
            "factor_label_zh": factor.get("factor_label_zh"),
            "factor_type": factor.get("factor_type"),
            "factor_value": factor.get("factor_value"),
            "factor_value_label_zh": factor.get("factor_value_label_zh"),
            "sample_count": sample_count,
            "min_factor_trades": min_factor_trades,
            "low_sample": sample_count < min_factor_trades,
            "win_count": win_count,
            "loss_count": loss_count,
            "flat_count": flat_count,
            "win_rate": _rate(win_count, sample_count),
            "average_trade_return_pct": _mean_present(trade_returns),
            "sold_too_early_observed_count": len(observed_post_exit),
            "sold_too_early_count": sold_count,
            "sold_too_early_rate_5d": _rate(sold_count, len(observed_post_exit)),
            "average_max_high_return_pct_5d": _mean_present(
                [_optional_float(trade.get("max_high_return_pct_5d")) for trade in observed_post_exit]
            ),
            "profile_flags": _factor_profile_flags(
                sample_count=sample_count,
                min_factor_trades=min_factor_trades,
                win_rate=_rate(win_count, sample_count),
                average_return=_mean_present(trade_returns),
                sold_too_early_rate=_rate(sold_count, len(observed_post_exit)),
            ),
            "sample_refs": [_sample_ref(trade) for trade in trades[:12]],
        }
    )


def _factor_profile_flags(
    *,
    sample_count: int,
    min_factor_trades: int,
    win_rate: float | None,
    average_return: float | None,
    sold_too_early_rate: float | None,
) -> list[str]:
    if sample_count < min_factor_trades:
        return ["low_sample"]
    flags: list[str] = []
    if win_rate is not None and average_return is not None:
        if win_rate >= 0.6 and average_return > 0:
            flags.append("winning_bias")
        if win_rate <= 0.4 and average_return < 0:
            flags.append("losing_bias")
    if sold_too_early_rate is not None and sold_too_early_rate >= 0.7:
        flags.append("sold_too_early_bias")
    return flags or ["neutral"]


def _top_winning_factors(summaries: Sequence[Mapping[str, Any]], *, top: int) -> list[dict[str, Any]]:
    items = [
        dict(summary)
        for summary in summaries
        if not summary.get("low_sample")
        and (_optional_float(summary.get("average_trade_return_pct")) or 0.0) > 0
        and (_optional_float(summary.get("win_rate")) or 0.0) >= 0.5
    ]
    items.sort(
        key=lambda item: (
            -(_optional_float(item.get("win_rate")) or 0.0),
            -(_optional_float(item.get("average_trade_return_pct")) or 0.0),
            -(_optional_int(item.get("sample_count")) or 0),
            str(item.get("factor_key")),
            str(item.get("factor_value")),
        )
    )
    return items[:top]


def _top_losing_factors(summaries: Sequence[Mapping[str, Any]], *, top: int) -> list[dict[str, Any]]:
    items = [
        dict(summary)
        for summary in summaries
        if not summary.get("low_sample")
        and (_optional_float(summary.get("average_trade_return_pct")) or 0.0) < 0
    ]
    items.sort(
        key=lambda item: (
            _optional_float(item.get("win_rate")) if _optional_float(item.get("win_rate")) is not None else 1.0,
            _optional_float(item.get("average_trade_return_pct")) or 0.0,
            -(_optional_int(item.get("sample_count")) or 0),
            str(item.get("factor_key")),
            str(item.get("factor_value")),
        )
    )
    return items[:top]


def _top_sold_too_early_factors(summaries: Sequence[Mapping[str, Any]], *, top: int) -> list[dict[str, Any]]:
    items = [
        dict(summary)
        for summary in summaries
        if not summary.get("low_sample")
        and (_optional_int(summary.get("sold_too_early_observed_count")) or 0) > 0
        and (_optional_float(summary.get("sold_too_early_rate_5d")) or 0.0) > 0
    ]
    items.sort(
        key=lambda item: (
            -(_optional_float(item.get("sold_too_early_rate_5d")) or 0.0),
            -(_optional_int(item.get("sold_too_early_count")) or 0),
            -(_optional_float(item.get("average_max_high_return_pct_5d")) or 0.0),
            -(_optional_int(item.get("sample_count")) or 0),
            str(item.get("factor_key")),
        )
    )
    return items[:top]


def _entry_factors(entry_event: Mapping[str, Any]) -> list[dict[str, Any]]:
    factors: list[dict[str, Any]] = []
    method_name = entry_event.get("method_name")
    if method_name:
        factors.append(_factor("entry.method_name", "category", method_name, "入场方法"))
    reason_code = entry_event.get("reason_code")
    if reason_code:
        factors.append(_factor("entry.reason_code", "category", reason_code, "入场原因"))

    for key, value in sorted(_as_mapping(entry_event.get("checks")).items()):
        if isinstance(value, bool):
            factor_key = f"entry.check.{key}"
            factors.append(_factor(factor_key, "check", "true" if value else "false", _entry_factor_label(key)))
    for key, value in sorted(_as_mapping(entry_event.get("categories")).items()):
        if value is not None:
            factor_key = f"entry.category.{key}"
            factors.append(_factor(factor_key, "category", str(value), _entry_category_label(key)))
    return factors


def _factor(key: str, factor_type: str, value: Any, label_zh: str) -> dict[str, str]:
    return {
        "factor_key": key,
        "factor_label_zh": label_zh,
        "factor_type": factor_type,
        "factor_value": str(value),
        "factor_value_label_zh": _factor_value_label(value),
    }


def _entry_factor_label(key: str) -> str:
    declaration = _ATTRIBUTION_DECLARATIONS.get(key)
    if declaration is not None:
        return declaration.label_zh
    return {
        "kdj_j_below_threshold": "KDJ J 低于阈值",
        "kdj_j_above_threshold": "KDJ J 高于阈值",
        "symbol.ma.price_above_ma25": "价格在 MA25 上方",
        "symbol.ma.price_above_ma60": "价格在 MA60 上方",
        "symbol.ma.bullish_trend": "个股均线多头",
        "market.hs300.bullish_trend": "沪深300多头趋势",
        "industry.kdj.j_below_threshold": "行业 KDJ J 低于阈值",
    }.get(key, key)


def _entry_category_label(key: str) -> str:
    return {
        "industry.sw_l1.code": "申万一级行业",
        "sizing.risk_group": "仓位风险组",
    }.get(key, f"入场分类：{key}")


def _factor_value_label(value: Any) -> str:
    text = str(value)
    return {
        "true": "是",
        "false": "否",
        "kdj_oversold_entry": "KDJ 超卖入场",
        "KDJ_J_BELOW_13": "KDJ J 低于 13",
    }.get(text, text)


def _selected_entry_values(value: Any) -> dict[str, Any]:
    values = _as_mapping(value)
    selected_keys = (
        "symbol.close",
        "symbol.ma.ma25",
        "symbol.ma.ma60",
        "market.hs300.close",
        "market.hs300.ma20",
        "industry.kdj.j",
        "symbol.kdj.j",
        "kdj_j",
    )
    return {
        key: values[key]
        for key in selected_keys
        if key in values and _is_scalar_json_value(values[key])
    }


def _post_exit_by_trade_key(post_exit: Mapping[str, Any] | None) -> dict[tuple[str, str, str, str], Mapping[str, Any]]:
    if not post_exit:
        return {}
    return {
        _trade_key(item): _as_mapping(item)
        for item in _as_sequence(post_exit.get("observations"))
    }


def _trade_key(item: Any) -> tuple[str, str, str, str]:
    value = _as_mapping(item)
    return (
        str(value.get("symbol") or ""),
        str(value.get("entry_date") or ""),
        str(value.get("exit_date") or ""),
        str(value.get("exit_reason") or ""),
    )


def _event_by_type(trade: Mapping[str, Any], event_type: str) -> Mapping[str, Any]:
    for event in _as_sequence(trade.get("events")):
        event_map = _as_mapping(event)
        if event_map.get("event_type") == event_type:
            return event_map
    return {}


def _add_on_count(trade: Mapping[str, Any]) -> int:
    return sum(1 for event in _as_sequence(trade.get("events")) if _as_mapping(event).get("event_type") == "add_on")


def _sample_ref(trade: Mapping[str, Any]) -> dict[str, Any]:
    return _drop_none(
        {
            "run_id": trade.get("run_id"),
            "trade_index": trade.get("trade_index"),
            "symbol": trade.get("symbol"),
            "entry_date": trade.get("entry_date"),
            "exit_date": trade.get("exit_date"),
            "outcome": trade.get("outcome"),
            "return_pct": trade.get("return_pct"),
        }
    )


def _factor_sort_key(item: Mapping[str, Any]) -> tuple[int, float, int, str, str]:
    sample_count = _optional_int(item.get("sample_count")) or 0
    avg_return = abs(_optional_float(item.get("average_trade_return_pct")) or 0.0)
    return (
        1 if item.get("low_sample") else 0,
        -avg_return,
        -sample_count,
        str(item.get("factor_key")),
        str(item.get("factor_value")),
    )


def _adaptation_label_zh(value: str) -> str:
    return {
        "preferred": "优先适配",
        "conditional": "条件适配",
        "defensive": "防守/降仓",
        "avoid": "规避",
        "uncertain": "不确定",
    }.get(value, value)


def _adaptation_reason_zh(adaptation: str, metrics: Mapping[str, Any], risk_flags: Sequence[str]) -> str:
    sample_note = "存在样本风险，需要下钻确认。" if risk_flags else "样本风险未触发。"
    if adaptation == "preferred":
        return f"平均段收益为正，胜率达到优先阈值，且多数行情段盈利；{sample_note}"
    if adaptation == "conditional":
        return f"平均段收益为正，但胜率或分段一致性不足，只能作为条件启用候选；{sample_note}"
    if adaptation == "avoid":
        return f"平均段收益为负，胜率低于规避阈值，且多数行情段亏损；{sample_note}"
    if adaptation == "defensive":
        return f"平均段收益为负，但亏损一致性或胜率未达到明确规避阈值，应先降仓或限制交易；{sample_note}"
    return f"关键收益或胜率证据不足，不能形成适配判断；{sample_note}"


def _factor_section(title: str, factors: Any, *, limit: int) -> list[str]:
    rows = _as_sequence(factors)
    lines = ["", title, ""]
    if not rows:
        lines.append("当前没有达到样本阈值的因子。")
        return lines
    lines.extend(
        [
            "| 因子 | 值 | 样本 | 胜率 | 平均收益 | 卖飞率 | 交易引用 |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in rows[:limit]:
        item = _as_mapping(row)
        lines.append(
            "| "
            f"{_escape_cell(item.get('factor_label_zh'))} | "
            f"{_escape_cell(item.get('factor_value_label_zh'))} | "
            f"{item.get('sample_count')} | "
            f"{_format_optional_percent(item.get('win_rate'))} | "
            f"{_format_optional_percent(item.get('average_trade_return_pct'))} | "
            f"{_format_optional_percent(item.get('sold_too_early_rate_5d'))} | "
            f"{_format_sample_refs(item.get('sample_refs'))} |"
        )
    if len(rows) > limit:
        lines.append("")
        lines.append(f"仅展示前 {limit} 条，完整因子见 `strategy_adaptation_matrix.json`。")
    return lines


def _format_sample_refs(value: Any, *, limit: int = 6) -> str:
    refs = _as_sequence(value)
    if not refs:
        return "-"
    labels = []
    for ref in refs[:limit]:
        item = _as_mapping(ref)
        labels.append(f"{item.get('run_id')}#{item.get('trade_index')}")
    suffix = "..." if len(refs) > limit else ""
    return ", ".join(labels) + suffix


def _risk_labels(value: Any) -> str:
    labels = {
        "low_segment_count": "行情段不足",
        "low_sample_segments": "存在低样本段",
        "no_trades": "无交易",
        "missing_market_type_metrics": "关键指标缺失",
    }
    flags = _as_sequence(value)
    if not flags:
        return "-"
    return "；".join(labels.get(str(flag), str(flag)) for flag in flags)


def _load_summary(source: Mapping[str, Any] | str | Path) -> tuple[Mapping[str, Any], Path | None]:
    if isinstance(source, Mapping):
        return source, None
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"missing market type summary: {path}")
    return _as_mapping(json.loads(path.read_text(encoding="utf-8"))), path


def _read_json(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing run artifact: {path}")
    return _as_mapping(json.loads(path.read_text(encoding="utf-8")))


def _read_optional_json(path: Path) -> Mapping[str, Any] | None:
    if not path.exists():
        return None
    return _as_mapping(json.loads(path.read_text(encoding="utf-8")))


def _trade_win_rate(trades: Sequence[Mapping[str, Any]]) -> float | None:
    return _rate(sum(1 for trade in trades if trade.get("outcome") == "win"), len(trades))


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _mean_present(values: Sequence[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return mean(present) if present else None


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except ValueError:
        return None


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _as_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _drop_none(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _is_scalar_json_value(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _format_optional_percent(value: Any) -> str:
    number = _optional_float(value)
    if number is None:
        return "-"
    return f"{number:.2%}"


def _format_bool(value: Any) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    return "-"


def _escape_cell(value: Any) -> str:
    if value is None:
        return "-"
    return " ".join(str(value).replace("|", "/").split())
