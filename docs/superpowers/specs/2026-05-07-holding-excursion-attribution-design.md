# 持仓画像 + DEA lookback + 月度统计：4 张归因表

**日期**：2026-05-07
**范围**：`my_strategy/src/strategy.py`、`my_strategy/tools/attribution.py`、`my_strategy/tests/test_strategy.py`、`my_strategy/tests/test_attribution.py`、`my_strategy/tests/test_attribution_run.py`、`docs/FEATURES.md`、`docs/CHANGELOG.md`

## 背景

策略已上线 13 张归因表（含 magic-number-scan 加的 2 张），但仍缺三类标准量化诊断信息：

1. **持仓画像（MFE/MAE）**：每笔在持仓期内"最高浮盈"和"最深浮亏"未记录。无法回答"止盈是否过早（mfe 大、回吐多）/ 止损是否过晚（mae 深、underwater 久）"。
2. **dea_lookback_days 的事前评估**：入场条件④的 `dea_lookback_days = 5` 是又一个魔数，未做扫描归因。
3. **月度细化**：`yearly_stats` 5 行样本太薄，无法看到时间序列演化与年内异常。

## 目标

新增 3 项数据采集 + 4 张归因表，**只看不改**——不调任何策略阈值。

## 非目标

- ❌ 不修改任何策略阈值（dea_lookback_days、TP1/TP2/MA25 等魔数本轮不动）
- ❌ 不做季节性表（month-of-year 5 年样本太薄）
- ❌ 不做 MFE × exit_reason 等二维交叉表
- ❌ 不引入新的输入文件
- ❌ 不动止盈/止损/加仓决策逻辑（MFE/MAE 仅观测）

---

## Part 1：strategy.py 数据采集

### 1.1 新增 state 字段

`MyStrategy._init_state` 与 `_reset_state` 添加：

```python
'first_buy_price': None,        # 首买入价，加仓后不更新
'mfe_pct': 0.0,                  # 持仓期内最高浮盈（百分点，≥ 0）
'mae_pct': 0.0,                  # 持仓期内最深浮亏（百分点，≤ 0）
'dea_neg_distance_days': None,  # 距上次 DEA<0 的 bar 数（首买入时记录）
```

### 1.2 首买时锁定基准并记录 dea 距离

`next()` 首次买入分支（`add_count == 0` 且未持仓的入场逻辑）执行后追加：

```python
state['first_buy_price'] = float(d.close[0])  # close 即执行价（set_coc=True）
state['dea_neg_distance_days'] = _scan_dea_neg_distance(d, max_lookback=200)
```

辅助函数（模块级，`strategy.py`）：

```python
def _scan_dea_neg_distance(d, max_lookback=200):
    """从当前 bar 往回扫，找到第一根 DEA<0 的 bar 数距离。

    返回 int：1..max_lookback。找不到（200 bar 内一直 ≥ 0）则返回 max_lookback。
    上限 200 ≈ 一年交易日，足够覆盖现行 5 日 lookback 的扫描需求。
    """
    for i in range(1, max_lookback + 1):
        if d.dea[-i] < 0:
            return i
    return max_lookback
```

> **基准选择理由**：用 `first_buy_price`（A 方案）而非滚动 `avg_cost`，让 MFE/MAE 与 `take_profit_*_pct` / `return_pct` 同口径（都基于首买价的百分比）。

### 1.3 持仓期更新 MFE/MAE

`next()` 持仓分支（已有 `state['add_count'] >= 0` 的持仓代码块）追加：

```python
fb = state['first_buy_price']
if fb is not None and fb > 0:
    high_pct = (d.high[0] - fb) / fb * 100.0
    low_pct = (d.low[0] - fb) / fb * 100.0
    if high_pct > state['mfe_pct']:
        state['mfe_pct'] = high_pct
    if low_pct < state['mae_pct']:
        state['mae_pct'] = low_pct
```

### 1.4 平仓写入 trade_log

