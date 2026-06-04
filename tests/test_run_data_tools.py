import json
from pathlib import Path

from attbacktrader.cli import run_data_dictionary as run_data_dictionary_cli
from attbacktrader.cli import run_data_drilldown as run_data_drilldown_cli
from attbacktrader.cli import run_data_drilldown_batch as run_data_drilldown_batch_cli
from attbacktrader.cli import run_data_overview as run_data_overview_cli
from attbacktrader.cli import run_data_attribution_index as run_data_attribution_index_cli
from attbacktrader.reports import (
    build_run_data_attribution_index,
    build_run_data_dictionary,
    build_run_data_drilldown,
    build_run_data_drilldown_batch,
    build_run_data_overview,
    render_run_data_attribution_index_markdown_zh,
    render_run_data_dictionary_markdown_zh,
    render_run_data_drilldown_markdown_zh,
    render_run_data_drilldown_batch_markdown_zh,
    render_run_data_overview_markdown_zh,
    write_run_data_attribution_index,
    write_run_data_dictionary,
    write_run_data_drilldown,
    write_run_data_drilldown_batch,
    write_run_data_overview,
)


def test_run_data_dictionary_describes_artifacts_and_reason_labels(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)

    dictionary = build_run_data_dictionary(run_dir)
    markdown = render_run_data_dictionary_markdown_zh(dictionary)
    json_path, markdown_path = write_run_data_dictionary(dictionary, output_dir=tmp_path / "dictionary")

    assert dictionary["schema"] == "attbacktrader.run_data_dictionary.v1"
    assert dictionary["run_id"] == "run-data-test"
    assert dictionary["reason_code_labels"]["BOARD_LOT_TOO_SMALL"] == "不足一手，无法下单"
    assert any(artifact["artifact"] == "trade_review" for artifact in dictionary["artifacts"])
    assert any(artifact["artifact"] == "strategy_environment_profile" for artifact in dictionary["artifacts"])
    assert "回测数据字典" in markdown
    assert "trade_review.json" in markdown
    assert "strategy_environment_profile.json" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def test_run_data_overview_summarizes_counts_and_translated_blocks(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)

    overview = build_run_data_overview(run_dir, top_symbols=2)
    markdown = render_run_data_overview_markdown_zh(overview)
    json_path, markdown_path = write_run_data_overview(overview, output_dir=tmp_path / "overview")

    assert overview["schema"] == "attbacktrader.run_data_overview.v1"
    assert overview["metrics"]["returns"]["final_equity"] == 1010000.0
    assert overview["trades"]["closed_trade_count"] == 2
    assert overview["trades"]["open_position_count"] == 1
    assert overview["signals"]["signal_intent_count"] == 3
    assert overview["execution"]["event_count"] == 3
    assert overview["review"]["opportunity_count"] == 1
    assert overview["signals"]["blocked_by_counts"][0]["label_zh"] == "不足一手，无法下单"
    assert "回测数据总览" in markdown
    assert "BOARD_LOT_TOO_SMALL" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def test_run_data_drilldown_wraps_review_sample_with_human_summary(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)

    drilldown = build_run_data_drilldown(run_dir, kind="opportunity", sample_index=1, context_limit=5)
    markdown = render_run_data_drilldown_markdown_zh(drilldown)
    json_path, markdown_path = write_run_data_drilldown(drilldown, output_dir=tmp_path / "drilldown")

    assert drilldown["schema"] == "attbacktrader.run_data_drilldown.v1"
    assert drilldown["sample_id"] == "opportunity.1"
    assert drilldown["summary"]["blocked_by"] == "BOARD_LOT_TOO_SMALL"
    assert drilldown["summary"]["blocked_by_zh"] == "不足一手，无法下单"
    assert drilldown["sections"]["signal_intent_match_count"] == 1
    assert drilldown["sections"]["execution_events"][0]["event_type"] == "rejected"
    assert "回测样本下钻" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def test_run_data_drilldown_batch_builds_multiple_samples(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)

    batch = build_run_data_drilldown_batch(
        run_dir,
        sample_refs=[
            {"kind": "trade", "trade_index": 1},
            {"kind": "opportunity", "sample_index": 1},
            {"kind": "add_on", "sample_index": 1},
        ],
        context_limit=5,
    )
    markdown = render_run_data_drilldown_batch_markdown_zh(batch)
    json_path, markdown_path = write_run_data_drilldown_batch(batch, output_dir=tmp_path / "batch")

    assert batch["schema"] == "attbacktrader.run_data_drilldown_batch.v1"
    assert batch["sample_count"] == 3
    assert [sample["sample_id"] for sample in batch["samples"]] == ["trade.1", "opportunity.1", "add_on.1"]
    assert batch["samples"][1]["summary"]["blocked_by_zh"] == "不足一手，无法下单"
    assert "回测批量样本下钻" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def test_run_data_attribution_index_filters_entry_checks(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)

    index = build_run_data_attribution_index(
        run_dir,
        filters=[
            "entry.symbol.ma.bullish_trend=true",
            "entry.market.hs300.bullish_trend=false",
        ],
    )
    markdown = render_run_data_attribution_index_markdown_zh(index)
    json_path, markdown_path = write_run_data_attribution_index(index, output_dir=tmp_path / "index")

    assert index["schema"] == "attbacktrader.run_data_attribution_index.v1"
    assert index["match_count"] == 1
    assert index["matching_samples"][0]["sample_id"] == "trade.1"
    assert any(field["field"] == "symbol.ma.bullish_trend" for field in index["fields"])
    assert "回测归因字段索引" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def test_run_data_clis_write_outputs(tmp_path: Path, capsys) -> None:
    run_dir = _run_dir(tmp_path)
    output_dir = tmp_path / "cli-out"

    dictionary_exit = run_data_dictionary_cli.main(["--run-dir", str(run_dir), "--output-dir", str(output_dir)])
    dictionary_stdout = json.loads(capsys.readouterr().out)
    overview_exit = run_data_overview_cli.main(["--run-dir", str(run_dir), "--output-dir", str(output_dir)])
    overview_stdout = json.loads(capsys.readouterr().out)
    drilldown_exit = run_data_drilldown_cli.main(
        [
            "--run-dir",
            str(run_dir),
            "--kind",
            "trade",
            "--trade-index",
            "1",
            "--output-dir",
            str(output_dir),
        ]
    )
    drilldown_stdout = json.loads(capsys.readouterr().out)
    batch_exit = run_data_drilldown_batch_cli.main(
        [
            "--run-dir",
            str(run_dir),
            "--trade-index",
            "1",
            "--opportunity-sample-index",
            "1",
            "--output-dir",
            str(output_dir),
        ]
    )
    batch_stdout = json.loads(capsys.readouterr().out)
    index_exit = run_data_attribution_index_cli.main(
        [
            "--run-dir",
            str(run_dir),
            "--filter",
            "entry.symbol.ma.bullish_trend=true",
            "--output-dir",
            str(output_dir),
        ]
    )
    index_stdout = json.loads(capsys.readouterr().out)

    assert dictionary_exit == 0
    assert overview_exit == 0
    assert drilldown_exit == 0
    assert batch_exit == 0
    assert index_exit == 0
    assert dictionary_stdout["artifacts"]["run_data_dictionary_json_path"] == str(output_dir / "run_data_dictionary.json")
    assert overview_stdout["closed_trade_count"] == 2
    assert drilldown_stdout["sample_id"] == "trade.1"
    assert batch_stdout["sample_ids"] == ["trade.1", "opportunity.1"]
    assert index_stdout["matching_sample_ids"] == ["trade.1"]
    assert (output_dir / "run_data_overview.zh.md").exists()
    assert (output_dir / "run_data_drilldown.trade.1.zh.md").exists()
    assert (output_dir / "run_data_drilldown_batch.zh.md").exists()
    assert (output_dir / "run_data_attribution_index.zh.md").exists()


