# Baoma V1 20Y Stability Research

本文档记录 2026-07-03 对
`docs/baoma-v1-20260703-practical-freeze` 所封存 Baoma V1 策略的
20 年稳定性研究入口判断。

## Scope Assumption

本研究先按“20 个完整自然年”理解：

```text
2006-01-01 到 2025-12-31
```

如果“20 年”实际是指 `2020 年` 单年度稳定性，应改成年度切片研究，
不能和本文的 20 年窗口混用。

## Branch And Local Evidence Check

已切出研究分支：

```text
research/baoma-v1-20y-stability
```

初始检查时 CodeGraph 在当前工作区显示未初始化。按本研究分支要求，
已在当前仓库根目录执行 `codegraph init`，当前索引状态为 up to date：

- files: 762
- nodes: 11,791
- edges: 34,910

后续结构定位优先使用 CodeGraph；字面文本和报告字段仍使用 `rg`。

初始检查时，当前工作区缺少正式 20 年研究所需的本地离线证据：

- `data/` 目录不存在。
- freeze manifest 指向的 2015-2025 run artifact 不存在于本机
  `reports/` 下。
- freeze manifest 指向的动态成分股 Parquet、historical union CSV、
  3x3 soil/seed summary 和 4D score/soil/seed matrix summary 均不在本机。
- 初始检查时，本机 `reports/` 只看到已有的 2Y vs 10Y environment-fit
  comparison 相关目录，不能替代完整 run artifact。本次 dry-run 额外生成的
  `_research-baoma-v1-20y-stability-scored-contract` 只是调参契约输出，
  不是历史回测证据。

用户随后明确授权从并行开发 checkout：

```text
C:\Work\GitWork\GoalStockBacktrad
```

复制数据到当前仓库。已导入到当前仓库 ignored runtime 目录：

| imported artifact | target |
|---|---|
| market/reference snapshots, 177,509 files, about 13.55GB | `data/snapshots/` |
| 2015-2025 dynamic run artifact, 36 files, about 2.27GB | `reports/baoma-v1-dynamic-hs300-csi500-2015-2025-strict-t1-industry-evidence-run-window-union/` |
| 2015-2025 soil/seed 3x3 report | `reports/soil-seed-strength-3x3-baoma-v1-dynamic-hs300-csi500-2015-2025-strict-t1-current-run/` |
| 2015-2025 score/soil/seed 4D matrix report | `reports/score-soil-seed-4d-matrix-baoma-v1-dynamic-hs300-csi500-2015-2025-strict-t1-industry-evidence/` |
| 2015-2025 dynamic pool input | `reports/baoma-v1-dynamic-hs300-csi500-2015-2025/input/` |
| 2005-2014 pre-2015 input | `reports/pre2015-2005-2014/input/` |

初始导入后未发现现成的合并窗口：

```text
reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/
```

已在当前仓库生成 2006-2025 合并窗口输入：

| artifact | path |
|---|---|
| dynamic constituents | `reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/hs300-csi500-dynamic-constituents-2006-2025-with-2005-anchor.parquet` |
| run-window union pool | `reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/hs300-csi500-dynamic-union-run-window-2006-2025-with-2005-anchor.csv` |
| industry-evidence RunPlan | `reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/run-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-industry-evidence.yaml` |
| no-industry RunPlan | `reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/run-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-run-window-union.yaml` |

生成口径：

- 2005-2014 动态成分来自 `reports/pre2015-2005-2014/input/`。
- 2015-2025 动态成分来自 `reports/baoma-v1-dynamic-hs300-csi500-2015-2025/input/`。
- 2015 以后只取 `trade_date >= 2015-01-01`，避免 2014 anchor 与
  pre-2015 输入重复。
- 合并后 `dynamic_row_count=860394`，run-window rows 为 `806094`。
- 2006-2025 run-window union 成分股数为 `2001`。

已执行最小离线 preflight：

```text
python -m attbacktrader.cli.data_preflight \
  --config examples/run-baoma-v1-fixed-sample-2015-2024-maxhold800.yaml \
  --offline-data \
  --max-symbols 1 \
  --json \
  --strict
```

结果：`status=error`。最小样本已失败：

- `checked_symbol_count=1`
- `failed_symbol_count=1`
- `error_summary.index.ValueError=33`
- `error_summary.symbol.ValueError=1`
- 股票、沪深300、中证500和 31 个 SW2021 一级行业指数都需要 provider
  才能创建或刷新快照。

这说明当前工作区不能直接进行正式离线回测。若此时联网补数并继续把结果
写成“正式回测证据”，会违反项目的回测证据边界。

导入后已使用 2015-2025 freeze run plan 做小样本离线 preflight：

```text
python -m attbacktrader.cli.data_preflight \
  --config reports/baoma-v1-dynamic-hs300-csi500-2015-2025-strict-t1-industry-evidence-run-window-union/run_plan.json \
  --offline-data \
  --max-symbols 5 \
  --json \
  --strict
```

结果：

- `status=warning`
- `failed_symbol_count=0`
- `index_results` 为 `ok`
- 31 个 SW2021 行业指数均为 `ok`
- 快照动作为 `exact_reused`
- warning 来自部分股票 `daily_bars.MISSING_TRADING_SESSIONS` 和
  `daily_bars.MISSING_LEADING_RANGE`

这说明导入后的快照已经可被离线流程读取；但这还不是完整 1,552 只股票的
正式 preflight，只是复制后可用性验证。

## 2026-07-03 Data Completeness Result

### Industry-Evidence Path

2006-2025 industry-evidence RunPlan 的小样本离线 preflight：

```text
python -m attbacktrader.cli.data_preflight \
  --config reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/run-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-industry-evidence.yaml \
  --offline-data \
  --max-symbols 20 \
  --json \
  --strict
```

结果为 `status=error`：

- `checked_symbol_count=20`
- `failed_symbol_count=8`
- 31 个 SW2021 行业指数全部 error。
- 行业指数错误为 `provider is required when industry index snapshots must be refreshed or created`。

结论：当前本地数据不能支持 2006-2025 industry-evidence 正式离线回测。
SW2021 行业指数需要先补齐到 2006-2025；否则不能报告行业归因、行业 KDJ/MACD
或 `entry.volatility.symbol_atr_to_industry_median_bucket` 等行业证据。

### No-Industry Local Consolidation

为分离行业指数缺口，已生成 no-industry RunPlan：

```text
reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/run-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-run-window-union.yaml
```

该 RunPlan 关闭：

- `data.industry_series.indexes`
- `analysis.industry_attribution.enabled`
- `analysis.entry_attribution.enabled`
- `analysis.attribution.enabled`

第一次完整 no-industry 离线 preflight 结果：

| item | value |
|---|---:|
| requested symbols | 2,001 |
| warning symbols | 222 |
| error symbols | 1,779 |
| daily snapshot errors | 1,617 |
| tradability snapshot errors | 162 |

诊断后确认，大量 error 并不是完全没有本地数据，而是快照被切成多段：

```text
data/snapshots/daily_bars/qfq/<symbol>_<start>_<end>.parquet
data/snapshots/tradability/stock/<symbol>_<start>_<end>.parquet
```

