# Baoma V1 含行业主线口径审计

## 结论

当前主线应切回含行业矩阵。

理由是 combined HS300 + CSI500 的最终行业链路已经达到全覆盖：

```text
closed_trade_count: 42,909
industry_mapping_status_counts: matched 42,909 / 42,909
industry_classification_status_counts: matched 42,909 / 42,909
industry_soil_status_counts: matched 42,909 / 42,909
soil_with_industry_unknown_count: 0
```

因此，后续主线不应继续把 no-industry 作为第一路径。no-industry 应保留为 baseline，用来衡量行业土壤是否带来增量解释力。

## 最终输入口径

最终 industry time-soil map：

```text
reports/industry-sw-akshare-historical-mixed-warmup-stitch-index-warmup-earliest-membership-backfill-experimental-time-soil-map-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/
```

关键 metadata：

```text
source_rows:
reports/score-year-seed-soil-v2-index-warmup-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/scored_trade_rows_soil_v2.parquet

industry_source_requested:
SW_AKSHARE_HISTORICAL_MIXED_WARMUP_STITCH_EARLIEST_MEMBERSHIP_BACKFILL_EXPERIMENTAL

industry_index_source:
SW_AKSHARE_HISTORICAL_MIXED_WARMUP_STITCH_EARLIEST_MEMBERSHIP_BACKFILL_EXPERIMENTAL
```

最终含行业矩阵目录：

```text
reports/soil-with-industry-v1-sw-akshare-historical-mixed-warmup-stitch-index-warmup-earliest-membership-backfill-experimental-baoma-v1-dynamic-hs300-csi500-2006-2025/
```

兼容旧命名目录也指向同一最终 source：

```text
reports/soil-with-industry-v1-baoma-v1-dynamic-hs300-csi500-2006-2025/
```

## 覆盖检查

年度覆盖文件：

```text
coverage_by_year.parquet
```

审计结果：

| 项目 | 结果 |
|---|---:|
| 年份范围 | 2006-2025 |
| total trades | 42,909 |
| 每年 complete_pct | 100% |
| 每年 unknown_soil_count | 0 |
| soil_with_industry_unknown_count | 0 |

这说明含行业口径可以作为 20 年主线输入。

## 主要矩阵产物

```text
trade_soil_with_industry_v1.parquet
matrix_score_year_seed_soil_with_industry_v1_exact.parquet
matrix_score_seed_soil_with_industry_v1_exact.parquet
matrix_score_bucket_year_seed_soil_with_industry_v1.parquet
matrix_score_bucket_seed_soil_with_industry_v1.parquet
soil_with_industry_v1_summary.parquet
soil_with_industry_v1_seed_summary.parquet
soil_no_industry_v2_to_soil_with_industry_v1_cross.parquet
```

## 全样本核心结果

| soil_with_industry | trades | win rate | avg return | profit factor | net pnl |
|---|---:|---:|---:|---:|---:|
| very_strong_soil | 14,996 | 54.53% | 2.66% | 2.02 | 2,006,044,181 |
| strong_soil | 8,248 | 46.90% | 0.83% | 1.26 | 189,031,828 |
| neutral_soil | 7,190 | 48.60% | 0.94% | 1.33 | 238,469,219 |
| weak_soil | 4,067 | 48.64% | 0.80% | 1.29 | 103,403,543 |
| very_weak_soil | 8,408 | 42.48% | 0.00% | 1.00 | -168,609,689 |

`very_strong_soil` 与 `very_weak_soil` 的区分度明确，适合作为后续 scorer / gate 的候选主轴。

## 与 no-industry baseline 的关系

含行业口径不是替代 no-industry，而是主线解释层。

no-industry baseline 的作用：

- 衡量行业土壤是否带来增量解释力。
- 检查行业补齐口径是否引入过拟合或样本重分类噪声。
- 保留没有行业证据时的 fallback 解释。

关键迁移观察：

- `strong_soil -> very_strong_soil`: 14,996 笔，均笔 2.66%，PF 2.02。
- `weak_soil -> very_weak_soil`: 8,283 笔，均笔 -0.02%，PF 0.99。
- 行业土壤把原 no-industry 的 strong/weak 样本进一步拉开，是有效增量信号。

## 证据边界

当前行业链路包含实验性补齐：

```text
earliest_membership_backfill
warmup stitch
AKShare / historical mixed source
```

因此报告中必须保留 source/status 说明，不能把该口径简写成“纯官方 SW2021 全历史行业证据”。

但这不再阻止含行业矩阵作为主线。正确表述是：

```text
industry-enhanced mainline with explicit backfill/source audit
```

## 下一步

优先做含行业矩阵的 scorer/gate 候选审计：

1. 以 `soil_with_industry_v1_summary` 和 `soil_with_industry_v1_seed_summary` 选出保守、均衡、进攻三档候选。
2. 与 no-industry baseline 做同口径 lift 对照。
3. 再进入 scored portfolio / runner replay，验证真实持仓容量和资金竞争下是否仍有效。

