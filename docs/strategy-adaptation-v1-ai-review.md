# Strategy Adaptation V1 AI Review

本文件记录一次按 sealed baseline 执行的 AI 复盘结果。复盘只读取已落盘
artifacts 和版本化 baseline，不重跑策略、不重算指标、不补默认值。

## Sources Read

- `examples/strategy-adaptation-v1-baseline.json`
- `docs/strategy-adaptation-v1-closure.md`
- `docs/next-stage-exit-method-attribution.md`
- `reports/strategy-variant-validation-tushare-market-type-add-on/strategy_variant_validation.json`
- `reports/strategy-variant-attribution-tushare-market-type-add-on-bull/strategy_variant_attribution.json`

## Golden Fixture

The machine-readable expected review boundary is stored in:

- `examples/strategy-adaptation-v1-ai-review-golden.json`

Use it to check future AI reviews of the sealed V1 stage. Wording may differ,
but the review must preserve the required metrics, evidence refs, sample refs,
final recommendation, and `must_not_claim` boundaries recorded in that fixture.

## Golden Coverage

The current review intentionally covers these golden-required points:

- V1 框架已经完成已知市场类型到变体归因复盘的闭环。
- 牛市变体 bull_market_let_winners_run 不应继续作为让盈利奔跑方向推进。
- 熊市变体改善亏损和回撤，但不能直接接受为策略规则。
- 震荡市变体基本持平略好，不是当前优先方向。
- 下一步必须先解释 `ma_macd_weakening_exit` 为什么在牛市变体中过快退出。

The bull-market variant risk that must remain visible is:

- 当前归因还没有拆开 `ma_macd_weakening_exit` 内部到底是 MA 条件、MACD 条件，还是组合触发顺序导致退出过快。

## Review Verdict

Strategy Adaptation V1 可以封板。当前框架已经能从已知市场类型出发，
完成基线回测、策略适配矩阵、有限变体生成、变体执行验证和变体归因复盘。

但当前证据不支持直接进入策略切换或参数调整。下一阶段应该严格进入
Exit Method Attribution，先解释 `ma_macd_weakening_exit` 在牛市变体中为什么
过快退出。

## Findings

### Finding 1: V1 框架闭环成立

**Claim:** 当前版本已经完成“已知市场类型 -> 变体验证 -> 变体归因”的闭环。

**Evidence refs:**

- `docs/strategy-adaptation-v1-closure.md`
- `examples/strategy-adaptation-v1-baseline.json`

**Evidence:** baseline manifest 记录了基线市场段 manifest、市场类型汇总、
策略适配矩阵、变体草案、变体 RunPlan manifest、变体市场类型汇总、
变体验证对比和牛市变体归因 artifact。

**Risk:** `reports/` 是本地输出且被 Git ignore；版本化 baseline 只保存关键
路径和指标，不保存完整 run artifacts。

**Next check:** 后续变更必须继续能对比
`examples/strategy-adaptation-v1-baseline.json` 中记录的指标。

### Finding 2: 牛市变体不应继续作为“让盈利奔跑”方向推进

**Claim:** 牛市变体 `bull_market_let_winners_run` 实际没有让盈利继续跑，而是
把退出触发变快，造成交易数暴增、平均持仓压缩和平均盈利下降。

**Evidence refs:**

- `market_type_id=bull_market`
- `reports/strategy-variant-validation-tushare-market-type-add-on/strategy_variant_validation.json`
- `reports/strategy-variant-attribution-tushare-market-type-add-on-bull/strategy_variant_attribution.json`

**Evidence:**

- 平均收益：`25.37% -> 9.75%`
- 加权胜率：`67.05% -> 53.05%`
- 交易数：`88 -> 262`
- 平均持仓：`24.35 天 -> 4.06 天`
- 5 天内同标的重入：`15 -> 132`
- 平均盈利：`10.41% -> 2.55%`
- 主退出方式：`kdj_overheated_exit -> ma_macd_weakening_exit`

**Sample refs:**

- `run_id=tushare-market-type-add-on-market-segment-2014_2015_bull_market__variant__bull_market_let_winners_run`, `trade_index=15 -> 17`, `symbol=000001.SZ`
- `run_id=tushare-market-type-add-on-market-segment-2014_2015_bull_market__variant__bull_market_let_winners_run`, `trade_index=17 -> 22`, `symbol=000001.SZ`
- `run_id=tushare-market-type-add-on-market-segment-2020_2021_structural_bull_market__variant__bull_market_let_winners_run`, `trade_index=1 -> 6`, `symbol=000001.SZ`

**Risk:** 当前归因已经能定位行为变化，但还没有拆开
`ma_macd_weakening_exit` 内部到底是 MA 条件、MACD 条件，还是组合触发顺序
导致退出过快。

**Next check:** 进入 `docs/next-stage-exit-method-attribution.md`，先做退出方法
证据下钻，不生成新的牛市变体。

### Finding 3: 熊市变体表现改善，但不能直接接受为策略规则

**Claim:** 熊市变体相对基线降低了亏损和回撤，但当前证据只能说明它是值得
复盘的候选，不能说明它已经是可上线规则。

**Evidence refs:**

- `market_type_id=bear_market`
- `reports/strategy-variant-validation-tushare-market-type-add-on/strategy_variant_validation.json`

**Evidence:**

- 平均收益：`-12.17% -> -5.77%`
- 平均回撤：`15.62% -> 7.01%`
- 交易数：`137 -> 83`
- 加权胜率：`30.66% -> 26.51%`

**Risk:** 熊市改善可能来自降低暴露、关闭加仓、交易数下降，或这些因素共同
作用。当前还没有做熊市变体归因。

**Next check:** 等 Exit Method Attribution 首 slice 完成后，再决定是否做
bear-market attribution，避免同时展开多个方向。

### Finding 4: 震荡市变体不是当前优先方向

**Claim:** 震荡市变体相对基线基本持平略好，但没有明显到需要优先展开新阶段。

**Evidence refs:**

- `market_type_id=range_market`
- `reports/strategy-variant-validation-tushare-market-type-add-on/strategy_variant_validation.json`

**Evidence:**

- 平均收益：`5.32% -> 5.61%`
- 平均回撤：`8.62% -> 8.39%`
- 胜率：`50.44% -> 50.44%`
- 交易数：`113 -> 113`

**Risk:** 变动幅度小，可能只是有限样本内的轻微差异。

**Next check:** 不作为下一阶段主线。等退出方法归因和熊市归因有明确结论后
再回来比较震荡市。

## Final Recommendation

当前 AI 复盘可以稳定得出同一个下一步：

```text
Do not tune.
Do not switch strategy.
Do not add market recognition.
Start Exit Method Attribution.
```

第一刀应该解释：

```text
为什么 ma_macd_weakening_exit 在 bull_market 变体中把平均持仓从 24.35 天压到 4.06 天？
```

只有当退出方法证据下钻能解释具体触发原因后，才允许生成新的候选变体。