预检需要单个声明覆盖全窗口的目标快照；因此已执行本地离线 consolidation，
只在源分段文件名能证明覆盖完整目标区间时生成宽快照，不覆盖既有目标文件。

consolidation manifest：

```text
reports/baoma-v1-dynamic-hs300-csi500-2006-2025/preflight-offline/local-snapshot-consolidation.json
```

结果：

| target | exists | created | missing source ranges |
|---|---:|---:|---:|
| daily bars, 2005-01-01..2025-12-31 | 384 | 367 | 1,250 |
| tradability, 2006-01-01..2025-12-31 | 222 | 247 | 1,532 |

consolidation 后再次完整 no-industry 离线 preflight：

```text
reports/baoma-v1-dynamic-hs300-csi500-2006-2025/preflight-offline/data-preflight-no-industry-full-after-local-consolidation.json
```

结果：

| item | value |
|---|---:|
| requested symbols | 2,001 |
| warning symbols | 469 |
| error symbols | 1,532 |
| daily snapshot errors | 1,250 |
| tradability snapshot errors | 282 |

注意：剩余 1,532 只被排除的股票全部缺 tradability 覆盖；其中 1,250 只还同时缺
daily bars 覆盖。不能用默认 tradability 或空数据静默补齐。

### Offline-Local-Complete Filtered Universe

已生成显式过滤后的本地完整股票池和 RunPlan：

| artifact | path |
|---|---|
| filtered stock pool | `reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/hs300-csi500-dynamic-union-run-window-2006-2025-with-2005-anchor-offline-local-complete.csv` |
| filtered RunPlan | `reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/run-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-offline-local-complete.yaml` |
| filter manifest | `reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/run-window-local-data-filter.json` |

过滤结果：

| item | value |
|---|---:|
| base symbols | 2,001 |
| retained symbols | 469 |
| excluded symbols | 1,532 |

过滤版完整离线 preflight：

```text
python -m attbacktrader.cli.data_preflight \
  --config reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/run-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-offline-local-complete.yaml \
  --offline-data \
  --strict \
  --no-progress \
  --output reports/baoma-v1-dynamic-hs300-csi500-2006-2025/preflight-offline/data-preflight-no-industry-offline-local-complete-full.json
```

结果：

| item | value |
|---|---:|
| status | warning |
| symbols | 469/469 |
| error symbols | 0 |
| warning symbols | 469 |
| `MISSING_LEADING_RANGE` | 265 |
| `MISSING_TRADING_SESSIONS` | 469 |
| `MISSING_TRAILING_RANGE` | 27 |

这个结果只证明 `469` 只 no-industry 子宇宙可以完全离线进入下一步。
它不能替代 2,001 只全量动态池结论，也不能替代 industry-evidence 结论。

### Remaining Data Gaps To Import

已生成剩余缺口清单：

| artifact | path |
|---|---|
| JSON gap inventory | `reports/baoma-v1-dynamic-hs300-csi500-2006-2025/preflight-offline/local-data-gap-inventory.json` |
| CSV gap inventory | `reports/baoma-v1-dynamic-hs300-csi500-2006-2025/preflight-offline/local-data-gap-inventory.csv` |

汇总：

| profile | count |
|---|---:|
| daily missing + tradability missing | 1,250 |
| daily ok + tradability missing | 282 |

若要把 2006-2025 全量动态池推进到正式离线回测，至少还需要导入或准备：

- 1,250 只股票的 qfq daily bars 宽区间快照，目标声明区间为
  `2005-01-01..2025-12-31`。
- 1,532 只股票的 tradability 宽区间快照，目标声明区间为
  `2006-01-01..2025-12-31`。
- 31 个 SW2021 行业指数的 index bars，目标覆盖 `2006-01-01..2025-12-31`；
  如果继续做 industry-evidence，还要保证行业归因所需的行业会员/证据链完整。

### Gap-Fill Follow-Up

用户确认“补齐”。已进入联网数据准备阶段，并保持以下边界：

- 使用 Tushare 只刷新本地 ignored snapshot 和 prepare-data artifact。
- 不把联网阶段输出当正式回测结果。
- 补齐后必须再用 `--offline-data --strict` 复验。
- Tushare token 来自环境变量 `TUSHARE_TOKEN`，没有写入仓库文件。

补齐过程发现两个特殊问题：

1. `600018.SH` 的 Tushare qfq `pro_bar` 在 2006 年返回 383 行 OHLC 全为
   `NaN` 的记录。处理方式：只把有效 OHLC 行写入 daily bar snapshot；
   停牌/无行情日由 tradability snapshot 表达。
2. `T00018.SH` 是沪深300历史成分中的临时代码，覆盖 `2005-04-08..2006-10-25`；
   `600018.SH` 从 `2006-10-26` 接续。处理方式：生成 normalized-symbols
   输入，把 `T00018.SH -> 600018.SH`，不把它当独立股票。

手工修复和 normalized manifest：

```text
reports/baoma-v1-dynamic-hs300-csi500-2006-2025/prepare-data/manual-data-fixes-and-symbol-normalization.json
```

normalized 关键输入：

| artifact | path |
|---|---|
| dynamic pool | `reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/hs300-csi500-dynamic-constituents-2006-2025-with-2005-anchor-normalized-symbols.parquet` |
| stock pool | `reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/hs300-csi500-dynamic-union-run-window-2006-2025-with-2005-anchor-normalized-symbols.csv` |
| no-industry RunPlan | `reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/run-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-normalized-symbols.yaml` |
| industry-evidence RunPlan | `reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/run-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-industry-evidence-normalized-symbols.yaml` |

no-industry normalized 全量离线 preflight：

```text
python -m attbacktrader.cli.data_preflight \
  --config reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/run-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-normalized-symbols.yaml \
  --offline-data \
  --strict \
  --no-progress \
  --output reports/baoma-v1-dynamic-hs300-csi500-2006-2025/preflight-offline/data-preflight-no-industry-normalized-symbols-full.json
```

结果：

| item | value |
|---|---:|
| status | warning |
| symbols | 2,000/2,000 |
| error symbols | 0 |
| warning symbols | 2,000 |
| `MISSING_LEADING_RANGE` | 1,087 |
| `MISSING_TRADING_SESSIONS` | 2,000 |
| `MISSING_TRAILING_RANGE` | 155 |

结论：`2006-2025 no-industry normalized` 股票侧数据已经补齐到可离线运行；
warning 仍需在报告中作为停牌、上市时间、尾部缺口等质量提示暴露。

industry-evidence normalized 数据准备：

- 31 个 SW2021 行业指数联网 gap-fill 成功创建 snapshot。
- gap-fill 报告：
  `reports/baoma-v1-dynamic-hs300-csi500-2006-2025/prepare-data/data-preflight-gapfill-industry-evidence-normalized-symbols-max1.json`
- 行业指数覆盖表：
  `reports/baoma-v1-dynamic-hs300-csi500-2006-2025/prepare-data/industry-index-coverage-summary.csv`

但 industry-evidence normalized 全量离线 preflight 仍失败：

