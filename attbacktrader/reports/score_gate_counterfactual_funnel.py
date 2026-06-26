"""Score-gate counterfactual funnel from persisted entry-factor evidence."""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


SCORE_GATE_COUNTERFACTUAL_FUNNEL_SCHEMA = "attbacktrader.score_gate_counterfactual_funnel.v1"

DEFAULT_EXCLUDED_GATE_FIELD_PREFIXES: tuple[str, ...] = (
    "industry.",
    "entry.universe.",
)


def build_score_gate_counterfactual_funnel(
    environment_fit: Mapping[str, Any] | str | Path,
    factor_matrix: Mapping[str, Any] | str | Path,
    *,
    min_positive_sample_count: int = 300,
    min_positive_years: int = 8,
    min_positive_average_return_pct: float = 0.015,
    min_positive_win_rate: float = 0.49,
    min_positive_max_loss_pct: float = -0.40,
    min_positive_hits: int = 1,
    min_risk_sample_count: int = 300,
    risk_average_return_ceiling_pct: float = 0.0,
    risk_win_rate_ceiling: float = 0.42,
    risk_max_loss_ceiling_pct: float | None = None,
    max_risk_hits: int = 0,
    excluded_field_prefixes: Sequence[str] = DEFAULT_EXCLUDED_GATE_FIELD_PREFIXES,
    gate_candidate_limit: int = 30,
    sample_limit: int = 20,
) -> dict[str, Any]:
    """Build a completed-trade counterfactual for matrix-derived entry score gates."""

    _validate_positive_int(min_positive_sample_count, "min_positive_sample_count")
    _validate_positive_int(min_positive_years, "min_positive_years")
    _validate_positive_int(min_positive_hits, "min_positive_hits")
    _validate_positive_int(min_risk_sample_count, "min_risk_sample_count")
    if max_risk_hits < 0:
        raise ValueError("max_risk_hits must be >= 0")
    _validate_positive_int(gate_candidate_limit, "gate_candidate_limit")
    _validate_positive_int(sample_limit, "sample_limit")

    environment_payload = _load_json_like(environment_fit)
    matrix_payload = _load_json_like(factor_matrix)
    trades = [
        _as_mapping(row)
        for row in _as_sequence(environment_payload.get("trade_contributions"))
        if _as_mapping(row.get("environment"))
    ]
    if not trades:
        raise ValueError("environment_fit must include non-empty trade_contributions with environment fields")

    gate_config = {
        "min_positive_sample_count": min_positive_sample_count,
        "min_positive_years": min_positive_years,
        "min_positive_average_return_pct": min_positive_average_return_pct,
        "min_positive_win_rate": min_positive_win_rate,
        "min_positive_max_loss_pct": min_positive_max_loss_pct,
        "min_positive_hits": min_positive_hits,
        "min_risk_sample_count": min_risk_sample_count,
        "risk_average_return_ceiling_pct": risk_average_return_ceiling_pct,
        "risk_win_rate_ceiling": risk_win_rate_ceiling,
        "risk_max_loss_ceiling_pct": risk_max_loss_ceiling_pct,
        "max_risk_hits": max_risk_hits,
        "excluded_field_prefixes": list(excluded_field_prefixes),
        "gate_candidate_limit": gate_candidate_limit,
    }
    positive_candidates = _positive_gate_candidates(
        matrix_payload,
        gate_config=gate_config,
    )
    if not positive_candidates:
        raise ValueError("no positive gate candidates selected from factor matrix; relax gate thresholds")
    risk_candidates = _risk_gate_candidates(
        matrix_payload,
        gate_config=gate_config,
        positive_candidates=positive_candidates,
    )

    decisions = [
        _score_trade(
            trade,
            positive_candidates=positive_candidates,
            risk_candidates=risk_candidates,
            min_positive_hits=min_positive_hits,
            max_risk_hits=max_risk_hits,
        )
        for trade in trades
    ]
    passed = [row for row in decisions if row["gate_passed"]]
    blocked = [row for row in decisions if not row["gate_passed"]]

    return {
        "schema": SCORE_GATE_COUNTERFACTUAL_FUNNEL_SCHEMA,
        "source_artifacts": {
            "environment_fit": _source_path(environment_fit),
            "factor_matrix": _source_path(factor_matrix),
        },
        "run_id": environment_payload.get("run_id") or matrix_payload.get("run_id"),
        "gate_config": gate_config,
        "gate_definition": {
            "positive_gate": "gate_passed requires positive_hit_count >= min_positive_hits",
            "risk_gate": "gate_passed requires risk_hit_count <= max_risk_hits",
            "caveat_zh": "这是已完成交易样本上的反事实过滤，不是现金再分配后的组合回测。",
        },
        "factor_screen": {
            "positive_gate_candidates": positive_candidates,
            "risk_gate_candidates": risk_candidates,
            "excluded_field_prefixes": list(excluded_field_prefixes),
        },
        "funnel": _funnel(decisions),
        "summary": {
            "all_trades": _stats_from_decisions(decisions),
            "gate_passed": _stats_from_decisions(passed),
            "gate_blocked": _stats_from_decisions(blocked),
            "counterfactual_delta": _counterfactual_delta(decisions, passed, blocked),
        },
        "by_year": _by_year(decisions),
        "by_positive_candidate": _candidate_impact(decisions, positive_candidates, "positive_hits"),
        "by_risk_candidate": _candidate_impact(decisions, risk_candidates, "risk_hits"),
        "samples": {
            "worst_blocked_trades": _trade_samples(blocked, key=lambda row: _optional_float(row.get("return_pct")) or math.inf, limit=sample_limit),
            "best_blocked_winners": _trade_samples(
                [row for row in blocked if (_optional_float(row.get("return_pct")) or 0.0) > 0],
                key=lambda row: -(_optional_float(row.get("return_pct")) or -math.inf),
                limit=sample_limit,
            ),
            "worst_passed_trades": _trade_samples(passed, key=lambda row: _optional_float(row.get("return_pct")) or math.inf, limit=sample_limit),
        },
        "ai_usage_rules": [
            "本报告只读取已落盘 completed-trade 归因证据，不重跑策略、不重新计算指标、不联网取数。",
            "gate_passed 是反事实过滤标签，不代表真实组合收益；真实收益仍需 Scored Portfolio Backtest 验证。",
            "blocked winning trades 是漏掉的盈利样本，必须和 blocked losses 一起看，不能只看挡掉亏损。",
            "默认排除行业和股票池字段，避免把行业/样本池暴露直接固化成通用 score gate。",
        ],
    }


