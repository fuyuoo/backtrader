import numpy as np
import pandas as pd
from my_strategy.tools.portfolio_attribution import (
    compute_portfolio_risk_metrics,
    compute_losing_streak_stats,
    compute_drawdown_periods,
    compute_concurrent_positions_stats,
)


def test_compute_portfolio_risk_metrics_returns_overall_yearly_monthly():
    np.random.seed(0)
    dates = pd.date_range('2019-01-01', '2020-12-31', freq='B')
    daily_ret = pd.Series(np.random.normal(0.0005, 0.01, size=len(dates)), index=dates)
    out = compute_portfolio_risk_metrics(daily_ret)
    assert set(out.columns) >= {
        'period_type', 'period_label', 'sharpe', 'sortino', 'calmar',
        'max_drawdown', 'max_dd_duration_days',
        'annualized_return', 'annualized_vol', 'downside_vol',
    }
    assert (out['period_type'] == 'overall').any()
    assert (out['period_type'] == 'yearly').any()
    assert (out['period_type'] == 'monthly').any()
    overall = out[out['period_type'] == 'overall'].iloc[0]
    assert overall['max_drawdown'] <= 0


def test_compute_losing_streak_stats_finds_longest_streaks():
    trades = pd.DataFrame({
        'return_pct': [1, -1, -1, 1, -1, -1, -1, 1, 1, -1],
        'entry_date': pd.date_range('2024-01-01', periods=10),
    })
    out = compute_losing_streak_stats(trades)
    longest_loss = out[out['metric'] == 'longest_losing_streak']['value'].iloc[0]
    longest_win = out[out['metric'] == 'longest_winning_streak']['value'].iloc[0]
    assert longest_loss == 3
    assert longest_win == 2


def test_compute_drawdown_periods_returns_top_n_with_durations():
    dates = pd.date_range('2024-01-01', periods=20, freq='D')
    # 构造一个明显的回撤
    rets = [0.01] * 5 + [-0.02] * 5 + [0.01] * 5 + [-0.03] * 3 + [0.01] * 2
    daily_ret = pd.Series(rets, index=dates)
    out = compute_drawdown_periods(daily_ret, top_n=3)
    assert set(out.columns) >= {
        'rank', 'start_date', 'trough_date', 'recovery_date',
        'peak_value', 'trough_value', 'drawdown_pct',
        'duration_days', 'recovery_days',
    }
    assert len(out) <= 3
    assert all(out['drawdown_pct'] < 0)


def test_compute_concurrent_positions_stats_summary_and_buckets():
    log = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=10),
        'count': [50, 60, 100, 100, 150, 180, 200, 200, 90, 50],
    })
    out = compute_concurrent_positions_stats(log, max_positions=200)
    assert (out['metric_type'] == 'summary').any()
    assert (out['metric_type'] == 'position_count_bucket').any()
    max_row = out[(out['metric_type'] == 'summary') & (out['bucket'] == 'max')].iloc[0]
    assert max_row['value'] == 200
    pct_at_cap = out[
        (out['metric_type'] == 'summary') & (out['bucket'] == 'pct_at_cap')
    ].iloc[0]
    # 200 出现 2 次 / 10 天 = 0.2
    assert abs(pct_at_cap['value'] - 0.2) < 1e-6


def test_compute_concurrent_positions_stats_accepts_list_of_ints():
    log = [50, 60, 100, 100, 150, 180, 200, 200, 90, 50]
    out = compute_concurrent_positions_stats(log, max_positions=200)
    max_row = out[(out['metric_type'] == 'summary') & (out['bucket'] == 'max')].iloc[0]
    assert max_row['value'] == 200
