from __future__ import annotations

import argparse
import dataclasses
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from attbacktrader.config import load_run_plan
from attbacktrader.data.snapshots import SnapshotReadCache
from attbacktrader.runners import PreparedRunDataCache, execute_run_plan
DEFAULT_CONFIG = (
    REPO_ROOT
    / "reports"
    / "formal-strategy-gate-config-hs300-only-2006-2025"
    / "run_plan_near_high_60d_gate_v1.json"
)
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "reports"
    / "near-high-60d-holding-sweep-hs300-only-2006-2025"
)


class ProgressLogger:
    def __init__(self, path: Path) -> None:
        self._started_at = time.monotonic()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("w", encoding="utf-8")

    def emit(self, event: Mapping[str, object]) -> None:
        payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "elapsed_seconds": round(time.monotonic() - self._started_at, 3),
            **event,
        }
        self._file.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()


def _trade_to_row(index: int, trade: Any) -> dict[str, Any]:
    if dataclasses.is_dataclass(trade):
        row = dataclasses.asdict(trade)
    elif hasattr(trade, "model_dump"):
        row = trade.model_dump()
    else:
        row = {
            key: getattr(trade, key, None)
            for key in (
                "symbol",
                "entry_date",
                "exit_date",
                "entry_price",
                "exit_price",
                "exit_reason",
                "quantity",
                "original_entry_price",
                "remaining_cost_basis_at_exit",
                "entry_quantity",
                "entry_gross_value",
                "exit_gross_value",
                "net_pnl",
                "realized_return_pct",
            )
        }
    row["trade_index"] = index
    return row


def _closed_trades_frame(result: Any) -> pd.DataFrame:
    return pd.DataFrame(_trade_to_row(index, trade) for index, trade in enumerate(result.closed_trades, start=1))


def _safe_div(numerator: float, denominator: float) -> float | None:
    if denominator == 0 or pd.isna(denominator):
        return None
    return numerator / denominator


def _profit_factor(trades: pd.DataFrame) -> float | None:
    if trades.empty or "net_pnl" not in trades:
        return None
    gains = float(trades.loc[trades["net_pnl"] > 0, "net_pnl"].sum())
    losses = float(trades.loc[trades["net_pnl"] < 0, "net_pnl"].sum())
    return _safe_div(gains, abs(losses))


def _annualized_return(starting_equity: float, final_equity: float, days: int) -> float | None:
    if starting_equity <= 0 or final_equity <= 0 or days <= 0:
        return None
    return (final_equity / starting_equity) ** (365.25 / days) - 1


def _total_metrics(max_holding_count: int, result: Any, trades: pd.DataFrame) -> dict[str, Any]:
    report = result.report
    returns = report.returns
    trade_quality = report.trade_quality
    benchmark = report.benchmark_comparison[0] if report.benchmark_comparison else None
    run_days = None
    if not trades.empty:
        run_days = (pd.to_datetime(trades["exit_date"]).max() - pd.to_datetime(trades["entry_date"]).min()).days

    return {
        "max_holding_count": max_holding_count,
        "run_id": result.run_id,
        "starting_equity": returns.starting_equity,
        "final_equity": returns.final_equity,
        "cumulative_return_pct": returns.cumulative_return * 100,
        "annualized_return_pct": (
            _annualized_return(returns.starting_equity, returns.final_equity, int(run_days)) * 100
            if run_days
            else None
        ),
        "max_drawdown_pct": report.risk.max_drawdown * -100,
        "trade_count": trade_quality.trade_count,
        "win_rate_pct": trade_quality.win_rate * 100,
        "average_win_pct": trade_quality.average_win * 100,
        "average_loss_pct": trade_quality.average_loss * 100,
        "profit_loss_ratio": trade_quality.profit_loss_ratio,
        "trade_profit_factor": _profit_factor(trades),
        "avg_trade_return_pct": trades["realized_return_pct"].mean() * 100 if not trades.empty else None,
        "median_trade_return_pct": trades["realized_return_pct"].median() * 100 if not trades.empty else None,
        "open_position_count": result.report.portfolio_behavior.open_position_count,
        "completed_order_count": result.report.execution_costs.completed_count,
        "benchmark_return_pct": benchmark.benchmark_return * 100 if benchmark else None,
        "excess_return_pct": benchmark.excess_return * 100 if benchmark else None,
    }


def _period_metrics(max_holding_count: int, trades: pd.DataFrame) -> list[dict[str, Any]]:
    if trades.empty:
        return []
    trades = trades.copy()
    trades["entry_date"] = pd.to_datetime(trades["entry_date"])
    trades["exit_date"] = pd.to_datetime(trades["exit_date"])
    trades["holding_days"] = (trades["exit_date"] - trades["entry_date"]).dt.days
    periods = (
        ("2006-2014", "2006-01-01", "2014-12-31"),
        ("2015-2021", "2015-01-01", "2021-12-31"),
        ("2022-2025", "2022-01-01", "2025-12-31"),
    )
    rows: list[dict[str, Any]] = []
    for period, start, end in periods:
        subset = trades[(trades["entry_date"] >= start) & (trades["entry_date"] <= end)]
        if subset.empty:
            rows.append({"max_holding_count": max_holding_count, "period": period, "trade_count": 0})
            continue
        rows.append(
            {
                "max_holding_count": max_holding_count,
                "period": period,
                "trade_count": int(len(subset)),
                "win_rate_pct": float((subset["net_pnl"] > 0).mean() * 100),
                "avg_trade_return_pct": float(subset["realized_return_pct"].mean() * 100),
                "median_trade_return_pct": float(subset["realized_return_pct"].median() * 100),
                "trade_profit_factor": _profit_factor(subset),
                "net_pnl": float(subset["net_pnl"].sum()),
                "avg_holding_days": float(subset["holding_days"].mean()),
            }
        )
    return rows


