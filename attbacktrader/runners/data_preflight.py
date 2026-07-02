"""Preflight market data inputs before running a full backtest."""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from threading import Lock

from attbacktrader.config import RunPlan, TradableSeriesConfig
from attbacktrader.config.models import SeriesSelection
from attbacktrader.data.providers import RunDataProvider
from attbacktrader.data.quality import DataQualityIssue
from attbacktrader.data.snapshots import SnapshotProvenance, SnapshotReadCache
from attbacktrader.features import IndicatorRequirement, indicator_spec
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
    performance_profile: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class _PreflightSymbolOutcome:
    result: DataPreflightSymbolResult
    prepared_symbol: PreparedSymbolData | None = None


def run_data_preflight(
    run_plan: RunPlan,
    *,
    provider: RunDataProvider | None = None,
    snapshot_read_cache: SnapshotReadCache | None = None,
    prepared_symbol_cache: MutableMapping[str, PreparedSymbolData] | None = None,
    parallel_workers: int | None = None,
    max_symbols: int | None = None,
    indicator_alarm_threshold: float = 0.05,
    progress: Callable[[int, int, str, str], None] | None = None,
    event_progress: Callable[[Mapping[str, object]], None] | None = None,
) -> DataPreflightReport:
    if indicator_alarm_threshold < 0:
        raise ValueError("indicator_alarm_threshold must be non-negative")
    if max_symbols is not None and max_symbols <= 0:
        raise ValueError("max_symbols must be positive")
    if parallel_workers is not None and parallel_workers <= 0:
        raise ValueError("parallel_workers must be positive")

    series = run_plan.data.resolved_tradable_series
    if max_symbols is not None:
        series = series[:max_symbols]
    indicator_requirements = tuple(sorted(required_indicators_for_strategy_config(run_plan.strategy)))

    _emit_preflight_event(
        event_progress,
        stage="data_preflight",
        status="started",
        run_id=run_plan.run.id,
        total_symbols=len(series),
    )
    index_symbols = tuple(dict.fromkeys((*run_plan.data.decision_series.indexes, *run_plan.data.benchmark_series.indexes)))
    _emit_preflight_event(
        event_progress,
        stage="data_preflight_indexes",
        status="started",
        run_id=run_plan.run.id,
        index_count=len(index_symbols),
    )
    prepared_indexes, index_results = _prepare_common_indexes(
        run_plan,
        provider=provider,
        snapshot_read_cache=snapshot_read_cache,
    )
    _emit_preflight_event(
        event_progress,
        stage="data_preflight_indexes",
        status="completed",
        run_id=run_plan.run.id,
        index_count=len(index_results),
        error_count=sum(1 for result in index_results if result.status == "error"),
    )
    _emit_preflight_event(
        event_progress,
        stage="data_preflight_industry_indexes",
        status="started",
        run_id=run_plan.run.id,
        index_count=len(run_plan.data.industry_series.indexes),
    )
    _, industry_index_results = _prepare_common_industry_indexes(
        run_plan,
        provider=provider,
        snapshot_read_cache=snapshot_read_cache,
    )
    _emit_preflight_event(
        event_progress,
        stage="data_preflight_industry_indexes",
        status="completed",
        run_id=run_plan.run.id,
        index_count=len(industry_index_results),
        error_count=sum(1 for result in industry_index_results if result.status == "error"),
    )
    trading_calendar = _trading_calendar_for_run(run_plan, prepared_indexes)

    symbol_results: list[DataPreflightSymbolResult] = []
    running_ok_count = 0
    running_warning_count = 0
    running_failed_count = 0
    symbol_prepare_phase_seconds: dict[str, float] = {}
    symbol_prepare_phase_counts: dict[str, int] = {}
    symbol_prepare_phase_lock = Lock()
    resolved_parallel_workers = _resolve_preflight_parallel_workers(
        run_plan,
        provider=provider,
        symbol_count=len(series),
        parallel_workers=parallel_workers,
    )

    def record_symbol_prepare_phase(phase: str, seconds: float) -> None:
        with symbol_prepare_phase_lock:
            symbol_prepare_phase_seconds[phase] = symbol_prepare_phase_seconds.get(phase, 0.0) + seconds
            symbol_prepare_phase_counts[phase] = symbol_prepare_phase_counts.get(phase, 0) + 1

    _emit_preflight_event(
        event_progress,
        stage="data_preflight_symbols",
        status="started",
        run_id=run_plan.run.id,
        total_symbols=len(series),
        parallel_worker_count=resolved_parallel_workers,
    )
    symbols_started_at = time.perf_counter()

    def record_symbol_outcome(
        *,
        processed_count: int,
        symbol_position: int,
        item: TradableSeriesConfig,
        outcome: _PreflightSymbolOutcome,
    ) -> None:
        nonlocal running_ok_count, running_warning_count, running_failed_count
        result = outcome.result
        if prepared_symbol_cache is not None and outcome.prepared_symbol is not None:
            prepared_symbol_cache[item.symbol] = outcome.prepared_symbol
        if result.status == "ok":
            running_ok_count += 1
        elif result.status == "warning":
            running_warning_count += 1
        elif result.status == "error":
            running_failed_count += 1
        if progress is not None:
            progress(processed_count, len(series), item.symbol, result.status)
        _emit_preflight_event(
            event_progress,
            stage="data_preflight_symbols",
            status="running",
            run_id=run_plan.run.id,
            processed_symbol_count=processed_count,
            total_symbols=len(series),
            symbol=item.symbol,
            symbol_position=symbol_position,
            symbol_status=result.status,
            ok_symbol_count=running_ok_count,
            warning_symbol_count=running_warning_count,
            failed_symbol_count=running_failed_count,
        )

    if resolved_parallel_workers == 1:
        for index, item in enumerate(series, start=1):
            outcome = _preflight_symbol(
                run_plan,
                series=item,
                provider=provider,
                indicator_requirements=indicator_requirements,
                indicator_alarm_threshold=indicator_alarm_threshold,
                trading_calendar=trading_calendar,
                snapshot_read_cache=snapshot_read_cache,
                phase_timer=record_symbol_prepare_phase,
            )
            symbol_results.append(outcome.result)
            record_symbol_outcome(
                processed_count=index,
                symbol_position=index,
                item=item,
                outcome=outcome,
            )
    else:
        results_by_position: list[DataPreflightSymbolResult | None] = [None] * len(series)
        completed_count = 0
        with ThreadPoolExecutor(max_workers=resolved_parallel_workers) as executor:
            futures = {
                executor.submit(
                    _preflight_symbol,
                    run_plan,
                    series=item,
                    provider=provider,
                    indicator_requirements=indicator_requirements,
                    indicator_alarm_threshold=indicator_alarm_threshold,
                    trading_calendar=trading_calendar,
                    snapshot_read_cache=snapshot_read_cache,
                    phase_timer=record_symbol_prepare_phase,
                ): (index, item)
                for index, item in enumerate(series, start=1)
            }
            for future in as_completed(futures):
                index, item = futures[future]
                outcome = future.result()
                completed_count += 1
                results_by_position[index - 1] = outcome.result
                record_symbol_outcome(
                    processed_count=completed_count,
                    symbol_position=index,
                    item=item,
                    outcome=outcome,
                )
        symbol_results.extend(
            result
            for result in results_by_position
            if result is not None
        )
    symbols_wall_seconds = time.perf_counter() - symbols_started_at

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
    performance_profile = _data_preflight_performance_profile(
        total_symbols=len(series),
        symbol_results=symbol_results,
        symbol_prepare_phase_seconds=symbol_prepare_phase_seconds,
        symbol_prepare_phase_counts=symbol_prepare_phase_counts,
        prepared_symbol_cache=prepared_symbol_cache,
        parallel_worker_count=resolved_parallel_workers,
        symbols_wall_seconds=symbols_wall_seconds,
    )

    _emit_preflight_event(
        event_progress,
        stage="data_preflight_symbols",
        status="completed",
        run_id=run_plan.run.id,
        total_symbols=len(series),
        ok_symbol_count=ok_count,
        warning_symbol_count=warning_count,
        failed_symbol_count=failed_count,
        parallel_worker_count=resolved_parallel_workers,
        performance_profile=performance_profile,
    )
    _emit_preflight_event(
        event_progress,
        stage="data_preflight",
        status="completed",
        run_id=run_plan.run.id,
        preflight_status=status,
        total_symbols=len(series),
        ok_symbol_count=ok_count,
        warning_symbol_count=warning_count,
        failed_symbol_count=failed_count,
        parallel_worker_count=resolved_parallel_workers,
        performance_profile=performance_profile,
    )

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
        performance_profile=performance_profile,
    )


