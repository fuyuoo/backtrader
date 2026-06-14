from pathlib import Path

import pytest
from pydantic import ValidationError

from attbacktrader.config import RunPlan, load_run_plan
from attbacktrader.config.loader import ConfigLoadError
from attbacktrader.features import IndicatorRequirement
from attbacktrader.strategies.bindings import bind_strategy_methods, required_indicators_for_strategy_config


def minimal_config() -> dict:
    return {
        "run": {
            "id": "unit-test",
            "from_date": "2021-01-01",
            "to_date": "2021-12-31",
        },
        "data": {
            "snapshot_root": "data/snapshots",
            "symbols": ["000001.SZ"],
            "benchmark_series": {"indexes": ["000300.SH"]},
        },
        "strategy": {
            "template": "trend_template_v1",
            "entry_method": "kdj_oversold_entry",
            "profit_taking_method": "kdj_overheated_exit",
            "stop_loss_method": "fixed_percent_stop",
            "sizing_rule": "equal_weight",
        },
        "broker": {
            "initial_cash": 1000000,
            "commission_rate": 0.0003,
            "stamp_tax_rate": 0.001,
            "transfer_fee_rate": 0.00001,
            "slippage": {"type": "percent", "value": 0.0005},
        },
    }


def test_example_run_yaml_loads_to_immutable_run_plan() -> None:
    run_plan = load_run_plan(Path("examples/run.yaml"))

    assert run_plan.run.id == "trend-v1-example"
    assert run_plan.strategy.template == "trend_template_v1"
    assert run_plan.strategy.entry_method == "kdj_oversold_entry"
    assert run_plan.strategy.profit_taking_method == "kdj_overheated_exit"
    assert run_plan.strategy.stop_loss_method == "fixed_percent_stop"
    assert run_plan.data.provider == "tushare"
    assert run_plan.data.price_adjustment == "qfq"
    assert run_plan.data.refresh_snapshots is True
    assert run_plan.data.symbols == ()
    assert [series.symbol for series in run_plan.data.resolved_tradable_series] == ["000001.SZ", "600519.SH"]
    assert [series.asset_type for series in run_plan.data.resolved_tradable_series] == ["stock", "stock"]
    assert run_plan.execution.engine == "backtrader"
    assert run_plan.execution.stake == 100
    assert run_plan.output.persist is True
    assert run_plan.output.report_root == Path("reports")
    assert run_plan.output.artifact_detail == "compact"
    assert run_plan.output.signal_audit_sample_limit == 200
    assert run_plan.analysis.industry_attribution.source == "SW2021"
    assert run_plan.analysis.market_regime.timeframes == ("D", "W", "M")
    assert run_plan.analysis.scenario_fit.min_trades == 3
    assert run_plan.analysis.entry_attribution.enabled is True
    assert run_plan.analysis.entry_attribution.market_symbol == "000300.SH"
    assert run_plan.analysis.entry_attribution.entry_filter.enabled is False
    assert run_plan.data.benchmark_series.indexes == (
        "000001.SH",
        "000300.SH",
        "399006.SZ",
    )

    with pytest.raises(ValidationError, match="frozen"):
        run_plan.run.id = "changed"


def test_expanded_baseline_example_loads_as_fixed_stake_comparison_run() -> None:
    run_plan = load_run_plan(Path("examples/run-tushare-expanded-baseline.yaml"))

    assert run_plan.run.id == "tushare-expanded-baseline-2023-2024"
    assert run_plan.run.from_date.isoformat() == "2023-01-01"
    assert run_plan.run.to_date.isoformat() == "2024-12-31"
    assert len(run_plan.data.resolved_tradable_series) == 10
    assert run_plan.data.benchmark_series.indexes == (
        "000001.SH",
        "000300.SH",
        "399006.SZ",
        "000905.SH",
    )
    assert run_plan.data.industry_series.indexes == (
        "801780.SI",
        "801120.SI",
        "801110.SI",
        "801150.SI",
        "801730.SI",
        "801080.SI",
        "801790.SI",
    )
    assert run_plan.strategy.sizing_params == {}
    assert run_plan.execution.stake == 100
    assert run_plan.analysis.scenario_fit.min_trades == 10


