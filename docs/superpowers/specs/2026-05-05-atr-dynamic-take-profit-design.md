# ATR 自适应止盈设计文档

**日期：** 2026-05-05  
**状态：** 待实现

## 背景

现有策略的止盈1阈值固定为5%，止盈2固定为10%。不同股票波动率差异大，固定阈值存在两个问题：
- 高波动股：5%是日常噪音，容易被过早触发
- 低波动股：5%需要较长时间才能到达，阈值偏高

## 目标

用入场时的 ATR（平均真实波幅）动态计算每笔交易的止盈阈值，让阈值与该股票当前的真实波动幅度匹配。

## 设计

### 核心公式

```
atr_pct   = ATR(N日) / 入场成交价
tp1_pct   = clip(k × atr_pct, min_pct, max_pct)
tp2_pct   = tp1_pct × 2
```

- `clip` 将阈值约束在 [min_pct, max_pct] 之间，防止极端值
- `tp2_pct` 始终为 `tp1_pct` 的2倍，与现有逻辑保持一致

### 计算时机

- **`__init__`**：为每只股票初始化 `bt.indicators.ATR(d, period=atr_period)`，存入 `self.atr[d]`，backtrader 自动逐 bar 更新
- **`notify_order`**：在 `initial_buy` 成交时，读取当前 bar 的 ATR 值，计算 `tp1_pct` / `tp2_pct`，写入该股票的 `stock_state`
- **加仓（`add_on`）**：不重新计算，止盈阈值维持首次建仓时的值
- **重新入场**：下一次 `initial_buy` 时重新计算，每个 episode 独立快照

### stock_state 新增字段

| 字段 | 类型 | 含义 |
|------|------|------|
| `tp1_pct` | float | 本 episode 的止盈1阈值（入场时计算） |
| `tp2_pct` | float | 本 episode 的止盈2阈值（= tp1_pct × 2） |
| `initial_size` | int | 首次建仓成交股数，用于固定两次止盈的卖出量 |

`_reset_state` 中将这三个字段初始化为 `None`，在 `initial_buy` 成交后赋值。

### 止盈卖出数量

两次止盈都卖出**原始建仓量的1/3**（取整到100股），而非当时持仓的1/3：

```python
tp_sell_size = int(state['initial_size'] / 3 / 100) * 100
```

这样 tp1 和 tp2 卖出的绝对股数相同，合计约卖出原始建仓量的2/3。

### 止盈成本价基准

tp1 和 tp2 的盈亏比均以**原始建仓价（`state['entry_price']`）**为基准，不受加仓均价影响：

```python
pnl_pct = (close - state['entry_price']) / state['entry_price']
```

这与现有代码行为一致，无需修改此计算逻辑。

### next() 中的使用

```python
# 止盈阈值：用动态值，fallback 到配置固定值
tp1 = state['tp1_pct'] or self.p.take_profit_1_pct
tp2 = state['tp2_pct'] or self.p.take_profit_2_pct

# 卖出数量：用原始建仓量的1/3
tp_sell_size = int((state['initial_size'] or pos.size) / 3 / 100) * 100
```

### 大阳线逻辑说明（现有行为，不变）

`big_candle_seen`（持仓期间出现 >1% 阳线）**只禁止加仓**，不影响初始建仓，也不影响清仓后的重新入场。`_reset_state` 在清仓时重置该标记。此行为保持不变。

### 新增配置参数

在 `config.json` 和 `MyStrategy.params` 中新增：

| 参数 | 默认值 | 含义 |
|------|--------|------|
| `atr_period` | 20 | 计算 ATR 的天数窗口 |
| `atr_multiplier` | 1.5 | ATR 倍数 k |
| `take_profit_min_pct` | 0.03 | 止盈阈值下限 3% |
| `take_profit_max_pct` | 0.12 | 止盈阈值上限 12% |

原有 `take_profit_1_pct` / `take_profit_2_pct` 保留作 fallback（ATR 数据不足时使用）。

## 输出到回测 CSV

`_finalize_episode` 中在 `trade_log` 记录里新增两个字段：

| 字段 | 含义 |
|------|------|
| `tp1_pct` | 本 episode 实际使用的止盈1阈值（ATR动态值或fallback固定值） |
| `tp2_pct` | 本 episode 实际使用的止盈2阈值 |

这两个值从 `stock_state` 读取，在 episode 结束时一并写入，最终体现在 `results/trade_summary.csv` 中。

## 改动文件

| 文件 | 改动内容 |
|------|----------|
| `my_strategy/strategy.py` | 新增ATR指标初始化；`stock_state` 新增 `tp1_pct`/`tp2_pct`/`initial_size`；`notify_order` 中计算并写入；`next()` 中替换固定阈值和卖出数量；`_finalize_episode` 输出 `tp1_pct`/`tp2_pct` 到 trade_log |
| `my_strategy/config.json` | 新增4个参数 |

## 边界情况

- **ATR数据不足**（入场时 bar 数 < atr_period）：`atr[d][0]` 可能为 NaN，此时 fallback 到 `take_profit_1_pct` 固定值
- **atr_period=20，但数据刚开始**：backtrader ATR 指标在数据不足时返回 NaN，需在计算前做 `if atr_val == atr_val` 判断
