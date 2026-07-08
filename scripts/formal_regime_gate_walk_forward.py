"""Compare selected regime gates in the walk-forward portfolio proxy.

This is the formal gate comparison for the shortlisted risk switches:

- near_high_60d
- soil_ge_8_and_industry_above_ma60
- hs300_weekly_kdj_strong

The source scores are already walk-forward calibrated by year. This script only
filters the test-year candidate pool before daily score ranking and portfolio
simulation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

import pandas as pd

import walk_forward_portfolio_validation as wf


DEFAULT_WALK_FORWARD_DIR = Path("reports/walk-forward-portfolio-validation-hs300-only-2006-2025")
DEFAULT_OUTPUT_DIR = Path("reports/formal-regime-gate-walk-forward-hs300-only-2006-2025")

SCORE_COL = "wf_calibrated_total_score"
INITIAL_CASH = 1_000_000.0
MAX_NEW_PER_DAY_VALUES = (1, 3, 5)
MAX_HOLDING_VALUES = (5, 10, 20)

PERIODS = (
    ("full", "2013-2025", None, None),
    ("early_oos", "2013-2014", "2013-01-01", "2014-12-31"),
    ("pre_recent", "2015-2021", "2015-01-01", "2021-12-31"),
    ("recent", "2022-2025", "2022-01-01", "2025-12-31"),
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = _load_detail(Path(args.walk_forward_dir))
    gates = _gate_definitions()

    metrics, selected_rows, equity_rows = _run_full_grid(df, gates, initial_cash=float(args.initial_cash))
    period_metrics = _run_period_grid(df, gates, initial_cash=float(args.initial_cash))
    yearly_metrics = _run_yearly_grid(df, gates, initial_cash=float(args.initial_cash))
    scorecard = _scorecard(period_metrics)
    pass_rates = _pass_rate_table(df, gates)

    metrics_path = output_dir / "formal_gate_portfolio_metrics.csv"
    period_path = output_dir / "formal_gate_period_metrics.csv"
    yearly_path = output_dir / "formal_gate_yearly_metrics.csv"
    scorecard_path = output_dir / "formal_gate_scorecard.csv"
    pass_rate_path = output_dir / "formal_gate_candidate_pass_rates.csv"
    selected_path = output_dir / "formal_gate_selected_trades.parquet"
    equity_path = output_dir / "formal_gate_equity_curves.parquet"
    metadata_path = output_dir / "formal_gate_metadata.json"
    markdown_path = output_dir / "formal_gate_walk_forward.zh.md"

    pd.DataFrame(metrics).to_csv(metrics_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(period_metrics).to_csv(period_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(yearly_metrics).to_csv(yearly_path, index=False, encoding="utf-8-sig")
    scorecard.to_csv(scorecard_path, index=False, encoding="utf-8-sig")
    pass_rates.to_csv(pass_rate_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(selected_rows).to_parquet(selected_path, index=False)
    pd.DataFrame(equity_rows).to_parquet(equity_path, index=False)

    metadata = {
        "schema": "attbacktrader.formal_regime_gate_walk_forward.v1",
        "source_walk_forward_dir": str(args.walk_forward_dir),
        "score_col": SCORE_COL,
        "initial_cash": float(args.initial_cash),
        "max_new_per_day_values": list(MAX_NEW_PER_DAY_VALUES),
        "max_holding_values": list(MAX_HOLDING_VALUES),
        "gates": [
            {
                "gate_id": gate["gate_id"],
                "label_zh": gate["label_zh"],
                "definition_zh": gate["definition_zh"],
                "main": bool(gate["main"]),
            }
            for gate in gates
        ],
        "caveat_zh": "输入为已完成交易样本和 walk-forward 分数；组合模拟有现金/持仓/每日买入约束，但不是重新 K 线撮合。",
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown_path.write_text(
        _render_markdown(
            metrics=pd.DataFrame(metrics),
            period_metrics=pd.DataFrame(period_metrics),
            yearly_metrics=pd.DataFrame(yearly_metrics),
            scorecard=scorecard,
            pass_rates=pass_rates,
            artifacts={
                "portfolio_metrics": metrics_path,
                "period_metrics": period_path,
                "yearly_metrics": yearly_path,
                "scorecard": scorecard_path,
                "candidate_pass_rates": pass_rate_path,
                "selected_trades": selected_path,
                "equity_curves": equity_path,
                "metadata": metadata_path,
            },
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "gate_count": len(gates),
                "analysis_markdown": str(markdown_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Formal walk-forward comparison for shortlisted regime gates")
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
    near_high = lambda df: df["entry.price_position.near_high_60d_bucket"].eq("near_high")
    soil_industry = lambda df: (
        pd.to_numeric(df["soil_score_with_industry_v1"], errors="coerce") >= 8
    ) & df["industry_ma60_position"].eq("above_ma60")
    kdj_strong = lambda df: df["hs300.weekly_kdj_state"].eq("strong")

    return [
        _gate("no_gate", "无 gate", "不过滤候选池", lambda df: pd.Series(True, index=df.index), True),
        _gate("near_high_60d", "near_high_60d", "个股接近60日高点", near_high, True),
        _gate(
            "soil_ge_8_and_industry_above_ma60",
            "soil+industry",
            "含行业土壤分>=8 且 行业在MA60上方",
            soil_industry,
            True,
        ),
        _gate("hs300_weekly_kdj_strong", "KDJ strong", "HS300周线KDJ为strong", kdj_strong, True),
        _gate(
            "combo_any",
            "组合 gate（三者任一）",
            "near_high_60d OR soil+industry OR KDJ strong",
            lambda df: near_high(df) | soil_industry(df) | kdj_strong(df),
            True,
        ),
        _gate(
            "combo_all_reference",
            "严格组合参考（三者同时）",
            "near_high_60d AND soil+industry AND KDJ strong",
            lambda df: near_high(df) & soil_industry(df) & kdj_strong(df),
            False,
        ),
    ]


def _gate(
    gate_id: str,
    label_zh: str,
    definition_zh: str,
    mask_fn: Callable[[pd.DataFrame], pd.Series],
    main: bool,
) -> dict[str, Any]:
    return {
        "gate_id": gate_id,
        "label_zh": label_zh,
        "definition_zh": definition_zh,
        "mask_fn": mask_fn,
        "main": main,
    }


def _run_full_grid(
    df: pd.DataFrame,
    gates: list[dict[str, Any]],
    *,
    initial_cash: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    metrics: list[dict[str, Any]] = []
    selected_rows: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []
    for gate in gates:
        gate_df = _apply_gate(df, gate)
        for max_new in MAX_NEW_PER_DAY_VALUES:
            for max_holding in MAX_HOLDING_VALUES:
                result = wf._simulate_portfolio(
                    gate_df,
                    strategy_id=f"wf_total.{gate['gate_id']}",
                    strategy_label=f"Walk-forward总分 + {gate['label_zh']}",
                    score_col=SCORE_COL,
                    max_new_per_day=max_new,
                    max_holding_count=max_holding,
                    initial_cash=initial_cash,
                )
                metrics.append(
                    {
                        **_gate_fields(gate, df, gate_df),
                        **result["metrics"],
                        "period_id": "full",
                        "period_zh": "2013-2025",
                    }
                )
                selected_rows.extend(
                    {**row, "gate_id": gate["gate_id"], "gate_label_zh": gate["label_zh"]}
                    for row in result["selected"]
                )
                equity_rows.extend(
                    {**row, "gate_id": gate["gate_id"], "gate_label_zh": gate["label_zh"]}
                    for row in result["equity_curve"]
                )
    return metrics, selected_rows, equity_rows


def _run_period_grid(df: pd.DataFrame, gates: list[dict[str, Any]], *, initial_cash: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for gate in gates:
        gate_df = _apply_gate(df, gate)
        for period_id, period_zh, start, end in PERIODS:
            period_df = wf._period_slice(gate_df, start, end)
            period_all = wf._period_slice(df, start, end)
            for max_new in MAX_NEW_PER_DAY_VALUES:
                for max_holding in MAX_HOLDING_VALUES:
                    result = wf._simulate_portfolio(
                        period_df,
                        strategy_id=f"wf_total.{gate['gate_id']}",
                        strategy_label=f"Walk-forward总分 + {gate['label_zh']}",
                        score_col=SCORE_COL,
                        max_new_per_day=max_new,
                        max_holding_count=max_holding,
                        initial_cash=initial_cash,
                    )
                    rows.append(
                        {
                            **_gate_fields(gate, period_all, period_df),
                            **result["metrics"],
                            "period_id": period_id,
                            "period_zh": period_zh,
                        }
                    )
    return rows


def _run_yearly_grid(df: pd.DataFrame, gates: list[dict[str, Any]], *, initial_cash: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for gate in gates:
        gate_df = _apply_gate(df, gate)
        for year in sorted(int(value) for value in df["entry_year"].dropna().unique()):
            year_all = df[df["entry_year"].eq(year)]
            year_df = gate_df[gate_df["entry_year"].eq(year)]
            for max_new in MAX_NEW_PER_DAY_VALUES:
                for max_holding in MAX_HOLDING_VALUES:
                    result = wf._simulate_portfolio(
                        year_df,
                        strategy_id=f"wf_total.{gate['gate_id']}",
                        strategy_label=f"Walk-forward总分 + {gate['label_zh']}",
                        score_col=SCORE_COL,
                        max_new_per_day=max_new,
                        max_holding_count=max_holding,
                        initial_cash=initial_cash,
                    )
                    rows.append(
                        {
                            **_gate_fields(gate, year_all, year_df),
                            **result["metrics"],
                            "year": year,
                        }
                    )
    return rows


def _pass_rate_table(df: pd.DataFrame, gates: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for gate in gates:
        gate_df = _apply_gate(df, gate)
        for period_id, period_zh, start, end in PERIODS:
            period_all = wf._period_slice(df, start, end)
            period_gate = wf._period_slice(gate_df, start, end)
            rows.append(
                {
                    **_gate_fields(gate, period_all, period_gate),
                    "period_id": period_id,
                    "period_zh": period_zh,
                }
            )
    return pd.DataFrame(rows)


def _scorecard(period_metrics: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(period_metrics)
    base = df[df["gate_id"].eq("no_gate")]
    rows: list[dict[str, Any]] = []
    for (gate_id, max_new, max_holding), group in df.groupby(["gate_id", "max_new_per_day", "max_holding_count"]):
        if gate_id == "no_gate":
            continue
        recent = _one(group, "recent")
        pre = _one(group, "pre_recent")
        full = _one(group, "full")
        base_recent = _one(base[(base["max_new_per_day"].eq(max_new)) & (base["max_holding_count"].eq(max_holding))], "recent")
        base_pre = _one(base[(base["max_new_per_day"].eq(max_new)) & (base["max_holding_count"].eq(max_holding))], "pre_recent")
        base_full = _one(base[(base["max_new_per_day"].eq(max_new)) & (base["max_holding_count"].eq(max_holding))], "full")
        if recent is None or pre is None or full is None or base_recent is None or base_pre is None or base_full is None:
            continue
        rows.append(
            {
                "gate_id": gate_id,
                "gate_label_zh": str(group["gate_label_zh"].iloc[0]),
                "gate_definition_zh": str(group["gate_definition_zh"].iloc[0]),
                "is_main_gate": bool(group["is_main_gate"].iloc[0]),
                "max_new_per_day": int(max_new),
                "max_holding_count": int(max_holding),
                "candidate_pass_rate_pct": full["candidate_pass_rate_pct"],
                "full_annualized_return_pct": full["annualized_return_pct"],
                "full_max_drawdown_pct": full["max_drawdown_pct"],
                "full_profit_factor": full["profit_factor"],
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
                "full_ann_return_lift_pct": _diff(full["annualized_return_pct"], base_full["annualized_return_pct"]),
                "score": _gate_score(recent, pre, full, base_recent, base_pre, base_full),
            }
        )
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    return result.sort_values(["is_main_gate", "max_holding_count", "max_new_per_day", "score"], ascending=[False, True, True, False])


def _apply_gate(df: pd.DataFrame, gate: dict[str, Any]) -> pd.DataFrame:
    mask = gate["mask_fn"](df).fillna(False)
    return df.loc[mask].copy()


def _gate_fields(gate: dict[str, Any], all_df: pd.DataFrame, gate_df: pd.DataFrame) -> dict[str, Any]:
    return {
        "gate_id": gate["gate_id"],
        "gate_label_zh": gate["label_zh"],
        "gate_definition_zh": gate["definition_zh"],
        "is_main_gate": bool(gate["main"]),
        "candidate_count_before_gate": int(len(all_df)),
        "candidate_count_after_gate": int(len(gate_df)),
        "candidate_pass_rate_pct": float(len(gate_df) / len(all_df) * 100.0) if len(all_df) else None,
    }


def _one(df: pd.DataFrame, period_id: str) -> dict[str, Any] | None:
    row = df[df["period_id"].eq(period_id)]
    if row.empty:
        return None
    return row.iloc[0].to_dict()


def _gate_score(
    recent: dict[str, Any],
    pre: dict[str, Any],
    full: dict[str, Any],
    base_recent: dict[str, Any],
    base_pre: dict[str, Any],
    base_full: dict[str, Any],
) -> float:
    recent_return_lift = _safe_diff(recent.get("annualized_return_pct"), base_recent.get("annualized_return_pct"))
    recent_pf_lift = _safe_diff(recent.get("profit_factor"), base_recent.get("profit_factor"))
    recent_drawdown_lift = _safe_diff(recent.get("max_drawdown_pct"), base_recent.get("max_drawdown_pct"))
    pre_return_lift = _safe_diff(pre.get("annualized_return_pct"), base_pre.get("annualized_return_pct"))
    pre_pf_lift = _safe_diff(pre.get("profit_factor"), base_pre.get("profit_factor"))
    full_return_lift = _safe_diff(full.get("annualized_return_pct"), base_full.get("annualized_return_pct"))
    recent_trade_count = float(recent.get("trade_count") or 0.0)
    sample_penalty = max(0.0, 120.0 - recent_trade_count) / 120.0 * 3.0
    pre_penalty = max(0.0, -pre_return_lift) * 0.35 + max(0.0, -pre_pf_lift) * 5.0
    return (
        recent_return_lift
        + 8.0 * recent_pf_lift
        + 0.30 * recent_drawdown_lift
        + 0.35 * full_return_lift
        - pre_penalty
        - sample_penalty
    )


def _safe_diff(value: Any, base: Any) -> float:
    result = _diff(value, base)
    return float(result) if result is not None else 0.0


def _diff(value: Any, base: Any) -> float | None:
    if value is None or base is None:
        return None
    try:
        if pd.isna(value) or pd.isna(base):
            return None
    except (TypeError, ValueError):
        pass
    return float(value) - float(base)


def _render_markdown(
    *,
    metrics: pd.DataFrame,
    period_metrics: pd.DataFrame,
    yearly_metrics: pd.DataFrame,
    scorecard: pd.DataFrame,
    pass_rates: pd.DataFrame,
    artifacts: dict[str, Path],
) -> str:
    main_scorecard = scorecard[scorecard["is_main_gate"].eq(True)].copy()
    best_by_gate = (
        main_scorecard.sort_values(["score", "recent_annualized_return_pct"], ascending=[False, False])
        .groupby("gate_id", as_index=False)
        .head(1)
        .sort_values("score", ascending=False)
    )
    core_cases = scorecard[
        scorecard["is_main_gate"].eq(True)
        & (
            (scorecard["max_new_per_day"].eq(1) & scorecard["max_holding_count"].eq(20))
            | (scorecard["max_new_per_day"].eq(3) & scorecard["max_holding_count"].eq(10))
        )
    ].copy()
    period_core = period_metrics[
        period_metrics["is_main_gate"].eq(True)
        & period_metrics["max_new_per_day"].eq(3)
        & period_metrics["max_holding_count"].eq(10)
    ].copy()
    yearly_recent_core = yearly_metrics[
        yearly_metrics["is_main_gate"].eq(True)
        & yearly_metrics["max_new_per_day"].eq(3)
        & yearly_metrics["max_holding_count"].eq(10)
        & yearly_metrics["year"].isin([2022, 2023, 2024, 2025])
    ].copy()
    strict_reference = scorecard[scorecard["gate_id"].eq("combo_all_reference")].sort_values(
        ["score", "recent_annualized_return_pct"], ascending=[False, False]
    ).head(5)

    lines = [
        "# 正式 Regime Gate Walk-forward 组合对照",
        "",
        "## 口径",
        "",
        "- 输入使用阶段 4 的 walk-forward 已评分交易明细，分数本身只来自测试年前训练窗口。",
        "- gate 先过滤候选池，再按 `wf_calibrated_total_score` 做每日排名。",
        "- 组合模拟包含初始资金、最大持仓、每日买入上限和退出后资金回收；仍属于已完成交易样本代理回测，不是重新 K 线撮合。",
        "- 主对照：无 gate / near_high_60d / soil+industry / KDJ strong / 组合 gate（三者任一）。严格三者同时满足只作参考。",
        "",
        "## 候选池通过率",
        "",
    ]
    lines.extend(
        _table(
            pass_rates[pass_rates["period_id"].isin(["full", "pre_recent", "recent"])],
            [
                "period_zh",
                "gate_label_zh",
                "candidate_count_before_gate",
                "candidate_count_after_gate",
                "candidate_pass_rate_pct",
            ],
            limit=40,
        )
    )

    lines.extend(["", "## 每个 Gate 最佳参数", ""])
    lines.extend(
        _table(
            best_by_gate,
            [
                "gate_label_zh",
                "max_new_per_day",
                "max_holding_count",
                "candidate_pass_rate_pct",
                "full_annualized_return_pct",
                "full_max_drawdown_pct",
                "recent_annualized_return_pct",
                "recent_max_drawdown_pct",
                "recent_profit_factor",
                "pre_annualized_return_pct",
                "score",
            ],
            limit=20,
        )
    )

    lines.extend(["", "## 核心参数对照", ""])
    lines.extend(
        _table(
            core_cases.sort_values(["max_holding_count", "max_new_per_day", "score"], ascending=[True, True, False]),
            [
                "gate_label_zh",
                "max_new_per_day",
                "max_holding_count",
                "full_annualized_return_pct",
                "full_max_drawdown_pct",
                "recent_annualized_return_pct",
                "recent_max_drawdown_pct",
                "recent_profit_factor",
                "pre_annualized_return_pct",
                "pre_profit_factor",
            ],
            limit=60,
        )
    )

    lines.extend(["", "## 分时期对照（Top3 / MaxHold10）", ""])
    lines.extend(
        _table(
            period_core.sort_values(["period_id", "gate_id"]),
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

    lines.extend(["", "## 2022-2025 年度对照（Top3 / MaxHold10）", ""])
    lines.extend(
        _table(
            yearly_recent_core.sort_values(["year", "gate_id"]),
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

    lines.extend(["", "## 严格组合参考", ""])
    lines.extend(
        _table(
            strict_reference,
            [
                "gate_label_zh",
                "max_new_per_day",
                "max_holding_count",
                "candidate_pass_rate_pct",
                "recent_annualized_return_pct",
                "recent_max_drawdown_pct",
                "recent_profit_factor",
                "pre_annualized_return_pct",
            ],
            limit=10,
        )
    )

    lines.extend(
        [
            "",
            "## 初步判断",
            "",
            "- 如果 gate 在 2022-2025 改善年化/PF/回撤，同时 2015-2021 不显著变差，才适合作为候选池规则。",
            "- 如果 gate 只在 Top1/MaxHold20 有效，说明它更适合容量稀缺时排序；如果 Top3/MaxHold10 也有效，才更适合常规交易。",
            "- 严格三者同时满足通常样本更少，只用于观察方向，不建议直接作为实盘第一版硬规则。",
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
