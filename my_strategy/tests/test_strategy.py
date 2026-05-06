"""
使用合成价格数据验证策略的关键信号触发。
"""
import backtrader as bt
import pandas as pd
import numpy as np
from src.strategy import StockData, MyStrategy


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


def _make_signal_data():
    """构造一只能在某日触发 5 条必要条件的合成股票。

    触发条件设计（bar 70，index=70）：
      - close=10.8 < prev_close=11.0 → 阴线 ✓
      - close=10.8 > ma60=10.0 → ✓
      - dea[70]=0.05 > 0 → ✓
      - past_deas[1..5] = dea[69..65] 含 -0.1 → ✓
    """
    import pandas as pd
    n = 80
    dates = pd.date_range('2023-01-01', periods=n, freq='B')
    # bar 0-68: 稳定 10.0；bar 69: 涨到 11.0；bar 70: 回落到 10.8（阴线触发信号）
    close = [10.0] * 69 + [11.0, 10.8] + [11.2] * (n - 71)
    ma60 = [None] * 59 + [10.0] * (n - 59)
    ma25 = [None] * 24 + [10.0] * (n - 24)
    # dea: 前 69 根为负，bar 70 起转正；past_deas 回看 5 天 (bar65-69) 全为负
    dea = [-0.1] * 69 + [0.05] + [0.1] * (n - 70)
    df = pd.DataFrame({
        'datetime': dates,
        'open': close,
        'high': [c + 0.1 for c in close],
        'low': [c - 0.1 for c in close],
        'close': close,
        'volume': [1000] * n,
        'ma25': ma25,
        'ma60': ma60,
        'dea': dea,
    })
    df = df.set_index('datetime')
    return df


def test_strategy_writes_signals_log():
    """run cerebro on synthetic data and verify signals_log is populated."""
    import backtrader as bt
    import pandas as pd
    df = _make_signal_data()
    sector_map = {'TEST.SZ': '801010.SI'}

    cerebro = bt.Cerebro()
    cerebro.addstrategy(MyStrategy, sector_map=sector_map)
    data = StockData(dataname=df, name='TEST.SZ')
    cerebro.adddata(data)
    cerebro.broker.setcash(1_000_000)
    strats = cerebro.run()

    strat = strats[0]
    assert hasattr(strat, 'signals_log')
    assert len(strat.signals_log) >= 1
    rec = strat.signals_log[0]
    assert rec['ts_code'] == 'TEST.SZ'
    assert rec['sector'] == '801010.SI'
    assert 'ma25' in rec
    assert 'was_bought' in rec
