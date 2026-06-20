"""Build standard reports from completed strategy runs."""

from __future__ import annotations

from collections.abc import Sequence

from attbacktrader.reports.models import (
    BacktestReport,
    BenchmarkComparisonSummary,
    IndustryAttributionSummary,
    MarketRegimeSummary,
    PortfolioBehaviorSummary,
    ReturnSummary,
    RiskSummary,
    ScenarioFitSummary,
    TradeQualitySummary,
)
from attbacktrader.engines.ledger import EquityCurvePoint
from attbacktrader.strategies.templates import ClosedTrade, TrendTemplateV1Result


def build_report_from_trend_result(
    result: TrendTemplateV1Result,
    *,
    report_id: str,
    starting_equity: float = 1.0,
    benchmark_comparison: Sequence[BenchmarkComparisonSummary] = (),
    industry_attribution: Sequence[IndustryAttributionSummary] = (),
    market_regime: MarketRegimeSummary | None = None,
    scenario_fit: ScenarioFitSummary | None = None,
    portfolio_behavior: PortfolioBehaviorSummary | None = None,
) -> BacktestReport:
    return build_report_from_closed_trades(
        result.closed_trades,
        report_id=report_id,
        starting_equity=starting_equity,
        benchmark_comparison=benchmark_comparison,
        industry_attribution=industry_attribution,
        market_regime=market_regime,
        scenario_fit=scenario_fit,
        portfolio_behavior=portfolio_behavior,
    )


def build_report_from_closed_trades(
    closed_trades: Sequence[ClosedTrade],
    *,
    report_id: str,
    starting_equity: float = 1.0,
    benchmark_comparison: Sequence[BenchmarkComparisonSummary] = (),
    industry_attribution: Sequence[IndustryAttributionSummary] = (),
    market_regime: MarketRegimeSummary | None = None,
    scenario_fit: ScenarioFitSummary | None = None,
    portfolio_behavior: PortfolioBehaviorSummary | None = None,
) -> BacktestReport:
    if starting_equity <= 0:
        raise ValueError("starting_equity must be positive")

    equity_points = _equity_points(closed_trades, starting_equity=starting_equity)
    final_equity = equity_points[-1]

    return BacktestReport(
        report_id=report_id,
        returns=ReturnSummary(
            starting_equity=starting_equity,
            final_equity=final_equity,
            cumulative_return=final_equity / starting_equity - 1.0,
        ),
        risk=RiskSummary(max_drawdown=_max_drawdown(equity_points)),
        trade_quality=_trade_quality(closed_trades),
        benchmark_comparison=tuple(benchmark_comparison),
        industry_attribution=tuple(industry_attribution),
        market_regime=market_regime,
        scenario_fit=scenario_fit,
        portfolio_behavior=portfolio_behavior,
    )


def build_report_from_equity_curve(
    equity_curve: Sequence[EquityCurvePoint],
    *,
    closed_trades: Sequence[ClosedTrade],
    report_id: str,
    starting_equity: float | None = None,
    benchmark_comparison: Sequence[BenchmarkComparisonSummary] = (),
    industry_attribution: Sequence[IndustryAttributionSummary] = (),
    market_regime: MarketRegimeSummary | None = None,
    scenario_fit: ScenarioFitSummary | None = None,
    portfolio_behavior: PortfolioBehaviorSummary | None = None,
) -> BacktestReport:
    if not equity_curve:
        raise ValueError("equity_curve cannot be empty")

    starting_equity = starting_equity if starting_equity is not None else equity_curve[0].total_value
    if starting_equity <= 0:
        raise ValueError("starting_equity must be positive")

    equity_points = (starting_equity,) + tuple(point.total_value for point in equity_curve)
    final_equity = equity_points[-1]

    return BacktestReport(
        report_id=report_id,
        returns=ReturnSummary(
            starting_equity=starting_equity,
            final_equity=final_equity,
            cumulative_return=final_equity / starting_equity - 1.0,
        ),
        risk=RiskSummary(max_drawdown=_max_drawdown(equity_points)),
        trade_quality=_trade_quality(closed_trades),
        benchmark_comparison=tuple(benchmark_comparison),
        industry_attribution=tuple(industry_attribution),
        market_regime=market_regime,
        scenario_fit=scenario_fit,
        portfolio_behavior=portfolio_behavior,
    )


def _equity_points(closed_trades: Sequence[ClosedTrade], *, starting_equity: float) -> tuple[float, ...]:
    equity = starting_equity
    points = [equity]

    if any(trade.net_pnl is not None for trade in closed_trades):
        for trade in closed_trades:
            equity += float(trade.net_pnl or 0.0)
            points.append(equity)
        return tuple(points)

    for trade in closed_trades:
        equity *= 1.0 + trade.return_pct
        points.append(equity)

    return tuple(points)


def _max_drawdown(equity_points: Sequence[float]) -> float:
    peak = equity_points[0]
    max_drawdown = 0.0

    for equity in equity_points:
        peak = max(peak, equity)
        drawdown = (peak - equity) / peak
        max_drawdown = max(max_drawdown, drawdown)

    return max_drawdown


def _trade_quality(closed_trades: Sequence[ClosedTrade]) -> TradeQualitySummary:
    returns = [trade.return_pct for trade in closed_trades]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    trade_count = len(returns)

    average_win = _average(wins)
    average_loss = _average(losses)

    profit_loss_ratio: float | None = None
    if average_win is not None and average_loss is not None and average_loss < 0:
        profit_loss_ratio = average_win / abs(average_loss)

    return TradeQualitySummary(
        trade_count=trade_count,
        win_count=len(wins),
        loss_count=len(losses),
        win_rate=(len(wins) / trade_count) if trade_count else None,
        average_win=average_win,
        average_loss=average_loss,
        profit_loss_ratio=profit_loss_ratio,
    )


def _average(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)
