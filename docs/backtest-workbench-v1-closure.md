# Backtest Workbench V1 Closure

本文档封板当前 Backtest Workbench V1。封板对象是回测证据工作台，
不是某个策略参数、策略收益结果或自动调参流程。

## Closure Statement

Seal Backtest Workbench V1 as an AI-friendly evidence workbench: run, validate, index, review, compare, and close bounded experiment cycles from persisted artifacts.

## Accepted Verification

| check | command | expected |
|---|---|---|
| `acceptance_smoke` | `python scripts\acceptance_smoke.py` | 231 passed; Strategy Adaptation V1 golden check status ok, check_count 72, failed_count 0; Workbench Closure golden check status ok, failed_count 0 |
| `full_pytest` | `python -m pytest -q` | 315 passed |
| `diff_check` | `git diff --check` | no whitespace errors; CRLF warnings are acceptable on Windows |

## Accepted Navigation State

| source | exists | schema | summary |
|---|---:|---|---|
| `run_catalog` | True | `attbacktrader.run_catalog.v1` | run_count=24, group_count=9 |
| `experiment_lifecycle` | True | `attbacktrader.experiment_lifecycle.v1` | chain_count=9, decision_gap=0 |
| `strategy_adaptation_golden_check` | True | `attbacktrader.ai_review_golden_check.v1` | status=ok, failed=0 |

## Closure Criteria

| criterion | status | evidence |
|---|---|---|
| curated acceptance smoke 通过 | `accepted` | python scripts\acceptance_smoke.py -> 231 passed; Strategy golden 72/72 ok; Workbench closure golden ok |
| 完整仓库测试通过 | `accepted` | python -m pytest -q -> 315 passed |
| Run Catalog 可作为第一入口 | `accepted` | reports\run-catalog\run_catalog.json |
| Experiment Lifecycle 可显示实验阶段 | `accepted` | reports\experiment-lifecycle\experiment_lifecycle.json decision_gap_count=0 |
| Strategy Adaptation V1 受 golden check 保护 | `accepted` | reports\strategy-adaptation-v1-ai-review-golden-check\ai_review_golden_check.json |
| Exit Method Attribution 等深度分析已 parked | `accepted` | docs/next-stage-exit-method-attribution.md; docs/exit-method-attribution-missing-evidence-check.md |

## Accepted Commands

| command | direction | purpose |
|---|---|---|
| `att-run-plan` | 回测执行 | 从一个已验证 YAML RunPlan 执行可重复回测并落盘证据链。 |
| `att-run-catalog` | 工作台导航 | 索引已落盘 runs、角色、artifact 完整性、证据状态和可比较分组。 |
| `att-experiment-lifecycle` | 实验治理 | 查看候选、草稿、确认、生成、执行、比较、归因和缺失决策阶段。 |
| `att-experiment-decisions` | 实验治理 | 从显式 decision input 写出 accepted/rejected/parked 实验决策记录。 |
| `att-run-data-overview` | AI 下钻 | 读取单个 run 的第一屏总览和证据状态。 |
| `att-run-data-dictionary` | AI 下钻 | 解释单个 run 的 artifact 和字段含义。 |
| `att-review-packet` | AI 复盘 | 从已落盘 run 生成 Skill 可读复盘包。 |
| `att-review-findings` | AI 复盘 | 把复盘包整理成引用明确的 finding。 |
| `att-review-experiment-candidates` | 实验治理 | 把 finding 转成候选验证方向，不修改策略。 |
| `att-review-experiment-drafts` | 实验治理 | 生成需要人工确认的实验草稿。 |
| `att-review-experiment-confirm` | 实验治理 | 把一个人工确认草稿转成合法 RunPlan。 |
| `att-compare-runs` | 比较验证 | 比较多个已落盘 run 的收益、风险、交易和阻断差异。 |
| `att-compare-environment-fit` | 比较验证 | 比较多个 run 的环境适配证据稳定性。 |
| `att-generate-market-segment-runs` | 市场段验证 | 从人工行情段 catalog 生成合法市场段 RunPlans。 |
| `att-market-type-summary` | 市场段验证 | 汇总已知牛市、震荡市、熊市段表现。 |
| `att-strategy-adaptation-matrix` | 策略适配 V1 | 从已知市场类型的交易证据生成适配矩阵。 |
| `att-strategy-variant-validation` | 策略适配 V1 | 比较基线和策略变体在已知市场类型下的表现。 |
| `att-review-golden-check` | 封板校验 | 校验 sealed-stage AI review 是否越界或漏证据。 |
| `att-workbench-closure-snapshot` | 封板/验收 | 写出 Backtest Workbench V1 baseline JSON 和 closure 文档。 |
| `att-workbench-closure-golden-check` | 封板校验 | 校验 Workbench V1 closure 文档是否忠实保留 baseline 的命令、非目标、测试计数和 AI 读取顺序。 |
| `att-ai-skill-entry-contract` | AI 易用 | 写出 ATTbacktrader AI review Skill 的固定入口、证据门禁和输出合同。 |
| `scripts\acceptance_smoke.py` | 封板校验 | 运行 curated regression suite、sealed V1 golden check 和 Workbench closure golden check。 |

## Accepted Artifact Groups

### 单次回测核心证据

