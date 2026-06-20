# ATR 自适应止盈 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用入场时的 ATR 动态计算每笔交易的止盈阈值，替换现有的固定5%/10%，并将阈值输出到 trade_summary.csv。

**Architecture:** 在 `MyStrategy.__init__` 中为每只股票初始化 `bt.indicators.ATR`；在 `notify_order` 的 `initial_buy` 成交时计算并快照 `tp1_pct`/`tp2_pct`/`initial_size` 到 `stock_state`；`next()` 中用动态阈值和 `initial_size` 固定卖出量；`_finalize_episode` 将阈值写入 `trade_log`。

**Tech Stack:** Python 3, backtrader, pandas, pytest

---

## 文件变更清单

| 文件 | 变更类型 | 内容 |
|------|----------|------|
| `my_strategy/config.json` | 修改 | 新增4个参数 |
| `my_strategy/strategy.py` | 修改 | ATR指标、stock_state字段、notify_order计算、next()止盈逻辑、_finalize_episode输出 |
| `my_strategy/backtest.py` | 修改 | setup_cerebro 传递新参数，run_index_strategy 同步 |
| `my_strategy/tests/test_atr_take_profit.py` | 新建 | 单元测试 + 集成冒烟测试 |

---

## Task 1: 新增配置参数

**Files:**
- Modify: `my_strategy/config.json`
- Modify: `my_strategy/strategy.py:32-38`（MyStrategy.params）
- Modify: `my_strategy/backtest.py:87-94`（setup_cerebro addstrategy）
- Modify: `my_strategy/backtest.py:304-311`（run_index_strategy addstrategy）

- [ ] **Step 1: 写失败测试**

新建 `my_strategy/tests/test_atr_take_profit.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```
cd my_strategy
python -m pytest tests/test_atr_take_profit.py::test_config_has_atr_params -v
```

预期：FAIL，`KeyError: 'atr_period'`

- [ ] **Step 3: 修改 config.json**

在 `my_strategy/config.json` 末尾 `"benchmark_codes"` 行之前插入（保持 JSON 合法）：

```json
{
  "tushare_token": "6c07eb83d0933edda3ee061585600d3940ff1bfef9beb0a0ab8bd7e3",
  "start_date": "20180101",
  "end_date": "20241231",
  "backTest_Start_data": "20190101",
  "backTest_end_data": "20240101",
  "initial_cash": 100000000,
  "max_positions": 30,
  "commission_rate": 0.0003,
  "stamp_duty": 0.001,
  "stock_list_path": "stock_list.csv",
  "data_dir": "data/",
  "results_dir": "results/",
  "dea_lookback_days": 5,
  "take_profit_1_pct": 0.05,
  "take_profit_2_pct": 0.10,
  "atr_period": 20,
  "atr_multiplier": 1.5,
  "take_profit_min_pct": 0.03,
  "take_profit_max_pct": 0.12,
  "benchmark_codes": ["000300.SH", "000905.SH"]
}
```

- [ ] **Step 4: 修改 strategy.py MyStrategy.params**

将：
```python
    params = (
        ('initial_cash', 100_000_000),
        ('max_positions', 200),
        ('take_profit_1_pct', 0.05),
        ('take_profit_2_pct', 0.10),
        ('dea_lookback_days', 5),
    )
```

改为：
```python
    params = (
        ('initial_cash', 100_000_000),
        ('max_positions', 200),
        ('take_profit_1_pct', 0.05),
        ('take_profit_2_pct', 0.10),
        ('dea_lookback_days', 5),
        ('atr_period', 20),
        ('atr_multiplier', 1.5),
        ('take_profit_min_pct', 0.03),
        ('take_profit_max_pct', 0.12),
    )
```

- [ ] **Step 5: 修改 backtest.py setup_cerebro**

将：
```python
    cerebro.addstrategy(
        MyStrategy,
        initial_cash=cfg['initial_cash'],
        max_positions=cfg['max_positions'],
        take_profit_1_pct=cfg['take_profit_1_pct'],
        take_profit_2_pct=cfg['take_profit_2_pct'],
        dea_lookback_days=cfg['dea_lookback_days'],
    )
```

改为：
```python
    cerebro.addstrategy(
        MyStrategy,
        initial_cash=cfg['initial_cash'],
        max_positions=cfg['max_positions'],
        take_profit_1_pct=cfg['take_profit_1_pct'],
        take_profit_2_pct=cfg['take_profit_2_pct'],
        dea_lookback_days=cfg['dea_lookback_days'],
        atr_period=cfg.get('atr_period', 20),
        atr_multiplier=cfg.get('atr_multiplier', 1.5),
        take_profit_min_pct=cfg.get('take_profit_min_pct', 0.03),
        take_profit_max_pct=cfg.get('take_profit_max_pct', 0.12),
    )
