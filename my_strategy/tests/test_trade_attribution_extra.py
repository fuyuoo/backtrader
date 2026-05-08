import pandas as pd
from my_strategy.tools.trade_attribution_extra import compute_payoff_metrics, compute_signal_stability, compute_signal_correlation_matrix, compute_multi_factor_combo_stats


def _make_trades():
    return pd.DataFrame({
        'ts_code': ['A', 'B', 'C', 'D', 'E'],
        'return_pct': [10.0, 5.0, -3.0, -8.0, 0.0],
        'entry_date': pd.to_datetime(
            ['2024-01-02', '2024-02-02', '2024-03-02', '2024-04-02', '2024-05-02']),
        'exit_reason': ['MA25清仓', 'MA25清仓', 'MA60止损', 'MA60止损', 'MA25清仓'],
        'industry': ['801010', '801010', '801080', '801080', '801010'],
        'entry_hs300_dif_above_zero': [True, True, False, False, True],
        'entry_stock_bull_align': [True, False, False, False, True],
    })


def test_compute_payoff_metrics_overall_row():
    trades = _make_trades()
    out = compute_payoff_metrics(trades)
    overall = out[(out['dimension'] == 'overall') & (out['bucket'] == 'all')].iloc[0]
    assert overall['n'] == 5
    # win=10+5=15, loss=-3-8=-11, avg_win=7.5, avg_loss=-5.5
    assert abs(overall['avg_win'] - 7.5) < 1e-6
    assert abs(overall['avg_loss'] - (-5.5)) < 1e-6
    assert abs(overall['payoff_ratio'] - (7.5 / 5.5)) < 1e-6
    assert abs(overall['profit_factor'] - (15 / 11)) < 1e-6
    # expectancy = win_rate * avg_win + (1-win_rate) * avg_loss
    # win_rate = 2/5 = 0.4 (return_pct > 0); 含 0 不算赢
    # expectancy = 0.4*7.5 + 0.6*(-5.5) = 3.0 - 3.3 = -0.3
    # 但要注意 0 既不算 win 也不算 loss 时分母如何
    assert overall['n'] == 5


def test_compute_payoff_metrics_includes_exit_reason_and_year_dimensions():
    trades = _make_trades()
    out = compute_payoff_metrics(trades)
    assert (out['dimension'] == 'exit_reason').any()
    assert (out['dimension'] == 'year').any()
    assert (out['dimension'] == 'sector').any()
    assert (out['dimension'] == 'regime').any()


def test_compute_signal_stability_outputs_per_signal_per_year():
    trades = pd.DataFrame({
        'return_pct': [10, -5, 8, -3, 12, -2, 15, -8],
        'entry_date': pd.to_datetime([
            '2019-01-01', '2019-06-01', '2020-01-01', '2020-06-01',
            '2021-01-01', '2021-06-01', '2022-01-01', '2022-06-01']),
        'entry_hs300_dif_above_zero': [True, False, True, False, True, False, True, False],
        'entry_stock_bull_align': [True, True, True, True, False, False, False, False],
    })
    out = compute_signal_stability(trades, signals_whitelist=[
        'entry_hs300_dif_above_zero', 'entry_stock_bull_align'])
    assert set(out.columns) >= {
        'signal_name', 'period_year', 'n', 'win_rate', 'avg_return',
        't_stat_vs_zero', 'p_value', 'rank_within_signal',
    }
    # entry_hs300_dif_above_zero=True 在 2019/2020/2021/2022 各 1 笔
    sig_true = out[(out['signal_name'] == 'entry_hs300_dif_above_zero=True')]
    assert sorted(sig_true['period_year'].tolist()) == [2019, 2020, 2021, 2022]


def test_compute_signal_correlation_matrix_long_format():
    trades = pd.DataFrame({
        'sig_a': [1, 0, 1, 0, 1],
        'sig_b': [1, 0, 1, 0, 1],   # 完全相关
        'sig_c': [0, 1, 0, 1, 0],   # 完全反相关
    })
    out = compute_signal_correlation_matrix(trades, ['sig_a', 'sig_b', 'sig_c'])
    assert set(out.columns) >= {'signal_a', 'signal_b', 'pearson_r', 'spearman_r', 'n'}
    ab = out[(out['signal_a'] == 'sig_a') & (out['signal_b'] == 'sig_b')].iloc[0]
    ac = out[(out['signal_a'] == 'sig_a') & (out['signal_b'] == 'sig_c')].iloc[0]
    assert abs(ab['pearson_r'] - 1.0) < 1e-6
    assert abs(ac['pearson_r'] - (-1.0)) < 1e-6


def test_compute_multi_factor_combo_stats_3way_crosstab():
    trades = pd.DataFrame({
        'return_pct': [10, -5, 8, -3, 12, -2, 15, -8],
        'sig_a': [True, True, False, False, True, True, False, False],
        'sig_b': [True, False, True, False, True, False, True, False],
        'sig_c': [True, True, True, True, False, False, False, False],
    })
    combos = [('sig_a', 'sig_b', 'sig_c')]
    out = compute_multi_factor_combo_stats(trades, combos)
    assert set(out.columns) >= {
        'signal_a_name', 'signal_a_value',
        'signal_b_name', 'signal_b_value',
        'signal_c_name', 'signal_c_value',
        'n', 'win_rate', 'avg_return',
        't_stat_vs_overall', 'p_value_vs_overall', 'low_sample_warning',
    }
    # 8 笔交易共 8 种组合可能（2^3）
    assert len(out) <= 8
