# Strategy Adaptation Stage

本文档定义封版后的下一阶段：策略适配与切换规则设计。

## 封板状态

Strategy Adaptation V1 已封板。封板文档和基线 manifest：

```text
docs/strategy-adaptation-v1-closure.md
examples/strategy-adaptation-v1-baseline.json
```

下一阶段单独定义在：

```text
docs/next-stage-exit-method-attribution.md
```

本文件保留 V1 的能力地图和证据链，不再继续追加调参、策略切换或市场识别
范围。

## 当前方向

当前先不做市场类型识别。牛市、震荡市、熊市仍然来自人工整理的行情段
catalog 或已落盘的 `market_type_summary.json`。本阶段先回答：

> 在已知市场类型下，当前策略适合什么环境，不适合什么环境，原因来自哪些入场证据？

## 第一项能力：策略适配矩阵

`att-strategy-adaptation-matrix` 读取已落盘 artifacts，生成：

```text
strategy_adaptation_matrix.json
strategy_adaptation_matrix.zh.md
```

数据流：

```text
market_type_summary.json
  -> 每个 segment 的 report_dir
  -> trade_lifecycle.json 的 completed trades
  -> entry event 的 checks/categories/method/reason
  -> post_exit_analysis.json 的卖出后 5 天结果
  -> 按牛市/震荡市/熊市聚合
```

## 边界

- 不识别牛市、震荡市、熊市。
- 不重跑回测。
- 不重算指标。
- 不补默认值。
- 不把报告层做成决策层。
- 不自动调参。

## 可扩展方式

新增入场归因维度时，优先让策略执行时把证据写入
`trade_lifecycle.json` 的 entry event：

- `checks`：适合布尔判断，例如 `market.hs300.bullish_trend=true`。
- `categories`：适合枚举分类，例如行业、风险组、入场方法。
- `values`：只作为样本证据保留，不在矩阵层默认分箱。

矩阵会自动聚合新增的 `checks` 和 `categories`，不需要为了每个新维度修改
矩阵代码。

## 验收

第一项能力完成时应满足：

- 能从 `market_type_summary.json` 生成策略适配矩阵。
- 每个市场类型能看到收益、回撤、胜率、卖飞率和适配判断。
- 每个市场类型能看到盈利入场因子、亏损入场因子、卖飞入场因子。
- 因子样本包含 `run_id` 和 `trade_index`，AI 可以继续下钻原始交易证据。
- 输出规则明确说明不重算指标、不识别行情、不自动调参。

## 第二项能力：矩阵因子下钻

`att-strategy-adaptation-drilldown` 从矩阵中的某个因子回到原始交易样本：

```powershell
att-strategy-adaptation-drilldown --matrix reports\strategy-adaptation-matrix-tushare-market-type-add-on\strategy_adaptation_matrix.json --market-type-id bull_market --section winning_entry_factors --factor-rank 1
```

输出：

```text
strategy_adaptation_drilldown.json
strategy_adaptation_drilldown.zh.md
```

它使用矩阵里的 `sample_refs`，按 `run_id + trade_index` 调用既有
`review_sample` 证据包。这样 AI 不需要手动在多个 run 目录里找样本，
也不会重算入场指标。

## 第三项能力：策略变体验证草案

`att-strategy-variant-drafts` 从矩阵生成有限的人工确认草案：

```powershell
att-strategy-variant-drafts --matrix reports\strategy-adaptation-matrix-tushare-market-type-add-on\strategy_adaptation_matrix.json --base-config examples\run-tushare-market-type-add-on.yaml
```

输出：

```text
strategy_variant_drafts.json
strategy_variant_drafts.zh.md
*.yaml
```

当前草案只覆盖三类方向：

- 牛市优先适配：验证是否需要放宽过早止盈，让盈利趋势继续跑。
- 震荡市条件适配：验证关闭加仓后是否更适合快进快出。
- 熊市规避/防守：验证关闭加仓和降低仓位暴露后，亏损是否收敛。

这些草案仍然不是可直接采纳的策略规则。它们必须先人工确认，再转换成
合法 RunPlan，并只在对应人工市场类型分段上验证。

## 第四项能力：策略变体执行验证

`att-generate-strategy-variant-runs` 把矩阵生成的草案转换成每个行情段的
合法 RunPlan：

```powershell
att-generate-strategy-variant-runs --drafts reports\strategy-variant-drafts-tushare-market-type-add-on\strategy_variant_drafts.json --market-segment-manifest examples\generated-market-segment-runs\tushare-market-type-add-on\market_segment_run_manifest.json
```

输出：

```text
strategy_variant_run_manifest.json
strategy_variant_run_manifest.zh.md
*.run.yaml
```

默认模式会尝试复用已有快照；当本地快照因为停牌或末端缺交易日不能覆盖
完整段时，可以加 `--refresh-snapshots`，让 provider 补齐或确认缺失数据。

变体 RunPlan 跑完后，先用 `att-market-type-summary` 生成变体版
`market_type_summary.json`，再用 `att-strategy-variant-validation` 对比基线：

```powershell
att-strategy-variant-validation --baseline-summary reports\market-type-summary-tushare-market-type-add-on\market_type_summary.json --variant-summary reports\market-type-summary-strategy-variant-tushare-market-type-add-on\market_type_summary.json
```

输出：

```text
strategy_variant_validation.json
strategy_variant_validation.zh.md
```

当前真实验证结果显示：

- 熊市变体：平均收益从 -12.17% 到 -5.77%，平均回撤从 15.62% 到 7.01%。
- 震荡市变体：平均收益从 5.32% 到 5.61%，交易数不变。
- 牛市变体：平均收益从 25.37% 到 9.75%，胜率从 67.05% 到 53.05%，交易数从 88 增至 262。

这只是候选验证结果，不是策略切换规则。下一步如果要继续，应从这些对比
反查具体交易样本，解释为什么某个变体在某类行情改善或退化。

## 第五项能力：策略变体归因复盘

`att-strategy-variant-attribution` 在验证对比之后继续下钻某个市场类型：

```powershell
att-strategy-variant-attribution --baseline-manifest examples\generated-market-segment-runs\tushare-market-type-add-on\market_segment_run_manifest.json --variant-manifest examples\generated-strategy-variant-runs\tushare-market-type-add-on\strategy_variant_run_manifest.json --market-type-id bull_market
```

输出：

```text
strategy_variant_attribution.json
strategy_variant_attribution.zh.md
```

它按 `segment_id` 配对基线和变体 run artifacts，然后读取：

- `report.json`：收益、回撤、胜率、平均盈利/亏损。
- `trade_lifecycle.json`：入场/退出方法、退出原因、持仓天数、同标的退出后重入间隔。

当前牛市变体归因显示：

- 交易数从 88 增至 262。
- 平均持仓从 24.35 天降至 4.06 天。
- 5 天内同标的重入从 15 次增至 132 次。
- 平均盈利从 10.41% 降至 2.55%。
- 主退出方式从 `kdj_overheated_exit` 变为 `ma_macd_weakening_exit`。

因此牛市变体的主要候选问题不是“趋势持有不足”，而是新退出方式触发过快，
导致频繁释放仓位、同标的快速重入，并把盈利切薄。这个结论仍然只是复盘
结论，下一步应先针对退出方法做证据下钻，而不是直接调参或上线切换规则。
