# Evidence Chain And Analysis Correctness

This document fixes the current evidence contract for result-driven framework
work. The priority is framework correctness, not parameter tuning.

## Direction

ATTbacktrader should make every reported number traceable to upstream run
evidence. Reports should display and summarize evidence; they should not
recalculate indicators, rerun strategy methods, or infer missing decision data.

## Source Of Truth

| Layer | Source artifact | Owns |
|---|---|---|
| Raw market data | `snapshots.json` plus referenced snapshots | fetched/reused bars, reference data, provenance, quality issues |
| Numeric indicators | indicator snapshots referenced by `snapshots.json` | reusable numeric values such as KDJ, MA, MACD, RSI, ATR |
| Strategy decisions | `signal_audit.json` | entry, add-on, hold, avoid, profit exit, stop exit intents and decision evidence |
| Sizing decisions | `signal_audit.json`; extracted as `sizing_audit.json` | requested quantity, caps, sizing blocks, risk/exposure context |
| Execution | `execution_audit.json` | submitted, accepted, completed, failed, and rejected broker/constraint events |
| Position and trades | `positions.json`, `trades.json`, `equity_curve.json` | mark-to-market state, open positions, closed trades, final account value |
| Diagnostics | `result_diagnostics.json` | summaries derived from trades, signal audit, execution audit, and open positions |
| Trade lifecycle | `trade_lifecycle.json` | per-completed-trade entry/add-on/exit timeline with linked signal and execution evidence |
| Post-exit follow-up | `post_exit_analysis.json` | configured-window observations, rebound threshold layers, and ranked sold-too-early samples after completed trade exits, derived from closed trades, exit intents, and prepared bars |
| Trade review | `trade_review.json` | unified per-trade review, sold-too-early profile grouping, stop-loss rebound attribution, opportunity/block opportunity-cost attribution, and add-on entry-point follow-up assembled from lifecycle, post-exit, signal, execution, and snapshot evidence |
| Environment fit | `environment_fit.json`, `environment_fit.zh.md` | downstream grouping of completed trades by decision-time entry environment, win rate, return, net PnL, and entry-value return |
| Environment fit comparison | `environment_fit_comparison.json`, `environment_fit_comparison.zh.md` | cross-run comparison of environment-fit stability, sample risk, and common-environment deltas without rerunning strategies |
| AI review packet | `review_packet.<focus>.json`, `review_packet.<focus>.zh.md` | focus-specific, capped, AI/Skill-friendly packet assembled from persisted run artifacts with source pointers and sample indexes |
| AI review findings | `review_findings.<focus>.json`, `review_findings.<focus>.zh.md` | structured finding draft and AI task contract derived from a review packet |
| Review sample drill-down | `review_sample.<kind>.<id>.json`, `review_sample.<kind>.<id>.zh.md` | single-sample evidence packet linking a trade/opportunity/add-on sample back to lifecycle, post-exit, signal, execution, and closed-trade evidence |
| Review sample batch | `review_sample_batch.<focus>.json`, `review_sample_batch.<focus>.zh.md` | batch expansion of finding sample refs into compact sample evidence summaries and optional individual sample packet paths |
| AI review brief | `review_brief.<focus>.json`, `review_brief.<focus>.zh.md` | Skill-ready brief that combines findings, evidence rules, expanded sample summaries, and a first-page environment-fit summary |
| AI review result | `ai_review_result.<focus>.json`, `ai_review_result.<focus>.zh.md` | persisted structured review output derived from a brief and carrying required evidence/sample refs |
| Review experiment candidates | `review_experiment_candidates.<focus>.json`, `review_experiment_candidates.<focus>.zh.md` | validation candidates derived from findings and samples, including environment-fit sample-stability checks, explicitly not tuning decisions |
| Review experiment drafts | `review_experiment_drafts.<focus>.json`, `review_experiment_drafts.<focus>.zh.md`, individual YAML drafts | manually confirmable next-run draft plans derived from candidates, including environment-fit comparison drafts; not executable RunPlans until reviewed |
| Confirmed review experiment RunPlan | `review_experiment_confirmed.<draft_id>.json`, `review_experiment_confirmed.<draft_id>.zh.md`, `<draft_id>.run.yaml` | manually confirmed, validated RunPlan output generated from one draft with review metadata stripped from executable YAML |
| Human reports | `report.md`, `report.zh.md` | concise presentation of the report model and diagnostics |
| Evidence validation | `evidence_validation.json` | consistency checks across the artifacts above |
| Real-run regression | `examples/real-run-regression-baseline.json`; `run_regression.json` | accepted metric snapshots and drift checks for persisted real-run artifacts |

## Invariants

- A completed trade must match one successful entry intent on `entry_date`.
- A completed trade must match one successful exit intent on `exit_date` and
  `exit_reason`.
- An `ENTER` or `ADD_ON` intent must carry sizing evidence before execution.
- An execution event must reference an emitted signal intent by symbol, signal
  date, and reason code.
- A rejected A-share execution must carry the same blocked reason as the
  referenced blocked signal intent.
- A rejected execution must have zero executable quantity, and direction-bound
  reasons such as limit-up buy, limit-down sell, cash, and T+1 must match the
  execution side.
- A completed sell execution must correspond to a closed trade.
- `result_diagnostics.json` counts must match `signal_audit.json` and
  `trades.json`.
- Successful add-on attribution samples must be grouped into the completed
  trade lifecycle after primary entry and before exit.
- Add-on lifecycle attribution must come from an emitted `ADD_ON` intent; the
  report layer must not infer add-ons from position size changes alone.
