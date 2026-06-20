# Next Stage: Exit Method Attribution

Status: designed but deferred. This is not the current main line after the
workbench-level zoom-out. Keep this document as a future analysis contract, but
do not implement it before the Backtest Workbench system closure work resumes.

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

## Minimal Artifact Contract

The first implementation artifact is:

```text
exit_method_attribution.json
exit_method_attribution.zh.md
```

The JSON schema name should be:

```text
attbacktrader.exit_method_attribution.v1
```

The artifact explains exit behavior for one manually known market type and one
baseline-vs-variant manifest pair. It is a downstream attribution artifact. It
does not calculate indicators, rerun a strategy, fetch data, or decide strategy
switching rules.

The initial missing-evidence audit is recorded in:

```text
docs/exit-method-attribution-missing-evidence-check.md
```

That audit found enough existing `ma_macd_weakening_exit` MA/MACD component
evidence to start the first implementation slice without upstream evidence
capture.

### Required Inputs

The command must read:

- baseline segment manifest, such as
  `examples/generated-market-segment-runs/tushare-market-type-add-on/market_segment_run_manifest.json`;
- variant segment manifest, such as
  `examples/generated-strategy-variant-runs/tushare-market-type-add-on/strategy_variant_run_manifest.json`;
- `market_type_id`, initially `bull_market`;
- each selected segment's `trade_lifecycle.json`;
- each selected segment's `post_exit_analysis.json` when present;
- each selected segment's `trade_review.json` when present;
- each selected segment's `report.json` for trade-quality metrics only;
- optionally `strategy_variant_attribution.json` as prior-stage summary context.

The command must not require `reports/strategy-variant-attribution-...` to exist,
because this artifact should be able to explain exit methods directly from the
paired run artifacts.

### Top-Level Shape

Recommended minimal JSON shape:

```json
{
  "schema": "attbacktrader.exit_method_attribution.v1",
  "market_type_id": "bull_market",
  "baseline_manifest_path": "string",
  "variant_manifest_path": "string",
  "selected_exit_method": "ma_macd_weakening_exit",
  "selected_variant_id": "bull_market_let_winners_run",
  "short_reentry_days": 5,
  "post_exit_window_days": [3, 5, 10, 20],
  "evidence_sources": [],
  "overview": {},
  "paired_segments": [],
  "exit_method_groups": [],
  "trigger_component_groups": [],
  "samples": {},
  "missing_evidence": {},
  "conclusion_candidates_zh": [],
  "rules": []
}
```

### Overview Fields

`overview` should answer whether the selected exit method is the likely source
of the behavior change:

```json
{
  "baseline_run_count": 3,
  "variant_run_count": 3,
  "paired_segment_count": 3,
  "baseline_primary_exit_method": "kdj_overheated_exit",
  "variant_primary_exit_method": "ma_macd_weakening_exit",
  "baseline_trade_count": 88,
  "variant_trade_count": 262,
  "baseline_average_holding_days": 24.35,
  "variant_average_holding_days": 4.06,
  "baseline_short_reentry_count": 15,
  "variant_short_reentry_count": 132,
  "baseline_average_win": 0.1041,
  "variant_average_win": 0.0255
}
```

Numbers may be `null` when the source artifact does not provide them. Missing
values must stay missing; do not substitute `0`.

### Paired Segment Rows

`paired_segments[]` should preserve segment-level traceability:

```json
{
  "segment_id": "2014_2015_bull_market",
  "market_type_id": "bull_market",
  "baseline_run_id": "string",
  "variant_run_id": "string",
  "baseline": {
    "trade_count": 0,
    "average_holding_days": null,
    "exit_method_counts": []
  },
  "variant": {
    "trade_count": 0,
    "average_holding_days": null,
    "exit_method_counts": []
  },
  "delta": {
    "trade_count": 0,
    "average_holding_days": null,
    "short_reentry_count": 0,
    "average_win": null
  },
  "sample_refs": []
}
```

This row exists so AI can drill from a portfolio-level claim back to one known
market segment without guessing which run produced the evidence.

### Exit Method Groups

`exit_method_groups[]` is the main summary table. It groups completed trades by
exit method and reason, separately for baseline and variant:

