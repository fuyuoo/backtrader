"""Compare environment-fit reports across persisted runs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


ENVIRONMENT_FIT_COMPARISON_SCHEMA = "attbacktrader.environment_fit_comparison.v1"


def build_environment_fit_comparison(
    environment_fits_or_paths: Sequence[Mapping[str, Any] | str | Path],
    *,
    common_limit: int = 20,
    sample_ref_limit: int = 3,
) -> dict[str, Any]:
    """Compare persisted ``environment_fit.json`` artifacts without recalculation."""

    if len(environment_fits_or_paths) < 2:
        raise ValueError("at least two environment fit reports are required")
    if common_limit <= 0:
        raise ValueError("common_limit must be greater than 0")
    if sample_ref_limit <= 0:
        raise ValueError("sample_ref_limit must be greater than 0")

    loaded = [_load_environment_fit(source) for source in environment_fits_or_paths]
    reports = [item[0] for item in loaded]
    paths = [item[1] for item in loaded]
    rows = [_comparison_row(report, path) for report, path in zip(reports, paths)]
    common = _common_environment_deltas(reports, limit=common_limit)
    stability = _best_environment_stability(rows)
    drill_down_sample_refs = _drill_down_sample_refs(stability, limit=sample_ref_limit)
    return {
        "schema": ENVIRONMENT_FIT_COMPARISON_SCHEMA,
        "baseline_run_id": rows[0]["run_id"],
        "run_ids": [row["run_id"] for row in rows],
        "source_count": len(rows),
        "rows": rows,
        "best_environment_stability": stability,
        "common_environment_count": common["total_count"],
        "common_environment_deltas": common["deltas"],
        "drill_down_sample_count": len(drill_down_sample_refs),
        "drill_down_sample_refs": drill_down_sample_refs,
        "rules": [
            "只比较已落盘的 environment_fit.json，不重跑策略、不重算指标。",
            "最佳环境在所有 run 中一致且样本数不低于阈值，才可称为稳定线索。",
            "低样本组合只能作为复盘线索，不能作为策略适配结论或调参依据。",
            "drill_down_sample_refs 只用于反查代表交易证据，不代表抽样统计显著性。",
            "净 PnL、入场资金收益率、胜率需要同时查看；不要只看单一指标。",
        ],
    }


def render_environment_fit_comparison_markdown_zh(comparison: Mapping[str, Any]) -> str:
    """Render an environment-fit comparison as Chinese Markdown."""

    lines = [
        "# 环境适配对比",
        "",
        f"- schema: `{comparison.get('schema')}`",
        f"- baseline_run_id: `{comparison.get('baseline_run_id')}`",
        f"- source_count: `{comparison.get('source_count')}`",
        "",
        "## 概览",
        "",
        "| 运行 | 交易 | 可计算贡献 | 总净 PnL | 入场资金收益率 | 净利润最高环境 | 样本 | 资金收益率最高环境 | 样本 | 低样本组合 |",
        "|---|---:|---:|---:|---:|---|---:|---|---:|---:|",
    ]
    for row in _as_sequence(comparison.get("rows")):
        row_map = _as_mapping(row)
        best_net = _as_mapping(row_map.get("best_by_net_pnl"))
        best_capital = _as_mapping(row_map.get("best_by_return_on_entry_value"))
        lines.append(
            "| "
            f"{row_map.get('run_id')} | "
            f"{row_map.get('trade_count')} | "
            f"{row_map.get('contribution_available_count')} | "
            f"{_format_optional_number(row_map.get('overall_net_pnl'))} | "
            f"{_format_optional_percent(row_map.get('overall_return_on_entry_value'))} | "
            f"{_escape_cell(best_net.get('label_zh'))} | "
            f"{best_net.get('sample_count') or '-'} | "
            f"{_escape_cell(best_capital.get('label_zh'))} | "
            f"{best_capital.get('sample_count') or '-'} | "
            f"{row_map.get('low_sample_combination_count')} |"
        )

    lines.extend(
        [
            "",
            "## 最佳环境稳定性",
            "",
            "| 口径 | 状态 | 基准环境 | 各运行环境 | 样本风险 |",
            "|---|---|---|---|---|",
        ]
    )
    for check in _as_sequence(comparison.get("best_environment_stability")):
        check_map = _as_mapping(check)
        environments = [
            f"{_as_mapping(item).get('run_id')}={_as_mapping(item).get('label_zh')}"
            for item in _as_sequence(check_map.get("run_environments"))
        ]
        lines.append(
            "| "
            f"{check_map.get('criterion_zh')} | "
            f"{check_map.get('status_zh')} | "
            f"{_escape_cell(check_map.get('baseline_label_zh'))} | "
            f"{_escape_cell('；'.join(environments))} | "
            f"{_escape_cell(', '.join(str(item) for item in _as_sequence(check_map.get('sample_risk_run_ids'))) or '-')} |"
        )

    deltas = _as_sequence(comparison.get("common_environment_deltas"))
    if deltas:
        lines.extend(
            [
                "",
                "## 共同环境差异",
                "",
                f"共同环境总数：{comparison.get('common_environment_count')}",
                "",
                "| 环境 | 对比运行 | 样本差 | 净 PnL 差 | 入场资金收益率差 | 胜率差 |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        for item in deltas:
            item_map = _as_mapping(item)
            for delta in _as_sequence(item_map.get("deltas")):
                delta_map = _as_mapping(delta)
                lines.append(
                    "| "
                    f"{_escape_cell(item_map.get('label_zh'))} | "
                    f"{delta_map.get('run_id')} | "
                    f"{_format_optional_signed_int(delta_map.get('sample_count_delta'))} | "
                    f"{_format_optional_signed_number(delta_map.get('net_pnl_delta'))} | "
                    f"{_format_optional_signed_percent(delta_map.get('return_on_entry_value_delta'))} | "
                    f"{_format_optional_signed_percent(delta_map.get('win_rate_delta'))} |"
                )

    sample_refs = _as_sequence(comparison.get("drill_down_sample_refs"))
    if sample_refs:
        lines.extend(
            [
                "",
                "## 建议下钻样本",
                "",
                "| 运行 | 口径 | 环境 | trade_index | 原因 |",
                "|---|---|---|---:|---|",
            ]
        )
        for ref in sample_refs:
            ref_map = _as_mapping(ref)
            lines.append(
                "| "
                f"{ref_map.get('run_id')} | "
                f"{ref_map.get('criterion_zh')} | "
                f"{_escape_cell(ref_map.get('label_zh'))} | "
                f"{ref_map.get('trade_index')} | "
                f"{_escape_cell(ref_map.get('reason_zh'))} |"
            )

    lines.extend(["", "## 使用规则"])
    for rule in _as_sequence(comparison.get("rules")):
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def write_environment_fit_comparison(
    comparison: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Write environment-fit comparison JSON and Chinese Markdown."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "environment_fit_comparison.json"
    markdown_path = output_path / "environment_fit_comparison.zh.md"
    json_path.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_environment_fit_comparison_markdown_zh(comparison), encoding="utf-8")
    return json_path, markdown_path


def safe_environment_fit_comparison_dir_name(run_ids: Sequence[str]) -> str:
    joined = "__vs__".join(run_ids)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", joined.strip())
    return f"environment-fit-comparison-{safe or 'runs'}"


def _load_environment_fit(source: Mapping[str, Any] | str | Path) -> tuple[Mapping[str, Any], Path | None]:
    if isinstance(source, Mapping):
        return source, None
    path = Path(source)
    if path.is_dir():
        path = path / "environment_fit.json"
    if not path.exists():
        raise FileNotFoundError(f"missing environment fit artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8")), path


def _comparison_row(report: Mapping[str, Any], path: Path | None) -> dict[str, Any]:
    best = _as_mapping(report.get("best_environments"))
    warnings = _as_mapping(report.get("sample_warnings"))
    overall = _as_mapping(report.get("overall"))
    min_sample_count = _optional_int(report.get("min_sample_count"))
    return {
        "run_id": report.get("run_id"),
        "source_dir": report.get("source_dir"),
        "environment_fit_path": str(path) if path is not None else None,
        "min_sample_count": min_sample_count,
        "trade_count": _optional_int(report.get("trade_count")),
        "contribution_available_count": _optional_int(report.get("contribution_available_count")),
        "overall_net_pnl": _optional_float(overall.get("net_pnl")),
        "overall_return_on_entry_value": _optional_float(overall.get("return_on_entry_value")),
        "best_by_net_pnl": _compact_environment(best.get("best_by_net_pnl"), min_sample_count=min_sample_count),
        "best_by_return_on_entry_value": _compact_environment(
            best.get("best_by_return_on_entry_value"),
            min_sample_count=min_sample_count,
        ),
        "low_sample_combination_count": _optional_int(warnings.get("low_sample_combination_count")),
    }


def _best_environment_stability(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    checks = []
    for key, label in (
        ("best_by_net_pnl", "净利润最高"),
        ("best_by_return_on_entry_value", "资金收益率最高"),
    ):
        environments = [_as_mapping(row.get(key)) for row in rows]
        summary_keys = [environment.get("summary_key") for environment in environments if environment.get("summary_key")]
        sample_risk_run_ids = [
            row.get("run_id")
            for row, environment in zip(rows, environments)
            if environment.get("low_sample") is True
        ]
        status = _stability_status(summary_keys, len(rows), sample_risk_run_ids)
        checks.append(
            {
                "criterion": key,
                "criterion_zh": label,
                "status": status,
                "status_zh": _stability_status_zh(status),
                "baseline_summary_key": environments[0].get("summary_key") if environments else None,
                "baseline_label_zh": environments[0].get("label_zh") if environments else None,
                "run_environments": [
                    {
                        "run_id": row.get("run_id"),
                        "summary_key": environment.get("summary_key"),
                        "label_zh": environment.get("label_zh"),
                        "sample_count": environment.get("sample_count"),
                        "low_sample": environment.get("low_sample"),
                        "net_pnl": environment.get("net_pnl"),
                        "return_on_entry_value": environment.get("return_on_entry_value"),
                        "trade_indexes": environment.get("trade_indexes", []),
                    }
                    for row, environment in zip(rows, environments)
                ],
                "sample_risk_run_ids": [run_id for run_id in sample_risk_run_ids if run_id is not None],
            }
        )
    return checks


def _common_environment_deltas(reports: Sequence[Mapping[str, Any]], *, limit: int) -> dict[str, Any]:
    lookups = [_summary_lookup(report) for report in reports]
    common_keys = set(lookups[0])
    for lookup in lookups[1:]:
        common_keys &= set(lookup)

    baseline_lookup = lookups[0]
    sorted_keys = sorted(
        common_keys,
        key=lambda key: abs(_optional_float(baseline_lookup[key].get("net_pnl")) or 0.0),
        reverse=True,
    )
    deltas = []
    for key in sorted_keys[:limit]:
        baseline = baseline_lookup[key]
        deltas.append(
            {
                "summary_key": key,
                "summary_kind": baseline.get("summary_kind"),
                "label_zh": baseline.get("label_zh"),
                "baseline": _compact_environment(baseline, min_sample_count=_optional_int(reports[0].get("min_sample_count"))),
                "deltas": [
                    _environment_delta(
                        run_id=report.get("run_id"),
                        baseline=baseline,
                        current=lookup[key],
                    )
                    for report, lookup in zip(reports[1:], lookups[1:])
                ],
            }
        )
    return {"total_count": len(common_keys), "deltas": deltas}


def _drill_down_sample_refs(stability_checks: Sequence[Mapping[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()
    for check in stability_checks:
        check_map = _as_mapping(check)
        for environment in _as_sequence(check_map.get("run_environments")):
            environment_map = _as_mapping(environment)
            run_id = str(environment_map.get("run_id") or "")
            summary_key = str(environment_map.get("summary_key") or "")
            if not run_id or not summary_key:
                continue
            for trade_index in _as_sequence(environment_map.get("trade_indexes"))[:limit]:
                trade_int = _optional_int(trade_index)
                if trade_int is None:
                    continue
                key = (run_id, summary_key, trade_int)
                if key in seen:
                    continue
                seen.add(key)
                refs.append(
                    {
                        "run_id": run_id,
                        "kind": "trade",
                        "trade_index": trade_int,
                        "criterion": check_map.get("criterion"),
                        "criterion_zh": check_map.get("criterion_zh"),
                        "summary_key": summary_key,
                        "label_zh": environment_map.get("label_zh"),
                        "reason": "best_environment_representative_trade",
                        "reason_zh": "最佳环境代表交易，用于反查入场环境证据。",
                    }
                )
    return refs


def _summary_lookup(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    lookup: dict[str, Mapping[str, Any]] = {}
    for summary in list(_as_sequence(report.get("single_factor_summaries"))) + list(
        _as_sequence(report.get("combination_summaries"))
    ):
        summary_map = _as_mapping(summary)
        key = _summary_key(summary_map)
        if key is not None:
            lookup[key] = summary_map
    return lookup


def _environment_delta(
    *,
    run_id: Any,
    baseline: Mapping[str, Any],
    current: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "sample_count_delta": _optional_int_delta(current.get("sample_count"), baseline.get("sample_count")),
        "net_pnl_delta": _optional_delta(current.get("net_pnl"), baseline.get("net_pnl")),
        "return_on_entry_value_delta": _optional_delta(
            current.get("return_on_entry_value"),
            baseline.get("return_on_entry_value"),
        ),
        "win_rate_delta": _optional_delta(current.get("win_rate"), baseline.get("win_rate")),
    }


def _compact_environment(value: Any, *, min_sample_count: int | None) -> dict[str, Any]:
    summary = _as_mapping(value)
    if not summary:
        return {}
    sample_count = _optional_int(summary.get("sample_count"))
    low_sample = None
    if sample_count is not None and min_sample_count is not None:
        low_sample = sample_count < min_sample_count
    return _drop_none(
        {
            "summary_key": _summary_key(summary),
            "summary_kind": summary.get("summary_kind"),
            "field": summary.get("field"),
            "value": summary.get("value"),
            "fields": summary.get("fields"),
            "label_zh": summary.get("label_zh"),
            "sample_count": sample_count,
            "low_sample": low_sample,
            "win_rate": _optional_float(summary.get("win_rate")),
            "average_return_pct": _optional_float(summary.get("average_return_pct")),
            "net_pnl": _optional_float(summary.get("net_pnl")),
            "return_on_entry_value": _optional_float(summary.get("return_on_entry_value")),
            "trade_indexes": summary.get("trade_indexes"),
        }
    )


def _summary_key(summary: Mapping[str, Any]) -> str | None:
    kind = summary.get("summary_kind")
    if kind == "single_factor":
        field = summary.get("field")
        if field is None:
            return None
        return f"single:{field}={_value_token(summary.get('value'))}"
    if kind == "combination":
        fields = _as_mapping(summary.get("fields"))
        if fields:
            values = "|".join(f"{field}={_value_token(fields[field])}" for field in sorted(fields))
            return f"combination:{values}"
        profile_key = summary.get("profile_key")
        if profile_key is not None:
            return f"combination:{profile_key}"
    return None


def _value_token(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if value is None:
        return "missing"
    return str(value)


def _stability_status(summary_keys: Sequence[Any], expected_count: int, sample_risk_run_ids: Sequence[Any]) -> str:
    if len(summary_keys) < expected_count:
        return "missing"
    if len(set(summary_keys)) == 1:
        return "same_but_low_sample" if sample_risk_run_ids else "stable"
    return "changed_with_sample_risk" if sample_risk_run_ids else "changed"


def _stability_status_zh(status: str) -> str:
    return {
        "stable": "稳定线索",
        "same_but_low_sample": "环境一致但样本不足",
        "changed": "环境变化",
        "changed_with_sample_risk": "环境变化且有样本风险",
        "missing": "证据缺失",
    }.get(status, status)


def _optional_delta(value: Any, baseline: Any) -> float | None:
    current = _optional_float(value)
    base = _optional_float(baseline)
    if current is None or base is None:
        return None
    return current - base


def _optional_int_delta(value: Any, baseline: Any) -> int | None:
    current = _optional_int(value)
    base = _optional_int(baseline)
    if current is None or base is None:
        return None
    return current - base


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
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_optional_number(value: Any) -> str:
    number = _optional_float(value)
    if number is None:
        return "-"
    return f"{number:.6f}".rstrip("0").rstrip(".")


def _format_optional_signed_number(value: Any) -> str:
    number = _optional_float(value)
    if number is None:
        return "-"
    prefix = "+" if number > 0 else ""
    return f"{prefix}{_format_optional_number(number)}"


def _format_optional_signed_int(value: Any) -> str:
    number = _optional_int(value)
    if number is None:
        return "-"
    return f"{number:+d}"


def _format_optional_percent(value: Any) -> str:
    number = _optional_float(value)
    if number is None:
        return "-"
    return f"{number * 100:.2f}%"


def _format_optional_signed_percent(value: Any) -> str:
    number = _optional_float(value)
    if number is None:
        return "-"
    prefix = "+" if number > 0 else ""
    return f"{prefix}{number * 100:.2f}%"


def _escape_cell(value: Any) -> str:
    if value is None:
        return "-"
    return str(value).replace("|", "\\|")


def _drop_none(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _as_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return value
    return ()
