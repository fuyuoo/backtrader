import json
from pathlib import Path

from attbacktrader.reports import build_attribution_matrix, write_attribution_matrix


def test_attribution_matrix_buckets_entry_add_on_and_post_exit(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "trade_attribution.json",
        {
            "schema": "attbacktrader.trade_attribution.v1",
            "trade_count": 2,
            "attributions": [
                _attribution(
                    trade_index=1,
                    symbol="000001.SZ",
                    outcome="win",
                    return_pct=0.10,
                    exit_reason="BAOMA_MA25_PROFIT_EXIT_TRIGGERED",
                    dea_age=2,
                    symbol_kdj=85.0,
                    market_kdj=70.0,
                    industry_kdj=45.0,
                    weekly_symbol_kdj=62.0,
                    weekly_industry_kdj=33.0,
                    macd_zone="red_bar_wrapping_lines",
                    weekly_macd_zone="red_bar_two_line_escape",
                    industry_macd_zone="red_bar_one_line_escape",
                    weekly_industry_macd_zone="red_bar_wrapping_lines",
                    industry_trend_state="bullish",
                    industry_strength_state="strong_outperform",
                    add_on_dea_age=3,
                    add_on_symbol_kdj=45.0,
                    exit_symbol_kdj=82.0,
                    exit_market_kdj=66.0,
                ),
                _attribution(
                    trade_index=2,
                    symbol="000002.SZ",
                    outcome="loss",
                    return_pct=-0.04,
                    exit_reason="BAOMA_MA60_STOP_TRIGGERED",
                    dea_age=12,
                    symbol_kdj=20.0,
                    market_kdj=8.0,
                    industry_kdj=11.0,
                    weekly_symbol_kdj=None,
                    weekly_industry_kdj=84.0,
                    macd_zone="green_bar_or_zero",
                    weekly_macd_zone=None,
                    industry_macd_zone="green_bar_or_zero",
                    weekly_industry_macd_zone=None,
                    industry_trend_state="not_bullish",
                    industry_strength_state="weak_underperform",
                    add_on_dea_age=None,
                    add_on_symbol_kdj=None,
                    exit_symbol_kdj=10.0,
                    exit_market_kdj=11.0,
                ),
            ],
        },
    )
    _write_json(
        tmp_path / "post_exit_analysis.json",
        {
            "observations": [
                {
                    "symbol": "000001.SZ",
                    "entry_date": "2024-01-02",
                    "exit_date": "2024-01-10",
                    "exit_reason": "BAOMA_MA25_PROFIT_EXIT_TRIGGERED",
                    "max_high_return_pct": 0.06,
                    "primary_window_close_return_pct": 0.01,
                    "sold_too_early": True,
                },
                {
                    "symbol": "000002.SZ",
                    "entry_date": "2024-01-03",
                    "exit_date": "2024-01-11",
                    "exit_reason": "BAOMA_MA60_STOP_TRIGGERED",
                    "max_high_return_pct": 0.01,
                    "primary_window_close_return_pct": -0.01,
                    "sold_too_early": False,
                },
            ]
        },
    )

    report = build_attribution_matrix(tmp_path, min_sample_count=1, top_n=20)
    matrix_by_id = {matrix["matrix_id"]: matrix for matrix in report["matrices"]}

    assert report["schema"] == "attbacktrader.attribution_matrix.v1"
    assert matrix_by_id["entry_dea_symbol_kdj"]["rows"][0]["sample_count"] == 1
    assert any(
        row["dimensions"] == {"dea_age": "0-2", "symbol_kdj_j": ">=80"}
        for row in matrix_by_id["entry_dea_symbol_kdj"]["rows"]
    )
    profit_rows = matrix_by_id["profit_exit_kdj_post_5d"]["rows"]
    assert profit_rows[0]["post_exit_rebound_rate_5pct"] == 1.0
    assert any(
        row["dimensions"] == {"industry_trend_state": "bullish", "market_hs300_kdj_j": "50-80"}
        for row in matrix_by_id["entry_industry_trend_market_kdj"]["rows"]
    )
    assert any(
        row["dimensions"] == {"industry_relative_strength": "strong_outperform", "symbol_kdj_j": ">=80"}
        for row in matrix_by_id["entry_industry_relative_strength"]["rows"]
    )
    assert any(
        row["dimensions"] == {"symbol_kdj_j": ">=80", "symbol_weekly_kdj_j": "50-80"}
        for row in matrix_by_id["entry_symbol_daily_weekly_kdj"]["rows"]
    )
    assert any(
        row["dimensions"] == {"symbol_kdj_j": "13-30", "symbol_weekly_kdj_j": "missing"}
        for row in matrix_by_id["entry_symbol_daily_weekly_kdj"]["rows"]
    )
    assert any(
        row["dimensions"] == {"industry_kdj_j": "30-50", "industry_weekly_kdj_j": "30-50"}
        for row in matrix_by_id["entry_industry_daily_weekly_kdj"]["rows"]
    )
    assert any(
        row["dimensions"] == {"industry_kdj_j": "<13", "industry_weekly_kdj_j": ">=80"}
        for row in matrix_by_id["entry_industry_daily_weekly_kdj"]["rows"]
    )
    assert any(
        row["dimensions"]
        == {
            "symbol_macd_zone": "red_bar_wrapping_lines",
            "symbol_weekly_macd_zone": "red_bar_two_line_escape",
        }
        for row in matrix_by_id["entry_symbol_daily_weekly_macd_zone"]["rows"]
    )
    assert any(
        row["dimensions"] == {"symbol_macd_zone": "green_bar_or_zero", "symbol_weekly_macd_zone": "missing"}
        for row in matrix_by_id["entry_symbol_daily_weekly_macd_zone"]["rows"]
    )
    assert any(
        row["dimensions"]
        == {
            "industry_macd_zone": "red_bar_one_line_escape",
            "industry_weekly_macd_zone": "red_bar_wrapping_lines",
        }
        for row in matrix_by_id["entry_industry_daily_weekly_macd_zone"]["rows"]
    )
    assert any(
        row["dimensions"] == {"industry_macd_zone": "green_bar_or_zero", "industry_weekly_macd_zone": "missing"}
        for row in matrix_by_id["entry_industry_daily_weekly_macd_zone"]["rows"]
    )
    assert any(
        row["dimensions"] == {"industry_relative_strength": "strong_outperform", "dea_age": "3-5"}
        for row in matrix_by_id["add_on_industry_relative_strength"]["rows"]
    )

    json_path, markdown_path = write_attribution_matrix(report)
    assert json_path.exists()
    assert "归因分桶矩阵" in markdown_path.read_text(encoding="utf-8")


