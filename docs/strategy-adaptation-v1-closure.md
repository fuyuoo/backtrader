# Strategy Adaptation V1 Closure

本文档封板当前策略适配阶段。封板对象是策略适配与变体复盘框架 V1，
不是某个策略参数或策略切换规则。

## Closure Statement

当前版本已经完成从已知行情类型到变体归因复盘的闭环：

```text
manual market segments
  -> baseline segment RunPlans
  -> baseline run artifacts
  -> market_type_summary
  -> strategy_adaptation_matrix
  -> strategy_variant_drafts
  -> generated legal variant RunPlans
  -> variant run artifacts
  -> strategy_variant_validation
  -> strategy_variant_attribution
```

这个闭环的用途是让后续开发从真实回测结果和交易证据出发，而不是继续凭
主观感觉添加指标、调参数或扩大报告。

## What Is Sealed

- 人工牛市、震荡市、熊市行情段 catalog。
- 基线市场段回测和 `market_type_summary.json`。
- 策略适配矩阵和矩阵下钻能力。
- 矩阵到人工确认变体草案的生成能力。
- 草案到合法市场段 RunPlan 的生成能力。
- 基线 vs 变体市场类型对比能力。
- 变体相对基线的交易行为归因能力。
- AI skill 读取这些 artifacts 的工作流。

## Accepted Evidence

当前封板接受以下本地 artifacts 作为 V1 证据链：

- `reports/market-type-summary-tushare-market-type-add-on/market_type_summary.json`
- `reports/strategy-adaptation-matrix-tushare-market-type-add-on/strategy_adaptation_matrix.json`
- `reports/strategy-adaptation-drilldown-tushare-market-type-add-on-bull/strategy_adaptation_drilldown.json`
- `reports/strategy-variant-drafts-tushare-market-type-add-on/strategy_variant_drafts.json`
- `examples/generated-strategy-variant-runs/tushare-market-type-add-on/strategy_variant_run_manifest.json`
- `reports/market-type-summary-strategy-variant-tushare-market-type-add-on/market_type_summary.json`
- `reports/strategy-variant-validation-tushare-market-type-add-on/strategy_variant_validation.json`
- `reports/strategy-variant-attribution-tushare-market-type-add-on-bull/strategy_variant_attribution.json`

Because `reports/` is local output and ignored by Git, the versioned baseline
summary is stored in:

```text
examples/strategy-adaptation-v1-baseline.json
```

## Current Findings

Market-type validation currently shows:

- Bull market variant degraded: average return `25.37% -> 9.75%`, win rate
  `67.05% -> 53.05%`, trade count `88 -> 262`.
- Range market variant was roughly neutral to slightly better: average return
  `5.32% -> 5.61%`, trade count unchanged at `113`.
- Bear market variant improved loss and drawdown: average return
  `-12.17% -> -5.77%`, average drawdown `15.62% -> 7.01%`.

Bull-market attribution currently shows the failed variant did not let winners
run. Instead:

- average holding days changed from `24.35` to `4.06`;
- trade count changed from `88` to `262`;
- same-symbol re-entry within 5 days changed from `15` to `132`;
- average win changed from `10.41%` to `2.55%`;
- primary exit method changed from `kdj_overheated_exit` to
  `ma_macd_weakening_exit`.

The current candidate explanation is: `ma_macd_weakening_exit` exits too fast
in bull-market segments, releases capital quickly, triggers frequent same-symbol
re-entry, and cuts average winning trade size.

## Explicit Non-Claims

This closure does not claim:

- the strategy is profitable enough for production;
- the bull/range/bear labels can be detected automatically;
- the variant should be used for live strategy switching;
- `ma_macd_weakening_exit` is wrong in every environment;
- the bear-market defensive variant is accepted as final strategy logic.

## Frozen Boundaries

Do not extend this V1 stage by:

- adding automatic market-type recognition;
- adding automatic parameter tuning;
- adding a strategy switcher;
- expanding the market taxonomy beyond bull/range/bear;
- adding new attribution dimensions unless a new stage document accepts that
  scope;
- changing strategy behavior based only on this closure document.

## Verification

Current accepted verification:

```text
python scripts\acceptance_smoke.py
231 passed
Strategy Adaptation V1 golden check summary
status: ok
check_count: 72
failed_count: 0
Workbench Closure golden check summary
status: ok
check_count: 124
failed_count: 0

python -m pytest -q
315 passed
```

## Next Stage

The originally proposed next stage was defined separately in:

```text
docs/next-stage-exit-method-attribution.md
```

That stage is now parked as a future deep-analysis tool. The current main line
is Backtest Workbench V1 closure, captured in:

```text
docs/backtest-workbench-system-map.md
examples/backtest-workbench-v1-baseline.json
docs/backtest-workbench-v1-closure.md
```
