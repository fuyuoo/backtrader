"""First strategy template used to validate the framework flow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Sequence

from attbacktrader.data import DailyBar
from attbacktrader.features import (
    IndicatorFrame,
    MarketFeatureRow,
    build_indicator_snapshots_for_requirements,
    indicator_frame_from_snapshots,
    indicator_snapshots_from_frame_for_requirements,
    join_bars_with_indicators,
)
from attbacktrader.sizing import EqualWeightSizing
from attbacktrader.strategies import TradeIntent, TradeIntentType
from attbacktrader.strategies.methods import (
    FixedPercentStop,
    KdjOverheatedExit,
    KdjOversoldEntry,
    NoAddOn,
    required_indicator_requirements,
)


@dataclass(frozen=True)
class Position:
    symbol: str
    entry_date: date
    entry_price: float
    size: int = 0
    add_on_count: int = 0


@dataclass(frozen=True)
class ClosedTrade:
    symbol: str
    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    exit_reason: str
    quantity: int | None = None
    original_entry_price: float | None = None
    remaining_cost_basis_at_exit: float | None = None
    entry_quantity: int | None = None
    entry_gross_value: float | None = None
    exit_gross_value: float | None = None
    net_pnl: float | None = None
    realized_return_pct: float | None = None

    @property
    def return_pct(self) -> float:
        if self.realized_return_pct is not None:
            return self.realized_return_pct
        if self.entry_price <= 0:
            return 0.0
        return self.exit_price / self.entry_price - 1.0


@dataclass(frozen=True)
class TrendTemplateV1Result:
    intents: tuple[TradeIntent, ...]
    closed_trades: tuple[ClosedTrade, ...]
    open_position: Position | None


@dataclass(frozen=True)
class TrendTemplateV1PortfolioResult:
    intents: tuple[TradeIntent, ...]
    closed_trades: tuple[ClosedTrade, ...]
    open_positions: tuple[Position, ...]


@dataclass(frozen=True)
class TrendTemplateV1:
    entry_method: KdjOversoldEntry = KdjOversoldEntry()
    profit_taking_method: KdjOverheatedExit = KdjOverheatedExit()
    stop_loss_method: Any = FixedPercentStop(loss_percent=0.05)
    add_on_method: Any = NoAddOn()
    sizing_method: Any = EqualWeightSizing()

    @property
    def required_indicators(self):
        return tuple(
            sorted(
                required_indicator_requirements(
                    self.entry_method,
                    self.profit_taking_method,
                    self.stop_loss_method,
                    self.add_on_method,
                    self.sizing_method,
                )
            )
        )

    @property
    def required_indicator_names(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    requirement.name
                    for requirement in self.required_indicators
                }
            )
        )

    def run_single_symbol(
        self,
        bars: Sequence[DailyBar],
        *,
        indicators: IndicatorFrame | None = None,
    ) -> TrendTemplateV1Result:
        if not bars:
            raise ValueError("bars cannot be empty")

        ordered_bars = tuple(sorted(bars, key=lambda bar: bar.trade_date))
        symbol = ordered_bars[0].symbol
        if any(bar.symbol != symbol for bar in ordered_bars):
            raise ValueError("TrendTemplateV1.run_single_symbol requires one symbol")

        indicator_frame = indicators or indicator_frame_from_snapshots(
            build_indicator_snapshots_for_requirements(
                ordered_bars,
                indicator_requirements=self.required_indicators,
            )
        )
        if indicator_frame.symbol != symbol:
            raise ValueError("indicator frame symbol must match bars")

        rows = join_bars_with_indicators(
            ordered_bars,
            indicator_snapshots_from_frame_for_requirements(
                indicator_frame,
                ordered_bars,
                indicator_requirements=self.required_indicators,
            ),
            indicator_requirements=self.required_indicators,
        )
        return self.run_single_symbol_rows(rows)

    def run_single_symbol_rows(self, rows: Sequence[MarketFeatureRow]) -> TrendTemplateV1Result:
        if not rows:
            raise ValueError("rows cannot be empty")

        ordered_rows = tuple(sorted(rows, key=lambda row: row.trade_date))
        symbol = ordered_rows[0].symbol
        if any(row.symbol != symbol for row in ordered_rows):
            raise ValueError("TrendTemplateV1.run_single_symbol_rows requires one symbol")

        intents: list[TradeIntent] = []
        closed_trades: list[ClosedTrade] = []
        position: Position | None = None

        for index, row in enumerate(ordered_rows):
            bar = row.bar
            previous_row = ordered_rows[index - 1] if index > 0 else None
            if position is None:
                entry_intent = self.entry_method.evaluate(
                    symbol=symbol,
                    trade_date=bar.trade_date,
                    row=row,
                    previous_row=previous_row,
                )
                intents.append(entry_intent)

                if entry_intent.intent_type == TradeIntentType.ENTER:
                    position = Position(symbol=symbol, entry_date=bar.trade_date, entry_price=bar.close, size=1)

                continue

            stop_intent = self.stop_loss_method.evaluate(
                symbol=symbol,
                trade_date=bar.trade_date,
                entry_price=position.entry_price,
                current_price=bar.close,
                row=row,
                previous_row=previous_row,
            )
            intents.append(stop_intent)
            if stop_intent.intent_type == TradeIntentType.EXIT_LOSS:
                closed_trades.append(_close_trade(position, bar, stop_intent.reason_code))
                position = None
                continue

            profit_intent = self.profit_taking_method.evaluate(
                symbol=symbol,
                trade_date=bar.trade_date,
                row=row,
                previous_row=previous_row,
            )
            intents.append(profit_intent)
            if profit_intent.intent_type == TradeIntentType.EXIT_PROFIT:
                closed_trades.append(_close_trade(position, bar, profit_intent.reason_code))
                position = None
                continue

            if not _add_on_enabled(self.add_on_method):
                continue

            add_on_intent = self.add_on_method.evaluate(
                symbol=symbol,
                trade_date=bar.trade_date,
                current_quantity=position.size,
                entry_price=position.entry_price,
                current_price=bar.close,
                add_on_count=position.add_on_count,
                row=row,
                previous_row=previous_row,
            )
            intents.append(add_on_intent)
            if add_on_intent.intent_type == TradeIntentType.ADD_ON:
                new_size = max(1, position.size) + 1
                position = Position(
                    symbol=position.symbol,
                    entry_date=position.entry_date,
                    entry_price=((position.entry_price * max(1, position.size)) + bar.close) / new_size,
                    size=new_size,
                    add_on_count=position.add_on_count + 1,
                )

        return TrendTemplateV1Result(
            intents=tuple(intents),
            closed_trades=tuple(closed_trades),
            open_position=position,
        )

    def run_portfolio(
        self,
        bars_by_symbol: Mapping[str, Sequence[DailyBar]],
        *,
        indicators_by_symbol: Mapping[str, IndicatorFrame] | None = None,
    ) -> TrendTemplateV1PortfolioResult:
        if not bars_by_symbol:
            raise ValueError("bars_by_symbol cannot be empty")

        intents: list[TradeIntent] = []
        closed_trades: list[ClosedTrade] = []
        open_positions: list[Position] = []
        indicators_by_symbol = indicators_by_symbol or {}

        for symbol in sorted(bars_by_symbol):
            bars = bars_by_symbol[symbol]
            if not bars:
                raise ValueError(f"bars cannot be empty for {symbol}")
            if any(bar.symbol != symbol for bar in bars):
                raise ValueError(f"bars key {symbol!r} must match contained symbols")

            result = self.run_single_symbol(
                bars,
                indicators=indicators_by_symbol.get(symbol),
            )
            intents.extend(result.intents)
            closed_trades.extend(result.closed_trades)
            if result.open_position is not None:
                open_positions.append(result.open_position)

        return TrendTemplateV1PortfolioResult(
            intents=tuple(sorted(intents, key=lambda intent: (intent.trade_date, intent.symbol, intent.reason_code))),
            closed_trades=tuple(sorted(closed_trades, key=lambda trade: (trade.exit_date, trade.symbol))),
            open_positions=tuple(sorted(open_positions, key=lambda position: (position.entry_date, position.symbol))),
        )


def _close_trade(position: Position, exit_bar: DailyBar, exit_reason: str) -> ClosedTrade:
    return ClosedTrade(
        symbol=position.symbol,
        entry_date=position.entry_date,
        exit_date=exit_bar.trade_date,
        entry_price=position.entry_price,
        exit_price=exit_bar.close,
        exit_reason=exit_reason,
    )


def _add_on_enabled(add_on_method: Any) -> bool:
    return getattr(add_on_method, "method_name", None) != "none"