`_finalize_episode` 内 trade_log 字典追加 3 行：

```python
'mfe_pct': round(state['mfe_pct'], 4),
'mae_pct': round(state['mae_pct'], 4),
'dea_neg_distance_days': state['dea_neg_distance_days'],
```

### 1.5 行为不变性

- MFE/MAE/dea_distance 全部为只读观测，不参与买/卖/加仓判定
- 旧 `trade_log` 列零删除，行数零变化
- 重跑回测后 `trade_summary.csv` 多 3 列；现有 11 张归因表的所有列都不变

---

## Part 2：归因表

### 输出位置

均落入 `cfg['attribution_report_dir']`（默认 `my_strategy/reports/`）。归因表 11 → 15 张。

### Table 1：`mfe_mae_by_exit.csv`

**目的**：把 MFE/MAE 画像按出场原因切片，定位"哪类出场被止盈过早 / 止损过晚"。

**输入字段**：`trades['exit_reason'] / mfe_pct / mae_pct / return_pct`。

**列**：

| 列 | 含义 |
|---|---|
| exit_reason | 出场原因（与现 exit_reason_stats 同口径） |
| count | 笔数 |
| avg_return | 平均 return_pct（4 位） |
| avg_mfe | 平均 mfe_pct（4 位） |
| avg_mae | 平均 mae_pct（4 位） |
| avg_pullback | `avg(mfe_pct - return_pct)`（4 位）—— 平均回吐 |
| avg_underwater | `avg(-mae_pct)`（4 位）—— 平均浮亏深度 |

**排序**：按 count 降序。

**怎么解读**：
- `avg_pullback` 大 → 该出场原因把利润回吐多，止盈逻辑可能过松或过晚
- `avg_underwater` 大但 `avg_return > 0` → 这笔几乎被止损但活下来了，止损位置可能偏紧
- `avg_underwater` 大且 `avg_return < 0` → 止损按设计触发，没有被错误触发

### Table 2：`mfe_distribution.csv`

**目的**：按 MFE 桶看"曾经浮盈过 X% 的笔最终落地多少"，揭示赢家是否被回吐。

**输入字段**：`trades['mfe_pct'] / return_pct / status`。

**分桶**（6 桶）：

| bucket 标签 | 区间（百分点） |
|---|---|
| `[<0%)` | (-∞, 0) |
| `[0%,2%)` | [0, 2) |
| `[2%,5%)` | [2, 5) |
| `[5%,10%)` | [5, 10) |
| `[10%,20%)` | [10, 20) |
| `[20%+)` | [20, +∞) |

`pd.cut(bins=[-inf, 0, 2, 5, 10, 20, inf], right=False, include_lowest=False)`。

> `[<0%)` 桶在新数据下不会被命中（mfe 默认 0），保留为防御性。

**列**：

| 列 | 含义 |
|---|---|
| bucket | 桶标签 |
| count | 笔数 |
| win_rate | `return_pct > 0` 比例（4 位） |
| avg_return | 平均 return_pct（4 位） |
| median_return | 中位数 return_pct（4 位） |
| pct_completed | `status == 'completed'` 比例（4 位） |

**排序**：按 bucket 区间顺序。

### Table 3：`dea_lookback_stats.csv`

**目的**：评估"距上次 DEA<0 的 bar 数"对收益的影响，用于事前评估 `dea_lookback_days`（默认 5）的合理性。

**输入字段**：`trades['dea_neg_distance_days']`。

**分桶**（11 桶）：

| bucket 标签 | 区间（bar 数） | 语义 |
|---|---|---|
| `[0,1)` | [0, 1) | 防御桶（`_scan_dea_neg_distance` 最小返回 1，永远不命中） |
| `[1,2)` | [1, 2) | 昨日 DEA<0、今日刚翻多 |
| `[2,3)` | [2, 3) | 前日 DEA<0 |
| `[3,4)` | [3, 4) | |
| `[4,5)` | [4, 5) | |
| `[5,7)` | [5, 7) | 含距离=5（现行阈值边界）和距离=6（已超阈值） |
| `[7,10)` | [7, 10) | |
| `[10,15)` | [10, 15) | |
| `[15,30)` | [15, 30) | |
| `[30,60)` | [30, 60) | |
| `[60+)` | [60, +∞) | 含上限 200 |

