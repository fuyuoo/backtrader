# Baoma V1 Market Stage Attribution

本文档记录 Baoma V1 第一版市场阶段归因接入结果。它是报告层归因，不改变策略、
不重跑交易规则。

## Scope

市场阶段字段来自指数日线快照：

- `bullish`: `close > ma20 > ma60`
- `bearish`: `close < ma20 < ma60`
- `mixed`: 其他情况

第一版同时计算沪深300和中证500：

| field | meaning | timing | default environment_fit |
|---|---|---|---|
| `market.hs300.entry_stage` | 沪深300入场信号日市场阶段 | entry | no |
| `market.hs300.exit_stage` | 沪深300出场日市场阶段 | exit | no |
| `market.hs300.entry_to_exit_stage` | 沪深300入场到出场市场阶段迁移 | post_trade | no |
| `market.csi500.entry_stage` | 中证500入场信号日市场阶段 | entry | no |
| `market.csi500.exit_stage` | 中证500出场日市场阶段 | exit | no |
| `market.csi500.entry_to_exit_stage` | 中证500入场到出场市场阶段迁移 | post_trade | no |

注意：`entry_stage` 使用入场信号日，不是成交日；`exit_stage` 和
`entry_to_exit_stage` 是事后诊断字段，不能作为默认入场筛选因子。

## Generated Artifacts

### 2015-2024

| artifact | path |
|---|---|
| market stage fit json | `reports/baoma-v1-fixed-sample-2015-2024-maxhold800/market_stage_environment_fit_review/environment_fit.enriched.json` |
| market stage fit zh | `reports/baoma-v1-fixed-sample-2015-2024-maxhold800/market_stage_environment_fit_review/environment_fit.enriched.zh.md` |

### 2023-2024

| artifact | path |
|---|---|
| market stage fit json | `reports/baoma-v1-fixed-sample-2023-2024-maxhold800/market_stage_environment_fit_review/environment_fit.enriched.json` |
| market stage fit zh | `reports/baoma-v1-fixed-sample-2023-2024-maxhold800/market_stage_environment_fit_review/environment_fit.enriched.zh.md` |

### Comparison

| artifact | path |
|---|---|
| market stage comparison json | `reports/environment-fit-comparison-baoma-v1-market-stage-2023-2024-maxhold800__vs__2015-2024-maxhold800/environment_fit_comparison.json` |
| market stage comparison zh | `reports/environment-fit-comparison-baoma-v1-market-stage-2023-2024-maxhold800__vs__2015-2024-maxhold800/environment_fit_comparison.zh.md` |

## First Read

### 2023-2024

- sample_count: `4610`
- overall win_rate: `45.70%`
- overall average_return_pct: `0.85%`
- overall net_pnl: `155,837,965`
- overall return_on_entry_value: `0.50%`
- 净利润最高：`中证500出场日市场阶段=mixed`，样本 `1850`，胜率 `53.14%`，平均收益 `2.28%`，净 PnL `245,865,249`。
- 资金收益率最高：`中证500入场到出场市场阶段迁移=bearish_to_bullish`，样本 `102`，胜率 `97.06%`，平均收益 `10.39%`，入场资金收益率 `9.91%`。

### 2015-2024

- sample_count: `18349`
- overall win_rate: `48.32%`
- overall average_return_pct: `1.50%`
- overall net_pnl: `1,285,797,727`
- overall return_on_entry_value: `1.10%`
- 净利润最高：`中证500出场日市场阶段=bullish`，样本 `4231`，胜率 `60.13%`，平均收益 `4.05%`，净 PnL `961,441,091`。
- 资金收益率最高：`中证500入场到出场市场阶段迁移=bearish_to_bullish`，样本 `316`，胜率 `90.51%`，平均收益 `9.31%`，入场资金收益率 `9.18%`。

## Stability Notes

- 净利润最高环境在 2 年和 10 年之间发生变化：2 年是中证500出场阶段 `mixed`，10 年是中证500出场阶段 `bullish`。
- 资金收益率最高环境稳定：两段样本都是中证500 `bearish_to_bullish`。
- 这说明“熊转牛/熊转震荡”的持仓期阶段迁移对收益解释很强，但它含有出场信息，只能用于复盘和后续实验设计，不能直接作为入场筛选。
- 出场日为 `bearish` 的分组在 10 年样本中明显拖累净 PnL，中证500出场阶段 `bearish` 净 PnL 为 `-460,278,502`。

