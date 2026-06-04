"""Post-run analysis helpers."""

from .attribution import attribute_trades_by_shenwan_industry
from .benchmarks import compare_strategy_to_benchmarks
from .execution import summarize_execution_costs
from .pipeline import AnalysisEvidence, enrich_backtest_report
from .portfolio import summarize_portfolio_behavior
from .regime import classify_market_regime, summarize_market_regime_inputs
from .scenario_fit import evaluate_scenario_fit

__all__ = [
    "AnalysisEvidence",
    "attribute_trades_by_shenwan_industry",
    "classify_market_regime",
    "compare_strategy_to_benchmarks",
    "enrich_backtest_report",
    "evaluate_scenario_fit",
    "summarize_execution_costs",
    "summarize_market_regime_inputs",
    "summarize_portfolio_behavior",
]
