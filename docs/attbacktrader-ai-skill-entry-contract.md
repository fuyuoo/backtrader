# ATTbacktrader AI Skill Entry Contract

- schema: `attbacktrader.ai_skill_entry_contract.v1`
- generated_on: `2026-06-05`
- skill_name: `attbacktrader-ai-review`
- objective: 让 AI 复盘从固定入口开始，按证据顺序读取，不重跑策略、不跳过证据门禁、不无限扩展分析方向。

## First Read Order

| order | artifact | required | when | command | stop rule |
|---:|---|---:|---|---|---|
| 1 | `reports/run-catalog/run_catalog.json` | True | 任何工作台复盘或 run 选择前。 | `att-run-catalog` | 如果目标 run 不存在，先报告缺失，不猜路径。 |
| 2 | `reports/experiment-lifecycle/experiment_lifecycle.json` | True | 涉及实验、变体、下一步建议或封板状态时。 | `att-experiment-lifecycle` | 如果链路缺少执行或比较，先说明当前阶段，不直接评价策略。 |
| 3 | `reports/experiment-decisions/experiment_decisions.json` | False | 涉及 compared/attributed experiment 的最终处理时。 | `att-experiment-decisions` | 如果 lifecycle 仍缺 decision，先生成或要求显式 decision input。 |
| 4 | `reports/<run_id>/run_data_overview.json` | True | 进入单个 run 复盘时。 | `att-run-data-overview --run-id <run_id>` | 如果 evidence_validation.status != ok，先报告证据问题。 |
| 5 | `reports/<run_id>/run_data_dictionary.json` | True | 需要解释字段或下钻 artifact 时。 | `att-run-data-dictionary --run-id <run_id>` | 如果字段含义不明，不自行推断。 |
| 6 | `reports/<run_id>/review_packet.all.json` | False | 需要 AI 复盘样本、finding 或候选实验时。 | `att-review-packet --run-dir reports/<run_id> --focus all` | 如果 packet 不存在，可生成；生成后再写 finding。 |
| 7 | `comparison / market_type_summary / strategy_variant_validation` | False | 需要跨 run、跨市场类型或策略变体比较时。 | `att-compare-runs / att-market-type-summary / att-strategy-variant-validation` | 没有比较 artifact 时，不从单 run 推出环境适配或策略优劣。 |

## Interaction Modes

| mode | direction | first reads | output |
|---|---|---|---|
| `workspace_status` | 工作台状态 | run_catalog, experiment_lifecycle, experiment_decisions, workbench_closure | 当前可用 run、证据缺口、实验缺口、最推荐下一步。 |
| `single_run_review` | 单 run 复盘 | run_catalog, run_data_overview, run_data_dictionary, review_packet | 证据状态、关键 findings、引用样本、三个下一步。 |
| `experiment_followup` | 实验治理 | experiment_lifecycle, experiment_decisions, review_findings, review_experiment_drafts | 当前阶段、缺失阶段、是否需要人工确认或决策记录。 |
| `strategy_variant_review` | 策略变体验证 | strategy_variant_validation, strategy_variant_attribution, experiment_lifecycle, experiment_decisions | 变体相对基线变化、证据引用、是否 parked/accepted/rejected 的建议。 |
| `sealed_stage_check` | 封板校验 | workbench_closure, workbench_closure_golden_check, strategy_adaptation_v1_baseline, golden_check | 是否越界、是否漏掉 non-goals、是否需要 golden check。 |

## Preflight Gates

- `catalog_exists`: 开始复盘前必须有 Run Catalog；没有就运行 att-run-catalog。
- `run_exists`: 用户给 run_id 时必须在 catalog 中找到；找不到先报告缺失。
- `evidence_ok`: 单 run 复盘必须先看 evidence_validation.status；非 ok 时停止策略结论。
- `lifecycle_stage`: 涉及实验时必须先读 Experiment Lifecycle；缺 execution/comparison/decision 时先说明缺口。
- `comparison_required`: 涉及适合什么环境、哪个策略更好时必须有 comparison 或 market_type_summary。
- `manual_confirmation`: 确认 RunPlan、执行变体、记录决策前必须有用户确认或已有 confirmation artifact。

## Allowed Actions

- 生成 run catalog: `att-run-catalog`
- 生成 experiment lifecycle: `att-experiment-lifecycle`
- 生成 experiment decision records: `att-experiment-decisions`
- 生成单 run overview: `att-run-data-overview --run-id <run_id>`
- 生成单 run dictionary: `att-run-data-dictionary --run-id <run_id>`
- 生成 AI review packet: `att-review-packet --run-dir reports/<run_id> --focus all`
- 生成 findings 和 samples: `att-review-findings / att-review-expand-samples`
- 生成 bounded experiment candidates/drafts: `att-review-experiment-candidates / att-review-experiment-drafts`
- 读取比较 artifact: `att-compare-runs / att-compare-environment-fit / att-strategy-variant-validation`
- 运行 sealed golden check: `att-review-golden-check`
- 运行 Workbench closure golden check: `att-workbench-closure-golden-check`

## Forbidden Actions

- 不在 review 中重跑策略，除非用户明确要求执行某个 RunPlan。
- 不抓取新行情数据来补 review 证据。
- 不从单个 run 直接推导策略适合的市场环境。
- 不把 post-exit rebound、卖飞、机会成本直接变成交易规则。
- 不默认填充缺失 warmup、缺失 evidence、缺失 future bars。
- 不自动确认 review draft 或 strategy variant draft。
- 不运行 planning draft YAML；只运行合法 RunPlan YAML。
- 不宣称策略可上线、可自动切换、可自动调参。

## Evidence Citation Rules

- 单 run 复盘 finding: finding_id + artifact path + 至少一个 trade_index 或 sample_index。
- 环境适配结论: environment_fit / environment_fit_comparison source + sample warning + representative trade refs。
- 市场类型或策略变体结论: market_type_id + baseline/variant summary paths + segment_id 或 run_id。
- 策略变体行为解释: strategy_variant_attribution source + segment_id + variant_run_id + sample run_id/trade_index。
- 实验下一步或决策: experiment_lifecycle chain_id + missing_stages + next_action_zh；已有决策时引用 experiment_decisions decision_id。

## Output Contract

- language: zh-CN
- max_next_actions: 3
- must_include: current_direction_zh, evidence_status_zh, bounded_findings, risk_or_caveat_zh, next_actions_with_direction_and_purpose, most_recommended_next_action_with_why

## Next Recommendation Contract

- 每个推荐必须标明 direction_zh。
- 每个推荐必须说明 purpose_zh。
- 必须明确一个 most_recommended，并说明 why_zh。
- 推荐必须来自 lifecycle 缺口、closure allowed slices 或用户当前目标，不要无限深化单一分析点。

## Rules

- AI Skill Entry Contract 是 Skill 的读取和输出边界，不是新的策略分析结果。
- 除非用户明确要求跑回测，AI review 默认只读取 persisted artifacts。
- 任何结论必须经过 evidence_validation、sample refs、run_id/trade_index 或 comparison source 引用。
- 当 Experiment Lifecycle 显示缺少 decision 时，下一步应先记录 accepted/rejected/parked，而不是继续调参。
- 每次完成一个功能后的推荐必须给出三个下一步，并标明方向、作用、最推荐项和原因。
