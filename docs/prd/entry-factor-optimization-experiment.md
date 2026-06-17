# PRD: Entry Factor Optimization Experiment

## Problem Statement

The user wants to move from Bayesian Factor Discovery into real entry-factor optimization without accidentally optimizing lifecycle evidence, exit rules, scale-out behavior, sizing, or noisy market-regime artifacts. The current discovery report can rank `tradable_pre_entry` factor buckets, but it does not prove that a factor remains useful when used as a real entry filter in a fresh backtest. The user specifically wants an automated process that tests one candidate factor as a real strategy variant, identifies genuinely favorable and unfavorable entry factors, and only then considers stable factors for combination.

The system must avoid the misleading shortcut of deleting historical trades from an existing artifact. Real validation must re-run the strategy variant so freed capital, max-holding pressure, execution constraints, replacement trades, and run artifacts are reflected. It must also avoid a simple 2023/2024 train-test assumption because the two years have different market conditions; validation must be stratified by year and objective market stage.

## Solution

Build an Entry Factor Optimization Experiment workflow with two stages.

Stage 1 is a Single-Factor Real Validation Matrix. It reads Bayesian Factor Discovery results, takes only `tradable_pre_entry` candidates, selects the first wave as positive Top 10 and negative Top 10, generates one real strategy variant per candidate, re-runs each variant against the same baseline run settings, and compares each variant against baseline. Positive candidate buckets become keep filters. Negative candidate buckets become exclude filters. Each candidate is then classified as stable favorable, stable unfavorable, market-stage dependent, or noise.

Stage 2 is Stable Entry Factor Combination Validation. It uses only factors that survived Stage 1 and tests combined filters one step at a time with full backtests. This stage checks whether individually useful entry filters remain useful when stacked. It is not an exhaustive combination search and does not permanently change the default strategy.

The workflow must produce machine-readable and Chinese Markdown artifacts that show overall results, year-stratified results, objective market-stage-stratified results, sample count effects, and final classification. Lifecycle diagnostic fields must be ignored for optimization inputs, though they may still exist in source discovery artifacts.

## User Stories

