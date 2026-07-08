from __future__ import annotations

import math
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports" / "seed-v2-candidate-hs300-only-2006-2025" / "seed_v2_candidate_trade_detail.parquet"
INDEX = ROOT / "data" / "snapshots" / "indexes" / "000300_SH_20060101_20251231.parquet"
OUT = ROOT / "reports" / "factor-evidence-scorecard-hs300-only-2006-2025"


NUMERIC_FACTORS: dict[str, tuple[str, str]] = {
    "soil_score_with_industry_v1": ("soil", "含行业土壤分"),
    "soil_score_no_industry_v2": ("soil", "大盘土壤分"),
    "hs300.index_soil_v2_score": ("soil", "HS300 土壤分"),
    "industry_soil_score_v1": ("soil", "行业土壤分"),
    "score_no_industry_v1": ("total", "旧总分"),
    "seed_score_no_industry_v1": ("seed", "旧种子分"),
    "seed_v2_candidate_score": ("seed", "种子 v2 候选分"),
    "seed_v2_liquidity_score": ("seed", "流动性分"),
    "seed_v2_market_cap_score": ("seed", "市值分"),
    "seed_v2_price_position_score": ("seed", "价格位置分"),
    "score_component.symbol.macd.energy_zone": ("seed", "MACD 能量区"),
    "score_component.entry.signal_strength.dea_value_bucket": ("seed", "DEA 值强度"),
    "score_component.entry.signal_strength.dif_dea_distance_bucket": ("seed", "DIF/DEA 距离"),
    "score_component.entry.signal_strength.macd_bar_bucket": ("seed", "MACD 红柱强度"),
    "score_component.market.hs300.weekly.kdj_state": ("soil", "HS300 周线 KDJ 分"),
}


CATEGORICAL_FACTORS: dict[str, tuple[str, str]] = {
    "hs300.weekly_kdj_state": ("soil", "HS300 周线 KDJ 状态"),
    "hs300.ma60_position": ("soil", "HS300 MA60 位置"),
    "hs300.ma_position_bucket": ("soil", "HS300 均线位置桶"),
    "hs300.ma_stack_state": ("soil", "HS300 均线排列"),
    "industry_weekly_kdj_state": ("soil", "行业周线 KDJ 状态"),
    "industry_ma60_position": ("soil", "行业 MA60 位置"),
    "industry_ma_position_bucket": ("soil", "行业均线位置桶"),
    "industry_ma_stack_state": ("soil", "行业均线排列"),
    "entry.liquidity.turnover_rate_bucket": ("seed", "换手率桶"),
    "entry.liquidity.turnover_rate_20d_bucket": ("seed", "20日换手率桶"),
    "entry.liquidity.amount_vs_20d_bucket": ("seed", "成交额相对20日桶"),
    "entry.liquidity.amount_vs_60d_bucket": ("seed", "成交额相对60日桶"),
    "entry.market_cap.total_mv_abs_bucket": ("seed", "总市值桶"),
    "entry.market_cap.circulating_mv_abs_bucket": ("seed", "流通市值桶"),
    "entry.price_position.interval_60d_bucket": ("seed", "60日区间位置桶"),
    "entry.price_position.near_high_60d_bucket": ("seed", "接近60日高点桶"),
    "entry.price_position.signal_close_ma60_atr_multiple_bucket": ("seed", "距MA60 ATR桶"),
}


MARKET_CYCLES = [
    ("2006-2007", "超级牛市", 2006, 2007),
    ("2008", "崩盘熊市", 2008, 2008),
    ("2009", "强反弹", 2009, 2009),
    ("2010-2013", "震荡弱市", 2010, 2013),
    ("2014-2015", "杠杆牛/股灾", 2014, 2015),
    ("2016-2017", "修复/蓝筹强", 2016, 2017),
    ("2018", "去杠杆熊市", 2018, 2018),
    ("2019-2020", "核心资产牛", 2019, 2020),
    ("2021", "高位切换/转弱", 2021, 2021),
    ("2022-2023", "下行熊市", 2022, 2023),
    ("2024-2025", "修复期", 2024, 2025),
]


