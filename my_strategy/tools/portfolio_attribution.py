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


def compute_losing_streak_stats(trades: pd.DataFrame) -> pd.DataFrame:
    if 'return_pct' not in trades.columns or 'entry_date' not in trades.columns:
        return pd.DataFrame()
    t = trades.sort_values('entry_date')
    signs = (t['return_pct'] > 0).astype(int).where(t['return_pct'] != 0, np.nan)

    def _streaks(arr, target):
        max_len = cur = 0
        lengths = []
        for x in arr:
            if x == target:
                cur += 1
                max_len = max(max_len, cur)
            else:
                if cur > 0:
                    lengths.append(cur)
                cur = 0
        if cur > 0:
            lengths.append(cur)
        return max_len, lengths

    longest_loss, loss_lens = _streaks(signs.fillna(-1).tolist(), 0)
    longest_win, _ = _streaks(signs.fillna(-1).tolist(), 1)
    avg_loss_streak = float(np.mean(loss_lens)) if loss_lens else 0.0
    pct_ge_5 = float(np.mean([x >= 5 for x in loss_lens])) if loss_lens else 0.0
    return pd.DataFrame([
        {'metric': 'longest_losing_streak', 'value': longest_loss},
        {'metric': 'longest_winning_streak', 'value': longest_win},
        {'metric': 'avg_losing_streak_length', 'value': round(avg_loss_streak, 4)},
        {'metric': 'pct_losing_streaks_ge_5', 'value': round(pct_ge_5, 4)},
    ])


def compute_drawdown_periods(daily_ret: pd.Series, top_n: int = 10) -> pd.DataFrame:
    r = pd.Series(daily_ret).dropna()
    r.index = pd.to_datetime(r.index)
    equity = (1 + r).cumprod()
    running_peak = equity.cummax()
    in_dd = equity < running_peak

    # 找到所有回撤区间
    periods = []
    i = 0
    arr = in_dd.values
    idx = equity.index
    while i < len(arr):
        if arr[i]:
            start = i
            # 找峰值（前一个非回撤点的峰）
            peak_idx = start - 1 if start > 0 else 0
            peak_value = float(equity.iloc[peak_idx])
            # 找谷底
            j = i
            trough_value = float(equity.iloc[j])
            trough_idx = j
            while j < len(arr) and arr[j]:
                if equity.iloc[j] < trough_value:
                    trough_value = float(equity.iloc[j])
                    trough_idx = j
                j += 1
            recovery_idx = j if j < len(arr) else None
            periods.append({
                'start_date': idx[peak_idx],
                'trough_date': idx[trough_idx],
                'recovery_date': idx[recovery_idx] if recovery_idx is not None else pd.NaT,
                'peak_value': peak_value,
                'trough_value': trough_value,
                'drawdown_pct': round((trough_value / peak_value - 1) * 100, 4),
                'duration_days': (idx[trough_idx] - idx[peak_idx]).days,
                'recovery_days': (idx[recovery_idx] - idx[trough_idx]).days
                                 if recovery_idx is not None else -1,
            })
            i = j
        else:
            i += 1
    df = pd.DataFrame(periods)
    if df.empty:
        return df
    df = df.sort_values('drawdown_pct').head(top_n).reset_index(drop=True)
    df.insert(0, 'rank', range(1, len(df) + 1))
    return df


def compute_concurrent_positions_stats(
    position_count_log,
    max_positions: int,
) -> pd.DataFrame:
    """输入可以是 list[int]（每根 Bar 的并发持仓数，per Task 0 投研）、
    list[(date, count)] 或 DataFrame[date, count]。"""
    if isinstance(position_count_log, list):
        if not position_count_log:
            df = pd.DataFrame({'date': [], 'count': []})
        elif isinstance(position_count_log[0], (int, float, np.integer, np.floating)):
            # list[int] — per Task 0, the real production schema
            df = pd.DataFrame({
                'date': pd.RangeIndex(len(position_count_log)),
                'count': position_count_log,
            })
        else:
            df = pd.DataFrame(position_count_log, columns=['date', 'count'])
    else:
        df = pd.DataFrame(position_count_log).copy()
        if 'count' not in df.columns:
            df = df.rename(columns={df.columns[1]: 'count'})
    counts = df['count'].astype(int)
    n = len(counts)
    rows = [
        {'metric_type': 'summary', 'bucket': 'max', 'value': float(counts.max()), 'days_at_level': np.nan, 'pct_of_time': np.nan},
        {'metric_type': 'summary', 'bucket': 'avg', 'value': round(float(counts.mean()), 2), 'days_at_level': np.nan, 'pct_of_time': np.nan},
        {'metric_type': 'summary', 'bucket': 'median', 'value': float(counts.median()), 'days_at_level': np.nan, 'pct_of_time': np.nan},
        {'metric_type': 'summary', 'bucket': 'p95', 'value': float(counts.quantile(0.95)), 'days_at_level': np.nan, 'pct_of_time': np.nan},
        {'metric_type': 'summary', 'bucket': 'pct_at_cap', 'value': round(float((counts == max_positions).mean()), 4), 'days_at_level': np.nan, 'pct_of_time': np.nan},
        {'metric_type': 'summary', 'bucket': 'pct_below_50', 'value': round(float((counts < 50).mean()), 4), 'days_at_level': np.nan, 'pct_of_time': np.nan},
    ]
    edges = [(0, 0), (1, 25), (26, 50), (51, 100), (101, 150), (151, 200)]
    for lo, hi in edges:
        mask = (counts >= lo) & (counts <= hi)
        days = int(mask.sum())
        rows.append({
            'metric_type': 'position_count_bucket',
            'bucket': f"{lo}-{hi}" if lo != hi else str(lo),
            'value': np.nan,
            'days_at_level': days,
            'pct_of_time': round(days / n, 4) if n > 0 else 0.0,
        })
    return pd.DataFrame(rows)
