"""Deterministic business-engine portfolio simulation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Any, Mapping, Sequence

from attbacktrader.data import DailyBar
from attbacktrader.engines.ledger import EquityCurvePoint, PositionSnapshot
from attbacktrader.features import (
    IndicatorFrame,
    MarketFeatureRow,
    build_indicator_snapshots_for_requirements,
    indicator_frame_from_snapshots,
    indicator_snapshots_from_frame_for_requirements,
    join_bars_with_indicators,
)
from attbacktrader.sizing import SizingDecision
from attbacktrader.strategies import TradeIntent, TradeIntentType
from attbacktrader.strategies.attribution import EntryAttributionContext, with_entry_attribution_controls, with_sizing_attribution
from attbacktrader.strategies.templates import ClosedTrade, Position, TrendTemplateV1, TrendTemplateV1PortfolioResult


@dataclass(frozen=True)
class BusinessPortfolioRunResult:
    strategy_result: TrendTemplateV1PortfolioResult
    final_cash: float
    final_value: float
    equity_curve: tuple[EquityCurvePoint, ...]
    position_snapshots: tuple[PositionSnapshot, ...]


@dataclass(frozen=True)
class _BusinessPosition:
    symbol: str
    size: int
    entry_date: date
    entry_price: float
    add_on_count: int = 0


def run_trend_template_v1_portfolio_business(
    strategy_template: TrendTemplateV1,
    bars_by_symbol: Mapping[str, Sequence[DailyBar]],
    *,
    initial_cash: float,
    stake: int,
    indicators_by_symbol: Mapping[str, IndicatorFrame] | None = None,
    risk_group_by_symbol: Mapping[str, str] | None = None,
    entry_attribution_context: EntryAttributionContext | None = None,
) -> BusinessPortfolioRunResult:
    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    if stake <= 0:
        raise ValueError("stake must be positive")
    if not bars_by_symbol:
        raise ValueError("bars_by_symbol cannot be empty")

    rows_by_key = _portfolio_rows_by_key(
        strategy_template,
        bars_by_symbol,
        indicators_by_symbol=dict(indicators_by_symbol or {}),
    )
    previous_rows_by_key = _previous_rows_by_key(rows_by_key)
    dates = tuple(sorted({trade_date for _, trade_date in rows_by_key}))
    risk_group_by_symbol = dict(risk_group_by_symbol or {})

    cash = float(initial_cash)
    positions: dict[str, _BusinessPosition] = {}
    latest_prices: dict[str, float] = {}
    daily_turnover_value: dict[date, float] = {}
    last_rebalance_date_by_symbol: dict[str, date] = {}
    intents: list[TradeIntent] = []
    closed_trades: list[ClosedTrade] = []
    equity_curve: list[EquityCurvePoint] = []
    position_snapshots: list[PositionSnapshot] = []
    peak_value = float(initial_cash)

    for trade_date in dates:
        symbols_for_date = tuple(sorted(symbol for symbol, row_date in rows_by_key if row_date == trade_date))
        for symbol in symbols_for_date:
            row = rows_by_key[(symbol, trade_date)]
            previous_row = previous_rows_by_key.get((symbol, trade_date))
            close = float(row.bar.close)
            latest_prices[symbol] = close
            position = positions.get(symbol)

            if position is None:
                entry_intent = strategy_template.entry_method.evaluate(
                    symbol=symbol,
                    trade_date=trade_date,
                    row=row,
                    previous_row=previous_row,
                )
                entry_intent = _intent_with_entry_attribution(
                    entry_intent,
                    entry_attribution_context,
                    symbol=symbol,
                    trade_date=trade_date,
                )
                if entry_intent.intent_type != TradeIntentType.ENTER:
                    intents.append(entry_intent)
                    continue

                total_value = _portfolio_value(cash, positions, latest_prices)
                risk_group = risk_group_by_symbol.get(symbol)
                sizing_decision = strategy_template.sizing_method.size_entry(
                    symbol=symbol,
                    trade_date=trade_date,
                    price=close,
                    cash=cash,
                    total_value=total_value,
                    current_quantity=0,
                    current_holding_count=len(positions),
                    fallback_quantity=stake,
                    row=row,
                    current_exposure_value=_current_exposure_value(positions, latest_prices),
                    current_risk_group_exposure_value=_current_risk_group_exposure_value(
                        positions,
                        latest_prices,
                        risk_group_by_symbol=risk_group_by_symbol,
                        risk_group=risk_group,
                    ),
                    current_turnover_value=daily_turnover_value.get(trade_date, 0.0),
                    last_rebalance_date=last_rebalance_date_by_symbol.get(symbol),
                    risk_group=risk_group,
                )
                requested_quantity = sizing_decision.requested_quantity
                executable_quantity = min(requested_quantity, int(cash / close))
                entry_intent = _intent_with_sizing(
                    entry_intent,
                    sizing_decision,
                    executable_quantity=executable_quantity,
                    entry_attribution_context=entry_attribution_context,
                )
                if executable_quantity <= 0:
                    intents.append(_blocked_intent(entry_intent, sizing_decision.blocked_by or "INSUFFICIENT_CASH"))
                    continue

                cost = executable_quantity * close
                cash -= cost
                positions[symbol] = _BusinessPosition(
                    symbol=symbol,
                    size=executable_quantity,
                    entry_date=trade_date,
                    entry_price=close,
                )
                daily_turnover_value[trade_date] = daily_turnover_value.get(trade_date, 0.0) + cost
                last_rebalance_date_by_symbol[symbol] = trade_date
                intents.append(entry_intent)
                continue

            stop_intent = strategy_template.stop_loss_method.evaluate(
                symbol=symbol,
                trade_date=trade_date,
                entry_price=position.entry_price,
                current_price=close,
                row=row,
                previous_row=previous_row,
            )
            stop_intent = _intent_with_entry_attribution(
                stop_intent,
                entry_attribution_context,
                symbol=symbol,
                trade_date=trade_date,
            )
            intents.append(stop_intent)
            if stop_intent.intent_type == TradeIntentType.EXIT_LOSS:
                cash += position.size * close
                closed_trades.append(_close_trade(position, row.bar, stop_intent.reason_code))
                positions.pop(symbol)
                continue

            profit_intent = strategy_template.profit_taking_method.evaluate(
                symbol=symbol,
                trade_date=trade_date,
                row=row,
                previous_row=previous_row,
            )
            profit_intent = _intent_with_entry_attribution(
                profit_intent,
                entry_attribution_context,
                symbol=symbol,
                trade_date=trade_date,
            )
            intents.append(profit_intent)
            if profit_intent.intent_type == TradeIntentType.EXIT_PROFIT:
                cash += position.size * close
                closed_trades.append(_close_trade(position, row.bar, profit_intent.reason_code))
                positions.pop(symbol)
                continue

            if not _add_on_enabled(strategy_template.add_on_method):
                continue

            add_on_intent = strategy_template.add_on_method.evaluate(
                symbol=symbol,
                trade_date=trade_date,
                current_quantity=position.size,
                entry_price=position.entry_price,
                current_price=close,
                add_on_count=position.add_on_count,
                row=row,
                previous_row=previous_row,
            )
            add_on_intent = _intent_with_entry_attribution(
                add_on_intent,
                entry_attribution_context,
                symbol=symbol,
                trade_date=trade_date,
            )
            if add_on_intent.intent_type != TradeIntentType.ADD_ON:
                intents.append(add_on_intent)
                continue

            total_value = _portfolio_value(cash, positions, latest_prices)
            risk_group = risk_group_by_symbol.get(symbol)
            sizing_decision = strategy_template.sizing_method.size_entry(
                symbol=symbol,
                trade_date=trade_date,
                price=close,
                cash=cash,
                total_value=total_value,
                current_quantity=position.size,
                current_holding_count=len(positions),
                fallback_quantity=stake,
                row=row,
                current_exposure_value=_current_exposure_value(positions, latest_prices),
                current_risk_group_exposure_value=_current_risk_group_exposure_value(
                    positions,
                    latest_prices,
                    risk_group_by_symbol=risk_group_by_symbol,
                    risk_group=risk_group,
                ),
                current_turnover_value=daily_turnover_value.get(trade_date, 0.0),
                last_rebalance_date=last_rebalance_date_by_symbol.get(symbol),
                risk_group=risk_group,
            )
            requested_quantity = sizing_decision.requested_quantity
            executable_quantity = min(requested_quantity, int(cash / close))
            add_on_intent = _intent_with_sizing(
                add_on_intent,
                sizing_decision,
                executable_quantity=executable_quantity,
                entry_attribution_context=entry_attribution_context,
            )
            if executable_quantity <= 0:
                intents.append(_blocked_intent(add_on_intent, sizing_decision.blocked_by or "INSUFFICIENT_CASH"))
                continue

            cost = executable_quantity * close
            new_size = position.size + executable_quantity
            cash -= cost
            positions[symbol] = _BusinessPosition(
                symbol=symbol,
                size=new_size,
                entry_date=position.entry_date,
                entry_price=((position.size * position.entry_price) + cost) / new_size,
                add_on_count=position.add_on_count + 1,
            )
            daily_turnover_value[trade_date] = daily_turnover_value.get(trade_date, 0.0) + cost
            last_rebalance_date_by_symbol[symbol] = trade_date
            intents.append(add_on_intent)

        snapshots = _position_snapshots(trade_date, positions, latest_prices)
        position_snapshots.extend(snapshots)
        total_value = cash + sum(snapshot.market_value for snapshot in snapshots)
        peak_value = max(peak_value, total_value)
        drawdown = (peak_value - total_value) / peak_value if peak_value > 0 else 0.0
        exposure = sum(abs(snapshot.market_value) for snapshot in snapshots) / total_value if total_value > 0 else 0.0
        equity_curve.append(
            EquityCurvePoint(
                trade_date=trade_date,
                cash=cash,
                position_value=sum(snapshot.market_value for snapshot in snapshots),
                total_value=total_value,
                drawdown=drawdown,
                holding_count=len(snapshots),
                exposure=exposure,
            )
        )

    final_value = equity_curve[-1].total_value if equity_curve else cash
    open_positions = tuple(
        Position(
            symbol=symbol,
            entry_date=position.entry_date,
            entry_price=position.entry_price,
            size=position.size,
            add_on_count=position.add_on_count,
        )
        for symbol, position in sorted(positions.items())
    )
    strategy_result = TrendTemplateV1PortfolioResult(
        intents=tuple(sorted(intents, key=lambda intent: (intent.trade_date, intent.symbol, intent.reason_code))),
        closed_trades=tuple(sorted(closed_trades, key=lambda trade: (trade.exit_date, trade.symbol))),
        open_positions=open_positions,
    )
    return BusinessPortfolioRunResult(
        strategy_result=strategy_result,
        final_cash=cash,
        final_value=final_value,
        equity_curve=tuple(equity_curve),
        position_snapshots=tuple(position_snapshots),
    )


def _portfolio_rows_by_key(
    strategy_template: TrendTemplateV1,
    bars_by_symbol: Mapping[str, Sequence[DailyBar]],
    *,
    indicators_by_symbol: Mapping[str, IndicatorFrame],
) -> dict[tuple[str, date], MarketFeatureRow]:
    rows_by_key: dict[tuple[str, date], MarketFeatureRow] = {}
    for symbol, bars in sorted(bars_by_symbol.items()):
        symbol_bars = tuple(sorted(bars, key=lambda bar: bar.trade_date))
        if not symbol_bars:
            raise ValueError(f"bars cannot be empty for {symbol}")
        if any(bar.symbol != symbol for bar in symbol_bars):
            raise ValueError(f"bars key {symbol!r} must match contained symbols")

        indicator_frame = indicators_by_symbol.get(symbol) or indicator_frame_from_snapshots(
            build_indicator_snapshots_for_requirements(
                symbol_bars,
                indicator_requirements=strategy_template.required_indicators,
            )
        )
        rows = join_bars_with_indicators(
            symbol_bars,
            indicator_snapshots_from_frame_for_requirements(
                indicator_frame,
                symbol_bars,
                indicator_requirements=strategy_template.required_indicators,
            ),
            indicator_requirements=strategy_template.required_indicators,
        )
        for row in rows:
            rows_by_key[(row.symbol, row.trade_date)] = row
    return rows_by_key


def _previous_rows_by_key(
    rows_by_key: Mapping[tuple[str, date], MarketFeatureRow],
) -> dict[tuple[str, date], MarketFeatureRow]:
    previous: dict[tuple[str, date], MarketFeatureRow] = {}
    rows_by_symbol: dict[str, list[MarketFeatureRow]] = {}
    for row in rows_by_key.values():
        rows_by_symbol.setdefault(row.symbol, []).append(row)

    for symbol, rows in rows_by_symbol.items():
        ordered_rows = tuple(sorted(rows, key=lambda row: row.trade_date))
        for index, row in enumerate(ordered_rows):
            if index > 0:
                previous[(symbol, row.trade_date)] = ordered_rows[index - 1]
    return previous


def _intent_with_sizing(
    intent: TradeIntent,
    sizing_decision: SizingDecision,
    *,
    executable_quantity: int,
    entry_attribution_context: EntryAttributionContext | None,
) -> TradeIntent:
    sizing_values = dict(sizing_decision.signal_values)
    sizing_values["business_executable_quantity"] = executable_quantity
    signal_values = dict(intent.signal_values)
    signal_values["sizing"] = sizing_values
    sized_intent = replace(
        intent,
        signal_values=signal_values,
        blocked_by=sizing_decision.blocked_by or intent.blocked_by,
    )
    return with_sizing_attribution(
        sized_intent,
        sizing_values,
        enabled_factor_keys=entry_attribution_context.enabled_factor_keys if entry_attribution_context is not None else None,
    )


def _intent_with_entry_attribution(
    intent: TradeIntent,
    context: EntryAttributionContext | None,
    *,
    symbol: str,
    trade_date: date,
) -> TradeIntent:
    if context is None:
        return intent
    return with_entry_attribution_controls(intent, context, symbol=symbol, trade_date=trade_date)


def _blocked_intent(intent: TradeIntent, blocked_by: str) -> TradeIntent:
    return replace(intent, blocked_by=blocked_by)


def _add_on_enabled(add_on_method: Any) -> bool:
    return getattr(add_on_method, "method_name", None) != "none"


def _portfolio_value(
    cash: float,
    positions: Mapping[str, _BusinessPosition],
    latest_prices: Mapping[str, float],
) -> float:
    return cash + _current_exposure_value(positions, latest_prices)


def _current_exposure_value(
    positions: Mapping[str, _BusinessPosition],
    latest_prices: Mapping[str, float],
) -> float:
    return sum(
        position.size * latest_prices.get(symbol, position.entry_price)
        for symbol, position in positions.items()
    )


def _current_risk_group_exposure_value(
    positions: Mapping[str, _BusinessPosition],
    latest_prices: Mapping[str, float],
    *,
    risk_group_by_symbol: Mapping[str, str],
    risk_group: str | None,
) -> float:
    if risk_group is None:
        return 0.0
    return sum(
        position.size * latest_prices.get(symbol, position.entry_price)
        for symbol, position in positions.items()
        if risk_group_by_symbol.get(symbol) == risk_group
    )


def _position_snapshots(
    trade_date: date,
    positions: Mapping[str, _BusinessPosition],
    latest_prices: Mapping[str, float],
) -> tuple[PositionSnapshot, ...]:
    snapshots: list[PositionSnapshot] = []
    for symbol, position in sorted(positions.items()):
        price = latest_prices.get(symbol, position.entry_price)
        market_value = position.size * price
        cost_basis = position.size * position.entry_price
        unrealized_return = price / position.entry_price - 1.0 if position.entry_price != 0 else None
        snapshots.append(
            PositionSnapshot(
                trade_date=trade_date,
                symbol=symbol,
                size=float(position.size),
                price=price,
                market_value=market_value,
                cost_basis=cost_basis,
                unrealized_pnl=market_value - cost_basis,
                unrealized_return=unrealized_return,
            )
        )
    return tuple(snapshots)


def _close_trade(position: _BusinessPosition, exit_bar: DailyBar, exit_reason: str) -> ClosedTrade:
    return ClosedTrade(
        symbol=position.symbol,
        entry_date=position.entry_date,
        exit_date=exit_bar.trade_date,
        entry_price=position.entry_price,
        exit_price=exit_bar.close,
        exit_reason=exit_reason,
    )
