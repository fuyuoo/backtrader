"""Trade-level 扩展归因报告（5 张）。输入: trade_summary.csv。"""
from pathlib import Path

import numpy as np
import pandas as pd


def _payoff_block(sub: pd.DataFrame, dimension: str, bucket: str) -> dict:
    n = len(sub)
    if n == 0:
        return None
    r = sub['return_pct']
    wins = r[r > 0]
    losses = r[r < 0]
    n_wins = len(wins)
    n_losses = len(losses)
    avg_win = wins.mean() if n_wins > 0 else 0.0
    avg_loss = losses.mean() if n_losses > 0 else 0.0
    sum_win = wins.sum() if n_wins > 0 else 0.0
    sum_loss = losses.sum() if n_losses > 0 else 0.0
    payoff = (avg_win / abs(avg_loss)) if avg_loss < 0 else np.nan
    profit_factor = (sum_win / abs(sum_loss)) if sum_loss < 0 else np.nan
    win_rate = n_wins / n if n > 0 else 0.0
    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
    return {
        'dimension': dimension,
        'bucket': bucket,
        'n': n,
        'win_rate': round(win_rate, 4),
        'avg_win': round(float(avg_win), 4),
        'avg_loss': round(float(avg_loss), 4),
        'payoff_ratio': float(payoff) if pd.notna(payoff) else np.nan,
        'profit_factor': float(profit_factor) if pd.notna(profit_factor) else np.nan,
        'expectancy': round(float(expectancy), 4),
        'max_win': round(float(r.max()), 4),
        'max_loss': round(float(r.min()), 4),
    }


def compute_payoff_metrics(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    rows.append(_payoff_block(trades, 'overall', 'all'))
    if 'exit_reason' in trades.columns:
        for v, sub in trades.groupby('exit_reason'):
            rows.append(_payoff_block(sub, 'exit_reason', str(v)))
    if 'entry_date' in trades.columns:
        years = pd.to_datetime(trades['entry_date']).dt.year
        for y, sub in trades.groupby(years):
            rows.append(_payoff_block(sub, 'year', str(int(y))))
    if 'industry' in trades.columns:
        for v, sub in trades.groupby('industry'):
            if pd.notna(v):
                rows.append(_payoff_block(sub, 'sector', str(v)))
    if {'entry_hs300_dif_above_zero', 'entry_stock_bull_align'}.issubset(trades.columns):
        for (a, b), sub in trades.groupby(
            ['entry_hs300_dif_above_zero', 'entry_stock_bull_align']
        ):
            label = f"hs300_dif={a}|stock_bull={b}"
            rows.append(_payoff_block(sub, 'regime', label))
    return pd.DataFrame([r for r in rows if r is not None])