def _run_dir(root: Path) -> Path:
    path = root / "run-data-test"
    path.mkdir()
    _write_json(
        path / "run_plan.json",
        {
            "run": {"id": "run-data-test", "from_date": "2024-01-01", "to_date": "2024-01-31"},
            "data": {
                "provider": "fake",
                "price_adjustment": "qfq",
                "tradable_series": [
                    {"symbol": "000001.SZ", "asset_type": "stock"},
                    {"symbol": "600519.SH", "asset_type": "stock"},
                ],
                "benchmark_series": {"indexes": ["000300.SH"]},
                "industry_series": {"source": "SW2021", "indexes": ["801780.SI"]},
            },
            "strategy": {
                "template": "trend_template_v1",
                "entry_method": "kdj_oversold_entry",
                "profit_taking_method": "kdj_overheated_exit",
                "stop_loss_method": "fixed_percent_stop",
                "add_on_method": "kdj_oversold_add_on",
                "sizing_rule": "equal_weight",
            },
            "broker": {"initial_cash": 1000000.0, "commission_rate": 0.0003},
        },
    )
    _write_json(
        path / "report.json",
        {
            "report_id": "run-data-test",
            "returns": {"starting_equity": 1000000.0, "final_equity": 1010000.0, "cumulative_return": 0.01},
            "risk": {"max_drawdown": 0.02},
            "trade_quality": {"trade_count": 2, "win_count": 1, "loss_count": 1, "win_rate": 0.5},
            "market_regime": {"primary_label": "input_only", "timeframes": ["D", "W", "M"]},
        },
    )
    _write_json(
        path / "evidence_validation.json",
        {
            "status": "ok",
            "counts": {
                "symbol_count": 2,
                "closed_trade_count": 2,
                "signal_intent_count": 3,
                "execution_event_count": 3,
                "trade_review_opportunity_count": 1,
                "trade_review_add_on_entry_count": 1,
            },
            "error_count": 0,
            "warning_count": 0,
            "issues": [],
        },
    )
    _write_json(
        path / "trades.json",
        {
            "closed_trades": [
                {
                    "symbol": "000001.SZ",
                    "entry_date": "2024-01-05",
                    "exit_date": "2024-01-10",
                    "entry_price": 10.0,
                    "exit_price": 9.4,
                    "exit_reason": "FIXED_5_PERCENT_STOP",
                },
                {
                    "symbol": "600519.SH",
                    "entry_date": "2024-01-11",
                    "exit_date": "2024-01-18",
                    "entry_price": 1000.0,
                    "exit_price": 1100.0,
                    "exit_reason": "KDJ_J_ABOVE_100",
                },
            ],
            "open_positions": [
                {"symbol": "000333.SZ", "entry_date": "2024-01-29", "entry_price": 50.0, "size": 1000, "add_on_count": 0}
            ],
        },
    )
    _write_json(
        path / "equity_curve.json",
        [
            {
                "trade_date": "2024-01-02",
                "cash": 1000000.0,
                "position_value": 0.0,
                "total_value": 1000000.0,
                "drawdown": 0.0,
                "holding_count": 0,
                "exposure": 0.0,
            },
            {
                "trade_date": "2024-01-31",
                "cash": 500000.0,
                "position_value": 510000.0,
                "total_value": 1010000.0,
                "drawdown": 0.01,
                "holding_count": 1,
                "exposure": 0.5,
            },
        ],
    )
    _write_json(
        path / "signal_audit.json",
        [
            {
                "intent_type": "enter",
                "symbol": "000001.SZ",
                "trade_date": "2024-01-05",
                "method_name": "kdj_oversold_entry",
                "reason_code": "KDJ_J_BELOW_13",
                "blocked_by": None,
                "signal_values": {"checks": {"kdj_j_below_threshold": True}},
            },
            {
                "intent_type": "exit_loss",
                "symbol": "000001.SZ",
                "trade_date": "2024-01-10",
                "method_name": "fixed_percent_stop",
                "reason_code": "FIXED_5_PERCENT_STOP",
                "blocked_by": None,
                "signal_values": {"checks": {"current_price_at_or_below_stop": True}},
            },
            {
                "intent_type": "enter",
                "symbol": "600519.SH",
                "trade_date": "2024-01-04",
                "method_name": "kdj_oversold_entry",
                "reason_code": "KDJ_J_BELOW_13",
                "blocked_by": "BOARD_LOT_TOO_SMALL",
                "signal_values": {"checks": {"kdj_j_below_threshold": True}},
            },
        ],
    )
    _write_json(
        path / "sizing_audit.json",
        [
            {
                "symbol": "600519.SH",
                "trade_date": "2024-01-04",
                "intent_type": "enter",
                "blocked_by": "BOARD_LOT_TOO_SMALL",
                "sizing": {"requested_quantity": 50, "executable_quantity": 0},
            }
        ],
    )
    _write_json(
        path / "execution_audit.json",
        [
            {
                "event_date": "2024-01-05",
                "signal_date": "2024-01-05",
                "symbol": "000001.SZ",
                "side": "buy",
                "event_type": "completed",
                "status": "Completed",
                "reason_code": "KDJ_J_BELOW_13",
                "blocked_by": None,
                "executed_quantity": 1000,
                "executed_price": 10.0,
            },
            {
                "event_date": "2024-01-10",
                "signal_date": "2024-01-10",
                "symbol": "000001.SZ",
                "side": "sell",
                "event_type": "completed",
                "status": "Completed",
                "reason_code": "FIXED_5_PERCENT_STOP",
                "blocked_by": None,
                "executed_quantity": 1000,
                "executed_price": 9.4,
            },
            {
                "event_date": "2024-01-04",
                "signal_date": "2024-01-04",
                "symbol": "600519.SH",
                "side": "buy",
                "event_type": "rejected",
                "status": "rejected",
                "reason_code": "KDJ_J_BELOW_13",
                "blocked_by": "BOARD_LOT_TOO_SMALL",
                "requested_quantity": 50,
                "executable_quantity": 0,
            },
        ],
    )
    _write_json(
        path / "positions.json",
        [
            {"trade_date": "2024-01-31", "symbol": "000333.SZ", "size": 1000, "price": 51.0, "value": 51000.0}
        ],
    )
    _write_json(
        path / "snapshots.json",
        {
            "symbols": [{"symbol": "000001.SZ", "snapshot_path": "data/snapshots/000001.parquet"}],
            "benchmarks": [{"symbol": "000300.SH"}],
            "industry_indexes": [{"symbol": "801780.SI"}],
        },
    )
    _write_json(
        path / "trade_lifecycle.json",
        {
            "trade_count": 2,
            "lifecycles": [
                {
                    "trade_index": 1,
                    "symbol": "000001.SZ",
                    "outcome": "loss",
                    "entry_date": "2024-01-05",
                    "exit_date": "2024-01-10",
                    "exit_reason": "FIXED_5_PERCENT_STOP",
                    "return_pct": -0.06,
                    "events": [],
                }
            ],
        },
    )
    _write_json(
        path / "post_exit_analysis.json",
        {
            "window_days": 5,
            "configured_window_days": [3, 5],
            "rebound_thresholds": [0.0, 0.05],
            "observations": [
                {
                    "trade_index": 1,
                    "symbol": "000001.SZ",
                    "entry_date": "2024-01-05",
                    "exit_date": "2024-01-10",
                    "exit_reason": "FIXED_5_PERCENT_STOP",
                    "sold_too_early": True,
                    "max_high_return_pct": 0.08,
                    "primary_window_close_return_pct": 0.03,
                }
            ],
            "summaries": [],
            "window_summaries": [],
            "threshold_summaries": [],
        },
    )
    _write_json(
        path / "trade_review.json",
        {
            "trade_count": 2,
            "sold_too_early_count": 1,
            "opportunity_count": 1,
            "add_on_entry_count": 1,
            "sold_too_early_profiles": [],
            "stop_loss_rebound_profiles": [],
            "opportunity_cost_summaries": [],
            "add_on_entry_summaries": [],
            "trades": [
                {
                    "trade_index": 1,
                    "symbol": "000001.SZ",
                    "outcome": "loss",
                    "entry_date": "2024-01-05",
                    "exit_date": "2024-01-10",
                    "exit_reason": "FIXED_5_PERCENT_STOP",
                    "return_pct": -0.06,
                    "entry_method_name": "kdj_oversold_entry",
                    "exit_method_name": "fixed_percent_stop",
                    "sold_too_early": True,
                    "max_high_return_pct": 0.08,
                    "entry_checks": {
                        "kdj_j_below_threshold": True,
                        "symbol.ma.bullish_trend": True,
                        "market.hs300.bullish_trend": False,
                    },
                    "exit_checks": {"current_price_at_or_below_stop": True},
                }
            ],
            "opportunities": [
                {
                    "sample_index": 1,
                    "source": "execution",
                    "opportunity_group": "execution_rejection",
                    "symbol": "600519.SH",
                    "trade_date": "2024-01-04",
                    "intent_type": "enter",
                    "method_name": "kdj_oversold_entry",
                    "reason_code": "KDJ_J_BELOW_13",
                    "blocked_by": "BOARD_LOT_TOO_SMALL",
                    "failed_checks": [],
                    "checks": {"kdj_j_below_threshold": True},
                    "opportunity_price": 1000.0,
                    "follow_up": {
                        "window_days": 5,
                        "observed_day_count": 5,
                        "complete": True,
                        "window_close_return_pct": 0.1,
                        "max_high_return_pct": 0.12,
                    },
                }
            ],
            "add_on_entry_points": [
                {
                    "sample_index": 1,
                    "trade_index": 1,
                    "symbol": "000001.SZ",
                    "outcome": "loss",
                    "trade_return_pct": -0.06,
                    "add_on_date": "2024-01-07",
                    "method_name": "kdj_oversold_add_on",
                    "reason_code": "KDJ_OVERSOLD_ADD_ON",
                    "checks": {
                        "symbol.ma.bullish_trend": True,
                        "market.hs300.bullish_trend": False,
                    },
                    "categories": {"symbol.ma.trend_state": "bullish"},
                    "add_on_price": 10.2,
                    "follow_up": {
                        "window_days": 5,
                        "observed_day_count": 5,
                        "complete": True,
                        "window_close_return_pct": -0.02,
                        "max_high_return_pct": 0.03,
                    },
                }
            ],
        },
    )
    return path


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
