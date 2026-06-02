"""Market-regime and water-temperature analysis."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from statistics import fmean, pstdev

from attbacktrader.data import IndexBar, resample_daily_bars
from attbacktrader.reports import MarketRegimeSummary, MarketRegimeWindowSummary


def classify_market_regime(
    *,
    benchmark_bars_by_symbol: Mapping[str, Sequence[IndexBar]],
    industry_index_bars_by_symbol: Mapping[str, Sequence[IndexBar]] = {},
    timeframes: Sequence[str] = ("D", "W", "M"),
) -> MarketRegimeSummary:
    windows = tuple(
        _classify_timeframe(
            timeframe=timeframe,
            benchmark_bars_by_symbol=benchmark_bars_by_symbol,
            industry_index_bars_by_symbol=industry_index_bars_by_symbol,
        )
        for timeframe in timeframes
    )

    primary = next((window for window in windows if window.timeframe == "D"), windows[0])
    return MarketRegimeSummary(primary_label=primary.label, windows=windows)


def _classify_timeframe(
    *,
    timeframe: str,
    benchmark_bars_by_symbol: Mapping[str, Sequence[IndexBar]],
    industry_index_bars_by_symbol: Mapping[str, Sequence[IndexBar]],
) -> MarketRegimeWindowSummary:
    benchmark_series = [
        _resample_if_needed(bars, timeframe)
        for _, bars in sorted(benchmark_bars_by_symbol.items())
    ]
    benchmark_metrics = [_series_metrics(bars) for bars in benchmark_series if len(bars) >= 2]

    benchmark_return = _average([metrics["return"] for metrics in benchmark_metrics])
    benchmark_max_drawdown = _average([metrics["max_drawdown"] for metrics in benchmark_metrics])
    benchmark_volatility = _average([metrics["volatility"] for metrics in benchmark_metrics if metrics["volatility"] is not None])

    industry_series = [
        _resample_if_needed(bars, timeframe)
        for _, bars in sorted(industry_index_bars_by_symbol.items())
    ]
    industry_returns = [
        _series_return(bars)
        for bars in industry_series
        if len(bars) >= 2
    ]
    industry_positive_ratio = None
    if industry_returns:
        industry_positive_ratio = sum(1 for value in industry_returns if value > 0) / len(industry_returns)

    return MarketRegimeWindowSummary(
        timeframe=timeframe,
        label=_label_for_metrics(
            benchmark_return=benchmark_return,
            benchmark_max_drawdown=benchmark_max_drawdown,
            industry_positive_ratio=industry_positive_ratio,
        ),
        benchmark_count=len(benchmark_metrics),
        benchmark_return=benchmark_return,
        benchmark_max_drawdown=benchmark_max_drawdown,
        benchmark_volatility=benchmark_volatility,
        industry_count=len(industry_returns),
        industry_positive_ratio=industry_positive_ratio,
    )


def _resample_if_needed(bars: Sequence[IndexBar], timeframe: str) -> tuple[IndexBar, ...]:
    ordered = tuple(sorted(bars, key=lambda bar: bar.trade_date))
    if timeframe == "D":
        return ordered
    if timeframe in {"W", "M"}:
        return resample_daily_bars(ordered, frequency=timeframe)
    raise ValueError("market regime timeframe must be D, W, or M")


def _series_metrics(bars: Sequence[IndexBar]) -> dict[str, float | None]:
    closes = [bar.close for bar in bars]
    returns = [current / previous - 1.0 for previous, current in zip(closes, closes[1:])]
    volatility = pstdev(returns) if len(returns) >= 2 else None
    return {
        "return": _series_return(bars),
        "max_drawdown": _max_drawdown(closes),
        "volatility": volatility,
    }


def _series_return(bars: Sequence[IndexBar]) -> float:
    ordered = tuple(sorted(bars, key=lambda bar: bar.trade_date))
    return ordered[-1].close / ordered[0].close - 1.0


def _max_drawdown(values: Sequence[float]) -> float:
    peak = values[0]
    max_drawdown = 0.0

    for value in values:
        peak = max(peak, value)
        drawdown = (peak - value) / peak
        max_drawdown = max(max_drawdown, drawdown)

    return max_drawdown


def _average(values: Sequence[float | None]) -> float | None:
    clean_values = [value for value in values if value is not None]
    if not clean_values:
        return None
    return fmean(clean_values)


def _label_for_metrics(
    *,
    benchmark_return: float | None,
    benchmark_max_drawdown: float | None,
    industry_positive_ratio: float | None,
) -> str:
    if benchmark_return is None:
        return "insufficient_evidence"

    if (
        benchmark_return >= 0.05
        and (benchmark_max_drawdown is None or benchmark_max_drawdown <= 0.08)
        and (industry_positive_ratio is None or industry_positive_ratio >= 0.6)
    ):
        return "hot"

    if (
        benchmark_return <= -0.05
        or (benchmark_max_drawdown is not None and benchmark_max_drawdown >= 0.12)
        or (industry_positive_ratio is not None and industry_positive_ratio < 0.35)
    ):
        return "cold"

    if benchmark_return >= 0.0 and (industry_positive_ratio is None or industry_positive_ratio >= 0.5):
        return "warm"

    return "neutral"
