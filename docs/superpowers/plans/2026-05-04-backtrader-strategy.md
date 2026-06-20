# Backtrader 多股票回测策略 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现沪深300 + 中证500成分股的多股票组合回测，支持三步走：数据下载 → 指标预计算 → 回测执行，全部参数配置驱动。

**Architecture:** 四个独立模块（downloader / calc_indicators / strategy / backtest），通过 config.json 共享参数，数据以 CSV 文件传递。strategy.py 读取预计算好的指标 CSV，不在回测时重复计算指标。

**Tech Stack:** Python 3.8+, backtrader, pandas, tushare, pytest

---

## 文件清单

| 文件 | 职责 |
|------|------|
| `backtrader/config.json` | 全局参数配置 |
| `backtrader/stock_list.csv` | 股票代码列表 |
| `backtrader/downloader.py` | 从 Tushare 下载原始 OHLCV 数据 |
| `backtrader/calc_indicators.py` | 预计算 MA25/MA60/DEA/prev_close |
| `backtrader/strategy.py` | StockData feed + StockCommission + MyStrategy |
| `backtrader/backtest.py` | 主入口：加载数据 → 运行回测 → 输出结果 |
| `backtrader/tests/test_calc_indicators.py` | 指标计算单元测试 |
| `backtrader/tests/test_strategy.py` | 策略逻辑集成测试（使用合成数据） |

---

## Task 1: 项目骨架 + 配置文件

**Files:**
- Create: `backtrader/config.json`
- Create: `backtrader/stock_list.csv`
- Create: `backtrader/data/.gitkeep`
- Create: `backtrader/results/.gitkeep`

- [ ] **Step 1: 创建 config.json**

```json
{
  "tushare_token": "your_token_here",
  "start_date": "20180101",
  "end_date": "20241231",
  "initial_cash": 100000000,
  "max_positions": 200,
  "commission_rate": 0.0003,
  "stamp_duty": 0.001,
  "stock_list_path": "stock_list.csv",
  "data_dir": "data/",
  "results_dir": "results/",
  "dea_lookback_days": 5,
  "take_profit_1_pct": 0.05,
  "take_profit_2_pct": 0.10
}
```

保存到 `backtrader/config.json`。

- [ ] **Step 2: 创建 stock_list.csv**

文件内容（首行为表头，后续每行一个股票代码）：

```csv
ts_code
600276.SH
600519.SH
603288.SH
```

保存到 `backtrader/stock_list.csv`。实际使用时替换为沪深300+中证500完整列表。

- [ ] **Step 3: 创建数据目录**

```bash
mkdir backtrader/data
mkdir backtrader/results
mkdir backtrader/tests
```

在 `backtrader/data/` 和 `backtrader/results/` 各放一个 `.gitkeep` 空文件，确保目录被 git 追踪。

- [ ] **Step 4: Commit**

```bash
git add backtrader/config.json backtrader/stock_list.csv backtrader/data/.gitkeep backtrader/results/.gitkeep backtrader/tests/
git commit -m "feat: add project scaffold, config, and directory structure"
```

---

## Task 2: downloader.py

**Files:**
- Create: `backtrader/downloader.py`

- [ ] **Step 1: 写 downloader.py**

