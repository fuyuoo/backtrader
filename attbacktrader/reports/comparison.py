"""Compare persisted run artifacts for result-driven strategy development."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


_BLOCK_REASON_ZH = {
    "ATR_RISK_UNAVAILABLE": "ATR 风险值不可用",
    "BOARD_LOT_TOO_SMALL": "不足一手",
    "CASH_NOT_ENOUGH": "现金不足",
    "LIMIT_DOWN_SELL_BLOCKED": "跌停卖出受限",
    "LIMIT_UP_BUY_BLOCKED": "涨停买入受限",
    "MAX_HOLDING_COUNT": "达到最大持仓数量",
    "REBALANCE_INTERVAL": "再平衡间隔不足",
    "SIZING_ZERO_QUANTITY": "仓位计算为 0",
    "SUSPENDED": "停牌",
    "T_PLUS_ONE_SELL_BLOCKED": "T+1 卖出受限",
}


@dataclass(frozen=True)
class RunComparisonReasonCount:
    reason: str
    count: int


@dataclass(frozen=True)
class RunComparisonRow:
    run_id: str
    run_dir: Path
    engine: str | None
    from_date: str | None
    to_date: str | None
    symbol_count: int
    final_value: float | None
    cumulative_return: float | None
    max_drawdown: float | None
    trade_count: int
    win_rate: float | None
    profit_loss_ratio: float | None
    execution_rejection_count: int
    execution_rejection_reason_counts: tuple[RunComparisonReasonCount, ...]
    sizing_blocked_count: int
    entry_filter_count: int
    add_on_signal_count: int


@dataclass(frozen=True)
class RunComparisonDelta:
    run_id: str
    baseline_run_id: str
    final_value_delta: float | None
    cumulative_return_delta: float | None
    max_drawdown_delta: float | None
    trade_count_delta: int
    entry_filter_count_delta: int
    add_on_signal_count_delta: int


@dataclass(frozen=True)
class RunComparison:
    baseline_run_id: str | None
    rows: tuple[RunComparisonRow, ...]
    deltas: tuple[RunComparisonDelta, ...]


def build_run_comparison(run_dirs: Sequence[str | Path]) -> RunComparison:
    rows = tuple(_comparison_row(Path(run_dir)) for run_dir in run_dirs)
    baseline = rows[0] if rows else None
    return RunComparison(
        baseline_run_id=baseline.run_id if baseline is not None else None,
        rows=rows,
        deltas=tuple(_comparison_delta(row, baseline) for row in rows[1:] if baseline is not None),
    )


def write_run_comparison(
    comparison: RunComparison,
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "comparison.json"
    markdown_path = output_path / "comparison.zh.md"
    json_path.write_text(
        json.dumps(_jsonable_comparison(comparison), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(render_run_comparison_markdown_zh(comparison), encoding="utf-8")
    return json_path, markdown_path


def render_run_comparison_markdown_zh(comparison: RunComparison) -> str:
    lines = [
        "# 回测对照",
        "",
        f"基准运行：{comparison.baseline_run_id or '-'}",
        "",
        "| 运行 | 期末权益 | 累计收益 | 最大回撤 | 交易 | 胜率 | 盈亏比 | 入场过滤 | 加仓信号 | 拒单 | Sizing 拦截 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in comparison.rows:
        lines.append(
            "| "
            f"{row.run_id} | "
            f"{_format_optional_number(row.final_value)} | "
            f"{_format_optional_percent(row.cumulative_return)} | "
            f"{_format_optional_percent(row.max_drawdown)} | "
            f"{row.trade_count} | "
            f"{_format_optional_percent(row.win_rate)} | "
            f"{_format_optional_number(row.profit_loss_ratio)} | "
            f"{row.entry_filter_count} | "
            f"{row.add_on_signal_count} | "
            f"{row.execution_rejection_count}{_format_reason_counts(row.execution_rejection_reason_counts)} | "
            f"{row.sizing_blocked_count} |"
        )

    if comparison.deltas:
        lines.extend(
            [
                "",
                "## 相对基准差异",
                "",
                "| 运行 | 期末权益差 | 累计收益差 | 最大回撤差 | 交易差 | 入场过滤差 | 加仓信号差 |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for delta in comparison.deltas:
            lines.append(
                "| "
                f"{delta.run_id} | "
                f"{_format_optional_signed_number(delta.final_value_delta)} | "
                f"{_format_optional_signed_percent(delta.cumulative_return_delta)} | "
                f"{_format_optional_signed_percent(delta.max_drawdown_delta)} | "
                f"{delta.trade_count_delta:+d} | "
                f"{delta.entry_filter_count_delta:+d} | "
                f"{delta.add_on_signal_count_delta:+d} |"
            )

    return "\n".join(lines).rstrip() + "\n"


def run_comparison_to_jsonable(comparison: RunComparison) -> dict[str, Any]:
    return _jsonable_comparison(comparison)


def _comparison_row(run_dir: Path) -> RunComparisonRow:
    run_plan = _read_json(run_dir / "run_plan.json")
    report = _read_json(run_dir / "report.json")
    diagnostics = _read_json(run_dir / "result_diagnostics.json")
    signal_audit = _read_json(run_dir / "signal_audit.json")

    report_returns = _mapping(report.get("returns"))
    report_risk = _mapping(report.get("risk"))
    report_quality = _mapping(report.get("trade_quality"))
    run_config = _mapping(run_plan.get("run"))
    data_config = _mapping(run_plan.get("data"))
    execution_config = _mapping(run_plan.get("execution"))

    return RunComparisonRow(
        run_id=str(run_config.get("id") or run_dir.name),
        run_dir=run_dir,
        engine=_optional_str(execution_config.get("engine")),
        from_date=_optional_str(run_config.get("from_date")),
        to_date=_optional_str(run_config.get("to_date")),
        symbol_count=_symbol_count(data_config),
        final_value=_optional_float(report_returns.get("final_equity")),
        cumulative_return=_optional_float(report_returns.get("cumulative_return")),
        max_drawdown=_optional_float(report_risk.get("max_drawdown")),
        trade_count=int(report_quality.get("trade_count") or 0),
        win_rate=_optional_float(report_quality.get("win_rate")),
        profit_loss_ratio=_optional_float(report_quality.get("profit_loss_ratio")),
        execution_rejection_count=_diagnostic_sum(diagnostics, "execution_rejection_count"),
        execution_rejection_reason_counts=_diagnostic_reason_counts(diagnostics, "execution_rejection_counts"),
        sizing_blocked_count=_diagnostic_sum(diagnostics, "sizing_blocked_count"),
        entry_filter_count=sum(
            1
            for intent in signal_audit
            if isinstance(intent, Mapping) and intent.get("reason_code") == "ENTRY_ATTRIBUTION_FILTERED"
        ),
        add_on_signal_count=sum(
            1
            for intent in signal_audit
            if isinstance(intent, Mapping) and intent.get("intent_type") == "add_on"
        ),
    )


def _comparison_delta(row: RunComparisonRow, baseline: RunComparisonRow) -> RunComparisonDelta:
    return RunComparisonDelta(
        run_id=row.run_id,
        baseline_run_id=baseline.run_id,
        final_value_delta=_optional_delta(row.final_value, baseline.final_value),
        cumulative_return_delta=_optional_delta(row.cumulative_return, baseline.cumulative_return),
        max_drawdown_delta=_optional_delta(row.max_drawdown, baseline.max_drawdown),
        trade_count_delta=row.trade_count - baseline.trade_count,
        entry_filter_count_delta=row.entry_filter_count - baseline.entry_filter_count,
        add_on_signal_count_delta=row.add_on_signal_count - baseline.add_on_signal_count,
    )


def _jsonable_comparison(comparison: RunComparison) -> dict[str, Any]:
    return {
        "baseline_run_id": comparison.baseline_run_id,
        "rows": [
            {
                "run_id": row.run_id,
                "run_dir": str(row.run_dir),
                "engine": row.engine,
                "from_date": row.from_date,
                "to_date": row.to_date,
                "symbol_count": row.symbol_count,
                "final_value": row.final_value,
                "cumulative_return": row.cumulative_return,
                "max_drawdown": row.max_drawdown,
                "trade_count": row.trade_count,
                "win_rate": row.win_rate,
                "profit_loss_ratio": row.profit_loss_ratio,
                "execution_rejection_count": row.execution_rejection_count,
                "execution_rejection_reason_counts": [
                    {"reason": item.reason, "count": item.count}
                    for item in row.execution_rejection_reason_counts
                ],
                "sizing_blocked_count": row.sizing_blocked_count,
                "entry_filter_count": row.entry_filter_count,
                "add_on_signal_count": row.add_on_signal_count,
            }
            for row in comparison.rows
        ],
        "deltas": [
            {
                "run_id": delta.run_id,
                "baseline_run_id": delta.baseline_run_id,
                "final_value_delta": delta.final_value_delta,
                "cumulative_return_delta": delta.cumulative_return_delta,
                "max_drawdown_delta": delta.max_drawdown_delta,
                "trade_count_delta": delta.trade_count_delta,
                "entry_filter_count_delta": delta.entry_filter_count_delta,
                "add_on_signal_count_delta": delta.add_on_signal_count_delta,
            }
            for delta in comparison.deltas
        ],
    }


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"missing run artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def _optional_delta(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return value - baseline


def _symbol_count(data_config: Mapping[str, Any]) -> int:
    tradable_series = data_config.get("tradable_series")
    if isinstance(tradable_series, list):
        return len(tradable_series)
    symbols = data_config.get("symbols")
    if isinstance(symbols, list):
        return len(symbols)
    return 0


def _diagnostic_sum(diagnostics: Mapping[str, Any], field_name: str) -> int:
    symbols = diagnostics.get("symbols")
    if not isinstance(symbols, list):
        return 0
    return sum(
        int(symbol.get(field_name) or 0)
        for symbol in symbols
        if isinstance(symbol, Mapping)
    )


def _diagnostic_reason_counts(diagnostics: Mapping[str, Any], field_name: str) -> tuple[RunComparisonReasonCount, ...]:
    counts: dict[str, int] = {}
    symbols = diagnostics.get("symbols")
    if not isinstance(symbols, list):
        return ()
    for symbol in symbols:
        if not isinstance(symbol, Mapping):
            continue
        rows = symbol.get(field_name)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            reason = str(row.get("reason") or "")
            if not reason:
                continue
            counts[reason] = counts.get(reason, 0) + int(row.get("count") or 0)
    return tuple(
        RunComparisonReasonCount(reason=reason, count=count)
        for reason, count in sorted(counts.items())
    )


def safe_comparison_dir_name(run_ids: Sequence[str]) -> str:
    joined = "__vs__".join(run_ids)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", joined.strip())
    return f"comparison-{safe or 'runs'}"


def _format_optional_number(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _format_optional_signed_number(value: float | None) -> str:
    if value is None:
        return "-"
    prefix = "+" if value > 0 else ""
    return f"{prefix}{_format_optional_number(value)}"


def _format_optional_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.2f}%"


def _format_optional_signed_percent(value: float | None) -> str:
    if value is None:
        return "-"
    prefix = "+" if value > 0 else ""
    return f"{prefix}{value * 100:.2f}%"


def _format_reason_counts(counts: tuple[RunComparisonReasonCount, ...]) -> str:
    if not counts:
        return ""
    return " (" + ", ".join(f"{_translate_block_reason(item.reason)}:{item.count}" for item in counts) + ")"


def _translate_block_reason(reason: str) -> str:
    label = _BLOCK_REASON_ZH.get(reason)
    if label is None:
        return reason
    return f"{label} ({reason})"
