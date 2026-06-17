import json
from pathlib import Path

import yaml

from attbacktrader.cli import entry_factor_validation_manifest as manifest_cli
from attbacktrader.config import RunPlan
from attbacktrader.reports import (
    ENTRY_FACTOR_VALIDATION_MANIFEST_SCHEMA,
    build_entry_factor_validation_manifest,
    render_entry_factor_validation_manifest_markdown_zh,
    write_entry_factor_validation_manifest,
)


def test_entry_factor_validation_manifest_generates_single_factor_run_plans() -> None:
    manifest = build_entry_factor_validation_manifest(
        _discovery_report_fixture(),
        _baseline_run_plan_fixture(),
        positive_limit=1,
        negative_limit=1,
        reuse_snapshots=True,
    )

    assert manifest["schema"] == ENTRY_FACTOR_VALIDATION_MANIFEST_SCHEMA
    assert manifest["base_run_id"] == "baoma-baseline"
    assert manifest["generated_count"] == 2
    assert [candidate["direction"] for candidate in manifest["candidates"]] == ["positive", "negative"]
    assert [candidate["action"] for candidate in manifest["candidates"]] == ["keep", "exclude"]
    assert all(candidate["view"] == "tradable_pre_entry" for candidate in manifest["candidates"])
    assert not any(candidate["field_key"].startswith("trade.") for candidate in manifest["candidates"])

    positive_run_plan = manifest["candidates"][0]["run_plan"]
    negative_run_plan = manifest["candidates"][1]["run_plan"]

    assert positive_run_plan["run"]["id"].startswith("baoma-baseline-efv-pos001-")
    assert positive_run_plan["data"]["refresh_snapshots"] is False
    assert positive_run_plan["execution"] == _baseline_run_plan_fixture()["execution"]
    assert positive_run_plan["strategy"] == _baseline_run_plan_fixture()["strategy"]
    assert positive_run_plan["analysis"]["entry_attribution"]["entry_filter"] == {
        "enabled": True,
        "conditions": [
            {
                "field": "symbol.ma.trend_state",
                "operator": "eq",
                "value": "bullish",
                "action": "keep",
            }
        ],
        "missing_policy": "block",
    }
    assert negative_run_plan["analysis"]["entry_attribution"]["entry_filter"]["conditions"][0]["action"] == "exclude"

    for candidate in manifest["candidates"]:
        RunPlan.from_mapping(candidate["run_plan"])

    markdown = render_entry_factor_validation_manifest_markdown_zh(manifest)
    assert "入场单因子验证 Manifest" in markdown
    assert "keep" in markdown
    assert "exclude" in markdown