```python
import json
import time
import logging
import pandas as pd
import tushare as ts
from pathlib import Path

logging.basicConfig(filename='download_errors.log', level=logging.ERROR,
                    format='%(asctime)s %(message)s')


def load_config(config_path='config.json'):
    with open(config_path, 'r') as f:
        return json.load(f)


def get_last_date(csv_path):
    """读取本地 CSV 最后一条交易日期，用于增量下载。"""
    df = pd.read_csv(csv_path, usecols=['trade_date'])
    return df['trade_date'].max()


def download_stock(pro, ts_code, start_date, end_date, data_dir):
    """下载单只股票数据，支持增量更新。"""
    csv_path = Path(data_dir) / f"{ts_code}.csv"

    if csv_path.exists():
        last_date = get_last_date(csv_path)
        # 从下一天开始增量下载
        next_date = pd.Timestamp(last_date) + pd.Timedelta(days=1)
        actual_start = next_date.strftime('%Y%m%d')
        if actual_start >= end_date:
            return  # 已是最新，跳过
    else:
        actual_start = start_date

    df = ts.pro_bar(
        ts_code=ts_code,
        adj='qfq',
        start_date=actual_start,
        end_date=end_date,
        fields='trade_date,open,high,low,close,vol'
    )
    if df is None or df.empty:
        return

    df = df.rename(columns={'vol': 'volume'})
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.sort_values('trade_date').reset_index(drop=True)

    if csv_path.exists():
        existing = pd.read_csv(csv_path, parse_dates=['trade_date'])
        df = pd.concat([existing, df], ignore_index=True)
        df = df.drop_duplicates(subset='trade_date').sort_values('trade_date')

    df.to_csv(csv_path, index=False)


def main():
    cfg = load_config()
    ts.set_token(cfg['tushare_token'])
    pro = ts.pro_api()

    stocks = pd.read_csv(cfg['stock_list_path'])['ts_code'].tolist()
    data_dir = cfg['data_dir']
    Path(data_dir).mkdir(exist_ok=True)

    for i, ts_code in enumerate(stocks):
        try:
            download_stock(pro, ts_code, cfg['start_date'], cfg['end_date'], data_dir)
            print(f"[{i+1}/{len(stocks)}] {ts_code} OK")
        except Exception as e:
            logging.error(f"{ts_code}: {e}")
            print(f"[{i+1}/{len(stocks)}] {ts_code} FAILED: {e}")
        time.sleep(0.3)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: 手动验证**

在 `backtrader/` 目录下，先在 `config.json` 填入真实 tushare token，然后：

```bash
cd backtrader
python downloader.py
```

预期：`data/` 目录下出现 `600276.SH.csv` 等文件，控制台打印 `[1/3] 600276.SH OK`。

- [ ] **Step 3: Commit**

```bash
git add backtrader/downloader.py
git commit -m "feat: add downloader with incremental update support"
```

---

## Task 3: calc_indicators.py + 单元测试

**Files:**
- Create: `backtrader/calc_indicators.py`
- Create: `backtrader/tests/test_calc_indicators.py`

- [ ] **Step 1: 写失败的单元测试**

```python
# backtrader/tests/test_calc_indicators.py
import pandas as pd
import numpy as np
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from calc_indicators import compute_indicators


def make_ohlcv(n=100, base_close=10.0):
    """生成简单的合成 OHLCV 数据。"""
    dates = pd.date_range('2020-01-01', periods=n, freq='B')
    closes = [base_close + i * 0.01 for i in range(n)]
    df = pd.DataFrame({
        'trade_date': dates,
        'open': closes,
        'high': [c + 0.1 for c in closes],
        'low': [c - 0.1 for c in closes],
        'close': closes,
        'volume': [100000] * n,
    })
    return df


def test_output_columns():
    df = make_ohlcv(100)
    result = compute_indicators(df)
    expected_cols = {'trade_date', 'open', 'high', 'low', 'close', 'volume',
                     'ma25', 'ma60', 'dea', 'prev_close'}
    assert expected_cols.issubset(set(result.columns))


def test_ma25_value():
    df = make_ohlcv(100)
    result = compute_indicators(df)
    # 第25行（索引24）开始 ma25 应有值
    assert pd.notna(result.loc[24, 'ma25'])
    # 前24行 ma25 应为 NaN
    assert pd.isna(result.loc[23, 'ma25'])
    # 验证第25行均值
    expected = df['close'].iloc[:25].mean()
    assert abs(result.loc[24, 'ma25'] - expected) < 1e-6


def test_prev_close():
    df = make_ohlcv(10)
    result = compute_indicators(df)
    # 第2行的 prev_close 应等于第1行的 close
    assert result.loc[1, 'prev_close'] == df.loc[0, 'close']
    # 第1行的 prev_close 应为 NaN
    assert pd.isna(result.loc[0, 'prev_close'])


def test_row_count_unchanged():
    df = make_ohlcv(80)
    result = compute_indicators(df)
    assert len(result) == len(df)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backtrader
python -m pytest tests/test_calc_indicators.py -v
```

预期：`ImportError: cannot import name 'compute_indicators'`（函数未定义）。

- [ ] **Step 3: 写 calc_indicators.py**

```python
import json
import pandas as pd
from pathlib import Path


