"""Pydantic models for validated backtest run plans."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt, field_validator, model_validator

from attbacktrader.data.adjustments import DEFAULT_PRICE_ADJUSTMENT
from attbacktrader.strategies.bindings import allowed_strategy_component_values, strategy_component_binding_fields


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
    decision_series: SeriesSelection = Field(default_factory=SeriesSelection)
    benchmark_series: SeriesSelection = Field(default_factory=SeriesSelection)
    industry_series: IndustrySeriesConfig = Field(default_factory=IndustrySeriesConfig)

    @model_validator(mode="after")
    def validate_tradable_scope(self) -> "DataConfig":
        if not self.symbols and not self.tradable_series:
            raise ValueError("data.symbols or data.tradable_series must contain at least one tradable series")

        symbols = [series.symbol for series in self.tradable_series] if self.tradable_series else list(self.symbols)
        duplicates = sorted({symbol for symbol in symbols if symbols.count(symbol) > 1})
        if duplicates:
            raise ValueError(f"duplicate tradable symbols: {duplicates}")

        return self

    @property
    def resolved_tradable_series(self) -> tuple[TradableSeriesConfig, ...]:
        if self.tradable_series:
            return self.tradable_series

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
    sizing_rule: str = Field(min_length=1)

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
        return self


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


class ExecutionConfig(FrozenModel):
    engine: Literal["business", "backtrader"] = "business"
    stake: PositiveInt = 100


class OutputConfig(FrozenModel):
    persist: bool = True
    report_root: Path = Path("reports")


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


class AnalysisConfig(FrozenModel):
    industry_attribution: IndustryAttributionConfig = Field(default_factory=IndustryAttributionConfig)
    market_regime: MarketRegimeConfig = Field(default_factory=MarketRegimeConfig)
    scenario_fit: ScenarioFitConfig = Field(default_factory=ScenarioFitConfig)


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
