import pandas as pd
import pytest
from my_strategy.tools.position_curve_attribution import compute_holding_period_curve, compute_mfe_timing, compute_sector_concentration_stats


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


def test_compute_mfe_timing_classifies_by_position_in_holding():
    # trade 0: peak 在持仓早期 (day 1 of 6)
    rows = []
    for i in range(6):
        rows.append({
            'trade_id': 0, 'ts_code': 'A',
            'entry_date': pd.Timestamp('2024-01-02'),
            'holding_day_n': i, 'date': pd.Timestamp('2024-01-02') + pd.Timedelta(days=i),
            'close': 10.0, 'cum_return_pct': [0, 5, 3, 2, 1, 0][i],
            'drawdown_from_peak_pct': 0.0, 'sector_code': '801010',
        })
    # trade 1: peak 在持仓晚期 (day 5 of 6)
    for i in range(6):
        rows.append({
            'trade_id': 1, 'ts_code': 'B',
            'entry_date': pd.Timestamp('2024-02-02'),
            'holding_day_n': i, 'date': pd.Timestamp('2024-02-02') + pd.Timedelta(days=i),
            'close': 20.0, 'cum_return_pct': [0, 1, 2, 3, 4, 5][i],
            'drawdown_from_peak_pct': 0.0, 'sector_code': '801080',
        })
    pnl = pd.DataFrame(rows)
    out = compute_mfe_timing(pnl)
    assert set(out.columns) >= {
        'mfe_timing_bucket', 'n', 'win_rate', 'avg_return',
        'avg_holding_days', 'avg_mfe_pct',
    }
    buckets = out['mfe_timing_bucket'].tolist()
    assert any('早期' in b for b in buckets)
    assert any('晚期' in b for b in buckets)


def test_compute_sector_concentration_stats_summary_and_top_n():
    snap = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=5),
        'n_positions': [10, 10, 10, 10, 10],
        'sectors_held': [3, 2, 5, 4, 1],
        'top_sector_code': ['801010', '801010', '801080', '801010', '801080'],
        'top_sector_share': [0.5, 0.7, 0.3, 0.4, 1.0],
        'herfindahl_index': [0.30, 0.50, 0.20, 0.25, 1.0],
    })
    out = compute_sector_concentration_stats(snap, top_n=2)
    assert (out['metric_type'] == 'summary').any()
    assert (out['metric_type'] == 'top_concentrated_day').any()
    avg_max = out[(out['metric_type'] == 'summary') & (out['label'] == 'avg_max_sector_share')].iloc[0]
    # avg(0.5, 0.7, 0.3, 0.4, 1.0) = 0.58
    assert abs(avg_max['value'] - 0.58) < 1e-3