```text
reports/baoma-v1-dynamic-hs300-csi500-2006-2025/preflight-offline/data-preflight-industry-evidence-normalized-symbols-full.json
```

结果：

| item | value |
|---|---:|
| status | error |
| stock symbols | 2,000/2,000 |
| stock error symbols | 0 |
| industry index errors | 31 |
| error summary | `index.ValueError: 31` |

根因：当前 Tushare/SW2021 行业指数日线实际从 `2012-08-01` 附近开始，
不能覆盖 2006-2025 industry factors 所需的 2005 warmup 和 2006-2012 run window。
这不是 token、复制或重试问题，不能用默认值或空数据补齐。

当前数据完整性 summary：

```text
reports/baoma-v1-dynamic-hs300-csi500-2006-2025/prepare-data/data-completeness-summary.json
```

截至本次补齐后，安全结论改为：

```text
2006-2025 no-industry normalized universe 已具备正式离线回测数据条件；
2006-2025 SW2021 industry-evidence universe 不具备正式离线回测数据条件。
```

## Parallel Branch Data Import Note

用户提示并行开发分支附近可能有数据目录：

```text
C:\Work\GitWork\GoalStockBacktrad\data
C:\Work\GitWork\GoalStockBacktrad\datas
```

但本仓库的 AGENTS 约束是：只在当前仓库根目录内读取、编辑和运行本仓库任务，
不依赖当前仓库根目录之外的其他 checkout。因此不要让 RunPlan、文档或报告
直接引用上述外部路径。

如果这些目录确实包含本研究需要的快照或 run artifact，推荐做法是把数据复制
到当前仓库的 ignored runtime 目录后再验证：

| source kind | target under current repo |
|---|---|
| market/reference snapshots | `data/snapshots/` |
| completed run artifacts | `reports/<run_id>/` |
| dynamic stock pool input CSV/Parquet/metadata | `reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/` |
| attribution/reference snapshots | `data/snapshots/attribution_reference/` 或 run plan 所声明的 snapshot path |

拷贝后必须先跑离线 preflight。只有 `--offline-data --strict` 通过后，才能把
这些 copied artifacts 当作正式回测输入。

## Existing Evidence That Can Be Used

### 2015-2024 Fixed-Sample Evidence

`docs/baoma-v1-2015-2024-environment-fit-closure.md` 和
`examples/baoma-v1-2015-2024-environment-fit-baseline.json` 已封存
2015-2024、固定 800 股票池、`max_holding_count=800` 的样本采集证据。

核心数字：

| item | value |
|---|---:|
| closed trades | 18,349 |
| win rate | 48.32% |
| profit/loss ratio | 1.66 |
| max drawdown | 1.83% |
| environment-fit return on entry value | 1.10% |
| environment-fit net PnL | 1,285,797,727 |

重要边界：这是 `Trade-Sample Backtest`，不是真实组合收益证据。
它使用大资金和 `max_holding_count=800`，没有真实资金竞争、持仓容量竞争
和行业集中度约束。

### 2023-2024 vs 2015-2024 Stability Evidence

`docs/baoma-v1-2y-vs-10y-environment-fit-stability.md` 已完成
2 年和 10 年归因稳定性比较。

稳定偏强线索包括：

- `MA60 上方超过 2ATR`：2 年 lift 0.71%，10 年 lift 0.82%。
- `接近 60 日高点`：2 年 lift 1.28%，10 年 lift 0.96%。
- 中证500 bullish、沪深300和中证500双强环境。
- 电子、计算机行业稳定偏强。
- `MA60 上方超过 2ATR + 电力设备/电子` 组合稳定偏强。

稳定偏弱线索包括：

- 非银金融、交通运输行业稳定偏弱。
- `固定 5% 止盈=1_2ATR + 非银金融` 稳定偏弱。

重要边界：这是归因稳定性比较，不是策略调参结果，也不是上线规则。

### 2015-2025 Dynamic-Membership Freeze

`docs/baoma-v1-20260703-practical-freeze` 封存了 2015-2025 动态沪深300
+ 中证500 成分股样本采集结果和 soil/seed/score 诊断矩阵。

关键结论：

- 已平仓交易 25,253 笔。
- `强土壤 + 强种子`：3,829 笔，胜率 59.31%，均笔收益 2.24%，PF 1.68。
- `score 3-4` 开始整体改善。
- `score 5-8` 整体较好但不严格单调。
- `score 9+` 样本只有 79 笔且总 PnL 为负，不能解释为越高越好。
- `弱土壤 + 弱种子` 应作为下一轮组合回测优先排除项。

重要边界：当前工作区没有该 freeze 指向的完整 `reports/` 原始证据，
所以本机不能重新审计逐笔交易、逐日信号、sizing decision、完整年度矩阵
和字段覆盖率。

## Current Judgment

当前证据支持的判断是：

```text
Baoma V1 在 2015-2025 样本采集口径下存在清晰的趋势/动量环境适配线索；
soil/seed 能解释同一 score 附近的交易质量差异；
但当前工作区仍不能证明该策略在 2006-2025 的全量 20 年稳定性。
```

补齐后，当前本地数据已经支持一个完整股票侧、但不含行业证据的 20 年口径：

```text
2006-2025 no-industry normalized universe, 2,000 symbols, offline preflight error=0
```

这个口径可以进入正式离线 trade-sample 回测，用来验证 2006-2025 股票信号和
A 股执行约束下的基础稳定性；但它仍不包含 SW2021 行业指数证据，不能和
2015-2025 industry-evidence freeze 直接等价比较。

当前本地数据不能支持：

```text
2006-2025 SW2021 industry-evidence normalized universe
```

原因不是股票缺口，而是 SW2021 行业指数日线实际从 2012-08 左右开始，
无法覆盖 2006-2012 和 2005 warmup。除非换用可追溯到 2006 的行业指数来源、
降低/改造行业因子口径，或把 industry-evidence 分析窗口后移，否则不能把
industry-evidence 作为完整 20 年证据。

从 20 年研究视角，最重要的风险是：

- A 股 2006-2014 的市场制度、成分股结构、流动性和小盘风格与
  2015-2025 差异很大。
- 如果直接把 2015-2025 soil/seed/score 结论外推到 2006-2014，
  会产生样本外稳定性误判。
- 如果继续只看 `max_holding_count=800` 样本采集结果，会把“信号广泛有效”
  和“真实组合可赚钱”混在一起。
- 如果在完整 20 年样本上一次性调阈值，再报告 20 年表现，会变成样本内调参。

因此，20 年稳定性必须拆成两层证据：

1. `Trade-Sample Backtest`：先用 no-industry normalized 口径验证信号是否跨
   20 年仍有方向性。
2. `Scored Portfolio Backtest`：验证真实持仓数、现金竞争和行业约束下是否仍稳定。

只有第二层通过，才可以讨论实战组合口径。

## Proposed 20Y Research Design

### Stage 0 - Data Preparation Only

数据准备阶段可以联网，但输出必须落成本地快照和输入 artifact。
正式回测阶段必须完全离线。

推荐先生成 2006-2025 run window 所需的动态池，并保留 2005 anchor：

