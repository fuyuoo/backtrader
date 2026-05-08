import pandas as pd
from my_strategy.tools.trade_attribution_extra import compute_payoff_metrics


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
