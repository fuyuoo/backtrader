"""验证 trade_summary 4 个新列计算正确。"""
import pandas as pd
import pytest
from my_strategy.backtest import _add_trade_summary_metrics


def _hs300_daily():
    """合成 HS300 close 序列：2024-01-02 ~ 2024-01-15，每天 +1%。"""
    return pd.DataFrame({
        'trade_date': pd.date_range('2024-01-02', periods=10, freq='B'),
        'close': [100 * (1.01 ** i) for i in range(10)],
    })


def test_mfe_minus_realized_basic():
    summary = pd.DataFrame({
        'episode': [1],
        'entry_date': pd.to_datetime(['2024-01-02']),
        'exit_date': pd.to_datetime(['2024-01-08']),
        'return_pct': [5.0],
        'mfe_pct': [10.0],
    })
    out = _add_trade_summary_metrics(summary, hs300_daily=_hs300_daily())
    assert abs(out.iloc[0]['mfe_minus_realized'] - 5.0) < 1e-9


def test_exit_efficiency_when_mfe_positive():
    summary = pd.DataFrame({
        'episode': [1, 2],
        'entry_date': pd.to_datetime(['2024-01-02', '2024-01-02']),
        'exit_date': pd.to_datetime(['2024-01-08', '2024-01-08']),
        'return_pct': [5.0, -3.0],
        'mfe_pct': [10.0, 0.0],  # 第二笔 mfe=0 → exit_efficiency NaN
    })
    out = _add_trade_summary_metrics(summary, hs300_daily=_hs300_daily())
    assert abs(out.iloc[0]['exit_efficiency'] - 0.5) < 1e-9
    assert pd.isna(out.iloc[1]['exit_efficiency'])


def test_benchmark_return_during_holding():
    """HS300 从 1/2 到 1/8 涨 5%（每天 +1%，5 个交易日）。"""
    summary = pd.DataFrame({
        'episode': [1],
        'entry_date': pd.to_datetime(['2024-01-02']),
        'exit_date': pd.to_datetime(['2024-01-08']),
        'return_pct': [10.0],
        'mfe_pct': [12.0],
    })
    out = _add_trade_summary_metrics(summary, hs300_daily=_hs300_daily())
    # 1/2 close=100, 1/8 close ≈ 100 * 1.01^4 ≈ 104.06 (1/2 是 0 天后)
    # bench_return = (104.06 - 100) / 100 ≈ 4.06%
    bench = out.iloc[0]['benchmark_return_during_holding']
    assert 4.0 < bench < 4.2


def test_per_trade_alpha():
    summary = pd.DataFrame({
        'episode': [1],
        'entry_date': pd.to_datetime(['2024-01-02']),
        'exit_date': pd.to_datetime(['2024-01-08']),
        'return_pct': [10.0],
        'mfe_pct': [12.0],
    })
    out = _add_trade_summary_metrics(summary, hs300_daily=_hs300_daily())
    # alpha = 10 - bench(~4.06) ≈ 5.94
    assert 5.5 < out.iloc[0]['per_trade_alpha'] < 6.5


def test_handles_missing_hs300():
    """HS300 数据为 None → benchmark_return / per_trade_alpha 为 NaN，不抛错。"""
    summary = pd.DataFrame({
        'episode': [1],
        'entry_date': pd.to_datetime(['2024-01-02']),
        'exit_date': pd.to_datetime(['2024-01-08']),
        'return_pct': [10.0],
        'mfe_pct': [12.0],
    })
    out = _add_trade_summary_metrics(summary, hs300_daily=None)
    assert pd.isna(out.iloc[0]['benchmark_return_during_holding'])
    assert pd.isna(out.iloc[0]['per_trade_alpha'])
    # 前两列仍应正确
    assert abs(out.iloc[0]['mfe_minus_realized'] - 2.0) < 1e-9


def test_handles_open_position_no_exit_date():
    """exit_date NaN（未平仓）→ 后两列 NaN，前两列 NaN（mfe_pct 仍可能有但定义不全）。"""
    summary = pd.DataFrame({
        'episode': [1],
        'entry_date': pd.to_datetime(['2024-01-02']),
        'exit_date': [pd.NaT],
        'return_pct': [pd.NA],
        'mfe_pct': [5.0],
    })
    out = _add_trade_summary_metrics(summary, hs300_daily=_hs300_daily())
    # 未平仓应不抛错；4 列均为 NaN
    assert pd.isna(out.iloc[0]['mfe_minus_realized'])
    assert pd.isna(out.iloc[0]['exit_efficiency'])
    assert pd.isna(out.iloc[0]['benchmark_return_during_holding'])
    assert pd.isna(out.iloc[0]['per_trade_alpha'])
