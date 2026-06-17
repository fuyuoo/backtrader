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
    EntryAttributionFilterCondition,
    EntryAttributionFilterRule,
    TradeIntent,
    TradeIntentType,
    apply_entry_attribution_filter,
    build_entry_attribution_context,
)
from attbacktrader.strategies.methods import FixedPercentStop, KdjOverheatedExit
from attbacktrader.strategies.templates import TrendTemplateV1


def test_entry_attribution_context_builds_symbol_market_and_industry_evidence() -> None:
    bars = _daily_bars("000001.SZ", count=90, start_close=10.0, step=0.3)
    market_bars = _index_bars("000300.SH", count=90, start_close=3000.0, step=8.0)
    csi500_bars = _index_bars("000905.SH", count=90, start_close=5000.0, step=12.0)
    industry_bars = _index_bars("801780.SI", count=90, start_close=50.0, step=-0.4)
    frame = indicator_frame_from_snapshots(
        build_indicator_snapshots_for_requirements(
            bars,
            indicator_requirements=(
                IndicatorRequirement("kdj", "D"),
                IndicatorRequirement("macd", "D"),
                IndicatorRequirement("ma20", "D"),
                IndicatorRequirement("ma25", "D"),
                IndicatorRequirement("ma60", "D"),
                IndicatorRequirement("kdj", "W"),
                IndicatorRequirement("macd", "W"),
            ),
        )
    )

    context = build_entry_attribution_context(
        bars_by_symbol={"000001.SZ": bars},
        indicators_by_symbol={"000001.SZ": frame},
        benchmark_bars_by_symbol={"000300.SH": market_bars, "000905.SH": csi500_bars},
        industry_index_bars_by_symbol={"801780.SI": industry_bars},
        memberships_by_symbol={"000001.SZ": (_membership("000001.SZ", "801780.SI"),)},
    )

    evidence = context.evidence_for("000001.SZ", bars[-1].trade_date)
    percentile_buckets = {"p0_p20", "p20_p40", "p40_p60", "p60_p80", "p80_p100"}
    strength_buckets = {"lte_0", "0_0p1pct", "0p1_0p3pct", "0p3_0p6pct", "gte_0p6pct"}
    interval_buckets = {"low_0_20", "low_mid_20_40", "mid_40_60", "high_mid_60_80", "high_80_100"}
    atr_multiple_buckets = {
        "below_ma60_gt_2atr",
        "below_ma60_1_2atr",
        "below_ma60_0_1atr",
        "above_ma60_0_1atr",
        "above_ma60_1_2atr",
        "above_ma60_gt_2atr",
    }
    ma_spread_buckets = {"ma25_lte_ma60", "0_2pct", "2_5pct", "5_10pct", "gte_10pct"}
    ma60_slope_buckets = {"down_gt_5pct", "down_0_5pct", "flat_0_2pct", "up_2_5pct", "up_gt_5pct"}
    shadow_buckets = {
        "short_shadows",
        "long_upper_shadow",
        "long_lower_shadow",
        "both_long_shadows",
        "balanced_shadows",
    }
    fixed_atr_multiple_buckets = {"lt_1atr", "1_2atr", "2_3atr", "gte_3atr"}

    assert evidence is not None
    assert evidence.values["symbol.kdj.k"] > 0
    assert evidence.values["symbol.kdj.d"] > 0
    assert evidence.values["symbol.kdj.j"] > 0
    assert evidence.values["symbol.kdj.threshold"] == 13.0
    assert evidence.checks["symbol.kdj.j_below_threshold"] is False
    assert evidence.values["symbol.kdj.week.k"] > 0
    assert evidence.values["symbol.kdj.week.d"] > 0
    assert evidence.values["symbol.kdj.week.j"] > 0
    assert evidence.values["symbol.kdj.week.indicator_date"] < bars[-1].trade_date.isoformat()
    assert evidence.categories["symbol.kdj.week.j_bucket"] in {"<13", "13-30", "30-50", "50-80", ">=80"}
    assert evidence.categories["symbol.kdj.week.state"] in {"oversold", "recovering", "strong", "overheated"}
    assert evidence.categories["entry.weekly.symbol_kdj_j_bucket"] in {"<13", "13-30", "30-50", "50-80", ">=80"}
    assert evidence.categories["entry.weekly.symbol_kdj_state"] in {"oversold", "recovering", "strong", "overheated"}
    assert "symbol.macd.dif" in evidence.values
    assert "symbol.macd.dea" in evidence.values
    assert evidence.values["symbol.macd.macd_bar"] == (evidence.values["symbol.macd.dif"] - evidence.values["symbol.macd.dea"]) * 2
    assert evidence.values["symbol.macd.dea_waterline_age_trading_days"] >= 0
    assert evidence.categories["symbol.macd.energy_zone"] in {
        "green_bar_or_zero",
        "red_bar_wrapping_lines",
        "red_bar_one_line_escape",
        "red_bar_two_line_escape",
        "red_bar_uncategorized",
    }
    assert evidence.values["symbol.macd.week.indicator_date"] < bars[-1].trade_date.isoformat()
    assert evidence.values["symbol.macd.week.macd_bar"] == (
        evidence.values["symbol.macd.week.dif"] - evidence.values["symbol.macd.week.dea"]
    ) * 2
    assert evidence.categories["symbol.macd.week.energy_zone"] in {
        "green_bar_or_zero",
        "red_bar_wrapping_lines",
        "red_bar_one_line_escape",
        "red_bar_two_line_escape",
        "red_bar_uncategorized",
    }
    assert evidence.values["symbol.ma.ma20"] > 0
    assert evidence.values["symbol.ma.ma25"] > 0
    assert evidence.values["symbol.ma.ma60"] > 0
    assert evidence.checks["symbol.ma.price_above_ma25"] is True
    assert evidence.checks["symbol.ma.price_above_ma60"] is True
    assert evidence.checks["symbol.ma.ma20_above_ma60"] is True
    assert evidence.checks["symbol.ma.bullish_trend"] is True
    assert evidence.categories["symbol.ma.trend_state"] == "bullish"
    assert evidence.categories["entry.volatility.return_vol_20d_bucket"] in percentile_buckets
    assert evidence.categories["entry.volatility.return_vol_60d_bucket"] in percentile_buckets
    assert evidence.categories["entry.volatility.atr_20d_bucket"] in percentile_buckets
    assert evidence.categories["entry.volatility.max_amplitude_20d_bucket"] in percentile_buckets
    assert evidence.categories["entry.momentum.return_20d_bucket"] in percentile_buckets
    assert evidence.categories["entry.momentum.return_60d_bucket"] in percentile_buckets
    assert evidence.categories["entry.momentum.new_high_20d_bucket"] in {"new_high", "not_new_high"}
    assert evidence.categories["entry.momentum.new_high_60d_bucket"] in {"new_high", "not_new_high"}
    assert evidence.categories["entry.price_position.near_high_20d_bucket"] in {
        "at_high",
        "near_high",
        "moderate_pullback",
        "deep_pullback",
        "far_from_high",
    }
    assert evidence.categories["entry.price_position.near_high_60d_bucket"] in {
        "at_high",
        "near_high",
        "moderate_pullback",
        "deep_pullback",
        "far_from_high",
    }
    assert evidence.categories["entry.price_position.interval_20d_bucket"] in interval_buckets
    assert evidence.categories["entry.price_position.interval_60d_bucket"] in interval_buckets
    assert evidence.categories["entry.price_position.signal_close_ma60_atr_multiple_bucket"] in atr_multiple_buckets
    assert evidence.categories["entry.signal_strength.dea_value_bucket"] in strength_buckets
    assert evidence.categories["entry.signal_strength.macd_bar_bucket"] in strength_buckets
    assert evidence.categories["entry.signal_strength.dif_dea_distance_bucket"] in strength_buckets
    assert evidence.categories["entry.signal_strength.ma25_above_ma60_spread_bucket"] in ma_spread_buckets
    assert evidence.categories["entry.signal_strength.ma60_slope_20d_bucket"] in ma60_slope_buckets
    assert evidence.categories["entry.signal_strength.signal_candle_body_bucket"] == "lt_1pct"
    assert evidence.categories["entry.signal_strength.signal_upper_lower_shadow_bucket"] in shadow_buckets
    assert evidence.categories["entry.signal_strength.dea_waterline_age_trading_days_bucket"] in {
        "day_0",
        "day_1_3",
        "day_4_7",
        "day_8_14",
        "gt_14d",
    }
    assert evidence.categories["entry.stop_fit.fixed_atr_multiple_bucket"] in fixed_atr_multiple_buckets
    assert evidence.checks["market.hs300.bullish_trend"] is True
    assert evidence.values["market.hs300.ma20"] > evidence.values["market.hs300.ma60"]
    assert evidence.values["market.hs300.kdj.k"] > 0
    assert evidence.values["market.hs300.kdj.d"] > 0
    assert evidence.values["market.hs300.kdj.j"] > 0
    assert evidence.values["market.hs300.kdj.threshold"] == 13.0
    assert evidence.checks["market.hs300.kdj.j_below_threshold"] is False
    assert evidence.categories["market.hs300.trend_state"] == "bullish"
    assert evidence.categories["market.hs300.return_vol_20d_bucket"] in {"lt_1pct", "1_2pct", "2_3pct", "3_5pct", "gte_5pct"}
    assert evidence.categories["market.hs300.return_vol_60d_bucket"] in {"lt_1pct", "1_2pct", "2_3pct", "3_5pct", "gte_5pct"}
    assert evidence.categories["market.csi500.return_vol_20d_bucket"] in {"lt_1pct", "1_2pct", "2_3pct", "3_5pct", "gte_5pct"}
    assert evidence.categories["market.csi500.return_vol_60d_bucket"] in {"lt_1pct", "1_2pct", "2_3pct", "3_5pct", "gte_5pct"}
    assert evidence.categories["market.hs300.weekly.kdj_state"] in {"oversold", "recovering", "strong", "overheated"}
    assert evidence.categories["market.csi500.weekly.kdj_state"] in {"oversold", "recovering", "strong", "overheated"}
    assert evidence.categories["industry.sw_l1.code"] == "801780.SI"
    assert evidence.checks["industry.kdj.j_below_threshold"] is True
    assert evidence.categories["industry.kdj.j_bucket"] == "<13"
    assert evidence.categories["industry.kdj.state"] == "oversold"
    assert evidence.values["industry.kdj.week.k"] > 0
    assert evidence.values["industry.kdj.week.d"] > 0
    assert isinstance(evidence.values["industry.kdj.week.j"], float)
    assert evidence.values["industry.kdj.week.indicator_date"] < bars[-1].trade_date.isoformat()
    assert evidence.categories["industry.kdj.week.j_bucket"] in {"<13", "13-30", "30-50", "50-80", ">=80"}
    assert evidence.categories["industry.kdj.week.state"] in {"oversold", "recovering", "strong", "overheated"}
    assert "industry.macd.dif" in evidence.values
    assert "industry.macd.dea" in evidence.values
    assert evidence.values["industry.macd.macd_bar"] == (
        evidence.values["industry.macd.dif"] - evidence.values["industry.macd.dea"]
    ) * 2
    assert evidence.categories["industry.macd.energy_zone"] in {
        "green_bar_or_zero",
        "red_bar_wrapping_lines",
        "red_bar_one_line_escape",
        "red_bar_two_line_escape",
        "red_bar_uncategorized",
    }
    assert evidence.values["industry.macd.week.indicator_date"] < bars[-1].trade_date.isoformat()
    assert evidence.values["industry.macd.week.macd_bar"] == (
        evidence.values["industry.macd.week.dif"] - evidence.values["industry.macd.week.dea"]
    ) * 2
    assert evidence.categories["industry.macd.week.energy_zone"] in {
        "green_bar_or_zero",
        "red_bar_wrapping_lines",
        "red_bar_one_line_escape",
        "red_bar_two_line_escape",
        "red_bar_uncategorized",
    }
    assert evidence.values["industry.ma.ma20"] < evidence.values["industry.ma.ma60"]
    assert evidence.checks["industry.ma.price_above_ma20"] is False
    assert evidence.checks["industry.ma.price_above_ma60"] is False
    assert evidence.checks["industry.ma.ma20_above_ma60"] is False
    assert evidence.checks["industry.ma.bullish_trend"] is False
    assert evidence.categories["industry.ma.trend_state"] == "not_bullish"
    assert evidence.categories["industry.volatility.return_vol_20d_bucket"] in {"lt_1pct", "1_2pct", "2_3pct", "3_5pct", "gte_5pct"}
    assert evidence.categories["industry.volatility.return_vol_60d_bucket"] in {"lt_1pct", "1_2pct", "2_3pct", "3_5pct", "gte_5pct"}
    assert evidence.categories["industry.volatility.atr_20d_bucket"] in {"lt_1pct", "1_2pct", "2_3pct", "3_5pct", "gte_5pct"}
    assert evidence.categories["industry.price_position.near_high_60d_bucket"] in {
        "at_high",
        "near_high",
        "moderate_pullback",
        "deep_pullback",
        "far_from_high",
    }
    assert "industry.relative.hs300.return_20d" in evidence.values
    assert "industry.relative.hs300.return_60d" in evidence.values
    assert evidence.values["industry.relative.hs300.excess_return_20d"] < 0
    assert evidence.values["industry.relative.hs300.excess_return_60d"] < 0
    assert evidence.checks["industry.relative.hs300.outperform_20d"] is False
    assert evidence.checks["industry.relative.hs300.outperform_60d"] is False
    assert evidence.categories["industry.relative.hs300.strength_state"] == "weak_underperform"