def test_entry_factor_validation_manifest_cli_writes_artifacts(tmp_path: Path, capsys) -> None:
    discovery_path = tmp_path / "bayesian_factor_discovery.json"
    discovery_path.write_text(json.dumps(_discovery_report_fixture(), ensure_ascii=False), encoding="utf-8")
    baseline_path = tmp_path / "baseline.yaml"
    baseline_path.write_text(yaml.safe_dump(_baseline_run_plan_fixture(), allow_unicode=True, sort_keys=False), encoding="utf-8")

    exit_code = manifest_cli.main(
        [
            "--discovery",
            str(discovery_path),
            "--baseline-run-plan",
            str(baseline_path),
            "--output-dir",
            str(tmp_path / "manifest"),
            "--positive-limit",
            "1",
            "--negative-limit",
            "1",
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["schema"] == ENTRY_FACTOR_VALIDATION_MANIFEST_SCHEMA
    assert stdout["generated_count"] == 2
    assert (tmp_path / "manifest" / "entry_factor_validation_manifest.json").exists()
    assert (tmp_path / "manifest" / "entry_factor_validation_manifest.zh.md").exists()
    assert len(stdout["artifacts"]["entry_factor_validation_run_plan_paths"]) == 2

    generated = yaml.safe_load(Path(stdout["artifacts"]["entry_factor_validation_run_plan_paths"][0]).read_text(encoding="utf-8"))
    RunPlan.from_mapping(generated)


def test_entry_factor_validation_manifest_skips_future_candidates_even_if_ranked() -> None:
    discovery = _discovery_report_fixture()
    discovery["rankings"]["tradable_pre_entry"]["positive"].insert(
        0,
        _candidate("trade.path.reached_10pct_bucket", "reached", "positive", 5.0, 10),
    )

    manifest = build_entry_factor_validation_manifest(
        discovery,
        _baseline_run_plan_fixture(),
        positive_limit=2,
        negative_limit=0,
    )

    assert manifest["generated_count"] == 2
    assert [candidate["field_key"] for candidate in manifest["candidates"]] == [
        "symbol.ma.trend_state",
        "industry.kdj.week.state",
    ]


def test_entry_factor_validation_manifest_skips_undeclared_runtime_candidates() -> None:
    discovery = _discovery_report_fixture()
    discovery["rankings"]["tradable_pre_entry"]["positive"].insert(
        0,
        _candidate("entry.market_cap.total_mv_abs_bucket", "0_100yi", "positive", 5.0, 10),
    )

    manifest = build_entry_factor_validation_manifest(
        discovery,
        _baseline_run_plan_fixture(),
        positive_limit=1,
        negative_limit=0,
    )

    assert manifest["generated_count"] == 1
    assert manifest["candidates"][0]["field_key"] == "symbol.ma.trend_state"


def test_entry_factor_validation_manifest_includes_new_runtime_bucket_candidates() -> None:
    discovery = _discovery_report_fixture()
    discovery["rankings"]["tradable_pre_entry"]["positive"] = [
        _candidate("industry.volatility.return_vol_60d_bucket", "2_3pct", "positive", 5.0, 10),
        _candidate("market.csi500.return_vol_20d_bucket", "3_5pct", "positive", 4.0, 10),
        _candidate("market.csi500.weekly.kdj_state", "strong", "positive", 3.8, 10),
        _candidate("entry.volatility.symbol_atr_to_industry_median_bucket", "1p2_1p6x", "positive", 3.6, 10),
        _candidate("entry.momentum.return_120d_bucket", "p80_p100", "positive", 3.4, 10),
        _candidate("entry.momentum.new_high_120d_bucket", "new_high", "positive", 3.2, 10),
        _candidate("market.objective.entry_index_drawdown_250d_bucket", "drawdown_gt_20pct", "positive", 3.1, 10),
        _candidate("market.objective.entry_index_ma60_slope_20d_bucket", "down_gt_5pct", "positive", 3.05, 10),
        _candidate("entry.signal_strength.signal_candle_body_bucket", "gte_5pct", "positive", 3.0, 10),
        _candidate("entry.signal_strength.signal_upper_lower_shadow_bucket", "long_lower_shadow", "positive", 2.9, 10),
        _candidate("entry.signal_strength.dea_waterline_age_trading_days_bucket", "day_1_3", "positive", 2.85, 10),
        _candidate("entry.signal_strength.macd_bar_bucket", "0_0p1pct", "positive", 2.8, 10),
        _candidate("entry.momentum.return_20d_bucket", "p80_p100", "positive", 2.6, 10),
        _candidate("entry.stop_fit.fixed_atr_multiple_bucket", "2_3atr", "positive", 2.5, 10),
        _candidate("entry.price_position.interval_60d_bucket", "low_0_20", "positive", 2.4, 10),
        _candidate(
            "entry.price_position.signal_close_ma60_atr_multiple_bucket",
            "above_ma60_0_1atr",
            "positive",
            2.2,
            10,
        ),
    ]

    manifest = build_entry_factor_validation_manifest(
        discovery,
        _baseline_run_plan_fixture(),
        positive_limit=16,
        negative_limit=0,
    )

    assert manifest["generated_count"] == 16
    assert [candidate["field_key"] for candidate in manifest["candidates"]] == [
        "industry.volatility.return_vol_60d_bucket",
        "market.csi500.return_vol_20d_bucket",
        "market.csi500.weekly.kdj_state",
        "entry.volatility.symbol_atr_to_industry_median_bucket",
        "entry.momentum.return_120d_bucket",
        "entry.momentum.new_high_120d_bucket",
        "market.objective.entry_index_drawdown_250d_bucket",
        "market.objective.entry_index_ma60_slope_20d_bucket",
        "entry.signal_strength.signal_candle_body_bucket",
        "entry.signal_strength.signal_upper_lower_shadow_bucket",
        "entry.signal_strength.dea_waterline_age_trading_days_bucket",
        "entry.signal_strength.macd_bar_bucket",
        "entry.momentum.return_20d_bucket",
        "entry.stop_fit.fixed_atr_multiple_bucket",
        "entry.price_position.interval_60d_bucket",
        "entry.price_position.signal_close_ma60_atr_multiple_bucket",
    ]


def _discovery_report_fixture() -> dict:
    return {
        "schema": "attbacktrader.bayesian_factor_discovery.v1",
        "run_id": "discovery-test",
        "source_artifacts": {"wide_samples": "wide.json", "field_index": None},
        "rankings": {
            "tradable_pre_entry": {
                "positive": [
                    _candidate("symbol.ma.trend_state", "bullish", "positive", 1.5, 8),
                    _candidate("industry.kdj.week.state", "strong", "positive", 1.1, 6),
                ],
                "negative": [
                    _candidate("symbol.macd.energy_zone", "green_bar_or_zero", "negative", -1.4, 8),
                    _candidate("market.hs300.trend_state", "not_bullish", "negative", -1.0, 5),
                ],
                "weak": [],
            },
            "lifecycle_diagnostic": {
                "positive": [
                    _candidate("trade.path.reached_10pct_bucket", "reached", "positive", 2.0, 8),
                ],
                "negative": [],
                "weak": [],
            },
        },
    }


def _candidate(field_key: str, value: str, direction: str, score: float, sample_count: int) -> dict:
    return {
        "field_key": field_key,
        "field_label_zh": field_key,
        "value": value,
        "value_label_zh": value,
        "label_zh": f"{field_key}={value}",
        "direction": direction,
        "factor_quality_score": score,
        "sample_count": sample_count,
        "future_function_guard": {"eligible_for_entry_rule_review": not field_key.startswith("trade.")},
        "flags": [],
    }


def _baseline_run_plan_fixture() -> dict:
    return {
        "run": {
            "id": "baoma-baseline",
            "from_date": "2023-01-01",
            "to_date": "2024-12-31",
        },
        "data": {
            "snapshot_root": "data/snapshots",
            "refresh_snapshots": True,
            "symbols": ["000001.SZ"],
            "benchmark_series": {"indexes": ["000300.SH"]},
        },
        "strategy": {
            "template": "trend_template_v1",
            "entry_method": "baoma_entry",
            "profit_taking_method": "baoma_ma25_profit_exit",
            "stop_loss_method": "baoma_ma60_stop",
            "add_on_method": "baoma_add_on",
            "sizing_rule": "equal_weight",
            "sizing_params": {"max_holding_count": 800, "min_order_quantity": 100},
        },
        "constraints": {"ashare": {"enabled": True, "board_lot_size": 100}},
        "broker": {
            "initial_cash": 1_200_000,
            "commission_rate": 0.0003,
            "stamp_tax_rate": 0.001,
            "transfer_fee_rate": 0.00001,
            "slippage": {"type": "percent", "value": 0.0005},
        },
        "execution": {
            "engine": "baoma_v1_business",
            "stake": 100,
            "baoma": {
                "buy_slice_fraction": 0.25,
                "first_scale_out_return": 0.04,
                "second_scale_out_return": 0.12,
                "scale_out_mode": "atr_multiple",
                "first_scale_out_atr_multiple": 2.0,
                "second_scale_out_atr_multiple": 4.0,
            },
        },
        "analysis": {
            "industry_attribution": {"enabled": False},
            "market_regime": {"enabled": False},
            "scenario_fit": {"enabled": False},
        },
    }