def load_config(config_path='config.json'):
    with open(config_path, 'r') as f:
        return json.load(f)


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    输入：包含 trade_date/open/high/low/close/volume 的 DataFrame（已按日期升序排列）
    输出：追加 ma25/ma60/dea/prev_close 列的 DataFrame
    """
    df = df.copy()
    df['ma25'] = df['close'].rolling(window=25, min_periods=25).mean()
    df['ma60'] = df['close'].rolling(window=60, min_periods=60).mean()

    # MACD(12, 26, 9)：EMA12 - EMA26 = DIF，DIF 的 9 日 EMA = DEA
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    df['dea'] = dif.ewm(span=9, adjust=False).mean()

    df['prev_close'] = df['close'].shift(1)
    return df


def main():
    cfg = load_config()
    data_dir = Path(cfg['data_dir'])
    stocks = pd.read_csv(cfg['stock_list_path'])['ts_code'].tolist()

    for i, ts_code in enumerate(stocks):
        src = data_dir / f"{ts_code}.csv"
        dst = data_dir / f"{ts_code}_indicators.csv"
        if not src.exists():
            print(f"[{i+1}/{len(stocks)}] {ts_code} SKIP (no raw data)")
            continue
        df = pd.read_csv(src, parse_dates=['trade_date'])
        df = df.sort_values('trade_date').reset_index(drop=True)
        result = compute_indicators(df)
        result.to_csv(dst, index=False)
        print(f"[{i+1}/{len(stocks)}] {ts_code} OK")


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backtrader
python -m pytest tests/test_calc_indicators.py -v
```

预期输出：
```
test_calc_indicators.py::test_output_columns PASSED
test_calc_indicators.py::test_ma25_value PASSED
test_calc_indicators.py::test_prev_close PASSED
test_calc_indicators.py::test_row_count_unchanged PASSED
4 passed
```

- [ ] **Step 5: 手动运行验证**

```bash
python calc_indicators.py
```

预期：`data/600276.SH_indicators.csv` 出现，包含 ma25/ma60/dea/prev_close 列。

- [ ] **Step 6: Commit**

```bash
git add backtrader/calc_indicators.py backtrader/tests/test_calc_indicators.py
git commit -m "feat: add calc_indicators with MA25/MA60/DEA/prev_close + tests"
```

---

## Task 4: strategy.py — StockData + StockCommission

**Files:**
- Create: `backtrader/strategy.py`

- [ ] **Step 1: 写 strategy.py 的前两个类**

```python
# backtrader/strategy.py
import backtrader as bt


class StockData(bt.feeds.PandasData):
    """自定义数据 feed，读取预计算好的指标列。"""
    lines = ('ma25', 'ma60', 'dea', 'prev_close')
    params = (
        ('ma25', -1),       # -1 表示按列名自动匹配
        ('ma60', -1),
        ('dea', -1),
        ('prev_close', -1),
    )


class StockCommission(bt.CommInfoBase):
    """A 股手续费：买入收佣金，卖出收佣金 + 印花税。"""
    params = (
        ('stocklike', True),
        ('commtype', bt.CommInfoBase.COMM_PERC),
        ('percabs', True),      # commission 以小数表示（0.0003 而非 0.03%）
        ('stamp_duty', 0.001),  # 印花税 0.1%
    )

    def _getcommission(self, size, price, pseudoexec):
        if size > 0:  # 买入
            return abs(size) * price * self.p.commission
        elif size < 0:  # 卖出
            return abs(size) * price * (self.p.commission + self.p.stamp_duty)
        return 0.0
```

- [ ] **Step 2: Commit**

```bash
git add backtrader/strategy.py
git commit -m "feat: add StockData feed and StockCommission classes"
```

---

## Task 5: strategy.py — MyStrategy 策略逻辑

**Files:**
- Modify: `backtrader/strategy.py`
- Create: `backtrader/tests/test_strategy.py`

- [ ] **Step 1: 写策略集成测试（合成数据验证信号触发）**

```python
# backtrader/tests/test_strategy.py
"""
使用合成价格数据验证策略的关键信号触发。
用 cerebro 跑一小段数据，通过 notify_order 记录订单，断言订单数量和方向。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import backtrader as bt
import pandas as pd
import numpy as np
import datetime
from strategy import StockData, MyStrategy


