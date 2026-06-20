# Design: 完整交易路径统计与策略分析

**Date:** 2026-05-04  
**Scope:** `my_strategy/strategy.py`, `my_strategy/backtest.py`  
**Output:** `results/trade_summary.csv`, `results/trade_list.csv`（新增 reason 列）

---

## 目标

回测结束后，输出两个 CSV 文件：

1. `trade_list.csv` — 原始订单日志（已有），新增 `reason` 列标记每笔订单的触发原因
2. `trade_summary.csv` — 每行一个完整交易周期，含收益率、持仓天数、出场原因等

同时在控制台打印汇总统计区块，帮助分析策略改进方向。

---

## 一、核心机制：订单打标签 + 交易周期追踪

### 1.1 `pending_reason` 字典

在 `MyStrategy.__init__()` 中新增：

```python
self.pending_reason = {}  # Order -> reason string
```

每次在 `next()` 下单时，立刻记录原因：

```python
o = self.buy(data=d, size=buy_size)
self.pending_reason[o] = 'initial_buy'
```

| 触发场景 | reason 值 |
|---|---|
| 初始建仓 | `initial_buy` |
| 加仓（第1/2次）| `add_on` |
| 止盈第一次（+5%）| `take_profit_1` |
| 止盈第二次（+10%）| `take_profit_2` |
| MA60 止损清仓 | `MA60_stop` |
| MA25 跟踪止盈清仓 | `MA25_stop` |

`notify_order()` 成交时从字典中取出 reason，写入 `order_log` 条目，并从字典中删除该键。

### 1.2 `episode_state` 字典

在 `MyStrategy.__init__()` 中新增：

```python
self.episode_state = {}   # data -> {buys: [], sells: [], episode_num: int}
self.trade_log = []       # 已完成的完整交易列表
```

每只股票初始化：
```python
for d in self.datas:
    self.episode_state[d] = {'buys': [], 'sells': [], 'episode_num': 0}
```

**买单成交时**：将 `(date, size, price)` 追加到 `episode_state[d]['buys']`。

**卖单成交时**：将 `(date, size, price, reason)` 追加到 `episode_state[d]['sells']`。  
当 `sum(sells.size) >= sum(buys.size)` 时，触发周期结束逻辑，计算统计并推入 `trade_log`，然后重置 buys/sells 列表，episode_num +1。

**回测结束时**（`stop()` 方法）：将所有 buys 非空但未平仓的周期以 `status=incomplete` 推入 `trade_log`。

---

## 二、`trade_summary.csv` 列结构

| 列名 | 类型 | 说明 |
|---|---|---|
| `ts_code` | str | 股票代码 |
| `episode` | int | 该股票第几轮交易（从1开始） |
| `entry_date` | date | 首次建仓日期 |
| `exit_date` | date | 最后清仓日期（incomplete 为空） |
| `holding_days` | int | 持有自然日天数 |
| `avg_cost` | float | 加权平均买入成本（元/股） |
| `avg_exit_price` | float | 加权平均卖出价（元/股，incomplete 为空） |
| `total_shares` | int | 总买入股数 |
| `gross_pnl` | float | 毛盈亏（元）= (avg_exit_price - avg_cost) × total_shares |
| `return_pct` | float | 收益率（%）= (avg_exit_price - avg_cost) / avg_cost × 100 |
| `add_count` | int | 加仓次数（0/1/2） |
| `take_profit_count` | int | 触发分批止盈次数（0/1/2） |
| `exit_reason` | str | 最终出场原因：`MA60止损` / `MA25清仓` / `未平仓` |
| `status` | str | `completed` / `incomplete` |

`trade_list.csv` 在原有列基础上新增 `reason` 列和 `episode` 列，可通过 `ts_code + episode` 与 `trade_summary.csv` 关联查看每笔完整交易的子订单明细。

---

## 三、汇总统计（控制台输出）

回测结束后新增 `========== 交易统计 ==========` 区块，包含：

### 交易质量
- 总交易笔数 / 已完成 / 未平仓
- 胜率（return_pct > 0 的比例）
- 平均收益率（全部 / 盈利交易 / 亏损交易）
- 盈亏比（平均盈利 / 平均亏损绝对值）
- 最大单笔盈利 % / 最大单笔亏损 %
- 利润因子（总盈利之和 / 总亏损绝对值之和）

### 时间维度
- 平均持仓天数（全部 / 盈利 / 亏损）
- 最长持仓 / 最短持仓天数
- 每月平均交易频次

### 策略信号分析
- MA60止损 占 X%（其中盈利 Y 笔 / 亏损 Z 笔）
- MA25清仓 占 X%（其中盈利 Y 笔 / 亏损 Z 笔）

---

## 四、改动范围

| 文件 | 改动内容 |
|---|---|
| `my_strategy/strategy.py` | 新增 `pending_reason`、`episode_state`、`trade_log`；修改 `__init__`、`notify_order`、`next()`（每处下单加一行打标签）；新增 `stop()` 方法处理未平仓周期 |
| `my_strategy/backtest.py` | `print_results()` 中新增：读取 `r.trade_log` 生成 `trade_summary.csv`；打印汇总统计区块；`trade_list.csv` 保留，新增 reason 列 |

不改动：`calc_indicators.py`、`downloader.py`、`config.json`、数据文件。