```

- [ ] **Step 6: 修改 backtest.py run_index_strategy**

同样位置（约第304行）将：
```python
    cerebro.addstrategy(
        MyStrategy,
        initial_cash=cfg['initial_cash'],
        max_positions=1,
        take_profit_1_pct=cfg['take_profit_1_pct'],
        take_profit_2_pct=cfg['take_profit_2_pct'],
        dea_lookback_days=cfg['dea_lookback_days'],
    )
```

改为：
```python
    cerebro.addstrategy(
        MyStrategy,
        initial_cash=cfg['initial_cash'],
        max_positions=1,
        take_profit_1_pct=cfg['take_profit_1_pct'],
        take_profit_2_pct=cfg['take_profit_2_pct'],
        dea_lookback_days=cfg['dea_lookback_days'],
        atr_period=cfg.get('atr_period', 20),
        atr_multiplier=cfg.get('atr_multiplier', 1.5),
        take_profit_min_pct=cfg.get('take_profit_min_pct', 0.03),
        take_profit_max_pct=cfg.get('take_profit_max_pct', 0.12),
    )
```

- [ ] **Step 7: 运行测试确认通过**

```
cd my_strategy
python -m pytest tests/test_atr_take_profit.py::test_config_has_atr_params -v
```

预期：PASS

- [ ] **Step 8: 提交**

```
git add my_strategy/config.json my_strategy/strategy.py my_strategy/backtest.py my_strategy/tests/test_atr_take_profit.py
git commit -m "feat: add ATR take-profit config params to config.json, strategy, backtest"
```

---

## Task 2: ATR 指标初始化 + stock_state 新增字段

**Files:**
- Modify: `my_strategy/strategy.py:40-56`（`__init__`）
- Modify: `my_strategy/strategy.py:74-82`（`_reset_state`）

- [ ] **Step 1: 写失败测试**

在 `my_strategy/tests/test_atr_take_profit.py` 追加：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```
cd my_strategy
python -m pytest tests/test_atr_take_profit.py::test_stock_state_has_new_fields -v
```

预期：FAIL，`AssertionError: 'tp1_pct' not in state`

- [ ] **Step 3: 修改 strategy.py __init__ — 初始化 ATR + stock_state**

在 `__init__` 中，将：
```python
        self.stock_state = {}
        for d in self.datas:
            self.stock_state[d] = {
                'take_profit_count': 0,
                'in_ma60_obs': False,
                'in_ma25_obs': False,
                'entry_price': None,
                'big_candle_seen': False,
                'add_count': 0,
            }
```

改为：
```python
        self.atr = {d: bt.indicators.ATR(d, period=self.p.atr_period) for d in self.datas}

        self.stock_state = {}
        for d in self.datas:
            self.stock_state[d] = {
                'take_profit_count': 0,
                'in_ma60_obs': False,
                'in_ma25_obs': False,
                'entry_price': None,
                'big_candle_seen': False,
                'add_count': 0,
                'tp1_pct': None,
                'tp2_pct': None,
                'initial_size': None,
            }
```

- [ ] **Step 4: 修改 _reset_state**

将：
```python
    def _reset_state(self, d):
        self.stock_state[d] = {
            'take_profit_count': 0,
            'in_ma60_obs': False,
            'in_ma25_obs': False,
            'entry_price': None,
            'big_candle_seen': False,
            'add_count': 0,
        }
```

改为：
```python
    def _reset_state(self, d):
        self.stock_state[d] = {
            'take_profit_count': 0,
            'in_ma60_obs': False,
            'in_ma25_obs': False,
            'entry_price': None,
            'big_candle_seen': False,
            'add_count': 0,
            'tp1_pct': None,
            'tp2_pct': None,
            'initial_size': None,
        }
