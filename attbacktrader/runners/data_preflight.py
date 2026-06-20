"""Preflight market data inputs before running a full backtest."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from attbacktrader.config import RunPlan, TradableSeriesConfig
from attbacktrader.config.models import SeriesSelection
from attbacktrader.data.providers import RunDataProvider
from attbacktrader.data.quality import DataQualityIssue
from attbacktrader.data.snapshots import SnapshotProvenance
from attbacktrader.features import IndicatorRequirement
from attbacktrader.runners.prepared_data import (
    PreparedIndexData,
    PreparedSymbolData,
    _prepare_index_data_by_symbol,
    _prepare_industry_index_data_by_symbol,
    _prepare_symbol_data,
    _trading_calendar_for_run,
)
from attbacktrader.strategies.bindings import required_indicators_for_strategy_config


@dataclass(frozen=True)
class IndicatorCoverage:
    name: str
    timeframe: str
    total_count: int
    available_count: int
    missing_count: int
    missing_ratio: float
    status: str


@dataclass(frozen=True)
class TradabilityCoverage:
    enabled: bool
    status_count: int
    expected_count: int
    missing_count: int
    missing_ratio: float
    status: str


@dataclass(frozen=True)
class DataPreflightSymbolResult:
    symbol: str
    asset_type: str
    adjustment: str
    status: str
    bar_count: int = 0
    bar_start_date: date | None = None
    bar_end_date: date | None = None
    calculation_start_date: date | None = None
    snapshot_path: Path | None = None
    snapshot_action: str | None = None
    indicator_snapshot_paths: tuple[Path, ...] = ()
    indicator_snapshot_actions: tuple[str, ...] = ()
    indicator_coverage: tuple[IndicatorCoverage, ...] = ()
    tradability_snapshot_path: Path | None = None
    tradability_snapshot_action: str | None = None
    tradability_coverage: TradabilityCoverage | None = None
    data_quality_issues: tuple[DataQualityIssue, ...] = ()
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class DataPreflightIndexResult:
    symbol: str
    status: str
    bar_count: int = 0
    calculation_bar_count: int = 0
    snapshot_path: Path | None = None
    snapshot_action: str | None = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class DataPreflightReport:
    schema: str
    run_id: str
    status: str
    run_start_date: date
    run_end_date: date
    requested_symbol_count: int
    checked_symbol_count: int
    ok_symbol_count: int
    warning_symbol_count: int
    failed_symbol_count: int
    indicator_alarm_threshold: float
    required_indicators: tuple[str, ...]
    index_results: tuple[DataPreflightIndexResult, ...]
    industry_index_results: tuple[DataPreflightIndexResult, ...]
    symbol_results: tuple[DataPreflightSymbolResult, ...]
    issue_summary: dict[str, int]
    error_summary: dict[str, int]


def run_data_preflight(
    run_plan: RunPlan,
    *,
    provider: RunDataProvider | None = None,
    max_symbols: int | None = None,
    indicator_alarm_threshold: float = 0.05,
    progress: Callable[[int, int, str, str], None] | None = None,
) -> DataPreflightReport:
    if indicator_alarm_threshold < 0:
        raise ValueError("indicator_alarm_threshold must be non-negative")
    if max_symbols is not None and max_symbols <= 0:
        raise ValueError("max_symbols must be positive")

    series = run_plan.data.resolved_tradable_series
    if max_symbols is not None:
        series = series[:max_symbols]
    indicator_requirements = tuple(sorted(required_indicators_for_strategy_config(run_plan.strategy)))

    prepared_indexes, index_results = _prepare_common_indexes(run_plan, provider=provider)
    _, industry_index_results = _prepare_common_industry_indexes(run_plan, provider=provider)
    trading_calendar = _trading_calendar_for_run(run_plan, prepared_indexes)

    symbol_results: list[DataPreflightSymbolResult] = []
    for index, item in enumerate(series, start=1):
        result = _preflight_symbol(
            run_plan,
            series=item,
            provider=provider,
            indicator_requirements=indicator_requirements,
            indicator_alarm_threshold=indicator_alarm_threshold,
            trading_calendar=trading_calendar,
        )
        symbol_results.append(result)
        if progress is not None:
            progress(index, len(series), item.symbol, result.status)

    issue_summary = _issue_summary(symbol_results)
    error_summary = _error_summary(symbol_results, index_results, industry_index_results)
    ok_count = sum(1 for result in symbol_results if result.status == "ok")
    warning_count = sum(1 for result in symbol_results if result.status == "warning")
    failed_count = sum(1 for result in symbol_results if result.status == "error")
    status = "ok"
    if failed_count or any(result.status == "error" for result in (*index_results, *industry_index_results)):
        status = "error"
    elif warning_count or any(result.status == "warning" for result in (*index_results, *industry_index_results)):
        status = "warning"

    return DataPreflightReport(
        schema="attbacktrader.data_preflight.v1",
        run_id=run_plan.run.id,
        status=status,
        run_start_date=run_plan.run.from_date,
        run_end_date=run_plan.run.to_date,
        requested_symbol_count=len(run_plan.data.resolved_tradable_series),
        checked_symbol_count=len(symbol_results),
        ok_symbol_count=ok_count,
        warning_symbol_count=warning_count,
        failed_symbol_count=failed_count,
        indicator_alarm_threshold=indicator_alarm_threshold,
        required_indicators=tuple(f"{item.name}:{item.timeframe}" for item in indicator_requirements),
        index_results=index_results,
        industry_index_results=industry_index_results,
        symbol_results=tuple(symbol_results),
        issue_summary=issue_summary,
        error_summary=error_summary,
    )


def render_data_preflight_summary_text(report: DataPreflightReport) -> str:
    lines = [
        f"data_preflight status={report.status}",
        f"run_id={report.run_id}",
        f"symbols={report.checked_symbol_count}/{report.requested_symbol_count} "
        f"ok={report.ok_symbol_count} warning={report.warning_symbol_count} error={report.failed_symbol_count}",
        "required_indicators=" + ",".join(report.required_indicators),
    ]
    if report.issue_summary:
        lines.append("issue_summary=" + ",".join(f"{key}:{value}" for key, value in sorted(report.issue_summary.items())))
    if report.error_summary:
        lines.append("error_summary=" + ",".join(f"{key}:{value}" for key, value in sorted(report.error_summary.items())))

    problem_symbols = [
        result
        for result in report.symbol_results
        if result.status != "ok"
    ][:10]
    for result in problem_symbols:
        lines.append(
            f"{result.symbol} status={result.status} bars={result.bar_count} "
            f"error={result.error_type or '-'}"
        )
    return "\n".join(lines)


def write_data_preflight_report(report: DataPreflightReport, path: str | Path) -> Path:
    import json

    from attbacktrader.reports import to_jsonable

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(to_jsonable(report), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output_path


def _preflight_symbol(
    run_plan: RunPlan,
    *,
    series: TradableSeriesConfig,
    provider: RunDataProvider | None,
    indicator_requirements: tuple[IndicatorRequirement, ...],
    indicator_alarm_threshold: float,
    trading_calendar,
) -> DataPreflightSymbolResult:
    try:
        prepared = _prepare_symbol_data(
            _single_symbol_run_plan(run_plan, series),
            series=series,
            provider=provider,
            indicator_requirements=indicator_requirements,
            trading_calendar=trading_calendar,
        )
    except Exception as exc:
        return DataPreflightSymbolResult(
            symbol=series.symbol,
            asset_type=series.asset_type,
            adjustment=series.price_adjustment or "none",
            status="error",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )

    return _symbol_result_from_prepared(
        run_plan,
        prepared,
        indicator_requirements=indicator_requirements,
        indicator_alarm_threshold=indicator_alarm_threshold,
    )


def _single_symbol_run_plan(run_plan: RunPlan, series: TradableSeriesConfig) -> RunPlan:
    data = run_plan.data.model_copy(
        update={
            "symbols": (),
            "stock_pool_file": None,
            "tradable_series": (series,),
            "decision_series": SeriesSelection(indexes=()),
            "benchmark_series": SeriesSelection(indexes=()),
            "industry_series": run_plan.data.industry_series.model_copy(update={"indexes": ()}),
        }
    )
    return run_plan.model_copy(update={"data": data})


def _symbol_result_from_prepared(
    run_plan: RunPlan,
    prepared: PreparedSymbolData,
    *,
    indicator_requirements: tuple[IndicatorRequirement, ...],
    indicator_alarm_threshold: float,
) -> DataPreflightSymbolResult:
    indicator_coverage = tuple(
        _indicator_coverage(
            prepared,
            requirement=requirement,
            threshold=indicator_alarm_threshold,
            start_date=run_plan.run.from_date,
            end_date=run_plan.run.to_date,
        )
        for requirement in indicator_requirements
    )
    tradability_coverage = _tradability_coverage(prepared)
    has_indicator_alarm = any(item.status == "error" for item in indicator_coverage)
    has_quality_warning = any(issue.severity in {"warning", "error"} for issue in prepared.data_quality_issues)
    has_tradability_warning = tradability_coverage is not None and tradability_coverage.status != "ok"
    status = "error" if has_indicator_alarm else "warning" if has_quality_warning or has_tradability_warning else "ok"
    bar_dates = tuple(bar.trade_date for bar in prepared.bars)

    return DataPreflightSymbolResult(
        symbol=prepared.symbol,
        asset_type=prepared.asset_type,
        adjustment=prepared.adjustment,
        status=status,
        bar_count=len(prepared.bars),
        bar_start_date=min(bar_dates) if bar_dates else None,
        bar_end_date=max(bar_dates) if bar_dates else None,
        calculation_start_date=_provenance_requested_start_date(prepared.snapshot_provenance),
        snapshot_path=prepared.snapshot_path,
        snapshot_action=prepared.snapshot_provenance.action,
        indicator_snapshot_paths=prepared.indicator_snapshot_paths,
        indicator_snapshot_actions=tuple(item.action for item in prepared.indicator_snapshot_provenance),
        indicator_coverage=indicator_coverage,
        tradability_snapshot_path=prepared.tradability_snapshot_path,
        tradability_snapshot_action=(
            prepared.tradability_snapshot_provenance.action
            if prepared.tradability_snapshot_provenance is not None
            else None
        ),
        tradability_coverage=tradability_coverage,
        data_quality_issues=prepared.data_quality_issues,
    )


def _indicator_coverage(
    prepared: PreparedSymbolData,
    *,
    requirement: IndicatorRequirement,
    threshold: float,
    start_date: date,
    end_date: date,
) -> IndicatorCoverage:
    snapshots = tuple(
        snapshot
        for snapshot in prepared.indicator_snapshots
        if snapshot.timeframe == requirement.timeframe
        and start_date <= snapshot.trade_date <= end_date
    )
    available_count = sum(1 for snapshot in snapshots if snapshot.has_indicator(requirement.name))
    total_count = len(snapshots)
    missing_count = max(0, total_count - available_count)
    missing_ratio = missing_count / total_count if total_count else 1.0
    status = "ok" if total_count and missing_ratio <= threshold else "error"
    return IndicatorCoverage(
        name=requirement.name,
        timeframe=requirement.timeframe,
        total_count=total_count,
        available_count=available_count,
        missing_count=missing_count,
        missing_ratio=missing_ratio,
        status=status,
    )


def _tradability_coverage(prepared: PreparedSymbolData) -> TradabilityCoverage | None:
    if prepared.tradability_snapshot_path is None:
        return None
    bar_dates = {bar.trade_date for bar in prepared.bars}
    status_dates = {status.trade_date for status in prepared.tradability_statuses}
    missing_count = len(bar_dates - status_dates)
    expected_count = len(bar_dates)
    missing_ratio = missing_count / expected_count if expected_count else 1.0
    return TradabilityCoverage(
        enabled=True,
        status_count=len(status_dates),
        expected_count=expected_count,
        missing_count=missing_count,
        missing_ratio=missing_ratio,
        status="ok" if expected_count and missing_ratio <= 0.05 else "warning",
    )


def _prepare_common_indexes(
    run_plan: RunPlan,
    *,
    provider: RunDataProvider | None,
) -> tuple[dict[str, PreparedIndexData], tuple[DataPreflightIndexResult, ...]]:
    try:
        prepared = _prepare_index_data_by_symbol(run_plan, provider=provider)
    except Exception as exc:
        symbols = tuple(dict.fromkeys((*run_plan.data.decision_series.indexes, *run_plan.data.benchmark_series.indexes)))
        return {}, tuple(
            DataPreflightIndexResult(
                symbol=symbol,
                status="error",
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            for symbol in symbols
        )

    return prepared, tuple(_index_result(item) for item in prepared.values())


def _prepare_common_industry_indexes(
    run_plan: RunPlan,
    *,
    provider: RunDataProvider | None,
) -> tuple[dict[str, PreparedIndexData], tuple[DataPreflightIndexResult, ...]]:
    try:
        prepared = _prepare_industry_index_data_by_symbol(run_plan, provider=provider)
    except Exception as exc:
        return {}, tuple(
            DataPreflightIndexResult(
                symbol=symbol,
                status="error",
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            for symbol in run_plan.data.industry_series.indexes
        )

    return prepared, tuple(_index_result(item) for item in prepared.values())


def _index_result(prepared: PreparedIndexData) -> DataPreflightIndexResult:
    status = "ok" if prepared.bars else "error"
    return DataPreflightIndexResult(
        symbol=prepared.symbol,
        status=status,
        bar_count=len(prepared.bars),
        calculation_bar_count=len(prepared.calculation_bars),
        snapshot_path=prepared.snapshot_path,
        snapshot_action=prepared.snapshot_provenance.action,
    )


def _provenance_requested_start_date(provenance: SnapshotProvenance) -> date | None:
    value = provenance.details.get("requested_start_date")
    if value is None:
        return provenance.start_date
    return date.fromisoformat(str(value))


def _issue_summary(results: list[DataPreflightSymbolResult]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for result in results:
        for issue in result.data_quality_issues:
            counter[f"{issue.scope}.{issue.code}"] += 1
        for coverage in result.indicator_coverage:
            if coverage.status != "ok":
                counter[f"indicator.{coverage.name}:{coverage.timeframe}"] += 1
        if result.tradability_coverage is not None and result.tradability_coverage.status != "ok":
            counter["tradability.missing_status"] += 1
    return dict(sorted(counter.items()))


def _error_summary(
    symbol_results: list[DataPreflightSymbolResult],
    index_results: tuple[DataPreflightIndexResult, ...],
    industry_index_results: tuple[DataPreflightIndexResult, ...],
) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for result in symbol_results:
        if result.error_type:
            counter[f"symbol.{result.error_type}"] += 1
    for result in (*index_results, *industry_index_results):
        if result.error_type:
            counter[f"index.{result.error_type}"] += 1
    return dict(sorted(counter.items()))
