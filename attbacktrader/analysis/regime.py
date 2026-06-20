"""Market-regime input summaries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from attbacktrader.data import IndexBar
from attbacktrader.reports import MarketRegimeSummary


def summarize_market_regime_inputs(
    *,
    benchmark_symbols: Sequence[str],
    industry_index_symbols: Sequence[str] = (),
    timeframes: Sequence[str] = ("D", "W", "M"),
) -> MarketRegimeSummary:
    """Return configured market-regime inputs without deriving a temperature label."""

    return MarketRegimeSummary(
        primary_label="input_only",
        windows=(),
        benchmark_symbols=tuple(benchmark_symbols),
        industry_index_symbols=tuple(industry_index_symbols),
        timeframes=tuple(timeframes),
    )


def classify_market_regime(
    *,
    benchmark_bars_by_symbol: Mapping[str, Sequence[IndexBar]] | None,
    industry_index_bars_by_symbol: Mapping[str, Sequence[IndexBar]] | None = None,
    timeframes: Sequence[str] = ("D", "W", "M"),
) -> MarketRegimeSummary:
    benchmark_bars_by_symbol = benchmark_bars_by_symbol or {}
    industry_index_bars_by_symbol = industry_index_bars_by_symbol or {}
    return summarize_market_regime_inputs(
        benchmark_symbols=tuple(benchmark_bars_by_symbol),
        industry_index_symbols=tuple(industry_index_bars_by_symbol),
        timeframes=timeframes,
    )
