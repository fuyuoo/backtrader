# Trade Summary & Statistics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 回测结束后输出 `trade_summary.csv`（每行一个完整交易周期，含收益率/出场原因）并在控制台打印策略分析统计。

**Architecture:** 在 `strategy.py` 中，每次下单时用 `pending_reason` 字典打标签；`notify_order` 成交时将买卖记录写入 `episode_state`；position 归零时调用 `_finalize_episode` 计算并写入 `trade_log`；`backtest.py` 的 `print_results` 读取 `trade_log` 生成 CSV 并打印统计。

**Tech Stack:** Python 3.14, backtrader, pandas, pytest

---

## File Map

| 文件 | 改动类型 | 内容 |
|---|---|---|
| `my_strategy/strategy.py` | Modify | 新增 `pending_reason`、`episode_state`、`trade_log`、`_finalize_episode`、`stop()`；更新 `notify_order` 和 `next()` |
| `my_strategy/backtest.py` | Modify | 新增 `_print_trade_stats`；更新 `print_results` 输出 `trade_summary.csv` 和统计 |
| `my_strategy/tests/test_strategy.py` | Modify | 新增测试：`trade_log` 结构、`order_log` 含 reason/episode |
| `my_strategy/tests/test_backtest.py` | Create | 新增测试：`_print_trade_stats` 统计逻辑 |

---

### Task 1: 写失败测试（TDD 先写测试）

**Files:**
- Modify: `my_strategy/tests/test_strategy.py`

- [ ] **Step 1: 在 `test_strategy.py` 末尾追加两个新测试**

```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

```
cd my_strategy
pytest tests/test_strategy.py::test_order_log_has_reason_and_episode tests/test_strategy.py::test_trade_log_has_required_keys -v
```

预期：两个测试均 FAIL（`AttributeError: 'MyStrategy' object has no attribute 'trade_log'` 或 `KeyError: 'reason'`）

---

### Task 2: 在 `__init__` 中新增数据结构

**Files:**
- Modify: `my_strategy/strategy.py:40-55`（`__init__` 方法）

- [ ] **Step 1: 在 `self.orders = {}` 之后追加三行**

在 `strategy.py` 的 `__init__` 末尾，`self.orders = {}` 后面追加：

```python
        self.pending_reason = {}
        self.episode_state = {
            d: {'buys': [], 'sells': [], 'episode_num': 1}
            for d in self.datas
        }
        self.trade_log = []
```

- [ ] **Step 2: 运行测试，确认 `test_trade_log_has_required_keys` 部分通过**

```
cd my_strategy
pytest tests/test_strategy.py::test_trade_log_has_required_keys -v
```

预期：FAIL，但错误变为 `AssertionError: trade_log 应至少有一条记录`（属性已存在，但 trade_log 为空）

---

### Task 3: 新增 `_finalize_episode` 方法

**Files:**
- Modify: `my_strategy/strategy.py`（在 `_has_pending_order` 之后插入新方法）

- [ ] **Step 1: 在 `_has_pending_order` 方法之后插入 `_finalize_episode`**

```python
    def _finalize_episode(self, d, status='completed'):
        ep = self.episode_state[d]
        buys, sells = ep['buys'], ep['sells']
        if not buys:
            return
        total_shares = sum(b['size'] for b in buys)
        avg_cost = sum(b['size'] * b['price'] for b in buys) / total_shares
        entry_date = buys[0]['date']
        add_count = sum(1 for b in buys if b['reason'] == 'add_on')
        if sells:
            total_sold = sum(s['size'] for s in sells)
            avg_exit_price = sum(s['size'] * s['price'] for s in sells) / total_sold
            exit_date = sells[-1]['date']
            holding_days = (exit_date - entry_date).days
            gross_pnl = (avg_exit_price - avg_cost) * total_shares
            return_pct = (avg_exit_price - avg_cost) / avg_cost * 100
            take_profit_count = sum(
                1 for s in sells if s['reason'] in ('take_profit_1', 'take_profit_2')
            )
            exit_reason = {'MA60_stop': 'MA60止损', 'MA25_stop': 'MA25清仓'}.get(
                sells[-1]['reason'], sells[-1]['reason']
            )
        else:
            avg_exit_price = exit_date = holding_days = gross_pnl = return_pct = None
            take_profit_count = 0
            exit_reason = '未平仓'
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
        ep['buys'] = []
        ep['sells'] = []
        ep['episode_num'] += 1
