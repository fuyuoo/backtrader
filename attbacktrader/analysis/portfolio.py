"""Portfolio-behavior summaries from completed run state."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from attbacktrader.reports import PortfolioBehaviorSummary, SymbolContributionSummary
from attbacktrader.strategies.templates import ClosedTrade, Position


def summarize_portfolio_behavior(
    closed_trades: Sequence[ClosedTrade],
    *,
    open_positions: Sequence[Position] = (),
    final_cash: float | None = None,
    final_value: float | None = None,
) -> PortfolioBehaviorSummary:
    trades_by_symbol: dict[str, list[ClosedTrade]] = defaultdict(list)
    for trade in closed_trades:
        trades_by_symbol[trade.symbol].append(trade)

    symbol_contributions = tuple(
        _symbol_contribution(symbol, trades)
        for symbol, trades in sorted(trades_by_symbol.items())
    )

    max_symbol_trade_share = None
    if closed_trades:
        max_symbol_trade_share = max(len(trades) for trades in trades_by_symbol.values()) / len(closed_trades)

    cash_ratio = None
    if final_cash is not None and final_value is not None and final_value > 0:
        cash_ratio = final_cash / final_value

    return PortfolioBehaviorSummary(
        open_position_count=len(open_positions),
        open_symbols=tuple(sorted(position.symbol for position in open_positions)),
        closed_symbol_count=len(symbol_contributions),
        max_symbol_trade_share=max_symbol_trade_share,
        cash_ratio=cash_ratio,
        symbol_contributions=symbol_contributions,
    )


def _symbol_contribution(symbol: str, trades: Sequence[ClosedTrade]) -> SymbolContributionSummary:
    equity = 1.0
    returns = [trade.return_pct for trade in trades]
    for value in returns:
        equity *= 1.0 + value

    return SymbolContributionSummary(
        symbol=symbol,
        trade_count=len(trades),
        cumulative_return=equity - 1.0,
        average_return=sum(returns) / len(returns),
    )
