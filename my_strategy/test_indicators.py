import pandas as pd
import tempfile
from pathlib import Path
from calc_indicators import compute_indicators, compute_weekly_monthly_indicators


def _make_ohlc(n, start='2020-01-01'):
    dates = pd.date_range(start, periods=n, freq='B')
    import numpy as np
    np.random.seed(42)
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


def test_circ_mv_conversion():
    df = _make_ohlc(100)
    result = compute_indicators(df)
    assert 'circ_mv' in result.columns
    # 5,000,000 万元 ÷ 10000 → 500.0 亿元
    assert abs(result['circ_mv'].iloc[-1] - 500.0) < 0.01


def test_weekly_monthly_columns_added():
    df = _make_ohlc(300)
    result = compute_indicators(df)

    with tempfile.TemporaryDirectory() as tmpdir:
        # 生成周线和月线 CSV
        weekly = df.set_index('trade_date')['close'].resample('W').last().dropna().reset_index()
        weekly.columns = ['trade_date', 'close']
        weekly['open'] = weekly['close'] * 0.99
        weekly['high'] = weekly['close'] * 1.01
        weekly['low'] = weekly['close'] * 0.98
        weekly.to_csv(Path(tmpdir) / 'TEST.SH_weekly.csv', index=False)

        monthly = df.set_index('trade_date')['close'].resample('ME').last().dropna().reset_index()
        monthly.columns = ['trade_date', 'close']
        monthly['open'] = monthly['close'] * 0.99
        monthly['high'] = monthly['close'] * 1.01
        monthly['low'] = monthly['close'] * 0.98
        monthly.to_csv(Path(tmpdir) / 'TEST.SH_monthly.csv', index=False)

        out = compute_weekly_monthly_indicators('TEST.SH', result, tmpdir)

    assert 'week_kdj_j' in out.columns
    assert 'week_macd_zone' in out.columns
    assert 'month_macd_zone' in out.columns
    # 非全 NaN（有足够数据预热后应有值）
    assert out['week_kdj_j'].notna().any()
    assert out['week_macd_zone'].notna().any()
    assert out['month_macd_zone'].notna().any()


def test_missing_weekly_monthly_files():
    df = _make_ohlc(100)
    result = compute_indicators(df)
    with tempfile.TemporaryDirectory() as tmpdir:
        out = compute_weekly_monthly_indicators('NOFILE.SH', result, tmpdir)
    assert 'week_kdj_j' in out.columns
    assert out['week_kdj_j'].isna().all()
    assert out['week_macd_zone'].isna().all()
    assert out['month_macd_zone'].isna().all()


if __name__ == '__main__':
    test_circ_mv_conversion()
    test_weekly_monthly_columns_added()
    test_missing_weekly_monthly_files()
    print("ALL TESTS PASSED")
