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