def max_drawdown_pct(s: pd.Series) -> float:
    s = s.dropna()
    if s.empty:
        return math.nan
    return float((s / s.cummax() - 1.0).min() * 100.0)


def profit_factor(r: pd.Series) -> float:
    r = r.dropna()
    loss = -r[r < 0].sum()
    if loss == 0:
        return math.inf if (r > 0).any() else math.nan
    return float(r[r > 0].sum() / loss)


def spearman(x: pd.Series, y: pd.Series) -> float:
    pair = pd.concat([x, y], axis=1).dropna()
    if len(pair) < 30 or pair.iloc[:, 0].nunique() < 3:
        return math.nan
    return float(pair.iloc[:, 0].rank().corr(pair.iloc[:, 1].rank()))


def high_low_spread_pct(x: pd.Series, y: pd.Series) -> float:
    pair = pd.concat([x, y], axis=1).dropna()
    if len(pair) < 30 or pair.iloc[:, 0].nunique() < 3:
        return math.nan
    factor = pair.iloc[:, 0]
    ret = pair.iloc[:, 1]
    low_cut = factor.quantile(0.30)
    high_cut = factor.quantile(0.70)
    low = ret[factor <= low_cut]
    high = ret[factor >= high_cut]
    if len(low) < 10 or len(high) < 10:
        return math.nan
    return float(high.mean() - low.mean())


def clipped(v: float, lo: float, hi: float) -> float:
    if pd.isna(v):
        return 0.0
    return max(lo, min(hi, float(v)))


def suggested_weight(score: float, median_spread: float, positive_year_share: float) -> float:
    if score >= 75 and median_spread > 0 and positive_year_share >= 70:
        return 2.0
    if score >= 60 and median_spread > 0 and positive_year_share >= 60:
        return 1.0
    if score >= 50 and median_spread > 0:
        return 0.5
    if score <= 35 and median_spread < 0:
        return -0.5
    return 0.0


def conclusion(score: float, weight: float, valid_years: int) -> str:
    if valid_years < 8:
        return "样本年数不足，观察"
    if weight >= 1.5:
        return "强候选，可进入评分"
    if weight > 0:
        return "候选，小权重进入"
    if weight < 0:
        return "负向候选，可作扣分"
    if score >= 45:
        return "证据一般，暂不加权"
    return "暂不采用"


def weak_state_value(factor: str, value: str) -> bool:
    weak_values = {
        "bearish_stack",
        "below_or_equal_ma60",
        "below_ma60",
        "below_ma120",
        "below_ma250",
    }
    return (factor.startswith("hs300.") or factor.startswith("industry_") or factor.startswith("industry.")) and value in weak_values


def load_trades() -> pd.DataFrame:
    df = pd.read_parquet(SOURCE)
    df = df.copy()
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df["year"] = df["entry_date"].dt.year
    df["return_pct"] = pd.to_numeric(df["return_pct"], errors="coerce")
    df["is_win"] = df["return_pct"] > 0
    df = df[df["year"].between(2006, 2025)].copy()
    for period, regime, start, end in MARKET_CYCLES:
        mask = df["year"].between(start, end)
        df.loc[mask, "market_cycle"] = period
        df.loc[mask, "market_cycle_regime"] = regime
    return df


