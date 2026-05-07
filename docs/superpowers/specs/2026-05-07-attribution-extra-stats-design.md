# 归因报告扩展：4 张关键统计表

**日期**：2026-05-07
**范围**：`my_strategy/tools/attribution.py`、`my_strategy/tests/test_attribution_run.py`

## 背景

现有归因输出 5 份报告（trade_profile / top_trades / bottom_trades / sector_winrate / factor_alpha），仅能从 **行业、收益分桶、3 个因子** 三个角度切片。

针对当前 5911 笔交易（小亏占比 54%、3 个因子 alpha 全负、bottom_trades 全是未平仓）的诊断结果，4 个关键维度数据缺失：

1. 不同 **exit_reason** 的胜率与收益——无法判断哪个出场逻辑在拖后腿
2. 不同 **add_count** 的最终结果——加仓机制是否真的有用未知
3. 不同 **入场条件** 的判别力——KDJ-J、MA 对齐、MACD 区间各自对结果的贡献未知
4. **年度稳定性**——不知道整体表现是不是只在某一年炸了

## 目标

在 `attribution.run()` 末尾追加 4 张新报告，全部沿用现有 `_join_trades_with_signals` 数据流，不引入新输入文件、不修改现有 5 张表。

## 输出文件

全部写入 `reports/`（路径来自 `cfg['attribution_report_dir']`）。

### 1. `reports/exit_reason_stats.csv`

按 `exit_reason` 分组：

| 列 | 含义 |
|---|---|
| exit_reason | 出场原因（MA25清仓 / take_profit_1 / take_profit_2 / 跌停止损 / 未平仓 ...） |
| count | 笔数 |
| win_rate | 收益 > 0 的比例（保留 4 位） |
| avg_return | 平均 return_pct |
| avg_holding_days | 平均持仓天数 |
| avg_add_count | 平均加仓次数 |

排序：`count` 降序。

### 2. `reports/add_count_stats.csv`

按 `add_count` 分组（0 / 1 / 2 / 3+，超过 3 合并为 "3+"）：

| 列 | 含义 |
|---|---|
| add_count | 加仓次数（"0" / "1" / "2" / "3+"） |
| count | 笔数 |
| win_rate | 收益 > 0 的比例 |
| avg_return | 平均 return_pct |
| avg_holding_days | 平均持仓天数 |
| pct_completed | 已平仓比例（status == "completed" / count）|

排序：`add_count` 升序。`pct_completed` 用于辨别"加得越多越容易卡住"。

### 3. `reports/entry_condition_stats.csv`（A 方案：单条件长表）

对 7 个入场字段分别 group，结果 union：

| 列 | 含义 |
|---|---|
| condition_field | 字段名 |
| bucket | 桶名 |
| count | 笔数 |
| win_rate | 胜率 |
| avg_return | 平均收益 |
| avg_holding_days | 平均持仓天数 |

**字段与分桶**：

| condition_field | bucket 规则 |
|---|---|
| entry_kdj_j | 固定阈值 `[0,40) / [40,80) / [80,100) / [100+)` |
| entry_ma60_dist_pct | 固定阈值 5 桶：`[<0%) / [0%, 5%) / [5%, 10%) / [10%, 20%) / [20%+)`（用于事前判断，无 look-ahead） |
| ma_alignment | 直接按值 group（全多头 / 局部多头 / 局部空头 / 全空头）|
| macd_zone | 直接按值 group（区间0/1/2/3）|
| entry_week_kdj_j | 同 entry_kdj_j |
| entry_week_macd_zone | 同 macd_zone |
| entry_month_macd_zone | 同 macd_zone |

排序：`condition_field` 升序，组内 `bucket` 升序（数值字段按区间下界，类别字段按字符串）。

### 4. `reports/yearly_stats.csv`

按 `entry_date.dt.year` 分组：

| 列 | 含义 |
|---|---|
| year | 入场年份 |
| count | 笔数 |
| win_rate | 胜率 |
| avg_return | 平均 return_pct |
| median_return | return_pct 中位数（抗大盈/大亏离群值） |
| total_pnl_yuan | sum(gross_pnl)，单位元，真实落账盈亏 |
| avg_holding_days | 平均持仓天数 |

排序：`year` 升序。

> **跨年可比性说明**：策略目前**不复利**（[strategy.py:54](my_strategy/src/strategy.py#L54) 的 `position_limit = initial_cash / max_positions` 在 `__init__` 中只算一次），单仓位金额常数。因此 `total_pnl_yuan` 跨年比较公平、无量级失真。

## 实现位置

```
my_strategy/tools/attribution.py
├── compute_exit_reason_stats(trades)
├── compute_add_count_stats(trades)
├── compute_entry_condition_stats(trades)
│   └── 内部三个分桶 helper（数值固定阈值 / qcut / 类别）
├── compute_yearly_stats(trades)
└── run() 末尾追加四个 to_csv 调用
```

新函数全部接受 `trades` 参数即可（这 4 张表只需 trade_summary 字段，不依赖 signals_log），但与现有函数风格保持一致：返回 `pd.DataFrame`，由 `run()` 负责落盘。

## 错误处理（与现有约定一致）

- 所有新函数：当 trades 为空、目标列缺失、或 group 后无有效行时，**返回带正确表头的空 DataFrame**，不抛异常。
- 数值分桶：含 NaN 的行直接丢弃（`dropna(subset=[field])`），不计入任何桶。
- 固定阈值分桶：超出区间的极端值（如 ma60_dist_pct < 0% 已含；> 20% 入 `[20%+)` 桶），无遗漏。

## 测试

扩展 `my_strategy/tests/test_attribution_run.py`：

```python
EXPECTED_FILES = [
    'trade_profile.csv',
    'top_trades.csv',
    'bottom_trades.csv',
    'sector_winrate.csv',
    'factor_alpha.csv',
    'exit_reason_stats.csv',     # NEW
    'add_count_stats.csv',       # NEW
    'entry_condition_stats.csv', # NEW
    'yearly_stats.csv',          # NEW
]
```

通过条件：跑 `python my_strategy/tests/test_attribution_run.py` 后 9 份报告全部产出且非空（factor_alpha 仍可空，因 indicator 文件可能无 factor_ 列）。

## 文档维护（CLAUDE.md 强制规则）

- `docs/FEATURES.md` §6 「归因分析」章节追加 4 张新表的说明
- `docs/CHANGELOG.md` 顶部追加 2026-05-07 条目

## 非目标（明确不做）

- ❌ 不做入场条件的笛卡尔积交叉表（B 方案），样本会被切薄
- ❌ 不引入新输入文件，不修改 trade_summary / signals_log schema
- ❌ 不在归因里直接给出"应该改什么策略"的结论——只提供数据，决策留给后续 brainstorming
- ❌ 不做月度/季度切片（年度足够）

## 风险

- `entry_kdj_j` 固定阈值在不同市场环境下解释力可能不一致（牛市 J>80 频繁触发，熊市稀少）。如果观察到样本严重偏倚，后续可改五分位（仅作事后归因）。
- `add_count` 的 "3+" 合并桶在 add_count 分布极偏时（比如绝大多数 = 0）信息量很低，但不影响结构正确性。
- yearly_stats 的 `total_pnl_yuan` 不能直接换算成"年度收益率"——需要除以当年初始组合净值才是收益率。本表只回答"绝对盈亏量级"，组合层面年化由 backtest.py 的 `annual_returns` 单独打印。