```text
python -m attbacktrader.cli.dynamic_stock_pool \
  --start-date 2005-01-01 \
  --end-date 2025-12-31 \
  --output-parquet reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/hs300-csi500-dynamic-constituents-2006-2025-with-2005-anchor.parquet \
  --union-output reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/hs300-csi500-dynamic-union-run-window-2006-2025-with-2005-anchor.csv \
  --metadata-output reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/hs300-csi500-dynamic-constituents-2006-2025-with-2005-anchor.json
```

然后用数据准备模式刷新本地快照。此阶段可以使用 Tushare，但产物不能直接
当作正式回测结果：

```text
python -m attbacktrader.cli.run_plan \
  --config reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/run-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-industry-evidence.yaml \
  --tushare-date-window-days 8000 \
  --progress-log reports/baoma-v1-dynamic-hs300-csi500-2006-2025/prepare-data/run-plan-progress.ndjson \
  --summary-json
```

### Stage 1 - Offline Preflight

正式回测前必须先离线 preflight：

```text
python -m attbacktrader.cli.data_preflight \
  --config reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/run-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-industry-evidence.yaml \
  --offline-data \
  --strict \
  --output reports/baoma-v1-dynamic-hs300-csi500-2006-2025/preflight-offline/data-preflight.json
```

通过条件：

- `status=ok`。
- 覆盖 2006-01-01 到 2025-12-31 的股票、沪深300、中证500和 SW2021
  行业指数快照。
- 缺失、排除、warning 都必须显式记录，不能默认填充。

### Stage 2 - 20Y Trade-Sample Backtest

第一层研究仍保持 freeze 的样本采集口径，以便和当前 baseline 可比：

- `max_holding_count=800`
- `initial_cash=10,000,000,000`
- `baoma_entry`
- `baoma_ma25_profit_exit`
- `baoma_ma60_stop`
- `baoma_add_on`
- 动态沪深300 + 中证500 T-1 成分股门槛
- A 股 T+1、涨跌停、停牌、整手约束

正式回测命令必须使用 `--offline-data`：

```text
python -m attbacktrader.cli.run_plan \
  --config reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/run-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-industry-evidence.yaml \
  --offline-data \
  --progress-log reports/baoma-v1-dynamic-hs300-csi500-2006-2025/run-offline/run-plan-progress.ndjson \
  --summary-json
```

交易样本层面的稳定性指标至少包括：

- 分年度交易数、胜率、均笔收益、PF、净 PnL。
- rolling 5Y 的交易数、胜率、均笔收益、PF。
- score bucket 的年度正样本比例。
- soil/seed 3x3 的年度正样本比例。
- soil_type/seed_type 的年度正样本比例。
- 2006-2014 与 2015-2025 的同口径差异。
- 牛市、熊市、震荡市中的同口径差异。

建议的通过线：

- 核心组合 `强土壤 + 强种子` 在有足够样本的年份中至少 70% 年份均笔收益为正。
- `弱土壤 + 弱种子` 相对核心组合长期劣后，而不是只在一两个年份劣后。
- `score 3-4` 以上相对 `<=0` 和 `1-2` 有稳定 lift，但不要求严格单调。
- 2006-2014 不出现完全相反的 soil/seed 方向。

这些通过线只用于判断是否值得进入组合层，不用于直接生成交易规则。

### Stage 3 - Scored Portfolio Backtest

第二层研究必须进入真实组合约束：

```yaml
sizing_params:
  max_holding_count: 10
  max_total_exposure_percent: 0.85
  max_risk_group_exposure_percent: 0.20
  risk_group_level: 1
  min_order_quantity: 100
```

使用 freeze 中的三档 gate 作为初始对照，而不是在全样本中直接定死：

| gate | rule |
|---|---|
| conservative | `score >= 5` 且 `强土壤 + 强种子`，或类型为 `全局强势/行业带动 + 健康趋势回踩` |
| balanced | `score >= 4` 且 soil/seed 至少一个为强，排除 `弱土壤 + 弱种子` |
| aggressive | `score >= 3` 且进入类型白名单，允许 `强种子 + 弱土壤` 小仓位参与 |

当前 `att-scored-entry-allocation-tuning --mode dry-run` 的默认 walk-forward
只覆盖 2015-2024：

| fold | train | test |
|---|---|---|
| 1 | 2015-2019 | 2020 |
| 2 | 2016-2020 | 2021 |
| 3 | 2017-2021 | 2022 |
| 4 | 2018-2022 | 2023 |
| 5 | 2019-2023 | 2024 |

20 年研究应扩展 walk-forward，例如：

- train 2006-2010, test 2011
- train 2007-2011, test 2012
- ...
- train 2020-2024, test 2025

组合层通过条件至少包括：

- 样本外年度收益和基准超额不能由少数年份贡献。
- 最大回撤可接受，并且不能显著劣于 baseline 解释。
- 换手和交易成本后仍有正向超额。
- 行业集中度被约束后，核心 soil/seed/score 仍有效。
- gate 从 conservative 到 aggressive 的收益和回撤变化可解释。

## Recommended Next Step

### 2026-07-03 Objective Correction

用户进一步明确，本轮 20Y 研究的第一产物不是直接证明组合收益，
而是取得 Baoma 策略的逐笔交易内容，供后续做归因矩阵使用。

目标矩阵为：

```text
score x year x seed x soil
```

因此正式回测的成功条件应改为：

- 生成完整 closed trades，用于逐笔交易样本。
- 生成完整 `signal_audit`，用于回连 entry signal date 和入场环境。
- 保留足够的 entry attribution categories / values，供后续重算 score、seed、
  soil。
- 明确记录无法生成的行业字段，而不是用空值、近似值或后验行业数据填充。

当前已完成的最终无行业离线 preflight：

```text
reports/baoma-v1-dynamic-hs300-csi500-2006-2025/preflight-offline/data-preflight-no-industry-normalized-symbols-final-check.json
```

结果：

| item | value |
|---|---:|
| requested symbols | 2,000 |
| checked symbols | 2,000 |
| failed symbols | 0 |
| status | warning |
| benchmark indexes | `000300.SH`, `000905.SH` ok |
| industry indexes | none |
| snapshot actions | `exact_reused` only |

warning 来自交易日覆盖质量告警，不是缺失快照或联网依赖：

- `daily_bars.MISSING_LEADING_RANGE`: 1,087
- `daily_bars.MISSING_TRADING_SESSIONS`: 2,000
- `daily_bars.MISSING_TRAILING_RANGE`: 155

这说明 `no-industry normalized` 路径可以作为离线回测数据底座。
但当前 no-industry RunPlan 关闭了：

- `analysis.attribution.enabled`
- `analysis.entry_attribution.enabled`
- `analysis.industry_attribution.enabled`

如果直接使用该 RunPlan 回测，只能得到交易内容和基础 `signal_audit`；
后续 4D 矩阵会缺少关键 score/seed/soil 证据。

