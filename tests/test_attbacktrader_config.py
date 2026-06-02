from pathlib import Path

import pytest
from pydantic import ValidationError

from attbacktrader.config import RunPlan, load_run_plan
from attbacktrader.config.loader import ConfigLoadError


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
    assert run_plan.analysis.industry_attribution.source == "SW2021"
    assert run_plan.analysis.market_regime.timeframes == ("D", "W", "M")
    assert run_plan.analysis.scenario_fit.min_trades == 3
    assert run_plan.data.benchmark_series.indexes == (
        "000001.SH",
        "000300.SH",
        "399006.SZ",
        "000510.SH",
    )

    with pytest.raises(ValidationError, match="frozen"):
        run_plan.run.id = "changed"


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
