"""Indicator update planning helpers."""

from __future__ import annotations

from dataclasses import dataclass

from attbacktrader.features.registry import (
    IndicatorRequirement,
    IndicatorSpec,
    indicator_names_for_timeframe,
    indicator_spec,
    normalize_indicator_requirements,
)


@dataclass(frozen=True)
class IndicatorUpdatePlan:
    symbol: str
    timeframe: str
    requirements: tuple[IndicatorRequirement, ...]
    specs: tuple[IndicatorSpec, ...]

    @property
    def indicator_names(self) -> tuple[str, ...]:
        return tuple(spec.name for spec in self.specs)

    @property
    def warmup_bars(self) -> int:
        return max((spec.warmup_bars for spec in self.specs), default=0)

    @property
    def recompute_lookback_bars(self) -> int:
        return max((spec.recompute_lookback_bars for spec in self.specs), default=0)

    @property
    def requires_state(self) -> bool:
        return any(spec.requires_state for spec in self.specs)

    @property
    def version_fingerprint(self) -> str:
        parts = [
            f"{spec.name}:{spec.version}:{dict(spec.params)}"
            for spec in self.specs
        ]
        return "|".join(parts)


def build_indicator_update_plans(
    *,
    symbol: str,
    indicator_requirements: tuple[IndicatorRequirement, ...],
) -> tuple[IndicatorUpdatePlan, ...]:
    requirements = normalize_indicator_requirements(indicator_requirements)
    plans: list[IndicatorUpdatePlan] = []

    for timeframe in ("D", "W", "M"):
        indicator_names = indicator_names_for_timeframe(requirements, timeframe=timeframe)
        if not indicator_names:
            continue

        timeframe_requirements = tuple(
            requirement
            for requirement in requirements
            if requirement.timeframe == timeframe
        )
        specs = tuple(indicator_spec(name) for name in indicator_names)
        plans.append(
            IndicatorUpdatePlan(
                symbol=symbol,
                timeframe=timeframe,
                requirements=timeframe_requirements,
                specs=specs,
            )
        )

    return tuple(plans)
