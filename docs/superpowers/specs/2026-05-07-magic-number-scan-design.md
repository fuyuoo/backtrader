# 魔数扫描归因：first_buy_size_stats / add_block_stats

**日期**：2026-05-07
**范围**：`my_strategy/src/strategy.py`、`my_strategy/backtest.py`、`my_strategy/tools/attribution.py`、`my_strategy/tests/test_attribution.py`、`my_strategy/tests/test_attribution_run.py`、`docs/FEATURES.md`、`docs/CHANGELOG.md`

## 背景

当前策略含两个魔数 1%，硬编码于 `strategy.py`：

1. **首仓尺寸**（`strategy.py:363`）：`(close - ma60) / ma60 <= 0.01` 时满仓买入；否则 1/3 仓买入。
2. **加仓阻断**（`strategy.py:273`）：持仓期任意一日 `(close - open) / open > 0.01`（>1% 阳线），永久禁止后续加仓。

要回答"1% 是不是最优"，必须先有针对这两个阈值的事前归因表。现有 5911 笔交易归因（trade_profile / sector_winrate / factor_alpha / entry_condition_stats / yearly_stats 等 9 张表）都不能直接评估这两个魔数。

## 目标

新增 2 张归因表，扫描这两个魔数附近多档候选阈值的表现，**只看见、不更改**——魔数实际优化留给下一轮 spec。

## 非目标

- ❌ 不调整策略阈值（本 spec 仅做归因，不改 1%）
- ❌ 不做 `entry_ma60_dist_pct × max_bullish_candle_pct` 二维交叉表
- ❌ 不在归因表里给"应该改成多少"的结论文字
- ❌ 不引入新的输入文件（除回测产物外）

## 数据采集（Part 1）：strategy.py 增加 `max_bullish_candle_pct`

### 现状

`MyStrategy.next()` 持仓分支用 bool `state['big_candle_seen']`：
```python
if open_ > 0 and (close - open_) / open_ > 0.01:
    state['big_candle_seen'] = True
```
加仓判定：`if state['add_count'] < 2 and not state['big_candle_seen']:`

只能告诉我们"在 1% 阈值下是否阻断"。换其他阈值视角即信息丢失。

### 改动

1. `state` 初始化里 `'big_candle_seen': False` 改为 `'max_bullish_candle_pct': 0.0`。
2. 持仓判定改为：
   ```python
   if open_ > 0:
       pct = (close - open_) / open_
       if pct > state['max_bullish_candle_pct']:
           state['max_bullish_candle_pct'] = pct
   ```
3. 加仓判定改为：`if state['add_count'] < 2 and state['max_bullish_candle_pct'] <= 0.01:`
4. 平仓时把 `state['max_bullish_candle_pct']` 写入 `trade_summary.csv` 的新列。

### 行为不变性

阈值仍是 0.01，加仓判定的真值表与原实现完全等价（`max ≤ 0.01` ⇔ `从未出现 > 0.01 的阳线`），下一次回测的 trade_list / signals_log / 现有 9 张归因表与今天**逐行一致**（除新增列外）。

### 数据语义

- **类型**：float
- **单位**：小数（0.0083 = 0.83%）
- **范围**：[0, +∞)
- **含义**：本笔交易（一个 episode）持仓期内全部交易日中 `(close-open)/open` 的最大值；持仓期未出现阳线则记 0
- **NaN 政策**：不出现 NaN（默认 0）

## 归因表（Part 2）：attribution.py 增加 2 张表

### 输出位置

均落入 `cfg['attribution_report_dir']`（默认 `my_strategy/reports/`）。

### Table 1：`first_buy_size_stats.csv`

**目的**：评估首仓尺寸触发线 `entry_ma60_dist_pct ≤ 1%` 的 1% 是否最优。

**输入字段**：`trades['entry_ma60_dist_pct']`（已存在，无需采集改动；单位百分比，例 0.5 表示 0.5%）。

**分桶**（11 桶，1% 附近 0.5% 步长）：