1. **主线推进方向**：先创建并验证一个
   `2006-2025 no-industry attribution normalized` RunPlan。
   它沿用已通过 preflight 的股票、指数、动态池和执行约束，但开启非行业
   entry attribution 字段，用于产出后续矩阵所需的交易级环境证据。
   不做这一步的风险是跑完 20 年后只能看交易样本，无法稳定生成
   `score x year x seed x soil` 矩阵。
   下一步最小动作是从
   `run-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-normalized-symbols.yaml`
   派生新 RunPlan，只启用非行业字段：

   - `entry.momentum.return_20d_bucket`
   - `entry.momentum.return_60d_bucket`
   - `entry.price_position.signal_close_ma60_atr_multiple_bucket`
   - `entry.signal_strength.dea_value_bucket`
   - `entry.signal_strength.dif_dea_distance_bucket`
   - `entry.signal_strength.macd_bar_bucket`
   - `entry.stop_fit.fixed_atr_multiple_bucket`
   - `market.csi500.weekly.kdj_state`
   - `market.hs300.weekly.kdj_state`

   已创建归因样本生产 RunPlan：

   ```text
   reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/run-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols.yaml
   ```

   该 RunPlan 的校验结果：

   - `analysis.attribution.enabled=true`
   - `analysis.entry_attribution.enabled=true`
   - `analysis.industry_attribution.enabled=false`
   - `data.industry_series.indexes=[]`
   - 非行业归因字段数：9

   已执行 5 标的小样本离线 preflight：

   ```text
   reports/baoma-v1-dynamic-hs300-csi500-2006-2025/preflight-offline/data-preflight-no-industry-attribution-normalized-symbols-smoke.json
   ```

   结果为 `status=warning`，`checked=5`，`failed=0`。warning 仍是日线覆盖
   质量告警，不是联网依赖或行业指数缺失。

### 2026-07-03 Attribution-Sample Run Result

已按“交易内容 + 归因样本生产”口径完成正式离线回测：

```text
python -m attbacktrader.cli.run_plan \
  --config reports/baoma-v1-dynamic-hs300-csi500-2006-2025/input/run-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols.yaml \
  --offline-data \
  --progress-log reports/baoma-v1-dynamic-hs300-csi500-2006-2025/run-logs/baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols.progress.ndjson \
  --progress-interval-days 20 \
  --summary-json
```

输出目录：

```text
reports/baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/
```

本次运行完成状态：

| item | value |
|---|---:|
| run window | 2006-01-01..2025-12-31 |
| symbols | 2,000 |
| evidence status | ok |
| evidence errors | 0 |
| evidence warnings | 0 |
| trade rows | 43,100 |
| closed trades | 42,909 |
| open positions | 191 |
| signal audit rows | 8,879,478 |
| enter intents | 43,100 |
| completed execution events | 142,970 |
| sizing decisions | 65,530 |

关键产物：

| artifact | rows / size | purpose |
|---|---:|---|
| `trades.parquet` | 43,100 rows | closed trades + open positions |
| `signal_audit.parquet` | 8,879,478 rows, about 1.19GB | signal / intent / entry attribution source |
| `trade_attribution.json` | about 436MB | post-trade attribution |
| `trade_lifecycle.json` | about 628MB | lifecycle detail |
| `trade_review.json` | about 293MB | trade review and opportunity samples |
| `result_diagnostics.json` | about 763MB | run diagnostics |
| `execution_audit.parquet` | 142,970 rows | execution event audit |
| `evidence_validation.json` | status ok | artifact consistency check |

`trades.parquet` 分布：

| record_type | count |
|---|---:|
| closed_trade | 42,909 |
| open_position | 191 |

`signal_audit.parquet` intent 分布：

| intent_type | count |
|---|---:|
| hold | 8,567,940 |
| avoid | 202,326 |
| enter | 43,100 |
| add_on | 22,430 |
| exit_loss | 22,723 |
| exit_profit | 20,959 |

入场样本 9 个非行业归因字段覆盖：

| field | present | missing | present rate |
|---|---:|---:|---:|
| `entry.momentum.return_20d_bucket` | 43,046 | 54 | 99.87% |
| `entry.momentum.return_60d_bucket` | 42,847 | 253 | 99.41% |
| `entry.price_position.signal_close_ma60_atr_multiple_bucket` | 42,854 | 246 | 99.43% |
| `entry.signal_strength.dea_value_bucket` | 43,100 | 0 | 100.00% |
| `entry.signal_strength.dif_dea_distance_bucket` | 43,100 | 0 | 100.00% |
| `entry.signal_strength.macd_bar_bucket` | 43,100 | 0 | 100.00% |
| `entry.stop_fit.fixed_atr_multiple_bucket` | 43,053 | 47 | 99.89% |
| `market.csi500.weekly.kdj_state` | 43,097 | 3 | 99.99% |
| `market.hs300.weekly.kdj_state` | 43,100 | 0 | 100.00% |

说明：

- 本次正式运行全程使用 `--offline-data`，没有正式回测期间联网补数。
- 这不是完整 industry-evidence run；行业指数、行业 KDJ、行业 ATR 中位数等字段
  没有启用，不能把本次结果解释为行业归因证据。
- `equity_curve.parquet` 和 `positions.parquet` 当前为空表；本轮目标是交易记录和归因
  样本生产，不把它作为最终组合权益曲线证据使用。
- 回测摘要中包含收益类指标，但本阶段只作为运行诊断，不作为 scored portfolio
  收益结论。

2. **风险纠偏方向**：不要把 no-industry 结果解释成 industry-evidence 结果。
   现在最大的误判风险是沿用 2015-2025 的 soil/seed/industry 解释，但 2006-2012
   没有 SW2021 行业指数证据。
   下一步最小动作是把 industry-evidence 方向拆成单独决策：要么寻找可覆盖
   2006 的行业指数来源，要么把行业证据窗口后移到可覆盖区间，要么暂时从
   20 年结论中移除行业因子。

3. **扩展研究方向**：trade-sample 通过后，再扩展 scored portfolio walk-forward。
   不做这一步会继续停留在大资金样本采集证据，无法回答真实组合稳定性。
   下一步最小动作是把 scored allocation 默认 folds 从 2015-2024 扩展到 2006-2025，
   并用 conservative/balanced/aggressive 三档 gate 做样本外对照。

### 2026-07-03 Score x Year x Seed x Soil Matrix

已基于本次正式离线 run 的 `trades.parquet` + `signal_audit.parquet` 生成
无行业版四维归因矩阵。

输出目录：

```text
reports/score-year-seed-soil-matrix-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/
```

核心文件：

| artifact | purpose |
|---|---|
| `scored_trade_rows.parquet` / `.csv` | 每笔平仓交易 + `score_no_industry_v1` + seed/soil 标签 |
| `matrix_score_year_seed_soil_exact.parquet` / `.csv` | 精确分数 x 年份 x 种子 x 土壤主矩阵 |
| `matrix_score_bucket_year_seed_soil.parquet` / `.csv` | 分数桶 x 年份 x 种子 x 土壤矩阵 |
| `score_summary.parquet` / `.csv` | 按精确分数汇总 |
| `score_bucket_summary.parquet` / `.csv` | 按分数桶汇总 |
| `soil_seed_summary.parquet` / `.csv` | 土壤 x 种子汇总 |
| `field_coverage.parquet` / `.csv` | 评分字段覆盖和取值分布 |
| `metadata.json` | 规则、阈值、输入、缺失处理口径 |
| `summary.zh.md` | 中文摘要 |

