"""Run walk-forward portfolio validation for HS300-only soil/seed scores.

This script intentionally uses completed trade records as a lightweight
portfolio proxy. It does not re-simulate daily bars or intraday execution.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

import score_calibration_report as calibration


DEFAULT_CALIBRATION_DIR = Path("reports/score-calibration-hs300-only-2006-2025")
DEFAULT_OUTPUT_DIR = Path("reports/walk-forward-portfolio-validation-hs300-only-2006-2025")

TRAIN_START_YEAR = 2006
FIRST_TEST_YEAR = 2013
LAST_TEST_YEAR = 2025
INITIAL_CASH = 1_000_000.0
MIN_BUCKET_TRADES = 80

STRATEGIES = (
    {
        "strategy_id": "baseline_fifo",
        "label_zh": "Baseline-原始顺序",
        "score_col": None,
        "leakage": "none",
    },
    {
        "strategy_id": "seed_score_v1",
        "label_zh": "旧种子分",
        "score_col": "seed_score_no_industry_v1",
        "leakage": "none",
    },
    {
        "strategy_id": "seed_v2_candidate",
        "label_zh": "Seed V2 候选分",
        "score_col": "seed_v2_candidate_score",
        "leakage": "none",
    },
    {
        "strategy_id": "wf_calibrated_seed",
        "label_zh": "Walk-forward 校准种子分",
        "score_col": "wf_calibrated_seed_score",
        "leakage": "walk_forward_train_only",
    },
    {
        "strategy_id": "wf_calibrated_total",
        "label_zh": "Walk-forward 校准总分",
        "score_col": "wf_calibrated_total_score",
        "leakage": "walk_forward_train_only",
    },
    {
        "strategy_id": "insample_calibrated_total_reference",
        "label_zh": "In-sample 总分参考",
        "score_col": "calibrated_total_score",
        "leakage": "leaky_reference",
    },
)

MAX_NEW_PER_DAY_VALUES = (1, 3, 5)
MAX_HOLDING_VALUES = (5, 10, 20)
PERIODS = (
    ("walk_forward_full", "Walk-forward 全样本", None, None),
    ("2013_2014", "2013-2014", "2013-01-01", "2014-12-31"),
    ("2015_2021", "2015-2021", "2015-01-01", "2021-12-31"),
    ("2022_2025", "2022-2025", "2022-01-01", "2025-12-31"),
)


@dataclass
class Candidate:
    symbol: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    return_pct: float
    fold_id: str
    test_year: int
    trade_index: int
    daily_rank: int
    daily_candidate_count: int
    score_for_rank: float


@dataclass
class Position:
    row: Candidate
    allocation: float
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    symbol: str


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    source = _load_detail(Path(args.calibration_dir))
    scored, fold_rows, score_maps = _build_walk_forward_scores(
        source,
        first_test_year=int(args.first_test_year),
        last_test_year=int(args.last_test_year),
        train_start_year=int(args.train_start_year),
        min_bucket_trades=int(args.min_bucket_trades),
    )

    simulation_rows, selected_rows, equity_rows = _run_simulation_grid(scored, initial_cash=float(args.initial_cash))
    period_rows = _run_period_grid(scored, initial_cash=float(args.initial_cash))
    yearly_rows = _run_yearly_grid(scored, initial_cash=float(args.initial_cash))

    scored_path = output_dir / "walk_forward_scored_trade_detail.parquet"
    fold_path = output_dir / "walk_forward_fold_summary.csv"
    score_maps_path = output_dir / "walk_forward_fold_score_maps.json"
    metrics_path = output_dir / "walk_forward_portfolio_metrics.csv"
    period_path = output_dir / "walk_forward_period_metrics.csv"
    yearly_path = output_dir / "walk_forward_yearly_metrics.csv"
    selected_path = output_dir / "walk_forward_selected_trades.parquet"
    equity_path = output_dir / "walk_forward_equity_curves.parquet"
    metadata_path = output_dir / "walk_forward_metadata.json"
    markdown_path = output_dir / "walk_forward_portfolio_validation.zh.md"

    scored.to_parquet(scored_path, index=False)
    pd.DataFrame(fold_rows).to_csv(fold_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(simulation_rows).to_csv(metrics_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(period_rows).to_csv(period_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(yearly_rows).to_csv(yearly_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(selected_rows).to_parquet(selected_path, index=False)
    pd.DataFrame(equity_rows).to_parquet(equity_path, index=False)
    score_maps_path.write_text(json.dumps(score_maps, ensure_ascii=False, indent=2), encoding="utf-8")

    metadata = {
        "schema": "attbacktrader.walk_forward_portfolio_validation.v1",
        "source_calibration_dir": str(args.calibration_dir),
        "train_start_year": int(args.train_start_year),
        "first_test_year": int(args.first_test_year),
        "last_test_year": int(args.last_test_year),
        "initial_cash": float(args.initial_cash),
        "min_bucket_trades": int(args.min_bucket_trades),
        "strategy_notes": {
            item["strategy_id"]: {
                "label_zh": item["label_zh"],
                "score_col": item["score_col"],
                "leakage": item["leakage"],
            }
            for item in STRATEGIES
        },
        "risk_notes": [
            "这是已完成交易样本上的代理组合回测，不是完整 K 线撮合。",
            "组合净值只在入场/出场事件日更新，最大回撤低估了持仓期内波动。",
            "walk-forward 校准分只使用测试年前的数据估分；in-sample 参考分不可用于实战判断。",
        ],
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown_path.write_text(
        _render_markdown(
            metrics=pd.DataFrame(simulation_rows),
            period_metrics=pd.DataFrame(period_rows),
            yearly_metrics=pd.DataFrame(yearly_rows),
            fold_summary=pd.DataFrame(fold_rows),
            artifacts={
                "scored_trade_detail": scored_path,
                "fold_summary": fold_path,
                "fold_score_maps": score_maps_path,
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
                "output_dir": str(output_dir),
                "walk_forward_trade_count": int(len(scored)),
                "fold_count": int(len(fold_rows)),
                "analysis_markdown": str(markdown_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Walk-forward portfolio validation for calibrated soil/seed scores")
    parser.add_argument("--calibration-dir", default=str(DEFAULT_CALIBRATION_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--train-start-year", type=int, default=TRAIN_START_YEAR)
    parser.add_argument("--first-test-year", type=int, default=FIRST_TEST_YEAR)
    parser.add_argument("--last-test-year", type=int, default=LAST_TEST_YEAR)
    parser.add_argument("--initial-cash", type=float, default=INITIAL_CASH)
    parser.add_argument("--min-bucket-trades", type=int, default=MIN_BUCKET_TRADES)
    return parser.parse_args(argv)


def _load_detail(calibration_dir: Path) -> pd.DataFrame:
    path = calibration_dir / "score_calibration_trade_detail.parquet"
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_parquet(path).copy()
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df["exit_date"] = pd.to_datetime(df["exit_date"])
    df["entry_year"] = df["entry_date"].dt.year
    df["return_pct"] = pd.to_numeric(df["return_pct"], errors="coerce")
    return calibration._add_score_buckets(df)


def _build_walk_forward_scores(
    df: pd.DataFrame,
    *,
    first_test_year: int,
    last_test_year: int,
    train_start_year: int,
    min_bucket_trades: int,
) -> tuple[pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
    scored_parts: list[pd.DataFrame] = []
    fold_rows: list[dict[str, Any]] = []
    score_maps: dict[str, Any] = {}
    for test_year in range(first_test_year, last_test_year + 1):
        train = df[(df["entry_year"] >= train_start_year) & (df["entry_year"] < test_year)].copy()
        test = df[df["entry_year"] == test_year].copy()
        if train.empty or test.empty:
            continue

        score_map = _fit_training_score_map(train, min_bucket_trades=min_bucket_trades)
        scored = calibration._apply_calibrated_scores(test, score_map)
        scored["fold_id"] = f"train_{train_start_year}_{test_year - 1}_test_{test_year}"
        scored["train_start_year"] = train_start_year
        scored["train_end_year"] = test_year - 1
        scored["test_year"] = test_year
        scored["wf_calibrated_seed_score"] = scored["calibrated_seed_score"]
        scored["wf_calibrated_soil_score"] = scored["calibrated_soil_score"]
        scored["wf_calibrated_total_score"] = scored["calibrated_total_score"]

        scored_parts.append(scored)
        score_maps[str(test_year)] = score_map
        fold_rows.append(
            {
                "fold_id": scored["fold_id"].iloc[0],
                "train_start_year": train_start_year,
                "train_end_year": test_year - 1,
                "test_year": test_year,
                "train_trade_count": int(len(train)),
                "test_trade_count": int(len(test)),
                "score_field_count": int(len(score_map)),
                "score_bucket_count": int(sum(len(item) for item in score_map.values())),
                "train_win_rate_pct": _win_rate(train),
                "test_win_rate_pct": _win_rate(test),
                "train_avg_return_pct": _avg_return(train),
                "test_avg_return_pct": _avg_return(test),
            }
        )

    if not scored_parts:
        raise ValueError("no walk-forward folds were generated")
    result = pd.concat(scored_parts, ignore_index=True)
    return result, fold_rows, score_maps


def _fit_training_score_map(df: pd.DataFrame, *, min_bucket_trades: int) -> dict[str, dict[str, int]]:
    fields = (*calibration.CALIBRATION_FIELDS, "calib.seed_score_v1_bucket", "calib.soil_score_with_industry_bucket")
    base = _trade_stats(df)
    result: dict[str, dict[str, int]] = {}
    for field in fields:
        if field not in df.columns:
            continue
        bucket_scores: dict[str, int] = {}
        for bucket, bucket_df in df.groupby(field, dropna=False):
            label = calibration._bucket_label(bucket)
            stats = _trade_stats(bucket_df)
            bucket_scores[label] = _score_bucket_from_training(
                stats,
                base,
                min_bucket_trades=min_bucket_trades,
            )
        result[field] = bucket_scores
    return result


def _score_bucket_from_training(
    stats: dict[str, float | int | None],
    base: dict[str, float | int | None],
    *,
    min_bucket_trades: int,
) -> int:
    if int(stats["trade_count"] or 0) < min_bucket_trades:
        return 0
    avg_lift = _number(stats["avg_return_pct"]) - _number(base["avg_return_pct"])
    win_lift = _number(stats["win_rate_pct"]) - _number(base["win_rate_pct"])
    pf_lift = _number(stats["profit_factor"]) - _number(base["profit_factor"])

    score = 0
    if avg_lift >= 1.0 and win_lift >= 4.0:
        score += 2
    elif avg_lift >= 0.25 and win_lift >= 1.0:
        score += 1

    if avg_lift <= -1.0 and win_lift <= -4.0:
        score -= 2
    elif avg_lift <= -0.25 and win_lift <= -1.0:
        score -= 1

    if pf_lift >= 0.15 and score > 0:
        score += 1
    if pf_lift <= -0.15 and score < 0:
        score -= 1
    return int(max(-2, min(2, score)))


def _run_simulation_grid(df: pd.DataFrame, *, initial_cash: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    metrics: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []
    for strategy in STRATEGIES:
        for max_new in MAX_NEW_PER_DAY_VALUES:
            for max_holding in MAX_HOLDING_VALUES:
                result = _simulate_portfolio(
                    df,
                    strategy_id=str(strategy["strategy_id"]),
                    strategy_label=str(strategy["label_zh"]),
                    score_col=strategy["score_col"],
                    max_new_per_day=max_new,
                    max_holding_count=max_holding,
                    initial_cash=initial_cash,
                )
                metrics.append({**result["metrics"], "period_id": "walk_forward_full", "period_zh": "Walk-forward 全样本"})
                selected.extend(result["selected"])
                equity_rows.extend(result["equity_curve"])
    return metrics, selected, equity_rows


def _run_period_grid(df: pd.DataFrame, *, initial_cash: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for period_id, period_zh, start, end in PERIODS:
        period_df = _period_slice(df, start, end)
        for strategy in STRATEGIES:
            for max_new in MAX_NEW_PER_DAY_VALUES:
                for max_holding in MAX_HOLDING_VALUES:
                    result = _simulate_portfolio(
                        period_df,
                        strategy_id=str(strategy["strategy_id"]),
                        strategy_label=str(strategy["label_zh"]),
                        score_col=strategy["score_col"],
                        max_new_per_day=max_new,
                        max_holding_count=max_holding,
                        initial_cash=initial_cash,
                    )
                    rows.append({**result["metrics"], "period_id": period_id, "period_zh": period_zh})
    return rows


def _run_yearly_grid(df: pd.DataFrame, *, initial_cash: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for year in sorted(int(value) for value in df["entry_year"].dropna().unique()):
        year_df = df[df["entry_year"] == year]
        for strategy in STRATEGIES:
            for max_new in MAX_NEW_PER_DAY_VALUES:
                for max_holding in MAX_HOLDING_VALUES:
                    result = _simulate_portfolio(
                        year_df,
                        strategy_id=str(strategy["strategy_id"]),
                        strategy_label=str(strategy["label_zh"]),
                        score_col=strategy["score_col"],
                        max_new_per_day=max_new,
                        max_holding_count=max_holding,
                        initial_cash=initial_cash,
                    )
                    rows.append({**result["metrics"], "year": year})
    return rows


def _simulate_portfolio(
    df: pd.DataFrame,
    *,
    strategy_id: str,
    strategy_label: str,
    score_col: str | None,
    max_new_per_day: int,
    max_holding_count: int,
    initial_cash: float,
) -> dict[str, Any]:
    candidates = _rank_candidates(df, score_col)
    if candidates.empty:
        metrics = _portfolio_metrics(
            strategy_id=strategy_id,
            strategy_label=strategy_label,
            score_col=score_col,
            max_new_per_day=max_new_per_day,
            max_holding_count=max_holding_count,
            initial_cash=initial_cash,
            selected=[],
            equity_curve=[],
            start_date=None,
            end_date=None,
        )
        return {"metrics": metrics, "selected": [], "equity_curve": []}

    cash = float(initial_cash)
    open_positions: list[Position] = []
    selected: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    blocked_capacity = 0
    blocked_duplicate = 0
    blocked_cash = 0
    candidate_records = _candidate_records(candidates)
    dates = sorted({item.entry_date for item in candidate_records}.union({item.exit_date for item in candidate_records}))
    candidate_by_day: dict[pd.Timestamp, list[Candidate]] = {}
    for item in candidate_records:
        candidate_by_day.setdefault(item.entry_date, []).append(item)

    for date in dates:
        remaining_positions: list[Position] = []
        for pos in open_positions:
            if pos.exit_date > date:
                remaining_positions.append(pos)
                continue
            ret = _number(pos.row.return_pct) / 100.0
            proceeds = pos.allocation * (1.0 + ret)
            pnl = proceeds - pos.allocation
            cash += proceeds
            selected.append(_selected_row(pos, strategy_id, strategy_label, score_col, max_new_per_day, max_holding_count, pnl))
        open_positions = remaining_positions

        day_candidates = candidate_by_day.get(date)
        opened_today = 0
        if day_candidates is not None:
            held_symbols = {pos.symbol for pos in open_positions}
            for row in day_candidates:
                if opened_today >= max_new_per_day:
                    break
                if len(open_positions) >= max_holding_count:
                    blocked_capacity += 1
                    continue
                symbol = str(row.symbol)
                if symbol in held_symbols:
                    blocked_duplicate += 1
                    continue
                pseudo_equity = cash + sum(pos.allocation for pos in open_positions)
                allocation = min(cash, pseudo_equity / max_holding_count)
                if allocation <= 0:
                    blocked_cash += 1
                    continue
                cash -= allocation
                open_positions.append(
                    Position(
                        row=row,
                        allocation=allocation,
                        entry_date=row.entry_date,
                        exit_date=row.exit_date,
                        symbol=symbol,
                    )
                )
                held_symbols.add(symbol)
                opened_today += 1

        pseudo_equity = cash + sum(pos.allocation for pos in open_positions)
        equity_curve.append(
            {
                "strategy_id": strategy_id,
                "strategy_label_zh": strategy_label,
                "score_col": score_col or "",
                "max_new_per_day": max_new_per_day,
                "max_holding_count": max_holding_count,
                "date": date,
                "cash": cash,
                "open_position_count": len(open_positions),
                "equity_proxy": pseudo_equity,
            }
        )

    metrics = _portfolio_metrics(
        strategy_id=strategy_id,
        strategy_label=strategy_label,
        score_col=score_col,
        max_new_per_day=max_new_per_day,
        max_holding_count=max_holding_count,
        initial_cash=initial_cash,
        selected=selected,
        equity_curve=equity_curve,
        start_date=min(dates),
        end_date=max(dates),
    )
    metrics["blocked_capacity_count"] = blocked_capacity
    metrics["blocked_duplicate_count"] = blocked_duplicate
    metrics["blocked_cash_count"] = blocked_cash
    metrics["candidate_count"] = int(len(candidates))
    return {"metrics": metrics, "selected": selected, "equity_curve": equity_curve}


def _rank_candidates(df: pd.DataFrame, score_col: str | None) -> pd.DataFrame:
    ranked = df.copy()
    if score_col is None:
        ranked["_score_for_rank"] = 0.0
        ranked = ranked.sort_values(["entry_date", "trade_index", "symbol"], ascending=[True, True, True])
    else:
        ranked["_score_for_rank"] = pd.to_numeric(ranked[score_col], errors="coerce").fillna(float("-inf"))
        tie_cols = ["entry_date", "_score_for_rank", "seed_score_no_industry_v1", "symbol", "trade_index"]
        ranked = ranked.sort_values(tie_cols, ascending=[True, False, False, True, True])
    ranked["_daily_rank"] = ranked.groupby("entry_date").cumcount() + 1
    ranked["_daily_candidate_count"] = ranked.groupby("entry_date")["symbol"].transform("count")
    return ranked[
        [
            "symbol",
            "entry_date",
            "exit_date",
            "return_pct",
            "fold_id",
            "test_year",
            "trade_index",
            "_daily_rank",
            "_daily_candidate_count",
            "_score_for_rank",
        ]
    ].copy()


def _candidate_records(candidates: pd.DataFrame) -> list[Candidate]:
    records: list[Candidate] = []
    for row in candidates.itertuples(index=False, name=None):
        (
            symbol,
            entry_date,
            exit_date,
            return_pct,
            fold_id,
            test_year,
            trade_index,
            daily_rank,
            daily_candidate_count,
            score_for_rank,
        ) = row
        records.append(
            Candidate(
                symbol=str(symbol),
                entry_date=pd.Timestamp(entry_date),
                exit_date=pd.Timestamp(exit_date),
                return_pct=_number(return_pct),
                fold_id=str(fold_id),
                test_year=int(test_year or 0),
                trade_index=int(trade_index or 0),
                daily_rank=int(daily_rank or 0),
                daily_candidate_count=int(daily_candidate_count or 0),
                score_for_rank=_number(score_for_rank),
            )
        )
    return records


def _selected_row(
    pos: Position,
    strategy_id: str,
    strategy_label: str,
    score_col: str | None,
    max_new_per_day: int,
    max_holding_count: int,
    pnl: float,
) -> dict[str, Any]:
    row = pos.row
    return {
        "strategy_id": strategy_id,
        "strategy_label_zh": strategy_label,
        "score_col": score_col or "",
        "max_new_per_day": max_new_per_day,
        "max_holding_count": max_holding_count,
        "fold_id": row.fold_id,
        "test_year": row.test_year,
        "symbol": row.symbol,
        "entry_date": str(row.entry_date.date()),
        "exit_date": str(row.exit_date.date()),
        "daily_rank": row.daily_rank,
        "daily_candidate_count": row.daily_candidate_count,
        "score": row.score_for_rank,
        "allocation": float(pos.allocation),
        "return_pct": row.return_pct,
        "pnl": float(pnl),
    }


def _portfolio_metrics(
    *,
    strategy_id: str,
    strategy_label: str,
    score_col: str | None,
    max_new_per_day: int,
    max_holding_count: int,
    initial_cash: float,
    selected: list[dict[str, Any]],
    equity_curve: list[dict[str, Any]],
    start_date: pd.Timestamp | None,
    end_date: pd.Timestamp | None,
) -> dict[str, Any]:
    pnl = pd.Series([row["pnl"] for row in selected], dtype=float)
    returns = pd.Series([row["return_pct"] for row in selected], dtype=float)
    final_equity = float(equity_curve[-1]["equity_proxy"]) if equity_curve else float(initial_cash)
    total_return_pct = (final_equity / initial_cash - 1.0) * 100.0
    days = int((end_date - start_date).days) + 1 if start_date is not None and end_date is not None else 0
    annualized_return_pct = _annualized_return(initial_cash, final_equity, days)
    wins = returns[returns > 0]
    pnl_wins = pnl[pnl > 0]
    pnl_losses = pnl[pnl < 0]
    equity = pd.Series([row["equity_proxy"] for row in equity_curve], dtype=float)
    drawdown_pct = ((equity / equity.cummax()) - 1.0) * 100.0 if len(equity) else pd.Series(dtype=float)
    avg_holding_count = (
        float(pd.Series([row["open_position_count"] for row in equity_curve], dtype=float).mean())
        if equity_curve
        else None
    )
    return {
        "strategy_id": strategy_id,
        "strategy_label_zh": strategy_label,
        "score_col": score_col or "",
        "max_new_per_day": max_new_per_day,
        "max_holding_count": max_holding_count,
        "trade_count": int(len(selected)),
        "win_rate_pct": float(len(wins) / len(returns) * 100) if len(returns) else None,
        "avg_trade_return_pct": float(returns.mean()) if len(returns) else None,
        "profit_factor": float(pnl_wins.sum() / abs(pnl_losses.sum())) if len(pnl_losses) and abs(pnl_losses.sum()) > 0 else None,
        "initial_cash": float(initial_cash),
        "final_equity_proxy": final_equity,
        "total_return_pct": total_return_pct,
        "annualized_return_pct": annualized_return_pct,
        "max_drawdown_pct": float(drawdown_pct.min()) if len(drawdown_pct) else None,
        "avg_holding_count": avg_holding_count,
        "start_date": str(start_date.date()) if start_date is not None else "",
        "end_date": str(end_date.date()) if end_date is not None else "",
        "calendar_days": days,
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


def _trade_stats(df: pd.DataFrame) -> dict[str, float | int | None]:
    returns = pd.to_numeric(df["return_pct"], errors="coerce").dropna()
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    return {
        "trade_count": int(len(df)),
        "win_rate_pct": float(len(wins) / len(returns) * 100) if len(returns) else None,
        "avg_return_pct": float(returns.mean()) if len(returns) else None,
        "profit_factor": float(wins.sum() / abs(losses.sum())) if len(losses) and abs(losses.sum()) > 0 else None,
    }


def _win_rate(df: pd.DataFrame) -> float | None:
    return _trade_stats(df)["win_rate_pct"]


def _avg_return(df: pd.DataFrame) -> float | None:
    return _trade_stats(df)["avg_return_pct"]


def _number(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(result) else result


def _annualized_return(initial_cash: float, final_equity: float, days: int) -> float | None:
    if initial_cash <= 0 or final_equity <= 0 or days <= 0:
        return None
    years = days / 365.25
    if years <= 0:
        return None
    return float(((final_equity / initial_cash) ** (1.0 / years) - 1.0) * 100.0)


def _render_markdown(
    *,
    metrics: pd.DataFrame,
    period_metrics: pd.DataFrame,
    yearly_metrics: pd.DataFrame,
    fold_summary: pd.DataFrame,
    artifacts: dict[str, Path],
) -> str:
    core = metrics[
        (metrics["max_new_per_day"].isin([1, 3, 5]))
        & (metrics["max_holding_count"].isin([5, 10, 20]))
        & (metrics["strategy_id"].isin(["baseline_fifo", "seed_score_v1", "seed_v2_candidate", "wf_calibrated_seed", "wf_calibrated_total"]))
    ].copy()
    core = core.sort_values(["max_holding_count", "max_new_per_day", "annualized_return_pct"], ascending=[True, True, False])

    best_by_strategy = (
        metrics[~metrics["strategy_id"].eq("insample_calibrated_total_reference")]
        .sort_values(["annualized_return_pct", "max_drawdown_pct"], ascending=[False, False])
        .groupby("strategy_id", as_index=False)
        .head(1)
        .sort_values("annualized_return_pct", ascending=False)
    )

    period_core = period_metrics[
        (period_metrics["strategy_id"].isin(["baseline_fifo", "wf_calibrated_seed", "wf_calibrated_total"]))
        & (period_metrics["max_new_per_day"].eq(3))
        & (period_metrics["max_holding_count"].eq(10))
    ].copy()

    yearly_core = yearly_metrics[
        (yearly_metrics["strategy_id"].isin(["baseline_fifo", "wf_calibrated_total"]))
        & (yearly_metrics["max_new_per_day"].eq(3))
        & (yearly_metrics["max_holding_count"].eq(10))
    ].copy()

    lines = [
        "# Walk-forward 组合验证报告",
        "",
        "## 口径",
        "",
        "- 每个测试年只使用此前年份重新估 bucket 分数，再验证测试年候选。默认首个测试年为 2013。",
        "- 组合模拟是已完成交易样本上的代理回测：使用 `entry_date/exit_date/return_pct`，不重新做 K 线撮合。",
        "- 净值只在交易事件日更新，最大回撤无法反映持仓期间的真实浮动回撤。",
        "- `insample_calibrated_total_reference` 只是泄漏参考，不参与实战结论。",
        "",
        "## Fold 概览",
        "",
    ]
    lines.extend(
        _table(
            fold_summary,
            [
                "fold_id",
                "train_trade_count",
                "test_trade_count",
                "score_field_count",
                "score_bucket_count",
                "train_win_rate_pct",
                "test_win_rate_pct",
            ],
            limit=30,
        )
    )

    lines.extend(["", "## 每个策略最佳参数", ""])
    lines.extend(
        _table(
            best_by_strategy,
            [
                "strategy_label_zh",
                "max_new_per_day",
                "max_holding_count",
                "trade_count",
                "annualized_return_pct",
                "max_drawdown_pct",
                "win_rate_pct",
                "avg_trade_return_pct",
                "profit_factor",
                "final_equity_proxy",
            ],
            limit=30,
        )
    )

    lines.extend(["", "## 全样本网格核心对比", ""])
    lines.extend(
        _table(
            core,
            [
                "strategy_label_zh",
                "max_new_per_day",
                "max_holding_count",
                "trade_count",
                "annualized_return_pct",
                "max_drawdown_pct",
                "win_rate_pct",
                "avg_trade_return_pct",
                "profit_factor",
            ],
            limit=90,
        )
    )

    lines.extend(["", "## 分时期对照（Top3 / MaxHold10）", ""])
    lines.extend(
        _table(
            period_core,
            [
                "period_zh",
                "strategy_label_zh",
                "trade_count",
                "annualized_return_pct",
                "max_drawdown_pct",
                "win_rate_pct",
                "avg_trade_return_pct",
                "profit_factor",
            ],
            limit=60,
        )
    )

    lines.extend(["", "## 年度对照（Top3 / MaxHold10）", ""])
    lines.extend(
        _table(
            yearly_core,
            [
                "year",
                "strategy_label_zh",
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
            "- 如果 walk-forward 校准分在相同 TopN/持仓约束下持续优于 baseline 和旧 seed，才说明新因子可以进入策略评分层。",
            "- 如果只在 in-sample 参考分中变好，而 walk-forward 分没有变好，说明阶段 3 校准过拟合。",
            "- 如果 2022-2025 明显失效，下一步应优先做近期 regime gate，而不是继续扩大候选因子数量。",
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
