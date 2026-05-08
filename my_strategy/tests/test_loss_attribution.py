# my_strategy/tests/test_loss_attribution.py
import numpy as np
import pandas as pd
import pytest
from my_strategy.tools.trade_attribution_extra import compute_loss_attribution


def _make_trades():
    """构造数据：sig_x = False 时 return 总是负，sig_x = True 时随机。"""
    rng = np.random.RandomState(0)
    n = 200
    sig_x = rng.rand(n) > 0.5
    ret = np.where(sig_x, rng.normal(5, 5, n), rng.normal(-5, 5, n))
    return pd.DataFrame({
        'return_pct': ret,
        'sig_x': sig_x,
        'sig_y': rng.rand(n) > 0.5,  # 与 return 无关
    })


def test_loss_attribution_columns():
    trades = _make_trades()
    out = compute_loss_attribution(trades, signals=['sig_x', 'sig_y'])
    expected = {'signal_name', 'signal_value', 'freq_in_universe',
                'freq_in_losses', 'freq_in_heavy_losses',
                'lift_loss', 'lift_heavy_loss',
                'chi2_stat', 'p_value',
                'n_universe', 'n_losses', 'n_heavy_losses'}
    assert expected.issubset(set(out.columns))


def test_loss_attribution_finds_high_lift_for_loss_signal():
    trades = _make_trades()
    out = compute_loss_attribution(trades, signals=['sig_x', 'sig_y'])
    sig_x_false = out[(out['signal_name'] == 'sig_x') & (out['signal_value'] == 'False')].iloc[0]
    sig_y_false = out[(out['signal_name'] == 'sig_y') & (out['signal_value'] == 'False')].iloc[0]
    assert sig_x_false['lift_loss'] > sig_y_false['lift_loss']
    assert sig_x_false['p_value'] < 0.05  # 显著相关


def test_loss_attribution_returns_rows_on_no_losses():
    trades = pd.DataFrame({'return_pct': [1, 2, 3], 'sig_x': [True, True, False]})
    out = compute_loss_attribution(trades, signals=['sig_x'])
    # 无亏损交易，n_losses=0；输出仍应有行（freq_in_losses=NaN）
    assert (out['n_losses'] == 0).all()
    assert out['freq_in_losses'].isna().all()
    assert out['lift_loss'].isna().all()
