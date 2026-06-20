# Backtest Workbench System Map

本文档重新定义当前阶段主线。当前目标不是继续细化某个卖点、卖飞原因或
单一策略规则，而是把整个回测体系收敛成一个可复用、可验证、AI 易用的
Backtest Workbench。

## Current Purpose

当前版本的最终目的：

```text
配置一次策略和数据范围
  -> 跑出可重复回测
  -> 落盘完整证据链
  -> 自动校验证据一致性
  -> 生成 AI 可读复盘包
  -> 比较多次实验
  -> 给出下一轮有限验证方向
```

这不是策略收益优化系统，也不是自动调参系统。它首先是一个能长期支撑
策略研究的证据工作台。

## System Layers

| Layer | Owned By | Purpose | Current Status |
|---|---|---|---|
| Run Plan | `attbacktrader/config/` | 把 YAML 配置验证成不可变运行计划。 | Stable |
| Data Snapshot | `attbacktrader/data/` | 复用或拉取股票、指数、行业、停牌和涨跌停数据。 | Stable enough |
| Indicator Snapshot | `attbacktrader/features/` | 计算可复用数值指标，支持 D/W/M，对 warmup 保持缺失。 | Stable enough |
| Strategy Methods | `attbacktrader/strategies/` | 固定模板 + 绑定的 entry/exit/add-on/sizing 方法。 | Stable enough |
| Execution | `attbacktrader/engines/`, `constraints/`, `sizing/` | 执行回测、A 股约束、资金和仓位。 | Stable enough |
| Run Artifacts | `attbacktrader/reports/writer.py` | 落盘 run_plan、report、trades、audit、lifecycle、review 等证据。 | Stable |
| Evidence Validation | `attbacktrader/reports/evidence_validation.py` | 不重跑策略，检查 artifacts 之间的一致性。 | Stable |
| Review Workbench | `attbacktrader/reports/run_data.py`, `review_packet.py`, `ai_review.py` | 让人和 AI 能总览、查字典、下钻、批量复盘。 | Stable enough |
| Experiment Comparison | `comparison.py`, `environment_fit_comparison.py`, `market_type_summary.py` | 比较多个 run 或已知市场类型表现。 | Stable enough |
| Strategy Adaptation V1 | `strategy_adaptation_matrix.py`, `strategy_variant_attribution.py` | 从已知市场类型生成矩阵、变体验证和变体归因。 | Sealed |
| Workbench Navigation | `run_catalog.py`, `experiment_lifecycle.py`, `experiment_decisions.py`, `workbench_closure.py`, `workbench_closure_golden_check.py`, `ai_skill_contract.py` | 索引 run、证据状态、实验链路阶段、显式决策、封板合同、封板校验、AI 读取合同和下一步缺口。 | Stable enough |
| Closure Gate | `scripts/acceptance_smoke.py` | 跑 curated tests 和 sealed V1 AI review golden check。 | Stable |

## Evidence Flow

The evidence flow should remain downstream after execution:

```text
run.yaml
  -> RunPlan
  -> PreparedRunData + snapshots
  -> engine execution
  -> signal_audit / sizing_audit / execution_audit
  -> trades / equity_curve / positions
  -> trade_lifecycle / post_exit_analysis / trade_review
  -> evidence_validation
  -> run_data_overview / dictionary / drilldown / attribution_index
  -> review_packet / findings / sample_batch / brief / ai_review_result
  -> experiment_candidates / drafts / confirmed validation runs
  -> comparison / market_type_summary / strategy_adaptation_matrix
  -> experiment_decisions / lifecycle closure
```

The report layer must not recalculate indicators, infer missing checks, or turn
post-run observations into strategy rules.

## What Is Already Sealed

The following slices are now treated as sealed or stable enough for the current
workbench:

- MVP base at commit `d339bfc`.
- Chinese report renderer and standard report artifacts.
- Indicator snapshots, D/W/M alignment, and missing warmup semantics.
- Signal audit, sizing audit, execution audit, lifecycle, post-exit, and trade
  review artifacts.
- Evidence validation gate.
- AI review packet/findings/sample/brief/result workflow.
- Run data dictionary, overview, drilldown, batch drilldown, attribution index.
- Manual bull/range/bear market-type validation.
- Strategy Adaptation V1, sealed at commit `8c63fdf`.
- AI review golden check wired into `scripts/acceptance_smoke.py`.
- Run Catalog, Experiment Lifecycle, Experiment Decision Records, Workbench Closure Snapshot, Workbench Closure Golden Check, and AI Skill Entry Contract first slices.

