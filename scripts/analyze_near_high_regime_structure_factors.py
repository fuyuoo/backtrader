from __future__ import annotations

import math
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "near-high-60d-regime-structure-factor-diagnosis-hs300-only-2006-2025"

SWEEP = ROOT / "reports" / "near-high-60d-holding-sweep-hs300-only-2006-2025"
FORMAL = ROOT / "reports" / "formal-regime-gate-walk-forward-hs300-only-2006-2025"
SEED = ROOT / "reports" / "seed-v2-candidate-hs300-only-2006-2025"
INDEX = ROOT / "data" / "snapshots" / "indexes" / "000300_SH_20060101_20251231.parquet"


PERIODS = (
    ("2006-2014", 2006, 2014),
    ("2015-2021", 2015, 2021),
    ("2022-2025", 2022, 2025),
)


def pct(v: float | int | None, digits: int = 2) -> str:
    if v is None or pd.isna(v):
        return ""
    return f"{float(v):.{digits}f}%"


def ratio(v: float | int | None, digits: int = 2) -> str:
    if v is None or pd.isna(v):
        return ""
    if math.isinf(float(v)):
        return "inf"
    return f"{float(v):.{digits}f}"


def profit_factor(r: pd.Series) -> float:
    r = r.dropna()
    loss = -r[r < 0].sum()
    if loss == 0:
        return math.inf if r.gt(0).any() else math.nan
    return float(r[r > 0].sum() / loss)


def max_drawdown_pct(values: pd.Series) -> float:
    values = values.dropna()
    if values.empty:
        return math.nan
    return float((values / values.cummax() - 1.0).min() * 100.0)


def trade_stats(g: pd.DataFrame, return_col: str = "return_pct") -> pd.Series:
    r = pd.to_numeric(g[return_col], errors="coerce").dropna()
    return pd.Series(
        {
            "trade_count": len(g),
            "win_rate_pct": float(r.gt(0).mean() * 100.0) if len(r) else math.nan,
            "avg_return_pct": float(r.mean() * 100.0) if len(r) else math.nan,
            "median_return_pct": float(r.median() * 100.0) if len(r) else math.nan,
            "avg_win_pct": float(r[r > 0].mean() * 100.0) if r.gt(0).any() else math.nan,
            "avg_loss_pct": float(r[r < 0].mean() * 100.0) if r.lt(0).any() else math.nan,
            "profit_factor": profit_factor(r),
            "net_pnl": float(pd.to_numeric(g.get("pnl", g.get("net_pnl")), errors="coerce").sum()),
        }
    )


def add_period(df: pd.DataFrame, year_col: str = "year") -> pd.DataFrame:
    df = df.copy()
    df["period"] = ""
    for label, start, end in PERIODS:
        df.loc[df[year_col].between(start, end), "period"] = label
    return df


def load_hs300_regime() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    bars = pd.read_parquet(INDEX)
    bars["trade_date"] = pd.to_datetime(bars["trade_date"])
    bars = bars.sort_values("trade_date").drop_duplicates("trade_date")
    bars = bars[(bars["trade_date"] >= "2006-01-01") & (bars["trade_date"] <= "2025-12-31")].copy()
    bars["year"] = bars["trade_date"].dt.year
    for n in (20, 60, 120, 250):
        bars[f"ma{n}"] = bars["close"].rolling(n, min_periods=n).mean()
        bars[f"above_ma{n}"] = bars["close"] > bars[f"ma{n}"]
    bars["ma20_gt_ma60"] = bars["ma20"] > bars["ma60"]
    bars["ma60_slope_20d"] = bars["ma60"] / bars["ma60"].shift(20) - 1.0
    bars["market_regime"] = "mixed"
    bars.loc[(bars["above_ma60"]) & (bars["ma20_gt_ma60"]), "market_regime"] = "bullish"
    bars.loc[(~bars["above_ma60"]) & (~bars["ma20_gt_ma60"]), "market_regime"] = "bearish"

    annual_rows = []
    for year, g in bars.groupby("year"):
        if year < 2006 or year > 2025:
            continue
        annual_rows.append(
            {
                "year": int(year),
                "start_close": float(g.iloc[0]["close"]),
                "end_close": float(g.iloc[-1]["close"]),
                "return_pct": float((g.iloc[-1]["close"] / g.iloc[0]["close"] - 1.0) * 100.0),
                "max_drawdown_pct": max_drawdown_pct(g["close"]),
                "above_ma60_pct": float(g["above_ma60"].mean() * 100.0),
                "above_ma120_pct": float(g["above_ma120"].mean() * 100.0),
                "above_ma250_pct": float(g["above_ma250"].mean() * 100.0),
                "ma20_gt_ma60_pct": float(g["ma20_gt_ma60"].mean() * 100.0),
            }
        )
    annual = pd.DataFrame(annual_rows)
    annual["regime_label"] = "震荡/混合"
    annual.loc[(annual["return_pct"] < 0) & (annual["above_ma60_pct"] < 40), "regime_label"] = "弱市/熊市"
    annual.loc[(annual["return_pct"] > 0) & (annual["above_ma60_pct"] >= 50), "regime_label"] = "强市/修复"

    period_rows = []
    for label, start, end in PERIODS:
        g = bars[bars["year"].between(start, end)]
        period_rows.append(
            {
                "period": label,
                "return_pct": float((g.iloc[-1]["close"] / g.iloc[0]["close"] - 1.0) * 100.0),
                "max_drawdown_pct": max_drawdown_pct(g["close"]),
                "above_ma60_pct": float(g["above_ma60"].mean() * 100.0),
                "above_ma120_pct": float(g["above_ma120"].mean() * 100.0),
                "above_ma250_pct": float(g["above_ma250"].mean() * 100.0),
                "ma20_gt_ma60_pct": float(g["ma20_gt_ma60"].mean() * 100.0),
            }
        )
    periods = pd.DataFrame(period_rows)
    return bars, annual, periods