def test_expanded_sized_example_loads_practical_portfolio_controls() -> None:
    run_plan = load_run_plan(Path("examples/run-tushare-expanded-sized.yaml"))
    methods = bind_strategy_methods(run_plan.strategy)

    assert run_plan.run.id == "tushare-expanded-sized-2023-2024"
    assert len(run_plan.data.resolved_tradable_series) == 10
    assert methods.sizing_method.max_holding_count == 5
    assert methods.sizing_method.max_position_percent == 0.18
    assert methods.sizing_method.max_total_exposure_percent == 0.9
    assert methods.sizing_method.max_risk_group_exposure_percent == 0.3
    assert methods.sizing_method.cash_reserve_percent == 0.05
    assert methods.sizing_method.max_turnover_percent == 0.35
    assert methods.sizing_method.risk_group_level == 1
    assert methods.sizing_method.atr_risk_percent == 0.01
    assert methods.sizing_method.atr_timeframe == "D"
    assert IndicatorRequirement("kdj", "D") in required_indicators_for_strategy_config(run_plan.strategy)
    assert IndicatorRequirement("atr14", "D") in required_indicators_for_strategy_config(run_plan.strategy)


def test_expanded_add_on_example_enforces_minimum_board_lot_sizing() -> None:
    run_plan = load_run_plan(Path("examples/run-tushare-expanded-add-on.yaml"))
    methods = bind_strategy_methods(run_plan.strategy)

    assert run_plan.run.id == "tushare-expanded-add-on-2023-2024"
    assert methods.sizing_method.min_order_quantity == 100


def test_baoma_example_loads_dedicated_business_runner_config() -> None:
    run_plan = load_run_plan(Path("examples/run-baoma-v1-fixed-sample.yaml"))

    assert run_plan.data.stock_pool_file == Path("examples/stock-pools/baoma-hs300-csi500-20260607.csv")
    assert len(run_plan.data.resolved_tradable_series) == 800
    assert run_plan.data.resolved_tradable_series[0].symbol == "000001.SZ"
    assert run_plan.data.resolved_tradable_series[-1].symbol == "689009.SH"
    assert {series.asset_type for series in run_plan.data.resolved_tradable_series} == {"stock"}
    assert {series.price_adjustment for series in run_plan.data.resolved_tradable_series} == {"qfq"}
    assert run_plan.execution.engine == "baoma_v1_business"
    assert run_plan.execution.baoma.buy_slice_fraction == pytest.approx(0.33)
    assert run_plan.execution.baoma.scale_out_mode == "fixed_percent"
    assert run_plan.execution.baoma.first_scale_out_return == pytest.approx(0.05)
    assert run_plan.execution.baoma.second_scale_out_return == pytest.approx(0.15)
    assert run_plan.execution.baoma.force_exit_at_end is False
    assert run_plan.analysis.industry_attribution.enabled is True
    assert run_plan.analysis.industry_attribution.source == "SW2021"
    assert len(run_plan.data.industry_series.indexes) == 31
    assert "801780.SI" in run_plan.data.industry_series.indexes


def test_baoma_execution_config_accepts_atr_scale_out() -> None:
    raw_config = minimal_config()
    raw_config["execution"] = {
        "engine": "baoma_v1_business",
        "baoma": {
            "scale_out_mode": "atr_multiple",
            "first_scale_out_atr_multiple": 1.0,
            "second_scale_out_atr_multiple": 2.0,
        },
    }

    run_plan = RunPlan.from_mapping(raw_config)

    assert run_plan.execution.baoma.scale_out_mode == "atr_multiple"
    assert run_plan.execution.baoma.first_scale_out_atr_multiple == pytest.approx(1.0)
    assert run_plan.execution.baoma.second_scale_out_atr_multiple == pytest.approx(2.0)


def test_baoma_execution_config_accepts_second_scale_out_confirmation() -> None:
    raw_config = minimal_config()
    raw_config["execution"] = {
        "engine": "baoma_v1_business",
        "baoma": {
            "scale_out_mode": "atr_multiple",
            "first_scale_out_atr_multiple": 2.0,
            "second_scale_out_atr_multiple": 4.0,
            "second_scale_out_confirmation": {
                "enabled": True,
                "mode": "kdj_cci_boll_up_distance",
                "min_kdj_j": 100.0,
                "min_cci14": 150.0,
                "min_boll_up_distance": 0.03,
            },
        },
    }

    run_plan = RunPlan.from_mapping(raw_config)

    confirmation = run_plan.execution.baoma.second_scale_out_confirmation
    assert confirmation.enabled is True
    assert confirmation.mode == "kdj_cci_boll_up_distance"
    assert confirmation.min_kdj_j == pytest.approx(100.0)
    assert confirmation.min_cci14 == pytest.approx(150.0)
    assert confirmation.min_boll_up_distance == pytest.approx(0.03)


