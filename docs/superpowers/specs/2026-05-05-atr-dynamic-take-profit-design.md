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

`_reset_state` 中将这两个字段初始化为 `None`，在 `initial_buy` 成交后赋值。

### next() 中的使用

```python
# 原来：
if pnl_pct >= self.p.take_profit_1_pct:
# 改为：
tp1 = state['tp1_pct'] or self.p.take_profit_1_pct  # fallback 兼容
if pnl_pct >= tp1:
```

### 新增配置参数

在 `config.json` 和 `MyStrategy.params` 中新增：

| 参数 | 默认值 | 含义 |
|------|--------|------|
| `atr_period` | 20 | 计算 ATR 的天数窗口 |
| `atr_multiplier` | 1.5 | ATR 倍数 k |
| `take_profit_min_pct` | 0.03 | 止盈阈值下限 3% |
| `take_profit_max_pct` | 0.12 | 止盈阈值上限 12% |

原有 `take_profit_1_pct` / `take_profit_2_pct` 保留作 fallback（ATR 数据不足时使用）。

## 改动文件

| 文件 | 改动内容 |
|------|----------|
| `my_strategy/strategy.py` | 新增ATR指标初始化；`stock_state` 新增 `tp1_pct`/`tp2_pct`；`notify_order` 中计算并写入；`next()` 中替换固定阈值 |
| `my_strategy/config.json` | 新增4个参数 |

## 边界情况

- **ATR数据不足**（入场时 bar 数 < atr_period）：`atr[d][0]` 可能为 NaN，此时 fallback 到 `take_profit_1_pct` 固定值
- **atr_period=20，但数据刚开始**：backtrader ATR 指标在数据不足时返回 NaN，需在计算前做 `if atr_val == atr_val` 判断