def build_market_context(trades: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    idx = pd.read_parquet(INDEX)
    idx["trade_date"] = pd.to_datetime(idx["trade_date"])
    idx = idx.sort_values("trade_date").drop_duplicates("trade_date")
    idx = idx[(idx["trade_date"] >= "2006-01-01") & (idx["trade_date"] <= "2025-12-31")].copy()
    idx["year"] = idx["trade_date"].dt.year
    idx["ma60"] = idx["close"].rolling(60, min_periods=60).mean()
    idx["above_ma60"] = idx["close"] > idx["ma60"]
    rows = []
    for year, g in idx.groupby("year"):
        t = trades[trades["year"] == year]
        rows.append(
            {
                "year": int(year),
                "hs300_return_pct": float((g.iloc[-1]["close"] / g.iloc[0]["close"] - 1.0) * 100.0),
                "hs300_max_drawdown_pct": max_drawdown_pct(g["close"]),
                "hs300_above_ma60_pct": float(g["above_ma60"].mean() * 100.0),
                "trade_count": len(t),
                "strategy_win_rate_pct": float(t["is_win"].mean() * 100.0) if len(t) else math.nan,
                "strategy_avg_return_pct": float(t["return_pct"].mean()) if len(t) else math.nan,
                "strategy_profit_factor": profit_factor(t["return_pct"]) if len(t) else math.nan,
            }
        )
    yearly = pd.DataFrame(rows)
    cycle_rows = []
    for period, regime, start, end in MARKET_CYCLES:
        g = yearly[yearly["year"].between(start, end)]
        t = trades[trades["year"].between(start, end)]
        idx_g = idx[idx["year"].between(start, end)]
        cycle_rows.append(
            {
                "market_cycle": period,
                "market_cycle_regime": regime,
                "start_year": start,
                "end_year": end,
                "hs300_return_pct": float((idx_g.iloc[-1]["close"] / idx_g.iloc[0]["close"] - 1.0) * 100.0),
                "hs300_max_drawdown_pct": max_drawdown_pct(idx_g["close"]),
                "hs300_above_ma60_pct": float(idx_g["above_ma60"].mean() * 100.0),
                "trade_count": len(t),
                "strategy_win_rate_pct": float(t["is_win"].mean() * 100.0),
                "strategy_avg_return_pct": float(t["return_pct"].mean()),
                "strategy_profit_factor": profit_factor(t["return_pct"]),
            }
        )
    return yearly, pd.DataFrame(cycle_rows)


def numeric_annual_metrics(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for factor, (domain, label) in NUMERIC_FACTORS.items():
        if factor not in trades.columns:
            continue
        for year, g in trades.groupby("year"):
            x = pd.to_numeric(g[factor], errors="coerce")
            r = g["return_pct"]
            coverage = float(x.notna().mean() * 100.0)
            rows.append(
                {
                    "factor": factor,
                    "factor_label_zh": label,
                    "domain": domain,
                    "year": int(year),
                    "trade_count": len(g),
                    "coverage_pct": coverage,
                    "unique_value_count": int(x.nunique(dropna=True)),
                    "spearman_ic": spearman(x, r),
                    "top30_minus_bottom30_return_pct": high_low_spread_pct(x, r),
                    "win_mean": float(x[g["is_win"]].mean()) if x[g["is_win"]].notna().any() else math.nan,
                    "loss_mean": float(x[~g["is_win"]].mean()) if x[~g["is_win"]].notna().any() else math.nan,
                    "win_minus_loss": float(x[g["is_win"]].mean() - x[~g["is_win"]].mean())
                    if x[g["is_win"]].notna().any() and x[~g["is_win"]].notna().any()
                    else math.nan,
                }
            )
    return pd.DataFrame(rows)


def numeric_cycle_metrics(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for factor, (domain, label) in NUMERIC_FACTORS.items():
        if factor not in trades.columns:
            continue
        for (cycle, regime), g in trades.groupby(["market_cycle", "market_cycle_regime"], sort=False):
            x = pd.to_numeric(g[factor], errors="coerce")
            r = g["return_pct"]
            rows.append(
                {
                    "factor": factor,
                    "factor_label_zh": label,
                    "domain": domain,
                    "market_cycle": cycle,
                    "market_cycle_regime": regime,
                    "trade_count": len(g),
                    "coverage_pct": float(x.notna().mean() * 100.0),
                    "spearman_ic": spearman(x, r),
                    "top30_minus_bottom30_return_pct": high_low_spread_pct(x, r),
                }
            )
    return pd.DataFrame(rows)


def build_numeric_scorecard(annual: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    available = [f for f in NUMERIC_FACTORS if f in trades.columns]
    corr = trades[available].apply(pd.to_numeric, errors="coerce").rank().corr().abs()
    for factor, g in annual.groupby("factor"):
        valid = g[g["coverage_pct"] >= 80].copy()
        valid = valid[valid["top30_minus_bottom30_return_pct"].notna() | valid["spearman_ic"].notna()]
        if valid.empty:
            continue
        positive_year = (valid["top30_minus_bottom30_return_pct"].fillna(0) > 0) & (
            valid["spearman_ic"].fillna(0) > -0.02
        )
        recent = valid[valid["year"].between(2021, 2025)]
        cycle_positive = []
        for _, _, start, end in MARKET_CYCLES:
            yg = valid[valid["year"].between(start, end)]
            if len(yg):
                cycle_positive.append(float(yg["top30_minus_bottom30_return_pct"].median()) > 0)

        coverage_score = clipped(valid["coverage_pct"].median() / 95.0, 0, 1) * 20
        direction_score = positive_year.mean() * 25
        cycle_score = (sum(cycle_positive) / len(cycle_positive) * 20) if cycle_positive else 0
        median_spread = float(valid["top30_minus_bottom30_return_pct"].median())
        effect_score = clipped(median_spread / 2.0, 0, 1) * 15
        recent_score = (
            ((recent["top30_minus_bottom30_return_pct"].fillna(0) > 0) & (recent["spearman_ic"].fillna(0) > -0.02)).mean()
            * 10
            if len(recent)
            else 0
        )
        sample_score = clipped(len(valid) / 20.0, 0, 1) * 10
        peer_corr = corr[factor].drop(labels=[factor], errors="ignore").max() if factor in corr else math.nan
        redundancy_penalty = 10 if peer_corr >= 0.85 else 5 if peer_corr >= 0.70 else 0
        score = coverage_score + direction_score + cycle_score + effect_score + recent_score + sample_score - redundancy_penalty
        weight = suggested_weight(score, median_spread, positive_year.mean() * 100.0)
        first = g.iloc[0]
        conclusion_text = conclusion(score, weight, len(valid))
        if factor in {"score_no_industry_v1", "seed_score_no_industry_v1"}:
            weight = 0.0
            conclusion_text = "旧版/复合参考，不重复加权"
        elif peer_corr >= 0.90 and weight > 0:
            weight = 0.0
            conclusion_text = "与已有分高度重复，暂不重复加权"
        rows.append(
            {
                "factor": factor,
                "factor_label_zh": first["factor_label_zh"],
                "domain": first["domain"],
                "evidence_score": round(score, 2),
                "suggested_weight": weight,
                "coverage_median_pct": round(float(valid["coverage_pct"].median()), 2),
                "valid_years": int(len(valid)),
                "positive_year_share_pct": round(float(positive_year.mean() * 100.0), 2),
                "positive_cycle_share_pct": round(float(sum(cycle_positive) / len(cycle_positive) * 100.0), 2)
                if cycle_positive
                else math.nan,
                "median_annual_ic": round(float(valid["spearman_ic"].median()), 4),
                "median_high_low_spread_pct": round(median_spread, 4),
                "recent_positive_year_share_pct": round(float(recent_score), 2),
                "max_abs_peer_corr": round(float(peer_corr), 4) if not pd.isna(peer_corr) else math.nan,
                "redundancy_penalty": redundancy_penalty,
                "conclusion": conclusion_text,
            }
        )
    return pd.DataFrame(rows).sort_values(["evidence_score", "median_high_low_spread_pct"], ascending=False)


def categorical_value_scorecard(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    yearly_base = trades.groupby("year").agg(year_avg_return=("return_pct", "mean"), year_win=("is_win", "mean"))
    for factor, (domain, label) in CATEGORICAL_FACTORS.items():
        if factor not in trades.columns:
            continue
        work = trades[[factor, "year", "return_pct", "is_win"]].copy()
        work[factor] = work[factor].fillna("missing").astype(str)
        total_count = len(work)
        for value, vg in work.groupby(factor):
            if len(vg) < 80:
                continue
            annual_rows = []
            for year, yg in vg.groupby("year"):
                if len(yg) < 10 or year not in yearly_base.index:
                    continue
                annual_rows.append(
                    {
                        "year": year,
                        "sample_count": len(yg),
                        "avg_return_lift_pct": yg["return_pct"].mean() - yearly_base.loc[year, "year_avg_return"],
                        "win_rate_lift_pct": (yg["is_win"].mean() - yearly_base.loc[year, "year_win"]) * 100.0,
                    }
                )
            if len(annual_rows) < 5:
                continue
            annual = pd.DataFrame(annual_rows)
            positive_share = float((annual["avg_return_lift_pct"] > 0).mean() * 100.0)
            median_lift = float(annual["avg_return_lift_pct"].median())
            sample_share = len(vg) / total_count * 100.0
            coverage_score = clipped(sample_share / 20.0, 0, 1) * 20
            stability_score = positive_share / 100.0 * 35
            effect_score = clipped(median_lift / 1.5, 0, 1) * 25
            year_score = clipped(len(annual) / 20.0, 0, 1) * 10
            recent = annual[annual["year"].between(2021, 2025)]
            recent_score = float((recent["avg_return_lift_pct"] > 0).mean() * 10.0) if len(recent) else 0
            score = coverage_score + stability_score + effect_score + year_score + recent_score
            weight = suggested_weight(score, median_lift, positive_share)
            conclusion_text = conclusion(score, weight, len(annual))
            if len(annual) < 8:
                weight = 0.0
                conclusion_text = "样本年数不足，观察"
            elif weak_state_value(factor, value):
                weight = 0.0
                conclusion_text = "弱市状态仅作分层，不直接加分"
            rows.append(
                {
                    "factor": factor,
                    "factor_label_zh": label,
                    "value": value,
                    "domain": domain,
                    "evidence_score": round(score, 2),
                    "suggested_weight": weight,
                    "sample_count": int(len(vg)),
                    "sample_share_pct": round(sample_share, 2),
                    "valid_years": int(len(annual)),
                    "positive_year_share_pct": round(positive_share, 2),
                    "median_return_lift_pct": round(median_lift, 4),
                    "median_win_rate_lift_pct": round(float(annual["win_rate_lift_pct"].median()), 4),
                    "conclusion": conclusion_text,
                }
            )
    return pd.DataFrame(rows).sort_values(["evidence_score", "median_return_lift_pct"], ascending=False)


def fmt(v: object, digits: int = 2) -> str:
    if isinstance(v, float):
        if math.isinf(v):
            return "inf"
        if pd.isna(v):
            return ""
        return f"{v:.{digits}f}"
    return str(v)


def markdown_table(df: pd.DataFrame, cols: list[str], headers: list[str], n: int | None = None) -> str:
    view = df[cols].head(n) if n else df[cols]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in view.iterrows():
        lines.append("| " + " | ".join(fmt(row[c]) for c in cols) + " |")
    return "\n".join(lines)


def write_report(
    yearly_context: pd.DataFrame,
    cycle_context: pd.DataFrame,
    numeric_scorecard: pd.DataFrame,
    categorical_scorecard: pd.DataFrame,
) -> None:
    positive_numeric = numeric_scorecard[numeric_scorecard["suggested_weight"] > 0]
    positive_cat = categorical_scorecard[categorical_scorecard["suggested_weight"] > 0]
    lines = [
        "# 因子证据评分 Roadmap 年度版",
        "",
        "## 口径",
        "",
        "- 因子证据以年度为原子样本，不再使用 `2006-2014 / 2015-2021 / 2022-2025` 三段式做主判断。",
        "- 市场周期只用于解释稳定性，不用于直接调权重。",
        "- 评分目标是找稳定正向因子进入 seed/soil 打分，不是寻找某段收益最优 gate。",
        "",
        "## 年份切分建议",
        "",
        markdown_table(
            cycle_context,
            [
                "market_cycle",
                "market_cycle_regime",
                "hs300_return_pct",
                "hs300_max_drawdown_pct",
                "trade_count",
                "strategy_avg_return_pct",
                "strategy_profit_factor",
            ],
            ["年份", "市场状态", "HS300收益", "HS300回撤", "交易数", "策略平均单笔", "策略PF"],
        ),
        "",
        "## 数值因子证据评分",
        "",
        markdown_table(
            numeric_scorecard,
            [
                "factor_label_zh",
                "domain",
                "evidence_score",
                "suggested_weight",
                "valid_years",
                "positive_year_share_pct",
                "median_high_low_spread_pct",
                "max_abs_peer_corr",
                "conclusion",
            ],
            ["因子", "归属", "证据分", "建议权重", "有效年数", "正向年占比", "高低分差", "最高相关", "结论"],
            16,
        ),
        "",
        "## 分类因子取值证据评分",
        "",
        markdown_table(
            categorical_scorecard,
            [
                "factor_label_zh",
                "value",
                "domain",
                "evidence_score",
                "suggested_weight",
                "sample_count",
                "positive_year_share_pct",
                "median_return_lift_pct",
                "conclusion",
            ],
            ["因子", "取值", "归属", "证据分", "建议权重", "样本", "正向年占比", "收益提升", "结论"],
            20,
        ),
        "",
        "## 推荐进入下一版打分的候选",
        "",
        markdown_table(
            positive_numeric,
            ["factor_label_zh", "domain", "evidence_score", "suggested_weight", "conclusion"],
            ["数值因子", "归属", "证据分", "建议权重", "结论"],
        )
        if len(positive_numeric)
        else "暂无数值因子达到加权阈值。",
        "",
        markdown_table(
            positive_cat,
            ["factor_label_zh", "value", "domain", "evidence_score", "suggested_weight", "conclusion"],
            ["分类因子", "取值", "归属", "证据分", "建议权重", "结论"],
        )
        if len(positive_cat)
        else "暂无分类因子取值达到加权阈值。",
        "",
        "## 下一步",
        "",
        "1. 用本表建议权重生成 `seed/soil score v2 evidence-weighted`。",
        "2. 只验证排名能力：每日 Top1/Top3/Top5、MaxHold10/20，不再优化单个 gate。",
        "3. Walk-forward 中只允许使用训练年内的因子证据分，测试年只验证，不参与调权。",
        "",
        "## 产物",
        "",
        f"- `{OUT / 'factor_evidence_scorecard.zh.md'}`",
        f"- `{OUT / 'numeric_factor_scorecard.csv'}`",
        f"- `{OUT / 'numeric_factor_annual_metrics.csv'}`",
        f"- `{OUT / 'numeric_factor_cycle_metrics.csv'}`",
        f"- `{OUT / 'categorical_factor_value_scorecard.csv'}`",
        f"- `{OUT / 'market_cycle_context.csv'}`",
        f"- `{OUT / 'yearly_strategy_market_context.csv'}`",
    ]
    (OUT / "factor_evidence_scorecard.zh.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    trades = load_trades()
    yearly_context, cycle_context = build_market_context(trades)
    annual = numeric_annual_metrics(trades)
    cycle = numeric_cycle_metrics(trades)
    numeric_scorecard = build_numeric_scorecard(annual, trades)
    categorical_scorecard = categorical_value_scorecard(trades)

    yearly_context.to_csv(OUT / "yearly_strategy_market_context.csv", index=False, encoding="utf-8-sig")
    cycle_context.to_csv(OUT / "market_cycle_context.csv", index=False, encoding="utf-8-sig")
    annual.to_csv(OUT / "numeric_factor_annual_metrics.csv", index=False, encoding="utf-8-sig")
    cycle.to_csv(OUT / "numeric_factor_cycle_metrics.csv", index=False, encoding="utf-8-sig")
    numeric_scorecard.to_csv(OUT / "numeric_factor_scorecard.csv", index=False, encoding="utf-8-sig")
    categorical_scorecard.to_csv(OUT / "categorical_factor_value_scorecard.csv", index=False, encoding="utf-8-sig")
    write_report(yearly_context, cycle_context, numeric_scorecard, categorical_scorecard)
    print(OUT)


if __name__ == "__main__":
    main()
