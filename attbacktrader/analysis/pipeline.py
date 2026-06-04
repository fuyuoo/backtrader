"""Enrich Backtest Reports with configured analysis evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from attbacktrader.analysis.attribution import attribute_trades_by_shenwan_industry
from attbacktrader.analysis.benchmarks import compare_strategy_to_benchmarks
from attbacktrader.analysis.execution import summarize_execution_costs
from attbacktrader.analysis.portfolio import summarize_portfolio_behavior
from attbacktrader.analysis.regime import summarize_market_regime_inputs
from attbacktrader.analysis.scenario_fit import evaluate_scenario_fit
from attbacktrader.config import RunPlan
from attbacktrader.data import IndexBar, StockIndustryMembership
from attbacktrader.engines.ledger import ExecutionAuditEvent
from attbacktrader.reports.models import BacktestReport
from attbacktrader.strategies.templates import ClosedTrade, Position


@dataclass(frozen=True)
class AnalysisEvidence:
    benchmark_bars_by_symbol: Mapping[str, tuple[IndexBar, ...]]
    industry_index_bars_by_symbol: Mapping[str, tuple[IndexBar, ...]]
    memberships_by_symbol: Mapping[str, tuple[StockIndustryMembership, ...]]
    open_positions: tuple[Position, ...] = ()
    execution_audit: tuple[ExecutionAuditEvent, ...] = ()
    final_cash: float | None = None
    final_value: float | None = None


def enrich_backtest_report(
    run_plan: RunPlan,
    *,
    base_report: BacktestReport,
    closed_trades: tuple[ClosedTrade, ...],
    evidence: AnalysisEvidence,
) -> BacktestReport:
    benchmark_comparison = compare_strategy_to_benchmarks(
        strategy_return=base_report.returns.cumulative_return,
        index_bars_by_symbol=evidence.benchmark_bars_by_symbol,
    )

    industry_attribution = ()
    if run_plan.analysis.industry_attribution.enabled:
        industry_attribution = attribute_trades_by_shenwan_industry(
            closed_trades,
            memberships_by_symbol=evidence.memberships_by_symbol,
            levels=run_plan.analysis.industry_attribution.levels,
        )

    market_regime = None
    if run_plan.analysis.market_regime.enabled:
        market_regime = summarize_market_regime_inputs(
            benchmark_symbols=run_plan.data.benchmark_series.indexes,
            industry_index_symbols=run_plan.data.industry_series.indexes,
            timeframes=run_plan.analysis.market_regime.timeframes,
        )

    report = replace(
        base_report,
        benchmark_comparison=benchmark_comparison,
        industry_attribution=industry_attribution,
        market_regime=market_regime,
        portfolio_behavior=summarize_portfolio_behavior(
            closed_trades,
            open_positions=evidence.open_positions,
            final_cash=evidence.final_cash,
            final_value=evidence.final_value,
        ),
        execution_costs=summarize_execution_costs(evidence.execution_audit),
    )

    if run_plan.analysis.scenario_fit.enabled:
        return replace(
            report,
            scenario_fit=evaluate_scenario_fit(
                report,
                min_trades=run_plan.analysis.scenario_fit.min_trades,
            ),
        )

    return report