- direction: 回测执行
- purpose: 证明一次 run 可复盘、可校验、可下钻。
- `run_plan.json`
- `report.json`
- `report.zh.md`
- `trades.json`
- `signal_audit.json`
- `sizing_audit.json`
- `execution_audit.json`
- `trade_lifecycle.json`
- `trade_lifecycle.zh.md`
- `trade_review.json`
- `trade_review.zh.md`
- `post_exit_analysis.json`
- `post_exit_analysis.zh.md`
- `evidence_validation.json`
- `equity_curve.json`
- `positions.json`
- `snapshots.json`

### AI 复盘工作台

- direction: AI 复盘
- purpose: 让 AI 从总览、字典、样本和 brief 开始复盘。
- `run_data_overview.json`
- `run_data_dictionary.json`
- `run_data_drilldown.json`
- `run_data_drilldown_batch.json`
- `run_data_attribution_index.json`
- `review_packet.<focus>.json`
- `review_findings.<focus>.json`
- `review_sample.<kind>.<id>.json`
- `review_sample_batch.<focus>.json`
- `review_brief.<focus>.json`
- `ai_review_result.<focus>.json`

### 实验治理

- direction: 实验闭环
- purpose: 把复盘发现转成有限候选、草稿、确认和生命周期状态。
- `review_experiment_candidates.<focus>.json`
- `review_experiment_drafts.<focus>.json`
- `review_experiment_confirmed.<draft>.json`
- `run_catalog.json`
- `run_catalog.zh.md`
- `experiment_lifecycle.json`
- `experiment_lifecycle.zh.md`
- `experiment_decisions.json`
- `experiment_decisions.zh.md`
- `examples/experiment-decisions/workbench-v1-strategy-variant-decisions.json`

### 比较与市场类型

- direction: 比较验证
- purpose: 比较 run、环境适配、市场段和策略变体表现。
- `comparison.json`
- `environment_fit_comparison.json`
- `market_segment_run_manifest.json`
- `market_type_summary.json`
- `strategy_adaptation_matrix.json`
- `strategy_adaptation_drilldown.json`
- `strategy_variant_drafts.json`
- `strategy_variant_run_manifest.json`
- `strategy_variant_validation.json`
- `strategy_variant_attribution.json`

### 封板合同

- direction: 封板/验收
- purpose: 固定当前 V1 边界、测试计数、非目标和 AI 入口。
- `examples/backtest-workbench-v1-baseline.json`
- `docs/backtest-workbench-v1-closure.md`
- `workbench_closure_golden_check.json`
- `workbench_closure_golden_check.zh.md`
- `examples/attbacktrader-ai-skill-entry-contract.json`
- `docs/attbacktrader-ai-skill-entry-contract.md`
- `examples/strategy-adaptation-v1-baseline.json`
- `docs/strategy-adaptation-v1-closure.md`
- `examples/strategy-adaptation-v1-ai-review-golden.json`
- `ai_review_golden_check.json`

## Active Non-Goals

- 不做自动参数调优或贝叶斯优化。
- 不做自动策略搜索。
- 不做自动牛市/震荡市/熊市识别。
- 不做自动策略切换。
- 不把报告层后验观察直接变成交易规则。
- 不在指标层计算多头趋势、突破、卖飞原因等决策语义。
- 不默认填充缺失 warmup、缺失证据或缺失未来窗口。
- 不继续在当前主线深挖 Exit Method Attribution；该方向已 parked 为未来 stage。
- 不宣称当前策略已经可上线或适合生产交易。

## AI First Read Order

| order | artifact | purpose |
|---:|---|---|
| 1 | `reports/run-catalog/run_catalog.json` | 先确定 run 是否存在、证据是否完整、可比较分组是什么。 |
| 2 | `reports/experiment-lifecycle/experiment_lifecycle.json` | 再确定实验链路卡在 draft、execution、comparison、attribution 还是 decision。 |
| 3 | `reports/experiment-decisions/experiment_decisions.json` | 涉及 compared/attributed experiment 时先看 explicit accepted/rejected/parked 决策。 |
| 4 | `reports/<run_id>/run_data_overview.json` | 读取单个 run 的复盘总览和 evidence_validation 状态。 |
| 5 | `reports/<run_id>/run_data_dictionary.json` | 确认字段含义和 artifact 下钻入口。 |
| 6 | `reports/<run_id>/review_packet.all.json` | 进入 AI review，引用样本和证据，不重跑策略。 |
| 7 | `comparison / market_type_summary / strategy_variant_validation` | 只有需要比较时才读取，不从单 run 直接推出策略结论。 |

## Next Allowed Slices

| slice | direction | purpose |
|---|---|---|
| AI Skill Contract Golden Check | AI 易用/封板校验 | 校验 Skill 文档是否保留 contract 的 first-read order、preflight gates 和输出推荐规则。 |
| AI Skill Dry-run Review Smoke | AI 可用性验证 | 用一个已知 run 按 Skill 入口完整复盘，检查证据引用、边界和三下一步输出是否稳定。 |
| Workbench Artifact Freshness Check | 工作台可用性 | 检查 run catalog、lifecycle、decisions、closure、AI contract 是否由最新命令生成，避免 AI 读到旧 artifact。 |

## Rules

- Workbench Closure Snapshot 是边界合同，不是策略收益评分。
- Snapshot 只记录已接受命令、artifact、测试、文档和非目标；不重跑回测。
- reports/ 下的本地 artifacts 可缺失；缺失时先生成 Run Catalog 和 Experiment Lifecycle。
- 新的深度分析必须先进入独立 stage 文档，不能在 Workbench V1 内无限扩展。
- accepted/rejected/parked 决策应作为实验生命周期的下一层闭环，不应由收益表现自动推断。
