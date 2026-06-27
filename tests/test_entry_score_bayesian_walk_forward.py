import json
from pathlib import Path

import pytest

from attbacktrader.cli import entry_score_bayesian_walk_forward as walk_cli
from attbacktrader.reports import entry_score_bayesian_walk_forward as walk_report
from attbacktrader.reports import (
    ENTRY_SCORE_BAYESIAN_WALK_FORWARD_SCHEMA,
    build_entry_score_bayesian_walk_forward,
    render_entry_score_bayesian_walk_forward_markdown_zh,
    require_optuna_for_entry_score_bayesian_walk_forward,
    write_entry_score_bayesian_walk_forward,
)


def test_entry_score_bayesian_walk_forward_builds_oos_folds() -> None:
    report = build_entry_score_bayesian_walk_forward(
        _environment_fit_payload(),
        first_train_year=2020,
        last_test_year=2024,
        train_years=2,
        n_trials=12,
        seed=7,
        min_train_pass_rate=0.10,
        min_train_sample_count=1,
        min_train_yearly_pass_count=1,
        optimizer="random",
        sample_limit=3,
    )
    markdown = render_entry_score_bayesian_walk_forward_markdown_zh(report)

    assert report["schema"] == ENTRY_SCORE_BAYESIAN_WALK_FORWARD_SCHEMA
    assert report["configuration"]["optimizer"] == "explicit_random_search"
    assert report["configuration"]["min_train_yearly_pass_count"] == 1
    assert [fold["test_year"] for fold in report["folds"]] == [2022, 2023, 2024]
    assert report["aggregate_oos"]["all_test_trades"]["sample_count"] == 12
    assert "min_entry_score" in report["folds"][0]["optimization"]["best_params"]
    top_trial_details = report["folds"][0]["optimization"]["top_trials"][0]["details"]
    assert "yearly_sample_penalty" in top_trial_details
    assert "selected_count_by_year" in top_trial_details
    assert report["best_parameter_summary"]
    assert "贝叶斯因子分数 Walk-Forward" in markdown
    assert "OOS 汇总" in markdown