def render_score_gate_counterfactual_funnel_markdown_zh(report: Mapping[str, Any]) -> str:
    """Render a Chinese Markdown summary for the counterfactual funnel."""

    summary = _as_mapping(report.get("summary"))
    delta = _as_mapping(summary.get("counterfactual_delta"))
    lines = [
        "# Score Gate 反事实漏斗",
        "",
        "## 概览",
        "",
        "| 项目 | 值 |",
        "|---|---:|",
        f"| run_id | `{report.get('run_id')}` |",
        f"| 原始交易数 | {_as_mapping(summary.get('all_trades')).get('sample_count')} |",
        f"| Gate通过交易数 | {_as_mapping(summary.get('gate_passed')).get('sample_count')} |",
        f"| Gate阻断交易数 | {_as_mapping(summary.get('gate_blocked')).get('sample_count')} |",
        f"| 阻断亏损交易 | {delta.get('blocked_loss_count')} |",
        f"| 漏掉盈利交易 | {delta.get('blocked_win_count')} |",
        f"| 阻断亏损PnL | {_format_money(delta.get('blocked_loss_net_pnl'))} |",
        f"| 漏掉盈利PnL | {_format_money(delta.get('missed_win_net_pnl'))} |",
        f"| 移除被阻断交易后的净PnL变化 | {_format_money(delta.get('net_pnl_delta_if_blocked_removed'))} |",
        "",
        "## 口径",
        "",
        "- 本报告是已完成交易样本上的反事实过滤，不是现金再分配后的组合回测。",
        "- `Gate通过` 表示交易命中足够数量的安全正向因子，且未命中过多风险因子。",
        "- `阻断亏损PnL` 和 `漏掉盈利PnL` 必须一起看；只看挡掉亏损会高估 gate。",
        "- 默认不把行业代码和股票池字段作为通用 gate 候选。",
        "",
    ]
    lines.extend(_gate_config_section(_as_mapping(report.get("gate_config"))))
    lines.extend(_candidate_section("正向 Gate 候选", _as_sequence(_as_mapping(report.get("factor_screen")).get("positive_gate_candidates"))))
    lines.extend(_candidate_section("风险 Gate 候选", _as_sequence(_as_mapping(report.get("factor_screen")).get("risk_gate_candidates"))))
    lines.extend(_summary_section(summary))
    lines.extend(_year_section(_as_sequence(report.get("by_year"))))
    lines.extend(_sample_section("最差被阻断交易", _as_sequence(_as_mapping(report.get("samples")).get("worst_blocked_trades"))))
    lines.extend(_sample_section("被阻断的最佳盈利交易", _as_sequence(_as_mapping(report.get("samples")).get("best_blocked_winners"))))
    lines.extend(_sample_section("Gate通过后的最差交易", _as_sequence(_as_mapping(report.get("samples")).get("worst_passed_trades"))))
    return "\n".join(lines) + "\n"