## Current Non-Goal

Exit Method Attribution is not the active main line. It remains a designed
future analysis tool:

```text
docs/next-stage-exit-method-attribution.md
docs/exit-method-attribution-missing-evidence-check.md
```

Those documents are useful because they show that exit-method evidence exists,
but implementing that artifact now would push the project deeper into one
strategy's sell-side details. The current main line is broader: make the
workbench itself easy to run, inspect, compare, and hand to AI.

## Workbench Status And Remaining Gaps

### 1. Run Catalog

First slice status: implemented.

`att-run-catalog` writes `run_catalog.json` plus `run_catalog.zh.md`. It
answers:

- what runs exist;
- which runs are baseline, experiment, market segment, strategy variant, or
  review-only;
- which artifacts are present;
- which evidence checks passed;
- which runs are comparable.

It is an entry map, not a strategy analysis result.

### 2. Experiment Lifecycle

The system has candidates, drafts, confirmations, generated runs, comparisons,
and sealed baselines. The first lifecycle view now shows:

```text
finding
  -> candidate
  -> draft
  -> confirmed RunPlan
  -> executed run
  -> comparison
  -> accepted / rejected / parked decision
```

First slice status: implemented.

`att-experiment-lifecycle` writes `experiment_lifecycle.json` plus
`experiment_lifecycle.zh.md`. It reads review candidates/drafts/confirmations,
strategy variant drafts/manifests/validation/attribution, and Run Catalog when
available. It then reports chain state, executed run evidence status, missing
stages, and bounded next actions. It does not rerun backtests, judge strategy
quality, or auto-tune parameters.

### 3. Closure Snapshot

`acceptance_smoke.py` is now a good gate, and the first machine-readable
closure snapshot for the whole workbench now exists:

```text
examples/backtest-workbench-v1-baseline.json
docs/backtest-workbench-v1-closure.md
```

First slice status: implemented.

The current Workbench Closure Snapshot records:

- accepted commands;
- accepted artifact names;
- accepted test counts;
- sealed docs;
- active non-goals;
- required local report paths when available.

### 4. AI Skill Entry Contract

First slice status: implemented.

The AI review skill can inspect run artifacts, and the workbench now has one
first-page contract for AI:

```text
Given a run id or catalog entry, start here, then read these artifacts, then
produce this shape of answer, then suggest only bounded next actions.
```

`att-ai-skill-entry-contract` writes:

```text
examples/attbacktrader-ai-skill-entry-contract.json
docs/attbacktrader-ai-skill-entry-contract.md
```

The local `attbacktrader-ai-review` Skill now starts from this contract,
Run Catalog, Experiment Lifecycle, Experiment Decision Records, run overview,
dictionary, and review packet.

### 5. Experiment Decision Records

First slice status: implemented.

`att-experiment-decisions` writes:

```text
reports/experiment-decisions/experiment_decisions.json
reports/experiment-decisions/experiment_decisions.zh.md
```

The versioned input lives at:

```text
examples/experiment-decisions/workbench-v1-strategy-variant-decisions.json
```

It records explicit `accepted / rejected / parked` outcomes only. It does not
infer decisions from returns. Current Workbench V1 strategy-variant chains have
`decision_gap_count=0`: one bull-market variant is rejected, and range/bear
variants are parked.

### 6. Workbench Closure Golden Check

Strategy Adaptation V1 has a deterministic AI review golden check. Workbench V1
now has a deterministic closure golden check too.

First slice status: implemented.

`att-workbench-closure-golden-check` reads:

```text
examples/backtest-workbench-v1-baseline.json
docs/backtest-workbench-v1-closure.md
```

and writes:

```text
reports/workbench-closure-golden-check/workbench_closure_golden_check.json
reports/workbench-closure-golden-check/workbench_closure_golden_check.zh.md
```

It fails when the closure Markdown omits accepted commands, artifact groups,
non-goals, verification counts, rules, next allowed slices, or AI first-read
order from the baseline.

## Workbench Closure Target

The current closure target is:

```text
Backtest Workbench V1 Closure
```

First slice status: implemented.

The accepted baseline is:

```text
examples/backtest-workbench-v1-baseline.json
docs/backtest-workbench-v1-closure.md
```

It is achieved for the current V1 boundary because:

- `python scripts\acceptance_smoke.py` passes;
- one command or artifact can list the accepted run catalog;
- a run catalog entry can point AI to overview, dictionary, evidence validation,
  review packet, and comparison outputs;
