import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def test_config_has_atr_params():
    cfg = json.loads((Path(__file__).parent.parent / 'config.json').read_text())
    assert 'atr_period' in cfg
    assert 'atr_multiplier' in cfg
    assert 'take_profit_min_pct' in cfg
    assert 'take_profit_max_pct' in cfg
    assert cfg['atr_period'] == 20
    assert cfg['atr_multiplier'] == 1.5
    assert cfg['take_profit_min_pct'] == 0.03
    assert cfg['take_profit_max_pct'] == 0.12


import backtrader as bt
import pandas as pd
import numpy as np
from strategy import MyStrategy, StockData


def _make_feed(n=100, start='2020-01-01'):
    """生成含 n 根 K 线的合成数据 feed。"""
    dates = pd.bdate_range(start, periods=n)
    close = np.cumprod(1 + np.random.normal(0.001, 0.02, n)) * 10.0
    open_ = close * np.random.uniform(0.98, 1.02, n)
    high = np.maximum(close, open_) * np.random.uniform(1.0, 1.03, n)
    low = np.minimum(close, open_) * np.random.uniform(0.97, 1.0, n)
    volume = np.random.randint(100000, 500000, n).astype(float)
    ma25 = pd.Series(close).rolling(25).mean().values
    ma60 = pd.Series(close).rolling(60).mean().values
    dea = np.where(np.arange(n) > 30, 0.1, -0.1)
    df = pd.DataFrame({
        'trade_date': dates,
        'open': open_, 'high': high, 'low': low, 'close': close, 'volume': volume,
        'ma25': ma25, 'ma60': ma60, 'dea': dea,
    })
    df.index = df['trade_date']
    return StockData(dataname=df)


def test_stock_state_has_new_fields():
    cerebro = bt.Cerebro()
    cerebro.adddata(_make_feed(), name='TEST')
    cerebro.broker.set_cash(1_000_000)
    cerebro.addstrategy(MyStrategy, initial_cash=1_000_000, max_positions=1)
    result = cerebro.run()
    st = result[0]
    d = st.datas[0]
    state = st.stock_state[d]
    assert 'tp1_pct' in state
    assert 'tp2_pct' in state
    assert 'initial_size' in state
