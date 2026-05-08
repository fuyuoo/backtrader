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


def compute_mfe_timing(daily_position_pnl: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for trade_id, g in daily_position_pnl.groupby('trade_id'):
        if g.empty:
            continue
        max_day = int(g['holding_day_n'].max())
        if max_day == 0:
            continue
        peak_idx = g['cum_return_pct'].idxmax()
        peak_day = int(g.loc[peak_idx, 'holding_day_n'])
        peak_value = float(g.loc[peak_idx, 'cum_return_pct'])
        ratio = peak_day / max_day
        if ratio <= 1/3:
            bucket = '早期(前 1/3)'
        elif ratio <= 2/3:
            bucket = '中期(中 1/3)'
        else:
            bucket = '晚期(后 1/3)'
        final_return = float(g.iloc[-1]['cum_return_pct'])
        rows.append({
            'trade_id': trade_id,
            'mfe_timing_bucket': bucket,
            'holding_days': max_day,
            'final_return': final_return,
            'mfe_pct': peak_value,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    out = df.groupby('mfe_timing_bucket').agg(
        n=('trade_id', 'count'),
        win_rate=('final_return', lambda s: (s > 0).mean()),
        avg_return=('final_return', 'mean'),
        avg_holding_days=('holding_days', 'mean'),
        avg_mfe_pct=('mfe_pct', 'mean'),
    ).reset_index()
    for c in ['win_rate', 'avg_return', 'avg_holding_days', 'avg_mfe_pct']:
        out[c] = out[c].round(4)
    return out