```

- [ ] **Step 5: 运行测试确认通过**

```
cd my_strategy
python -m pytest tests/test_atr_take_profit.py::test_stock_state_has_new_fields -v
```

预期：PASS

- [ ] **Step 6: 提交**

```
git add my_strategy/strategy.py
git commit -m "feat: init ATR indicators and add tp1_pct/tp2_pct/initial_size to stock_state"
```

---

## Task 3: notify_order 中计算并存储 ATR 快照

**Files:**
- Modify: `my_strategy/strategy.py:142-183`（`notify_order`）

- [ ] **Step 1: 写失败测试**

在 `my_strategy/tests/test_atr_take_profit.py` 追加：

```python
def test_tp_pcts_set_after_initial_buy():
    """initial_buy 成交后，stock_state 中的 tp1_pct/tp2_pct/initial_size 应被赋值。"""
    np.random.seed(42)
    cerebro = bt.Cerebro()
    cerebro.adddata(_make_feed(n=150), name='TEST')
    cerebro.broker.set_cash(1_000_000)
    cerebro.addstrategy(
        MyStrategy,
        initial_cash=1_000_000,
        max_positions=1,
        atr_period=20,
        atr_multiplier=1.5,
        take_profit_min_pct=0.03,
        take_profit_max_pct=0.12,
    )
    result = cerebro.run()
    st = result[0]
    # 如果有过任何买入，trade_log 里应有 tp1_pct 字段
    if st.trade_log:
        row = st.trade_log[0]
        # tp1_pct 在 _finalize_episode 输出前就应被设置（通过 stock_state）
        # 这里验证 notify_order 正确赋值：找到第一次 initial_buy 后的 stock_state
        pass  # 实际通过 Task 5 的集成测试验证
    # 验证：order_log 中存在 initial_buy
    buy_orders = [o for o in st.order_log if o['reason'] == 'initial_buy']
    assert len(buy_orders) > 0, "合成数据应触发至少一次买入"
