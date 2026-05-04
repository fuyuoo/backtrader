"""
使用合成价格数据验证策略的关键信号触发。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import backtrader as bt
import pandas as pd
import numpy as np
from strategy import StockData, MyStrategy


def make_feed(n=150, start='2020-01-01'):
    """生成合成数据：稳定上涨，MA60之上，制造一次阴线+DEA上穿信号。"""
    dates = pd.date_range(start, periods=n, freq='B')
    closes = [10.0 + i * 0.05 for i in range(n)]

    prev_closes = [np.nan] + closes[:-1]

    ma60 = [np.nan] * 59 + [sum(closes[i-59:i+1]) / 60 for i in range(59, n)]
    ma25 = [np.nan] * 24 + [sum(closes[i-24:i+1]) / 25 for i in range(24, n)]

    # DEA: negative for first 70 bars, positive after (crossing 0)
    dea = [-0.1] * 70 + [0.1] * (n - 70)

    # Make bar 70 a bearish candle (close < prev_close)
    closes[70] = closes[70] - 0.2

    df = pd.DataFrame({
        'trade_date': dates,
        'open': closes,
        'high': [c + 0.05 for c in closes],
        'low': [c - 0.05 for c in closes],
        'close': closes,
        'volume': [1000000] * n,
        'ma25': ma25,
        'ma60': ma60,
        'dea': dea,
        'prev_close': prev_closes,
    })
    df.index = df['trade_date']
    return df


def run_backtest(df, initial_cash=1_000_000, max_positions=10,
                 take_profit_1_pct=0.05, take_profit_2_pct=0.10,
                 dea_lookback_days=5):
    cerebro = bt.Cerebro()
    feed = StockData(dataname=df,
                     fromdate=df.index[0],
                     todate=df.index[-1])
    cerebro.adddata(feed, name='TEST')
    cerebro.broker.set_cash(initial_cash)
    cerebro.addstrategy(
        MyStrategy,
        initial_cash=initial_cash,
        max_positions=max_positions,
        take_profit_1_pct=take_profit_1_pct,
        take_profit_2_pct=take_profit_2_pct,
        dea_lookback_days=dea_lookback_days,
    )
    results = cerebro.run()
    return results[0]


def test_entry_signal_triggers_buy():
    """入场信号（阴线+DEA上穿+close>MA60）应触发一笔买入订单。"""
    df = make_feed()
    strat = run_backtest(df)
    buy_orders = [o for o in strat.order_log if o['side'] == 'buy']
    assert len(buy_orders) >= 1, "应至少有一笔买入订单"


def test_take_profit_1_triggers():
    """持仓盈利≥5%时应触发第一次止盈卖出。"""
    df = make_feed()
    strat = run_backtest(df)
    sell_orders = [o for o in strat.order_log if o['side'] == 'sell']
    assert len(sell_orders) >= 1, "应至少有一笔卖出订单（止盈）"


def test_order_log_has_reason_and_episode():
    """order_log 每条记录应含 reason 和 episode 字段。"""
    df = make_feed()
    strat = run_backtest(df)
    assert len(strat.order_log) > 0
    for entry in strat.order_log:
        assert 'reason' in entry, f"缺少 reason 字段: {entry}"
        assert 'episode' in entry, f"缺少 episode 字段: {entry}"
        assert entry['reason'] in (
            'initial_buy', 'add_on', 'take_profit_1', 'take_profit_2',
            'MA60_stop', 'MA25_stop', 'unknown'
        ), f"未知 reason: {entry['reason']}"


def test_trade_log_has_required_keys():
    """trade_log 应存在且每条记录含所有必要字段。"""
    df = make_feed()
    strat = run_backtest(df)
    assert hasattr(strat, 'trade_log'), "strategy 缺少 trade_log 属性"
    # make_feed 价格持续上涨，持仓不会在回测内关闭，stop() 应产生 incomplete 条目
    assert len(strat.trade_log) >= 1, "trade_log 应至少有一条记录"
    required_keys = {
        'ts_code', 'episode', 'entry_date', 'exit_date', 'holding_days',
        'avg_cost', 'avg_exit_price', 'total_shares', 'gross_pnl',
        'return_pct', 'add_count', 'take_profit_count', 'exit_reason', 'status'
    }
    for entry in strat.trade_log:
        missing = required_keys - set(entry.keys())
        assert not missing, f"trade_log 条目缺少字段: {missing}"