def test_entry_attribution_context_uses_same_day_cross_section_percentile_buckets() -> None:
    bars_by_symbol = {
        "000001.SZ": _daily_bars("000001.SZ", count=130, start_close=10.0, step=0.1),
        "000002.SZ": _daily_bars("000002.SZ", count=130, start_close=10.0, step=0.2),
        "000003.SZ": _daily_bars("000003.SZ", count=130, start_close=10.0, step=0.3),
    }

    context = build_entry_attribution_context(
        bars_by_symbol=bars_by_symbol,
        indicators_by_symbol={},
        memberships_by_symbol={
            symbol: (_membership(symbol, "801780.SI"),)
            for symbol in bars_by_symbol
        },
    )

    trade_date = bars_by_symbol["000001.SZ"][-1].trade_date
    momentum_buckets = {
        symbol: context.evidence_for(symbol, trade_date).categories["entry.momentum.return_20d_bucket"]
        for symbol in bars_by_symbol
    }
    long_momentum_buckets = {
        symbol: context.evidence_for(symbol, trade_date).categories["entry.momentum.return_120d_bucket"]
        for symbol in bars_by_symbol
    }
    industry_relative_atr_buckets = {
        symbol: context.evidence_for(symbol, trade_date).categories["entry.volatility.symbol_atr_to_industry_median_bucket"]
        for symbol in bars_by_symbol
    }

    assert set(momentum_buckets.values()) == {"p20_p40", "p60_p80", "p80_p100"}
    assert set(long_momentum_buckets.values()) == {"p20_p40", "p60_p80", "p80_p100"}
    assert set(industry_relative_atr_buckets.values()) <= {"lt_0p8x", "0p8_1p2x", "1p2_1p6x", "1p6_2x", "gte_2x"}
    assert len(set(industry_relative_atr_buckets.values())) >= 2


