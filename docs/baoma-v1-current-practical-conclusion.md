# Baoma V1 Current Practical Conclusion

本文档记录 2026-07-03 对当前 Baoma V1 回测证据的实战口径结论。
它不是新的回测结果，也不是上线承诺；它用于固定当前证据能支持什么、
不能支持什么，以及下一轮组合回测应如何设置。

## Conclusion

当前 Baoma V1 的主回测仍应定义为 `Trade-Sample Backtest`，不是实盘组合回测。

原因很直接：

- 初始资金是 `10,000,000,000`。
- `sizing_params` 只有 `max_holding_count=800` 和 `min_order_quantity=100`。
- 没有启用 `max_total_exposure_percent`。
- 没有启用 `max_risk_group_exposure_percent`。
- 没有同一行业最多持仓数限制。
- 没有按 score/soil/seed 排序后的资金和持仓容量竞争。

所以当前回测可以用于发现候选因子、土壤、种子和行业状态的统计倾向；
不能直接回答“实盘今天应该买哪几只、买多少仓位、组合收益会如何”。

## Industry Control Status

当前 RunPlan 已接入申万行业归因：

```text
analysis.industry_attribution.enabled = true
analysis.industry_attribution.source = SW2021
analysis.industry_attribution.levels = [1, 2, 3]
```

但这只是行业证据和后验归因，不是行业规避。

代码层已有行业风险组能力：`risk_group_by_symbol(level=1/2/3)` 可以把股票映射到
申万行业，`EqualWeightSizing.max_risk_group_exposure_percent` 可以限制同一行业市值占比。
当前主回测没有配置该上限，因此不会因为同行业集中而拦截买入。

## Practical Starting Policy

如果进入实战口径，下一轮不应该继续用 `max_holding_count=800` 的样本采集设置。
建议先跑一个固定参数 scored portfolio 对照实验：

```yaml
sizing_params:
  max_holding_count: 10
  max_total_exposure_percent: 0.85
  max_risk_group_exposure_percent: 0.20
  risk_group_level: 1
  min_order_quantity: 100
```

组合规则建议：

| item | initial setting | reason |
|---|---:|---|
| 最大持仓数 | 10 | 避免样本回测式过度分散，便于观察真实资金竞争 |
| 总仓位上限 | 85% | 给信号断档、停牌、滑点和回撤留现金缓冲 |
| 单票目标仓位 | 8%-10% | 与 10 只组合匹配，避免单票过小导致噪声主导 |
| 申万一级行业上限 | 20% | 单行业最多接近两只满仓票，降低主题拥挤 |
| 行业优先规则 | prefer unheld industry | 同分或接近分数时优先未持有行业 |

如果需要更硬的行业规避，还应新增一个组合控制：

```text
max_risk_group_holding_count = 2
```

当前代码已有行业市值上限，但没有独立的“同一行业最多 N 只”约束。

## Score Usage Boundary

当前 soil/seed/score 证据适合做候选排序和过滤，不适合直接人工拍成永久阈值。

第一版可执行口径应是：

1. 每个交易日只看 T-1 已完成 K 线和已落盘证据。
2. 过滤掉明显弱 soil 或弱 seed 的候选。
3. 对剩余候选按 score 排序。
4. 只买入达到 score gate 且通过现金、持仓数、行业约束的前排候选。
5. 不在测试窗口根据结果重调 score gate 或权重。

买入分数不建议现在直接定死为某个绝对值。更稳妥的第一轮验证方式是同时跑：

| gate | interpretation |
|---|---|
| conservative | 只买最高分层，验证确定性 |
| balanced | 最高分层放宽一档，验证交易数量和回撤 |
| aggressive | 保留更多候选，验证收益是否来自广覆盖还是高质量 |

最终实战阈值应从 scored portfolio 的样本外结果里选，而不是从
`Trade-Sample Backtest` 的后验矩阵里直接选。

## Next Decision

当前最推荐的下一步是：冻结一版 soil/seed/score 规则，建立
`Scored Portfolio Backtest`，用真实持仓数、资金竞争和行业约束重跑。

判定标准不是单笔交易样本胜率，而是组合层面的：

- 年化收益和基准超额。
- 最大回撤。
- 持仓集中度。
- 行业集中度。
- turnover 和交易成本。
- score gate 漏斗。
- 分年度和市场阶段稳定性。

如果 scored portfolio 仍然稳定，Baoma V1 才进入实战参数讨论；
如果不稳定，当前 soil/seed/score 只保留为研究线索，不进入交易规则。
