# Time Sample Stability Check

This document records the first time-sample expansion after the current
backtest baseline. It validates environment-fit stability only; it is not a
strategy approval or a tuning decision.

## Experiment Boundary

| Field | Value |
|---|---|
| Baseline run | `tushare-expanded-add-on-2023-2024` |
| Expanded run | `tushare-expanded-add-on-2019-2024-sample-stability` |
| Config | `examples/run-tushare-expanded-add-on-2019-2024-sample-stability.yaml` |
| Changed variable | Time range only |
| Baseline range | `2023-01-01` to `2024-12-31` |
| Expanded range | `2019-01-04` to `2024-12-31` |
| Symbol pool | unchanged, 10 symbols |
| Strategy and execution rules | unchanged |
| Evidence validation | `ok`, errors `0`, warnings `0` |

## Result Comparison

| Metric | Baseline | Expanded |
|---|---:|---:|
| Final equity | `985642.2497650513` | `1045020.5506013487` |
| Cumulative return | `-0.014357750234948674` | `0.0450205506013488` |
| Max drawdown | `0.1886705986935961` | `0.42242134894640376` |
| Closed trades | `129` | `385` |
| Win rate | `0.4418604651162791` | `0.45714285714285713` |
| Add-on signals | `4` | `45` |
| Execution rejections | `0` | `6` |

The expanded run improved cumulative return but also exposed a much larger
drawdown. This keeps the framework direction in review mode, not tuning mode.

## Environment-Fit Result

The net-PnL best environment stayed stable:

| Criterion | Baseline | Expanded | Status |
|---|---|---|---|
| Net PnL highest | `行业 KDJ J 低于阈值=是` | `行业 KDJ J 低于阈值=是` | stable lead |

The supporting sample count increased from `79` to `233`.

The return-on-entry-value best combination changed:

| Criterion | Baseline | Expanded | Status |
|---|---|---|---|
| Return on entry value highest | `行业 KDJ低位 + 沪深300多头 + 个股均线多头 + 价格在 MA25/MA60 上方` | `行业 KDJ低位 + 沪深300非多头 + 个股均线非多头 + 价格在 MA25 上方 + 价格不在 MA60 上方` | changed |

That means the broad environment clue is stable, but the narrower combination
is not stable enough to become a rule.

## Review Artifacts

```text
reports/tushare-expanded-add-on-2019-2024-sample-stability/report.zh.md
reports/tushare-expanded-add-on-2019-2024-sample-stability/run_data_overview.zh.md
reports/tushare-expanded-add-on-2019-2024-sample-stability/review_brief.all.zh.md
reports/tushare-expanded-add-on-2019-2024-sample-stability/ai_review_result.all.zh.md
reports/tushare-expanded-add-on-2019-2024-sample-stability/environment-stability-check/run_data_drilldown_batch.zh.md
reports/environment-fit-comparison-tushare-expanded-add-on-2023-2024__vs__tushare-expanded-add-on-2019-2024-sample-stability/environment_fit_comparison.zh.md
reports/comparison-tushare-expanded-add-on-2023-2024__vs__tushare-expanded-add-on-2019-2024-sample-stability/comparison.zh.md
```

## Current Judgement

- `行业 KDJ J 低于阈值=是` is now a stronger environment-fit lead because it
  stayed the net-PnL best environment after time expansion.
- The bullish MA/HS300 combination is not stable across the time expansion.
- The strategy still has a major drawdown problem in the longer sample, so the
  next step should validate market-type behavior before turning any finding
  into a strategy rule.