1. As a strategy researcher, I want the optimizer to use only `tradable_pre_entry` factor candidates, so that future-looking lifecycle evidence cannot become an entry rule.
2. As a strategy researcher, I want positive factor buckets to become keep filters, so that I can test whether restricting entries to favorable conditions improves the strategy.
3. As a strategy researcher, I want negative factor buckets to become exclude filters, so that I can test whether avoiding unfavorable conditions improves the strategy without overly narrowing the trade universe.
4. As a strategy researcher, I want each candidate factor tested as its own real strategy variant, so that I can identify the individual effect of that factor before combining it with others.
5. As a strategy researcher, I want the first wave limited to positive Top 10 and negative Top 10, so that the validation loop is useful without becoming a large uncontrolled batch.
6. As a strategy researcher, I want the workflow to re-run actual backtests, so that the results include changed cash usage, replacement trades, max-holding effects, and execution constraints.
7. As a strategy researcher, I want the report to compare every variant against the same baseline, so that improvements and regressions are visible in a consistent frame.
8. As a strategy researcher, I want year-level results for 2023 and 2024, so that I can see whether a factor only worked in one calendar year.
9. As a strategy researcher, I want objective market-stage stratification, so that a bull-market effect is not mistaken for factor quality.
10. As a strategy researcher, I want mixed, bullish, and bearish entry-stage slices reported separately, so that I can identify conditional factors rather than overgeneralizing.
11. As a strategy researcher, I want the report to flag small market-stage sample counts, so that thin slices do not become strong conclusions.
12. As a strategy researcher, I want each candidate classified as stable favorable, stable unfavorable, market-stage dependent, or noise, so that I know which factors deserve further work.
13. As a strategy researcher, I want stable favorable and stable unfavorable factors separated, so that good keep filters and useful exclude filters are not mixed together.
14. As a strategy researcher, I want market-stage dependent factors retained but clearly labeled, so that I can later decide whether to build conditional market-regime rules.
15. As a strategy researcher, I want noisy factors preserved in the report with reasons, so that rejected candidates are auditable and not repeatedly retested by accident.
16. As a strategy researcher, I want the workflow to record the source discovery report and candidate rank used, so that every validation run can be traced back to the evidence that generated it.
17. As a strategy researcher, I want generated variants to keep the same baseline strategy, execution, scale-out, max-holding, broker, and data settings except for the entry filter, so that candidate comparisons are meaningful.
18. As a strategy researcher, I want the output to show trade count retained or excluded, so that I can see whether a rule improves quality only by shrinking the strategy too much.
19. As a strategy researcher, I want the output to show return rate, win rate, drawdown, Profit Factor, and trade count together, so that no single metric dominates the decision.
20. As a strategy researcher, I want the workflow to avoid optimizing exits, scale-outs, sizing, and add-ons, so that this PRD remains focused on entry factors only.
21. As a strategy researcher, I want the workflow to avoid multi-factor search in Stage 1, so that individual factor effects are not hidden by ordering and interaction effects.
22. As a strategy researcher, I want Stage 2 to combine only Stage 1 survivors, so that factor stacking is based on evidence rather than brute-force exploration.
23. As a strategy researcher, I want each Stage 2 combination step to be a real backtest, so that combined rules are validated under real portfolio behavior.
24. As a strategy researcher, I want the system to stop short of changing the default strategy, so that validated candidates remain experimental until explicitly promoted.
25. As a strategy researcher, I want generated artifacts to be consumable by later AI review, so that factor classifications can be audited with sample references and source metrics.
26. As a maintainer, I want the entry filter expression contract to support bucket equality and exclusion, so that Bayesian discovery buckets can be represented legally in RunPlan variants.
27. As a maintainer, I want existing boolean entry-attribution filters to keep working, so that current examples and tests do not regress.
28. As a maintainer, I want invalid or future-function candidate fields rejected before running backtests, so that the workflow fails fast on unsafe inputs.
29. As a maintainer, I want generated run IDs to encode candidate identity and filter action, so that variant artifacts are easy to locate and compare.
30. As a maintainer, I want a dry-run or manifest mode, so that candidate run plans can be reviewed before expensive backtests are launched.
31. As a maintainer, I want CLI output to summarize generated count, executed count, and artifact paths, so that automation can chain the workflow.
32. As a maintainer, I want report builders to consume persisted run artifacts rather than rerunning analysis internally, so that artifact ownership remains consistent.
33. As a maintainer, I want tests at the configuration, strategy-filter, runner, and report seams, so that behavior is protected without overfitting implementation details.
34. As a maintainer, I want the PRD to respect the deferred parameter-tuning ADR, so that this feature remains validation-oriented and does not become a general Bayesian optimizer.
35. As a future agent, I want clear out-of-scope boundaries, so that implementation does not drift into lifecycle optimization or exhaustive rule search.

## Implementation Decisions

- The workflow is an Entry Factor Optimization Experiment, not a Bayesian parameter tuning system.
- Candidate input comes from Bayesian Factor Discovery artifacts and must use only the `tradable_pre_entry` view.
- `lifecycle_diagnostic`, `trade.path`, exit, post-exit, entry-to-exit, sizing, and indicator-date metadata fields must be rejected as optimization candidates.
- Stage 1 is a Single-Factor Real Validation Matrix.
- Stage 1 first wave uses positive Top 10 and negative Top 10 from the discovery ranking, for a maximum of 20 real single-factor backtests.
- Positive candidate buckets use keep-filter semantics: allow entry only when the candidate bucket is present.
- Negative candidate buckets use exclude-filter semantics: block entry when the candidate bucket is present.
- Each Stage 1 candidate must be represented as a real strategy variant and full RunPlan execution, not as offline deletion from completed trades.
- Generated variants must preserve the baseline strategy, execution, 2x/4x ATR scale-out behavior, max-holding setting, broker, data source, snapshots, and output shape unless the entry filter explicitly changes them.
- The existing boolean entry-attribution filter is not enough for this PRD; the filter contract needs a value/bucket condition shape capable of expressing equality and exclusion rules over entry attribution categories or bucket fields.
- Existing boolean `require_checks` behavior must remain backward compatible.
- Filtered entries should remain visible as blocked or avoided entry evidence with a stable blocked reason, so existing audit and review artifacts can explain what was filtered.
- Candidate generation should produce a manifest of run variants before execution, including source discovery artifact, source candidate rank, field key, bucket value, direction, action, and generated run ID.
- A CLI should support generating the validation matrix, optionally executing the generated variants, and writing machine-readable plus Chinese Markdown outputs.
- Stage 1 comparison must include baseline versus variant metrics for total sample, year slices, and objective entry market-stage slices.
- Metrics must include trade count, win rate, average return, capital return or return on entry value where available, Profit Factor, drawdown or drawdown proxy from the resulting run artifacts, and sample-retention impact.
- Factor classification must be explicit: stable favorable, stable unfavorable, market-stage dependent, noise, and insufficient sample where applicable.
- A factor can be marked stable only if its overall result improves and it does not obviously fail year or common market-stage slices.
- A factor can be marked market-stage dependent when it helps in a market stage but does not generalize across stages.
- A factor must not be promoted just because it works in a tiny bullish or bearish slice.
- Stage 2 is Stable Entry Factor Combination Validation.
- Stage 2 may only use Stage 1 survivors and must add filters step by step, re-running the strategy after each addition.
- Stage 2 must not do exhaustive multi-factor combination search.
- Stage 2 results remain candidate evidence and must not automatically change the default strategy configuration.
- Reports belong in the reports layer, CLI orchestration belongs in the CLI layer, RunPlan generation belongs behind a reusable module rather than inside CLI-only code, and strategy decision behavior must remain in the strategy/filter layer.
- The implementation must respect the deferred parameter-tuning ADR: this is a validation workflow over explicitly proposed entry filters, not a general optimization engine.

