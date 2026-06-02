"""Indicator calculations used by strategy methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class KDJValue:
    k: float
    d: float
    j: float


def calculate_kdj(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    period: int = 9,
    initial_k: float = 50.0,
    initial_d: float = 50.0,
) -> tuple[KDJValue, ...]:
    """Calculate KDJ values using the common RSV smoothing formula."""

    if period <= 0:
        raise ValueError("period must be positive")

    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("highs, lows, and closes must have the same length")

    k_value = initial_k
    d_value = initial_d
    values: list[KDJValue] = []

    for index, close in enumerate(closes):
        start = max(0, index - period + 1)
        highest_high = max(highs[start : index + 1])
        lowest_low = min(lows[start : index + 1])

        if highest_high == lowest_low:
            rsv = 50.0
        else:
            rsv = (close - lowest_low) / (highest_high - lowest_low) * 100.0

        k_value = (2.0 / 3.0) * k_value + (1.0 / 3.0) * rsv
        d_value = (2.0 / 3.0) * d_value + (1.0 / 3.0) * k_value
        j_value = 3.0 * k_value - 2.0 * d_value
        values.append(KDJValue(k=k_value, d=d_value, j=j_value))

    return tuple(values)