## Rebuild Commands

```powershell
python -m attbacktrader.cli.attribution_wide_samples --run-dir reports/baoma-v1-fixed-sample-2015-2024-maxhold800 --reference-snapshot data\snapshots\attribution_reference\full_a_main_chinext_star\2015-01-01_2024-12-31_baoma-v1-maxhold800-entry-scope-full-a-industry-backfilled --daily-price-cache-dir data/snapshots/tushare_reference_raw/full_a_main_chinext_star/2015-01-01_2024-12-31_baoma-v1-maxhold800-entry-scope-full-a-industry-backfilled --snapshot-root data/snapshots --industry-source SW2021 --output-dir reports/baoma-v1-fixed-sample-2015-2024-maxhold800/full_entry_scope_environment_fit_review
python -m attbacktrader.cli.attribution_wide_samples --run-dir reports/baoma-v1-fixed-sample-2023-2024-maxhold800 --reference-snapshot data\snapshots\attribution_reference\full_a_main_chinext_star\2022-08-26_2024-12-31_baoma-v1-maxhold800-entry-scope-full-a-industry-backfilled --daily-price-cache-dir data\snapshots\daily_bars\qfq --snapshot-root data/snapshots --industry-source SW2021 --output-dir reports/baoma-v1-fixed-sample-2023-2024-maxhold800/full_entry_scope_environment_fit_review
```

```powershell
python -m attbacktrader.cli.environment_fit --wide-samples reports/baoma-v1-fixed-sample-2015-2024-maxhold800/full_entry_scope_environment_fit_review --field-index reports/baoma-v1-fixed-sample-2015-2024-maxhold800/full_entry_scope_environment_fit_review --replace-default-fields --field market.hs300.entry_stage --field market.hs300.exit_stage --field market.hs300.entry_to_exit_stage --field market.csi500.entry_stage --field market.csi500.exit_stage --field market.csi500.entry_to_exit_stage --pair market.hs300.entry_stage,market.hs300.exit_stage --pair market.hs300.entry_stage,market.hs300.entry_to_exit_stage --pair market.csi500.entry_stage,market.csi500.exit_stage --pair market.csi500.entry_stage,market.csi500.entry_to_exit_stage --min-sample-count 10 --output-dir reports/baoma-v1-fixed-sample-2015-2024-maxhold800/market_stage_environment_fit_review
python -m attbacktrader.cli.environment_fit --wide-samples reports/baoma-v1-fixed-sample-2023-2024-maxhold800/full_entry_scope_environment_fit_review --field-index reports/baoma-v1-fixed-sample-2023-2024-maxhold800/full_entry_scope_environment_fit_review --replace-default-fields --field market.hs300.entry_stage --field market.hs300.exit_stage --field market.hs300.entry_to_exit_stage --field market.csi500.entry_stage --field market.csi500.exit_stage --field market.csi500.entry_to_exit_stage --pair market.hs300.entry_stage,market.hs300.exit_stage --pair market.hs300.entry_stage,market.hs300.entry_to_exit_stage --pair market.csi500.entry_stage,market.csi500.exit_stage --pair market.csi500.entry_stage,market.csi500.entry_to_exit_stage --min-sample-count 10 --output-dir reports/baoma-v1-fixed-sample-2023-2024-maxhold800/market_stage_environment_fit_review
python -m attbacktrader.cli.compare_environment_fit --environment-fit reports/baoma-v1-fixed-sample-2023-2024-maxhold800/market_stage_environment_fit_review/environment_fit.enriched.json --environment-fit reports/baoma-v1-fixed-sample-2015-2024-maxhold800/market_stage_environment_fit_review/environment_fit.enriched.json --common-limit 50 --sample-ref-limit 5 --output-dir reports/environment-fit-comparison-baoma-v1-market-stage-2023-2024-maxhold800__vs__2015-2024-maxhold800
```
