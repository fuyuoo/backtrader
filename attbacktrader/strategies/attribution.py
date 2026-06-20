"""Entry attribution evidence helpers."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from types import MappingProxyType
from typing import Any, Mapping

from attbacktrader.data import DailyBar, IndexBar, StockIndustryMembership, resample_daily_bars
from attbacktrader.data.snapshots.attribution_reference import FIELD_DEFINITIONS as ATTRIBUTION_REFERENCE_FIELD_DEFINITIONS
from attbacktrader.features import (
    IndicatorFrame,
    IndicatorRequirement,
    calculate_kdj,
    calculate_macd,
    calculate_sma,
    completed_indicator_before_event,
)
from attbacktrader.strategies.intents import TradeIntent, TradeIntentType


ENTRY_ATTRIBUTION_INDICATOR_REQUIREMENTS = (
    IndicatorRequirement("kdj", "D"),
    IndicatorRequirement("ma20", "D"),
    IndicatorRequirement("ma25", "D"),
    IndicatorRequirement("ma60", "D"),
)

ATTRIBUTION_FACTOR_SELECTION_SCHEMA = "attbacktrader.attribution_factor_selection.v1"
VALID_ATTRIBUTION_FACTOR_TYPES = {"check", "value", "category", "text"}
VALID_ATTRIBUTION_SCOPES = {"symbol", "industry", "market", "sizing", "execution", "portfolio"}
VALID_ATTRIBUTION_TIMINGS = {"entry", "add_on", "exit", "holding", "post_exit"}


@dataclass(frozen=True)
class EntryAttributionFactorDeclaration:
    key: str
    factor_type: str
    label_zh: str
    label_en: str
    scope: str
    dependencies: tuple[str, ...] = ()
    missing_behavior: str = "missing"
    owner: str = "framework"
    timings: tuple[str, ...] = ("entry",)
    compatible_strategies: tuple[str, ...] = ()
    compatible_methods: tuple[str, ...] = ()
    source: str = "artifact_bound_lookup"
    value_type: str | None = None

    def __post_init__(self) -> None:
        factor_type = str(self.factor_type)
        if factor_type not in VALID_ATTRIBUTION_FACTOR_TYPES:
            raise ValueError("factor_type must be check, value, category, or text")
        if self.scope not in VALID_ATTRIBUTION_SCOPES:
            raise ValueError("scope must be symbol, industry, market, sizing, execution, or portfolio")
        if self.missing_behavior != "missing":
            raise ValueError("entry attribution missing behavior must be missing")
        timings = tuple(str(timing) for timing in self.timings)
        if not timings:
            raise ValueError("attribution factor timings cannot be empty")
        invalid_timings = sorted(set(timings) - VALID_ATTRIBUTION_TIMINGS)
        if invalid_timings:
            raise ValueError(f"unsupported attribution factor timings: {invalid_timings}")
        object.__setattr__(self, "factor_type", factor_type)
        object.__setattr__(self, "timings", timings)
        object.__setattr__(self, "dependencies", tuple(str(value) for value in self.dependencies))
        object.__setattr__(self, "compatible_strategies", tuple(str(value) for value in self.compatible_strategies))
        object.__setattr__(self, "compatible_methods", tuple(str(value) for value in self.compatible_methods))
        if self.value_type is None:
            object.__setattr__(self, "value_type", factor_type)


AttributionFactorDeclaration = EntryAttributionFactorDeclaration


@dataclass(frozen=True)
class EntryAttributionEvidence:
    checks: Mapping[str, bool] = field(default_factory=dict)
    values: Mapping[str, Any] = field(default_factory=dict)
    categories: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "checks",
            MappingProxyType(
                {
                    str(key): value
                    for key, value in self.checks.items()
                    if isinstance(value, bool)
                }
            ),
        )
        object.__setattr__(
            self,
            "values",
            MappingProxyType(
                {
                    str(key): value
                    for key, value in self.values.items()
                    if _is_scalar_json_value(value) and not isinstance(value, bool)
                }
            ),
        )
        object.__setattr__(
            self,
            "categories",
            MappingProxyType(
                {
                    str(key): str(value)
                    for key, value in self.categories.items()
                    if value is not None
                }
            ),
        )

    def is_empty(self) -> bool:
        return not self.checks and not self.values and not self.categories

    def to_signal_values(self) -> dict[str, dict[str, Any]]:
        return entry_attribution_payload(
            checks=self.checks,
            values=self.values,
            categories=self.categories,
        )


@dataclass(frozen=True)
class EntryAttributionFilterCondition:
    field: str
    value: Any
    action: str
    operator: str = "eq"

    def __post_init__(self) -> None:
        field_name = str(self.field)
        if not field_name:
            raise ValueError("entry attribution filter condition field cannot be empty")
        operator = str(self.operator)
        if operator not in {"eq", "gt", "gte", "lt", "lte"}:
            raise ValueError("entry attribution filter condition operator must be one of eq, gt, gte, lt, lte")
        action = str(self.action)
        if action not in {"keep", "exclude"}:
            raise ValueError("entry attribution filter condition action must be keep or exclude")
        if not _is_scalar_json_value(self.value):
            raise ValueError("entry attribution filter condition value must be a scalar JSON value")
        object.__setattr__(self, "field", field_name)
        object.__setattr__(self, "operator", operator)
        object.__setattr__(self, "action", action)


@dataclass(frozen=True)
class EntryAttributionFilterRule:
    enabled: bool = False
    required_checks: tuple[str, ...] = ()
    conditions: tuple[EntryAttributionFilterCondition, ...] = ()
    missing_policy: str = "block"
    reason_code: str = "ENTRY_ATTRIBUTION_FILTERED"
    blocked_by: str = "ENTRY_ATTRIBUTION_FILTER"

    def __post_init__(self) -> None:
        if self.missing_policy not in {"block", "pass"}:
            raise ValueError("entry attribution filter missing_policy must be block or pass")
        required_checks = tuple(str(key) for key in self.required_checks)
        if len(set(required_checks)) != len(required_checks):
            raise ValueError("entry attribution filter required_checks cannot contain duplicates")
        object.__setattr__(self, "required_checks", required_checks)
        conditions = tuple(self.conditions)
        condition_keys = tuple((condition.field, condition.operator, condition.value, condition.action) for condition in conditions)
        if len(set(condition_keys)) != len(condition_keys):
            raise ValueError("entry attribution filter conditions cannot contain duplicates")
        object.__setattr__(self, "conditions", conditions)

    def is_active(self) -> bool:
        return self.enabled and (bool(self.required_checks) or bool(self.conditions))


@dataclass(frozen=True)
class EntryAttributionContext:
    evidence_by_key: Mapping[tuple[str, date], EntryAttributionEvidence]
    enabled_factor_keys: frozenset[str] | None = None
    entry_filter: EntryAttributionFilterRule = field(default_factory=EntryAttributionFilterRule)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_by_key", MappingProxyType(dict(self.evidence_by_key)))
        if self.enabled_factor_keys is None:
            enabled_factor_keys = frozenset(entry_attribution_declaration_by_key())
        else:
            enabled_factor_keys = frozenset(str(key) for key in self.enabled_factor_keys)
        object.__setattr__(self, "enabled_factor_keys", enabled_factor_keys)

    def evidence_for(self, symbol: str, trade_date: date) -> EntryAttributionEvidence | None:
        return self.evidence_by_key.get((symbol, trade_date))

    def factor_enabled(self, key: str) -> bool:
        return key in self.enabled_factor_keys


STANDARD_ENTRY_ATTRIBUTION_FACTORS = (
    EntryAttributionFactorDeclaration(
        key="symbol.close",
        factor_type="value",
        label_zh="个股收盘价",
        label_en="Symbol close",
        scope="symbol",
        dependencies=("close",),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.kdj.k",
        factor_type="value",
        label_zh="个股 KDJ K",
        label_en="Symbol KDJ K",
        scope="symbol",
        dependencies=("kdj:D",),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.kdj.d",
        factor_type="value",
        label_zh="个股 KDJ D",
        label_en="Symbol KDJ D",
        scope="symbol",
        dependencies=("kdj:D",),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.kdj.j",
        factor_type="value",
        label_zh="个股 KDJ J",
        label_en="Symbol KDJ J",
        scope="symbol",
        dependencies=("kdj:D",),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.kdj.threshold",
        factor_type="value",
        label_zh="个股 KDJ 阈值",
        label_en="Symbol KDJ threshold",
        scope="symbol",
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.kdj.j_below_threshold",
        factor_type="check",
        label_zh="个股 KDJ J 低于阈值",
        label_en="Symbol KDJ J below threshold",
        scope="symbol",
        dependencies=("kdj:D",),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.kdj.week.indicator_date",
        factor_type="value",
        label_zh="个股周线 KDJ 指标日期",
        label_en="Symbol weekly KDJ indicator date",
        scope="symbol",
        dependencies=("kdj:W",),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.kdj.week.k",
        factor_type="value",
        label_zh="个股周线 KDJ K",
        label_en="Symbol weekly KDJ K",
        scope="symbol",
        dependencies=("kdj:W",),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.kdj.week.d",
        factor_type="value",
        label_zh="个股周线 KDJ D",
        label_en="Symbol weekly KDJ D",
        scope="symbol",
        dependencies=("kdj:W",),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.kdj.week.j",
        factor_type="value",
        label_zh="个股周线 KDJ J",
        label_en="Symbol weekly KDJ J",
        scope="symbol",
        dependencies=("kdj:W",),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.kdj.week.j_bucket",
        factor_type="category",
        label_zh="个股周线 KDJ J 分桶",
        label_en="Symbol weekly KDJ J bucket",
        scope="symbol",
        dependencies=("kdj:W",),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.kdj.week.state",
        factor_type="category",
        label_zh="个股周线 KDJ 状态",
        label_en="Symbol weekly KDJ state",
        scope="symbol",
        dependencies=("kdj:W",),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.macd.dea",
        factor_type="value",
        label_zh="个股 MACD DEA",
        label_en="Symbol MACD DEA",
        scope="symbol",
        dependencies=("macd:D",),
        owner="baoma_v1",
        compatible_strategies=("baoma_v1",),
        compatible_methods=("baoma_entry", "baoma_add_on"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.macd.dif",
        factor_type="value",
        label_zh="个股 MACD DIF",
        label_en="Symbol MACD DIF",
        scope="symbol",
        dependencies=("macd:D",),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.macd.macd_bar",
        factor_type="value",
        label_zh="个股 MACD 归因柱",
        label_en="Symbol MACD attribution bar",
        scope="symbol",
        dependencies=("macd:D",),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.macd.energy_zone",
        factor_type="category",
        label_zh="个股日线 MACD 能量区间",
        label_en="Symbol daily MACD energy zone",
        scope="symbol",
        dependencies=("macd:D",),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.macd.week.indicator_date",
        factor_type="value",
        label_zh="个股周线 MACD 指标日期",
        label_en="Symbol weekly MACD indicator date",
        scope="symbol",
        dependencies=("macd:W",),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.macd.week.dif",
        factor_type="value",
        label_zh="个股周线 MACD DIF",
        label_en="Symbol weekly MACD DIF",
        scope="symbol",
        dependencies=("macd:W",),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.macd.week.dea",
        factor_type="value",
        label_zh="个股周线 MACD DEA",
        label_en="Symbol weekly MACD DEA",
        scope="symbol",
        dependencies=("macd:W",),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.macd.week.macd_bar",
        factor_type="value",
        label_zh="个股周线 MACD 归因柱",
        label_en="Symbol weekly MACD attribution bar",
        scope="symbol",
        dependencies=("macd:W",),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.macd.week.energy_zone",
        factor_type="category",
        label_zh="个股周线 MACD 能量区间",
        label_en="Symbol weekly MACD energy zone",
        scope="symbol",
        dependencies=("macd:W",),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.macd.dea_positive",
        factor_type="check",
        label_zh="个股 DEA 上水",
        label_en="Symbol DEA above zero",
        scope="symbol",
        dependencies=("macd:D",),
        owner="baoma_v1",
        compatible_strategies=("baoma_v1",),
        compatible_methods=("baoma_entry", "baoma_add_on"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.macd.dea_recent_waterline",
        factor_type="check",
        label_zh="个股 DEA 最近上水",
        label_en="Symbol DEA recent waterline",
        scope="symbol",
        dependencies=("macd:D",),
        owner="baoma_v1",
        compatible_strategies=("baoma_v1",),
        compatible_methods=("baoma_entry", "baoma_add_on"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.macd.dea_waterline_age_trading_days",
        factor_type="value",
        label_zh="个股 DEA 上水天数",
        label_en="Symbol DEA waterline age in trading days",
        scope="symbol",
        dependencies=("macd:D",),
        owner="baoma_v1",
        compatible_strategies=("baoma_v1",),
        compatible_methods=("baoma_entry", "baoma_add_on"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.macd.dea_waterline_max_age_days",
        factor_type="value",
        label_zh="个股 DEA 上水天数阈值",
        label_en="Symbol DEA waterline max age days",
        scope="symbol",
        owner="baoma_v1",
        compatible_strategies=("baoma_v1",),
        compatible_methods=("baoma_entry", "baoma_add_on"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.ma.ma20",
        factor_type="value",
        label_zh="个股 MA20",
        label_en="Symbol MA20",
        scope="symbol",
        dependencies=("ma20:D",),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.ma.ma25",
        factor_type="value",
        label_zh="个股 MA25",
        label_en="Symbol MA25",
        scope="symbol",
        dependencies=("ma25:D",),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.ma.ma60",
        factor_type="value",
        label_zh="个股 MA60",
        label_en="Symbol MA60",
        scope="symbol",
        dependencies=("ma60:D",),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.ma.price_above_ma25",
        factor_type="check",
        label_zh="价格在 MA25 上方",
        label_en="Price above MA25",
        scope="symbol",
        dependencies=("close", "ma25:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.ma.price_above_ma60",
        factor_type="check",
        label_zh="价格在 MA60 上方",
        label_en="Price above MA60",
        scope="symbol",
        dependencies=("close", "ma60:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.ma.ma20_above_ma60",
        factor_type="check",
        label_zh="个股 MA20 高于 MA60",
        label_en="Symbol MA20 above MA60",
        scope="symbol",
        dependencies=("ma20:D", "ma60:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.ma.bullish_trend",
        factor_type="check",
        label_zh="个股均线多头趋势",
        label_en="Symbol MA bullish trend",
        scope="symbol",
        dependencies=("close", "ma20:D", "ma60:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="symbol.ma.trend_state",
        factor_type="category",
        label_zh="个股均线趋势状态",
        label_en="Symbol MA trend state",
        scope="symbol",
        dependencies=("close", "ma20:D", "ma60:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.volatility.return_vol_20d_bucket",
        factor_type="category",
        label_zh="个股 20 日收益波动率分位桶",
        label_en="Symbol 20-day return volatility percentile bucket",
        scope="symbol",
        dependencies=("close",),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.volatility.return_vol_60d_bucket",
        factor_type="category",
        label_zh="个股 60 日收益波动率分位桶",
        label_en="Symbol 60-day return volatility percentile bucket",
        scope="symbol",
        dependencies=("close",),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.volatility.atr_20d_bucket",
        factor_type="category",
        label_zh="个股 20 日 ATR 百分比分位桶",
        label_en="Symbol 20-day ATR percentage percentile bucket",
        scope="symbol",
        dependencies=("high", "low", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.volatility.max_amplitude_20d_bucket",
        factor_type="category",
        label_zh="近20日最大振幅分位桶",
        label_en="Symbol 20-day max amplitude percentile bucket",
        scope="symbol",
        dependencies=("high", "low"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.volatility.industry_atr_percentile_bucket",
        factor_type="category",
        label_zh="个股ATR行业内分位桶",
        label_en="Symbol ATR percentile within industry bucket",
        scope="symbol",
        dependencies=("high", "low", "close", "industry_membership"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.volatility.symbol_atr_to_industry_median_bucket",
        factor_type="category",
        label_zh="个股ATR相对行业中位数桶",
        label_en="Symbol ATR versus industry median bucket",
        scope="symbol",
        dependencies=("high", "low", "close", "industry_membership"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.momentum.return_20d_bucket",
        factor_type="category",
        label_zh="个股 20 日收益率分位桶",
        label_en="Symbol 20-day return percentile bucket",
        scope="symbol",
        dependencies=("close",),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.momentum.return_60d_bucket",
        factor_type="category",
        label_zh="个股 60 日收益率分位桶",
        label_en="Symbol 60-day return percentile bucket",
        scope="symbol",
        dependencies=("close",),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.momentum.return_120d_bucket",
        factor_type="category",
        label_zh="个股 120 日收益率分位桶",
        label_en="Symbol 120-day return percentile bucket",
        scope="symbol",
        dependencies=("close",),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.momentum.new_high_20d_bucket",
        factor_type="category",
        label_zh="个股20日新高状态",
        label_en="Symbol 20-day new high status",
        scope="symbol",
        dependencies=("high", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.momentum.new_high_60d_bucket",
        factor_type="category",
        label_zh="个股60日新高状态",
        label_en="Symbol 60-day new high status",
        scope="symbol",
        dependencies=("high", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.momentum.new_high_120d_bucket",
        factor_type="category",
        label_zh="个股120日新高状态",
        label_en="Symbol 120-day new high status",
        scope="symbol",
        dependencies=("high", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.price_position.near_high_20d_bucket",
        factor_type="category",
        label_zh="个股距 20 日高点位置桶",
        label_en="Symbol distance from 20-day high bucket",
        scope="symbol",
        dependencies=("high", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.price_position.near_high_60d_bucket",
        factor_type="category",
        label_zh="个股距 60 日高点位置桶",
        label_en="Symbol distance from 60-day high bucket",
        scope="symbol",
        dependencies=("high", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.price_position.interval_20d_bucket",
        factor_type="category",
        label_zh="个股 20 日区间位置桶",
        label_en="Symbol 20-day interval position bucket",
        scope="symbol",
        dependencies=("high", "low", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.price_position.interval_60d_bucket",
        factor_type="category",
        label_zh="个股 60 日区间位置桶",
        label_en="Symbol 60-day interval position bucket",
        scope="symbol",
        dependencies=("high", "low", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.price_position.signal_close_ma60_atr_multiple_bucket",
        factor_type="category",
        label_zh="信号日收盘价距 MA60 的 ATR 倍数桶",
        label_en="Signal close distance from MA60 in ATR bucket",
        scope="symbol",
        dependencies=("close", "ma60:D", "atr20"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.price_position.signal_close_ma60_pct",
        factor_type="value",
        label_zh="信号日收盘价距 MA60 百分比",
        label_en="Signal close distance from MA60 percentage",
        scope="symbol",
        dependencies=("close", "ma60:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.signal_strength.dea_value_bucket",
        factor_type="category",
        label_zh="信号日 DEA 强度桶",
        label_en="Signal DEA strength bucket",
        scope="symbol",
        dependencies=("macd:D", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.signal_strength.dea_waterline_age_trading_days_bucket",
        factor_type="category",
        label_zh="信号日 DEA 上水天数桶",
        label_en="Signal DEA waterline age in trading days bucket",
        scope="symbol",
        dependencies=("macd:D",),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.signal_strength.macd_bar_bucket",
        factor_type="category",
        label_zh="信号日 MACD 柱强度桶",
        label_en="Signal MACD bar strength bucket",
        scope="symbol",
        dependencies=("macd:D", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.signal_strength.dif_dea_distance_bucket",
        factor_type="category",
        label_zh="信号日 DIF-DEA 距离强度桶",
        label_en="Signal DIF-DEA distance strength bucket",
        scope="symbol",
        dependencies=("macd:D", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.signal_strength.ma25_above_ma60_spread_bucket",
        factor_type="category",
        label_zh="信号日 MA25 高于 MA60 幅度桶",
        label_en="Signal MA25 above MA60 spread bucket",
        scope="symbol",
        dependencies=("ma25:D", "ma60:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.signal_strength.ma60_slope_20d_bucket",
        factor_type="category",
        label_zh="信号日 MA60 20 日斜率桶",
        label_en="Signal MA60 20-day slope bucket",
        scope="symbol",
        dependencies=("ma60:D",),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.signal_strength.signal_candle_body_bucket",
        factor_type="category",
        label_zh="信号 K 线实体占比桶",
        label_en="Signal candle body percentage bucket",
        scope="symbol",
        dependencies=("open", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.signal_strength.signal_candle_body_pct",
        factor_type="value",
        label_zh="信号 K 线实体占比",
        label_en="Signal candle body percentage",
        scope="symbol",
        dependencies=("open", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.signal_strength.signal_upper_lower_shadow_bucket",
        factor_type="category",
        label_zh="信号K线上下影线结构桶",
        label_en="Signal candle upper/lower shadow structure bucket",
        scope="symbol",
        dependencies=("open", "high", "low", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.stop_fit.fixed_atr_multiple_bucket",
        factor_type="category",
        label_zh="固定5%对应ATR倍数桶",
        label_en="Fixed 5 percent stop distance in ATR multiple bucket",
        scope="symbol",
        dependencies=("high", "low", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.execution.signal_to_entry_return_bucket",
        factor_type="category",
        label_zh="信号日close到入场成交价涨跌桶",
        label_en="Signal close to entry execution return bucket",
        scope="execution",
        dependencies=("trade_lifecycle",),
        source="trade_lifecycle",
    ),
    EntryAttributionFactorDeclaration(
        key="entry.weekly.symbol_kdj_j_bucket",
        factor_type="category",
        label_zh="个股周线KDJ J分桶",
        label_en="Symbol weekly KDJ J bucket",
        scope="symbol",
        dependencies=("kdj:W",),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.weekly.symbol_kdj_state",
        factor_type="category",
        label_zh="个股周线KDJ状态",
        label_en="Symbol weekly KDJ state",
        scope="symbol",
        dependencies=("kdj:W",),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.weekly.symbol_close_vs_week_ma20_bucket",
        factor_type="category",
        label_zh="个股周线收盘相对 MA20 桶",
        label_en="Symbol weekly close versus weekly MA20 bucket",
        scope="symbol",
        dependencies=("weekly_bars", "ma20:W"),
    ),
    EntryAttributionFactorDeclaration(
        key="entry.weekly.symbol_ma_trend_bucket",
        factor_type="category",
        label_zh="个股周线均线趋势桶",
        label_en="Symbol weekly moving-average trend bucket",
        scope="symbol",
        dependencies=("weekly_bars",),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.sw_l1.code",
        factor_type="category",
        label_zh="申万一级行业代码",
        label_en="SW level 1 industry code",
        scope="industry",
    ),
    EntryAttributionFactorDeclaration(
        key="industry.kdj.k",
        factor_type="value",
        label_zh="行业 KDJ K",
        label_en="Industry KDJ K",
        scope="industry",
        dependencies=("industry_index_bars", "kdj:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.kdj.d",
        factor_type="value",
        label_zh="行业 KDJ D",
        label_en="Industry KDJ D",
        scope="industry",
        dependencies=("industry_index_bars", "kdj:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.kdj.j",
        factor_type="value",
        label_zh="行业 KDJ J",
        label_en="Industry KDJ J",
        scope="industry",
        dependencies=("industry_index_bars", "kdj:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.kdj.j_below_threshold",
        factor_type="check",
        label_zh="行业 KDJ J 低于阈值",
        label_en="Industry KDJ J below threshold",
        scope="industry",
        dependencies=("industry_index_bars", "kdj:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.kdj.j_bucket",
        factor_type="category",
        label_zh="行业 KDJ J 分桶",
        label_en="Industry KDJ J bucket",
        scope="industry",
        dependencies=("industry_index_bars", "kdj:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.kdj.state",
        factor_type="category",
        label_zh="行业 KDJ 状态",
        label_en="Industry KDJ state",
        scope="industry",
        dependencies=("industry_index_bars", "kdj:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.kdj.week.indicator_date",
        factor_type="value",
        label_zh="行业周线 KDJ 指标日期",
        label_en="Industry weekly KDJ indicator date",
        scope="industry",
        dependencies=("industry_index_bars", "kdj:W"),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.kdj.week.k",
        factor_type="value",
        label_zh="行业周线 KDJ K",
        label_en="Industry weekly KDJ K",
        scope="industry",
        dependencies=("industry_index_bars", "kdj:W"),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.kdj.week.d",
        factor_type="value",
        label_zh="行业周线 KDJ D",
        label_en="Industry weekly KDJ D",
        scope="industry",
        dependencies=("industry_index_bars", "kdj:W"),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.kdj.week.j",
        factor_type="value",
        label_zh="行业周线 KDJ J",
        label_en="Industry weekly KDJ J",
        scope="industry",
        dependencies=("industry_index_bars", "kdj:W"),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.kdj.week.j_bucket",
        factor_type="category",
        label_zh="行业周线 KDJ J 分桶",
        label_en="Industry weekly KDJ J bucket",
        scope="industry",
        dependencies=("industry_index_bars", "kdj:W"),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.kdj.week.state",
        factor_type="category",
        label_zh="行业周线 KDJ 状态",
        label_en="Industry weekly KDJ state",
        scope="industry",
        dependencies=("industry_index_bars", "kdj:W"),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.macd.dif",
        factor_type="value",
        label_zh="行业 MACD DIF",
        label_en="Industry MACD DIF",
        scope="industry",
        dependencies=("industry_index_bars", "macd:D"),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.macd.dea",
        factor_type="value",
        label_zh="行业 MACD DEA",
        label_en="Industry MACD DEA",
        scope="industry",
        dependencies=("industry_index_bars", "macd:D"),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.macd.macd_bar",
        factor_type="value",
        label_zh="行业 MACD 归因柱",
        label_en="Industry MACD attribution bar",
        scope="industry",
        dependencies=("industry_index_bars", "macd:D"),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.macd.energy_zone",
        factor_type="category",
        label_zh="行业日线 MACD 能量区间",
        label_en="Industry daily MACD energy zone",
        scope="industry",
        dependencies=("industry_index_bars", "macd:D"),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.macd.week.indicator_date",
        factor_type="value",
        label_zh="行业周线 MACD 指标日期",
        label_en="Industry weekly MACD indicator date",
        scope="industry",
        dependencies=("industry_index_bars", "macd:W"),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.macd.week.dif",
        factor_type="value",
        label_zh="行业周线 MACD DIF",
        label_en="Industry weekly MACD DIF",
        scope="industry",
        dependencies=("industry_index_bars", "macd:W"),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.macd.week.dea",
        factor_type="value",
        label_zh="行业周线 MACD DEA",
        label_en="Industry weekly MACD DEA",
        scope="industry",
        dependencies=("industry_index_bars", "macd:W"),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.macd.week.macd_bar",
        factor_type="value",
        label_zh="行业周线 MACD 归因柱",
        label_en="Industry weekly MACD attribution bar",
        scope="industry",
        dependencies=("industry_index_bars", "macd:W"),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.macd.week.energy_zone",
        factor_type="category",
        label_zh="行业周线 MACD 能量区间",
        label_en="Industry weekly MACD energy zone",
        scope="industry",
        dependencies=("industry_index_bars", "macd:W"),
        timings=("entry", "add_on", "exit"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.ma.ma20",
        factor_type="value",
        label_zh="行业 MA20",
        label_en="Industry MA20",
        scope="industry",
        dependencies=("industry_index_bars", "ma20:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.ma.ma60",
        factor_type="value",
        label_zh="行业 MA60",
        label_en="Industry MA60",
        scope="industry",
        dependencies=("industry_index_bars", "ma60:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.ma.price_above_ma20",
        factor_type="check",
        label_zh="行业价格在 MA20 上方",
        label_en="Industry price above MA20",
        scope="industry",
        dependencies=("industry_index_bars", "close", "ma20:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.ma.price_above_ma60",
        factor_type="check",
        label_zh="行业价格在 MA60 上方",
        label_en="Industry price above MA60",
        scope="industry",
        dependencies=("industry_index_bars", "close", "ma60:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.ma.ma20_above_ma60",
        factor_type="check",
        label_zh="行业 MA20 高于 MA60",
        label_en="Industry MA20 above MA60",
        scope="industry",
        dependencies=("industry_index_bars", "ma20:D", "ma60:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.ma.bullish_trend",
        factor_type="check",
        label_zh="行业均线多头趋势",
        label_en="Industry MA bullish trend",
        scope="industry",
        dependencies=("industry_index_bars", "close", "ma20:D", "ma60:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.ma.trend_state",
        factor_type="category",
        label_zh="行业均线趋势状态",
        label_en="Industry MA trend state",
        scope="industry",
        dependencies=("industry_index_bars", "close", "ma20:D", "ma60:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.volatility.return_vol_20d_bucket",
        factor_type="category",
        label_zh="行业 20 日收益波动率桶",
        label_en="Industry 20-day return volatility bucket",
        scope="industry",
        dependencies=("industry_index_bars", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.volatility.return_vol_60d_bucket",
        factor_type="category",
        label_zh="行业 60 日收益波动率桶",
        label_en="Industry 60-day return volatility bucket",
        scope="industry",
        dependencies=("industry_index_bars", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.volatility.atr_20d_bucket",
        factor_type="category",
        label_zh="行业 20 日 ATR 百分比桶",
        label_en="Industry 20-day ATR percentage bucket",
        scope="industry",
        dependencies=("industry_index_bars", "high", "low", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.price_position.near_high_60d_bucket",
        factor_type="category",
        label_zh="行业距 60 日高点位置桶",
        label_en="Industry distance from 60-day high bucket",
        scope="industry",
        dependencies=("industry_index_bars", "high", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.relative.hs300.return_20d",
        factor_type="value",
        label_zh="行业 20 日收益",
        label_en="Industry 20-day return",
        scope="industry",
        dependencies=("industry_index_bars", "000300.SH"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.relative.hs300.return_60d",
        factor_type="value",
        label_zh="行业 60 日收益",
        label_en="Industry 60-day return",
        scope="industry",
        dependencies=("industry_index_bars", "000300.SH"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.relative.hs300.excess_return_20d",
        factor_type="value",
        label_zh="行业相对沪深300 20 日超额收益",
        label_en="Industry 20-day excess return vs CSI 300",
        scope="industry",
        dependencies=("industry_index_bars", "000300.SH"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.relative.hs300.excess_return_60d",
        factor_type="value",
        label_zh="行业相对沪深300 60 日超额收益",
        label_en="Industry 60-day excess return vs CSI 300",
        scope="industry",
        dependencies=("industry_index_bars", "000300.SH"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.relative.hs300.outperform_20d",
        factor_type="check",
        label_zh="行业 20 日强于沪深300",
        label_en="Industry 20-day outperform CSI 300",
        scope="industry",
        dependencies=("industry_index_bars", "000300.SH"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.relative.hs300.outperform_60d",
        factor_type="check",
        label_zh="行业 60 日强于沪深300",
        label_en="Industry 60-day outperform CSI 300",
        scope="industry",
        dependencies=("industry_index_bars", "000300.SH"),
    ),
    EntryAttributionFactorDeclaration(
        key="industry.relative.hs300.strength_state",
        factor_type="category",
        label_zh="行业相对沪深300强弱状态",
        label_en="Industry relative strength state vs CSI 300",
        scope="industry",
        dependencies=("industry_index_bars", "000300.SH"),
    ),
    EntryAttributionFactorDeclaration(
        key="market.hs300.close",
        factor_type="value",
        label_zh="沪深300收盘价",
        label_en="CSI 300 close",
        scope="market",
        dependencies=("000300.SH",),
    ),
    EntryAttributionFactorDeclaration(
        key="market.hs300.ma20",
        factor_type="value",
        label_zh="沪深300 MA20",
        label_en="CSI 300 MA20",
        scope="market",
        dependencies=("000300.SH", "ma20:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="market.hs300.ma60",
        factor_type="value",
        label_zh="沪深300 MA60",
        label_en="CSI 300 MA60",
        scope="market",
        dependencies=("000300.SH", "ma60:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="market.hs300.bullish_trend",
        factor_type="check",
        label_zh="沪深300多头趋势",
        label_en="CSI 300 bullish trend",
        scope="market",
        dependencies=("000300.SH", "close", "ma20:D", "ma60:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="market.hs300.trend_state",
        factor_type="category",
        label_zh="沪深300趋势状态",
        label_en="CSI 300 trend state",
        scope="market",
        dependencies=("000300.SH", "close", "ma20:D", "ma60:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="market.hs300.return_vol_20d_bucket",
        factor_type="category",
        label_zh="沪深300 20 日收益波动率桶",
        label_en="CSI 300 20-day return volatility bucket",
        scope="market",
        dependencies=("000300.SH", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="market.hs300.return_vol_60d_bucket",
        factor_type="category",
        label_zh="沪深300 60 日收益波动率桶",
        label_en="CSI 300 60-day return volatility bucket",
        scope="market",
        dependencies=("000300.SH", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="market.hs300.kdj.k",
        factor_type="value",
        label_zh="沪深300 KDJ K",
        label_en="CSI 300 KDJ K",
        scope="market",
        dependencies=("000300.SH", "kdj:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="market.hs300.kdj.d",
        factor_type="value",
        label_zh="沪深300 KDJ D",
        label_en="CSI 300 KDJ D",
        scope="market",
        dependencies=("000300.SH", "kdj:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="market.hs300.kdj.j",
        factor_type="value",
        label_zh="沪深300 KDJ J",
        label_en="CSI 300 KDJ J",
        scope="market",
        dependencies=("000300.SH", "kdj:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="market.hs300.kdj.threshold",
        factor_type="value",
        label_zh="沪深300 KDJ 阈值",
        label_en="CSI 300 KDJ threshold",
        scope="market",
        dependencies=("000300.SH", "kdj:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="market.hs300.kdj.j_below_threshold",
        factor_type="check",
        label_zh="沪深300 KDJ J 低于阈值",
        label_en="CSI 300 KDJ J below threshold",
        scope="market",
        dependencies=("000300.SH", "kdj:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="market.hs300.weekly.kdj_state",
        factor_type="category",
        label_zh="沪深300周线KDJ状态",
        label_en="CSI 300 weekly KDJ state",
        scope="market",
        dependencies=("000300.SH", "kdj:W"),
    ),
    EntryAttributionFactorDeclaration(
        key="market.hs300.weekly.ma_trend_bucket",
        factor_type="category",
        label_zh="沪深300周线均线趋势桶",
        label_en="CSI 300 weekly moving-average trend bucket",
        scope="market",
        dependencies=("000300.SH", "weekly_bars"),
    ),
    EntryAttributionFactorDeclaration(
        key="market.csi500.return_vol_20d_bucket",
        factor_type="category",
        label_zh="中证500 20 日收益波动率桶",
        label_en="CSI 500 20-day return volatility bucket",
        scope="market",
        dependencies=("000905.SH", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="market.csi500.weekly.kdj_state",
        factor_type="category",
        label_zh="中证500周线KDJ状态",
        label_en="CSI 500 weekly KDJ state",
        scope="market",
        dependencies=("000905.SH", "kdj:W"),
    ),
    EntryAttributionFactorDeclaration(
        key="market.csi500.weekly.ma_trend_bucket",
        factor_type="category",
        label_zh="中证500周线均线趋势桶",
        label_en="CSI 500 weekly moving-average trend bucket",
        scope="market",
        dependencies=("000905.SH", "weekly_bars"),
    ),
    EntryAttributionFactorDeclaration(
        key="market.csi500.return_vol_60d_bucket",
        factor_type="category",
        label_zh="中证500 60 日收益波动率桶",
        label_en="CSI 500 60-day return volatility bucket",
        scope="market",
        dependencies=("000905.SH", "close"),
    ),
    EntryAttributionFactorDeclaration(
        key="market.objective.entry_index_drawdown_250d_bucket",
        factor_type="category",
        label_zh="客观市场入场指数250日回撤桶",
        label_en="Objective market entry index 250-day drawdown bucket",
        scope="market",
        dependencies=("000300.SH", "000905.SH", "close", "ma250:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="market.objective.entry_index_ma60_slope_20d_bucket",
        factor_type="category",
        label_zh="客观市场入场指数MA60 20日斜率桶",
        label_en="Objective market entry index MA60 20-day slope bucket",
        scope="market",
        dependencies=("000300.SH", "000905.SH", "ma60:D"),
    ),
    EntryAttributionFactorDeclaration(
        key="sizing.risk_group",
        factor_type="category",
        label_zh="仓位风险组",
        label_en="Sizing risk group",
        scope="sizing",
    ),
)

_STANDARD_ENTRY_ATTRIBUTION_FACTOR_KEYS = frozenset(
    declaration.key for declaration in STANDARD_ENTRY_ATTRIBUTION_FACTORS
)


def _reference_entry_attribution_declaration(
    definition: Mapping[str, Any],
) -> EntryAttributionFactorDeclaration:
    field_key = str(definition.get("field_key") or "")
    value_type = str(definition.get("value_type") or ("bucket" if field_key.endswith("_bucket") else "value"))
    factor_type = "category" if value_type in {"bucket", "category"} else "value"
    scope = "industry" if field_key.startswith("industry.") else "symbol"
    return EntryAttributionFactorDeclaration(
        key=field_key,
        factor_type=factor_type,
        label_zh=str(definition.get("label_zh") or field_key),
        label_en=field_key,
        scope=scope,
        dependencies=("attribution_reference_snapshot",),
        source="attribution_reference_snapshot",
        value_type=value_type,
    )


REFERENCE_ENTRY_ATTRIBUTION_FACTORS = tuple(
    _reference_entry_attribution_declaration(definition)
    for definition in ATTRIBUTION_REFERENCE_FIELD_DEFINITIONS
    if str(definition.get("field_key") or "") not in _STANDARD_ENTRY_ATTRIBUTION_FACTOR_KEYS
)

STANDARD_ENTRY_ATTRIBUTION_FACTORS = STANDARD_ENTRY_ATTRIBUTION_FACTORS + REFERENCE_ENTRY_ATTRIBUTION_FACTORS

STANDARD_ATTRIBUTION_FACTORS = STANDARD_ENTRY_ATTRIBUTION_FACTORS


def entry_attribution_factor_declarations() -> tuple[EntryAttributionFactorDeclaration, ...]:
    return STANDARD_ENTRY_ATTRIBUTION_FACTORS


def entry_attribution_declaration_by_key() -> dict[str, EntryAttributionFactorDeclaration]:
    return {declaration.key: declaration for declaration in STANDARD_ENTRY_ATTRIBUTION_FACTORS}


def entry_attribution_factor_keys() -> tuple[str, ...]:
    return tuple(declaration.key for declaration in STANDARD_ENTRY_ATTRIBUTION_FACTORS)


def attribution_factor_declarations() -> tuple[AttributionFactorDeclaration, ...]:
    return STANDARD_ATTRIBUTION_FACTORS


def attribution_declaration_by_key() -> dict[str, AttributionFactorDeclaration]:
    return {declaration.key: declaration for declaration in STANDARD_ATTRIBUTION_FACTORS}


def attribution_factor_keys() -> tuple[str, ...]:
    return tuple(declaration.key for declaration in STANDARD_ATTRIBUTION_FACTORS)


def resolve_attribution_factor_selection(
    include: Sequence[str],
    *,
    applicable_factor_keys: Sequence[str] | None = None,
    configured_source: str,
) -> dict[str, Any]:
    declarations = attribution_declaration_by_key()
    applicable = tuple(str(key) for key in (applicable_factor_keys or attribution_factor_keys()))
    include_keys = tuple(str(key) for key in include)
    duplicate_include = sorted({key for key in include_keys if include_keys.count(key) > 1})
    if duplicate_include:
        raise ValueError(f"attribution include factors cannot contain duplicates: {duplicate_include}")

    invalid_applicable = sorted(key for key in applicable if key not in declarations)
    if invalid_applicable:
        raise ValueError(f"unknown applicable attribution factors: {invalid_applicable}")

    invalid_include = sorted(key for key in include_keys if key not in declarations)
    if invalid_include:
        raise ValueError(f"unknown attribution include factors: {invalid_include}")

    not_applicable = sorted(set(include_keys) - set(applicable))
    if not_applicable:
        raise ValueError(f"attribution include factors are not applicable: {not_applicable}")

    include_set = frozenset(include_keys)
    not_include = tuple(key for key in applicable if key not in include_set)

    return {
        "schema": ATTRIBUTION_FACTOR_SELECTION_SCHEMA,
        "configured_source": configured_source,
        "applicable": applicable,
        "include": include_keys,
        "not_include": not_include,
        "include_count": len(include_keys),
        "not_include_count": len(not_include),
        "factors": tuple(
            {
                **attribution_factor_declaration_payload(declarations[key]),
                "selected": key in include_set,
            }
            for key in applicable
        ),
    }


def attribution_factor_declaration_payload(declaration: AttributionFactorDeclaration) -> dict[str, Any]:
    return {
        "key": declaration.key,
        "owner": declaration.owner,
        "timings": declaration.timings,
        "factor_type": declaration.factor_type,
        "value_type": declaration.value_type,
        "label_zh": declaration.label_zh,
        "label_en": declaration.label_en,
        "scope": declaration.scope,
        "source": declaration.source,
        "dependencies": declaration.dependencies,
        "missing_behavior": declaration.missing_behavior,
        "compatible_strategies": declaration.compatible_strategies,
        "compatible_methods": declaration.compatible_methods,
    }


def entry_attribution_payload(
    *,
    checks: Mapping[str, bool] | None = None,
    values: Mapping[str, Any] | None = None,
    categories: Mapping[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    return {
        "checks": {
            str(key): value
            for key, value in dict(checks or {}).items()
            if isinstance(value, bool)
        },
        "values": {
            str(key): value
            for key, value in dict(values or {}).items()
            if _is_scalar_json_value(value) and not isinstance(value, bool)
        },
        "categories": {
            str(key): str(value)
            for key, value in dict(categories or {}).items()
            if value is not None
        },
    }


def with_entry_attribution_evidence(
    intent: TradeIntent,
    evidence: EntryAttributionEvidence | None,
) -> TradeIntent:
    if evidence is None or evidence.is_empty():
        return intent

    signal_values = dict(intent.signal_values)
    signal_values["attribution"] = _merge_attribution_payloads(
        signal_values.get("attribution"),
        evidence.to_signal_values(),
    )
    return replace(intent, signal_values=signal_values)


def with_enabled_entry_attribution_factors(
    intent: TradeIntent,
    enabled_factor_keys: frozenset[str] | Sequence[str],
) -> TradeIntent:
    enabled_keys = frozenset(str(key) for key in enabled_factor_keys)
    signal_values = dict(intent.signal_values)
    attribution = signal_values.get("attribution")
    if not isinstance(attribution, Mapping):
        return intent

    filtered = _filter_attribution_payload(attribution, enabled_keys)
    if not filtered["checks"] and not filtered["values"] and not filtered["categories"]:
        signal_values.pop("attribution", None)
    else:
        signal_values["attribution"] = filtered
    return replace(intent, signal_values=signal_values)


def _entry_attribution_condition_audits(
    attribution: Mapping[str, Any],
    conditions: Sequence[EntryAttributionFilterCondition],
    *,
    missing_policy: str,
) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    for condition in conditions:
        found, actual, source = _entry_attribution_condition_value(attribution, condition.field)
        matched = found and _entry_attribution_condition_matches(
            actual,
            operator=condition.operator,
            expected=condition.value,
        )
        if not found:
            passed = missing_policy == "pass"
        elif condition.action == "keep":
            passed = matched
        else:
            passed = not matched
        audits.append(
            {
                "field": condition.field,
                "operator": condition.operator,
                "value": condition.value,
                "action": condition.action,
                "actual": actual if found else None,
                "matched": matched,
                "passed": passed,
                "source": source if found else None,
            }
        )
    return audits


def _entry_attribution_condition_matches(
    actual: Any,
    *,
    operator: str,
    expected: Any,
) -> bool:
    if operator == "eq":
        return actual == expected
    actual_number = _filter_number(actual)
    expected_number = _filter_number(expected)
    if actual_number is None or expected_number is None:
        return False
    if operator == "gt":
        return actual_number > expected_number
    if operator == "gte":
        return actual_number >= expected_number
    if operator == "lt":
        return actual_number < expected_number
    if operator == "lte":
        return actual_number <= expected_number
    return False


def _filter_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            return None
        return float(value)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _entry_attribution_condition_value(
    attribution: Mapping[str, Any],
    field_name: str,
) -> tuple[bool, Any, str | None]:
    for source in ("categories", "values", "checks"):
        raw_values = attribution.get(source)
        if isinstance(raw_values, Mapping) and field_name in raw_values:
            return True, raw_values[field_name], source
    return False, None, None


def apply_entry_attribution_filter(
    intent: TradeIntent,
    rule: EntryAttributionFilterRule,
) -> TradeIntent:
    if not rule.is_active():
        return intent
    if intent.intent_type != TradeIntentType.ENTER:
        return intent

    attribution = _attribution_payload(intent.signal_values)
    raw_checks = attribution.get("checks")
    checks = raw_checks if isinstance(raw_checks, Mapping) else {}
    passed_checks: list[str] = []
    failed_checks: list[str] = []
    missing_checks: list[str] = []

    for key in rule.required_checks:
        value = checks.get(key)
        if value is True:
            passed_checks.append(key)
        elif value is False:
            failed_checks.append(key)
        else:
            missing_checks.append(key)

    condition_audits = _entry_attribution_condition_audits(
        attribution,
        rule.conditions,
        missing_policy=rule.missing_policy,
    )
    failed_conditions = [
        condition["field"]
        for condition in condition_audits
        if not condition["passed"] and condition["source"] is not None
    ]
    missing_conditions = [
        condition["field"]
        for condition in condition_audits
        if condition["source"] is None
    ]

    blocked = (
        bool(failed_checks)
        or (bool(missing_checks) and rule.missing_policy == "block")
        or any(not condition["passed"] for condition in condition_audits)
    )
    signal_values = dict(intent.signal_values)
    signal_values["entry_attribution_filter"] = {
        "enabled": True,
        "required_checks": list(rule.required_checks),
        "conditions": condition_audits,
        "passed": not blocked,
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
        "missing_checks": missing_checks,
        "failed_conditions": failed_conditions,
        "missing_conditions": missing_conditions,
        "missing_policy": rule.missing_policy,
    }
    if not blocked:
        return replace(intent, signal_values=signal_values)

    signal_values["entry_attribution_filter"]["blocked_by"] = rule.blocked_by
    signal_values["entry_attribution_filter"]["original_reason_code"] = intent.reason_code
    return replace(
        intent,
        intent_type=TradeIntentType.AVOID,
        reason_code=rule.reason_code,
        signal_values=signal_values,
        blocked_by=rule.blocked_by,
    )


def with_entry_attribution_controls(
    intent: TradeIntent,
    context: EntryAttributionContext | None,
    *,
    symbol: str,
    trade_date: date,
) -> TradeIntent:
    if context is None:
        return intent

    controlled_intent = with_entry_attribution_evidence(intent, context.evidence_for(symbol, trade_date))
    controlled_intent = with_enabled_entry_attribution_factors(
        controlled_intent,
        context.enabled_factor_keys or frozenset(),
    )
    return apply_entry_attribution_filter(controlled_intent, context.entry_filter)


def with_sizing_attribution(
    intent: TradeIntent,
    sizing_values: Mapping[str, Any],
    *,
    enabled_factor_keys: frozenset[str] | Sequence[str] | None = None,
) -> TradeIntent:
    if enabled_factor_keys is not None and "sizing.risk_group" not in set(enabled_factor_keys):
        return intent

    categories: dict[str, str] = {}
    risk_group = sizing_values.get("risk_group")
    if risk_group:
        categories["sizing.risk_group"] = str(risk_group)

    if not categories:
        return intent

    return with_entry_attribution_evidence(
        intent,
        EntryAttributionEvidence(categories=categories),
    )


def build_entry_attribution_context(
    *,
    bars_by_symbol: Mapping[str, Sequence[DailyBar]],
    indicators_by_symbol: Mapping[str, IndicatorFrame],
    benchmark_bars_by_symbol: Mapping[str, Sequence[IndexBar]] | None = None,
    industry_index_bars_by_symbol: Mapping[str, Sequence[IndexBar]] | None = None,
    memberships_by_symbol: Mapping[str, Sequence[StockIndustryMembership]] | None = None,
    attribution_reference_evidence_by_symbol_date: (
        Mapping[str, Mapping[date, EntryAttributionEvidence]] | None
    ) = None,
    market_symbol: str = "000300.SH",
    market_fast_period: int = 20,
    market_slow_period: int = 60,
    industry_kdj_threshold: float = 13.0,
    symbol_kdj_threshold: float = 13.0,
    market_kdj_threshold: float = 13.0,
    enabled_factor_keys: Sequence[str] | None = None,
    entry_filter: EntryAttributionFilterRule | None = None,
) -> EntryAttributionContext:
    enabled_keys = frozenset(enabled_factor_keys if enabled_factor_keys is not None else entry_attribution_factor_keys())
    benchmark_bars_by_symbol = dict(benchmark_bars_by_symbol or {})
    industry_index_bars_by_symbol = dict(industry_index_bars_by_symbol or {})
    memberships_by_symbol = dict(memberships_by_symbol or {})
    attribution_reference_evidence_by_symbol_date = dict(attribution_reference_evidence_by_symbol_date or {})
    market_evidence_by_date: dict[date, EntryAttributionEvidence] = {}
    market_symbols = tuple(dict.fromkeys((market_symbol, *benchmark_bars_by_symbol)))
    for current_market_symbol in market_symbols:
        current_market_evidence = _market_trend_evidence_by_date(
            benchmark_bars_by_symbol.get(current_market_symbol, ()),
            market_symbol=current_market_symbol,
            fast_period=market_fast_period,
            slow_period=market_slow_period,
            kdj_threshold=market_kdj_threshold,
        )
        for evidence_date, evidence in current_market_evidence.items():
            market_evidence_by_date[evidence_date] = _merge_evidence(
                market_evidence_by_date.get(evidence_date),
                evidence,
            )
    objective_market_evidence_by_date = _objective_market_component_evidence_by_date(benchmark_bars_by_symbol)
    for evidence_date, evidence in objective_market_evidence_by_date.items():
        market_evidence_by_date[evidence_date] = _merge_evidence(
            market_evidence_by_date.get(evidence_date),
            evidence,
        )
    industry_evidence_by_symbol = _industry_kdj_evidence_by_symbol(
        industry_index_bars_by_symbol,
        market_bars=benchmark_bars_by_symbol.get(market_symbol, ()),
        threshold=industry_kdj_threshold,
    )
    symbol_cross_section_evidence_by_symbol = _symbol_cross_section_evidence_by_symbol(bars_by_symbol)
    symbol_industry_relative_evidence_by_symbol = _symbol_industry_relative_evidence_by_symbol(
        bars_by_symbol,
        memberships_by_symbol=memberships_by_symbol,
    )

    evidence_by_key: dict[tuple[str, date], EntryAttributionEvidence] = {}
    for symbol, bars in sorted(bars_by_symbol.items()):
        ordered_bars = tuple(sorted(bars, key=lambda value: value.trade_date))
        frame = indicators_by_symbol.get(symbol)
        ma_values_by_period = {
            period: _ma_values_by_date(ordered_bars, period=period)
            for period in (20, 25, 60)
        }
        symbol_derived_evidence_by_date = _symbol_derived_evidence_by_date(ordered_bars)
        symbol_cross_section_evidence_by_date = symbol_cross_section_evidence_by_symbol.get(symbol, {})
        symbol_industry_relative_evidence_by_date = symbol_industry_relative_evidence_by_symbol.get(symbol, {})
        attribution_reference_evidence_by_date = attribution_reference_evidence_by_symbol_date.get(symbol, {})
        for bar in ordered_bars:
            evidence = _merge_evidence(
                _latest_evidence_on_or_before(attribution_reference_evidence_by_date, bar.trade_date),
                _latest_evidence_on_or_before(symbol_derived_evidence_by_date, bar.trade_date),
                _latest_evidence_on_or_before(symbol_cross_section_evidence_by_date, bar.trade_date),
                _latest_evidence_on_or_before(symbol_industry_relative_evidence_by_date, bar.trade_date),
                _symbol_evidence(
                    bar,
                    frame,
                    ma_values={
                        period: values_by_date[bar.trade_date]
                        for period, values_by_date in ma_values_by_period.items()
                        if bar.trade_date in values_by_date
                    },
                    kdj_threshold=symbol_kdj_threshold,
                ),
                _latest_evidence_on_or_before(market_evidence_by_date, bar.trade_date),
                _industry_evidence_for_symbol_date(
                    symbol,
                    bar.trade_date,
                    memberships_by_symbol=memberships_by_symbol,
                    industry_evidence_by_symbol=industry_evidence_by_symbol,
                ),
            )
            evidence = _filter_evidence(evidence, enabled_keys)
            if not evidence.is_empty():
                evidence_by_key[(symbol, bar.trade_date)] = evidence

    return EntryAttributionContext(
        evidence_by_key=evidence_by_key,
        enabled_factor_keys=enabled_keys,
        entry_filter=entry_filter or EntryAttributionFilterRule(),
    )


def _symbol_cross_section_evidence_by_symbol(
    bars_by_symbol: Mapping[str, Sequence[DailyBar]],
) -> dict[str, dict[date, EntryAttributionEvidence]]:
    raw_values_by_field: dict[str, dict[str, dict[date, float]]] = {
        "entry.volatility.return_vol_20d_bucket": {},
        "entry.volatility.return_vol_60d_bucket": {},
        "entry.volatility.atr_20d_bucket": {},
        "entry.volatility.max_amplitude_20d_bucket": {},
        "entry.momentum.return_20d_bucket": {},
        "entry.momentum.return_60d_bucket": {},
        "entry.momentum.return_120d_bucket": {},
    }
    for symbol, bars in bars_by_symbol.items():
        ordered_bars = tuple(sorted(bars, key=lambda value: value.trade_date))
        raw_values_by_field["entry.volatility.return_vol_20d_bucket"][symbol] = (
            _return_volatility_values_by_date(ordered_bars, period=20)
        )
        raw_values_by_field["entry.volatility.return_vol_60d_bucket"][symbol] = (
            _return_volatility_values_by_date(ordered_bars, period=60)
        )
        raw_values_by_field["entry.volatility.atr_20d_bucket"][symbol] = (
            _atr_pct_values_by_date(ordered_bars, period=20)
        )
        raw_values_by_field["entry.volatility.max_amplitude_20d_bucket"][symbol] = (
            _max_amplitude_values_by_date(ordered_bars, period=20)
        )
        raw_values_by_field["entry.momentum.return_20d_bucket"][symbol] = (
            _return_values_by_date(ordered_bars, period=20)
        )
        raw_values_by_field["entry.momentum.return_60d_bucket"][symbol] = (
            _return_values_by_date(ordered_bars, period=60)
        )
        raw_values_by_field["entry.momentum.return_120d_bucket"][symbol] = (
            _return_values_by_date(ordered_bars, period=120)
        )

    categories_by_symbol_date: dict[str, dict[date, dict[str, str]]] = {}
    for field_key, values_by_symbol in raw_values_by_field.items():
        percentiles_by_symbol = _cross_section_percentiles_by_symbol(values_by_symbol)
        for symbol, values_by_date in percentiles_by_symbol.items():
            for trade_date, percentile in values_by_date.items():
                bucket = _percentile_bucket(percentile)
                if bucket is None:
                    continue
                categories_by_symbol_date.setdefault(symbol, {}).setdefault(trade_date, {})[field_key] = bucket

    evidence_by_symbol: dict[str, dict[date, EntryAttributionEvidence]] = {}
    for symbol, categories_by_date in categories_by_symbol_date.items():
        evidence_by_symbol[symbol] = {
            trade_date: EntryAttributionEvidence(categories=categories)
            for trade_date, categories in categories_by_date.items()
            if categories
        }
    return evidence_by_symbol


def _symbol_industry_relative_evidence_by_symbol(
    bars_by_symbol: Mapping[str, Sequence[DailyBar]],
    *,
    memberships_by_symbol: Mapping[str, Sequence[StockIndustryMembership]],
) -> dict[str, dict[date, EntryAttributionEvidence]]:
    values_by_industry_date: dict[tuple[str, date], list[tuple[str, float]]] = {}
    for symbol, bars in bars_by_symbol.items():
        ordered_bars = tuple(sorted(bars, key=lambda value: value.trade_date))
        atr_pct_by_date = _atr_pct_values_by_date(ordered_bars, period=20)
        for trade_date, atr_pct in atr_pct_by_date.items():
            if not math.isfinite(atr_pct):
                continue
            membership = _membership_on(symbol, trade_date, memberships_by_symbol=memberships_by_symbol)
            if membership is None:
                continue
            values_by_industry_date.setdefault((membership.level1_code, trade_date), []).append(
                (symbol, float(atr_pct))
            )

    categories_by_symbol_date: dict[str, dict[date, dict[str, str]]] = {}
    for (_industry_code, trade_date), values in values_by_industry_date.items():
        median_value = _median_float([value for _symbol, value in values])
        sorted_values = sorted(values, key=lambda item: (item[1], item[0]))
        count = len(sorted_values)
        index = 0
        while index < count:
            end = index + 1
            while end < count and sorted_values[end][1] == sorted_values[index][1]:
                end += 1
            average_rank = ((index + 1) + end) / 2.0
            percentile_bucket = _percentile_bucket(average_rank / count)
            for symbol, value in sorted_values[index:end]:
                categories = categories_by_symbol_date.setdefault(symbol, {}).setdefault(trade_date, {})
                if percentile_bucket is not None:
                    categories["entry.volatility.industry_atr_percentile_bucket"] = percentile_bucket
                if median_value is not None and median_value > 0:
                    ratio_bucket = _relative_ratio_bucket(value / median_value)
                    if ratio_bucket is not None:
                        categories["entry.volatility.symbol_atr_to_industry_median_bucket"] = ratio_bucket
            index = end

    evidence_by_symbol: dict[str, dict[date, EntryAttributionEvidence]] = {}
    for symbol, categories_by_date in categories_by_symbol_date.items():
        evidence_by_symbol[symbol] = {
            trade_date: EntryAttributionEvidence(categories=categories)
            for trade_date, categories in categories_by_date.items()
            if categories
        }
    return evidence_by_symbol


def _symbol_derived_evidence_by_date(
    bars: Sequence[DailyBar],
) -> dict[date, EntryAttributionEvidence]:
    ordered_bars = tuple(sorted(bars, key=lambda value: value.trade_date))
    if not ordered_bars:
        return {}

    atr_20d = _atr_values_by_date(ordered_bars, period=20)
    atr_pct_20d = _atr_pct_values_by_date(ordered_bars, period=20)
    ma60_values = _ma_values_by_date(ordered_bars, period=60)
    near_high_20d = _near_high_values_by_date(ordered_bars, period=20)
    near_high_60d = _near_high_values_by_date(ordered_bars, period=60)
    new_high_20d = _new_high_values_by_date(ordered_bars, period=20)
    new_high_60d = _new_high_values_by_date(ordered_bars, period=60)
    new_high_120d = _new_high_values_by_date(ordered_bars, period=120)
    interval_20d = _interval_values_by_date(ordered_bars, period=20)
    interval_60d = _interval_values_by_date(ordered_bars, period=60)
    ma60_slope_20d = _ma_slope_values_by_date(ordered_bars, period=60, lookback=20)
    weekly_close_vs_ma20 = _weekly_close_vs_ma20_by_date(ordered_bars)
    weekly_ma_trend = _weekly_ma_trend_by_date(ordered_bars)

    evidence_by_date: dict[date, EntryAttributionEvidence] = {}
    for bar in ordered_bars:
        values: dict[str, Any] = {}
        categories: dict[str, str] = {}
        near_high_20d_bucket = _near_high_bucket(near_high_20d.get(bar.trade_date))
        near_high_60d_bucket = _near_high_bucket(near_high_60d.get(bar.trade_date))
        new_high_20d_bucket = _new_high_bucket(new_high_20d.get(bar.trade_date))
        new_high_60d_bucket = _new_high_bucket(new_high_60d.get(bar.trade_date))
        new_high_120d_bucket = _new_high_bucket(new_high_120d.get(bar.trade_date))
        interval_20d_bucket = _interval_bucket(interval_20d.get(bar.trade_date))
        interval_60d_bucket = _interval_bucket(interval_60d.get(bar.trade_date))
        atr_value = atr_20d.get(bar.trade_date)
        atr_pct_value = atr_pct_20d.get(bar.trade_date)
        ma60_value = ma60_values.get(bar.trade_date)
        signal_close_ma60_pct = None
        signal_close_ma60_atr_multiple_bucket = None
        if atr_value is not None and atr_value > 0 and ma60_value is not None:
            signal_close_ma60_atr_multiple_bucket = _atr_multiple_bucket((bar.close - ma60_value) / atr_value)
        if ma60_value is not None and ma60_value > 0:
            signal_close_ma60_pct = bar.close / ma60_value - 1.0
        fixed_atr_multiple_bucket = None
        if atr_pct_value is not None and atr_pct_value > 0:
            fixed_atr_multiple_bucket = _fixed_atr_multiple_bucket(0.05 / atr_pct_value)
        ma60_slope_20d_bucket = _ma60_slope_bucket(ma60_slope_20d.get(bar.trade_date))
        signal_body_pct = _candle_body_pct(bar)
        signal_body_bucket = _candle_body_bucket(signal_body_pct)
        signal_shadow_bucket = _signal_shadow_bucket(bar)
        weekly_close_vs_ma20_bucket = _ma20_distance_bucket(
            _latest_number_before(weekly_close_vs_ma20, bar.trade_date)
        )
        weekly_ma_trend_bucket = _latest_string_before(weekly_ma_trend, bar.trade_date)

        if near_high_20d_bucket is not None:
            categories["entry.price_position.near_high_20d_bucket"] = near_high_20d_bucket
        if near_high_60d_bucket is not None:
            categories["entry.price_position.near_high_60d_bucket"] = near_high_60d_bucket
        if new_high_20d_bucket is not None:
            categories["entry.momentum.new_high_20d_bucket"] = new_high_20d_bucket
        if new_high_60d_bucket is not None:
            categories["entry.momentum.new_high_60d_bucket"] = new_high_60d_bucket
        if new_high_120d_bucket is not None:
            categories["entry.momentum.new_high_120d_bucket"] = new_high_120d_bucket
        if interval_20d_bucket is not None:
            categories["entry.price_position.interval_20d_bucket"] = interval_20d_bucket
        if interval_60d_bucket is not None:
            categories["entry.price_position.interval_60d_bucket"] = interval_60d_bucket
        if signal_close_ma60_atr_multiple_bucket is not None:
            categories["entry.price_position.signal_close_ma60_atr_multiple_bucket"] = signal_close_ma60_atr_multiple_bucket
        if signal_close_ma60_pct is not None:
            values["entry.price_position.signal_close_ma60_pct"] = signal_close_ma60_pct
        if fixed_atr_multiple_bucket is not None:
            categories["entry.stop_fit.fixed_atr_multiple_bucket"] = fixed_atr_multiple_bucket
        if ma60_slope_20d_bucket is not None:
            categories["entry.signal_strength.ma60_slope_20d_bucket"] = ma60_slope_20d_bucket
        if signal_body_bucket is not None:
            categories["entry.signal_strength.signal_candle_body_bucket"] = signal_body_bucket
        if signal_body_pct is not None:
            values["entry.signal_strength.signal_candle_body_pct"] = signal_body_pct
        if signal_shadow_bucket is not None:
            categories["entry.signal_strength.signal_upper_lower_shadow_bucket"] = signal_shadow_bucket
        if weekly_close_vs_ma20_bucket is not None:
            categories["entry.weekly.symbol_close_vs_week_ma20_bucket"] = weekly_close_vs_ma20_bucket
        if weekly_ma_trend_bucket is not None:
            categories["entry.weekly.symbol_ma_trend_bucket"] = weekly_ma_trend_bucket

        if values or categories:
            evidence_by_date[bar.trade_date] = EntryAttributionEvidence(values=values, categories=categories)

    return evidence_by_date


def _symbol_evidence(
    bar: DailyBar,
    frame: IndicatorFrame | None,
    *,
    ma_values: Mapping[int, float],
    kdj_threshold: float,
) -> EntryAttributionEvidence:
    values: dict[str, Any] = {"symbol.close": bar.close}
    checks: dict[str, bool] = {}
    categories: dict[str, str] = {}

    if frame is not None:
        try:
            kdj = frame.kdj_at(bar.trade_date)
            values["symbol.kdj.k"] = kdj.k
            values["symbol.kdj.d"] = kdj.d
            values["symbol.kdj.j"] = kdj.j
            values["symbol.kdj.threshold"] = kdj_threshold
            checks["symbol.kdj.j_below_threshold"] = kdj.j < kdj_threshold
        except KeyError:
            pass
        try:
            weekly_kdj = completed_indicator_before_event(
                frame,
                name="kdj",
                timeframe="W",
                event_date=bar.trade_date,
            )
            values["symbol.kdj.week.indicator_date"] = weekly_kdj.indicator_date.isoformat()
            values["symbol.kdj.week.k"] = weekly_kdj.value.k
            values["symbol.kdj.week.d"] = weekly_kdj.value.d
            values["symbol.kdj.week.j"] = weekly_kdj.value.j
            weekly_j_bucket = _kdj_j_bucket(weekly_kdj.value.j)
            weekly_state = _kdj_state(weekly_kdj.value.j)
            categories["symbol.kdj.week.j_bucket"] = weekly_j_bucket
            categories["symbol.kdj.week.state"] = weekly_state
            categories["entry.weekly.symbol_kdj_j_bucket"] = weekly_j_bucket
            categories["entry.weekly.symbol_kdj_state"] = weekly_state
        except KeyError:
            pass
        try:
            macd = frame.macd_at(bar.trade_date)
            macd_bar = _macd_attribution_bar(macd.line, macd.signal)
            values["symbol.macd.dif"] = macd.line
            values["symbol.macd.dea"] = macd.signal
            values["symbol.macd.macd_bar"] = macd_bar
            categories["symbol.macd.energy_zone"] = _macd_energy_zone(macd.line, macd.signal)
            if bar.close > 0:
                categories["entry.signal_strength.dea_value_bucket"] = _positive_strength_bucket(
                    macd.signal / bar.close
                )
                categories["entry.signal_strength.macd_bar_bucket"] = _signed_strength_bucket(
                    macd_bar / bar.close
                )
                categories["entry.signal_strength.dif_dea_distance_bucket"] = _signed_strength_bucket(
                    (macd.line - macd.signal) / bar.close
                )
            waterline_age = _dea_waterline_age_trading_days(frame, bar.trade_date)
            waterline_age_bucket = _dea_waterline_age_bucket(waterline_age)
            if waterline_age is not None:
                values["symbol.macd.dea_waterline_age_trading_days"] = waterline_age
            if waterline_age_bucket is not None:
                categories["entry.signal_strength.dea_waterline_age_trading_days_bucket"] = waterline_age_bucket
        except KeyError:
            pass
        try:
            weekly_macd = completed_indicator_before_event(
                frame,
                name="macd",
                timeframe="W",
                event_date=bar.trade_date,
            )
            values["symbol.macd.week.indicator_date"] = weekly_macd.indicator_date.isoformat()
            values["symbol.macd.week.dif"] = weekly_macd.value.line
            values["symbol.macd.week.dea"] = weekly_macd.value.signal
            values["symbol.macd.week.macd_bar"] = _macd_attribution_bar(
                weekly_macd.value.line,
                weekly_macd.value.signal,
            )
            categories["symbol.macd.week.energy_zone"] = _macd_energy_zone(
                weekly_macd.value.line,
                weekly_macd.value.signal,
            )
        except KeyError:
            pass

    resolved_ma_values = {
        period: _symbol_ma_value(bar.trade_date, frame, period=period, fallback=ma_values.get(period))
        for period in (20, 25, 60)
    }
    for period, value in resolved_ma_values.items():
        if value is not None:
            values[f"symbol.ma.ma{period}"] = value

    ma25_value = resolved_ma_values[25]
    if ma25_value is not None:
        checks["symbol.ma.price_above_ma25"] = bar.close > ma25_value

    ma60_value = resolved_ma_values[60]
    if ma60_value is not None:
        checks["symbol.ma.price_above_ma60"] = bar.close > ma60_value

    ma20_value = resolved_ma_values[20]
    if ma25_value is not None and ma60_value is not None and ma60_value > 0:
        categories["entry.signal_strength.ma25_above_ma60_spread_bucket"] = _ma_spread_bucket(
            (ma25_value - ma60_value) / ma60_value
        )

    if ma20_value is not None and ma60_value is not None:
        ma20_above_ma60 = ma20_value > ma60_value
        bullish_trend = bar.close > ma20_value > ma60_value
        checks["symbol.ma.ma20_above_ma60"] = ma20_above_ma60
        checks["symbol.ma.bullish_trend"] = bullish_trend
        categories["symbol.ma.trend_state"] = "bullish" if bullish_trend else "not_bullish"

    return EntryAttributionEvidence(checks=checks, values=values, categories=categories)


def _symbol_ma_value(
    trade_date: date,
    frame: IndicatorFrame | None,
    *,
    period: int,
    fallback: float | None,
) -> float | None:
    if frame is not None:
        try:
            return frame.ma_at(trade_date, period=period).value
        except KeyError:
            pass
    return fallback


def _ma_values_by_date(bars: Sequence[DailyBar], *, period: int) -> dict[date, float]:
    ordered_bars = tuple(sorted(bars, key=lambda value: value.trade_date))
    ma_values = calculate_sma([bar.close for bar in ordered_bars], period=period)
    return {
        bar.trade_date: ma.value
        for bar, ma in zip(ordered_bars, ma_values)
        if ma is not None
    }


def _objective_market_component_evidence_by_date(
    benchmark_bars_by_symbol: Mapping[str, Sequence[IndexBar]],
) -> dict[date, EntryAttributionEvidence]:
    if "000985.CSI" in benchmark_bars_by_symbol:
        selected_symbols = ("000985.CSI",)
    elif "000300.SH" in benchmark_bars_by_symbol and "000905.SH" in benchmark_bars_by_symbol:
        selected_symbols = ("000300.SH", "000905.SH")
    else:
        return {}

    component_values_by_symbol: dict[str, dict[str, dict[date, float]]] = {}
    for symbol in selected_symbols:
        ordered_bars = tuple(sorted(benchmark_bars_by_symbol.get(symbol, ()), key=lambda value: value.trade_date))
        if not ordered_bars:
            return {}
        component_values_by_symbol[symbol] = {
            "drawdown_250d": _drawdown_values_by_date(ordered_bars, period=250),
            "ma60_slope_20d": _ma_slope_values_by_date(ordered_bars, period=60, lookback=20),
        }

    candidate_dates = sorted(
        {
            trade_date
            for components in component_values_by_symbol.values()
            for values_by_date in components.values()
            for trade_date in values_by_date
        }
    )
    evidence_by_date: dict[date, EntryAttributionEvidence] = {}
    for trade_date in candidate_dates:
        drawdowns = [
            component_values_by_symbol[symbol]["drawdown_250d"].get(trade_date)
            for symbol in selected_symbols
        ]
        slopes = [
            component_values_by_symbol[symbol]["ma60_slope_20d"].get(trade_date)
            for symbol in selected_symbols
        ]
        if any(value is None for value in drawdowns) or any(value is None for value in slopes):
            continue
        drawdown = sum(value for value in drawdowns if value is not None) / len(drawdowns)
        slope = sum(value for value in slopes if value is not None) / len(slopes)
        drawdown_bucket = _index_drawdown_bucket(drawdown)
        slope_bucket = _ma60_slope_bucket(slope)
        categories: dict[str, str] = {}
        if drawdown_bucket is not None:
            categories["market.objective.entry_index_drawdown_250d_bucket"] = drawdown_bucket
        if slope_bucket is not None:
            categories["market.objective.entry_index_ma60_slope_20d_bucket"] = slope_bucket
        if categories:
            evidence_by_date[trade_date] = EntryAttributionEvidence(categories=categories)
    return evidence_by_date


def _market_trend_evidence_by_date(
    bars: Sequence[IndexBar],
    *,
    market_symbol: str,
    fast_period: int,
    slow_period: int,
    kdj_threshold: float,
) -> dict[date, EntryAttributionEvidence]:
    ordered_bars = tuple(sorted(bars, key=lambda value: value.trade_date))
    if not ordered_bars:
        return {}

    closes = [bar.close for bar in ordered_bars]
    fast_values = calculate_sma(closes, period=fast_period)
    slow_values = calculate_sma(closes, period=slow_period)
    return_vol_20d = _return_volatility_values_by_date(ordered_bars, period=20)
    return_vol_60d = _return_volatility_values_by_date(ordered_bars, period=60)
    weekly_kdj_by_date = _weekly_kdj_values_by_date(ordered_bars)
    weekly_ma_trend_by_date = _weekly_ma_trend_by_date(ordered_bars)
    kdj_values = calculate_kdj(
        [bar.high for bar in ordered_bars],
        [bar.low for bar in ordered_bars],
        closes,
    )
    prefix = f"market.{_market_key(market_symbol)}"
    evidence_by_date: dict[date, EntryAttributionEvidence] = {}

    for bar, fast_ma, slow_ma, kdj in zip(ordered_bars, fast_values, slow_values, kdj_values):
        values: dict[str, Any] = {f"{prefix}.close": bar.close}
        checks: dict[str, bool] = {}
        categories: dict[str, str] = {}

        if fast_ma is not None:
            values[f"{prefix}.ma{fast_period}"] = fast_ma.value
        if slow_ma is not None:
            values[f"{prefix}.ma{slow_period}"] = slow_ma.value
        if fast_ma is not None and slow_ma is not None:
            bullish = bar.close > fast_ma.value > slow_ma.value
            checks[f"{prefix}.bullish_trend"] = bullish
            categories[f"{prefix}.trend_state"] = "bullish" if bullish else "not_bullish"
        return_vol_20d_bucket = _volatility_pct_bucket(return_vol_20d.get(bar.trade_date))
        if return_vol_20d_bucket is not None:
            categories[f"{prefix}.return_vol_20d_bucket"] = return_vol_20d_bucket
        return_vol_60d_bucket = _volatility_pct_bucket(return_vol_60d.get(bar.trade_date))
        if return_vol_60d_bucket is not None:
            categories[f"{prefix}.return_vol_60d_bucket"] = return_vol_60d_bucket
        values[f"{prefix}.kdj.k"] = kdj.k
        values[f"{prefix}.kdj.d"] = kdj.d
        values[f"{prefix}.kdj.j"] = kdj.j
        values[f"{prefix}.kdj.threshold"] = kdj_threshold
        checks[f"{prefix}.kdj.j_below_threshold"] = kdj.j < kdj_threshold
        weekly_kdj = _latest_completed_weekly_kdj(weekly_kdj_by_date, event_date=bar.trade_date)
        if weekly_kdj is not None:
            _weekly_date, weekly_value = weekly_kdj
            categories[f"{prefix}.weekly.kdj_state"] = _kdj_state(weekly_value.j)
        weekly_ma_trend = _latest_string_before(weekly_ma_trend_by_date, bar.trade_date)
        if weekly_ma_trend is not None:
            categories[f"{prefix}.weekly.ma_trend_bucket"] = weekly_ma_trend

        evidence_by_date[bar.trade_date] = EntryAttributionEvidence(
            checks=checks,
            values=values,
            categories=categories,
        )

    return evidence_by_date


def _industry_kdj_evidence_by_symbol(
    industry_index_bars_by_symbol: Mapping[str, Sequence[IndexBar]],
    *,
    market_bars: Sequence[IndexBar],
    threshold: float,
) -> dict[str, dict[date, EntryAttributionEvidence]]:
    evidence_by_symbol: dict[str, dict[date, EntryAttributionEvidence]] = {}
    market_returns_20d = _return_values_by_date(market_bars, period=20)
    market_returns_60d = _return_values_by_date(market_bars, period=60)

    for industry_symbol, bars in industry_index_bars_by_symbol.items():
        ordered_bars = tuple(sorted(bars, key=lambda value: value.trade_date))
        if not ordered_bars:
            continue
        closes = [bar.close for bar in ordered_bars]
        kdj_values = calculate_kdj(
            [bar.high for bar in ordered_bars],
            [bar.low for bar in ordered_bars],
            closes,
        )
        macd_values = calculate_macd(closes)
        ma20_values = calculate_sma(closes, period=20)
        ma60_values = calculate_sma(closes, period=60)
        weekly_kdj_by_date = _weekly_kdj_values_by_date(ordered_bars)
        weekly_macd_by_date = _weekly_macd_values_by_date(ordered_bars)
        industry_returns_20d = _return_values_by_date(ordered_bars, period=20)
        industry_returns_60d = _return_values_by_date(ordered_bars, period=60)
        industry_return_vol_20d = _return_volatility_values_by_date(ordered_bars, period=20)
        industry_return_vol_60d = _return_volatility_values_by_date(ordered_bars, period=60)
        industry_atr_pct_20d = _atr_pct_values_by_date(ordered_bars, period=20)
        industry_near_high_60d = _near_high_values_by_date(ordered_bars, period=60)
        evidence_by_date: dict[date, EntryAttributionEvidence] = {}
        for bar, kdj, macd, ma20, ma60 in zip(ordered_bars, kdj_values, macd_values, ma20_values, ma60_values):
            values: dict[str, Any] = {
                "industry.kdj.k": kdj.k,
                "industry.kdj.d": kdj.d,
                "industry.kdj.j": kdj.j,
                "industry.macd.dif": macd.line,
                "industry.macd.dea": macd.signal,
                "industry.macd.macd_bar": _macd_attribution_bar(macd.line, macd.signal),
            }
            checks: dict[str, bool] = {"industry.kdj.j_below_threshold": kdj.j < threshold}
            categories: dict[str, str] = {
                "industry.sw_l1.code": industry_symbol,
                "industry.kdj.j_bucket": _kdj_j_bucket(kdj.j),
                "industry.kdj.state": _kdj_state(kdj.j),
                "industry.macd.energy_zone": _macd_energy_zone(macd.line, macd.signal),
            }
            weekly_kdj = _latest_completed_weekly_kdj(weekly_kdj_by_date, event_date=bar.trade_date)
            if weekly_kdj is not None:
                weekly_date, weekly_value = weekly_kdj
                values["industry.kdj.week.indicator_date"] = weekly_date.isoformat()
                values["industry.kdj.week.k"] = weekly_value.k
                values["industry.kdj.week.d"] = weekly_value.d
                values["industry.kdj.week.j"] = weekly_value.j
                categories["industry.kdj.week.j_bucket"] = _kdj_j_bucket(weekly_value.j)
                categories["industry.kdj.week.state"] = _kdj_state(weekly_value.j)
            weekly_macd = _latest_completed_weekly_macd(weekly_macd_by_date, event_date=bar.trade_date)
            if weekly_macd is not None:
                weekly_date, weekly_value = weekly_macd
                values["industry.macd.week.indicator_date"] = weekly_date.isoformat()
                values["industry.macd.week.dif"] = weekly_value.line
                values["industry.macd.week.dea"] = weekly_value.signal
                values["industry.macd.week.macd_bar"] = _macd_attribution_bar(
                    weekly_value.line,
                    weekly_value.signal,
                )
                categories["industry.macd.week.energy_zone"] = _macd_energy_zone(
                    weekly_value.line,
                    weekly_value.signal,
                )
            if ma20 is not None:
                values["industry.ma.ma20"] = ma20.value
                checks["industry.ma.price_above_ma20"] = bar.close > ma20.value
            if ma60 is not None:
                values["industry.ma.ma60"] = ma60.value
                checks["industry.ma.price_above_ma60"] = bar.close > ma60.value
            if ma20 is not None and ma60 is not None:
                checks["industry.ma.ma20_above_ma60"] = ma20.value > ma60.value
                bullish = bar.close > ma20.value > ma60.value
                checks["industry.ma.bullish_trend"] = bullish
                categories["industry.ma.trend_state"] = "bullish" if bullish else "not_bullish"

            industry_return_vol_20d_bucket = _volatility_pct_bucket(industry_return_vol_20d.get(bar.trade_date))
            if industry_return_vol_20d_bucket is not None:
                categories["industry.volatility.return_vol_20d_bucket"] = industry_return_vol_20d_bucket
            industry_return_vol_60d_bucket = _volatility_pct_bucket(industry_return_vol_60d.get(bar.trade_date))
            if industry_return_vol_60d_bucket is not None:
                categories["industry.volatility.return_vol_60d_bucket"] = industry_return_vol_60d_bucket
            industry_atr_pct_20d_bucket = _volatility_pct_bucket(industry_atr_pct_20d.get(bar.trade_date))
            if industry_atr_pct_20d_bucket is not None:
                categories["industry.volatility.atr_20d_bucket"] = industry_atr_pct_20d_bucket
            industry_near_high_60d_bucket = _near_high_bucket(industry_near_high_60d.get(bar.trade_date))
            if industry_near_high_60d_bucket is not None:
                categories["industry.price_position.near_high_60d_bucket"] = industry_near_high_60d_bucket

            industry_return_20d = industry_returns_20d.get(bar.trade_date)
            market_return_20d = _latest_number_on_or_before(market_returns_20d, bar.trade_date)
            if industry_return_20d is not None:
                values["industry.relative.hs300.return_20d"] = industry_return_20d
            if industry_return_20d is not None and market_return_20d is not None:
                excess_20d = industry_return_20d - market_return_20d
                values["industry.relative.hs300.excess_return_20d"] = excess_20d
                checks["industry.relative.hs300.outperform_20d"] = excess_20d > 0

            industry_return_60d = industry_returns_60d.get(bar.trade_date)
            market_return_60d = _latest_number_on_or_before(market_returns_60d, bar.trade_date)
            if industry_return_60d is not None:
                values["industry.relative.hs300.return_60d"] = industry_return_60d
            if industry_return_60d is not None and market_return_60d is not None:
                excess_60d = industry_return_60d - market_return_60d
                values["industry.relative.hs300.excess_return_60d"] = excess_60d
                checks["industry.relative.hs300.outperform_60d"] = excess_60d > 0
                categories["industry.relative.hs300.strength_state"] = _relative_strength_state(excess_60d)

            evidence_by_date[bar.trade_date] = EntryAttributionEvidence(
                checks=checks,
                values=values,
                categories=categories,
            )
        evidence_by_symbol[industry_symbol] = evidence_by_date

    return evidence_by_symbol


def _weekly_kdj_values_by_date(bars: Sequence[IndexBar]) -> dict[date, Any]:
    weekly_bars = resample_daily_bars(bars, frequency="W")
    if not weekly_bars:
        return {}
    kdj_values = calculate_kdj(
        [bar.high for bar in weekly_bars],
        [bar.low for bar in weekly_bars],
        [bar.close for bar in weekly_bars],
    )
    return {bar.trade_date: kdj for bar, kdj in zip(weekly_bars, kdj_values)}


def _weekly_macd_values_by_date(bars: Sequence[IndexBar]) -> dict[date, Any]:
    weekly_bars = resample_daily_bars(bars, frequency="W")
    if not weekly_bars:
        return {}
    macd_values = calculate_macd([bar.close for bar in weekly_bars])
    return {bar.trade_date: macd for bar, macd in zip(weekly_bars, macd_values)}


def _latest_completed_weekly_kdj(
    values_by_date: Mapping[date, Any],
    *,
    event_date: date,
) -> tuple[date, Any] | None:
    available_dates = [candidate_date for candidate_date in values_by_date if candidate_date < event_date]
    if not available_dates:
        return None
    indicator_date = max(available_dates)
    return indicator_date, values_by_date[indicator_date]


def _latest_completed_weekly_macd(
    values_by_date: Mapping[date, Any],
    *,
    event_date: date,
) -> tuple[date, Any] | None:
    available_dates = [candidate_date for candidate_date in values_by_date if candidate_date < event_date]
    if not available_dates:
        return None
    indicator_date = max(available_dates)
    return indicator_date, values_by_date[indicator_date]


def _return_volatility_values_by_date(bars: Sequence[Any], *, period: int) -> dict[date, float]:
    ordered_bars = tuple(sorted(bars, key=lambda value: value.trade_date))
    returns: list[float | None] = [None]
    for previous, current in zip(ordered_bars, ordered_bars[1:]):
        if previous.close <= 0:
            returns.append(None)
        else:
            returns.append(current.close / previous.close - 1.0)

    values_by_date: dict[date, float] = {}
    for index, bar in enumerate(ordered_bars):
        if index < period:
            continue
        window = returns[index - period + 1:index + 1]
        if len(window) != period or any(value is None for value in window):
            continue
        values_by_date[bar.trade_date] = _sample_std(tuple(value for value in window if value is not None))
    return values_by_date


def _cross_section_percentiles_by_symbol(
    values_by_symbol: Mapping[str, Mapping[date, float]],
) -> dict[str, dict[date, float]]:
    values_by_date: dict[date, list[tuple[str, float]]] = {}
    for symbol, symbol_values_by_date in values_by_symbol.items():
        for trade_date, value in symbol_values_by_date.items():
            if not math.isfinite(value):
                continue
            values_by_date.setdefault(trade_date, []).append((symbol, float(value)))

    percentiles_by_symbol: dict[str, dict[date, float]] = {}
    for trade_date, values in values_by_date.items():
        sorted_values = sorted(values, key=lambda item: (item[1], item[0]))
        count = len(sorted_values)
        index = 0
        while index < count:
            end = index + 1
            while end < count and sorted_values[end][1] == sorted_values[index][1]:
                end += 1
            average_rank = ((index + 1) + end) / 2.0
            percentile = average_rank / count
            for symbol, _value in sorted_values[index:end]:
                percentiles_by_symbol.setdefault(symbol, {})[trade_date] = percentile
            index = end
    return percentiles_by_symbol


def _atr_values_by_date(bars: Sequence[Any], *, period: int) -> dict[date, float]:
    ordered_bars = tuple(sorted(bars, key=lambda value: value.trade_date))
    true_ranges: list[float] = []
    for index, bar in enumerate(ordered_bars):
        candidates = [bar.high - bar.low]
        if index > 0:
            previous_close = ordered_bars[index - 1].close
            candidates.extend((abs(bar.high - previous_close), abs(bar.low - previous_close)))
        true_ranges.append(max(candidates))

    values_by_date: dict[date, float] = {}
    for index, bar in enumerate(ordered_bars):
        if index < period - 1:
            continue
        atr = sum(true_ranges[index - period + 1:index + 1]) / period
        values_by_date[bar.trade_date] = atr
    return values_by_date


def _atr_pct_values_by_date(bars: Sequence[Any], *, period: int) -> dict[date, float]:
    ordered_bars = tuple(sorted(bars, key=lambda value: value.trade_date))
    close_by_date = {bar.trade_date: bar.close for bar in ordered_bars}
    values_by_date: dict[date, float] = {}
    for trade_date, atr in _atr_values_by_date(ordered_bars, period=period).items():
        close = close_by_date.get(trade_date)
        if close is None or close <= 0:
            continue
        values_by_date[trade_date] = atr / close
    return values_by_date


def _near_high_values_by_date(bars: Sequence[Any], *, period: int) -> dict[date, float]:
    ordered_bars = tuple(sorted(bars, key=lambda value: value.trade_date))
    values_by_date: dict[date, float] = {}
    for index, bar in enumerate(ordered_bars):
        if index < period - 1:
            continue
        rolling_high = max(candidate.high for candidate in ordered_bars[index - period + 1:index + 1])
        if rolling_high <= 0:
            continue
        values_by_date[bar.trade_date] = bar.close / rolling_high - 1.0
    return values_by_date


def _new_high_values_by_date(bars: Sequence[Any], *, period: int) -> dict[date, bool]:
    ordered_bars = tuple(sorted(bars, key=lambda value: value.trade_date))
    values_by_date: dict[date, bool] = {}
    for index, bar in enumerate(ordered_bars):
        if index < period - 1:
            continue
        rolling_high = max(candidate.high for candidate in ordered_bars[index - period + 1:index + 1])
        values_by_date[bar.trade_date] = bar.close >= rolling_high
    return values_by_date


def _interval_values_by_date(bars: Sequence[Any], *, period: int) -> dict[date, float]:
    ordered_bars = tuple(sorted(bars, key=lambda value: value.trade_date))
    values_by_date: dict[date, float] = {}
    for index, bar in enumerate(ordered_bars):
        if index < period - 1:
            continue
        window = ordered_bars[index - period + 1:index + 1]
        rolling_high = max(candidate.high for candidate in window)
        rolling_low = min(candidate.low for candidate in window)
        interval = rolling_high - rolling_low
        if interval <= 0:
            continue
        values_by_date[bar.trade_date] = (bar.close - rolling_low) / interval
    return values_by_date


def _max_amplitude_values_by_date(bars: Sequence[Any], *, period: int) -> dict[date, float]:
    ordered_bars = tuple(sorted(bars, key=lambda value: value.trade_date))
    values_by_date: dict[date, float] = {}
    for index, bar in enumerate(ordered_bars):
        if index < period - 1:
            continue
        window = ordered_bars[index - period + 1:index + 1]
        rolling_high = max(candidate.high for candidate in window)
        rolling_low = min(candidate.low for candidate in window)
        if rolling_low <= 0:
            continue
        values_by_date[bar.trade_date] = rolling_high / rolling_low - 1.0
    return values_by_date


def _ma_slope_values_by_date(
    bars: Sequence[Any],
    *,
    period: int,
    lookback: int,
) -> dict[date, float]:
    ordered_bars = tuple(sorted(bars, key=lambda value: value.trade_date))
    ma_values = _ma_values_by_date(ordered_bars, period=period)
    values_by_date: dict[date, float] = {}
    for index, bar in enumerate(ordered_bars):
        if index < lookback:
            continue
        previous_date = ordered_bars[index - lookback].trade_date
        current_ma = ma_values.get(bar.trade_date)
        previous_ma = ma_values.get(previous_date)
        if current_ma is None or previous_ma is None or previous_ma <= 0:
            continue
        values_by_date[bar.trade_date] = current_ma / previous_ma - 1.0
    return values_by_date


def _drawdown_values_by_date(bars: Sequence[Any], *, period: int) -> dict[date, float]:
    ordered_bars = tuple(sorted(bars, key=lambda value: value.trade_date))
    values_by_date: dict[date, float] = {}
    for index, bar in enumerate(ordered_bars):
        if index < period - 1:
            continue
        rolling_high = max(candidate.high for candidate in ordered_bars[index - period + 1:index + 1])
        if rolling_high <= 0:
            continue
        values_by_date[bar.trade_date] = bar.close / rolling_high - 1.0
    return values_by_date


def _weekly_close_vs_ma20_by_date(bars: Sequence[DailyBar]) -> dict[date, float]:
    weekly_bars = resample_daily_bars(bars, frequency="W")
    if not weekly_bars:
        return {}
    ma20_values = calculate_sma([bar.close for bar in weekly_bars], period=20)
    return {
        bar.trade_date: bar.close / ma.value - 1.0
        for bar, ma in zip(weekly_bars, ma20_values)
        if ma is not None and ma.value > 0
    }


def _weekly_ma_trend_by_date(bars: Sequence[Any]) -> dict[date, str]:
    weekly_bars = resample_daily_bars(bars, frequency="W")
    if not weekly_bars:
        return {}
    closes = [bar.close for bar in weekly_bars]
    ma5_values = calculate_sma(closes, period=5)
    ma10_values = calculate_sma(closes, period=10)
    ma20_values = calculate_sma(closes, period=20)
    values_by_date: dict[date, str] = {}
    for bar, ma5, ma10, ma20 in zip(weekly_bars, ma5_values, ma10_values, ma20_values):
        if ma5 is None or ma10 is None or ma20 is None:
            continue
        values_by_date[bar.trade_date] = _weekly_ma_trend(
            close=bar.close,
            ma5=ma5.value,
            ma10=ma10.value,
            ma20=ma20.value,
        )
    return values_by_date


def _weekly_ma_trend(*, close: float, ma5: float, ma10: float, ma20: float) -> str:
    if close > ma20 and ma5 > ma10 > ma20:
        return "uptrend"
    if close < ma20 and ma5 < ma10 < ma20:
        return "downtrend"
    return "mixed"


def _median_float(values: Sequence[float]) -> float | None:
    present = sorted(value for value in values if math.isfinite(value))
    count = len(present)
    if count == 0:
        return None
    midpoint = count // 2
    if count % 2:
        return present[midpoint]
    return (present[midpoint - 1] + present[midpoint]) / 2.0


def _sample_std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def _candle_body_pct(bar: DailyBar) -> float | None:
    if bar.close <= 0:
        return None
    return abs(bar.open - bar.close) / bar.close


def _signal_shadow_bucket(bar: DailyBar) -> str | None:
    if bar.close <= 0:
        return None
    upper_shadow = max(0.0, bar.high - max(bar.open, bar.close)) / bar.close
    lower_shadow = max(0.0, min(bar.open, bar.close) - bar.low) / bar.close
    if upper_shadow < 0.01 and lower_shadow < 0.01:
        return "short_shadows"
    if upper_shadow >= lower_shadow * 2 and upper_shadow >= 0.01:
        return "long_upper_shadow"
    if lower_shadow >= upper_shadow * 2 and lower_shadow >= 0.01:
        return "long_lower_shadow"
    if upper_shadow >= 0.01 and lower_shadow >= 0.01:
        return "both_long_shadows"
    return "balanced_shadows"


def _dea_waterline_age_trading_days(frame: IndicatorFrame, trade_date: date) -> int | None:
    if frame.macd_by_key is None:
        return None
    current_macd = frame.macd_at(trade_date)
    if current_macd.signal <= 0:
        return None

    available_dates = sorted(
        key[-1]
        for key in frame.macd_by_key
        if key[0] == "D" and key[-1] <= trade_date
    )
    if trade_date not in available_dates:
        return None
    current_index = available_dates.index(trade_date)
    start_index = None
    for index in range(current_index, -1, -1):
        candidate_date = available_dates[index]
        if frame.macd_by_key[("D", candidate_date)].signal <= 0:
            if index + 1 <= current_index:
                start_index = index + 1
            break
    if start_index is None:
        return None
    return current_index - start_index


def _return_values_by_date(bars: Sequence[Any], *, period: int) -> dict[date, float]:
    ordered_bars = tuple(sorted(bars, key=lambda value: value.trade_date))
    returns: dict[date, float] = {}
    for index, bar in enumerate(ordered_bars):
        if index < period:
            continue
        base_close = ordered_bars[index - period].close
        if base_close <= 0:
            continue
        returns[bar.trade_date] = bar.close / base_close - 1.0
    return returns


def _latest_number_on_or_before(values_by_date: Mapping[date, float], trade_date: date) -> float | None:
    available_dates = [candidate_date for candidate_date in values_by_date if candidate_date <= trade_date]
    if not available_dates:
        return None
    return values_by_date[max(available_dates)]


def _latest_number_before(values_by_date: Mapping[date, float], trade_date: date) -> float | None:
    available_dates = [candidate_date for candidate_date in values_by_date if candidate_date < trade_date]
    if not available_dates:
        return None
    return values_by_date[max(available_dates)]


def _latest_string_before(values_by_date: Mapping[date, str], trade_date: date) -> str | None:
    available_dates = [candidate_date for candidate_date in values_by_date if candidate_date < trade_date]
    if not available_dates:
        return None
    return values_by_date[max(available_dates)]


def _kdj_j_bucket(value: float) -> str:
    if value < 13:
        return "<13"
    if value < 30:
        return "13-30"
    if value < 50:
        return "30-50"
    if value < 80:
        return "50-80"
    return ">=80"


def _kdj_state(value: float) -> str:
    if value < 13:
        return "oversold"
    if value < 50:
        return "recovering"
    if value < 80:
        return "strong"
    return "overheated"


def _macd_attribution_bar(dif: float, dea: float) -> float:
    return 2.0 * (dif - dea)


def _macd_energy_zone(dif: float, dea: float) -> str:
    macd_bar = _macd_attribution_bar(dif, dea)
    if macd_bar <= 0:
        return "green_bar_or_zero"
    dif_above_bar = dif > macd_bar
    dea_above_bar = dea > macd_bar
    if not dif_above_bar and not dea_above_bar and macd_bar > dif and macd_bar > dea:
        return "red_bar_wrapping_lines"
    if dif_above_bar and dea_above_bar:
        return "red_bar_two_line_escape"
    if dif_above_bar != dea_above_bar:
        return "red_bar_one_line_escape"
    return "red_bar_uncategorized"


def _relative_strength_state(excess_return: float) -> str:
    if excess_return >= 0.05:
        return "strong_outperform"
    if excess_return > 0:
        return "outperform"
    if excess_return <= -0.05:
        return "weak_underperform"
    return "underperform"


def _percentile_bucket(value: float | None) -> str | None:
    if value is None:
        return None
    if value <= 0.2:
        return "p0_p20"
    if value <= 0.4:
        return "p20_p40"
    if value <= 0.6:
        return "p40_p60"
    if value <= 0.8:
        return "p60_p80"
    return "p80_p100"


def _volatility_pct_bucket(value: float | None) -> str | None:
    if value is None or value < 0:
        return None
    if value < 0.01:
        return "lt_1pct"
    if value < 0.02:
        return "1_2pct"
    if value < 0.03:
        return "2_3pct"
    if value < 0.05:
        return "3_5pct"
    return "gte_5pct"


def _relative_ratio_bucket(value: float | None) -> str | None:
    if value is None or value < 0:
        return None
    if value < 0.8:
        return "lt_0p8x"
    if value < 1.2:
        return "0p8_1p2x"
    if value < 1.6:
        return "1p2_1p6x"
    if value < 2:
        return "1p6_2x"
    return "gte_2x"


def _near_high_bucket(value: float | None) -> str | None:
    if value is None:
        return None
    if value >= -0.01:
        return "at_high"
    if value >= -0.03:
        return "near_high"
    if value >= -0.08:
        return "moderate_pullback"
    if value >= -0.15:
        return "deep_pullback"
    return "far_from_high"


def _new_high_bucket(value: bool | None) -> str | None:
    if value is None:
        return None
    return "new_high" if value else "not_new_high"


def _interval_bucket(value: float | None) -> str | None:
    if value is None:
        return None
    if value <= 0.2:
        return "low_0_20"
    if value <= 0.4:
        return "low_mid_20_40"
    if value <= 0.6:
        return "mid_40_60"
    if value <= 0.8:
        return "high_mid_60_80"
    return "high_80_100"


def _atr_multiple_bucket(value: float | None) -> str | None:
    if value is None:
        return None
    if value < -2:
        return "below_ma60_gt_2atr"
    if value < -1:
        return "below_ma60_1_2atr"
    if value < 0:
        return "below_ma60_0_1atr"
    if value <= 1:
        return "above_ma60_0_1atr"
    if value <= 2:
        return "above_ma60_1_2atr"
    return "above_ma60_gt_2atr"


def _fixed_atr_multiple_bucket(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 1:
        return "lt_1atr"
    if value < 2:
        return "1_2atr"
    if value < 3:
        return "2_3atr"
    return "gte_3atr"


def _positive_strength_bucket(value: float | None) -> str | None:
    if value is None:
        return None
    if value <= 0:
        return "lte_0"
    if value < 0.001:
        return "0_0p1pct"
    if value < 0.003:
        return "0p1_0p3pct"
    if value < 0.006:
        return "0p3_0p6pct"
    return "gte_0p6pct"


def _signed_strength_bucket(value: float | None) -> str | None:
    return _positive_strength_bucket(value)


def _dea_waterline_age_bucket(value: int | None) -> str | None:
    if value is None:
        return None
    if value <= 0:
        return "day_0"
    if value <= 3:
        return "day_1_3"
    if value <= 7:
        return "day_4_7"
    if value <= 14:
        return "day_8_14"
    return "gt_14d"


def _ma_spread_bucket(value: float | None) -> str | None:
    if value is None:
        return None
    if value <= 0:
        return "ma25_lte_ma60"
    if value < 0.02:
        return "0_2pct"
    if value < 0.05:
        return "2_5pct"
    if value < 0.10:
        return "5_10pct"
    return "gte_10pct"


def _ma60_slope_bucket(value: float | None) -> str | None:
    if value is None:
        return None
    if value < -0.05:
        return "down_gt_5pct"
    if value < 0:
        return "down_0_5pct"
    if value < 0.02:
        return "flat_0_2pct"
    if value < 0.05:
        return "up_2_5pct"
    return "up_gt_5pct"


def _index_drawdown_bucket(value: float | None) -> str | None:
    if value is None:
        return None
    if value > -0.05:
        return "drawdown_0_5pct"
    if value > -0.15:
        return "drawdown_5_15pct"
    if value > -0.20:
        return "drawdown_15_20pct"
    return "drawdown_gt_20pct"


def _candle_body_bucket(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 0.01:
        return "lt_1pct"
    if value < 0.03:
        return "1_3pct"
    if value < 0.05:
        return "3_5pct"
    return "gte_5pct"


def _ma20_distance_bucket(value: float | None) -> str | None:
    if value is None:
        return None
    if value < -0.10:
        return "below_gt_10pct"
    if value < 0:
        return "below_0_10pct"
    if value < 0.05:
        return "above_0_5pct"
    if value < 0.15:
        return "above_5_15pct"
    return "above_gt_15pct"


def _industry_evidence_for_symbol_date(
    symbol: str,
    trade_date: date,
    *,
    memberships_by_symbol: Mapping[str, Sequence[StockIndustryMembership]],
    industry_evidence_by_symbol: Mapping[str, Mapping[date, EntryAttributionEvidence]],
) -> EntryAttributionEvidence | None:
    membership = _membership_on(symbol, trade_date, memberships_by_symbol=memberships_by_symbol)
    if membership is None:
        return None

    return _latest_evidence_on_or_before(
        industry_evidence_by_symbol.get(membership.level1_code, {}),
        trade_date,
    )


def _membership_on(
    symbol: str,
    trade_date: date,
    *,
    memberships_by_symbol: Mapping[str, Sequence[StockIndustryMembership]],
) -> StockIndustryMembership | None:
    memberships = tuple(memberships_by_symbol.get(symbol, ()))
    active_memberships = tuple(membership for membership in memberships if membership.active_on(trade_date))
    if active_memberships:
        return sorted(active_memberships, key=lambda value: (value.in_date, value.level1_code))[-1]
    future_memberships = tuple(membership for membership in memberships if trade_date < membership.in_date)
    if future_memberships:
        return sorted(future_memberships, key=lambda value: (value.in_date, value.level1_code))[0]
    return None


def _latest_evidence_on_or_before(
    evidence_by_date: Mapping[date, EntryAttributionEvidence],
    trade_date: date,
) -> EntryAttributionEvidence | None:
    available_dates = [candidate_date for candidate_date in evidence_by_date if candidate_date <= trade_date]
    if not available_dates:
        return None
    return evidence_by_date[max(available_dates)]


def _merge_evidence(*items: EntryAttributionEvidence | None) -> EntryAttributionEvidence:
    checks: dict[str, bool] = {}
    values: dict[str, Any] = {}
    categories: dict[str, str] = {}

    for item in items:
        if item is None:
            continue
        checks.update(item.checks)
        values.update(item.values)
        categories.update(item.categories)

    return EntryAttributionEvidence(checks=checks, values=values, categories=categories)


def _filter_evidence(
    evidence: EntryAttributionEvidence,
    enabled_factor_keys: frozenset[str],
) -> EntryAttributionEvidence:
    return EntryAttributionEvidence(
        checks={
            key: value
            for key, value in evidence.checks.items()
            if key in enabled_factor_keys
        },
        values={
            key: value
            for key, value in evidence.values.items()
            if key in enabled_factor_keys
        },
        categories={
            key: value
            for key, value in evidence.categories.items()
            if key in enabled_factor_keys
        },
    )


def _filter_attribution_payload(
    payload: object,
    enabled_factor_keys: frozenset[str],
) -> dict[str, dict[str, Any]]:
    attribution = _attribution_payload(payload)
    checks = attribution.get("checks")
    values = attribution.get("values")
    categories = attribution.get("categories")
    return entry_attribution_payload(
        checks={
            str(key): value
            for key, value in dict(checks or {}).items()
            if key in enabled_factor_keys
        } if isinstance(checks, Mapping) else {},
        values={
            str(key): value
            for key, value in dict(values or {}).items()
            if key in enabled_factor_keys
        } if isinstance(values, Mapping) else {},
        categories={
            str(key): value
            for key, value in dict(categories or {}).items()
            if key in enabled_factor_keys
        } if isinstance(categories, Mapping) else {},
    )


def _attribution_payload(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        attribution = value.get("attribution")
        if isinstance(attribution, Mapping):
            return attribution
        if {"checks", "values", "categories"} & set(value):
            return value
    return {}


def _merge_attribution_payloads(*payloads: object) -> dict[str, dict[str, Any]]:
    checks: dict[str, bool] = {}
    values: dict[str, Any] = {}
    categories: dict[str, str] = {}

    for payload in payloads:
        if not isinstance(payload, Mapping):
            continue
        raw_checks = payload.get("checks")
        if isinstance(raw_checks, Mapping):
            checks.update(
                {
                    str(key): value
                    for key, value in raw_checks.items()
                    if isinstance(value, bool)
                }
            )
        raw_values = payload.get("values")
        if isinstance(raw_values, Mapping):
            values.update(
                {
                    str(key): value
                    for key, value in raw_values.items()
                    if _is_scalar_json_value(value) and not isinstance(value, bool)
                }
            )
        raw_categories = payload.get("categories")
        if isinstance(raw_categories, Mapping):
            categories.update(
                {
                    str(key): str(value)
                    for key, value in raw_categories.items()
                    if value is not None
                }
            )

    return entry_attribution_payload(checks=checks, values=values, categories=categories)


def _market_key(symbol: str) -> str:
    if symbol == "000300.SH":
        return "hs300"
    if symbol == "000905.SH":
        return "csi500"
    return symbol.lower().replace(".", "_")


def _is_scalar_json_value(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))
