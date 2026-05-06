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


from my_strategy.src.calc_indicators import (
    merge_fundamentals,
    add_single_stock_factors,
    merge_sector_momentum,
)


def test_merge_fundamentals_aligns_by_ann_date():
    daily = pd.DataFrame({
        'trade_date': pd.to_datetime(['2024-04-29', '2024-04-30', '2024-05-06']),
        'close': [10.0, 10.1, 10.2],
    })
    daily_basic = pd.DataFrame({
        'trade_date': pd.to_datetime(['2024-04-29', '2024-04-30', '2024-05-06']),
        'pe_ttm': [12.0, 12.1, 12.2],
        'pb': [1.5, 1.51, 1.52],
        'total_mv': [1e5, 1.01e5, 1.02e5],
    })
    # ann_date = 20240430，2024-04-29 之前不可见，从 2024-04-30 起可见
    fina = pd.DataFrame({
        'ann_date': pd.to_datetime(['2024-04-30']),
        'end_date': pd.to_datetime(['2024-03-31']),
        'roe': [12.5],
        'netprofit_yoy': [15.0],
    })

    out = merge_fundamentals(daily, daily_basic, fina)

    assert out.loc[out['trade_date'] == pd.Timestamp('2024-04-29'), 'roe'].isna().all()
    assert out.loc[out['trade_date'] == pd.Timestamp('2024-04-30'), 'roe'].iloc[0] == 12.5
    assert out.loc[out['trade_date'] == pd.Timestamp('2024-05-06'), 'roe'].iloc[0] == 12.5
    # daily_basic 字段直接合并
    assert out.loc[out['trade_date'] == pd.Timestamp('2024-04-30'), 'pe_ttm'].iloc[0] == 12.1


def test_merge_fundamentals_no_fina_data():
    daily = pd.DataFrame({
        'trade_date': pd.to_datetime(['2024-04-30']),
        'close': [10.0],
    })
    daily_basic = pd.DataFrame({
        'trade_date': pd.to_datetime(['2024-04-30']),
        'pe_ttm': [12.1], 'pb': [1.51], 'total_mv': [1e5],
    })
    fina_empty = pd.DataFrame(columns=['ann_date', 'end_date', 'roe', 'netprofit_yoy'])

    out = merge_fundamentals(daily, daily_basic, fina_empty)
    assert out['roe'].isna().all()
    assert out['pe_ttm'].iloc[0] == 12.1


def test_add_single_stock_factors_computes_momentum_and_dist():
    import pandas as pd
    df = pd.DataFrame({
        'trade_date': pd.date_range('2024-01-01', periods=70),
        'close': list(range(100, 170)),
        'ma60': [None] * 60 + [130.0] * 10,
        'dea': [0.5] * 70,
    })
    out = add_single_stock_factors(df)
    assert 'factor_momentum_60d' in out.columns
    assert 'factor_ma60_dist' in out.columns
    assert 'factor_macd_strength' in out.columns
    # 最后一行：close[-1]=169, close[-61]=109 → (169-109)/109
    assert abs(out['factor_momentum_60d'].iloc[-1] - (169 - 109) / 109) < 1e-6
    # ma60_dist 最后一行：(169 - 130) / 130
    assert abs(out['factor_ma60_dist'].iloc[-1] - (169 - 130) / 130) < 1e-6
    assert out['factor_macd_strength'].iloc[-1] == 0.5


def test_merge_sector_momentum_aligns_by_date():
    import pandas as pd
    sector_dates = pd.date_range('2023-09-01', periods=70)
    # daily 日期落在 sector_idx 有动量值的范围内（第 61 行起，即 2023-10-31 之后）
    daily = pd.DataFrame({
        'trade_date': pd.to_datetime([sector_dates[61], sector_dates[62]]),
        'close': [10.0, 10.1],
    })
    sector_idx = pd.DataFrame({
        'trade_date': sector_dates,
        'close': list(range(1000, 1070)),
    })

    out = merge_sector_momentum(daily, sector_idx)
    assert 'factor_sector_momentum_60d' in out.columns
    assert not out['factor_sector_momentum_60d'].isna().all()
