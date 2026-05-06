import pandas as pd
import numpy as np
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from calc_indicators import compute_indicators


def make_ohlcv(n=100, base_close=10.0):
    """生成简单的合成 OHLCV 数据。"""
    dates = pd.date_range('2020-01-01', periods=n, freq='B')
    closes = [base_close + i * 0.01 for i in range(n)]
    df = pd.DataFrame({
        'trade_date': dates,
        'open': closes,
        'high': [c + 0.1 for c in closes],
        'low': [c - 0.1 for c in closes],
        'close': closes,
        'volume': [100000] * n,
    })
    return df


def test_output_columns():
    df = make_ohlcv(100)
    result = compute_indicators(df)
    expected_cols = {'trade_date', 'open', 'high', 'low', 'close', 'volume',
                     'ma25', 'ma60', 'dea'}
    assert expected_cols.issubset(set(result.columns))


def test_ma25_value():
    df = make_ohlcv(100)
    result = compute_indicators(df)
    assert pd.notna(result.loc[24, 'ma25'])
    assert pd.isna(result.loc[23, 'ma25'])
    expected = df['close'].iloc[:25].mean()
    assert abs(result.loc[24, 'ma25'] - expected) < 1e-6


def test_row_count_unchanged():
    df = make_ohlcv(80)
    result = compute_indicators(df)
    assert len(result) == len(df)
