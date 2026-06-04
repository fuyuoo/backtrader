# Run Review Workbench Closure

本文档定义当前阶段的封版终点。目标不是继续优化策略收益，而是让一次真实回测成为 AI 可读、证据可追溯、样本可下钻的复盘工作台。

## 终点定义

当前阶段完成时，用户应该能做到：

1. 用一个 YAML Run Plan 跑出真实回测。
2. 得到完整 Run Artifact：配置、报告、交易、信号、仓位、执行、归因、止盈止损后观察。
3. 用 `run_data_overview.json` 快速判断这个 run 是否可用。
4. 用 `run_data_dictionary.json` 理解每个 artifact 和关键字段。
5. 用 `run_data_drilldown*.json` 按 `trade_index` 或 `sample_index` 下钻单个或多个样本。
6. 用 `run_data_attribution_index.json` 按入场、退出、机会、加仓归因字段筛选样本。
7. 让 AI 在不重跑、不重算、不补默认值的情况下输出带证据引用的复盘结论。
8. 让 AI 给出有限的下一轮实验候选，而不是自动调参或无限优化。

## 非目标

以下内容不属于当前阶段：

- 自动参数优化。
- 自动策略搜索。
- 大型 Dashboard。
- 实盘交易或券商接入。
- AI 直接断言策略会赚钱。
- 为报告展示无限追加 UI 或图表。
- 为单次复盘无限追加指标。

## 必备工具

| 命令 | 作用 |
|---|---|
| `att-run-data-dictionary` | 生成回测数据字典，说明每个 JSON 是什么。 |
| `att-run-data-overview` | 生成 run 总览，显示收益、风险、交易、信号、执行、复盘层数量。 |
| `att-run-data-drilldown` | 下钻一个 trade/opportunity/add_on 样本。 |
| `att-run-data-drilldown-batch` | 批量下钻多个样本，方便 AI 横向比较。 |
| `att-run-data-attribution-index` | 建立归因字段索引，并可按字段等值筛选样本。 |
| `att-strategy-environment-profile` | 将环境适配统计收敛为适合、规避和不确定环境候选。 |
| `att-generate-market-segment-runs` | 从人工整理的相似行情段 catalog 生成验证 RunPlan 草稿。 |
| `att-market-type-summary` | 汇总牛市、震荡市、熊市验证 run 的已落盘结果。 |
| `att-review-packet` 到 `att-review-result` | 生成 AI 复盘包、findings、brief、结果和实验候选。 |

## 必备 Artifact

对一个真实 run，例如 `reports/tushare-expanded-add-on-2023-2024/`，封版时至少应存在：

```text
run_plan.json
report.json
report.zh.md
trades.json
equity_curve.json
positions.json
signal_audit.json
sizing_audit.json
execution_audit.json
trade_lifecycle.json
trade_review.json
environment_fit.json
strategy_environment_profile.json
post_exit_analysis.json
evidence_validation.json
run_data_dictionary.json
run_data_overview.json
run_data_drilldown_batch.json
run_data_attribution_index.json
review_packet.all.json
review_findings.all.json
review_sample_batch.all.json
review_brief.all.json
ai_review_result.all.json
review_experiment_candidates.all.json
```

## AI 标准工作流

AI 复盘一个 run 时应按这个顺序工作：

1. 读取 `evidence_validation.json`，若 `status != ok`，停止复盘并先修证据链。
2. 读取 `run_data_overview.json`，确认 run 范围、交易数、信号数、执行数、复盘样本数。
3. 读取 `run_data_dictionary.json`，确认字段含义和样本主键。
4. 用 `run_data_attribution_index.json` 找候选样本集合。
5. 用 `run_data_drilldown_batch.json` 横向比较样本证据。
6. 输出复盘结论时必须引用 `sample_id`，并优先引用 `trade_index` 或 `sample_index`。
7. 输出下一步时只给有限候选，不直接调参。

## 验收命令

运行 curated acceptance：

```powershell
python scripts\acceptance_smoke.py
```

对真实 run 生成封版工具产物：

```powershell
python -m attbacktrader.cli.run_data_dictionary --run-dir reports/tushare-expanded-add-on-2023-2024
python -m attbacktrader.cli.run_data_overview --run-dir reports/tushare-expanded-add-on-2023-2024
python -m attbacktrader.cli.run_data_drilldown_batch --run-dir reports/tushare-expanded-add-on-2023-2024 --sample-ref trade:117 --sample-ref trade:116 --sample-ref opportunity:12 --sample-ref add_on:1
python -m attbacktrader.cli.run_data_attribution_index --run-dir reports/tushare-expanded-add-on-2023-2024 --filter entry.market.hs300.bullish_trend=false
python -m attbacktrader.cli.market_type_summary --manifest examples/generated-market-segment-runs/tushare-market-type-add-on/market_segment_run_manifest.json --report-root reports
```

验收时至少确认：

- `evidence_validation.status` 为 `ok`。
- `run_data_overview.json` 能显示 closed trades、signal intents、execution events、review counts。
- `run_data_dictionary.json` 包含 artifact 说明和 reason code 中文翻译。
- `run_data_drilldown_batch.json` 至少包含一个 trade、一个 opportunity、一个 add_on 样本。
- `run_data_attribution_index.json` 能按 `entry.*` 或 `exit.*` 条件筛出样本。
- 9 段市场类型验证 run 的 `evidence_validation.status` 均为 `ok`。
- `market_type_summary.json` 能按牛市、震荡市、熊市汇总收益、回撤、交易数、胜率和卖飞率。
- AI 复盘结果不重算指标，不补默认值，不把后验线索写成因果结论。

## 停止线

达到以上验收后，当前阶段应封版。后续新增工作必须属于新的阶段，且先说明方向、作用、验收标准。

当前阶段结束后的合理下一阶段是“策略适配与切换规则设计”，而不是继续扩展复盘框架本身。

## 已完成：人工市场类型验证

环境验证不按自然年份机械切分。当前只维护三个顶层市场类型：牛市、
震荡市、熊市。每个类型保留三个历史时间段，先比较组内共性，再跨类型
比较策略表现，为后续连续回测中的策略切换规则提供样本基础。
`att-generate-market-segment-runs` 只消费人工 catalog 中的类型、日期和价格
行为来源，生成合法 RunPlan 草稿；代码不负责判断某段行情是否相似。
市场类型验证使用单独的长期上市股票池，避免早期行情段因为个股上市太晚
而中断。`att-market-type-summary` 只读取已落盘 artifacts，汇总牛市、
震荡市、熊市的收益、回撤、交易数、胜率和卖飞率，不输出策略切换结论。

已验收的市场类型验证结果：

| 类型 | 段数 | 交易数 | 平均收益 | 平均回撤 | 加权胜率 |
|---|---:|---:|---:|---:|---:|
| 牛市 | 3 | 88 | 25.37% | 4.90% | 67.05% |
| 震荡市 | 3 | 113 | 5.32% | 8.62% | 50.44% |
| 熊市 | 3 | 137 | -12.17% | 15.62% | 30.66% |

## 封版状态

当前阶段可以封版。封版后停止继续扩展复盘框架和报告层，不再新增指标、
归因维度、行情分类、策略调优或切换规则。后续工作必须进入新阶段，并
先写清方向、作用和验收标准。