## Testing Decisions

- Tests should verify external behavior at the highest useful seam and avoid locking in internal helper structure.
- Configuration tests should verify that the new entry filter condition contract accepts legal keep/exclude bucket conditions, rejects unknown fields, rejects lifecycle/future-function fields when used as entry optimization filters, and keeps existing boolean require-check filters working.
- Strategy-filter tests should verify that a matching keep condition allows an entry, a non-matching keep condition blocks it, a matching exclude condition blocks it, a non-matching exclude condition allows it, and missing evidence follows the configured missing policy.
- Runner or manifest tests should verify that Stage 1 candidate generation creates one legal RunPlan variant per selected candidate and preserves baseline settings except for the entry filter and run identity.
- CLI smoke tests should verify dry-run or manifest output, artifact paths, and validation summary output without requiring live Tushare access.
- Report tests should verify that a baseline plus candidate variant set is classified into stable favorable, stable unfavorable, market-stage dependent, noise, and insufficient sample cases using small deterministic fixtures.
- Backward compatibility tests should keep the existing attribution filter experiment behavior valid for boolean check filters.
- The highest-priority prior art for tests is the existing RunPlan execution tests, entry-attribution filter tests, attribution-filter experiment config tests, Bayesian factor discovery tests, environment-fit tests, and run comparison/report tests.
- Live long-running backtests should not be required in the default test suite; use fake providers, tiny fixtures, or persisted synthetic artifacts for automated tests.
- The real 2x/4x ATR maxhold800 run can be used as a manual acceptance smoke after implementation, but not as the only correctness signal.

## Out of Scope

- Optimizing lifecycle diagnostic factors.
- Using `trade.path`, exit, post-exit, entry-to-exit, sizing, or metadata anchor fields as entry optimization inputs.
- Optimizing profit-taking, stop-loss, scale-out thresholds, add-on behavior, or sizing.
- Exhaustive multi-factor search.
- Bayesian parameter tuning or general Bayesian optimization.
- Automatically promoting validated filters into the default strategy.
- Recutting continuous thresholds or creating new factor buckets during optimization.
- Ranking same-day entry candidates or changing max-holding behavior.
- Fetching new market data inside report builders.
- Treating offline completed-trade deletion as final validation.

## Further Notes

The current discovery run for the 2x/4x ATR maxhold800 sample produced 110 tradable pre-entry fields and 45 positive/negative entry candidate buckets after metadata-anchor exclusion. The first validation wave should use the positive Top 10 and negative Top 10 from that artifact.

The market-stage validation should use objective entry market stage because 2023 and 2024 are not equivalent regimes in the current sample. The stage definition is based on selected index state plus market breadth; `mixed` means neither strong bullish nor strong bearish conditions are satisfied.

This PRD intentionally supersedes the earlier idea of choosing Top 5 from offline screening. Offline screening can remain an optional estimate, but it must not be treated as the source of truth for real factor quality.
