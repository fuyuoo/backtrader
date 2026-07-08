"""Validate daily top-N candidate ranking from calibrated soil/seed scores."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_CALIBRATION_DIR = Path("reports/score-calibration-hs300-only-2006-2025")
DEFAULT_OUTPUT_DIR = Path("reports/daily-candidate-ranking-validation-hs300-only-2006-2025")

SCORE_COLUMNS = (
    "seed_score_no_industry_v1",
    "seed_v2_candidate_score",
    "calibrated_seed_score",
    "calibrated_total_score",
)
TOP_N_VALUES = (1, 3, 5, 10, 20, 30, 50)
PERIODS = (
    ("full", "全样本", None, None),
    ("2006_2014", "2006-2014", "2006-01-01", "2014-12-31"),
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


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = _load_detail(Path(args.calibration_dir))
    baseline = _baseline_table(df)
    topn = _topn_table(df)
    rank_buckets = _rank_bucket_table(df)
    daily_summary = _daily_summary_table(df)

    baseline_path = output_dir / "daily_ranking_baseline_metrics.csv"
    topn_path = output_dir / "daily_ranking_topn_metrics.csv"
    rank_bucket_path = output_dir / "daily_ranking_bucket_metrics.csv"
    daily_summary_path = output_dir / "daily_ranking_candidate_day_summary.csv"
    metadata_path = output_dir / "daily_ranking_metadata.json"
    markdown_path = output_dir / "daily_ranking_validation.zh.md"

    baseline.to_csv(baseline_path, index=False, encoding="utf-8-sig")
    topn.to_csv(topn_path, index=False, encoding="utf-8-sig")
    rank_buckets.to_csv(rank_bucket_path, index=False, encoding="utf-8-sig")
    daily_summary.to_csv(daily_summary_path, index=False, encoding="utf-8-sig")

    metadata = {
        "schema": "attbacktrader.daily_candidate_ranking_validation.v1",
        "source_calibration_dir": str(args.calibration_dir),
        "candidate_scope_zh": "已完成交易样本中的每日入场候选；不是完整资金撮合组合回测。",
        "ranking_date": "entry_date",
        "score_columns": list(SCORE_COLUMNS),
        "top_n_values": list(TOP_N_VALUES),
        "risk_notes": [
            "calibrated_* 分数来自同一样本校准，存在 in-sample 乐观偏差。",
            "本报告只验证日内排序质量，不模拟持仓上限、现金占用、行业约束和重叠持仓。",
            "下一步应把评分表接入 scored portfolio simulator 做样本外 walk-forward。",
        ],
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(
        _render_markdown(
            baseline=baseline,
            topn=topn,
            rank_buckets=rank_buckets,
            daily_summary=daily_summary,
            artifacts={
                "baseline_metrics": baseline_path,
                "topn_metrics": topn_path,
                "rank_bucket_metrics": rank_bucket_path,
                "candidate_day_summary": daily_summary_path,
                "metadata": metadata_path,
            },
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "trade_count": int(len(df)),
                "candidate_days": int(df["entry_date"].nunique()),
                "analysis_markdown": str(markdown_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate daily candidate ranking Top-N selections")
    parser.add_argument("--calibration-dir", default=str(DEFAULT_CALIBRATION_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args(argv)


def _load_detail(calibration_dir: Path) -> pd.DataFrame:
    path = calibration_dir / "score_calibration_trade_detail.parquet"
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_parquet(path)
    df = df.copy()
    df["entry_date"] = pd.to_datetime(df["entry_date"]).dt.date.astype(str)
    df["exit_date"] = pd.to_datetime(df["exit_date"]).dt.date.astype(str)
    return df


def _baseline_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for period_id, label, start, end in PERIODS:
        period_df = _period_slice(df, start, end)
        rows.append({"period_id": period_id, "period_zh": label, "strategy": "baseline_all", **_stats(period_df)})
    return pd.DataFrame(rows)


def _topn_table(df: pd.DataFrame) -> pd.DataFrame:
    baseline = _baseline_table(df)
    baseline_by_period = {row.period_id: row for row in baseline.itertuples(index=False)}
    rows = []
    for score_col in SCORE_COLUMNS:
        ranked = _rank_by_day(df, score_col)
        for top_n in TOP_N_VALUES:
            selected = ranked[ranked["_daily_rank"] <= top_n]
            for period_id, label, start, end in PERIODS:
                subset = _period_slice(selected, start, end)
                stats = _stats(subset)
                base = baseline_by_period[period_id]
                rows.append(
                    {
                        "score_col": score_col,
                        "top_n": top_n,
                        "period_id": period_id,
                        "period_zh": label,
                        **stats,
                        "trade_count_vs_baseline_pct": _ratio(stats["trade_count"], base.trade_count),
                        "win_rate_lift_pct": _diff(stats["win_rate_pct"], base.win_rate_pct),
                        "avg_return_lift_pct": _diff(stats["avg_return_pct"], base.avg_return_pct),
                        "profit_factor_lift": _diff(stats["profit_factor"], base.profit_factor),
                    }
                )
    return pd.DataFrame(rows).sort_values(["score_col", "top_n", "period_id"])


def _rank_bucket_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for score_col in SCORE_COLUMNS:
        ranked = _rank_by_day(df, score_col)
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
                        **_stats(_period_slice(bucket_df, start, end)),
                    }
                )
    return pd.DataFrame(rows).sort_values(["score_col", "rank_bucket", "period_id"])


def _daily_summary_table(df: pd.DataFrame) -> pd.DataFrame:
    by_day = df.groupby("entry_date").size().rename("candidate_count").reset_index()
    rows = [
        {
            "period_id": period_id,
            "period_zh": label,
            "candidate_days": int(len(period_df)),
            "avg_candidates_per_day": float(period_df["candidate_count"].mean()) if len(period_df) else None,
            "median_candidates_per_day": float(period_df["candidate_count"].median()) if len(period_df) else None,
            "max_candidates_per_day": int(period_df["candidate_count"].max()) if len(period_df) else None,
            "days_gt_5_candidates": int((period_df["candidate_count"] > 5).sum()) if len(period_df) else 0,
            "days_gt_10_candidates": int((period_df["candidate_count"] > 10).sum()) if len(period_df) else 0,
            "days_gt_20_candidates": int((period_df["candidate_count"] > 20).sum()) if len(period_df) else 0,
        }
        for period_id, label, start, end in PERIODS
        for period_df in [_period_slice_by_entry_date(by_day, start, end)]
    ]
    return pd.DataFrame(rows)


def _rank_by_day(df: pd.DataFrame, score_col: str) -> pd.DataFrame:
    ranked = df.copy()
    ranked["_score_for_rank"] = pd.to_numeric(ranked[score_col], errors="coerce").fillna(float("-inf"))
    ranked = ranked.sort_values(
        ["entry_date", "_score_for_rank", "seed_score_no_industry_v1", "symbol", "trade_index"],
        ascending=[True, False, False, True, True],
    )
    ranked["_daily_rank"] = ranked.groupby("entry_date").cumcount() + 1
    ranked["_daily_candidate_count"] = ranked.groupby("entry_date")["symbol"].transform("count")
    ranked["_daily_rank_pct"] = ranked["_daily_rank"] / ranked["_daily_candidate_count"]
    return ranked


def _period_slice(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    dates = pd.to_datetime(df["entry_date"])
    mask = pd.Series(True, index=df.index)
    if start is not None:
        mask &= dates >= pd.Timestamp(start)
    if end is not None:
        mask &= dates <= pd.Timestamp(end)
    return df.loc[mask]


def _period_slice_by_entry_date(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    dates = pd.to_datetime(df["entry_date"])
    mask = pd.Series(True, index=df.index)
    if start is not None:
        mask &= dates >= pd.Timestamp(start)
    if end is not None:
        mask &= dates <= pd.Timestamp(end)
    return df.loc[mask]


def _stats(df: pd.DataFrame) -> dict[str, Any]:
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
        "closed_trade_pnl_max_drawdown": _closed_trade_pnl_drawdown(df),
        "return_sum_max_drawdown_pct": _return_sum_drawdown(df),
    }


def _closed_trade_pnl_drawdown(df: pd.DataFrame) -> float | None:
    if df.empty or "exit_date" not in df or "net_pnl" not in df:
        return None
    daily = pd.to_numeric(df["net_pnl"], errors="coerce").groupby(pd.to_datetime(df["exit_date"])).sum().sort_index()
    cumulative = daily.cumsum()
    drawdown = cumulative - cumulative.cummax()
    return float(drawdown.min()) if len(drawdown) else None


def _return_sum_drawdown(df: pd.DataFrame) -> float | None:
    if df.empty or "exit_date" not in df:
        return None
    returns = pd.to_numeric(df["return_pct"], errors="coerce")
    daily = returns.groupby(pd.to_datetime(df["exit_date"])).sum().sort_index()
    cumulative = daily.cumsum()
    drawdown = cumulative - cumulative.cummax()
    return float(drawdown.min()) if len(drawdown) else None


def _ratio(value: Any, base: Any) -> float | None:
    if base in (None, 0):
        return None
    return float(value) / float(base) * 100


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
    baseline: pd.DataFrame,
    topn: pd.DataFrame,
    rank_buckets: pd.DataFrame,
    daily_summary: pd.DataFrame,
    artifacts: dict[str, Path],
) -> str:
    lines = [
        "# 每日候选池排名验证",
        "",
        "## 口径",
        "",
        "- 以 `entry_date` 为每日候选分组，在当天候选中按分数从高到低排序。",
        "- 本报告只使用已完成交易样本验证排序质量，不模拟现金、持仓上限、行业约束或重叠持仓。",
        "- `calibrated_*` 分数来自阶段 3 同样本校准，因此本报告仍是 in-sample 验证；下一步需要 walk-forward 组合回测。",
        "",
        "## 每日候选数量",
        "",
    ]
    lines.extend(
        _table(
            daily_summary,
            [
                "period_zh",
                "candidate_days",
                "avg_candidates_per_day",
                "median_candidates_per_day",
                "max_candidates_per_day",
                "days_gt_10_candidates",
                "days_gt_20_candidates",
            ],
            limit=20,
        )
    )

    lines.extend(["", "## Baseline", ""])
    lines.extend(
        _table(
            baseline,
            [
                "period_zh",
                "trade_count",
                "candidate_days",
                "win_rate_pct",
                "avg_return_pct",
                "profit_factor",
                "return_sum_max_drawdown_pct",
            ],
            limit=20,
        )
    )

    lines.extend(["", "## TopN 核心对比", ""])
    core = topn[
        (topn["period_id"] == "full")
        & (topn["top_n"].isin([1, 3, 5, 10, 20]))
        & (topn["score_col"].isin(["seed_score_no_industry_v1", "seed_v2_candidate_score", "calibrated_seed_score", "calibrated_total_score"]))
    ].copy()
    lines.extend(
        _table(
            core,
            [
                "score_col",
                "top_n",
                "trade_count",
                "trade_count_vs_baseline_pct",
                "win_rate_pct",
                "avg_return_pct",
                "profit_factor",
                "win_rate_lift_pct",
                "avg_return_lift_pct",
            ],
            limit=80,
        )
    )

    lines.extend(["", "## 分时期 Top10", ""])
    period_top10 = topn[
        (topn["top_n"] == 10)
        & (topn["score_col"].isin(["seed_score_no_industry_v1", "seed_v2_candidate_score", "calibrated_seed_score", "calibrated_total_score"]))
    ].copy()
    lines.extend(
        _table(
            period_top10,
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
            limit=80,
        )
    )

    lines.extend(["", "## 日内排名桶", ""])
    rank_display = rank_buckets[
        (rank_buckets["period_id"] == "full")
        & (rank_buckets["score_col"].isin(["calibrated_seed_score", "calibrated_total_score"]))
    ].copy()
    lines.extend(
        _table(
            rank_display,
            ["score_col", "rank_bucket_zh", "trade_count", "win_rate_pct", "avg_return_pct", "profit_factor"],
            limit=40,
        )
    )

    lines.extend(
        [
            "",
            "## 初步判断",
            "",
            "- 如果 TopN 相对 baseline 的胜率、平均收益、PF 同时改善，说明该分数具备日内排序价值。",
            "- 如果日内第1名、第2-3名、第4-5名不能形成大致递减关系，则该分数更适合 gate，不适合作为精细排名。",
            "- 实战前必须把候选评分接入组合模拟器，加入现金、持仓数、行业分散、同日退出资金复用等约束。",
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
