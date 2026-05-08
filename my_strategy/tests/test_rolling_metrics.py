# my_strategy/tests/test_rolling_metrics.py
import numpy as np
import pandas as pd
import pytest
from my_strategy.tools.portfolio_attribution import compute_rolling_metrics


def test_rolling_metrics_columns():
    rng = np.random.RandomState(0)
    daily_ret = pd.Series(
        rng.normal(0.0005, 0.01, size=300),
        index=pd.date_range('2024-01-01', periods=300, freq='B'),
    )
    out = compute_rolling_metrics(daily_ret, window=252)
    expected = {'window_end_date', 'window_size_days', 'n_trading_days',
                'sharpe', 'sortino', 'win_rate_daily', 'max_dd_in_window'}
    assert expected.issubset(set(out.columns))


def test_rolling_metrics_returns_post_window_rows():
    rng = np.random.RandomState(0)
    daily_ret = pd.Series(rng.normal(0, 0.01, size=300),
                          index=pd.date_range('2024-01-01', periods=300, freq='B'))
    out = compute_rolling_metrics(daily_ret, window=252)
    # 300 - 252 + 1 = 49 行
    assert len(out) == 49
    assert out['n_trading_days'].iloc[0] == 252


def test_rolling_metrics_uptrend_positive_sharpe():
    """持续上升 daily_ret → rolling Sharpe 应 >= 0。"""
    daily_ret = pd.Series([0.001] * 300,
                          index=pd.date_range('2024-01-01', periods=300, freq='B'))
    out = compute_rolling_metrics(daily_ret, window=252)
    # 所有窗口都是恒定收益，Sharpe 是 inf 或非常大；这里只要求 >= 0
    assert (out['sharpe'].fillna(0) >= 0).all()


def test_rolling_metrics_max_dd_negative():
    """前半上升后半下降 → max_dd 出现负值。"""
    daily_ret = pd.Series([0.005] * 200 + [-0.005] * 100,
                          index=pd.date_range('2024-01-01', periods=300, freq='B'))
    out = compute_rolling_metrics(daily_ret, window=252)
    assert (out['max_dd_in_window'] < 0).any()