## 2026-07-08 Scorer/Gate 候选审计结果

已新增可复跑脚本：

```text
scripts/audit_industry_enhanced_scorer_gate_candidates.py
```

默认输出目录：

```text
reports/industry-enhanced-scorer-gate-audit-baoma-v1-dynamic-hs300-csi500-2006-2025/
```

生成 artifact：

```text
industry_enhanced_scorer_gate_audit.json
industry_enhanced_scorer_gate_audit.zh.md
```

三档候选结果：

| 档位 | 规则 | trades | win rate | avg return | PF | net pnl | 正收益年份 | vs no-industry strong avg lift |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 保守 | `very_strong_soil` | 14,996 | 54.53% | 2.66% | 2.02 | 2,006,044,181 | 13/20 | +0.77pct |
| 均衡 | `very_strong_soil` 或 `strong_soil + strong_seed` | 20,517 | 53.25% | 2.17% | 1.75 | 2,093,874,365 | 14/20 | +0.28pct |
| 进攻 | `very_strong_soil` 或 `strong/neutral_soil + strong_seed` | 25,982 | 52.96% | 1.96% | 1.67 | 2,331,401,333 | 15/20 | +0.07pct |

Seed overlay 诊断：

| overlay | trades | win rate | avg return | PF | 正收益年份 | 结论 |
|---|---:|---:|---:|---:|---:|---|
| `very_strong_soil + strong_seed` | 8,634 | 58.18% | 2.68% | 1.88 | 11/20 | 胜率更高，但样本更窄，年度稳定性弱于纯 `very_strong_soil`。 |

当前建议：

1. 第一轮 runner replay 使用保守档，先验证行业主轴 `very_strong_soil` 在资金竞争下是否仍有 lift。
2. 第二轮 replay 使用均衡档，测试扩大样本后的 PF、回撤和容量。
3. 进攻档只作为容量边界测试，不应先定为主线。

## 2026-07-08 保守档 Runner Replay 对照

已新增快速 replay 脚本：

```text
scripts/run_industry_gate_replay_from_signal_audit.py
```

该脚本不重新执行 2000 只股票的 Baoma engine。它读取已落盘 source run 的
`signal_audit.parquet`，分批构造 actionable decision events，再调用同一个
`simulate_precomputed_score_portfolio(...)` replay 核心。

source run：

```text
reports/baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/
```

对照输出：

```text
reports/industry-gate-runner-replay-comparison-2006-2025-replay-cash-10m/
```

组合 replay 口径：

```text
window: 2006-01-01 -> 2025-12-31
initial_cash: 10,000,000
max_holding_count: 20
max_new_positions_per_day: 5
cash_reserve_ratio: 0.05
industry_max_new_per_day: 1
```

事件 contract：

```text
signal_audit_rows_scanned: 8,879,478
actionable_event_count: 86,782
enter_event_count: 43,100
```

结果级对照：

| candidate | score rows | matched enter | missing enter | selected | closed | cumulative | max drawdown | win rate | PF | final value |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 含行业保守档 `very_strong_soil` | 14,996 | 14,996 | 28,104 | 1,947 | 1,947 | 459.50% | 33.59% | 36.83% | 1.69 | 55,950,427 |
| no-industry strong baseline | 23,647 | 23,647 | 19,453 | 2,387 | 2,387 | 204.42% | 37.74% | 34.52% | 1.43 | 30,441,571 |

Lift：

| metric | 含行业保守档 - no-industry strong |
|---|---:|
| cumulative_return | +255.09pct |
| max_drawdown | -4.15pct |
| win_rate | +2.31pct |
| profit_factor | +0.26 |
| selected trades | -440 |

结论：

含行业保守档在真实资金竞争 replay 下胜出。它不是靠更多交易取胜，而是在少选 440 笔的情况下提升累计收益、PF 和回撤。因此当前主线可以进入第二步：跑均衡档 replay，测试扩大样本后的容量边界。

## 2026-07-08 均衡档 Runner Replay 对照

均衡档规则：

```text
very_strong_soil
OR
strong_soil + strong_seed
```

已生成均衡档 score artifact：

```text
reports/industry-balanced-entry-score-runner-2006-2025-replay-cash-10m/entry_score_artifact.parquet
```

artifact 行数：

```text
score rows: 20,517
```

同一 replay 脚本已扩展为三组对照：

```text
industry_very_strong
industry_balanced
no_industry_strong
```

结果级对照：

| candidate | score rows | matched enter | missing enter | selected | closed | cumulative | max drawdown | win rate | PF | final value |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 含行业保守档 `very_strong_soil` | 14,996 | 14,996 | 28,104 | 1,947 | 1,947 | 459.50% | 33.59% | 36.83% | 1.69 | 55,950,427 |
| 含行业均衡档 | 20,517 | 20,517 | 22,583 | 2,383 | 2,383 | 463.68% | 40.92% | 37.98% | 1.55 | 56,367,763 |
| no-industry strong baseline | 23,647 | 23,647 | 19,453 | 2,387 | 2,387 | 204.42% | 37.74% | 34.52% | 1.43 | 30,441,571 |

