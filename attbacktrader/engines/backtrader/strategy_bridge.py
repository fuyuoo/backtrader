"""Bridge Trend Template V1 into a native backtrader Strategy."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Mapping, Sequence

import backtrader as bt

from attbacktrader.constraints import (
    AShareMarketState,
    ChinaAShareConstraintSet,
    ConstraintDecision,
    ExecutionRequest,
    OrderSide,
)
from attbacktrader.data import DailyBar
from attbacktrader.data.tradability import TradabilityStatus
from attbacktrader.engines.backtrader.execution import BacktraderAShareSettings
from attbacktrader.engines.ledger import EquityCurvePoint, ExecutionAuditEvent, PositionSnapshot
from attbacktrader.features import (
    IndicatorFrame,
    MarketFeatureRow,
    build_indicator_snapshots,
    indicator_frame_from_snapshots,
    indicator_snapshots_from_frame,
    join_bars_with_indicators,
)
from attbacktrader.strategies import TradeIntent, TradeIntentType
from attbacktrader.strategies.methods import FixedPercentStop, KdjOverheatedExit, KdjOversoldEntry
from attbacktrader.strategies.templates import ClosedTrade, Position, TrendTemplateV1PortfolioResult, TrendTemplateV1Result


@dataclass(frozen=True)
class BacktraderBridgeState:
    intents: tuple[TradeIntent, ...]
    closed_trades: tuple[ClosedTrade, ...]
    open_position: Position | None


@dataclass(frozen=True)
class _BrokerStateRecord:
    cash: float
    total_value: float
    position_snapshots: tuple[PositionSnapshot, ...]


class TrendTemplateV1BacktraderStrategy(bt.Strategy):
    params = (
        ("bars", None),
        ("stake", 1),
        ("entry_method", None),
        ("profit_taking_method", None),
        ("stop_loss_method", None),
        ("indicators", None),
        ("rows", None),
        ("ashare_settings", None),
        ("tradability_by_symbol", None),
    )

    def __init__(self) -> None:
        bars = tuple(self.p.bars or ())
        if not bars:
            raise ValueError("bars parameter is required")

        self._symbol = bars[0].symbol
        if any(bar.symbol != self._symbol for bar in bars):
            raise ValueError("TrendTemplateV1BacktraderStrategy requires one symbol")

        self._rows_by_date = _rows_by_date(
            bars,
            rows=tuple(self.p.rows or ()),
            indicators=self.p.indicators,
        )
        self._entry_method = self.p.entry_method or KdjOversoldEntry()
        self._profit_taking_method = self.p.profit_taking_method or KdjOverheatedExit()
        self._stop_loss_method = self.p.stop_loss_method or FixedPercentStop(loss_percent=0.05)
        self._ashare_settings = self.p.ashare_settings or BacktraderAShareSettings()
        self._tradability_by_key = _tradability_by_key(dict(self.p.tradability_by_symbol or {}))
        self._intents: list[TradeIntent] = []
        self._closed_trades: list[ClosedTrade] = []
        self._order = None
        self._entry_date: date | None = None
        self._entry_price: float | None = None
        self._broker_records: dict[date, _BrokerStateRecord] = {}
        self._execution_audit: list[ExecutionAuditEvent] = []

    def next(self) -> None:
        _record_current_broker_state(self, self._broker_records)

        if self._order is not None:
            return

        trade_date = self.data.datetime.date(0)
        close = float(self.data.close[0])
        row = self._rows_by_date[trade_date]
        kdj = row.indicators.kdj

        if not self.position:
            entry_intent = self._entry_method.evaluate(
                symbol=self._symbol,
                trade_date=trade_date,
                kdj=kdj,
            )
            if entry_intent.intent_type == TradeIntentType.ENTER:
                order_size, decision = _constrained_order_size(
                    self,
                    data=self.data,
                    symbol=self._symbol,
                    trade_date=trade_date,
                    side=OrderSide.BUY,
                    requested_quantity=int(self.p.stake),
                    price=close,
                    ashare_settings=self._ashare_settings,
                    tradability_by_key=self._tradability_by_key,
                )
                if decision is not None and decision.rejected:
                    self._intents.append(_blocked_intent(entry_intent, decision))
                    self._execution_audit.append(
                        _rejected_execution_audit(
                            intent=entry_intent,
                            side=OrderSide.BUY,
                            requested_quantity=int(self.p.stake),
                            signal_price=close,
                            decision=decision,
                        )
                    )
                    return

                self._intents.append(entry_intent)
                self._order = self.buy(size=order_size)
                _attach_order_audit_info(
                    self._order,
                    intent=entry_intent,
                    side=OrderSide.BUY,
                    requested_quantity=int(self.p.stake),
                    executable_quantity=order_size,
                    signal_price=close,
                )
                self._execution_audit.append(_submitted_execution_audit(self._order))
                return
            self._intents.append(entry_intent)
            return

        stop_intent = self._stop_loss_method.evaluate(
            symbol=self._symbol,
            trade_date=trade_date,
            entry_price=float(self.position.price),
            current_price=close,
        )
        if stop_intent.intent_type == TradeIntentType.EXIT_LOSS:
            order_size, decision = _constrained_order_size(
                self,
                data=self.data,
                symbol=self._symbol,
                trade_date=trade_date,
                side=OrderSide.SELL,
                requested_quantity=int(self.position.size),
                price=close,
                ashare_settings=self._ashare_settings,
                tradability_by_key=self._tradability_by_key,
                position_open_date=self._entry_date,
            )
            if decision is not None and decision.rejected:
                self._intents.append(_blocked_intent(stop_intent, decision))
                self._execution_audit.append(
                    _rejected_execution_audit(
                        intent=stop_intent,
                        side=OrderSide.SELL,
                        requested_quantity=int(self.position.size),
                        signal_price=close,
                        decision=decision,
                    )
                )
                return

            self._intents.append(stop_intent)
            self._order = self.sell(size=order_size)
            _attach_order_audit_info(
                self._order,
                intent=stop_intent,
                side=OrderSide.SELL,
                requested_quantity=int(self.position.size),
                executable_quantity=order_size,
                signal_price=close,
            )
            self._execution_audit.append(_submitted_execution_audit(self._order))
            return
        self._intents.append(stop_intent)

        profit_intent = self._profit_taking_method.evaluate(
            symbol=self._symbol,
            trade_date=trade_date,
            kdj=kdj,
        )
        if profit_intent.intent_type == TradeIntentType.EXIT_PROFIT:
            order_size, decision = _constrained_order_size(
                self,
                data=self.data,
                symbol=self._symbol,
                trade_date=trade_date,
                side=OrderSide.SELL,
                requested_quantity=int(self.position.size),
                price=close,
                ashare_settings=self._ashare_settings,
                tradability_by_key=self._tradability_by_key,
                position_open_date=self._entry_date,
            )
            if decision is not None and decision.rejected:
                self._intents.append(_blocked_intent(profit_intent, decision))
                self._execution_audit.append(
                    _rejected_execution_audit(
                        intent=profit_intent,
                        side=OrderSide.SELL,
                        requested_quantity=int(self.position.size),
                        signal_price=close,
                        decision=decision,
                    )
                )
                return

            self._intents.append(profit_intent)
            self._order = self.sell(size=order_size)
            _attach_order_audit_info(
                self._order,
                intent=profit_intent,
                side=OrderSide.SELL,
                requested_quantity=int(self.position.size),
                executable_quantity=order_size,
                signal_price=close,
            )
            self._execution_audit.append(_submitted_execution_audit(self._order))
            return
        self._intents.append(profit_intent)

    def notify_order(self, order) -> None:
        if order.status == order.Submitted:
            return

        if order.status == order.Accepted:
            self._execution_audit.append(_order_execution_audit(order, event_type="accepted", strategy=self))
            return

        if order.status == order.Completed:
            executed_date = self.data.num2date(order.executed.dt).date()
            executed_price = float(order.executed.price)

            if order.isbuy():
                self._entry_date = executed_date
                self._entry_price = executed_price
            else:
                if self._entry_date is None or self._entry_price is None:
                    raise RuntimeError("sell completed without an open entry record")

                self._closed_trades.append(
                    ClosedTrade(
                        symbol=self._symbol,
                        entry_date=self._entry_date,
                        exit_date=executed_date,
                        entry_price=self._entry_price,
                        exit_price=executed_price,
                        exit_reason=str(order.info.reason_code),
                    )
                )
                self._entry_date = None
                self._entry_price = None

            self._execution_audit.append(_order_execution_audit(order, event_type="completed", strategy=self))
        else:
            self._execution_audit.append(_order_execution_audit(order, event_type="failed", strategy=self))

        self._order = None

    def stop(self) -> None:
        _record_current_broker_state(self, self._broker_records)

    def result(self) -> TrendTemplateV1Result:
        open_position = None
        if self._entry_date is not None and self._entry_price is not None:
            open_position = Position(
                symbol=self._symbol,
                entry_date=self._entry_date,
                entry_price=self._entry_price,
            )

        return TrendTemplateV1Result(
            intents=tuple(self._intents),
            closed_trades=tuple(self._closed_trades),
            open_position=open_position,
        )

    def equity_curve(self) -> tuple[EquityCurvePoint, ...]:
        return _equity_curve_from_records(self._broker_records)

    def position_snapshots(self) -> tuple[PositionSnapshot, ...]:
        return _position_snapshots_from_records(self._broker_records)

    def execution_audit(self) -> tuple[ExecutionAuditEvent, ...]:
        return tuple(self._execution_audit)


class TrendTemplateV1PortfolioBacktraderStrategy(bt.Strategy):
    params = (
        ("bars_by_symbol", None),
        ("stake", 1),
        ("entry_method", None),
        ("profit_taking_method", None),
        ("stop_loss_method", None),
        ("rows_by_symbol", None),
        ("indicators_by_symbol", None),
        ("ashare_settings", None),
        ("tradability_by_symbol", None),
    )

    def __init__(self) -> None:
        bars_by_symbol = {
            str(symbol): tuple(bars)
            for symbol, bars in dict(self.p.bars_by_symbol or {}).items()
        }
        if not bars_by_symbol:
            raise ValueError("bars_by_symbol parameter is required")

        self._rows_by_key = _portfolio_rows_by_key(
            bars_by_symbol,
            rows_by_symbol=dict(self.p.rows_by_symbol or {}),
            indicators_by_symbol=dict(self.p.indicators_by_symbol or {}),
        )
        self._entry_method = self.p.entry_method or KdjOversoldEntry()
        self._profit_taking_method = self.p.profit_taking_method or KdjOverheatedExit()
        self._stop_loss_method = self.p.stop_loss_method or FixedPercentStop(loss_percent=0.05)
        self._ashare_settings = self.p.ashare_settings or BacktraderAShareSettings()
        self._tradability_by_key = _tradability_by_key(dict(self.p.tradability_by_symbol or {}))
        self._intents: list[TradeIntent] = []
        self._closed_trades: list[ClosedTrade] = []
        self._pending_orders: dict[str, object] = {}
        self._entry_by_symbol: dict[str, tuple[date, float]] = {}
        self._processed_keys: set[tuple[str, date]] = set()
        self._broker_records: dict[date, _BrokerStateRecord] = {}
        self._execution_audit: list[ExecutionAuditEvent] = []

    def next(self) -> None:
        _record_current_broker_state(self, self._broker_records)

        for data in self.datas:
            symbol = str(data._name)
            trade_date = data.datetime.date(0)
            key = (symbol, trade_date)
            if key in self._processed_keys or symbol in self._pending_orders:
                continue
            self._processed_keys.add(key)

            row = self._rows_by_key[key]
            kdj = row.indicators.kdj
            close = float(data.close[0])
            position = self.getposition(data)

            if not position:
                entry_intent = self._entry_method.evaluate(
                    symbol=symbol,
                    trade_date=trade_date,
                    kdj=kdj,
                )
                if entry_intent.intent_type == TradeIntentType.ENTER:
                    order_size, decision = _constrained_order_size(
                        self,
                        data=data,
                        symbol=symbol,
                        trade_date=trade_date,
                        side=OrderSide.BUY,
                        requested_quantity=int(self.p.stake),
                        price=close,
                        ashare_settings=self._ashare_settings,
                        tradability_by_key=self._tradability_by_key,
                    )
                    if decision is not None and decision.rejected:
                        self._intents.append(_blocked_intent(entry_intent, decision))
                        self._execution_audit.append(
                            _rejected_execution_audit(
                                intent=entry_intent,
                                side=OrderSide.BUY,
                                requested_quantity=int(self.p.stake),
                                signal_price=close,
                                decision=decision,
                            )
                        )
                        continue

                    self._intents.append(entry_intent)
                    order = self.buy(data=data, size=order_size)
                    _attach_order_audit_info(
                        order,
                        intent=entry_intent,
                        side=OrderSide.BUY,
                        requested_quantity=int(self.p.stake),
                        executable_quantity=order_size,
                        signal_price=close,
                    )
                    self._execution_audit.append(_submitted_execution_audit(order))
                    self._pending_orders[symbol] = order
                    continue
                self._intents.append(entry_intent)
                continue

            entry_date, entry_price = self._entry_by_symbol[symbol]
            stop_intent = self._stop_loss_method.evaluate(
                symbol=symbol,
                trade_date=trade_date,
                entry_price=entry_price,
                current_price=close,
            )
            if stop_intent.intent_type == TradeIntentType.EXIT_LOSS:
                order_size, decision = _constrained_order_size(
                    self,
                    data=data,
                    symbol=symbol,
                    trade_date=trade_date,
                    side=OrderSide.SELL,
                    requested_quantity=int(position.size),
                    price=close,
                    ashare_settings=self._ashare_settings,
                    tradability_by_key=self._tradability_by_key,
                    position_open_date=entry_date,
                )
                if decision is not None and decision.rejected:
                    self._intents.append(_blocked_intent(stop_intent, decision))
                    self._execution_audit.append(
                        _rejected_execution_audit(
                            intent=stop_intent,
                            side=OrderSide.SELL,
                            requested_quantity=int(position.size),
                            signal_price=close,
                            decision=decision,
                        )
                    )
                    continue

                self._intents.append(stop_intent)
                order = self.sell(data=data, size=order_size)
                _attach_order_audit_info(
                    order,
                    intent=stop_intent,
                    side=OrderSide.SELL,
                    requested_quantity=int(position.size),
                    executable_quantity=order_size,
                    signal_price=close,
                )
                self._execution_audit.append(_submitted_execution_audit(order))
                self._pending_orders[symbol] = order
                continue
            self._intents.append(stop_intent)

            profit_intent = self._profit_taking_method.evaluate(
                symbol=symbol,
                trade_date=trade_date,
                kdj=kdj,
            )
            if profit_intent.intent_type == TradeIntentType.EXIT_PROFIT:
                order_size, decision = _constrained_order_size(
                    self,
                    data=data,
                    symbol=symbol,
                    trade_date=trade_date,
                    side=OrderSide.SELL,
                    requested_quantity=int(position.size),
                    price=close,
                    ashare_settings=self._ashare_settings,
                    tradability_by_key=self._tradability_by_key,
                    position_open_date=entry_date,
                )
                if decision is not None and decision.rejected:
                    self._intents.append(_blocked_intent(profit_intent, decision))
                    self._execution_audit.append(
                        _rejected_execution_audit(
                            intent=profit_intent,
                            side=OrderSide.SELL,
                            requested_quantity=int(position.size),
                            signal_price=close,
                            decision=decision,
                        )
                    )
                    continue

                self._intents.append(profit_intent)
                order = self.sell(data=data, size=order_size)
                _attach_order_audit_info(
                    order,
                    intent=profit_intent,
                    side=OrderSide.SELL,
                    requested_quantity=int(position.size),
                    executable_quantity=order_size,
                    signal_price=close,
                )
                self._execution_audit.append(_submitted_execution_audit(order))
                self._pending_orders[symbol] = order
                continue
            self._intents.append(profit_intent)

    def notify_order(self, order) -> None:
        if order.status == order.Submitted:
            return

        if order.status == order.Accepted:
            self._execution_audit.append(_order_execution_audit(order, event_type="accepted", strategy=self))
            return

        symbol = str(order.data._name)
        if order.status == order.Completed:
            executed_date = order.data.num2date(order.executed.dt).date()
            executed_price = float(order.executed.price)

            if order.isbuy():
                self._entry_by_symbol[symbol] = (executed_date, executed_price)
            else:
                try:
                    entry_date, entry_price = self._entry_by_symbol.pop(symbol)
                except KeyError as exc:
                    raise RuntimeError(f"sell completed without an open entry record for {symbol}") from exc

                self._closed_trades.append(
                    ClosedTrade(
                        symbol=symbol,
                        entry_date=entry_date,
                        exit_date=executed_date,
                        entry_price=entry_price,
                        exit_price=executed_price,
                        exit_reason=str(order.info.reason_code),
                    )
                )
            self._execution_audit.append(_order_execution_audit(order, event_type="completed", strategy=self))
        else:
            self._execution_audit.append(_order_execution_audit(order, event_type="failed", strategy=self))

        self._pending_orders.pop(symbol, None)

    def stop(self) -> None:
        _record_current_broker_state(self, self._broker_records)

    def result(self) -> TrendTemplateV1PortfolioResult:
        open_positions = tuple(
            Position(symbol=symbol, entry_date=entry_date, entry_price=entry_price)
            for symbol, (entry_date, entry_price) in sorted(self._entry_by_symbol.items())
        )

        return TrendTemplateV1PortfolioResult(
            intents=tuple(self._intents),
            closed_trades=tuple(sorted(self._closed_trades, key=lambda trade: (trade.exit_date, trade.symbol))),
            open_positions=open_positions,
        )

    def equity_curve(self) -> tuple[EquityCurvePoint, ...]:
        return _equity_curve_from_records(self._broker_records)

    def position_snapshots(self) -> tuple[PositionSnapshot, ...]:
        return _position_snapshots_from_records(self._broker_records)

    def execution_audit(self) -> tuple[ExecutionAuditEvent, ...]:
        return tuple(self._execution_audit)


def _rows_by_date(
    bars: tuple[DailyBar, ...],
    *,
    rows: tuple[MarketFeatureRow, ...],
    indicators: IndicatorFrame | None,
) -> dict[date, MarketFeatureRow]:
    symbol = bars[0].symbol
    if rows:
        if any(row.symbol != symbol for row in rows):
            raise ValueError("market feature rows symbol must match bars")
        return {row.trade_date: row for row in rows}

    indicator_frame = indicators or indicator_frame_from_snapshots(build_indicator_snapshots(bars))
    if indicator_frame.symbol != symbol:
        raise ValueError("indicator frame symbol must match bars")

    joined_rows = join_bars_with_indicators(bars, indicator_snapshots_from_frame(indicator_frame, bars))
    return {row.trade_date: row for row in joined_rows}


def _portfolio_rows_by_key(
    bars_by_symbol: Mapping[str, Sequence[DailyBar]],
    *,
    rows_by_symbol: Mapping[str, Sequence[MarketFeatureRow]],
    indicators_by_symbol: Mapping[str, IndicatorFrame],
) -> dict[tuple[str, date], MarketFeatureRow]:
    rows_by_key: dict[tuple[str, date], MarketFeatureRow] = {}

    for symbol, bars in bars_by_symbol.items():
        symbol_bars = tuple(bars)
        if not symbol_bars:
            raise ValueError(f"bars cannot be empty for {symbol}")
        if any(bar.symbol != symbol for bar in symbol_bars):
            raise ValueError(f"bars key {symbol!r} must match contained symbols")

        rows = tuple(rows_by_symbol.get(symbol, ()))
        if rows:
            if any(row.symbol != symbol for row in rows):
                raise ValueError(f"market feature rows symbol must match bars for {symbol}")
        else:
            indicator_frame = indicators_by_symbol.get(symbol) or indicator_frame_from_snapshots(
                build_indicator_snapshots(symbol_bars)
            )
            if indicator_frame.symbol != symbol:
                raise ValueError(f"indicator frame symbol must match bars for {symbol}")
            rows = join_bars_with_indicators(symbol_bars, indicator_snapshots_from_frame(indicator_frame, symbol_bars))

        for row in rows:
            rows_by_key[(row.symbol, row.trade_date)] = row

    return rows_by_key


def _record_current_broker_state(strategy: bt.Strategy, records: dict[date, _BrokerStateRecord]) -> None:
    trade_date = _current_strategy_date(strategy)
    records[trade_date] = _BrokerStateRecord(
        cash=float(strategy.broker.getcash()),
        total_value=float(strategy.broker.getvalue()),
        position_snapshots=_current_position_snapshots(strategy, trade_date),
    )


def _current_strategy_date(strategy: bt.Strategy) -> date:
    current_dates = [data.datetime.date(0) for data in strategy.datas if len(data)]
    if not current_dates:
        raise RuntimeError("cannot record broker state before any data point is available")
    return max(current_dates)


def _current_position_snapshots(strategy: bt.Strategy, trade_date: date) -> tuple[PositionSnapshot, ...]:
    snapshots: list[PositionSnapshot] = []

    for data in strategy.datas:
        if not len(data):
            continue

        position = strategy.getposition(data)
        if not position:
            continue

        symbol = str(data._name)
        size = float(position.size)
        price = float(data.close[0])
        entry_price = float(position.price)
        market_value = size * price
        cost_basis = size * entry_price
        unrealized_return = None
        if entry_price != 0:
            unrealized_return = price / entry_price - 1.0

        snapshots.append(
            PositionSnapshot(
                trade_date=trade_date,
                symbol=symbol,
                size=size,
                price=price,
                market_value=market_value,
                cost_basis=cost_basis,
                unrealized_pnl=market_value - cost_basis,
                unrealized_return=unrealized_return,
            )
        )

    return tuple(sorted(snapshots, key=lambda snapshot: snapshot.symbol))


def _equity_curve_from_records(records: Mapping[date, _BrokerStateRecord]) -> tuple[EquityCurvePoint, ...]:
    points: list[EquityCurvePoint] = []
    peak: float | None = None

    for trade_date, record in sorted(records.items()):
        total_value = record.total_value
        peak = total_value if peak is None else max(peak, total_value)
        drawdown = 0.0
        if peak > 0:
            drawdown = (peak - total_value) / peak

        position_value = sum(abs(snapshot.market_value) for snapshot in record.position_snapshots)
        exposure = position_value / total_value if total_value > 0 else 0.0
        points.append(
            EquityCurvePoint(
                trade_date=trade_date,
                cash=record.cash,
                position_value=position_value,
                total_value=total_value,
                drawdown=drawdown,
                holding_count=len(record.position_snapshots),
                exposure=exposure,
            )
        )

    return tuple(points)


def _position_snapshots_from_records(records: Mapping[date, _BrokerStateRecord]) -> tuple[PositionSnapshot, ...]:
    snapshots: list[PositionSnapshot] = []
    for _, record in sorted(records.items()):
        snapshots.extend(record.position_snapshots)
    return tuple(snapshots)


def _attach_order_audit_info(
    order,
    *,
    intent: TradeIntent,
    side: OrderSide,
    requested_quantity: int,
    executable_quantity: int,
    signal_price: float,
) -> None:
    order.addinfo(
        reason_code=intent.reason_code,
        signal_date=intent.trade_date,
        signal_price=signal_price,
        requested_quantity=requested_quantity,
        executable_quantity=executable_quantity,
        side=side.value,
    )


def _rejected_execution_audit(
    *,
    intent: TradeIntent,
    side: OrderSide,
    requested_quantity: int,
    signal_price: float,
    decision: ConstraintDecision,
) -> ExecutionAuditEvent:
    blocked_by = ",".join(reason.value for reason in decision.blocked_by)
    return ExecutionAuditEvent(
        event_date=intent.trade_date,
        signal_date=intent.trade_date,
        symbol=intent.symbol,
        side=side.value,
        event_type="rejected",
        status="rejected",
        reason_code=intent.reason_code,
        requested_quantity=requested_quantity,
        executable_quantity=decision.executable_quantity,
        signal_price=signal_price,
        blocked_by=blocked_by,
    )


def _submitted_execution_audit(order) -> ExecutionAuditEvent:
    return ExecutionAuditEvent(
        event_date=order.info.signal_date,
        signal_date=order.info.signal_date,
        symbol=str(order.data._name),
        side=str(order.info.side),
        event_type="submitted",
        status="submitted",
        reason_code=str(order.info.reason_code),
        requested_quantity=int(order.info.requested_quantity),
        executable_quantity=int(order.info.executable_quantity),
        signal_price=float(order.info.signal_price),
        order_ref=int(order.ref),
    )


def _order_execution_audit(order, *, event_type: str, strategy: bt.Strategy) -> ExecutionAuditEvent:
    executed_date = _executed_date(order)
    executed_price = _executed_price(order)
    executed_quantity = _executed_quantity(order)
    signal_price = float(order.info.signal_price)

    return ExecutionAuditEvent(
        event_date=executed_date or order.info.signal_date,
        signal_date=order.info.signal_date,
        symbol=str(order.data._name),
        side=str(order.info.side),
        event_type=event_type,
        status=_order_status_name(order),
        reason_code=str(order.info.reason_code),
        requested_quantity=int(order.info.requested_quantity),
        executable_quantity=int(order.info.executable_quantity),
        signal_price=signal_price,
        order_ref=int(order.ref),
        executed_date=executed_date,
        executed_quantity=executed_quantity,
        executed_price=executed_price,
        commission=_executed_commission(order),
        gross_value=_executed_gross_value(order),
        slippage=_slippage_per_share(side=str(order.info.side), signal_price=signal_price, executed_price=executed_price),
        cash_after=float(strategy.broker.getcash()),
        value_after=float(strategy.broker.getvalue()),
    )


def _executed_date(order) -> date | None:
    executed_dt = getattr(order.executed, "dt", None)
    if not executed_dt:
        return None
    return order.data.num2date(executed_dt).date()


def _executed_price(order) -> float | None:
    price = float(getattr(order.executed, "price", 0.0) or 0.0)
    if price <= 0:
        return None
    return price


def _executed_quantity(order) -> float | None:
    size = float(getattr(order.executed, "size", 0.0) or 0.0)
    if size == 0:
        return None
    return abs(size)


def _executed_commission(order) -> float | None:
    if _executed_quantity(order) is None:
        return None
    return float(getattr(order.executed, "comm", 0.0) or 0.0)


def _executed_gross_value(order) -> float | None:
    quantity = _executed_quantity(order)
    price = _executed_price(order)
    if quantity is None or price is None:
        return None
    return quantity * price


def _slippage_per_share(*, side: str, signal_price: float, executed_price: float | None) -> float | None:
    if executed_price is None:
        return None
    if side == OrderSide.BUY.value:
        return executed_price - signal_price
    return signal_price - executed_price


def _order_status_name(order) -> str:
    if hasattr(order, "getstatusname"):
        return str(order.getstatusname())
    return str(order.status)


def _constrained_order_size(
    strategy: bt.Strategy,
    *,
    data,
    symbol: str,
    trade_date: date,
    side: OrderSide,
    requested_quantity: int,
    price: float,
    ashare_settings: BacktraderAShareSettings,
    tradability_by_key: Mapping[tuple[str, date], TradabilityStatus],
    position_open_date: date | None = None,
) -> tuple[int, ConstraintDecision | None]:
    if not ashare_settings.enabled:
        return requested_quantity, None

    status = tradability_by_key.get((symbol, trade_date))
    market_state = AShareMarketState(
        symbol=symbol,
        trade_date=trade_date,
        is_suspended=bool(status and status.is_suspended and ashare_settings.suspension_enabled),
        is_limit_up=bool(status and status.is_limit_up and ashare_settings.limit_up_down_enabled),
        is_limit_down=bool(status and status.is_limit_down and ashare_settings.limit_up_down_enabled),
    )

    decision = ChinaAShareConstraintSet(
        board_lot_size=ashare_settings.board_lot_size,
        t_plus_one=ashare_settings.t_plus_one_enabled,
    ).evaluate(
        ExecutionRequest(
            symbol=symbol,
            trade_date=trade_date,
            side=side,
            quantity=requested_quantity,
            price=price,
            position_open_date=position_open_date,
        ),
        market_state=market_state,
        available_cash=float(strategy.broker.getcash()),
    )
    if decision.rejected:
        return 0, decision

    return decision.executable_quantity, decision


def _blocked_intent(intent: TradeIntent, decision: ConstraintDecision) -> TradeIntent:
    return replace(
        intent,
        blocked_by=",".join(reason.value for reason in decision.blocked_by),
    )


def _tradability_by_key(
    tradability_by_symbol: Mapping[str, Sequence[TradabilityStatus]],
) -> dict[tuple[str, date], TradabilityStatus]:
    statuses_by_key: dict[tuple[str, date], TradabilityStatus] = {}
    for symbol, statuses in tradability_by_symbol.items():
        for status in statuses:
            if status.symbol != symbol:
                raise ValueError(f"tradability status symbol must match key for {symbol}")
            statuses_by_key[(status.symbol, status.trade_date)] = status
    return statuses_by_key
