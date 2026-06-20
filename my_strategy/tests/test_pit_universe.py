# my_strategy/tests/test_pit_universe.py
"""PIT universe 过滤逻辑单元测试。

测试 _resolve_pit_window 函数：给定一只股票的 list_date / delist_date 与 backtest 的全局窗口，
返回该股的有效 (fromdate, todate) tuple。
"""
import pandas as pd
from datetime import datetime
from my_strategy.backtest import _resolve_pit_window


def _d(s):
    return pd.to_datetime(s)


def test_pit_window_stock_predates_backtest():
    """股票早就上市 → 用 backtest 全窗口。"""
    fromdate, todate = _resolve_pit_window(
        list_date='19910403', delist_date=pd.NA,
        bt_start=_d('2010-01-01'), bt_end=_d('2025-12-31'),
    )
    assert fromdate == _d('2010-01-01')
    assert todate == _d('2025-12-31')


def test_pit_window_stock_lists_during_backtest():
    """股票在 backtest 窗口内才上市 → 用上市日做起点。"""
    fromdate, todate = _resolve_pit_window(
        list_date='20150601', delist_date=pd.NA,
        bt_start=_d('2010-01-01'), bt_end=_d('2025-12-31'),
    )
    assert fromdate == _d('2015-06-01')
    assert todate == _d('2025-12-31')


def test_pit_window_stock_delisted_during_backtest():
    """股票在 backtest 窗口内退市 → 用退市日做终点。"""
    fromdate, todate = _resolve_pit_window(
        list_date='20050101', delist_date='20180630',
        bt_start=_d('2010-01-01'), bt_end=_d('2025-12-31'),
    )
    assert fromdate == _d('2010-01-01')
    assert todate == _d('2018-06-30')


def test_pit_window_stock_lists_after_backtest():
    """股票在 backtest 窗口结束后才上市 → 返回 None（应排除该股）。"""
    result = _resolve_pit_window(
        list_date='20300101', delist_date=pd.NA,
        bt_start=_d('2010-01-01'), bt_end=_d('2025-12-31'),
    )
    assert result is None


def test_pit_window_stock_delisted_before_backtest():
    """股票在 backtest 窗口前已退市 → 返回 None。"""
    result = _resolve_pit_window(
        list_date='19950101', delist_date='20050601',
        bt_start=_d('2010-01-01'), bt_end=_d('2025-12-31'),
    )
    assert result is None


def test_pit_window_missing_list_date_uses_backtest_start():
    """list_date 缺失（NaN）→ 退化为 backtest 全窗口（保守，不排除）。"""
    fromdate, todate = _resolve_pit_window(
        list_date=pd.NA, delist_date=pd.NA,
        bt_start=_d('2010-01-01'), bt_end=_d('2025-12-31'),
    )
    assert fromdate == _d('2010-01-01')
    assert todate == _d('2025-12-31')


def test_pit_window_float_list_date():
    """list_date 以浮点格式存储（pandas CSV读回）→ 正确解析。"""
    fromdate, todate = _resolve_pit_window(
        list_date=19910403.0, delist_date=pd.NA,
        bt_start=_d('2010-01-01'), bt_end=_d('2025-12-31'),
    )
    assert fromdate == _d('2010-01-01')  # 早于 bt_start → 用 bt_start
    assert todate == _d('2025-12-31')