| bucket 标签 | 区间（百分点） |
|---|---|
| `[<-1%)` | (-∞, -1) |
| `[-1%,-0.5%)` | [-1, -0.5) |
| `[-0.5%,0%)` | [-0.5, 0) |
| `[0%,0.5%)` | [0, 0.5) |
| `[0.5%,1%)` | [0.5, 1) |
| `[1%,1.5%)` | [1, 1.5) |
| `[1.5%,2%)` | [1.5, 2) |
| `[2%,3%)` | [2, 3) |
| `[3%,5%)` | [3, 5) |
| `[5%,10%)` | [5, 10) |
| `[10%+)` | [10, +∞) |

`pd.cut(bins=[-inf,-1,-0.5,0,0.5,1,1.5,2,3,5,10,inf], right=False, include_lowest=False)`。

**列**：

| 列 | 含义 |
|---|---|
| bucket | 桶标签 |
| count | 笔数 |
| win_rate | `return_pct > 0` 的比例（4 位） |
| avg_return | 平均 `return_pct`（4 位） |
| median_return | 中位数 `return_pct`（4 位） |
| avg_holding_days | 平均持仓天数（1 位） |
| avg_add_count | 平均加仓次数（2 位） |
| pct_completed | `status == 'completed'` 比例（4 位） |

**排序**：按 bucket 区间顺序（与上表自上而下一致）。

**`gross_pnl` 不输出的理由**：仓位差异（≤1% 满仓 vs >1% 1/3 仓）让 `gross_pnl` 在阈值两侧不可比；`return_pct` 是仓位无关量，是干净的阈值选择依据。

### Table 2：`add_block_stats.csv`

**目的**：评估加仓阻断阈值 `max_bullish_candle_pct > 1%` 的 1% 是否最优。

**输入字段**：`trades['max_bullish_candle_pct']`（Part 1 新增；单位小数，例 0.0083 = 0.83%）。

**分桶**（9 桶，1% 附近 0.5% 步长，单位**小数**）：

| bucket 标签 | 区间（小数） |
|---|---|
| `[<0%)` | (-∞, 0) |
| `[0%,0.5%)` | [0, 0.005) |
| `[0.5%,1%)` | [0.005, 0.01) |
| `[1%,1.5%)` | [0.01, 0.015) |
| `[1.5%,2%)` | [0.015, 0.02) |
| `[2%,3%)` | [0.02, 0.03) |
| `[3%,5%)` | [0.03, 0.05) |
| `[5%,10%)` | [0.05, 0.10) |
| `[10%+)` | [0.10, +∞) |

`pd.cut(bins=[-inf,0,0.005,0.01,0.015,0.02,0.03,0.05,0.10,inf], right=False, include_lowest=False)`。

> `[<0%)` 桶在新数据下不会被命中（max 默认 0），保留为防御性。

**列**：与 Table 1 同字段同精度。

**排序**：按 bucket 区间顺序。

**怎么解读**：对候选阈值 T，所有 bucket ≥ T 的行合并为"被阻断组"，bucket < T 的行为"放行组"。比较两组的 `win_rate` 与 `avg_return`，识别合理阈值：
- 阻断组明显跑输放行组 → 当前阈值或更严的阈值合理；
- 阻断组反而跑赢放行组 → 阈值该放宽（这些"大阳线"其实是好信号，不该阻断）。

### 实现位置

`my_strategy/tools/attribution.py`：

```
├── compute_first_buy_size_stats(trades)
├── compute_add_block_stats(trades)
└── run() 末尾追加 2 个 to_csv（在 yearly.to_csv 之后）
```

模块顶部增加常量：

```python
_FIRST_BUY_BINS = [-np.inf, -1, -0.5, 0, 0.5, 1, 1.5, 2, 3, 5, 10, np.inf]
_FIRST_BUY_LABELS = ['[<-1%)', '[-1%,-0.5%)', '[-0.5%,0%)',
                     '[0%,0.5%)', '[0.5%,1%)', '[1%,1.5%)',
                     '[1.5%,2%)', '[2%,3%)', '[3%,5%)',
                     '[5%,10%)', '[10%+)']
_ADD_BLOCK_BINS = [-np.inf, 0, 0.005, 0.01, 0.015, 0.02, 0.03, 0.05, 0.10, np.inf]
_ADD_BLOCK_LABELS = ['[<0%)', '[0%,0.5%)', '[0.5%,1%)',
                     '[1%,1.5%)', '[1.5%,2%)', '[2%,3%)',
                     '[3%,5%)', '[5%,10%)', '[10%+)']
```

