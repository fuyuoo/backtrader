from dataclasses import dataclass
from datetime import date, timedelta

from attbacktrader.data import DailyBar, IndexBar, StockIndustryMembership
from attbacktrader.engines.backtrader import BacktraderAShareSettings, run_trend_template_v1_backtrader
from attbacktrader.engines.business import run_trend_template_v1_portfolio_business
from attbacktrader.features import (
    IndicatorRequirement,
    build_indicator_snapshots_for_requirements,
    indicator_frame_from_snapshots,
)
from attbacktrader.strategies import (
    EntryAttributionFilterRule,
    TradeIntent,
    TradeIntentType,
    build_entry_attribution_context,
)
from attbacktrader.strategies.methods import FixedPercentStop, KdjOverheatedExit
from attbacktrader.strategies.templates import TrendTemplateV1


def test_entry_attribution_context_builds_symbol_market_and_industry_evidence() -> None:
    bars = _daily_bars("000001.SZ", count=70, start_close=10.0, step=0.3)
    market_bars = _index_bars("000300.SH", count=70, start_close=3000.0, step=8.0)
    industry_bars = _index_bars("801780.SI", count=70, start_close=50.0, step=-0.4)
    frame = indicator_frame_from_snapshots(
        build_indicator_snapshots_for_requirements(
            bars,
            indicator_requirements=(
                IndicatorRequirement("kdj", "D"),
                IndicatorRequirement("ma20", "D"),
                IndicatorRequirement("ma25", "D"),
                IndicatorRequirement("ma60", "D"),
            ),
        )
    )

    context = build_entry_attribution_context(
        bars_by_symbol={"000001.SZ": bars},
        indicators_by_symbol={"000001.SZ": frame},
        benchmark_bars_by_symbol={"000300.SH": market_bars},
        industry_index_bars_by_symbol={"801780.SI": industry_bars},
        memberships_by_symbol={"000001.SZ": (_membership("000001.SZ", "801780.SI"),)},
    )

    evidence = context.evidence_for("000001.SZ", bars[-1].trade_date)

    assert evidence is not None
    assert evidence.values["symbol.ma.ma20"] > 0
    assert evidence.values["symbol.ma.ma25"] > 0
    assert evidence.values["symbol.ma.ma60"] > 0
    assert evidence.checks["symbol.ma.price_above_ma25"] is True
    assert evidence.checks["symbol.ma.price_above_ma60"] is True
    assert evidence.checks["symbol.ma.ma20_above_ma60"] is True
    assert evidence.checks["symbol.ma.bullish_trend"] is True
    assert evidence.categories["symbol.ma.trend_state"] == "bullish"
    assert evidence.checks["market.hs300.bullish_trend"] is True
    assert evidence.values["market.hs300.ma20"] > evidence.values["market.hs300.ma60"]
    assert evidence.categories["market.hs300.trend_state"] == "bullish"
    assert evidence.categories["industry.sw_l1.code"] == "801780.SI"
    assert evidence.checks["industry.kdj.j_below_threshold"] is True


def test_entry_attribution_context_does_not_default_missing_long_ma_factors() -> None:
    bars = _daily_bars("000001.SZ", count=50, start_close=10.0, step=0.3)
    frame = indicator_frame_from_snapshots(
        build_indicator_snapshots_for_requirements(
            bars,
            indicator_requirements=(
                IndicatorRequirement("ma20", "D"),
                IndicatorRequirement("ma25", "D"),
                IndicatorRequirement("ma60", "D"),
            ),
        )
    )

    context = build_entry_attribution_context(
        bars_by_symbol={"000001.SZ": bars},
        indicators_by_symbol={"000001.SZ": frame},
    )

    evidence = context.evidence_for("000001.SZ", bars[-1].trade_date)

    assert evidence is not None
    assert "symbol.ma.ma20" in evidence.values
    assert "symbol.ma.ma25" in evidence.values
    assert "symbol.ma.ma60" not in evidence.values
    assert "symbol.ma.price_above_ma60" not in evidence.checks
    assert "symbol.ma.bullish_trend" not in evidence.checks
    assert "symbol.ma.trend_state" not in evidence.categories


