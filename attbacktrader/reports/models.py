"""Standard report models for completed backtests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReturnSummary:
    starting_equity: float
    final_equity: float
    cumulative_return: float


@dataclass(frozen=True)
class RiskSummary:
    max_drawdown: float


@dataclass(frozen=True)
class TradeQualitySummary:
    trade_count: int
    win_count: int
    loss_count: int
    win_rate: float | None
    average_win: float | None
    average_loss: float | None
    profit_loss_ratio: float | None


@dataclass(frozen=True)
class BenchmarkComparisonSummary:
    benchmark_symbol: str
    strategy_return: float
    benchmark_return: float
    excess_return: float


@dataclass(frozen=True)
class IndustryAttributionSummary:
    level: int
    industry_code: str
    industry_name: str
    trade_count: int
    average_return: float
    contribution_return: float


@dataclass(frozen=True)
class MarketRegimeWindowSummary:
    timeframe: str
    label: str
    benchmark_count: int
    benchmark_return: float | None
    benchmark_max_drawdown: float | None
    benchmark_volatility: float | None
    industry_count: int
    industry_positive_ratio: float | None


@dataclass(frozen=True)
class MarketRegimeSummary:
    primary_label: str
    windows: tuple[MarketRegimeWindowSummary, ...]


@dataclass(frozen=True)
class ScenarioFitSummary:
    label: str
    score: int
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class SymbolContributionSummary:
    symbol: str
    trade_count: int
    cumulative_return: float
    average_return: float


@dataclass(frozen=True)
class PortfolioBehaviorSummary:
    open_position_count: int
    open_symbols: tuple[str, ...]
    closed_symbol_count: int
    max_symbol_trade_share: float | None
    cash_ratio: float | None
    symbol_contributions: tuple[SymbolContributionSummary, ...]


@dataclass(frozen=True)
class ExecutionRejectionSummary:
    blocked_by: str
    count: int


@dataclass(frozen=True)
class ExecutionCostSummary:
    order_count: int
    submitted_count: int
    accepted_count: int
    completed_count: int
    failed_count: int
    rejected_count: int
    fill_rate: float | None
    rejection_rate: float | None
    total_commission: float
    average_commission: float | None
    total_slippage_cost: float
    average_slippage_cost: float | None
    rejections: tuple[ExecutionRejectionSummary, ...]


@dataclass(frozen=True)
class BacktestReport:
    report_id: str
    returns: ReturnSummary
    risk: RiskSummary
    trade_quality: TradeQualitySummary
    benchmark_comparison: tuple[BenchmarkComparisonSummary, ...] = ()
    industry_attribution: tuple[IndustryAttributionSummary, ...] = ()
    market_regime: MarketRegimeSummary | None = None
    scenario_fit: ScenarioFitSummary | None = None
    portfolio_behavior: PortfolioBehaviorSummary | None = None
    execution_costs: ExecutionCostSummary | None = None
