# Baoma v1 土壤数据补齐 Runbook

本文记录 2026-07-05 这轮为了压低 `unknown_soil` 做过的数据补齐内容，以及重新生成报告或拆分回测时必须保留的口径。

核心结论：

- 旧默认链路会退回 `SW2014` / `SW2014_AKSHARE` 和 2006 起始指数文件，早期样本会重新出现 `unknown_soil`。
- 补齐后的 combined 报告使用了指数 warm-up、申万行业历史混合源、行业指数 warm-up stitch、最早成分回填四层补齐。
- 数据准备阶段可以联网拉取 AKShare；正式回测和报告复算必须只使用本地离线快照，不能边回测边联网补数据。

## 当前状态快照

截至 2026-07-05 检查：

| 产物 | 路径 | 关键状态 |
| --- | --- | --- |
| combined 含行业土壤报告 | `reports/soil-with-industry-v1-baoma-v1-dynamic-hs300-csi500-2006-2025/` | `closed_trade_count = 42,909`，`soil_with_industry_unknown_count = 0` |
| combined no-industry soil v2 warm-up 版 | `reports/score-year-seed-soil-v2-index-warmup-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/` | `soil_v2_unknown_count = 0` |
| combined 最终行业 time-soil map | `reports/industry-sw-akshare-historical-mixed-warmup-stitch-index-warmup-earliest-membership-backfill-experimental-time-soil-map-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/` | 行业映射、分类、行业土壤均 `42,909 / 42,909 matched` |
| 当前 HS300-only 含行业报告 | `reports/soil-with-industry-v1-baoma-v1-dynamic-hs300-only-2006-2025/` | 当前仍有 `soil_with_industry_unknown_count = 5,188`，因为 source 指回旧行业 map |
| 当前 HS300-only no-industry soil v2 | `reports/score-year-seed-soil-v2-matrix-baoma-v1-dynamic-hs300-only-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/` | 当前仍有 `soil_v2_unknown_count = 148`，说明 HS300-only 也需要指数 warm-up 版 v2 |

所以，重新回测或重新生成 HS300-only 报告时，不能只跑最后的 HTML 生成。至少要先恢复：

1. no-industry soil v2 的指数 warm-up 输入。
2. 行业 map 的最终申万补齐源。
3. `soil-with-industry-v1` 的 source dir，不能走脚本默认值。

## 补过哪些数据

### 1. 指数 warm-up 快照

补齐目标是让早期交易信号也能计算指数土壤组件，尤其是 MA120/MA250、周 KDJ、日 MACD 等需要历史窗口的指标。

最终快照：

- `data/snapshots/indexes/000300_SH_20050101_20251231_warmup.parquet`
- `data/snapshots/indexes/000905_SH_20050101_20251231_warmup.parquet`

生成脚本：

- `reports/score-year-seed-soil-v2-matrix-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/_build_index_warmup_snapshots_2005_2025.py`

这个脚本只拼接已有本地指数快照，不联网：

- `000300_SH_20050101_20141231.parquet`
- `000300_SH_20150101_20251231.parquet`
- `000905_SH_20050101_20141231.parquet`
- `000905_SH_20150101_20251231.parquet`

### 2. AKShare/申万行业历史源

BigQuant SDK 权限申请不下来后，补齐路线改为 AKShare + 本地申万快照。

相关快照目录：

- `data/snapshots/industries/sw/SW2014_AKSHARE_MEMBERSHIP_STRICT/`
- `data/snapshots/industries/sw/SW2014_AKSHARE_MEMBERSHIP_BACKMAP_EXPERIMENTAL/`
- `data/snapshots/industries/sw/SW_AKSHARE_HISTORICAL_MIXED_EXPERIMENTAL/`
- `data/snapshots/industries/sw/SW_AKSHARE_HISTORICAL_MIXED_WARMUP_STITCH_EXPERIMENTAL/`
- `data/snapshots/industries/sw/SW_AKSHARE_HISTORICAL_MIXED_WARMUP_STITCH_EARLIEST_MEMBERSHIP_BACKFILL_EXPERIMENTAL/`

最终使用的是最后一个：

`data/snapshots/industries/sw/SW_AKSHARE_HISTORICAL_MIXED_WARMUP_STITCH_EARLIEST_MEMBERSHIP_BACKFILL_EXPERIMENTAL/`

它下面必须至少有：

- `classifications.parquet`
- `memberships/`
- `index_bars/`

### 3. 行业指数 warm-up stitch

目的：有些新申万一级行业指数起始时间晚，直接用官方起始日会导致早期行业土壤缺指标。这里用明确记录的 proxy 旧行业指数补早期 warm-up，只用于指标预热，不覆盖目标行业官方指数起始后的真实 bar。

