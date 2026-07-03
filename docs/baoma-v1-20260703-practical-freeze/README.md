# Baoma V1 2026-07-03 Practical Freeze

这个目录是 2026-07-03 Baoma V1 当前研究结论的稳定入口。
它把本轮发现按四个问题固化下来：

1. 策略方式。
2. 回测时间。
3. 回测股票类型。
4. 回测结果和方式。

本目录不保存 ignored `reports/` 下的大体积产物，只保存可复盘的结论、
关键数字、路径和边界。

## 1. 策略方式

当前策略是 Baoma V1，接在 `trend_template_v1` 策略模板上。

| item | value |
|---|---|
| strategy template | `trend_template_v1` |
| entry | `baoma_entry` |
| profit taking | `baoma_ma25_profit_exit` |
| stop loss | `baoma_ma60_stop` |
| add on | `baoma_add_on` |
| sizing | `equal_weight` |
| entry param | `dea_max_age_trading_days=14` |
| add-on param | `dea_max_age_trading_days=14`, `max_add_on_count=2` |
| buy slice | `buy_slice_fraction=0.33` |
| scale out | fixed percent, first `5%`, second `15%` |

当前 sizing 仍是样本采集口径：

```yaml
sizing_params:
  max_holding_count: 800
  min_order_quantity: 100
```

这意味着本轮不是实盘组合策略。它没有启用：

- `max_total_exposure_percent`
- `max_risk_group_exposure_percent`
- 同一行业最多持仓数
- score/soil/seed 排序后的资金竞争

A 股执行约束已启用：

| constraint | value |
|---|---|
| T+1 | enabled |
| 涨跌停 | enabled |
| 停牌 | enabled |
| 整手 | `100` |

行业证据已接入 SW2021，但当前只用于归因和矩阵，不是行业规避。

## 2. 回测时间

| item | value |
|---|---|
| run id | `baoma-v1-dynamic-hs300-csi500-2015-2025-strict-t1-industry-evidence-run-window-union` |
| from date | `2015-01-01` |
| to date | `2025-12-31` |
| 已平仓交易 entry range | `2015-01-08` 到 `2025-12-30` |
| 年份覆盖 | 2015-2025 |

本轮矩阵不重跑策略，只读取该 run 已落盘 artifact。

## 3. 回测股票类型

股票池是 A 股沪深300 + 中证500动态成分股，不是全 A，也不是人工精选股票池。

| item | value |
|---|---|
| price adjustment | `qfq` |
| historical union CSV | `reports/baoma-v1-dynamic-hs300-csi500-2015-2025/input/hs300-csi500-dynamic-union-run-window-2015-2025-with-2014-anchor.csv` |
| dynamic membership parquet | `reports/baoma-v1-dynamic-hs300-csi500-2015-2025/input/hs300-csi500-dynamic-constituents-2015-2025-with-2014-anchor.parquet` |
| historical union symbol count | 1,552 |
| dynamic membership rows | 141,200 |
| dynamic membership symbol count | 1,554 |
| scored closed-trade symbol count | 1,505 |
| benchmarks | `000300.SH`, `000905.SH` |
| industry source | `SW2021` |
| SW2021 level-1 industry indexes | 31 |

读取规则：

- historical union CSV 是数据准备宇宙。
- dynamic membership parquet 是 T-1 入场门槛。
- 候选必须在信号证据日属于沪深300或中证500动态成分股。
- 不能把这个结果外推为全 A 实盘结论。

## 4. 回测结果和方式

### 4.1 Run Evidence

| item | value |
|---|---:|
| evidence status | `ok` |
| evidence errors | 0 |
| evidence warnings | 0 |
| closed trades | 25,253 |
| open positions at end | 183 |
| signal intents | 4,448,322 |
| sizing decisions | 39,716 |
| execution events | 83,316 |
| rejected orders | 0 |

报告层记录的样本采集口径组合数字：

| item | value |
|---|---:|
| starting equity | 10,000,000,000 |
| final equity | 10,951,050,348 |
| cumulative return | 9.51% |
| max drawdown | 4.10% |
| closed-trade win rate | 46.03% |
| profit/loss ratio | 1.58 |

这些组合数字只记录，不作为实盘收益证据。原因是当前配置使用
`max_holding_count=800` 和 `10,000,000,000` 初始资金，没有真实持仓数、
现金竞争和行业集中度约束。

### 4.2 Matrix Method

本轮矩阵构建方式：

