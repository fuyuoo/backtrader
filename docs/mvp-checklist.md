# ATTbacktrader MVP Closure Checklist

This document defines the closure boundary for the first usable version of
ATTbacktrader. The goal is a stable, data-driven backtesting framework skeleton,
not a full research platform or parameter optimization system.

## Closure Goal

The MVP is ready when a user can:

- define one immutable YAML run plan;
- fetch or reuse local market snapshots;
- compute indicator snapshots separately from raw data;
- run a deterministic portfolio backtest through the configured engine;
- persist execution, position, trade, snapshot, and report artifacts;
- review a lightweight human-readable report;
- identify first-pass strategy-fit environments and actual trade PnL contribution from persisted evidence;
- rerun a curated regression suite and a real Tushare smoke check.

## Completed MVP Capabilities

| Area | Status | Closure Criteria |
|---|---|---|
| Independent business package | Done | New framework code lives under `attbacktrader/`; upstream `backtrader/` remains the engine library. |
| Run plan parsing | Done | YAML is validated into an immutable `RunPlan` before execution. |
| Configuration switches | Done | Data refresh, A-share constraints, analysis sections, engine, and output persistence are controlled by config. |
| Data provider abstraction | Done | Runtime code depends on `RunDataProvider`; Tushare is the current provider implementation. |
| Tushare token handling | Done | Token is read from `.secrets/tushare_token.txt` and is not committed. |
| Stock daily snapshots | Done | Stock daily bars are stored as qfq Parquet snapshots by default. |
| Tradable series model | Done | Stocks, indexes, and industry indexes can be declared as tradable series without coupling strategy logic to a stock-only type. |
| Index snapshots | Done | Benchmark and decision index series can be fetched and stored. |
| Shenwan industry snapshots | Done | Shenwan classification, membership, and industry index bars are snapshot-backed. |
| Tradability snapshots | Done | Suspension and daily limit state are stored separately for A-share constraints. |
| Indicator snapshots | Done | KDJ indicators are calculated into separate snapshots and joined by `(symbol, trade_date)` at runtime. |
| Daily to weekly/monthly resampling | Done | Daily OHLCV bars can be deterministically aggregated to weekly and monthly windows. |
| Strategy template | Done | `Trend Template V1` is the first fixed code-backed template. |
| Strategy method binding | Done | Entry, profit-taking, stop-loss, add-on, and sizing choices are selected one-to-one from registered bindings. |
| MVP trading rule | Done | KDJ J < 13 enters, KDJ J > 100 exits profit, and fixed 5% stop-loss exits loss. |
| Add-on execution slice | Done | Optional `kdj_oversold_add_on` can emit `ADD_ON` while already holding, reuse sizing, and update position average cost in both business and backtrader engines. |
| Portfolio backtest | Done | Multi-symbol portfolio runs share one broker cash account through the backtrader adapter. |
| Business engine path | Done | The business runner keeps deterministic portfolio cash, position value, equity curve, and position snapshots without broker-specific costs. |
| Backtrader adapter | Done | Prepared data, strategy methods, broker settings, and constraints are mapped into backtrader. |
| A-share constraints | Done | Board lot, cash, T+1, suspension, limit-up buy block, and limit-down sell block are covered. |
| Broker costs | Done | Commission, stamp tax, transfer fee, and slippage are applied through the adapter. |
| Execution ledger | Done | Equity curve and position snapshots are emitted by the backtrader path. |
| Execution audit | Done | Submitted, accepted, completed, failed, and rejected order events are persisted. |
| Standard report model | Done | Returns, risk, trade quality, portfolio behavior, benchmark comparison, industry attribution, market input display, scenario fit, and execution costs are represented. |
| Markdown report | Done | `report.md` is generated beside `report.json` for first-pass review. |
| Run artifacts | Done | `run_plan.json`, `result.json`, `report.json`, `report.md`, `report.zh.md`, `trades.json`, `signal_audit.json`, `sizing_audit.json`, `result_diagnostics.json`, `trade_lifecycle.json`, `trade_lifecycle.zh.md`, `trade_review.json`, `trade_review.zh.md`, `environment_fit.json`, `environment_fit.zh.md`, `strategy_environment_profile.json`, `strategy_environment_profile.zh.md`, `post_exit_analysis.json`, `post_exit_analysis.zh.md`, `evidence_validation.json`, `equity_curve.json`, `positions.json`, `execution_audit.json`, and `snapshots.json` are persisted. |
| Run catalog | Done | `att-run-catalog` writes `run_catalog.json` plus `run_catalog.zh.md`, indexing known runs, roles, artifact presence, evidence-validation status, manifest-derived comparison groups, and AI next-read commands without rerunning backtests. |
| Experiment lifecycle | Done | `att-experiment-lifecycle` writes `experiment_lifecycle.json` plus `experiment_lifecycle.zh.md`, linking review candidates/drafts/confirmations, strategy variant generated runs, Run Catalog execution status, validation comparisons, attribution drill-downs, missing stages, and bounded next actions without rerunning backtests. |
| Experiment decision records | Done | `att-experiment-decisions` writes `experiment_decisions.json` plus `experiment_decisions.zh.md` from explicit accepted/rejected/parked inputs, closing compared/attributed experiment chains without deriving decisions from returns. |
| Workbench closure snapshot | Done | `att-workbench-closure-snapshot` writes `examples/backtest-workbench-v1-baseline.json` and `docs/backtest-workbench-v1-closure.md`, recording accepted commands, artifact groups, verification counts, sealed docs, active non-goals, AI read order, and allowed next slices. |
| Workbench closure golden check | Done | `att-workbench-closure-golden-check` writes `workbench_closure_golden_check.json` plus `workbench_closure_golden_check.zh.md`, failing when the closure Markdown omits baseline commands, artifact groups, non-goals, verification counts, rules, next slices, or AI read order. |
| AI Skill entry contract | Done | `att-ai-skill-entry-contract` writes `examples/attbacktrader-ai-skill-entry-contract.json` and `docs/attbacktrader-ai-skill-entry-contract.md`, fixing AI first-read order, preflight gates, allowed/forbidden actions, evidence citation rules, output shape, and three-next-action recommendation rules. |
| Evidence validation | Done | `evidence_validation.json` checks signal, sizing, execution rejection reasons, trade, diagnostics, equity, report, post-exit, and trade-review consistency without rerunning strategies or recalculating indicators. |
| Lifecycle attribution | Done | `result_diagnostics.json` now groups successful add-on intents into the completed trade lifecycle between primary entry and exit, then summarizes winning-vs-losing add-on evidence and feeds concise add-on entry-point detail rows in Markdown. |
| Trade lifecycle artifact | Done | `trade_lifecycle.json` stores each completed trade's entry/add-on/exit timeline with signal evidence, linked execution events, and filter indexes. |
| Trade lifecycle Chinese review | Done | `trade_lifecycle.zh.md` provides a concise Chinese review surface over the lifecycle artifact without expanding every factor. |
| Unified trade review | Done | `trade_review.json` and `trade_review.zh.md` combine lifecycle events, sold-too-early profile grouping, stop-loss rebound attribution, opportunity/block opportunity-cost attribution, and add-on entry-point follow-up from existing signal, execution, post-exit, and snapshot evidence. |
| Environment fit and PnL contribution | Done | `environment_fit.json` and `environment_fit.zh.md` consume `trade_review` and `trade_lifecycle` to group entry environments by win rate, average return, actual completed-order net PnL, and return on entry value without rerunning strategies or filling missing checks. The Chinese report now starts with conclusion candidates and sample-size warnings. |
| Environment fit comparison | Done | `att-compare-environment-fit` reads existing `environment_fit.json` artifacts and writes `environment_fit_comparison.json` plus `environment_fit_comparison.zh.md` to compare best-environment stability, low-sample risk, and common-environment deltas. |
| Strategy environment profile | Done | `strategy_environment_profile.json` and `strategy_environment_profile.zh.md` convert persisted environment-fit evidence into suitable, avoid, and uncertain environment candidates with evidence strength, reasons, and trade sample refs for AI-first review. |
| AI review packet | Done | `att-review-packet` reads persisted run artifacts and writes `review_packet.<focus>.json` plus `review_packet.<focus>.zh.md` with an `ai_contract`, source artifact pointers, summaries, capped samples, and environment-fit/profit-contribution context for Skill-assisted review. |
| AI review findings | Done | `att-review-findings` writes `review_findings.<focus>.json` plus `review_findings.<focus>.zh.md` from a review packet with citation-ready finding IDs, evidence refs, sample refs, caveats, and next checks. |
| Review sample drill-down | Done | `att-review-sample` writes `review_sample.<kind>.<id>.json` plus `review_sample.<kind>.<id>.zh.md`, linking one trade, opportunity, or add-on sample back to lifecycle, post-exit, signal, execution, and closed-trade evidence. |
| Review sample batch | Done | `att-review-expand-samples` expands finding sample refs into `review_sample_batch.<focus>.json` plus optional individual sample packets for Skill-assisted review. |
| AI review brief | Done | `att-review-brief` writes `review_brief.<focus>.json` plus `review_brief.<focus>.zh.md`, combining findings, sample summaries, evidence rules, environment-fit first-page summary, and an expected Skill output schema. |
| AI review result | Done | `att-review-result` persists `ai_review_result.<focus>.json` plus `ai_review_result.<focus>.zh.md` from a review brief, preserving claim, evidence, sample, risk, and next-check fields. |
| AI review golden check | Done | `att-review-golden-check` reads an AI review JSON or Markdown plus a golden fixture and writes `ai_review_golden_check.json` plus `ai_review_golden_check.zh.md`, failing when required sealed-stage claims, metrics, evidence refs, sample refs, or `must_not_claim` boundaries are violated. |
| Review experiment candidates | Done | `att-review-experiment-candidates` writes validation candidates from findings and expanded samples, including environment-fit sample-stability validation, without mutating run plans or tuning parameters. |
| Review experiment drafts | Done | `att-review-experiment-drafts` writes a draft manifest and individual YAML planning drafts, including environment-fit comparison drafts, that require manual confirmation before conversion into legal RunPlan YAML. |
| Review experiment confirmation | Done | `att-review-experiment-confirm --confirm` converts exactly one manually accepted draft into a validated legal RunPlan YAML while keeping review metadata in a confirmation manifest. |
| Post-exit follow-up | Done | `post_exit_analysis.json` and `post_exit_analysis.zh.md` look up configured windows after each completed trade's exit, attach exit-day evidence, rank sold-too-early samples, group sold-too-early rates by exit checks such as stop hit, KDJ overheated, symbol MA, market trend, or industry KDJ context, and summarize configurable rebound threshold layers. Missing future bars remain missing, not default-filled. |
| Correctness golden samples | Done | Focused fixtures pin indicator warmup, weekly/monthly alignment, buy/add-on/sell lifecycle grouping, execution-cost audit totals, and missing-attribution semantics. |
| Expanded attribution factors | Done | Entry attribution includes symbol MA20/MA25/MA60 values plus decision-layer checks such as price above MA60, MA20 above MA60, and symbol MA bullish trend. |
| Execution constraint golden samples | Done | Focused fixtures validate board-lot, cash, suspension, limit-up buy, limit-down sell, and T+1 rejection evidence. |
| Run comparison artifacts | Done | `att-compare-runs` reads persisted run artifacts and writes `comparison.json` plus `comparison.zh.md` for baseline/filter/sizing/add-on comparisons, including rejection reason counts such as `BOARD_LOT_TOO_SMALL`. |
| Real-run regression baseline | Done | `att-validate-run-regression` compares persisted real-run artifacts with `examples/real-run-regression-baseline.json` and writes `run_regression.json` plus `run_regression.zh.md`, including execution rejection reason metrics. |
| Attribution filter experiments | Done | `att-generate-attribution-filter-experiments` expands a matrix into validated YAML variants for result-driven filter experiments, including symbol MA trend and MA60 filter variants. |
| Manual market segment validation drafts | Done | `att-generate-market-segment-runs` consumes a manually sourced market-segment catalog and writes legal RunPlan YAMLs plus a manifest, without code-based market-state detection. |
| Manual market type validation summary | Done | A manually sourced catalog groups bull, range, and bear market periods with at least three segments each; `att-market-type-summary` reads persisted artifacts and writes `market_type_summary.json` plus `market_type_summary.zh.md` without producing strategy-switching conclusions. |
| Strategy adaptation matrix | Done | `att-strategy-adaptation-matrix` consumes known market-type summaries and each segment's persisted trade lifecycle/post-exit artifacts, then writes `strategy_adaptation_matrix.json` plus `strategy_adaptation_matrix.zh.md` with market-type fit, winning entry factors, losing entry factors, sold-too-early entry factors, and `run_id`/`trade_index` sample refs without detecting market type or recalculating indicators. |
| Strategy adaptation drill-down and variant drafts | Done | `att-strategy-adaptation-drilldown` expands one matrix factor into review sample packets, while `att-strategy-variant-drafts` writes manually confirmable bull/range/bear strategy-variant validation drafts without implementing market-type recognition or automatic strategy switching. |
| Strategy variant execution validation | Done | `att-generate-strategy-variant-runs` converts confirmed matrix-derived drafts into legal segment RunPlan YAMLs, and `att-strategy-variant-validation` compares baseline versus variant `market_type_summary.json` artifacts by market type without automatic tuning or strategy switching. |
| Strategy variant attribution drill-down | Done | `att-strategy-variant-attribution` compares paired baseline and variant segment artifacts for one market type, then reports exit-method shifts, holding-period compression, same-symbol re-entry density, average-win compression, and sample refs from `trade_lifecycle.json`. |
| Acceptance script | Done | `scripts/acceptance_smoke.py` runs the curated ATTbacktrader regression suite, the sealed Strategy Adaptation V1 AI review golden check, and optional real Tushare smoke. |
| Documentation | Done | `README.md`, `CONTEXT.md`, ADRs, architecture guide, blueprint, and this checklist define current behavior and boundaries. |

