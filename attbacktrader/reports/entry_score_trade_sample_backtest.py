"""Fixed entry-score trade-sample backtest from persisted entry-factor evidence."""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ENTRY_SCORE_TRADE_SAMPLE_BACKTEST_SCHEMA = "attbacktrader.entry_score_trade_sample_backtest.v1"


DEFAULT_ENTRY_SCORE_SCORING_CONFIG: dict[str, Any] = {
    "name": "baoma_v1_factor_score_v1",
    "description_zh": "强趋势阴线回踩因子打分框架：趋势核心加分，形态/放量确认加分，弱动量、行业/市场周线极端、放量冲高和高风险组合扣分。",
    "factor_weights": {
        "entry.price_position.ma60_atr_multiple_bucket": {
            "above_ma60_gt_2atr": 2.0,
            "above_ma60_1_2atr": 1.0,
            "above_ma60_0_1atr": -1.0,
            "below_ma60_0_1atr": -2.0,
        },
        "entry.signal_strength.dif_dea_distance_bucket": {
            "gte_0p6pct": 2.0,
            "lte_0": -3.0,
            "0_0p1pct": -2.0,
            "0p1_0p3pct": -1.0,
        },
        "entry.signal_strength.macd_bar_bucket": {
            "gte_0p6pct": 1.0,
            "lte_0": -3.0,
            "0p1_0p3pct": -1.5,
            "0p3_0p6pct": -1.0,
        },
        "entry.signal_strength.dea_value_bucket": {
            "gte_0p6pct": 1.0,
            "0_0p1pct": -2.0,
        },
        "entry.momentum.symbol_vs_hs300_return_20d_bucket": {
            "outperform_gt_10pct": 1.0,
        },
        "entry.momentum.symbol_vs_industry_return_20d_bucket": {
            "outperform_gt_10pct": 1.0,
            "outperform_0_3pct": -0.5,
        },
        "entry.price_position.near_high_60d_bucket": {
            "near_high": 1.5,
        },
        "entry.signal_strength.signal_candle_body_bucket": {
            "gte_5pct": 2.0,
            "3_5pct": 1.0,
            "lt_1pct": -0.5,
        },
        "entry.signal_strength.signal_upper_lower_shadow_bucket": {
            "long_lower_shadow": 1.0,
            "both_long_shadows": 1.0,
            "short_shadows": -1.0,
        },
        "entry.liquidity.amount_5d_vs_20d_bucket": {
            "gte_2x": 1.0,
            "1p6_2x": 0.5,
            "lt_0p8x": -1.0,
        },
        "entry.signal_strength.ma60_slope_20d_bucket": {
            "flat_0_2pct": 1.0,
            "down_gt_5pct": -1.0,
        },
        "entry.volatility.atr_20d_bucket": {
            "p60_p80": 0.5,
            "p0_p20": -0.5,
        },
        "entry.momentum.return_20d_bucket": {
            "p0_p20": -2.0,
            "p80_p100": 0.5,
        },
        "entry.momentum.return_60d_bucket": {
            "p0_p20": -2.0,
            "p80_p100": 0.5,
        },
        "entry.signal_strength.dea_waterline_age_trading_days_bucket": {
            "day_1_3": 0.5,
            "day_4_7": -0.5,
            "day_8_14": -1.5,
        },
        "entry.stop_fit.fixed_atr_multiple_bucket": {
            "2_3atr": -1.0,
        },
        "entry.volatility.symbol_atr_to_industry_median_bucket": {
            "1p2_1p6x": -0.5,
        },
        "entry.weekly.symbol_kdj_state": {
            "overheated": 1.0,
            "strong": 0.5,
            "oversold": -0.5,
        },
        "industry.weekly.kdj_state": {
            "recovering": 0.5,
            "oversold": -2.0,
            "overheated": -0.5,
        },
        "market.hs300.weekly.kdj_state": {
            "oversold": -1.5,
            "strong": 0.5,
        },
        "market.csi500.weekly.kdj_state": {
            "strong": -2.0,
            "overheated": 0.5,
        },
        "market.csi500.trend_state": {
            "bearish": -1.0,
        },
        "market.objective.entry_stage": {
            "bearish": 1.0,
            "bullish": -0.5,
        },
    },
    "interaction_weights": [
        {
            "name": "贴MA60但MACD强仍弱",
            "fields": {
                "entry.price_position.ma60_atr_multiple_bucket": "above_ma60_0_1atr",
                "entry.signal_strength.macd_bar_bucket": "gte_0p6pct",
            },
            "weight": -1.0,
        },
        {
            "name": "强趋势共振",
            "fields": {
                "entry.price_position.ma60_atr_multiple_bucket": "above_ma60_gt_2atr",
                "entry.signal_strength.dif_dea_distance_bucket": "gte_0p6pct",
                "entry.signal_strength.macd_bar_bucket": "gte_0p6pct",
            },
            "weight": 1.0,
        },
        {
            "name": "强趋势近高",
            "fields": {
                "entry.price_position.near_high_60d_bucket": "near_high",
                "entry.signal_strength.dif_dea_distance_bucket": "gte_0p6pct",
                "entry.signal_strength.macd_bar_bucket": "gte_0p6pct",
            },
            "weight": 1.0,
        },
        {
            "name": "弱20日且弱60日",
            "fields": {
                "entry.momentum.return_20d_bucket": "p0_p20",
                "entry.momentum.return_60d_bucket": "p0_p20",
            },
            "weight": -5.0,
        },
        {
            "name": "行业过热且中证500周线强",
            "fields": {
                "industry.weekly.kdj_state": "overheated",
                "market.csi500.weekly.kdj_state": "strong",
            },
            "weight": -5.0,
        },
        {
            "name": "中证500周线强且个股波动偏高",
            "fields": {
                "market.csi500.weekly.kdj_state": "strong",
                "entry.volatility.symbol_atr_to_industry_median_bucket": "1p2_1p6x",
            },
            "weight": -5.0,
        },
        {
            "name": "行业超卖且个股波动偏高",
            "fields": {
                "industry.weekly.kdj_state": "oversold",
                "entry.volatility.symbol_atr_to_industry_median_bucket": "1p2_1p6x",
            },
            "weight": -4.0,
        },
        {
            "name": "中证500周线强且固定止损适配差",
            "fields": {
                "market.csi500.weekly.kdj_state": "strong",
                "entry.stop_fit.fixed_atr_multiple_bucket": "2_3atr",
            },
            "weight": -4.0,
        },
        {
            "name": "行业强但DEA水上过久",
            "fields": {
                "industry.weekly.kdj_state": "strong",
                "entry.signal_strength.dea_waterline_age_trading_days_bucket": "day_8_14",
            },
            "weight": -3.0,
        },
        {
            "name": "个股周线过热叠加行业过热和中证500强",
            "fields": {
                "entry.weekly.symbol_kdj_state": "overheated",
                "industry.weekly.kdj_state": "overheated",
                "market.csi500.weekly.kdj_state": "strong",
            },
            "weight": -4.0,
        },
    ],
}