生成脚本：

- `reports/industry-sw2014-time-soil-map-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/_build_sw_historical_mixed_warmup_stitch_experimental.py`

重要边界：

- 这是实验性 warm-up 源。
- proxy 选择写在脚本和 metadata 里，后续要做敏感性检查。
- 不能把它当成无条件的官方行业历史真值。

### 4. 最早成分回填

最后只剩一个 pre-first-membership gap，用第一条已知同股票成分关系向前回填到信号日。

生成脚本：

- `reports/industry-sw2014-time-soil-map-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/_build_sw_warmup_stitch_earliest_membership_backfill_experimental.py`

metadata 记录的唯一回填：

| symbol | 原始最早 in_date | 回填到 | 行业 |
| --- | --- | --- | --- |
| `000926.SZ` | `2007-07-02` | `2007-03-16` | 钢铁，`801040.SI` |

重要边界：

- 这是为了最终覆盖率的实验性回填。
- 它假设第一条已知行业在更早信号日已经有效，证据强度弱于严格成分记录。
- 后续正式研究应该保留 strict 源和 backfill 源的敏感性对照。

## 为什么重新生成会丢数据

几个报告脚本目前还是 report-local 临时脚本，默认值偏旧：

| 脚本 | 如果不设环境变量，会退回 |
| --- | --- |
| `_build_score_year_seed_soil_v2_matrix.py` | `000300_SH_20060101_20251231.parquet` 和 `000905_SH_20060101_20251231.parquet`，早期缺 warm-up |
| `_build_industry_sw2014_time_soil_map.py` | `ATT_INDUSTRY_SOURCE=SW2014`，`ATT_INDUSTRY_INDEX_SOURCE=SW2014` |
| `_build_soil_with_industry_v1.py` | 默认 source dir 是旧的 `industry-sw2014-akshare...` 口径 |

这就是 HS300-only 重新生成后又出现 `unknown_soil` 的主要原因。当前检查到：

- HS300-only no-industry soil v2 还有 `148` 个 unknown。
- HS300-only 行业 map 使用旧源：`industry_source_requested = SW2014`，`industry_index_source = SW2014_AKSHARE`。
- HS300-only 含行业土壤报告最终还有 `5,188` 个 unknown。

## combined 补齐链路的恢复顺序

先检查关键文件是否存在：

```powershell
Test-Path data/snapshots/indexes/000300_SH_20050101_20251231_warmup.parquet
Test-Path data/snapshots/indexes/000905_SH_20050101_20251231_warmup.parquet
Test-Path data/snapshots/industries/sw/SW_AKSHARE_HISTORICAL_MIXED_WARMUP_STITCH_EARLIEST_MEMBERSHIP_BACKFILL_EXPERIMENTAL/classifications.parquet
Test-Path data/snapshots/industries/sw/SW_AKSHARE_HISTORICAL_MIXED_WARMUP_STITCH_EARLIEST_MEMBERSHIP_BACKFILL_EXPERIMENTAL/memberships
Test-Path data/snapshots/industries/sw/SW_AKSHARE_HISTORICAL_MIXED_WARMUP_STITCH_EARLIEST_MEMBERSHIP_BACKFILL_EXPERIMENTAL/index_bars
```

如果指数 warm-up 丢了，先重建：

```powershell
python reports/score-year-seed-soil-v2-matrix-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/_build_index_warmup_snapshots_2005_2025.py
```

然后用 warm-up 指数重建 no-industry soil v2：

```powershell
$env:ATT_HS300_INDEX_BARS = "data/snapshots/indexes/000300_SH_20050101_20251231_warmup.parquet"
$env:ATT_CSI500_INDEX_BARS = "data/snapshots/indexes/000905_SH_20050101_20251231_warmup.parquet"
$env:ATT_SOIL_V2_OUT_DIR = "reports/score-year-seed-soil-v2-index-warmup-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols"
python reports/score-year-seed-soil-v2-matrix-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/_build_score_year_seed_soil_v2_matrix.py
```

再用最终行业源重建 industry time-soil map：

