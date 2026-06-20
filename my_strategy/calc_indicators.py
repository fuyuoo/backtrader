"""Compatibility exports for legacy ``my_strategy.calc_indicators`` imports."""

import pandas as pd

from my_strategy.src.calc_indicators import *  # noqa: F401,F403
from my_strategy.src import calc_indicators as _impl


def compute_indicators(*args, **kwargs):
    """Support both legacy ``compute_indicators(df)`` and current CLI signature."""

    if len(args) == 1 and not kwargs and isinstance(args[0], pd.DataFrame):
        result = _impl.compute_all_indicators(args[0])
        if "trade_date" in result.columns:
            result = result.copy()
            result.index = pd.to_datetime(result["trade_date"])
        return result
    return _impl.compute_indicators(*args, **kwargs)
