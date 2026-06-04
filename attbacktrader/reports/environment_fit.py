"""Environment fit and profit contribution summaries for persisted runs."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from attbacktrader.strategies.attribution import entry_attribution_declaration_by_key


ENVIRONMENT_FIT_SCHEMA = "attbacktrader.environment_fit.v1"

DEFAULT_ENVIRONMENT_FIELDS: tuple[str, ...] = (
    "industry.kdj.j_below_threshold",
    "market.hs300.bullish_trend",
    "symbol.ma.bullish_trend",
    "symbol.ma.price_above_ma25",
    "symbol.ma.price_above_ma60",
)

_ATTRIBUTION_DECLARATIONS = entry_attribution_declaration_by_key()


def build_environment_fit_report_from_run_dir(
    run_dir: str | Path,
    *,
    environment_fields: Sequence[str] = DEFAULT_ENVIRONMENT_FIELDS,
    min_sample_count: int = 5,
) -> dict[str, Any]:
    """Build an environment-fit report from persisted run artifacts."""

    run_path = Path(run_dir)
    if not run_path.exists():
        raise FileNotFoundError(f"Run artifact directory does not exist: {run_path}")

    run_plan = _as_mapping(_load_json_if_exists(run_path / "run_plan.json"))
    trade_review = _as_mapping(_load_json_if_exists(run_path / "trade_review.json"))
    trade_lifecycle = _as_mapping(_load_json_if_exists(run_path / "trade_lifecycle.json"))
    return build_environment_fit_report_from_artifacts(
        run_id=_run_id(run_path, run_plan),
        source_dir=str(run_path),
        trade_review=trade_review,
        trade_lifecycle=trade_lifecycle,
        environment_fields=environment_fields,
        min_sample_count=min_sample_count,
    )


def build_environment_fit_report_from_artifacts(
    *,
    run_id: str,
    source_dir: str | None = None,
    trade_review: Mapping[str, Any],
    trade_lifecycle: Mapping[str, Any] | None = None,
    environment_fields: Sequence[str] = DEFAULT_ENVIRONMENT_FIELDS,
    min_sample_count: int = 5,
) -> dict[str, Any]:
    """Build environment and contribution summaries from report artifacts.

    The report treats missing checks as unavailable evidence. Missing values are
    never defaulted to False or zero.
    """

    if min_sample_count <= 0:
        raise ValueError("min_sample_count must be greater than 0")

    fields = tuple(str(field) for field in environment_fields)
    trades = _trade_rows(
        trade_review,
        trade_lifecycle=_as_mapping(trade_lifecycle),
        environment_fields=fields,
    )
    single_factor_summaries = _single_factor_summaries(trades, fields)
    combination_summaries = _combination_summaries(trades, fields)
    trade_contributions = _trade_contributions(trades)
    return {
        "schema": ENVIRONMENT_FIT_SCHEMA,
        "run_id": run_id,
        "source_dir": source_dir,
        "environment_fields": [
            {
                "field": field,
                "label_zh": _factor_label(field),
            }
            for field in fields
        ],
        "min_sample_count": min_sample_count,
        "trade_count": len(trades),
        "contribution_available_count": sum(
            1
            for trade in trades
            if _as_mapping(trade.get("profit_contribution")).get("contribution_available") is True
        ),
        "overall": _stats(trades),
        "best_environments": _best_environments(
            single_factor_summaries=single_factor_summaries,
            combination_summaries=combination_summaries,
            min_sample_count=min_sample_count,
        ),
        "sample_warnings": _sample_warnings(
            single_factor_summaries=single_factor_summaries,
            combination_summaries=combination_summaries,
            min_sample_count=min_sample_count,
        ),
        "single_factor_summaries": single_factor_summaries,
        "combination_summaries": combination_summaries,
        "trade_contributions": trade_contributions,
        "ai_usage_rules": [
            "该报告只消费已落盘的 trade_review 和 trade_lifecycle，不重跑策略、不重算指标。",
            "字段缺失表示当时没有足够证据，不能当成 false、0 或中性结果。",
            "胜率和平均收益按交易 return_pct 统计；利润贡献按已完成执行的成交额和佣金统计。",
            "组合环境只统计所有配置字段都存在的交易，样本数低于 min_sample_count 的组合只能作为线索。",
        ],
    }


def render_environment_fit_markdown_zh(report: Mapping[str, Any], *, limit: int = 50) -> str:
    """Render an environment-fit report in Chinese Markdown."""

    overall = _as_mapping(report.get("overall"))
    lines = [
        "# 策略环境适配与利润贡献",
        "",
        "## 概览",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
        f"| run_id | `{report.get('run_id')}` |",
        f"| 交易样本 | {report.get('trade_count')} |",
        f"| 有资金贡献口径的交易 | {report.get('contribution_available_count')} |",
        f"| 最小结论样本数 | {report.get('min_sample_count')} |",
        f"| 总胜率 | {_format_optional_percent(overall.get('win_rate'))} |",
        f"| 平均单笔收益 | {_format_optional_percent(overall.get('average_return_pct'))} |",
        f"| 总净 PnL | {_format_optional_money(overall.get('net_pnl'))} |",
        f"| 入场成交额收益率 | {_format_optional_percent(overall.get('return_on_entry_value'))} |",
    ]

    best = _as_mapping(report.get("best_environments"))
    if best:
        lines.extend(
            [
                "",
                "## 结论摘要",
                "",
                "| 口径 | 类型 | 环境 | 样本 | 胜率 | 平均收益 | 净 PnL | 入场资金收益率 | 交易编号 |",
                "|---|---|---|---:|---:|---:|---:|---:|---|",
            ]
        )
        for key, label in (
            ("best_by_net_pnl", "净利润最高"),
            ("best_by_return_on_entry_value", "资金收益率最高"),
            ("best_by_win_rate", "胜率最高"),
            ("worst_by_net_pnl", "净利润最低"),
        ):
            candidate = _as_mapping(best.get(key))
            if not candidate:
                continue
            lines.append(
                "| "
                f"{label} | "
                f"{_summary_kind_label(candidate.get('summary_kind'))} | "
                f"{_escape_cell(candidate.get('label_zh'))} | "
                f"{candidate.get('sample_count')} | "
                f"{_format_optional_percent(candidate.get('win_rate'))} | "
                f"{_format_optional_percent(candidate.get('average_return_pct'))} | "
                f"{_format_optional_money(candidate.get('net_pnl'))} | "
                f"{_format_optional_percent(candidate.get('return_on_entry_value'))} | "
                f"{_format_indexes(candidate.get('trade_indexes'))} |"
            )

    warnings = _as_mapping(report.get("sample_warnings"))
    if warnings:
        low_single = int(warnings.get("low_sample_single_factor_count", 0))
        low_combo = int(warnings.get("low_sample_combination_count", 0))
        lines.extend(
            [
                "",
                "## 样本不足警告",
                "",
                "| 项目 | 值 |",
                "|---|---:|",
                f"| 最小结论样本数 | {warnings.get('min_sample_count')} |",
                f"| 样本不足单因子分组 | {low_single} |",
                f"| 样本不足组合分组 | {low_combo} |",
            ]
        )
        if low_single or low_combo:
            lines.append("")
            lines.append("以下分组样本数低于阈值，只能作为线索，不能作为稳定结论。")
            lines.extend(
                [
                    "",
                    "| 类型 | 环境 | 样本 | 胜率 | 平均收益 | 净 PnL | 入场资金收益率 |",
                    "|---|---|---:|---:|---:|---:|---:|",
                ]
            )
            for candidate in _as_sequence(warnings.get("low_sample_candidates"))[:10]:
                candidate_map = _as_mapping(candidate)
                lines.append(
                    "| "
                    f"{_summary_kind_label(candidate_map.get('summary_kind'))} | "
                    f"{_escape_cell(candidate_map.get('label_zh'))} | "
                    f"{candidate_map.get('sample_count')} | "
                    f"{_format_optional_percent(candidate_map.get('win_rate'))} | "
                    f"{_format_optional_percent(candidate_map.get('average_return_pct'))} | "
                    f"{_format_optional_money(candidate_map.get('net_pnl'))} | "
                    f"{_format_optional_percent(candidate_map.get('return_on_entry_value'))} |"
                )
        else:
            lines.append("")
            lines.append("当前分组没有低于最小结论样本数的候选。")

    lines.extend(
        [
            "",
            "## 环境字段",
            "",
            "| 字段 | 含义 |",
            "|---|---|",
        ]
    )
    for field in _as_sequence(report.get("environment_fields")):
        field_map = _as_mapping(field)
        lines.append(f"| `{field_map.get('field')}` | {_escape_cell(field_map.get('label_zh'))} |")

    lines.extend(
        [
            "",
            "## 单因子环境表现",
            "",
            "| 字段 | 值 | 样本 | 胜率 | 平均收益 | 净 PnL | 入场资金收益率 | 止损 | 止盈 | 交易编号 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for summary in _as_sequence(report.get("single_factor_summaries"))[:limit]:
        summary_map = _as_mapping(summary)
        lines.append(_summary_row(summary_map, include_field=True))

    lines.extend(
        [
            "",
            "## 组合环境表现",
            "",
            "| 组合 | 样本 | 胜率 | 平均收益 | 净 PnL | 入场资金收益率 | 止损 | 止盈 | 交易编号 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for summary in _as_sequence(report.get("combination_summaries"))[:limit]:
        summary_map = _as_mapping(summary)
        lines.append(_summary_row(summary_map, include_field=False))

    lines.extend(
        [
            "",
            "## 交易利润贡献明细",
            "",
            "| # | 股票 | 入场 | 退出 | 结果 | 退出原因 | 收益率 | 净 PnL | 入场成交额 | 退出成交额 | 总佣金 | 入场环境 |",
            "|---:|---|---|---|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for contribution in _as_sequence(report.get("trade_contributions"))[:limit]:
        row = _as_mapping(contribution)
        lines.append(
            "| "
            f"{row.get('trade_index')} | "
            f"{row.get('symbol')} | "
            f"{row.get('entry_date')} | "
            f"{row.get('exit_date')} | "
            f"{_outcome_label(row.get('outcome'))} | "
            f"{row.get('exit_reason')} | "
            f"{_format_optional_percent(row.get('return_pct'))} | "
            f"{_format_optional_money(row.get('net_pnl'))} | "
            f"{_format_optional_money(row.get('entry_gross_value'))} | "
            f"{_format_optional_money(row.get('exit_gross_value'))} | "
            f"{_format_optional_money(row.get('total_commission'))} | "
            f"{_escape_cell(_format_environment(row.get('environment')))} |"
        )
    if len(_as_sequence(report.get("trade_contributions"))) > limit:
        lines.append("")
        lines.append(f"仅展示前 {limit} 条交易，完整明细见 `environment_fit.json`。")

    lines.extend(["", "## AI 使用规则"])
    for rule in _as_sequence(report.get("ai_usage_rules")):
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def write_environment_fit_report(
    report: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write environment fit JSON and Chinese Markdown artifacts."""

    target_dir = Path(output_dir) if output_dir is not None else Path(str(report["source_dir"]))
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / "environment_fit.json"
    markdown_path = target_dir / "environment_fit.zh.md"
    json_path.write_text(_to_pretty_json(report), encoding="utf-8")
    markdown_path.write_text(render_environment_fit_markdown_zh(report), encoding="utf-8")
    return json_path, markdown_path


