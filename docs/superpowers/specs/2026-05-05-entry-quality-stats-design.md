# 设计文档：进场质量统计增强

**日期**: 2026-05-05  
**状态**: 已批准，待实现

---

## 1. 背景与目标

当前 `trade_summary.csv` 只记录了出场维度的数据（exit_reason、holding_days、return_pct 等），缺乏进场时的市场状态信息，无法回答"哪种信号环境下进场效果最好"。

本次改动目标：
- 为每笔交易补充5个进场质量维度（KDJ_J、MA60距离、行业、MA排列、MACD区间）
- 输出聚合统计（CSV + 终端打印）
- 修复持仓数统计（替换无意义的资金占用率）
- 补充基准全区间收益对比
- 支持对基准指数独立运行策略并对比收益

---

## 2. 方案选择

采用**方案 B（事后富化）**：

- `calc_indicators.py` 新增指标列
- 回测后 `backtest.py` 按 `(ts_code, entry_date)` join 指标 CSV，富化 trade_summary
- `strategy.py` 只做最小改动（持仓数 log）
- 行业信息由 `downloader.py` 从 Tushare `pro.stock_basic()` 下载

优点：策略逻辑与统计报告完全解耦，新增统计维度不影响回测速度。

---

## 3. 文件改动清单

| 文件 | 改动内容 |
|---|---|
| `downloader.py` | 新增 `download_sector_info()` |
| `calc_indicators.py` | 新增 MA144、MA180、KDJ_J 三列 |
| `strategy.py` | 移除 `max_capital_utilization`；新增 `position_count_log` |
| `backtest.py` | 富化 trade_summary；新增聚合统计；指数策略；持仓数统计；基准全区间行 |

新增数据文件：`data/stock_sector.csv`

---

## 4. 新增指标定义（calc_indicators.py）

### MA144 / MA180
```python
df['ma144'] = df['close'].rolling(144, min_periods=144).mean().round(2)
df['ma180'] = df['close'].rolling(180, min_periods=180).mean().round(2)
```

### KDJ_J（9日标准算法）
```python
low9  = df['low'].rolling(9, min_periods=9).min()
high9 = df['high'].rolling(9, min_periods=9).max()
rsv   = ((df['close'] - low9) / (high9 - low9).replace(0, 1) * 100).clip(0, 100)
k     = rsv.ewm(com=2, adjust=False).mean()
d     = k.ewm(com=2, adjust=False).mean()
df['kdj_j'] = (3 * k - 2 * d).round(2)
```

当 high9 == low9 时用 `.replace(0, 1)` 防止除零（rsv 此时为 100，clip 到合理范围）。

---

## 5. 进场质量维度定义

### 5.1 新增 trade_summary 列

| 列名 | 类型 | 说明 |
|---|---|---|
| `entry_kdj_j` | float | 进场当日 KDJ_J 值 |
| `entry_ma60_dist_pct` | float | `(close - ma60) / ma60 * 100`，进场距 MA60 百分比 |
| `industry` | str | 行业分类（from stock_sector.csv） |
| `ma_alignment` | str | MA 排列状态（见下） |
| `macd_zone` | str | MACD 区间（见下） |

### 5.2 MA 排列规则（基于 MA25/MA60/MA144/MA180）

| 标签 | 条件 |
|---|---|
| `全多头` | MA25 > MA60 > MA144 > MA180 |
| `全空头` | MA25 < MA60 < MA144 < MA180 |
| `局部多头` | MA25 > MA60，不满足全多头 |
| `局部空头` | MA25 < MA60，不满足全空头 |
| `混合` | 其他情况 |

若 MA144 或 MA180 为 NaN（数据不足），降级只看 MA25/MA60。

### 5.3 MACD 区间规则

MACD 柱体 = 2 × (DIF − DEA)

| 标签 | 条件 |
|---|---|
| `区间0` | MACD ≤ 0 |
| `区间1` | MACD > 0 且 MACD > DIF 且 MACD > DEA |
| `区间2` | MACD > 0 且（DIF > MACD 或 DEA > MACD）且不满足区间3 |
| `区间3` | MACD > 0 且 DIF > MACD 且 DEA > MACD |

---

