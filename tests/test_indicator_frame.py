from datetime import date
from pathlib import Path

import pytest

from attbacktrader.data import DailyBar
from attbacktrader.data.snapshots import read_daily_bars_csv
from attbacktrader.features import build_indicator_frame
from attbacktrader.strategies.templates import TrendTemplateV1


def test_indicator_frame_builds_reusable_kdj_series() -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))

    indicators = build_indicator_frame(bars)

    assert indicators.symbol == "000001.SZ"
    assert indicators.kdj_at(date(2024, 1, 3)).j == pytest.approx(11.1111111111)

    result = TrendTemplateV1().run_single_symbol(bars, indicators=indicators)
    assert len(result.closed_trades) == 2


def test_indicator_frame_rejects_multi_symbol_bars() -> None:
    bars = [
        DailyBar("000001.SZ", date(2024, 1, 2), 10.0, 10.0, 10.0, 10.0),
        DailyBar("600000.SH", date(2024, 1, 2), 10.0, 10.0, 10.0, 10.0),
    ]

    with pytest.raises(ValueError, match="one symbol"):
        build_indicator_frame(bars)


def test_strategy_rejects_indicator_symbol_mismatch() -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    other_bars = [
        DailyBar("600000.SH", bar.trade_date, bar.open, bar.high, bar.low, bar.close, bar.volume)
        for bar in bars
    ]
    indicators = build_indicator_frame(other_bars)

    with pytest.raises(ValueError, match="indicator frame symbol"):
        TrendTemplateV1().run_single_symbol(bars, indicators=indicators)
