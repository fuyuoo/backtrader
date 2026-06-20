from pathlib import Path

import yaml

from attbacktrader.cli.attribution_filter_experiments import generate_attribution_filter_experiment_configs
from attbacktrader.config import RunPlan


def test_generate_attribution_filter_experiment_configs_writes_valid_run_plans(tmp_path: Path) -> None:
    base_config = {
        "run": {"id": "base", "from_date": "2024-01-01", "to_date": "2024-12-31"},
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
        "analysis": {
            "entry_attribution": {
                "factors": ["symbol.ma.price_above_ma25"],
                "entry_filter": {"enabled": True, "require_checks": ["symbol.ma.price_above_ma25"]},
            }
        },
    }
    matrix = {
        "base_config": "base.yaml",
        "variants": [
            {
                "name": "symbol-ma-hs300",
                "require_checks": [
                    "symbol.ma.price_above_ma60",
                    "symbol.ma.bullish_trend",
                    "market.hs300.bullish_trend",
                ],
                "missing_policy": "pass",
                "market_fast_period": 10,
                "market_slow_period": 40,
            }
        ],
    }
    (tmp_path / "base.yaml").write_text(yaml.safe_dump(base_config, sort_keys=False), encoding="utf-8")
    matrix_path = tmp_path / "matrix.yaml"
    matrix_path.write_text(yaml.safe_dump(matrix, sort_keys=False), encoding="utf-8")

    generated_paths = generate_attribution_filter_experiment_configs(
        matrix_path=matrix_path,
        output_dir=tmp_path / "generated",
    )

    generated = yaml.safe_load(generated_paths[0].read_text(encoding="utf-8"))
    run_plan = RunPlan.from_mapping(generated)

    assert generated_paths[0].name == "base-symbol-ma-hs300.yaml"
    assert run_plan.run.id == "base-symbol-ma-hs300"
    assert run_plan.analysis.entry_attribution.market_fast_period == 10
    assert run_plan.analysis.entry_attribution.market_slow_period == 40
    assert run_plan.analysis.entry_attribution.entry_filter.missing_policy == "pass"
    assert "symbol.ma.price_above_ma60" in run_plan.analysis.entry_attribution.factors
    assert "symbol.ma.bullish_trend" in run_plan.analysis.entry_attribution.factors
    assert "market.hs300.bullish_trend" in run_plan.analysis.entry_attribution.factors
