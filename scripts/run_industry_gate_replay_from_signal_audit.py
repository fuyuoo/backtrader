"""Replay industry gate score artifacts from an existing Baoma signal audit."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from attbacktrader.reports import to_jsonable
from attbacktrader.reports.scored_entry_allocation_tuning import simulate_precomputed_score_portfolio


DEFAULT_SOURCE_RUN_DIR = Path(
    "reports/baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols"
)
DEFAULT_OUTPUT_DIR = Path("reports/industry-gate-runner-replay-comparison-2006-2025-replay-cash-10m")
DEFAULT_INDUSTRY_RUN_DIR = Path("reports/industry-very-strong-entry-score-runner-2006-2025-replay-cash-10m")
DEFAULT_BALANCED_RUN_DIR = Path("reports/industry-balanced-entry-score-runner-2006-2025-replay-cash-10m")
DEFAULT_NO_INDUSTRY_RUN_DIR = Path("reports/no-industry-strong-entry-score-runner-2006-2025-replay-cash-10m")
FUTURE_FIELDS_EXCLUDED = (
    "exit_date",
    "exit_price",
    "return_pct",
    "realized_return_pct",
    "net_pnl",
    "is_win",
    "holding_days",
    "exit_reason",
)
ACTIONABLE_INTENTS = {"enter", "exit_profit", "exit_loss"}
METRIC_KEYS = (
    "cumulative_return",
    "annualized_return",
    "max_drawdown",
    "sharpe_ratio",
    "sortino_ratio",
    "calmar_ratio",
    "trade_count",
    "closed_trade_count",
    "win_rate",
    "profit_factor",
    "average_trade_return",
    "median_trade_return",
    "average_holding_count",
    "maximum_holding_count",
    "average_cash_ratio",
    "average_exposure",
    "turnover",
)


def build_industry_gate_replay_comparison(
    *,
    source_run_dir: str | Path = DEFAULT_SOURCE_RUN_DIR,
    industry_run_dir: str | Path = DEFAULT_INDUSTRY_RUN_DIR,
    balanced_run_dir: str | Path = DEFAULT_BALANCED_RUN_DIR,
    no_industry_run_dir: str | Path = DEFAULT_NO_INDUSTRY_RUN_DIR,
    start_date: str = "2006-01-01",
    end_date: str = "2025-12-31",
    initial_cash: float = 10_000_000.0,
    max_holding_count: int = 20,
    max_new_positions_per_day: int = 5,
    cash_reserve_ratio: float = 0.05,
    industry_max_new_per_day: int | None = 1,
) -> dict[str, Any]:
    source_dir = Path(source_run_dir)
    industry_dir = Path(industry_run_dir)
    balanced_dir = Path(balanced_run_dir)
    no_industry_dir = Path(no_industry_run_dir)
    stock_pool_order = _load_stock_pool_order(source_dir / "run_plan.json")
    events, extraction = _extract_decision_events(
        source_dir / "signal_audit.parquet",
        stock_pool_order_by_symbol=stock_pool_order,
        start_date=start_date,
        end_date=end_date,
    )
    portfolio_controls = {
        "initial_cash": float(initial_cash),
        "max_holding_count": int(max_holding_count),
        "max_new_positions_per_day": int(max_new_positions_per_day),
        "cash_reserve_ratio": float(cash_reserve_ratio),
        "industry_max_new_per_day": industry_max_new_per_day,
        "board_lot_size": 100,
        "allow_same_day_exit_cash_reuse": True,
        "prefer_unheld_industries": False,
    }
    candidates = [
        _candidate_config(
            "industry_very_strong",
            "含行业保守档",
            industry_dir,
            "industry_very_strong_soil_v1_conservative",
            "entry.score.industry_very_strong_soil_v1",
        ),
        _candidate_config(
            "industry_balanced",
            "含行业均衡档",
            balanced_dir,
            "industry_balanced_soil_v1",
            "entry.score.industry_balanced_soil_v1",
        ),
        _candidate_config(
            "no_industry_strong",
            "no-industry strong baseline",
            no_industry_dir,
            "no_industry_strong_soil_v2_baseline",
            "entry.score.no_industry_strong_soil_v2",
        ),
    ]

    results = []
    for candidate in candidates:
        score_rows = _load_score_rows(candidate["artifact_path"], score_field=str(candidate["score_field"]))
        replay = simulate_precomputed_score_portfolio(
            events,
            score_rows=score_rows,
            score_field=str(candidate["score_field"]),
            score_id=str(candidate["score_id"]),
            portfolio_controls=portfolio_controls,
            missing_score_policy="skip",
            score_gate={"derived_from": "precomputed_industry_gate_artifact"},
        )
        candidate_result = {
            **candidate,
            "score_row_count": len(score_rows),
            "precomputed_score_contract": replay["precomputed_score_contract"],
            "metrics": {**_as_mapping(replay["metrics"]), "final_value": replay.get("final_value")},
            "funnel": replay["funnel"],
            "artifacts": _write_candidate_artifacts(candidate, replay),
        }
        results.append(candidate_result)

    return {
        "schema": "attbacktrader.industry_gate_runner_replay_comparison.v1",
        "source_run_dir": str(source_dir),
        "signal_audit_path": str(source_dir / "signal_audit.parquet"),
        "window": {"start": start_date, "end": end_date},
        "event_extraction": extraction,
        "portfolio_controls": portfolio_controls,
        "candidates": results,
        "comparison": _comparison(results),
    }


def write_industry_gate_replay_comparison(report: Mapping[str, Any], *, output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> tuple[Path, Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "industry_gate_runner_replay_comparison.json"
    markdown_path = out / "industry_gate_runner_replay_comparison.zh.md"
    payload = _jsonable(dict(report))
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_industry_gate_replay_comparison_markdown_zh(payload), encoding="utf-8")
    return json_path, markdown_path


def render_industry_gate_replay_comparison_markdown_zh(report: Mapping[str, Any]) -> str:
    comparison = _as_mapping(report.get("comparison"))
    lines = [
        "# 含行业 Gate Runner Replay 对照",
        "",
        "## 结论",
        "",
        str(comparison.get("summary_zh")),
        "",
        "## 输入",
        "",
        f"- source run：`{report.get('source_run_dir')}`",
        f"- signal audit：`{report.get('signal_audit_path')}`",
        f"- window：`{_as_mapping(report.get('window')).get('start')}` -> `{_as_mapping(report.get('window')).get('end')}`",
        f"- actionable events：{_fmt_int(_as_mapping(report.get('event_extraction')).get('actionable_event_count'))}",
        f"- enter events：{_fmt_int(_as_mapping(report.get('event_extraction')).get('enter_event_count'))}",
        f"- portfolio controls：`{json.dumps(_as_mapping(report.get('portfolio_controls')), ensure_ascii=False, sort_keys=True)}`",
        "",
        "## 结果",
        "",
        "| candidate | score rows | matched enter | missing enter | selected | closed | cumulative | annualized | max drawdown | win rate | PF | final value |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in _as_sequence(report.get("candidates")):
        metrics = _as_mapping(item.get("metrics"))
        contract = _as_mapping(item.get("precomputed_score_contract"))
        lines.append(
            "| "
            f"{item.get('label_zh')} | "
            f"{_fmt_int(item.get('score_row_count'))} | "
            f"{_fmt_int(contract.get('matched_enter_score_count'))} | "
            f"{_fmt_int(contract.get('missing_enter_score_count'))} | "
            f"{_fmt_int(metrics.get('trade_count'))} | "
            f"{_fmt_int(metrics.get('closed_trade_count'))} | "
            f"{_fmt_pct(metrics.get('cumulative_return'))} | "
            f"{_fmt_pct(metrics.get('annualized_return'))} | "
            f"{_fmt_pct(metrics.get('max_drawdown'))} | "
            f"{_fmt_pct(metrics.get('win_rate'))} | "
            f"{_fmt_num(metrics.get('profit_factor'))} | "
            f"{_fmt_int(metrics.get('final_value'))} |"
        )

    lines.extend(
        [
            "",
            "## Lift vs no-industry strong",
            "",
            "| candidate | metric | delta |",
            "|---|---|---:|",
        ]
    )
    for item in _as_sequence(comparison.get("candidate_comparisons")):
        candidate_id = item.get("tested_candidate_id")
        for key, value in _as_mapping(item.get("metric_delta")).items():
            formatter = _fmt_pct if key in {"cumulative_return", "annualized_return", "max_drawdown", "win_rate"} else _fmt_num
            lines.append(f"| {candidate_id} | {key} | {formatter(value)} |")

    lines.extend(
        [
            "",
            "## Artifacts",
            "",
        ]
    )
    for item in _as_sequence(report.get("candidates")):
        lines.append(f"- {item.get('candidate_id')}：`{_as_mapping(item.get('artifacts')).get('output_dir')}`")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = build_industry_gate_replay_comparison(
        source_run_dir=args.source_run_dir,
        industry_run_dir=args.industry_run_dir,
        balanced_run_dir=args.balanced_run_dir,
        no_industry_run_dir=args.no_industry_run_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        initial_cash=args.initial_cash,
        max_holding_count=args.max_holding_count,
        max_new_positions_per_day=args.max_new_positions_per_day,
        cash_reserve_ratio=args.cash_reserve_ratio,
        industry_max_new_per_day=args.industry_max_new_per_day,
    )
    json_path, markdown_path = write_industry_gate_replay_comparison(report, output_dir=args.output_dir)
    print(
        json.dumps(
            {
                "status": "ok",
                "json": str(json_path),
                "markdown": str(markdown_path),
                "summary_zh": report["comparison"]["summary_zh"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay industry gate artifacts from source signal_audit")
    parser.add_argument("--source-run-dir", type=Path, default=DEFAULT_SOURCE_RUN_DIR)
    parser.add_argument("--industry-run-dir", type=Path, default=DEFAULT_INDUSTRY_RUN_DIR)
    parser.add_argument("--balanced-run-dir", type=Path, default=DEFAULT_BALANCED_RUN_DIR)
    parser.add_argument("--no-industry-run-dir", type=Path, default=DEFAULT_NO_INDUSTRY_RUN_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--start-date", default="2006-01-01")
    parser.add_argument("--end-date", default="2025-12-31")
    parser.add_argument("--initial-cash", type=float, default=10_000_000.0)
    parser.add_argument("--max-holding-count", type=int, default=20)
    parser.add_argument("--max-new-positions-per-day", type=int, default=5)
    parser.add_argument("--cash-reserve-ratio", type=float, default=0.05)
    parser.add_argument("--industry-max-new-per-day", type=int, default=1)
    return parser.parse_args(argv)


def _candidate_config(candidate_id: str, label_zh: str, run_dir: Path, score_id: str, score_field: str) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "label_zh": label_zh,
        "run_dir": str(run_dir),
        "artifact_path": str(run_dir / "entry_score_artifact.parquet"),
        "score_id": score_id,
        "score_field": score_field,
    }


def _extract_decision_events(
    signal_audit_path: Path,
    *,
    stock_pool_order_by_symbol: Mapping[str, int],
    start_date: str,
    end_date: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    import pyarrow.parquet as pq

    events: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    scanned = 0
    columns = ["intent_type", "symbol", "trade_date", "signal_values"]
    parquet_file = pq.ParquetFile(signal_audit_path)
    for batch in parquet_file.iter_batches(batch_size=100_000, columns=columns):
        for row in batch.to_pylist():
            scanned += 1
            intent_type = str(row.get("intent_type") or "")
            counts[intent_type] += 1
            if intent_type not in ACTIONABLE_INTENTS:
                continue
            trade_date = str(row.get("trade_date") or "")
            if trade_date < start_date or trade_date > end_date:
                continue
            symbol = str(row.get("symbol") or "")
            signal_values = _decode_json(row.get("signal_values"))
            evidence = _decision_evidence(signal_values)
            events.append(
                {
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "intent_type": intent_type,
                    "price": _signal_row_price(row, signal_values, evidence),
                    "industry": evidence.get("industry.sw_l1.code") or evidence.get("industry"),
                    "stock_pool_order": int(stock_pool_order_by_symbol.get(symbol) or 0),
                    "tradable": True,
                    "evidence": evidence,
                }
            )
    events.sort(key=lambda item: (str(item["trade_date"]), str(item["symbol"]), str(item["intent_type"])))
    return events, {
        "signal_audit_rows_scanned": scanned,
        "actionable_event_count": len(events),
        "enter_event_count": sum(1 for event in events if event["intent_type"] == "enter"),
        "intent_type_counts": dict(counts),
    }


def _load_score_rows(path: str | Path, *, score_field: str) -> list[dict[str, Any]]:
    frame = pd.read_parquet(path)
    required = {"symbol", "entry_date", score_field}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{path} missing columns: {missing}")
    rows = []
    for row in frame.to_dict("records"):
        rows.append(
            {
                "symbol": str(row["symbol"]),
                "trade_date": _date_label(row["entry_date"]),
                score_field: float(row[score_field]),
            }
        )
    return rows


def _write_candidate_artifacts(candidate: Mapping[str, Any], replay: Mapping[str, Any]) -> dict[str, str]:
    out = Path(str(candidate["run_dir"]))
    out.mkdir(parents=True, exist_ok=True)
    (out / "entry_score_contract.json").write_text(
        json.dumps(_jsonable(replay["precomputed_score_contract"]), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out / "entry_score_replay_summary.json").write_text(
        json.dumps(
            _jsonable(
                {
                    "candidate_id": candidate["candidate_id"],
                    "score_id": candidate["score_id"],
                    "score_field": candidate["score_field"],
                    "artifact_path": candidate["artifact_path"],
                    "precomputed_score_contract": replay["precomputed_score_contract"],
                    "metrics": replay["metrics"],
                    "funnel": replay["funnel"],
                    "portfolio_controls": replay["portfolio_controls"],
                }
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _records_to_parquet(out / "entry_score_selected_entries.parquet", _as_sequence(replay.get("executed_entries")))
    _records_to_parquet(out / "entry_score_blocked_entries.parquet", _as_sequence(replay.get("blocked_entries")))
    _records_to_parquet(out / "entry_score_equity_curve.parquet", _as_sequence(replay.get("equity_curve")))
    return {
        "output_dir": str(out),
        "contract": str(out / "entry_score_contract.json"),
        "summary": str(out / "entry_score_replay_summary.json"),
        "selected_entries": str(out / "entry_score_selected_entries.parquet"),
        "blocked_entries": str(out / "entry_score_blocked_entries.parquet"),
        "equity_curve": str(out / "entry_score_equity_curve.parquet"),
    }


def _comparison(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_id = {str(item["candidate_id"]): item for item in results}
    baseline = _as_mapping(_as_mapping(by_id["no_industry_strong"]).get("metrics"))
    comparisons = [
        _candidate_comparison(by_id, baseline, tested_candidate_id)
        for tested_candidate_id in ("industry_very_strong", "industry_balanced")
        if tested_candidate_id in by_id
    ]
    summary_parts = [
        (
            f"{item['tested_candidate_id']}：{item['verdict']}，"
            f"年化差 {_fmt_pct(_as_mapping(item.get('metric_delta')).get('annualized_return'))}，"
            f"PF 差 {_fmt_num(_as_mapping(item.get('metric_delta')).get('profit_factor'))}，"
            f"selected 差 {_fmt_num(_as_mapping(item.get('metric_delta')).get('trade_count'))}"
        )
        for item in comparisons
    ]
    return {
        "baseline_candidate_id": "no_industry_strong",
        "candidate_comparisons": comparisons,
        "summary_zh": "；".join(summary_parts) + "。",
    }


def _candidate_comparison(
    by_id: Mapping[str, Mapping[str, Any]],
    baseline: Mapping[str, Any],
    tested_candidate_id: str,
) -> dict[str, Any]:
    tested = _as_mapping(_as_mapping(by_id[tested_candidate_id]).get("metrics"))
    delta = {
        key: _delta(tested.get(key), baseline.get(key))
        for key in METRIC_KEYS
        if _delta(tested.get(key), baseline.get(key)) is not None
    }
    pf_delta = delta.get("profit_factor")
    ann_delta = delta.get("annualized_return")
    verdict = "胜出" if (pf_delta is not None and pf_delta > 0 and ann_delta is not None and ann_delta > 0) else "未胜出"
    return {
        "baseline_candidate_id": "no_industry_strong",
        "tested_candidate_id": tested_candidate_id,
        "verdict": verdict,
        "metric_delta": delta,
    }


def _load_stock_pool_order(run_plan_path: Path) -> dict[str, int]:
    plan = json.loads(run_plan_path.read_text(encoding="utf-8"))
    stock_pool_file = Path(str(_as_mapping(plan.get("data")).get("stock_pool_file")))
    if not stock_pool_file.is_absolute():
        stock_pool_file = Path.cwd() / stock_pool_file
    frame = pd.read_csv(stock_pool_file)
    symbol_col = "ts_code" if "ts_code" in frame.columns else "symbol"
    return {str(symbol): idx for idx, symbol in enumerate(frame[symbol_col].astype(str), start=1)}


def _decode_json(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not value:
        return {}
    return json.loads(str(value))


def _decision_evidence(signal_values: Mapping[str, Any]) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    attribution = _as_mapping(signal_values.get("attribution"))
    for bucket in ("values", "categories", "checks"):
        evidence.update(dict(_as_mapping(attribution.get(bucket))))
    evidence.update(dict(_as_mapping(signal_values.get("evidence"))))
    for field in FUTURE_FIELDS_EXCLUDED:
        evidence.pop(field, None)
    return json.loads(json.dumps(evidence, ensure_ascii=False, default=str))


def _signal_row_price(row: Mapping[str, Any], signal_values: Mapping[str, Any], evidence: Mapping[str, Any]) -> float:
    for value in (
        row.get("price"),
        evidence.get("symbol.close"),
        evidence.get("symbol.close.current"),
        signal_values.get("close"),
        signal_values.get("current_close"),
    ):
        number = _number_or_none(value)
        if number is not None:
            return number
    raise ValueError(f"missing price for {row.get('symbol')} {row.get('trade_date')}")


def _records_to_parquet(path: Path, records: Sequence[Any]) -> None:
    frame = pd.DataFrame([_parquet_record(record) for record in records])
    frame.to_parquet(path, index=False, compression="zstd")


def _parquet_record(record: Any) -> dict[str, object]:
    payload = to_jsonable(record)
    if not isinstance(payload, Mapping):
        return {"value_json": _compact_json(payload)}
    return {str(key): _parquet_cell(value) for key, value in payload.items()}


def _parquet_cell(value: Any) -> Any:
    value = to_jsonable(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return _compact_json(value)


def _compact_json(value: Any) -> str:
    return json.dumps(to_jsonable(value), ensure_ascii=False, separators=(",", ":"))


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _delta(left: Any, right: Any) -> float | None:
    left_number = _number_or_none(left)
    right_number = _number_or_none(right)
    if left_number is None or right_number is None:
        return None
    return left_number - right_number


def _date_label(value: Any) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _jsonable(value: Any) -> Any:
    return to_jsonable(value)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or value is None:
        return ()
    return value if isinstance(value, Sequence) else ()


def _fmt_int(value: Any) -> str:
    number = _number_or_none(value)
    return "-" if number is None else f"{number:,.0f}"


def _fmt_pct(value: Any) -> str:
    number = _number_or_none(value)
    return "-" if number is None else f"{number:.2%}"


def _fmt_num(value: Any) -> str:
    number = _number_or_none(value)
    return "-" if number is None else f"{number:.6g}"


if __name__ == "__main__":
    raise SystemExit(main())
