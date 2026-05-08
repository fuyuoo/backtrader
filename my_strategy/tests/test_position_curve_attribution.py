import pandas as pd
import pytest
from my_strategy.tools.position_curve_attribution import compute_holding_period_curve


def _make_daily_pnl():
    """构造 2 笔交易，每笔 5 天持仓"""
    rows = []
    # trade 0: 持仓 5 天，每天 +1%
    for i in range(5):
        rows.append({
            'trade_id': 0, 'ts_code': 'A',
            'entry_date': pd.Timestamp('2024-01-02'),
            'holding_day_n': i,
            'date': pd.Timestamp('2024-01-02') + pd.Timedelta(days=i),
            'close': 10.0 * (1 + i * 0.01),
            'cum_return_pct': i * 1.0,
            'drawdown_from_peak_pct': 0.0,
            'sector_code': '801010',
        })
    # trade 1: 持仓 3 天
    for i in range(3):
        rows.append({
            'trade_id': 1, 'ts_code': 'B',
            'entry_date': pd.Timestamp('2024-02-02'),
            'holding_day_n': i,
            'date': pd.Timestamp('2024-02-02') + pd.Timedelta(days=i),
            'close': 20.0 * (1 - i * 0.01),
            'cum_return_pct': -i * 1.0,
            'drawdown_from_peak_pct': -i * 1.0,
            'sector_code': '801080',
        })
    return pd.DataFrame(rows)


def test_compute_holding_period_curve_emits_sample_points():
    pnl = _make_daily_pnl()
    out = compute_holding_period_curve(pnl)
    assert set(out.columns) >= {
        'holding_day_n', 'n_active_trades', 'avg_cum_return',
        'median_cum_return', 'win_rate_at_day_n',
        'p25_cum_return', 'p75_cum_return', 'avg_drawdown_from_peak',
    }
    # day 0: 2 笔活跃；day 3: 1 笔活跃（trade 0 仍在）
    d0 = out[out['holding_day_n'] == 0].iloc[0]
    assert d0['n_active_trades'] == 2
    d3 = out[out['holding_day_n'] == 3].iloc[0]
    assert d3['n_active_trades'] == 1
