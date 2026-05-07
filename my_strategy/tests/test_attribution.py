import pandas as pd
from my_strategy.tools.attribution import (
    compute_trade_profile,
    compute_top_bottom_trades,
    compute_sector_winrate,
    compute_exit_reason_stats,
    compute_add_count_stats,
    compute_entry_condition_stats,
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


def _make_trade_summary_extended():
    """覆盖 exit_reason / add_count / status / gross_pnl / entry_date 等扩展字段。"""
    return pd.DataFrame({
        'ts_code': ['A.SZ', 'B.SZ', 'C.SZ', 'D.SZ', 'E.SZ', 'F.SZ'],
        'entry_date': pd.to_datetime(
            ['2022-01-05', '2022-06-10', '2023-02-08', '2023-09-15',
             '2024-03-12', '2024-11-20']),
        'return_pct': [15.0, -3.0, 8.0, -12.0, 2.0, float('nan')],
        'gross_pnl': [15000.0, -3000.0, 8000.0, -12000.0, 2000.0, float('nan')],
        'holding_days': [40.0, 15.0, 60.0, 22.0, 10.0, float('nan')],
        'add_count': [2, 0, 1, 0, 1, 1],
        'exit_reason': ['take_profit_2', 'MA25清仓', 'take_profit_2',
                        'MA25清仓', 'take_profit_1', '未平仓'],
        'status': ['completed', 'completed', 'completed',
                   'completed', 'completed', 'incomplete'],
    })


def test_compute_exit_reason_stats_groups_by_reason():
    trades = _make_trade_summary_extended()
    out = compute_exit_reason_stats(trades)
    assert set(out['exit_reason']) == {
        'take_profit_2', 'MA25清仓', 'take_profit_1', '未平仓'}
    ma25 = out[out['exit_reason'] == 'MA25清仓'].iloc[0]
    assert ma25['count'] == 2
    assert ma25['win_rate'] == 0.0
    assert ma25['avg_return'] == -7.5
    incomplete = out[out['exit_reason'] == '未平仓'].iloc[0]
    assert incomplete['count'] == 1
    assert pd.isna(incomplete['win_rate'])
    assert list(out['count']) == sorted(out['count'], reverse=True)


def test_compute_exit_reason_stats_empty_input():
    out = compute_exit_reason_stats(pd.DataFrame())
    assert list(out.columns) == ['exit_reason', 'count', 'win_rate',
                                  'avg_return', 'avg_holding_days',
                                  'avg_add_count']
    assert len(out) == 0


def test_compute_add_count_stats_buckets_3plus():
    trades = pd.DataFrame({
        'add_count': [0, 0, 1, 1, 2, 3, 4, 5],
        'return_pct': [1.0, 2.0, 3.0, -1.0, 0.5, 10.0, 20.0, 30.0],
        'gross_pnl': [100, 200, 300, -100, 50, 1000, 2000, 3000],
        'holding_days': [10, 12, 20, 18, 30, 50, 60, 70],
        'status': ['completed'] * 8,
    })
    out = compute_add_count_stats(trades)
    assert set(out['add_count']) == {'0', '1', '2', '3+'}
    bucket_3plus = out[out['add_count'] == '3+'].iloc[0]
    assert bucket_3plus['count'] == 3
    assert list(out['add_count']) == ['0', '1', '2', '3+']


def test_compute_add_count_stats_pct_completed():
    trades = pd.DataFrame({
        'add_count': [1, 1, 1, 1],
        'return_pct': [1.0, 2.0, float('nan'), float('nan')],
        'gross_pnl': [100, 200, float('nan'), float('nan')],
        'holding_days': [10, 12, float('nan'), float('nan')],
        'status': ['completed', 'completed', 'incomplete', 'incomplete'],
    })
    out = compute_add_count_stats(trades)
    row = out[out['add_count'] == '1'].iloc[0]
    assert row['count'] == 4
    assert row['pct_completed'] == 0.5


def test_compute_add_count_stats_empty_input():
    out = compute_add_count_stats(pd.DataFrame())
    assert list(out.columns) == ['add_count', 'count', 'win_rate',
                                  'avg_return', 'avg_holding_days',
                                  'pct_completed']
    assert len(out) == 0


def test_compute_entry_condition_stats_kdj_buckets():
    trades = pd.DataFrame({
        'entry_kdj_j': [25.0, 50.0, 75.0, 90.0, 110.0],
        'entry_ma60_dist_pct': [0.5, 3.0, 8.0, 15.0, 25.0],
        'ma_alignment': ['全多头'] * 5,
        'macd_zone': ['区间1'] * 5,
        'entry_week_kdj_j': [30.0, 55.0, 70.0, 85.0, 105.0],
        'entry_week_macd_zone': ['区间0'] * 5,
        'entry_month_macd_zone': ['区间0'] * 5,
        'return_pct': [5.0, 3.0, 1.0, -2.0, -8.0],
        'gross_pnl': [500, 300, 100, -200, -800],
        'holding_days': [30, 25, 20, 15, 10],
    })
    out = compute_entry_condition_stats(trades)
    assert set(out['condition_field']) == {
        'entry_kdj_j', 'entry_ma60_dist_pct', 'ma_alignment',
        'macd_zone', 'entry_week_kdj_j', 'entry_week_macd_zone',
        'entry_month_macd_zone'}
    kdj = out[out['condition_field'] == 'entry_kdj_j']
    assert set(kdj['bucket']) == {'[0,40)', '[40,80)', '[80,100)', '[100+)'}
    bucket_4080 = kdj[kdj['bucket'] == '[40,80)'].iloc[0]
    assert bucket_4080['count'] == 2


def test_compute_entry_condition_stats_ma60_dist_buckets():
    trades = pd.DataFrame({
        'entry_kdj_j': [50.0] * 6,
        'entry_ma60_dist_pct': [-1.0, 0.5, 7.5, 15.0, 25.0, 35.0],
        'ma_alignment': ['全多头'] * 6,
        'macd_zone': ['区间1'] * 6,
        'entry_week_kdj_j': [50.0] * 6,
        'entry_week_macd_zone': ['区间0'] * 6,
        'entry_month_macd_zone': ['区间0'] * 6,
        'return_pct': [1.0] * 6,
        'gross_pnl': [100] * 6,
        'holding_days': [10] * 6,
    })
    out = compute_entry_condition_stats(trades)
    ma60 = out[out['condition_field'] == 'entry_ma60_dist_pct']
    assert set(ma60['bucket']) == {
        '[<0%)', '[0%,5%)', '[5%,10%)', '[10%,20%)', '[20%+)'}
    assert ma60[ma60['bucket'] == '[<0%)'].iloc[0]['count'] == 1
    assert ma60[ma60['bucket'] == '[20%+)'].iloc[0]['count'] == 2


def test_compute_entry_condition_stats_categorical():
    trades = pd.DataFrame({
        'entry_kdj_j': [50.0] * 4,
        'entry_ma60_dist_pct': [3.0] * 4,
        'ma_alignment': ['全多头', '全多头', '局部空头', '全空头'],
        'macd_zone': ['区间1'] * 4,
        'entry_week_kdj_j': [50.0] * 4,
        'entry_week_macd_zone': ['区间0'] * 4,
        'entry_month_macd_zone': ['区间0'] * 4,
        'return_pct': [5.0, 3.0, -2.0, -10.0],
        'gross_pnl': [500, 300, -200, -1000],
        'holding_days': [20, 15, 10, 8],
    })
    out = compute_entry_condition_stats(trades)
    align = out[out['condition_field'] == 'ma_alignment']
    full_long = align[align['bucket'] == '全多头'].iloc[0]
    assert full_long['count'] == 2
    assert full_long['avg_return'] == 4.0


def test_compute_entry_condition_stats_empty_input():
    out = compute_entry_condition_stats(pd.DataFrame())
    assert list(out.columns) == ['condition_field', 'bucket', 'count',
                                  'win_rate', 'avg_return', 'avg_holding_days']
    assert len(out) == 0