## 6. 行业信息下载（downloader.py）

新增函数 `download_sector_info(cfg)`：
```python
def download_sector_info(data_dir):
    pro = ts.pro_api()
    df = pro.stock_basic(fields='ts_code,industry')
    df.to_csv(Path(data_dir) / 'stock_sector.csv', index=False)
```

在 `main()` 末尾调用一次。用户需要重新跑 `python downloader.py` 生成该文件。

---

## 7. strategy.py 改动

### 7.1 移除 max_capital_utilization

删除 `__init__` 中的 `self.max_capital_utilization = 0.0`，以及 `next()` 末尾的更新逻辑。

### 7.2 新增 position_count_log

```python
# __init__
self.position_count_log = []

# next() 末尾（for 循环外）
self.position_count_log.append(self._current_position_count())
```

---

## 8. backtest.py 改动

### 8.1 富化 trade_summary

新增函数 `_enrich_trade_summary(summary_df, cfg)`：
1. 读取 `stock_sector.csv` → industry 映射 dict
2. 对每行 trade_summary，按 `(ts_code, entry_date)` 查找对应 `_indicators.csv` 的当天行
3. 提取 `kdj_j`、`ma60`、`close`、`ma25`、`ma144`、`ma180`、`dif`、`dea`、`macd` 计算各维度标签
4. 写回 `trade_summary.csv`

### 8.2 聚合统计打印

新增函数 `_print_entry_quality_stats(df)`，对 `completed` 子集：

- 按 `ma_alignment` 分组：笔数、胜率、平均收益
- 按 `macd_zone` 分组：笔数、胜率、平均收益
- 按 `industry` 分组：笔数、胜率、平均收益、总盈亏（Top 10）
- KDJ_J 分桶统计：<20、20-50、50-80、>80 各桶的胜率和平均收益
- MA60 距离分桶：≤1%、1-3%、3-5%、>5% 各桶的胜率和平均收益

### 8.3 持仓数统计（替换资金占用率）

从 `r.position_count_log` 计算并打印：
```
最大同时持仓：N 只
最小同时持仓：N 只
平均同时持仓：N.N 只
中位数持仓：N.N 只
```

### 8.4 基准全区间收益行

`_compute_benchmarks_returns` 现有 `annual` dict 和 `annualized` 字段已足够。  
在年度收益表格末尾新增一行：

```
全区间  +XX.XX%  +XX.XX%  +X.XX%  +XX.XX%  +X.XX%
```

策略全区间年化收益用 `bt.analyzers.Returns` 的 `rnorm100`；总收益从 `_TimeReturn` 累积乘积读取（`(1+time_return).cumprod().iloc[-1] - 1`）。年度收益表"全区间"行展示年化收益率（与各基准 `annualized` 字段对齐）。

### 8.5 指数策略模拟

新增函数 `run_index_strategy(cfg, index_code) -> dict`：
1. 读取 `data/{index_code}.csv`，调用 `compute_indicators()` 计算指标（不保存）
2. 新建 cerebro，`max_positions=1`，`initial_cash=cfg['initial_cash']`
3. 运行策略，提取 `trade_log`
4. 返回 `{'code': index_code, 'annual_return': ..., 'total_return': ..., 'win_rate': ..., 'n_trades': ...}`

在 `print_results` 中遍历 `benchmark_codes`，依次调用并打印汇总表：

```
========== 指数策略回测 ==========
指数         年化收益    总收益    胜率    笔数
000300.SH   +12.34%   +85.2%   58.3%    24
000905.SH   +15.67%  +110.4%   61.5%    26
==================================
```

---

## 9. 执行顺序（用户操作）

1. `python downloader.py` — 下载 stock_sector.csv（如已有指数 CSV 则跳过指数下载）
2. `python calc_indicators.py` — 重新计算所有股票的 indicators（新增 ma144/ma180/kdj_j）
3. `python backtest.py` — 回测，自动富化并输出新统计

---

## 10. 不在本次范围内

- KDJ_J 不加入交易策略逻辑（只用于事后统计）
- MA144/MA180 不加入 `StockData` feed lines（只存在 indicators CSV）
- 指数策略模拟不改变主策略的任何参数
