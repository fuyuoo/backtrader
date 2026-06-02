"""Execute validated run plans against prepared market snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from attbacktrader.analysis import AnalysisEvidence, enrich_backtest_report
from attbacktrader.config import RunPlan
from attbacktrader.data.providers import RunDataProvider
from attbacktrader.engines.backtrader import (
    BacktraderAShareSettings,
    BacktraderBrokerSettings,
    run_trend_template_v1_portfolio_backtrader,
)
from attbacktrader.engines.ledger import EquityCurvePoint, ExecutionAuditEvent, PositionSnapshot
from attbacktrader.reports import build_report_from_closed_trades, build_report_from_equity_curve, build_report_from_trend_result
from attbacktrader.reports.models import BacktestReport
from attbacktrader.runners.prepared_data import (
    IndexSeriesResult,
    IndustryClassificationResult,
    IndustryMembershipResult,
    PreparedSymbolData,
    prepare_run_data,
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
    tradability_snapshot_path: Path | None
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
    closed_trades: tuple[ClosedTrade, ...]
    open_positions: tuple[Position, ...]
    equity_curve: tuple[EquityCurvePoint, ...]
    position_snapshots: tuple[PositionSnapshot, ...]
    execution_audit: tuple[ExecutionAuditEvent, ...]
    report: BacktestReport
    final_cash: float | None
    final_value: float | None


def execute_run_plan(
    run_plan: RunPlan,
    *,
    provider: RunDataProvider | None = None,
) -> RunPlanExecutionResult:
    prepared_data = prepare_run_data(run_plan, provider=provider)
    strategy_template = build_strategy_template(run_plan.strategy)

    if run_plan.execution.engine == "backtrader":
        engine_result = run_trend_template_v1_portfolio_backtrader(
            prepared_data.bars_by_symbol,
            initial_cash=run_plan.broker.initial_cash,
            stake=run_plan.execution.stake,
            indicators_by_symbol=prepared_data.indicators_by_symbol,
            tradability_by_symbol=prepared_data.tradability_by_symbol,
            entry_method=strategy_template.entry_method,
            profit_taking_method=strategy_template.profit_taking_method,
            stop_loss_method=strategy_template.stop_loss_method,
            broker_settings=BacktraderBrokerSettings(
                commission_rate=run_plan.broker.commission_rate,
                stamp_tax_rate=run_plan.broker.stamp_tax_rate,
                transfer_fee_rate=run_plan.broker.transfer_fee_rate,
                slippage_type=run_plan.broker.slippage.type,
                slippage_value=run_plan.broker.slippage.value,
            ),
            ashare_settings=BacktraderAShareSettings(
                enabled=run_plan.constraints.ashare.enabled,
                board_lot_size=run_plan.constraints.ashare.board_lot_size,
                suspension_enabled=run_plan.constraints.ashare.suspension,
                limit_up_down_enabled=run_plan.constraints.ashare.limit_up_down,
                t_plus_one_enabled=run_plan.constraints.ashare.t_plus_one,
            ),
        )
        portfolio_result = engine_result.strategy_result
        final_cash = engine_result.final_cash
        final_value = engine_result.final_value
        equity_curve = engine_result.equity_curve
        position_snapshots = engine_result.position_snapshots
        execution_audit = engine_result.execution_audit
    else:
        portfolio_result = strategy_template.run_portfolio(
            prepared_data.bars_by_symbol,
            indicators_by_symbol=prepared_data.indicators_by_symbol,
        )
        final_cash = None
        final_value = None
        equity_curve = ()
        position_snapshots = ()
        execution_audit = ()

    symbol_results = _symbol_results_from_portfolio(
        run_plan,
        prepared_by_symbol=prepared_data.symbol_data_by_symbol,
        portfolio_result=portfolio_result,
    )
    if equity_curve:
        base_report = build_report_from_equity_curve(
            equity_curve,
            closed_trades=portfolio_result.closed_trades,
            report_id=run_plan.run.id,
            starting_equity=run_plan.broker.initial_cash,
        )
    else:
        base_report = build_report_from_closed_trades(portfolio_result.closed_trades, report_id=run_plan.run.id)
    report = enrich_backtest_report(
        run_plan,
        base_report=base_report,
        closed_trades=portfolio_result.closed_trades,
        evidence=AnalysisEvidence(
            benchmark_bars_by_symbol=prepared_data.benchmark_bars_by_symbol(run_plan),
            industry_index_bars_by_symbol=prepared_data.industry_index_bars_by_symbol(run_plan),
            memberships_by_symbol=prepared_data.memberships_by_symbol,
            open_positions=portfolio_result.open_positions,
            execution_audit=execution_audit,
            final_cash=final_cash,
            final_value=final_value,
        ),
    )

    return RunPlanExecutionResult(
        run_id=run_plan.run.id,
        engine=run_plan.execution.engine,
        adjustment=prepared_data.adjustment_label,
        symbols=prepared_data.symbols,
        symbol_results=symbol_results,
        benchmark_results=prepared_data.benchmark_results(run_plan),
        decision_series_results=prepared_data.decision_series_results(run_plan),
        industry_index_results=prepared_data.industry_index_results(run_plan),
        industry_classification_result=prepared_data.industry_classification_result,
        industry_membership_results=prepared_data.industry_membership_results,
        closed_trades=portfolio_result.closed_trades,
        open_positions=portfolio_result.open_positions,
        equity_curve=equity_curve,
        position_snapshots=position_snapshots,
        execution_audit=execution_audit,
        report=report,
        final_cash=final_cash,
        final_value=final_value,
    )


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
                tradability_snapshot_path=prepared.tradability_snapshot_path,
                intent_count=len(intents),
                closed_trades=closed_trades,
                open_position=open_position,
                report=build_report_from_trend_result(trend_result, report_id=f"{run_plan.run.id}:{symbol}"),
            )
        )

    return tuple(symbol_results)