```powershell
$env:ATT_INDUSTRY_SOURCE = "SW_AKSHARE_HISTORICAL_MIXED_WARMUP_STITCH_EARLIEST_MEMBERSHIP_BACKFILL_EXPERIMENTAL"
$env:ATT_INDUSTRY_INDEX_SOURCE = "SW_AKSHARE_HISTORICAL_MIXED_WARMUP_STITCH_EARLIEST_MEMBERSHIP_BACKFILL_EXPERIMENTAL"
$env:ATT_INDUSTRY_MAP_SOURCE_ROWS = "reports/score-year-seed-soil-v2-index-warmup-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/scored_trade_rows_soil_v2.parquet"
$env:ATT_INDUSTRY_MAP_OUT_DIR = "reports/industry-sw-akshare-historical-mixed-warmup-stitch-index-warmup-earliest-membership-backfill-experimental-time-soil-map-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols"
python reports/industry-sw2014-time-soil-map-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/_build_industry_sw2014_time_soil_map.py
```

最后重建含行业土壤报告和 HTML：

```powershell
$env:ATT_SOIL_WITH_INDUSTRY_SOURCE_DIR = "reports/industry-sw-akshare-historical-mixed-warmup-stitch-index-warmup-earliest-membership-backfill-experimental-time-soil-map-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols"
$env:ATT_SOIL_WITH_INDUSTRY_OUT_DIR = "reports/soil-with-industry-v1-baoma-v1-dynamic-hs300-csi500-2006-2025"
python reports/soil-with-industry-v1-baoma-v1-dynamic-hs300-csi500-2006-2025/_build_soil_with_industry_v1.py

$env:ATT_YEAR_SCORE_VIEW_REPORT_DIR = "reports/soil-with-industry-v1-baoma-v1-dynamic-hs300-csi500-2006-2025"
python reports/soil-with-industry-v1-baoma-v1-dynamic-hs300-csi500-2006-2025/_build_year_score_soil_seed_hs300_views.py

$env:ATT_INTERACTIVE_VIEW_REPORT_DIR = "reports/soil-with-industry-v1-baoma-v1-dynamic-hs300-csi500-2006-2025"
python reports/soil-with-industry-v1-baoma-v1-dynamic-hs300-csi500-2006-2025/_build_interactive_year_score_view.py
```

验收：

```powershell
$m = Get-Content reports/soil-with-industry-v1-baoma-v1-dynamic-hs300-csi500-2006-2025/metadata.json -Raw | ConvertFrom-Json
$m.closed_trade_count
$m.soil_with_industry_unknown_count
$m.source_rows

$im = Get-Content reports/industry-sw-akshare-historical-mixed-warmup-stitch-index-warmup-earliest-membership-backfill-experimental-time-soil-map-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/metadata.json -Raw | ConvertFrom-Json
$im.industry_mapping_status_counts
$im.industry_soil_status_counts
```

combined 合格标准：

- `closed_trade_count = 42909`
- `soil_with_industry_unknown_count = 0`
- industry map 的 `industry_mapping_status_counts` 全部为 `matched: 42909`
- industry map 的 `industry_soil_status_counts` 全部为 `matched: 42909`
- `metadata.source_rows` 指向带 `earliest-membership-backfill-experimental` 的行业 map，而不是旧 `industry-sw2014-akshare...`

## HS300-only 恢复口径

HS300-only 不是简单把 combined 报告过滤一下。它有两个不同层次：

- `index_specific_soil_split`：基于 combined 交易样本做 post-run 拆分和重新看分，不是独立回测。
- HS300-only 回测：只用沪深300动态股票池重新跑策略，再单独做 soil v2、行业 map、含行业土壤报告。

如果要恢复当前 HS300-only 报告的土壤覆盖，建议先按下面顺序做。

### 1. 生成 HS300-only 的 warm-up no-industry soil v2

```powershell
$env:ATT_SOIL_V2_V1_DIR = "reports/score-year-seed-soil-matrix-baoma-v1-dynamic-hs300-only-2006-2025-strict-t1-no-industry-attribution-normalized-symbols"
$env:ATT_SOIL_V2_OUT_DIR = "reports/score-year-seed-soil-v2-index-warmup-baoma-v1-dynamic-hs300-only-2006-2025-strict-t1-no-industry-attribution-normalized-symbols"
$env:ATT_HS300_INDEX_BARS = "data/snapshots/indexes/000300_SH_20050101_20251231_warmup.parquet"
$env:ATT_CSI500_INDEX_BARS = "data/snapshots/indexes/000905_SH_20050101_20251231_warmup.parquet"
python reports/score-year-seed-soil-v2-matrix-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/_build_score_year_seed_soil_v2_matrix.py
```

注意：这个脚本目前是从 combined 报告目录复制出来的临时脚本，脚本内部 `RUN_ID` 仍是 combined 常量。用于恢复数据时可以通过环境变量换输入和输出，但正式化前应把 `RUN_ID` 参数化，避免 metadata 误导。

验收：

```powershell
$m = Get-Content reports/score-year-seed-soil-v2-index-warmup-baoma-v1-dynamic-hs300-only-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/metadata.json -Raw | ConvertFrom-Json
$m.soil_v2_unknown_count
$m.index_sources
```

