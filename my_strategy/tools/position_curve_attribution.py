"""基于 daily_position_pnl / daily_portfolio_snapshot / trade_list 的报告（4 张）。"""
from pathlib import Path

import numpy as np
import pandas as pd

_HOLDING_SAMPLE_DAYS = [1, 2, 3, 5, 7, 10, 15, 20, 25, 30, 40, 50, 60, 75, 90]


def compute_holding_period_curve(daily_position_pnl: pd.DataFrame) -> pd.DataFrame:
    sample_points = [0] + _HOLDING_SAMPLE_DAYS
    rows = []
    for n in sample_points:
        sub = daily_position_pnl[daily_position_pnl['holding_day_n'] == n]
        if sub.empty:
            continue
        r = sub['cum_return_pct'].dropna()
        dd = sub['drawdown_from_peak_pct'].dropna()
        rows.append({
            'holding_day_n': n,
            'n_active_trades': len(sub),
            'avg_cum_return': round(float(r.mean()), 4) if len(r) else np.nan,
            'median_cum_return': round(float(r.median()), 4) if len(r) else np.nan,
            'win_rate_at_day_n': round(float((r > 0).mean()), 4) if len(r) else np.nan,
            'p25_cum_return': round(float(r.quantile(0.25)), 4) if len(r) else np.nan,
            'p75_cum_return': round(float(r.quantile(0.75)), 4) if len(r) else np.nan,
            'avg_drawdown_from_peak': round(float(dd.mean()), 4) if len(dd) else np.nan,
        })
    return pd.DataFrame(rows)
