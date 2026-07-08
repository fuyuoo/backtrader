"""Diagnose 2022-2025 failure and test simple regime gates.

The input is the walk-forward scored trade detail produced by
walk_forward_portfolio_validation.py. Gates are applied before daily ranking,
then the same lightweight portfolio proxy is reused.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

import pandas as pd

import walk_forward_portfolio_validation as wf


DEFAULT_WALK_FORWARD_DIR = Path("reports/walk-forward-portfolio-validation-hs300-only-2006-2025")
DEFAULT_OUTPUT_DIR = Path("reports/recent-regime-gate-analysis-hs300-only-2006-2025")

CORE_SCORE_COL = "wf_calibrated_total_score"
CORE_STRATEGY_ID = "wf_total"
CORE_STRATEGY_LABEL = "Walk-forward 总分"
INITIAL_CASH = 1_000_000.0

PORTFOLIO_CASES = (
    ("top1_hold20", "Top1 / MaxHold20", 1, 20),
    ("top3_hold10", "Top3 / MaxHold10", 3, 10),
)
PERIODS = (
    ("full", "2013-2025", None, None),
    ("pre_recent", "2015-2021", "2015-01-01", "2021-12-31"),
    ("recent", "2022-2025", "2022-01-01", "2025-12-31"),
)
DIAGNOSTIC_FIELDS = (
    ("soil_layer5_with_industry_v1", "土壤层-含行业"),
    ("soil_layer_no_industry_v2", "土壤层-HS300"),
    ("industry_soil_layer_v1", "行业土壤层"),
    ("hs300.ma_stack_state", "HS300 均线结构"),
    ("hs300.ma60_position", "HS300 MA60 位置"),
    ("hs300.daily_macd_zone", "HS300 日线 MACD 区域"),
    ("hs300.weekly_kdj_state", "HS300 周线 KDJ"),
    ("industry_ma_stack_state", "行业均线结构"),
    ("industry_ma60_position", "行业 MA60 位置"),
    ("industry_daily_macd_zone", "行业日线 MACD 区域"),
    ("entry.price_position.near_high_60d_bucket", "个股60日高点距离"),
    ("entry.price_position.signal_close_ma60_atr_multiple_bucket", "个股相对MA60 ATR位置"),
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    detail = _load_detail(Path(args.walk_forward_dir))
    gates = _gate_definitions()

    bucket_diagnostics = _bucket_diagnostics(detail)
    gate_metrics, selected_rows = _gate_portfolio_metrics(detail, gates, initial_cash=float(args.initial_cash))
    scorecard = _gate_scorecard(gate_metrics)
    yearly = _recent_yearly_metrics(detail, gates, initial_cash=float(args.initial_cash))

    bucket_path = output_dir / "recent_regime_bucket_diagnostics.csv"
    gate_path = output_dir / "recent_regime_gate_portfolio_metrics.csv"
    scorecard_path = output_dir / "recent_regime_gate_scorecard.csv"
    yearly_path = output_dir / "recent_regime_gate_yearly_metrics.csv"
    selected_path = output_dir / "recent_regime_gate_selected_trades.parquet"
    metadata_path = output_dir / "recent_regime_gate_metadata.json"
    markdown_path = output_dir / "recent_regime_gate_analysis.zh.md"

    bucket_diagnostics.to_csv(bucket_path, index=False, encoding="utf-8-sig")
    gate_metrics.to_csv(gate_path, index=False, encoding="utf-8-sig")
    scorecard.to_csv(scorecard_path, index=False, encoding="utf-8-sig")
    yearly.to_csv(yearly_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(selected_rows).to_parquet(selected_path, index=False)

    metadata = {
        "schema": "attbacktrader.recent_regime_gate_analysis.v1",
        "source_walk_forward_dir": str(args.walk_forward_dir),
        "score_col": CORE_SCORE_COL,
        "portfolio_cases": [
            {"case_id": case_id, "label_zh": label, "max_new_per_day": max_new, "max_holding_count": max_hold}
            for case_id, label, max_new, max_hold in PORTFOLIO_CASES
        ],
        "periods": [
            {"period_id": period_id, "label_zh": label, "start": start, "end": end}
            for period_id, label, start, end in PERIODS
        ],
        "risk_notes": [
            "这是代理组合 gate 实验，不是正式撮合回测。",
            "gate 定义是手工候选，用于缩小下一轮正式回测范围。",
            "本报告重点评估 2022-2025 改善，同时观察 2015-2021 是否被过度伤害。",
        ],
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(
        _render_markdown(
            bucket_diagnostics=bucket_diagnostics,
            gate_metrics=gate_metrics,
            scorecard=scorecard,
            yearly=yearly,
            artifacts={
                "bucket_diagnostics": bucket_path,
                "gate_portfolio_metrics": gate_path,
                "gate_scorecard": scorecard_path,
                "gate_yearly_metrics": yearly_path,
                "selected_trades": selected_path,
                "metadata": metadata_path,
            },
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "gate_count": int(len(gates)),
                "analysis_markdown": str(markdown_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze recent regime gates for 2022-2025 failure")
    parser.add_argument("--walk-forward-dir", default=str(DEFAULT_WALK_FORWARD_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--initial-cash", type=float, default=INITIAL_CASH)
    return parser.parse_args(argv)


def _load_detail(walk_forward_dir: Path) -> pd.DataFrame:
    path = walk_forward_dir / "walk_forward_scored_trade_detail.parquet"
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_parquet(path).copy()
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df["exit_date"] = pd.to_datetime(df["exit_date"])
    df["entry_year"] = df["entry_date"].dt.year
    df["return_pct"] = pd.to_numeric(df["return_pct"], errors="coerce")
    return df


def _gate_definitions() -> list[dict[str, Any]]:
    return [
        _gate("no_gate", "不加风险开关", lambda df: pd.Series(True, index=df.index), "reference"),
        _gate(
            "soil_with_industry_ge_8",
            "含行业土壤分 >= 8",
            lambda df: pd.to_numeric(df["soil_score_with_industry_v1"], errors="coerce") >= 8,
            "soil",
        ),
        _gate(
            "soil_with_industry_ge_12",
            "含行业土壤分 >= 12",
            lambda df: pd.to_numeric(df["soil_score_with_industry_v1"], errors="coerce") >= 12,
            "soil",
        ),
        _gate(
            "soil_layer_strong_only",
            "只做 strong/very strong 土壤",
            lambda df: df["soil_layer5_with_industry_v1"].isin(["strong_soil", "very_strong_soil"]),
            "soil",
        ),
        _gate(
            "soil_layer_very_strong_only",
            "只做 very strong 土壤",
            lambda df: df["soil_layer5_with_industry_v1"].eq("very_strong_soil"),
            "soil",
        ),
        _gate(
            "hs300_soil_ge_8",
            "HS300 土壤分 >= 8",
            lambda df: pd.to_numeric(df["hs300.index_soil_v2_score"], errors="coerce") >= 8,
            "market",
        ),
        _gate(
            "hs300_soil_ge_10",
            "HS300 土壤分 >= 10",
            lambda df: pd.to_numeric(df["hs300.index_soil_v2_score"], errors="coerce") >= 10,
            "market",
        ),
        _gate(
            "hs300_above_ma60",
            "HS300 在 MA60 上方",
            lambda df: df["hs300.ma60_position"].eq("above_ma60"),
            "market",
        ),
        _gate(
            "hs300_bullish_stack",
            "HS300 多头均线结构",
            lambda df: df["hs300.ma_stack_state"].eq("bullish_stack"),
            "market",
        ),
        _gate(
            "hs300_not_bearish_stack",
            "HS300 非空头均线结构",
            lambda df: ~df["hs300.ma_stack_state"].eq("bearish_stack"),
            "market",
        ),
        _gate(
            "hs300_red_macd",
            "HS300 MACD 红柱区",
            lambda df: df["hs300.daily_macd_zone"].astype(str).str.startswith("red_bar"),
            "market",
        ),
        _gate(
            "hs300_weekly_kdj_strong",
            "HS300 周线KDJ强势",
            lambda df: df["hs300.weekly_kdj_state"].eq("strong"),
            "market",
        ),
        _gate(
            "hs300_stack_not_mixed_below",
            "避开HS300混乱/MA60下方结构",
            lambda df: ~df["hs300.ma_stack_state"].isin(["mixed", "below_ma60"]),
            "market",
        ),
        _gate(
            "industry_strong_or_neutral",
            "行业土壤不弱",
            lambda df: df["industry_soil_layer_v1"].isin(["neutral_industry_soil", "strong_industry_soil"]),
            "industry",
        ),
        _gate(
            "industry_strong_only",
            "只做强行业土壤",
            lambda df: df["industry_soil_layer_v1"].eq("strong_industry_soil"),
            "industry",
        ),
        _gate(
            "industry_above_ma60",
            "行业在 MA60 上方",
            lambda df: df["industry_ma60_position"].eq("above_ma60"),
            "industry",
        ),
        _gate(
            "market_industry_both_above_ma60",
            "HS300和行业均在MA60上方",
            lambda df: df["hs300.ma60_position"].eq("above_ma60") & df["industry_ma60_position"].eq("above_ma60"),
            "combo",
        ),
        _gate(
            "market_not_bearish_and_industry_not_weak",
            "HS300非空头且行业不弱",
            lambda df: (~df["hs300.ma_stack_state"].eq("bearish_stack"))
            & df["industry_soil_layer_v1"].isin(["neutral_industry_soil", "strong_industry_soil"]),
            "combo",
        ),
        _gate(
            "soil_ge_8_and_hs300_above_ma60",
            "含行业土壤>=8且HS300在MA60上方",
            lambda df: (pd.to_numeric(df["soil_score_with_industry_v1"], errors="coerce") >= 8)
            & df["hs300.ma60_position"].eq("above_ma60"),
            "combo",
        ),
        _gate(
            "soil_ge_8_and_industry_above_ma60",
            "含行业土壤>=8且行业在MA60上方",
            lambda df: (pd.to_numeric(df["soil_score_with_industry_v1"], errors="coerce") >= 8)
            & df["industry_ma60_position"].eq("above_ma60"),
            "combo",
        ),
        _gate(
            "hs300_kdj_strong_and_soil_ge_8",
            "HS300周KDJ强且含行业土壤>=8",
            lambda df: df["hs300.weekly_kdj_state"].eq("strong")
            & (pd.to_numeric(df["soil_score_with_industry_v1"], errors="coerce") >= 8),
            "combo",
        ),
        _gate(
            "near_high_60d",
            "个股接近60日高点",
            lambda df: df["entry.price_position.near_high_60d_bucket"].eq("near_high"),
            "price",
        ),
        _gate(
            "near_high_or_moderate_pullback_60d",
            "个股近高点/中等回撤",
            lambda df: df["entry.price_position.near_high_60d_bucket"].isin(["near_high", "moderate_pullback"]),
            "price",
        ),
        _gate(
            "above_ma60_gt_1atr",
            "个股高于MA60超过1ATR",
            lambda df: df["entry.price_position.signal_close_ma60_atr_multiple_bucket"].isin(
                ["above_ma60_1_2atr", "above_ma60_gt_2atr"]
            ),
            "price",
        ),
    ]


def _gate(gate_id: str, label_zh: str, mask_fn: Callable[[pd.DataFrame], pd.Series], family: str) -> dict[str, Any]:
    return {"gate_id": gate_id, "label_zh": label_zh, "mask_fn": mask_fn, "family": family}


def _bucket_diagnostics(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for field, label in DIAGNOSTIC_FIELDS:
        if field not in df.columns:
            continue
        for bucket, bucket_df in df.groupby(field, dropna=False):
            full_stats = _trade_stats(bucket_df)
            recent_stats = _trade_stats(_period_slice(bucket_df, "2022-01-01", "2025-12-31"))
            pre_stats = _trade_stats(_period_slice(bucket_df, "2015-01-01", "2021-12-31"))
            rows.append(
                {
                    "field": field,
                    "field_label_zh": label,
                    "bucket": _bucket_label(bucket),
                    "full_trade_count": full_stats["trade_count"],
                    "full_win_rate_pct": full_stats["win_rate_pct"],
                    "full_avg_return_pct": full_stats["avg_return_pct"],
                    "full_profit_factor": full_stats["profit_factor"],
                    "pre_recent_trade_count": pre_stats["trade_count"],
                    "pre_recent_win_rate_pct": pre_stats["win_rate_pct"],
                    "pre_recent_avg_return_pct": pre_stats["avg_return_pct"],
                    "pre_recent_profit_factor": pre_stats["profit_factor"],
                    "recent_trade_count": recent_stats["trade_count"],
                    "recent_win_rate_pct": recent_stats["win_rate_pct"],
                    "recent_avg_return_pct": recent_stats["avg_return_pct"],
                    "recent_profit_factor": recent_stats["profit_factor"],
                    "recent_minus_pre_avg_return_pct": _diff(recent_stats["avg_return_pct"], pre_stats["avg_return_pct"]),
                    "recent_minus_pre_win_rate_pct": _diff(recent_stats["win_rate_pct"], pre_stats["win_rate_pct"]),
                }
            )
    return pd.DataFrame(rows).sort_values(["field", "recent_avg_return_pct"], ascending=[True, False])


def _gate_portfolio_metrics(
    df: pd.DataFrame,
    gates: list[dict[str, Any]],
    *,
    initial_cash: float,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    selected_rows: list[dict[str, Any]] = []
    for gate in gates:
        gate_df = _apply_gate(df, gate)
        pass_rate = len(gate_df) / len(df) * 100.0 if len(df) else 0.0
        for case_id, case_label, max_new, max_hold in PORTFOLIO_CASES:
            for period_id, period_label, start, end in PERIODS:
                period_df = _period_slice(gate_df, start, end)
                result = wf._simulate_portfolio(
                    period_df,
                    strategy_id=f"{CORE_STRATEGY_ID}.{gate['gate_id']}.{case_id}",
                    strategy_label=f"{CORE_STRATEGY_LABEL} + {gate['label_zh']}",
                    score_col=CORE_SCORE_COL,
                    max_new_per_day=max_new,
                    max_holding_count=max_hold,
                    initial_cash=initial_cash,
                )
                rows.append(
                    {
                        "gate_id": gate["gate_id"],
                        "gate_label_zh": gate["label_zh"],
                        "gate_family": gate["family"],
                        "candidate_pass_rate_pct": pass_rate,
                        "case_id": case_id,
                        "case_label_zh": case_label,
                        "period_id": period_id,
                        "period_zh": period_label,
                        **result["metrics"],
                    }
                )
                if period_id == "full":
                    selected_rows.extend(
                        {**row, "gate_id": gate["gate_id"], "case_id": case_id}
                        for row in result["selected"]
                    )
    return pd.DataFrame(rows), selected_rows


def _gate_scorecard(metrics: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    base = metrics[metrics["gate_id"].eq("no_gate")]
    for (gate_id, case_id), group in metrics.groupby(["gate_id", "case_id"]):
        if gate_id == "no_gate":
            continue
        recent = _one(group, "recent")
        pre = _one(group, "pre_recent")
        full = _one(group, "full")
        base_recent = _one(base[base["case_id"].eq(case_id)], "recent")
        base_pre = _one(base[base["case_id"].eq(case_id)], "pre_recent")
        if recent is None or pre is None or full is None or base_recent is None or base_pre is None:
            continue
        rows.append(
            {
                "gate_id": gate_id,
                "gate_label_zh": str(group["gate_label_zh"].iloc[0]),
                "gate_family": str(group["gate_family"].iloc[0]),
                "case_id": case_id,
                "case_label_zh": str(group["case_label_zh"].iloc[0]),
                "candidate_pass_rate_pct": float(group["candidate_pass_rate_pct"].iloc[0]),
                "recent_annualized_return_pct": recent["annualized_return_pct"],
                "recent_max_drawdown_pct": recent["max_drawdown_pct"],
                "recent_profit_factor": recent["profit_factor"],
                "recent_trade_count": recent["trade_count"],
                "recent_ann_return_lift_pct": _diff(recent["annualized_return_pct"], base_recent["annualized_return_pct"]),
                "recent_drawdown_lift_pct": _diff(recent["max_drawdown_pct"], base_recent["max_drawdown_pct"]),
                "recent_pf_lift": _diff(recent["profit_factor"], base_recent["profit_factor"]),
                "pre_annualized_return_pct": pre["annualized_return_pct"],
                "pre_max_drawdown_pct": pre["max_drawdown_pct"],
                "pre_profit_factor": pre["profit_factor"],
                "pre_ann_return_lift_pct": _diff(pre["annualized_return_pct"], base_pre["annualized_return_pct"]),
                "pre_pf_lift": _diff(pre["profit_factor"], base_pre["profit_factor"]),
                "full_annualized_return_pct": full["annualized_return_pct"],
                "full_max_drawdown_pct": full["max_drawdown_pct"],
                "score": _gate_score(recent, pre, base_recent, base_pre),
            }
        )
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    return result.sort_values(["case_id", "score", "recent_annualized_return_pct"], ascending=[True, False, False])


def _recent_yearly_metrics(df: pd.DataFrame, gates: list[dict[str, Any]], *, initial_cash: float) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    selected_gates = [
        gate
        for gate in gates
        if gate["gate_id"]
        in {
            "no_gate",
            "soil_layer_very_strong_only",
            "hs300_weekly_kdj_strong",
            "market_not_bearish_and_industry_not_weak",
            "soil_ge_8_and_hs300_above_ma60",
            "soil_ge_8_and_industry_above_ma60",
            "hs300_kdj_strong_and_soil_ge_8",
            "near_high_60d",
        }
    ]
    recent = _period_slice(df, "2022-01-01", "2025-12-31")
    for gate in selected_gates:
        gate_df = _apply_gate(recent, gate)
        for year in sorted(gate_df["entry_year"].dropna().unique()):
            year_df = gate_df[gate_df["entry_year"].eq(year)]
            for case_id, case_label, max_new, max_hold in PORTFOLIO_CASES:
                result = wf._simulate_portfolio(
                    year_df,
                    strategy_id=f"{CORE_STRATEGY_ID}.{gate['gate_id']}.{case_id}",
                    strategy_label=f"{CORE_STRATEGY_LABEL} + {gate['label_zh']}",
                    score_col=CORE_SCORE_COL,
                    max_new_per_day=max_new,
                    max_holding_count=max_hold,
                    initial_cash=initial_cash,
                )
                rows.append(
                    {
                        "gate_id": gate["gate_id"],
                        "gate_label_zh": gate["label_zh"],
                        "case_id": case_id,
                        "case_label_zh": case_label,
                        "year": int(year),
                        **result["metrics"],
                    }
                )
    return pd.DataFrame(rows)


def _apply_gate(df: pd.DataFrame, gate: dict[str, Any]) -> pd.DataFrame:
    mask = gate["mask_fn"](df).fillna(False)
    return df.loc[mask].copy()


def _trade_stats(df: pd.DataFrame) -> dict[str, Any]:
    returns = pd.to_numeric(df["return_pct"], errors="coerce").dropna()
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    return {
        "trade_count": int(len(df)),
        "win_rate_pct": float(len(wins) / len(returns) * 100) if len(returns) else None,
        "avg_return_pct": float(returns.mean()) if len(returns) else None,
        "profit_factor": float(wins.sum() / abs(losses.sum())) if len(losses) and abs(losses.sum()) > 0 else None,
    }


def _period_slice(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    if start is None and end is None:
        return df.copy()
    dates = pd.to_datetime(df["entry_date"])
    mask = pd.Series(True, index=df.index)
    if start is not None:
        mask &= dates >= pd.Timestamp(start)
    if end is not None:
        mask &= dates <= pd.Timestamp(end)
    return df.loc[mask].copy()


def _one(df: pd.DataFrame, period_id: str) -> dict[str, Any] | None:
    rows = df[df["period_id"].eq(period_id)]
    if rows.empty:
        return None
    return rows.iloc[0].to_dict()


def _gate_score(recent: dict[str, Any], pre: dict[str, Any], base_recent: dict[str, Any], base_pre: dict[str, Any]) -> float:
    recent_return_lift = _safe_diff(recent.get("annualized_return_pct"), base_recent.get("annualized_return_pct"))
    recent_pf_lift = _safe_diff(recent.get("profit_factor"), base_recent.get("profit_factor"))
    recent_drawdown_lift = _safe_diff(recent.get("max_drawdown_pct"), base_recent.get("max_drawdown_pct"))
    pre_return_lift = _safe_diff(pre.get("annualized_return_pct"), base_pre.get("annualized_return_pct"))
    pre_pf_lift = _safe_diff(pre.get("profit_factor"), base_pre.get("profit_factor"))
    trade_penalty = max(0.0, 120.0 - float(recent.get("trade_count") or 0.0)) / 120.0 * 5.0
    pre_penalty = max(0.0, -pre_return_lift) * 0.4 + max(0.0, -pre_pf_lift) * 8.0
    return recent_return_lift + 10.0 * recent_pf_lift + 0.35 * recent_drawdown_lift - pre_penalty - trade_penalty


def _safe_diff(value: Any, base: Any) -> float:
    diff = _diff(value, base)
    return float(diff) if diff is not None else 0.0


def _diff(value: Any, base: Any) -> float | None:
    if value is None or base is None:
        return None
    try:
        if pd.isna(value) or pd.isna(base):
            return None
    except (TypeError, ValueError):
        pass
    return float(value) - float(base)


def _bucket_label(value: Any) -> str:
    if value is None:
        return "nan"
    try:
        if pd.isna(value):
            return "nan"
    except (TypeError, ValueError):
        pass
    return str(value)


def _render_markdown(
    *,
    bucket_diagnostics: pd.DataFrame,
    gate_metrics: pd.DataFrame,
    scorecard: pd.DataFrame,
    yearly: pd.DataFrame,
    artifacts: dict[str, Path],
) -> str:
    core = gate_metrics[
        (gate_metrics["case_id"].eq("top3_hold10"))
        & (gate_metrics["period_id"].isin(["pre_recent", "recent"]))
        & (
            gate_metrics["gate_id"].isin(
                [
                    "no_gate",
                    "soil_layer_very_strong_only",
                    "hs300_weekly_kdj_strong",
                    "market_not_bearish_and_industry_not_weak",
                    "soil_ge_8_and_hs300_above_ma60",
                    "soil_ge_8_and_industry_above_ma60",
                    "hs300_kdj_strong_and_soil_ge_8",
                    "near_high_60d",
                    "industry_strong_only",
                ]
            )
        )
    ].copy()
    top_scorecard = scorecard.groupby("case_id", group_keys=False).head(12) if not scorecard.empty else scorecard
    recent_bad = bucket_diagnostics[
        (bucket_diagnostics["recent_trade_count"] >= 100)
        & (bucket_diagnostics["recent_avg_return_pct"].notna())
    ].sort_values(["recent_avg_return_pct", "recent_trade_count"], ascending=[True, False]).head(25)
    recent_good = bucket_diagnostics[
        (bucket_diagnostics["recent_trade_count"] >= 100)
        & (bucket_diagnostics["recent_avg_return_pct"].notna())
    ].sort_values(["recent_avg_return_pct", "recent_trade_count"], ascending=[False, False]).head(25)
    yearly_core = yearly[
        (yearly["case_id"].eq("top3_hold10"))
        & (
            yearly["gate_id"].isin(
                [
                    "no_gate",
                    "soil_layer_very_strong_only",
                    "hs300_weekly_kdj_strong",
                    "market_not_bearish_and_industry_not_weak",
                    "soil_ge_8_and_hs300_above_ma60",
                    "soil_ge_8_and_industry_above_ma60",
                    "hs300_kdj_strong_and_soil_ge_8",
                    "near_high_60d",
                ]
            )
        )
    ].copy()

    lines = [
        "# 2022-2025 Regime Gate / 风险开关分析",
        "",
        "## 口径",
        "",
        "- 输入为 walk-forward 已评分交易明细，gate 先过滤候选，再用 `wf_calibrated_total_score` 做每日排序。",
        "- 重点看 `2022-2025` 是否改善，同时检查 `2015-2021` 是否被明显伤害。",
        "- 这是代理组合实验，不是正式 K 线撮合；结论用于筛选下一轮正式策略参数。",
        "",
        "## Gate 评分榜",
        "",
    ]
    lines.extend(
        _table(
            top_scorecard,
            [
                "case_label_zh",
                "gate_label_zh",
                "candidate_pass_rate_pct",
                "recent_annualized_return_pct",
                "recent_max_drawdown_pct",
                "recent_profit_factor",
                "recent_ann_return_lift_pct",
                "pre_annualized_return_pct",
                "pre_ann_return_lift_pct",
                "score",
            ],
            limit=30,
        )
    )

    lines.extend(["", "## 核心 Gate 分时期对照（Top3 / MaxHold10）", ""])
    lines.extend(
        _table(
            core.sort_values(["gate_id", "period_id"]),
            [
                "period_zh",
                "gate_label_zh",
                "trade_count",
                "annualized_return_pct",
                "max_drawdown_pct",
                "win_rate_pct",
                "avg_trade_return_pct",
                "profit_factor",
            ],
            limit=80,
        )
    )

    lines.extend(["", "## 2022-2025 最差 Bucket", ""])
    lines.extend(
        _table(
            recent_bad,
            [
                "field_label_zh",
                "bucket",
                "recent_trade_count",
                "recent_win_rate_pct",
                "recent_avg_return_pct",
                "recent_profit_factor",
                "pre_recent_avg_return_pct",
            ],
            limit=25,
        )
    )

    lines.extend(["", "## 2022-2025 较好 Bucket", ""])
    lines.extend(
        _table(
            recent_good,
            [
                "field_label_zh",
                "bucket",
                "recent_trade_count",
                "recent_win_rate_pct",
                "recent_avg_return_pct",
                "recent_profit_factor",
                "pre_recent_avg_return_pct",
            ],
            limit=25,
        )
    )

    lines.extend(["", "## 近期年度对照（Top3 / MaxHold10）", ""])
    lines.extend(
        _table(
            yearly_core.sort_values(["year", "gate_id"]),
            [
                "year",
                "gate_label_zh",
                "trade_count",
                "annualized_return_pct",
                "max_drawdown_pct",
                "win_rate_pct",
                "avg_trade_return_pct",
                "profit_factor",
            ],
            limit=80,
        )
    )

    lines.extend(
        [
            "",
            "## 初步判断",
            "",
            "- 优先保留能改善 2022-2025 年化/PF/回撤，且不明显破坏 2015-2021 的 gate。",
            "- 如果 gate 只靠大幅降低交易数变好，要进入下一轮完整回测前先确认容量是否还能接受。",
            "- 如果所有单一 gate 都不能解决 2022-2025，下一步应做动态仓位，而不是硬过滤。",
            "",
            "## 产物",
            "",
            *[f"- `{name}`: `{path}`" for name, path in artifacts.items()],
            "",
        ]
    )
    return "\n".join(lines)


def _table(df: pd.DataFrame, columns: list[str], *, limit: int) -> list[str]:
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    if df.empty:
        lines.append("| " + " | ".join("-" for _ in columns) + " |")
        return lines
    for _, row in df.head(limit)[columns].iterrows():
        values = [_fmt(row[col]) for col in columns]
        lines.append("| " + " | ".join(values) + " |")
    return lines


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    try:
        if pd.isna(value):
            return "-"
    except (TypeError, ValueError):
        pass
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