def test_entry_attribution_context_uses_completed_weekly_symbol_context() -> None:
    bars = _daily_bars("000001.SZ", count=160, start_close=10.0, step=0.2)

    context = build_entry_attribution_context(
        bars_by_symbol={"000001.SZ": bars},
        indicators_by_symbol={},
    )

    evidence = context.evidence_for("000001.SZ", bars[-1].trade_date)

    assert evidence is not None
    assert evidence.categories["entry.momentum.new_high_120d_bucket"] in {"new_high", "not_new_high"}
    assert evidence.categories["entry.weekly.symbol_close_vs_week_ma20_bucket"] in {
        "below_gt_10pct",
        "below_0_10pct",
        "above_0_5pct",
        "above_5_15pct",
        "above_gt_15pct",
    }
    assert evidence.categories["entry.weekly.symbol_ma_trend_bucket"] in {"uptrend", "downtrend", "mixed"}


def test_entry_attribution_context_builds_objective_market_index_components() -> None:
    bars = _daily_bars("000001.SZ", count=280, start_close=10.0, step=0.1)
    hs300_bars = _index_bars("000300.SH", count=280, start_close=3000.0, step=-2.0)
    csi500_bars = _index_bars("000905.SH", count=280, start_close=5000.0, step=-3.0)

    context = build_entry_attribution_context(
        bars_by_symbol={"000001.SZ": bars},
        indicators_by_symbol={},
        benchmark_bars_by_symbol={"000300.SH": hs300_bars, "000905.SH": csi500_bars},
    )

    evidence = context.evidence_for("000001.SZ", bars[-1].trade_date)

    assert evidence.categories["market.objective.entry_index_drawdown_250d_bucket"] in {
        "drawdown_0_5pct",
        "drawdown_5_15pct",
        "drawdown_15_20pct",
        "drawdown_gt_20pct",
    }
    assert evidence.categories["market.objective.entry_index_ma60_slope_20d_bucket"] in {
        "down_gt_5pct",
        "down_0_5pct",
        "flat_0_2pct",
        "up_2_5pct",
        "up_gt_5pct",
    }