## Accepted MVP Limitations

These are acceptable for first-version closure because the goal is to stabilize
the framework boundary before expanding research depth.

| Limitation | Current Choice | Later Direction |
|---|---|---|
| One strategy template | Only `Trend Template V1` is implemented. | Add more templates after bindings and report contracts remain stable. |
| One-to-one method selection | Each run selects exactly one entry, profit-taking, stop-loss, add-on, and sizing method. | Add richer composition only after method semantics are explicit. |
| Limited indicators | KDJ, MACD, MA20, MA25, MA60, RSI14, and ATR14 are calculated indicator snapshots. Method bindings can request D/W/M timeframes. | Add more numeric indicators through `features/`; keep composite decisions in strategy methods. |
| Sizing/Risk slices | `equal_weight` keeps fixed `execution.stake` by default and can optionally cap max holdings, max position value, total exposure, risk-group exposure, cash reserve, turnover, rebalance interval, and ATR risk. | Add richer rebalance orders and portfolio construction later. |
| Report metrics are first-slice | Current report covers cumulative return, max drawdown, trade quality, attribution, market input display, scenario fit, portfolio behavior, and execution costs. | Add annualized return, volatility, Sharpe, Calmar, drawdown duration, turnover, and net trade PnL metrics later. |
| Markdown report only | `report.md` is intentionally lightweight. | Add HTML or richer report presentation after report fields settle. |
| Tushare-only provider | Provider boundary exists, but only Tushare is implemented. | Add local/offline or other provider implementations without changing strategy code. |
| Snapshot metadata is file-based | Time-series snapshots are Parquet; metadata SQLite is not required for MVP. | Add SQLite metadata when lookup complexity justifies it. |
| No large historical CI | Tests use deterministic fixtures and focused smoke checks. | Add larger benchmark datasets outside fast CI when needed. |