def _emit_preflight_event(
    event_progress: Callable[[Mapping[str, object]], None] | None,
    **event: object,
) -> None:
    if event_progress is None:
        return
    event_progress(event)


def _data_preflight_performance_profile(
    *,
    total_symbols: int,
    symbol_results: Sequence[DataPreflightSymbolResult],
    symbol_prepare_phase_seconds: Mapping[str, float],
    symbol_prepare_phase_counts: Mapping[str, int],
    prepared_symbol_cache: Mapping[str, PreparedSymbolData] | None,
    parallel_worker_count: int,
    symbols_wall_seconds: float,
) -> dict[str, object]:
    return {
        "symbol_count": total_symbols,
        "checked_symbol_count": len(symbol_results),
        "ok_symbol_count": sum(1 for result in symbol_results if result.status == "ok"),
        "warning_symbol_count": sum(1 for result in symbol_results if result.status == "warning"),
        "failed_symbol_count": sum(1 for result in symbol_results if result.status == "error"),
        "prepared_symbol_cache_count": len(prepared_symbol_cache) if prepared_symbol_cache is not None else 0,
        "parallel_worker_count": parallel_worker_count,
        "snapshot_profile": _data_preflight_snapshot_profile(symbol_results),
        "symbol_prepare_phase_profile": _symbol_prepare_phase_profile(
            total_symbols=total_symbols,
            phase_seconds=symbol_prepare_phase_seconds,
            phase_counts=symbol_prepare_phase_counts,
            parallel_worker_count=parallel_worker_count,
            wall_seconds=symbols_wall_seconds,
        ),
    }


