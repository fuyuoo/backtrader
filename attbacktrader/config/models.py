"""Pydantic models for validated backtest run plans."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt, field_validator, model_validator

from attbacktrader.data.adjustments import DEFAULT_PRICE_ADJUSTMENT
from attbacktrader.data.stock_pool import read_fixed_stock_pool_csv
from attbacktrader.strategies.bindings import (
    allowed_strategy_component_values,
    strategy_component_binding_fields,
    validate_strategy_component_params,
)
from attbacktrader.strategies.attribution import (
    attribution_declaration_by_key,
    entry_attribution_declaration_by_key,
    entry_attribution_factor_keys,
    resolve_attribution_factor_selection,
)


class FrozenModel(BaseModel):
    """Base model for immutable, strict run-plan configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class RunConfig(FrozenModel):
    id: str = Field(min_length=1)
    from_date: date
    to_date: date

    @model_validator(mode="after")
    def validate_date_range(self) -> "RunConfig":
        if self.to_date < self.from_date:
            raise ValueError("run.to_date must be on or after run.from_date")
        return self


class SeriesSelection(FrozenModel):
    indexes: tuple[str, ...] = ()


class TradableSeriesConfig(FrozenModel):
    symbol: str = Field(min_length=1)
    asset_type: Literal["stock", "index", "industry_index"] = "stock"
    provider: Literal["tushare"] = "tushare"
    price_adjustment: Literal["none", "qfq", "hfq"] | None = None

    @model_validator(mode="after")
    def default_price_adjustment(self) -> "TradableSeriesConfig":
        if self.price_adjustment is None:
            adjustment = DEFAULT_PRICE_ADJUSTMENT if self.asset_type == "stock" else "none"
            object.__setattr__(self, "price_adjustment", adjustment)
        return self


class IndustrySeriesConfig(FrozenModel):
    source: Literal["SW2021"] = "SW2021"
    indexes: tuple[str, ...] = ()


class DataConfig(FrozenModel):
    snapshot_root: Path
    provider: Literal["tushare"] = "tushare"
    price_adjustment: Literal["qfq", "hfq"] = DEFAULT_PRICE_ADJUSTMENT
    refresh_snapshots: bool = True
    symbols: tuple[str, ...] = ()
    tradable_series: tuple[TradableSeriesConfig, ...] = ()
    stock_pool_file: Path | None = None
    decision_series: SeriesSelection = Field(default_factory=SeriesSelection)
    benchmark_series: SeriesSelection = Field(default_factory=SeriesSelection)
    industry_series: IndustrySeriesConfig = Field(default_factory=IndustrySeriesConfig)

    @model_validator(mode="after")
    def validate_tradable_scope(self) -> "DataConfig":
        sources = [
            name
            for name, has_value in (
                ("data.symbols", bool(self.symbols)),
                ("data.tradable_series", bool(self.tradable_series)),
                ("data.stock_pool_file", self.stock_pool_file is not None),
            )
            if has_value
        ]
        if not sources:
            raise ValueError(
                "data.symbols, data.tradable_series, or data.stock_pool_file must contain at least one tradable series"
            )
        if len(sources) > 1:
            raise ValueError(f"tradable scope must use exactly one source, got: {sources}")

        symbols = [series.symbol for series in self.tradable_series] if self.tradable_series else list(self.symbols)
        duplicates = sorted({symbol for symbol in symbols if symbols.count(symbol) > 1})
        if duplicates:
            raise ValueError(f"duplicate tradable symbols: {duplicates}")

        return self

    @property
    def resolved_tradable_series(self) -> tuple[TradableSeriesConfig, ...]:
        if self.tradable_series:
            return self.tradable_series

        if self.stock_pool_file is not None:
            return tuple(
                TradableSeriesConfig(
                    symbol=member.symbol,
                    asset_type="stock",
                    provider=self.provider,
                    price_adjustment=self.price_adjustment,
                )
                for member in read_fixed_stock_pool_csv(self.stock_pool_file)
            )

        return tuple(
            TradableSeriesConfig(
                symbol=symbol,
                asset_type="stock",
                provider=self.provider,
                price_adjustment=self.price_adjustment,
            )
            for symbol in self.symbols
        )