def test_entry_attribution_uses_earliest_known_industry_membership_for_prior_dates() -> None:
    bars = _daily_bars("000001.SZ", count=70, start_close=10.0, step=0.3)
    industry_bars = _index_bars("801780.SI", count=70, start_close=50.0, step=-0.4)
    future_membership = StockIndustryMembership(
        symbol="000001.SZ",
        stock_name="fixture",
        level1_code="801780.SI",
        level1_name="银行",
        level2_code="801783.SI",
        level2_name="银行 II",
        level3_code="857831.SI",
        level3_name="银行 III",
        in_date=bars[-1].trade_date + timedelta(days=30),
        out_date=None,
        is_new=True,
    )

    context = build_entry_attribution_context(
        bars_by_symbol={"000001.SZ": bars},
        indicators_by_symbol={},
        industry_index_bars_by_symbol={"801780.SI": industry_bars},
        memberships_by_symbol={"000001.SZ": (future_membership,)},
    )

    evidence = context.evidence_for("000001.SZ", bars[-1].trade_date)

    assert evidence is not None
    assert evidence.categories["industry.sw_l1.code"] == "801780.SI"
    assert "industry.kdj.j" in evidence.values


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


def test_entry_attribution_filter_keep_condition_allows_matching_category() -> None:
    intent = TradeIntent(
        intent_type=TradeIntentType.ENTER,
        symbol="000001.SZ",
        trade_date=date(2024, 1, 2),
        method_name="date_entry",
        reason_code="DATE_ENTRY",
        signal_values={
            "attribution": {
                "categories": {
                    "entry.volatility.atr_20d_bucket": "2_3pct",
                }
            }
        },
    )
    rule = EntryAttributionFilterRule(
        enabled=True,
        conditions=(
            EntryAttributionFilterCondition(
                field="entry.volatility.atr_20d_bucket",
                value="2_3pct",
                action="keep",
            ),
        ),
        missing_policy="block",
    )

    filtered = apply_entry_attribution_filter(intent, rule)

    assert filtered.intent_type == TradeIntentType.ENTER
    filter_audit = filtered.signal_values["entry_attribution_filter"]
    assert filter_audit["passed"] is True
    assert filter_audit["conditions"] == [
        {
            "field": "entry.volatility.atr_20d_bucket",
            "operator": "eq",
            "value": "2_3pct",
            "action": "keep",
            "actual": "2_3pct",
            "matched": True,
            "passed": True,
            "source": "categories",
        }
    ]