矩阵和 summary 表已扩展收益分布字段：中位收益、P10/P90、收益标准差、
最大单笔收益、最大单笔亏损、最大单笔亏损幅度、平均盈利、平均亏损、
平均盈亏比、最大/最小单笔净盈亏、平均/最长持仓天等。这里的“最大单笔亏损”
是已平仓交易的 realized return 最差值，不是持仓期间最大浮亏/MAE。

生成口径：

- 只读本地 run artifact，不重跑策略、不联网。
- 只纳入 `record_type=closed_trade` 的 42,909 笔平仓交易；191 个
  `open_position` 排除在收益矩阵之外。
- 入场信号回连使用 `symbol + entry_date`，43,100 个 enter 信号，平仓交易回连缺失 0。
- `score_no_industry_v1` 使用 10 个 `signal_audit.attribution.categories` 字段：
  `symbol.macd.energy_zone`、7 个入场/个股强度字段、2 个市场周 KDJ 字段。
- 这不是旧的 industry fixed score5；行业 KDJ、行业 ATR、行业指数土壤均未纳入。
- 缺失或未知 score 字段对分数贡献 0，但在 coverage 中显式记录。
- seed 分层严格要求 8 个 seed 字段完整，缺任一字段记为 `unknown_seed`。
- soil 分层严格要求 `market.csi500.weekly.kdj_state` 与
  `market.hs300.weekly.kdj_state` 同时存在，缺任一字段记为 `unknown_soil`。

覆盖校验：

| item | value |
|---|---:|
| closed trades in matrix | 42,909 |
| open positions excluded | 191 |
| signal entry count | 43,100 |
| missing signal joins | 0 |
| score complete trades | 42,656 |
| score complete rate | 99.41% |
| unknown seed | 253 |
| unknown soil | 3 |

按分数桶汇总：

| score bucket | trades | win rate | avg return | PF | net pnl |
|---|---:|---:|---:|---:|---:|
| `<=0` | 1,024 | 40.72% | 0.74% | 1.37 | 25,135,135 |
| `1-3` | 1,396 | 40.83% | 0.85% | 1.43 | 50,842,030 |
| `4-6` | 3,936 | 40.14% | 1.04% | 1.51 | 192,282,025 |
| `7-9` | 10,063 | 44.06% | 1.19% | 1.48 | 530,540,053 |
| `10-12` | 14,343 | 50.01% | 1.42% | 1.48 | 802,942,727 |
| `13-15` | 10,110 | 56.21% | 1.58% | 1.45 | 709,160,992 |
| `16+` | 2,037 | 60.53% | 1.20% | 1.28 | 57,436,120 |

土壤 x 种子主观察：

| soil | seed | trades | win rate | avg return | PF | net pnl |
|---|---|---:|---:|---:|---:|---:|
| strong | strong | 14,675 | 55.58% | 2.03% | 1.67 | 1,401,332,324 |
| strong | neutral | 6,652 | 47.58% | 2.00% | 1.90 | 639,669,669 |
| strong | weak | 2,630 | 40.95% | 1.04% | 1.53 | 113,650,973 |
| neutral | strong | 10,735 | 49.19% | 0.68% | 1.20 | 104,331,970 |
| weak | strong | 4,195 | 43.22% | 0.14% | 1.04 | -32,880,304 |
| weak | weak | 274 | 32.48% | -0.80% | 0.64 | -14,283,564 |

初步判断：

- `strong_soil + strong_seed` 是当前 no-industry 口径下最清晰的正向核心样本。
- 弱土壤下，即使强种子也明显变弱，`weak_soil + weak_seed` 应作为优先排除候选。
- 分数从 `10-12` 到 `13-15` 质量继续改善，但 `16+` 胜率高、均笔和 PF 反而回落；
  这提示 score 不应单独越高越买，后面要结合 year/seed/soil 和真实组合容量验证。
- 以上仍是 trade-sample 归因矩阵，不是 portfolio 回测结论。

### 2026-07-03 Soil v2 Post-Run Matrix

已在不重跑策略、不联网的前提下，用本地 HS300/CSI500 指数快照生成
`soil_v2`，并重新输出 `score x year x seed x soil_v2` 四维矩阵。

输出目录：

```text
reports/score-year-seed-soil-v2-matrix-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/
```

核心文件：

| artifact | purpose |
|---|---|
| `index_soil_v2_features.parquet` / `.csv` | HS300/CSI500 每日 soil_v2 指数环境特征 |
| `scored_trade_rows_soil_v2.parquet` / `.csv` | 每笔平仓交易 + soil_v2 |
| `matrix_score_year_seed_soil_v2_exact.parquet` / `.csv` | 精确分数 x 年份 x 种子 x soil_v2 |
| `matrix_score_bucket_year_seed_soil_v2.parquet` / `.csv` | 分数桶 x 年份 x 种子 x soil_v2 |
| `soil_v2_seed_summary.parquet` / `.csv` | soil_v2 x seed 汇总 |
| `soil_v1_v2_cross_summary.parquet` / `.csv` | soil_v1 与 soil_v2 对照 |
| `view_year_score_seed_soil_v2_exact.zh.csv` | 中文精确分数查看表 |
| `view_year_score_bucket_seed_soil_v2.zh.csv` | 中文分数桶查看表 |

`soil_v2` 构成：

| component | source | scoring |
|---|---|---|
| weekly KDJ state | HS300/CSI500 最近已完成周线 KDJ | oversold=-1, recovering=0, strong=+1, overheated=+1 |
| daily MACD zone | HS300/CSI500 日线 MACD 三区间 | green=-2, red wrapping=+1, red escape=+2 |
| MA60 position | close 是否在 MA60 上方 | above=+1, below/equal=-1 |
| MA position bucket | close 站上最长周期 MA20/60/120/250 | above20=0, above60=+1, above120=+2, above250=+3, below20=-1 |
| MA stack | MA20/60/120 结构 | bullish_stack=+2, partial_bullish=+1, mixed=0, below_ma60=-1, bearish_stack=-2 |

分层阈值：

| soil_v2_score | layer |
|---:|---|
| `>= 8` | `strong_soil` |
| `3..7` | `neutral_soil` |
| `< 3` | `weak_soil` |
| critical component missing | `unknown_soil` |

覆盖校验：

| item | value |
|---|---:|
| closed trades | 42,909 |
| soil_v2 strong | 23,439 |
| soil_v2 neutral | 6,872 |
| soil_v2 weak | 12,450 |
| soil_v2 unknown | 148 |

`soil_v2 unknown` 主要来自 2006 年初指数 MA60 / 均线结构 warmup 不足：

| missing components | count |
|---|---:|
| HS300/CSI500 MA60 position + MA stack | 107 |
| HS300/CSI500 MA60 position + MA position bucket + MA stack | 38 |
| HS300/CSI500 weekly KDJ + MA60/MA position/MA stack | 3 |