class StrategyConfig(FrozenModel):
    template: Literal["trend_template_v1"]
    entry_method: str = Field(min_length=1)
    profit_taking_method: str = Field(min_length=1)
    stop_loss_method: str = Field(min_length=1)
    add_on_method: str = "none"
    sizing_rule: str = Field(min_length=1)
    entry_params: dict[str, Any] = Field(default_factory=dict)
    profit_taking_params: dict[str, Any] = Field(default_factory=dict)
    stop_loss_params: dict[str, Any] = Field(default_factory=dict)
    add_on_params: dict[str, Any] = Field(default_factory=dict)
    sizing_params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_component_bindings(self) -> "StrategyConfig":
        for field_name in strategy_component_binding_fields(self.template):
            allowed_values = allowed_strategy_component_values(self.template, field_name)
            value = getattr(self, field_name)
            if value not in allowed_values:
                allowed = ", ".join(sorted(allowed_values))
                raise ValueError(
                    f"strategy.{field_name}={value!r} is not bound to "
                    f"template {self.template!r}; allowed values: {allowed}"
                )
            validate_strategy_component_params(
                self.template,
                field_name,
                value,
                getattr(self, _strategy_params_field_name(field_name), {}),
            )
        return self


def _strategy_params_field_name(field_name: str) -> str:
    return {
        "entry_method": "entry_params",
        "profit_taking_method": "profit_taking_params",
        "stop_loss_method": "stop_loss_params",
        "add_on_method": "add_on_params",
        "sizing_rule": "sizing_params",
    }.get(field_name, f"{field_name}_params")


class AShareConstraintConfig(FrozenModel):
    enabled: bool = True
    t_plus_one: bool = True
    limit_up_down: bool = True
    suspension: bool = True
    board_lot_size: PositiveInt = 100


class ConstraintsConfig(FrozenModel):
    ashare: AShareConstraintConfig = Field(default_factory=AShareConstraintConfig)


class SlippageConfig(FrozenModel):
    type: Literal["percent", "fixed"]
    value: float = Field(ge=0)


class BrokerConfig(FrozenModel):
    initial_cash: PositiveFloat
    commission_rate: float = Field(ge=0)
    stamp_tax_rate: float = Field(ge=0)
    transfer_fee_rate: float = Field(ge=0)
    slippage: SlippageConfig


class SecondScaleOutConfirmationConfig(FrozenModel):
    enabled: bool = False
    mode: Literal["boll_up_distance", "kdj_cci", "kdj_cci_boll_up_distance"] = "boll_up_distance"
    min_boll_up_distance: float | None = None
    min_kdj_j: float | None = None
    min_cci14: float | None = None

    @model_validator(mode="after")
    def validate_required_thresholds(self) -> "SecondScaleOutConfirmationConfig":
        if not self.enabled:
            return self

        if self.mode in {"boll_up_distance", "kdj_cci_boll_up_distance"} and self.min_boll_up_distance is None:
            raise ValueError(
                "execution.baoma.second_scale_out_confirmation.min_boll_up_distance is required "
                f"when mode={self.mode!r}"
            )
        if self.mode in {"kdj_cci", "kdj_cci_boll_up_distance"} and self.min_kdj_j is None:
            raise ValueError(
                "execution.baoma.second_scale_out_confirmation.min_kdj_j is required "
                f"when mode={self.mode!r}"
            )
        if self.mode in {"kdj_cci", "kdj_cci_boll_up_distance"} and self.min_cci14 is None:
            raise ValueError(
                "execution.baoma.second_scale_out_confirmation.min_cci14 is required "
                f"when mode={self.mode!r}"
            )
        return self


class BaomaExecutionConfig(FrozenModel):
    buy_slice_fraction: float = Field(default=0.33, gt=0, le=1)
    scale_out_mode: Literal["fixed_percent", "atr_multiple"] = "fixed_percent"
    first_scale_out_return: float = Field(default=0.05, gt=0)
    second_scale_out_return: float = Field(default=0.15, gt=0)
    first_scale_out_atr_multiple: float | None = Field(default=None, gt=0)
    second_scale_out_atr_multiple: float | None = Field(default=None, gt=0)
    second_scale_out_confirmation: SecondScaleOutConfirmationConfig = Field(
        default_factory=SecondScaleOutConfirmationConfig
    )
    force_exit_at_end: bool = False

    @model_validator(mode="after")
    def validate_scale_out_thresholds(self) -> "BaomaExecutionConfig":
        if self.scale_out_mode == "fixed_percent":
            if self.second_scale_out_confirmation.enabled:
                raise ValueError(
                    "execution.baoma.second_scale_out_confirmation is only supported "
                    "when scale_out_mode='atr_multiple'"
                )
            if self.second_scale_out_return <= self.first_scale_out_return:
                raise ValueError("execution.baoma.second_scale_out_return must be greater than first_scale_out_return")
            return self

        if self.first_scale_out_atr_multiple is None or self.second_scale_out_atr_multiple is None:
            raise ValueError(
                "execution.baoma first_scale_out_atr_multiple and second_scale_out_atr_multiple are required "
                "when scale_out_mode='atr_multiple'"
            )
        if self.second_scale_out_atr_multiple <= self.first_scale_out_atr_multiple:
            raise ValueError(
                "execution.baoma.second_scale_out_atr_multiple must be greater than first_scale_out_atr_multiple"
            )
        return self