`pd.cut(bins=[0, 1, 2, 3, 4, 5, 7, 10, 15, 30, 60, inf], right=False, include_lowest=True)`。

> **当前阈值下哪些桶有数据**：策略入场需要 `dea_neg_distance_days ≤ dea_lookback_days = 5`。所以 `[1,2) [2,3) [3,4) [4,5)` 必有数据；`[5,7)` 桶包含距离==5（触发）和距离==6（阻断），现行阈值下只有距离==5 进来；`[7,10)` 之后的桶在现行阈值下全部为空——它们只在用户放宽 `dea_lookback_days` 重新回测后才会出现数据。`[0,1)` 桶因 `_scan_dea_neg_distance` 最小返回 1，永远为空，作为防御桶保留。本表保留全部 11 桶，便于阈值放宽后直接对比同一份输出格式。

**列**：与现有 entry_condition_stats 同口径：

| 列 | 含义 |
|---|---|
| bucket | 桶标签 |
| count | 笔数 |
| win_rate | 4 位 |
| avg_return | 4 位 |
| median_return | 4 位 |
| avg_holding_days | 1 位 |
| avg_add_count | 2 位 |
| pct_completed | 4 位 |

**排序**：按 bucket 区间顺序。

### Table 4：`monthly_stats.csv`

**目的**：把 `yearly_stats` 细化到 year-month，看时间序列演化（衰减、异常月份、回测期内的稳定性）。

**输入字段**：`trades['entry_date']` 转为 Period('M')。

**列**（与 yearly_stats 同口径）：

| 列 | 含义 |
|---|---|
| year_month | YYYY-MM 字符串 |
| count | 当月入场笔数 |
| win_rate | 4 位 |
| avg_return | 4 位 |
| median_return | 4 位 |
| total_pnl_yuan | 当月总盈亏（元，0 位） |
| avg_holding_days | 1 位 |

**排序**：按 year_month 升序。**所有出现过入场的月份都列出**，没有入场的月份不补 0 行。

---

## Part 3：实现位置

```
my_strategy/src/strategy.py
└── 新增模块函数 _scan_dea_neg_distance(d, max_lookback=200)
└── _init_state / _reset_state：新 4 个字段
└── next() 首买分支：锁定 first_buy_price + 调用 _scan_dea_neg_distance
└── next() 持仓分支：更新 mfe_pct / mae_pct
└── _finalize_episode：trade_log 新增 3 列

my_strategy/tools/attribution.py
├── compute_mfe_mae_by_exit(trades)
├── compute_mfe_distribution(trades)
├── compute_dea_lookback_stats(trades)
├── compute_monthly_stats(trades)
└── run() 末尾：4 个 to_csv（紧跟 add_block_stats 之后）
```

模块顶部新增常量：

```python
_MFE_BINS = [-np.inf, 0, 2, 5, 10, 20, np.inf]
_MFE_LABELS = ['[<0%)', '[0%,2%)', '[2%,5%)', '[5%,10%)', '[10%,20%)', '[20%+)']
_DEA_LOOKBACK_BINS = [0, 1, 2, 3, 4, 5, 7, 10, 15, 30, 60, np.inf]
_DEA_LOOKBACK_LABELS = ['[0,1)', '[1,2)', '[2,3)', '[3,4)', '[4,5)',
                         '[5,7)', '[7,10)', '[10,15)', '[15,30)',
                         '[30,60)', '[60+)']
```