- Exit attribution must come from the emitted exit intent. Shared symbol,
  industry, and market context can be attached to exit intents, but reports must
  not calculate that context after the run.
- The final equity point must match `final_value` and `final_cash`.
- Latest position snapshots must match open positions and the last equity
  position value.
- Post-exit and trade-review follow-up rows must keep return fields missing
  when future bars or prices are missing; validation must not accept defaulted
  zero returns.

## Boundaries

Indicators are reusable numeric calculations. Composite states such as bullish
trend, entry filter pass/fail, add-on eligibility, and exit weakening are
decision-layer facts and belong in strategy methods or shared attribution
evidence builders.

Attribution is a lookup from completed trades back to decision-time evidence.
Missing evidence is counted as missing. It is not treated as `false`, `0`, or a
neutral default.

Lifecycle attribution extends that lookup to add-on intents. Add-on evidence is
not a new trade by itself; it is grouped into the completed trade that was open
when the add-on decision happened.

Trade lifecycle detail is a persisted evidence view. It links completed trades
back to entry, successful add-on, and exit intents plus execution events, but it
does not infer trades or add-ons that are not already present upstream.
Its indexes are navigation aids over the same evidence, grouped by symbol,
outcome, exit reason, add-on count, entry checks, entry categories, and
execution rejection reason.

Trade review is a consolidated downstream view. It combines lifecycle events,
post-exit sold-too-early labels, stop-loss rebound attribution, and
opportunity/block samples such as entry filters, sizing blocks, and execution
rejections. It can look up the configured post-opportunity window from prepared
bars to estimate opportunity cost. It can also look up successful add-on entry
points inside a completed trade lifecycle and observe the configured window
after the add-on date. It does not rerun entry logic, rejudge blocked trades, or
decide whether an add-on should have happened. It is a review surface over
existing evidence, not a new source of trade, indicator, or strategy facts.

AI review packets are an even thinner downstream view over persisted artifacts.
They select a focus such as sold-too-early, stop-loss rebound, opportunity
cost, add-on entry points, or validation, then write capped summaries and
samples with `trade_index` or `sample_index` pointers. They do not own counts,
recalculate indicators, rerun strategy methods, or infer missing follow-up
returns. Their `ai_contract` exists to constrain later Skill-based analysis to
the same evidence boundary.

AI review findings and sample drill-down packets are generated from the same
evidence. Findings provide a structured task contract and citation-ready
finding drafts for an AI reviewer. Sample drill-down packets start from one
`trade_index` or `sample_index` and collect nearby persisted evidence so a Skill
can inspect a case without loading every artifact in the run directory. Neither
artifact is a new source of metrics or strategy facts.

Review sample batches and AI review briefs are orchestration artifacts for
Skill-based review. A batch expands finding sample refs into compact evidence
summaries and optional individual sample files. A brief combines findings,
sample summaries, a first-page environment-fit summary, and an expected output
schema for the reviewing Skill.
AI review results persist the structured review output so a research record can
be compared later. Review experiment candidates and drafts turn findings into
next validation ideas, such as adding an evidence grouping or checking a
blocking reason cluster. They must not directly mutate run plans or tune
strategy parameters; YAML drafts require manual conversion into a legal RunPlan
before execution.

Environment-fit comparison is the validation view for sample-stability
candidates. It compares already-generated `environment_fit.json` files and can
mark best environments as stable, changed, or low-sample-risk. It is still a
review artifact: it does not create strategy facts and cannot promote a
low-sample environment into a trading rule. Its `drill_down_sample_refs` field
points to representative `trade_index` rows for exact evidence lookup; those
refs are navigation hints, not a statistical sample design.

Confirmed review experiment RunPlans close the tooling loop without changing
the strategy boundary. Confirmation is explicit (`--confirm`), one draft is
converted at a time, and only legal RunPlan top-level fields are written to the
executable YAML. Review metadata such as `review_candidate` stays in the JSON
manifest and Markdown note so the RunPlan remains valid configuration rather
than a mixed evidence artifact.

Post-exit follow-up is also a downstream evidence view. It starts from completed
trades, the matched exit intent, and prepared bars after `exit_date` to observe
configured trading-day windows such as 3/5/10/20. It can label a stop-loss or
profit-taking exit as sold-too-early when price rebounds after sale, and it can
group those labels by exit-day checks such as stop hit or KDJ overheated.
Rebound threshold layers, such as 0/2/5/10%, are configurable review buckets
over the same observed future bars. Those labels, groups, and ranked sample
tables are explanatory review evidence, not strategy decisions or causality
claims.

Diagnostics and reports are downstream consumers. They may aggregate, count, and
rank evidence, but they must not repair missing evidence by recalculating
indicators or re-evaluating strategy rules.

## Validation Artifact

`evidence_validation.json` is produced with every persisted run. It is an
acceptance artifact for data-analysis correctness:

- `status: ok` means no consistency errors were found;
- `status: failed` means at least one cross-artifact invariant failed;
- warnings are allowed for non-fatal evidence gaps;
- issue records include `code`, `artifact`, optional symbol/date, and expected
  versus actual values.

The validation layer consumes in-memory run results and already prepared
snapshot evidence before artifact write. It does not fetch data, run a
backtest, calculate indicators, or mutate outputs. It also validates the
downstream review surfaces enough to catch broken counts and default-filled
missing follow-up returns.

## Regression Baseline

`att-validate-run-regression` validates already persisted real-run artifacts
against `examples/real-run-regression-baseline.json`. It checks accepted metrics
such as final value, return, drawdown, trade count, entry-filter count,
add-on-signal count, execution rejection reason count, completed-order count,
and evidence-validation status.
This is a drift guard for framework changes; it is not a tuning target.