class ExecutionConfig(FrozenModel):
    engine: Literal["business", "backtrader", "baoma_v1_business"] = "business"
    stake: PositiveInt = 100
    baoma: BaomaExecutionConfig = Field(default_factory=BaomaExecutionConfig)


class OutputConfig(FrozenModel):
    persist: bool = True
    report_root: Path = Path("reports")
    artifact_detail: Literal["compact", "full"] = "compact"
    signal_audit_sample_limit: int = Field(default=200, ge=0)


class IndustryAttributionConfig(FrozenModel):
    enabled: bool = True
    source: Literal["SW2021"] = "SW2021"
    levels: tuple[int, ...] = (1, 2, 3)

    @field_validator("levels")
    @classmethod
    def validate_levels(cls, levels: tuple[int, ...]) -> tuple[int, ...]:
        if not levels:
            raise ValueError("analysis.industry_attribution.levels cannot be empty")

        allowed = {1, 2, 3}
        invalid = sorted(set(levels) - allowed)
        if invalid:
            raise ValueError(f"unsupported Shenwan industry levels: {invalid}")

        if len(set(levels)) != len(levels):
            raise ValueError("analysis.industry_attribution.levels cannot contain duplicates")

        return levels


class MarketRegimeConfig(FrozenModel):
    enabled: bool = True
    timeframes: tuple[Literal["D", "W", "M"], ...] = ("D", "W", "M")

    @field_validator("timeframes")
    @classmethod
    def validate_timeframes(cls, timeframes: tuple[str, ...]) -> tuple[str, ...]:
        if not timeframes:
            raise ValueError("analysis.market_regime.timeframes cannot be empty")

        if len(set(timeframes)) != len(timeframes):
            raise ValueError("analysis.market_regime.timeframes cannot contain duplicates")

        return timeframes


class ScenarioFitConfig(FrozenModel):
    enabled: bool = True
    min_trades: PositiveInt = 3


class EntryAttributionFilterConditionConfig(FrozenModel):
    field: str = Field(min_length=1)
    value: Any
    action: Literal["keep", "exclude"]
    operator: Literal["eq", "gt", "gte", "lt", "lte"] = "eq"

    @field_validator("field")
    @classmethod
    def validate_field(cls, field_name: str) -> str:
        normalized = field_name.strip()
        if not normalized:
            raise ValueError("analysis.entry_attribution.entry_filter.conditions.field cannot be empty")
        if _entry_filter_condition_uses_future_field(normalized):
            raise ValueError(f"entry attribution filter condition cannot use future field: {normalized}")
        if not _entry_filter_condition_has_allowed_namespace(normalized):
            raise ValueError(f"unknown entry attribution filter condition field: {normalized}")
        return normalized

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: Any) -> Any:
        if value is None or not isinstance(value, (str, int, float, bool)):
            raise ValueError("analysis.entry_attribution.entry_filter.conditions.value must be a scalar value")
        return value


class EntryAttributionFilterConfig(FrozenModel):
    enabled: bool = False
    require_checks: tuple[str, ...] = ()
    conditions: tuple[EntryAttributionFilterConditionConfig, ...] = ()
    missing_policy: Literal["block", "pass"] = "block"
    reason_code: str = "ENTRY_ATTRIBUTION_FILTERED"
    blocked_by: str = "ENTRY_ATTRIBUTION_FILTER"

    @field_validator("require_checks")
    @classmethod
    def validate_require_checks(cls, require_checks: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(require_checks)) != len(require_checks):
            raise ValueError("analysis.entry_attribution.entry_filter.require_checks cannot contain duplicates")

        declarations = entry_attribution_declaration_by_key()
        invalid = sorted(key for key in require_checks if key not in declarations)
        if invalid:
            raise ValueError(f"unknown entry attribution filter checks: {invalid}")

        non_checks = sorted(
            key
            for key in require_checks
            if declarations[key].factor_type != "check"
        )
        if non_checks:
            raise ValueError(f"entry attribution filter can only require check factors: {non_checks}")

        return require_checks

    @field_validator("conditions")
    @classmethod
    def validate_conditions(
        cls,
        conditions: tuple[EntryAttributionFilterConditionConfig, ...],
    ) -> tuple[EntryAttributionFilterConditionConfig, ...]:
        condition_keys = tuple(
            (condition.field, condition.operator, condition.value, condition.action)
            for condition in conditions
        )
        if len(set(condition_keys)) != len(condition_keys):
            raise ValueError("analysis.entry_attribution.entry_filter.conditions cannot contain duplicates")
        return conditions


