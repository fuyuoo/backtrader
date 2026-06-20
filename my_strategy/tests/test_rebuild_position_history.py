import pandas as pd
import pytest
from pathlib import Path
from my_strategy.tools.rebuild_position_history import (
    build_daily_position_pnl,
    build_daily_portfolio_snapshot,
)


def _make_trades():
    return pd.DataFrame({
        'ts_code': ['A.SZ', 'B.SZ'],
        'entry_date': pd.to_datetime(['2024-01-02', '2024-01-03']),
        'exit_date': pd.to_datetime(['2024-01-05', '2024-01-08']),
        'avg_cost': [10.0, 20.0],
    })


def _make_daily_dict():
    return {
        'A.SZ': pd.DataFrame({
            'date': pd.to_datetime(['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05']),
            'close': [10.0, 11.0, 10.5, 12.0],
        }),
        'B.SZ': pd.DataFrame({
            'date': pd.to_datetime(['2024-01-03', '2024-01-04', '2024-01-05', '2024-01-08']),
            'close': [20.0, 21.0, 19.0, 22.0],
        }),
    }


def _make_sector_map():
    return pd.DataFrame({
        'ts_code': ['A.SZ', 'B.SZ'],
        'sw_index_code': ['801010', '801080'],
    })


def test_build_daily_position_pnl_emits_one_row_per_trade_per_day():
    trades = _make_trades()
    dailies = _make_daily_dict()
    sec = _make_sector_map()
    out = build_daily_position_pnl(trades, dailies, sec)
    # A.SZ 持仓 4 天 (1/2~1/5) + B.SZ 持仓 4 天 (1/3~1/8 含 3 个交易日 + 入场日) = 视具体行情
    assert set(out.columns) >= {
        'trade_id', 'ts_code', 'entry_date', 'holding_day_n',
        'date', 'close', 'cum_return_pct', 'drawdown_from_peak_pct', 'sector_code',
    }
    a_rows = out[out['ts_code'] == 'A.SZ']
    assert len(a_rows) == 4  # 1/2, 1/3, 1/4, 1/5
    assert a_rows['holding_day_n'].tolist() == [0, 1, 2, 3]
    # 1/3 cum_return = (11-10)/10 = 10%
    assert abs(a_rows.iloc[1]['cum_return_pct'] - 10.0) < 1e-6
    # 1/4 cum_return = (10.5-10)/10 = 5%, peak so far = 10%, drawdown_from_peak = -4.55%
    assert abs(a_rows.iloc[2]['drawdown_from_peak_pct'] - ((10.5/11.0 - 1) * 100)) < 1e-3


def test_build_daily_portfolio_snapshot_aggregates_by_date():
    trades = _make_trades()
    dailies = _make_daily_dict()
    sec = _make_sector_map()
    pnl = build_daily_position_pnl(trades, dailies, sec)
    snap = build_daily_portfolio_snapshot(pnl)
    assert set(snap.columns) >= {
        'date', 'n_positions', 'sectors_held', 'top_sector_code',
        'top_sector_share', 'herfindahl_index',
    }
    # 1/3 应有 A.SZ 和 B.SZ 同时持仓
    d_0103 = snap[snap['date'] == pd.Timestamp('2024-01-03')].iloc[0]
    assert d_0103['n_positions'] == 2
    assert d_0103['sectors_held'] == 2
    assert abs(d_0103['herfindahl_index'] - (0.5 ** 2 + 0.5 ** 2)) < 1e-6


def test_build_raises_on_missing_daily_data():
    trades = _make_trades()
    dailies = {'A.SZ': _make_daily_dict()['A.SZ']}  # 缺 B.SZ
    sec = _make_sector_map()
    with pytest.raises((KeyError, FileNotFoundError, ValueError)):
        build_daily_position_pnl(trades, dailies, sec)