def test_business_engine_injects_entry_attribution_into_entry_intent() -> None:
    bars = _daily_bars("000001.SZ", count=70, start_close=10.0, step=0.3)
    requirements = (
        IndicatorRequirement("kdj", "D"),
        IndicatorRequirement("ma25", "D"),
    )
    frame = indicator_frame_from_snapshots(
        build_indicator_snapshots_for_requirements(bars, indicator_requirements=requirements)
    )
    context = build_entry_attribution_context(
        bars_by_symbol={"000001.SZ": bars},
        indicators_by_symbol={"000001.SZ": frame},
    )
    strategy = TrendTemplateV1(
        entry_method=_LastDayEntry(entry_date=bars[-1].trade_date),
        profit_taking_method=KdjOverheatedExit(),
        stop_loss_method=FixedPercentStop(loss_percent=0.05),
    )

    result = run_trend_template_v1_portfolio_business(
        strategy,
        {"000001.SZ": bars},
        initial_cash=1000000.0,
        stake=100,
        indicators_by_symbol={"000001.SZ": frame},
        risk_group_by_symbol={"000001.SZ": "801780.SI"},
        entry_attribution_context=context,
    )

    entry_intent = next(intent for intent in result.strategy_result.intents if intent.intent_type == TradeIntentType.ENTER)
    attribution = entry_intent.signal_values["attribution"]

    assert attribution["checks"]["symbol.ma.price_above_ma25"] is True
    assert attribution["values"]["symbol.ma.ma25"] > 0
    assert attribution["categories"]["sizing.risk_group"] == "801780.SI"


def test_backtrader_engine_injects_entry_attribution_into_exit_intent() -> None:
    bars = _daily_bars("000001.SZ", count=75, start_close=10.0, step=0.3)
    market_bars = _index_bars("000300.SH", count=75, start_close=3000.0, step=8.0)
    industry_bars = _index_bars("801780.SI", count=75, start_close=50.0, step=-0.4)
    requirements = (
        IndicatorRequirement("kdj", "D"),
        IndicatorRequirement("ma20", "D"),
        IndicatorRequirement("ma25", "D"),
        IndicatorRequirement("ma60", "D"),
    )
    frame = indicator_frame_from_snapshots(
        build_indicator_snapshots_for_requirements(bars, indicator_requirements=requirements)
    )
    context = build_entry_attribution_context(
        bars_by_symbol={"000001.SZ": bars},
        indicators_by_symbol={"000001.SZ": frame},
        benchmark_bars_by_symbol={"000300.SH": market_bars},
        industry_index_bars_by_symbol={"801780.SI": industry_bars},
        memberships_by_symbol={"000001.SZ": (_membership("000001.SZ", "801780.SI"),)},
    )

    result = run_trend_template_v1_backtrader(
        bars,
        initial_cash=1000000.0,
        stake=100,
        indicators=frame,
        risk_group_by_symbol={"000001.SZ": "801780.SI"},
        entry_attribution_context=context,
        entry_method=_DateEntry(entry_date=bars[62].trade_date),
        profit_taking_method=_DateProfitExit(exit_date=bars[70].trade_date),
        stop_loss_method=FixedPercentStop(loss_percent=0.5),
        ashare_settings=BacktraderAShareSettings(enabled=False),
    )

    exit_intent = next(
        intent
        for intent in result.strategy_result.intents
        if intent.intent_type == TradeIntentType.EXIT_PROFIT
    )
    attribution = exit_intent.signal_values["attribution"]

    assert attribution["checks"]["symbol.ma.price_above_ma25"] is True
    assert attribution["checks"]["symbol.ma.bullish_trend"] is True
    assert attribution["checks"]["market.hs300.bullish_trend"] is True
    assert attribution["checks"]["industry.kdj.j_below_threshold"] is True
    assert attribution["values"]["symbol.ma.ma60"] > 0
    assert attribution["categories"]["market.hs300.trend_state"] == "bullish"