soil_v2 x seed 关键结果：

| soil_v2 | seed | trades | win rate | avg return | PF | net pnl |
|---|---|---:|---:|---:|---:|---:|
| strong | strong | 14,219 | 54.43% | 1.85% | 1.57 | 1,197,443,660 |
| strong | neutral | 6,683 | 47.46% | 1.95% | 1.84 | 643,792,888 |
| strong | weak | 2,437 | 40.66% | 1.35% | 1.73 | 152,417,212 |
| neutral | strong | 5,259 | 53.64% | 1.39% | 1.45 | 257,048,725 |
| weak | strong | 10,127 | 46.32% | 0.40% | 1.12 | 18,291,605 |
| weak | weak | 786 | 37.91% | -0.25% | 0.89 | -16,865,834 |

soil_v1 与 soil_v2 的主要差异：

| soil_v1 | soil_v2 | trades | win rate | avg return | PF | net pnl |
|---|---|---:|---:|---:|---:|---:|
| strong | strong | 19,651 | 51.89% | 2.05% | 1.76 | 1,937,022,714 |
| strong | weak | 1,585 | 48.52% | 1.11% | 1.38 | 102,842,537 |
| neutral | weak | 6,610 | 45.76% | 0.35% | 1.12 | -43,541,506 |
| weak | weak | 4,255 | 40.99% | -0.01% | 1.00 | -59,277,834 |

初步判断：

- soil_v2 比 soil_v1 更接近“完整市场环境”，因为它同时纳入 KDJ、MACD、MA60、
  站上均线层级和均线多头结构。
- `strong_soil_v2` 下弱种子也仍有正收益，说明强市场环境对 Baoma 入场样本有明显抬升。
- `weak_soil_v2 + strong_seed` 明显降质：10,127 笔，均笔 0.40%，PF 1.12，
  只能作为低权重或待组合验证候选，不能和强土壤强种子同权。
- `weak_soil_v2 + weak_seed` 已经是明确排除候选。
- 这仍是 post-run trade-sample 归因，不是组合回测结论。

### 2026-07-03 SW2014 Stock-Time-Industry Mapping

按新的研究口径，行业部分先不做阻塞式完整性预检，也不回退到 SW2021。
本次只执行 `股票 + signal_date -> SW2014 active membership -> 当日一级行业指数土壤`
映射；缺失项保留缺失状态，避免把不存在的行业证据混入归因。

已在数据准备阶段联网拉取 SW2014 快照；后续映射和归因不联网、不重跑策略。

输出目录：

```text
reports/industry-sw2014-time-soil-map-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/
```

核心文件：

| artifact | purpose |
|---|---|
| `trade_industry_time_soil_map.parquet` / `.csv` | 每笔平仓交易 + SW2014 行业映射状态 + 行业土壤字段 |
| `industry_soil_features.parquet` / `.csv` | SW2014 一级行业指数每日 soil 特征 |
| `industry_mapping_summary.parquet` / `.csv` | 行业会员映射命中/缺失状态 |
| `industry_soil_summary.parquet` / `.csv` | 行业土壤分层后的交易表现 |
| `score_bucket_industry_soil_summary.parquet` / `.csv` | 分数桶 x 行业土壤 |
| `score_bucket_seed_industry_soil_summary.parquet` / `.csv` | 分数桶 x 种子 x 行业土壤 |
| `year_industry_soil_summary.parquet` / `.csv` | 年份 x 行业土壤 |

SW2014 快照拉取结果：

| item | value |
|---|---:|
| classifications | 359 |
| level1 industries | 28 |
| membership rows | 5,864 |
| membership symbols | 5,864 |
| level1 index bars files | 28 |

行业指数行情覆盖限制：

- `801010.SI` 到 `801230.SI` 等旧一级行业多从 `2012-08-01` 开始。
- `801710.SI` 到 `801890.SI` 等一级行业多从 `2014-02-21` 开始。
- 因此 2006-2011 以及 2012/2014 前的行业土壤仍然不能计算，保留 unknown。

membership 口径限制：

Tushare `index_member_all` 返回的会员数据中有 4 个一级代码不在 SW2014 分类表：

| code | trades |
|---|---:|
| `801950.SI` | 912 |
| `801960.SI` | 575 |
| `801970.SI` | 497 |
| `801980.SI` | 132 |

这些交易已标记为 `membership_level1_not_in_sw2014_classification`，没有强行归入
SW2014 行业土壤。

映射执行结果：

| status | trades |
|---|---:|
| `matched` | 35,173 |
| `missing_active_membership` | 7,722 |
| `missing_membership_source` | 14 |

分类状态：

| status | trades |
|---|---:|
| `matched` | 33,057 |
| `no_membership` | 7,736 |
| `missing_level1_classification` | 2,116 |

行业土壤状态：

| status | trades |
|---|---:|
| `matched` | 23,619 |
| `missing_industry_index_bar_before_signal_date` | 9,079 |
| `missing_industry_membership` | 7,736 |
| `membership_level1_not_in_sw2014_classification` | 2,116 |
| `missing_components` | 359 |

行业土壤结果：

| industry_soil | trades | win rate | avg return | median | best | worst | PF | net pnl |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `strong_industry_soil` | 10,833 | 49.43% | 1.66% | -0.33% | 98.34% | -80.05% | 1.60 | 857,798,913 |
| `neutral_industry_soil` | 5,717 | 46.13% | 0.61% | -1.18% | 114.28% | -48.56% | 1.21 | 106,270,260 |
| `weak_industry_soil` | 7,069 | 44.09% | 0.65% | -1.44% | 115.91% | -30.84% | 1.24 | 134,124,648 |
| `unknown_industry_soil` | 19,290 | 51.74% | 1.59% | 0.29% | 447.29% | -75.53% | 1.52 | 1,270,145,261 |

结论：

- SW2014 membership 和一级行业指数快照已经落到 `data/snapshots/industries/sw/SW2014/`。
- 可计算行业土壤的样本为 23,619 笔；unknown 仍有 19,290 笔，主要来自行业指数早期无行情、
  membership 缺失、以及 membership 一级代码不属于 SW2014 分类表。
- 这份结果可以作为“行业当时状态”归因的初版输入，但不能解释 2006-2011 前半段行业环境。
- 本次没有用 SW2021 兜底，也没有根据股票名称、当前行业或后验行业关系推断历史行业。

### 2026-07-03 Tushare SW Industry Data Re-Probe

针对“是否真的没有行业 K 线”重新核验 Tushare 申万相关接口。

官方文档口径：

- `index_classify` 可获取 SW2014 和 SW2021 行业分类。
- `index_member_all` 可获取申万行业成分。
- `sw_daily` 是申万行业日线行情接口。
- `index_daily` 官方说明不包含申万行业指数行情数据。

本地探测输出：

```text
reports/industry-sw2014-time-soil-map-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/tushare_sw_industry_probe.json
```

关键发现：