def make_feed(n=150, start='2020-01-01'):
    """生成合成数据：稳定上涨，MA60之上，制造一次阴线+DEA上穿信号。"""
    dates = pd.date_range(start, periods=n, freq='B')
    closes = [10.0 + i * 0.05 for i in range(n)]

    # 模拟 prev_close
    prev_closes = [np.nan] + closes[:-1]

    # 模拟 ma60（前59天为 NaN，之后为均值近似）
    ma60 = [np.nan] * 59 + [sum(closes[i-59:i+1]) / 60 for i in range(59, n)]
    ma25 = [np.nan] * 24 + [sum(closes[i-24:i+1]) / 25 for i in range(24, n)]

    # DEA：前段为负（-0.1），第70天开始为正（+0.1），制造上穿0轴
    dea = [-0.1] * 70 + [0.1] * (n - 70)

    # 第70天制造阴线（close < prev_close）
    for i in range(70, 71):
        closes[i] = closes[i] - 0.2  # 阴线

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
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backtrader
python -m pytest tests/test_strategy.py -v
```

预期：`ImportError: cannot import name 'MyStrategy'`。

- [ ] **Step 3: 在 strategy.py 追加 MyStrategy 类**

```python
class MyStrategy(bt.Strategy):
    params = (
        ('initial_cash', 100_000_000),
        ('max_positions', 200),
        ('take_profit_1_pct', 0.05),
        ('take_profit_2_pct', 0.10),
        ('dea_lookback_days', 5),
    )

    def __init__(self):
        self.position_limit = self.p.initial_cash / self.p.max_positions

        # per-stock 状态
        self.stock_state = {}
        for d in self.datas:
            self.stock_state[d] = {
                'take_profit_count': 0,
                'in_ma60_obs': False,
                'in_ma25_obs': False,
            }

        # 记录订单，供测试和日志使用
        self.order_log = []
        self.orders = {}  # d -> 当前未完成订单，防止重复下单

    def _current_position_count(self):
        return sum(1 for d in self.datas if self.getposition(d).size > 0)

    def _reset_state(self, d):
        self.stock_state[d] = {
            'take_profit_count': 0,
            'in_ma60_obs': False,
            'in_ma25_obs': False,
        }

    def _has_pending_order(self, d):
        o = self.orders.get(d)
        return o is not None and o.alive()

    def notify_order(self, order):
        if order.status in (order.Completed, order.Canceled, order.Rejected):
            side = 'buy' if order.isbuy() else 'sell'
            self.order_log.append({
                'date': self.data.datetime.date(0),
                'side': side,
                'size': order.executed.size,
                'price': order.executed.price,
            })
            # 订单完结，清除引用
            for d, o in list(self.orders.items()):
                if o is order:
                    self.orders.pop(d, None)
                    break

    def next(self):
        for d in self.datas:
            state = self.stock_state[d]
            pos = self.getposition(d)
            close = d.close[0]
            ma25 = d.ma25[0]
            ma60 = d.ma60[0]

            # 跳过指标尚未就绪的行
            if ma60 != ma60:  # NaN check
                continue

            if self._has_pending_order(d):
                continue

            # === 1. 尾盘卖出检测（有持仓） ===
            if pos.size > 0:
                avg_price = pos.price
                pnl_pct = (close - avg_price) / avg_price

                # MA60 止损
                if state['in_ma60_obs']:
                    if close < ma60:
                        o = self.close(data=d, exectype=bt.Order.Close)
                        self.orders[d] = o
                        self._reset_state(d)
                        continue
                    else:
                        state['in_ma60_obs'] = False
                elif close < ma60:
                    state['in_ma60_obs'] = True

                # MA25 清仓（止盈2次后激活）
                if state['take_profit_count'] >= 2 and ma25 == ma25:
                    if state['in_ma25_obs']:
                        if close < ma25:
                            o = self.close(data=d, exectype=bt.Order.Close)
                            self.orders[d] = o
                            self._reset_state(d)
                            continue
                        else:
                            state['in_ma25_obs'] = False
                    elif close < ma25:
                        state['in_ma25_obs'] = True

                # 止盈
                if state['take_profit_count'] == 0 and pnl_pct >= self.p.take_profit_1_pct:
                    sell_size = int(pos.size / 3 / 100) * 100
                    if sell_size > 0:
                        o = self.sell(data=d, size=sell_size, exectype=bt.Order.Close)
                        self.orders[d] = o
                        state['take_profit_count'] = 1
                elif state['take_profit_count'] == 1 and pnl_pct >= self.p.take_profit_2_pct:
                    sell_size = int(pos.size / 3 / 100) * 100
                    if sell_size > 0:
                        o = self.sell(data=d, size=sell_size, exectype=bt.Order.Close)
                        self.orders[d] = o
                        state['take_profit_count'] = 2

            # === 2. 尾盘入场扫描（无持仓） ===
            else:
                prev_close = d.prev_close[0]
                dea = d.dea[0]

                # prev_close 未就绪时跳过
                if prev_close != prev_close:
                    continue

                # 阴线
                if close >= prev_close:
                    continue

                # close > MA60
                if close <= ma60:
                    continue

                # DEA 刚上穿 0 轴：今日 DEA > 0，前 N 日 DEA 均 ≤ 0
                if dea <= 0:
                    continue
                n = self.p.dea_lookback_days
                past_deas = [d.dea[-i] for i in range(1, n + 1)]
                if any(v > 0 for v in past_deas if v == v):
                    continue

                # 持仓数检查
                if self._current_position_count() >= self.p.max_positions:
                    continue

                # 买入 1/3 仓位（用收盘价估算股数，实际以次日开盘价成交）
                buy_value = self.position_limit / 3
                buy_size = int(buy_value / close / 100) * 100
                if buy_size <= 0:
                    continue

                o = self.buy(data=d, size=buy_size)
                self.orders[d] = o
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backtrader
python -m pytest tests/test_strategy.py -v
```

预期：
```
test_strategy.py::test_entry_signal_triggers_buy PASSED
test_strategy.py::test_take_profit_1_triggers PASSED
2 passed
```

- [ ] **Step 5: Commit**

```bash
git add backtrader/strategy.py backtrader/tests/test_strategy.py
git commit -m "feat: add MyStrategy with entry/exit/stop-loss logic + tests"
```

---

## Task 6: backtest.py — 主入口

**Files:**
- Create: `backtrader/backtest.py`

- [ ] **Step 1: 写 backtest.py**

```python
import json
import datetime
import pandas as pd
import backtrader as bt
from pathlib import Path
from strategy import StockData, StockCommission, MyStrategy