def load_near_high_formal_with_factors() -> pd.DataFrame:
    selected = pd.read_parquet(FORMAL / "formal_gate_selected_trades.parquet")
    selected = selected[
        (selected["gate_id"] == "near_high_60d")
        & (selected["max_new_per_day"] == 3)
        & (selected["max_holding_count"] == 10)
    ].copy()
    factors = pd.read_parquet(SEED / "seed_v2_candidate_trade_detail.parquet")

    keys = ["symbol", "entry_date", "exit_date"]
    for df in (selected, factors):
        df["entry_date"] = pd.to_datetime(df["entry_date"]).dt.strftime("%Y-%m-%d")
        df["exit_date"] = pd.to_datetime(df["exit_date"]).dt.strftime("%Y-%m-%d")

    keep_cols = keys + [
        "holding_days",
        "exit_reason",
        "seed_score_no_industry_v1",
        "seed_v2_candidate_score",
        "seed_v2_liquidity_score",
        "seed_v2_market_cap_score",
        "seed_v2_price_position_score",
        "soil_score_no_industry_v2",
        "soil_score_with_industry_v1",
        "industry_soil_score_v1",
        "hs300.index_soil_v2_score",
        "hs300.weekly_kdj_state",
        "hs300.ma60_position",
        "hs300.ma_position_bucket",
        "hs300.ma_stack_state",
        "industry_weekly_kdj_state",
        "industry_ma60_position",
        "industry_ma_position_bucket",
        "industry_ma_stack_state",
        "entry.liquidity.turnover_rate_bucket",
        "entry.liquidity.turnover_rate_20d_bucket",
        "entry.liquidity.amount_vs_20d_bucket",
        "entry.market_cap.total_mv_abs_bucket",
        "entry.market_cap.circulating_mv_abs_bucket",
        "entry.price_position.interval_60d_bucket",
        "entry.price_position.near_high_60d_bucket",
    ]
    factors = factors[[c for c in keep_cols if c in factors.columns]].drop_duplicates(keys)
    merged = selected.merge(factors, on=keys, how="left", validate="one_to_one")
    merged["entry_date_dt"] = pd.to_datetime(merged["entry_date"])
    merged["year"] = merged["entry_date_dt"].dt.year
    # formal_gate_selected_trades.return_pct is already stored as percentage points.
    merged["return_decimal"] = pd.to_numeric(merged["return_pct"], errors="coerce") / 100.0
    merged["is_win"] = merged["return_decimal"] > 0
    return add_period(merged)


