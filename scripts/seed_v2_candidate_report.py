"""Build an offline seed_v2 candidate scoring report from existing artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_SOIL_REPORT_DIR = Path("reports/soil-with-industry-v1-baoma-v1-dynamic-hs300-only-2006-2025")
DEFAULT_REFERENCE_SNAPSHOT = Path(
    "data/snapshots/attribution_reference/full_a_main_chinext_star/"
    "2006-01-01_2025-12-31_hs300-only-entry-scope-liquidity-gating-v1"
)
DEFAULT_OUTPUT_DIR = Path("reports/seed-v2-candidate-hs300-only-2006-2025")

REFERENCE_FIELDS = (
    "entry.liquidity.turnover_rate_bucket",
    "entry.liquidity.turnover_rate_5d_bucket",
    "entry.liquidity.turnover_rate_20d_bucket",
    "entry.liquidity.amount_vs_20d_bucket",
    "entry.liquidity.amount_vs_60d_bucket",
    "entry.liquidity.amount_5d_vs_20d_bucket",
    "entry.liquidity.amount_20d_vs_60d_bucket",
    "entry.liquidity.volume_ratio_bucket",
    "entry.market_cap.circulating_mv_abs_bucket",
    "entry.market_cap.total_mv_abs_bucket",
    "entry.price_position.signal_close_ma60_atr_multiple_bucket",
    "entry.price_position.interval_20d_bucket",
    "entry.price_position.interval_60d_bucket",
    "entry.price_position.near_high_20d_bucket",
    "entry.price_position.near_high_60d_bucket",
)

PERIODS = (
    ("full", "全样本", None, None),
    ("2006_2014", "2006-2014", "2006-01-01", "2014-12-31"),
    ("2015_2021", "2015-2021", "2015-01-01", "2021-12-31"),
    ("2022_2025", "2022-2025", "2022-01-01", "2025-12-31"),
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trades = pd.read_parquet(Path(args.soil_report_dir) / "trade_soil_with_industry_v1.parquet")
    reference = _load_reference_buckets(Path(args.reference_snapshot))
    scored = _score_seed_v2_candidate(trades, reference)

    detail_path = output_dir / "seed_v2_candidate_trade_detail.parquet"
    scored.to_parquet(detail_path, index=False)

    layer_period = _layer_period_table(scored)
    layer_period_path = output_dir / "seed_v2_candidate_layer_period_metrics.csv"
    layer_period.to_csv(layer_period_path, index=False, encoding="utf-8-sig")

    component_by_layer = _component_by_layer(scored)
    component_path = output_dir / "seed_v2_candidate_component_by_layer.csv"
    component_by_layer.to_csv(component_path, index=False, encoding="utf-8-sig")

    bucket_diagnostics = _bucket_diagnostics(scored)
    bucket_path = output_dir / "seed_v2_candidate_bucket_diagnostics.csv"
    bucket_diagnostics.to_csv(bucket_path, index=False, encoding="utf-8-sig")

    coverage = _coverage(scored)
    coverage_path = output_dir / "seed_v2_candidate_factor_coverage.csv"
    coverage.to_csv(coverage_path, index=False, encoding="utf-8-sig")

    metadata = _metadata(args, scored, coverage)
    metadata_path = output_dir / "seed_v2_candidate_metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    markdown_path = output_dir / "seed_v2_candidate_analysis.zh.md"
    markdown_path.write_text(
        _render_markdown(
            scored=scored,
            layer_period=layer_period,
            component_by_layer=component_by_layer,
            bucket_diagnostics=bucket_diagnostics,
            coverage=coverage,
            artifacts={
                "detail_parquet": detail_path,
                "layer_period_csv": layer_period_path,
                "component_csv": component_path,
                "bucket_csv": bucket_path,
                "coverage_csv": coverage_path,
                "metadata_json": metadata_path,
            },
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "trade_count": int(len(scored)),
                "coverage_csv": str(coverage_path),
                "analysis_markdown": str(markdown_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build seed_v2 candidate offline scoring report")
    parser.add_argument("--soil-report-dir", default=str(DEFAULT_SOIL_REPORT_DIR))
    parser.add_argument("--reference-snapshot", default=str(DEFAULT_REFERENCE_SNAPSHOT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args(argv)


def _load_reference_buckets(snapshot_dir: Path) -> pd.DataFrame:
    values_path = snapshot_dir / "reference_values.parquet"
    if not values_path.exists():
        raise FileNotFoundError(values_path)
    ref = pd.read_parquet(values_path)
    ref = ref.loc[ref["field_key"].isin(REFERENCE_FIELDS), ["symbol", "trade_date", "field_key", "bucket"]].copy()
    ref["trade_date"] = pd.to_datetime(ref["trade_date"]).dt.date.astype(str)
    wide = ref.pivot_table(
        index=["symbol", "trade_date"],
        columns="field_key",
        values="bucket",
        aggfunc="first",
    ).reset_index()
    wide.columns.name = None
    return wide


def _score_seed_v2_candidate(trades: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    df = trades.copy()
    df["signal_date"] = pd.to_datetime(df["signal_date"]).dt.date.astype(str)
    df = df.merge(
        reference,
        left_on=["symbol", "signal_date"],
        right_on=["symbol", "trade_date"],
        how="left",
        suffixes=("", "_reference"),
    )
    df.drop(columns=["trade_date"], inplace=True, errors="ignore")

    df["seed_v2_liquidity_score"] = df.apply(_liquidity_score, axis=1)
    df["seed_v2_market_cap_score"] = df.apply(_market_cap_score, axis=1)
    df["seed_v2_price_position_score"] = df.apply(_price_position_score, axis=1)
    df["seed_v2_extra_score"] = (
        df["seed_v2_liquidity_score"] + df["seed_v2_market_cap_score"] + df["seed_v2_price_position_score"]
    )
    df["seed_v2_candidate_score"] = df["seed_score_no_industry_v1"].fillna(0).astype(int) + df["seed_v2_extra_score"]
    df["seed_v2_candidate_layer"] = df["seed_v2_candidate_score"].map(_seed_v2_layer)
    df["seed_v2_reference_complete"] = df[list(REFERENCE_FIELDS)].notna().all(axis=1)
    df["seed_v2_reference_missing_field_count"] = df[list(REFERENCE_FIELDS)].isna().sum(axis=1)
    return df


def _liquidity_score(row: pd.Series) -> int:
    score = 0
    turnover = [
        row.get("entry.liquidity.turnover_rate_bucket"),
        row.get("entry.liquidity.turnover_rate_5d_bucket"),
        row.get("entry.liquidity.turnover_rate_20d_bucket"),
    ]
    if "lt_1pct" in turnover:
        score -= 2
    if row.get("entry.liquidity.turnover_rate_5d_bucket") in {"3_5pct", "5_10pct"}:
        score += 1
    if row.get("entry.liquidity.turnover_rate_bucket") == "gte_10pct":
        score -= 1

    amount = [
        row.get("entry.liquidity.amount_vs_20d_bucket"),
        row.get("entry.liquidity.amount_vs_60d_bucket"),
        row.get("entry.liquidity.amount_5d_vs_20d_bucket"),
        row.get("entry.liquidity.amount_20d_vs_60d_bucket"),
    ]
    if any(value in {"1p2_1p6x", "1p6_2x"} for value in amount):
        score += 1
    if "lt_0p8x" in amount:
        score -= 1

    volume_ratio = row.get("entry.liquidity.volume_ratio_bucket")
    if volume_ratio == "1p2_2x":
        score += 1
    elif volume_ratio in {"lt_0p8x", "gte_4x"}:
        score -= 1
    return max(-3, min(3, score))


def _market_cap_score(row: pd.Series) -> int:
    circulating = row.get("entry.market_cap.circulating_mv_abs_bucket")
    if circulating == "0_100yi":
        return -1
    if circulating in {"300_600yi", "600_1000yi", "1000_1500yi"}:
        return 1
    return 0


def _price_position_score(row: pd.Series) -> int:
    score = 0
    ma60_atr = row.get("entry.price_position.signal_close_ma60_atr_multiple_bucket")
    score += {
        "below_ma60_gt_2atr": -2,
        "below_ma60_1_2atr": -1,
        "below_ma60_0_1atr": 0,
        "above_ma60_0_1atr": 1,
        "above_ma60_1_2atr": 1,
        "above_ma60_gt_2atr": 0,
    }.get(ma60_atr, 0)

    for field in ("entry.price_position.interval_20d_bucket", "entry.price_position.interval_60d_bucket"):
        score += {
            "low_0_20": -1,
            "low_mid_20_40": 0,
            "mid_40_60": 1,
            "high_mid_60_80": 1,
            "high_80_100": 0,
        }.get(row.get(field), 0)

    for field in ("entry.price_position.near_high_20d_bucket", "entry.price_position.near_high_60d_bucket"):
        score += {
            "deep_pullback": -1,
            "far_from_high": 0,
            "moderate_pullback": 1,
            "near_high": 1,
            "at_high": 0,
        }.get(row.get(field), 0)
    return max(-3, min(3, score))


def _seed_v2_layer(score: int) -> str:
    if score >= 8:
        return "strong_seed_v2_candidate"
    if score >= 5:
        return "neutral_seed_v2_candidate"
    return "weak_seed_v2_candidate"


def _layer_period_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for period_id, label, start, end in PERIODS:
        period_df = _period_slice(df, start, end)
        rows.append({"period_id": period_id, "period_zh": label, "layer_type": "overall", "layer": "all", **_stats(period_df)})
        for layer_col in ("seed_layer_no_industry_v1", "seed_v2_candidate_layer", "soil_layer5_with_industry_v1"):
            for layer, group in period_df.groupby(layer_col, dropna=False):
                rows.append(
                    {
                        "period_id": period_id,
                        "period_zh": label,
                        "layer_type": layer_col,
                        "layer": str(layer),
                        **_stats(group),
                    }
                )
    return pd.DataFrame(rows)


def _component_by_layer(df: pd.DataFrame) -> pd.DataFrame:
    component_cols = [
        "seed_score_no_industry_v1",
        "seed_v2_liquidity_score",
        "seed_v2_market_cap_score",
        "seed_v2_price_position_score",
        "seed_v2_extra_score",
    ]
    rows = []
    for layer, group in df.groupby("seed_v2_candidate_layer"):
        for col in component_cols:
            rows.append(
                {
                    "layer": layer,
                    "component": col,
                    "mean_score": group[col].mean(),
                    "positive_rate_pct": (group[col] > 0).mean() * 100,
                    "negative_rate_pct": (group[col] < 0).mean() * 100,
                    "zero_rate_pct": (group[col] == 0).mean() * 100,
                    **_stats(group),
                }
            )
    return pd.DataFrame(rows)


def _bucket_diagnostics(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for field in REFERENCE_FIELDS:
        if field not in df.columns:
            continue
        for value, group in df.groupby(field, dropna=False):
            rows.append({"field": field, "bucket": str(value), **_stats(group)})
    return pd.DataFrame(rows).sort_values(["field", "trade_count"], ascending=[True, False])


def _coverage(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for field in REFERENCE_FIELDS:
        present = int(df[field].notna().sum()) if field in df.columns else 0
        rows.append(
            {
                "field": field,
                "present_count": present,
                "missing_count": int(len(df) - present),
                "coverage_pct": present / len(df) * 100 if len(df) else 0,
            }
        )
    return pd.DataFrame(rows)


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
    net_pnl = pd.to_numeric(df.get("net_pnl"), errors="coerce").dropna() if "net_pnl" in df else pd.Series(dtype=float)
    wins = returns[returns > 0]
    losses = returns[returns <= 0]
    pnl_wins = net_pnl[net_pnl > 0]
    pnl_losses = net_pnl[net_pnl < 0]
    return {
        "trade_count": int(len(df)),
        "win_rate_pct": float(len(wins) / len(returns) * 100) if len(returns) else None,
        "avg_return_pct": float(returns.mean()) if len(returns) else None,
        "median_return_pct": float(returns.median()) if len(returns) else None,
        "profit_factor": float(pnl_wins.sum() / abs(pnl_losses.sum())) if len(pnl_losses) and abs(pnl_losses.sum()) > 0 else None,
        "return_sum_pct": float(returns.sum()) if len(returns) else None,
        "avg_holding_days": float(pd.to_numeric(df.get("holding_days"), errors="coerce").mean()) if "holding_days" in df else None,
        "net_pnl_sum": float(net_pnl.sum()) if len(net_pnl) else None,
    }


def _metadata(args: argparse.Namespace, scored: pd.DataFrame, coverage: pd.DataFrame) -> dict[str, Any]:
    return {
        "schema": "attbacktrader.seed_v2_candidate_report.v1",
        "source": {
            "soil_report_dir": str(args.soil_report_dir),
            "reference_snapshot": str(args.reference_snapshot),
        },
        "trade_count": int(len(scored)),
        "score_formula": (
            "seed_score_no_industry_v1 + seed_v2_liquidity_score + "
            "seed_v2_market_cap_score + seed_v2_price_position_score"
        ),
        "layer_thresholds": {
            "strong_seed_v2_candidate": "score >= 8",
            "neutral_seed_v2_candidate": "5 <= score <= 7",
            "weak_seed_v2_candidate": "score <= 4",
        },
        "candidate_scope": {
            "included_now": [
                "existing MACD signal-strength seed score",
                "liquidity buckets from attribution_reference",
                "circulating market-cap absolute bucket from attribution_reference",
                "price-position buckets from attribution_reference",
            ],
            "not_yet_full_period_included": [
                "symbol relative strength versus HS300/industry",
                "MA25/MA60 spread and MA60 slope",
                "signal candle body/shadow structure",
                "symbol weekly MA trend and weekly KDJ state",
            ],
        },
        "coverage": coverage.to_dict(orient="records"),
    }


def _render_markdown(
    *,
    scored: pd.DataFrame,
    layer_period: pd.DataFrame,
    component_by_layer: pd.DataFrame,
    bucket_diagnostics: pd.DataFrame,
    coverage: pd.DataFrame,
    artifacts: dict[str, Path],
) -> str:
    lines = [
        "# seed_v2 候选评分离线诊断",
        "",
        "## 结论摘要",
        "",
        "- 当前正式种子仍以 MACD 信号强度为主体；本报告把流动性、市值、价格位置作为 seed_v2 候选轻量入分。",
        "- 本轮不改策略，只对既有交易样本做离线重评分，因此结论用于筛选候选权重，不等同于真实调仓回测。",
        "- 全期 reference snapshot 覆盖市值、流动性、价格位置；相对强弱、MA25/MA60 结构、K 线实体/影线、个股周线趋势仍未完整进入本版。",
        "",
        "## 评分口径",
        "",
        "`seed_v2_candidate_score = seed_score_no_industry_v1 + liquidity + market_cap + price_position`",
        "",
        "| 分层 | 阈值 |",
        "|---|---:|",
        "| 强种子 v2 候选 | >= 8 |",
        "| 中种子 v2 候选 | 5 到 7 |",
        "| 弱种子 v2 候选 | <= 4 |",
        "",
        "## 字段覆盖率",
        "",
        "| 字段 | 覆盖率 | 缺失 |",
        "|---|---:|---:|",
    ]
    for row in coverage.itertuples(index=False):
        lines.append(f"| `{row.field}` | {row.coverage_pct:.2f}% | {row.missing_count} |")

    lines.extend(["", "## 分时期分层表现", ""])
    display = layer_period[
        layer_period["layer_type"].isin(["overall", "seed_layer_no_industry_v1", "seed_v2_candidate_layer"])
    ].copy()
    lines.extend(_table(display, ["period_zh", "layer_type", "layer", "trade_count", "win_rate_pct", "avg_return_pct", "profit_factor"]))

    lines.extend(["", "## seed_v2 组件均值", ""])
    lines.extend(_table(component_by_layer, ["layer", "component", "mean_score", "positive_rate_pct", "negative_rate_pct", "trade_count", "win_rate_pct", "profit_factor"]))

    top_buckets = bucket_diagnostics[bucket_diagnostics["trade_count"] >= 100].copy()
    top_buckets = top_buckets.sort_values(["avg_return_pct", "trade_count"], ascending=[False, False]).head(20)
    lines.extend(["", "## 候选桶 Top 20", ""])
    lines.extend(_table(top_buckets, ["field", "bucket", "trade_count", "win_rate_pct", "avg_return_pct", "profit_factor"]))

    lines.extend(
        [
            "",
            "## 产物",
            "",
            *[f"- `{name}`: `{path}`" for name, path in artifacts.items()],
            "",
        ]
    )
    return "\n".join(lines)


def _table(df: pd.DataFrame, columns: list[str]) -> list[str]:
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for _, row in df[columns].iterrows():
        values = []
        for col in columns:
            value = row[col]
            if isinstance(value, float):
                values.append(f"{value:.4f}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return lines


if __name__ == "__main__":
    raise SystemExit(main())