```

---

### Task 4: 新增 `stop()` 方法

**Files:**
- Modify: `my_strategy/strategy.py`（在 `_finalize_episode` 之后插入）

- [ ] **Step 1: 在 `_finalize_episode` 之后插入 `stop()` 方法**

```python
    def stop(self):
        for d in self.datas:
            if self.episode_state[d]['buys']:
                self._finalize_episode(d, status='incomplete')
```

- [ ] **Step 2: 运行测试，确认 `test_trade_log_has_required_keys` 现在通过**

```
cd my_strategy
pytest tests/test_strategy.py::test_trade_log_has_required_keys -v
```

预期：PASS（`stop()` 将未平仓持仓写入 `trade_log`，所有字段存在）

---

### Task 5: 更新 `notify_order` — 打标签 + 追踪买卖

**Files:**
- Modify: `my_strategy/strategy.py:74-93`（整个 `notify_order` 方法）

- [ ] **Step 1: 将 `notify_order` 整体替换为以下实现**

```python
    def notify_order(self, order):
        if order.status in (order.Completed, order.Canceled, order.Rejected):
            reason = self.pending_reason.pop(order, 'unknown')
            ep = self.episode_state[order.data]
            episode_num = ep['episode_num']  # 在可能的 finalize 之前先捕获

            if order.status == order.Completed:
                if order.isbuy():
                    state = self.stock_state[order.data]
                    if state['entry_price'] is None:
                        state['entry_price'] = order.executed.price
                    ep['buys'].append({
                        'date': bt.num2date(order.executed.dt).date(),
                        'size': order.executed.size,
                        'price': order.executed.price,
                        'reason': reason,
                    })
                else:
                    ep['sells'].append({
                        'date': bt.num2date(order.executed.dt).date(),
                        'size': abs(order.executed.size),
                        'price': order.executed.price,
                        'reason': reason,
                    })
                    total_bought = sum(b['size'] for b in ep['buys'])
                    total_sold = sum(s['size'] for s in ep['sells'])
                    if total_sold >= total_bought > 0:
                        self._finalize_episode(order.data)

            self.order_log.append({
                'date': bt.num2date(order.executed.dt).date(),
                'ts_code': order.data._name,
                'side': 'buy' if order.isbuy() else 'sell',
                'size': order.executed.size,
                'price': order.executed.price,
                'reason': reason,
                'episode': episode_num,
            })
            for d, o in list(self.orders.items()):
                if o is order:
                    self.orders.pop(d, None)
                    break
```

- [ ] **Step 2: 运行两个新测试**

```
cd my_strategy
pytest tests/test_strategy.py::test_order_log_has_reason_and_episode tests/test_strategy.py::test_trade_log_has_required_keys -v
```

预期：`test_order_log_has_reason_and_episode` 仍 FAIL（reason 还未在 `next()` 中设置，全是 `'unknown'`）；`test_trade_log_has_required_keys` PASS

---

### Task 6: 更新 `next()` — 每处下单后设置 `pending_reason`

**Files:**
- Modify: `my_strategy/strategy.py:95-211`（`next()` 方法中的6处下单）

- [ ] **Step 1: MA60 止损处（第120-124行区域）**

将：
```python
                        o = self.close(data=d, exectype=bt.Order.Market)
                        self.orders[d] = o
                        self._reset_state(d)
                        continue
                    else:
                        state['in_ma60_obs'] = False
```
改为：
```python
                        o = self.close(data=d, exectype=bt.Order.Market)
                        self.pending_reason[o] = 'MA60_stop'
                        self.orders[d] = o
                        self._reset_state(d)
                        continue
                    else:
                        state['in_ma60_obs'] = False
```

- [ ] **Step 2: MA25 止盈清仓处（第132-138行区域）**

将：
```python
                        if close < ma25:
                            o = self.close(data=d, exectype=bt.Order.Market)
                            self.orders[d] = o
                            self._reset_state(d)
                            continue
                        else:
                            state['in_ma25_obs'] = False
```
改为：
```python
                        if close < ma25:
                            o = self.close(data=d, exectype=bt.Order.Market)
                            self.pending_reason[o] = 'MA25_stop'
                            self.orders[d] = o
                            self._reset_state(d)
                            continue
                        else:
                            state['in_ma25_obs'] = False
