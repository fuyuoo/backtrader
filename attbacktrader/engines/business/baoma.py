"""Dedicated deterministic business runner for Baoma v1."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date

from attbacktrader.data import DailyBar
from attbacktrader.engines.business.lifecycle import (
    ExecutionLifecycleComponent,
    LifecycleClosedTrade,
    LifecycleEndRunResult,
    LifecycleExecutionEvent,
    LifecyclePositionSnapshot,
    LifecycleState,
    ScaleOutStage,
)
from attbacktrader.features import (
    IndicatorFrame,
    IndicatorRequirement,
    MarketFeatureRow,
    build_indicator_snapshots_for_requirements,
    indicator_frame_from_snapshots,
    indicator_snapshots_from_frame_for_requirements,
    join_bars_with_indicators,
)
from attbacktrader.strategies import EntryAttributionContext, TradeIntent, TradeIntentType
from attbacktrader.strategies.attribution import with_entry_attribution_evidence
from attbacktrader.strategies.methods import BaomaAddOn, BaomaEntry, BaomaMa25ProfitExit, BaomaMa60Stop


@dataclass(frozen=True)
class SecondScaleOutConfirmationRule:
    enabled: bool = False
    mode: str = "boll_up_distance"
    min_boll_up_distance: float | None = None
    min_kdj_j: float | None = None
    min_cci14: float | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"boll_up_distance", "kdj_cci", "kdj_cci_boll_up_distance"}:
            raise ValueError("second_scale_out_confirmation.mode is unsupported")
        if not self.enabled:
            return
        if self.requires_boll_up_distance and self.min_boll_up_distance is None:
            raise ValueError("min_boll_up_distance is required for second scale-out confirmation")
        if self.requires_kdj_cci and self.min_kdj_j is None:
            raise ValueError("min_kdj_j is required for second scale-out confirmation")
        if self.requires_kdj_cci and self.min_cci14 is None:
            raise ValueError("min_cci14 is required for second scale-out confirmation")

    @property
    def requires_boll_up_distance(self) -> bool:
        return self.mode in {"boll_up_distance", "kdj_cci_boll_up_distance"}

    @property
    def requires_kdj_cci(self) -> bool:
        return self.mode in {"kdj_cci", "kdj_cci_boll_up_distance"}


@dataclass(frozen=True)
class BaomaBusinessRunConfig:
    total_asset_value: float = 10_000_000_000.0
    max_holding_count: int = 200
    buy_slice_fraction: float = 0.33
    board_lot_size: int = 100
    scale_out_mode: str = "fixed_percent"
    first_scale_out_return: float = 0.05
    second_scale_out_return: float = 0.15
    first_scale_out_atr_multiple: float | None = None
    second_scale_out_atr_multiple: float | None = None
    second_scale_out_confirmation: SecondScaleOutConfirmationRule = field(
        default_factory=SecondScaleOutConfirmationRule
    )
    force_exit_at_end: bool = False

    def __post_init__(self) -> None:
        if self.total_asset_value <= 0:
            raise ValueError("total_asset_value must be positive")
        if self.max_holding_count <= 0:
            raise ValueError("max_holding_count must be positive")
        if not 0 < self.buy_slice_fraction <= 1:
            raise ValueError("buy_slice_fraction must be in (0, 1]")
        if self.board_lot_size <= 0:
            raise ValueError("board_lot_size must be positive")
        if self.scale_out_mode not in {"fixed_percent", "atr_multiple"}:
            raise ValueError("scale_out_mode must be fixed_percent or atr_multiple")
        if self.scale_out_mode == "fixed_percent":
            if self.second_scale_out_confirmation.enabled:
                raise ValueError("second scale-out confirmation requires atr_multiple scale_out_mode")
            if self.first_scale_out_return <= 0:
                raise ValueError("first_scale_out_return must be positive")
            if self.second_scale_out_return <= self.first_scale_out_return:
                raise ValueError("second_scale_out_return must be greater than first_scale_out_return")
        else:
            if self.first_scale_out_atr_multiple is None or self.second_scale_out_atr_multiple is None:
                raise ValueError("ATR scale-out requires first and second ATR multiples")
            if self.first_scale_out_atr_multiple <= 0:
                raise ValueError("first_scale_out_atr_multiple must be positive")
            if self.second_scale_out_atr_multiple <= self.first_scale_out_atr_multiple:
                raise ValueError("second_scale_out_atr_multiple must be greater than first_scale_out_atr_multiple")

    @property
    def per_symbol_max_value(self) -> float:
        return self.total_asset_value / self.max_holding_count

    @property
    def buy_slice_value(self) -> float:
        return self.per_symbol_max_value * self.buy_slice_fraction

    def buy_quantity_for_price(self, price: float) -> int:
        if price <= 0:
            return 0
        raw_quantity = int(self.buy_slice_value / price)
        return raw_quantity - (raw_quantity % self.board_lot_size)


@dataclass(frozen=True)
class BaomaBusinessRunResult:
    intents: tuple[TradeIntent, ...]
    lifecycle_events: tuple[LifecycleExecutionEvent, ...]
    lifecycle_snapshots: tuple[LifecyclePositionSnapshot, ...]
    closed_trades: tuple[LifecycleClosedTrade, ...]
    open_positions: tuple[LifecyclePositionSnapshot, ...]
    end_run_results: tuple[LifecycleEndRunResult, ...] = ()


@dataclass(frozen=True)
class _ScaleOutEntryContext:
    entry_signal_date: date
    entry_signal_day_atr14: float | None
    missing_reason: str | None = None


@dataclass(frozen=True)
class _ScaleOutCheck:
    stage: ScaleOutStage | None = None
    atr_multiple: float | None = None
    trigger_price: float | None = None
    missing_reason: str | None = None
    confirmation_required: bool = False
    confirmation_passed: bool | None = None
    confirmation_mode: str | None = None
    confirmation_block_reason: str | None = None
    kdj_j: float | None = None
    cci14: float | None = None
    boll_up20_2: float | None = None
    boll_up_distance_pct: float | None = None
    confirmation_checks: Mapping[str, bool | None] = field(default_factory=dict)


def run_baoma_v1_business(
    bars_by_symbol: Mapping[str, Sequence[DailyBar]],
    *,
    indicators_by_symbol: Mapping[str, IndicatorFrame] | None = None,
    config: BaomaBusinessRunConfig | None = None,
    entry_method: BaomaEntry | None = None,
    add_on_method: BaomaAddOn | None = None,
    stop_loss_method: BaomaMa60Stop | None = None,
    profit_exit_method: BaomaMa25ProfitExit | None = None,
    entry_attribution_context: EntryAttributionContext | None = None,
) -> BaomaBusinessRunResult:
    """Run Baoma v1 execution rules without portfolio cash simulation."""

    if not bars_by_symbol:
        raise ValueError("bars_by_symbol cannot be empty")

    config = config or BaomaBusinessRunConfig()
    entry_method = entry_method or BaomaEntry()
    add_on_method = add_on_method or BaomaAddOn()
    stop_loss_method = stop_loss_method or BaomaMa60Stop()
    profit_exit_method = profit_exit_method or BaomaMa25ProfitExit()
    requirements = _required_indicators(
        entry_method,
        add_on_method,
        stop_loss_method,
        profit_exit_method,
        config=config,
    )
    symbols = tuple(bars_by_symbol.keys())
    rows_by_key = _rows_by_key(
        bars_by_symbol,
        indicators_by_symbol=dict(indicators_by_symbol or {}),
        indicator_requirements=requirements,
    )
    previous_rows_by_key = _previous_rows_by_key(rows_by_key)
    dates = tuple(sorted({trade_date for _, trade_date in rows_by_key}))

    lifecycles: dict[str, ExecutionLifecycleComponent] = {}
    closed_counts_by_symbol: dict[str, int] = {}
    add_on_count_by_symbol: dict[str, int] = {}
    latest_prices: dict[str, float] = {}
    intents: list[TradeIntent] = []
    lifecycle_events: list[LifecycleExecutionEvent] = []
    lifecycle_snapshots: list[LifecyclePositionSnapshot] = []
    closed_trades: list[LifecycleClosedTrade] = []
    end_run_results: list[LifecycleEndRunResult] = []
    scale_out_context_by_symbol: dict[str, _ScaleOutEntryContext] = {}
    scale_out_missing_recorded_by_symbol: dict[str, bool] = {}

    for trade_date in dates:
        for symbol in symbols:
            row = rows_by_key.get((symbol, trade_date))
            if row is None:
                continue

            previous_row = previous_rows_by_key.get((symbol, trade_date))
            latest_prices[symbol] = float(row.bar.close)
            lifecycle = lifecycles.get(symbol)
            if lifecycle is not None and lifecycle.total_quantity > 0:
                lifecycle.advance_day(
                    trade_date=trade_date,
                    close_price=_profit_reference_close(row, previous_row),
                )

            if lifecycle is not None and lifecycle.state == LifecycleState.PENDING_FULL_EXIT:
                event = lifecycle.retry_pending_exit(trade_date=trade_date, price=float(row.bar.close))
                lifecycle_events.append(event)
                _collect_new_closed_trades(lifecycle, closed_counts_by_symbol, closed_trades)
                lifecycle_snapshots.append(lifecycle.snapshot(trade_date=trade_date))
                continue

            if lifecycle is None or lifecycle.total_quantity <= 0:
                entry_intent = entry_method.evaluate(
                    symbol=symbol,
                    trade_date=trade_date,
                    row=row,
                    previous_row=previous_row,
                )
                entry_intent = _intent_with_attribution(
                    entry_intent,
                    entry_attribution_context,
                    symbol=symbol,
                    trade_date=trade_date,
                )
                if entry_intent.intent_type != TradeIntentType.ENTER:
                    intents.append(entry_intent)
                    continue

                quantity = config.buy_quantity_for_price(float(row.bar.open))
                if _open_holding_count(lifecycles) >= config.max_holding_count:
                    intents.append(
                        _intent_with_sizing(
                            entry_intent,
                            config=config,
                            price=float(row.bar.open),
                            requested_quantity=quantity,
                            business_executable_quantity=0,
                            blocked_by="MAX_HOLDING_COUNT",
                        )
                    )
                    lifecycle_events.append(
                        _rejected_buy_event(
                            symbol=symbol,
                            trade_date=trade_date,
                            reason_code=entry_intent.reason_code,
                            requested_quantity=quantity,
                            price=float(row.bar.open),
                            blocked_by="MAX_HOLDING_COUNT",
                        )
                    )
                    continue

                lifecycle = ExecutionLifecycleComponent(symbol=symbol, board_lot_size=config.board_lot_size)
                lifecycles[symbol] = lifecycle
                closed_counts_by_symbol[symbol] = 0
                add_on_count_by_symbol[symbol] = 0
                event = lifecycle.buy(
                    trade_date=trade_date,
                    price=float(row.bar.open),
                    quantity=quantity,
                    reason_code=entry_intent.reason_code,
                )
                lifecycle_events.append(event)
                if event.accepted:
                    scale_out_context_by_symbol[symbol] = _scale_out_entry_context(row)
                    scale_out_missing_recorded_by_symbol[symbol] = False
                intents.append(
                    _intent_with_sizing(
                        entry_intent,
                        config=config,
                        price=float(row.bar.open),
                        requested_quantity=quantity,
                        business_executable_quantity=event.executed_quantity if event.accepted else 0,
                        blocked_by=None if event.accepted else event.blocked_by or "BUY_REJECTED",
                    )
                )
                lifecycle_snapshots.append(lifecycle.snapshot(trade_date=trade_date))
                continue

            stop_intent = stop_loss_method.evaluate(
                symbol=symbol,
                trade_date=trade_date,
                entry_price=lifecycle.adjusted_remaining_cost_basis,
                current_price=float(row.bar.close),
                row=row,
                previous_row=previous_row,
            )
            stop_intent = _intent_with_attribution(
                stop_intent,
                entry_attribution_context,
                symbol=symbol,
                trade_date=trade_date,
            )
            profit_intent = profit_exit_method.evaluate(
                symbol=symbol,
                trade_date=trade_date,
                row=row,
                previous_row=previous_row,
                adjusted_remaining_cost_basis=lifecycle.adjusted_remaining_cost_basis,
                cost_recovered=lifecycle.cost_recovered,
            )
            profit_intent = _intent_with_attribution(
                profit_intent,
                entry_attribution_context,
                symbol=symbol,
                trade_date=trade_date,
            )
            intents.extend((stop_intent, profit_intent))

            full_exit_intent = _full_exit_intent(stop_intent, profit_intent)
            if full_exit_intent is not None:
                lifecycle.enter_exit_watch(trade_date=trade_date, reason_code=full_exit_intent.reason_code)
                event = lifecycle.confirm_full_exit(
                    trade_date=trade_date,
                    price=float(row.bar.close),
                    reason_code=full_exit_intent.reason_code,
                )
                lifecycle_events.append(event)
                _collect_new_closed_trades(lifecycle, closed_counts_by_symbol, closed_trades)
                lifecycle_snapshots.append(lifecycle.snapshot(trade_date=trade_date))
                continue

            watch_block = _watch_block_reason(stop_intent, profit_intent)
            if watch_block is not None:
                lifecycle.enter_exit_watch(trade_date=trade_date, reason_code=watch_block)

            if watch_block is not None:
                add_on_intent = _evaluate_add_on(
                    add_on_method,
                    symbol=symbol,
                    trade_date=trade_date,
                    lifecycle=lifecycle,
                    row=row,
                    previous_row=previous_row,
                    add_on_count=add_on_count_by_symbol.get(symbol, 0),
                    entry_attribution_context=entry_attribution_context,
                )
                intents.append(
                    _intent_with_sizing(
                        add_on_intent,
                        config=config,
                        price=float(row.bar.open),
                        requested_quantity=config.buy_quantity_for_price(float(row.bar.open)),
                        business_executable_quantity=0,
                        blocked_by=watch_block,
                    )
                )
                lifecycle_snapshots.append(lifecycle.snapshot(trade_date=trade_date))
                continue

            scale_out_check = _scale_out_check(
                lifecycle,
                row=row,
                config=config,
                entry_context=scale_out_context_by_symbol.get(symbol),
            )
            if scale_out_check.missing_reason and not scale_out_missing_recorded_by_symbol.get(symbol, False):
                intents.append(
                    _scale_out_missing_intent(
                        symbol=symbol,
                        trade_date=trade_date,
                        reason_code=scale_out_check.missing_reason,
                        entry_context=scale_out_context_by_symbol.get(symbol),
                    )
                )
                scale_out_missing_recorded_by_symbol[symbol] = True
            if scale_out_check.confirmation_required and scale_out_check.confirmation_passed is False:
                intents.append(
                    _scale_out_confirmation_blocked_intent(
                        symbol=symbol,
                        trade_date=trade_date,
                        check=scale_out_check,
                        entry_context=scale_out_context_by_symbol.get(symbol),
                    )
                )
            if scale_out_check.stage is not None:
                event = lifecycle.scale_out(
                    trade_date=trade_date,
                    price=float(row.bar.close),
                    stage=scale_out_check.stage,
                    reason_code=_scale_out_reason_code(scale_out_check.stage, config=config),
                    scale_out_mode=config.scale_out_mode,
                    entry_signal_date=scale_out_context_by_symbol.get(symbol).entry_signal_date
                    if scale_out_context_by_symbol.get(symbol) is not None
                    else None,
                    entry_signal_day_atr14=scale_out_context_by_symbol.get(symbol).entry_signal_day_atr14
                    if scale_out_context_by_symbol.get(symbol) is not None
                    else None,
                    atr_multiple=scale_out_check.atr_multiple,
                    scale_out_trigger_price=scale_out_check.trigger_price,
                    confirmation_required=scale_out_check.confirmation_required,
                    confirmation_passed=scale_out_check.confirmation_passed,
                    confirmation_mode=scale_out_check.confirmation_mode,
                    confirmation_block_reason=scale_out_check.confirmation_block_reason,
                    kdj_j=scale_out_check.kdj_j,
                    cci14=scale_out_check.cci14,
                    boll_up20_2=scale_out_check.boll_up20_2,
                    boll_up_distance_pct=scale_out_check.boll_up_distance_pct,
                )
                lifecycle_events.append(event)
                lifecycle.advance_day(trade_date=trade_date, close_price=float(row.bar.close))
                lifecycle_snapshots.append(lifecycle.snapshot(trade_date=trade_date))
                continue

            add_on_intent = _evaluate_add_on(
                add_on_method,
                symbol=symbol,
                trade_date=trade_date,
                lifecycle=lifecycle,
                row=row,
                previous_row=previous_row,
                add_on_count=add_on_count_by_symbol.get(symbol, 0),
                entry_attribution_context=entry_attribution_context,
            )
            if add_on_intent.intent_type != TradeIntentType.ADD_ON:
                intents.append(add_on_intent)
                lifecycle_snapshots.append(lifecycle.snapshot(trade_date=trade_date))
                continue

            if not lifecycle.can_add_on(trade_date):
                intents.append(
                    _intent_with_sizing(
                        add_on_intent,
                        config=config,
                        price=float(row.bar.open),
                        requested_quantity=config.buy_quantity_for_price(float(row.bar.open)),
                        business_executable_quantity=0,
                        blocked_by="LIFECYCLE_ADD_ON_BLOCKED",
                    )
                )
                lifecycle_snapshots.append(lifecycle.snapshot(trade_date=trade_date))
                continue

            quantity = config.buy_quantity_for_price(float(row.bar.open))
            event = lifecycle.buy(
                trade_date=trade_date,
                price=float(row.bar.open),
                quantity=quantity,
                reason_code=add_on_intent.reason_code,
            )
            lifecycle_events.append(event)
            if event.accepted:
                add_on_count_by_symbol[symbol] = add_on_count_by_symbol.get(symbol, 0) + 1
                intents.append(
                    _intent_with_sizing(
                        add_on_intent,
                        config=config,
                        price=float(row.bar.open),
                        requested_quantity=quantity,
                        business_executable_quantity=event.executed_quantity,
                    )
                )
            else:
                intents.append(
                    _intent_with_sizing(
                        add_on_intent,
                        config=config,
                        price=float(row.bar.open),
                        requested_quantity=quantity,
                        business_executable_quantity=0,
                        blocked_by=event.blocked_by or "ADD_ON_REJECTED",
                    )
                )
            lifecycle_snapshots.append(lifecycle.snapshot(trade_date=trade_date))

    end_date = dates[-1]
    if config.force_exit_at_end:
        for symbol in symbols:
            lifecycle = lifecycles.get(symbol)
            if lifecycle is None or lifecycle.total_quantity <= 0:
                continue
            price = latest_prices.get(symbol)
            if price is None:
                continue
            result = lifecycle.finish_run(end_date=end_date, price=price, reason_code="END_LIQUIDATION")
            end_run_results.append(result)
            if result.forced_exit_event is not None:
                lifecycle_events.append(result.forced_exit_event)
            _collect_new_closed_trades(lifecycle, closed_counts_by_symbol, closed_trades)
            lifecycle_snapshots.append(lifecycle.snapshot(trade_date=end_date))

    open_positions = tuple(
        lifecycle.snapshot(trade_date=end_date)
        for symbol in symbols
        if (lifecycle := lifecycles.get(symbol)) is not None and lifecycle.total_quantity > 0
    )
    return BaomaBusinessRunResult(
        intents=tuple(intents),
        lifecycle_events=tuple(lifecycle_events),
        lifecycle_snapshots=tuple(lifecycle_snapshots),
        closed_trades=tuple(closed_trades),
        open_positions=open_positions,
        end_run_results=tuple(end_run_results),
    )


def _required_indicators(*methods: object, config: BaomaBusinessRunConfig) -> tuple[IndicatorRequirement, ...]:
    requirements: set[IndicatorRequirement] = set()
    for method in methods:
        requirements.update(getattr(method, "required_indicators"))
    if config.scale_out_mode == "atr_multiple":
        requirements.add(IndicatorRequirement("atr14", "D"))
        confirmation = config.second_scale_out_confirmation
        if confirmation.enabled and confirmation.requires_kdj_cci:
            requirements.add(IndicatorRequirement("kdj", "D"))
            requirements.add(IndicatorRequirement("cci14", "D"))
        if confirmation.enabled and confirmation.requires_boll_up_distance:
            requirements.add(IndicatorRequirement("boll_up20_2", "D"))
    return tuple(sorted(requirements, key=lambda item: (item.timeframe, item.name)))


def _rows_by_key(
    bars_by_symbol: Mapping[str, Sequence[DailyBar]],
    *,
    indicators_by_symbol: Mapping[str, IndicatorFrame],
    indicator_requirements: Sequence[IndicatorRequirement],
) -> dict[tuple[str, date], MarketFeatureRow]:
    rows_by_key: dict[tuple[str, date], MarketFeatureRow] = {}
    for symbol, bars in bars_by_symbol.items():
        symbol_bars = tuple(sorted(bars, key=lambda bar: bar.trade_date))
        if not symbol_bars:
            raise ValueError(f"bars cannot be empty for {symbol}")
        if any(bar.symbol != symbol for bar in symbol_bars):
            raise ValueError(f"bars key {symbol!r} must match contained symbols")

        indicator_frame = indicators_by_symbol.get(symbol) or indicator_frame_from_snapshots(
            build_indicator_snapshots_for_requirements(
                symbol_bars,
                indicator_requirements=indicator_requirements,
            )
        )
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


def _previous_rows_by_key(
    rows_by_key: Mapping[tuple[str, date], MarketFeatureRow],
) -> dict[tuple[str, date], MarketFeatureRow]:
    previous: dict[tuple[str, date], MarketFeatureRow] = {}
    rows_by_symbol: dict[str, list[MarketFeatureRow]] = {}
    for row in rows_by_key.values():
        rows_by_symbol.setdefault(row.symbol, []).append(row)

    for rows in rows_by_symbol.values():
        ordered_rows = tuple(sorted(rows, key=lambda row: row.trade_date))
        for index, row in enumerate(ordered_rows):
            if index > 0:
                previous[(row.symbol, row.trade_date)] = ordered_rows[index - 1]
    return previous


def _profit_reference_close(row: MarketFeatureRow, previous_row: MarketFeatureRow | None) -> float:
    if previous_row is not None:
        return float(previous_row.bar.close)
    return float(row.bar.close)


def _open_holding_count(lifecycles: Mapping[str, ExecutionLifecycleComponent]) -> int:
    return sum(1 for lifecycle in lifecycles.values() if lifecycle.total_quantity > 0)


def _full_exit_intent(stop_intent: TradeIntent, profit_intent: TradeIntent) -> TradeIntent | None:
    if stop_intent.intent_type == TradeIntentType.EXIT_LOSS:
        return stop_intent
    if profit_intent.intent_type == TradeIntentType.EXIT_PROFIT:
        return profit_intent
    return None


def _watch_block_reason(stop_intent: TradeIntent, profit_intent: TradeIntent) -> str | None:
    stop_watch = _previous_ma_break(stop_intent)
    profit_watch = _previous_ma_break(profit_intent)
    if stop_watch and profit_watch:
        return "FULL_EXIT_WATCH"
    if stop_watch:
        return "MA60_EXIT_WATCH"
    if profit_watch:
        return "MA25_PROFIT_EXIT_WATCH"
    return None


def _previous_ma_break(intent: TradeIntent) -> bool:
    checks = intent.signal_values.get("checks")
    if not isinstance(checks, Mapping):
        return False
    return bool(checks.get("previous_price_below_ma"))


def _scale_out_check(
    lifecycle: ExecutionLifecycleComponent,
    *,
    row: MarketFeatureRow,
    config: BaomaBusinessRunConfig,
    entry_context: _ScaleOutEntryContext | None,
) -> _ScaleOutCheck:
    if lifecycle.total_quantity <= 0 or lifecycle.sellable_quantity(row.trade_date) <= 0:
        return _ScaleOutCheck()
    if config.scale_out_mode == "atr_multiple":
        return _atr_scale_out_check(
            lifecycle,
            row=row,
            config=config,
            entry_context=entry_context,
        )
    return _fixed_percent_scale_out_check(lifecycle, row=row, config=config)


def _fixed_percent_scale_out_check(
    lifecycle: ExecutionLifecycleComponent,
    *,
    row: MarketFeatureRow,
    config: BaomaBusinessRunConfig,
) -> _ScaleOutCheck:
    if lifecycle.cost_recovered:
        return _ScaleOutCheck(stage=_next_incomplete_scale_out_stage(lifecycle))

    cost_basis = lifecycle.adjusted_remaining_cost_basis
    if cost_basis is None or cost_basis <= 0:
        return _ScaleOutCheck()

    unrealized_return = float(row.bar.close) / cost_basis - 1.0
    if (
        not lifecycle.is_scale_out_stage_completed(ScaleOutStage.FIVE_PERCENT)
        and unrealized_return > config.first_scale_out_return
    ):
        return _ScaleOutCheck(stage=ScaleOutStage.FIVE_PERCENT)
    if (
        not lifecycle.is_scale_out_stage_completed(ScaleOutStage.FIFTEEN_PERCENT)
        and unrealized_return > config.second_scale_out_return
    ):
        return _ScaleOutCheck(stage=ScaleOutStage.FIFTEEN_PERCENT)
    return _ScaleOutCheck()


def _atr_scale_out_check(
    lifecycle: ExecutionLifecycleComponent,
    *,
    row: MarketFeatureRow,
    config: BaomaBusinessRunConfig,
    entry_context: _ScaleOutEntryContext | None,
) -> _ScaleOutCheck:
    if entry_context is None:
        return _ScaleOutCheck(missing_reason="ATR_SCALE_OUT_ENTRY_CONTEXT_MISSING")
    if entry_context.entry_signal_day_atr14 is None:
        return _ScaleOutCheck(missing_reason=entry_context.missing_reason or "ATR_SCALE_OUT_ATR14_UNAVAILABLE")

    cost_basis = lifecycle.adjusted_remaining_cost_basis
    if cost_basis is None:
        return _ScaleOutCheck()

    current_close = float(row.bar.close)
    if not lifecycle.is_scale_out_stage_completed(ScaleOutStage.FIVE_PERCENT):
        atr_multiple = _scale_out_atr_multiple_for_stage(ScaleOutStage.FIVE_PERCENT, config)
        trigger_price = cost_basis + entry_context.entry_signal_day_atr14 * atr_multiple
        if current_close > trigger_price:
            return _ScaleOutCheck(
                stage=ScaleOutStage.FIVE_PERCENT,
                atr_multiple=atr_multiple,
                trigger_price=trigger_price,
            )

    if not lifecycle.is_scale_out_stage_completed(ScaleOutStage.FIFTEEN_PERCENT):
        atr_multiple = _scale_out_atr_multiple_for_stage(ScaleOutStage.FIFTEEN_PERCENT, config)
        trigger_price = cost_basis + entry_context.entry_signal_day_atr14 * atr_multiple
        if current_close > trigger_price:
            confirmation = _second_scale_out_confirmation(row=row, config=config)
            if confirmation.confirmation_required and confirmation.confirmation_passed is False:
                return _ScaleOutCheck(
                    atr_multiple=atr_multiple,
                    trigger_price=trigger_price,
                    confirmation_required=confirmation.confirmation_required,
                    confirmation_passed=confirmation.confirmation_passed,
                    confirmation_mode=confirmation.confirmation_mode,
                    confirmation_block_reason=confirmation.confirmation_block_reason,
                    kdj_j=confirmation.kdj_j,
                    cci14=confirmation.cci14,
                    boll_up20_2=confirmation.boll_up20_2,
                    boll_up_distance_pct=confirmation.boll_up_distance_pct,
                    confirmation_checks=confirmation.confirmation_checks,
                )
            return _ScaleOutCheck(
                stage=ScaleOutStage.FIFTEEN_PERCENT,
                atr_multiple=atr_multiple,
                trigger_price=trigger_price,
                confirmation_required=confirmation.confirmation_required,
                confirmation_passed=confirmation.confirmation_passed,
                confirmation_mode=confirmation.confirmation_mode,
                confirmation_block_reason=confirmation.confirmation_block_reason,
                kdj_j=confirmation.kdj_j,
                cci14=confirmation.cci14,
                boll_up20_2=confirmation.boll_up20_2,
                boll_up_distance_pct=confirmation.boll_up_distance_pct,
                confirmation_checks=confirmation.confirmation_checks,
            )

    return _ScaleOutCheck()


def _second_scale_out_confirmation(
    *,
    row: MarketFeatureRow,
    config: BaomaBusinessRunConfig,
) -> _ScaleOutCheck:
    rule = config.second_scale_out_confirmation
    if not rule.enabled:
        return _ScaleOutCheck(confirmation_required=False)

    kdj_j: float | None = None
    cci14: float | None = None
    boll_up20_2: float | None = None
    boll_up_distance_pct: float | None = None
    checks: dict[str, bool | None] = {
        "confirmation_required": True,
    }
    block_reasons: list[str] = []

    if rule.requires_kdj_cci:
        try:
            kdj_j = float(row.indicators.kdj_at("D").j)
        except KeyError:
            block_reasons.append("KDJ_J_UNAVAILABLE")
            checks["kdj_j_at_or_above_min"] = None
        else:
            assert rule.min_kdj_j is not None
            kdj_passed = kdj_j >= rule.min_kdj_j
            checks["kdj_j_at_or_above_min"] = kdj_passed
            if not kdj_passed:
                block_reasons.append("KDJ_J_BELOW_MIN")

        try:
            cci14 = float(row.indicators.cci_at(14, "D").value)
        except KeyError:
            block_reasons.append("CCI14_UNAVAILABLE")
            checks["cci14_at_or_above_min"] = None
        else:
            assert rule.min_cci14 is not None
            cci_passed = cci14 >= rule.min_cci14
            checks["cci14_at_or_above_min"] = cci_passed
            if not cci_passed:
                block_reasons.append("CCI14_BELOW_MIN")

    if rule.requires_boll_up_distance:
        try:
            boll_up20_2 = float(row.indicators.boll_up_at(20, 2.0, "D"))
        except KeyError:
            block_reasons.append("BOLL_UP20_2_UNAVAILABLE")
            checks["boll_up_distance_at_or_above_min"] = None
        else:
            if boll_up20_2 <= 0:
                block_reasons.append("BOLL_UP20_2_UNAVAILABLE")
                checks["boll_up_distance_at_or_above_min"] = None
            else:
                assert rule.min_boll_up_distance is not None
                boll_up_distance_pct = float(row.bar.close) / boll_up20_2 - 1.0
                boll_passed = boll_up_distance_pct >= rule.min_boll_up_distance
                checks["boll_up_distance_at_or_above_min"] = boll_passed
                if not boll_passed:
                    block_reasons.append("BOLL_UP_DISTANCE_BELOW_MIN")

    checks["required_values_available"] = not any(reason.endswith("_UNAVAILABLE") for reason in block_reasons)
    confirmation_passed = not block_reasons
    return _ScaleOutCheck(
        confirmation_required=True,
        confirmation_passed=confirmation_passed,
        confirmation_mode=rule.mode,
        confirmation_block_reason=";".join(block_reasons) if block_reasons else None,
        kdj_j=kdj_j,
        cci14=cci14,
        boll_up20_2=boll_up20_2,
        boll_up_distance_pct=boll_up_distance_pct,
        confirmation_checks=checks,
    )


def _atr_scale_out_trigger_price(
    lifecycle: ExecutionLifecycleComponent,
    entry_context: _ScaleOutEntryContext,
    atr_multiple: float,
) -> float | None:
    cost_basis = lifecycle.adjusted_remaining_cost_basis
    if cost_basis is None or entry_context.entry_signal_day_atr14 is None:
        return None
    return cost_basis + entry_context.entry_signal_day_atr14 * atr_multiple


def _scale_out_atr_multiple_for_stage(stage: ScaleOutStage, config: BaomaBusinessRunConfig) -> float:
    if stage == ScaleOutStage.FIVE_PERCENT:
        assert config.first_scale_out_atr_multiple is not None
        return float(config.first_scale_out_atr_multiple)
    assert config.second_scale_out_atr_multiple is not None
    return float(config.second_scale_out_atr_multiple)


def _next_incomplete_scale_out_stage(lifecycle: ExecutionLifecycleComponent) -> ScaleOutStage | None:
    if not lifecycle.is_scale_out_stage_completed(ScaleOutStage.FIVE_PERCENT):
        return ScaleOutStage.FIVE_PERCENT
    if not lifecycle.is_scale_out_stage_completed(ScaleOutStage.FIFTEEN_PERCENT):
        return ScaleOutStage.FIFTEEN_PERCENT
    return None


def _scale_out_reason_code(stage: ScaleOutStage, *, config: BaomaBusinessRunConfig) -> str:
    if config.scale_out_mode == "atr_multiple":
        if stage == ScaleOutStage.FIVE_PERCENT:
            return "BAOMA_SCALE_OUT_ATR_FIRST_TRIGGERED"
        return "BAOMA_SCALE_OUT_ATR_SECOND_TRIGGERED"
    if stage == ScaleOutStage.FIVE_PERCENT:
        return "BAOMA_SCALE_OUT_5_PERCENT_TRIGGERED"
    return "BAOMA_SCALE_OUT_15_PERCENT_TRIGGERED"


def _scale_out_entry_context(row: MarketFeatureRow) -> _ScaleOutEntryContext:
    try:
        atr14 = row.indicators.atr_at(14).value
    except KeyError:
        return _ScaleOutEntryContext(
            entry_signal_date=row.trade_date,
            entry_signal_day_atr14=None,
            missing_reason="ATR_SCALE_OUT_ATR14_UNAVAILABLE",
        )
    return _ScaleOutEntryContext(
        entry_signal_date=row.trade_date,
        entry_signal_day_atr14=atr14,
    )


def _scale_out_missing_intent(
    *,
    symbol: str,
    trade_date: date,
    reason_code: str,
    entry_context: _ScaleOutEntryContext | None,
) -> TradeIntent:
    return TradeIntent(
        intent_type=TradeIntentType.HOLD,
        symbol=symbol,
        trade_date=trade_date,
        method_name="atr_based_scale_out",
        reason_code=reason_code,
        signal_values={
            "entry_signal_date": entry_context.entry_signal_date.isoformat() if entry_context is not None else None,
            "entry_signal_day_atr14": entry_context.entry_signal_day_atr14 if entry_context is not None else None,
            "checks": {
                "entry_signal_day_atr14_available": bool(
                    entry_context is not None and entry_context.entry_signal_day_atr14 is not None
                )
            },
        },
    )


def _scale_out_confirmation_blocked_intent(
    *,
    symbol: str,
    trade_date: date,
    check: _ScaleOutCheck,
    entry_context: _ScaleOutEntryContext | None,
) -> TradeIntent:
    return TradeIntent(
        intent_type=TradeIntentType.HOLD,
        symbol=symbol,
        trade_date=trade_date,
        method_name="atr_based_scale_out",
        reason_code="ATR_SCALE_OUT_SECOND_CONFIRMATION_BLOCKED",
        blocked_by="SECOND_SCALE_OUT_CONFIRMATION",
        signal_values={
            "entry_signal_date": entry_context.entry_signal_date.isoformat() if entry_context is not None else None,
            "entry_signal_day_atr14": entry_context.entry_signal_day_atr14 if entry_context is not None else None,
            "atr_multiple": check.atr_multiple,
            "scale_out_trigger_price": check.trigger_price,
            "confirmation_required": check.confirmation_required,
            "confirmation_passed": check.confirmation_passed,
            "confirmation_mode": check.confirmation_mode,
            "confirmation_block_reason": check.confirmation_block_reason,
            "kdj_j": check.kdj_j,
            "cci14": check.cci14,
            "boll_up20_2": check.boll_up20_2,
            "boll_up_distance_pct": check.boll_up_distance_pct,
            "checks": dict(check.confirmation_checks),
        },
    )


def _evaluate_add_on(
    add_on_method: BaomaAddOn,
    *,
    symbol: str,
    trade_date: date,
    lifecycle: ExecutionLifecycleComponent,
    row: MarketFeatureRow,
    previous_row: MarketFeatureRow | None,
    add_on_count: int,
    entry_attribution_context: EntryAttributionContext | None = None,
) -> TradeIntent:
    intent = add_on_method.evaluate(
        symbol=symbol,
        trade_date=trade_date,
        current_quantity=lifecycle.total_quantity,
        entry_price=lifecycle.adjusted_remaining_cost_basis,
        current_price=float(row.bar.open),
        add_on_count=add_on_count,
        ever_profitable=lifecycle.ever_profitable,
        row=row,
        previous_row=previous_row,
    )
    return _intent_with_attribution(
        intent,
        entry_attribution_context,
        symbol=symbol,
        trade_date=trade_date,
    )


def _intent_with_attribution(
    intent: TradeIntent,
    context: EntryAttributionContext | None,
    *,
    symbol: str,
    trade_date: date,
) -> TradeIntent:
    if context is None:
        return intent
    return with_entry_attribution_evidence(intent, context.evidence_for(symbol, trade_date))


def _collect_new_closed_trades(
    lifecycle: ExecutionLifecycleComponent,
    closed_counts_by_symbol: dict[str, int],
    closed_trades: list[LifecycleClosedTrade],
) -> None:
    current_count = closed_counts_by_symbol.get(lifecycle.symbol, 0)
    new_closed_trades = lifecycle.closed_trades[current_count:]
    if new_closed_trades:
        closed_trades.extend(new_closed_trades)
        closed_counts_by_symbol[lifecycle.symbol] = lifecycle.closed_trades_count


def _blocked_intent(intent: TradeIntent, blocked_by: str) -> TradeIntent:
    return replace(intent, blocked_by=blocked_by)


def _intent_with_sizing(
    intent: TradeIntent,
    *,
    config: BaomaBusinessRunConfig,
    price: float,
    requested_quantity: int,
    business_executable_quantity: int,
    blocked_by: str | None = None,
) -> TradeIntent:
    if intent.intent_type not in {TradeIntentType.ENTER, TradeIntentType.ADD_ON}:
        return _blocked_intent(intent, blocked_by) if blocked_by is not None else intent

    sizing = {
        "rule": "baoma_fixed_slice",
        "total_asset_value": config.total_asset_value,
        "max_holding_count": config.max_holding_count,
        "per_symbol_max_value": config.per_symbol_max_value,
        "buy_slice_fraction": config.buy_slice_fraction,
        "target_value": config.buy_slice_value,
        "price": price,
        "board_lot_size": config.board_lot_size,
        "requested_quantity": requested_quantity,
        "business_executable_quantity": business_executable_quantity,
    }
    if blocked_by is not None:
        sizing["blocked_by"] = blocked_by

    signal_values = dict(intent.signal_values)
    signal_values["sizing"] = sizing
    return replace(intent, signal_values=signal_values, blocked_by=blocked_by or intent.blocked_by)


def _rejected_buy_event(
    *,
    symbol: str,
    trade_date: date,
    reason_code: str,
    requested_quantity: int,
    price: float,
    blocked_by: str,
) -> LifecycleExecutionEvent:
    return LifecycleExecutionEvent(
        trade_date=trade_date,
        symbol=symbol,
        side="buy",
        status="rejected",
        reason_code=reason_code,
        requested_quantity=requested_quantity,
        executed_quantity=0,
        price=price,
        blocked_by=blocked_by,
    )
