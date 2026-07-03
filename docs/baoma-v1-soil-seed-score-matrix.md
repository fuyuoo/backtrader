# Baoma V1 Soil Seed Score Matrix

本文档封板 2026-07-03 生成的 Baoma V1 `soil x seed x score`
矩阵。封板对象是本轮已落盘交易样本上的后验诊断矩阵，不是实盘组合收益结论，
也不是已经验证过的买入规则。

机器可读 baseline：

```text
examples/baoma-v1-soil-seed-score-matrix-baseline.json
```

## Matrix Statement

本轮矩阵的核心结论是：

```text
score 有方向性，但不能单独使用；
soil/seed 能显著解释同一 score 附近的交易质量差异；
soil_type/seed_type 进一步说明“强土壤”和“强种子”内部仍有结构差异。
```

因此下一轮实战口径应进入 `Scored Portfolio Backtest`：

```text
T-1 evidence
  -> soil/seed/type/score 过滤和排序
  -> score gate
  -> 持仓数、现金、行业约束竞争
  -> T 日尝试买入
```

不能把本矩阵直接解释为“某个分数必买”。

## Evidence

| item | value |
|---|---|
| 输入回测 | `reports/baoma-v1-dynamic-hs300-csi500-2015-2025-strict-t1-industry-evidence-run-window-union` |
| 3x3 soil/seed 源 | `reports/soil-seed-strength-3x3-baoma-v1-dynamic-hs300-csi500-2015-2025-strict-t1-current-run` |
| 4D 矩阵 | `reports/score-soil-seed-4d-matrix-baoma-v1-dynamic-hs300-csi500-2015-2025-strict-t1-industry-evidence` |
| 交易样本 | 已平仓交易 `25,253` |
| 年份 | 2015-2025 |
| 执行口径 | 不重跑策略、不联网，只读本地 run artifact、指数快照、日线快照和 attribution reference |
| score 口径 | 沿用旧 fixed score5 scorer config；缺失字段按 scorer 行为贡献 0，并单独记录覆盖率 |
| soil/seed 口径 | 当前 run 重新计算 3x3 标签，用 `symbol + entry_date` 回连 |

## Coverage

| item | value |
|---|---:|
| signal_audit 入场信号缺失 | 0 |
| soil/seed matched_current_3x3 | 25,253 |
| soil unknown | 5 |
| seed unknown | 0 |
| score 全字段完整交易 | 24,841 |
| score 完整率 | 98.37% |
| score 字段平均覆盖 | 99.56% |

已知缺口：`300114.SZ` 有 SW2021 显式空行业会员记录，相关 5 笔 soil
缺失保留为缺失证据，不推断填充。

## Vocabulary

| field | meaning |
|---|---|
| `soil_layer_v1` | 大盘、指数和行业环境强弱分层，取值为强/中/弱土壤 |
| `seed_layer_v1` | 个股入场形态强弱分层，取值为强/中/弱种子 |
| `score_exact` | 旧 fixed score5 scorer 重算出的精确分数 |
| `score_bucket` | 分数桶：`<=0`、`1-2`、`3-4`、`5`、`6`、`7`、`8`、`9+` |
| `soil_type_v1` | 土壤内部类型诊断，不改变 `soil_layer_v1` |
| `seed_type_v1` | 种子内部类型诊断，不改变 `seed_layer_v1` |

## 3x3 Soil Seed Matrix

| soil | seed | trades | win rate | avg return | PF |
|---|---|---:|---:|---:|---:|
| 强土壤 | 强种子 | 3,829 | 59.31% | 2.24% | 1.68 |
| 强土壤 | 中种子 | 4,135 | 48.32% | 1.46% | 1.55 |
| 强土壤 | 弱种子 | 2,050 | 40.15% | 0.82% | 1.39 |
| 中土壤 | 强种子 | 2,949 | 50.63% | 0.97% | 1.26 |
| 中土壤 | 中种子 | 4,142 | 42.56% | 0.80% | 1.31 |
| 中土壤 | 弱种子 | 2,607 | 33.76% | 0.23% | 1.11 |
| 弱土壤 | 强种子 | 1,513 | 53.14% | 0.95% | 1.27 |
| 弱土壤 | 中种子 | 2,218 | 41.88% | 0.14% | 1.05 |
| 弱土壤 | 弱种子 | 1,805 | 36.57% | -0.11% | 0.95 |

解释边界：

- `强土壤 + 强种子` 是当前最清晰的正向组合。
- `强土壤` 对中/弱种子仍有托底效果，但弱种子收益明显下降。
- `强种子` 可以部分抵消弱土壤，但平均收益不如强土壤。
- `弱土壤 + 弱种子` 是第一轮组合回测应优先规避的组合。

## Score Matrix

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

解释边界：

- `3-4` 开始整体质量明显改善，是第一轮组合回测的最低候选带。
- `5-8` 质量整体较好，但 `7` 不优于 `6`，说明分数不是严格单调。
- `8` 最强但样本较少，只能作为高优先级候选带，不应单独定为唯一买点。
- `9+` 样本只有 79 笔，且总 PnL 为负，不能简单理解为“越高越好”。

## Score x Soil x Seed Findings

样本数不少于 100 的分数桶组合中，较强单元包括：