def _data_preflight_snapshot_profile(
    symbol_results: Sequence[DataPreflightSymbolResult],
) -> dict[str, object]:
    action_counts: dict[str, int] = {}
    type_action_counts: dict[str, int] = {}
    source_snapshot_reference_count = 0

    for result in symbol_results:
        if result.snapshot_action is not None:
            _increment_count(action_counts, result.snapshot_action)
            _increment_count(type_action_counts, f"daily_bars.{result.snapshot_action}")
            if result.snapshot_path is not None:
                source_snapshot_reference_count += 1
        for action in result.indicator_snapshot_actions:
            _increment_count(action_counts, action)
            _increment_count(type_action_counts, f"indicator.{action}")
        source_snapshot_reference_count += len(result.indicator_snapshot_paths)
        if result.tradability_snapshot_action is not None:
            _increment_count(action_counts, result.tradability_snapshot_action)
            _increment_count(type_action_counts, f"tradability.{result.tradability_snapshot_action}")
            if result.tradability_snapshot_path is not None:
                source_snapshot_reference_count += 1

    return {
        "action_counts": action_counts,
        "type_action_counts": type_action_counts,
        "source_snapshot_reference_count": source_snapshot_reference_count,
        "source_snapshot_read_count_lower_bound": source_snapshot_reference_count,
    }