def test_business_engine_applies_configured_entry_attribution_filter_before_sizing() -> None:
    bars = _daily_bars("000001.SZ", count=70, start_close=30.0, step=-0.3)
    frame = indicator_frame_from_snapshots(
        build_indicator_snapshots_for_requirements(
            bars,
            indicator_requirements=(
                IndicatorRequirement("kdj", "D"),
                IndicatorRequirement("ma20", "D"),
                IndicatorRequirement("ma25", "D"),
                IndicatorRequirement("ma60", "D"),
            ),
        )
    )
    context = build_entry_attribution_context(
        bars_by_symbol={"000001.SZ": bars},
        indicators_by_symbol={"000001.SZ": frame},
        enabled_factor_keys=("symbol.ma.price_above_ma25",),
        entry_filter=EntryAttributionFilterRule(
            enabled=True,
            required_checks=("symbol.ma.price_above_ma25",),
            missing_policy="block",
        ),
    )
    strategy = TrendTemplateV1(
        entry_method=_LastDayEntry(entry_date=bars[-1].trade_date),
        profit_taking_method=KdjOverheatedExit(),
        stop_loss_method=FixedPercentStop(loss_percent=0.05),
    )

    result = run_trend_template_v1_portfolio_business(
        strategy,
        {"000001.SZ": bars},
        initial_cash=1000000.0,
        stake=100,
        indicators_by_symbol={"000001.SZ": frame},
        risk_group_by_symbol={"000001.SZ": "801780.SI"},
        entry_attribution_context=context,
    )

    filtered_intent = next(intent for intent in result.strategy_result.intents if intent.reason_code == "ENTRY_ATTRIBUTION_FILTERED")

    assert filtered_intent.intent_type == TradeIntentType.AVOID
    assert filtered_intent.blocked_by == "ENTRY_ATTRIBUTION_FILTER"
    assert filtered_intent.signal_values["entry_attribution_filter"]["failed_checks"] == ["symbol.ma.price_above_ma25"]
    assert filtered_intent.signal_values["attribution"]["checks"] == {"symbol.ma.price_above_ma25": False}
    assert "sizing" not in filtered_intent.signal_values
    assert result.strategy_result.closed_trades == ()


@dataclass(frozen=True)
class _LastDayEntry:
    entry_date: date
    method_name: str = "last_day_entry"
    required_indicators = frozenset({IndicatorRequirement("ma25", "D")})

    def evaluate(self, *, symbol, trade_date, row=None, previous_row=None) -> TradeIntent:
        intent_type = TradeIntentType.ENTER if trade_date == self.entry_date else TradeIntentType.HOLD
        return TradeIntent(
            intent_type=intent_type,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="LAST_DAY_ENTRY" if intent_type == TradeIntentType.ENTER else "WAITING",
        )


@dataclass(frozen=True)
class _DateEntry:
    entry_date: date
    method_name: str = "date_entry"
    required_indicators = frozenset({IndicatorRequirement("ma25", "D")})

    def evaluate(self, *, symbol, trade_date, row=None, previous_row=None) -> TradeIntent:
        intent_type = TradeIntentType.ENTER if trade_date == self.entry_date else TradeIntentType.HOLD
        return TradeIntent(
            intent_type=intent_type,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="DATE_ENTRY" if intent_type == TradeIntentType.ENTER else "WAITING",
        )


@dataclass(frozen=True)
class _DateProfitExit:
    exit_date: date
    method_name: str = "date_profit_exit"
    required_indicators = frozenset({IndicatorRequirement("ma25", "D")})

    def evaluate(self, *, symbol, trade_date, row=None, previous_row=None) -> TradeIntent:
        intent_type = TradeIntentType.EXIT_PROFIT if trade_date == self.exit_date else TradeIntentType.HOLD
        return TradeIntent(
            intent_type=intent_type,
            symbol=symbol,
            trade_date=trade_date,
            method_name=self.method_name,
            reason_code="DATE_PROFIT_EXIT" if intent_type == TradeIntentType.EXIT_PROFIT else "WAITING",
            signal_values={"checks": {"fixture_profit_exit": intent_type == TradeIntentType.EXIT_PROFIT}},
        )


def _daily_bars(symbol: str, *, count: int, start_close: float, step: float) -> tuple[DailyBar, ...]:
    start_date = date(2024, 1, 1)
    return tuple(
        DailyBar(
            symbol=symbol,
            trade_date=start_date + timedelta(days=index),
            open=max(0.1, start_close + index * step),
            high=max(0.2, start_close + index * step + 0.5),
            low=max(0.1, start_close + index * step - 0.5),
            close=max(0.1, start_close + index * step),
            volume=1000.0,
        )
        for index in range(count)
    )


def _index_bars(symbol: str, *, count: int, start_close: float, step: float) -> tuple[IndexBar, ...]:
    start_date = date(2024, 1, 1)
    return tuple(
        IndexBar(
            symbol=symbol,
            trade_date=start_date + timedelta(days=index),
            open=max(0.1, start_close + index * step),
            high=max(0.2, start_close + index * step + 0.5),
            low=max(0.1, start_close + index * step - 0.5),
            close=max(0.1, start_close + index * step),
            volume=1000.0,
        )
        for index in range(count)
    )


def _membership(symbol: str, level1_code: str) -> StockIndustryMembership:
    return StockIndustryMembership(
        symbol=symbol,
        stock_name="fixture",
        level1_code=level1_code,
        level1_name="银行",
        level2_code="801783.SI",
        level2_name="银行 II",
        level3_code="857831.SI",
        level3_name="银行 III",
        in_date=date(2020, 1, 1),
        out_date=None,
        is_new=False,
    )