def load_config(config_path='config.json'):
    with open(config_path, 'r') as f:
        return json.load(f)


def load_feeds(cfg):
    """读取所有股票的指标 CSV，返回 (name, feed) 列表。"""
    stocks = pd.read_csv(cfg['stock_list_path'])['ts_code'].tolist()
    data_dir = Path(cfg['data_dir'])
    start = datetime.datetime.strptime(cfg['start_date'], '%Y%m%d')
    end = datetime.datetime.strptime(cfg['end_date'], '%Y%m%d')

    feeds = []
    for ts_code in stocks:
        path = data_dir / f"{ts_code}_indicators.csv"
        if not path.exists():
            print(f"SKIP {ts_code}: 指标文件不存在，请先运行 calc_indicators.py")
            continue
        df = pd.read_csv(path, parse_dates=['trade_date'])
        df = df.sort_values('trade_date').reset_index(drop=True)
        df.index = df['trade_date']
        feed = StockData(dataname=df, fromdate=start, todate=end)
        feeds.append((ts_code, feed))
    return feeds


def setup_cerebro(cfg, feeds):
    cerebro = bt.Cerebro()

    for name, feed in feeds:
        cerebro.adddata(feed, name=name)

    cerebro.broker.set_cash(cfg['initial_cash'])

    comm = StockCommission(
        commission=cfg['commission_rate'],
        stamp_duty=cfg['stamp_duty'],
    )
    cerebro.broker.addcommissioninfo(comm)

    cerebro.broker.set_slippage_perc(perc=0.0001)

    cerebro.addstrategy(
        MyStrategy,
        initial_cash=cfg['initial_cash'],
        max_positions=cfg['max_positions'],
        take_profit_1_pct=cfg['take_profit_1_pct'],
        take_profit_2_pct=cfg['take_profit_2_pct'],
        dea_lookback_days=cfg['dea_lookback_days'],
    )

    cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name='_AnnualReturn')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='_DrawDown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='_Returns', tann=252)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio_A, _name='_SharpeRatio_A')
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='_TimeReturn')

    return cerebro