相对 no-industry strong baseline：

| candidate | cumulative lift | drawdown delta | win-rate lift | PF lift | selected delta |
|---|---:|---:|---:|---:|---:|
| 含行业保守档 | +255.09pct | -4.15pct | +2.31pct | +0.26 | -440 |
| 含行业均衡档 | +259.26pct | +3.18pct | +3.46pct | +0.12 | -4 |

解释：

- 均衡档基本恢复了 baseline 的成交容量：`2,383` vs `2,387`。
- 均衡档最终收益略高于保守档：`56.37M` vs `55.95M`。
- 均衡档的代价是回撤更高：`40.92%`，高于保守档 `33.59%`，也高于 no-industry strong baseline `37.74%`。
- 保守档仍是质量主线；均衡档是容量/收益上限候选，不应直接替代保守档作为风险受控主线。

当前判断：

1. 若目标是风险受控主线，优先保守档。
2. 若目标是容量和最终收益，均衡档值得进入下一层回撤/年份弱点审计。
3. 下一步不应先跑进攻档，应先拆均衡档为什么增加回撤，尤其看 `2008`、`2018`、`2022-2023` 和 `strong_soil + strong_seed` 增量交易。

## 2026-07-08 进攻档 Runner Replay 对照

按用户要求补跑进攻档。进攻档规则：

```text
very_strong_soil
OR
(strong_soil OR neutral_soil) + strong_seed
```

已生成进攻档 score artifact：

```text
reports/industry-aggressive-entry-score-runner-2006-2025-replay-cash-10m/entry_score_artifact.parquet
```

artifact 行数：

```text
score rows: 25,982
very_strong_soil: 14,996
strong_soil: 5,521
neutral_soil: 5,465
```

同一 replay 脚本已扩展为四组对照：

```text
industry_very_strong
industry_balanced
industry_aggressive
no_industry_strong
```

结果级对照：

| candidate | score rows | matched enter | missing enter | selected | closed | cumulative | max drawdown | win rate | PF | final value |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 含行业保守档 `very_strong_soil` | 14,996 | 14,996 | 28,104 | 1,947 | 1,947 | 459.50% | 33.59% | 36.83% | 1.69 | 55,950,427 |
| 含行业均衡档 | 20,517 | 20,517 | 22,583 | 2,383 | 2,383 | 463.68% | 40.92% | 37.98% | 1.55 | 56,367,763 |
| 含行业进攻档 | 25,982 | 25,982 | 17,118 | 2,982 | 2,982 | 882.14% | 40.59% | 36.38% | 1.56 | 98,214,065 |
| no-industry strong baseline | 23,647 | 23,647 | 19,453 | 2,387 | 2,387 | 204.42% | 37.74% | 34.52% | 1.43 | 30,441,571 |

相对 no-industry strong baseline：

| candidate | cumulative lift | drawdown delta | win-rate lift | PF lift | selected delta |
|---|---:|---:|---:|---:|---:|
| 含行业保守档 | +255.09pct | -4.15pct | +2.31pct | +0.26 | -440 |
| 含行业均衡档 | +259.26pct | +3.18pct | +3.46pct | +0.12 | -4 |
| 含行业进攻档 | +677.72pct | +2.85pct | +1.86pct | +0.13 | +595 |

年度弱点粗看：

| candidate | worst years |
|---|---|
| 含行业保守档 | 2008 -31.11%, 2016 -11.91%, 2012 -6.03%, 2013 -5.20%, 2011 -4.80% |
| 含行业均衡档 | 2008 -26.29%, 2022 -20.55%, 2016 -12.08%, 2024 -8.90%, 2023 -8.31% |
| 含行业进攻档 | 2022 -24.22%, 2012 -15.46%, 2011 -15.06%, 2016 -11.20%, 2018 -10.38% |
| no-industry strong baseline | 2008 -25.90%, 2016 -17.00%, 2024 -12.11%, 2022 -11.58%, 2023 -11.55% |

解释：

- 进攻档不是单纯扩大成交数。它比 no-industry strong baseline 多选 `595` 笔，但最终资金从 `30.44M` 提升到 `98.21M`。
- 进攻档也不是无代价胜出。它的最大回撤 `40.59%` 高于 baseline `37.74%`，接近均衡档 `40.92%`，明显高于保守档 `33.59%`。
- 进攻档的风险结构发生变化：baseline 的弱点集中在 `2022-2024`，进攻档则暴露 `2022`、`2011-2012`、`2018`。这说明它打开了新收益空间，也引入了新的年份风险。

当前修正判断：

1. 保守档仍是风险受控主线。
2. 进攻档已经值得进入下一层审计，因为它在同口径 replay 下显著提高最终资金，且 PF 仍高于 baseline。
3. 下一步应拆进攻档相对均衡档的增量交易，重点看 `neutral_soil + strong_seed` 和 `2022`、`2011-2012`、`2018` 的亏损来源。