def test_baoma_execution_config_requires_confirmation_thresholds_by_mode() -> None:
    raw_config = minimal_config()
    raw_config["execution"] = {
        "engine": "baoma_v1_business",
        "baoma": {
            "scale_out_mode": "atr_multiple",
            "first_scale_out_atr_multiple": 2.0,
            "second_scale_out_atr_multiple": 4.0,
            "second_scale_out_confirmation": {
                "enabled": True,
                "mode": "kdj_cci",
                "min_kdj_j": 100.0,
            },
        },
    }

    with pytest.raises(ValidationError, match="min_cci14"):
        RunPlan.from_mapping(raw_config)


def test_baoma_execution_config_rejects_confirmation_for_fixed_scale_out() -> None:
    raw_config = minimal_config()
    raw_config["execution"] = {
        "engine": "baoma_v1_business",
        "baoma": {
            "scale_out_mode": "fixed_percent",
            "second_scale_out_confirmation": {
                "enabled": True,
                "mode": "boll_up_distance",
                "min_boll_up_distance": 0.03,
            },
        },
    }

    with pytest.raises(ValidationError, match="second_scale_out_confirmation"):
        RunPlan.from_mapping(raw_config)


def test_baoma_execution_config_requires_atr_scale_out_multiples() -> None:
    raw_config = minimal_config()
    raw_config["execution"] = {
        "engine": "baoma_v1_business",
        "baoma": {
            "scale_out_mode": "atr_multiple",
        },
    }

    with pytest.raises(ValidationError, match="first_scale_out_atr_multiple"):
        RunPlan.from_mapping(raw_config)


def test_attribution_filter_example_loads_configured_entry_filter() -> None:
    run_plan = load_run_plan(Path("examples/run-tushare-attribution-filter.yaml"))

    assert run_plan.run.id == "tushare-attribution-filter-2023-2024"
    assert run_plan.analysis.entry_attribution.enabled is True
    assert run_plan.analysis.entry_attribution.entry_filter.enabled is True
    assert run_plan.analysis.entry_attribution.entry_filter.require_checks == (
        "symbol.ma.price_above_ma25",
        "market.hs300.bullish_trend",
    )
    assert "industry.kdj.j_below_threshold" in run_plan.analysis.entry_attribution.factors


def test_minimal_valid_config_uses_default_analysis_and_constraints() -> None:
    run_plan = RunPlan.from_mapping(minimal_config())

    assert run_plan.constraints.ashare.enabled is True
    assert run_plan.constraints.ashare.board_lot_size == 100
    assert run_plan.data.provider == "tushare"
    assert run_plan.data.price_adjustment == "qfq"
    assert run_plan.data.refresh_snapshots is True
    assert run_plan.data.resolved_tradable_series[0].symbol == "000001.SZ"
    assert run_plan.data.resolved_tradable_series[0].asset_type == "stock"
    assert run_plan.data.resolved_tradable_series[0].price_adjustment == "qfq"
    assert run_plan.execution.engine == "business"
    assert run_plan.execution.stake == 100
    assert run_plan.output.persist is True
    assert run_plan.output.report_root == Path("reports")
    assert run_plan.analysis.industry_attribution.source == "SW2021"
    assert run_plan.analysis.industry_attribution.levels == (1, 2, 3)
    assert run_plan.analysis.market_regime.enabled is True
    assert run_plan.analysis.market_regime.timeframes == ("D", "W", "M")
    assert run_plan.analysis.scenario_fit.enabled is True
    assert run_plan.analysis.scenario_fit.min_trades == 3
    assert "symbol.ma.price_above_ma25" in run_plan.analysis.entry_attribution.resolved_factors
    assert run_plan.analysis.attribution.enabled is True
    assert "symbol.ma.price_above_ma25" in run_plan.analysis.resolved_attribution_factor_selection["include"]
    assert run_plan.analysis.resolved_attribution_factor_selection["not_include"] == ()
    assert run_plan.analysis.post_exit.window_days == (5,)
    assert run_plan.analysis.post_exit.primary_window_days == 5
    assert run_plan.analysis.post_exit.rebound_thresholds == (0.0, 0.02, 0.05, 0.10)


