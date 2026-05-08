import numpy as np
import pandas as pd
from my_strategy.tools.portfolio_attribution import compute_portfolio_risk_metrics


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