def test_entry_attribution_filter_keep_condition_blocks_non_matching_category() -> None:
    intent = TradeIntent(
        intent_type=TradeIntentType.ENTER,
        symbol="000001.SZ",
        trade_date=date(2024, 1, 2),
        method_name="date_entry",
        reason_code="DATE_ENTRY",
        signal_values={
            "attribution": {
                "categories": {
                    "entry.volatility.atr_20d_bucket": "0_1pct",
                }
            }
        },
    )
    rule = EntryAttributionFilterRule(
        enabled=True,
        conditions=(
            EntryAttributionFilterCondition(
                field="entry.volatility.atr_20d_bucket",
                value="2_3pct",
                action="keep",
            ),
        ),
        missing_policy="block",
    )

    filtered = apply_entry_attribution_filter(intent, rule)

    assert filtered.intent_type == TradeIntentType.AVOID
    assert filtered.reason_code == "ENTRY_ATTRIBUTION_FILTERED"
    assert filtered.blocked_by == "ENTRY_ATTRIBUTION_FILTER"
    filter_audit = filtered.signal_values["entry_attribution_filter"]
    assert filter_audit["passed"] is False
    assert filter_audit["failed_conditions"] == ["entry.volatility.atr_20d_bucket"]
    assert filter_audit["conditions"][0]["actual"] == "0_1pct"
    assert filter_audit["conditions"][0]["matched"] is False
    assert filter_audit["conditions"][0]["passed"] is False


