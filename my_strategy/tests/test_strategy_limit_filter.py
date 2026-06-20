# my_strategy/tests/test_strategy_limit_filter.py
"""涨跌停过滤逻辑单元测试。
直接测试 _is_limit_up / _is_limit_down 静态逻辑，不启动完整 cerebro。
"""
import pytest
from unittest.mock import MagicMock
from my_strategy.src.strategy import MyStrategy


def _mock_data(closes):
    """构造一个 mock data feed，data.close[0] 取最后一个，data.close[-1] 取倒数第二个。"""
    data = MagicMock()
    data.__len__.return_value = len(closes)
    data.close.__getitem__.side_effect = lambda i: closes[i - 1] if i <= 0 else None
    return data


def test_is_limit_up_detects_995pct():
    data = _mock_data([10.0, 11.0])  # +10%
    assert MyStrategy._is_limit_up(None, data) is True


def test_is_limit_up_misses_98pct():
    data = _mock_data([10.0, 10.95])  # +9.5%
    assert MyStrategy._is_limit_up(None, data) is False


def test_is_limit_down_detects_negative_995pct():
    data = _mock_data([10.0, 9.0])  # -10%
    assert MyStrategy._is_limit_down(None, data) is True


def test_is_limit_down_misses_negative_98pct():
    data = _mock_data([10.0, 9.05])  # -9.5%
    assert MyStrategy._is_limit_down(None, data) is False


def test_is_limit_handles_short_data():
    data = MagicMock()
    data.__len__.return_value = 0
    assert MyStrategy._is_limit_up(None, data) is False
    assert MyStrategy._is_limit_down(None, data) is False