def _trade_rows(
    trade_review: Mapping[str, Any],
    *,
    trade_lifecycle: Mapping[str, Any],
    environment_fields: Sequence[str],
) -> list[dict[str, Any]]:
    lifecycle_by_index = {
        int(lifecycle["trade_index"]): _as_mapping(lifecycle)
        for lifecycle in _as_sequence(trade_lifecycle.get("lifecycles"))
        if _as_mapping(lifecycle).get("trade_index") is not None
    }
    rows = []
    for trade in _as_sequence(trade_review.get("trades")):
        trade_map = _as_mapping(trade)
        trade_index = _optional_int(trade_map.get("trade_index"))
        if trade_index is None:
            continue
        entry_checks = _as_mapping(trade_map.get("entry_checks"))
        environment = {
            field: entry_checks[field]
            for field in environment_fields
            if field in entry_checks
        }
        lifecycle = lifecycle_by_index.get(trade_index, {})
        contribution = _profit_contribution(lifecycle)
        rows.append(
            _drop_empty(
                {
                    "trade_index": trade_index,
                    "symbol": trade_map.get("symbol"),
                    "outcome": trade_map.get("outcome"),
                    "entry_date": trade_map.get("entry_date"),
                    "exit_date": trade_map.get("exit_date"),
                    "exit_reason": trade_map.get("exit_reason"),
                    "return_pct": _optional_float(trade_map.get("return_pct")),
                    "entry_checks": dict(entry_checks),
                    "environment": environment,
                    "profit_contribution": contribution,
                }
            )
        )
    return rows


