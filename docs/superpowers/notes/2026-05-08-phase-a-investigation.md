# Phase A 实施前调研报告

**日期**：2026-05-08  
**目的**：确认实际数据源结构，为 Phase A 统计分析框架 Tasks 1–16 提供可靠的输入依据。

---

## Step 1：trade_list.csv 是否含 commission/stamp_duty

**文件路径**：`my_strategy/results/trade_list.csv`（注意：实际在 `results/`，不在 `reports/`）

**实际列清单**（第 1 行表头）：
```
date, ts_code, side, size, price, reason, episode
```

**结论**：无 `commission` 列，无 `stamp_duty` 列。共 7 列，仅记录成交方向、手数、价格、原因、轮次编号。

**cost_breakdown 实施策略**：Task 15 必须采用反推方案——
- 买入手续费：`commission_rate × price × size`（commission_rate 从 backtest.py 配置中读取，目前设为 0.0003）
- 卖出手续费：同上
- 印花税：仅卖出方向计，`0.001 × price × size`
- 回合总成本：买入佣金 + 卖出佣金 + 印花税
- 数据源：`trade_list.csv` 按 `episode` 分组，匹配 `side=buy` / `side=sell` 记录

---

## Step 2：position_count_log 的 schema

**赋值位置**：`my_strategy/src/strategy.py` 第 98 行初始化，第 425 行追加：

```python
# strategy.py:98
self.position_count_log = []

# strategy.py:425（每根 Bar 的 next() 末尾执行）
self.position_count_log.append(self._current_position_count())
```

**`_current_position_count()` 逻辑**（第 101–109 行）：遍历所有 data，统计 `position.size > 0` 或有存活买单的标的数量，返回一个 `int`。

**结论**：`position_count_log` 是 `list[int]`，每个元素是当根 Bar 结束时的同时持仓标的数量（含挂单未成交的买入）。

**concurrent_positions_stats 输入解析方式**：
- 直接对 list 做 `max / min / mean / median / percentile`
- 可按 Bar 索引对应日期序列生成时序分布（strategy 对象同时有 `self.datas[0]`，可按 Bar 编号反查日期）
- `backtest.py` 第 828 行：`position_count_log=getattr(r, 'position_count_log', None)` 已透传到 `_print_trade_stats()`

---

## Step 3：daily.csv 复权状态

**文件路径**：`my_strategy/data/daily/{ts_code}.csv`（如 `000001.SZ.csv`）

**实际列清单**（`000001.SZ.csv` 第 1 行）：
```
trade_date, open, high, low, close, volume, amount, pct_chg, circ_mv
```

**复权状态确认**：`my_strategy/src/downloader.py` 第 70–75 行调用 Tushare `pro_bar` 时显式传入 `adj='qfq'`（前复权）：

```python
seg = _call_with_timeout(ts.pro_bar,
    ts_code=ts_code,
    adj='qfq',      # ← 前复权
    ...
)
```

**结论**：所有 `data/daily/*.csv` 均为**前复权（qfq）**价格序列。

**daily_position_pnl 注意事项**：
- 直接使用 `close` 计算持仓市值和浮盈浮亏，无需额外复权处理
- 前复权价格历史一致性已保证，但绝对价格与原始成交价（`trade_list.csv` 中的 `price`）可能存在微小偏差（因为 trade_list 记录的是成交时的前复权价，随复权基准更新会略有漂移）
- 建议在报告注释中说明：PnL 计算基于同一复权基准，内部一致，但不代表历史真实成交现金

---

## Step 4：signal_correlation_matrix 最终白名单

**识别方法**：从 `trade_summary.csv` 表头筛选 `entry_` 前缀、`ma_alignment`、`macd_zone`、`factor_` 前缀字段：

```
entry_kdj_j, entry_ma60_dist_pct, entry_circ_mv, entry_week_kdj_j,
entry_hs300_dif_above_zero, entry_hs300_bull_align,
entry_stock_bull_align, entry_stock_above_ma25,
entry_sector_bull_align, entry_sector_above_ma25,
entry_sector_dif_above_zero, entry_sector_week_macd_zone,
entry_sector_month_macd_zone, entry_sector_momentum_60d,
ma_alignment, macd_zone, entry_week_macd_zone, entry_month_macd_zone
```

**最终白名单（15 个）**，结合 spec §3.2.1 固定清单 + trade_summary 实际字段：

| # | 字段名 | 类型 | 来源 |
|---|--------|------|------|
| 1 | `entry_hs300_dif_above_zero` | bool | trade_summary |
| 2 | `entry_hs300_bull_align` | bool | trade_summary |
| 3 | `entry_stock_bull_align` | bool | trade_summary |
| 4 | `entry_stock_above_ma25` | bool | trade_summary |
| 5 | `entry_sector_dif_above_zero` | bool | trade_summary |
| 6 | `entry_sector_above_ma25` | bool | trade_summary |
| 7 | `entry_sector_bull_align` | bool | trade_summary |
| 8 | `entry_sector_week_macd_zone` | cat | trade_summary |
| 9 | `entry_sector_month_macd_zone` | cat | trade_summary |
| 10 | `entry_month_macd_zone` | cat | trade_summary（即 `entry_month_macd_zone`） |
| 11 | `entry_week_macd_zone` | cat | trade_summary |
| 12 | `ma_alignment` | cat | trade_summary |
| 13 | `entry_kdj_j` | numeric | trade_summary（对应 spec factor_kdj_j） |
| 14 | `entry_ma60_dist_pct` | numeric | trade_summary（对应 spec factor_ma60_dist） |
| 15 | `entry_sector_momentum_60d` | numeric | trade_summary（对应 spec factor_momentum_60d） |

**说明**：
- spec §3.2.1 中的 `hs300_dif_above_zero` 等字段在 trade_summary 中带 `entry_` 前缀（如 `entry_hs300_dif_above_zero`），白名单统一使用实际列名
- `entry_circ_mv`、`entry_week_kdj_j` 不列入白名单（流通市值为规模变量非信号、周 KDJ 与日 KDJ 高度相关）
- `macd_zone`（日线）与 `entry_week_macd_zone` 保留，但在相关矩阵中需注意两者 Spearman 相关可能偏高

---

## 附：路径差异说明

| 任务文档中的路径 | 实际路径 |
|----------------|----------|
| `my_strategy/reports/trade_list.csv` | `my_strategy/results/trade_list.csv` |
| `my_strategy/src/strategy.py` | `my_strategy/src/strategy.py`（正确） |
| `my_strategy/data/{ts_code}_daily.csv` | `my_strategy/data/daily/{ts_code}.csv`（在 `daily/` 子目录） |
| `my_strategy/results/trade_summary.csv` | `my_strategy/results/trade_summary.csv`（正确） |