def test_stock_pool_file_resolves_to_stock_tradable_series(tmp_path: Path) -> None:
    pool_path = tmp_path / "pool.csv"
    pool_path.write_text(
        "\n".join(
            [
                "ts_code,name,source_index,freeze_date",
                "000001.SZ,Ping An Bank,HS300,2026-06-07",
                "600036.SH,China Merchants Bank,HS300,2026-06-07",
            ]
        ),
        encoding="utf-8",
    )
    raw_config = minimal_config()
    raw_config["data"].pop("symbols")
    raw_config["data"]["stock_pool_file"] = str(pool_path)

    run_plan = RunPlan.from_mapping(raw_config)

    assert [series.symbol for series in run_plan.data.resolved_tradable_series] == [
        "000001.SZ",
        "600036.SH",
    ]
    assert [series.asset_type for series in run_plan.data.resolved_tradable_series] == ["stock", "stock"]
    assert [series.price_adjustment for series in run_plan.data.resolved_tradable_series] == ["qfq", "qfq"]


def test_tradable_scope_sources_are_mutually_exclusive() -> None:
    raw_config = minimal_config()
    raw_config["data"]["stock_pool_file"] = "examples/stock-pools/baoma-fixed-sample.csv"

    with pytest.raises(ValidationError, match="tradable scope must use exactly one source"):
        RunPlan.from_mapping(raw_config)


def test_invalid_date_range_fails_before_execution() -> None:
    raw_config = minimal_config()
    raw_config["run"]["from_date"] = "2022-01-01"
    raw_config["run"]["to_date"] = "2021-01-01"

    with pytest.raises(ValidationError, match="to_date"):
        RunPlan.from_mapping(raw_config)


def test_strategy_method_must_be_bound_to_template() -> None:
    raw_config = minimal_config()
    raw_config["strategy"]["entry_method"] = "unknown_entry"

    with pytest.raises(ValidationError, match="not bound"):
        RunPlan.from_mapping(raw_config)


def test_industry_levels_must_be_shenwan_levels() -> None:
    raw_config = minimal_config()
    raw_config["analysis"] = {
        "industry_attribution": {
            "enabled": True,
            "levels": [1, 4],
        }
    }

    with pytest.raises(ValidationError, match="unsupported Shenwan industry levels"):
        RunPlan.from_mapping(raw_config)


def test_market_regime_timeframes_cannot_contain_duplicates() -> None:
    raw_config = minimal_config()
    raw_config["analysis"] = {
        "market_regime": {
            "enabled": True,
            "timeframes": ["D", "D"],
        }
    }

    with pytest.raises(ValidationError, match="timeframes"):
        RunPlan.from_mapping(raw_config)


def test_entry_attribution_config_validates_factors_and_filter_checks() -> None:
    raw_config = minimal_config()
    raw_config["analysis"] = {
        "entry_attribution": {
            "enabled": True,
            "factors": [
                "symbol.ma.price_above_ma25",
                "market.hs300.bullish_trend",
            ],
            "entry_filter": {
                "enabled": True,
                "require_checks": [
                    "symbol.ma.price_above_ma25",
                    "market.hs300.bullish_trend",
                ],
                "missing_policy": "block",
            },
        }
    }

    run_plan = RunPlan.from_mapping(raw_config)

    assert run_plan.analysis.entry_attribution.factors == (
        "symbol.ma.price_above_ma25",
        "market.hs300.bullish_trend",
    )
    assert run_plan.analysis.entry_attribution.entry_filter.require_checks == (
        "symbol.ma.price_above_ma25",
        "market.hs300.bullish_trend",
    )


def test_attribution_config_resolves_include_and_not_include() -> None:
    raw_config = minimal_config()
    raw_config["analysis"] = {
        "attribution": {
            "include": [
                "symbol.ma.price_above_ma25",
                "market.hs300.bullish_trend",
            ],
        }
    }

    run_plan = RunPlan.from_mapping(raw_config)
    selection = run_plan.analysis.resolved_attribution_factor_selection

    assert selection["configured_source"] == "analysis.attribution.include"
    assert selection["include"] == (
        "symbol.ma.price_above_ma25",
        "market.hs300.bullish_trend",
    )
    assert "symbol.ma.ma60" in selection["not_include"]
    assert selection["include_count"] == 2
    assert selection["not_include_count"] == len(selection["applicable"]) - 2
    assert run_plan.analysis.resolved_entry_attribution_factors == selection["include"]
    selected_factors = [factor for factor in selection["factors"] if factor["selected"]]
    assert [factor["key"] for factor in selected_factors] == list(selection["include"])


