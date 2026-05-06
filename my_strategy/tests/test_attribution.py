import pandas as pd
from my_strategy.tools.attribution import (
    compute_trade_profile,
    compute_top_bottom_trades,
    compute_sector_winrate,
)


def _make_trade_log():
    return pd.DataFrame({
        'ts_code': ['A.SZ', 'B.SZ', 'C.SZ', 'D.SZ', 'E.SZ'],
        'entry_date': pd.to_datetime(
            ['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05', '2024-01-08']),
        'return_pct': [15.0, 3.0, 0.0, -3.0, -15.0],
        'holding_days': [40, 20, 10, 15, 30],
    })


def _make_signals_log():
    return pd.DataFrame({
        'ts_code': ['A.SZ', 'B.SZ', 'C.SZ', 'D.SZ', 'E.SZ'],
        'date': pd.to_datetime(
            ['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05', '2024-01-08']).date,
        'sector': ['801010.SI', '801010.SI', '801080.SI', '801080.SI', '801120.SI'],
        'factor_roe': [20.0, 15.0, 10.0, 5.0, 0.0],
        'pct_roe': [1.0, 0.7, 0.5, 0.3, 0.0],
        'pct_pe': [0.8, 0.6, 0.5, 0.4, 0.2],
        'pct_momentum_60d': [0.9, 0.7, 0.5, 0.3, 0.1],
    })


def test_compute_trade_profile_buckets_by_return():
    trades = _make_trade_log()
    sigs = _make_signals_log()
    out = compute_trade_profile(trades, sigs)
    # 期望桶：大盈 / 小盈 / 持平 / 小亏 / 大亏 各 1 笔
    assert set(out['bucket']) >= {'大盈', '小盈', '持平', '小亏', '大亏'}
    big_win = out[out['bucket'] == '大盈'].iloc[0]
    big_loss = out[out['bucket'] == '大亏'].iloc[0]
    assert big_win['mean_pct_roe'] > big_loss['mean_pct_roe']


def test_compute_top_bottom_trades_returns_extremes():
    trades = _make_trade_log()
    sigs = _make_signals_log()
    top, bottom = compute_top_bottom_trades(trades, sigs, n=2)
    assert list(top['return_pct']) == [15.0, 3.0]
    assert list(bottom['return_pct']) == [-15.0, -3.0]


def test_compute_sector_winrate_aggregates_by_sector():
    trades = _make_trade_log()
    sigs = _make_signals_log()
    out = compute_sector_winrate(trades, sigs)
    assert 'sector' in out.columns
    assert 'win_rate' in out.columns
    assert 'avg_return' in out.columns
    sw_801010 = out[out['sector'] == '801010.SI'].iloc[0]
    # A.SZ +15, B.SZ +3 → win_rate = 1.0
    assert sw_801010['win_rate'] == 1.0


from my_strategy.tools.attribution import compute_factor_alpha


def test_compute_factor_alpha_picks_top_n_per_day():
    """构造一个高 ROE 信号事后必赚的样本，验证 alpha 计算方向正确。"""
    sigs = pd.DataFrame({
        'ts_code': ['A', 'B', 'C', 'D', 'E', 'F'],
        'date': pd.to_datetime(['2024-01-01'] * 3 + ['2024-01-02'] * 3).date,
        'pct_roe': [0.9, 0.5, 0.1, 0.9, 0.5, 0.1],
        'pct_pe': [0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
        'forward_return_20d': [0.1, 0.05, -0.05, 0.08, 0.04, -0.04],
    })
    out = compute_factor_alpha(sigs, top_n=1, factors=['pct_roe', 'pct_pe'],
                               horizon='forward_return_20d')
    roe_row = out[out['factor'] == 'pct_roe'].iloc[0]
    # 每日 Top-1 by pct_roe = A 和 D：(0.1 + 0.08)/2 = 0.09
    assert abs(roe_row['top_n_avg'] - 0.09) < 1e-6
    # baseline = 全部信号平均 = (0.1+0.05-0.05+0.08+0.04-0.04)/6 ≈ 0.03
    assert roe_row['top_n_avg'] > roe_row['baseline_avg']
    assert roe_row['alpha'] > 0
