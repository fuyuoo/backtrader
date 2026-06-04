"""Code-backed strategy methods bound to strategy templates."""

from attbacktrader.features import IndicatorRequirement

from .add_on import KdjOversoldAddOn, NoAddOn
from .entry import (
    KdjOversoldEntry,
    MacdBullishCrossoverEntry,
    MovingAverageBullishTrendEntry,
    MovingAverageMacdBullishConfirmationEntry,
)
from .profit_taking import (
    KdjOverheatedExit,
    MacdBearishCrossoverExit,
    MovingAverageMacdWeakeningExit,
    RsiOverboughtExit,
)
from .stop_loss import AtrMultipleStop, FixedPercentStop


def required_indicator_requirements(*methods) -> frozenset[IndicatorRequirement]:
    requirements: set[IndicatorRequirement] = set()
    for method in methods:
        requirements.update(getattr(method, "required_indicators", ()))
    return frozenset(requirements)


def required_indicator_names(*methods) -> frozenset[str]:
    return frozenset(requirement.name for requirement in required_indicator_requirements(*methods))


__all__ = [
    "AtrMultipleStop",
    "FixedPercentStop",
    "KdjOversoldAddOn",
    "KdjOverheatedExit",
    "KdjOversoldEntry",
    "MacdBearishCrossoverExit",
    "MacdBullishCrossoverEntry",
    "MovingAverageBullishTrendEntry",
    "MovingAverageMacdBullishConfirmationEntry",
    "MovingAverageMacdWeakeningExit",
    "NoAddOn",
    "RsiOverboughtExit",
    "required_indicator_requirements",
    "required_indicator_names",
]