## Explicitly Out Of Scope For MVP

- Bayesian parameter tuning.
- Tuning set and test set orchestration.
- Automatic strategy search.
- Arbitrary global composition of buy/sell rules.
- AI-generated scenario conclusions.
- Live trading or broker integration.
- Intraday data.
- Full production portfolio construction.
- Full HTML dashboard or visualization layer.

## Closure Verification

Run the curated business regression suite:

```powershell
.\.venv\Scripts\python.exe scripts\acceptance_smoke.py
```

Expected result for current HEAD:

```text
231 passed
Strategy Adaptation V1 golden check summary
status: ok
check_count: 72
failed_count: 0
Workbench Closure golden check summary
status: ok
check_count: 124
failed_count: 0
Acceptance smoke passed.
```

At the MVP closure commit `d339bfc`, the curated suite contained 81 tests.
Post-MVP slices added the Chinese report renderer, MACD indicator,
method-binding coverage, D/W/M indicator requirement alignment, parameterized
strategy methods, MA/RSI/ATR numeric indicators, signal audit artifacts,
IndicatorSpec planning, indicator snapshot tail overwrite/append support,
indicator snapshot metadata, rolling state continuation for KDJ/MACD/RSI/ATR,
tradable bar snapshot range discovery/reuse, MA+MACD composite decision
methods, per-condition signal audit checks, indicator snapshot range discovery,
strategy golden cases for MA+MACD intent sequences, sizing/risk V1,
prepared-data quality issues, and snapshot provenance artifacts, so current
HEAD reports 135 passed. Result-driven expanded baseline/sized examples,
their configuration validation, and market-temperature input-only reporting
left the suite at 136 passed. Result diagnostics coverage increased the
suite to 137 passed. Entry attribution factor declarations, MA25 support,
market/industry/symbol entry evidence, and winning-vs-losing attribution
contrast increased the current suite to 140 passed. Configurable attribution
factor selection, entry-attribution filters, exit attribution summaries, add-on
signal-count outputs, and the attribution-filter example are now part of the
post-MVP result-driven workflow and increased the current suite to 144 passed.
Run comparison artifacts, attribution-filter experiment generation, optional
real add-on execution, and focused add-on execution tests increased the current
suite to 149 passed.
Evidence validation and cross-artifact correctness checks increased the current
suite to 152 passed. Successful add-on lifecycle attribution, correctness
golden samples, and writer persistence coverage increased the current suite to
156 passed. Trade lifecycle artifacts, expanded A-share rejection evidence
validation, and real-run regression baseline checks increased the current suite
to 163 passed. Lifecycle indexes, expanded symbol MA attribution factors, and
execution constraint golden samples increased the current suite to 171 passed.
Post-exit follow-up analysis, lifecycle Chinese review Markdown, rejection
reason comparison/regression metrics, and expanded attribution-filter matrix
coverage increased the current suite to 173 passed.
Configurable post-exit windows, exit-day evidence capture, and post-exit
factor grouping increased the current suite to 175 passed.
Exit intent shared attribution context, ranked sold-too-early Markdown samples,
and add-on entry-point detail rendering increased the current suite to
176 passed.
Unified trade review artifacts and opportunity/block attribution coverage
increased the current suite to 177 passed.
Trade-review add-on entry-point follow-up and downstream review validation
increased the current suite to 178 passed.
AI-friendly review packet generation and CLI coverage increased the current
suite to 180 passed.
AI review findings and sample drill-down packets increased the current suite to
183 passed.
AI review sample batching, Skill-ready review brief generation, and review
experiment candidates increased the current suite to 186 passed.
Persisted AI review results, review experiment YAML drafts, and their CLI
coverage increased the current suite to 189 passed.
Run data dictionary, overview, single/batch drill-down, attribution-field index,
and closure-boundary tooling increased the current suite to 195 passed.
Environment fit reporting, completed-order PnL contribution grouping, writer
persistence, and CLI coverage increased the current suite to 197 passed.
Environment-fit conclusion rendering, sample-size warnings, and review-packet
environment-fit inputs increased the current suite to 198 passed.
Environment-fit comparison artifacts and CLI coverage increased the current
suite to 200 passed.
Structured AI review results with environment-comparison evidence and review
experiment confirmation into validated RunPlan YAML increased the current suite
to 202 passed.
Manual bull/range/bear market type validation, long-history validation stock
universe, generated market-segment RunPlans, market-type summary artifacts,
and Tushare index OHLC normalization increased the curated acceptance suite to
208 passed.
The strategy adaptation matrix now reverse-looks up completed trades into
entry-time evidence and post-exit follow-up across known market types, raising
the curated acceptance suite to 210 passed.
Strategy adaptation drill-down and strategy variant draft generation connect the
matrix to AI review samples and bounded validation plans, raising the curated
acceptance suite to 212 passed. Legal strategy-variant segment RunPlan
generation and baseline-vs-variant market-type validation comparison increased
the curated acceptance suite to 214 passed. Strategy-variant attribution
drill-down for paired baseline/variant market segments increased the curated
acceptance suite to 216 passed. AI review golden-check coverage for sealed V1
reviews increased the curated acceptance suite to 218 passed. The acceptance
script now runs the sealed Strategy Adaptation V1 golden check as a default
closure gate, and its focused script test increased the curated suite to
219 passed. Run Catalog indexing and CLI coverage increased the curated suite
to 221 passed. Experiment Lifecycle indexing and CLI coverage increased the
curated suite to 223 passed. Workbench Closure Snapshot and CLI coverage
increased the curated suite to 225 passed. AI Skill Entry Contract and CLI
coverage increased the curated suite to 227 passed. Experiment Decision
Records and lifecycle decision-stage coverage increased the curated suite to
229 passed. Workbench Closure Golden Check and CLI failure-path coverage
increased the curated suite to 231 passed. The acceptance script now also runs
Workbench Closure Golden Check as a default closure gate. The full repository suite currently reports 315
passed.