```json
{
  "run_side": "variant",
  "exit_method_name": "ma_macd_weakening_exit",
  "exit_reason": "MA_MACD_WEAKENING_EXIT",
  "trade_count": 0,
  "win_count": 0,
  "loss_count": 0,
  "average_return_pct": null,
  "average_win": null,
  "average_loss": null,
  "average_holding_days": null,
  "median_holding_days": null,
  "sold_too_early_count": 0,
  "sold_too_early_rate": null,
  "short_reentry_count": 0,
  "short_reentry_rate": null,
  "missing_exit_evidence_count": 0,
  "sample_refs": []
}
```

`short_reentry_rate` uses the group's own `trade_count` as denominator when
available. If `trade_count` is zero or missing, the rate must be `null`.

### Trigger Component Groups

`trigger_component_groups[]` is the first slice that directly targets
`ma_macd_weakening_exit`. It should split the selected method by exit-day
decision evidence already present in the matched exit intent:

```json
{
  "exit_method_name": "ma_macd_weakening_exit",
  "component_key": "symbol.macd.weakening",
  "component_type": "check",
  "component_value": true,
  "sample_count": 0,
  "average_holding_days": null,
  "average_return_pct": null,
  "sold_too_early_rate": null,
  "short_reentry_count": 0,
  "sample_refs": []
}
```

The first implementation may group every available exit check/category from
`exit_checks` and `exit_categories`. It should not invent MA/MACD component
names when the evidence is missing. If `ma_macd_weakening_exit` only records a
coarse reason code today, the artifact must report that as missing component
evidence instead of claiming which sub-condition fired.

### Samples

The artifact should cap but preserve representative samples:

```json
{
  "fast_reentry_samples": [
    {
      "run_side": "variant",
      "run_id": "string",
      "trade_index": 15,
      "symbol": "000001.SZ",
      "exit_date": "2015-01-01",
      "exit_method_name": "ma_macd_weakening_exit",
      "reentry_trade_index": 17,
      "reentry_gap_days": 2,
      "sample_reason": "same_symbol_reentry_within_5d"
    }
  ],
  "sold_too_early_samples": [],
  "holding_compression_samples": []
}
```

Sample refs must include at least `run_id + trade_index`. When a sample links to
another trade, include the second `trade_index` instead of embedding the full
trade.

### Missing Evidence

Missing evidence is part of the result:

```json
{
  "exit_event_missing_count": 0,
  "exit_method_missing_count": 0,
  "exit_reason_missing_count": 0,
  "exit_checks_missing_count": 0,
  "post_exit_missing_count": 0,
  "trade_review_missing_count": 0,
  "affected_sample_refs": []
}
```

If missing exit checks block the MA/MACD split, the conclusion should say so.
That means the next task is upstream evidence capture, not post-run
recalculation.

### Markdown Shape

`exit_method_attribution.zh.md` should be concise and AI-readable:

1. conclusion candidates;
2. overview metric deltas;
3. exit-method group table;
4. trigger-component group table;
5. top fast-reentry samples;
6. top sold-too-early samples;
7. missing evidence summary;
8. non-claims and next check.

Markdown should not expand every lifecycle row. Full detail stays in JSON.

## In Scope

- Read existing `trade_lifecycle.json` and `post_exit_analysis.json`.
- Group completed trades by `exit_method_name`, `exit_reason`, exit checks, and
  selected exit values when present.
- Compare baseline and variant exit behavior within the same `segment_id`.
- Report holding-period compression, average-win compression, stop-loss rate,
  sold-too-early rate, and same-symbol re-entry density by exit method.
- Emit sample refs using `run_id + trade_index`.
- Produce Chinese Markdown for AI review.
- Preserve baseline-vs-variant segment pairing so a conclusion can be traced
  back to `segment_id`.
- Report missing exit-method component evidence explicitly.

## Out Of Scope

- Automatic parameter tuning.
- Automatic market-type detection.
- Automatic strategy switching.
- Changing `ma_macd_weakening_exit` logic before evidence is inspected.
- Adding new indicators just to explain the current report.
- Treating missing exit evidence as false, neutral, or zero.
- Proving live-trading suitability.
- Splitting `ma_macd_weakening_exit` into MA/MACD sub-causes unless those
  sub-condition checks already exist in decision-time exit evidence.

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
- If `ma_macd_weakening_exit` lacks component evidence, the artifact identifies
  that evidence gap instead of making a MA/MACD sub-cause claim.
- `exit_method_attribution.zh.md` is sufficient for AI to decide the next check
  without opening every segment run manually.

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
