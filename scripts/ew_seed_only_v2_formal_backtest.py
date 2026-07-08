"""Audit and formally validate ew_seed_only_v2 on real Baoma decision events.

The script is backtest-only. It injects only the decision-time score into
entry events and reuses the scored portfolio simulator for ranking/capacity
validation. It does not alter live strategy configuration.
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from attbacktrader.reports import scored_entry_allocation_tuning as scored_sim  # noqa: E402


BASE_RUN_DIR = ROOT / "reports" / "baoma-v1-dynamic-hs300-only-2006-2025-strict-t1-no-industry-attribution-normalized-symbols"
SCORED_TRADE_DETAIL = (
    ROOT
    / "reports"
    / "evidence-weighted-ranking-validation-hs300-only-2006-2025"
    / "evidence_weighted_scored_trade_detail.parquet"
)
OUTPUT_DIR = ROOT / "reports" / "ew-seed-only-v2-formal-backtest-hs300-only-2013-2025"
SCORE_FIELD = "entry.score.ew_seed_only_v2"
TEST_START = "2013-01-01"
TEST_END = "2025-12-31"
INITIAL_CASH = 10_000_000.0
MAX_NEW_VALUES = (1, 3, 5)
MAX_HOLD_VALUES = (10, 20)
MARKET_CYCLE_PERIODS = (
    ("walk_forward_full", "2013-2025 全测试窗", "2013-01-01", "2025-12-31", "全样本"),
    ("cycle_2010_2013", "2010-2013 震荡弱市（测试覆盖2013）", "2013-01-01", "2013-12-31", "震荡弱市"),
    ("cycle_2014_2015", "2014-2015 杠杆牛/股灾", "2014-01-01", "2015-12-31", "杠杆牛/股灾"),
    ("cycle_2016_2017", "2016-2017 修复/蓝筹强", "2016-01-01", "2017-12-31", "修复/蓝筹强"),
    ("cycle_2018", "2018 去杠杆熊市", "2018-01-01", "2018-12-31", "去杠杆熊市"),
    ("cycle_2019_2020", "2019-2020 核心资产牛", "2019-01-01", "2020-12-31", "核心资产牛"),
    ("cycle_2021", "2021 高位切换/转弱", "2021-01-01", "2021-12-31", "高位切换/转弱"),
    ("cycle_2022_2023", "2022-2023 下行熊市", "2022-01-01", "2023-12-31", "下行熊市"),
    ("cycle_2024_2025", "2024-2025 修复期", "2024-01-01", "2025-12-31", "修复期"),
)
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


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    score_frame = load_score_frame(SCORED_TRADE_DETAIL)
    score_by_key = build_score_map(score_frame)
    stock_pool_order = load_stock_pool_order(BASE_RUN_DIR / "run_plan.json")
    events, extract_profile = extract_decision_events(
        BASE_RUN_DIR / "signal_audit.parquet",
        score_by_key=score_by_key,
        stock_pool_order_by_symbol=stock_pool_order,
    )
    score_rows = precomputed_score_rows(score_frame)

    contract = build_contract(score_frame, events, score_by_key, extract_profile)
    metrics, period_metrics, yearly_metrics, selected, closed, blocked, equity = run_validation_grid(events, score_rows)

    metrics = add_baseline_lifts(metrics, key_cols=["max_new_positions_per_day", "max_holding_count"])
    period_metrics = add_baseline_lifts(
        period_metrics,
        key_cols=["period_id", "max_new_positions_per_day", "max_holding_count"],
    )
    yearly_metrics = add_baseline_lifts(
        yearly_metrics,
        key_cols=["year", "max_new_positions_per_day", "max_holding_count"],
    )

    write_outputs(
        contract=contract,
        events=events,
        metrics=metrics,
        period_metrics=period_metrics,
        yearly_metrics=yearly_metrics,
        selected=selected,
        closed=closed,
        blocked=blocked,
        equity=equity,
    )
    print(
        json.dumps(
            {
                "output_dir": str(OUTPUT_DIR),
                "event_count": len(events),
                "enter_event_count": sum(1 for event in events if event["intent_type"] == "enter"),
                "contract": str(OUTPUT_DIR / "ew_seed_only_v2_score_contract.json"),
                "report": str(OUTPUT_DIR / "ew_seed_only_v2_formal_backtest.zh.md"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def load_score_frame(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_parquet(path).copy()
    df["entry_date"] = pd.to_datetime(df["entry_date"]).dt.strftime("%Y-%m-%d")
    df["ew_seed_only_score"] = pd.to_numeric(df["ew_seed_only_score"], errors="coerce")
    return df


def build_score_map(df: pd.DataFrame) -> dict[tuple[str, str], dict[str, Any]]:
    if df.duplicated(["symbol", "entry_date"]).any():
        dup_count = int(df.duplicated(["symbol", "entry_date"]).sum())
        raise ValueError(f"score detail contains duplicated symbol-entry_date keys: {dup_count}")
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in df.itertuples(index=False):
        result[(str(row.symbol), str(row.entry_date))] = {
            "score": float(row.ew_seed_only_score),
            "seed_v2_candidate_score": float(row.seed_v2_candidate_score),
            "fold_id": str(row.fold_id),
            "train_start_year": int(row.train_start_year),
            "train_end_year": int(row.train_end_year),
            "test_year": int(row.test_year),
        }
    return result


def precomputed_score_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in df.itertuples(index=False):
        rows.append(
            {
                "symbol": str(row.symbol),
                "trade_date": str(row.entry_date),
                SCORE_FIELD: float(row.ew_seed_only_score),
                "seed_v2_candidate_score": float(row.seed_v2_candidate_score),
                "fold_id": str(row.fold_id),
                "train_start_year": int(row.train_start_year),
                "train_end_year": int(row.train_end_year),
                "test_year": int(row.test_year),
            }
        )
    return rows


def load_stock_pool_order(run_plan_path: Path) -> dict[str, int]:
    plan = json.loads(run_plan_path.read_text(encoding="utf-8"))
    stock_pool_file = Path(plan["data"]["stock_pool_file"])
    frame = pd.read_csv(stock_pool_file)
    symbol_col = "ts_code" if "ts_code" in frame.columns else "symbol"
    return {str(symbol): idx for idx, symbol in enumerate(frame[symbol_col].astype(str), start=1)}


def extract_decision_events(
    signal_audit_path: Path,
    *,
    score_by_key: Mapping[tuple[str, str], Mapping[str, Any]],
    stock_pool_order_by_symbol: Mapping[str, int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise ImportError("pyarrow is required to scan signal_audit.parquet") from exc

    events: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    matched_enter = 0
    missing_score_enter = 0
    scanned = 0
    columns = ["intent_type", "symbol", "trade_date", "signal_values", "blocked_by"]
    parquet_file = pq.ParquetFile(signal_audit_path)
    for batch in parquet_file.iter_batches(batch_size=100_000, columns=columns):
        for row in batch.to_pylist():
            scanned += 1
            intent_type = str(row.get("intent_type") or "")
            if intent_type not in {"enter", "exit_profit", "exit_loss"}:
                continue
            trade_date = str(row.get("trade_date") or "")
            if trade_date < TEST_START or trade_date > TEST_END:
                continue
            symbol = str(row.get("symbol") or "")
            signal_values = decode_json(row.get("signal_values"))
            evidence = decision_evidence(signal_values)
            price = signal_row_price(row, signal_values, evidence)
            event = {
                "symbol": symbol,
                "trade_date": trade_date,
                "intent_type": intent_type,
                "price": price,
                "industry": evidence.get("industry.sw_l1.code") or evidence.get("industry"),
                "stock_pool_order": int(stock_pool_order_by_symbol.get(symbol) or 0),
                "tradable": True,
                "evidence": evidence,
            }
            if intent_type == "enter":
                score = score_by_key.get((symbol, trade_date))
                if score is None:
                    event["evidence"][SCORE_FIELD] = None
                    event["evidence"]["entry.score.ew_seed_only_v2_status"] = "missing"
                    missing_score_enter += 1
                else:
                    event["evidence"][SCORE_FIELD] = float(score["score"])
                    event["evidence"]["entry.score.ew_seed_only_v2_status"] = "present"
                    event["evidence"]["entry.score.ew_seed_only_v2_fold_id"] = score["fold_id"]
                    event["evidence"]["entry.score.ew_seed_only_v2_train_end_year"] = score["train_end_year"]
                    matched_enter += 1
            events.append(event)
            counts[intent_type] += 1

    events.sort(key=lambda item: (str(item["trade_date"]), str(item["symbol"]), str(item["intent_type"])))
    return events, {
        "schema": "attbacktrader.ew_seed_only_v2_decision_event_extract_profile.v1",
        "source_signal_audit": str(signal_audit_path),
        "scanned_rows": scanned,
        "event_count": len(events),
        "intent_type_counts": dict(counts),
        "matched_enter_score_count": matched_enter,
        "missing_enter_score_count": missing_score_enter,
        "test_start": TEST_START,
        "test_end": TEST_END,
    }


def decode_json(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not value:
        return {}
    return json.loads(str(value))


def decision_evidence(signal_values: Mapping[str, Any]) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    attribution = as_mapping(signal_values.get("attribution"))
    for bucket in ("values", "categories", "checks"):
        evidence.update(dict(as_mapping(attribution.get(bucket))))
    evidence.update(dict(as_mapping(signal_values.get("evidence"))))
    for field in FUTURE_FIELDS_EXCLUDED:
        evidence.pop(field, None)
    return json.loads(json.dumps(evidence, ensure_ascii=False, default=str))


def signal_row_price(row: Mapping[str, Any], signal_values: Mapping[str, Any], evidence: Mapping[str, Any]) -> float:
    for value in (
        row.get("price"),
        evidence.get("symbol.close"),
        evidence.get("symbol.close.current"),
        signal_values.get("close"),
        signal_values.get("current_close"),
    ):
        number = number_or_none(value)
        if number is not None:
            return number
    raise ValueError(f"missing price for {row.get('symbol')} {row.get('trade_date')}")


def build_contract(
    score_frame: pd.DataFrame,
    events: list[dict[str, Any]],
    score_by_key: Mapping[tuple[str, str], Mapping[str, Any]],
    extract_profile: Mapping[str, Any],
) -> dict[str, Any]:
    enter_events = [event for event in events if event["intent_type"] == "enter"]
    enter_keys = {(event["symbol"], event["trade_date"]) for event in enter_events}
    score_keys = set(score_by_key)
    score_values = pd.to_numeric(score_frame["ew_seed_only_score"], errors="coerce")
    year_counts = score_frame.groupby("test_year").size().rename("score_trade_count").reset_index()
    score_quantiles = score_values.quantile([0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]).to_dict()
    return {
        "schema": "attbacktrader.ew_seed_only_v2_score_contract.v1",
        "roadmap_check": "第5步准备：score contract + 正式候选池资金约束回测；未改实盘，未加入 soil 主分，未继续优化 gate。",
        "score_id": "ew_seed_only_v2",
        "score_field": SCORE_FIELD,
        "scope": "backtest_only",
        "source_scored_trade_detail": str(SCORED_TRADE_DETAIL),
        "source_run_dir": str(BASE_RUN_DIR),
        "test_window": {"start": TEST_START, "end": TEST_END},
        "score_detail": {
            "row_count": int(len(score_frame)),
            "symbol_count": int(score_frame["symbol"].nunique()),
            "entry_date_min": str(score_frame["entry_date"].min()),
            "entry_date_max": str(score_frame["entry_date"].max()),
            "duplicate_symbol_entry_date_count": int(score_frame.duplicated(["symbol", "entry_date"]).sum()),
            "missing_score_count": int(score_frame["ew_seed_only_score"].isna().sum()),
            "non_finite_score_count": int((~score_values.map(lambda value: math.isfinite(float(value)) if pd.notna(value) else False)).sum()),
            "score_quantiles": {str(key): float(value) for key, value in score_quantiles.items()},
            "year_counts": year_counts.to_dict("records"),
        },
        "decision_event_coverage": {
            "enter_event_count": len(enter_events),
            "enter_score_matched_count": int(len(enter_keys & score_keys)),
            "enter_score_missing_count": int(len(enter_keys - score_keys)),
            "score_keys_not_in_enter_events_count": int(len(score_keys - enter_keys)),
            "match_rate_pct": float(len(enter_keys & score_keys) / len(enter_events) * 100) if enter_events else None,
        },
        "leakage_controls": {
            "injected_fields": [SCORE_FIELD, "entry.score.ew_seed_only_v2_status"],
            "future_fields_excluded": list(FUTURE_FIELDS_EXCLUDED),
            "notes": [
                "Only symbol, decision date, score, fold id, and train_end_year are injected into enter events.",
                "Return, PnL, exit date, exit price, win/loss, and holding-day fields are not injected.",
                "The upstream evidence-weighted score uses walk-forward folds; each test year is scored using prior years only.",
            ],
        },
        "extract_profile": dict(extract_profile),
    }


def run_validation_grid(events: list[dict[str, Any]], score_rows: list[dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    metrics_rows: list[dict[str, Any]] = []
    period_rows: list[dict[str, Any]] = []
    yearly_rows: list[dict[str, Any]] = []
    selected_rows: list[dict[str, Any]] = []
    closed_rows: list[dict[str, Any]] = []
    blocked_rows: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []

    for max_new in MAX_NEW_VALUES:
        for max_hold in MAX_HOLD_VALUES:
            for strategy_id, unscored in (("baseline_stock_pool_order", True), ("ew_seed_only_v2", False)):
                result = simulate(
                    events,
                    score_rows=score_rows,
                    strategy_id=strategy_id,
                    max_new=max_new,
                    max_hold=max_hold,
                    unscored_baseline=unscored,
                )
                metrics_rows.append(
                    {
                        "strategy_id": strategy_id,
                        "max_new_positions_per_day": max_new,
                        "max_holding_count": max_hold,
                        **result["metrics"],
                    }
                )
                selected_rows.extend(add_strategy_rows(result["executed_entries"], strategy_id, max_new, max_hold))
                closed_rows.extend(add_strategy_rows(result["closed_trades"], strategy_id, max_new, max_hold))
                blocked_rows.extend(add_strategy_rows(result["blocked_entries"], strategy_id, max_new, max_hold))
                equity_rows.extend(add_strategy_rows(result["equity_curve"], strategy_id, max_new, max_hold))

                for period_id, period_zh, start, end, market_cycle_regime in MARKET_CYCLE_PERIODS:
                    period_events = [event for event in events if start <= str(event["trade_date"]) <= end]
                    period_result = simulate(
                        period_events,
                        score_rows=score_rows,
                        strategy_id=strategy_id,
                        max_new=max_new,
                        max_hold=max_hold,
                        unscored_baseline=unscored,
                    )
                    period_rows.append(
                        {
                            "strategy_id": strategy_id,
                            "period_id": period_id,
                            "period_zh": period_zh,
                            "market_cycle_regime": market_cycle_regime,
                            "max_new_positions_per_day": max_new,
                            "max_holding_count": max_hold,
                            **period_result["metrics"],
                        }
                    )

                years = sorted({str(event["trade_date"])[:4] for event in events})
                for year in years:
                    year_events = [event for event in events if str(event["trade_date"]).startswith(year)]
                    year_result = simulate(
                        year_events,
                        score_rows=score_rows,
                        strategy_id=strategy_id,
                        max_new=max_new,
                        max_hold=max_hold,
                        unscored_baseline=unscored,
                    )
                    yearly_rows.append(
                        {
                            "strategy_id": strategy_id,
                            "year": int(year),
                            "max_new_positions_per_day": max_new,
                            "max_holding_count": max_hold,
                            **year_result["metrics"],
                        }
                    )

    return (
        pd.DataFrame(metrics_rows),
        pd.DataFrame(period_rows),
        pd.DataFrame(yearly_rows),
        pd.DataFrame(selected_rows),
        pd.DataFrame(closed_rows),
        pd.DataFrame(blocked_rows),
        pd.DataFrame(equity_rows),
    )


def simulate(
    events: list[dict[str, Any]],
    *,
    score_rows: list[dict[str, Any]],
    strategy_id: str,
    max_new: int,
    max_hold: int,
    unscored_baseline: bool,
) -> dict[str, Any]:
    portfolio_controls = {
        "initial_cash": INITIAL_CASH,
        "max_holding_count": max_hold,
        "max_new_positions_per_day": max_new,
        "cash_reserve_ratio": 0.05,
        "industry_max_new_per_day": 1,
        "board_lot_size": 100,
        "allow_same_day_exit_cash_reuse": True,
        "prefer_unheld_industries": False,
    }
    return scored_sim.simulate_precomputed_score_portfolio(
        events,
        score_rows=score_rows,
        score_field=SCORE_FIELD,
        score_id="ew_seed_only_v2",
        portfolio_controls=portfolio_controls,
        missing_score_policy="skip",
        score_gate={"derived_from": "precomputed_ew_seed_only_v2"},
        unscored_baseline=unscored_baseline,
    )


def add_strategy_rows(rows: Iterable[Mapping[str, Any]], strategy_id: str, max_new: int, max_hold: int) -> list[dict[str, Any]]:
    return [
        {
            "strategy_id": strategy_id,
            "max_new_positions_per_day": max_new,
            "max_holding_count": max_hold,
            **json.loads(json.dumps(dict(row), ensure_ascii=False, default=str)),
        }
        for row in rows
    ]


def add_baseline_lifts(df: pd.DataFrame, *, key_cols: list[str]) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    base_cols = [
        *key_cols,
        "annualized_return",
        "max_drawdown",
        "win_rate",
        "profit_factor",
        "trade_count",
    ]
    base = out[out["strategy_id"].eq("baseline_stock_pool_order")][base_cols].rename(
        columns={
            "annualized_return": "baseline_annualized_return",
            "max_drawdown": "baseline_max_drawdown",
            "win_rate": "baseline_win_rate",
            "profit_factor": "baseline_profit_factor",
            "trade_count": "baseline_trade_count",
        }
    )
    out = out.merge(base, on=key_cols, how="left")
    out["annualized_lift"] = out["annualized_return"] - out["baseline_annualized_return"]
    out["max_drawdown_delta"] = out["max_drawdown"] - out["baseline_max_drawdown"]
    out["win_rate_lift"] = out["win_rate"] - out["baseline_win_rate"]
    out["profit_factor_lift"] = out["profit_factor"] - out["baseline_profit_factor"]
    return out


def write_outputs(
    *,
    contract: Mapping[str, Any],
    events: list[dict[str, Any]],
    metrics: pd.DataFrame,
    period_metrics: pd.DataFrame,
    yearly_metrics: pd.DataFrame,
    selected: pd.DataFrame,
    closed: pd.DataFrame,
    blocked: pd.DataFrame,
    equity: pd.DataFrame,
) -> None:
    contract_path = OUTPUT_DIR / "ew_seed_only_v2_score_contract.json"
    contract_md_path = OUTPUT_DIR / "ew_seed_only_v2_score_contract.zh.md"
    events_meta_path = OUTPUT_DIR / "decision_event_table_ew_seed_only_v2.json"
    events_path = OUTPUT_DIR / "decision_events_ew_seed_only_v2.parquet"
    metrics_path = OUTPUT_DIR / "formal_backtest_metrics.csv"
    period_path = OUTPUT_DIR / "formal_backtest_period_metrics.csv"
    yearly_path = OUTPUT_DIR / "formal_backtest_yearly_metrics.csv"
    selected_path = OUTPUT_DIR / "formal_backtest_selected_entries.parquet"
    closed_path = OUTPUT_DIR / "formal_backtest_closed_trades.parquet"
    blocked_path = OUTPUT_DIR / "formal_backtest_blocked_entries.parquet"
    equity_path = OUTPUT_DIR / "formal_backtest_equity_curves.parquet"
    report_path = OUTPUT_DIR / "ew_seed_only_v2_formal_backtest.zh.md"

    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    contract_md_path.write_text(render_contract_markdown(contract), encoding="utf-8")
    write_event_table(events, metadata_path=events_meta_path, events_path=events_path)
    metrics.to_csv(metrics_path, index=False, encoding="utf-8-sig")
    period_metrics.to_csv(period_path, index=False, encoding="utf-8-sig")
    yearly_metrics.to_csv(yearly_path, index=False, encoding="utf-8-sig")
    selected.to_parquet(selected_path, index=False)
    closed.to_parquet(closed_path, index=False)
    blocked.to_parquet(blocked_path, index=False)
    equity.to_parquet(equity_path, index=False)
    report_path.write_text(
        render_report(
            contract=contract,
            metrics=metrics,
            period_metrics=period_metrics,
            yearly_metrics=yearly_metrics,
            artifacts={
                "score_contract": contract_path,
                "score_contract_md": contract_md_path,
                "decision_event_table": events_meta_path,
                "decision_events": events_path,
                "metrics": metrics_path,
                "period_metrics": period_path,
                "yearly_metrics": yearly_path,
                "selected_entries": selected_path,
                "closed_trades": closed_path,
                "blocked_entries": blocked_path,
                "equity_curves": equity_path,
            },
        ),
        encoding="utf-8",
    )


def write_event_table(events: list[dict[str, Any]], *, metadata_path: Path, events_path: Path) -> None:
    rows = []
    for event in events:
        item = dict(event)
        evidence = item.pop("evidence", {})
        item["evidence_json"] = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        rows.append(item)
    pd.DataFrame(rows).to_parquet(events_path, index=False, compression="zstd")
    metadata = {
        "schema": scored_sim.STRATEGY_DECISION_EVENT_TABLE_SCHEMA,
        "event_count": len(events),
        "event_storage": {
            "format": "parquet",
            "path": events_path.name,
            "compression": "zstd",
            "evidence_column": "evidence_json",
        },
        "stores": ["actionable decision intents", "decision-time evidence", "ew_seed_only_v2 score"],
        "scope": "backtest_only",
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def render_contract_markdown(contract: Mapping[str, Any]) -> str:
    coverage = as_mapping(contract.get("decision_event_coverage"))
    detail = as_mapping(contract.get("score_detail"))
    return "\n".join(
        [
            "# ew_seed_only_v2 Score Contract",
            "",
            "## Roadmap 对照",
            "",
            f"- {contract.get('roadmap_check')}",
            "",
            "## 数据契约",
            "",
            f"- score 字段: `{contract.get('score_field')}`",
            f"- 使用窗口: `{as_mapping(contract.get('test_window')).get('start')}` 到 `{as_mapping(contract.get('test_window')).get('end')}`",
            f"- score 明细行数: `{detail.get('row_count')}`",
            f"- symbol-entry_date 重复: `{detail.get('duplicate_symbol_entry_date_count')}`",
            f"- score 缺失: `{detail.get('missing_score_count')}`",
            "",
            "## 覆盖率",
            "",
            f"- enter 事件数: `{coverage.get('enter_event_count')}`",
            f"- 匹配 score: `{coverage.get('enter_score_matched_count')}`",
            f"- 缺失 score: `{coverage.get('enter_score_missing_count')}`",
            f"- 匹配率: `{fmt_pct((coverage.get('match_rate_pct') or 0) / 100)}`",
            "",
            "## 泄漏控制",
            "",
            *[f"- 未注入未来字段: `{field}`" for field in FUTURE_FIELDS_EXCLUDED],
        ]
    )


def render_report(
    *,
    contract: Mapping[str, Any],
    metrics: pd.DataFrame,
    period_metrics: pd.DataFrame,
    yearly_metrics: pd.DataFrame,
    artifacts: Mapping[str, Path],
) -> str:
    core = metrics[metrics["strategy_id"].isin(["baseline_stock_pool_order", "ew_seed_only_v2"])].sort_values(
        ["max_holding_count", "max_new_positions_per_day", "strategy_id"]
    )
    cycle_top3 = period_metrics[
        (period_metrics["max_new_positions_per_day"].eq(3))
        & (period_metrics["max_holding_count"].eq(20))
        & (period_metrics["strategy_id"].isin(["baseline_stock_pool_order", "ew_seed_only_v2"]))
    ].copy()
    yearly_top3 = yearly_metrics[
        (yearly_metrics["max_new_positions_per_day"].eq(3))
        & (yearly_metrics["max_holding_count"].eq(20))
        & (yearly_metrics["strategy_id"].isin(["baseline_stock_pool_order", "ew_seed_only_v2"]))
    ].copy()
    coverage = as_mapping(contract.get("decision_event_coverage"))
    lines = [
        "# ew_seed_only_v2 正式候选池回测对照",
        "",
        "## Roadmap 对照",
        "",
        "- 本报告属于第 5 步：score contract + 正式候选池资金约束回测。",
        "- 没有改正式 runner 或实盘配置；没有加入 soil 主排名分；没有继续优化 gate。",
        "",
        "## Contract 摘要",
        "",
        f"- enter 事件: `{coverage.get('enter_event_count')}`",
        f"- score 匹配: `{coverage.get('enter_score_matched_count')}`",
        f"- score 缺失: `{coverage.get('enter_score_missing_count')}`",
        f"- 匹配率: `{fmt_pct((coverage.get('match_rate_pct') or 0) / 100)}`",
        "",
        "## 全样本对照",
        "",
        *table(
            core,
            [
                "strategy_id",
                "max_new_positions_per_day",
                "max_holding_count",
                "trade_count",
                "annualized_return",
                "max_drawdown",
                "win_rate",
                "profit_factor",
                "annualized_lift",
            ],
            40,
        ),
        "",
        "## Market-cycle Top3 / MaxHold20",
        "",
        *table(
            cycle_top3,
            [
                "strategy_id",
                "period_zh",
                "market_cycle_regime",
                "trade_count",
                "annualized_return",
                "max_drawdown",
                "win_rate",
                "profit_factor",
                "annualized_lift",
            ],
            40,
        ),
        "",
        "## 年度 Top3 / MaxHold20",
        "",
        *table(
            yearly_top3,
            [
                "strategy_id",
                "year",
                "trade_count",
                "annualized_return",
                "max_drawdown",
                "win_rate",
                "profit_factor",
                "annualized_lift",
            ],
            80,
        ),
        "",
        "## 初步判断",
        "",
        "- 如果 `ew_seed_only_v2` 在完整事件流下仍优于 stock-pool-order baseline，才进入 runner-level 接口设计。",
        "- 如果优势只来自 MaxHold/TopN 代理口径，在正式事件流里消失，就回到 score contract 和候选池覆盖率排查。",
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
        lines.append("| " + " | ".join(fmt_value(row[col], col) for col in columns) + " |")
    return lines


def fmt_value(value: Any, column: str) -> str:
    if value is None:
        return "-"
    try:
        if pd.isna(value):
            return "-"
    except (TypeError, ValueError):
        pass
    if isinstance(value, float):
        if any(key in column for key in ("return", "drawdown", "win_rate", "lift")):
            return fmt_pct(value)
        return f"{value:.4f}"
    return str(value)


def fmt_pct(value: Any) -> str:
    number = number_or_none(value)
    if number is None:
        return "-"
    return f"{number * 100:.2f}%"


def as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def number_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


if __name__ == "__main__":
    raise SystemExit(main())
