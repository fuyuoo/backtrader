import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from src.calc_indicators import compute_indicators, compute_weekly_monthly_indicators


def make_ohlcv(n=100, base_close=10.0):
    """生成简单的合成 OHLCV 数据（单调上涨）。"""
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


def make_random_ohlcv(n, start='2020-01-01', seed=42):
    """生成带随机游走的合成 OHLCV，含 circ_mv 字段。"""
    np.random.seed(seed)
    dates = pd.date_range(start, periods=n, freq='B')
    close = 10 + np.cumsum(np.random.randn(n) * 0.1)
    return pd.DataFrame({
        'trade_date': dates,
        'open': close * 0.99,
        'high': close * 1.01,
        'low': close * 0.98,
        'close': close,
        'volume': 1000,
        'amount': close * 1000,
        'pct_chg': 0.0,
        'circ_mv': 5_000_000.0,  # 5,000,000 万元 = 500 亿元
    })


# ── compute_indicators ───────────────────────────────────────────────────────

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


def test_circ_mv_conversion():
    """circ_mv 万元 → 亿元 的换算。"""
    df = make_random_ohlcv(100)
    result = compute_indicators(df)
    assert 'circ_mv' in result.columns
    # 5,000,000 万元 ÷ 10000 → 500.0 亿元
    assert abs(result['circ_mv'].iloc[-1] - 500.0) < 0.01


# ── compute_weekly_monthly_indicators ────────────────────────────────────────

def test_weekly_monthly_columns_added():
    """周线/月线 CSV 存在时，应 merge 出对应的 KDJ_J / MACD 区间字段。"""
    df = make_random_ohlcv(300)
    result = compute_indicators(df)

    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        (data_dir / 'weekly').mkdir()
        (data_dir / 'monthly').mkdir()

        weekly = df.set_index('trade_date')['close'].resample('W').last().dropna().reset_index()
        weekly.columns = ['trade_date', 'close']
        weekly['open'] = weekly['close'] * 0.99
        weekly['high'] = weekly['close'] * 1.01
        weekly['low'] = weekly['close'] * 0.98
        weekly.to_csv(data_dir / 'weekly' / 'TEST.SH.csv', index=False)

        monthly = df.set_index('trade_date')['close'].resample('ME').last().dropna().reset_index()
        monthly.columns = ['trade_date', 'close']
        monthly['open'] = monthly['close'] * 0.99
        monthly['high'] = monthly['close'] * 1.01
        monthly['low'] = monthly['close'] * 0.98
        monthly.to_csv(data_dir / 'monthly' / 'TEST.SH.csv', index=False)

        out = compute_weekly_monthly_indicators('TEST.SH', result, data_dir)

    assert 'week_kdj_j' in out.columns
    assert 'week_macd_zone' in out.columns
    assert 'month_macd_zone' in out.columns
    assert out['week_kdj_j'].notna().any()
    assert out['week_macd_zone'].notna().any()
    assert out['month_macd_zone'].notna().any()


def test_missing_weekly_monthly_files():
    """周线/月线 CSV 不存在时返回的列应全为 NaN，不抛错。"""
    df = make_random_ohlcv(100)
    result = compute_indicators(df)
    with tempfile.TemporaryDirectory() as tmpdir:
        out = compute_weekly_monthly_indicators('NOFILE.SH', result, tmpdir)
    assert 'week_kdj_j' in out.columns
    assert out['week_kdj_j'].isna().all()
    assert out['week_macd_zone'].isna().all()
    assert out['month_macd_zone'].isna().all()