def _symbol_prepare_phase_profile(
    *,
    total_symbols: int,
    phase_seconds: Mapping[str, float],
    phase_counts: Mapping[str, int],
    parallel_worker_count: int,
    wall_seconds: float,
) -> dict[str, object]:
    rounded_seconds = {
        phase: round(seconds, 6)
        for phase, seconds in sorted(phase_seconds.items())
    }
    counts = {
        phase: phase_counts[phase]
        for phase in sorted(phase_counts)
    }
    avg_seconds = {
        phase: round(rounded_seconds[phase] / counts[phase], 6)
        for phase in rounded_seconds
        if counts.get(phase, 0) > 0
    }
    return {
        "symbol_count": total_symbols,
        "measured_symbol_count": max(counts.values(), default=0),
        "parallel_worker_count": parallel_worker_count,
        "phase_seconds": rounded_seconds,
        "phase_counts": counts,
        "phase_avg_seconds": avg_seconds,
        "recorded_seconds": round(sum(rounded_seconds.values()), 6),
        "wall_seconds": round(wall_seconds, 6),
    }


def _resolve_preflight_parallel_workers(
    run_plan: RunPlan,
    *,
    provider: RunDataProvider | None,
    symbol_count: int,
    parallel_workers: int | None,
) -> int:
    if symbol_count <= 1:
        return 1
    if provider is not None or run_plan.data.refresh_snapshots:
        return 1
    if parallel_workers is not None:
        return min(parallel_workers, symbol_count)
    return min(symbol_count, os.cpu_count() or 1, 4)


def _increment_count(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


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
    snapshot_read_cache: SnapshotReadCache | None,
    phase_timer: Callable[[str, float], None] | None,
) -> _PreflightSymbolOutcome:
    try:
        prepared = _prepare_symbol_data(
            _single_symbol_run_plan(run_plan, series),
            series=series,
            provider=provider,
            indicator_requirements=indicator_requirements,
            trading_calendar=trading_calendar,
            snapshot_read_cache=snapshot_read_cache,
            phase_timer=phase_timer,
        )
    except Exception as exc:
        return _PreflightSymbolOutcome(
            result=DataPreflightSymbolResult(
                symbol=series.symbol,
                asset_type=series.asset_type,
                adjustment=series.price_adjustment or "none",
                status="error",
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
        )

    return _PreflightSymbolOutcome(
        result=_symbol_result_from_prepared(
            run_plan,
            prepared,
            indicator_requirements=indicator_requirements,
            indicator_alarm_threshold=indicator_alarm_threshold,
        ),
        prepared_symbol=prepared,
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
    timeframe_snapshots = tuple(
        sorted(
            (
                snapshot
                for snapshot in prepared.indicator_snapshots
                if snapshot.timeframe == requirement.timeframe
            ),
            key=lambda snapshot: snapshot.trade_date,
        )
    )
    if not timeframe_snapshots:
        return IndicatorCoverage(
            name=requirement.name,
            timeframe=requirement.timeframe,
            total_count=0,
            available_count=0,
            missing_count=0,
            missing_ratio=1.0,
            status="error",
        )

    warmup_bars = indicator_spec(requirement.name).warmup_bars
    eligible_snapshots = tuple(
        snapshot
        for snapshot in timeframe_snapshots[max(0, warmup_bars - 1) :]
        if start_date <= snapshot.trade_date <= end_date
    )
    available_count = sum(1 for snapshot in eligible_snapshots if snapshot.has_indicator(requirement.name))
    total_count = len(eligible_snapshots)
    missing_count = max(0, total_count - available_count)
    missing_ratio = missing_count / total_count if total_count else 0.0
    status = "ok" if missing_ratio <= threshold else "error"
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
    snapshot_read_cache: SnapshotReadCache | None,
) -> tuple[dict[str, PreparedIndexData], tuple[DataPreflightIndexResult, ...]]:
    try:
        prepared = _prepare_index_data_by_symbol(
            run_plan,
            provider=provider,
            snapshot_read_cache=snapshot_read_cache,
        )
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
    snapshot_read_cache: SnapshotReadCache | None,
) -> tuple[dict[str, PreparedIndexData], tuple[DataPreflightIndexResult, ...]]:
    try:
        prepared = _prepare_industry_index_data_by_symbol(
            run_plan,
            provider=provider,
            snapshot_read_cache=snapshot_read_cache,
        )
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