def test_attribution_config_can_disable_all_factor_selection() -> None:
    raw_config = minimal_config()
    raw_config["analysis"] = {
        "attribution": {"enabled": False},
    }

    run_plan = RunPlan.from_mapping(raw_config)
    selection = run_plan.analysis.resolved_attribution_factor_selection

    assert selection["include"] == ()
    assert "symbol.ma.price_above_ma25" in selection["not_include"]
    assert run_plan.analysis.resolved_entry_attribution_factors == ()


def test_attribution_include_validates_unknown_and_duplicate_factors() -> None:
    raw_config = minimal_config()
    raw_config["analysis"] = {
        "attribution": {
            "include": ["symbol.ma.ma60", "symbol.ma.ma60"],
        }
    }

    with pytest.raises(ValidationError, match="cannot contain duplicates"):
        RunPlan.from_mapping(raw_config)

    raw_config = minimal_config()
    raw_config["analysis"] = {
        "attribution": {
            "include": ["missing.factor"],
        }
    }

    with pytest.raises(ValidationError, match="unknown attribution include factors"):
        RunPlan.from_mapping(raw_config)


def test_entry_attribution_filter_checks_must_be_enabled_factors() -> None:
    raw_config = minimal_config()
    raw_config["analysis"] = {
        "entry_attribution": {
            "factors": ["symbol.ma.price_above_ma25"],
            "entry_filter": {
                "enabled": True,
                "require_checks": ["market.hs300.bullish_trend"],
            },
        }
    }

    with pytest.raises(ValidationError, match="must be included"):
        RunPlan.from_mapping(raw_config)


def test_post_exit_analysis_config_validates_windows() -> None:
    raw_config = minimal_config()
    raw_config["analysis"] = {
        "post_exit": {
            "window_days": [10, 3, 5],
            "primary_window_days": 5,
            "sold_too_early_threshold": 0.01,
            "rebound_thresholds": [0.05, 0.0, 0.02],
        }
    }

    run_plan = RunPlan.from_mapping(raw_config)

    assert run_plan.analysis.post_exit.window_days == (3, 5, 10)
    assert run_plan.analysis.post_exit.primary_window_days == 5
    assert run_plan.analysis.post_exit.sold_too_early_threshold == 0.01
    assert run_plan.analysis.post_exit.rebound_thresholds == (0.0, 0.02, 0.05)


def test_post_exit_primary_window_must_be_configured() -> None:
    raw_config = minimal_config()
    raw_config["analysis"] = {
        "post_exit": {
            "window_days": [3, 10],
            "primary_window_days": 5,
        }
    }

    with pytest.raises(ValidationError, match="primary_window_days"):
        RunPlan.from_mapping(raw_config)


def test_tradable_series_can_mix_asset_types() -> None:
    raw_config = minimal_config()
    raw_config["data"].pop("symbols")
    raw_config["data"]["tradable_series"] = [
        {"symbol": "000001.SZ", "asset_type": "stock", "price_adjustment": "qfq"},
        {"symbol": "000001.SH", "asset_type": "index"},
        {"symbol": "801780.SI", "asset_type": "industry_index"},
    ]

    run_plan = RunPlan.from_mapping(raw_config)

    assert run_plan.data.symbols == ()
    assert [series.symbol for series in run_plan.data.resolved_tradable_series] == [
        "000001.SZ",
        "000001.SH",
        "801780.SI",
    ]
    assert [series.asset_type for series in run_plan.data.resolved_tradable_series] == [
        "stock",
        "index",
        "industry_index",
    ]
    assert [series.price_adjustment for series in run_plan.data.resolved_tradable_series] == ["qfq", "none", "none"]


def test_yaml_must_contain_mapping(tmp_path: Path) -> None:
    config_path = tmp_path / "bad.yaml"
    config_path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

    with pytest.raises(ConfigLoadError, match="must contain a YAML mapping"):
        load_run_plan(config_path)
