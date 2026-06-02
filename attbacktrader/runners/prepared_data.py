"""Prepare Data Snapshots and feature frames for a Run Plan."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from attbacktrader.config import RunPlan, TradableSeriesConfig
from attbacktrader.data import (
    DailyBar,
    IndexBar,
    MarketBar,
    ShenwanIndustryClassification,
    StockIndustryMembership,
    TradabilityStatus,
)
from attbacktrader.data.providers import RunDataProvider
from attbacktrader.data.snapshots import (
    index_bars_snapshot_path,
    industry_index_bars_snapshot_path,
    read_daily_bars_parquet,
    read_index_bars_parquet,
    read_shenwan_classifications_parquet,
    read_stock_industry_memberships_parquet,
    read_tradability_statuses_parquet,
    shenwan_classification_snapshot_path,
    stock_industry_membership_snapshot_path,
    tradable_bars_snapshot_path,
    tradability_status_snapshot_path,
    write_daily_bars_parquet,
    write_index_bars_parquet,
    write_shenwan_classifications_parquet,
    write_stock_industry_memberships_parquet,
    write_tradability_statuses_parquet,
)
from attbacktrader.features import (
    IndicatorFrame,
    IndicatorSnapshot,
    build_indicator_snapshots,
    indicator_frame_from_snapshots,
    indicator_snapshot_path,
    read_indicator_snapshots_parquet,
    write_indicator_snapshots_parquet,
)


@dataclass(frozen=True)
class PreparedSymbolData:
    symbol: str
    asset_type: str
    adjustment: str
    bars: tuple[DailyBar, ...]
    indicator_snapshots: tuple[IndicatorSnapshot, ...]
    indicator_frame: IndicatorFrame
    snapshot_path: Path
    indicator_snapshot_path: Path
    tradability_statuses: tuple[TradabilityStatus, ...] = ()
    tradability_snapshot_path: Path | None = None


@dataclass(frozen=True)
class PreparedIndexData:
    symbol: str
    bars: tuple[IndexBar, ...]
    snapshot_path: Path


@dataclass(frozen=True)
class IndexSeriesResult:
    symbol: str
    bar_count: int
    snapshot_path: Path


@dataclass(frozen=True)
class IndustryClassificationResult:
    source: str
    classification_count: int
    snapshot_path: Path


@dataclass(frozen=True)
class IndustryMembershipResult:
    symbol: str
    membership_count: int
    snapshot_path: Path


@dataclass(frozen=True)
class PreparedRunData:
    tradable_series: tuple[TradableSeriesConfig, ...]
    symbol_data_by_symbol: Mapping[str, PreparedSymbolData]
    index_data_by_symbol: Mapping[str, PreparedIndexData]
    industry_index_data_by_symbol: Mapping[str, PreparedIndexData]
    industry_classification_result: IndustryClassificationResult | None
    industry_membership_results: tuple[IndustryMembershipResult, ...]
    memberships_by_symbol: Mapping[str, tuple[StockIndustryMembership, ...]]

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(series.symbol for series in self.tradable_series)

    @property
    def adjustment_label(self) -> str:
        adjustments = {series.price_adjustment or "none" for series in self.tradable_series}
        if len(adjustments) == 1:
            return next(iter(adjustments))
        return "mixed"

    @property
    def bars_by_symbol(self) -> dict[str, tuple[DailyBar, ...]]:
        return {
            symbol: self.symbol_data_by_symbol[symbol].bars
            for symbol in self.symbols
        }

    @property
    def indicators_by_symbol(self) -> dict[str, IndicatorFrame]:
        return {
            symbol: self.symbol_data_by_symbol[symbol].indicator_frame
            for symbol in self.symbols
        }

    @property
    def tradability_by_symbol(self) -> dict[str, tuple[TradabilityStatus, ...]]:
        return {
            symbol: self.symbol_data_by_symbol[symbol].tradability_statuses
            for symbol in self.symbols
            if self.symbol_data_by_symbol[symbol].tradability_statuses
        }

    def benchmark_bars_by_symbol(self, run_plan: RunPlan) -> dict[str, tuple[IndexBar, ...]]:
        return {
            symbol: self.index_data_by_symbol[symbol].bars
            for symbol in run_plan.data.benchmark_series.indexes
            if symbol in self.index_data_by_symbol
        }

    def industry_index_bars_by_symbol(self, run_plan: RunPlan) -> dict[str, tuple[IndexBar, ...]]:
        return {
            symbol: self.industry_index_data_by_symbol[symbol].bars
            for symbol in run_plan.data.industry_series.indexes
            if symbol in self.industry_index_data_by_symbol
        }

    def benchmark_results(self, run_plan: RunPlan) -> tuple[IndexSeriesResult, ...]:
        return tuple(
            _index_series_result(self.index_data_by_symbol[symbol])
            for symbol in run_plan.data.benchmark_series.indexes
            if symbol in self.index_data_by_symbol
        )

    def decision_series_results(self, run_plan: RunPlan) -> tuple[IndexSeriesResult, ...]:
        return tuple(
            _index_series_result(self.index_data_by_symbol[symbol])
            for symbol in run_plan.data.decision_series.indexes
            if symbol in self.index_data_by_symbol
        )

    def industry_index_results(self, run_plan: RunPlan) -> tuple[IndexSeriesResult, ...]:
        return tuple(
            _index_series_result(self.industry_index_data_by_symbol[symbol])
            for symbol in run_plan.data.industry_series.indexes
            if symbol in self.industry_index_data_by_symbol
        )


def prepare_run_data(
    run_plan: RunPlan,
    *,
    provider: RunDataProvider | None = None,
) -> PreparedRunData:
    tradable_series = run_plan.data.resolved_tradable_series
    prepared_symbols = tuple(
        _prepare_symbol_data(run_plan, series=series, provider=provider)
        for series in tradable_series
    )
    prepared_by_symbol = {prepared.symbol: prepared for prepared in prepared_symbols}
    prepared_indexes_by_symbol = _prepare_index_data_by_symbol(run_plan, provider=provider)
    prepared_industry_indexes_by_symbol = _prepare_industry_index_data_by_symbol(run_plan, provider=provider)
    industry_classification_result, industry_membership_results, memberships_by_symbol = _prepare_industry_data(
        run_plan,
        tradable_series=tradable_series,
        provider=provider,
    )

    return PreparedRunData(
        tradable_series=tradable_series,
        symbol_data_by_symbol=prepared_by_symbol,
        index_data_by_symbol=prepared_indexes_by_symbol,
        industry_index_data_by_symbol=prepared_industry_indexes_by_symbol,
        industry_classification_result=industry_classification_result,
        industry_membership_results=industry_membership_results,
        memberships_by_symbol=memberships_by_symbol,
    )


def _prepare_symbol_data(
    run_plan: RunPlan,
    *,
    series: TradableSeriesConfig,
    provider: RunDataProvider | None,
) -> PreparedSymbolData:
    snapshot_path = tradable_bars_snapshot_path(
        run_plan.data.snapshot_root,
        symbol=series.symbol,
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
        asset_type=series.asset_type,
        adjustment=series.price_adjustment or "none",
    )
    indicator_path = indicator_snapshot_path(
        run_plan.data.snapshot_root,
        symbol=series.symbol,
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
        adjustment=series.price_adjustment or "none",
        asset_type=series.asset_type,
    )
    tradability_path = None
    if _needs_tradability_status(run_plan, series):
        tradability_path = tradability_status_snapshot_path(
            run_plan.data.snapshot_root,
            symbol=series.symbol,
            start_date=run_plan.run.from_date,
            end_date=run_plan.run.to_date,
            asset_type=series.asset_type,
        )

    bars = _load_or_fetch_bars(run_plan, series=series, path=snapshot_path, provider=provider)
    indicator_snapshots = _load_or_build_indicators(run_plan, bars=bars, path=indicator_path)
    indicator_frame = indicator_frame_from_snapshots(indicator_snapshots)
    tradability_statuses = ()
    if tradability_path is not None:
        tradability_statuses = _load_or_fetch_tradability_statuses(
            run_plan,
            symbol=series.symbol,
            path=tradability_path,
            provider=provider,
        )

    return PreparedSymbolData(
        symbol=series.symbol,
        asset_type=series.asset_type,
        adjustment=series.price_adjustment or "none",
        bars=bars,
        indicator_snapshots=indicator_snapshots,
        indicator_frame=indicator_frame,
        snapshot_path=snapshot_path,
        indicator_snapshot_path=indicator_path,
        tradability_statuses=tradability_statuses,
        tradability_snapshot_path=tradability_path,
    )


def _load_or_fetch_bars(
    run_plan: RunPlan,
    *,
    series: TradableSeriesConfig,
    path: Path,
    provider: RunDataProvider | None,
) -> tuple[DailyBar, ...]:
    if not run_plan.data.refresh_snapshots and path.exists():
        return read_daily_bars_parquet(path)

    if provider is None:
        raise ValueError("provider is required when snapshots must be refreshed or created")

    bars = _fetch_tradable_bars(run_plan, series=series, provider=provider)
    if not bars:
        raise ValueError(f"no daily bars returned for {series.symbol}")

    write_daily_bars_parquet(bars, path)
    return bars


def _fetch_tradable_bars(
    run_plan: RunPlan,
    *,
    series: TradableSeriesConfig,
    provider: RunDataProvider,
) -> tuple[DailyBar, ...]:
    if series.asset_type == "stock":
        return provider.fetch_daily_bars(
            symbol=series.symbol,
            start_date=run_plan.run.from_date,
            end_date=run_plan.run.to_date,
            adjustment=series.price_adjustment or run_plan.data.price_adjustment,
        )

    if series.asset_type == "index":
        index_bars = provider.fetch_index_daily_bars(
            symbol=series.symbol,
            start_date=run_plan.run.from_date,
            end_date=run_plan.run.to_date,
        )
        return _index_bars_to_market_bars(index_bars)

    if series.asset_type == "industry_index":
        index_bars = provider.fetch_industry_index_daily_bars(
            symbol=series.symbol,
            start_date=run_plan.run.from_date,
            end_date=run_plan.run.to_date,
            source=run_plan.data.industry_series.source,
        )
        return _index_bars_to_market_bars(index_bars)

    raise ValueError(f"unsupported tradable asset_type: {series.asset_type}")


def _index_bars_to_market_bars(index_bars: tuple[IndexBar, ...]) -> tuple[DailyBar, ...]:
    return tuple(
        MarketBar(
            symbol=bar.symbol,
            trade_date=bar.trade_date,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )
        for bar in index_bars
    )


def _load_or_build_indicators(
    run_plan: RunPlan,
    *,
    bars: tuple[DailyBar, ...],
    path: Path,
) -> tuple[IndicatorSnapshot, ...]:
    if not run_plan.data.refresh_snapshots and path.exists():
        return read_indicator_snapshots_parquet(path)

    snapshots = build_indicator_snapshots(bars)
    write_indicator_snapshots_parquet(snapshots, path)
    return snapshots


def _needs_tradability_status(run_plan: RunPlan, series: TradableSeriesConfig) -> bool:
    ashare = run_plan.constraints.ashare
    return (
        ashare.enabled
        and series.asset_type == "stock"
        and (ashare.suspension or ashare.limit_up_down)
    )


def _load_or_fetch_tradability_statuses(
    run_plan: RunPlan,
    *,
    symbol: str,
    path: Path,
    provider: RunDataProvider | None,
) -> tuple[TradabilityStatus, ...]:
    if not run_plan.data.refresh_snapshots and path.exists():
        return read_tradability_statuses_parquet(path)

    if provider is None:
        raise ValueError("provider is required when tradability snapshots must be refreshed or created")

    statuses = provider.fetch_tradability_statuses(
        symbol=symbol,
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
    )
    write_tradability_statuses_parquet(statuses, path)
    return statuses


def _prepare_index_data_by_symbol(
    run_plan: RunPlan,
    *,
    provider: RunDataProvider | None,
) -> dict[str, PreparedIndexData]:
    index_symbols = tuple(
        dict.fromkeys(
            (
                *run_plan.data.decision_series.indexes,
                *run_plan.data.benchmark_series.indexes,
            )
        )
    )

    return {
        symbol: _prepare_index_data(run_plan, symbol=symbol, provider=provider)
        for symbol in index_symbols
    }


def _prepare_index_data(
    run_plan: RunPlan,
    *,
    symbol: str,
    provider: RunDataProvider | None,
) -> PreparedIndexData:
    snapshot_path = index_bars_snapshot_path(
        run_plan.data.snapshot_root,
        symbol=symbol,
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
    )
    bars = _load_or_fetch_index_bars(run_plan, symbol=symbol, path=snapshot_path, provider=provider)
    return PreparedIndexData(symbol=symbol, bars=bars, snapshot_path=snapshot_path)


def _load_or_fetch_index_bars(
    run_plan: RunPlan,
    *,
    symbol: str,
    path: Path,
    provider: RunDataProvider | None,
) -> tuple[IndexBar, ...]:
    if not run_plan.data.refresh_snapshots and path.exists():
        return read_index_bars_parquet(path)

    if provider is None:
        raise ValueError("provider is required when index snapshots must be refreshed or created")

    bars = provider.fetch_index_daily_bars(
        symbol=symbol,
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
    )

    write_index_bars_parquet(bars, path)
    return bars


def _prepare_industry_index_data_by_symbol(
    run_plan: RunPlan,
    *,
    provider: RunDataProvider | None,
) -> dict[str, PreparedIndexData]:
    return {
        symbol: _prepare_industry_index_data(run_plan, symbol=symbol, provider=provider)
        for symbol in run_plan.data.industry_series.indexes
    }


def _prepare_industry_index_data(
    run_plan: RunPlan,
    *,
    symbol: str,
    provider: RunDataProvider | None,
) -> PreparedIndexData:
    source = run_plan.data.industry_series.source
    snapshot_path = industry_index_bars_snapshot_path(
        run_plan.data.snapshot_root,
        symbol=symbol,
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
        source=source,
    )
    bars = _load_or_fetch_industry_index_bars(
        run_plan,
        symbol=symbol,
        source=source,
        path=snapshot_path,
        provider=provider,
    )
    return PreparedIndexData(symbol=symbol, bars=bars, snapshot_path=snapshot_path)


def _load_or_fetch_industry_index_bars(
    run_plan: RunPlan,
    *,
    symbol: str,
    source: str,
    path: Path,
    provider: RunDataProvider | None,
) -> tuple[IndexBar, ...]:
    if not run_plan.data.refresh_snapshots and path.exists():
        return read_index_bars_parquet(path)

    if provider is None:
        raise ValueError("provider is required when industry index snapshots must be refreshed or created")

    bars = provider.fetch_industry_index_daily_bars(
        symbol=symbol,
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
        source=source,
    )
    write_index_bars_parquet(bars, path)
    return bars


def _prepare_industry_data(
    run_plan: RunPlan,
    *,
    tradable_series: tuple[TradableSeriesConfig, ...],
    provider: RunDataProvider | None,
) -> tuple[IndustryClassificationResult | None, tuple[IndustryMembershipResult, ...], dict[str, tuple[StockIndustryMembership, ...]]]:
    if not run_plan.analysis.industry_attribution.enabled:
        return None, (), {}

    stock_series = tuple(series for series in tradable_series if series.asset_type == "stock")
    if not stock_series:
        return None, (), {}

    source = run_plan.analysis.industry_attribution.source
    classification_path = shenwan_classification_snapshot_path(run_plan.data.snapshot_root, source=source)
    classifications = _load_or_fetch_shenwan_classifications(
        run_plan,
        source=source,
        path=classification_path,
        provider=provider,
    )
    classification_result = IndustryClassificationResult(
        source=source,
        classification_count=len(classifications),
        snapshot_path=classification_path,
    )

    memberships_by_symbol: dict[str, tuple[StockIndustryMembership, ...]] = {}
    membership_results: list[IndustryMembershipResult] = []
    for series in stock_series:
        symbol = series.symbol
        membership_path = stock_industry_membership_snapshot_path(
            run_plan.data.snapshot_root,
            symbol=symbol,
            source=source,
        )
        memberships = _load_or_fetch_stock_industry_memberships(
            run_plan,
            symbol=symbol,
            source=source,
            path=membership_path,
            provider=provider,
        )
        memberships_by_symbol[symbol] = memberships
        membership_results.append(
            IndustryMembershipResult(
                symbol=symbol,
                membership_count=len(memberships),
                snapshot_path=membership_path,
            )
        )

    return classification_result, tuple(membership_results), memberships_by_symbol


def _load_or_fetch_shenwan_classifications(
    run_plan: RunPlan,
    *,
    source: str,
    path: Path,
    provider: RunDataProvider | None,
) -> tuple[ShenwanIndustryClassification, ...]:
    if not run_plan.data.refresh_snapshots and path.exists():
        return read_shenwan_classifications_parquet(path)

    if provider is None:
        raise ValueError("provider is required when industry snapshots must be refreshed or created")

    classifications = provider.fetch_shenwan_industry_classifications(source=source)
    if not classifications:
        raise ValueError(f"no Shenwan industry classifications returned for {source}")

    write_shenwan_classifications_parquet(classifications, path)
    return classifications


def _load_or_fetch_stock_industry_memberships(
    run_plan: RunPlan,
    *,
    symbol: str,
    source: str,
    path: Path,
    provider: RunDataProvider | None,
) -> tuple[StockIndustryMembership, ...]:
    if not run_plan.data.refresh_snapshots and path.exists():
        return read_stock_industry_memberships_parquet(path)

    if provider is None:
        raise ValueError("provider is required when industry snapshots must be refreshed or created")

    memberships = provider.fetch_stock_industry_memberships(symbol=symbol, source=source)
    if not memberships:
        raise ValueError(f"no Shenwan industry memberships returned for {symbol}")

    write_stock_industry_memberships_parquet(memberships, path)
    return memberships


def _index_series_result(prepared: PreparedIndexData) -> IndexSeriesResult:
    return IndexSeriesResult(
        symbol=prepared.symbol,
        bar_count=len(prepared.bars),
        snapshot_path=prepared.snapshot_path,
    )
