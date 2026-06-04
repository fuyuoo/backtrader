"""Entry attribution evidence helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from types import MappingProxyType
from typing import Any, Mapping

from attbacktrader.data import DailyBar, IndexBar, StockIndustryMembership
from attbacktrader.features import IndicatorFrame, IndicatorRequirement, calculate_kdj, calculate_sma
from attbacktrader.strategies.intents import TradeIntent, TradeIntentType


ENTRY_ATTRIBUTION_INDICATOR_REQUIREMENTS = (
    IndicatorRequirement("ma20", "D"),
    IndicatorRequirement("ma25", "D"),
    IndicatorRequirement("ma60", "D"),
)


@dataclass(frozen=True)
class EntryAttributionFactorDeclaration:
    key: str
    factor_type: str
    label_zh: str
    label_en: str
    scope: str
    dependencies: tuple[str, ...] = ()
    missing_behavior: str = "missing"

    def __post_init__(self) -> None:
        if self.factor_type not in {"check", "value", "category"}:
            raise ValueError("factor_type must be check, value, or category")
        if self.scope not in {"symbol", "industry", "market", "sizing"}:
            raise ValueError("scope must be symbol, industry, market, or sizing")
        if self.missing_behavior != "missing":
            raise ValueError("entry attribution missing behavior must be missing")


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
        key="sizing.risk_group",
        factor_type="category",
        label_zh="仓位风险组",
        label_en="Sizing risk group",
        scope="sizing",
    ),
)


def entry_attribution_factor_declarations() -> tuple[EntryAttributionFactorDeclaration, ...]:
    return STANDARD_ENTRY_ATTRIBUTION_FACTORS


def entry_attribution_declaration_by_key() -> dict[str, EntryAttributionFactorDeclaration]:
    return {declaration.key: declaration for declaration in STANDARD_ENTRY_ATTRIBUTION_FACTORS}


def entry_attribution_factor_keys() -> tuple[str, ...]:
    return tuple(declaration.key for declaration in STANDARD_ENTRY_ATTRIBUTION_FACTORS)


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
    )
    industry_evidence_by_symbol = _industry_kdj_evidence_by_symbol(
        industry_index_bars_by_symbol,
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
) -> EntryAttributionEvidence:
    values: dict[str, Any] = {"symbol.close": bar.close}
    checks: dict[str, bool] = {}
    categories: dict[str, str] = {}

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
) -> dict[date, EntryAttributionEvidence]:
    ordered_bars = tuple(sorted(bars, key=lambda value: value.trade_date))
    if not ordered_bars:
        return {}

    closes = [bar.close for bar in ordered_bars]
    fast_values = calculate_sma(closes, period=fast_period)
    slow_values = calculate_sma(closes, period=slow_period)
    prefix = f"market.{_market_key(market_symbol)}"
    evidence_by_date: dict[date, EntryAttributionEvidence] = {}

    for bar, fast_ma, slow_ma in zip(ordered_bars, fast_values, slow_values):
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

        evidence_by_date[bar.trade_date] = EntryAttributionEvidence(
            checks=checks,
            values=values,
            categories=categories,
        )

    return evidence_by_date


def _industry_kdj_evidence_by_symbol(
    industry_index_bars_by_symbol: Mapping[str, Sequence[IndexBar]],
    *,
    threshold: float,
) -> dict[str, dict[date, EntryAttributionEvidence]]:
    evidence_by_symbol: dict[str, dict[date, EntryAttributionEvidence]] = {}

    for industry_symbol, bars in industry_index_bars_by_symbol.items():
        ordered_bars = tuple(sorted(bars, key=lambda value: value.trade_date))
        if not ordered_bars:
            continue
        kdj_values = calculate_kdj(
            [bar.high for bar in ordered_bars],
            [bar.low for bar in ordered_bars],
            [bar.close for bar in ordered_bars],
        )
        evidence_by_symbol[industry_symbol] = {
            bar.trade_date: EntryAttributionEvidence(
                checks={"industry.kdj.j_below_threshold": kdj.j < threshold},
                values={
                    "industry.kdj.k": kdj.k,
                    "industry.kdj.d": kdj.d,
                    "industry.kdj.j": kdj.j,
                },
                categories={"industry.sw_l1.code": industry_symbol},
            )
            for bar, kdj in zip(ordered_bars, kdj_values)
        }

    return evidence_by_symbol


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
