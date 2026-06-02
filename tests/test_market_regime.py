from datetime import date, timedelta

import pytest

from attbacktrader.analysis import classify_market_regime
from attbacktrader.data import IndexBar


def test_classify_market_regime_hot_with_positive_benchmark_and_industry_diffusion() -> None:
    benchmark = _index_series("000001.SH", [100.0, 102.0, 106.0, 108.0])
    industry_a = _index_series("801780.SI", [100.0, 101.0, 102.0, 103.0])
    industry_b = _index_series("801120.SI", [100.0, 100.5, 101.0, 102.0])

    regime = classify_market_regime(
        benchmark_bars_by_symbol={"000001.SH": benchmark},
        industry_index_bars_by_symbol={"801780.SI": industry_a, "801120.SI": industry_b},
        timeframes=("D", "W", "M"),
    )

    assert regime.primary_label == "hot"
    assert [window.timeframe for window in regime.windows] == ["D", "W", "M"]
    assert regime.windows[0].benchmark_count == 1
    assert regime.windows[0].benchmark_return == pytest.approx(0.08)
    assert regime.windows[0].industry_positive_ratio == 1.0


def test_classify_market_regime_cold_with_negative_benchmark() -> None:
    benchmark = _index_series("000001.SH", [100.0, 97.0, 93.0, 90.0])
    industry = _index_series("801780.SI", [100.0, 99.0, 98.0, 97.0])

    regime = classify_market_regime(
        benchmark_bars_by_symbol={"000001.SH": benchmark},
        industry_index_bars_by_symbol={"801780.SI": industry},
        timeframes=("D",),
    )

    assert regime.primary_label == "cold"
    assert regime.windows[0].benchmark_return == pytest.approx(-0.10)
    assert regime.windows[0].industry_positive_ratio == 0.0


def test_classify_market_regime_requires_benchmark_evidence() -> None:
    regime = classify_market_regime(
        benchmark_bars_by_symbol={},
        industry_index_bars_by_symbol={},
        timeframes=("D",),
    )

    assert regime.primary_label == "insufficient_evidence"
    assert regime.windows[0].benchmark_count == 0
    assert regime.windows[0].industry_count == 0


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
