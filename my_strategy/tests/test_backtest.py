import pandas as pd
from datetime import date
from backtest import _print_trade_stats, backfill_forward_returns


def _make_summary_df():
    return pd.DataFrame([
        {
            'ts_code': '600000.SH', 'episode': 1,
            'entry_date': date(2019, 1, 10), 'exit_date': date(2019, 2, 15),
            'holding_days': 36, 'avg_cost': 10.0, 'avg_exit_price': 11.0,
            'total_shares': 1000, 'gross_pnl': 1000.0, 'return_pct': 10.0,
            'add_count': 0, 'take_profit_count': 2, 'exit_reason': 'MA25清仓',
            'status': 'completed',
        },
        {
            'ts_code': '600001.SH', 'episode': 1,
            'entry_date': date(2019, 3, 1), 'exit_date': date(2019, 3, 20),
            'holding_days': 19, 'avg_cost': 10.0, 'avg_exit_price': 9.5,
            'total_shares': 1000, 'gross_pnl': -500.0, 'return_pct': -5.0,
            'add_count': 0, 'take_profit_count': 0, 'exit_reason': 'MA60止损',
            'status': 'completed',
        },
    ])


def test_print_trade_stats_win_rate(capsys):
    _print_trade_stats(_make_summary_df())
    out = capsys.readouterr().out
    assert '胜率：50.0%' in out


def test_print_trade_stats_payoff_ratio(capsys):
    _print_trade_stats(_make_summary_df())
    out = capsys.readouterr().out
    # avg_win=10.0, avg_loss=5.0, payoff=2.0
    assert '盈亏比：2.00' in out


def test_print_trade_stats_exit_reason(capsys):
    _print_trade_stats(_make_summary_df())
    out = capsys.readouterr().out
    assert 'MA60止损' in out
    assert 'MA25清仓' in out


def test_print_trade_stats_empty(capsys):
    """空 DataFrame 不应崩溃。"""
    _print_trade_stats(pd.DataFrame())
    out = capsys.readouterr().out
    assert '无已完成交易' in out


def test_backfill_forward_returns_5_20_60():
    indicators_by_code = {
        'A.SZ': pd.DataFrame({
            'trade_date': pd.date_range('2024-01-01', periods=80, freq='B'),
            'close': list(range(100, 180)),
        })
    }
    signals = [
        {'ts_code': 'A.SZ', 'date': pd.Timestamp('2024-01-01').date(),
         'forward_return_5d': None, 'forward_return_20d': None, 'forward_return_60d': None},
    ]
    backfill_forward_returns(signals, indicators_by_code)
    assert abs(signals[0]['forward_return_5d'] - (105 - 100) / 100) < 1e-6
    assert abs(signals[0]['forward_return_20d'] - (120 - 100) / 100) < 1e-6
    assert abs(signals[0]['forward_return_60d'] - (160 - 100) / 100) < 1e-6


def test_backfill_forward_returns_handles_missing_horizon():
    """信号触发后剩余交易日不足时，对应字段保持 None。"""
    indicators_by_code = {
        'A.SZ': pd.DataFrame({
            'trade_date': pd.date_range('2024-01-01', periods=10, freq='B'),
            'close': [100.0] * 10,
        })
    }
    signals = [
        {'ts_code': 'A.SZ', 'date': pd.Timestamp('2024-01-08').date(),
         'forward_return_5d': None, 'forward_return_20d': None, 'forward_return_60d': None},
    ]
    backfill_forward_returns(signals, indicators_by_code)
    assert signals[0]['forward_return_5d'] is None
    assert signals[0]['forward_return_20d'] is None
    assert signals[0]['forward_return_60d'] is None
