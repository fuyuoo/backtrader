import json
from pathlib import Path

import pandas as pd

from attbacktrader.data import IndexBar
from attbacktrader.data.snapshots import index_bars_snapshot_path, industry_index_bars_snapshot_path, write_index_bars_parquet
from attbacktrader.cli import run_data_dictionary as run_data_dictionary_cli
from attbacktrader.cli import run_data_drilldown as run_data_drilldown_cli
from attbacktrader.cli import run_data_drilldown_batch as run_data_drilldown_batch_cli
from attbacktrader.cli import run_data_overview as run_data_overview_cli
from attbacktrader.cli import run_data_attribution_index as run_data_attribution_index_cli
from attbacktrader.cli import run_data_attribution_summary as run_data_attribution_summary_cli
from attbacktrader.cli import attribution_wide_samples as attribution_wide_samples_cli
from attbacktrader.cli import environment_fit as environment_fit_cli
from attbacktrader.reports import (
    build_attribution_field_index,
    build_attribution_wide_samples,
    build_environment_fit_report_from_wide_samples,
    build_run_data_attribution_index,
    build_run_data_attribution_summary,
    build_run_data_dictionary,
    build_run_data_drilldown,
    build_run_data_drilldown_batch,
    build_run_data_overview,
    render_run_data_attribution_index_markdown_zh,
    render_run_data_attribution_summary_markdown_zh,
    render_run_data_dictionary_markdown_zh,
    render_run_data_drilldown_markdown_zh,
    render_run_data_drilldown_batch_markdown_zh,
    render_run_data_overview_markdown_zh,
    write_attribution_wide_samples,
    write_run_data_attribution_index,
    write_run_data_attribution_summary,
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
    assert any(artifact["artifact"] == "trade_attribution" for artifact in dictionary["artifacts"])
    assert any(artifact["artifact"] == "trade_review" for artifact in dictionary["artifacts"])
    assert any(artifact["artifact"] == "strategy_environment_profile" for artifact in dictionary["artifacts"])
    assert "回测数据字典" in markdown
    assert "trade_attribution.json" in markdown
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
    assert overview["trade_attribution"]["factor_summary_count"] == 1
    assert overview["review"]["opportunity_count"] == 1
    assert overview["signals"]["blocked_by_counts"][0]["label_zh"] == "不足一手，无法下单"
    assert "回测数据总览" in markdown
    assert "BOARD_LOT_TOO_SMALL" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def test_run_data_overview_accepts_compact_signal_audit(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    _write_json(
        run_dir / "signal_audit.json",
        {
            "schema": "attbacktrader.compact_signal_audit.v1",
            "artifact_detail": "compact",
            "raw_signal_audit_persisted": False,
            "total_count": 491587,
            "intent_type_counts": [{"key": "hold", "count": 480000}, {"key": "enter", "count": 1000}],
            "reason_code_counts": [{"key": "KDJ_J_BELOW_13", "count": 1000}],
            "blocked_by_counts": [{"key": "BOARD_LOT_TOO_SMALL", "count": 31, "label_zh": "不足一手，无法下单"}],
            "method_counts": [{"key": "kdj_oversold_entry", "count": 1000}],
            "date_range": {"start": "2024-01-01", "end": "2024-01-31"},
            "samples": [],
        },
    )

    overview = build_run_data_overview(run_dir, top_symbols=2)

    assert overview["signals"]["artifact_detail"] == "compact"
    assert overview["signals"]["signal_intent_count"] == 491587
    assert overview["signals"]["blocked_by_counts"][0]["key"] == "BOARD_LOT_TOO_SMALL"
    signal_artifact = next(row for row in overview["artifacts"] if row["artifact"] == "signal_audit")
    assert signal_artifact["count"] == 491587
    attribution_artifact = next(row for row in overview["artifacts"] if row["artifact"] == "trade_attribution")
    assert attribution_artifact["count"]["trades"] == 2


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
    assert index["source_artifacts"]["trade_attribution"] is True
    assert index["match_count"] == 1
    assert index["matching_samples"][0]["sample_id"] == "trade.1"
    assert any(field["field"] == "symbol.ma.bullish_trend" for field in index["fields"])
    assert "回测归因字段索引" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def test_run_data_attribution_index_filters_trade_attribution_industry_and_add_on_factors(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)

    industry_index = build_run_data_attribution_index(
        run_dir,
        filters=[
            "entry.industry.kdj.j_below_threshold=true",
            "entry.industry.sw_l1.code=801780.SI",
        ],
    )
    add_on_index = build_run_data_attribution_index(
        run_dir,
        filters=["add_on.symbol.ma.price_above_ma60=true"],
    )
    opportunity_index = build_run_data_attribution_index(
        run_dir,
        filters=["opportunity.blocked_by=BOARD_LOT_TOO_SMALL"],
    )
    numeric_index = build_run_data_attribution_index(
        run_dir,
        filters=["entry.industry.kdj.j<13"],
    )
    numeric_miss_index = build_run_data_attribution_index(
        run_dir,
        filters=["entry.industry.kdj.j>=13"],
    )

    assert industry_index["match_count"] == 1
    assert industry_index["matching_samples"][0]["sample_id"] == "trade.1"
    assert industry_index["matching_samples"][0]["fields"]["industry.sw_l1.code"] == "801780.SI"
    assert numeric_index["filters"][0]["operator"] == "<"
    assert numeric_index["match_count"] == 1
    assert numeric_miss_index["match_count"] == 0
    assert add_on_index["match_count"] == 1
    assert add_on_index["matching_samples"][0]["scope"] == "add_on"
    assert add_on_index["matching_samples"][0]["sample_id"] == "trade.1"
    assert opportunity_index["match_count"] == 1
    assert opportunity_index["matching_samples"][0]["sample_id"] == "opportunity.1"


def test_run_data_attribution_summary_compacts_top_and_bottom_factor_candidates(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)

    summary = build_run_data_attribution_summary(run_dir, min_sample_count=1, top_n=20)
    markdown = render_run_data_attribution_summary_markdown_zh(summary)
    json_path, markdown_path = write_run_data_attribution_summary(summary, output_dir=tmp_path / "summary")

    assert summary["schema"] == "attbacktrader.run_data_attribution_summary.v1"
    assert summary["overall"]["trade_count"] == 1
    assert summary["preferred_candidates"]
    assert summary["avoid_candidates"]
    assert summary["preferred_combination_candidates"]
    assert summary["preferred_candidates"][0]["query_filter"]
    assert any(
        "entry.industry.kdj.j<13" in candidate["query_filters"]
        and "entry.symbol.ma.bullish_trend=true" in candidate["query_filters"]
        for candidate in summary["preferred_combination_candidates"] + summary["avoid_combination_candidates"]
    )
    assert "回测归因摘要" in markdown
    assert "适合组合候选" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def test_attribution_wide_samples_builds_field_index_and_enriched_environment_fit(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    reference_path = _reference_snapshot(tmp_path)

    wide_samples = build_attribution_wide_samples(run_dir, reference_snapshot=reference_path)
    wide_path, csv_path, index_path, markdown_path = write_attribution_wide_samples(
        wide_samples,
        output_dir=tmp_path / "wide",
    )
    enriched = build_environment_fit_report_from_wide_samples(
        wide_path,
        field_index=index_path,
        min_sample_count=1,
    )

    assert wide_samples["schema"] == "attbacktrader.attribution_wide_samples.v1"
    assert wide_samples["sample_count"] == 1
    assert wide_samples["samples"][0]["signal_date"] == "2024-01-04"
    assert wide_samples["field_index"]["schema"] == "attbacktrader.attribution_field_index.v1"
    assert "entry.price_position.near_high_20d_bucket" in wide_samples["environment_fit_default_fields"]
    assert (
        wide_samples["samples"][0]["field_values"]["entry.price_position.near_high_20d_bucket"]["asof_date"]
        == "2024-01-04"
    )
    assert (
        wide_samples["samples"][0]["field_values"]["entry.price_position.ma60_atr_multiple_bucket"]["bucket"]
        == "above_ma60_1_2atr"
    )
    assert (
        wide_samples["samples"][0]["field_values"]["entry.price_position.signal_close_ma60_atr_multiple_bucket"]["bucket"]
        == "above_ma60_0_1atr"
    )
    assert "entry.valuation.pe_bucket" in [field["field_key"] for field in wide_samples["field_index"]["fields"]]
    assert wide_path.exists()
    assert csv_path.exists()
    assert index_path.exists()
    assert markdown_path.exists()
    assert enriched["variant"] == "enriched"
    assert enriched["trade_count"] == 1
    assert any(
        field["field"] == "entry.price_position.ma60_atr_multiple_bucket"
        and field["label_zh"] == "入场价距MA60的ATR倍数桶"
        for field in enriched["environment_fields"]
    )
    assert any(
        summary["field"] == "entry.price_position.near_high_20d_bucket"
        for summary in enriched["single_factor_summaries"]
    )


def test_attribution_field_index_does_not_fallback_raw_for_bucket_fields() -> None:
    wide_samples = {
        "schema": "attbacktrader.attribution_wide_samples.v1",
        "run_id": "field-index-bucket-test",
        "source_dir": "reports/field-index-bucket-test",
        "reference_path": "reference",
        "samples": [
            {
                "trade_index": 1,
                "return_pct": -0.01,
                "field_values": {
                    "entry.volatility.atr_20d_bucket": {
                        "raw": 0.032,
                        "bucket": None,
                        "exception_codes": ["reference_excluded_st"],
                    }
                },
            },
            {
                "trade_index": 2,
                "return_pct": 0.02,
                "field_values": {
                    "entry.volatility.atr_20d_bucket": {
                        "raw": 0.025,
                        "bucket": "p20_p40",
                        "exception_codes": [],
                    }
                },
            },
        ],
    }

    index = build_attribution_field_index(
        wide_samples,
        field_catalog={
            "entry.volatility.atr_20d_bucket": {
                "field_key": "entry.volatility.atr_20d_bucket",
                "value_type": "bucket",
            }
        },
    )

    field = index["fields"][0]
    values = {bucket["value"]: bucket["count"] for bucket in field["bucket_distribution"]}
    assert field["coverage_stats"]["missing_count"] == 1
    assert values == {"p20_p40": 1, None: 1}


def test_attribution_wide_samples_treats_stale_reference_rows_as_missing(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    reference_path = _reference_snapshot(tmp_path)
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    for row in reference["rows"]:
        row["trade_date"] = "2023-12-20"
        row["asof_date"] = "2023-12-20"
    reference_path.write_text(json.dumps(reference, ensure_ascii=False), encoding="utf-8")

    wide_samples = build_attribution_wide_samples(
        run_dir,
        reference_snapshot=reference_path,
        max_staleness_trading_days=5,
    )

    sample = wide_samples["samples"][0]
    near_high = sample["field_values"]["entry.price_position.near_high_20d_bucket"]
    assert near_high["raw"] is None
    assert near_high["bucket"] is None
    assert near_high["exception_codes"] == ["reference_record_missing"]
    assert "reference_record_missing" in sample["attribution_exception_codes"]


def test_attribution_wide_samples_derives_path_and_signal_strength_from_daily_cache(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    reference_path = _reference_snapshot(tmp_path)
    daily_cache = _daily_price_cache(tmp_path)
    snapshot_root = _industry_index_cache(tmp_path)

    wide_samples = build_attribution_wide_samples(
        run_dir,
        reference_snapshot=reference_path,
        daily_price_cache_dir=daily_cache,
        snapshot_root=snapshot_root,
    )

    fields = wide_samples["samples"][0]["field_values"]
    assert fields["trade.path.holding_days_bucket"]["bucket"] == "d4_10"
    assert fields["trade.path.max_favorable_return_before_exit_bucket"]["bucket"] == "5_10pct"
    assert fields["trade.path.max_adverse_return_before_exit_bucket"]["bucket"] == "minus5_to_minus10pct"
    assert fields["trade.path.first_profit_5pct_days_bucket"]["bucket"] == "day_1"
    assert fields["entry.signal_strength.dea_waterline_age_trading_days_bucket"]["bucket"] == "day_1_3"
    assert fields["entry.signal_strength.ma25_above_ma60_spread_bucket"]["bucket"] == "2_5pct"
    assert fields["entry.signal_strength.dif_dea_distance_bucket"]["bucket"] is not None
    assert fields["entry.signal_strength.macd_bar_bucket"]["bucket"] is not None
    assert fields["entry.signal_strength.signal_candle_body_bucket"]["bucket"] == "1_3pct"
    assert fields["entry.signal_strength.signal_upper_lower_shadow_bucket"]["bucket"] == "long_upper_shadow"
    assert fields["entry.weekly.symbol_kdj_j_bucket"]["bucket"] is not None
    assert fields["entry.weekly.symbol_kdj_state"]["bucket"] is not None
    assert fields["entry.weekly.symbol_ma_trend_bucket"]["bucket"] is not None
    assert fields["entry.weekly.symbol_close_vs_week_ma20_bucket"]["bucket"] is not None
    assert fields["industry.volatility.atr_20d_bucket"]["bucket"] is not None
    assert "industry_membership_backfilled" in fields["industry.volatility.atr_20d_bucket"]["exception_codes"]
    assert fields["industry.volatility.return_vol_20d_bucket"]["bucket"] is not None
    assert fields["industry.price_position.near_high_60d_bucket"]["bucket"] is not None
    assert fields["industry.weekly.kdj_j_bucket"]["bucket"] is not None
    assert fields["industry.weekly.kdj_state"]["bucket"] is not None
    assert "industry_membership_backfilled" in fields["industry.weekly.kdj_state"]["exception_codes"]
    assert fields["industry.weekly.ma_trend_bucket"]["bucket"] is not None
    assert fields["industry.weekly.relative_strength_bucket"]["bucket"] is not None
    assert fields["entry.market.source_index"]["bucket"] == "HS300"
    assert fields["market.hs300.trend_state"]["bucket"] in {"bullish", "bearish", "mixed"}
    assert fields["market.csi500.trend_state"]["bucket"] in {"bullish", "bearish", "mixed"}
    assert fields["market.hs300.entry_stage"]["bucket"] in {"bullish", "bearish", "mixed"}
    assert fields["market.hs300.exit_stage"]["bucket"] in {"bullish", "bearish", "mixed"}
    assert "_to_" in fields["market.hs300.entry_to_exit_stage"]["bucket"]
    assert fields["market.csi500.entry_stage"]["bucket"] in {"bullish", "bearish", "mixed"}
    assert fields["market.csi500.exit_stage"]["bucket"] in {"bullish", "bearish", "mixed"}
    assert "_to_" in fields["market.csi500.entry_to_exit_stage"]["bucket"]
    assert fields["market.hs300.weekly.kdj_state"]["bucket"] in {"oversold", "recovering", "strong", "overheated"}
    assert fields["entry.momentum.symbol_vs_hs300_return_20d_bucket"]["bucket"] is not None
    assert fields["entry.momentum.symbol_vs_industry_return_20d_bucket"]["bucket"] is not None
    assert fields["trade.path.max_favorable_atr_multiple_bucket"]["bucket"] == "positive_0_1atr"
    assert fields["trade.path.max_adverse_atr_multiple_bucket"]["bucket"] is not None
    assert fields["trade.path.reached_10pct_bucket"]["bucket"] == "not_reached"
    assert fields["trade.path.reached_15pct_bucket"]["bucket"] == "not_reached"
    assert fields["trade.path.post_exit_5d_max_high_return_bucket"]["bucket"] == "up_gt_10pct"
    assert fields["trade.exit.reason"]["bucket"] == "FIXED_5_PERCENT_STOP"
    assert "entry.weekly.symbol_kdj_state" in wide_samples["environment_fit_default_fields"]
    assert "industry.weekly.kdj_state" in wide_samples["environment_fit_default_fields"]
    assert "entry.market.source_index" in wide_samples["environment_fit_default_fields"]
    assert "market.hs300.trend_state" in wide_samples["environment_fit_default_fields"]
    assert "entry.momentum.symbol_vs_hs300_return_20d_bucket" in wide_samples["environment_fit_default_fields"]
    assert "market.hs300.entry_stage" not in wide_samples["environment_fit_default_fields"]
    assert "market.hs300.exit_stage" not in wide_samples["environment_fit_default_fields"]
    assert "market.hs300.entry_to_exit_stage" not in wide_samples["environment_fit_default_fields"]
    assert "trade.path.holding_days_bucket" not in wide_samples["environment_fit_default_fields"]
    assert "trade.path.max_favorable_atr_multiple_bucket" not in wide_samples["environment_fit_default_fields"]
    assert "trade.exit.reason" not in wide_samples["environment_fit_default_fields"]
    assert ["entry.market.source_index", "market.hs300.trend_state"] in wide_samples["environment_fit_pair_whitelist"]
    assert ["trade.exit.reason", "entry.signal_strength.dea_waterline_age_trading_days_bucket"] not in wide_samples[
        "environment_fit_pair_whitelist"
    ]
    assert ["trade.exit.reason", "entry.signal_strength.dea_waterline_age_trading_days_bucket"] in wide_samples[
        "outcome_diagnostic_pair_whitelist"
    ]
    assert ["trade.exit.reason", "market.hs300.entry_to_exit_stage"] in wide_samples[
        "outcome_diagnostic_pair_whitelist"
    ]


def test_attribution_wide_samples_adds_objective_market_stage_fields(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    reference_path = _reference_snapshot(tmp_path)
    daily_cache, snapshot_root = _objective_bull_market_context(tmp_path)

    wide_samples = build_attribution_wide_samples(
        run_dir,
        reference_snapshot=reference_path,
        daily_price_cache_dir=daily_cache,
        snapshot_root=snapshot_root,
    )

    fields = wide_samples["samples"][0]["field_values"]
    assert fields["market.objective.entry_stage"]["bucket"] == "bullish"
    assert fields["market.objective.exit_stage"]["bucket"] == "bullish"
    assert fields["market.objective.entry_to_exit_stage"]["bucket"] == "bullish_to_bullish"
    assert fields["market.objective.entry_breadth_ma60_ratio_bucket"]["bucket"] == "gte_65pct"
    assert fields["market.objective.entry_index_drawdown_250d_bucket"]["bucket"] == "drawdown_0_5pct"
    assert fields["market.objective.entry_index_ma60_slope_20d_bucket"]["bucket"] is not None
    assert fields["market.objective.entry_index_ma250_position"]["bucket"] == "above_ma250"
    assert fields["market.objective.entry_stage"]["raw"]["index_source"] == "hs300_csi500"
    assert fields["market.objective.entry_stage"]["raw"]["breadth_symbol_count"] == 3
    assert "market.objective.entry_stage" in wide_samples["environment_fit_default_fields"]
    assert "market.objective.entry_to_exit_stage" in wide_samples["environment_fit_default_fields"]
    assert ["entry.momentum.return_20d_bucket", "market.objective.entry_stage"] in wide_samples[
        "environment_fit_pair_whitelist"
    ]
    assert ["trade.exit.reason", "market.objective.entry_to_exit_stage"] in wide_samples[
        "outcome_diagnostic_pair_whitelist"
    ]


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
    summary_exit = run_data_attribution_summary_cli.main(
        [
            "--run-dir",
            str(run_dir),
            "--min-sample-count",
            "1",
            "--output-dir",
            str(output_dir),
        ]
    )
    summary_stdout = json.loads(capsys.readouterr().out)
    reference_path = _reference_snapshot(tmp_path)
    wide_exit = attribution_wide_samples_cli.main(
        [
            "--run-dir",
            str(run_dir),
            "--reference-snapshot",
            str(reference_path),
            "--output-dir",
            str(output_dir),
        ]
    )
    wide_stdout = json.loads(capsys.readouterr().out)
    enriched_exit = environment_fit_cli.main(
        [
            "--wide-samples",
            str(output_dir / "attribution_wide_samples.json"),
            "--field-index",
            str(output_dir / "attribution_field_index.json"),
            "--min-sample-count",
            "1",
            "--output-dir",
            str(output_dir),
        ]
    )
    enriched_stdout = json.loads(capsys.readouterr().out)

    assert dictionary_exit == 0
    assert overview_exit == 0
    assert drilldown_exit == 0
    assert batch_exit == 0
    assert index_exit == 0
    assert summary_exit == 0
    assert wide_exit == 0
    assert enriched_exit == 0
    assert dictionary_stdout["artifacts"]["run_data_dictionary_json_path"] == str(output_dir / "run_data_dictionary.json")
    assert overview_stdout["closed_trade_count"] == 2
    assert drilldown_stdout["sample_id"] == "trade.1"
    assert batch_stdout["sample_ids"] == ["trade.1", "opportunity.1"]
    assert index_stdout["matching_sample_ids"] == ["trade.1"]
    assert summary_stdout["preferred_count"] > 0
    assert summary_stdout["preferred_combination_count"] > 0
    assert wide_stdout["sample_count"] == 1
    assert enriched_stdout["schema"] == "attbacktrader.environment_fit.v1"
    assert (output_dir / "run_data_overview.zh.md").exists()
    assert (output_dir / "run_data_drilldown.trade.1.zh.md").exists()
    assert (output_dir / "run_data_drilldown_batch.zh.md").exists()
    assert (output_dir / "run_data_attribution_index.zh.md").exists()
    assert (output_dir / "run_data_attribution_summary.zh.md").exists()
    assert (output_dir / "attribution_wide_samples.json").exists()
    assert (output_dir / "attribution_wide_samples.csv").exists()
    assert (output_dir / "attribution_field_index.zh.md").exists()
    assert (output_dir / "environment_fit.enriched.json").exists()
    assert (output_dir / "environment_fit.enriched.zh.md").exists()


def _run_dir(root: Path) -> Path:
    path = root / "run-data-test"
    path.mkdir()
    (path / "stock_pool.csv").write_text(
        "ts_code,name,source_index\n000001.SZ,平安银行,HS300\n600519.SH,贵州茅台,CSI500\n",
        encoding="utf-8",
    )
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
                "stock_pool_file": "stock_pool.csv",
                "benchmark_series": {"indexes": ["000300.SH", "000905.SH"]},
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
                    "entry_price": 10.0,
                    "return_pct": -0.06,
                    "events": [
                        {
                            "event_type": "entry",
                            "trade_date": "2024-01-05",
                            "values": {
                                "signal_trade_date": "2024-01-04",
                                "close": 9.8,
                                "ma60": 9.0,
                            },
                            "executions": [
                                {
                                    "event_type": "completed",
                                    "side": "buy",
                                    "executed_price": 10.0,
                                    "executed_quantity": 1000,
                                }
                            ],
                        }
                    ],
                }
            ],
        },
    )
    _write_json(
        path / "trade_attribution.json",
        {
            "schema": "attbacktrader.trade_attribution.v1",
            "trade_count": 2,
            "entry_event_count": 2,
            "exit_event_count": 2,
            "add_on_event_count": 1,
            "attributions": [
                {
                    "trade_index": 1,
                    "symbol": "000001.SZ",
                    "outcome": "loss",
                    "entry_date": "2024-01-05",
                    "exit_date": "2024-01-10",
                    "exit_reason": "FIXED_5_PERCENT_STOP",
                    "return_pct": -0.06,
                    "entry": {
                        "trade_date": "2024-01-05",
                        "factors": [
                            {"key": "symbol.ma.bullish_trend", "value": True, "missing": False},
                            {"key": "market.hs300.bullish_trend", "value": False, "missing": False},
                            {"key": "industry.kdj.j_below_threshold", "value": True, "missing": False},
                            {"key": "industry.kdj.j", "value": 10.0, "missing": False},
                            {"key": "industry.sw_l1.code", "value": "801780.SI", "missing": False},
                            {"key": "symbol.open", "value": 10.0, "missing": False},
                            {"key": "symbol.close", "value": 9.8, "missing": False},
                            {"key": "symbol.ma.ma25", "value": 9.4, "missing": False},
                            {"key": "symbol.ma.ma60", "value": 9.0, "missing": False},
                            {"key": "symbol.macd.dif", "value": 0.08, "missing": False},
                            {"key": "symbol.macd.dea", "value": 0.05, "missing": False},
                            {"key": "symbol.macd.macd_bar", "value": 0.06, "missing": False},
                            {"key": "symbol.macd.dea_waterline_age_trading_days", "value": 2, "missing": False},
                        ],
                    },
                    "exit": {
                        "trade_date": "2024-01-10",
                        "factors": [
                            {"key": "symbol.ma.price_above_ma25", "value": False, "missing": False},
                        ],
                    },
                    "add_ons": [
                        {
                            "trade_date": "2024-01-07",
                            "factors": [
                                {"key": "symbol.ma.price_above_ma60", "value": True, "missing": False},
                            ],
                        }
                    ],
                }
            ],
            "factor_summaries": [
                {
                    "timing": "entry",
                    "key": "symbol.ma.bullish_trend",
                    "value_kind": "check",
                    "sample_count": 1,
                    "missing_count": 0,
                    "win_count": 0,
                    "loss_count": 1,
                    "win_rate": 0.0,
                    "average_return_pct": -0.06,
                    "value_buckets": [{"value": "true", "count": 1, "trade_indexes": [1]}],
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


def _reference_snapshot(root: Path) -> Path:
    path = root / "reference.json"
    _write_json(
        path,
        {
            "metadata": {
                "fields": [
                    {
                        "field_key": "industry.sw_l1.code",
                        "label_zh": "申万一级行业",
                        "value_type": "category",
                        "scope": "industry",
                        "default_in_environment_fit": True,
                    },
                    {
                        "field_key": "entry.price_position.near_high_20d_bucket",
                        "label_zh": "距20日高点桶",
                        "value_type": "bucket",
                        "scope": "price_position",
                        "bucket_rule": "fixed_explain_bucket",
                        "default_in_environment_fit": True,
                    },
                    {
                        "field_key": "entry.valuation.pe_bucket",
                        "label_zh": "PE桶",
                        "value_type": "bucket",
                        "scope": "valuation",
                        "bucket_rule": "fixed_explain_bucket",
                        "default_in_environment_fit": False,
                    },
                    {
                        "field_key": "entry.volatility.atr_20d_bucket",
                        "label_zh": "ATR百分比桶",
                        "value_type": "bucket",
                        "scope": "volatility",
                        "default_in_environment_fit": True,
                    },
                    {
                        "field_key": "entry.price_position.ma60_atr_multiple_bucket",
                        "label_zh": "入场价距MA60的ATR倍数桶",
                        "value_type": "bucket",
                        "scope": "price_position",
                        "bucket_rule": "fixed_explain_bucket",
                        "default_in_environment_fit": True,
                    },
                    {
                        "field_key": "entry.price_position.signal_close_ma60_atr_multiple_bucket",
                        "label_zh": "信号日close距MA60的ATR倍数桶",
                        "value_type": "bucket",
                        "scope": "price_position",
                        "bucket_rule": "fixed_explain_bucket",
                        "default_in_environment_fit": False,
                    },
                    {
                        "field_key": "entry.stop_fit.fixed_atr_multiple_bucket",
                        "label_zh": "5%止盈对应ATR倍数桶",
                        "value_type": "bucket",
                        "scope": "stop_fit",
                        "default_in_environment_fit": True,
                    },
                ],
                "environment_fit_default_fields": [
                    "industry.sw_l1.code",
                    "entry.price_position.near_high_20d_bucket",
                    "entry.volatility.atr_20d_bucket",
                    "entry.price_position.ma60_atr_multiple_bucket",
                    "entry.stop_fit.fixed_atr_multiple_bucket",
                ],
                "environment_fit_pair_whitelist": [
                    ["industry.sw_l1.code", "entry.stop_fit.fixed_atr_multiple_bucket"],
                    ["entry.volatility.atr_20d_bucket", "entry.stop_fit.fixed_atr_multiple_bucket"],
                ],
            },
            "rows": [
                {
                    "symbol": "000001.SZ",
                    "trade_date": "2024-01-04",
                    "field_key": "industry.sw_l1.code",
                    "value": "801780.SI",
                    "bucket": "801780.SI",
                    "asof_date": "2024-01-04",
                    "staleness_trading_days": 0,
                    "reference_count": 4000,
                    "exception_codes": ["industry_membership_backfilled"],
                },
                {
                    "symbol": "000001.SZ",
                    "trade_date": "2024-01-04",
                    "field_key": "entry.price_position.near_high_20d_bucket",
                    "value": -0.02,
                    "bucket": "near_high",
                    "asof_date": "2024-01-04",
                    "staleness_trading_days": 0,
                    "reference_count": 4000,
                },
                {
                    "symbol": "000001.SZ",
                    "trade_date": "2024-01-04",
                    "field_key": "entry.valuation.pe_bucket",
                    "value": -12.3,
                    "bucket": "negative",
                    "asof_date": "2024-01-04",
                    "staleness_trading_days": 0,
                    "exception_codes": ["negative_pe"],
                    "reference_count": 4000,
                },
                {
                    "symbol": "000001.SZ",
                    "trade_date": "2024-01-04",
                    "field_key": "entry.volatility.atr_20d_bucket",
                    "value": 0.1,
                    "bucket": "p60_p80",
                    "percentile": 0.72,
                    "asof_date": "2024-01-04",
                    "staleness_trading_days": 0,
                    "reference_count": 4000,
                },
                {
                    "symbol": "000001.SZ",
                    "trade_date": "2024-01-04",
                    "field_key": "entry.price_position.signal_close_ma60_atr_multiple_bucket",
                    "value": 0.8163265306122458,
                    "bucket": "above_ma60_0_1atr",
                    "asof_date": "2024-01-04",
                    "staleness_trading_days": 0,
                    "reference_count": 4000,
                },
                {
                    "symbol": "000001.SZ",
                    "trade_date": "2024-01-04",
                    "field_key": "entry.stop_fit.fixed_atr_multiple_bucket",
                    "value": 1.42,
                    "bucket": "one_to_two_atr",
                    "asof_date": "2024-01-04",
                    "staleness_trading_days": 0,
                    "reference_count": 4000,
                },
            ],
        },
    )
    return path


def _daily_price_cache(root: Path) -> Path:
    daily_dir = root / "daily-cache" / "daily"
    daily_dir.mkdir(parents=True)
    rows = []
    for index, trade_date in enumerate(pd.bdate_range("2023-07-03", "2024-01-12")):
        close = 8.0 + index * 0.025
        rows.append(
            {
                "ts_code": "000001.SZ",
                "trade_date": trade_date.strftime("%Y%m%d"),
                "open": close + 0.05,
                "high": close + 0.10,
                "low": close - 0.10,
                "close": close,
            }
        )
    overrides = {
        "20240104": {"open": 10.0, "high": 10.3, "low": 9.7, "close": 9.8},
        "20240105": {"open": 10.0, "high": 10.6, "low": 9.9, "close": 10.4},
        "20240108": {"open": 10.4, "high": 10.8, "low": 10.1, "close": 10.7},
        "20240109": {"open": 10.6, "high": 10.7, "low": 9.5, "close": 9.6},
        "20240110": {"open": 9.6, "high": 9.8, "low": 9.2, "close": 9.4},
    }
    for row in rows:
        if row["trade_date"] in overrides:
            row.update(overrides[row["trade_date"]])
    pd.DataFrame(rows).to_parquet(daily_dir / "daily.parquet", index=False)
    return daily_dir.parent


def _industry_index_cache(root: Path) -> Path:
    snapshot_root = root / "snapshots"
    start_date = pd.Timestamp("2023-07-03").date()
    end_date = pd.Timestamp("2024-01-12").date()
    for symbol_index, symbol in enumerate(("000300.SH", "000905.SH")):
        bars = []
        for index, trade_date in enumerate(pd.bdate_range(start_date, end_date)):
            base = 3000.0 + symbol_index * 500.0 + index * (2.0 + symbol_index)
            close = base * (1.0 + (0.005 if index % 9 == 0 else 0.0))
            high = max(base, close) * 1.01
            low = min(base, close) * 0.99
            bars.append(
                IndexBar(
                    symbol=symbol,
                    trade_date=trade_date.date(),
                    open=base,
                    high=high,
                    low=low,
                    close=close,
                    volume=2000000.0 + index,
                    amount=3000000.0 + index,
                )
            )
        write_index_bars_parquet(
            bars,
            index_bars_snapshot_path(
                snapshot_root,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            ),
        )
    for symbol_index, symbol in enumerate(("801780.SI", "801180.SI")):
        bars = []
        for index, trade_date in enumerate(pd.bdate_range(start_date, end_date)):
            base = 1000.0 + symbol_index * 100.0 + index * (1.5 + symbol_index * 0.3)
            close = base * (1.0 + (0.01 if index % 7 == 0 else 0.0))
            high = max(base, close) * 1.01
            low = min(base, close) * 0.99
            bars.append(
                IndexBar(
                    symbol=symbol,
                    trade_date=trade_date.date(),
                    open=base,
                    high=high,
                    low=low,
                    close=close,
                    volume=1000000.0 + index,
                    amount=2000000.0 + index,
                )
            )
        write_index_bars_parquet(
            bars,
            industry_index_bars_snapshot_path(
                snapshot_root,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                source="SW2021",
            ),
        )
    return snapshot_root


def _objective_bull_market_context(root: Path) -> tuple[Path, Path]:
    daily_dir = root / "objective-daily-cache" / "daily"
    daily_dir.mkdir(parents=True)
    start_date = pd.Timestamp("2022-10-03").date()
    end_date = pd.Timestamp("2024-01-12").date()
    trade_dates = list(pd.bdate_range(start_date, end_date))

    rows = []
    for symbol_index, symbol in enumerate(("000001.SZ", "000002.SZ", "000003.SZ")):
        for index, trade_date in enumerate(trade_dates):
            close = 8.0 + symbol_index + index * (0.035 + symbol_index * 0.002)
            rows.append(
                {
                    "ts_code": symbol,
                    "trade_date": trade_date.strftime("%Y%m%d"),
                    "open": close * 0.998,
                    "high": close * 1.002,
                    "low": close * 0.996,
                    "close": close,
                }
            )
    pd.DataFrame(rows).to_parquet(daily_dir / "daily.parquet", index=False)

    snapshot_root = root / "objective-snapshots"
    for symbol_index, symbol in enumerate(("000300.SH", "000905.SH")):
        bars = []
        for index, trade_date in enumerate(trade_dates):
            close = 3000.0 + symbol_index * 400.0 + index * (5.0 + symbol_index)
            bars.append(
                IndexBar(
                    symbol=symbol,
                    trade_date=trade_date.date(),
                    open=close * 0.999,
                    high=close * 1.002,
                    low=close * 0.997,
                    close=close,
                    volume=2000000.0 + index,
                    amount=3000000.0 + index,
                )
            )
        write_index_bars_parquet(
            bars,
            index_bars_snapshot_path(
                snapshot_root,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            ),
        )
    return daily_dir.parent, snapshot_root


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
