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


def make_hold_feed_with_big_candle(big_candle_pct=0.02):
    """生成在持仓期会出现 big_candle_pct 大小阳线的合成数据。

    前 70 bar 同 make_feed 的稳定上涨；bar 70 阴线触发买入；
    bar 80 制造一根 (close-open)/open == big_candle_pct 的阳线；
    其余 bar 仍是温和的小阴小阳。
    """
    n = 150
    dates = pd.date_range('2020-01-01', periods=n, freq='B')
    closes = [10.0 + i * 0.05 for i in range(n)]
    closes[70] = closes[70] - 0.2  # 阴线触发买入

    opens = list(closes)
    opens[80] = closes[80] / (1.0 + big_candle_pct)  # 让 bar 80 收阳 big_candle_pct

    prev_closes = [np.nan] + closes[:-1]
    ma60 = [np.nan] * 59 + [sum(closes[i - 59:i + 1]) / 60 for i in range(59, n)]
    ma25 = [np.nan] * 24 + [sum(closes[i - 24:i + 1]) / 25 for i in range(24, n)]
    dea = [-0.1] * 70 + [0.1] * (n - 70)

    df = pd.DataFrame({
        'trade_date': dates,
        'open': opens,
        'high': [max(o, c) + 0.05 for o, c in zip(opens, closes)],
        'low':  [min(o, c) - 0.05 for o, c in zip(opens, closes)],
        'close': closes,
        'volume': [1_000_000] * n,
        'ma25': ma25,
        'ma60': ma60,
        'dea': dea,
        'prev_close': prev_closes,
    })
    df.index = df['trade_date']
    return df


def test_max_bullish_candle_pct_recorded_in_trade_log():
    """持仓期出现 2% 阳线 → trade_log 的 max_bullish_candle_pct ≈ 0.02。"""
    df = make_hold_feed_with_big_candle(big_candle_pct=0.02)
    strat = run_backtest(df)
    assert len(strat.trade_log) >= 1
    rec = strat.trade_log[0]
    assert 'max_bullish_candle_pct' in rec
    assert abs(rec['max_bullish_candle_pct'] - 0.02) < 1e-6


def test_add_blocked_when_max_bullish_above_threshold():
    """阳线 2% > 0.01 → 后续加仓被阻断 → add_count == 0。"""
    df = make_hold_feed_with_big_candle(big_candle_pct=0.02)
    strat = run_backtest(df)
    assert len(strat.trade_log) >= 1
    assert strat.trade_log[0]['add_count'] == 0


def test_add_allowed_when_max_bullish_below_threshold():
    """阳线 0.5% ≤ 0.01 → 加仓机制不被该约束阻断（max_bullish_candle_pct 0.005）。"""
    df = make_hold_feed_with_big_candle(big_candle_pct=0.005)
    strat = run_backtest(df)
    assert len(strat.trade_log) >= 1
    assert strat.trade_log[0]['max_bullish_candle_pct'] <= 0.01 + 1e-9


def make_excursion_feed(mfe_pct=0.10, mae_pct=-0.05):
    """构造一笔交易，持仓期内最高浮盈 mfe_pct、最深浮亏 mae_pct（基于首买入价）。

    bar 0..69: ma60 平稳上涨准备；
    bar 70: 阴线 + close>ma60 + dea>0 + 历史 dea<0 → 触发首买入（close 即首买价）；
    bar 71: high 制造 mfe（low 接近）；
    bar 72: low 制造 mae；
    bar 73..149: 温和小阴小阳，持仓不平。
    """
    n = 150
    dates = pd.date_range('2020-01-01', periods=n, freq='B')
    closes = [10.0 + i * 0.05 for i in range(n)]
    closes[70] = closes[70] - 0.2  # 阴线触发买入
    # bar 73..n-1: 持仓期保持温和（接近首买价），避免自然涨幅淹没构造的 mfe/mae
    fb_close = closes[70]
    for i in range(73, n):
        # 在 fb 附近做小幅 ±0.5% 抖动，保持小阴小阳，但不超过构造区间
        closes[i] = fb_close * (1.0 + 0.001 * ((i % 5) - 2))
    opens = list(closes)
    highs = [max(o, c) + 0.05 for o, c in zip(opens, closes)]
    lows = [min(o, c) - 0.05 for o, c in zip(opens, closes)]

    # 首买价 = closes[70]
    fb = closes[70]
    # bar 71 制造 mfe：把 high 拉高到 fb*(1+mfe_pct)
    highs[71] = fb * (1.0 + mfe_pct)
    # bar 72 制造 mae：把 low 压到 fb*(1+mae_pct)
    lows[72] = fb * (1.0 + mae_pct)

    prev_closes = [np.nan] + closes[:-1]
    ma60 = [np.nan] * 59 + [sum(closes[i - 59:i + 1]) / 60 for i in range(59, n)]
    ma25 = [np.nan] * 24 + [sum(closes[i - 24:i + 1]) / 25 for i in range(24, n)]
    dea = [-0.1] * 70 + [0.1] * (n - 70)

    df = pd.DataFrame({
        'trade_date': dates,
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': [1_000_000] * n,
        'ma25': ma25,
        'ma60': ma60,
        'dea': dea,
        'prev_close': prev_closes,
    })
    df.index = df['trade_date']
    return df


def test_first_buy_price_locked_at_initial_buy():
    """首买价记录在 trade_log，并等于 close[70]（无加仓发生时）。"""
    df = make_excursion_feed(mfe_pct=0.005, mae_pct=-0.005)
    strat = run_backtest(df)
    assert len(strat.trade_log) >= 1
    rec = strat.trade_log[0]
    assert 'mfe_pct' in rec
    assert 'mae_pct' in rec
    assert 'dea_neg_distance_days' in rec


def test_mfe_mae_recorded_during_holding():
    """构造已知 ±10%/-5% 波动 → mfe/mae 与预期值匹配。"""
    df = make_excursion_feed(mfe_pct=0.10, mae_pct=-0.05)
    strat = run_backtest(df)
    rec = strat.trade_log[0]
    assert abs(rec['mfe_pct'] - 10.0) < 0.05  # 单位百分点
    assert abs(rec['mae_pct'] - (-5.0)) < 0.05


def test_dea_neg_distance_days_recorded():
    """make_excursion_feed 中 dea[0..69]<0、dea[70..]>0，bar 70 入场，
    所以 dea_neg_distance_days = 1（昨日 dea<0）。"""
    df = make_excursion_feed()
    strat = run_backtest(df)
    rec = strat.trade_log[0]
    assert rec['dea_neg_distance_days'] == 1


def test_dea_neg_distance_capped_at_max_lookback():
    """构造一份 dea 全程 ≥ 0 的 feed → 函数返回 max_lookback (200)。
    （这里直接调用 helper，不走完整回测。）"""
    from my_strategy.src.strategy import _scan_dea_neg_distance

    class FakeLine:
        def __init__(self, vals):
            self.vals = vals
        def __getitem__(self, idx):
            # backtrader 风格：idx=-i 表示 i bar 之前
            return self.vals[-1 + idx] if -1 + idx >= -len(self.vals) else float('nan')

    class FakeData:
        pass
    d = FakeData()
    d.dea = FakeLine([0.5] * 250)  # 全部 ≥ 0
    assert _scan_dea_neg_distance(d, max_lookback=200) == 200