class EntryAttributionConfig(FrozenModel):
    enabled: bool = True
    factors: tuple[str, ...] = ()
    market_symbol: str = "000300.SH"
    market_fast_period: PositiveInt = 20
    market_slow_period: PositiveInt = 60
    industry_kdj_threshold: float = 13.0
    entry_filter: EntryAttributionFilterConfig = Field(default_factory=EntryAttributionFilterConfig)

    @field_validator("factors")
    @classmethod
    def validate_factors(cls, factors: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(factors)) != len(factors):
            raise ValueError("analysis.entry_attribution.factors cannot contain duplicates")

        declarations = entry_attribution_declaration_by_key()
        invalid = sorted(key for key in factors if key not in declarations)
        if invalid:
            raise ValueError(f"unknown entry attribution factors: {invalid}")

        return factors

    @model_validator(mode="after")
    def validate_entry_attribution(self) -> "EntryAttributionConfig":
        if self.market_fast_period >= self.market_slow_period:
            raise ValueError("analysis.entry_attribution.market_fast_period must be less than market_slow_period")

        if self.entry_filter.enabled and not (self.entry_filter.require_checks or self.entry_filter.conditions):
            raise ValueError(
                "analysis.entry_attribution.entry_filter.require_checks or conditions cannot be empty when enabled"
            )

        if self.factors:
            missing_filter_factors = sorted(set(self.entry_filter.require_checks) - set(self.factors))
            if missing_filter_factors:
                raise ValueError(
                    "analysis.entry_attribution.entry_filter.require_checks must be included in "
                    f"analysis.entry_attribution.factors: {missing_filter_factors}"
                )
            missing_filter_condition_fields = sorted(
                set(_declared_entry_filter_condition_fields(self.entry_filter.conditions)) - set(self.factors)
            )
            if missing_filter_condition_fields:
                raise ValueError(
                    "analysis.entry_attribution.entry_filter.conditions must be included in "
                    f"analysis.entry_attribution.factors: {missing_filter_condition_fields}"
                )

        return self

    @property
    def resolved_factors(self) -> tuple[str, ...]:
        if self.factors:
            return self.factors
        return tuple(entry_attribution_declaration_by_key())


def _entry_filter_condition_uses_future_field(field_name: str) -> bool:
    normalized = field_name.lower()
    future_prefixes = (
        "trade.",
        "exit.",
        "post_exit.",
        "entry_to_exit.",
        "sizing.",
        "execution.",
        "portfolio.",
    )
    future_tokens = (
        "entry_to_exit",
        "post_exit",
        "sold_too_early",
        "stop_loss_rebound",
    )
    if normalized.startswith(future_prefixes):
        return True
    return any(token in normalized for token in future_tokens)


def _entry_filter_condition_has_allowed_namespace(field_name: str) -> bool:
    declarations = entry_attribution_declaration_by_key()
    declaration = declarations.get(field_name)
    if declaration is not None:
        return "entry" in declaration.timings and declaration.scope in {"symbol", "industry", "market", "execution"}
    return field_name.startswith(("entry.", "symbol.", "industry.", "market."))


def _declared_entry_filter_condition_fields(
    conditions: tuple[EntryAttributionFilterConditionConfig, ...],
) -> tuple[str, ...]:
    declarations = entry_attribution_declaration_by_key()
    return tuple(condition.field for condition in conditions if condition.field in declarations)


class AttributionConfig(FrozenModel):
    enabled: bool = True
    include: tuple[str, ...] = ()

    @field_validator("include")
    @classmethod
    def validate_include(cls, include: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(include)) != len(include):
            raise ValueError("analysis.attribution.include cannot contain duplicates")

        declarations = attribution_declaration_by_key()
        invalid = sorted(key for key in include if key not in declarations)
        if invalid:
            raise ValueError(f"unknown attribution include factors: {invalid}")

        return include