def build_market_trade_tables(formal: pd.DataFrame, hs300_bars: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    regime_cols = [
        "trade_date",
        "above_ma60",
        "above_ma120",
        "above_ma250",
        "ma20_gt_ma60",
        "ma60_slope_20d",
        "market_regime",
    ]
    regime = hs300_bars[regime_cols].copy()
    trade = formal.merge(regime, left_on="entry_date_dt", right_on="trade_date", how="left")

    by_period_regime = (
        trade.groupby(["period", "market_regime"], dropna=False)
        .apply(trade_stats, return_col="return_decimal", include_groups=False)
        .reset_index()
    )
    by_year_regime = (
        trade[trade["year"].between(2022, 2025)]
        .groupby(["year", "market_regime"], dropna=False)
        .apply(trade_stats, return_col="return_decimal", include_groups=False)
        .reset_index()
    )
    return by_period_regime, by_year_regime


def build_holding_structure() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    exit_rows = []
    for max_hold in (10, 20, 50):
        df = pd.read_parquet(
            SWEEP / f"baoma-v1-dynamic-hs300-only-2006-2025-near-high-60d-maxhold-{max_hold}.trades.parquet"
        )
        df["entry_date"] = pd.to_datetime(df["entry_date"])
        df["exit_date"] = pd.to_datetime(df["exit_date"])
        df["year"] = df["entry_date"].dt.year
        df["holding_days"] = (df["exit_date"] - df["entry_date"]).dt.days
        df["return_pct"] = df["realized_return_pct"]
        df["pnl"] = df["net_pnl"]
        df = add_period(df)
        for (period, year), g in df.groupby(["period", "year"]):
            s = trade_stats(g)
            s["max_holding_count"] = max_hold
            s["period"] = period
            s["year"] = int(year)
            s["avg_holding_days"] = float(g["holding_days"].mean())
            s["big_win_rate_pct"] = float((g["return_pct"] >= 0.10).mean() * 100.0)
            s["big_loss_rate_pct"] = float((g["return_pct"] <= -0.07).mean() * 100.0)
            rows.append(s)
        for (period, reason), g in df.groupby(["period", "exit_reason"]):
            exit_rows.append(
                {
                    "max_holding_count": max_hold,
                    "period": period,
                    "exit_reason": reason,
                    "trade_count": len(g),
                    "trade_share_pct": len(g) / len(df[df["period"] == period]) * 100.0,
                    "avg_return_pct": g["return_pct"].mean() * 100.0,
                    "profit_factor": profit_factor(g["return_pct"]),
                }
            )
    return pd.DataFrame(rows), pd.DataFrame(exit_rows)


def build_factor_diagnostics(formal: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    recent = formal[formal["year"].between(2022, 2025)].copy()
    numeric_factors = [
        "score",
        "seed_score_no_industry_v1",
        "seed_v2_candidate_score",
        "seed_v2_liquidity_score",
        "seed_v2_market_cap_score",
        "seed_v2_price_position_score",
        "soil_score_no_industry_v2",
        "soil_score_with_industry_v1",
        "industry_soil_score_v1",
        "hs300.index_soil_v2_score",
    ]
    diff_rows = []
    for col in numeric_factors:
        if col not in recent.columns:
            continue
        x = pd.to_numeric(recent[col], errors="coerce")
        win = x[recent["is_win"]]
        loss = x[~recent["is_win"]]
        diff_rows.append(
            {
                "factor": col,
                "coverage_pct": float(x.notna().mean() * 100.0),
                "win_mean": float(win.mean()) if len(win.dropna()) else math.nan,
                "loss_mean": float(loss.mean()) if len(loss.dropna()) else math.nan,
                "win_minus_loss": float(win.mean() - loss.mean()) if len(win.dropna()) and len(loss.dropna()) else math.nan,
                "win_median": float(win.median()) if len(win.dropna()) else math.nan,
                "loss_median": float(loss.median()) if len(loss.dropna()) else math.nan,
            }
        )

    categorical = [
        "hs300.weekly_kdj_state",
        "hs300.ma60_position",
        "hs300.ma_position_bucket",
        "hs300.ma_stack_state",
        "industry_weekly_kdj_state",
        "industry_ma60_position",
        "industry_ma_position_bucket",
        "industry_ma_stack_state",
        "entry.liquidity.turnover_rate_bucket",
        "entry.liquidity.turnover_rate_20d_bucket",
        "entry.liquidity.amount_vs_20d_bucket",
        "entry.market_cap.total_mv_abs_bucket",
        "entry.market_cap.circulating_mv_abs_bucket",
        "entry.price_position.interval_60d_bucket",
    ]
    cat_rows = []
    for col in categorical:
        if col not in recent.columns:
            continue
        for value, g in recent.groupby(col, dropna=False):
            if len(g) < 10:
                continue
            s = trade_stats(g, return_col="return_decimal")
            s["factor"] = col
            s["value"] = "missing" if pd.isna(value) else str(value)
            s["trade_share_pct"] = len(g) / len(recent) * 100.0
            cat_rows.append(s)

    diff = pd.DataFrame(diff_rows).sort_values("win_minus_loss", ascending=False)
    cat = pd.DataFrame(cat_rows).sort_values(["profit_factor", "avg_return_pct"], ascending=False)
    return diff, cat


def build_gate_validation_summary() -> pd.DataFrame:
    period_metrics = pd.read_csv(FORMAL / "formal_gate_period_metrics.csv")
    focus = period_metrics[
        (period_metrics["max_new_per_day"] == 3)
        & (period_metrics["max_holding_count"] == 10)
        & (period_metrics["period_zh"].isin(["2013-2025", "2015-2021", "2022-2025"]))
    ].copy()
    cols = [
        "period_zh",
        "gate_label_zh",
        "trade_count",
        "annualized_return_pct",
        "max_drawdown_pct",
        "win_rate_pct",
        "avg_trade_return_pct",
        "profit_factor",
        "candidate_pass_rate_pct",
    ]
    return focus[cols].sort_values(["period_zh", "annualized_return_pct"], ascending=[True, False])


def markdown_table(df: pd.DataFrame, columns: list[str], headers: list[str], max_rows: int | None = None) -> str:
    view = df[columns].copy()
    if max_rows is not None:
        view = view.head(max_rows)
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for _, row in view.iterrows():
        vals = []
        for col in columns:
            val = row[col]
            if isinstance(val, float):
                vals.append(ratio(val, 2))
            else:
                vals.append(str(val))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def write_report(
    annual: pd.DataFrame,
    period_regime: pd.DataFrame,
    year_regime: pd.DataFrame,
    structure: pd.DataFrame,
    exits: pd.DataFrame,
    factor_diff: pd.DataFrame,
    factor_cat: pd.DataFrame,
    gate_summary: pd.DataFrame,
) -> None:
    recent_structure = structure[(structure["max_holding_count"] == 10) & (structure["year"].between(2022, 2025))]
    recent_exits = exits[(exits["max_holding_count"] == 10) & (exits["period"] == "2022-2025")].sort_values(
        "trade_count", ascending=False
    )
    gate_recent = gate_summary[gate_summary["period_zh"] == "2022-2025"]
    gate_pre = gate_summary[gate_summary["period_zh"] == "2015-2021"]

    lines = [
        "# near_high_60d 近期失效四层诊断",
        "",
        "## 结论摘要",
        "",
        "- 2022-2023 的衰减和 HS300 弱市高度同向；2024-2025 大盘修复后，near_high_60d 的交易质量明显恢复。",
        "- 近四年不是因子永久失效，而是弱市里突破延续性下降，尤其 2023 是主要问题年份。",
        "- 正式 walk-forward 里，2022-2025 期间 KDJ strong 对近期改善最强，near_high_60d 其次；soil+industry 也有保护，但强度弱于 KDJ strong。",
        "- 因子差异层面，近期胜负更受大盘/行业 regime、价格位置与种子候选分影响；土壤高分需要和 regime gate 组合使用，不宜单独硬解释胜率。",
        "",
        "## 1. 市场 Regime 归因",
        "",
        "HS300 年度状态：",
        markdown_table(
            annual[annual["year"].between(2021, 2025)],
            ["year", "return_pct", "max_drawdown_pct", "above_ma60_pct", "above_ma120_pct", "regime_label"],
            ["年份", "HS300收益", "最大回撤", "MA60上方占比", "MA120上方占比", "判断"],
        ),
        "",
        "near_high_60d 正式样本按大盘 regime 分组：",
        markdown_table(
            period_regime[period_regime["period"].isin(["2015-2021", "2022-2025"])],
            ["period", "market_regime", "trade_count", "win_rate_pct", "avg_return_pct", "profit_factor"],
            ["时期", "大盘状态", "交易数", "胜率", "平均单笔", "PF"],
        ),
        "",
        "2022-2025 逐年按大盘 regime 分组：",
        markdown_table(
            year_regime,
            ["year", "market_regime", "trade_count", "win_rate_pct", "avg_return_pct", "profit_factor"],
            ["年份", "大盘状态", "交易数", "胜率", "平均单笔", "PF"],
        ),
        "",
        "## 2. 交易结构拆解",
        "",
        "正式 near_high_60d runner 的 MaxHold10 逐年结构：",
        markdown_table(
            recent_structure,
            [
                "year",
                "trade_count",
                "win_rate_pct",
                "avg_return_pct",
                "median_return_pct",
                "avg_win_pct",
                "avg_loss_pct",
                "profit_factor",
                "big_win_rate_pct",
                "big_loss_rate_pct",
                "avg_holding_days",
            ],
            ["年份", "交易数", "胜率", "平均", "中位", "平均盈利", "平均亏损", "PF", "大赚占比", "大亏占比", "持仓天"],
        ),
        "",
        "2022-2025 退出原因结构（MaxHold10）：",
        markdown_table(
            recent_exits,
            ["exit_reason", "trade_count", "trade_share_pct", "avg_return_pct", "profit_factor"],
            ["退出原因", "交易数", "占比", "平均单笔", "PF"],
        ),
        "",
        "## 3. 因子差异诊断",
        "",
        "2022-2025 near_high_60d / Top3 / MaxHold10，盈利交易与亏损交易的数值因子均值差：",
        markdown_table(
            factor_diff,
            ["factor", "coverage_pct", "win_mean", "loss_mean", "win_minus_loss"],
            ["因子", "覆盖率", "盈利均值", "亏损均值", "胜-负"],
        ),
        "",
        "2022-2025 表现较好的分类因子桶（样本数 >= 10，按 PF 排序）：",
        markdown_table(
            factor_cat,
            ["factor", "value", "trade_count", "trade_share_pct", "win_rate_pct", "avg_return_pct", "profit_factor"],
            ["因子", "取值", "交易数", "占比", "胜率", "平均单笔", "PF"],
            max_rows=20,
        ),
        "",
        "## 4. Gate 候选正式验证",
        "",
        "正式 walk-forward Top3 / MaxHold10 对照：",
        markdown_table(
            pd.concat([gate_pre, gate_recent], ignore_index=True),
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
            ["时期", "Gate", "交易数", "年化", "最大回撤", "胜率", "平均单笔", "PF"],
        ),
        "",
        "## 操作建议",
        "",
        "1. 近期风险开关优先级：`hs300_weekly_kdj_strong` > `near_high_60d` > `soil+industry`。",
        "2. `near_high_60d` 适合作为强势确认，但熊市中应被 HS300 regime gate 约束，不能单独放行。",
        "3. `soil+industry` 适合作为候选池质量过滤，不适合作为唯一风控开关。",
        "4. 下一轮应把 `near_high_60d + HS300 regime` 做成正式 runner 配置，和当前 near_high-only 的 MaxHold10 对齐重跑。",
        "",
        "## 产物",
        "",
        f"- `{OUT / 'hs300_regime_by_year.csv'}`",
        f"- `{OUT / 'near_high_market_regime_period_metrics.csv'}`",
        f"- `{OUT / 'near_high_trade_structure_yearly.csv'}`",
        f"- `{OUT / 'near_high_factor_win_loss_diffs.csv'}`",
        f"- `{OUT / 'near_high_factor_bucket_metrics.csv'}`",
        f"- `{OUT / 'formal_gate_validation_focus.csv'}`",
    ]
    (OUT / "near_high_regime_structure_factor_diagnosis.zh.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    hs300_bars, hs300_annual, hs300_periods = load_hs300_regime()
    formal = load_near_high_formal_with_factors()
    period_regime, year_regime = build_market_trade_tables(formal, hs300_bars)
    structure, exits = build_holding_structure()
    factor_diff, factor_cat = build_factor_diagnostics(formal)
    gate_summary = build_gate_validation_summary()

    hs300_annual.to_csv(OUT / "hs300_regime_by_year.csv", index=False, encoding="utf-8-sig")
    hs300_periods.to_csv(OUT / "hs300_regime_by_period.csv", index=False, encoding="utf-8-sig")
    period_regime.to_csv(OUT / "near_high_market_regime_period_metrics.csv", index=False, encoding="utf-8-sig")
    year_regime.to_csv(OUT / "near_high_market_regime_yearly_metrics.csv", index=False, encoding="utf-8-sig")
    structure.to_csv(OUT / "near_high_trade_structure_yearly.csv", index=False, encoding="utf-8-sig")
    exits.to_csv(OUT / "near_high_exit_reason_structure.csv", index=False, encoding="utf-8-sig")
    factor_diff.to_csv(OUT / "near_high_factor_win_loss_diffs.csv", index=False, encoding="utf-8-sig")
    factor_cat.to_csv(OUT / "near_high_factor_bucket_metrics.csv", index=False, encoding="utf-8-sig")
    gate_summary.to_csv(OUT / "formal_gate_validation_focus.csv", index=False, encoding="utf-8-sig")
    write_report(hs300_annual, period_regime, year_regime, structure, exits, factor_diff, factor_cat, gate_summary)
    print(OUT)


if __name__ == "__main__":
    main()
