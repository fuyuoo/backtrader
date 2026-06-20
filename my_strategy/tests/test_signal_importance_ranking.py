# my_strategy/tests/test_signal_importance_ranking.py
import numpy as np
import pandas as pd
import pytest
from my_strategy.tools.trade_attribution_extra import compute_signal_importance_ranking


def _make_trades(n=200):
    """构造 200 笔交易：
    sig_a (bool) 与 return 强正相关
    sig_b (bool) 与 return 无关
    sig_c (numeric) 与 return 强正相关
    """
    rng = np.random.RandomState(42)
    a = rng.rand(n) > 0.5
    c = rng.normal(0, 1, size=n)
    ret = a * 10 + c * 5 + rng.normal(0, 2, size=n)  # mainly driven by a, c
    b = rng.rand(n) > 0.5
    return pd.DataFrame({
        'ts_code': ['X'] * n,
        'entry_date': pd.date_range('2024-01-01', periods=n, freq='D'),
        'return_pct': ret,
        'forward_return_5d': ret + rng.normal(0, 1, size=n),
        'forward_return_20d': ret + rng.normal(0, 2, size=n),
        'forward_return_60d': ret + rng.normal(0, 3, size=n),
        'sig_a': a,
        'sig_b': b,
        'sig_c': c,
    })


def test_ranking_columns():
    trades = _make_trades()
    out = compute_signal_importance_ranking(trades, signals=['sig_a', 'sig_b', 'sig_c'])
    expected_cols = {
        'signal_name', 'signal_type', 'n', 'mean_return_when_true',
        'mean_return_when_false', 'effect_size', 't_stat', 'p_value',
        'ic_mean_5d', 'ic_mean_20d', 'ic_mean_60d', 'ic_ir_60d',
        'rank_by_effect_size', 'rank_by_ic', 'rank_combined',
    }
    assert expected_cols.issubset(set(out.columns))


def test_ranking_significant_signal_first():
    trades = _make_trades()
    out = compute_signal_importance_ranking(trades, signals=['sig_a', 'sig_b', 'sig_c'])
    rank_a = out[out['signal_name'] == 'sig_a']['rank_by_effect_size'].iloc[0]
    rank_b = out[out['signal_name'] == 'sig_b']['rank_by_effect_size'].iloc[0]
    assert rank_a < rank_b  # sig_a 比 sig_b 排名靠前（rank 1 = top）


def test_ranking_ic_for_numeric():
    trades = _make_trades()
    out = compute_signal_importance_ranking(trades, signals=['sig_c'])
    # sig_c 与 return 强相关 → ic_mean_60d 应有较大绝对值
    ic = out.iloc[0]['ic_mean_60d']
    assert abs(ic) > 0.2  # 20 月分桶的均值 IC 应远大于 0


def test_ranking_skips_missing_signal():
    trades = _make_trades()
    out = compute_signal_importance_ranking(trades, signals=['sig_a', 'nonexistent_sig'])
    assert 'nonexistent_sig' not in out['signal_name'].values
    assert 'sig_a' in out['signal_name'].values