`compute_mfe_distribution` / `compute_dea_lookback_stats` 复用 `_scan_bucket_aggregate`（magic-number-scan 已建立）。`compute_mfe_mae_by_exit` / `compute_monthly_stats` 用各自的 groupby 聚合（与现有 `compute_exit_reason_stats` / `compute_yearly_stats` 同风格）。

---

## Part 4：错误处理（与现约定一致）

- `trades` 为空 / 目标列缺失 / `dropna(subset=[field])` 后为空 → 返回带正确表头的空 DataFrame，不抛异常
- 旧 `trade_summary.csv`（无新 3 列）能让 `attribution.run()` 全部 4 个新表返回空表头，**不破坏其他 11 张表的产出**
- 含 NaN 的行 `dropna(subset=[field])` 丢弃，不计入任何桶
- 固定阈值分桶 `bins=[..., inf]` 保证极端值不丢失

---

## Part 5：测试

### 单元测试（`my_strategy/tests/test_attribution.py`）

每个新 compute_ 函数 3 个用例（共 12 个）：

- `test_compute_mfe_mae_by_exit_basic` / `_empty_input` / `_missing_column`
- `test_compute_mfe_distribution_buckets` / `_empty_input` / `_missing_column`
- `test_compute_dea_lookback_stats_buckets` / `_empty_input` / `_missing_column`
- `test_compute_monthly_stats_basic` / `_empty_input` / `_missing_column`

合成 trades DataFrame 覆盖每张表的桶/分组路径。

### 集成测试（`my_strategy/tests/test_attribution_run.py`）

`EXPECTED_FILES` 11 → 15，追加 4 张。在旧 `trade_summary.csv`（无 mfe/mae/dea_distance 列）上调用：3 张新表为空表头（容错），`monthly_stats.csv` 仍有真实数据（entry_date 一直存在）。

### Strategy 行为不变性测试（`my_strategy/tests/test_strategy.py`）

新增 4 个用例（合成数据喂回测）：

- `test_first_buy_price_locked_at_initial_buy`：加仓后 first_buy_price 不变
- `test_mfe_mae_recorded_during_holding`：构造已知波动，验证 mfe/mae 与预期值匹配（容差 1e-6）
- `test_dea_neg_distance_days_recorded`：构造已知 DEA 翻多场景，验证距离值
- `test_dea_neg_distance_capped_at_max_lookback`：构造 200+ bar 全程 DEA≥0 的场景，验证返回 200

---

## Part 6：文档维护

- `docs/FEATURES.md` §6 列表 10 → 14（追加 mfe_mae_by_exit / mfe_distribution / dea_lookback_stats / monthly_stats）
- `docs/CHANGELOG.md` 顶部追加 2026-05-07 一条："归因新增 4 张持仓画像/参数扫描/月度表 + strategy 采集 mfe/mae/dea_neg_distance"

---

## 风险

- **MFE/MAE 基准 vs 加仓**：基准锁定首买价，加仓后真实账户的浮盈/浮亏与 MFE/MAE 数值会偏离（加仓拉低实际成本→实际浮盈 > MFE 数值）。这是 A 方案选择的代价，已在设计中明确选 A 因为评估止盈/止损位置时与 take_profit_*_pct 同口径更重要。
- **dea_lookback_stats 现行阈值下后段桶为空**：`[5,7)` 及之后的桶在 `dea_lookback_days = 5` 下永远不会有数据。表里这些行会缺失。这是事实而非缺陷——用户放宽阈值后再回测就有数据。
- **monthly_stats 月份样本量**：5 年期约 60 个月，但每月入场笔数差异大（趋势市可能 200+ 笔，震荡月可能 < 30 笔）。解读时关注 count 列。
- **dea_neg_distance 上限 200 bar**：极少数刚上市股票或长期 DEA ≥ 0 的股票会触发上限并记 200。在 dea_lookback_stats 里这种笔会落入 `[60+)` 桶，量极少不影响结论。
- **重跑回测耗时**：约 12 分钟（5466 只股票 × 5 年）。本 spec 在所有代码改完后只需 1 次重跑。