### 2. 用最终申万源生成 HS300-only industry map

```powershell
$env:ATT_INDUSTRY_SOURCE = "SW_AKSHARE_HISTORICAL_MIXED_WARMUP_STITCH_EARLIEST_MEMBERSHIP_BACKFILL_EXPERIMENTAL"
$env:ATT_INDUSTRY_INDEX_SOURCE = "SW_AKSHARE_HISTORICAL_MIXED_WARMUP_STITCH_EARLIEST_MEMBERSHIP_BACKFILL_EXPERIMENTAL"
$env:ATT_INDUSTRY_MAP_SOURCE_ROWS = "reports/score-year-seed-soil-v2-index-warmup-baoma-v1-dynamic-hs300-only-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/scored_trade_rows_soil_v2.parquet"
$env:ATT_INDUSTRY_MAP_OUT_DIR = "reports/industry-sw-akshare-historical-mixed-warmup-stitch-index-warmup-earliest-membership-backfill-experimental-time-soil-map-baoma-v1-dynamic-hs300-only-2006-2025-strict-t1-no-industry-attribution-normalized-symbols"
python reports/industry-sw2014-time-soil-map-baoma-v1-dynamic-hs300-csi500-2006-2025-strict-t1-no-industry-attribution-normalized-symbols/_build_industry_sw2014_time_soil_map.py
```

注意：这个脚本内部 `RUN_ID` 也仍是 combined 常量。正式化前同样应该参数化。

### 3. 重建 HS300-only 含行业土壤报告

```powershell
$env:ATT_SOIL_WITH_INDUSTRY_SOURCE_DIR = "reports/industry-sw-akshare-historical-mixed-warmup-stitch-index-warmup-earliest-membership-backfill-experimental-time-soil-map-baoma-v1-dynamic-hs300-only-2006-2025-strict-t1-no-industry-attribution-normalized-symbols"
$env:ATT_SOIL_WITH_INDUSTRY_OUT_DIR = "reports/soil-with-industry-v1-baoma-v1-dynamic-hs300-only-2006-2025"
python reports/soil-with-industry-v1-baoma-v1-dynamic-hs300-csi500-2006-2025/_build_soil_with_industry_v1.py

$env:ATT_YEAR_SCORE_VIEW_REPORT_DIR = "reports/soil-with-industry-v1-baoma-v1-dynamic-hs300-only-2006-2025"
python reports/soil-with-industry-v1-baoma-v1-dynamic-hs300-csi500-2006-2025/_build_year_score_soil_seed_hs300_views.py

$env:ATT_INTERACTIVE_VIEW_REPORT_DIR = "reports/soil-with-industry-v1-baoma-v1-dynamic-hs300-only-2006-2025"
python reports/soil-with-industry-v1-baoma-v1-dynamic-hs300-csi500-2006-2025/_build_interactive_year_score_view.py
```

验收：

```powershell
$m = Get-Content reports/soil-with-industry-v1-baoma-v1-dynamic-hs300-only-2006-2025/metadata.json -Raw | ConvertFrom-Json
$m.closed_trade_count
$m.soil_with_industry_unknown_count
$m.source_rows
```

合格标准：

- `source_rows` 必须指向带 `earliest-membership-backfill-experimental` 的 HS300-only industry map。
- `soil_with_industry_unknown_count` 应显著低于当前旧口径的 `5,188`。
- 如果仍不是 0，要先看 no-industry soil v2 是否还有 unknown，再看 industry map 的 `industry_mapping_status_counts` 和 `industry_soil_status_counts`，不要直接改报告层隐藏 unknown。

## 禁区和后续改造

禁区：

- 不要在正式回测期间联网补数据。
- 不要让策略、引擎、报告生成脚本直接调用 AKShare。
- 不要把报告层的 post-run 归因当成真实组合回测收益证据。
- 不要把 `earliest_membership_backfill` 当成严格官方成分数据；它只是覆盖率实验。
- 不要只看 HTML 页面文字判断是否补齐，必须看 `metadata.json` 和 map 状态计数。

建议后续改造：

1. 把这些 report-local 脚本沉淀成正式 CLI 或 runner，`RUN_ID`、输入目录、输出目录、行业源、指数源全部参数化。
2. 给数据准备阶段增加 preflight：指数 warm-up、行业 membership、行业 index bars、soil v2 unknown、industry map unknown 必须逐项检查。
3. 保留三套研究口径：strict、warm-up stitch、earliest membership backfill。最终实战回测前要看结论是否对这些口径敏感。