def _format_pct(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.2f}%"


def _write_report(output_dir: Path, totals: pd.DataFrame, periods: pd.DataFrame) -> None:
    lines = [
        "# near_high_60d 持仓约束实盘 runner 回测对照",
        "",
        "口径：正式 `baoma_v1_business` runner，`near_high_60d` entry filter，离线数据；仅跳过完整 artifact writer，保留汇总与交易明细。",
        "",
        "## 总览",
        "",
        "| MaxHold | 累计收益 | 年化 | 最大回撤 | 交易数 | 胜率 | PF | 平均单笔 | 期末持仓 | 超额收益 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in totals.itertuples(index=False):
        lines.append(
            f"| {row.max_holding_count} | {_format_pct(row.cumulative_return_pct)} | "
            f"{_format_pct(row.annualized_return_pct)} | {_format_pct(row.max_drawdown_pct)} | "
            f"{int(row.trade_count)} | {_format_pct(row.win_rate_pct)} | "
            f"{row.trade_profit_factor:.2f} | {_format_pct(row.avg_trade_return_pct)} | "
            f"{int(row.open_position_count)} | {_format_pct(row.excess_return_pct)} |"
        )
    lines.extend(["", "## 分时期交易质量", ""])
    lines.extend(
        [
            "| MaxHold | 时期 | 交易数 | 胜率 | PF | 平均单笔 | 中位数单笔 | 净利润 | 平均持仓天数 |",
            "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in periods.itertuples(index=False):
        lines.append(
            f"| {row.max_holding_count} | {row.period} | {int(row.trade_count)} | "
            f"{_format_pct(row.win_rate_pct)} | {row.trade_profit_factor:.2f} | "
            f"{_format_pct(row.avg_trade_return_pct)} | {_format_pct(row.median_trade_return_pct)} | "
            f"{row.net_pnl:.0f} | {row.avg_holding_days:.1f} |"
        )
    (output_dir / "near_high_60d_holding_sweep_analysis.zh.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_sweep(config_path: Path, output_dir: Path, max_holds: tuple[int, ...], progress_interval_days: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    base_plan = load_run_plan(config_path)
    snapshot_read_cache = SnapshotReadCache()
    prepared_data_cache = PreparedRunDataCache()
    total_rows: list[dict[str, Any]] = []
    period_rows: list[dict[str, Any]] = []

    for max_holding_count in max_holds:
        run_id = f"baoma-v1-dynamic-hs300-only-2006-2025-near-high-60d-maxhold-{max_holding_count}"
        sizing_params = dict(base_plan.strategy.sizing_params)
        sizing_params["max_holding_count"] = max_holding_count
        plan = base_plan.model_copy(
            update={
                "run": base_plan.run.model_copy(update={"id": run_id}),
                "strategy": base_plan.strategy.model_copy(update={"sizing_params": sizing_params}),
                "output": base_plan.output.model_copy(update={"persist": False, "artifact_detail": "compact"}),
            }
        )

        progress = ProgressLogger(output_dir / f"{run_id}.progress.ndjson")
        try:
            progress.emit({"stage": "sweep_run", "status": "started", "run_id": run_id, "max_holding_count": max_holding_count})
            result = execute_run_plan(
                plan,
                provider=None,
                prepared_data_cache=prepared_data_cache,
                snapshot_read_cache=snapshot_read_cache,
                progress_callback=progress.emit,
                progress_interval_days=progress_interval_days,
            )
            trades = _closed_trades_frame(result)
            trades.to_parquet(output_dir / f"{run_id}.trades.parquet", index=False)
            total_rows.append(_total_metrics(max_holding_count, result, trades))
            period_rows.extend(_period_metrics(max_holding_count, trades))
            progress.emit({"stage": "sweep_run", "status": "completed", "run_id": run_id, "max_holding_count": max_holding_count})
        finally:
            progress.close()

        totals = pd.DataFrame(total_rows)
        periods = pd.DataFrame(period_rows)
        totals.to_csv(output_dir / "near_high_60d_holding_sweep_totals.csv", index=False, encoding="utf-8-sig")
        periods.to_csv(output_dir / "near_high_60d_holding_sweep_period_metrics.csv", index=False, encoding="utf-8-sig")
        _write_report(output_dir, totals, periods)
        (output_dir / "latest_completed.json").write_text(
            json.dumps({"max_holding_count": max_holding_count, "run_id": run_id}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-holds", type=int, nargs="+", default=[10, 20, 50])
    parser.add_argument("--progress-interval-days", type=int, default=250)
    args = parser.parse_args()
    run_sweep(
        args.config,
        args.output_dir.resolve(),
        tuple(args.max_holds),
        args.progress_interval_days,
    )


if __name__ == "__main__":
    main()
