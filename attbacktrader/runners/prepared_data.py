"""Prepare Data Snapshots and feature frames for a Run Plan."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping

from attbacktrader.config import RunPlan, TradableSeriesConfig
from attbacktrader.data import (
    DataQualityIssue,
    DailyBar,
    IndexBar,
    MarketBar,
    ShenwanIndustryClassification,
    StockIndustryMembership,
    TradingCalendar,
    TradabilityStatus,
    assess_daily_bar_quality,
    resample_daily_bars,
    trading_calendar_from_bars,
)
from attbacktrader.data.providers import RunDataProvider
from attbacktrader.data.snapshots import (
    DailyBarsSnapshotCandidate,
    SnapshotProvenance,
    discover_tradable_bars_snapshot_paths,
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
    write_merged_daily_bars_parquet,
    write_shenwan_classifications_parquet,
    write_stock_industry_memberships_parquet,
    write_tradability_statuses_parquet,
)
from attbacktrader.features import (
    IndicatorFrame,
    IndicatorRequirement,
    IndicatorSnapshot,
    IndicatorSnapshotCandidate,
    IndicatorSnapshotMetadata,
    IndicatorUpdatePlan,
    build_indicator_update_plans,
    build_indicator_snapshots,
    build_indicator_snapshots_from_state,
    discover_indicator_snapshot_paths,
    indicator_frame_from_snapshots,
    indicator_snapshot_path,
    indicator_states_from_bars,
    read_indicator_snapshot_metadata,
    read_indicator_snapshots_parquet,
    write_indicator_snapshot_metadata,
    write_indicator_snapshots_parquet,
    write_merged_indicator_snapshots_parquet,
)
from attbacktrader.strategies.bindings import required_indicators_for_strategy_config


@dataclass(frozen=True)
class DailyBarsLoadResult:
    bars: tuple[DailyBar, ...]
    provenance: SnapshotProvenance


@dataclass(frozen=True)
class IndicatorSnapshotsLoadResult:
    snapshots: tuple[IndicatorSnapshot, ...]
    provenance: SnapshotProvenance


@dataclass(frozen=True)
class TradabilityLoadResult:
    statuses: tuple[TradabilityStatus, ...]
    provenance: SnapshotProvenance


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
    snapshot_provenance: SnapshotProvenance
    indicator_snapshot_provenance: tuple[SnapshotProvenance, ...]
    data_quality_issues: tuple[DataQualityIssue, ...]
    indicator_snapshot_paths: tuple[Path, ...] = ()
    tradability_statuses: tuple[TradabilityStatus, ...] = ()
    tradability_snapshot_path: Path | None = None
    tradability_snapshot_provenance: SnapshotProvenance | None = None


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
    trading_calendar: TradingCalendar | None = None

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

    def risk_group_by_symbol(self, *, level: int = 1) -> dict[str, str]:
        if level not in {1, 2, 3}:
            raise ValueError("risk group level must be 1, 2, or 3")

        field_name = f"level{level}_code"
        groups: dict[str, str] = {}
        for symbol, memberships in self.memberships_by_symbol.items():
            membership = _latest_membership(memberships)
            if membership is not None:
                groups[symbol] = str(getattr(membership, field_name))
        return groups


def prepare_run_data(
    run_plan: RunPlan,
    *,
    provider: RunDataProvider | None = None,
) -> PreparedRunData:
    tradable_series = run_plan.data.resolved_tradable_series
    indicator_requirements = tuple(sorted(required_indicators_for_strategy_config(run_plan.strategy)))
    prepared_indexes_by_symbol = _prepare_index_data_by_symbol(run_plan, provider=provider)
    trading_calendar = _trading_calendar_for_run(run_plan, prepared_indexes_by_symbol)
    prepared_symbols = tuple(
        _prepare_symbol_data(
            run_plan,
            series=series,
            provider=provider,
            indicator_requirements=indicator_requirements,
            trading_calendar=trading_calendar,
        )
        for series in tradable_series
    )
    prepared_by_symbol = {prepared.symbol: prepared for prepared in prepared_symbols}
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
        trading_calendar=trading_calendar,
    )


def _trading_calendar_for_run(
    run_plan: RunPlan,
    prepared_indexes_by_symbol: Mapping[str, PreparedIndexData],
) -> TradingCalendar | None:
    calendar_symbols = (
        *run_plan.data.decision_series.indexes,
        *run_plan.data.benchmark_series.indexes,
    )
    for symbol in calendar_symbols:
        prepared = prepared_indexes_by_symbol.get(symbol)
        if prepared is None:
            continue
        calendar = trading_calendar_from_bars(symbol, prepared.bars)
        if calendar is not None:
            return calendar
    return None


def _latest_membership(
    memberships: tuple[StockIndustryMembership, ...],
) -> StockIndustryMembership | None:
    if not memberships:
        return None
    return sorted(memberships, key=lambda membership: (membership.in_date, membership.symbol))[-1]


def _prepare_symbol_data(
    run_plan: RunPlan,
    *,
    series: TradableSeriesConfig,
    provider: RunDataProvider | None,
    indicator_requirements: tuple[IndicatorRequirement, ...],
    trading_calendar: TradingCalendar | None,
) -> PreparedSymbolData:
    snapshot_path = tradable_bars_snapshot_path(
        run_plan.data.snapshot_root,
        symbol=series.symbol,
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
        asset_type=series.asset_type,
        adjustment=series.price_adjustment or "none",
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

    bars_load_result = _load_or_fetch_bars(run_plan, series=series, path=snapshot_path, provider=provider)
    bars = bars_load_result.bars
    data_quality_issues = assess_daily_bar_quality(
        bars,
        symbol=series.symbol,
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
        trading_calendar=trading_calendar,
    )
    indicator_snapshots, indicator_paths, indicator_provenance = _load_or_build_required_indicators(
        run_plan,
        series=series,
        bars=bars,
        indicator_requirements=indicator_requirements,
    )
    indicator_frame = indicator_frame_from_snapshots(indicator_snapshots)
    tradability_statuses = ()
    tradability_provenance = None
    if tradability_path is not None:
        tradability_load_result = _load_or_fetch_tradability_statuses(
            run_plan,
            symbol=series.symbol,
            path=tradability_path,
            provider=provider,
        )
        tradability_statuses = tradability_load_result.statuses
        tradability_provenance = tradability_load_result.provenance

    return PreparedSymbolData(
        symbol=series.symbol,
        asset_type=series.asset_type,
        adjustment=series.price_adjustment or "none",
        bars=bars,
        indicator_snapshots=indicator_snapshots,
        indicator_frame=indicator_frame,
        snapshot_path=snapshot_path,
        indicator_snapshot_path=indicator_paths[0],
        snapshot_provenance=bars_load_result.provenance,
        indicator_snapshot_provenance=indicator_provenance,
        data_quality_issues=data_quality_issues,
        indicator_snapshot_paths=indicator_paths,
        tradability_statuses=tradability_statuses,
        tradability_snapshot_path=tradability_path,
        tradability_snapshot_provenance=tradability_provenance,
    )


def _load_or_fetch_bars(
    run_plan: RunPlan,
    *,
    series: TradableSeriesConfig,
    path: Path,
    provider: RunDataProvider | None,
) -> DailyBarsLoadResult:
    if not run_plan.data.refresh_snapshots:
        existing_bars, candidates = _load_discovered_tradable_bars(
            run_plan,
            series=series,
        )
        if _bars_cover_date_range(
            existing_bars,
            start_date=run_plan.run.from_date,
            end_date=run_plan.run.to_date,
        ):
            bars = _bars_for_date_range(
                existing_bars,
                start_date=run_plan.run.from_date,
                end_date=run_plan.run.to_date,
            )
            if not path.exists():
                write_daily_bars_parquet(bars, path)
            action = "exact_reused" if _has_exact_bar_candidate(candidates, path) else "range_reused"
            return DailyBarsLoadResult(
                bars=bars,
                provenance=_snapshot_provenance(
                    snapshot_type="tradable_bars",
                    action=action,
                    path=path,
                    source_paths=_candidate_paths(candidates),
                    bars=bars,
                ),
            )

        if provider is None:
            raise ValueError("provider is required when snapshots must be refreshed or created")

        missing_bars, missing_ranges = _fetch_missing_tradable_bars(
            run_plan,
            series=series,
            provider=provider,
            existing_bars=existing_bars,
        )
        if not existing_bars and not missing_bars:
            raise ValueError(f"no daily bars returned for {series.symbol}")

        write_merged_daily_bars_parquet(
            existing_bars,
            missing_bars,
            path,
            start_date=run_plan.run.from_date,
            end_date=run_plan.run.to_date,
        )
        bars = _bars_for_date_range(
            read_daily_bars_parquet(path),
            start_date=run_plan.run.from_date,
            end_date=run_plan.run.to_date,
        )
        return DailyBarsLoadResult(
            bars=bars,
            provenance=_snapshot_provenance(
                snapshot_type="tradable_bars",
                action="incremental_filled" if existing_bars else "created",
                path=path,
                source_paths=_candidate_paths(candidates),
                bars=bars,
                details={"fetched_ranges": _date_ranges_payload(missing_ranges)},
            ),
        )

    if provider is None:
        raise ValueError("provider is required when snapshots must be refreshed or created")

    bars = _fetch_tradable_bars(run_plan, series=series, provider=provider)
    if not bars:
        raise ValueError(f"no daily bars returned for {series.symbol}")

    write_daily_bars_parquet(bars, path)
    return DailyBarsLoadResult(
        bars=bars,
        provenance=_snapshot_provenance(
            snapshot_type="tradable_bars",
            action="created",
            path=path,
            bars=bars,
        ),
    )


def _load_discovered_tradable_bars(
    run_plan: RunPlan,
    *,
    series: TradableSeriesConfig,
) -> tuple[tuple[DailyBar, ...], tuple[DailyBarsSnapshotCandidate, ...]]:
    candidates = discover_tradable_bars_snapshot_paths(
        run_plan.data.snapshot_root,
        symbol=series.symbol,
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
        asset_type=series.asset_type,
        adjustment=series.price_adjustment or "none",
    )
    return _read_daily_bar_candidates(candidates), candidates


def _read_daily_bar_candidates(candidates: tuple[DailyBarsSnapshotCandidate, ...]) -> tuple[DailyBar, ...]:
    bars: list[DailyBar] = []
    for candidate in candidates:
        bars.extend(read_daily_bars_parquet(candidate.path))
    return _deduplicate_bars(bars)


def _fetch_tradable_bars(
    run_plan: RunPlan,
    *,
    series: TradableSeriesConfig,
    provider: RunDataProvider,
) -> tuple[DailyBar, ...]:
    return _fetch_tradable_bars_for_range(
        run_plan,
        series=series,
        provider=provider,
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
    )


def _fetch_missing_tradable_bars(
    run_plan: RunPlan,
    *,
    series: TradableSeriesConfig,
    provider: RunDataProvider,
    existing_bars: tuple[DailyBar, ...],
) -> tuple[tuple[DailyBar, ...], tuple[tuple[date, date], ...]]:
    if not existing_bars:
        return _fetch_tradable_bars(run_plan, series=series, provider=provider), (
            (run_plan.run.from_date, run_plan.run.to_date),
        )

    existing_dates = tuple(sorted({bar.trade_date for bar in existing_bars}))
    missing_ranges: list[tuple[date, date]] = []
    if existing_dates[0] > run_plan.run.from_date:
        missing_ranges.append((run_plan.run.from_date, existing_dates[0] - timedelta(days=1)))
    if existing_dates[-1] < run_plan.run.to_date:
        missing_ranges.append((existing_dates[-1] + timedelta(days=1), run_plan.run.to_date))

    fetched_bars: list[DailyBar] = []
    for start_date, end_date in missing_ranges:
        if start_date > end_date:
            continue
        fetched_bars.extend(
            _fetch_tradable_bars_for_range(
                run_plan,
                series=series,
                provider=provider,
                start_date=start_date,
                end_date=end_date,
            )
        )
    return tuple(fetched_bars), tuple(missing_ranges)


def _fetch_tradable_bars_for_range(
    run_plan: RunPlan,
    *,
    series: TradableSeriesConfig,
    provider: RunDataProvider,
    start_date: date,
    end_date: date,
) -> tuple[DailyBar, ...]:
    if series.asset_type == "stock":
        return provider.fetch_daily_bars(
            symbol=series.symbol,
            start_date=start_date,
            end_date=end_date,
            adjustment=series.price_adjustment or run_plan.data.price_adjustment,
        )

    if series.asset_type == "index":
        index_bars = provider.fetch_index_daily_bars(
            symbol=series.symbol,
            start_date=start_date,
            end_date=end_date,
        )
        return _index_bars_to_market_bars(index_bars)

    if series.asset_type == "industry_index":
        index_bars = provider.fetch_industry_index_daily_bars(
            symbol=series.symbol,
            start_date=start_date,
            end_date=end_date,
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


def _bars_cover_date_range(
    bars: tuple[DailyBar, ...],
    *,
    start_date: date,
    end_date: date,
) -> bool:
    if not bars:
        return False
    dates = [bar.trade_date for bar in bars]
    return min(dates) <= start_date and max(dates) >= end_date


def _bars_for_date_range(
    bars: tuple[DailyBar, ...],
    *,
    start_date: date,
    end_date: date,
) -> tuple[DailyBar, ...]:
    return tuple(
        bar
        for bar in bars
        if start_date <= bar.trade_date <= end_date
    )


def _deduplicate_bars(bars: tuple[DailyBar, ...] | list[DailyBar]) -> tuple[DailyBar, ...]:
    bars_by_key = {
        (bar.symbol, bar.trade_date): bar
        for bar in bars
    }
    return tuple(sorted(bars_by_key.values(), key=lambda bar: (bar.symbol, bar.trade_date)))


def _snapshot_provenance(
    *,
    snapshot_type: str,
    action: str,
    path: Path,
    source_paths: tuple[Path, ...] = (),
    bars: tuple[DailyBar, ...] = (),
    indicator_snapshots: tuple[IndicatorSnapshot, ...] = (),
    details: Mapping[str, Any] | None = None,
) -> SnapshotProvenance:
    dates = [bar.trade_date for bar in bars]
    dates.extend(snapshot.trade_date for snapshot in indicator_snapshots)
    return SnapshotProvenance(
        snapshot_type=snapshot_type,
        action=action,
        path=path,
        source_paths=source_paths,
        start_date=min(dates) if dates else None,
        end_date=max(dates) if dates else None,
        details=details or {},
    )


def _candidate_paths(candidates) -> tuple[Path, ...]:
    return tuple(candidate.path for candidate in candidates)


def _has_exact_bar_candidate(candidates: tuple[DailyBarsSnapshotCandidate, ...], path: Path) -> bool:
    return any(candidate.path == path for candidate in candidates)


def _has_exact_indicator_candidate(candidates: tuple[IndicatorSnapshotCandidate, ...], path: Path) -> bool:
    return any(candidate.path == path for candidate in candidates)


def _date_ranges_payload(ranges: tuple[tuple[date, date], ...]) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        for start_date, end_date in ranges
    )


def _load_or_build_required_indicators(
    run_plan: RunPlan,
    *,
    series: TradableSeriesConfig,
    bars: tuple[DailyBar, ...],
    indicator_requirements: tuple[IndicatorRequirement, ...],
) -> tuple[tuple[IndicatorSnapshot, ...], tuple[Path, ...], tuple[SnapshotProvenance, ...]]:
    snapshots: list[IndicatorSnapshot] = []
    paths: list[Path] = []
    provenances: list[SnapshotProvenance] = []

    for plan in build_indicator_update_plans(
        symbol=series.symbol,
        indicator_requirements=indicator_requirements,
    ):
        path = indicator_snapshot_path(
            run_plan.data.snapshot_root,
            symbol=series.symbol,
            start_date=run_plan.run.from_date,
            end_date=run_plan.run.to_date,
            adjustment=series.price_adjustment or "none",
            asset_type=series.asset_type,
            indicator_names=plan.indicator_names,
            timeframe=plan.timeframe,
        )
        timeframe_bars = bars if plan.timeframe == "D" else resample_daily_bars(bars, frequency=plan.timeframe)
        load_result = _load_or_build_indicators(
            run_plan,
            series=series,
            bars=timeframe_bars,
            path=path,
            plan=plan,
        )
        snapshots.extend(load_result.snapshots)
        paths.append(path)
        provenances.append(load_result.provenance)

    return (
        tuple(sorted(snapshots, key=lambda snapshot: (snapshot.symbol, snapshot.timeframe, snapshot.trade_date))),
        tuple(paths),
        tuple(provenances),
    )


def _load_or_build_indicators(
    run_plan: RunPlan,
    *,
    series: TradableSeriesConfig,
    bars: tuple[DailyBar, ...],
    path: Path,
    plan: IndicatorUpdatePlan,
) -> IndicatorSnapshotsLoadResult:
    if not run_plan.data.refresh_snapshots:
        snapshots, metadata, candidates = _load_discovered_indicator_snapshots(
            run_plan,
            series=series,
            bars=bars,
            plan=plan,
        )
        if metadata is not None and not _indicator_metadata_matches_plan(metadata, plan):
            snapshots = build_indicator_snapshots(bars, indicator_names=plan.indicator_names, timeframe=plan.timeframe)
            write_indicator_snapshots_parquet(snapshots, path)
            _write_indicator_metadata(path, snapshots=snapshots, plan=plan, bars=bars)
            return IndicatorSnapshotsLoadResult(
                snapshots=snapshots,
                provenance=_snapshot_provenance(
                    snapshot_type="indicators",
                    action="created",
                    path=path,
                    source_paths=_candidate_paths(candidates),
                    indicator_snapshots=snapshots,
                    details={
                        "reason": "metadata_mismatch",
                        "indicator_names": plan.indicator_names,
                        "timeframe": plan.timeframe,
                    },
                ),
            )

        if _snapshots_cover_requested_bars(snapshots, bars, timeframe=plan.timeframe):
            requested_snapshots = _indicator_snapshots_for_bars(snapshots, bars, timeframe=plan.timeframe)
            if metadata is None or not path.exists() or read_indicator_snapshot_metadata(path) is None:
                if not path.exists():
                    write_indicator_snapshots_parquet(requested_snapshots, path)
                _write_indicator_metadata(path, snapshots=requested_snapshots, plan=plan, bars=bars)
            action = "exact_reused" if _has_exact_indicator_candidate(candidates, path) else "range_reused"
            return IndicatorSnapshotsLoadResult(
                snapshots=requested_snapshots,
                provenance=_snapshot_provenance(
                    snapshot_type="indicators",
                    action=action,
                    path=path,
                    source_paths=_candidate_paths(candidates),
                    indicator_snapshots=requested_snapshots,
                    details={
                        "indicator_names": plan.indicator_names,
                        "timeframe": plan.timeframe,
                    },
                ),
            )

        stateful_append = _build_stateful_indicator_append(
            snapshots,
            bars,
            plan=plan,
            metadata=metadata,
        )
        if stateful_append is not None:
            new_snapshots, new_states = stateful_append
            write_merged_indicator_snapshots_parquet(
                snapshots,
                new_snapshots,
                path,
                overwrite_from=new_snapshots[0].trade_date,
            )
            merged_snapshots = _indicator_snapshots_for_bars(
                read_indicator_snapshots_parquet(path),
                bars,
                timeframe=plan.timeframe,
            )
            write_indicator_snapshots_parquet(merged_snapshots, path)
            _write_indicator_metadata(
                path,
                snapshots=merged_snapshots,
                plan=plan,
                bars=bars,
                states=new_states,
            )
            return IndicatorSnapshotsLoadResult(
                snapshots=merged_snapshots,
                provenance=_snapshot_provenance(
                    snapshot_type="indicators",
                    action="incremental_filled",
                    path=path,
                    source_paths=_candidate_paths(candidates),
                    indicator_snapshots=merged_snapshots,
                    details={
                        "mode": "stateful_append",
                        "overwrite_from": new_snapshots[0].trade_date.isoformat(),
                        "indicator_names": plan.indicator_names,
                        "timeframe": plan.timeframe,
                    },
                ),
            )

        calculation_bars, overwrite_from = _indicator_rebuild_window(
            snapshots,
            bars,
            plan=plan,
        )
        new_snapshots = build_indicator_snapshots(
            calculation_bars,
            indicator_names=plan.indicator_names,
            timeframe=plan.timeframe,
        )
        write_merged_indicator_snapshots_parquet(
            snapshots,
            new_snapshots,
            path,
            overwrite_from=overwrite_from,
        )
        merged_snapshots = _indicator_snapshots_for_bars(
            read_indicator_snapshots_parquet(path),
            bars,
            timeframe=plan.timeframe,
        )
        write_indicator_snapshots_parquet(merged_snapshots, path)
        _write_indicator_metadata(path, snapshots=merged_snapshots, plan=plan, bars=bars)
        return IndicatorSnapshotsLoadResult(
            snapshots=merged_snapshots,
            provenance=_snapshot_provenance(
                snapshot_type="indicators",
                action="incremental_filled" if snapshots else "created",
                path=path,
                source_paths=_candidate_paths(candidates),
                indicator_snapshots=merged_snapshots,
                details={
                    "mode": "rebuild_window",
                    "calculation_start": calculation_bars[0].trade_date.isoformat(),
                    "overwrite_from": overwrite_from.isoformat(),
                    "indicator_names": plan.indicator_names,
                    "timeframe": plan.timeframe,
                },
            ),
        )

    snapshots = build_indicator_snapshots(bars, indicator_names=plan.indicator_names, timeframe=plan.timeframe)
    write_indicator_snapshots_parquet(snapshots, path)
    _write_indicator_metadata(path, snapshots=snapshots, plan=plan, bars=bars)
    return IndicatorSnapshotsLoadResult(
        snapshots=snapshots,
        provenance=_snapshot_provenance(
            snapshot_type="indicators",
            action="created",
            path=path,
            indicator_snapshots=snapshots,
            details={
                "indicator_names": plan.indicator_names,
                "timeframe": plan.timeframe,
            },
        ),
    )


def _load_discovered_indicator_snapshots(
    run_plan: RunPlan,
    *,
    series: TradableSeriesConfig,
    bars: tuple[DailyBar, ...],
    plan: IndicatorUpdatePlan,
) -> tuple[tuple[IndicatorSnapshot, ...], IndicatorSnapshotMetadata | None, tuple[IndicatorSnapshotCandidate, ...]]:
    if not bars:
        return (), None, ()

    candidates = discover_indicator_snapshot_paths(
        run_plan.data.snapshot_root,
        symbol=series.symbol,
        start_date=bars[0].trade_date,
        end_date=bars[-1].trade_date,
        adjustment=series.price_adjustment or "none",
        asset_type=series.asset_type,
        indicator_names=plan.indicator_names,
        timeframe=plan.timeframe,
    )
    candidates = tuple(
        candidate
        for candidate in candidates
        if candidate.start_date == bars[0].trade_date
    )
    snapshots, metadata = _read_indicator_candidates(candidates, bars=bars, plan=plan)
    return snapshots, metadata, candidates


def _read_indicator_candidates(
    candidates: tuple[IndicatorSnapshotCandidate, ...],
    *,
    bars: tuple[DailyBar, ...],
    plan: IndicatorUpdatePlan,
) -> tuple[tuple[IndicatorSnapshot, ...], IndicatorSnapshotMetadata | None]:
    snapshots: list[IndicatorSnapshot] = []
    selected_metadata: IndicatorSnapshotMetadata | None = None

    for candidate in candidates:
        metadata = read_indicator_snapshot_metadata(candidate.path)
        if metadata is not None and not _indicator_metadata_matches_plan(metadata, plan):
            continue

        snapshots.extend(
            _indicator_snapshots_for_bars(
                read_indicator_snapshots_parquet(candidate.path),
                bars,
                timeframe=plan.timeframe,
            )
        )
        if metadata is not None and _metadata_has_later_coverage(metadata, selected_metadata):
            selected_metadata = metadata

    return _deduplicate_indicator_snapshots(snapshots), selected_metadata


def _snapshots_cover_requested_bars(
    snapshots: tuple[IndicatorSnapshot, ...],
    bars: tuple[DailyBar, ...],
    *,
    timeframe: str,
) -> bool:
    if not snapshots:
        return False
    requested_dates = {bar.trade_date for bar in bars}
    snapshot_dates = {
        snapshot.trade_date
        for snapshot in snapshots
        if snapshot.timeframe == timeframe
    }
    return requested_dates.issubset(snapshot_dates)


def _indicator_snapshots_for_bars(
    snapshots: tuple[IndicatorSnapshot, ...],
    bars: tuple[DailyBar, ...],
    *,
    timeframe: str,
) -> tuple[IndicatorSnapshot, ...]:
    requested_dates = {bar.trade_date for bar in bars}
    return tuple(
        snapshot
        for snapshot in snapshots
        if snapshot.timeframe == timeframe and snapshot.trade_date in requested_dates
    )


def _deduplicate_indicator_snapshots(
    snapshots: list[IndicatorSnapshot] | tuple[IndicatorSnapshot, ...],
) -> tuple[IndicatorSnapshot, ...]:
    snapshots_by_key = {
        (snapshot.symbol, snapshot.timeframe, snapshot.trade_date): snapshot
        for snapshot in snapshots
    }
    return tuple(sorted(snapshots_by_key.values(), key=lambda snapshot: (snapshot.symbol, snapshot.timeframe, snapshot.trade_date)))


def _metadata_has_later_coverage(
    metadata: IndicatorSnapshotMetadata,
    selected_metadata: IndicatorSnapshotMetadata | None,
) -> bool:
    if selected_metadata is None:
        return True
    if metadata.end_date is None:
        return False
    if selected_metadata.end_date is None:
        return True
    return metadata.end_date > selected_metadata.end_date


def _build_stateful_indicator_append(
    existing_snapshots: tuple[IndicatorSnapshot, ...],
    bars: tuple[DailyBar, ...],
    *,
    plan: IndicatorUpdatePlan,
    metadata: IndicatorSnapshotMetadata | None,
) -> tuple[tuple[IndicatorSnapshot, ...], dict[str, dict[str, Any]]] | None:
    if metadata is None or not _indicator_metadata_matches_plan(metadata, plan):
        return None
    if not all(spec.requires_state for spec in plan.specs):
        return None

    prefix_length = _covered_prefix_length(existing_snapshots, bars, timeframe=plan.timeframe)
    if prefix_length == 0 or prefix_length >= len(bars):
        return None
    if metadata.end_date != bars[prefix_length - 1].trade_date:
        return None
    if not all(name in metadata.states for name in plan.indicator_names):
        return None

    new_bars = bars[prefix_length:]
    try:
        return build_indicator_snapshots_from_state(
            new_bars,
            indicator_names=plan.indicator_names,
            timeframe=plan.timeframe,
            states=metadata.states,
        )
    except (KeyError, ValueError):
        return None


def _covered_prefix_length(
    snapshots: tuple[IndicatorSnapshot, ...],
    bars: tuple[DailyBar, ...],
    *,
    timeframe: str,
) -> int:
    snapshot_dates = {
        snapshot.trade_date
        for snapshot in snapshots
        if snapshot.timeframe == timeframe
    }
    length = 0
    for bar in bars:
        if bar.trade_date not in snapshot_dates:
            break
        length += 1
    return length


def _indicator_metadata_matches_plan(
    metadata: IndicatorSnapshotMetadata,
    plan: IndicatorUpdatePlan,
) -> bool:
    return (
        metadata.symbol == plan.symbol
        and metadata.timeframe == plan.timeframe
        and metadata.indicator_names == plan.indicator_names
        and metadata.version_fingerprint == plan.version_fingerprint
        and metadata.warmup_bars == plan.warmup_bars
        and metadata.recompute_lookback_bars == plan.recompute_lookback_bars
        and metadata.requires_state == plan.requires_state
    )


def _write_indicator_metadata(
    path: Path,
    *,
    snapshots: tuple[IndicatorSnapshot, ...],
    plan: IndicatorUpdatePlan,
    bars: tuple[DailyBar, ...],
    states: Mapping[str, Mapping[str, Any]] | None = None,
) -> Path:
    snapshot_dates = [
        snapshot.trade_date
        for snapshot in snapshots
        if snapshot.timeframe == plan.timeframe
    ]
    metadata = IndicatorSnapshotMetadata(
        symbol=plan.symbol,
        timeframe=plan.timeframe,
        indicator_names=plan.indicator_names,
        version_fingerprint=plan.version_fingerprint,
        start_date=min(snapshot_dates) if snapshot_dates else None,
        end_date=max(snapshot_dates) if snapshot_dates else None,
        warmup_bars=plan.warmup_bars,
        recompute_lookback_bars=plan.recompute_lookback_bars,
        requires_state=plan.requires_state,
        states=states if states is not None else indicator_states_from_bars(plan.indicator_names, bars),
    )
    return write_indicator_snapshot_metadata(path, metadata)


def _indicator_rebuild_window(
    existing_snapshots: tuple[IndicatorSnapshot, ...],
    bars: tuple[DailyBar, ...],
    *,
    plan: IndicatorUpdatePlan,
) -> tuple[tuple[DailyBar, ...], date]:
    if not bars:
        raise ValueError("indicator rebuild requires at least one bar")

    if not existing_snapshots or plan.requires_state:
        return bars, bars[0].trade_date

    existing_dates = {
        snapshot.trade_date
        for snapshot in existing_snapshots
        if snapshot.timeframe == plan.timeframe
    }
    first_missing_index = next(
        (
            index
            for index, bar in enumerate(bars)
            if bar.trade_date not in existing_dates
        ),
        0,
    )
    overwrite_index = max(0, first_missing_index - plan.recompute_lookback_bars)
    calculation_index = max(0, overwrite_index - plan.recompute_lookback_bars)
    return bars[calculation_index:], bars[overwrite_index].trade_date


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
) -> TradabilityLoadResult:
    if not run_plan.data.refresh_snapshots and path.exists():
        statuses = read_tradability_statuses_parquet(path)
        return TradabilityLoadResult(
            statuses=statuses,
            provenance=SnapshotProvenance(
                snapshot_type="tradability_statuses",
                action="exact_reused",
                path=path,
                source_paths=(path,),
                start_date=min((status.trade_date for status in statuses), default=None),
                end_date=max((status.trade_date for status in statuses), default=None),
            ),
        )

    if provider is None:
        raise ValueError("provider is required when tradability snapshots must be refreshed or created")

    statuses = provider.fetch_tradability_statuses(
        symbol=symbol,
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
    )
    write_tradability_statuses_parquet(statuses, path)
    return TradabilityLoadResult(
        statuses=statuses,
        provenance=SnapshotProvenance(
            snapshot_type="tradability_statuses",
            action="created",
            path=path,
            start_date=min((status.trade_date for status in statuses), default=None),
            end_date=max((status.trade_date for status in statuses), default=None),
        ),
    )


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