def print_results(result, cfg):
    r = result[0]
    annual_ret = r.analyzers._Returns.get_analysis().get('rnorm100', 'N/A')
    max_dd = r.analyzers._DrawDown.get_analysis()['max']['drawdown']
    sharpe = r.analyzers._SharpeRatio_A.get_analysis().get('sharperatio', 'N/A')

    print("\n========== 回测结果 ==========")
    print(f"年化收益率：{annual_ret:.2f}%" if isinstance(annual_ret, float) else f"年化收益率：{annual_ret}")
    print(f"最大回撤：{max_dd:.2f}%")
    print(f"年化夏普比率：{sharpe:.3f}" if isinstance(sharpe, float) else f"年化夏普比率：{sharpe}")
    print("==============================\n")

    results_dir = Path(cfg['results_dir'])
    results_dir.mkdir(exist_ok=True)

    trade_df = pd.DataFrame(r.order_log)
    if not trade_df.empty:
        trade_df.to_csv(results_dir / 'trade_list.csv', index=False)
        print(f"交易记录已保存到 {results_dir / 'trade_list.csv'}")

    time_return = pd.Series(r.analyzers._TimeReturn.get_analysis())
    equity = (1 + time_return).cumprod()
    equity.plot(title='Equity Curve').get_figure().savefig(
        results_dir / 'equity_curve.png', dpi=150
    )
    print(f"资金曲线已保存到 {results_dir / 'equity_curve.png'}")


def main():
    cfg = load_config()
    feeds = load_feeds(cfg)
    if not feeds:
        print("没有可用的数据文件，请先运行 downloader.py 和 calc_indicators.py")
        return

    cerebro = setup_cerebro(cfg, feeds)
    print(f"初始资金：{cfg['initial_cash']:,.0f}")
    print(f"加载股票数：{len(feeds)}")
    print("开始回测...")

    result = cerebro.run()
    print_results(result, cfg)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: 端到端验证**

先确保已执行过 `downloader.py` 和 `calc_indicators.py`，然后：

```bash
cd backtrader
python backtest.py
```

预期：控制台打印年化收益率、最大回撤、夏普比率，`results/` 目录下出现 `trade_list.csv` 和 `equity_curve.png`。

- [ ] **Step 3: Commit**

```bash
git add backtrader/backtest.py
git commit -m "feat: add backtest main runner with broker setup and result output"
```

---

## Task 7: 运行全套测试 + 最终验证

- [ ] **Step 1: 运行全部单元测试**

```bash
cd backtrader
python -m pytest tests/ -v
```

预期：
```
tests/test_calc_indicators.py::test_output_columns PASSED
tests/test_calc_indicators.py::test_ma25_value PASSED
tests/test_calc_indicators.py::test_prev_close PASSED
tests/test_calc_indicators.py::test_row_count_unchanged PASSED
tests/test_strategy.py::test_entry_signal_triggers_buy PASSED
tests/test_strategy.py::test_take_profit_1_triggers PASSED
6 passed
```

- [ ] **Step 2: 完整流程验证（3只测试股票）**

确保 `stock_list.csv` 中只有 3 只股票，依次执行：

```bash
python downloader.py        # 下载原始数据
python calc_indicators.py   # 计算指标
python backtest.py          # 运行回测
```

检查：
- `data/` 下有 3 个 `*.csv` 和 3 个 `*_indicators.csv`
- `results/trade_list.csv` 非空，列包含 date/side/size/price
- `results/equity_curve.png` 图片正常生成

- [ ] **Step 3: 最终 Commit**

```bash
git add .
git commit -m "feat: complete backtrader multi-stock backtest pipeline"
```

---

## 自检：规格覆盖

| 需求 | 对应 Task |
|------|-----------|
| 沪深300+中证500，配置驱动股票列表 | Task 1（stock_list.csv + config） |
| Tushare 下载 + 增量更新 | Task 2（downloader.py） |
| 预计算 MA25/MA60/DEA/prev_close | Task 3（calc_indicators.py） |
| 自定义 PandasData 读取指标列 | Task 4（StockData） |
| 买入印花税+佣金手续费 | Task 4（StockCommission） |
| 入场信号：阴线+DEA上穿0+close>MA60 | Task 5（MyStrategy.next） |
| 买入 1/3 仓位，次日开盘成交 | Task 5（MyStrategy.next） |
| 止盈 5%/10% 各卖 1/3 | Task 5（MyStrategy.next） |
| MA60 止损（两日观察期） | Task 5（MyStrategy.next） |
| MA25 清仓（止盈2次后激活，两日观察期） | Task 5（MyStrategy.next） |
| 最大持仓数限制 | Task 5（_current_position_count） |
| 初始资金/最大持仓/日期范围全部配置化 | Task 1 + Task 6 |
| 输出年化收益/最大回撤/夏普 | Task 6（print_results） |
| 输出每笔交易明细 CSV | Task 6（trade_list.csv） |
| 输出资金曲线图 | Task 6（equity_curve.png） |