class PostExitAnalysisConfig(FrozenModel):
    enabled: bool = True
    window_days: tuple[PositiveInt, ...] = (5,)
    primary_window_days: PositiveInt = 5
    sold_too_early_threshold: float = Field(default=0.0, ge=0)
    rebound_thresholds: tuple[float, ...] = (0.0, 0.02, 0.05, 0.10)

    @field_validator("window_days")
    @classmethod
    def validate_window_days(cls, window_days: tuple[int, ...]) -> tuple[int, ...]:
        if not window_days:
            raise ValueError("analysis.post_exit.window_days cannot be empty")

        if len(set(window_days)) != len(window_days):
            raise ValueError("analysis.post_exit.window_days cannot contain duplicates")

        return tuple(sorted(window_days))

    @field_validator("rebound_thresholds")
    @classmethod
    def validate_rebound_thresholds(cls, rebound_thresholds: tuple[float, ...]) -> tuple[float, ...]:
        if not rebound_thresholds:
            raise ValueError("analysis.post_exit.rebound_thresholds cannot be empty")

        if any(threshold < 0 for threshold in rebound_thresholds):
            raise ValueError("analysis.post_exit.rebound_thresholds must be non-negative")

        if len(set(rebound_thresholds)) != len(rebound_thresholds):
            raise ValueError("analysis.post_exit.rebound_thresholds cannot contain duplicates")

        return tuple(sorted(rebound_thresholds))

    @model_validator(mode="after")
    def validate_primary_window(self) -> "PostExitAnalysisConfig":
        if self.primary_window_days not in self.window_days:
            raise ValueError("analysis.post_exit.primary_window_days must be included in window_days")
        return self


class AnalysisConfig(FrozenModel):
    attribution: AttributionConfig = Field(default_factory=AttributionConfig)
    industry_attribution: IndustryAttributionConfig = Field(default_factory=IndustryAttributionConfig)
    market_regime: MarketRegimeConfig = Field(default_factory=MarketRegimeConfig)
    scenario_fit: ScenarioFitConfig = Field(default_factory=ScenarioFitConfig)
    entry_attribution: EntryAttributionConfig = Field(default_factory=EntryAttributionConfig)
    post_exit: PostExitAnalysisConfig = Field(default_factory=PostExitAnalysisConfig)

    @model_validator(mode="after")
    def validate_attribution_selection(self) -> "AnalysisConfig":
        if self.entry_attribution.entry_filter.enabled:
            missing_filter_factors = sorted(
                set(self.entry_attribution.entry_filter.require_checks) - set(self.resolved_entry_attribution_factors)
            )
            if missing_filter_factors:
                raise ValueError(
                    "analysis.entry_attribution.entry_filter.require_checks must be included in resolved "
                    f"attribution factors: {missing_filter_factors}"
                )
            missing_filter_condition_fields = sorted(
                set(_declared_entry_filter_condition_fields(self.entry_attribution.entry_filter.conditions))
                - set(self.resolved_entry_attribution_factors)
            )
            if missing_filter_condition_fields:
                raise ValueError(
                    "analysis.entry_attribution.entry_filter.conditions must be included in resolved "
                    f"attribution factors: {missing_filter_condition_fields}"
                )
        return self

    @property
    def resolved_attribution_factor_selection(self) -> dict[str, Any]:
        applicable = tuple(attribution_declaration_by_key())
        if not self.attribution.enabled:
            include = ()
            configured_source = "analysis.attribution.enabled=false"
        elif self.attribution.include:
            include = self.attribution.include
            configured_source = "analysis.attribution.include"
        elif self.entry_attribution.factors:
            include = self.entry_attribution.factors
            configured_source = "analysis.entry_attribution.factors"
        else:
            include = applicable
            configured_source = "default:all_applicable"

        selection = resolve_attribution_factor_selection(
            include,
            applicable_factor_keys=applicable,
            configured_source=configured_source,
        )
        selection["enabled"] = self.attribution.enabled
        entry_keys = set(entry_attribution_factor_keys())
        selection["entry_attribution"] = {
            "enabled": self.entry_attribution.enabled,
            "runtime_include": (
                tuple(key for key in include if key in entry_keys)
                if self.entry_attribution.enabled
                else ()
            ),
        }
        return selection

    @property
    def resolved_entry_attribution_factors(self) -> tuple[str, ...]:
        if not self.entry_attribution.enabled:
            return ()
        selection = self.resolved_attribution_factor_selection
        entry_keys = set(entry_attribution_factor_keys())
        return tuple(key for key in selection["include"] if key in entry_keys)


class RunPlan(FrozenModel):
    run: RunConfig
    data: DataConfig
    strategy: StrategyConfig
    constraints: ConstraintsConfig = Field(default_factory=ConstraintsConfig)
    broker: BrokerConfig
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)

    @classmethod
    def from_mapping(cls, raw_config: dict[str, Any]) -> "RunPlan":
        return cls.model_validate(raw_config)