每个 compute 函数内部：`pd.cut` 分桶 → groupby bucket → 与现有 `compute_entry_condition_stats / compute_yearly_stats` 同口径聚合 → 按 labels 顺序输出。

### 错误处理（与现有约定一致）

- `trades` 为空 / 目标列缺失 / `dropna(subset=[field])` 后为空 → 返回带正确表头的空 DataFrame，不抛异常。
- `compute_add_block_stats` 在旧 `trade_summary.csv`（无 `max_bullish_candle_pct` 列）上调用时返回空表，不破坏 `attribution.run()` 的其他产出。
- 含 NaN 的行 `dropna(subset=[field])` 丢弃，不计入任何桶。
- 固定阈值分桶 `bins=[-inf, ..., inf]` 保证极端值不丢失。

## 测试

### 单元测试（`my_strategy/tests/test_attribution.py`）

- `test_compute_first_buy_size_stats_basic_buckets`：合成 12 行 trades，覆盖 11 个桶各 1 行 + 1 个 [0%,0.5%) 重复，验证桶标签集合、count 准确、`avg_return` 数值正确、排序与 labels 一致。
- `test_compute_first_buy_size_stats_empty_input`：空 DataFrame 输入返回带 8 列表头的空 DF。
- `test_compute_first_buy_size_stats_missing_column`：trades 含其他列但缺 `entry_ma60_dist_pct` 时返回空 DF。
- `test_compute_add_block_stats_basic_buckets`：合成 10 行 trades，覆盖 9 个桶各 1 行 + 1 个 `[1%,1.5%)` 重复，验证桶分配、聚合数值、排序。
- `test_compute_add_block_stats_empty_input`：空 DataFrame → 空表头 DF。
- `test_compute_add_block_stats_missing_column`：缺 `max_bullish_candle_pct` 列 → 空 DF。

共 6 个新单元测试。

### 集成测试（`my_strategy/tests/test_attribution_run.py`）

`EXPECTED_FILES` 从 9 → 11，追加 `first_buy_size_stats.csv`、`add_block_stats.csv`。`first_buy_size_stats.csv` 应有真实数据；`add_block_stats.csv` 在旧 `trade_summary.csv` 上为空表头（重跑回测后才会有数据）。

### Strategy 行为不变性测试

`my_strategy/tests/test_strategy_max_bullish_candle.py` 新建：用合成 OHLCV 喂回测，验证：

- 持仓期所有日 `(close-open)/open` 的最大值正确写入 `trade_summary.csv`；
- 当 max > 0.01 时，`add_count` 不再增加（行为与原 `big_candle_seen` 等价）；
- 当 max ≤ 0.01 时，加仓正常发生。

## 文档维护

- `docs/FEATURES.md` §6 输出列表从 8 项追加到 10 项（first_buy_size_stats / add_block_stats）。
- `docs/CHANGELOG.md` 顶部追加 2026-05-07 一条："归因报告新增 2 张魔数扫描表"。

## 风险

- **样本充分性**：5911 笔分到 11 桶后，远端桶（`[5%,10%)` / `[10%+)`）样本可能 < 30 笔，统计稳定性下降。这是 Table 1 的内生问题，与设计无关——查看时关注 count 列即可。
- **加仓阻断的事后混淆**：`avg_add_count` 在 Table 2 各桶之间不可直接比较——max 大的桶本身就被现有 1% 阈值阻断了，所以 `avg_add_count` 被压低。但这恰是我们要看的现象，不是缺陷；解读时把 `avg_add_count` 看作"现行阈值下的实际加仓"即可。
- **首仓尺寸的事后混淆**：Table 1 各桶的 `gross_pnl` 受当前 1% 阈值的仓位差异污染，已在设计中明确不输出 `gross_pnl`，只用 `return_pct` 系列。
- **行为不变性测试覆盖**：必须保证 strategy.py 的改动不引入回测路径偏差；上面 `test_strategy_max_bullish_candle.py` 是关键防线。