def write_score_gate_counterfactual_funnel(
    report: Mapping[str, Any],
    *,
    output_dir: str | Path,
    artifact_stem: str = "score_gate_counterfactual_funnel",
) -> tuple[Path, Path, dict[str, Any]]:
    """Write JSON and Chinese Markdown artifacts."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    payload = _jsonable(dict(report))
    json_path = output_path / f"{artifact_stem}.json"
    markdown_path = output_path / f"{artifact_stem}.zh.md"
    payload["artifacts"] = {
        "funnel_json": str(json_path),
        "funnel_markdown_zh": str(markdown_path),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_score_gate_counterfactual_funnel_markdown_zh(payload), encoding="utf-8")
    return json_path, markdown_path, payload


def safe_score_gate_counterfactual_funnel_dir_name(source_path: str | Path) -> str:
    """Build a stable report directory name from a source artifact path."""

    path = Path(source_path)
    name = path.parent.name if path.name.startswith("segmented_factor_contribution_matrix") else path.name
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-")
    return f"score-gate-counterfactual-funnel-{safe or 'factor-matrix'}"


def _positive_gate_candidates(
    matrix: Mapping[str, Any],
    *,
    gate_config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows = _matrix_rows(matrix)
    selected = []
    for row in rows:
        summary = _as_mapping(row.get("summary"))
        if not _gate_field_allowed(row, gate_config):
            continue
        if int(summary.get("sample_count") or 0) < int(gate_config["min_positive_sample_count"]):
            continue
        if int(row.get("positive_segment_count") or 0) < int(gate_config["min_positive_years"]):
            continue
        if (_optional_float(summary.get("average_return_pct")) or -math.inf) < float(gate_config["min_positive_average_return_pct"]):
            continue
        if (_optional_float(summary.get("win_rate")) or -math.inf) < float(gate_config["min_positive_win_rate"]):
            continue
        if (_optional_float(summary.get("min_return_pct")) or -math.inf) < float(gate_config["min_positive_max_loss_pct"]):
            continue
        selected.append(_candidate_ref(row, role="positive"))
    selected.sort(key=_positive_candidate_sort_key, reverse=True)
    return selected[: int(gate_config["gate_candidate_limit"])]


def _risk_gate_candidates(
    matrix: Mapping[str, Any],
    *,
    gate_config: Mapping[str, Any],
    positive_candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows = _matrix_rows(matrix)
    positive_keys = {(str(item.get("field")), _stable_value_key(item.get("value"))) for item in positive_candidates}
    selected = []
    for row in rows:
        summary = _as_mapping(row.get("summary"))
        key = (str(row.get("field")), _stable_value_key(row.get("value")))
        if key in positive_keys or not _gate_field_allowed(row, gate_config):
            continue
        if int(summary.get("sample_count") or 0) < int(gate_config["min_risk_sample_count"]):
            continue
        avg = _optional_float(summary.get("average_return_pct"))
        roev = _optional_float(summary.get("return_on_entry_value"))
        win_rate = _optional_float(summary.get("win_rate"))
        min_return = _optional_float(summary.get("min_return_pct"))
        max_loss_ceiling = gate_config.get("risk_max_loss_ceiling_pct")
        is_risk = (
            row.get("assessment") == "mostly_negative"
            or (avg is not None and avg <= float(gate_config["risk_average_return_ceiling_pct"]))
            or (roev is not None and roev <= 0)
            or (win_rate is not None and win_rate <= float(gate_config["risk_win_rate_ceiling"]))
            or (max_loss_ceiling is not None and min_return is not None and min_return <= float(max_loss_ceiling))
        )
        if is_risk:
            selected.append(_candidate_ref(row, role="risk"))
    selected.sort(key=_risk_candidate_sort_key)
    return selected[: int(gate_config["gate_candidate_limit"])]


def _score_trade(
    trade: Mapping[str, Any],
    *,
    positive_candidates: Sequence[Mapping[str, Any]],
    risk_candidates: Sequence[Mapping[str, Any]],
    min_positive_hits: int,
    max_risk_hits: int,
) -> dict[str, Any]:
    environment = _as_mapping(trade.get("environment"))
    positive_hits = _matching_candidates(environment, positive_candidates)
    risk_hits = _matching_candidates(environment, risk_candidates)
    positive_hit_count = len(positive_hits)
    risk_hit_count = len(risk_hits)
    return {
        "trade_index": trade.get("trade_index"),
        "symbol": trade.get("symbol"),
        "entry_date": trade.get("entry_date"),
        "exit_date": trade.get("exit_date"),
        "return_pct": trade.get("return_pct"),
        "net_pnl": trade.get("net_pnl"),
        "entry_gross_value": trade.get("entry_gross_value"),
        "exit_reason": trade.get("exit_reason"),
        "positive_hit_count": positive_hit_count,
        "risk_hit_count": risk_hit_count,
        "score": positive_hit_count - risk_hit_count,
        "gate_passed": positive_hit_count >= min_positive_hits and risk_hit_count <= max_risk_hits,
        "positive_hits": positive_hits,
        "risk_hits": risk_hits,
    }


def _matching_candidates(
    environment: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    hits = []
    for candidate in candidates:
        field = str(candidate.get("field") or "")
        if field not in environment:
            continue
        if _stable_value_key(environment.get(field)) == _stable_value_key(candidate.get("value")):
            hits.append(
                {
                    "field": field,
                    "value": candidate.get("value"),
                    "label_zh": candidate.get("label_zh"),
                }
            )
    return hits


def _matrix_rows(matrix: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = _as_sequence(matrix.get("annual_factor_bucket_matrix")) or _as_sequence(matrix.get("factor_bucket_matrix"))
    return [_as_mapping(row) for row in rows]


def _gate_field_allowed(row: Mapping[str, Any], gate_config: Mapping[str, Any]) -> bool:
    if row.get("field_usage") != "entry_decision":
        return False
    field = str(row.get("field") or "")
    excluded_prefixes = [str(item) for item in _as_sequence(gate_config.get("excluded_field_prefixes"))]
    return not any(field.startswith(prefix) for prefix in excluded_prefixes)


def _candidate_ref(row: Mapping[str, Any], *, role: str) -> dict[str, Any]:
    summary = _as_mapping(row.get("summary"))
    return {
        "role": role,
        "field": row.get("field"),
        "field_label_zh": row.get("field_label_zh"),
        "value": row.get("value"),
        "value_label_zh": row.get("value_label_zh"),
        "label_zh": row.get("label_zh"),
        "assessment": row.get("assessment"),
        "sample_count": summary.get("sample_count"),
        "average_return_pct": summary.get("average_return_pct"),
        "win_rate": summary.get("win_rate"),
        "return_on_entry_value": summary.get("return_on_entry_value"),
        "max_return_pct": summary.get("max_return_pct"),
        "min_return_pct": summary.get("min_return_pct"),
        "positive_segment_count": row.get("positive_segment_count"),
        "supported_segment_count": row.get("supported_segment_count"),
    }


def _positive_candidate_sort_key(row: Mapping[str, Any]) -> tuple[float, float, float, float, int]:
    return (
        float(row.get("positive_segment_count") or 0) / max(float(row.get("supported_segment_count") or 1), 1.0),
        _optional_float(row.get("average_return_pct")) or -math.inf,
        _optional_float(row.get("win_rate")) or -math.inf,
        _optional_float(row.get("min_return_pct")) or -math.inf,
        int(row.get("sample_count") or 0),
    )


def _risk_candidate_sort_key(row: Mapping[str, Any]) -> tuple[float, float, int]:
    return (
        _optional_float(row.get("average_return_pct")) or math.inf,
        _optional_float(row.get("return_on_entry_value")) or math.inf,
        -int(row.get("sample_count") or 0),
    )


def _funnel(decisions: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    blocked = [row for row in decisions if not row.get("gate_passed")]
    passed = [row for row in decisions if row.get("gate_passed")]
    return {
        "raw_completed_trades": len(decisions),
        "gate_passed_trades": len(passed),
        "gate_blocked_trades": len(blocked),
        "gate_blocked_losses": sum(1 for row in blocked if (_optional_float(row.get("return_pct")) or 0.0) <= 0),
        "gate_blocked_winners": sum(1 for row in blocked if (_optional_float(row.get("return_pct")) or 0.0) > 0),
        "passed_extreme_loss_20pct_count": sum(1 for row in passed if (_optional_float(row.get("return_pct")) or 0.0) <= -0.20),
        "blocked_extreme_loss_20pct_count": sum(1 for row in blocked if (_optional_float(row.get("return_pct")) or 0.0) <= -0.20),
        "passed_extreme_loss_30pct_count": sum(1 for row in passed if (_optional_float(row.get("return_pct")) or 0.0) <= -0.30),
        "blocked_extreme_loss_30pct_count": sum(1 for row in blocked if (_optional_float(row.get("return_pct")) or 0.0) <= -0.30),
    }


def _counterfactual_delta(
    all_rows: Sequence[Mapping[str, Any]],
    passed_rows: Sequence[Mapping[str, Any]],
    blocked_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    blocked_losses = [row for row in blocked_rows if (_optional_float(row.get("return_pct")) or 0.0) <= 0]
    blocked_wins = [row for row in blocked_rows if (_optional_float(row.get("return_pct")) or 0.0) > 0]
    blocked_net_pnl = _sum_float(row.get("net_pnl") for row in blocked_rows)
    blocked_loss_net_pnl = _sum_float(row.get("net_pnl") for row in blocked_losses)
    missed_win_net_pnl = _sum_float(row.get("net_pnl") for row in blocked_wins)
    all_stats = _stats_from_decisions(all_rows)
    passed_stats = _stats_from_decisions(passed_rows)
    return {
        "blocked_loss_count": len(blocked_losses),
        "blocked_win_count": len(blocked_wins),
        "blocked_loss_net_pnl": blocked_loss_net_pnl,
        "missed_win_net_pnl": missed_win_net_pnl,
        "blocked_net_pnl": blocked_net_pnl,
        "net_pnl_delta_if_blocked_removed": -blocked_net_pnl if blocked_net_pnl is not None else None,
        "gate_passed_return_on_entry_lift": _diff(passed_stats.get("return_on_entry_value"), all_stats.get("return_on_entry_value")),
        "gate_passed_average_return_lift": _diff(passed_stats.get("average_return_pct"), all_stats.get("average_return_pct")),
        "gate_passed_win_rate_lift": _diff(passed_stats.get("win_rate"), all_stats.get("win_rate")),
    }


def _stats_from_decisions(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    returns = [value for row in rows if (value := _optional_float(row.get("return_pct"))) is not None]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value <= 0]
    financial_rows = [
        row
        for row in rows
        if _optional_float(row.get("entry_gross_value")) is not None and _optional_float(row.get("net_pnl")) is not None
    ]
    entry_value = _sum_float(row.get("entry_gross_value") for row in financial_rows)
    net_pnl = _sum_float(row.get("net_pnl") for row in financial_rows)
    exit_reasons = Counter(str(row.get("exit_reason")) for row in rows if row.get("exit_reason") is not None)
    return {
        "sample_count": len(rows),
        "return_sample_count": len(returns),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": len(wins) / len(returns) if returns else None,
        "average_return_pct": _average(returns),
        "median_return_pct": _percentile(returns, 0.5),
        "max_return_pct": max(returns) if returns else None,
        "min_return_pct": min(returns) if returns else None,
        "average_win_return_pct": _average(wins),
        "average_loss_return_pct": _average(losses),
        "financial_trade_count": len(financial_rows),
        "total_entry_value": entry_value,
        "net_pnl": net_pnl,
        "return_on_entry_value": net_pnl / entry_value if entry_value and entry_value > 0 else None,
        "exit_reason_counts": [
            {"code": code, "count": count}
            for code, count in sorted(exit_reasons.items(), key=lambda item: (-item[1], item[0]))
        ],
    }


def _by_year(decisions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_year: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in decisions:
        entry_date = str(row.get("entry_date") or "")
        year = entry_date[:4] if re.match(r"^\d{4}-\d{2}-\d{2}$", entry_date) else "unknown"
        by_year[year].append(row)
    results = []
    for year, rows in sorted(by_year.items()):
        passed = [row for row in rows if row.get("gate_passed")]
        blocked = [row for row in rows if not row.get("gate_passed")]
        results.append(
            {
                "year": year,
                "all_trades": _stats_from_decisions(rows),
                "gate_passed": _stats_from_decisions(passed),
                "gate_blocked": _stats_from_decisions(blocked),
                "counterfactual_delta": _counterfactual_delta(rows, passed, blocked),
            }
        )
    return results


def _candidate_impact(
    decisions: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    hit_key: str,
) -> list[dict[str, Any]]:
    rows = []
    for candidate in candidates:
        label = str(candidate.get("label_zh") or "")
        matching = [
            row
            for row in decisions
            if any(_as_mapping(hit).get("label_zh") == label for hit in _as_sequence(row.get(hit_key)))
        ]
        rows.append(
            {
                "label_zh": label,
                "field": candidate.get("field"),
                "value": candidate.get("value"),
                "match_count": len(matching),
                "stats": _stats_from_decisions(matching),
            }
        )
    return rows


def _trade_samples(
    rows: Sequence[Mapping[str, Any]],
    *,
    key: Any,
    limit: int,
) -> list[dict[str, Any]]:
    samples = []
    for row in sorted(rows, key=key)[:limit]:
        samples.append(
            {
                "trade_index": row.get("trade_index"),
                "symbol": row.get("symbol"),
                "entry_date": row.get("entry_date"),
                "exit_date": row.get("exit_date"),
                "return_pct": row.get("return_pct"),
                "net_pnl": row.get("net_pnl"),
                "exit_reason": row.get("exit_reason"),
                "positive_hit_count": row.get("positive_hit_count"),
                "risk_hit_count": row.get("risk_hit_count"),
                "positive_hits": row.get("positive_hits"),
                "risk_hits": row.get("risk_hits"),
            }
        )
    return samples


def _gate_config_section(config: Mapping[str, Any]) -> list[str]:
    return [
        "## Gate 参数",
        "",
        "| 参数 | 值 |",
        "|---|---:|",
        f"| min_positive_sample_count | {config.get('min_positive_sample_count')} |",
        f"| min_positive_years | {config.get('min_positive_years')} |",
        f"| min_positive_average_return_pct | {_format_percent(config.get('min_positive_average_return_pct'))} |",
        f"| min_positive_win_rate | {_format_percent(config.get('min_positive_win_rate'))} |",
        f"| min_positive_max_loss_pct | {_format_percent(config.get('min_positive_max_loss_pct'))} |",
        f"| min_positive_hits | {config.get('min_positive_hits')} |",
        f"| max_risk_hits | {config.get('max_risk_hits')} |",
        "",
    ]


def _candidate_section(title: str, rows: Sequence[Any]) -> list[str]:
    lines = [
        f"## {title}",
        "",
        "| 因子桶 | 样本 | 平均单笔收益 | 胜率 | 资金收益率 | 最大盈利 | 最大亏损 | 正年/覆盖 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    if not rows:
        lines.append("| 无 | - | - | - | - | - | - | - |")
        lines.append("")
        return lines
    for row in rows:
        item = _as_mapping(row)
        lines.append(
            f"| {item.get('label_zh')} | "
            f"{item.get('sample_count')} | "
            f"{_format_percent(item.get('average_return_pct'))} | "
            f"{_format_percent(item.get('win_rate'))} | "
            f"{_format_percent(item.get('return_on_entry_value'))} | "
            f"{_format_percent(item.get('max_return_pct'))} | "
            f"{_format_percent(item.get('min_return_pct'))} | "
            f"{item.get('positive_segment_count')}/{item.get('supported_segment_count')} |"
        )
    lines.append("")
    return lines


def _summary_section(summary: Mapping[str, Any]) -> list[str]:
    rows = [
        ("原始全部交易", _as_mapping(summary.get("all_trades"))),
        ("Gate通过", _as_mapping(summary.get("gate_passed"))),
        ("Gate阻断", _as_mapping(summary.get("gate_blocked"))),
    ]
    lines = [
        "## 漏斗质量",
        "",
        "| 分组 | 样本 | 平均单笔收益 | 胜率 | 最大盈利 | 最大亏损 | 资金收益率 | 净PnL |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in rows:
        lines.append(
            f"| {label} | "
            f"{item.get('sample_count')} | "
            f"{_format_percent(item.get('average_return_pct'))} | "
            f"{_format_percent(item.get('win_rate'))} | "
            f"{_format_percent(item.get('max_return_pct'))} | "
            f"{_format_percent(item.get('min_return_pct'))} | "
            f"{_format_percent(item.get('return_on_entry_value'))} | "
            f"{_format_money(item.get('net_pnl'))} |"
        )
    lines.append("")
    return lines


def _year_section(rows: Sequence[Any]) -> list[str]:
    lines = [
        "## 年度漏斗",
        "",
        "| 年份 | 原始样本 | 通过样本 | 阻断样本 | 通过平均收益 | 通过胜率 | 阻断净PnL | 移除阻断后PnL变化 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        item = _as_mapping(row)
        all_stats = _as_mapping(item.get("all_trades"))
        passed = _as_mapping(item.get("gate_passed"))
        blocked = _as_mapping(item.get("gate_blocked"))
        delta = _as_mapping(item.get("counterfactual_delta"))
        lines.append(
            f"| {item.get('year')} | "
            f"{all_stats.get('sample_count')} | "
            f"{passed.get('sample_count')} | "
            f"{blocked.get('sample_count')} | "
            f"{_format_percent(passed.get('average_return_pct'))} | "
            f"{_format_percent(passed.get('win_rate'))} | "
            f"{_format_money(blocked.get('net_pnl'))} | "
            f"{_format_money(delta.get('net_pnl_delta_if_blocked_removed'))} |"
        )
    lines.append("")
    return lines


def _sample_section(title: str, rows: Sequence[Any]) -> list[str]:
    lines = [
        f"## {title}",
        "",
        "| trade_index | 标的 | 入场 | 出场 | 收益 | 净PnL | 退出原因 | 正向命中 | 风险命中 |",
        "|---:|---|---|---|---:|---:|---|---:|---:|",
    ]
    if not rows:
        lines.append("| 无 | - | - | - | - | - | - | - | - |")
        lines.append("")
        return lines
    for row in rows:
        item = _as_mapping(row)
        lines.append(
            f"| {item.get('trade_index')} | "
            f"{item.get('symbol')} | "
            f"{item.get('entry_date')} | "
            f"{item.get('exit_date')} | "
            f"{_format_percent(item.get('return_pct'))} | "
            f"{_format_money(item.get('net_pnl'))} | "
            f"{item.get('exit_reason')} | "
            f"{item.get('positive_hit_count')} | "
            f"{item.get('risk_hit_count')} |"
        )
    lines.append("")
    return lines


def _load_json_like(value: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    path = Path(value)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"artifact must be a JSON object: {path}")
    return payload


def _source_path(value: Mapping[str, Any] | str | Path) -> str | None:
    return None if isinstance(value, Mapping) else str(value)


def _validate_positive_int(value: int, name: str) -> None:
    if int(value) <= 0:
        raise ValueError(f"{name} must be greater than 0")


def _average(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[int(position)]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _diff(left: Any, right: Any) -> float | None:
    left_value = _optional_float(left)
    right_value = _optional_float(right)
    if left_value is None or right_value is None:
        return None
    return left_value - right_value


def _sum_float(values: Any) -> float | None:
    numbers = [number for value in values if (number := _optional_float(value)) is not None]
    return sum(numbers) if numbers else None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _stable_value_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _format_percent(value: Any) -> str:
    number = _optional_float(value)
    return "-" if number is None else f"{number:.2%}"


def _format_money(value: Any) -> str:
    number = _optional_float(value)
    return "-" if number is None else f"{number:,.0f}"


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> list[Any]:
    return list(value) if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else []


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_jsonable(item) for item in value]
    return value