def _profit_contribution(lifecycle: Mapping[str, Any]) -> dict[str, Any]:
    buy_gross = 0.0
    sell_gross = 0.0
    buy_commission = 0.0
    sell_commission = 0.0
    buy_quantity = 0.0
    sell_quantity = 0.0
    completed_buy_count = 0
    completed_sell_count = 0

    for event in _as_sequence(lifecycle.get("events")):
        for execution in _as_sequence(_as_mapping(event).get("executions")):
            execution_map = _as_mapping(execution)
            if str(execution_map.get("event_type", "")).lower() != "completed":
                continue
            side = str(execution_map.get("side", "")).lower()
            gross_value = _execution_gross_value(execution_map)
            if gross_value is None:
                continue
            quantity = _optional_float(execution_map.get("executed_quantity")) or 0.0
            commission = _optional_float(execution_map.get("commission")) or 0.0
            if side == "buy":
                buy_gross += gross_value
                buy_commission += commission
                buy_quantity += quantity
                completed_buy_count += 1
            elif side == "sell":
                sell_gross += gross_value
                sell_commission += commission
                sell_quantity += quantity
                completed_sell_count += 1

    contribution_available = buy_gross > 0 and sell_gross > 0
    gross_pnl = sell_gross - buy_gross if contribution_available else None
    net_pnl = (sell_gross - sell_commission) - (buy_gross + buy_commission) if contribution_available else None
    total_commission = buy_commission + sell_commission if (completed_buy_count or completed_sell_count) else None
    return _drop_empty(
        {
            "contribution_available": contribution_available,
            "entry_gross_value": buy_gross if buy_gross > 0 else None,
            "exit_gross_value": sell_gross if sell_gross > 0 else None,
            "entry_commission": buy_commission if completed_buy_count else None,
            "exit_commission": sell_commission if completed_sell_count else None,
            "total_commission": total_commission,
            "gross_pnl": gross_pnl,
            "net_pnl": net_pnl,
            "return_on_entry_value": (net_pnl / buy_gross) if net_pnl is not None and buy_gross > 0 else None,
            "entry_quantity": buy_quantity if buy_quantity > 0 else None,
            "exit_quantity": sell_quantity if sell_quantity > 0 else None,
            "completed_buy_count": completed_buy_count,
            "completed_sell_count": completed_sell_count,
        }
    )


