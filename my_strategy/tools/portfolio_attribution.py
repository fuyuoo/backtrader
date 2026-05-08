"""Portfolio-level 归因报告（5 张）。输入: _TimeReturn 日收益、benchmark、position_count_log。"""
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_TRADING_DAYS = 252


def _max_drawdown(equity: pd.Series) -> tuple:
    """返回 (max_dd, dd_duration_days)。equity 为累计资金曲线（从 1 开始）。"""
    if equity.empty:
        return (np.nan, 0)
    running_peak = equity.cummax()
    dd = equity / running_peak - 1.0
    max_dd = float(dd.min())
    if max_dd == 0:
        return (0.0, 0)
    trough_idx = dd.idxmin()
    peak_before = equity[:trough_idx].idxmax()
    duration = (trough_idx - peak_before).days
    return (max_dd, int(duration))


def _risk_block(daily_ret: pd.Series, period_type: str, period_label: str) -> dict:
    r = daily_ret.dropna()
    if len(r) < 2:
        return None
    equity = (1 + r).cumprod()
    ann_ret = float((1 + r.mean()) ** _TRADING_DAYS - 1)
    ann_vol = float(r.std(ddof=1) * np.sqrt(_TRADING_DAYS))
    downside = r[r < 0]
    down_vol = float(downside.std(ddof=1) * np.sqrt(_TRADING_DAYS)) if len(downside) >= 2 else np.nan
    sharpe = ann_ret / ann_vol if ann_vol > 0 else np.nan
    sortino = ann_ret / down_vol if down_vol and down_vol > 0 else np.nan
    max_dd, dd_dur = _max_drawdown(equity)
    calmar = ann_ret / abs(max_dd) if max_dd < 0 else np.nan
    return {
        'period_type': period_type,
        'period_label': period_label,
        'sharpe': round(sharpe, 4) if pd.notna(sharpe) else np.nan,
        'sortino': round(sortino, 4) if pd.notna(sortino) else np.nan,
        'calmar': round(calmar, 4) if pd.notna(calmar) else np.nan,
        'max_drawdown': round(max_dd, 4),
        'max_dd_duration_days': dd_dur,
        'annualized_return': round(ann_ret, 4),
        'annualized_vol': round(ann_vol, 4),
        'downside_vol': round(down_vol, 4) if pd.notna(down_vol) else np.nan,
    }


def compute_portfolio_risk_metrics(daily_ret: pd.Series) -> pd.DataFrame:
    daily_ret = pd.Series(daily_ret).dropna()
    daily_ret.index = pd.to_datetime(daily_ret.index)
    rows = []
    label = f"{daily_ret.index.min().date()}~{daily_ret.index.max().date()}"
    rows.append(_risk_block(daily_ret, 'overall', label))
    for y, g in daily_ret.groupby(daily_ret.index.year):
        rows.append(_risk_block(g, 'yearly', str(int(y))))
    for ym, g in daily_ret.groupby(daily_ret.index.to_period('M').astype(str)):
        rows.append(_risk_block(g, 'monthly', ym))
    return pd.DataFrame([r for r in rows if r is not None])
