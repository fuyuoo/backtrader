import pandas as pd
from my_strategy.tools.attribution import (
    compute_trade_profile,
    compute_top_bottom_trades,
    compute_sector_winrate,
    compute_exit_reason_stats,
    compute_add_count_stats,
    compute_entry_condition_stats,
    compute_yearly_stats,
    compute_first_buy_size_stats,
    compute_add_block_stats,
    compute_mfe_mae_by_exit,
    compute_mfe_distribution,
    compute_dea_lookback_stats,
    compute_monthly_stats,
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


def test_compute_yearly_stats_groups_by_year():
    trades = _make_trade_summary_extended()
    out = compute_yearly_stats(trades)
    assert list(out['year']) == [2022, 2023, 2024]
    y2022 = out[out['year'] == 2022].iloc[0]
    assert y2022['count'] == 2
    assert y2022['total_pnl_yuan'] == 12000.0
    assert y2022['win_rate'] == 0.5
    y2024 = out[out['year'] == 2024].iloc[0]
    assert y2024['count'] == 2
    assert y2024['win_rate'] == 1.0
    assert y2024['median_return'] == 2.0


def test_compute_yearly_stats_empty_input():
    out = compute_yearly_stats(pd.DataFrame())
    assert list(out.columns) == ['year', 'count', 'win_rate',
                                  'avg_return', 'median_return',
                                  'total_pnl_yuan', 'avg_holding_days']
    assert len(out) == 0


def test_compute_first_buy_size_stats_buckets():
    trades = pd.DataFrame({
        'entry_ma60_dist_pct': [
            -1.5,           # [<-1%)
            -0.7, -0.6,     # [-1%,-0.5%) 两笔
            -0.2,           # [-0.5%,0%)
            0.3,            # [0%,0.5%)
            0.7,            # [0.5%,1%)
            1.2,            # [1%,1.5%)
            1.7,            # [1.5%,2%)
            2.5,            # [2%,3%)
            4.0,            # [3%,5%)
            7.0,            # [5%,10%)
            15.0,           # [10%+)
        ],
        'return_pct': [-5.0, 1.0, 3.0, 2.0, 4.0, -2.0, 6.0, -1.0, 8.0, -3.0, 9.0, 0.0],
        'holding_days': [10, 12, 14, 20, 30, 25, 18, 15, 22, 28, 35, 40],
        'add_count': [0, 1, 0, 1, 2, 0, 1, 0, 2, 0, 1, 0],
        'status': ['completed'] * 12,
    })
    out = compute_first_buy_size_stats(trades)
    assert list(out['bucket']) == [
        '[<-1%)', '[-1%,-0.5%)', '[-0.5%,0%)',
        '[0%,0.5%)', '[0.5%,1%)', '[1%,1.5%)',
        '[1.5%,2%)', '[2%,3%)', '[3%,5%)',
        '[5%,10%)', '[10%+)',
    ]
    row_negativehalf = out[out['bucket'] == '[-1%,-0.5%)'].iloc[0]
    assert row_negativehalf['count'] == 2
    assert row_negativehalf['avg_return'] == 2.0  # (1+3)/2
    row_first = out[out['bucket'] == '[<-1%)'].iloc[0]
    assert row_first['count'] == 1
    assert row_first['win_rate'] == 0.0


def test_compute_first_buy_size_stats_empty_input():
    out = compute_first_buy_size_stats(pd.DataFrame())
    assert list(out.columns) == [
        'bucket', 'count', 'win_rate', 'avg_return', 'median_return',
        'avg_holding_days', 'avg_add_count', 'pct_completed',
    ]
    assert len(out) == 0


def test_compute_first_buy_size_stats_missing_column():
    out = compute_first_buy_size_stats(pd.DataFrame({'foo': [1, 2, 3]}))
    assert list(out.columns) == [
        'bucket', 'count', 'win_rate', 'avg_return', 'median_return',
        'avg_holding_days', 'avg_add_count', 'pct_completed',
    ]
    assert len(out) == 0


def test_compute_add_block_stats_buckets():
    trades = pd.DataFrame({
        'max_bullish_candle_pct': [
            0.0,            # [0%,0.5%)
            0.003,          # [0%,0.5%)（再加一笔）
            0.007,          # [0.5%,1%)
            0.012, 0.013,   # [1%,1.5%) 两笔
            0.018,          # [1.5%,2%)
            0.025,          # [2%,3%)
            0.040,          # [3%,5%)
            0.080,          # [5%,10%)
            0.150,          # [10%+)
        ],
        'return_pct': [3.0, 2.0, 5.0, -1.0, -2.0, 8.0, -4.0, 6.0, -3.0, 0.0],
        'holding_days': [10, 12, 15, 18, 20, 22, 25, 28, 30, 35],
        'add_count': [2, 1, 1, 0, 0, 1, 0, 1, 0, 0],
        'status': ['completed'] * 10,
    })
    out = compute_add_block_stats(trades)
    assert list(out['bucket']) == [
        '[0%,0.5%)', '[0.5%,1%)', '[1%,1.5%)',
        '[1.5%,2%)', '[2%,3%)', '[3%,5%)',
        '[5%,10%)', '[10%+)',
    ]
    row_1_15 = out[out['bucket'] == '[1%,1.5%)'].iloc[0]
    assert row_1_15['count'] == 2
    assert row_1_15['avg_return'] == -1.5
    assert row_1_15['win_rate'] == 0.0
    row_first = out[out['bucket'] == '[0%,0.5%)'].iloc[0]
    assert row_first['count'] == 2
    assert row_first['avg_return'] == 2.5


def test_compute_add_block_stats_empty_input():
    out = compute_add_block_stats(pd.DataFrame())
    assert list(out.columns) == [
        'bucket', 'count', 'win_rate', 'avg_return', 'median_return',
        'avg_holding_days', 'avg_add_count', 'pct_completed',
    ]
    assert len(out) == 0


def test_compute_add_block_stats_missing_column():
    out = compute_add_block_stats(pd.DataFrame({'return_pct': [1.0, 2.0]}))
    assert list(out.columns) == [
        'bucket', 'count', 'win_rate', 'avg_return', 'median_return',
        'avg_holding_days', 'avg_add_count', 'pct_completed',
    ]
    assert len(out) == 0


def test_compute_mfe_mae_by_exit_basic():
    trades = pd.DataFrame({
        'exit_reason': ['MA25清仓', 'MA25清仓', 'MA60止损', '止盈1'],
        'return_pct':  [3.0,        5.0,        -8.0,        4.0],
        'mfe_pct':     [8.0,        10.0,       2.0,         5.0],
        'mae_pct':     [-1.0,       -0.5,       -10.0,       -0.2],
    })
    out = compute_mfe_mae_by_exit(trades)
    assert list(out.columns) == [
        'exit_reason', 'count', 'avg_return',
        'avg_mfe', 'avg_mae', 'avg_pullback', 'avg_underwater',
    ]
    assert out.iloc[0]['exit_reason'] == 'MA25清仓'
    assert out.iloc[0]['count'] == 2
    assert out.iloc[0]['avg_return'] == 4.0
    assert out.iloc[0]['avg_mfe'] == 9.0
    assert out.iloc[0]['avg_mae'] == -0.75
    assert out.iloc[0]['avg_pullback'] == 5.0
    assert out.iloc[0]['avg_underwater'] == 0.75

    ma60 = out[out['exit_reason'] == 'MA60止损'].iloc[0]
    assert ma60['avg_underwater'] == 10.0


def test_compute_mfe_mae_by_exit_empty_input():
    out = compute_mfe_mae_by_exit(pd.DataFrame())
    assert list(out.columns) == [
        'exit_reason', 'count', 'avg_return',
        'avg_mfe', 'avg_mae', 'avg_pullback', 'avg_underwater',
    ]
    assert len(out) == 0


def test_compute_mfe_mae_by_exit_missing_column():
    out = compute_mfe_mae_by_exit(pd.DataFrame({'exit_reason': ['x']}))
    assert list(out.columns) == [
        'exit_reason', 'count', 'avg_return',
        'avg_mfe', 'avg_mae', 'avg_pullback', 'avg_underwater',
    ]
    assert len(out) == 0


def test_compute_mfe_distribution_buckets():
    trades = pd.DataFrame({
        'mfe_pct':    [-1.0,  0.5,  1.0, 3.0, 7.0, 12.0, 25.0, 4.0],
        'return_pct': [-2.0,  -1.0, 0.5, 1.0, 5.0, 10.0, 22.0, -3.0],
        'status':     ['completed'] * 8,
    })
    out = compute_mfe_distribution(trades)
    assert list(out.columns) == [
        'bucket', 'count', 'win_rate', 'avg_return',
        'median_return', 'pct_completed',
    ]
    expected = ['[<0%)', '[0%,2%)', '[2%,5%)', '[5%,10%)', '[10%,20%)', '[20%+)']
    assert list(out['bucket']) == expected
    row_2_5 = out[out['bucket'] == '[2%,5%)'].iloc[0]
    assert row_2_5['count'] == 2
    assert row_2_5['win_rate'] == 0.5
    row_first = out[out['bucket'] == '[<0%)'].iloc[0]
    assert row_first['count'] == 1
    assert row_first['win_rate'] == 0.0


def test_compute_mfe_distribution_empty_input():
    out = compute_mfe_distribution(pd.DataFrame())
    assert list(out.columns) == [
        'bucket', 'count', 'win_rate', 'avg_return',
        'median_return', 'pct_completed',
    ]
    assert len(out) == 0


def test_compute_mfe_distribution_missing_column():
    out = compute_mfe_distribution(pd.DataFrame({'return_pct': [1.0]}))
    assert list(out.columns) == [
        'bucket', 'count', 'win_rate', 'avg_return',
        'median_return', 'pct_completed',
    ]
    assert len(out) == 0


def test_compute_dea_lookback_stats_buckets():
    trades = pd.DataFrame({
        'dea_neg_distance_days': [1, 1, 2, 4, 5, 6, 8, 12, 25, 45, 100],
        'return_pct':              [3.0, 1.0, -2.0, 4.0, 5.0, -1.0, 2.0, -3.0, 6.0, -4.0, 8.0],
        'holding_days':            [10, 12, 15, 18, 20, 22, 25, 28, 30, 35, 40],
        'add_count':               [0, 1, 0, 1, 2, 0, 1, 0, 1, 0, 0],
        'status':                  ['completed'] * 11,
    })
    out = compute_dea_lookback_stats(trades)
    assert list(out.columns) == [
        'bucket', 'count', 'win_rate', 'avg_return', 'median_return',
        'avg_holding_days', 'avg_add_count', 'pct_completed',
    ]
    expected = ['[1,2)', '[2,3)', '[4,5)', '[5,7)', '[7,10)',
                '[10,15)', '[15,30)', '[30,60)', '[60+)']
    assert list(out['bucket']) == expected
    row_1 = out[out['bucket'] == '[1,2)'].iloc[0]
    assert row_1['count'] == 2
    assert row_1['avg_return'] == 2.0
    row_5_7 = out[out['bucket'] == '[5,7)'].iloc[0]
    assert row_5_7['count'] == 2


def test_compute_dea_lookback_stats_empty_input():
    out = compute_dea_lookback_stats(pd.DataFrame())
    assert list(out.columns) == [
        'bucket', 'count', 'win_rate', 'avg_return', 'median_return',
        'avg_holding_days', 'avg_add_count', 'pct_completed',
    ]
    assert len(out) == 0


def test_compute_dea_lookback_stats_missing_column():
    out = compute_dea_lookback_stats(pd.DataFrame({'return_pct': [1.0]}))
    assert list(out.columns) == [
        'bucket', 'count', 'win_rate', 'avg_return', 'median_return',
        'avg_holding_days', 'avg_add_count', 'pct_completed',
    ]
    assert len(out) == 0


def test_compute_monthly_stats_basic():
    trades = pd.DataFrame({
        'entry_date':    pd.to_datetime(['2023-01-15', '2023-01-20', '2023-03-05', '2023-03-10']),
        'return_pct':    [3.0, -1.0, 5.0, 2.0],
        'gross_pnl':     [3000.0, -1000.0, 5000.0, 2000.0],
        'holding_days':  [10, 15, 20, 12],
    })
    out = compute_monthly_stats(trades)
    assert list(out.columns) == [
        'year_month', 'count', 'win_rate', 'avg_return',
        'median_return', 'total_pnl_yuan', 'avg_holding_days',
    ]
    assert list(out['year_month']) == ['2023-01', '2023-03']
    jan = out[out['year_month'] == '2023-01'].iloc[0]
    assert jan['count'] == 2
    assert jan['win_rate'] == 0.5
    assert jan['avg_return'] == 1.0
    assert jan['total_pnl_yuan'] == 2000
    mar = out[out['year_month'] == '2023-03'].iloc[0]
    assert mar['count'] == 2
    assert mar['win_rate'] == 1.0


def test_compute_monthly_stats_empty_input():
    out = compute_monthly_stats(pd.DataFrame())
    assert list(out.columns) == [
        'year_month', 'count', 'win_rate', 'avg_return',
        'median_return', 'total_pnl_yuan', 'avg_holding_days',
    ]
    assert len(out) == 0


def test_compute_monthly_stats_missing_column():
    out = compute_monthly_stats(pd.DataFrame({'return_pct': [1.0]}))
    assert list(out.columns) == [
        'year_month', 'count', 'win_rate', 'avg_return',
        'median_return', 'total_pnl_yuan', 'avg_holding_days',
    ]
    assert len(out) == 0


def test_compute_hs300_dif_stats_basic():
    from tools.attribution import compute_hs300_dif_stats
    trades = pd.DataFrame([
        {'entry_hs300_dif_above_zero': True,  'return_pct': 5.0, 'holding_days': 10, 'status': 'completed'},
        {'entry_hs300_dif_above_zero': True,  'return_pct': -2.0, 'holding_days': 8,  'status': 'completed'},
        {'entry_hs300_dif_above_zero': False, 'return_pct': -3.0, 'holding_days': 12, 'status': 'completed'},
        {'entry_hs300_dif_above_zero': None,  'return_pct': 1.0, 'holding_days': 5,  'status': 'completed'},
    ])
    out = compute_hs300_dif_stats(trades)
    assert list(out['flag_value']) == ['True', 'False']
    true_row = out[out['flag_value'] == 'True'].iloc[0]
    assert true_row['count'] == 2
    assert true_row['win_rate'] == 0.5
    assert true_row['avg_return'] == round((5.0 + -2.0) / 2, 4)


def test_compute_hs300_bull_align_stats_basic():
    from tools.attribution import compute_hs300_bull_align_stats
    trades = pd.DataFrame([
        {'entry_hs300_bull_align': True,  'return_pct': 4.0, 'holding_days': 10, 'status': 'completed'},
        {'entry_hs300_bull_align': False, 'return_pct': -1.0, 'holding_days': 7, 'status': 'completed'},
    ])
    out = compute_hs300_bull_align_stats(trades)
    assert set(out['flag_value']) == {'True', 'False'}
    assert out[out['flag_value'] == 'True'].iloc[0]['win_rate'] == 1.0


def test_compute_stock_bull_align_stats_basic():
    from tools.attribution import compute_stock_bull_align_stats
    trades = pd.DataFrame([
        {'entry_stock_bull_align': True,  'return_pct': 3.0, 'holding_days': 9, 'status': 'completed'},
        {'entry_stock_bull_align': False, 'return_pct': -2.0, 'holding_days': 6, 'status': 'completed'},
    ])
    out = compute_stock_bull_align_stats(trades)
    assert len(out) == 2


def test_compute_stock_above_ma25_stats_basic():
    from tools.attribution import compute_stock_above_ma25_stats
    trades = pd.DataFrame([
        {'entry_stock_above_ma25': True,  'return_pct': 2.0, 'holding_days': 8,  'status': 'completed'},
        {'entry_stock_above_ma25': False, 'return_pct': -4.0, 'holding_days': 11, 'status': 'completed'},
    ])
    out = compute_stock_above_ma25_stats(trades)
    assert len(out) == 2


def test_compute_hs300_dif_stats_empty_input():
    from tools.attribution import compute_hs300_dif_stats
    out = compute_hs300_dif_stats(pd.DataFrame())
    assert out.empty
    assert list(out.columns) == ['flag_value', 'count', 'win_rate', 'avg_return', 'avg_holding_days']