def test_entry_score_bayesian_walk_forward_cli_writes_outputs(tmp_path: Path, capsys) -> None:
    source_path = tmp_path / "environment_fit.enriched.json"
    source_path.write_text(json.dumps(_environment_fit_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = walk_cli.main(
        [
            "--environment-fit",
            str(source_path),
            "--first-train-year",
            "2020",
            "--last-test-year",
            "2022",
            "--train-years",
            "2",
            "--n-trials",
            "4",
            "--optimizer",
            "random",
            "--min-train-pass-rate",
            "0.10",
            "--min-train-sample-count",
            "1",
            "--min-train-yearly-pass-count",
            "1",
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["schema"] == ENTRY_SCORE_BAYESIAN_WALK_FORWARD_SCHEMA
    assert stdout["configuration"]["min_train_yearly_pass_count"] == 1
    assert stdout["fold_count"] == 1
    assert (tmp_path / "out" / "entry_score_bayesian_walk_forward.json").exists()
    assert (tmp_path / "out" / "entry_score_bayesian_walk_forward.zh.md").exists()


def test_write_entry_score_bayesian_walk_forward_returns_payload_with_artifacts(tmp_path: Path) -> None:
    report = build_entry_score_bayesian_walk_forward(
        _environment_fit_payload(),
        first_train_year=2020,
        last_test_year=2022,
        train_years=2,
        n_trials=4,
        optimizer="random",
        min_train_pass_rate=0.10,
        min_train_sample_count=1,
    )

    json_path, markdown_path, payload = write_entry_score_bayesian_walk_forward(report, output_dir=tmp_path)

    assert json_path.exists()
    assert markdown_path.exists()
    assert payload["artifacts"]["walk_forward_markdown_zh"].endswith("entry_score_bayesian_walk_forward.zh.md")


def test_require_optuna_for_entry_score_bayesian_walk_forward_fails_explicitly() -> None:
    def fake_import_module(name: str) -> object:
        raise ImportError(name)

    with pytest.raises(ImportError, match="Optuna is required for Bayesian entry-score tuning"):
        require_optuna_for_entry_score_bayesian_walk_forward(import_module=fake_import_module)


def test_entry_score_objective_penalizes_sparse_training_years() -> None:
    base_config = walk_report._normalize_scoring_config(
        {
            "factor_weights": {"rank": {"top": 2.0}},
            "interaction_weights": [],
        }
    )
    weight_specs = walk_report._build_weight_parameter_specs(base_config)
    params = {str(spec["name"]): float(spec["default"]) for spec in weight_specs}
    params["min_entry_score"] = 1.0
    rows = [
        _trade(1, "2020-01-05", 0.10, {"rank": "top"}),
        _trade(2, "2020-02-05", 0.10, {"rank": "low"}),
        _trade(3, "2021-01-05", 0.10, {"rank": "low"}),
    ]

    _, details = walk_report._score_objective(
        rows,
        base_config=base_config,
        weight_specs=weight_specs,
        params=params,
        min_train_pass_rate=0.0,
        min_train_sample_count=1,
        min_train_yearly_pass_count=1,
    )

    assert details["selected_count_by_year"] == {2020: 1, 2021: 0}
    assert details["yearly_sample_penalty"] > 0


def _environment_fit_payload() -> dict:
    trades = []
    trade_index = 1
    for year in range(2020, 2025):
        trades.extend(
            [
                _trade(trade_index, f"{year}-01-05", 0.12, _strong_environment()),
                _trade(trade_index + 1, f"{year}-02-05", 0.08, _strong_environment()),
                _trade(trade_index + 2, f"{year}-03-05", -0.06, _weak_environment()),
                _trade(trade_index + 3, f"{year}-04-05", -0.03, _weak_environment()),
            ]
        )
        trade_index += 4
    return {
        "schema": "attbacktrader.environment_fit.v1",
        "run_id": "entry-score-walk-forward-test",
        "trade_contributions": trades,
    }


def _strong_environment() -> dict:
    return {
        "entry.price_position.ma60_atr_multiple_bucket": "above_ma60_gt_2atr",
        "entry.signal_strength.dif_dea_distance_bucket": "gte_0p6pct",
        "entry.signal_strength.macd_bar_bucket": "gte_0p6pct",
        "entry.signal_strength.dea_value_bucket": "gte_0p6pct",
        "entry.momentum.symbol_vs_hs300_return_20d_bucket": "outperform_gt_10pct",
        "entry.momentum.symbol_vs_industry_return_20d_bucket": "outperform_gt_10pct",
        "entry.price_position.near_high_60d_bucket": "near_high",
        "entry.signal_strength.signal_candle_body_bucket": "gte_5pct",
        "entry.signal_strength.signal_upper_lower_shadow_bucket": "long_lower_shadow",
        "entry.liquidity.amount_5d_vs_20d_bucket": "gte_2x",
        "entry.signal_strength.ma60_slope_20d_bucket": "flat_0_2pct",
        "entry.volatility.atr_20d_bucket": "p60_p80",
        "market.objective.entry_stage": "bearish",
    }


def _weak_environment() -> dict:
    return {
        "entry.price_position.ma60_atr_multiple_bucket": "above_ma60_0_1atr",
        "entry.signal_strength.dif_dea_distance_bucket": "lte_0",
        "entry.signal_strength.macd_bar_bucket": "lte_0",
        "entry.signal_strength.dea_value_bucket": "0_0p1pct",
        "entry.signal_strength.signal_candle_body_bucket": "lt_1pct",
        "entry.signal_strength.signal_upper_lower_shadow_bucket": "short_shadows",
        "entry.liquidity.amount_5d_vs_20d_bucket": "lt_0p8x",
        "market.hs300.weekly.kdj_state": "oversold",
    }


def _trade(trade_index: int, entry_date: str, return_pct: float, environment: dict) -> dict:
    return {
        "trade_index": trade_index,
        "symbol": f"000{trade_index:03d}.SZ",
        "entry_date": entry_date,
        "exit_date": entry_date,
        "outcome": "win" if return_pct > 0 else "loss",
        "exit_reason": "TAKE_PROFIT" if return_pct > 0 else "STOP_LOSS",
        "return_pct": return_pct,
        "environment": environment,
        "entry_gross_value": 1000.0,
        "exit_gross_value": 1000.0 * (1.0 + return_pct),
        "net_pnl": 1000.0 * return_pct,
        "return_on_entry_value": return_pct,
    }