- experiment lifecycle state is visible without reading every generated YAML;
- sealed Strategy Adaptation V1 remains comparable and protected by golden
  check;
- Exit Method Attribution and similar deep analysis tools are parked until the
  workbench lifecycle needs them.

## Completed Closure Slices

### Slice 1: Run Catalog

Add a persisted run catalog artifact that indexes known runs and their roles.
This is the highest-leverage next step because it gives both humans and AI one
entry point into the current artifact sprawl.

Expected shape:

```text
att-run-catalog
  -> run_catalog.json
  -> run_catalog.zh.md
```

First slice status: implemented.

The current command indexes persisted run directories under `reports/`, reads
market-segment and strategy-variant manifests when provided, identifies run
roles, checks required artifact presence, summarizes evidence-validation status,
and records manifest-derived comparison groups. It is an entry map, not a
strategy analysis result.

### Slice 2: Experiment Lifecycle View

Connect review findings, candidates, drafts, generated runs, comparisons, and
closure decisions into one lifecycle view. This keeps future work bounded.

Expected shape:

```text
experiment_lifecycle.json
experiment_lifecycle.zh.md
```

First slice status: implemented.

The current artifact shows review experiment chains that are still draft or
confirmed-but-unexecuted, plus strategy variant chains that have generated
segment runs, executed evidence-ok runs, validation comparison, and one bull
market attribution drill-down. Explicit accepted/rejected/parked decision
records now close the compared/attributed strategy-variant chains.

### Slice 3: Workbench Closure Snapshot

Create a versioned snapshot similar to Strategy Adaptation V1 baseline, but for
the whole workbench.

Expected shape:

```text
examples/backtest-workbench-v1-baseline.json
docs/backtest-workbench-v1-closure.md
```

First slice status: implemented.

The current baseline records `run_count=24`, `chain_count=9`, and
`decision_gap_count=0`. The remaining gap is not more report depth; it is a
deterministic closure golden check that prevents the workbench boundary from
drifting.

### Slice 4: AI Skill Entry Contract

Direction: AI 易用。

Purpose: 把 Run Catalog、Experiment Lifecycle、Experiment Decision Records、
run_data_overview、run_data_dictionary、review_packet 的读取顺序固化成 Skill
输入合同，让 AI 复盘从同一个入口开始。

First slice status: implemented.

### Slice 5: Experiment Decision Records

Direction: 实验治理。

Purpose: 为 compared/attributed experiment 增加
`accepted / rejected / parked` 决策 artifact，让生命周期真正闭环。

First slice status: implemented.

## Recommended Next Slices

### Slice 7: AI Skill Contract Golden Check

Direction: AI 易用/封板校验。

Purpose: 校验本地 Skill 文档是否保留 entry contract 的 first-read order、
preflight gates、forbidden actions 和三下一步推荐规则。

### Slice 8: AI Skill Dry-run Review Smoke

Direction: AI 可用性验证。

Purpose: 用一个已知 run 按 Skill 入口完整复盘，检查证据引用、边界和三下一步输出是否稳定。

### Slice 9: Workbench Artifact Freshness Check

Direction: 工作台可用性。

Purpose: 检查 run catalog、lifecycle、decisions、closure、AI contract 是否由最新命令生成，避免 AI 读到旧 artifact。

## Current Recommendation

Do not implement `att-exit-method-attribution` now.

Run Catalog, Experiment Lifecycle, and Experiment Decision Records are now the
active workbench entry points. Use Run Catalog first to find runs and evidence
status; use Experiment Lifecycle next to see whether an experiment chain is
drafted, confirmed, executed, compared, attributed, or decided; use Experiment
Decision Records to avoid re-opening already rejected or parked directions.

Reason:

- It improves the whole system, not one strategy detail.
- It gives AI a stable first entry point.
- It helps compare baseline, sized, filter, add-on, market segment, and variant
  runs without manual path hunting.
- It keeps future work bounded by showing exactly which lifecycle stage or
  closure check is missing.

Most recommended next slice: AI Skill Contract Golden Check.

Why:

- Run Catalog answers "what runs exist".
- Experiment Lifecycle answers "where each experiment is stuck".
- Experiment Decision Records closes compared/attributed experiment chains.
- Workbench Closure Snapshot answers "what is accepted as Backtest Workbench V1
  and what must not keep expanding".
- Workbench Closure Golden Check now protects the closure doc against baseline
  drift.
- AI Skill Entry Contract turns that map into repeatable AI behavior.
- AI Skill Contract Golden Check is now the next highest-leverage guard because
  the remaining drift risk is whether the Skill keeps following the contract.
