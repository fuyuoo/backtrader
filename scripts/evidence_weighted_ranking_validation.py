"""Walk-forward ranking validation for evidence-weighted seed/soil scores."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_factor_evidence_scorecard as evidence  # noqa: E402


OUTPUT_DIR = ROOT / "reports" / "evidence-weighted-ranking-validation-hs300-only-2006-2025"
FIRST_TEST_YEAR = 2013
LAST_TEST_YEAR = 2025
TRAIN_START_YEAR = 2006
TOP_N_VALUES = (1, 3, 5, 10, 20)
PERIODS = (
    ("walk_forward_full", "Walk-forward 2013-2025", "2013-01-01", "2025-12-31"),
    ("2013_2014", "2013-2014", "2013-01-01", "2014-12-31"),
    ("2015_2021", "2015-2021", "2015-01-01", "2021-12-31"),
    ("2022_2025", "2022-2025", "2022-01-01", "2025-12-31"),
)
RANK_BUCKETS = (
    ("rank_1", "日内第1名", 1, 1),
    ("rank_2_3", "日内第2-3名", 2, 3),
    ("rank_4_5", "日内第4-5名", 4, 5),
    ("rank_6_10", "日内第6-10名", 6, 10),
    ("rank_gt_10", "日内10名后", 11, None),
)
SCORE_COLUMNS = (
    "seed_score_no_industry_v1",
    "seed_v2_candidate_score",
    "ew_seed_only_score",
    "ew_seed_soil_score",
)
REFERENCE_ONLY_NUMERIC = {"score_no_industry_v1", "seed_score_no_industry_v1"}


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    trades = evidence.load_trades()
    scored, fold_rows, weight_rows = build_walk_forward_scores(trades)

    baseline = baseline_table(scored)
    topn = topn_table(scored, baseline)
    buckets = rank_bucket_table(scored)
    daily_summary = daily_summary_table(scored)

    scored_path = OUTPUT_DIR / "evidence_weighted_scored_trade_detail.parquet"
    fold_path = OUTPUT_DIR / "evidence_weighted_fold_summary.csv"
    weights_path = OUTPUT_DIR / "evidence_weighted_fold_weights.csv"
    baseline_path = OUTPUT_DIR / "evidence_weighted_baseline_metrics.csv"
    topn_path = OUTPUT_DIR / "evidence_weighted_topn_metrics.csv"
    bucket_path = OUTPUT_DIR / "evidence_weighted_rank_bucket_metrics.csv"
    daily_path = OUTPUT_DIR / "evidence_weighted_candidate_day_summary.csv"
    metadata_path = OUTPUT_DIR / "evidence_weighted_metadata.json"
    markdown_path = OUTPUT_DIR / "evidence_weighted_ranking_validation.zh.md"

    scored.to_parquet(scored_path, index=False)
    pd.DataFrame(fold_rows).to_csv(fold_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(weight_rows).to_csv(weights_path, index=False, encoding="utf-8-sig")
    baseline.to_csv(baseline_path, index=False, encoding="utf-8-sig")
    topn.to_csv(topn_path, index=False, encoding="utf-8-sig")
    buckets.to_csv(bucket_path, index=False, encoding="utf-8-sig")
    daily_summary.to_csv(daily_path, index=False, encoding="utf-8-sig")

    metadata = {
        "schema": "attbacktrader.evidence_weighted_ranking_validation.v1",
        "roadmap_check": "年度原子样本 -> evidence-weighted seed/soil score -> walk-forward 排名验证；未改策略，未接实盘，未优化 gate。",
        "source_trade_detail": str(evidence.SOURCE),
        "first_test_year": FIRST_TEST_YEAR,
        "last_test_year": LAST_TEST_YEAR,
        "train_start_year": TRAIN_START_YEAR,
        "score_columns": list(SCORE_COLUMNS),
        "top_n_values": list(TOP_N_VALUES),
        "notes": [
            "每个测试年只使用测试年前训练样本生成 evidence weights。",
            "数值因子按训练样本分位数映射到 0-1 后加权，降低量纲影响。",
            "分类因子只对训练期 evidence scorecard 中 suggested_weight 非零的取值加分。",
            "本报告验证日内排名质量，不模拟资金、持仓上限或完整 K 线撮合。",
        ],
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(
        render_markdown(
            baseline=baseline,
            topn=topn,
            buckets=buckets,
            daily_summary=daily_summary,
            fold_summary=pd.DataFrame(fold_rows),
            artifacts={
                "scored_trade_detail": scored_path,
                "fold_summary": fold_path,
                "fold_weights": weights_path,
                "baseline_metrics": baseline_path,
                "topn_metrics": topn_path,
                "rank_bucket_metrics": bucket_path,
                "candidate_day_summary": daily_path,
                "metadata": metadata_path,
            },
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "output_dir": str(OUTPUT_DIR),
                "trade_count": int(len(scored)),
                "candidate_days": int(scored["entry_date"].nunique()),
                "analysis_markdown": str(markdown_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def build_walk_forward_scores(trades: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]]]:
    scored_parts: list[pd.DataFrame] = []
    fold_rows: list[dict[str, Any]] = []
    weight_rows: list[dict[str, Any]] = []
    for test_year in range(FIRST_TEST_YEAR, LAST_TEST_YEAR + 1):
        train = trades[(trades["year"] >= TRAIN_START_YEAR) & (trades["year"] < test_year)].copy()
        test = trades[trades["year"] == test_year].copy()
        if train.empty or test.empty:
            continue

        numeric_weights, categorical_weights, fold_weight_rows = fit_fold_weights(train, test_year)
        scored = score_test_fold(test, train, numeric_weights, categorical_weights)
        scored["fold_id"] = f"train_{TRAIN_START_YEAR}_{test_year - 1}_test_{test_year}"
        scored["train_start_year"] = TRAIN_START_YEAR
        scored["train_end_year"] = test_year - 1
        scored["test_year"] = test_year
        scored_parts.append(scored)
        weight_rows.extend(fold_weight_rows)
        fold_rows.append(
            {
                "fold_id": scored["fold_id"].iloc[0],
                "train_start_year": TRAIN_START_YEAR,
                "train_end_year": test_year - 1,
                "test_year": test_year,
                "train_trade_count": int(len(train)),
                "test_trade_count": int(len(test)),
                "seed_numeric_weight_count": sum(1 for w in numeric_weights if w["domain"] == "seed"),
                "soil_numeric_weight_count": sum(1 for w in numeric_weights if w["domain"] == "soil"),
                "seed_categorical_weight_count": sum(1 for w in categorical_weights if w["domain"] == "seed"),
                "soil_categorical_weight_count": sum(1 for w in categorical_weights if w["domain"] == "soil"),
            }
        )
    if not scored_parts:
        raise RuntimeError("No walk-forward folds produced")
    return pd.concat(scored_parts, ignore_index=True), fold_rows, weight_rows


def fit_fold_weights(train: pd.DataFrame, test_year: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    annual = evidence.numeric_annual_metrics(train)
    numeric = evidence.build_numeric_scorecard(annual, train)
    categorical = evidence.categorical_value_scorecard(train)

    numeric_rows: list[dict[str, Any]] = []
    for row in numeric.to_dict("records"):
        weight = float(row.get("suggested_weight") or 0.0)
        factor = row["factor"]
        if weight == 0 or factor in REFERENCE_ONLY_NUMERIC:
            continue
        if factor not in train.columns:
            continue
        numeric_rows.append(
            {
                "test_year": test_year,
                "weight_type": "numeric",
                "domain": row["domain"],
                "factor": factor,
                "value": "",
                "weight": weight,
                "evidence_score": row["evidence_score"],
                "conclusion": row["conclusion"],
            }
        )

    categorical_rows: list[dict[str, Any]] = []
    for row in categorical.to_dict("records"):
        weight = float(row.get("suggested_weight") or 0.0)
        if weight == 0 or row["factor"] not in train.columns:
            continue
        categorical_rows.append(
            {
                "test_year": test_year,
                "weight_type": "categorical",
                "domain": row["domain"],
                "factor": row["factor"],
                "value": str(row["value"]),
                "weight": weight,
                "evidence_score": row["evidence_score"],
                "conclusion": row["conclusion"],
            }
        )
    return numeric_rows, categorical_rows, numeric_rows + categorical_rows


def score_test_fold(
    test: pd.DataFrame,
    train: pd.DataFrame,
    numeric_weights: list[dict[str, Any]],
    categorical_weights: list[dict[str, Any]],
) -> pd.DataFrame:
    scored = test.copy()
    scored["ew_seed_only_score"] = 0.0
    scored["ew_seed_soil_score"] = 0.0

    for weight_row in numeric_weights:
        factor = weight_row["factor"]
        weight = float(weight_row["weight"])
        domain = weight_row["domain"]
        train_values = pd.to_numeric(train[factor], errors="coerce").dropna().sort_values().to_numpy()
        if len(train_values) < 30:
            continue
        pct = pd.to_numeric(scored[factor], errors="coerce").map(lambda x: percentile_rank(train_values, x))
        contribution = pct.fillna(0.0) * weight
        if domain == "seed":
            scored["ew_seed_only_score"] += contribution
            scored["ew_seed_soil_score"] += contribution
        elif domain == "soil":
            scored["ew_seed_soil_score"] += contribution

    for weight_row in categorical_weights:
        factor = weight_row["factor"]
        weight = float(weight_row["weight"])
        domain = weight_row["domain"]
        value = str(weight_row["value"])
        contribution = (scored[factor].fillna("missing").astype(str) == value).astype(float) * weight
        if domain == "seed":
            scored["ew_seed_only_score"] += contribution
            scored["ew_seed_soil_score"] += contribution
        elif domain == "soil":
            scored["ew_seed_soil_score"] += contribution
    return scored


def percentile_rank(sorted_values: Any, value: Any) -> float | None:
    if pd.isna(value):
        return None
    import bisect

    n = len(sorted_values)
    if n == 0:
        return None
    pos = bisect.bisect_right(sorted_values, float(value))
    return pos / n


def baseline_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for period_id, label, start, end in PERIODS:
        period_df = period_slice(df, start, end)
        rows.append({"period_id": period_id, "period_zh": label, "strategy": "baseline_all", **stats(period_df)})
    return pd.DataFrame(rows)


def topn_table(df: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    baseline_by_period = {row.period_id: row for row in baseline.itertuples(index=False)}
    rows = []
    for score_col in SCORE_COLUMNS:
        ranked = rank_by_day(df, score_col)
        for top_n in TOP_N_VALUES:
            selected = ranked[ranked["_daily_rank"] <= top_n]
            for period_id, label, start, end in PERIODS:
                subset = period_slice(selected, start, end)
                stat = stats(subset)
                base = baseline_by_period[period_id]
                rows.append(
                    {
                        "score_col": score_col,
                        "top_n": top_n,
                        "period_id": period_id,
                        "period_zh": label,
                        **stat,
                        "trade_count_vs_baseline_pct": ratio(stat["trade_count"], base.trade_count),
                        "win_rate_lift_pct": diff(stat["win_rate_pct"], base.win_rate_pct),
                        "avg_return_lift_pct": diff(stat["avg_return_pct"], base.avg_return_pct),
                        "profit_factor_lift": diff(stat["profit_factor"], base.profit_factor),
                    }
                )
    return pd.DataFrame(rows).sort_values(["score_col", "top_n", "period_id"])


def rank_bucket_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for score_col in SCORE_COLUMNS:
        ranked = rank_by_day(df, score_col)
        for bucket_id, bucket_zh, low, high in RANK_BUCKETS:
            if high is None:
                bucket_df = ranked[ranked["_daily_rank"] >= low]
            else:
                bucket_df = ranked[(ranked["_daily_rank"] >= low) & (ranked["_daily_rank"] <= high)]
            for period_id, label, start, end in PERIODS:
                rows.append(
                    {
                        "score_col": score_col,
                        "rank_bucket": bucket_id,
                        "rank_bucket_zh": bucket_zh,
                        "period_id": period_id,
                        "period_zh": label,
                        **stats(period_slice(bucket_df, start, end)),
                    }
                )
    return pd.DataFrame(rows).sort_values(["score_col", "rank_bucket", "period_id"])


def daily_summary_table(df: pd.DataFrame) -> pd.DataFrame:
    by_day = df.groupby("entry_date").size().rename("candidate_count").reset_index()
    rows = []
    for period_id, label, start, end in PERIODS:
        period_df = period_slice(by_day, start, end)
        rows.append(
            {
                "period_id": period_id,
                "period_zh": label,
                "candidate_days": int(len(period_df)),
                "avg_candidates_per_day": float(period_df["candidate_count"].mean()) if len(period_df) else None,
                "median_candidates_per_day": float(period_df["candidate_count"].median()) if len(period_df) else None,
                "max_candidates_per_day": int(period_df["candidate_count"].max()) if len(period_df) else None,
                "days_gt_10_candidates": int((period_df["candidate_count"] > 10).sum()) if len(period_df) else 0,
                "days_gt_20_candidates": int((period_df["candidate_count"] > 20).sum()) if len(period_df) else 0,
            }
        )
    return pd.DataFrame(rows)


def rank_by_day(df: pd.DataFrame, score_col: str) -> pd.DataFrame:
    ranked = df.copy()
    ranked["_score_for_rank"] = pd.to_numeric(ranked[score_col], errors="coerce").fillna(float("-inf"))
    tie_cols = [c for c in ["seed_v2_candidate_score", "seed_score_no_industry_v1"] if c in ranked.columns]
    ranked = ranked.sort_values(
        ["entry_date", "_score_for_rank", *tie_cols, "symbol", "trade_index"],
        ascending=[True, False, *([False] * len(tie_cols)), True, True],
    )
    ranked["_daily_rank"] = ranked.groupby("entry_date").cumcount() + 1
    ranked["_daily_candidate_count"] = ranked.groupby("entry_date")["symbol"].transform("count")
    return ranked


def period_slice(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    dates = pd.to_datetime(df["entry_date"])
    mask = pd.Series(True, index=df.index)
    if start is not None:
        mask &= dates >= pd.Timestamp(start)
    if end is not None:
        mask &= dates <= pd.Timestamp(end)
    return df.loc[mask]


def stats(df: pd.DataFrame) -> dict[str, Any]:
    returns = pd.to_numeric(df["return_pct"], errors="coerce").dropna()
    wins = returns[returns > 0]
    net_pnl = pd.to_numeric(df.get("net_pnl"), errors="coerce").dropna() if "net_pnl" in df else pd.Series(dtype=float)
    pnl_wins = net_pnl[net_pnl > 0]
    pnl_losses = net_pnl[net_pnl < 0]
    return {
        "trade_count": int(len(df)),
        "candidate_days": int(df["entry_date"].nunique()) if "entry_date" in df else 0,
        "avg_selected_per_day": float(len(df) / df["entry_date"].nunique()) if len(df) and "entry_date" in df else None,
        "win_rate_pct": float(len(wins) / len(returns) * 100) if len(returns) else None,
        "avg_return_pct": float(returns.mean()) if len(returns) else None,
        "median_return_pct": float(returns.median()) if len(returns) else None,
        "profit_factor": float(pnl_wins.sum() / abs(pnl_losses.sum())) if len(pnl_losses) and abs(pnl_losses.sum()) > 0 else None,
        "return_sum_pct": float(returns.sum()) if len(returns) else None,
        "net_pnl_sum": float(net_pnl.sum()) if len(net_pnl) else None,
        "return_sum_max_drawdown_pct": return_sum_drawdown(df),
    }


def return_sum_drawdown(df: pd.DataFrame) -> float | None:
    if df.empty or "exit_date" not in df:
        return None
    returns = pd.to_numeric(df["return_pct"], errors="coerce")
    daily = returns.groupby(pd.to_datetime(df["exit_date"])).sum().sort_index()
    cumulative = daily.cumsum()
    drawdown = cumulative - cumulative.cummax()
    return float(drawdown.min()) if len(drawdown) else None


def ratio(value: Any, base: Any) -> float | None:
    if base in (None, 0):
        return None
    return float(value) / float(base) * 100


def diff(value: Any, base: Any) -> float | None:
    if value is None or base is None or pd.isna(value) or pd.isna(base):
        return None
    return float(value) - float(base)


def render_markdown(
    *,
    baseline: pd.DataFrame,
    topn: pd.DataFrame,
    buckets: pd.DataFrame,
    daily_summary: pd.DataFrame,
    fold_summary: pd.DataFrame,
    artifacts: dict[str, Path],
) -> str:
    full_top = topn[
        (topn["period_id"] == "walk_forward_full")
        & (topn["top_n"].isin([1, 3, 5, 10, 20]))
        & (topn["score_col"].isin(["seed_v2_candidate_score", "ew_seed_only_score", "ew_seed_soil_score"]))
    ]
    period_top3 = topn[
        (topn["top_n"] == 3)
        & (topn["score_col"].isin(["seed_v2_candidate_score", "ew_seed_only_score", "ew_seed_soil_score"]))
    ]
    bucket_full = buckets[
        (buckets["period_id"] == "walk_forward_full")
        & (buckets["score_col"].isin(["ew_seed_only_score", "ew_seed_soil_score"]))
    ]
    lines = [
        "# Evidence-weighted Seed/Soil 离线排名验证",
        "",
        "## Roadmap 对照",
        "",
        "- 本报告属于 `因子证据评分 -> seed/soil score v2 -> 离线排名验证`。",
        "- 没有改策略、没有接实盘、没有继续优化 gate。",
        "- 每个测试年只使用此前训练年份生成 evidence weights，测试年只验证排名。",
        "",
        "## 每日候选数量",
        "",
        *table(daily_summary, ["period_zh", "candidate_days", "avg_candidates_per_day", "median_candidates_per_day", "max_candidates_per_day"], 20),
        "",
        "## Baseline",
        "",
        *table(baseline, ["period_zh", "trade_count", "candidate_days", "win_rate_pct", "avg_return_pct", "profit_factor"], 20),
        "",
        "## Walk-forward TopN 核心对比",
        "",
        *table(
            full_top,
            [
                "score_col",
                "top_n",
                "trade_count",
                "win_rate_pct",
                "avg_return_pct",
                "profit_factor",
                "win_rate_lift_pct",
                "avg_return_lift_pct",
            ],
            60,
        ),
        "",
        "## 分时期 Top3",
        "",
        *table(
            period_top3,
            [
                "score_col",
                "period_zh",
                "trade_count",
                "win_rate_pct",
                "avg_return_pct",
                "profit_factor",
                "win_rate_lift_pct",
                "avg_return_lift_pct",
            ],
            80,
        ),
        "",
        "## 日内排名桶",
        "",
        *table(bucket_full, ["score_col", "rank_bucket_zh", "trade_count", "win_rate_pct", "avg_return_pct", "profit_factor"], 40),
        "",
        "## Fold 权重概况",
        "",
        *table(fold_summary, ["test_year", "train_trade_count", "test_trade_count", "seed_numeric_weight_count", "soil_numeric_weight_count", "seed_categorical_weight_count", "soil_categorical_weight_count"], 30),
        "",
        "## 判断规则",
        "",
        "- 如果 `ew_seed_soil_score` 稳定优于 `ew_seed_only_score`，土壤进入正式评分。",
        "- 如果 soil 只在个别年份好，土壤只保留为环境解释或仓位调节，不进入选股排名主分。",
        "- 如果 evidence-weighted 分数没有优于 `seed_v2_candidate_score`，说明当前权重生成方式还需要收紧。",
        "",
        "## 产物",
        "",
        *[f"- `{name}`: `{path}`" for name, path in artifacts.items()],
    ]
    return "\n".join(lines)


def table(df: pd.DataFrame, columns: list[str], limit: int) -> list[str]:
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for _, row in df.head(limit)[columns].iterrows():
        lines.append("| " + " | ".join(fmt(row[col]) for col in columns) + " |")
    return lines


def fmt(value: Any) -> str:
    if value is None:
        return "-"
    try:
        if pd.isna(value):
            return "-"
    except (TypeError, ValueError):
        pass
    if isinstance(value, float):
        if math.isinf(value):
            return "inf"
        return f"{value:.4f}"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