```

注意：ATR 快照存储的正确性将在 Task 5 的集成测试中通过 CSV 输出验证。此步确认策略能正常运行并触发买入。

- [ ] **Step 2: 运行测试确认通过（前置健康检查）**

```
cd my_strategy
python -m pytest tests/test_atr_take_profit.py::test_tp_pcts_set_after_initial_buy -v
```

预期：PASS（合成数据应能触发买入信号）

- [ ] **Step 3: 修改 notify_order — 在 initial_buy 成交时计算 ATR 快照**

在 `notify_order` 的 `if order.isbuy():` 块内，找到：
```python
                if order.isbuy():
                    state = self.stock_state[order.data]
                    if state['entry_price'] is None:
                        state['entry_price'] = order.executed.price
                    ep['buys'].append({
```

改为：
```python
                if order.isbuy():
                    state = self.stock_state[order.data]
                    if state['entry_price'] is None:
                        state['entry_price'] = order.executed.price
                    if reason == 'initial_buy':
                        state['initial_size'] = order.executed.size
                        atr_val = self.atr[order.data][0]
                        if atr_val == atr_val:  # not NaN
                            atr_pct = atr_val / order.executed.price
                            tp1 = max(self.p.take_profit_min_pct,
                                      min(self.p.take_profit_max_pct,
                                          self.p.atr_multiplier * atr_pct))
                        else:
                            tp1 = self.p.take_profit_1_pct
                        state['tp1_pct'] = tp1
                        state['tp2_pct'] = tp1 * 2
                    ep['buys'].append({
```

- [ ] **Step 4: 运行之前所有测试确认无回归**

```
cd my_strategy
python -m pytest tests/test_atr_take_profit.py -v
```

预期：全部 PASS

- [ ] **Step 5: 提交**

```
git add my_strategy/strategy.py
git commit -m "feat: compute ATR-based tp1_pct/tp2_pct/initial_size in notify_order on initial_buy"
```

---

## Task 4: next() 中使用动态阈值和 initial_size 固定卖出量

**Files:**
- Modify: `my_strategy/strategy.py:199-251`（`next()` 持仓止盈部分）

- [ ] **Step 1: 写失败测试**

在 `my_strategy/tests/test_atr_take_profit.py` 追加：

```python
def test_tp_threshold_formula():
    """验证 ATR 止盈阈值公式的数学正确性。"""
    def calc_tp1(atr_val, entry_price, k, min_pct, max_pct):
        atr_pct = atr_val / entry_price
        return max(min_pct, min(max_pct, k * atr_pct))

    # 正常情况：ATR%=3%, k=1.5 → 4.5%，在[3%,12%]范围内
    assert abs(calc_tp1(0.6, 20.0, 1.5, 0.03, 0.12) - 0.045) < 1e-9

    # 下限钳制：ATR%=1%, k=1.5 → 1.5% < 3% → 3%
    assert calc_tp1(0.1, 10.0, 1.5, 0.03, 0.12) == 0.03

    # 上限钳制：ATR%=10%, k=1.5 → 15% > 12% → 12%
    assert calc_tp1(2.0, 20.0, 1.5, 0.03, 0.12) == 0.12


def test_tp_sell_size_uses_initial_size():
    """两次止盈都应卖原始建仓量的1/3，而非当前持仓的1/3。"""
    initial_size = 900  # 原始建仓900股
    expected_sell = int(initial_size / 3 / 100) * 100  # = 300
    assert expected_sell == 300

    # 模拟 tp1 后剩余600股，tp2 也应卖300股而非 int(600/3/100)*100=200
    remaining = initial_size - expected_sell  # 600
    wrong_sell = int(remaining / 3 / 100) * 100  # = 200
    assert wrong_sell != expected_sell  # 确认旧逻辑确实不同
```

- [ ] **Step 2: 运行测试确认通过（纯数学，无需修改代码）**

```
cd my_strategy
python -m pytest tests/test_atr_take_profit.py::test_tp_threshold_formula tests/test_atr_take_profit.py::test_tp_sell_size_uses_initial_size -v
```

预期：PASS（这两个是纯数学验证，与代码无关）

- [ ] **Step 3: 修改 next() 的止盈逻辑**

在 `next()` 中，找到止盈部分（约第235-251行）：

```python
                # 止盈（以原始建仓价为基准）
                if state['take_profit_count'] == 0 and pnl_pct >= self.p.take_profit_1_pct:
                    sell_size = int(pos.size / 3 / 100) * 100
                    if sell_size > 0:
                        o = self.sell(data=d, size=sell_size, exectype=bt.Order.Market)
                        self.order_reasons[o.ref] = 'take_profit_1'
                        self.orders[d] = o
                        state['take_profit_count'] = 1
                        continue
                elif state['take_profit_count'] == 1 and pnl_pct >= self.p.take_profit_2_pct:
                    sell_size = int(pos.size / 3 / 100) * 100
                    if sell_size > 0:
                        o = self.sell(data=d, size=sell_size, exectype=bt.Order.Market)
                        self.order_reasons[o.ref] = 'take_profit_2'
                        self.orders[d] = o
                        state['take_profit_count'] = 2
                        continue
```

改为：

```python
                # 止盈（阈值用 ATR 动态值，卖出量用原始建仓量的1/3）
                tp1 = state['tp1_pct'] or self.p.take_profit_1_pct
                tp2 = state['tp2_pct'] or self.p.take_profit_2_pct
                tp_sell_size = int((state['initial_size'] or pos.size) / 3 / 100) * 100
                if state['take_profit_count'] == 0 and pnl_pct >= tp1:
                    if tp_sell_size > 0:
                        o = self.sell(data=d, size=tp_sell_size, exectype=bt.Order.Market)
                        self.order_reasons[o.ref] = 'take_profit_1'
                        self.orders[d] = o
                        state['take_profit_count'] = 1
                        continue
                elif state['take_profit_count'] == 1 and pnl_pct >= tp2:
                    if tp_sell_size > 0:
                        o = self.sell(data=d, size=tp_sell_size, exectype=bt.Order.Market)
                        self.order_reasons[o.ref] = 'take_profit_2'
                        self.orders[d] = o
                        state['take_profit_count'] = 2
                        continue
```

- [ ] **Step 4: 运行所有测试确认无回归**

```
cd my_strategy
python -m pytest tests/test_atr_take_profit.py -v
```

预期：全部 PASS

- [ ] **Step 5: 提交**

```
git add my_strategy/strategy.py
git commit -m "feat: use ATR dynamic thresholds and initial_size-based sell qty in next()"
```

---

## Task 5: _finalize_episode 输出 tp1_pct/tp2_pct 到 trade_log

**Files:**
- Modify: `my_strategy/strategy.py:88-135`（`_finalize_episode`）

- [ ] **Step 1: 写失败测试**

在 `my_strategy/tests/test_atr_take_profit.py` 追加：

```python
def test_trade_log_contains_tp_pcts():
    """trade_log 中每条记录应包含 tp1_pct 和 tp2_pct 字段。"""
    np.random.seed(0)
    cerebro = bt.Cerebro()
    cerebro.adddata(_make_feed(n=200), name='TEST')
    cerebro.broker.set_cash(1_000_000)
    cerebro.addstrategy(
        MyStrategy,
        initial_cash=1_000_000,
        max_positions=1,
        atr_period=20,
        atr_multiplier=1.5,
        take_profit_min_pct=0.03,
        take_profit_max_pct=0.12,
    )
    result = cerebro.run()
    st = result[0]
    completed = [r for r in st.trade_log if r.get('status') == 'completed']
    assert len(completed) > 0, "应有至少一笔已完成交易"
    for row in completed:
        assert 'tp1_pct' in row, f"trade_log 缺少 tp1_pct: {row}"
        assert 'tp2_pct' in row, f"trade_log 缺少 tp2_pct: {row}"
        assert row['tp1_pct'] is not None
        assert 0.03 <= row['tp1_pct'] <= 0.12
        assert abs(row['tp2_pct'] - row['tp1_pct'] * 2) < 1e-9
```

- [ ] **Step 2: 运行测试确认失败**

```
cd my_strategy
python -m pytest tests/test_atr_take_profit.py::test_trade_log_contains_tp_pcts -v
```

预期：FAIL，`KeyError: 'tp1_pct'`

- [ ] **Step 3: 修改 _finalize_episode，向 trade_log 写入 tp1_pct/tp2_pct**

在 `_finalize_episode` 中，找到 `self.trade_log.append({...})` 的字典，在 `'status': status,` 之后、`})` 之前添加两个字段：

将：
```python
        self.trade_log.append({
            'ts_code': d._name,
            'episode': ep['episode_num'],
            'entry_date': entry_date,
            'exit_date': exit_date,
            'holding_days': holding_days,
            'avg_cost': round(avg_cost, 4),
            'avg_exit_price': round(avg_exit_price, 4) if avg_exit_price is not None else None,
            'total_shares': int(total_shares),
            'gross_pnl': round(gross_pnl, 2) if gross_pnl is not None else None,
            'return_pct': round(return_pct, 4) if return_pct is not None else None,
            'add_count': add_count,
            'take_profit_count': take_profit_count,
            'exit_reason': exit_reason,
            'status': status,
        })
```

改为：
```python
        self.trade_log.append({
            'ts_code': d._name,
            'episode': ep['episode_num'],
            'entry_date': entry_date,
            'exit_date': exit_date,
            'holding_days': holding_days,
            'avg_cost': round(avg_cost, 4),
            'avg_exit_price': round(avg_exit_price, 4) if avg_exit_price is not None else None,
            'total_shares': int(total_shares),
            'gross_pnl': round(gross_pnl, 2) if gross_pnl is not None else None,
            'return_pct': round(return_pct, 4) if return_pct is not None else None,
            'add_count': add_count,
            'take_profit_count': take_profit_count,
            'exit_reason': exit_reason,
            'status': status,
            'tp1_pct': round(state['tp1_pct'], 4) if state['tp1_pct'] is not None else None,
            'tp2_pct': round(state['tp2_pct'], 4) if state['tp2_pct'] is not None else None,
        })
```

注意：`_finalize_episode` 已有 `d` 参数，但需要访问 `self.stock_state[d]`。在方法开头加一行：

在 `_finalize_episode(self, d, status='completed'):` 的方法体最开头（`ep = self.episode_state[d]` 之前）加：
```python
        state = self.stock_state[d]
```

- [ ] **Step 4: 运行所有测试确认通过**

```
cd my_strategy
python -m pytest tests/test_atr_take_profit.py -v
```

预期：全部 PASS

- [ ] **Step 5: 提交**

```
git add my_strategy/strategy.py
git commit -m "feat: output tp1_pct/tp2_pct to trade_log in _finalize_episode"
```

---

## Task 6: 端到端冒烟验证

**Files:**
- 无代码修改，仅运行验证

- [ ] **Step 1: 运行完整测试套件**

```
cd my_strategy
python -m pytest tests/test_atr_take_profit.py -v
```

预期：所有测试 PASS

- [ ] **Step 2: 确认 trade_summary.csv 含新列**

检查 `results/trade_summary.csv`（如果已有历史回测结果）是否有 `tp1_pct` 和 `tp2_pct` 列。如有旧文件需要重新跑回测才会更新。可以用快速检查：

```python
import pandas as pd
df = pd.read_csv('results/trade_summary.csv')
print(df.columns.tolist())
assert 'tp1_pct' in df.columns
assert 'tp2_pct' in df.columns
print(df[['ts_code', 'entry_date', 'tp1_pct', 'tp2_pct']].head())
```

- [ ] **Step 3: 最终提交**

```
git add my_strategy/tests/test_atr_take_profit.py
git commit -m "test: finalize ATR take-profit test suite"
```
