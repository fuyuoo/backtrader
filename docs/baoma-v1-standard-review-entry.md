# Baoma V1 Standard Review Entry

本文档记录 Baoma V1 当前阶段的标准复盘入口。它不是新的回测结果，也不是新的
交易规则；它只是把已经落盘的两年、十年和稳定性比较结果整理成固定读取顺序。

机器可读 baseline：

```text
examples/baoma-v1-standard-review-entry-baseline.json
```

## What Was Generated

### Catalog

| artifact | path | status |
|---|---|---|
| run catalog | `reports/run-catalog/run_catalog.json` | generated |
| run catalog zh | `reports/run-catalog/run_catalog.zh.md` | generated |

`run_catalog.json` 当前包含 29 个 run，并包含：

- `baoma-v1-fixed-sample-2015-2024-maxhold800`
- `baoma-v1-fixed-sample-2023-2024-maxhold800`

### 2015-2024 Run

| artifact | path |
|---|---|
| overview | `reports/baoma-v1-fixed-sample-2015-2024-maxhold800/run_data_overview.json` |
| overview zh | `reports/baoma-v1-fixed-sample-2015-2024-maxhold800/run_data_overview.zh.md` |
| dictionary | `reports/baoma-v1-fixed-sample-2015-2024-maxhold800/run_data_dictionary.json` |
| dictionary zh | `reports/baoma-v1-fixed-sample-2015-2024-maxhold800/run_data_dictionary.zh.md` |
| environment_fit packet | `reports/baoma-v1-fixed-sample-2015-2024-maxhold800/review_packet.environment_fit.json` |
| environment_fit findings | `reports/baoma-v1-fixed-sample-2015-2024-maxhold800/review_findings.environment_fit.json` |
| environment_fit brief | `reports/baoma-v1-fixed-sample-2015-2024-maxhold800/review_brief.environment_fit.json` |

Evidence status: `ok`; errors: `0`; warnings: `0`.

### 2023-2024 Run

| artifact | path |
|---|---|
| overview | `reports/baoma-v1-fixed-sample-2023-2024-maxhold800/run_data_overview.json` |
| overview zh | `reports/baoma-v1-fixed-sample-2023-2024-maxhold800/run_data_overview.zh.md` |
| dictionary | `reports/baoma-v1-fixed-sample-2023-2024-maxhold800/run_data_dictionary.json` |
| dictionary zh | `reports/baoma-v1-fixed-sample-2023-2024-maxhold800/run_data_dictionary.zh.md` |
| environment_fit packet | `reports/baoma-v1-fixed-sample-2023-2024-maxhold800/review_packet.environment_fit.json` |
| environment_fit findings | `reports/baoma-v1-fixed-sample-2023-2024-maxhold800/review_findings.environment_fit.json` |
| environment_fit brief | `reports/baoma-v1-fixed-sample-2023-2024-maxhold800/review_brief.environment_fit.json` |

Evidence status: `ok`; errors: `0`; warnings: `0`.

### Comparison Entries

| artifact | path |
|---|---|
| environment_fit comparison | `reports/environment-fit-comparison-baoma-v1-fixed-sample-2023-2024-maxhold800__vs__baoma-v1-fixed-sample-2015-2024-maxhold800/environment_fit_comparison.json` |
| factor stability review | `reports/environment-fit-comparison-baoma-v1-fixed-sample-2023-2024-maxhold800__vs__baoma-v1-fixed-sample-2015-2024-maxhold800/baoma_2y_vs_10y_factor_stability.json` |

## Read Order

1. 先读 `reports/run-catalog/run_catalog.json`，确认目标 run 存在。
2. 进入单 run 时，先读 `run_data_overview.json`，确认 `evidence_validation.status=ok`。
3. 解释字段、artifact 或下钻路径时，读 `run_data_dictionary.json`。
4. 复盘环境归因时，优先读 `review_brief.environment_fit.json`。
5. 需要证据展开时，再读 `review_findings.environment_fit.json` 和 `review_packet.environment_fit.json`。
6. 比较两年 vs 十年时，先读 `baoma_2y_vs_10y_factor_stability.json`，再读 `environment_fit_comparison.json`。

## Boundaries

- 标准入口不改变策略参数。
- 标准入口不重新回测。
- 标准入口不新增市场阶段归因。
- 当前 `review_packet/review_findings/review_brief` 使用 `focus=environment_fit`，
  只服务当前环境适配主线。
- `reports/` 是本地输出目录，通常被 Git ignore；版本化记录只保存路径、schema 和状态。

## Next Allowed Actions

1. **最推荐：市场阶段归因接入。**
   方向：行情阶段验证。
   目的：在标准入口已补齐后，把入场和出场所在市场阶段加入归因，验证稳定偏强因子是否跨行情阶段成立。

2. **候选规则草案。**
   方向：实验设计。
   目的：把 `MA60 > 2ATR`、`near_high_60d`、非银金融弱项整理成待人工确认的实验草案，而不是直接改策略。

3. **性能优化。**
   方向：运行效率。
   目的：优化 attribution wide samples 的 per-trade 计算路径，减少后续十年或全 A 归因的等待时间。
