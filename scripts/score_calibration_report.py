"""Calibrate offline soil/seed scores from existing HS300-only trade artifacts."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

import seed_v2_candidate_report as seed_v2


DEFAULT_SEED_V2_DIR = Path("reports/seed-v2-candidate-hs300-only-2006-2025")
DEFAULT_OUTPUT_DIR = Path("reports/score-calibration-hs300-only-2006-2025")

PERIODS = (
    ("full", "全样本", None, None),
    ("2006_2014", "2006-2014", "2006-01-01", "2014-12-31"),
    ("2015_2021", "2015-2021", "2015-01-01", "2021-12-31"),
    ("2022_2025", "2022-2025", "2022-01-01", "2025-12-31"),
)

FIELD_GROUPS: dict[str, dict[str, Any]] = {
    "seed_macd": {
        "label_zh": "种子-MACD信号",
        "fields": (
            "category.symbol.macd.energy_zone",
            "category.entry.signal_strength.dea_value_bucket",
            "category.entry.signal_strength.dif_dea_distance_bucket",
            "category.entry.signal_strength.macd_bar_bucket",
        ),
    },
    "seed_liquidity": {
        "label_zh": "种子-流动性",
        "fields": (
            "entry.liquidity.turnover_rate_bucket",
            "entry.liquidity.turnover_rate_5d_bucket",
            "entry.liquidity.turnover_rate_20d_bucket",
            "entry.liquidity.amount_vs_20d_bucket",
            "entry.liquidity.amount_vs_60d_bucket",
            "entry.liquidity.amount_5d_vs_20d_bucket",
            "entry.liquidity.amount_20d_vs_60d_bucket",
            "entry.liquidity.volume_ratio_bucket",
        ),
    },
    "seed_market_cap": {
        "label_zh": "种子-市值",
        "fields": (
            "entry.market_cap.circulating_mv_abs_bucket",
            "entry.market_cap.total_mv_abs_bucket",
        ),
    },
    "seed_price_position": {
        "label_zh": "种子-价格位置",
        "fields": (
            "entry.price_position.signal_close_ma60_atr_multiple_bucket",
            "entry.price_position.interval_20d_bucket",
            "entry.price_position.interval_60d_bucket",
            "entry.price_position.near_high_20d_bucket",
            "entry.price_position.near_high_60d_bucket",
        ),
    },
    "soil_environment": {
        "label_zh": "土壤-市场行业环境",
        "fields": (
            "soil_layer5_with_industry_v1",
            "soil_layer_no_industry_v2",
            "industry_soil_layer_v1",
        ),
    },
}

CALIBRATION_FIELDS = tuple(field for group in FIELD_GROUPS.values() for field in group["fields"])


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = _load_seed_v2_detail(Path(args.seed_v2_dir))
    df = _add_score_buckets(df)

    overall_by_period = _overall_by_period(df)
    bucket_scores = _bucket_score_table(df, overall_by_period)
    group_scores = _group_score_table(bucket_scores)
    score_map = _bucket_score_map(bucket_scores)

    calibrated = _apply_calibrated_scores(df, score_map)
    quantile_table = _quantile_table(calibrated)
    threshold_table = _threshold_search_table(calibrated)

    bucket_path = output_dir / "score_calibration_bucket_scores.csv"
    group_path = output_dir / "score_calibration_group_scores.csv"
    quantile_path = output_dir / "score_calibration_quantile_metrics.csv"
    threshold_path = output_dir / "score_calibration_threshold_search.csv"
    detail_path = output_dir / "score_calibration_trade_detail.parquet"
    score_map_path = output_dir / "score_calibration_bucket_score_map.json"
    metadata_path = output_dir / "score_calibration_metadata.json"
    markdown_path = output_dir / "score_calibration_analysis.zh.md"

    bucket_scores.to_csv(bucket_path, index=False, encoding="utf-8-sig")
    group_scores.to_csv(group_path, index=False, encoding="utf-8-sig")
    quantile_table.to_csv(quantile_path, index=False, encoding="utf-8-sig")
    threshold_table.to_csv(threshold_path, index=False, encoding="utf-8-sig")
    calibrated.to_parquet(detail_path, index=False)
    score_map_path.write_text(json.dumps(score_map, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    metadata = {
        "schema": "attbacktrader.score_calibration_report.v1",
        "source_seed_v2_dir": str(args.seed_v2_dir),
        "trade_count": int(len(calibrated)),
        "calibration_fields": list(CALIBRATION_FIELDS),
        "periods": [
            {"period_id": period_id, "label_zh": label, "start": start, "end": end}
            for period_id, label, start, end in PERIODS
        ],
        "score_policy": {
            "bucket_score_range": "-2..+2",
            "core_rule_zh": "全样本 lift + 分时期稳定性 + PF 风险共同决定建议分；低样本桶默认不建议入分。",
            "caveat_zh": "这是交易样本校准，不是每日候选池横截面样本外训练；进入实战前仍需 Stage 4 排名回测。",
        },
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown_path.write_text(
        _render_markdown(
            overall_by_period=overall_by_period,
            bucket_scores=bucket_scores,
            group_scores=group_scores,
            quantile_table=quantile_table,
            threshold_table=threshold_table,
            artifacts={
                "bucket_scores": bucket_path,
                "group_scores": group_path,
                "quantile_metrics": quantile_path,
                "threshold_search": threshold_path,
                "trade_detail": detail_path,
                "score_map": score_map_path,
                "metadata": metadata_path,
            },
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "trade_count": int(len(calibrated)),
                "analysis_markdown": str(markdown_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calibrate soil/seed score buckets from trade outcomes")
    parser.add_argument("--seed-v2-dir", default=str(DEFAULT_SEED_V2_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args(argv)


def _load_seed_v2_detail(seed_v2_dir: Path) -> pd.DataFrame:
    detail_path = seed_v2_dir / "seed_v2_candidate_trade_detail.parquet"
    if detail_path.exists():
        return pd.read_parquet(detail_path)
    trades = pd.read_parquet(seed_v2.DEFAULT_SOIL_REPORT_DIR / "trade_soil_with_industry_v1.parquet")
    reference = seed_v2._load_reference_buckets(seed_v2.DEFAULT_REFERENCE_SNAPSHOT)
    return seed_v2._score_seed_v2_candidate(trades, reference)


def _add_score_buckets(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["calib.seed_score_v1_bucket"] = pd.to_numeric(result["seed_score_no_industry_v1"], errors="coerce").map(
        _seed_score_bucket
    )
    result["calib.soil_score_with_industry_bucket"] = pd.to_numeric(
        result["soil_score_with_industry_v1"], errors="coerce"
    ).map(_soil_score_bucket)
    return result


def _seed_score_bucket(value: float | int | None) -> str | None:
    if value is None or pd.isna(value):
        return None
    value = int(value)
    if value <= 2:
        return "lte_2"
    if value <= 4:
        return "3_4"
    if value <= 6:
        return "5_6"
    if value <= 8:
        return "7_8"
    return "gte_9"


def _soil_score_bucket(value: float | int | None) -> str | None:
    if value is None or pd.isna(value):
        return None
    value = int(value)
    if value <= -1:
        return "lte_neg1"
    if value <= 3:
        return "0_3"
    if value <= 7:
        return "4_7"
    if value <= 11:
        return "8_11"
    return "gte_12"


def _overall_by_period(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    return {
        period_id: {"period_zh": label, **_stats(_period_slice(df, start, end))}
        for period_id, label, start, end in PERIODS
    }


def _bucket_score_table(df: pd.DataFrame, overall_by_period: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    fields = (*CALIBRATION_FIELDS, "calib.seed_score_v1_bucket", "calib.soil_score_with_industry_bucket")
    for field in fields:
        if field not in df.columns:
            continue
        group_id, group_label = _field_group(field)
        for bucket, bucket_df in df.groupby(field, dropna=False):
            full_stats = _stats(bucket_df)
            full_base = overall_by_period["full"]
            period_rows = []
            supported = 0
            positive = 0
            negative = 0
            for period_id, label, start, end in PERIODS[1:]:
                period_bucket = _period_slice(bucket_df, start, end)
                period_stats = _stats(period_bucket)
                period_base = overall_by_period[period_id]
                lift = _lift(period_stats, period_base)
                period_rows.append(
                    {
                        "period_id": period_id,
                        "period_zh": label,
                        **period_stats,
                        **{f"lift_{key}": value for key, value in lift.items()},
                    }
                )
                if int(period_stats["trade_count"]) >= 50:
                    supported += 1
                    avg_lift = lift.get("avg_return_pct")
                    wr_lift = lift.get("win_rate_pct")
                    if (avg_lift is not None and avg_lift > 0) and (wr_lift is not None and wr_lift > 0):
                        positive += 1
                    if (avg_lift is not None and avg_lift < 0) and (wr_lift is not None and wr_lift < 0):
                        negative += 1

            full_lift = _lift(full_stats, full_base)
            recommendation, confidence, reason = _recommended_bucket_score(
                full_stats,
                full_lift=full_lift,
                supported_period_count=supported,
                positive_period_count=positive,
                negative_period_count=negative,
            )
            row = {
                "group_id": group_id,
                "group_label_zh": group_label,
                "field": field,
                "bucket": _bucket_label(bucket),
                **full_stats,
                "lift_win_rate_pct": full_lift.get("win_rate_pct"),
                "lift_avg_return_pct": full_lift.get("avg_return_pct"),
                "lift_profit_factor": full_lift.get("profit_factor"),
                "supported_period_count": supported,
                "positive_period_count": positive,
                "negative_period_count": negative,
                "recommended_score": recommendation,
                "confidence": confidence,
                "reason_zh": reason,
            }
            for item in period_rows:
                period_id = item["period_id"]
                row[f"{period_id}_trade_count"] = item["trade_count"]
                row[f"{period_id}_win_rate_pct"] = item["win_rate_pct"]
                row[f"{period_id}_avg_return_pct"] = item["avg_return_pct"]
                row[f"{period_id}_profit_factor"] = item["profit_factor"]
                row[f"{period_id}_lift_win_rate_pct"] = item["lift_win_rate_pct"]
                row[f"{period_id}_lift_avg_return_pct"] = item["lift_avg_return_pct"]
            rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["group_id", "field", "recommended_score", "trade_count"],
        ascending=[True, True, False, False],
    )


def _field_group(field: str) -> tuple[str, str]:
    for group_id, group in FIELD_GROUPS.items():
        if field in group["fields"]:
            return group_id, str(group["label_zh"])
    if field.startswith("calib.seed"):
        return "seed_score_v1", "种子-原始分层"
    if field.startswith("calib.soil"):
        return "soil_score_v1", "土壤-原始分层"
    return "other", "其他"


def _recommended_bucket_score(
    stats: dict[str, Any],
    *,
    full_lift: dict[str, float | None],
    supported_period_count: int,
    positive_period_count: int,
    negative_period_count: int,
) -> tuple[int, str, str]:
    trade_count = int(stats["trade_count"])
    if trade_count < 80:
        return 0, "low_sample", "样本不足，暂不入分"

    avg_lift = _float_or_none(full_lift.get("avg_return_pct")) or 0.0
    wr_lift = _float_or_none(full_lift.get("win_rate_pct")) or 0.0
    pf = _float_or_none(stats.get("profit_factor"))

    if (
        avg_lift >= 1.0
        and wr_lift >= 4.0
        and (pf is None or pf >= 1.25)
        and positive_period_count >= 2
    ):
        return 2, "high", "收益/胜率显著高于基准，且至少两个时期同向"
    if avg_lift >= 0.25 and wr_lift >= 1.0 and (pf is None or pf >= 1.05) and positive_period_count >= 1:
        confidence = "medium" if positive_period_count >= 2 else "low"
        return 1, confidence, "相对基准正向，但稳定性或幅度未达强加分"
    if avg_lift <= -1.0 and wr_lift <= -4.0 and negative_period_count >= 2:
        return -2, "high", "收益/胜率显著弱于基准，且至少两个时期同向"
    if avg_lift <= -0.25 and wr_lift <= -1.0 and negative_period_count >= 1:
        confidence = "medium" if negative_period_count >= 2 else "low"
        return -1, confidence, "相对基准偏负，建议轻扣分或风险提示"
    if supported_period_count < 2:
        return 0, "low", "时期覆盖不足，暂设中性"
    return 0, "medium", "相对优势不明显，暂设中性"


def _group_score_table(bucket_scores: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for group_id, group in bucket_scores.groupby("group_id"):
        tradable = group[group["confidence"] != "low_sample"]
        positive = tradable[tradable["recommended_score"] > 0]
        negative = tradable[tradable["recommended_score"] < 0]
        mean_abs = tradable["recommended_score"].abs().mean() if len(tradable) else 0.0
        rows.append(
            {
                "group_id": group_id,
                "group_label_zh": str(group["group_label_zh"].iloc[0]),
                "bucket_count": int(len(group)),
                "scored_bucket_count": int(len(tradable)),
                "positive_bucket_count": int(len(positive)),
                "negative_bucket_count": int(len(negative)),
                "mean_abs_recommended_score": float(mean_abs) if not pd.isna(mean_abs) else 0.0,
                "suggested_group_weight": _suggested_group_weight(group_id, tradable),
                "comment_zh": _group_comment(group_id, tradable),
            }
        )
    return pd.DataFrame(rows).sort_values("group_id")


def _suggested_group_weight(group_id: str, group: pd.DataFrame) -> float:
    if group_id in {"soil_environment", "soil_score_v1"}:
        return 1.5
    if group_id == "seed_macd":
        return 1.0
    if group_id == "seed_market_cap":
        return 0.5
    if group_id in {"seed_liquidity", "seed_price_position"}:
        return 1.0
    return 1.0


def _group_comment(group_id: str, group: pd.DataFrame) -> str:
    if group_id == "seed_market_cap":
        return "市值方向需按桶校准；当前不建议简单按大市值加分。"
    if group_id == "soil_environment":
        return "土壤适合作为总分权重或交易开关，弱土壤下强种子仍需单独验证。"
    if group_id == "seed_liquidity":
        return "流动性更适合同时承担加分和风险扣分。"
    if group_id == "seed_price_position":
        return "价格位置信号较强，但需防止过高位置追涨风险。"
    if group_id == "seed_macd":
        return "原始 MACD 种子是基础信号，不建议被扩展因子完全覆盖。"
    return "按 bucket 分数进入候选总分。"


def _bucket_score_map(bucket_scores: pd.DataFrame) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    usable = bucket_scores[bucket_scores["confidence"] != "low_sample"]
    for field, group in usable.groupby("field"):
        result[str(field)] = {
            str(row.bucket): int(row.recommended_score)
            for row in group.itertuples(index=False)
            if str(row.bucket) != "nan"
        }
    return result


def _apply_calibrated_scores(df: pd.DataFrame, score_map: dict[str, dict[str, int]]) -> pd.DataFrame:
    result = df.copy()
    group_columns: dict[str, list[str]] = {group_id: [] for group_id in FIELD_GROUPS}
    group_columns.update({"seed_score_v1": [], "soil_score_v1": []})
    for field, bucket_map in score_map.items():
        if field not in result.columns:
            continue
        col = f"calibrated_component.{field}"
        result[col] = result[field].map(lambda value: bucket_map.get(_bucket_label(value), 0)).astype(float)
        group_id, _label = _field_group(field)
        group_columns.setdefault(group_id, []).append(col)

    for group_id, columns in group_columns.items():
        score_col = f"calibrated_group.{group_id}"
        if columns:
            result[score_col] = result[columns].mean(axis=1)
        else:
            result[score_col] = 0.0

    result["calibrated_seed_score"] = (
        result["calibrated_group.seed_macd"]
        + result["calibrated_group.seed_liquidity"]
        + 0.5 * result["calibrated_group.seed_market_cap"]
        + result["calibrated_group.seed_price_position"]
    )
    result["calibrated_soil_score"] = (
        1.5 * result["calibrated_group.soil_environment"]
        + result.get("calibrated_group.soil_score_v1", 0.0)
    )
    result["calibrated_total_score"] = result["calibrated_seed_score"] + result["calibrated_soil_score"]
    return result


def _quantile_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for score_col in ("seed_score_no_industry_v1", "seed_v2_candidate_score", "calibrated_seed_score", "calibrated_total_score"):
        if score_col not in df.columns:
            continue
        ranked = df.copy()
        ranked["_score_rank_pct"] = ranked[score_col].rank(method="first", pct=True)
        for quantile_id, label, low, high in (
            ("top_10pct", "Top 10%", 0.9, 1.0),
            ("top_20pct", "Top 20%", 0.8, 1.0),
            ("top_30pct", "Top 30%", 0.7, 1.0),
            ("mid_40pct", "Middle 40%", 0.3, 0.7),
            ("bottom_30pct", "Bottom 30%", 0.0, 0.3),
        ):
            subset = ranked[(ranked["_score_rank_pct"] > low) & (ranked["_score_rank_pct"] <= high)]
            rows.append({"score_col": score_col, "quantile_id": quantile_id, "quantile_zh": label, **_stats(subset)})
            for period_id, period_zh, start, end in PERIODS[1:]:
                period_subset = _period_slice(subset, start, end)
                rows.append(
                    {
                        "score_col": score_col,
                        "quantile_id": f"{quantile_id}.{period_id}",
                        "quantile_zh": f"{label} / {period_zh}",
                        **_stats(period_subset),
                    }
                )
    return pd.DataFrame(rows)


def _threshold_search_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for score_col in ("seed_v2_candidate_score", "calibrated_seed_score", "calibrated_total_score"):
        if score_col not in df.columns:
            continue
        values = sorted(set(float(value) for value in pd.to_numeric(df[score_col], errors="coerce").dropna()))
        if len(values) > 30:
            candidates = sorted(set(float(df[score_col].quantile(q)) for q in [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95]))
        else:
            candidates = values
        for threshold in candidates:
            subset = df[df[score_col] >= threshold]
            if len(subset) < 200:
                continue
            stats = _stats(subset)
            rows.append({"score_col": score_col, "threshold": threshold, **stats})
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    return result.sort_values(["score_col", "avg_return_pct", "win_rate_pct"], ascending=[True, False, False])


def _period_slice(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
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
        "win_rate_pct": float(len(wins) / len(returns) * 100) if len(returns) else None,
        "avg_return_pct": float(returns.mean()) if len(returns) else None,
        "median_return_pct": float(returns.median()) if len(returns) else None,
        "profit_factor": float(pnl_wins.sum() / abs(pnl_losses.sum())) if len(pnl_losses) and abs(pnl_losses.sum()) > 0 else None,
        "return_sum_pct": float(returns.sum()) if len(returns) else None,
        "net_pnl_sum": float(net_pnl.sum()) if len(net_pnl) else None,
    }


def _lift(stats: dict[str, Any], base: dict[str, Any]) -> dict[str, float | None]:
    keys = ("win_rate_pct", "avg_return_pct", "profit_factor")
    result = {}
    for key in keys:
        value = _float_or_none(stats.get(key))
        base_value = _float_or_none(base.get(key))
        result[key] = value - base_value if value is not None and base_value is not None else None
    return result


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(result) else result


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
    overall_by_period: dict[str, dict[str, Any]],
    bucket_scores: pd.DataFrame,
    group_scores: pd.DataFrame,
    quantile_table: pd.DataFrame,
    threshold_table: pd.DataFrame,
    artifacts: dict[str, Path],
) -> str:
    lines = [
        "# 土壤/种子评分校准报告",
        "",
        "## 结论先读",
        "",
        "- 这是阶段 3 的离线校准：目标是把候选因子转成可解释的 bucket 建议分，而不是直接改实盘策略。",
        "- 建议分使用 `-2/-1/0/+1/+2`，同时要求全样本表现和三段时期稳定性。",
        "- 输出里的 calibrated score 只能作为 Stage 4 每日候选池排名回测的输入候选，不能直接上线。",
        "",
        "## 全样本基准",
        "",
        "| 时期 | 交易数 | 胜率 | 平均收益 | PF |",
        "|---|---:|---:|---:|---:|",
    ]
    for period_id, item in overall_by_period.items():
        lines.append(
            f"| {item['period_zh']} | {item['trade_count']} | {_fmt(item['win_rate_pct'])} | "
            f"{_fmt(item['avg_return_pct'])} | {_fmt(item['profit_factor'])} |"
        )

    lines.extend(["", "## 因子组建议权重", ""])
    lines.extend(
        _table(
            group_scores,
            [
                "group_label_zh",
                "bucket_count",
                "positive_bucket_count",
                "negative_bucket_count",
                "suggested_group_weight",
                "comment_zh",
            ],
            limit=30,
        )
    )

    top_positive = bucket_scores[bucket_scores["trade_count"] >= 100].sort_values(
        ["recommended_score", "lift_avg_return_pct", "trade_count"], ascending=[False, False, False]
    ).head(30)
    top_negative = bucket_scores[bucket_scores["trade_count"] >= 100].sort_values(
        ["recommended_score", "lift_avg_return_pct", "trade_count"], ascending=[True, True, False]
    ).head(30)
    lines.extend(["", "## 建议加分 Bucket Top 30", ""])
    lines.extend(
        _table(
            top_positive,
            [
                "group_label_zh",
                "field",
                "bucket",
                "trade_count",
                "win_rate_pct",
                "avg_return_pct",
                "profit_factor",
                "recommended_score",
                "confidence",
            ],
            limit=30,
        )
    )
    lines.extend(["", "## 建议扣分 Bucket Top 30", ""])
    lines.extend(
        _table(
            top_negative,
            [
                "group_label_zh",
                "field",
                "bucket",
                "trade_count",
                "win_rate_pct",
                "avg_return_pct",
                "profit_factor",
                "recommended_score",
                "confidence",
            ],
            limit=30,
        )
    )

    lines.extend(["", "## 分位数验证", ""])
    display_quantiles = quantile_table[
        quantile_table["quantile_id"].isin(["top_10pct", "top_20pct", "top_30pct", "bottom_30pct"])
    ]
    lines.extend(
        _table(
            display_quantiles,
            ["score_col", "quantile_zh", "trade_count", "win_rate_pct", "avg_return_pct", "profit_factor"],
            limit=80,
        )
    )

    lines.extend(["", "## 阈值搜索 Top 20", ""])
    threshold_display = threshold_table.sort_values(
        ["avg_return_pct", "win_rate_pct", "trade_count"], ascending=[False, False, False]
    ).head(20)
    lines.extend(
        _table(
            threshold_display,
            ["score_col", "threshold", "trade_count", "win_rate_pct", "avg_return_pct", "profit_factor"],
            limit=20,
        )
    )

    lines.extend(
        [
            "",
            "## 下一步",
            "",
            "1. 用本报告的 bucket score map 做 Stage 4 每日候选池排名验证。",
            "2. 对市值因子按桶使用，不要按“大市值更好”的单调假设使用。",
            "3. 补齐相对强弱、MA结构、K线质量、周线结构后再跑第二版校准。",
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
        values = []
        for col in columns:
            values.append(_fmt(row[col]))
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
