"""Prepare Data Snapshots and feature frames for a Run Plan."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
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
    IndexBarsSnapshotCandidate,
    SnapshotReadCache,
    SnapshotProvenance,
    decode_attribution_reference_cell,
    discover_index_bars_snapshot_paths,
    discover_industry_index_bars_snapshot_paths,
    discover_tradable_bars_snapshot_paths,
    index_bars_snapshot_path,
    industry_index_bars_snapshot_path,
    read_daily_bars_parquet,
    read_attribution_reference_values_parquet,
    read_index_bars_parquet,
    read_shenwan_classifications_parquet,
    read_stock_industry_memberships_parquet,
    read_tradability_statuses_parquet,
    select_attribution_reference_snapshot_path,
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
from attbacktrader.strategies import EntryAttributionEvidence, attribution_declaration_by_key
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
class IndexBarsLoadResult:
    bars: tuple[IndexBar, ...]
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
    calculation_bars: tuple[IndexBar, ...]
    snapshot_path: Path
    snapshot_provenance: SnapshotProvenance


@dataclass(frozen=True)
class IndexSeriesResult:
    symbol: str
    bar_count: int
    snapshot_path: Path
    snapshot_provenance: SnapshotProvenance
    calculation_bar_count: int


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
    attribution_reference_evidence_by_symbol_date: Mapping[str, Mapping[date, EntryAttributionEvidence]] = field(
        default_factory=dict
    )

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

    def benchmark_calculation_bars_by_symbol(self, run_plan: RunPlan) -> dict[str, tuple[IndexBar, ...]]:
        return {
            symbol: self.index_data_by_symbol[symbol].calculation_bars
            for symbol in run_plan.data.benchmark_series.indexes
            if symbol in self.index_data_by_symbol
        }

    def industry_index_bars_by_symbol(self, run_plan: RunPlan) -> dict[str, tuple[IndexBar, ...]]:
        return {
            symbol: self.industry_index_data_by_symbol[symbol].bars
            for symbol in run_plan.data.industry_series.indexes
            if symbol in self.industry_index_data_by_symbol
        }

    def industry_index_calculation_bars_by_symbol(self, run_plan: RunPlan) -> dict[str, tuple[IndexBar, ...]]:
        return {
            symbol: self.industry_index_data_by_symbol[symbol].calculation_bars
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


@dataclass(frozen=True)
class PreparedRunDataCacheKey:
    fingerprint: str


class PreparedRunDataCache:
    """Cache Prepared Run Data when run plans have identical data requirements."""

    def __init__(self) -> None:
        self._items: dict[PreparedRunDataCacheKey, Any] = {}

    def get_or_prepare(
        self,
        run_plan: RunPlan,
        *,
        provider: RunDataProvider | None = None,
        snapshot_read_cache: SnapshotReadCache | None = None,
        prepare: Callable[..., Any] | None = None,
    ) -> Any:
        key = prepared_run_data_cache_key(run_plan)
        if key not in self._items:
            prepare_func = prepare if prepare is not None else prepare_run_data
            kwargs: dict[str, Any] = {"provider": provider}
            if snapshot_read_cache is not None:
                kwargs["snapshot_read_cache"] = snapshot_read_cache
            self._items[key] = prepare_func(run_plan, **kwargs)
        return self._items[key]


def prepared_run_data_cache_key(run_plan: RunPlan) -> PreparedRunDataCacheKey:
    payload = run_plan.model_dump(mode="json")
    run = dict(payload.get("run") or {})
    run.pop("id", None)
    payload["run"] = run
    payload.pop("output", None)
    fingerprint = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return PreparedRunDataCacheKey(fingerprint=fingerprint)


def prepare_run_data(
    run_plan: RunPlan,
    *,
    provider: RunDataProvider | None = None,
    snapshot_read_cache: SnapshotReadCache | None = None,
) -> PreparedRunData:
    tradable_series = run_plan.data.resolved_tradable_series
    indicator_requirements = _indicator_requirements_for_run_plan(run_plan)
    prepared_indexes_by_symbol = _prepare_index_data_by_symbol(
        run_plan,
        provider=provider,
        snapshot_read_cache=snapshot_read_cache,
    )
    trading_calendar = _trading_calendar_for_run(run_plan, prepared_indexes_by_symbol)
    prepared_symbols = tuple(
        _prepare_symbol_data(
            run_plan,
            series=series,
            provider=provider,
            indicator_requirements=indicator_requirements,
            trading_calendar=trading_calendar,
            snapshot_read_cache=snapshot_read_cache,
        )
        for series in tradable_series
    )
    prepared_by_symbol = {prepared.symbol: prepared for prepared in prepared_symbols}
    prepared_industry_indexes_by_symbol = _prepare_industry_index_data_by_symbol(
        run_plan,
        provider=provider,
        snapshot_read_cache=snapshot_read_cache,
    )
    industry_classification_result, industry_membership_results, memberships_by_symbol = _prepare_industry_data(
        run_plan,
        tradable_series=tradable_series,
        provider=provider,
    )
    attribution_reference_evidence_by_symbol_date = _prepare_attribution_reference_evidence_by_symbol_date(
        run_plan,
        symbols=tuple(prepared_by_symbol),
        snapshot_read_cache=snapshot_read_cache,
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
        attribution_reference_evidence_by_symbol_date=attribution_reference_evidence_by_symbol_date,
    )


def _indicator_requirements_for_run_plan(run_plan: RunPlan) -> tuple[IndicatorRequirement, ...]:
    requirements = set(required_indicators_for_strategy_config(run_plan.strategy))
    if run_plan.execution.engine == "baoma_v1_business":
        requirements.update(
            {
                IndicatorRequirement("atr14", "D"),
                IndicatorRequirement("kdj", "D"),
                IndicatorRequirement("cci14", "D"),
                IndicatorRequirement("boll_up20_2", "D"),
            }
        )
    declarations = attribution_declaration_by_key()
    selection = run_plan.analysis.resolved_attribution_factor_selection

    should_include_attribution_requirements = (
        selection.get("configured_source") == "analysis.attribution.include"
        or run_plan.execution.engine == "baoma_v1_business"
    )
    if selection.get("enabled", True) and should_include_attribution_requirements:
        for key in selection.get("include", ()):
            declaration = declarations.get(str(key))
            if declaration is None or declaration.scope != "symbol":
                continue
            requirements.update(_indicator_requirements_from_dependencies(declaration.dependencies))

    return tuple(sorted(requirements))


def _indicator_requirements_from_dependencies(
    dependencies: tuple[str, ...],
) -> tuple[IndicatorRequirement, ...]:
    requirements: list[IndicatorRequirement] = []
    for dependency in dependencies:
        if ":" not in dependency:
            continue
        name, timeframe = dependency.split(":", 1)
        if not name or not timeframe:
            continue
        requirements.append(IndicatorRequirement(name, timeframe))
    return tuple(requirements)


def _prepare_attribution_reference_evidence_by_symbol_date(
    run_plan: RunPlan,
    *,
    symbols: tuple[str, ...],
    snapshot_read_cache: SnapshotReadCache | None = None,
) -> dict[str, dict[date, EntryAttributionEvidence]]:
    field_keys = _attribution_reference_factor_keys_for_run(run_plan)
    if not symbols or not field_keys:
        return {}

    snapshot_path = select_attribution_reference_snapshot_path(
        run_plan.data.snapshot_root,
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
    )
    if snapshot_path is None:
        return {}

    rows = read_attribution_reference_values_parquet(
        snapshot_path,
        symbols=symbols,
        field_keys=field_keys,
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
        cache=snapshot_read_cache,
    )
    declarations = attribution_declaration_by_key()
    payload_by_symbol_date: dict[str, dict[date, dict[str, dict[str, Any]]]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "")
        trade_date = _reference_trade_date(row)
        field_key = str(row.get("field_key") or "")
        declaration = declarations.get(field_key)
        if not symbol or trade_date is None or declaration is None:
            continue
        payload = payload_by_symbol_date.setdefault(symbol, {}).setdefault(
            trade_date,
            {"checks": {}, "values": {}, "categories": {}},
        )
        raw_value = decode_attribution_reference_cell(row.get("value"))
        bucket = decode_attribution_reference_cell(row.get("bucket"))
        if declaration.factor_type == "category":
            category_value = bucket if bucket is not None else raw_value
            if category_value is not None:
                payload["categories"][field_key] = str(category_value)
        elif declaration.factor_type == "check":
            if isinstance(raw_value, bool):
                payload["checks"][field_key] = raw_value
        else:
            if raw_value is not None and not isinstance(raw_value, bool):
                payload["values"][field_key] = raw_value

    return {
        symbol: {
            trade_date: EntryAttributionEvidence(
                checks=payload["checks"],
                values=payload["values"],
                categories=payload["categories"],
            )
            for trade_date, payload in by_date.items()
            if payload["checks"] or payload["values"] or payload["categories"]
        }
        for symbol, by_date in payload_by_symbol_date.items()
        if by_date
    }


def _attribution_reference_factor_keys_for_run(run_plan: RunPlan) -> tuple[str, ...]:
    selection = run_plan.analysis.resolved_attribution_factor_selection
    configured_source = str(selection.get("configured_source") or "")
    config = run_plan.analysis.entry_attribution
    should_consider_selection = (
        config.enabled
        or config.entry_filter.enabled
        or configured_source in {"analysis.attribution.include", "analysis.entry_attribution.factors"}
    )
    selected_keys: set[str] = set()
    if selection.get("enabled", True) and should_consider_selection:
        selected_keys.update(str(key) for key in selection.get("include", ()))
    selected_keys.update(str(condition.field) for condition in config.entry_filter.conditions)

    declarations = attribution_declaration_by_key()
    return tuple(
        sorted(
            key
            for key in selected_keys
            if (declaration := declarations.get(key)) is not None
            and declaration.source == "attribution_reference_snapshot"
        )
    )


def _reference_trade_date(row: Mapping[str, Any]) -> date | None:
    for key in ("trade_date", "asof_date"):
        value = row.get(key)
        if isinstance(value, date):
            return value
        if value is None:
            continue
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            continue
    return None


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


def _indicator_calculation_start_date(
    run_start_date: date,
    *,
    indicator_requirements: tuple[IndicatorRequirement, ...],
) -> date:
    lookback_days = max(
        (
            _warmup_calendar_days(plan)
            for plan in build_indicator_update_plans(
                symbol="__warmup__",
                indicator_requirements=indicator_requirements,
            )
        ),
        default=0,
    )
    if lookback_days <= 0:
        return run_start_date
    return run_start_date - timedelta(days=lookback_days)


def _symbol_calculation_start_date(
    run_plan: RunPlan,
    *,
    indicator_requirements: tuple[IndicatorRequirement, ...],
) -> date:
    indicator_start_date = _indicator_calculation_start_date(
        run_plan.run.from_date,
        indicator_requirements=indicator_requirements,
    )
    if run_plan.execution.engine != "baoma_v1_business":
        return indicator_start_date
    return min(indicator_start_date, _one_year_before(run_plan.run.from_date))


def _one_year_before(value: date) -> date:
    try:
        return value.replace(year=value.year - 1)
    except ValueError:
        return value.replace(year=value.year - 1, day=28)


def _warmup_calendar_days(plan: IndicatorUpdatePlan) -> int:
    missing_bars = max(plan.warmup_bars - 1, 0)
    if missing_bars == 0:
        return 0
    if plan.timeframe == "D":
        return _calendar_days_for_trading_bars(missing_bars)
    if plan.timeframe == "W":
        return missing_bars * 7 + 14
    if plan.timeframe == "M":
        return missing_bars * 31 + 31
    raise ValueError(f"unsupported indicator timeframe: {plan.timeframe}")


def _calendar_days_for_trading_bars(bar_count: int) -> int:
    return ((bar_count * 7) + 4) // 5 + 7


_OBJECTIVE_MARKET_COMPONENT_INDEXES = ("000300.SH", "000905.SH")
_OBJECTIVE_MARKET_COMPOSITE_INDEX = "000985.CSI"
_OBJECTIVE_MARKET_FACTOR_KEYS = (
    "market.objective.entry_index_drawdown_250d_bucket",
    "market.objective.entry_index_ma60_slope_20d_bucket",
)


def _objective_market_component_symbols(run_plan: RunPlan) -> tuple[str, ...]:
    if not _entry_attribution_has_any_factor(run_plan, keys=_OBJECTIVE_MARKET_FACTOR_KEYS):
        return ()

    configured_indexes = set(run_plan.data.benchmark_series.indexes)
    if _OBJECTIVE_MARKET_COMPOSITE_INDEX in configured_indexes:
        return (_OBJECTIVE_MARKET_COMPOSITE_INDEX,)
    if set(_OBJECTIVE_MARKET_COMPONENT_INDEXES).issubset(configured_indexes):
        return _OBJECTIVE_MARKET_COMPONENT_INDEXES
    return ()


def _objective_market_calculation_start_date(run_start_date: date) -> date:
    return run_start_date - timedelta(days=_calendar_days_for_trading_bars(249))


def _entry_attribution_has_any_factor(run_plan: RunPlan, *, keys: tuple[str, ...]) -> bool:
    config = run_plan.analysis.entry_attribution
    return config.enabled and any(key in config.resolved_factors for key in keys)


def _market_index_calculation_start_date(run_plan: RunPlan, *, symbol: str) -> date:
    config = run_plan.analysis.entry_attribution
    start_date = run_plan.run.from_date
    if symbol in _objective_market_component_symbols(run_plan):
        start_date = min(start_date, _objective_market_calculation_start_date(run_plan.run.from_date))
    if not config.enabled or symbol != config.market_symbol:
        if symbol == "000300.SH" and _selected_attribution_has_any_factor(
            run_plan,
            prefixes=("industry.relative.hs300.", "market.hs300.ma"),
        ):
            start_date = min(
                start_date,
                _indicator_calculation_start_date(
                    run_plan.run.from_date,
                    indicator_requirements=(IndicatorRequirement("ma60", "D"),),
                ),
            )
        return start_date
    if _entry_attribution_has_factor(run_plan, prefix="market."):
        start_date = min(
            start_date,
            run_plan.run.from_date - timedelta(
                days=_calendar_days_for_trading_bars(max(config.market_slow_period - 1, 0))
            ),
        )
    if _selected_attribution_has_any_factor(
        run_plan,
        prefixes=("industry.relative.hs300.", "market.hs300.ma"),
    ):
        start_date = min(
            start_date,
            _indicator_calculation_start_date(
                run_plan.run.from_date,
                indicator_requirements=(IndicatorRequirement("ma60", "D"),),
            ),
        )
    return start_date


def _industry_index_calculation_start_date(run_plan: RunPlan) -> date:
    start_date = run_plan.run.from_date
    if _selected_attribution_has_any_factor(
        run_plan,
        prefixes=("industry.ma.", "industry.relative.hs300."),
    ):
        start_date = min(
            start_date,
            _indicator_calculation_start_date(
                run_plan.run.from_date,
                indicator_requirements=(IndicatorRequirement("ma60", "D"),),
            ),
        )
    if _selected_attribution_has_any_factor(run_plan, prefixes=("industry.kdj.week.",)):
        start_date = min(
            start_date,
            _indicator_calculation_start_date(
                run_plan.run.from_date,
                indicator_requirements=(IndicatorRequirement("kdj", "W"),),
            ),
        )
    if _selected_attribution_has_any_factor(run_plan, prefixes=("industry.macd.week.",)):
        start_date = min(
            start_date,
            _indicator_calculation_start_date(
                run_plan.run.from_date,
                indicator_requirements=(IndicatorRequirement("macd", "W"),),
            ),
        )
    if _selected_attribution_has_any_factor(run_plan, prefixes=("industry.macd.",)):
        start_date = min(
            start_date,
            _indicator_calculation_start_date(
                run_plan.run.from_date,
                indicator_requirements=(IndicatorRequirement("macd", "D"),),
            ),
        )
    if start_date < run_plan.run.from_date:
        return start_date
    if not _entry_attribution_has_factor(run_plan, prefix="industry."):
        return run_plan.run.from_date
    return _indicator_calculation_start_date(
        run_plan.run.from_date,
        indicator_requirements=(IndicatorRequirement("kdj", "D"),),
    )


def _entry_attribution_has_factor(run_plan: RunPlan, *, prefix: str) -> bool:
    config = run_plan.analysis.entry_attribution
    return config.enabled and any(factor.startswith(prefix) for factor in config.resolved_factors)


def _selected_attribution_has_any_factor(run_plan: RunPlan, *, prefixes: tuple[str, ...]) -> bool:
    selection = run_plan.analysis.resolved_attribution_factor_selection
    if selection.get("configured_source") != "analysis.attribution.include":
        return False
    return any(
        str(factor).startswith(prefix)
        for factor in selection.get("include", ())
        for prefix in prefixes
    )


def _prepare_symbol_data(
    run_plan: RunPlan,
    *,
    series: TradableSeriesConfig,
    provider: RunDataProvider | None,
    indicator_requirements: tuple[IndicatorRequirement, ...],
    trading_calendar: TradingCalendar | None,
    snapshot_read_cache: SnapshotReadCache | None = None,
) -> PreparedSymbolData:
    calculation_start_date = _symbol_calculation_start_date(
        run_plan,
        indicator_requirements=indicator_requirements,
    )
    snapshot_path = tradable_bars_snapshot_path(
        run_plan.data.snapshot_root,
        symbol=series.symbol,
        start_date=calculation_start_date,
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

    bars_load_result = _load_or_fetch_bars(
        run_plan,
        series=series,
        path=snapshot_path,
        provider=provider,
        start_date=calculation_start_date,
        end_date=run_plan.run.to_date,
        minimum_start_date=run_plan.run.from_date,
        snapshot_read_cache=snapshot_read_cache,
    )
    calculation_bars = bars_load_result.bars
    bars = _bars_for_date_range(
        calculation_bars,
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
    )
    if not bars:
        raise ValueError(f"no daily bars returned for {series.symbol} in run window")
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
        bars=calculation_bars,
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
    start_date: date,
    end_date: date,
    minimum_start_date: date,
    snapshot_read_cache: SnapshotReadCache | None = None,
) -> DailyBarsLoadResult:
    existing_bars, candidates = _load_discovered_tradable_bars(
        run_plan,
        series=series,
        start_date=start_date,
        end_date=end_date,
        snapshot_read_cache=snapshot_read_cache,
    )
    if not run_plan.data.refresh_snapshots:
        if _bars_cover_date_range(
            existing_bars,
            start_date=start_date,
            end_date=end_date,
        ):
            bars = _bars_for_date_range(
                existing_bars,
                start_date=start_date,
                end_date=end_date,
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
                    details=_bar_load_details(
                        requested_start_date=start_date,
                        requested_end_date=end_date,
                        minimum_start_date=minimum_start_date,
                    ),
                ),
            )

        if provider is None and _bars_cover_date_range(
            existing_bars,
            start_date=minimum_start_date,
            end_date=end_date,
        ):
            bars = _bars_for_date_range(
                existing_bars,
                start_date=start_date,
                end_date=end_date,
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
                    details=_bar_load_details(
                        requested_start_date=start_date,
                        requested_end_date=end_date,
                        minimum_start_date=minimum_start_date,
                        warmup_incomplete=True,
                    ),
                ),
            )

        if provider is None:
            raise ValueError("provider is required when snapshots must be refreshed or created")

        missing_bars, missing_ranges = _fetch_missing_tradable_bars(
            run_plan,
            series=series,
            provider=provider,
            existing_bars=existing_bars,
            start_date=start_date,
            end_date=end_date,
        )
        if not existing_bars and not missing_bars:
            raise ValueError(f"no daily bars returned for {series.symbol}")

        write_merged_daily_bars_parquet(
            existing_bars,
            missing_bars,
            path,
            start_date=start_date,
            end_date=end_date,
        )
        bars = _bars_for_date_range(
            read_daily_bars_parquet(path),
            start_date=start_date,
            end_date=end_date,
        )
        if not _has_bars_in_date_range(bars, start_date=minimum_start_date, end_date=end_date):
            raise ValueError(f"no daily bars returned for {series.symbol} in run window")
        return DailyBarsLoadResult(
            bars=bars,
            provenance=_snapshot_provenance(
                snapshot_type="tradable_bars",
                action="incremental_filled" if existing_bars else "created",
                path=path,
                source_paths=_candidate_paths(candidates),
                bars=bars,
                details=_bar_load_details(
                    requested_start_date=start_date,
                    requested_end_date=end_date,
                    minimum_start_date=minimum_start_date,
                    fetched_ranges=_date_ranges_payload(missing_ranges),
                    warmup_incomplete=not _bars_cover_date_range(
                        bars,
                        start_date=start_date,
                        end_date=end_date,
                    ),
                ),
            ),
        )

    if provider is None:
        raise ValueError("provider is required when snapshots must be refreshed or created")

    missing_bars, missing_ranges = _fetch_missing_tradable_bars(
        run_plan,
        series=series,
        provider=provider,
        existing_bars=existing_bars,
        start_date=start_date,
        end_date=end_date,
    )
    if not existing_bars and not missing_bars:
        raise ValueError(f"no daily bars returned for {series.symbol}")

    write_merged_daily_bars_parquet(
        existing_bars,
        missing_bars,
        path,
        start_date=start_date,
        end_date=end_date,
    )
    bars = _bars_for_date_range(
        read_daily_bars_parquet(path),
        start_date=start_date,
        end_date=end_date,
    )
    if not _has_bars_in_date_range(bars, start_date=minimum_start_date, end_date=end_date):
        raise ValueError(f"no daily bars returned for {series.symbol} in run window")

    return DailyBarsLoadResult(
        bars=bars,
        provenance=_snapshot_provenance(
            snapshot_type="tradable_bars",
            action=(
                "created"
                if not existing_bars
                else "incremental_filled"
                if missing_bars
                else ("exact_reused" if _has_exact_bar_candidate(candidates, path) else "range_reused")
            ),
            path=path,
            source_paths=_candidate_paths(candidates),
            bars=bars,
            details=_bar_load_details(
                requested_start_date=start_date,
                requested_end_date=end_date,
                minimum_start_date=minimum_start_date,
                fetched_ranges=_date_ranges_payload(missing_ranges),
                warmup_incomplete=not _bars_cover_date_range(
                    bars,
                    start_date=start_date,
                    end_date=end_date,
                ),
            ),
        ),
    )


def _load_discovered_tradable_bars(
    run_plan: RunPlan,
    *,
    series: TradableSeriesConfig,
    start_date: date,
    end_date: date,
    snapshot_read_cache: SnapshotReadCache | None = None,
) -> tuple[tuple[DailyBar, ...], tuple[DailyBarsSnapshotCandidate, ...]]:
    candidates = discover_tradable_bars_snapshot_paths(
        run_plan.data.snapshot_root,
        symbol=series.symbol,
        start_date=start_date,
        end_date=end_date,
        asset_type=series.asset_type,
        adjustment=series.price_adjustment or "none",
    )
    return _read_daily_bar_candidates(candidates, snapshot_read_cache=snapshot_read_cache), candidates


def _read_daily_bar_candidates(
    candidates: tuple[DailyBarsSnapshotCandidate, ...],
    *,
    snapshot_read_cache: SnapshotReadCache | None = None,
) -> tuple[DailyBar, ...]:
    bars: list[DailyBar] = []
    for candidate in candidates:
        bars.extend(read_daily_bars_parquet(candidate.path, cache=snapshot_read_cache))
    return _deduplicate_bars(bars)


def _fetch_tradable_bars(
    run_plan: RunPlan,
    *,
    series: TradableSeriesConfig,
    provider: RunDataProvider,
    start_date: date,
    end_date: date,
) -> tuple[DailyBar, ...]:
    return _fetch_tradable_bars_for_range(
        run_plan,
        series=series,
        provider=provider,
        start_date=start_date,
        end_date=end_date,
    )


def _fetch_missing_tradable_bars(
    run_plan: RunPlan,
    *,
    series: TradableSeriesConfig,
    provider: RunDataProvider,
    existing_bars: tuple[DailyBar, ...],
    start_date: date,
    end_date: date,
) -> tuple[tuple[DailyBar, ...], tuple[tuple[date, date], ...]]:
    if not existing_bars:
        return _fetch_tradable_bars(
            run_plan,
            series=series,
            provider=provider,
            start_date=start_date,
            end_date=end_date,
        ), (
            (start_date, end_date),
        )

    existing_dates = tuple(sorted({bar.trade_date for bar in existing_bars}))
    missing_ranges: list[tuple[date, date]] = []
    if existing_dates[0] > start_date:
        missing_ranges.append((start_date, existing_dates[0] - timedelta(days=1)))
    if existing_dates[-1] < end_date:
        missing_ranges.append((existing_dates[-1] + timedelta(days=1), end_date))

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


def _has_bars_in_date_range(
    bars: tuple[DailyBar, ...],
    *,
    start_date: date,
    end_date: date,
) -> bool:
    return any(start_date <= bar.trade_date <= end_date for bar in bars)


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


def _index_bars_cover_date_range(
    bars: tuple[IndexBar, ...],
    *,
    start_date: date,
    end_date: date,
) -> bool:
    if not bars:
        return False
    dates = [bar.trade_date for bar in bars]
    first_date = min(dates)
    return _covers_start_with_calendar_gap(first_date, start_date=start_date) and max(dates) >= end_date


def _covers_start_with_calendar_gap(first_date: date, *, start_date: date) -> bool:
    if first_date <= start_date:
        return True
    return (first_date - start_date).days <= 7


def _index_bars_for_date_range(
    bars: tuple[IndexBar, ...],
    *,
    start_date: date,
    end_date: date,
) -> tuple[IndexBar, ...]:
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


def _has_exact_index_candidate(candidates: tuple[IndexBarsSnapshotCandidate, ...], path: Path) -> bool:
    return any(candidate.path == path for candidate in candidates)


def _date_ranges_payload(ranges: tuple[tuple[date, date], ...]) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        for start_date, end_date in ranges
    )


def _bar_load_details(
    *,
    requested_start_date: date,
    requested_end_date: date,
    minimum_start_date: date,
    fetched_ranges: tuple[dict[str, str], ...] = (),
    warmup_incomplete: bool = False,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "requested_start_date": requested_start_date.isoformat(),
        "requested_end_date": requested_end_date.isoformat(),
        "minimum_start_date": minimum_start_date.isoformat(),
    }
    if fetched_ranges:
        details["fetched_ranges"] = fetched_ranges
    if warmup_incomplete:
        details["warmup_incomplete"] = True
    return details


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
        timeframe_bars = bars if plan.timeframe == "D" else resample_daily_bars(bars, frequency=plan.timeframe)
        path_start_date = timeframe_bars[0].trade_date if timeframe_bars else run_plan.run.from_date
        path_end_date = timeframe_bars[-1].trade_date if timeframe_bars else run_plan.run.to_date
        path = indicator_snapshot_path(
            run_plan.data.snapshot_root,
            symbol=series.symbol,
            start_date=path_start_date,
            end_date=path_end_date,
            adjustment=series.price_adjustment or "none",
            asset_type=series.asset_type,
            indicator_names=plan.indicator_names,
            timeframe=plan.timeframe,
        )
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
    snapshot_read_cache: SnapshotReadCache | None = None,
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
        symbol: _prepare_index_data(
            run_plan,
            symbol=symbol,
            provider=provider,
            snapshot_read_cache=snapshot_read_cache,
        )
        for symbol in index_symbols
    }


def _prepare_index_data(
    run_plan: RunPlan,
    *,
    symbol: str,
    provider: RunDataProvider | None,
    snapshot_read_cache: SnapshotReadCache | None = None,
) -> PreparedIndexData:
    calculation_start_date = _market_index_calculation_start_date(run_plan, symbol=symbol)
    snapshot_path = index_bars_snapshot_path(
        run_plan.data.snapshot_root,
        symbol=symbol,
        start_date=calculation_start_date,
        end_date=run_plan.run.to_date,
    )
    load_result = _load_or_fetch_index_bars(
        run_plan,
        symbol=symbol,
        path=snapshot_path,
        provider=provider,
        start_date=calculation_start_date,
        end_date=run_plan.run.to_date,
        snapshot_read_cache=snapshot_read_cache,
    )
    bars = _index_bars_for_date_range(
        load_result.bars,
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
    )
    return PreparedIndexData(
        symbol=symbol,
        bars=bars,
        calculation_bars=load_result.bars,
        snapshot_path=snapshot_path,
        snapshot_provenance=load_result.provenance,
    )


def _load_or_fetch_index_bars(
    run_plan: RunPlan,
    *,
    symbol: str,
    path: Path,
    provider: RunDataProvider | None,
    start_date: date,
    end_date: date,
    snapshot_read_cache: SnapshotReadCache | None = None,
) -> IndexBarsLoadResult:
    if not run_plan.data.refresh_snapshots:
        existing_bars, candidates = _load_discovered_index_bars(
            run_plan,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            snapshot_read_cache=snapshot_read_cache,
        )
        if _index_bars_cover_date_range(existing_bars, start_date=start_date, end_date=end_date):
            bars = _index_bars_for_date_range(existing_bars, start_date=start_date, end_date=end_date)
            if not path.exists():
                write_index_bars_parquet(bars, path)
            action = "exact_reused" if _has_exact_index_candidate(candidates, path) else "range_reused"
            return IndexBarsLoadResult(
                bars=bars,
                provenance=_snapshot_provenance(
                    snapshot_type="index_bars",
                    action=action,
                    path=path,
                    source_paths=_candidate_paths(candidates),
                    bars=bars,
                    details=_bar_load_details(
                        requested_start_date=start_date,
                        requested_end_date=end_date,
                        minimum_start_date=run_plan.run.from_date,
                    ),
                ),
            )

    if provider is None:
        raise ValueError("provider is required when index snapshots must be refreshed or created")

    bars = provider.fetch_index_daily_bars(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )

    write_index_bars_parquet(bars, path)
    return IndexBarsLoadResult(
        bars=bars,
        provenance=_snapshot_provenance(
            snapshot_type="index_bars",
            action="created",
            path=path,
            bars=bars,
            details=_bar_load_details(
                requested_start_date=start_date,
                requested_end_date=end_date,
                minimum_start_date=run_plan.run.from_date,
                warmup_incomplete=not _index_bars_cover_date_range(
                    bars,
                    start_date=start_date,
                    end_date=end_date,
                ),
            ),
        ),
    )


def _load_discovered_index_bars(
    run_plan: RunPlan,
    *,
    symbol: str,
    start_date: date,
    end_date: date,
    snapshot_read_cache: SnapshotReadCache | None = None,
) -> tuple[tuple[IndexBar, ...], tuple[IndexBarsSnapshotCandidate, ...]]:
    candidates = discover_index_bars_snapshot_paths(
        run_plan.data.snapshot_root,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )
    return _read_index_bar_candidates(candidates, snapshot_read_cache=snapshot_read_cache), candidates


def _prepare_industry_index_data_by_symbol(
    run_plan: RunPlan,
    *,
    provider: RunDataProvider | None,
    snapshot_read_cache: SnapshotReadCache | None = None,
) -> dict[str, PreparedIndexData]:
    return {
        symbol: _prepare_industry_index_data(
            run_plan,
            symbol=symbol,
            provider=provider,
            snapshot_read_cache=snapshot_read_cache,
        )
        for symbol in run_plan.data.industry_series.indexes
    }


def _prepare_industry_index_data(
    run_plan: RunPlan,
    *,
    symbol: str,
    provider: RunDataProvider | None,
    snapshot_read_cache: SnapshotReadCache | None = None,
) -> PreparedIndexData:
    source = run_plan.data.industry_series.source
    calculation_start_date = _industry_index_calculation_start_date(run_plan)
    snapshot_path = industry_index_bars_snapshot_path(
        run_plan.data.snapshot_root,
        symbol=symbol,
        start_date=calculation_start_date,
        end_date=run_plan.run.to_date,
        source=source,
    )
    load_result = _load_or_fetch_industry_index_bars(
        run_plan,
        symbol=symbol,
        source=source,
        path=snapshot_path,
        provider=provider,
        start_date=calculation_start_date,
        end_date=run_plan.run.to_date,
        snapshot_read_cache=snapshot_read_cache,
    )
    bars = _index_bars_for_date_range(
        load_result.bars,
        start_date=run_plan.run.from_date,
        end_date=run_plan.run.to_date,
    )
    return PreparedIndexData(
        symbol=symbol,
        bars=bars,
        calculation_bars=load_result.bars,
        snapshot_path=snapshot_path,
        snapshot_provenance=load_result.provenance,
    )


def _load_or_fetch_industry_index_bars(
    run_plan: RunPlan,
    *,
    symbol: str,
    source: str,
    path: Path,
    provider: RunDataProvider | None,
    start_date: date,
    end_date: date,
    snapshot_read_cache: SnapshotReadCache | None = None,
) -> IndexBarsLoadResult:
    if not run_plan.data.refresh_snapshots:
        existing_bars, candidates = _load_discovered_industry_index_bars(
            run_plan,
            symbol=symbol,
            source=source,
            start_date=start_date,
            end_date=end_date,
            snapshot_read_cache=snapshot_read_cache,
        )
        if _index_bars_cover_date_range(existing_bars, start_date=start_date, end_date=end_date):
            bars = _index_bars_for_date_range(existing_bars, start_date=start_date, end_date=end_date)
            if not path.exists():
                write_index_bars_parquet(bars, path)
            action = "exact_reused" if _has_exact_index_candidate(candidates, path) else "range_reused"
            return IndexBarsLoadResult(
                bars=bars,
                provenance=_snapshot_provenance(
                    snapshot_type="industry_index_bars",
                    action=action,
                    path=path,
                    source_paths=_candidate_paths(candidates),
                    bars=bars,
                    details=_bar_load_details(
                        requested_start_date=start_date,
                        requested_end_date=end_date,
                        minimum_start_date=run_plan.run.from_date,
                    ),
                ),
            )

    if provider is None:
        raise ValueError("provider is required when industry index snapshots must be refreshed or created")

    bars = provider.fetch_industry_index_daily_bars(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        source=source,
    )
    write_index_bars_parquet(bars, path)
    return IndexBarsLoadResult(
        bars=bars,
        provenance=_snapshot_provenance(
            snapshot_type="industry_index_bars",
            action="created",
            path=path,
            bars=bars,
            details=_bar_load_details(
                requested_start_date=start_date,
                requested_end_date=end_date,
                minimum_start_date=run_plan.run.from_date,
                warmup_incomplete=not _index_bars_cover_date_range(
                    bars,
                    start_date=start_date,
                    end_date=end_date,
                ),
            ),
        ),
    )


def _load_discovered_industry_index_bars(
    run_plan: RunPlan,
    *,
    symbol: str,
    source: str,
    start_date: date,
    end_date: date,
    snapshot_read_cache: SnapshotReadCache | None = None,
) -> tuple[tuple[IndexBar, ...], tuple[IndexBarsSnapshotCandidate, ...]]:
    candidates = discover_industry_index_bars_snapshot_paths(
        run_plan.data.snapshot_root,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        source=source,
    )
    return _read_index_bar_candidates(candidates, snapshot_read_cache=snapshot_read_cache), candidates


def _read_index_bar_candidates(
    candidates: tuple[IndexBarsSnapshotCandidate, ...],
    *,
    snapshot_read_cache: SnapshotReadCache | None = None,
) -> tuple[IndexBar, ...]:
    bars: list[IndexBar] = []
    for candidate in candidates:
        bars.extend(read_index_bars_parquet(candidate.path, cache=snapshot_read_cache))
    return _deduplicate_index_bars(bars)


def _deduplicate_index_bars(bars: tuple[IndexBar, ...] | list[IndexBar]) -> tuple[IndexBar, ...]:
    bars_by_key = {
        (bar.symbol, bar.trade_date): bar
        for bar in bars
    }
    return tuple(sorted(bars_by_key.values(), key=lambda bar: (bar.symbol, bar.trade_date)))


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
        snapshot_provenance=prepared.snapshot_provenance,
        calculation_bar_count=len(prepared.calculation_bars),
    )
