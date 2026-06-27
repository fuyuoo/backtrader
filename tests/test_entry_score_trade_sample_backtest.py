import json
from pathlib import Path

import pytest

from attbacktrader.cli import entry_score_trade_sample_backtest as score_cli
from attbacktrader.reports import (
    ENTRY_SCORE_TRADE_SAMPLE_BACKTEST_SCHEMA,
    build_entry_score_trade_sample_backtest,
    render_entry_score_trade_sample_backtest_markdown_zh,
    write_entry_score_trade_sample_backtest,
)


def test_entry_score_trade_sample_backtest_scores_and_filters_completed_trades() -> None:
    report = build_entry_score_trade_sample_backtest(_environment_fit_payload(), year=2024, min_entry_score=4.0)
    markdown = render_entry_score_trade_sample_backtest_markdown_zh(report)

    assert report["schema"] == ENTRY_SCORE_TRADE_SAMPLE_BACKTEST_SCHEMA
    assert report["year"] == 2024
    assert report["funnel"]["raw_completed_trades"] == 3
    assert report["funnel"]["score_passed_trades"] == 2
    assert report["summary"]["all_year_trades"]["sample_count"] == 3
    assert report["summary"]["score_passed"]["average_return_pct"] == pytest.approx(0.075)
    assert report["summary"]["score_passed"]["win_rate"] == pytest.approx(0.5)
    assert report["summary"]["score_blocked"]["average_return_pct"] == pytest.approx(-0.06)
    assert report["ranked_trades"][0]["trade_index"] == 1
    assert "固定因子打分一年验证" in markdown
    assert "无持仓上限" in markdown


def test_entry_score_trade_sample_backtest_applies_large_risk_deductions() -> None:
    payload = {
        "schema": "attbacktrader.environment_fit.v1",
        "run_id": "entry-score-risk-test",
        "trade_contributions": [
            _trade(
                5,
                "2024-04-05",
                0.10,
                {
                    "entry.price_position.ma60_atr_multiple_bucket": "above_ma60_gt_2atr",
                    "entry.signal_strength.dif_dea_distance_bucket": "gte_0p6pct",
                    "entry.signal_strength.macd_bar_bucket": "gte_0p6pct",
                    "entry.signal_strength.dea_value_bucket": "gte_0p6pct",
                    "entry.price_position.near_high_60d_bucket": "near_high",
                    "entry.momentum.return_20d_bucket": "p0_p20",
                    "entry.momentum.return_60d_bucket": "p0_p20",
                    "entry.signal_strength.dea_waterline_age_trading_days_bucket": "day_8_14",
                    "entry.stop_fit.fixed_atr_multiple_bucket": "2_3atr",
                    "entry.volatility.symbol_atr_to_industry_median_bucket": "1p2_1p6x",
                    "entry.weekly.symbol_kdj_state": "overheated",
                    "industry.weekly.kdj_state": "overheated",
                    "market.csi500.weekly.kdj_state": "strong",
                    "market.csi500.trend_state": "bearish",
                },
            ),
        ],
    }

    report = build_entry_score_trade_sample_backtest(payload, year=2024, min_entry_score=4.0)
    row = report["ranked_trades"][0]
    interaction_names = {item["name"] for item in row["score_contributions"]["interaction_weights"]}

    assert report["funnel"]["score_passed_trades"] == 0
    assert row["entry_score"] < 0
    assert "弱20日且弱60日" in interaction_names
    assert "行业过热且中证500周线强" in interaction_names


def test_entry_score_trade_sample_backtest_cli_writes_outputs(tmp_path: Path, capsys) -> None:
    source_path = tmp_path / "environment_fit.enriched.json"
    source_path.write_text(json.dumps(_environment_fit_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = score_cli.main(
        [
            "--environment-fit",
            str(source_path),
            "--year",
            "2024",
            "--min-entry-score",
            "4",
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["schema"] == ENTRY_SCORE_TRADE_SAMPLE_BACKTEST_SCHEMA
    assert stdout["funnel"]["score_passed_trades"] == 2
    assert (tmp_path / "out" / "entry_score_trade_sample_backtest.json").exists()
    assert (tmp_path / "out" / "entry_score_trade_sample_backtest.zh.md").exists()


def test_write_entry_score_trade_sample_backtest_returns_payload_with_artifacts(tmp_path: Path) -> None:
    report = build_entry_score_trade_sample_backtest(_environment_fit_payload(), year=2024, min_entry_score=4.0)

    json_path, markdown_path, payload = write_entry_score_trade_sample_backtest(report, output_dir=tmp_path)

    assert json_path.exists()
    assert markdown_path.exists()
    assert payload["artifacts"]["backtest_markdown_zh"].endswith("entry_score_trade_sample_backtest.zh.md")


def _environment_fit_payload() -> dict:
    return {
        "schema": "attbacktrader.environment_fit.v1",
        "run_id": "entry-score-test",
        "trade_contributions": [
            _trade(
                1,
                "2024-01-05",
                0.20,
                {
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
                },
            ),
            _trade(
                2,
                "2024-02-05",
                -0.06,
                {
                    "entry.price_position.ma60_atr_multiple_bucket": "above_ma60_0_1atr",
                    "entry.signal_strength.dif_dea_distance_bucket": "lte_0",
                    "entry.signal_strength.macd_bar_bucket": "gte_0p6pct",
                    "entry.signal_strength.dea_value_bucket": "0_0p1pct",
                    "entry.liquidity.amount_5d_vs_20d_bucket": "lt_0p8x",
                },
            ),
            _trade(
                3,
                "2024-03-05",
                -0.05,
                {
                    "entry.price_position.ma60_atr_multiple_bucket": "above_ma60_gt_2atr",
                    "entry.signal_strength.dif_dea_distance_bucket": "gte_0p6pct",
                    "entry.signal_strength.macd_bar_bucket": "gte_0p6pct",
                    "entry.signal_strength.dea_value_bucket": "gte_0p6pct",
                    "entry.price_position.near_high_60d_bucket": "near_high",
                },
            ),
            _trade(4, "2023-01-05", 0.50, {"entry.price_position.ma60_atr_multiple_bucket": "above_ma60_gt_2atr"}),
        ],
    }


def _trade(trade_index: int, entry_date: str, return_pct: float, environment: dict) -> dict:
    return {
        "trade_index": trade_index,
        "symbol": f"00000{trade_index}.SZ",
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
