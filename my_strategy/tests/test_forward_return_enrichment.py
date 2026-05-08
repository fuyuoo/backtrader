# my_strategy/tests/test_forward_return_enrichment.py
"""验证 forward_return_5d/20d/60d 写入 trade_summary。"""
import pandas as pd
from my_strategy.backtest import _add_forward_returns


def _make_daily(prices):
    return pd.DataFrame({
        'trade_date': pd.date_range('2024-01-02', periods=len(prices), freq='B'),
        'close': prices,
    })


def test_forward_return_5d():
    daily_lookup = {
        'A.SZ': _make_daily([10.0, 10.5, 11.0, 11.0, 11.0, 12.0, 13.0]),
    }
    summary = pd.DataFrame({
        'ts_code': ['A.SZ'],
        'entry_date': pd.to_datetime(['2024-01-02']),
    })
    out = _add_forward_returns(summary, daily_lookup, windows=(5,))
    # 1/2 close=10, +5 trade days → close=12, return = (12-10)/10 = 20%
    assert abs(out.iloc[0]['forward_return_5d'] - 20.0) < 1e-6


def test_forward_return_handles_missing_ts_code():
    daily_lookup = {}  # empty
    summary = pd.DataFrame({
        'ts_code': ['A.SZ'],
        'entry_date': pd.to_datetime(['2024-01-02']),
    })
    out = _add_forward_returns(summary, daily_lookup, windows=(5, 20, 60))
    assert pd.isna(out.iloc[0]['forward_return_5d'])
    assert pd.isna(out.iloc[0]['forward_return_60d'])


def test_forward_return_handles_short_series():
    """+60 trade days 超出数据末端 → NaN。"""
    daily_lookup = {'A.SZ': _make_daily([10.0] * 10)}
    summary = pd.DataFrame({
        'ts_code': ['A.SZ'],
        'entry_date': pd.to_datetime(['2024-01-02']),
    })
    out = _add_forward_returns(summary, daily_lookup, windows=(5, 20, 60))
    assert pd.notna(out.iloc[0]['forward_return_5d'])
    assert pd.isna(out.iloc[0]['forward_return_60d'])