| query | result |
|---|---:|
| `index_classify(src='SW2014')` | 359 rows |
| `index_classify(src='SW2021')` | 511 rows |
| `index_basic(market='SW')` | 950 rows |
| `sw_daily(ts_code='801010.SI', 2000-2012)` | 0 rows |
| `index_daily(ts_code='801010.SI', 2000-2012)` | 0 rows |
| `pro_bar(asset='I', ts_code='801010.SI', 2000-2012)` | 0 rows |
| `sw_daily(trade_date='20060104')` | 171 rows |

因此，原判断需要细化：

- Tushare 早期不是完全没有申万行业日线。
- 但早期没有可直接按 SW2014 一级行业代码拉取的日线，例如 `801010.SI`
  在 `2000-01-01..2012-07-31` 返回 0 行。
- 早期 `sw_daily(trade_date=...)` 返回的主要是 SW2021 二/三级行业代码，以及
  `801950.SI` 煤炭、`801960.SI` 石油石化、`801970.SI` 环保、`801980.SI` 美容护理
  等 SW2021 一级代码。
- 样例二/三级代码可以按 `ts_code` 拉连续早期 K 线，例如 `801038.SI`、
  `801044.SI`、`857831.SI` 在 `2000-01-04..2012-07-31` 均有 3,040 行。

按 2006-01-04 的早期 `sw_daily` 代码做分类树上卷：

| item | value |
|---|---:|
| early sw_daily codes | 171 |
| mapped to strict SW2014 level1 by industry_code | 145 |
| strict SW2014 level1 covered | 26 / 28 |
| strict SW2014 level1 missing | `801020.SI` 采掘, `801230.SI` 综合 |

这提供了一条新路线：

- 可以用早期 SW2021 二/三级行业指数 K 线，通过分类树上卷，合成
  “SW2014 一级行业代理 K 线”。
- 对 `采掘`，可考虑用 SW2021 的 `煤炭 + 石油石化` 合成代理，但这是口径映射，
  不是官方 SW2014 一级指数。
- 对 `综合`，早期样本未找到严格可上卷的子行业覆盖，需要继续单独处理或保持 unknown。

当前结论：

- 官方 SW2014 一级行业 K 线仍不能直接全 20 年覆盖。
- Tushare 内存在早期申万二/三级 K 线，可用于构造“代理一级行业土壤”。
- 如果后续要做全年份行业土壤，推荐新增一个明确标注的口径：
  `synthetic_sw2014_l1_from_sw_subindustry_daily`，不能和官方 SW2014 一级行业指数混称。

### 2026-07-03 External SW Industry Source Probe

继续探测 AKShare、BaoStock、BigQuant 等 Tushare 之外的数据源。

探测产物：

```text
reports/industry-sw2014-time-soil-map-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/external_industry_source_probe.json
reports/industry-sw2014-time-soil-map-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/akshare_sw2014_l1_index_bars_metadata.json
reports/industry-sw2014-akshare-time-soil-map-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/
```

AKShare 结果：

- 使用 `ak.index_hist_sw(symbol=<801xxx>, period='day')`。
- 字段包含 `代码、日期、收盘、开盘、最高、最低、成交量、成交额`。
- 已落盘到独立快照源 `data/snapshots/industries/sw/SW2014_AKSHARE/index_bars/`，
  没有覆盖 Tushare `SW2014` 快照。

AKShare SW2014 一级行业覆盖：

| coverage | industries |
|---|---:|
| `1999-12-30..2026-07-02` | 16 |
| `1999-12-30..2021-12-10` | 1 |
| `2014-02-21..2026-07-02` | 11 |

说明：

- `801010.SI` 农林牧渔、`801020.SI` 采掘、`801030.SI` 化工等旧一级行业可以覆盖
  2006 起点。
- `801780.SI` 银行、`801790.SI` 非银金融等 2014 新一级行业仍从 `2014-02-21`
  开始。
- `801020.SI` 采掘到 `2021-12-10` 截止，符合后续 SW2021 拆成煤炭/石油石化等
  新一级行业的口径变化。

用 AKShare 行业 K 线重跑行业土壤映射后：

| source | matched soil | unknown soil |
|---|---:|---:|
| Tushare `SW2014` index bars | 23,619 | 19,290 |
| AKShare `SW2014_AKSHARE` index bars | 29,021 | 13,888 |

AKShare 版本行业土壤分布：

| industry_soil | trades | win rate | avg return | median | PF | net pnl |
|---|---:|---:|---:|---:|---:|---:|
| `strong_industry_soil` | 13,816 | 50.66% | 1.95% | 0.12% | 1.69 | 1,285,505,337 |
| `neutral_industry_soil` | 6,770 | 47.84% | 0.82% | -0.88% | 1.29 | 182,872,123 |
| `weak_industry_soil` | 8,435 | 44.05% | 0.51% | -1.49% | 1.18 | 75,548,135 |
| `unknown_industry_soil` | 13,888 | 51.38% | 1.44% | 0.23% | 1.47 | 824,413,487 |

AKShare 仍不能完全解决全样本行业土壤，剩余 unknown 来源：

| status | trades |
|---|---:|
| `missing_industry_membership` | 7,736 |
| `missing_industry_index_bar_before_signal_date` | 3,900 |
| `membership_level1_not_in_sw2014_classification` | 2,116 |
| `missing_components` | 136 |

BaoStock 结果：

- 本地安装后尝试登录和查询 `sh.801010`、`sh.801020`、`sh.801780`。
- 登录失败：`10002007 网络接收错误`。
- 当前不能作为可用证据源；后续如果网络环境允许，可再复测。

efinance / 东方财富接口结果：

- 本地安装 `efinance` 后尝试查询 `801010`、`801020`、`801780`、
  `801010.SI`、`sh801010`。
- 均未能识别为有效证券代码，且底层东方财富历史行情请求返回连接异常。
- 当前不能作为申万行业指数的可靠备选源。

JoinQuant / BigQuant / Choice / iFinD / Wind：

- JoinQuant/JQData 文档明确存在 `finance.SW1_DAILY_PRICE`，即申万一级行业日行情表，
  字段包括 `date、code、name、open、high、low、close、volume、money、change_pct`。
  文档还说明申万行业指数多数以 `1999-12-31` 为基日，并提供自基日开始的行情数据。
- BigQuant 文档明确存在 `cn_stock_industry_sw_bar1d` 表，字段包含申万一级行业指数的
  开盘、收盘、最高、最低、成交量、成交额等，可作为商业数据备选。
- Choice / iFinD / Wind 属于终端/API 型商业源，理论上适合补全，但需要账号权限后
  实测导出。

当前推荐：

- 行业 K 线优先切到 `SW2014_AKSHARE` 源，作为比 Tushare 覆盖更好的官方申万页面来源。
- 若仍要找第二来源交叉校验，优先试 JoinQuant/JQData 的 `finance.SW1_DAILY_PRICE`，
  因为它和当前缺口最匹配。
- 报告中必须标注来源为 `AKShare index_hist_sw / 申万宏源指数历史页面`，不能和
  Tushare `sw_daily` 混成同一个数据源。
- 若要继续压缩 unknown，下一步不是再找一级行业 K 线，而是处理 membership 缺失和
  2014 新一级行业上市前的历史归属问题。