Run the same suite plus real Tushare data:

```powershell
.\.venv\Scripts\python.exe scripts\acceptance_smoke.py --with-tushare
```

Expected first smoke artifacts:

```text
reports/tushare-smoke-2024q1/
  report.json
  report.md
  report.zh.md
  signal_audit.json
  sizing_audit.json
  result_diagnostics.json
  trade_lifecycle.json
  trade_lifecycle.zh.md
  trade_review.json
  trade_review.zh.md
  environment_fit.json
  environment_fit.zh.md
  strategy_environment_profile.json
  strategy_environment_profile.zh.md
  post_exit_analysis.json
  post_exit_analysis.zh.md
  evidence_validation.json
  execution_audit.json
  equity_curve.json
  positions.json
  snapshots.json
```

The current accepted real Tushare smoke result is:

| Field | Value |
|---|---:|
| run_id | `tushare-smoke-2024q1` |
| engine | `backtrader` |
| final_value | `1000836.17205757` |
| cumulative_return | `0.0008361720575700282` |
| completed_orders | `8` |

## First Files To Review

1. `README.md`
2. `examples/run-tushare-smoke.yaml`
3. `examples/run-tushare-expanded-baseline.yaml`
4. `examples/run-tushare-expanded-sized.yaml`
5. `examples/run-tushare-expanded-add-on.yaml`
6. `examples/attribution-filter-experiments.yaml`
7. `reports/tushare-smoke-2024q1/report.md`
8. `reports/tushare-smoke-2024q1/execution_audit.json`
9. `reports/tushare-smoke-2024q1/evidence_validation.json`
10. `reports/tushare-expanded-add-on-2023-2024/result_diagnostics.json`
11. `reports/tushare-expanded-add-on-2023-2024/trade_lifecycle.json`
12. `reports/tushare-expanded-add-on-2023-2024/trade_lifecycle.zh.md`
13. `reports/tushare-expanded-add-on-2023-2024/environment_fit.zh.md`
14. `reports/tushare-expanded-add-on-2023-2024/trade_review.zh.md`
15. `reports/tushare-expanded-add-on-2023-2024/trade_review.json`
16. `reports/tushare-expanded-add-on-2023-2024/review_packet.all.zh.md`
17. `reports/tushare-expanded-add-on-2023-2024/review_packet.all.json`
18. `reports/tushare-expanded-add-on-2023-2024/review_findings.all.zh.md`
19. `reports/tushare-expanded-add-on-2023-2024/review_findings.all.json`
20. `reports/tushare-expanded-add-on-2023-2024/review_sample_batch.all.zh.md`
21. `reports/tushare-expanded-add-on-2023-2024/review_brief.all.zh.md`
22. `reports/tushare-expanded-add-on-2023-2024/ai_review_result.all.zh.md`
23. `reports/tushare-expanded-add-on-2023-2024/review_experiment_candidates.all.zh.md`
24. `examples/generated-review-experiments/tushare-expanded-add-on-2023-2024/review_experiment_drafts.all.zh.md`
25. `reports/tushare-expanded-add-on-2023-2024/review_sample.add_on.1.zh.md`
26. `reports/tushare-expanded-add-on-2023-2024/post_exit_analysis.zh.md`
27. `examples/real-run-regression-baseline.json`
28. `reports/real-run-regression-2023-2024/run_regression.zh.md`
29. `reports/comparison-tushare-expanded-baseline-2023-2024__vs__tushare-expanded-sized-2023-2024__vs__tushare-attribution-filter-2023-2024__vs__tushare-expanded-add-on-2023-2024/comparison.zh.md`
30. `reports/environment-fit-comparison-tushare-expanded-baseline-2023-2024__vs__tushare-expanded-sized-2023-2024__vs__tushare-attribution-filter-2023-2024__vs__tushare-expanded-add-on-2023-2024/environment_fit_comparison.zh.md`
31. `examples/generated-review-experiments/tushare-expanded-add-on-2023-2024/confirmed/environment_fit_sample_stability.run.yaml`
32. `examples/generated-review-experiments/tushare-expanded-add-on-2023-2024/confirmed/review_experiment_confirmed.environment_fit_sample_stability.zh.md`
33. `docs/first-version-blueprint.md`
34. `docs/architecture/project-structure.md`
35. `docs/architecture/evidence-chain.md`
36. `docs/run-review-workbench-closure.md`
37. `examples/manual-market-segments/a-share-market-type-validation.yaml`
38. `examples/run-tushare-market-type-add-on.yaml`
39. `examples/generated-market-segment-runs/tushare-market-type-add-on/market_segment_run_manifest.zh.md`
40. `reports/market-type-summary-tushare-market-type-add-on/market_type_summary.zh.md`
41. `docs/strategy-adaptation-stage.md`
42. `reports/strategy-adaptation-matrix-tushare-market-type-add-on/strategy_adaptation_matrix.zh.md`
43. `reports/strategy-adaptation-drilldown-tushare-market-type-add-on-bull/strategy_adaptation_drilldown.zh.md`
44. `reports/strategy-variant-drafts-tushare-market-type-add-on/strategy_variant_drafts.zh.md`
45. `examples/generated-strategy-variant-runs/tushare-market-type-add-on/strategy_variant_run_manifest.zh.md`
46. `reports/strategy-variant-validation-tushare-market-type-add-on/strategy_variant_validation.zh.md`
47. `reports/strategy-variant-attribution-tushare-market-type-add-on-bull/strategy_variant_attribution.zh.md`
48. `docs/strategy-adaptation-v1-closure.md`
49. `examples/strategy-adaptation-v1-baseline.json`
50. `docs/next-stage-exit-method-attribution.md`
51. `docs/strategy-adaptation-v1-ai-review.md`
52. `examples/strategy-adaptation-v1-ai-review-golden.json`
53. `reports/strategy-adaptation-v1-ai-review-golden-check/ai_review_golden_check.zh.md`
54. `docs/exit-method-attribution-missing-evidence-check.md`
55. `docs/backtest-workbench-system-map.md`
56. `reports/run-catalog/run_catalog.zh.md`
57. `reports/experiment-lifecycle/experiment_lifecycle.zh.md`
58. `examples/experiment-decisions/workbench-v1-strategy-variant-decisions.json`
59. `reports/experiment-decisions/experiment_decisions.zh.md`
60. `examples/backtest-workbench-v1-baseline.json`
61. `docs/backtest-workbench-v1-closure.md`
62. `reports/workbench-closure-golden-check/workbench_closure_golden_check.zh.md`
63. `examples/attbacktrader-ai-skill-entry-contract.json`
64. `docs/attbacktrader-ai-skill-entry-contract.md`

