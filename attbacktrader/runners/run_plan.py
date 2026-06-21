"""Execute validated run plans against prepared market snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from attbacktrader.analysis import AnalysisEvidence, enrich_backtest_report
from attbacktrader.config import RunPlan
from attbacktrader.data.providers import RunDataProvider
from attbacktrader.data.quality import DataQualityIssue
from attbacktrader.data.snapshots import SnapshotProvenance
from attbacktrader.engines.backtrader import (
    BacktraderAShareSettings,
    BacktraderBrokerSettings,
    run_trend_template_v1_portfolio_backtrader,
)
from attbacktrader.engines.business import (
    BaomaBusinessRunConfig,
    BaomaBusinessRunResult,
    LifecycleExecutionEvent,
    LifecyclePositionSnapshot,
    SecondScaleOutConfirmationRule,
    run_baoma_v1_business,
    run_trend_template_v1_portfolio_business,
)
from attbacktrader.engines.ledger import EquityCurvePoint, ExecutionAuditEvent, PositionSnapshot
from attbacktrader.reports import (
    PostExitAnalysisReport,
    build_post_exit_analysis,
    build_report_from_closed_trades,
    build_report_from_equity_curve,
    build_report_from_trend_result,
)
from attbacktrader.reports.models import BacktestReport
from attbacktrader.runners.data_preflight import (
    DataPreflightReport,
    DataPreflightSymbolResult,
    run_data_preflight,
)
from attbacktrader.runners.prepared_data import (
    IndexSeriesResult,
    IndustryClassificationResult,
    IndustryMembershipResult,
    PreparedSymbolData,
    prepare_run_data,
)
from attbacktrader.strategies import (
    EntryAttributionContext,
    EntryAttributionFilterCondition,
    EntryAttributionFilterRule,
    TradeIntent,
    build_entry_attribution_context,
    entry_attribution_factor_keys,
)
from attbacktrader.strategies.bindings import build_strategy_template
from attbacktrader.strategies.templates import ClosedTrade, Position, TrendTemplateV1PortfolioResult, TrendTemplateV1Result


@dataclass(frozen=True)
class SymbolRunResult:
    symbol: str
    asset_type: str
    adjustment: str
    bar_count: int
    snapshot_path: Path
    indicator_snapshot_path: Path
    indicator_snapshot_paths: tuple[Path, ...]
    snapshot_provenance: SnapshotProvenance
    indicator_snapshot_provenance: tuple[SnapshotProvenance, ...]
    data_quality_issues: tuple[DataQualityIssue, ...]
    tradability_snapshot_path: Path | None
    tradability_snapshot_provenance: SnapshotProvenance | None
    intents: tuple[TradeIntent, ...]
    intent_count: int
    closed_trades: tuple[ClosedTrade, ...]
    open_position: Position | None
    report: BacktestReport


@dataclass(frozen=True)
class RunPlanExecutionResult:
    run_id: str
    engine: str
    adjustment: str
    symbols: tuple[str, ...]
    symbol_results: tuple[SymbolRunResult, ...]
    benchmark_results: tuple[IndexSeriesResult, ...]
    decision_series_results: tuple[IndexSeriesResult, ...]
    industry_index_results: tuple[IndexSeriesResult, ...]
    industry_classification_result: IndustryClassificationResult | None
    industry_membership_results: tuple[IndustryMembershipResult, ...]
    signal_audit: tuple[TradeIntent, ...]
    closed_trades: tuple[ClosedTrade, ...]
    open_positions: tuple[Position, ...]
    equity_curve: tuple[EquityCurvePoint, ...]
    position_snapshots: tuple[PositionSnapshot, ...]
    execution_audit: tuple[ExecutionAuditEvent, ...]
    lifecycle_events: tuple[LifecycleExecutionEvent, ...]
    lifecycle_snapshots: tuple[LifecyclePositionSnapshot, ...]
    post_exit_analysis: PostExitAnalysisReport
    report: BacktestReport
    final_cash: float | None
    final_value: float | None
    data_preflight_report: object | None = None
    stock_pool_filter: object | None = None
    attribution_factor_selection: object | None = None


@dataclass(frozen=True)
class StockPoolFilterSymbol:
    symbol: str
    status: str
    bar_count: int
    bar_start_date: str | None
    bar_end_date: str | None
    error_type: str | None
    error_message: str | None
    indicator_alarms: tuple[str, ...]
    data_quality_issue_codes: tuple[str, ...]


@dataclass(frozen=True)
class StockPoolAutoFilterResult:
    schema: str
    enabled: bool
    source_pool_file: Path | None
    allowed_statuses: tuple[str, ...]
    original_count: int
    kept_count: int
    warning_count: int
    excluded_count: int
    kept_symbols: tuple[str, ...]
    warning_symbols: tuple[StockPoolFilterSymbol, ...]
    excluded_symbols: tuple[StockPoolFilterSymbol, ...]


def execute_run_plan(
    run_plan: RunPlan,
    *,
    provider: RunDataProvider | None = None,
) -> RunPlanExecutionResult:
    execution_run_plan, data_preflight_report, stock_pool_filter = _run_plan_with_auto_stock_pool_filter(
        run_plan,
        provider=provider,
    )
    prepared_data = prepare_run_data(execution_run_plan, provider=provider)
    strategy_template = build_strategy_template(execution_run_plan.strategy)

    if execution_run_plan.execution.engine == "backtrader":
        risk_group_by_symbol = prepared_data.risk_group_by_symbol(
            level=getattr(strategy_template.sizing_method, "risk_group_level", 1)
        )
        entry_attribution_context = _entry_attribution_context(execution_run_plan, prepared_data)
        engine_result = run_trend_template_v1_portfolio_backtrader(
            prepared_data.bars_by_symbol,
            initial_cash=execution_run_plan.broker.initial_cash,
            stake=execution_run_plan.execution.stake,
            indicators_by_symbol=prepared_data.indicators_by_symbol,
            tradability_by_symbol=prepared_data.tradability_by_symbol,
            risk_group_by_symbol=risk_group_by_symbol,
            entry_attribution_context=entry_attribution_context,
            entry_method=strategy_template.entry_method,
            profit_taking_method=strategy_template.profit_taking_method,
            stop_loss_method=strategy_template.stop_loss_method,
            add_on_method=strategy_template.add_on_method,
            sizing_method=strategy_template.sizing_method,
            broker_settings=BacktraderBrokerSettings(
                commission_rate=execution_run_plan.broker.commission_rate,
                stamp_tax_rate=execution_run_plan.broker.stamp_tax_rate,
                transfer_fee_rate=execution_run_plan.broker.transfer_fee_rate,
                slippage_type=execution_run_plan.broker.slippage.type,
                slippage_value=execution_run_plan.broker.slippage.value,
            ),
            ashare_settings=BacktraderAShareSettings(
                enabled=execution_run_plan.constraints.ashare.enabled,
                board_lot_size=execution_run_plan.constraints.ashare.board_lot_size,
                suspension_enabled=execution_run_plan.constraints.ashare.suspension,
                limit_up_down_enabled=execution_run_plan.constraints.ashare.limit_up_down,
                t_plus_one_enabled=execution_run_plan.constraints.ashare.t_plus_one,
            ),
        )
        portfolio_result = engine_result.strategy_result
        final_cash = engine_result.final_cash
        final_value = engine_result.final_value
        equity_curve = engine_result.equity_curve
        position_snapshots = engine_result.position_snapshots
        execution_audit = engine_result.execution_audit
        lifecycle_events = engine_result.lifecycle_events
        lifecycle_snapshots = engine_result.lifecycle_snapshots
    elif execution_run_plan.execution.engine == "baoma_v1_business":
        engine_result = run_baoma_v1_business(
            prepared_data.bars_by_symbol,
            indicators_by_symbol=prepared_data.indicators_by_symbol,
            config=_baoma_business_config(execution_run_plan),
            entry_method=strategy_template.entry_method,
            profit_exit_method=strategy_template.profit_taking_method,
            stop_loss_method=strategy_template.stop_loss_method,
            add_on_method=strategy_template.add_on_method,
            entry_attribution_context=_baoma_post_trade_attribution_context(execution_run_plan, prepared_data),
        )
        portfolio_result = _portfolio_result_from_baoma(engine_result)
        final_cash = None
        final_value = None
        equity_curve = ()
        position_snapshots = ()
        execution_audit = _execution_audit_from_baoma(engine_result)
        lifecycle_events = engine_result.lifecycle_events
        lifecycle_snapshots = engine_result.lifecycle_snapshots
    else:
        risk_group_by_symbol = prepared_data.risk_group_by_symbol(
            level=getattr(strategy_template.sizing_method, "risk_group_level", 1)
        )
        entry_attribution_context = _entry_attribution_context(execution_run_plan, prepared_data)
        engine_result = run_trend_template_v1_portfolio_business(
            strategy_template,
            prepared_data.bars_by_symbol,
            initial_cash=execution_run_plan.broker.initial_cash,
            stake=execution_run_plan.execution.stake,
            indicators_by_symbol=prepared_data.indicators_by_symbol,
            risk_group_by_symbol=risk_group_by_symbol,
            entry_attribution_context=entry_attribution_context,
        )
        portfolio_result = engine_result.strategy_result
        final_cash = engine_result.final_cash
        final_value = engine_result.final_value
        equity_curve = engine_result.equity_curve
        position_snapshots = engine_result.position_snapshots
        execution_audit = ()
        lifecycle_events = engine_result.lifecycle_events
        lifecycle_snapshots = engine_result.lifecycle_snapshots

    symbol_results = _symbol_results_from_portfolio(
        execution_run_plan,
        prepared_by_symbol=prepared_data.symbol_data_by_symbol,
        portfolio_result=portfolio_result,
    )
    if equity_curve:
        base_report = build_report_from_equity_curve(
            equity_curve,
            closed_trades=portfolio_result.closed_trades,
            report_id=execution_run_plan.run.id,
            starting_equity=execution_run_plan.broker.initial_cash,
        )
    else:
        base_report = build_report_from_closed_trades(
            portfolio_result.closed_trades,
            report_id=execution_run_plan.run.id,
            starting_equity=execution_run_plan.broker.initial_cash,
        )
    report = enrich_backtest_report(
        execution_run_plan,
        base_report=base_report,
        closed_trades=portfolio_result.closed_trades,
        evidence=AnalysisEvidence(
            benchmark_bars_by_symbol=prepared_data.benchmark_bars_by_symbol(execution_run_plan),
            industry_index_bars_by_symbol=prepared_data.industry_index_bars_by_symbol(execution_run_plan),
            memberships_by_symbol=prepared_data.memberships_by_symbol,
            open_positions=portfolio_result.open_positions,
            execution_audit=execution_audit,
            final_cash=final_cash,
            final_value=final_value,
        ),
    )
    post_exit_analysis = build_post_exit_analysis(
        closed_trades=portfolio_result.closed_trades,
        bars_by_symbol=prepared_data.bars_by_symbol,
        signal_audit=portfolio_result.intents,
        window_days=execution_run_plan.analysis.post_exit.window_days,
        primary_window_days=execution_run_plan.analysis.post_exit.primary_window_days,
        sold_too_early_threshold=execution_run_plan.analysis.post_exit.sold_too_early_threshold,
        rebound_thresholds=execution_run_plan.analysis.post_exit.rebound_thresholds,
    )

    return RunPlanExecutionResult(
        run_id=execution_run_plan.run.id,
        engine=execution_run_plan.execution.engine,
        adjustment=prepared_data.adjustment_label,
        symbols=prepared_data.symbols,
        symbol_results=symbol_results,
        benchmark_results=prepared_data.benchmark_results(execution_run_plan),
        decision_series_results=prepared_data.decision_series_results(execution_run_plan),
        industry_index_results=prepared_data.industry_index_results(execution_run_plan),
        industry_classification_result=prepared_data.industry_classification_result,
        industry_membership_results=prepared_data.industry_membership_results,
        signal_audit=portfolio_result.intents,
        closed_trades=portfolio_result.closed_trades,
        open_positions=portfolio_result.open_positions,
        equity_curve=equity_curve,
        position_snapshots=position_snapshots,
        execution_audit=execution_audit,
        lifecycle_events=lifecycle_events,
        lifecycle_snapshots=lifecycle_snapshots,
        post_exit_analysis=post_exit_analysis,
        report=report,
        final_cash=final_cash,
        final_value=final_value,
        data_preflight_report=data_preflight_report,
        stock_pool_filter=stock_pool_filter,
        attribution_factor_selection=execution_run_plan.analysis.resolved_attribution_factor_selection,
    )


def _run_plan_with_auto_stock_pool_filter(
    run_plan: RunPlan,
    *,
    provider: RunDataProvider | None,
) -> tuple[RunPlan, DataPreflightReport | None, StockPoolAutoFilterResult | None]:
    if run_plan.data.stock_pool_file is None:
        return run_plan, None, None

    preflight_run_plan = _run_plan_reusing_snapshots(run_plan)
    preflight = run_data_preflight(preflight_run_plan, provider=provider)
    stock_pool_filter = _stock_pool_filter_from_preflight(run_plan, preflight)
    if not stock_pool_filter.kept_symbols:
        raise ValueError("stock pool auto filter excluded all symbols")

    kept = set(stock_pool_filter.kept_symbols)
    kept_series = tuple(
        series
        for series in run_plan.data.resolved_tradable_series
        if series.symbol in kept
    )
    filtered_data = run_plan.data.model_copy(
        update={
            "symbols": (),
            "stock_pool_file": None,
            "tradable_series": kept_series,
            "refresh_snapshots": False,
        }
    )
    return run_plan.model_copy(update={"data": filtered_data}), preflight, stock_pool_filter


def _run_plan_reusing_snapshots(run_plan: RunPlan) -> RunPlan:
    if not run_plan.data.refresh_snapshots:
        return run_plan
    return run_plan.model_copy(
        update={
            "data": run_plan.data.model_copy(update={"refresh_snapshots": False}),
        }
    )


def _stock_pool_filter_from_preflight(
    run_plan: RunPlan,
    preflight: DataPreflightReport,
) -> StockPoolAutoFilterResult:
    allowed_statuses = ("ok", "warning")
    results_by_symbol = {result.symbol: result for result in preflight.symbol_results}
    original_series = run_plan.data.resolved_tradable_series
    kept_symbols: list[str] = []
    warning_symbols: list[StockPoolFilterSymbol] = []
    excluded_symbols: list[StockPoolFilterSymbol] = []

    for series in original_series:
        result = results_by_symbol.get(series.symbol)
        if result is None:
            excluded_symbols.append(
                StockPoolFilterSymbol(
                    symbol=series.symbol,
                    status="missing_preflight_result",
                    bar_count=0,
                    bar_start_date=None,
                    bar_end_date=None,
                    error_type="MissingPreflightResult",
                    error_message="symbol was not present in data preflight report",
                    indicator_alarms=(),
                    data_quality_issue_codes=(),
                )
            )
            continue

        summary = _stock_pool_filter_symbol(result)
        if result.status in allowed_statuses:
            kept_symbols.append(series.symbol)
            if result.status == "warning":
                warning_symbols.append(summary)
        else:
            excluded_symbols.append(summary)

    return StockPoolAutoFilterResult(
        schema="attbacktrader.stock_pool_auto_filter.v1",
        enabled=True,
        source_pool_file=run_plan.data.stock_pool_file,
        allowed_statuses=allowed_statuses,
        original_count=len(original_series),
        kept_count=len(kept_symbols),
        warning_count=len(warning_symbols),
        excluded_count=len(excluded_symbols),
        kept_symbols=tuple(kept_symbols),
        warning_symbols=tuple(warning_symbols),
        excluded_symbols=tuple(excluded_symbols),
    )


def _stock_pool_filter_symbol(result: DataPreflightSymbolResult) -> StockPoolFilterSymbol:
    return StockPoolFilterSymbol(
        symbol=result.symbol,
        status=result.status,
        bar_count=result.bar_count,
        bar_start_date=_date_label(result.bar_start_date),
        bar_end_date=_date_label(result.bar_end_date),
        error_type=result.error_type,
        error_message=result.error_message,
        indicator_alarms=tuple(
            f"{coverage.name}:{coverage.timeframe} missing={coverage.missing_count}/{coverage.total_count}"
            for coverage in result.indicator_coverage
            if coverage.status != "ok"
        ),
        data_quality_issue_codes=tuple(
            f"{issue.scope}.{issue.code}"
            for issue in result.data_quality_issues
        ),
    )


def _date_label(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _baoma_business_config(run_plan: RunPlan) -> BaomaBusinessRunConfig:
    sizing_params = dict(run_plan.strategy.sizing_params or {})
    max_holding_count = sizing_params.get("max_holding_count", 200)
    if max_holding_count is None:
        max_holding_count = 200
    return BaomaBusinessRunConfig(
        total_asset_value=run_plan.broker.initial_cash,
        max_holding_count=int(max_holding_count),
        buy_slice_fraction=run_plan.execution.baoma.buy_slice_fraction,
        board_lot_size=run_plan.constraints.ashare.board_lot_size,
        scale_out_mode=run_plan.execution.baoma.scale_out_mode,
        first_scale_out_return=run_plan.execution.baoma.first_scale_out_return,
        second_scale_out_return=run_plan.execution.baoma.second_scale_out_return,
        first_scale_out_atr_multiple=run_plan.execution.baoma.first_scale_out_atr_multiple,
        second_scale_out_atr_multiple=run_plan.execution.baoma.second_scale_out_atr_multiple,
        second_scale_out_confirmation=SecondScaleOutConfirmationRule(
            enabled=run_plan.execution.baoma.second_scale_out_confirmation.enabled,
            mode=run_plan.execution.baoma.second_scale_out_confirmation.mode,
            min_boll_up_distance=run_plan.execution.baoma.second_scale_out_confirmation.min_boll_up_distance,
            min_kdj_j=run_plan.execution.baoma.second_scale_out_confirmation.min_kdj_j,
            min_cci14=run_plan.execution.baoma.second_scale_out_confirmation.min_cci14,
        ),
        force_exit_at_end=run_plan.execution.baoma.force_exit_at_end,
    )


def _portfolio_result_from_baoma(result: BaomaBusinessRunResult) -> TrendTemplateV1PortfolioResult:
    return TrendTemplateV1PortfolioResult(
        intents=result.intents,
        closed_trades=tuple(
            ClosedTrade(
                symbol=trade.symbol,
                entry_date=trade.entry_date,
                exit_date=trade.exit_date,
                entry_price=trade.entry_price,
                exit_price=trade.exit_price,
                exit_reason=trade.exit_reason,
                quantity=trade.quantity,
                original_entry_price=trade.original_entry_price,
                remaining_cost_basis_at_exit=trade.remaining_cost_basis_at_exit,
                entry_quantity=trade.entry_quantity,
                entry_gross_value=trade.entry_gross_value,
                exit_gross_value=trade.exit_gross_value,
                net_pnl=trade.net_pnl,
                realized_return_pct=trade.realized_return_pct,
            )
            for trade in result.closed_trades
        ),
        open_positions=tuple(
            Position(
                symbol=position.symbol,
                entry_date=position.trade_date,
                entry_price=position.adjusted_remaining_cost_basis or 0.0,
                size=position.total_quantity,
            )
            for position in result.open_positions
        ),
    )


def _execution_audit_from_baoma(result: BaomaBusinessRunResult) -> tuple[ExecutionAuditEvent, ...]:
    return tuple(
        _execution_audit_event_from_lifecycle(event)
        for event in result.lifecycle_events
    )


def _execution_audit_event_from_lifecycle(event: LifecycleExecutionEvent) -> ExecutionAuditEvent:
    completed = event.accepted
    return ExecutionAuditEvent(
        event_date=event.trade_date,
        signal_date=event.trade_date,
        symbol=event.symbol,
        side=event.side,
        event_type="completed" if completed else "rejected",
        status="completed" if completed else "rejected",
        reason_code=event.reason_code,
        requested_quantity=event.requested_quantity,
        executable_quantity=event.executed_quantity,
        signal_price=event.price,
        blocked_by=event.blocked_by,
        executed_date=event.trade_date if completed else None,
        executed_quantity=float(event.executed_quantity) if completed else None,
        executed_price=event.price if completed else None,
        gross_value=event.executed_quantity * event.price if completed else None,
        position_quantity_after=event.position_quantity_after,
        remaining_cost_value_after=event.remaining_cost_value_after,
        remaining_cost_basis_after=event.remaining_cost_basis_after,
        cost_recovered_after=event.cost_recovered_after,
    )


def _entry_attribution_context(run_plan: RunPlan, prepared_data) -> EntryAttributionContext:
    config = run_plan.analysis.entry_attribution
    if not config.enabled:
        return EntryAttributionContext(evidence_by_key={}, enabled_factor_keys=frozenset())

    entry_filter = _entry_attribution_filter_rule(config)
    enabled_factor_keys = _entry_attribution_enabled_factor_keys(
        run_plan,
        run_plan.analysis.resolved_entry_attribution_factors,
    )
    return build_entry_attribution_context(
        bars_by_symbol=prepared_data.bars_by_symbol,
        indicators_by_symbol=prepared_data.indicators_by_symbol,
        benchmark_bars_by_symbol=prepared_data.benchmark_calculation_bars_by_symbol(run_plan),
        industry_index_bars_by_symbol=prepared_data.industry_index_calculation_bars_by_symbol(run_plan),
        memberships_by_symbol=prepared_data.memberships_by_symbol,
        attribution_reference_evidence_by_symbol_date=prepared_data.attribution_reference_evidence_by_symbol_date,
        market_symbol=config.market_symbol,
        market_fast_period=config.market_fast_period,
        market_slow_period=config.market_slow_period,
        industry_kdj_threshold=config.industry_kdj_threshold,
        enabled_factor_keys=enabled_factor_keys,
        entry_filter=entry_filter,
    )


def _baoma_post_trade_attribution_context(run_plan: RunPlan, prepared_data) -> EntryAttributionContext:
    config = run_plan.analysis.entry_attribution
    entry_filter = _entry_attribution_filter_rule(config)
    selection = run_plan.analysis.resolved_attribution_factor_selection
    if not selection.get("enabled", True) and not entry_filter.is_active():
        return EntryAttributionContext(evidence_by_key={}, enabled_factor_keys=frozenset())

    entry_keys = set(entry_attribution_factor_keys())
    base_factor_keys = (
        tuple(key for key in selection.get("include", ()) if key in entry_keys)
        if selection.get("enabled", True)
        else ()
    )
    enabled_factor_keys = _entry_attribution_enabled_factor_keys(run_plan, base_factor_keys)
    if not enabled_factor_keys and not entry_filter.is_active():
        return EntryAttributionContext(evidence_by_key={}, enabled_factor_keys=frozenset())

    return build_entry_attribution_context(
        bars_by_symbol=prepared_data.bars_by_symbol,
        indicators_by_symbol=prepared_data.indicators_by_symbol,
        benchmark_bars_by_symbol=prepared_data.benchmark_calculation_bars_by_symbol(run_plan),
        industry_index_bars_by_symbol=prepared_data.industry_index_calculation_bars_by_symbol(run_plan),
        memberships_by_symbol=prepared_data.memberships_by_symbol,
        attribution_reference_evidence_by_symbol_date=prepared_data.attribution_reference_evidence_by_symbol_date,
        market_symbol=config.market_symbol,
        market_fast_period=config.market_fast_period,
        market_slow_period=config.market_slow_period,
        industry_kdj_threshold=config.industry_kdj_threshold,
        enabled_factor_keys=enabled_factor_keys,
        entry_filter=entry_filter,
    )


def _entry_attribution_filter_rule(config) -> EntryAttributionFilterRule:
    if not config.enabled:
        return EntryAttributionFilterRule()
    return EntryAttributionFilterRule(
        enabled=config.entry_filter.enabled,
        required_checks=config.entry_filter.require_checks,
        conditions=tuple(
            EntryAttributionFilterCondition(
                field=condition.field,
                value=condition.value,
                action=condition.action,
                operator=condition.operator,
            )
            for condition in config.entry_filter.conditions
        ),
        missing_policy=config.entry_filter.missing_policy,
        reason_code=config.entry_filter.reason_code,
        blocked_by=config.entry_filter.blocked_by,
    )


def _entry_attribution_enabled_factor_keys(run_plan: RunPlan, base_factor_keys) -> tuple[str, ...]:
    condition_fields = tuple(
        condition.field
        for condition in run_plan.analysis.entry_attribution.entry_filter.conditions
    )
    return tuple(dict.fromkeys((*base_factor_keys, *condition_fields)))


def _symbol_results_from_portfolio(
    run_plan: RunPlan,
    *,
    prepared_by_symbol: Mapping[str, PreparedSymbolData],
    portfolio_result: TrendTemplateV1PortfolioResult,
) -> tuple[SymbolRunResult, ...]:
    symbol_results: list[SymbolRunResult] = []

    for series in run_plan.data.resolved_tradable_series:
        symbol = series.symbol
        prepared = prepared_by_symbol[symbol]
        intents = tuple(intent for intent in portfolio_result.intents if intent.symbol == symbol)
        closed_trades = tuple(trade for trade in portfolio_result.closed_trades if trade.symbol == symbol)
        open_position = next((position for position in portfolio_result.open_positions if position.symbol == symbol), None)
        trend_result = TrendTemplateV1Result(
            intents=intents,
            closed_trades=closed_trades,
            open_position=open_position,
        )

        symbol_results.append(
            SymbolRunResult(
                symbol=symbol,
                asset_type=prepared.asset_type,
                adjustment=prepared.adjustment,
                bar_count=len(prepared.bars),
                snapshot_path=prepared.snapshot_path,
                indicator_snapshot_path=prepared.indicator_snapshot_path,
                indicator_snapshot_paths=prepared.indicator_snapshot_paths,
                snapshot_provenance=prepared.snapshot_provenance,
                indicator_snapshot_provenance=prepared.indicator_snapshot_provenance,
                data_quality_issues=prepared.data_quality_issues,
                tradability_snapshot_path=prepared.tradability_snapshot_path,
                tradability_snapshot_provenance=prepared.tradability_snapshot_provenance,
                intents=intents,
                intent_count=len(intents),
                closed_trades=closed_trades,
                open_position=open_position,
                report=build_report_from_trend_result(trend_result, report_id=f"{run_plan.run.id}:{symbol}"),
            )
        )

    return tuple(symbol_results)