```

- [ ] **Step 3: 止盈第一次处（第144-150行区域）**

将：
```python
                    if sell_size > 0:
                        o = self.sell(data=d, size=sell_size, exectype=bt.Order.Market)
                        self.orders[d] = o
                        state['take_profit_count'] = 1
                        continue
```
改为：
```python
                    if sell_size > 0:
                        o = self.sell(data=d, size=sell_size, exectype=bt.Order.Market)
                        self.pending_reason[o] = 'take_profit_1'
                        self.orders[d] = o
                        state['take_profit_count'] = 1
                        continue
```

- [ ] **Step 4: 止盈第二次处（第151-157行区域）**

将：
```python
                    if sell_size > 0:
                        o = self.sell(data=d, size=sell_size, exectype=bt.Order.Market)
                        self.orders[d] = o
                        state['take_profit_count'] = 2
                        continue
```
改为：
```python
                    if sell_size > 0:
                        o = self.sell(data=d, size=sell_size, exectype=bt.Order.Market)
                        self.pending_reason[o] = 'take_profit_2'
                        self.orders[d] = o
                        state['take_profit_count'] = 2
                        continue
```

- [ ] **Step 5: 加仓处（第173-175行区域）**

将：
```python
                            if add_size > 0:
                                o = self.buy(data=d, size=add_size)
                                self.orders[d] = o
```
改为：
```python
                            if add_size > 0:
                                o = self.buy(data=d, size=add_size)
                                self.pending_reason[o] = 'add_on'
                                self.orders[d] = o
```

- [ ] **Step 6: 初始建仓处（第210-211行区域）**

将：
```python
                o = self.buy(data=d, size=buy_size)
                self.orders[d] = o
```
改为：
```python
                o = self.buy(data=d, size=buy_size)
                self.pending_reason[o] = 'initial_buy'
                self.orders[d] = o
```

- [ ] **Step 7: 运行全部策略测试**

```
cd my_strategy
pytest tests/test_strategy.py -v
```

预期：所有测试 PASS（包括原有的 `test_entry_signal_triggers_buy` 和 `test_take_profit_1_triggers`）

- [ ] **Step 8: Commit strategy.py 变更**

```bash
git add my_strategy/strategy.py my_strategy/tests/test_strategy.py
git commit -m "feat: add order reason tagging and episode tracking to MyStrategy"
```

---

### Task 7: 新增 `_print_trade_stats` + 对应测试

**Files:**
- Modify: `my_strategy/backtest.py`
- Create: `my_strategy/tests/test_backtest.py`

- [ ] **Step 1: 创建 `tests/test_backtest.py` 并写失败测试**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pandas as pd
from datetime import date
from backtest import _print_trade_stats


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
```

- [ ] **Step 2: 运行测试，确认失败**

```
cd my_strategy
pytest tests/test_backtest.py -v
```

预期：FAIL（`ImportError: cannot import name '_print_trade_stats' from 'backtest'`）

- [ ] **Step 3: 在 `backtest.py` 中新增 `_print_trade_stats` 函数**

在 `print_results` 函数之前插入：