## Current Post-MVP Direction

The current main line is Backtest Workbench system closure, defined in
`docs/backtest-workbench-system-map.md`. The goal is not to keep deepening one
sell-side attribution thread. The goal is a reusable, AI-friendly backtest
workbench that can run, validate, index, compare, review, and close experiment
cycles without losing boundary control.

The run-review workbench and manual market-type validation slice is sealed.
Strategy Adaptation V1 is also sealed in
`docs/strategy-adaptation-v1-closure.md`, with the accepted baseline captured in
`examples/strategy-adaptation-v1-baseline.json`. The expected AI review
boundary is captured in
`examples/strategy-adaptation-v1-ai-review-golden.json`. Do not keep expanding
the report framework, attribution dimensions, market taxonomy, or
strategy-variant loop in this sealed stage.
`att-review-golden-check` is the deterministic gate for this sealed review:
it checks the review document against the golden fixture and writes the latest
local result under
`reports/strategy-adaptation-v1-ai-review-golden-check/`.
The first strategy-adaptation artifact is
`strategy_adaptation_matrix.json`: it starts from known market types, reverse
looks up each completed trade's entry evidence from `trade_lifecycle.json`,
joins post-exit follow-up by trade key, and summarizes winning, losing, and
sold-too-early entry factors for AI drill-down.
`att-strategy-adaptation-drilldown` turns one matrix factor into review-sample
packets, and `att-strategy-variant-drafts` turns bull/range/bear matrix
conclusions into manually confirmable validation drafts such as letting winners
run in bull markets, disabling add-on in range markets, and defensive sizing in
bear markets. `att-generate-strategy-variant-runs` converts those drafts into
legal market-segment RunPlans, while `att-strategy-variant-validation` compares
the baseline and variant `market_type_summary.json` outputs so AI review can
judge whether a candidate improved a known market type before any switching
rule is considered. `att-strategy-variant-attribution` is the next drill-down:
it pairs baseline and variant segment artifacts for a selected market type and
explains behavior changes through exit-method shifts, holding-period
compression, same-symbol re-entry density, and sample refs from
`trade_lifecycle.json`.