1. 不联网。
2. 不重跑策略。
3. 只读本地 run artifact、指数快照、日线快照和 attribution reference。
4. 用旧 fixed score5 scorer config 重算 `score_exact`。
5. score 缺失字段按旧 scorer 行为贡献 0，同时记录覆盖率。
6. 重新计算当前 run 2015-2025 的 soil/seed 3x3 标签。
7. 用 `symbol + entry_date` 把 soil/seed 回连到已平仓交易。
8. 生成 score x soil x seed x year 四维矩阵。
9. 追加 `soil_type_v1` 和 `seed_type_v1` 诊断标签。

关键覆盖：

| item | value |
|---|---:|
| soil/seed matched current 3x3 | 25,253 |
| soil unknown | 5 |
| seed unknown | 0 |
| score complete trades | 24,841 |
| score complete rate | 98.37% |
| average score field coverage | 99.56% |

已知数据缺口：`300114.SZ` 有 SW2021 显式空行业会员记录，相关 5 笔
soil 缺口保留为缺失证据，不做推断填充。

### 4.3 Matrix Results

核心结论：

```text
score 有方向性，但不能单独使用；
soil/seed 能明显解释同一 score 附近的交易质量差异；
soil_type/seed_type 说明强土壤和强种子内部仍有结构差异。
```

3x3 soil/seed 核心结果：

| soil | seed | trades | win rate | avg return | PF |
|---|---|---:|---:|---:|---:|
| 强土壤 | 强种子 | 3,829 | 59.31% | 2.24% | 1.68 |
| 强土壤 | 中种子 | 4,135 | 48.32% | 1.46% | 1.55 |
| 中土壤 | 强种子 | 2,949 | 50.63% | 0.97% | 1.26 |
| 弱土壤 | 强种子 | 1,513 | 53.14% | 0.95% | 1.27 |
| 弱土壤 | 弱种子 | 1,805 | 36.57% | -0.11% | 0.95 |

score bucket 核心结果：

| score bucket | trades | win rate | avg return | PF | total PnL |
|---|---:|---:|---:|---:|---:|
| `<=0` | 7,590 | 38.39% | 0.29% | 1.12 | -4,865,060 |
| `1-2` | 3,901 | 42.68% | 0.78% | 1.28 | 93,879,518 |
| `3-4` | 6,842 | 49.84% | 1.37% | 1.47 | 413,119,437 |
| `5` | 2,999 | 51.35% | 1.38% | 1.46 | 197,917,163 |
| `6` | 2,000 | 51.95% | 1.47% | 1.45 | 111,438,228 |
| `7` | 1,297 | 52.66% | 1.13% | 1.35 | 81,643,072 |
| `8` | 545 | 60.00% | 2.47% | 1.77 | 59,079,183 |
| `9+` | 79 | 58.23% | 0.83% | 1.19 | -1,161,193 |

解释：

- `强土壤 + 强种子` 是当前最清晰的核心正向组合。
- `score 3-4` 开始明显改善，可以作为第一轮组合回测最低候选带。
- `score 5-8` 整体较好，但不是严格单调。
- `score 8` 最强但样本只有 545 笔，不能单独定为唯一买点。
- `score 9+` 样本只有 79 笔，总 PnL 为负，不能迷信最高分。
- `弱土壤 + 弱种子` 应作为下一轮组合回测优先排除项。

### 4.4 Practical Next Step

下一步应建立 `Scored Portfolio Backtest`，用真实组合约束重跑：

| item | initial setting |
|---|---:|
| max holding count | 10 |
| max total exposure | 85% |
| max SW2021 level-1 industry exposure | 20% |
| industry preference | 同分或近分时优先未持有行业 |

先跑三档 gate：

| gate | rule |
|---|---|
| conservative | `score >= 5` 且 `强土壤 + 强种子`，或类型为 `全局强势/行业带动 + 健康趋势回踩` |
| balanced | `score >= 4` 且 soil/seed 至少一个为强，排除 `弱土壤 + 弱种子` |
| aggressive | `score >= 3` 且进入类型白名单，允许 `强种子 + 弱土壤` 小仓位参与 |

下一轮成功标准必须是组合层面：

- 年化收益和基准超额。
- 最大回撤。
- 持仓集中度。
- 行业集中度。
- turnover 和交易成本。
- score gate 漏斗。
- 分年度和市场阶段稳定性。

## Canonical References

| purpose | path |
|---|---|
| practical conclusion | `docs/baoma-v1-current-practical-conclusion.md` |
| soil/seed/score matrix | `docs/baoma-v1-soil-seed-score-matrix.md` |
| matrix baseline | `examples/baoma-v1-soil-seed-score-matrix-baseline.json` |
| run artifact | `reports/baoma-v1-dynamic-hs300-csi500-2015-2025-strict-t1-industry-evidence-run-window-union` |
| freeze manifest | `docs/baoma-v1-20260703-practical-freeze/manifest.json` |
