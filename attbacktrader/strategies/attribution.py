"""Entry attribution evidence helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from types import MappingProxyType
from typing import Any, Mapping

from attbacktrader.data import DailyBar, IndexBar, StockIndustryMembership, resample_daily_bars
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
class EntryAttributionFilterRule:
    enabled: bool = False
    required_checks: tuple[str, ...] = ()
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

    def is_active(self) -> bool:
        return self.enabled and bool(self.required_checks)


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
        key="sizing.risk_group",
        factor_type="category",
        label_zh="仓位风险组",
        label_en="Sizing risk group",
        scope="sizing",
    ),
)

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

    blocked = bool(failed_checks) or (bool(missing_checks) and rule.missing_policy == "block")
    signal_values = dict(intent.signal_values)
    signal_values["entry_attribution_filter"] = {
        "enabled": True,
        "required_checks": list(rule.required_checks),
        "passed": not blocked,
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
        "missing_checks": missing_checks,
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
    market_evidence_by_date = _market_trend_evidence_by_date(
        benchmark_bars_by_symbol.get(market_symbol, ()),
        market_symbol=market_symbol,
        fast_period=market_fast_period,
        slow_period=market_slow_period,
        kdj_threshold=market_kdj_threshold,
    )
    industry_evidence_by_symbol = _industry_kdj_evidence_by_symbol(
        industry_index_bars_by_symbol,
        market_bars=benchmark_bars_by_symbol.get(market_symbol, ()),
        threshold=industry_kdj_threshold,
    )

    evidence_by_key: dict[tuple[str, date], EntryAttributionEvidence] = {}
    for symbol, bars in sorted(bars_by_symbol.items()):
        ordered_bars = tuple(sorted(bars, key=lambda value: value.trade_date))
        frame = indicators_by_symbol.get(symbol)
        ma_values_by_period = {
            period: _ma_values_by_date(ordered_bars, period=period)
            for period in (20, 25, 60)
        }
        for bar in ordered_bars:
            evidence = _merge_evidence(
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
            categories["symbol.kdj.week.j_bucket"] = _kdj_j_bucket(weekly_kdj.value.j)
            categories["symbol.kdj.week.state"] = _kdj_state(weekly_kdj.value.j)
        except KeyError:
            pass
        try:
            macd = frame.macd_at(bar.trade_date)
            values["symbol.macd.dif"] = macd.line
            values["symbol.macd.dea"] = macd.signal
            values["symbol.macd.macd_bar"] = _macd_attribution_bar(macd.line, macd.signal)
            categories["symbol.macd.energy_zone"] = _macd_energy_zone(macd.line, macd.signal)
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
        values[f"{prefix}.kdj.k"] = kdj.k
        values[f"{prefix}.kdj.d"] = kdj.d
        values[f"{prefix}.kdj.j"] = kdj.j
        values[f"{prefix}.kdj.threshold"] = kdj_threshold
        checks[f"{prefix}.kdj.j_below_threshold"] = kdj.j < kdj_threshold

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


def _return_values_by_date(bars: Sequence[IndexBar], *, period: int) -> dict[date, float]:
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
    return symbol.lower().replace(".", "_")


def _is_scalar_json_value(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))