Exit Method Attribution is now parked as a future analysis tool, defined in
`docs/next-stage-exit-method-attribution.md`. The minimal artifact contract is
already defined there as `attbacktrader.exit_method_attribution.v1`, but it is
not the active main line.
The first missing-evidence audit for this stage is recorded in
`docs/exit-method-attribution-missing-evidence-check.md`: current bull-market
variant artifacts already contain direct MA/MACD component checks for
`ma_macd_weakening_exit`, so the next implementation can start from persisted
artifacts instead of upstream evidence capture when that future stage resumes.

The Run Catalog first slice is now implemented through `att-run-catalog`: one
AI-readable index of known runs, roles, configs, artifact presence,
evidence-validation status, manifest-derived comparison groups, and next-read
commands. Use it as the first workbench entry point before opening individual
run artifacts.
The Experiment Lifecycle first slice is now implemented through
`att-experiment-lifecycle`: it links review experiment and strategy variant
chains across candidate, draft, confirmed plan, generated run, executed run,
comparison, attribution, and missing decision states without rerunning
backtests. Use it after Run Catalog to keep each experiment cycle bounded.
The Workbench Closure Snapshot is now implemented through
`att-workbench-closure-snapshot`: it writes the versioned baseline
`examples/backtest-workbench-v1-baseline.json` and closure document
`docs/backtest-workbench-v1-closure.md`, fixing accepted commands, artifacts,
test counts, sealed docs, active non-goals, AI read order, and allowed next
slices.
The AI Skill Entry Contract is now implemented through
`att-ai-skill-entry-contract`: it writes
`examples/attbacktrader-ai-skill-entry-contract.json` and
`docs/attbacktrader-ai-skill-entry-contract.md`, then the local
`attbacktrader-ai-review` Skill can start from Run Catalog, Experiment
Lifecycle, run overview, dictionary, and review packet before producing
evidence-cited recommendations.
Experiment Decision Records are now implemented through
`att-experiment-decisions`: explicit accepted/rejected/parked inputs close the
strategy variant lifecycle chains and the current Workbench closure baseline
records `decision_gap_count=0`. The decision artifact is governance state, not
strategy scoring or automatic parameter selection.
Workbench Closure Golden Check is now implemented through
`att-workbench-closure-golden-check`: it checks that
`docs/backtest-workbench-v1-closure.md` still reflects
`examples/backtest-workbench-v1-baseline.json` for accepted commands, artifact
groups, non-goals, verification counts, rules, next slices, and AI first-read
order.