| score bucket | soil | seed | trades | win rate | avg return | PF |
|---|---|---|---:|---:|---:|---:|
| `3-4` | 强土壤 | 强种子 | 1,769 | 62.63% | 2.77% | 1.89 |
| `6` | 强土壤 | 强种子 | 399 | 56.89% | 2.73% | 1.76 |
| `8` | 弱土壤 | 强种子 | 118 | 63.56% | 3.18% | 2.09 |
| `8` | 中土壤 | 强种子 | 144 | 59.03% | 2.12% | 1.58 |
| `5` | 强土壤 | 中种子 | 475 | 50.74% | 1.80% | 1.65 |
| `5` | 中土壤 | 强种子 | 561 | 53.30% | 1.78% | 1.55 |
| `1-2` | 强土壤 | 强种子 | 350 | 55.43% | 1.77% | 1.56 |

较弱或需要谨慎的单元包括：

| score bucket | soil | seed | trades | win rate | avg return | PF |
|---|---|---|---:|---:|---:|---:|
| `<=0` | 中土壤 | 强种子 | 344 | 39.24% | -1.29% | 0.72 |
| `<=0` | 弱土壤 | 强种子 | 138 | 44.93% | -0.27% | 0.93 |
| `7` | 强土壤 | 中种子 | 111 | 46.85% | -0.24% | 0.93 |
| `1-2` | 弱土壤 | 强种子 | 201 | 44.78% | -0.17% | 0.95 |
| `<=0` | 弱土壤 | 弱种子 | 1,252 | 36.42% | -0.17% | 0.92 |

关键判断：

- `score >= 3` 不是充分条件；它需要 soil/seed 共同确认。
- `强土壤 + 强种子` 即使在 `3-4` 桶也很强，不应被简单的 `score >= 5`
  阈值排除。
- `强种子` 如果处于低分或弱土壤环境，表现并不稳定。
- `score 7` 的个别子单元偏弱，说明 scorer 权重需要在 portfolio
  回测里重新验证，而不是继续人工加权。

## Type Diagnostics

类型列覆盖如下：

| type field | counts |
|---|---|
| `soil_type_v1` | `broad_strong=6554`, `industry_led=5596`, `mixed_choppy=4101`, `small_mid_tailwind=3764`, `large_cap_only=2836`, `broad_weak=2397`, `unknown=5` |
| `seed_type_v1` | `ma60_support_recovery=15188`, `healthy_trend_pullback=6572`, `overheated_extension=1166`, `technical_conflict=872`, `weak_energy_rebound=840`, `momentum_breakout=615` |

通过基础稳定性门槛的类型组合中，最值得进入下一轮组合回测的包括：

| soil type | seed type | trades | positive years | avg return | PF |
|---|---|---:|---:|---:|---:|
| 全局强势 | 过热延伸 | 621 | 8/10 | 2.72% | 2.03 |
| 全局强势 | 健康趋势回踩 | 1,919 | 9/11 | 2.44% | 1.71 |
| 行业带动 | 健康趋势回踩 | 1,452 | 9/11 | 2.22% | 1.69 |
| 全局弱势 | 健康趋势回踩 | 634 | 9/11 | 1.47% | 1.44 |
| 全局强势 | MA60支撑修复 | 3,431 | 8/11 | 1.17% | 1.47 |
| 中小盘顺风 | MA60支撑修复 | 2,314 | 7/11 | 1.10% | 1.45 |
| 中小盘顺风 | 健康趋势回踩 | 987 | 6/11 | 1.03% | 1.25 |
| 权重独强 | 健康趋势回踩 | 760 | 5/11 | 0.94% | 1.24 |
| 行业带动 | MA60支撑修复 | 3,681 | 7/11 | 0.59% | 1.26 |

需要克制解读：

- `全局强势 + 过热延伸` 历史表现强，但过热标签天然有回撤风险；
  它适合做高优先级候选，不适合无条件加仓。
- `混合震荡 + 健康趋势回踩` 平均收益只有 0.08%，PF 1.02，
  不应作为主买入环境。
- `技术冲突` 即使部分组合为正，也应先放在观察层。

## Initial Portfolio Gate Hypothesis

下一轮 scored portfolio 可以先用三档 gate 做对照，而不是一次定死：

| gate | candidate rule | purpose |
|---|---|---|
| conservative | `score >= 5` 且 `强土壤 + 强种子`，或类型为 `全局强势/行业带动 + 健康趋势回踩` | 验证最高确定性组合 |
| balanced | `score >= 4` 且 soil/seed 至少一个为强，排除 `弱土壤 + 弱种子` | 验证交易数量和收益质量平衡 |
| aggressive | `score >= 3` 且进入类型白名单，允许 `强种子 + 弱土壤` 小仓位参与 | 验证强个股形态能否穿越弱环境 |

第一轮组合回测的明确排除项：

- `弱土壤 + 弱种子`。
- `score <= 0`，除非作为专门的反事实对照。
- `mixed_choppy` 下的非强种子。
- `technical_conflict` 和 `weak_energy_rebound`，除非后续单独证明稳定。

这些 gate 是实验假设，不是上线规则。

## Next Decision

最推荐的下一步是固定本矩阵为 scorer 输入，跑 `Scored Portfolio Backtest`：

- 最大持仓数：10。
- 总仓位上限：85%。
- 申万一级行业上限：20%。
- 同分或近分时优先未持有行业。
- 对比 conservative / balanced / aggressive 三档 gate。

组合回测成功标准应从组合层面判断：收益、回撤、换手、行业集中度、
持仓集中度、score gate 漏斗和分年度稳定性，而不是继续只看单笔交易样本矩阵。
