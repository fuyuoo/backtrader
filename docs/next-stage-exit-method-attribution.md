# Next Stage: Exit Method Attribution

本文档定义 Strategy Adaptation V1 封板后的下一阶段。方向是退出方法归因，
不是继续做策略优化、调参或市场类型识别。

## Goal

解释已知市场类型中退出方法的行为差异，优先回答：

> 为什么 `ma_macd_weakening_exit` 在牛市变体里过快退出，并导致快速重入和盈利被切薄？

本阶段的输出应该让 AI 能从已落盘证据中判断一个退出方法的问题来自：

- 触发条件太敏感；
- 触发条件组合顺序不合理；
- 退出后同标的快速重入；
- 退出后卖飞；
- 某些市场类型或行业下退出证据不稳定。

## Starting Baseline

从以下封板基线开始：

```text
docs/strategy-adaptation-v1-closure.md
examples/strategy-adaptation-v1-baseline.json
reports/strategy-variant-attribution-tushare-market-type-add-on-bull/strategy_variant_attribution.json
```

当前已知问题：

```text
market_type_id: bull_market
variant: bull_market_let_winners_run
changed_method: profit_taking_method = ma_macd_weakening_exit
trade_count: 88 -> 262
average_holding_days: 24.35 -> 4.06
short_reentry_count_5d: 15 -> 132
average_win: 10.41% -> 2.55%
```

## Data Flow

本阶段仍然使用下游反查，不重跑策略方法：

```text
paired baseline/variant run artifacts
  -> trade_lifecycle.json
  -> exit events
  -> exit method / reason / checks / values
  -> post_exit_analysis.json
  -> same-symbol re-entry samples
  -> exit-method attribution report
```

If exit events do not contain enough checks or values, the first implementation
task is to improve decision-time exit evidence capture upstream. Do not fill the
missing evidence in reports.

## In Scope

- Read existing `trade_lifecycle.json` and `post_exit_analysis.json`.
- Group completed trades by `exit_method_name`, `exit_reason`, exit checks, and
  selected exit values when present.
- Compare baseline and variant exit behavior within the same `segment_id`.
- Report holding-period compression, average-win compression, stop-loss rate,
  sold-too-early rate, and same-symbol re-entry density by exit method.
- Emit sample refs using `run_id + trade_index`.
- Produce Chinese Markdown for AI review.

## Out Of Scope

- Automatic parameter tuning.
- Automatic market-type detection.
- Automatic strategy switching.
- Changing `ma_macd_weakening_exit` logic before evidence is inspected.
- Adding new indicators just to explain the current report.
- Treating missing exit evidence as false, neutral, or zero.
- Proving live-trading suitability.

## Acceptance Criteria

The next stage is ready when:

- AI can read one exit-method attribution artifact and explain why the bull
  variant exited too quickly.
- The report shows which exit method caused holding compression and fast
  re-entry.
- The report includes at least capped sample refs for the most important fast
  re-entry and sold-too-early examples.
- Missing exit evidence is counted explicitly.
- The current V1 baseline remains unchanged and can still be compared against
  future variants.

## First Implementation Slice

Recommended first slice:

```text
att-exit-method-attribution
  --baseline-manifest examples\generated-market-segment-runs\tushare-market-type-add-on\market_segment_run_manifest.json
  --variant-manifest examples\generated-strategy-variant-runs\tushare-market-type-add-on\strategy_variant_run_manifest.json
  --market-type-id bull_market
```

Expected output:

```text
exit_method_attribution.json
exit_method_attribution.zh.md
```

This command should explain the current bull-market `ma_macd_weakening_exit`
failure before any new strategy variant is generated.

## Later Candidates

After the first slice is complete:

- Bear-market variant attribution can verify whether improvement came from
  lower exposure, disabled add-on, or fewer trades.
- A candidate exit-method variant can be drafted only after exit evidence shows
  a specific failure mode.
- Strategy switching rules remain out of scope until at least one exit-method
  candidate passes the V1 baseline comparison.