The notes below are historical implementation context for the sealed workbench
and adaptation stack. They are not the active next-stage scope.

Start upstream of reporting: let strategy methods declare their required
indicators and timeframe, prepare only the matching indicator snapshot set,
then add new indicator-backed entry and exit methods through the existing
binding contract. Daily strategy rows align weekly and monthly indicators to
the latest completed higher-timeframe bar whose snapshot date is on or before
the daily trade date. Indicator calculation remains numeric and reusable only:
for example MA20, MA25, and MA60 are indicators, while a bullish MA trend is a
strategy decision. Windowed indicators remain unavailable until enough bars
exist and must not be filled with default values. Report enrichment should
follow after the strategy data flow and signal audit evidence are stable.
Indicator updates are planned per `symbol/timeframe`; the longest required
warmup/lookback in that group controls the shared recompute window. Indicator
snapshot metadata records the selected indicator set, fingerprint, coverage,
and rolling state. Fully stateful groups such as MACD can append from saved
state; mixed groups such as MA plus KDJ still rebuild the necessary shared
window because the group contains indicators with different continuation
semantics. Indicator snapshots are discovered by compatible
symbol/asset/adjustment/indicator/timeframe ranges, but reuse is limited to the
same calculation start so warmup semantics stay deterministic. Tradable bar
snapshots are discovered by compatible symbol/asset/adjustment ranges before
fetching; covered ranges can be reused offline, and partial ranges only fetch
missing leading/trailing edges. Composite strategy decisions such as MA+MACD
confirmation remain in strategy methods and write each condition result into
`signal_audit.json`; golden fixtures pin the expected intent sequence for these
methods. Sizing has advanced at the execution boundary: `equal_weight` can now
use max holding count, max position percent, total exposure, risk-group
exposure, cash reserve, daily turnover, rebalance interval, and ATR risk caps
while preserving fixed-stake behavior when no sizing parameters are supplied.
Prepared data now records snapshot provenance in `snapshots.json` so a run can
distinguish created, exact-reused, range-reused, and incrementally filled
snapshots. Daily bar quality checks emit non-fatal warnings for issues such as
symbol mismatches, duplicate dates, non-increasing dates, missing edge coverage,
and large calendar gaps. Trading Calendar V1 can derive sessions from decision
or benchmark index bars and report missing trading sessions directly. The
business engine now simulates portfolio cash and mark-to-market value
deterministically, while backtrader remains responsible for broker costs and
A-share execution constraints. Entry attribution is now configurable under
`analysis.entry_attribution`: selected namespaced factors can be retained or
trimmed, and decision-layer entry filters can block an entry before sizing when
required checks such as price above MA25 or CSI 300 bullish trend fail or are
missing. `sizing_audit.json` extracts sizing decisions from signal audit for
easier review, while `result_diagnostics.json` summarizes per-symbol outcomes,
winning/losing trade entry evidence, exit evidence, add-on signal counts, and
factor contrasts from signal audit. The current attribution direction follows
`docs/architecture/entry-attribution.md`: completed trades are the attribution
samples, decision-time evidence is captured under a namespaced attribution
contract, missing evidence is counted separately, and reports show concise
winning-vs-losing factor contrasts while JSON keeps full detail.
`evidence_validation.json` is now the framework correctness gate for persisted
run evidence: it checks that trades can be traced back to signal intents,
sizing evidence, execution events, diagnostics counts, and final equity outputs
without rerunning strategies or recalculating indicators. A-share rejection
evidence is now checked across signal and execution artifacts: blocked reasons
such as board-lot, cash, suspension, limit-up/down, and T+1 must match the
rejected execution side and have zero executable quantity.
Lifecycle attribution now groups successful add-on intents into the completed
trade they belong to, using the date range after primary entry and before exit;
winning and losing add-on summaries and contrasts are derived from those grouped
intents, and `report.md`/`report.zh.md` include a capped add-on entry-point
detail table for quick review. `trade_lifecycle.json` stores the per-trade entry/add-on/exit timeline
with signal evidence, linked execution events, and filter indexes by symbol,
outcome, exit reason, add-on count, entry checks, entry categories, and
execution rejection reason so detailed review does not depend on Markdown
expansion. `trade_lifecycle.zh.md` gives the same lifecycle data a concise
Chinese review surface. `trade_review.json` and `trade_review.zh.md` now join
completed-trade lifecycle, sold-too-early profile grouping, stop-loss rebound
attribution, and opportunity or block samples such as entry filters, sizing
blocks, signal blocks, and execution rejections into one review surface. The
review can also look up the post-opportunity window from prepared snapshots to
summarize sizing/execution opportunity cost without claiming the trade should
have been taken. Successful add-on entry points are also looked up from the
completed trade lifecycle and followed for the same review window, then grouped
by trade outcome and add-on evidence. `evidence_validation.json` now checks
post-exit and trade-review counts and catches default-filled missing follow-up
returns. `post_exit_analysis.json` now follows the same
downstream lookup pattern as attribution: after the run completes, it starts
from closed trades and prepared bars, then observes configured windows after
stop-loss/profit-taking exits to flag possible sold-too-early rebounds. Current
examples use 3/5/10/20 trading-day windows with 5 days as the primary review
window. The artifact also captures configurable rebound threshold layers such
as 0/2/5/10%, exit-day checks, and values from the exit
intent, then groups sold-too-early rates by factors such as stop-hit and KDJ
overheated; the Chinese review also ranks the most obvious sold-too-early
samples by rebound size. Exit intents now receive the same shared symbol,
industry, and market attribution context as entries and add-ons, so post-exit
factor groups can include symbol MA, CSI 300 trend, and industry KDJ evidence.
It does not rerun strategy methods, recalculate indicators, or
default-fill missing future bars. Entry attribution now also emits symbol
MA20/MA60 values and
decision-layer symbol MA trend checks when enough bars exist; missing long-window
evidence remains absent rather than default-filled. Correctness golden samples
pin warmup behavior, higher-timeframe alignment, buy/add-on/sell lifecycle
grouping, execution-cost audit totals, missing-attribution coverage semantics,
and A-share rejection evidence for board-lot, cash, suspension, limit-up/down,
and T+1 cases.
Result-driven backtest examples now split
the next review step into two runs: `run-tushare-expanded-baseline.yaml`
expands the sample while preserving fixed-stake sizing, and
`run-tushare-expanded-sized.yaml` uses the same sample with practical portfolio
controls so signal behavior and capital allocation can be compared separately.
`run-tushare-attribution-filter.yaml` adds a focused entry-filter experiment
derived from current attribution factors. `att-compare-runs` now compares
persisted run artifacts across baseline, sized, filter, and add-on variants,
including final value, cumulative return, max drawdown, trade quality,
execution/sizing blocks, execution rejection reason counts, entry-filter
blocks, and add-on signal counts.
`att-generate-attribution-filter-experiments` can generate validated
attribution-filter YAML variants from a small matrix, including symbol MA
bullish trend, price above MA60, and combined symbol MA plus CSI 300 checks.
Real add-on execution is
now selectable through `strategy.add_on_method`: `none` preserves legacy runs,
while `kdj_oversold_add_on` evaluates a held position using prepared KDJ,
profit threshold, and max add-on count, then reuses sizing to place the
additional buy and update the position average cost.
The latest expanded Tushare artifact refresh produced `evidence_validation: ok`
for baseline, sized, attribution-filter, and add-on runs. Final values were
`989324.9511796256`, `942143.6226874419`, `1024963.5979407353`, and
`963179.0879163865`; the add-on run emitted 4 add-on signals and now writes
`trade_review.json` plus `trade_review.zh.md`. The accepted
real-run regression baseline lives in `examples/real-run-regression-baseline.json`;
the latest local regression check wrote
`reports/real-run-regression-2023-2024/run_regression.json` with 56 checks,
0 failures, and status `ok`.
