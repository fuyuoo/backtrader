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
    DEFAULT_INDICATOR_NAMES,
    IndicatorFrame,
    IndicatorRequirement,
    MarketFeatureRow,
    build_indicator_snapshots_for_requirements,
    indicator_frame_from_snapshots,
    indicator_snapshots_from_frame_for_requirements,
    join_bars_with_indicators,
)
from attbacktrader.sizing import EqualWeightSizing, SizingDecision
from attbacktrader.strategies import TradeIntent, TradeIntentType
from attbacktrader.strategies.attribution import with_entry_attribution_controls, with_sizing_attribution
from attbacktrader.strategies.methods import (
    FixedPercentStop,
    NoAddOn,
    KdjOverheatedExit,
    KdjOversoldEntry,
    required_indicator_requirements,
)
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
        ("add_on_method", None),
        ("sizing_method", None),
        ("indicators", None),
        ("rows", None),
        ("ashare_settings", None),
        ("tradability_by_symbol", None),
        ("risk_group_by_symbol", None),
        ("entry_attribution_context", None),
    )

    def __init__(self) -> None:
        bars = tuple(self.p.bars or ())
        if not bars:
            raise ValueError("bars parameter is required")

        self._symbol = bars[0].symbol
        if any(bar.symbol != self._symbol for bar in bars):
            raise ValueError("TrendTemplateV1BacktraderStrategy requires one symbol")

        self._entry_method = self.p.entry_method or KdjOversoldEntry()
        self._profit_taking_method = self.p.profit_taking_method or KdjOverheatedExit()
        self._stop_loss_method = self.p.stop_loss_method or FixedPercentStop(loss_percent=0.05)
        self._add_on_method = self.p.add_on_method or NoAddOn()
        self._sizing_method = self.p.sizing_method or EqualWeightSizing()
        self._indicator_requirements = _required_indicator_requirements(
            self._entry_method,
            self._profit_taking_method,
            self._stop_loss_method,
            self._add_on_method,
            self._sizing_method,
        )
        self._rows_by_date = _rows_by_date(
            bars,
            rows=tuple(self.p.rows or ()),
            indicators=self.p.indicators,
            indicator_requirements=self._indicator_requirements,
        )
        self._previous_rows_by_date = _previous_rows_by_date(tuple(self._rows_by_date.values()))
        self._ashare_settings = self.p.ashare_settings or BacktraderAShareSettings()
        self._tradability_by_key = _tradability_by_key(dict(self.p.tradability_by_symbol or {}))
        self._risk_group_by_symbol = dict(self.p.risk_group_by_symbol or {})
        self._entry_attribution_context = self.p.entry_attribution_context
        self._intents: list[TradeIntent] = []
        self._closed_trades: list[ClosedTrade] = []
        self._order = None
        self._entry_date: date | None = None
        self._entry_price: float | None = None
        self._add_on_count = 0
        self._broker_records: dict[date, _BrokerStateRecord] = {}
        self._execution_audit: list[ExecutionAuditEvent] = []
        self._daily_turnover_value_by_date: dict[date, float] = {}
        self._last_rebalance_date_by_symbol: dict[str, date] = {}
        self._reserved_buy_value_by_symbol: dict[str, float] = {}

    def next(self) -> None:
        _record_current_broker_state(self, self._broker_records)

        if self._order is not None:
            return

        trade_date = self.data.datetime.date(0)
        close = float(self.data.close[0])
        row = self._rows_by_date.get(trade_date)
        if row is None:
            return
        previous_row = self._previous_rows_by_date.get(trade_date)

        if not self.position:
            entry_intent = self._entry_method.evaluate(
                symbol=self._symbol,
                trade_date=trade_date,
                row=row,
                previous_row=previous_row,
            )
            entry_intent = _intent_with_entry_attribution(
                entry_intent,
                self._entry_attribution_context,
                symbol=self._symbol,
                trade_date=trade_date,
            )
            if entry_intent.intent_type == TradeIntentType.ENTER:
                sizing_decision = self._sizing_method.size_entry(
                    symbol=self._symbol,
                    trade_date=trade_date,
                    price=close,
                    cash=float(self.broker.getcash()),
                    total_value=float(self.broker.getvalue()),
                    current_quantity=int(self.position.size),
                    current_holding_count=_current_holding_count(self),
                    fallback_quantity=int(self.p.stake),
                    row=row,
                    current_exposure_value=_current_exposure_value(self) + sum(self._reserved_buy_value_by_symbol.values()),
                    current_risk_group_exposure_value=_current_risk_group_exposure_value(
                        self,
                        risk_group_by_symbol=self._risk_group_by_symbol,
                        risk_group=self._risk_group_by_symbol.get(self._symbol),
                        reserved_buy_value_by_symbol=self._reserved_buy_value_by_symbol,
                    ),
                    current_turnover_value=self._daily_turnover_value_by_date.get(trade_date, 0.0),
                    last_rebalance_date=self._last_rebalance_date_by_symbol.get(self._symbol),
                    risk_group=self._risk_group_by_symbol.get(self._symbol),
                )
                entry_intent = _intent_with_sizing(
                    entry_intent,
                    sizing_decision,
                    entry_attribution_context=self._entry_attribution_context,
                )
                if sizing_decision.requested_quantity <= 0:
                    self._intents.append(entry_intent)
                    return

                order_size, decision = _constrained_order_size(
                    self,
                    data=self.data,
                    symbol=self._symbol,
                    trade_date=trade_date,
                    side=OrderSide.BUY,
                    requested_quantity=sizing_decision.requested_quantity,
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
                            requested_quantity=sizing_decision.requested_quantity,
                            signal_price=close,
                            decision=decision,
                        )
                    )
                    return

                self._intents.append(entry_intent)
                self._order = self.buy(size=order_size)
                self._daily_turnover_value_by_date[trade_date] = (
                    self._daily_turnover_value_by_date.get(trade_date, 0.0) + order_size * close
                )
                self._last_rebalance_date_by_symbol[self._symbol] = trade_date
                self._reserved_buy_value_by_symbol[self._symbol] = order_size * close
                _attach_order_audit_info(
                    self._order,
                    intent=entry_intent,
                    side=OrderSide.BUY,
                    requested_quantity=sizing_decision.requested_quantity,
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
            entry_price=float(self._entry_price if self._entry_price is not None else self.position.price),
            current_price=close,
            row=row,
            previous_row=previous_row,
        )
        stop_intent = _intent_with_entry_attribution(
            stop_intent,
            self._entry_attribution_context,
            symbol=self._symbol,
            trade_date=trade_date,
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
            row=row,
            previous_row=previous_row,
        )
        profit_intent = _intent_with_entry_attribution(
            profit_intent,
            self._entry_attribution_context,
            symbol=self._symbol,
            trade_date=trade_date,
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

        if not _add_on_enabled(self._add_on_method):
            return

        add_on_intent = self._add_on_method.evaluate(
            symbol=self._symbol,
            trade_date=trade_date,
            current_quantity=int(self.position.size),
            entry_price=float(self._entry_price if self._entry_price is not None else self.position.price),
            current_price=close,
            add_on_count=self._add_on_count,
            row=row,
            previous_row=previous_row,
        )
        add_on_intent = _intent_with_entry_attribution(
            add_on_intent,
            self._entry_attribution_context,
            symbol=self._symbol,
            trade_date=trade_date,
        )
        if add_on_intent.intent_type != TradeIntentType.ADD_ON:
            self._intents.append(add_on_intent)
            return

        sizing_decision = self._sizing_method.size_entry(
            symbol=self._symbol,
            trade_date=trade_date,
            price=close,
            cash=float(self.broker.getcash()),
            total_value=float(self.broker.getvalue()),
            current_quantity=int(self.position.size),
            current_holding_count=_current_holding_count(self),
            fallback_quantity=int(self.p.stake),
            row=row,
            current_exposure_value=_current_exposure_value(self) + sum(self._reserved_buy_value_by_symbol.values()),
            current_risk_group_exposure_value=_current_risk_group_exposure_value(
                self,
                risk_group_by_symbol=self._risk_group_by_symbol,
                risk_group=self._risk_group_by_symbol.get(self._symbol),
                reserved_buy_value_by_symbol=self._reserved_buy_value_by_symbol,
            ),
            current_turnover_value=self._daily_turnover_value_by_date.get(trade_date, 0.0),
            last_rebalance_date=self._last_rebalance_date_by_symbol.get(self._symbol),
            risk_group=self._risk_group_by_symbol.get(self._symbol),
        )
        add_on_intent = _intent_with_sizing(
            add_on_intent,
            sizing_decision,
            entry_attribution_context=self._entry_attribution_context,
        )
        if sizing_decision.requested_quantity <= 0:
            self._intents.append(add_on_intent)
            return

        order_size, decision = _constrained_order_size(
            self,
            data=self.data,
            symbol=self._symbol,
            trade_date=trade_date,
            side=OrderSide.BUY,
            requested_quantity=sizing_decision.requested_quantity,
            price=close,
            ashare_settings=self._ashare_settings,
            tradability_by_key=self._tradability_by_key,
        )
        if decision is not None and decision.rejected:
            self._intents.append(_blocked_intent(add_on_intent, decision))
            self._execution_audit.append(
                _rejected_execution_audit(
                    intent=add_on_intent,
                    side=OrderSide.BUY,
                    requested_quantity=sizing_decision.requested_quantity,
                    signal_price=close,
                    decision=decision,
                )
            )
            return

        self._intents.append(add_on_intent)
        self._order = self.buy(size=order_size)
        self._daily_turnover_value_by_date[trade_date] = (
            self._daily_turnover_value_by_date.get(trade_date, 0.0) + order_size * close
        )
        self._last_rebalance_date_by_symbol[self._symbol] = trade_date
        self._reserved_buy_value_by_symbol[self._symbol] = order_size * close
        _attach_order_audit_info(
            self._order,
            intent=add_on_intent,
            side=OrderSide.BUY,
            requested_quantity=sizing_decision.requested_quantity,
            executable_quantity=order_size,
            signal_price=close,
        )
        self._execution_audit.append(_submitted_execution_audit(self._order))

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
                executed_quantity = abs(float(order.executed.size))
                if (
                    str(order.info.intent_type) == TradeIntentType.ADD_ON.value
                    and self._entry_date is not None
                    and self._entry_price is not None
                ):
                    total_size = abs(float(self.position.size))
                    previous_size = max(0.0, total_size - executed_quantity)
                    self._entry_price = _weighted_average_price(
                        previous_quantity=previous_size,
                        previous_price=self._entry_price,
                        executed_quantity=executed_quantity,
                        executed_price=executed_price,
                    )
                    self._add_on_count += 1
                else:
                    self._entry_date = executed_date
                    self._entry_price = executed_price
                    self._add_on_count = 0
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
                self._add_on_count = 0

            self._execution_audit.append(_order_execution_audit(order, event_type="completed", strategy=self))
        else:
            self._execution_audit.append(_order_execution_audit(order, event_type="failed", strategy=self))

        if order.isbuy():
            self._reserved_buy_value_by_symbol.pop(str(order.data._name), None)
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
                size=int(self.position.size),
                add_on_count=self._add_on_count,
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
        ("add_on_method", None),
        ("sizing_method", None),
        ("rows_by_symbol", None),
        ("indicators_by_symbol", None),
        ("ashare_settings", None),
        ("tradability_by_symbol", None),
        ("risk_group_by_symbol", None),
        ("entry_attribution_context", None),
    )

    def __init__(self) -> None:
        bars_by_symbol = {
            str(symbol): tuple(bars)
            for symbol, bars in dict(self.p.bars_by_symbol or {}).items()
        }
        if not bars_by_symbol:
            raise ValueError("bars_by_symbol parameter is required")

        self._entry_method = self.p.entry_method or KdjOversoldEntry()
        self._profit_taking_method = self.p.profit_taking_method or KdjOverheatedExit()
        self._stop_loss_method = self.p.stop_loss_method or FixedPercentStop(loss_percent=0.05)
        self._add_on_method = self.p.add_on_method or NoAddOn()
        self._sizing_method = self.p.sizing_method or EqualWeightSizing()
        self._indicator_requirements = _required_indicator_requirements(
            self._entry_method,
            self._profit_taking_method,
            self._stop_loss_method,
            self._add_on_method,
            self._sizing_method,
        )
        self._rows_by_key = _portfolio_rows_by_key(
            bars_by_symbol,
            rows_by_symbol=dict(self.p.rows_by_symbol or {}),
            indicators_by_symbol=dict(self.p.indicators_by_symbol or {}),
            indicator_requirements=self._indicator_requirements,
        )
        self._previous_rows_by_key = _previous_rows_by_key(self._rows_by_key)
        self._ashare_settings = self.p.ashare_settings or BacktraderAShareSettings()
        self._tradability_by_key = _tradability_by_key(dict(self.p.tradability_by_symbol or {}))
        self._risk_group_by_symbol = dict(self.p.risk_group_by_symbol or {})
        self._entry_attribution_context = self.p.entry_attribution_context
        self._intents: list[TradeIntent] = []
        self._closed_trades: list[ClosedTrade] = []
        self._pending_orders: dict[str, object] = {}
        self._entry_by_symbol: dict[str, tuple[date, float]] = {}
        self._add_on_count_by_symbol: dict[str, int] = {}
        self._processed_keys: set[tuple[str, date]] = set()
        self._broker_records: dict[date, _BrokerStateRecord] = {}
        self._execution_audit: list[ExecutionAuditEvent] = []
        self._daily_turnover_value_by_date: dict[date, float] = {}
        self._last_rebalance_date_by_symbol: dict[str, date] = {}
        self._reserved_buy_value_by_symbol: dict[str, float] = {}

    def next(self) -> None:
        _record_current_broker_state(self, self._broker_records)

        for data in self.datas:
            symbol = str(data._name)
            trade_date = data.datetime.date(0)
            key = (symbol, trade_date)
            if key in self._processed_keys or symbol in self._pending_orders:
                continue

            row = self._rows_by_key.get(key)
            self._processed_keys.add(key)
            if row is None:
                continue
            previous_row = self._previous_rows_by_key.get(key)
            close = float(data.close[0])
            position = self.getposition(data)

            if not position:
                entry_intent = self._entry_method.evaluate(
                    symbol=symbol,
                    trade_date=trade_date,
                    row=row,
                    previous_row=previous_row,
                )
                entry_intent = _intent_with_entry_attribution(
                    entry_intent,
                    self._entry_attribution_context,
                    symbol=symbol,
                    trade_date=trade_date,
                )
                if entry_intent.intent_type == TradeIntentType.ENTER:
                    sizing_decision = self._sizing_method.size_entry(
                        symbol=symbol,
                        trade_date=trade_date,
                        price=close,
                        cash=float(self.broker.getcash()),
                        total_value=float(self.broker.getvalue()),
                        current_quantity=int(position.size),
                        current_holding_count=_current_holding_count(self) + _pending_buy_count(self._pending_orders),
                        fallback_quantity=int(self.p.stake),
                        row=row,
                        current_exposure_value=_current_exposure_value(self) + sum(self._reserved_buy_value_by_symbol.values()),
                        current_risk_group_exposure_value=_current_risk_group_exposure_value(
                            self,
                            risk_group_by_symbol=self._risk_group_by_symbol,
                            risk_group=self._risk_group_by_symbol.get(symbol),
                            reserved_buy_value_by_symbol=self._reserved_buy_value_by_symbol,
                        ),
                        current_turnover_value=self._daily_turnover_value_by_date.get(trade_date, 0.0),
                        last_rebalance_date=self._last_rebalance_date_by_symbol.get(symbol),
                        risk_group=self._risk_group_by_symbol.get(symbol),
                    )
                    entry_intent = _intent_with_sizing(
                        entry_intent,
                        sizing_decision,
                        entry_attribution_context=self._entry_attribution_context,
                    )
                    if sizing_decision.requested_quantity <= 0:
                        self._intents.append(entry_intent)
                        continue

                    order_size, decision = _constrained_order_size(
                        self,
                        data=data,
                        symbol=symbol,
                        trade_date=trade_date,
                        side=OrderSide.BUY,
                        requested_quantity=sizing_decision.requested_quantity,
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
                                requested_quantity=sizing_decision.requested_quantity,
                                signal_price=close,
                                decision=decision,
                            )
                        )
                        continue

                    self._intents.append(entry_intent)
                    order = self.buy(data=data, size=order_size)
                    self._daily_turnover_value_by_date[trade_date] = (
                        self._daily_turnover_value_by_date.get(trade_date, 0.0) + order_size * close
                    )
                    self._last_rebalance_date_by_symbol[symbol] = trade_date
                    self._reserved_buy_value_by_symbol[symbol] = order_size * close
                    _attach_order_audit_info(
                        order,
                        intent=entry_intent,
                        side=OrderSide.BUY,
                        requested_quantity=sizing_decision.requested_quantity,
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
                row=row,
                previous_row=previous_row,
            )
            stop_intent = _intent_with_entry_attribution(
                stop_intent,
                self._entry_attribution_context,
                symbol=symbol,
                trade_date=trade_date,
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
                row=row,
                previous_row=previous_row,
            )
            profit_intent = _intent_with_entry_attribution(
                profit_intent,
                self._entry_attribution_context,
                symbol=symbol,
                trade_date=trade_date,
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

            if not _add_on_enabled(self._add_on_method):
                continue

            add_on_intent = self._add_on_method.evaluate(
                symbol=symbol,
                trade_date=trade_date,
                current_quantity=int(position.size),
                entry_price=entry_price,
                current_price=close,
                add_on_count=self._add_on_count_by_symbol.get(symbol, 0),
                row=row,
                previous_row=previous_row,
            )
            add_on_intent = _intent_with_entry_attribution(
                add_on_intent,
                self._entry_attribution_context,
                symbol=symbol,
                trade_date=trade_date,
            )
            if add_on_intent.intent_type != TradeIntentType.ADD_ON:
                self._intents.append(add_on_intent)
                continue

            sizing_decision = self._sizing_method.size_entry(
                symbol=symbol,
                trade_date=trade_date,
                price=close,
                cash=float(self.broker.getcash()),
                total_value=float(self.broker.getvalue()),
                current_quantity=int(position.size),
                current_holding_count=_current_holding_count(self) + _pending_buy_count(self._pending_orders),
                fallback_quantity=int(self.p.stake),
                row=row,
                current_exposure_value=_current_exposure_value(self) + sum(self._reserved_buy_value_by_symbol.values()),
                current_risk_group_exposure_value=_current_risk_group_exposure_value(
                    self,
                    risk_group_by_symbol=self._risk_group_by_symbol,
                    risk_group=self._risk_group_by_symbol.get(symbol),
                    reserved_buy_value_by_symbol=self._reserved_buy_value_by_symbol,
                ),
                current_turnover_value=self._daily_turnover_value_by_date.get(trade_date, 0.0),
                last_rebalance_date=self._last_rebalance_date_by_symbol.get(symbol),
                risk_group=self._risk_group_by_symbol.get(symbol),
            )
            add_on_intent = _intent_with_sizing(
                add_on_intent,
                sizing_decision,
                entry_attribution_context=self._entry_attribution_context,
            )
            if sizing_decision.requested_quantity <= 0:
                self._intents.append(add_on_intent)
                continue

            order_size, decision = _constrained_order_size(
                self,
                data=data,
                symbol=symbol,
                trade_date=trade_date,
                side=OrderSide.BUY,
                requested_quantity=sizing_decision.requested_quantity,
                price=close,
                ashare_settings=self._ashare_settings,
                tradability_by_key=self._tradability_by_key,
            )
            if decision is not None and decision.rejected:
                self._intents.append(_blocked_intent(add_on_intent, decision))
                self._execution_audit.append(
                    _rejected_execution_audit(
                        intent=add_on_intent,
                        side=OrderSide.BUY,
                        requested_quantity=sizing_decision.requested_quantity,
                        signal_price=close,
                        decision=decision,
                    )
                )
                continue

            self._intents.append(add_on_intent)
            order = self.buy(data=data, size=order_size)
            self._daily_turnover_value_by_date[trade_date] = (
                self._daily_turnover_value_by_date.get(trade_date, 0.0) + order_size * close
            )
            self._last_rebalance_date_by_symbol[symbol] = trade_date
            self._reserved_buy_value_by_symbol[symbol] = order_size * close
            _attach_order_audit_info(
                order,
                intent=add_on_intent,
                side=OrderSide.BUY,
                requested_quantity=sizing_decision.requested_quantity,
                executable_quantity=order_size,
                signal_price=close,
            )
            self._execution_audit.append(_submitted_execution_audit(order))
            self._pending_orders[symbol] = order

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
                executed_quantity = abs(float(order.executed.size))
                if str(order.info.intent_type) == TradeIntentType.ADD_ON.value and symbol in self._entry_by_symbol:
                    entry_date, entry_price = self._entry_by_symbol[symbol]
                    total_size = abs(float(self.getposition(order.data).size))
                    previous_size = max(0.0, total_size - executed_quantity)
                    self._entry_by_symbol[symbol] = (
                        entry_date,
                        _weighted_average_price(
                            previous_quantity=previous_size,
                            previous_price=entry_price,
                            executed_quantity=executed_quantity,
                            executed_price=executed_price,
                        ),
                    )
                    self._add_on_count_by_symbol[symbol] = self._add_on_count_by_symbol.get(symbol, 0) + 1
                else:
                    self._entry_by_symbol[symbol] = (executed_date, executed_price)
                    self._add_on_count_by_symbol[symbol] = 0
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
                self._add_on_count_by_symbol.pop(symbol, None)
            self._execution_audit.append(_order_execution_audit(order, event_type="completed", strategy=self))
        else:
            self._execution_audit.append(_order_execution_audit(order, event_type="failed", strategy=self))

        self._pending_orders.pop(symbol, None)
        if order.isbuy():
            self._reserved_buy_value_by_symbol.pop(symbol, None)

    def stop(self) -> None:
        _record_current_broker_state(self, self._broker_records)

    def result(self) -> TrendTemplateV1PortfolioResult:
        position_size_by_symbol = {
            str(data._name): int(self.getposition(data).size)
            for data in self.datas
            if self.getposition(data)
        }
        open_positions = tuple(
            Position(
                symbol=symbol,
                entry_date=entry_date,
                entry_price=entry_price,
                size=position_size_by_symbol.get(symbol, 0),
                add_on_count=self._add_on_count_by_symbol.get(symbol, 0),
            )
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
    indicator_requirements: tuple[IndicatorRequirement, ...],
) -> dict[date, MarketFeatureRow]:
    symbol = bars[0].symbol
    if rows:
        if any(row.symbol != symbol for row in rows):
            raise ValueError("market feature rows symbol must match bars")
        return {row.trade_date: row for row in rows}

    indicator_frame = indicators or indicator_frame_from_snapshots(
        build_indicator_snapshots_for_requirements(
            bars,
            indicator_requirements=indicator_requirements,
        )
    )
    if indicator_frame.symbol != symbol:
        raise ValueError("indicator frame symbol must match bars")

    joined_rows = join_bars_with_indicators(
        bars,
        indicator_snapshots_from_frame_for_requirements(
            indicator_frame,
            bars,
            indicator_requirements=indicator_requirements,
        ),
        indicator_requirements=indicator_requirements,
    )
    return {row.trade_date: row for row in joined_rows}


def _portfolio_rows_by_key(
    bars_by_symbol: Mapping[str, Sequence[DailyBar]],
    *,
    rows_by_symbol: Mapping[str, Sequence[MarketFeatureRow]],
    indicators_by_symbol: Mapping[str, IndicatorFrame],
    indicator_requirements: tuple[IndicatorRequirement, ...],
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
                build_indicator_snapshots_for_requirements(
                    symbol_bars,
                    indicator_requirements=indicator_requirements,
                )
            )
            if indicator_frame.symbol != symbol:
                raise ValueError(f"indicator frame symbol must match bars for {symbol}")
            rows = join_bars_with_indicators(
                symbol_bars,
                indicator_snapshots_from_frame_for_requirements(
                    indicator_frame,
                    symbol_bars,
                    indicator_requirements=indicator_requirements,
                ),
                indicator_requirements=indicator_requirements,
            )

        for row in rows:
            rows_by_key[(row.symbol, row.trade_date)] = row

    return rows_by_key


def _previous_rows_by_date(rows: Sequence[MarketFeatureRow]) -> dict[date, MarketFeatureRow]:
    ordered_rows = tuple(sorted(rows, key=lambda row: row.trade_date))
    return {
        row.trade_date: ordered_rows[index - 1]
        for index, row in enumerate(ordered_rows)
        if index > 0
    }


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


def _required_indicator_requirements(*methods) -> tuple[IndicatorRequirement, ...]:
    requirements = required_indicator_requirements(*methods)
    if requirements:
        return tuple(sorted(requirements))
    return tuple(IndicatorRequirement(name) for name in DEFAULT_INDICATOR_NAMES)


def _intent_with_sizing(intent: TradeIntent, sizing_decision: SizingDecision, *, entry_attribution_context) -> TradeIntent:
    signal_values = dict(intent.signal_values)
    signal_values["sizing"] = dict(sizing_decision.signal_values)
    sized_intent = replace(
        intent,
        signal_values=signal_values,
        blocked_by=sizing_decision.blocked_by or intent.blocked_by,
    )
    return with_sizing_attribution(
        sized_intent,
        sizing_decision.signal_values,
        enabled_factor_keys=entry_attribution_context.enabled_factor_keys if entry_attribution_context is not None else None,
    )


def _intent_with_entry_attribution(
    intent: TradeIntent,
    context,
    *,
    symbol: str,
    trade_date: date,
) -> TradeIntent:
    if context is None:
        return intent
    return with_entry_attribution_controls(intent, context, symbol=symbol, trade_date=trade_date)


def _add_on_enabled(add_on_method) -> bool:
    return getattr(add_on_method, "method_name", None) != "none"


def _current_holding_count(strategy: bt.Strategy) -> int:
    return sum(1 for data in strategy.datas if strategy.getposition(data))


def _current_exposure_value(strategy: bt.Strategy) -> float:
    exposure_value = 0.0
    for data in strategy.datas:
        if not len(data):
            continue
        position = strategy.getposition(data)
        if not position:
            continue
        exposure_value += abs(float(position.size) * float(data.close[0]))
    return exposure_value


def _current_risk_group_exposure_value(
    strategy: bt.Strategy,
    *,
    risk_group_by_symbol: Mapping[str, str],
    risk_group: str | None,
    reserved_buy_value_by_symbol: Mapping[str, float] | None = None,
) -> float:
    if risk_group is None:
        return 0.0

    exposure_value = 0.0
    for data in strategy.datas:
        if not len(data):
            continue
        symbol = str(data._name)
        if risk_group_by_symbol.get(symbol) != risk_group:
            continue
        position = strategy.getposition(data)
        if not position:
            continue
        exposure_value += abs(float(position.size) * float(data.close[0]))
    for symbol, value in dict(reserved_buy_value_by_symbol or {}).items():
        if risk_group_by_symbol.get(symbol) == risk_group:
            exposure_value += abs(float(value))
    return exposure_value


def _pending_buy_count(pending_orders: Mapping[str, object]) -> int:
    count = 0
    for order in pending_orders.values():
        if hasattr(order, "isbuy") and order.isbuy():
            count += 1
    return count


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
        intent_type=intent.intent_type.value,
        reason_code=intent.reason_code,
        signal_date=intent.trade_date,
        signal_price=signal_price,
        requested_quantity=requested_quantity,
        executable_quantity=executable_quantity,
        side=side.value,
    )


def _weighted_average_price(
    *,
    previous_quantity: float,
    previous_price: float,
    executed_quantity: float,
    executed_price: float,
) -> float:
    total_quantity = previous_quantity + executed_quantity
    if total_quantity <= 0:
        return executed_price
    return ((previous_quantity * previous_price) + (executed_quantity * executed_price)) / total_quantity


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