def _attribution(
    *,
    trade_index: int,
    symbol: str,
    outcome: str,
    return_pct: float,
    exit_reason: str,
    dea_age: int | None,
    symbol_kdj: float,
    market_kdj: float,
    industry_kdj: float,
    weekly_symbol_kdj: float | None,
    weekly_industry_kdj: float | None,
    macd_zone: str | None,
    weekly_macd_zone: str | None,
    industry_macd_zone: str | None,
    weekly_industry_macd_zone: str | None,
    industry_trend_state: str,
    industry_strength_state: str,
    add_on_dea_age: int | None,
    add_on_symbol_kdj: float | None,
    exit_symbol_kdj: float,
    exit_market_kdj: float,
) -> dict:
    entry_date = f"2024-01-0{trade_index + 1}"
    exit_date = f"2024-01-1{trade_index - 1}"
    add_ons = []
    if add_on_dea_age is not None and add_on_symbol_kdj is not None:
        add_ons.append(
            {
                "timing": "add_on",
                "trade_date": "2024-01-05",
                "factors": [
                    _factor("symbol.macd.dea_waterline_age_trading_days", add_on_dea_age),
                    _factor("symbol.kdj.j", add_on_symbol_kdj),
                    _factor("industry.relative.hs300.strength_state", industry_strength_state),
                ],
            }
        )
    return {
        "trade_index": trade_index,
        "symbol": symbol,
        "outcome": outcome,
        "entry_date": entry_date,
        "exit_date": exit_date,
        "exit_reason": exit_reason,
        "return_pct": return_pct,
        "entry": {
            "timing": "entry",
            "trade_date": entry_date,
            "factors": [
                _factor("symbol.macd.dea_waterline_age_trading_days", dea_age),
                _factor("symbol.kdj.j", symbol_kdj),
                _factor("symbol.kdj.week.j", weekly_symbol_kdj),
                _factor("symbol.macd.energy_zone", macd_zone),
                _factor("symbol.macd.week.energy_zone", weekly_macd_zone),
                _factor("industry.kdj.j", industry_kdj),
                _factor("industry.kdj.week.j", weekly_industry_kdj),
                _factor("industry.macd.energy_zone", industry_macd_zone),
                _factor("industry.macd.week.energy_zone", weekly_industry_macd_zone),
                _factor("market.hs300.kdj.j", market_kdj),
                _factor("industry.ma.trend_state", industry_trend_state),
                _factor("industry.relative.hs300.strength_state", industry_strength_state),
            ],
        },
        "exit": {
            "timing": "exit",
            "trade_date": exit_date,
            "factors": [
                _factor("symbol.kdj.j", exit_symbol_kdj),
                _factor("market.hs300.kdj.j", exit_market_kdj),
            ],
        },
        "add_ons": add_ons,
    }


def _factor(key: str, value) -> dict:
    return {
        "key": key,
        "value": value,
        "value_kind": "value",
        "missing": value is None,
        "source": "test",
    }


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
