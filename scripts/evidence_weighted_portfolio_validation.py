"""Portfolio proxy validation for evidence-weighted seed/soil scores.

This script reuses the walk-forward portfolio proxy simulator and only changes
the ranking score. It does not alter live strategy configuration.
"""

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

import walk_forward_portfolio_validation as portfolio  # noqa: E402


SOURCE_DIR = ROOT / "reports" / "evidence-weighted-ranking-validation-hs300-only-2006-2025"
SOURCE = SOURCE_DIR / "evidence_weighted_scored_trade_detail.parquet"
OUTPUT_DIR = ROOT / "reports" / "evidence-weighted-portfolio-validation-hs300-only-2006-2025"

INITIAL_CASH = 1_000_000.0
MAX_NEW_PER_DAY_VALUES = (1, 3, 5)
MAX_HOLDING_VALUES = (10, 20)
PERIODS = (
    ("walk_forward_full", "Walk-forward 2013-2025", "2013-01-01", "2025-12-31"),
    ("2013_2014", "2013-2014", "2013-01-01", "2014-12-31"),
    ("2015_2021", "2015-2021", "2015-01-01", "2021-12-31"),
    ("2022_2025", "2022-2025", "2022-01-01", "2025-12-31"),
)
STRATEGIES = (
    {
        "strategy_id": "baseline_fifo",
        "label_zh": "Baseline-原始顺序",
        "score_col": None,
    },
    {
        "strategy_id": "seed_v2_candidate",
        "label_zh": "Seed V2 候选分",
        "score_col": "seed_v2_candidate_score",
    },
    {
        "strategy_id": "ew_seed_only",
        "label_zh": "Evidence Seed-only v2",
        "score_col": "ew_seed_only_score",
    },
    {
        "strategy_id": "ew_seed_soil",
        "label_zh": "Evidence Seed+Soil v2",
        "score_col": "ew_seed_soil_score",
    },
)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    trades = load_source()

    metrics_rows, selected_rows, equity_rows = run_full_grid(trades)
    period_rows = run_period_grid(trades)
    yearly_rows = run_yearly_grid(trades)

    metrics = add_baseline_lifts(pd.DataFrame(metrics_rows), key_cols=["max_new_per_day", "max_holding_count"])
    period_metrics = add_baseline_lifts(
        pd.DataFrame(period_rows),
        key_cols=["period_id", "max_new_per_day", "max_holding_count"],
    )
    yearly_metrics = add_baseline_lifts(
        pd.DataFrame(yearly_rows),
        key_cols=["year", "max_new_per_day", "max_holding_count"],
    )
    selected = pd.DataFrame(selected_rows)
    equity = pd.DataFrame(equity_rows)

    metrics_path = OUTPUT_DIR / "evidence_weighted_portfolio_metrics.csv"
    period_path = OUTPUT_DIR / "evidence_weighted_portfolio_period_metrics.csv"
    yearly_path = OUTPUT_DIR / "evidence_weighted_portfolio_yearly_metrics.csv"
    selected_path = OUTPUT_DIR / "evidence_weighted_portfolio_selected_trades.parquet"
    equity_path = OUTPUT_DIR / "evidence_weighted_portfolio_equity_curves.parquet"
    metadata_path = OUTPUT_DIR / "evidence_weighted_portfolio_metadata.json"
    markdown_path = OUTPUT_DIR / "evidence_weighted_portfolio_validation.zh.md"

    metrics.to_csv(metrics_path, index=False, encoding="utf-8-sig")
    period_metrics.to_csv(period_path, index=False, encoding="utf-8-sig")
    yearly_metrics.to_csv(yearly_path, index=False, encoding="utf-8-sig")
    selected.to_parquet(selected_path, index=False)
    equity.to_parquet(equity_path, index=False)

    metadata = {
        "schema": "attbacktrader.evidence_weighted_portfolio_validation.v1",
        "roadmap_check": "第4步：在 TopN + MaxHold 组合代理约束下验证 seed/soil v2；未改策略，未接实盘，未继续追 gate。",
        "source_scored_trade_detail": str(SOURCE),
        "initial_cash": INITIAL_CASH,
        "max_new_per_day_values": list(MAX_NEW_PER_DAY_VALUES),
        "max_holding_values": list(MAX_HOLDING_VALUES),
        "strategies": {
            item["strategy_id"]: {"label_zh": item["label_zh"], "score_col": item["score_col"]}
            for item in STRATEGIES
        },
        "notes": [
            "组合模拟复用 scripts/walk_forward_portfolio_validation.py 的代理回测口径。",
            "TopN 对应 max_new_per_day；MaxHold 对应 max_holding_count。",
            "净值只在入场/出场事件日更新，最大回撤低估持仓期内真实波动。",
            "本报告只验证评分排名进入资金约束后是否仍有优势，不改变正式策略或实盘参数。",
        ],
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(
        render_markdown(
            metrics=metrics,
            period_metrics=period_metrics,
            yearly_metrics=yearly_metrics,
            artifacts={
                "portfolio_metrics": metrics_path,
                "period_metrics": period_path,
                "yearly_metrics": yearly_path,
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
                "output_dir": str(OUTPUT_DIR),
                "trade_count": int(len(trades)),
                "selected_trade_rows": int(len(selected)),
                "analysis_markdown": str(markdown_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def load_source() -> pd.DataFrame:
    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)
    df = pd.read_parquet(SOURCE).copy()
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df["exit_date"] = pd.to_datetime(df["exit_date"])
    df["entry_year"] = df["entry_date"].dt.year
    if "test_year" not in df.columns:
        df["test_year"] = df["entry_year"]
    if "fold_id" not in df.columns:
        df["fold_id"] = "unknown"
    required = [
        "symbol",
        "entry_date",
        "exit_date",
        "return_pct",
        "fold_id",
        "test_year",
        "trade_index",
        "seed_score_no_industry_v1",
        "seed_v2_candidate_score",
        "ew_seed_only_score",
        "ew_seed_soil_score",
    ]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")
    return df


def run_full_grid(df: pd.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    metrics: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []
    for strategy in STRATEGIES:
        for max_new in MAX_NEW_PER_DAY_VALUES:
            for max_holding in MAX_HOLDING_VALUES:
                result = portfolio._simulate_portfolio(
                    df,
                    strategy_id=str(strategy["strategy_id"]),
                    strategy_label=str(strategy["label_zh"]),
                    score_col=strategy["score_col"],
                    max_new_per_day=max_new,
                    max_holding_count=max_holding,
                    initial_cash=INITIAL_CASH,
                )
                metrics.append({**result["metrics"], "period_id": "walk_forward_full", "period_zh": "Walk-forward 2013-2025"})
                selected.extend(result["selected"])
                equity_rows.extend(result["equity_curve"])
    return metrics, selected, equity_rows


def run_period_grid(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for period_id, period_zh, start, end in PERIODS:
        period_df = portfolio._period_slice(df, start, end)
        for strategy in STRATEGIES:
            for max_new in MAX_NEW_PER_DAY_VALUES:
                for max_holding in MAX_HOLDING_VALUES:
                    result = portfolio._simulate_portfolio(
                        period_df,
                        strategy_id=str(strategy["strategy_id"]),
                        strategy_label=str(strategy["label_zh"]),
                        score_col=strategy["score_col"],
                        max_new_per_day=max_new,
                        max_holding_count=max_holding,
                        initial_cash=INITIAL_CASH,
                    )
                    rows.append({**result["metrics"], "period_id": period_id, "period_zh": period_zh})
    return rows


def run_yearly_grid(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for year in sorted(int(value) for value in df["entry_year"].dropna().unique()):
        year_df = df[df["entry_year"] == year].copy()
        for strategy in STRATEGIES:
            for max_new in MAX_NEW_PER_DAY_VALUES:
                for max_holding in MAX_HOLDING_VALUES:
                    result = portfolio._simulate_portfolio(
                        year_df,
                        strategy_id=str(strategy["strategy_id"]),
                        strategy_label=str(strategy["label_zh"]),
                        score_col=strategy["score_col"],
                        max_new_per_day=max_new,
                        max_holding_count=max_holding,
                        initial_cash=INITIAL_CASH,
                    )
                    rows.append({**result["metrics"], "year": year})
    return rows


def add_baseline_lifts(df: pd.DataFrame, *, key_cols: list[str]) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    baseline_cols = [
        *key_cols,
        "annualized_return_pct",
        "max_drawdown_pct",
        "win_rate_pct",
        "avg_trade_return_pct",
        "profit_factor",
        "trade_count",
    ]
    base = out[out["strategy_id"].eq("baseline_fifo")][baseline_cols].rename(
        columns={
            "annualized_return_pct": "baseline_annualized_return_pct",
            "max_drawdown_pct": "baseline_max_drawdown_pct",
            "win_rate_pct": "baseline_win_rate_pct",
            "avg_trade_return_pct": "baseline_avg_trade_return_pct",
            "profit_factor": "baseline_profit_factor",
            "trade_count": "baseline_trade_count",
        }
    )
    out = out.merge(base, on=key_cols, how="left")
    out["annualized_lift_pct"] = out["annualized_return_pct"] - out["baseline_annualized_return_pct"]
    out["max_drawdown_delta_pct"] = out["max_drawdown_pct"] - out["baseline_max_drawdown_pct"]
    out["win_rate_lift_pct"] = out["win_rate_pct"] - out["baseline_win_rate_pct"]
    out["avg_trade_return_lift_pct"] = out["avg_trade_return_pct"] - out["baseline_avg_trade_return_pct"]
    out["profit_factor_lift"] = out["profit_factor"] - out["baseline_profit_factor"]
    return out


def render_markdown(
    *,
    metrics: pd.DataFrame,
    period_metrics: pd.DataFrame,
    yearly_metrics: pd.DataFrame,
    artifacts: dict[str, Path],
) -> str:
    core = metrics[
        (metrics["max_new_per_day"].isin([1, 3, 5]))
        & (metrics["max_holding_count"].isin([10, 20]))
        & (metrics["strategy_id"].isin(["seed_v2_candidate", "ew_seed_only", "ew_seed_soil"]))
    ].copy()
    core = core.sort_values(["max_holding_count", "max_new_per_day", "annualized_return_pct"], ascending=[True, True, False])

    best_by_strategy = (
        metrics[metrics["strategy_id"].isin(["seed_v2_candidate", "ew_seed_only", "ew_seed_soil"])]
        .sort_values(["annualized_return_pct", "max_drawdown_pct"], ascending=[False, False])
        .groupby("strategy_id", as_index=False)
        .head(1)
        .sort_values("annualized_return_pct", ascending=False)
    )

    period_top3_hold10 = period_metrics[
        (period_metrics["max_new_per_day"].eq(3))
        & (period_metrics["max_holding_count"].eq(10))
        & (period_metrics["strategy_id"].isin(["baseline_fifo", "seed_v2_candidate", "ew_seed_only", "ew_seed_soil"]))
    ].copy()
    period_top3_hold20 = period_metrics[
        (period_metrics["max_new_per_day"].eq(3))
        & (period_metrics["max_holding_count"].eq(20))
        & (period_metrics["strategy_id"].isin(["baseline_fifo", "seed_v2_candidate", "ew_seed_only", "ew_seed_soil"]))
    ].copy()
    yearly_top3_hold10 = yearly_metrics[
        (yearly_metrics["max_new_per_day"].eq(3))
        & (yearly_metrics["max_holding_count"].eq(10))
        & (yearly_metrics["strategy_id"].isin(["baseline_fifo", "ew_seed_only", "ew_seed_soil"]))
    ].copy()

    lines = [
        "# Evidence-weighted Seed/Soil 组合代理验证",
        "",
        "## Roadmap 对照",
        "",
        "- 本报告属于第 4 步：`seed/soil score v2 -> TopN + MaxHold 组合代理验证`。",
        "- 没有改正式策略配置，没有接实盘，也没有继续做 gate 过拟合。",
        "- 目标是看离线排名优势进入资金/持仓约束后是否仍然成立。",
        "",
        "## 口径",
        "",
        "- 输入为上一阶段 `evidence_weighted_scored_trade_detail.parquet`。",
        "- `TopN` 对应 `max_new_per_day`，本次为 1/3/5；`MaxHold` 为 10/20。",
        "- 组合模拟复用原 walk-forward portfolio proxy：按 score 日内排序、限制每日新开仓和最大持仓。",
        "- 这是已完成交易样本上的代理回测，不是完整 K 线撮合；净值只在事件日更新，回撤会低估持仓期波动。",
        "",
        "## 全样本核心对比",
        "",
        *table(
            core,
            [
                "strategy_id",
                "max_new_per_day",
                "max_holding_count",
                "trade_count",
                "annualized_return_pct",
                "max_drawdown_pct",
                "win_rate_pct",
                "avg_trade_return_pct",
                "profit_factor",
                "annualized_lift_pct",
            ],
            80,
        ),
        "",
        "## 各策略最佳组合",
        "",
        *table(
            best_by_strategy,
            [
                "strategy_id",
                "max_new_per_day",
                "max_holding_count",
                "trade_count",
                "annualized_return_pct",
                "max_drawdown_pct",
                "win_rate_pct",
                "profit_factor",
                "annualized_lift_pct",
            ],
            20,
        ),
        "",
        "## 分时期 Top3 / MaxHold10",
        "",
        *table(
            period_top3_hold10,
            [
                "strategy_id",
                "period_zh",
                "trade_count",
                "annualized_return_pct",
                "max_drawdown_pct",
                "win_rate_pct",
                "profit_factor",
                "annualized_lift_pct",
            ],
            80,
        ),
        "",
        "## 分时期 Top3 / MaxHold20",
        "",
        *table(
            period_top3_hold20,
            [
                "strategy_id",
                "period_zh",
                "trade_count",
                "annualized_return_pct",
                "max_drawdown_pct",
                "win_rate_pct",
                "profit_factor",
                "annualized_lift_pct",
            ],
            80,
        ),
        "",
        "## 年度 Top3 / MaxHold10",
        "",
        *table(
            yearly_top3_hold10,
            [
                "strategy_id",
                "year",
                "trade_count",
                "annualized_return_pct",
                "max_drawdown_pct",
                "win_rate_pct",
                "profit_factor",
                "annualized_lift_pct",
            ],
            120,
        ),
        "",
        "## 判断规则",
        "",
        "- 若 `ew_seed_only` 在多数 TopN/MaxHold 组合下优于 `seed_v2_candidate` 和 baseline，说明 evidence-weighted seed 分数可进入下一阶段。",
        "- 若 `ew_seed_soil` 只小幅好于或弱于 `ew_seed_only`，土壤仍应作为轻权重/仓位解释层，不宜成为主排名分。",
        "- 若近期 2022-2025 仍显著失效，下一步应回到因子稳定性和市场 regime 解释，而不是继续加硬 gate。",
        "",
        "## 产物",
        "",
        *[f"- `{name}`: `{path}`" for name, path in artifacts.items()],
    ]
    return "\n".join(lines)


def table(df: pd.DataFrame, columns: list[str], limit: int) -> list[str]:
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    if df.empty:
        lines.append("| " + " | ".join("-" for _ in columns) + " |")
        return lines
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
