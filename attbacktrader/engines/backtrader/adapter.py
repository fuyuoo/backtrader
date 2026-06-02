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
from attbacktrader.engines.ledger import EquityCurvePoint, ExecutionAuditEvent, PositionSnapshot
from attbacktrader.features import (
    IndicatorFrame,
    build_indicator_snapshots,
    indicator_frame_from_snapshots,
    indicator_snapshots_from_frame,
    join_bars_with_indicators,
)
from attbacktrader.strategies.templates import TrendTemplateV1PortfolioResult, TrendTemplateV1Result


@dataclass(frozen=True)
class BacktraderRunResult:
    strategy_result: TrendTemplateV1Result
    final_cash: float
    final_value: float
    equity_curve: tuple[EquityCurvePoint, ...]
    position_snapshots: tuple[PositionSnapshot, ...]
    execution_audit: tuple[ExecutionAuditEvent, ...]


@dataclass(frozen=True)
class BacktraderPortfolioRunResult:
    strategy_result: TrendTemplateV1PortfolioResult
    final_cash: float
    final_value: float
    equity_curve: tuple[EquityCurvePoint, ...]
    position_snapshots: tuple[PositionSnapshot, ...]
    execution_audit: tuple[ExecutionAuditEvent, ...]


def run_trend_template_v1_backtrader(
    bars: Sequence[DailyBar],
    *,
    initial_cash: float = 1000000.0,
    stake: int = 100,
    indicators: IndicatorFrame | None = None,
    tradability_statuses: Sequence[TradabilityStatus] = (),
    entry_method: Any = None,
    profit_taking_method: Any = None,
    stop_loss_method: Any = None,
    broker_settings: BacktraderBrokerSettings | None = None,
    ashare_settings: BacktraderAShareSettings | None = None,
) -> BacktraderRunResult:
    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    if stake <= 0:
        raise ValueError("stake must be positive")
    if not bars:
        raise ValueError("bars cannot be empty")

    ordered_bars = tuple(sorted(bars, key=lambda bar: bar.trade_date))
    symbol = ordered_bars[0].symbol
    if any(bar.symbol != symbol for bar in ordered_bars):
        raise ValueError("run_trend_template_v1_backtrader requires one symbol")

    indicator_frame = indicators or indicator_frame_from_snapshots(build_indicator_snapshots(ordered_bars))
    if indicator_frame.symbol != symbol:
        raise ValueError("indicator frame symbol must match bars")
    rows = join_bars_with_indicators(ordered_bars, indicator_snapshots_from_frame(indicator_frame, ordered_bars))

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
        entry_method=entry_method,
        profit_taking_method=profit_taking_method,
        stop_loss_method=stop_loss_method,
        ashare_settings=ashare_settings,
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
    )


def run_trend_template_v1_portfolio_backtrader(
    bars_by_symbol: Mapping[str, Sequence[DailyBar]],
    *,
    initial_cash: float = 1000000.0,
    stake: int = 100,
    indicators_by_symbol: Mapping[str, IndicatorFrame] | None = None,
    tradability_by_symbol: Mapping[str, Sequence[TradabilityStatus]] | None = None,
    entry_method: Any = None,
    profit_taking_method: Any = None,
    stop_loss_method: Any = None,
    broker_settings: BacktraderBrokerSettings | None = None,
    ashare_settings: BacktraderAShareSettings | None = None,
) -> BacktraderPortfolioRunResult:
    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    if stake <= 0:
        raise ValueError("stake must be positive")
    if not bars_by_symbol:
        raise ValueError("bars_by_symbol cannot be empty")

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
    for symbol, indicator_frame in indicators_by_symbol.items():
        if indicator_frame.symbol != symbol:
            raise ValueError(f"indicator frame symbol must match bars for {symbol}")

    rows_by_symbol = {
        symbol: join_bars_with_indicators(
            bars,
            indicator_snapshots_from_frame(
                indicators_by_symbol.get(symbol) or indicator_frame_from_snapshots(build_indicator_snapshots(bars)),
                bars,
            ),
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
        entry_method=entry_method,
        profit_taking_method=profit_taking_method,
        stop_loss_method=stop_loss_method,
        ashare_settings=ashare_settings,
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
    )


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