DEFAULT_THRESHOLD_SWEEP: tuple[float, ...] = (-3, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8)


def build_entry_score_trade_sample_backtest(
    environment_fit: Mapping[str, Any] | str | Path,
    *,
    year: int = 2024,
    min_entry_score: float = 4.0,
    scoring_config: Mapping[str, Any] | None = None,
    threshold_sweep: Sequence[float] = DEFAULT_THRESHOLD_SWEEP,
    sample_limit: int = 30,
) -> dict[str, Any]:
    """Score completed trades for one year and report score-gated trade-sample results."""

    if year < 1900 or year > 3000:
        raise ValueError("year must be a four-digit year")
    if sample_limit <= 0:
        raise ValueError("sample_limit must be positive")
    config = _normalize_scoring_config(scoring_config or DEFAULT_ENTRY_SCORE_SCORING_CONFIG)
    payload = _load_json_like(environment_fit)
    all_trades = [
        _as_mapping(row)
        for row in _as_sequence(payload.get("trade_contributions"))
        if _as_mapping(row.get("environment"))
    ]
    if not all_trades:
        raise ValueError("environment_fit must include non-empty trade_contributions with environment fields")

    year_prefix = f"{year:04d}-"
    year_trades = [trade for trade in all_trades if str(trade.get("entry_date", "")).startswith(year_prefix)]
    if not year_trades:
        raise ValueError(f"environment_fit has no trade_contributions with entry_date in {year}")

    scored_trades = [_score_trade_sample(trade, config) for trade in year_trades]
    selected = [row for row in scored_trades if float(row["entry_score"]) >= min_entry_score]
    blocked = [row for row in scored_trades if float(row["entry_score"]) < min_entry_score]
    ranked = sorted(scored_trades, key=_ranked_trade_key)

    return {
        "schema": ENTRY_SCORE_TRADE_SAMPLE_BACKTEST_SCHEMA,
        "source_artifacts": {
            "environment_fit": _source_path(environment_fit),
        },
        "run_id": payload.get("run_id"),
        "year": year,
        "scope": {
            "kind": "completed_trade_sample_score_gate",
            "holding_cap_policy": "none_in_trade_sample",
            "ranking_policy": "entry candidates are sorted by entry_score descending for reporting; with no holding cap all score-passing completed trades are included",
            "caveat_zh": "这是已完成交易样本上的打分过滤验证，不是完整候选级现金组合回测；compact signal_audit 无法重建未成交候选。",
        },
        "score_gate": {
            "min_entry_score": min_entry_score,
        },
        "scoring_config": config,
        "summary": {
            "all_year_trades": _stats(scored_trades),
            "score_passed": _stats(selected),
            "score_blocked": _stats(blocked),
            "delta_vs_all": _delta(_stats(selected), _stats(scored_trades)),
        },
        "funnel": {
            "raw_completed_trades": len(scored_trades),
            "score_passed_trades": len(selected),
            "score_blocked_trades": len(blocked),
            "score_pass_rate": len(selected) / len(scored_trades),
            "score_blocked_losses": sum(1 for row in blocked if (_optional_float(row.get("return_pct")) or 0.0) <= 0),
            "score_blocked_winners": sum(1 for row in blocked if (_optional_float(row.get("return_pct")) or 0.0) > 0),
        },
        "threshold_sweep": _threshold_sweep(scored_trades, threshold_sweep),
        "score_distribution": _score_distribution(scored_trades),
        "by_month": _by_month(selected),
        "samples": {
            "top_ranked_trades": _trade_samples(ranked, limit=sample_limit),
            "worst_score_passed_trades": _trade_samples(
                sorted(selected, key=lambda row: _optional_float(row.get("return_pct")) or math.inf),
                limit=sample_limit,
            ),
            "best_score_blocked_winners": _trade_samples(
                sorted(
                    [row for row in blocked if (_optional_float(row.get("return_pct")) or 0.0) > 0],
                    key=lambda row: -(_optional_float(row.get("return_pct")) or -math.inf),
                ),
                limit=sample_limit,
            ),
        },
        "ranked_trades": _trade_samples(ranked, limit=len(ranked)),
        "ai_usage_rules": [
            "本报告只读取已落盘 completed-trade 归因证据，不重跑策略、不重新计算指标、不联网取数。",
            "score gate 是 completed-trade 样本过滤，不包含未成交候选、现金竞争、真实持仓上限和每日容量约束。",
            "无持仓上限在本报告中表示所有分数达标的已完成交易都被保留，不按现金或仓位容量拒单。",
            "按分数降序排序只用于候选优先级观察；真实组合收益仍需 full signal_audit 或 Decision Event Table 后再做 Scored Portfolio Backtest。",
        ],
    }


