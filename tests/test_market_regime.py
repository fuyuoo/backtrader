from datetime import date, timedelta

from attbacktrader.analysis import classify_market_regime, summarize_market_regime_inputs
from attbacktrader.data import IndexBar


def test_summarize_market_regime_inputs_keeps_configured_values_without_calculation() -> None:
    summary = summarize_market_regime_inputs(
        benchmark_symbols=("000001.SH", "000300.SH"),
        industry_index_symbols=("801780.SI", "801120.SI"),
        timeframes=("D", "W", "M"),
    )

    assert summary.primary_label == "input_only"
    assert summary.windows == ()
    assert summary.benchmark_symbols == ("000001.SH", "000300.SH")
    assert summary.industry_index_symbols == ("801780.SI", "801120.SI")
    assert summary.timeframes == ("D", "W", "M")


def test_classify_market_regime_keeps_legacy_api_as_input_summary() -> None:
    benchmark = _index_series("000001.SH", [100.0, 102.0, 106.0, 108.0])
    industry_a = _index_series("801780.SI", [100.0, 101.0, 102.0, 103.0])
    industry_b = _index_series("801120.SI", [100.0, 100.5, 101.0, 102.0])

    regime = classify_market_regime(
        benchmark_bars_by_symbol={"000001.SH": benchmark},
        industry_index_bars_by_symbol={"801780.SI": industry_a, "801120.SI": industry_b},
        timeframes=("D", "W", "M"),
    )

    assert regime.primary_label == "input_only"
    assert regime.windows == ()
    assert regime.benchmark_symbols == ("000001.SH",)
    assert regime.industry_index_symbols == ("801780.SI", "801120.SI")
    assert regime.timeframes == ("D", "W", "M")


def _index_series(symbol: str, closes: list[float]) -> tuple[IndexBar, ...]:
    start = date(2024, 1, 2)
    return tuple(
        IndexBar(
            symbol=symbol,
            trade_date=start + timedelta(days=index),
            open=close,
            high=close + 1.0,
            low=close - 1.0,
            close=close,
            volume=1000.0,
            amount=2000.0,
        )
        for index, close in enumerate(closes)
    )
