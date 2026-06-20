"""Benchmark comparison calculations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from attbacktrader.data import IndexBar
from attbacktrader.reports import BenchmarkComparisonSummary


def compare_strategy_to_benchmarks(
    *,
    strategy_return: float,
    index_bars_by_symbol: Mapping[str, Sequence[IndexBar]],
) -> tuple[BenchmarkComparisonSummary, ...]:
    comparisons: list[BenchmarkComparisonSummary] = []

    for symbol in sorted(index_bars_by_symbol):
        bars = tuple(sorted(index_bars_by_symbol[symbol], key=lambda bar: bar.trade_date))
        if not bars:
            continue

        benchmark_return = bars[-1].close / bars[0].close - 1.0
        comparisons.append(
            BenchmarkComparisonSummary(
                benchmark_symbol=symbol,
                strategy_return=strategy_return,
                benchmark_return=benchmark_return,
                excess_return=strategy_return - benchmark_return,
            )
        )

    return tuple(comparisons)