```python
def _print_trade_stats(df):
    completed = df[df['status'] == 'completed'].copy() if 'status' in df.columns else pd.DataFrame()
    print("\n========== 交易统计 ==========")
    total = len(df)
    n_completed = len(completed)
    print(f"总交易笔数：{total}（已完成 {n_completed}，未平仓 {total - n_completed}）")
    if completed.empty:
        print("无已完成交易")
        print("==============================\n")
        return
    winners = completed[completed['return_pct'] > 0]
    losers = completed[completed['return_pct'] <= 0]
    win_rate = len(winners) / len(completed) * 100
    avg_ret = completed['return_pct'].mean()
    avg_win = winners['return_pct'].mean() if not winners.empty else 0.0
    avg_loss = losers['return_pct'].mean() if not losers.empty else 0.0
    payoff = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
    total_profit = winners['gross_pnl'].sum() if not winners.empty else 0.0
    total_loss = abs(losers['gross_pnl'].sum()) if not losers.empty else 0.0
    profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
    print(f"\n--- 交易质量 ---")
    print(f"胜率：{win_rate:.1f}%（{len(winners)} 盈 / {len(losers)} 亏）")
    print(f"平均收益率：{avg_ret:.2f}%（盈利 {avg_win:.2f}% / 亏损 {avg_loss:.2f}%）")
    print(f"盈亏比：{payoff:.2f}")
    print(f"利润因子：{profit_factor:.2f}")
    print(f"最大单笔盈利：{completed['return_pct'].max():.2f}%")
    print(f"最大单笔亏损：{completed['return_pct'].min():.2f}%")
    print(f"\n--- 时间维度 ---")
    avg_hold = completed['holding_days'].mean()
    avg_hold_win = winners['holding_days'].mean() if not winners.empty else 0.0
    avg_hold_loss = losers['holding_days'].mean() if not losers.empty else 0.0
    print(f"平均持仓天数：{avg_hold:.1f}（盈利 {avg_hold_win:.1f} / 亏损 {avg_hold_loss:.1f}）")
    print(f"最长持仓：{int(completed['holding_days'].max())} 天，最短持仓：{int(completed['holding_days'].min())} 天")
    entry_dates = pd.to_datetime(completed['entry_date'])
    n_months = entry_dates.dt.to_period('M').nunique()
    freq = len(completed) / n_months if n_months > 0 else 0.0
    print(f"每月平均交易频次：{freq:.1f} 笔")
    print(f"\n--- 策略信号分析 ---")
    for reason in ['MA60止损', 'MA25清仓']:
        subset = completed[completed['exit_reason'] == reason]
        if subset.empty:
            continue
        pct = len(subset) / len(completed) * 100
        w = len(subset[subset['return_pct'] > 0])
        l = len(subset[subset['return_pct'] <= 0])
        print(f"{reason}：{pct:.1f}%（盈利 {w} 笔 / 亏损 {l} 笔）")
    print("==============================\n")
```

- [ ] **Step 4: 运行测试，确认通过**

```
cd my_strategy
pytest tests/test_backtest.py -v
```

预期：全部 PASS

---

### Task 8: 更新 `print_results` 输出 `trade_summary.csv`

**Files:**
- Modify: `my_strategy/backtest.py:70-95`（`print_results` 函数）

- [ ] **Step 1: 将 `print_results` 中的 `trade_df` 相关代码替换**

将：
```python
    trade_df = pd.DataFrame(r.order_log)
    if not trade_df.empty:
        trade_df.to_csv(results_dir / 'trade_list.csv', index=False)
        print(f"交易记录已保存到 {results_dir / 'trade_list.csv'}")
```
改为：
```python
    trade_df = pd.DataFrame(r.order_log)
    if not trade_df.empty:
        trade_df.to_csv(results_dir / 'trade_list.csv', index=False)
        print(f"交易记录已保存到 {results_dir / 'trade_list.csv'}")

    summary_df = pd.DataFrame(r.trade_log)
    if not summary_df.empty:
        summary_df.to_csv(results_dir / 'trade_summary.csv', index=False)
        print(f"完整交易汇总已保存到 {results_dir / 'trade_summary.csv'}")
    _print_trade_stats(summary_df if not summary_df.empty else pd.DataFrame())
```

- [ ] **Step 2: 运行全部测试**

```
cd my_strategy
pytest tests/ -v
```

预期：所有测试 PASS

- [ ] **Step 3: 端到端手动验证（若有指标 CSV 数据）**

若 `my_strategy/data/` 下有 `*_indicators.csv` 文件，运行：

```
cd my_strategy
python backtest.py
```

检查：
1. 控制台出现 `========== 交易统计 ==========` 区块
2. `results/trade_summary.csv` 文件生成，且列名与设计文档一致
3. `results/trade_list.csv` 新增 `reason` 和 `episode` 列

- [ ] **Step 4: 最终 commit**

```bash
git add my_strategy/backtest.py my_strategy/tests/test_backtest.py
git commit -m "feat: output trade_summary.csv and print strategy statistics"
```

---

## 自检记录

- **Spec 覆盖**：订单打标签 ✓、episode 追踪 ✓、trade_summary.csv 全列 ✓、汇总统计3个维度 ✓、incomplete 处理 ✓
- **Placeholder 扫描**：无 TBD/TODO，所有代码块完整
- **类型一致性**：`_finalize_episode` 写入的 `trade_log` 字段名与 `_print_trade_stats` 读取的列名完全匹配（`status`, `return_pct`, `gross_pnl`, `holding_days`, `exit_reason`, `entry_date`）；`order_log` 的 `reason`/`episode` 字段在 Task 5 和 Task 6 均一致写入
