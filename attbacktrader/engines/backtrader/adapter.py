"""Minimal backtrader adapter for Trend Template V1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import backtrader as bt

from attbacktrader.data import DailyBar
from attbacktrader.data.tradability import TradabilityStatus
from attbacktrader.engines.backtrader.execution import (
    BacktraderAShareSettings,
    BacktraderBrokerSettings,
    configure_backtrader_broker,
)
from attbacktrader.engines.backtrader.feeds import daily_bars_to_pandas_frame
from attbacktrader.engines.backtrader.strategy_bridge import (
    TrendTemplateV1BacktraderStrategy,
    TrendTemplateV1PortfolioBacktraderStrategy,
)
from attbacktrader.engines.business.lifecycle import LifecycleExecutionEvent, LifecyclePositionSnapshot
from attbacktrader.engines.ledger import EquityCurvePoint, ExecutionAuditEvent, PositionSnapshot
from attbacktrader.features import (
    DEFAULT_INDICATOR_NAMES,
    IndicatorFrame,
    IndicatorRequirement,
    build_indicator_snapshots_for_requirements,
    indicator_frame_from_snapshots,
    indicator_snapshots_from_frame_for_requirements,
    join_bars_with_indicators,
)
from attbacktrader.strategies.attribution import EntryAttributionContext
from attbacktrader.strategies.methods import required_indicator_requirements
from attbacktrader.strategies.templates import TrendTemplateV1PortfolioResult, TrendTemplateV1Result


@dataclass(frozen=True)
class BacktraderRunResult:
    strategy_result: TrendTemplateV1Result
    final_cash: float
    final_value: float
    equity_curve: tuple[EquityCurvePoint, ...]
    position_snapshots: tuple[PositionSnapshot, ...]
    execution_audit: tuple[ExecutionAuditEvent, ...]
    lifecycle_events: tuple[LifecycleExecutionEvent, ...] = ()
    lifecycle_snapshots: tuple[LifecyclePositionSnapshot, ...] = ()


@dataclass(frozen=True)
class BacktraderPortfolioRunResult:
    strategy_result: TrendTemplateV1PortfolioResult
    final_cash: float
    final_value: float
    equity_curve: tuple[EquityCurvePoint, ...]
    position_snapshots: tuple[PositionSnapshot, ...]
    execution_audit: tuple[ExecutionAuditEvent, ...]
    lifecycle_events: tuple[LifecycleExecutionEvent, ...] = ()
    lifecycle_snapshots: tuple[LifecyclePositionSnapshot, ...] = ()


def run_trend_template_v1_backtrader(
    bars: Sequence[DailyBar],
    *,
    initial_cash: float = 1000000.0,
    stake: int = 100,
    indicators: IndicatorFrame | None = None,
    tradability_statuses: Sequence[TradabilityStatus] = (),
    risk_group_by_symbol: Mapping[str, str] | None = None,
    entry_attribution_context: EntryAttributionContext | None = None,
    entry_method: Any = None,
    profit_taking_method: Any = None,
    stop_loss_method: Any = None,
    add_on_method: Any = None,
    sizing_method: Any = None,
    broker_settings: BacktraderBrokerSettings | None = None,
    ashare_settings: BacktraderAShareSettings | None = None,
    lifecycle_enabled: bool = False,
    lifecycle_board_lot_size: int = 100,
) -> BacktraderRunResult:
    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    if stake <= 0:
        raise ValueError("stake must be positive")
    if not bars:
        raise ValueError("bars cannot be empty")
    if lifecycle_board_lot_size <= 0:
        raise ValueError("lifecycle_board_lot_size must be positive")

    ordered_bars = tuple(sorted(bars, key=lambda bar: bar.trade_date))
    symbol = ordered_bars[0].symbol
    if any(bar.symbol != symbol for bar in ordered_bars):
        raise ValueError("run_trend_template_v1_backtrader requires one symbol")

    indicator_requirements = _required_indicator_requirements(
        entry_method,
        profit_taking_method,
        stop_loss_method,
        add_on_method,
        sizing_method,
    )
    indicator_frame = indicators or indicator_frame_from_snapshots(
        build_indicator_snapshots_for_requirements(
            ordered_bars,
            indicator_requirements=indicator_requirements,
        )
    )
    if indicator_frame.symbol != symbol:
        raise ValueError("indicator frame symbol must match bars")
    rows = join_bars_with_indicators(
        ordered_bars,
        indicator_snapshots_from_frame_for_requirements(
            indicator_frame,
            ordered_bars,
            indicator_requirements=indicator_requirements,
        ),
        indicator_requirements=indicator_requirements,
    )

    cerebro = bt.Cerebro(stdstats=False, quicknotify=True)
    configure_backtrader_broker(cerebro, initial_cash=initial_cash, broker_settings=broker_settings)
    cerebro.adddata(_daily_bars_data_feed(ordered_bars), name=symbol)
    cerebro.addstrategy(
        TrendTemplateV1BacktraderStrategy,
        bars=ordered_bars,
        stake=stake,
        indicators=indicator_frame,
        rows=rows,
        tradability_by_symbol={symbol: tuple(tradability_statuses)},
        risk_group_by_symbol=dict(risk_group_by_symbol or {}),
        entry_attribution_context=entry_attribution_context,
        entry_method=entry_method,
        profit_taking_method=profit_taking_method,
        stop_loss_method=stop_loss_method,
        add_on_method=add_on_method,
        sizing_method=sizing_method,
        ashare_settings=ashare_settings,
        lifecycle_enabled=lifecycle_enabled,
        lifecycle_board_lot_size=lifecycle_board_lot_size,
    )

    strategies = cerebro.run()
    strategy = strategies[0]

    return BacktraderRunResult(
        strategy_result=strategy.result(),
        final_cash=float(cerebro.broker.getcash()),
        final_value=float(cerebro.broker.getvalue()),
        equity_curve=strategy.equity_curve(),
        position_snapshots=strategy.position_snapshots(),
        execution_audit=strategy.execution_audit(),
        lifecycle_events=strategy.lifecycle_events(),
        lifecycle_snapshots=strategy.lifecycle_snapshots(),
    )


def run_trend_template_v1_portfolio_backtrader(
    bars_by_symbol: Mapping[str, Sequence[DailyBar]],
    *,
    initial_cash: float = 1000000.0,
    stake: int = 100,
    indicators_by_symbol: Mapping[str, IndicatorFrame] | None = None,
    tradability_by_symbol: Mapping[str, Sequence[TradabilityStatus]] | None = None,
    risk_group_by_symbol: Mapping[str, str] | None = None,
    entry_attribution_context: EntryAttributionContext | None = None,
    entry_method: Any = None,
    profit_taking_method: Any = None,
    stop_loss_method: Any = None,
    add_on_method: Any = None,
    sizing_method: Any = None,
    broker_settings: BacktraderBrokerSettings | None = None,
    ashare_settings: BacktraderAShareSettings | None = None,
    lifecycle_enabled: bool = False,
    lifecycle_board_lot_size: int = 100,
) -> BacktraderPortfolioRunResult:
    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    if stake <= 0:
        raise ValueError("stake must be positive")
    if not bars_by_symbol:
        raise ValueError("bars_by_symbol cannot be empty")
    if lifecycle_board_lot_size <= 0:
        raise ValueError("lifecycle_board_lot_size must be positive")

    ordered_bars_by_symbol = {
        symbol: tuple(sorted(bars, key=lambda bar: bar.trade_date))
        for symbol, bars in sorted(bars_by_symbol.items())
    }
    for symbol, bars in ordered_bars_by_symbol.items():
        if not bars:
            raise ValueError(f"bars cannot be empty for {symbol}")
        if any(bar.symbol != symbol for bar in bars):
            raise ValueError(f"bars key {symbol!r} must match contained symbols")

    indicators_by_symbol = dict(indicators_by_symbol or {})
    tradability_by_symbol = {
        symbol: tuple(statuses)
        for symbol, statuses in dict(tradability_by_symbol or {}).items()
    }
    risk_group_by_symbol = dict(risk_group_by_symbol or {})
    for symbol, indicator_frame in indicators_by_symbol.items():
        if indicator_frame.symbol != symbol:
            raise ValueError(f"indicator frame symbol must match bars for {symbol}")

    indicator_requirements = _required_indicator_requirements(
        entry_method,
        profit_taking_method,
        stop_loss_method,
        add_on_method,
        sizing_method,
    )
    rows_by_symbol = {
        symbol: join_bars_with_indicators(
            bars,
            indicator_snapshots_from_frame_for_requirements(
                indicators_by_symbol.get(symbol)
                or indicator_frame_from_snapshots(
                    build_indicator_snapshots_for_requirements(
                        bars,
                        indicator_requirements=indicator_requirements,
                    )
                ),
                bars,
                indicator_requirements=indicator_requirements,
            ),
            indicator_requirements=indicator_requirements,
        )
        for symbol, bars in ordered_bars_by_symbol.items()
    }

    cerebro = bt.Cerebro(stdstats=False, quicknotify=True)
    configure_backtrader_broker(cerebro, initial_cash=initial_cash, broker_settings=broker_settings)
    for symbol, bars in ordered_bars_by_symbol.items():
        cerebro.adddata(_daily_bars_data_feed(bars), name=symbol)
    cerebro.addstrategy(
        TrendTemplateV1PortfolioBacktraderStrategy,
        bars_by_symbol=ordered_bars_by_symbol,
        stake=stake,
        indicators_by_symbol=indicators_by_symbol,
        rows_by_symbol=rows_by_symbol,
        tradability_by_symbol=tradability_by_symbol,
        risk_group_by_symbol=risk_group_by_symbol,
        entry_attribution_context=entry_attribution_context,
        entry_method=entry_method,
        profit_taking_method=profit_taking_method,
        stop_loss_method=stop_loss_method,
        add_on_method=add_on_method,
        sizing_method=sizing_method,
        ashare_settings=ashare_settings,
        lifecycle_enabled=lifecycle_enabled,
        lifecycle_board_lot_size=lifecycle_board_lot_size,
    )

    strategies = cerebro.run()
    strategy = strategies[0]

    return BacktraderPortfolioRunResult(
        strategy_result=strategy.result(),
        final_cash=float(cerebro.broker.getcash()),
        final_value=float(cerebro.broker.getvalue()),
        equity_curve=strategy.equity_curve(),
        position_snapshots=strategy.position_snapshots(),
        execution_audit=strategy.execution_audit(),
        lifecycle_events=strategy.lifecycle_events(),
        lifecycle_snapshots=strategy.lifecycle_snapshots(),
    )


def _required_indicator_requirements(*methods: Any) -> tuple[IndicatorRequirement, ...]:
    requirements = required_indicator_requirements(*(method for method in methods if method is not None))
    if requirements:
        return tuple(sorted(requirements))
    return tuple(IndicatorRequirement(name) for name in DEFAULT_INDICATOR_NAMES)


def _daily_bars_data_feed(bars: Sequence[DailyBar]):
    frame = daily_bars_to_pandas_frame(bars)
    return bt.feeds.PandasData(
        dataname=frame,
        datetime="trade_date",
        open="open",
        high="high",
        low="low",
        close="close",
        volume="volume",
        openinterest=-1,
    )