def render_entry_score_trade_sample_backtest_markdown_zh(report: Mapping[str, Any]) -> str:
    """Render a Chinese Markdown report for a fixed entry-score trade-sample backtest."""

    summary = _as_mapping(report.get("summary"))
    all_stats = _as_mapping(summary.get("all_year_trades"))
    selected = _as_mapping(summary.get("score_passed"))
    blocked = _as_mapping(summary.get("score_blocked"))
    delta = _as_mapping(summary.get("delta_vs_all"))
    funnel = _as_mapping(report.get("funnel"))
    score_gate = _as_mapping(report.get("score_gate"))
    scope = _as_mapping(report.get("scope"))

    lines = [
        "# 固定因子打分一年验证",
        "",
        "## 概览",
        "",
        "| 项目 | 值 |",
        "|---|---:|",
        f"| run_id | `{report.get('run_id')}` |",
        f"| 年份 | {report.get('year')} |",
        f"| 最低入场分数 | {_format_number(score_gate.get('min_entry_score'))} |",
        f"| 原始已完成交易数 | {funnel.get('raw_completed_trades')} |",
        f"| 分数达标交易数 | {funnel.get('score_passed_trades')} |",
        f"| 分数达标比例 | {_format_pct(funnel.get('score_pass_rate'))} |",
        "",
        "## 口径",
        "",
        f"- {scope.get('caveat_zh')}",
        "- `无持仓上限` 在这里表示所有分数达标的已完成交易都保留，不做现金容量拒单。",
        "- `按分数降序排序` 用于观察候选优先级；由于本轮无持仓上限，排序不改变保留集合。",
        "",
        "## 结果",
        "",
        "| 分组 | 样本数 | 平均收益 | 胜率 | 入场金额收益率 | 净PnL | 最大盈利 | 最大亏损 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        _summary_row("原始2024", all_stats),
        _summary_row("分数达标", selected),
        _summary_row("分数未达标", blocked),
        "",
        "## 相对原始样本变化",
        "",
        "| 指标 | 变化 |",
        "|---|---:|",
        f"| 平均收益 | {_format_pp(delta.get('average_return_pct'))} |",
        f"| 胜率 | {_format_pp(delta.get('win_rate'))} |",
        f"| 入场金额收益率 | {_format_pp(delta.get('return_on_entry_value'))} |",
        f"| 样本数变化 | {delta.get('sample_count')} |",
        "",
        "## 阈值扫描",
        "",
        "| 最低分 | 样本数 | 平均收益 | 胜率 | 入场金额收益率 | 净PnL | 最大亏损 |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in _as_sequence(report.get("threshold_sweep")):
        stats = _as_mapping(row.get("stats"))
        lines.append(
            f"| {_format_number(row.get('min_entry_score'))} | {stats.get('sample_count')} | "
            f"{_format_pct(stats.get('average_return_pct'))} | {_format_pct(stats.get('win_rate'))} | "
            f"{_format_pct(stats.get('return_on_entry_value'))} | {_format_money(stats.get('net_pnl'))} | "
            f"{_format_pct(stats.get('min_return_pct'))} |"
        )
    lines.extend(
        [
            "",
            "## 分数达标月度",
            "",
            "| 月份 | 样本数 | 平均收益 | 胜率 | 入场金额收益率 | 净PnL |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in _as_sequence(report.get("by_month")):
        stats = _as_mapping(row.get("stats"))
        lines.append(
            f"| {row.get('month')} | {stats.get('sample_count')} | {_format_pct(stats.get('average_return_pct'))} | "
            f"{_format_pct(stats.get('win_rate'))} | {_format_pct(stats.get('return_on_entry_value'))} | "
            f"{_format_money(stats.get('net_pnl'))} |"
        )
    lines.extend(_sample_section("最高分交易样本", _as_sequence(_as_mapping(report.get("samples")).get("top_ranked_trades"))))
    lines.extend(_sample_section("分数达标后的最差交易", _as_sequence(_as_mapping(report.get("samples")).get("worst_score_passed_trades"))))
    lines.extend(_sample_section("被分数挡掉的最佳盈利交易", _as_sequence(_as_mapping(report.get("samples")).get("best_score_blocked_winners"))))
    return "\n".join(lines) + "\n"


def write_entry_score_trade_sample_backtest(
    report: Mapping[str, Any],
    *,
    output_dir: str | Path,
    artifact_stem: str = "entry_score_trade_sample_backtest",
) -> tuple[Path, Path, dict[str, Any]]:
    """Write JSON and Chinese Markdown artifacts."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    payload = _jsonable(dict(report))
    json_path = output_path / f"{artifact_stem}.json"
    markdown_path = output_path / f"{artifact_stem}.zh.md"
    payload["artifacts"] = {
        "backtest_json": str(json_path),
        "backtest_markdown_zh": str(markdown_path),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_entry_score_trade_sample_backtest_markdown_zh(payload), encoding="utf-8")
    return json_path, markdown_path, payload


def safe_entry_score_trade_sample_backtest_dir_name(source_path: str | Path, *, year: int) -> str:
    """Build a stable report directory name from a source artifact path."""

    path = Path(source_path)
    source_name = path.parent.name if path.name.startswith("environment_fit") else path.stem
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", source_name).strip("-")
    return f"entry-score-trade-sample-backtest-{safe or 'environment-fit'}-{year}"


def _normalize_scoring_config(config: Mapping[str, Any]) -> dict[str, Any]:
    factor_weights: dict[str, dict[str, float]] = {}
    for field, weights in _as_mapping(config.get("factor_weights")).items():
        normalized_weights: dict[str, float] = {}
        for value, weight in _as_mapping(weights).items():
            normalized_weights[str(value)] = _required_number(weight, f"factor weight {field}={value}")
        factor_weights[str(field)] = normalized_weights
    if not factor_weights:
        raise ValueError("scoring_config.factor_weights cannot be empty")

    interactions: list[dict[str, Any]] = []
    for index, item in enumerate(_as_sequence(config.get("interaction_weights"))):
        interaction = _as_mapping(item)
        fields = {str(key): value for key, value in _as_mapping(interaction.get("fields")).items()}
        if not fields:
            raise ValueError(f"interaction_weights[{index}].fields cannot be empty")
        interactions.append(
            {
                "name": str(interaction.get("name") or f"interaction_{index}"),
                "fields": fields,
                "weight": _required_number(interaction.get("weight"), f"interaction weight {index}"),
            }
        )
    return {
        "name": str(config.get("name") or "entry_score"),
        "description_zh": str(config.get("description_zh") or ""),
        "factor_weights": factor_weights,
        "interaction_weights": interactions,
    }


def _score_trade_sample(trade: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    environment = _as_mapping(trade.get("environment"))
    score = 0.0
    factor_contributions: list[dict[str, Any]] = []
    for field, weights in _as_mapping(config.get("factor_weights")).items():
        value = environment.get(str(field))
        weight = _optional_float(_as_mapping(weights).get(str(value))) or 0.0
        if weight == 0.0:
            continue
        score += weight
        factor_contributions.append({"field": str(field), "value": value, "weight": weight})

    interaction_contributions: list[dict[str, Any]] = []
    for item in _as_sequence(config.get("interaction_weights")):
        interaction = _as_mapping(item)
        fields = _as_mapping(interaction.get("fields"))
        if all(environment.get(str(field)) == expected for field, expected in fields.items()):
            weight = _optional_float(interaction.get("weight")) or 0.0
            score += weight
            interaction_contributions.append(
                {
                    "name": str(interaction.get("name") or ""),
                    "fields": dict(fields),
                    "weight": weight,
                }
            )

    return {
        "trade_index": trade.get("trade_index"),
        "symbol": str(trade.get("symbol")),
        "entry_date": str(trade.get("entry_date")),
        "exit_date": str(trade.get("exit_date")),
        "exit_reason": trade.get("exit_reason"),
        "return_pct": _optional_float(trade.get("return_pct")) or 0.0,
        "entry_gross_value": _optional_float(trade.get("entry_gross_value")) or 0.0,
        "exit_gross_value": _optional_float(trade.get("exit_gross_value")) or 0.0,
        "net_pnl": _optional_float(trade.get("net_pnl")) or 0.0,
        "return_on_entry_value": _optional_float(trade.get("return_on_entry_value")) or 0.0,
        "entry_score": score,
        "environment": _jsonable(dict(environment)),
        "score_contributions": {
            "factor_weights": factor_contributions,
            "interaction_weights": interaction_contributions,
        },
    }


def _stats(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    values = [_optional_float(row.get("return_pct")) or 0.0 for row in rows]
    net_pnls = [_optional_float(row.get("net_pnl")) or 0.0 for row in rows]
    entry_values = [_optional_float(row.get("entry_gross_value")) or 0.0 for row in rows]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value <= 0]
    profit_sum = sum(pnl for pnl in net_pnls if pnl > 0)
    loss_sum = sum(pnl for pnl in net_pnls if pnl < 0)
    total_entry = sum(entry_values)
    return {
        "sample_count": len(rows),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": len(wins) / len(rows) if rows else 0.0,
        "average_return_pct": sum(values) / len(values) if values else 0.0,
        "median_return_pct": _median(values),
        "max_return_pct": max(values) if values else 0.0,
        "min_return_pct": min(values) if values else 0.0,
        "average_win_return_pct": sum(wins) / len(wins) if wins else 0.0,
        "average_loss_return_pct": sum(losses) / len(losses) if losses else 0.0,
        "total_entry_value": total_entry,
        "net_pnl": sum(net_pnls),
        "return_on_entry_value": sum(net_pnls) / total_entry if total_entry else 0.0,
        "profit_factor": profit_sum / abs(loss_sum) if loss_sum else None,
    }


def _delta(selected: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("average_return_pct", "win_rate", "return_on_entry_value", "profit_factor")
    return {
        "sample_count": int(selected.get("sample_count") or 0) - int(baseline.get("sample_count") or 0),
        **{key: _optional_float(selected.get(key)) - _optional_float(baseline.get(key)) for key in keys if _optional_float(selected.get(key)) is not None and _optional_float(baseline.get(key)) is not None},
        "net_pnl": (_optional_float(selected.get("net_pnl")) or 0.0) - (_optional_float(baseline.get("net_pnl")) or 0.0),
    }


def _threshold_sweep(rows: Sequence[Mapping[str, Any]], thresholds: Sequence[float]) -> list[dict[str, Any]]:
    sweep: list[dict[str, Any]] = []
    for threshold in thresholds:
        number = _required_number(threshold, "threshold")
        selected = [row for row in rows if (_optional_float(row.get("entry_score")) or 0.0) >= number]
        sweep.append({"min_entry_score": number, "stats": _stats(selected)})
    return sweep


def _score_distribution(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(_optional_float(row.get("entry_score")) or 0.0 for row in rows)
    return [{"entry_score": score, "count": count} for score, count in sorted(counts.items())]


def _by_month(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get("entry_date"))[:7]].append(row)
    return [{"month": month, "stats": _stats(items)} for month, items in sorted(groups.items())]


def _trade_samples(rows: Sequence[Mapping[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for row in list(rows)[:limit]:
        samples.append(
            {
                "trade_index": row.get("trade_index"),
                "symbol": row.get("symbol"),
                "entry_date": row.get("entry_date"),
                "exit_date": row.get("exit_date"),
                "entry_score": row.get("entry_score"),
                "return_pct": row.get("return_pct"),
                "net_pnl": row.get("net_pnl"),
                "exit_reason": row.get("exit_reason"),
                "score_contributions": _jsonable(_as_mapping(row.get("score_contributions"))),
            }
        )
    return samples


def _ranked_trade_key(row: Mapping[str, Any]) -> tuple[float, str, str, int]:
    return (
        -(_optional_float(row.get("entry_score")) or 0.0),
        str(row.get("entry_date")),
        str(row.get("symbol")),
        int(_optional_float(row.get("trade_index")) or 0),
    )


def _summary_row(label: str, stats: Mapping[str, Any]) -> str:
    return (
        f"| {label} | {stats.get('sample_count')} | {_format_pct(stats.get('average_return_pct'))} | "
        f"{_format_pct(stats.get('win_rate'))} | {_format_pct(stats.get('return_on_entry_value'))} | "
        f"{_format_money(stats.get('net_pnl'))} | {_format_pct(stats.get('max_return_pct'))} | "
        f"{_format_pct(stats.get('min_return_pct'))} |"
    )


def _sample_section(title: str, rows: Sequence[Mapping[str, Any]]) -> list[str]:
    lines = [
        "",
        f"## {title}",
        "",
        "| trade_index | symbol | entry | exit | score | return | netPnL |",
        "|---:|---|---|---|---:|---:|---:|",
    ]
    if not rows:
        lines.append("| - | - | - | - | - | - | - |")
        return lines
    for row in rows:
        lines.append(
            f"| {row.get('trade_index')} | `{row.get('symbol')}` | {row.get('entry_date')} | {row.get('exit_date')} | "
            f"{_format_number(row.get('entry_score'))} | {_format_pct(row.get('return_pct'))} | {_format_money(row.get('net_pnl'))} |"
        )
    return lines


def _load_json_like(value: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    path = Path(value)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return payload


def _source_path(value: Mapping[str, Any] | str | Path) -> str | None:
    if isinstance(value, Mapping):
        return None
    return str(value)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or value is None:
        return ()
    return value if isinstance(value, Sequence) else ()


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _required_number(value: Any, name: str) -> float:
    number = _optional_float(value)
    if number is None:
        raise ValueError(f"{name} must be numeric")
    return number


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _format_pct(value: Any) -> str:
    number = _optional_float(value)
    return "-" if number is None else f"{number * 100:.2f}%"


def _format_pp(value: Any) -> str:
    number = _optional_float(value)
    return "-" if number is None else f"{number * 100:+.2f}pp"


def _format_money(value: Any) -> str:
    number = _optional_float(value)
    return "-" if number is None else f"{number:,.0f}"


def _format_number(value: Any) -> str:
    number = _optional_float(value)
    if number is None:
        return "-"
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value