def _execution_gross_value(execution: Mapping[str, Any]) -> float | None:
    gross_value = _optional_float(execution.get("gross_value"))
    if gross_value is not None:
        return abs(gross_value)
    quantity = _optional_float(execution.get("executed_quantity"))
    price = _optional_float(execution.get("executed_price"))
    if quantity is None or price is None:
        return None
    return abs(quantity * price)


def _single_factor_summaries(
    trades: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for field in fields:
        buckets: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        values: dict[str, Any] = {}
        for trade in trades:
            environment = _as_mapping(trade.get("environment"))
            if field not in environment:
                continue
            value = environment[field]
            value_key = _stable_value_key(value)
            values[value_key] = value
            buckets[value_key].append(trade)
        for value_key, items in buckets.items():
            summary = _stats(items)
            summary.update(
                {
                    "summary_kind": "single_factor",
                    "field": field,
                    "field_label_zh": _factor_label(field),
                    "value": _jsonable_value(values[value_key]),
                    "value_label_zh": _value_label(values[value_key]),
                    "label_zh": f"{_factor_label(field)}={_value_label(values[value_key])}",
                }
            )
            summaries.append(summary)
    return sorted(
        summaries,
        key=lambda item: (
            str(item.get("field")),
            str(item.get("value")),
        ),
    )


def _combination_summaries(
    trades: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
) -> list[dict[str, Any]]:
    buckets: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    values_by_key: dict[str, dict[str, Any]] = {}
    for trade in trades:
        environment = _as_mapping(trade.get("environment"))
        if not all(field in environment for field in fields):
            continue
        values = {field: environment[field] for field in fields}
        key = _stable_value_key(values)
        values_by_key[key] = values
        buckets[key].append(trade)

    summaries = []
    for key, items in buckets.items():
        values = values_by_key[key]
        summary = _stats(items)
        summary.update(
            {
                "summary_kind": "combination",
                "fields": _jsonable_value(values),
                "profile_key": "|".join(f"{field}={_stable_value_key(values[field])}" for field in fields),
                "label_zh": _format_environment(values),
            }
        )
        summaries.append(summary)
    return sorted(
        summaries,
        key=lambda item: (
            -(item.get("net_pnl") if item.get("net_pnl") is not None else float("-inf")),
            -int(item.get("sample_count", 0)),
            str(item.get("profile_key")),
        ),
    )


def _stats(trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    returns = [
        value
        for trade in trades
        if (value := _optional_float(trade.get("return_pct"))) is not None
    ]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value <= 0]
    exit_reasons = Counter(str(trade.get("exit_reason")) for trade in trades if trade.get("exit_reason") is not None)

    financials = [
        _as_mapping(trade.get("profit_contribution"))
        for trade in trades
        if _as_mapping(trade.get("profit_contribution")).get("contribution_available") is True
    ]
    entry_values = [_optional_float(item.get("entry_gross_value")) or 0.0 for item in financials]
    exit_values = [_optional_float(item.get("exit_gross_value")) or 0.0 for item in financials]
    gross_pnls = [_optional_float(item.get("gross_pnl")) or 0.0 for item in financials]
    net_pnls = [_optional_float(item.get("net_pnl")) or 0.0 for item in financials]
    commissions = [_optional_float(item.get("total_commission")) or 0.0 for item in financials]
    positive_net = [value for value in net_pnls if value > 0]
    negative_net = [value for value in net_pnls if value < 0]
    total_entry_value = sum(entry_values)
    total_net_pnl = sum(net_pnls)

    return _drop_empty(
        {
            "sample_count": len(trades),
            "return_sample_count": len(returns),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": (len(wins) / len(returns)) if returns else None,
            "average_return_pct": _average(returns),
            "sum_return_pct": sum(returns) if returns else None,
            "average_win_return_pct": _average(wins),
            "average_loss_return_pct": _average(losses),
            "financial_trade_count": len(financials),
            "total_entry_value": total_entry_value if financials else None,
            "total_exit_value": sum(exit_values) if financials else None,
            "gross_pnl": sum(gross_pnls) if financials else None,
            "net_pnl": total_net_pnl if financials else None,
            "total_commission": sum(commissions) if financials else None,
            "return_on_entry_value": (total_net_pnl / total_entry_value) if total_entry_value > 0 else None,
            "pnl_win_count": len(positive_net),
            "pnl_loss_count": len(negative_net),
            "pnl_win_rate": (len(positive_net) / len(net_pnls)) if net_pnls else None,
            "profit_factor": (
                sum(positive_net) / abs(sum(negative_net))
                if positive_net and negative_net and sum(negative_net) != 0
                else None
            ),
            "stop_loss_count": exit_reasons.get("FIXED_5_PERCENT_STOP", 0),
            "take_profit_count": exit_reasons.get("KDJ_J_ABOVE_100", 0),
            "exit_reason_counts": [
                {"code": code, "count": count}
                for code, count in sorted(exit_reasons.items(), key=lambda item: (-item[1], item[0]))
            ],
            "trade_indexes": [trade.get("trade_index") for trade in trades if trade.get("trade_index") is not None],
        }
    )


def _best_environments(
    *,
    single_factor_summaries: Sequence[Mapping[str, Any]],
    combination_summaries: Sequence[Mapping[str, Any]],
    min_sample_count: int,
) -> dict[str, Any]:
    candidates = [
        _as_mapping(summary)
        for summary in (*single_factor_summaries, *combination_summaries)
        if int(_as_mapping(summary).get("sample_count", 0)) >= min_sample_count
    ]
    return _drop_empty(
        {
            "best_by_net_pnl": _compact_candidate(
                _best(candidates, key="net_pnl", require_financial=True)
            ),
            "best_by_return_on_entry_value": _compact_candidate(
                _best(candidates, key="return_on_entry_value", require_financial=True)
            ),
            "best_by_win_rate": _compact_candidate(_best(candidates, key="win_rate")),
            "worst_by_net_pnl": _compact_candidate(
                _best(candidates, key="net_pnl", require_financial=True, reverse=False)
            ),
        }
    )


def _sample_warnings(
    *,
    single_factor_summaries: Sequence[Mapping[str, Any]],
    combination_summaries: Sequence[Mapping[str, Any]],
    min_sample_count: int,
) -> dict[str, Any]:
    low_single = [
        _as_mapping(summary)
        for summary in single_factor_summaries
        if int(_as_mapping(summary).get("sample_count", 0)) < min_sample_count
    ]
    low_combinations = [
        _as_mapping(summary)
        for summary in combination_summaries
        if int(_as_mapping(summary).get("sample_count", 0)) < min_sample_count
    ]
    low_candidates = sorted(
        (*low_single, *low_combinations),
        key=lambda item: (
            abs(float(item.get("net_pnl") or 0.0)),
            abs(float(item.get("return_on_entry_value") or 0.0)),
            int(item.get("sample_count", 0)),
        ),
        reverse=True,
    )
    return {
        "min_sample_count": min_sample_count,
        "low_sample_single_factor_count": len(low_single),
        "low_sample_combination_count": len(low_combinations),
        "low_sample_candidates": [_compact_candidate(item) for item in low_candidates[:20]],
        "message_zh": "样本数低于阈值的分组只能作为复盘线索，不能作为稳定策略环境结论。",
    }


def _best(
    candidates: Sequence[Mapping[str, Any]],
    *,
    key: str,
    require_financial: bool = False,
    reverse: bool = True,
) -> Mapping[str, Any] | None:
    filtered = [
        candidate
        for candidate in candidates
        if candidate.get(key) is not None
        and (not require_financial or int(candidate.get("financial_trade_count", 0)) > 0)
    ]
    if not filtered:
        return None
    return sorted(
        filtered,
        key=lambda item: (
            float(item.get(key)),
            int(item.get("sample_count", 0)),
            float(item.get("average_return_pct") or 0.0),
        ),
        reverse=reverse,
    )[0]


def _compact_candidate(summary: Mapping[str, Any] | None) -> dict[str, Any]:
    if summary is None:
        return {}
    return _drop_empty(
        {
            "summary_kind": summary.get("summary_kind"),
            "field": summary.get("field"),
            "value": summary.get("value"),
            "fields": summary.get("fields"),
            "label_zh": summary.get("label_zh"),
            "sample_count": summary.get("sample_count"),
            "win_rate": summary.get("win_rate"),
            "average_return_pct": summary.get("average_return_pct"),
            "net_pnl": summary.get("net_pnl"),
            "return_on_entry_value": summary.get("return_on_entry_value"),
            "trade_indexes": summary.get("trade_indexes"),
        }
    )


def _trade_contributions(trades: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for trade in trades:
        contribution = _as_mapping(trade.get("profit_contribution"))
        rows.append(
            _drop_empty(
                {
                    "trade_index": trade.get("trade_index"),
                    "symbol": trade.get("symbol"),
                    "entry_date": trade.get("entry_date"),
                    "exit_date": trade.get("exit_date"),
                    "outcome": trade.get("outcome"),
                    "exit_reason": trade.get("exit_reason"),
                    "return_pct": trade.get("return_pct"),
                    "environment": trade.get("environment"),
                    "contribution_available": contribution.get("contribution_available"),
                    "entry_gross_value": contribution.get("entry_gross_value"),
                    "exit_gross_value": contribution.get("exit_gross_value"),
                    "gross_pnl": contribution.get("gross_pnl"),
                    "net_pnl": contribution.get("net_pnl"),
                    "total_commission": contribution.get("total_commission"),
                    "return_on_entry_value": contribution.get("return_on_entry_value"),
                    "completed_buy_count": contribution.get("completed_buy_count"),
                    "completed_sell_count": contribution.get("completed_sell_count"),
                }
            )
        )
    return sorted(
        rows,
        key=lambda row: (
            -(row.get("net_pnl") if row.get("net_pnl") is not None else float("-inf")),
            int(row.get("trade_index", 0)),
        ),
    )


def _summary_row(summary: Mapping[str, Any], *, include_field: bool) -> str:
    cells = []
    if include_field:
        cells.extend(
            [
                f"`{summary.get('field')}`",
                _escape_cell(summary.get("value_label_zh")),
            ]
        )
    else:
        cells.append(_escape_cell(summary.get("label_zh")))
    cells.extend(
        [
            str(summary.get("sample_count")),
            _format_optional_percent(summary.get("win_rate")),
            _format_optional_percent(summary.get("average_return_pct")),
            _format_optional_money(summary.get("net_pnl")),
            _format_optional_percent(summary.get("return_on_entry_value")),
            str(summary.get("stop_loss_count", 0)),
            str(summary.get("take_profit_count", 0)),
            _format_indexes(summary.get("trade_indexes")),
        ]
    )
    return "| " + " | ".join(cells) + " |"


def _format_environment(environment: Any) -> str:
    environment_map = _as_mapping(environment)
    if not environment_map:
        return "-"
    return "；".join(
        f"{_factor_label(field)}={_value_label(value)}"
        for field, value in sorted(environment_map.items())
    )


def _factor_label(key: str) -> str:
    declaration = _ATTRIBUTION_DECLARATIONS.get(key)
    if declaration is not None:
        return declaration.label_zh
    return {
        "kdj_j_below_threshold": "KDJ J 低于阈值",
        "trade.outcome": "交易结果",
        "trade.exit_reason": "退出原因",
    }.get(key, key)


def _value_label(value: Any) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    return {
        "true": "是",
        "false": "否",
        "win": "盈利",
        "loss": "亏损",
        "flat": "持平",
    }.get(str(value), str(value))


def _summary_kind_label(value: Any) -> str:
    return {
        "single_factor": "单因子",
        "combination": "组合",
    }.get(str(value), str(value))


def _outcome_label(value: Any) -> str:
    return {
        "win": "盈利",
        "loss": "亏损",
        "flat": "持平",
    }.get(str(value), str(value))


def _format_indexes(value: Any, *, limit: int = 20) -> str:
    indexes = _as_sequence(value)
    if not indexes:
        return "-"
    suffix = "..." if len(indexes) > limit else ""
    return ", ".join(str(index) for index in indexes[:limit]) + suffix


def _format_optional_percent(value: Any) -> str:
    number = _optional_float(value)
    if number is None:
        return "-"
    return f"{number * 100:.2f}%"


def _format_optional_money(value: Any) -> str:
    number = _optional_float(value)
    if number is None:
        return "-"
    return f"{number:,.2f}"


def _escape_cell(value: Any) -> str:
    return str(value).replace("|", "/") if value is not None else "-"


def _average(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _load_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _run_id(run_path: Path, run_plan: Mapping[str, Any]) -> str:
    return str(_as_mapping(run_plan.get("run")).get("id", run_path.name))


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _as_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, (list, tuple)):
        return value
    return ()


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except ValueError:
        return None


def _stable_value_key(value: Any) -> str:
    return json.dumps(_jsonable_value(value), ensure_ascii=False, sort_keys=True)


def _jsonable_value(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_jsonable_value(item) for item in value]
    if isinstance(value, list):
        return [_jsonable_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _jsonable_value(item) for key, item in value.items()}
    return value


def _drop_empty(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in source.items()
        if value is not None and value != {} and value != []
    }


def _to_pretty_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