def test_entry_attribution_filter_exclude_condition_blocks_matching_category() -> None:
    intent = TradeIntent(
        intent_type=TradeIntentType.ENTER,
        symbol="000001.SZ",
        trade_date=date(2024, 1, 2),
        method_name="date_entry",
        reason_code="DATE_ENTRY",
        signal_values={
            "attribution": {
                "categories": {
                    "entry.volatility.atr_20d_bucket": "0_1pct",
                }
            }
        },
    )
    rule = EntryAttributionFilterRule(
        enabled=True,
        conditions=(
            EntryAttributionFilterCondition(
                field="entry.volatility.atr_20d_bucket",
                value="0_1pct",
                action="exclude",
            ),
        ),
        missing_policy="block",
    )

    filtered = apply_entry_attribution_filter(intent, rule)

    assert filtered.intent_type == TradeIntentType.AVOID
    filter_audit = filtered.signal_values["entry_attribution_filter"]
    assert filter_audit["failed_conditions"] == ["entry.volatility.atr_20d_bucket"]
    assert filter_audit["conditions"][0]["matched"] is True
    assert filter_audit["conditions"][0]["passed"] is False


def test_entry_attribution_filter_condition_missing_policy_block_rejects_missing_field() -> None:
    intent = TradeIntent(
        intent_type=TradeIntentType.ENTER,
        symbol="000001.SZ",
        trade_date=date(2024, 1, 2),
        method_name="date_entry",
        reason_code="DATE_ENTRY",
        signal_values={"attribution": {"categories": {}}},
    )
    rule = EntryAttributionFilterRule(
        enabled=True,
        conditions=(
            EntryAttributionFilterCondition(
                field="entry.volatility.atr_20d_bucket",
                value="2_3pct",
                action="keep",
            ),
        ),
        missing_policy="block",
    )

    filtered = apply_entry_attribution_filter(intent, rule)

    assert filtered.intent_type == TradeIntentType.AVOID
    filter_audit = filtered.signal_values["entry_attribution_filter"]
    assert filter_audit["missing_conditions"] == ["entry.volatility.atr_20d_bucket"]
    assert filter_audit["conditions"][0]["actual"] is None
    assert filter_audit["conditions"][0]["source"] is None
    assert filter_audit["conditions"][0]["passed"] is False


def test_entry_attribution_filter_condition_missing_policy_pass_allows_missing_field() -> None:
    intent = TradeIntent(
        intent_type=TradeIntentType.ENTER,
        symbol="000001.SZ",
        trade_date=date(2024, 1, 2),
        method_name="date_entry",
        reason_code="DATE_ENTRY",
        signal_values={"attribution": {"categories": {}}},
    )
    rule = EntryAttributionFilterRule(
        enabled=True,
        conditions=(
            EntryAttributionFilterCondition(
                field="entry.volatility.atr_20d_bucket",
                value="2_3pct",
                action="keep",
            ),
        ),
        missing_policy="pass",
    )

    filtered = apply_entry_attribution_filter(intent, rule)

    assert filtered.intent_type == TradeIntentType.ENTER
    filter_audit = filtered.signal_values["entry_attribution_filter"]
    assert filter_audit["passed"] is True
    assert filter_audit["missing_conditions"] == ["entry.volatility.atr_20d_bucket"]
    assert filter_audit["conditions"][0]["passed"] is True


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
