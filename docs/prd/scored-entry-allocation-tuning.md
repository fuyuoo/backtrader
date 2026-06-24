# PRD: Scored Entry Allocation Tuning

## Problem Statement

The user has already used entry attribution, single-factor validation, and A-anchored pairwise entry-factor validation to identify favorable and unfavorable entry factor buckets. Those results are useful evidence, but they still come from validation and trade-sample style workflows where capital scarcity, ranked candidate competition, cash usage, holding capacity, and realistic portfolio exposure are not the primary evidence.

The next problem is to turn the screened entry factors into a scored portfolio workflow: on each signal date, eligible entry candidates should be scored from pre-entry factor evidence, ranked, filtered by a sufficiently high score gate, and then allowed to compete for real portfolio cash and holding capacity. The user also wants the scorer weights and selected portfolio controls to be tuned automatically without turning the exercise into full-sample historical parameter mining.

The system must avoid three misleading shortcuts:

- Treating `maxhold800` or large-capital trade-sample results as real portfolio return evidence.
- Optimizing against all of 2015-2024 and presenting the result as reusable.
- Caching completed trades instead of caching strategy decision evidence and then re-simulating portfolio state for each parameter set.

## Solution

Build a Scored Entry Allocation Tuning workflow with a cached strategy decision layer, two-stage walk-forward tuning, and scored portfolio validation.

The workflow has three layers:

1. Build a `Strategy Decision Event Table` from the baseline strategy and prepared evidence. It caches actionable decision events and decision-time evidence, not completed trades or portfolio results.
2. Run strict walk-forward tuning with five-year training windows and one-year test windows. Each fold uses Stage A trade-sample parameter pre-tuning to narrow the scorer search space, then Stage B scored portfolio parameter tuning to search within realistic portfolio constraints.
3. Produce out-of-sample scored portfolio reports with Pareto frontier outputs, `balanced`, `aggressive`, and `defensive` parameter sets, and detailed metrics and funnel diagnostics.

The first implementation scope is `Scored Entry Allocation Tuning`: optimize entry-candidate scoring weights, interaction weights, score gates, and selected allocation thresholds while keeping exit, add-on, scale-out, and lifecycle rules fixed. Exit and add-on optimization is explicitly deferred to a later stage.

## User Stories

1. As a strategy researcher, I want screened entry factors to become scoring inputs, so that candidate ranking uses validated pre-entry evidence instead of raw indicator magnitude.
2. As a strategy researcher, I want factor scores to be outcome-calibrated, so that a bucket receives weight because it improved historical training-window outcomes, not because its raw numeric value is larger.
3. As a strategy researcher, I want numerical indicators to be converted to buckets before scoring, so that the scorer remains aligned with the existing factor validation evidence.
4. As a strategy researcher, I want favorable buckets to add score and unfavorable buckets to apply a soft penalty, so that strong candidates can still compete when they carry some risk.
5. As a strategy researcher, I want two-factor combinations to have separate interaction weights, so that combinations can express additional strength or weakness beyond their single-factor components.
6. As a strategy researcher, I want interaction weights to allow positive and negative values, so that a pair of individually useful factors can still be penalized if the combination performs poorly.
7. As a strategy researcher, I want entry candidates to pass a score gate before trading, so that slightly positive or low-quality candidates do not consume capital.
8. As a strategy researcher, I want the score gate to combine a training-window z-score floor and training-window quantile threshold, so that the trading threshold remains meaningful across different weight scales.
9. As a strategy researcher, I want the default Stage B score gate to require `minimum_score_z = 0.75` and `minimum_score_quantile = 0.70`, so that candidates must be clearly better than ordinary signals before they can trade.
10. As a strategy researcher, I want Stage A to use a wider score gate, so that pre-tuning can learn factor direction from broader candidate coverage.
11. As a strategy researcher, I want Stage A to use `minimum_score_z = 0.0` and `minimum_score_quantile = 0.50`, so that only clearly weak candidates are filtered during pre-tuning.
12. As a strategy researcher, I want the scorer to use one global weight set rather than market-stage-specific weights in the first version, so that the model remains interpretable and less overfit.
13. As a strategy researcher, I want market-stage performance to be reported separately, so that later work can decide whether stage-conditional weights are justified.
14. As a strategy researcher, I want all automatic tuning to use walk-forward windows, so that test-year evidence is never used to choose parameters.
15. As a strategy researcher, I want five-year training and one-year test windows, so that each fold has enough training history while still producing multiple out-of-sample years.
16. As a strategy researcher, I want the walk-forward folds to cover 2020 through 2024 as test years, so that the final evidence spans several market environments.
17. As a strategy researcher, I want Stage A to be a trade-sample parameter pre-tuning pass, so that it can learn factor direction and narrow scorer search ranges with broad candidate coverage.
18. As a strategy researcher, I want Stage A to use high holding capacity and broad capital assumptions, so that pre-tuning is not dominated by portfolio scarcity.
19. As a strategy researcher, I want Stage A to still use a portfolio simulator rather than a completed-trade table, so that lifecycle, exit, cost, and execution behavior stay consistent with Stage B.
20. As a strategy researcher, I want Stage A output to narrow Stage B search space rather than approve final parameters, so that broad-sample pre-tuning does not become final portfolio evidence.
21. As a strategy researcher, I want Stage A elite trials to include the Pareto frontier plus the balanced-score top 20% trials, so that weight direction estimates are stable enough to narrow Stage B ranges.
22. As a strategy researcher, I want Stage B to tune within realistic scored portfolio constraints, so that final parameters are validated under actual cash and holding competition.
23. As a strategy researcher, I want Stage B default initial cash to be 10,000,000, so that board-lot and per-symbol sizing behavior are meaningful.
24. As a strategy researcher, I want Stage B default maximum holding count to be 20, so that the strategy has a clear real-portfolio capacity target.
25. As a strategy researcher, I want Stage B default maximum new positions per day to be 3, so that one signal burst does not consume the whole portfolio at once.
26. As a strategy researcher, I want Stage B default cash reserve ratio to be 5%, so that minor execution and board-lot effects do not create edge-case failures.
27. As a strategy researcher, I want Stage B default industry maximum new positions per day to be 1, so that same-day industry concentration is controlled.
28. As a strategy researcher, I want holding capacity and daily buy limits to be external sensitivity controls rather than part of the main Optuna search, so that scorer quality is not confused with lower exposure.
29. As a strategy researcher, I want a separate sensitivity mode for holding and capacity settings, so that I can later review 10/20/30 holding-cap behavior without slowing the default report.
30. As a strategy researcher, I want Stage A and Stage B to each have an unscored baseline under their own constraint regime, so that improvements are compared against the correct control group.
31. As a strategy researcher, I want Stage A baseline to be broad, high-capacity, unscored candidate filling, so that pre-tuning is compared against broad sample behavior.
32. As a strategy researcher, I want Stage B baseline to use realistic constraints and fixed stock-pool ordering, so that scored portfolio results are compared against an auditable unscored portfolio baseline.
33. As a strategy researcher, I want Stage B unscored ordering to use fixed stock-pool file order, so that baseline candidate ordering is deterministic and consistent with existing project language.
34. As a strategy researcher, I want Optuna/TPE to be used for automatic tuning, so that the workflow can search weights without manual parameter guessing.
35. As a maintainer, I want Optuna to be an optional tuning dependency, so that ordinary backtests and reports do not require tuning packages.
36. As a strategy researcher, I want standard mode to run 300 Stage A trials and 300 Stage B trials per fold, so that the default report has enough search depth for serious research.
37. As a strategy researcher, I want the total standard walk-forward budget to be 3,000 trials across five folds, so that expected runtime remains operationally feasible with caching.
38. As a strategy researcher, I want a smoke mode to run fewer trials, so that the full pipeline can be checked before launching a standard study.
39. As a strategy researcher, I want Optuna to optimize multiple objectives rather than a hand-weighted single score, so that objective weighting does not become another hidden assumption.
40. As a strategy researcher, I want the multi-objective study to optimize annualized return, Sharpe ratio, benchmark excess return, and maximum drawdown, so that return, risk-adjusted return, excess return, and downside risk are all represented.
41. As a strategy researcher, I want additional metrics such as Sortino, Calmar, information ratio, win rate, profit/loss ratio, profit factor, average trade return, turnover, cash ratio, and concentration recorded for every trial, so that final selection can be inspected beyond the four core objectives.
42. As a strategy researcher, I want Pareto frontier outputs, so that I can see the trade-off surface instead of only one selected parameter set.
43. As a strategy researcher, I want the workflow to output `balanced`, `aggressive`, and `defensive` recommended parameter sets, so that different risk preferences can be reviewed.
44. As a strategy researcher, I want the balanced selection to prioritize outperformance, drawdown control, Sharpe, Calmar, yearly stability, and reasonable turnover, so that it becomes the default recommendation.
45. As a strategy researcher, I want the aggressive selection to allow higher drawdown only within bounds, so that high-return parameters are not unbounded risk choices.
46. As a strategy researcher, I want the defensive selection to avoid becoming an empty-cash strategy, so that low drawdown is not achieved by refusing to trade.
47. As a strategy researcher, I want minimum trade-count gates, so that parameters that only trade a few lucky cases are rejected.
48. As a strategy researcher, I want training windows to require at least 50 trades per year, test years to require at least 20 trades, and full out-of-sample results to require at least 120 trades, so that reported metrics have enough sample support.
49. As a strategy researcher, I want the final report to show which candidates were filtered or blocked at each stage, so that I can adjust score gates, holding capacity, and portfolio controls from observed evidence.
50. As a strategy researcher, I want the scored entry funnel to break down raw candidates, score-gated candidates, rank-blocked candidates, holding-cap blocked candidates, cash-blocked candidates, industry-blocked candidates, tradability-blocked candidates, and executed entries, so that tuning failures are explainable.
51. As a strategy researcher, I want the funnel to be sliced by fold, year, market stage, and factor/combination hit status, so that bottlenecks are not hidden in global counts.
52. As a strategy researcher, I want the strategy decision cache to be reusable across trials, so that Optuna tuning runs in hours rather than days.
53. As a strategy researcher, I want the cache to store decision events and evidence, not completed trades, so that every trial still recomputes score, ranking, cash, positions, exits, equity curve, and metrics.
54. As a maintainer, I want the cache key to exclude scorer weights and trial IDs, so that tuning parameter changes do not invalidate signal evidence.
55. As a maintainer, I want simulation cache keys to include signal cache identity, fold, parameter hash, portfolio control hash, and simulator version, so that repeated trial results are safely reusable.
56. As a maintainer, I want cached decision events to be stored in a columnar format, so that fold slicing and trial simulation can read only needed columns efficiently.
57. As a maintainer, I want missing Optuna to fail with a clear tuning-extra install message, so that automatic tuning does not silently downgrade.
58. As a maintainer, I want command-line entry points to expose dry-run, smoke, standard, and sensitivity modes, so that expensive research runs can be planned and resumed.
59. As a maintainer, I want reports and artifacts to identify whether they came from Stage A, Stage B, or final out-of-sample evaluation, so that pre-tuning evidence is never mistaken for final portfolio validation.
60. As a future agent, I want the first implementation to keep exits, add-ons, scale-out, and lifecycle rules fixed, so that entry allocation results remain interpretable.
61. As a future agent, I want exit and add-on optimization recorded as future work, so that the next research stage can build on this one without mixing objectives.
62. As a future agent, I want small deterministic tests for scoring, event consumption, portfolio simulation, and tuning reports, so that default tests do not require live Tushare or long-running backtests.

## Implementation Decisions

- The new capability is Scored Entry Allocation Tuning, not a general all-parameter optimizer.
- The active portfolio research term is Scored Portfolio Backtest: eligible same-day entry candidates are scored using pre-entry evidence and compete for cash and holding capacity.
- The scorer uses Outcome-Calibrated Entry Score semantics. Factor contributions come from tuning-window outcomes for buckets and combinations, not raw indicator magnitudes.
- Numerical factor values must be represented as declared buckets or categorical conditions before they can enter the first scorer.
- The scorer contains single-factor bucket weights plus two-factor interaction weights.
- Unfavorable entry factors use Soft Entry Factor Penalty as the main treatment. Hard exclude variants may be compared later, but they are not the main scorer behavior.
- Two-factor interaction weights may be positive or negative.
- The first version uses one global scorer weight set. Market-stage-specific weights are out of scope but market-stage results must be reported.
- Candidate entry requires a Scored Entry Minimum Score combining a training-window z-score floor and a training-window quantile threshold.
- Stage A uses a broad score gate: z-score floor 0.0 and training score quantile 0.50.
- Stage B uses a stricter score gate: z-score floor 0.75 and training score quantile 0.70.
- The workflow uses a Strategy Decision Event Table as its reusable cache. It contains actionable decision intents and decision-time evidence for symbol-date rows.
- The Strategy Decision Event Table is simulation input before scoring, sizing, execution, and portfolio state determine actual trades.
- The main decision table stores actionable intents and required evidence, not every hold, avoid, or unavailable row.
- Hold, avoid, unavailable, and blocked rows can be represented in audits or summaries where needed, but they should not dominate the tuning simulation table.
- The decision cache must not store completed trades, final holdings, cash changes, equity curves, trial-specific scores, or selected buys.
- Each trial recomputes scores, ranking, buy decisions, cash, positions, exits, equity curves, metrics, and funnel counts.
- The workflow uses two-stage walk-forward tuning.
- Walk-forward uses five-year training, one-year test, and one-year step windows.
- The intended test windows are 2020, 2021, 2022, 2023, and 2024.
- Stage A is Trade-Sample Parameter Pre-Tuning.
- Stage A uses a high-capacity portfolio simulation rather than direct completed-trade statistics.
- Stage A broad constraints should allow high holding capacity, broad capital, no daily-new-position cap, no industry-new-position cap, and no cash reserve unless explicitly configured otherwise.
- Stage A output is not a final parameter set. It emits search-space narrowing recommendations for Stage B.
- Stage A elite trials are the Pareto frontier plus the top 20% of trials by balanced selection score.
- Stage A narrows Stage B per-factor and interaction search ranges by inspecting elite-trial weight distributions.
- Stable positive weights, stable negative weights, and unstable weights are classified from elite-trial sign probabilities.
- Stable ranges should use elite-trial percentile bands with margin. Unstable ranges should remain narrow and near-neutral rather than being overconfidently pruned.
- Stage B is Scored Portfolio Parameter Tuning.
- Stage B uses realistic portfolio constraints and validates the scorer under cash, holding, daily-entry, industry, board-lot, tradability, and execution constraints.
- Stage B default initial cash is 10,000,000.
- Stage B default maximum holding count is 20.
- Stage B default maximum new positions per day is 3.
- Stage B default cash reserve ratio is 5%.
- Stage B default industry maximum new positions per day is 1.
- Maximum holding count and maximum new positions per day are external sensitivity controls, not part of the main Optuna search.
- Standard mode runs 300 Stage A trials and 300 Stage B trials per fold.
- Smoke mode runs a smaller trial count to validate the pipeline before a standard run.
- Sensitivity mode can run alternate capacity controls after the default study is working.
- Optuna/TPE is the tuning engine.
- Optuna is an optional tuning dependency, not a core runtime dependency.
- The Optuna study is multi-objective.
- Core Optuna objectives are to maximize annualized return, maximize Sharpe ratio, maximize benchmark excess return, and minimize maximum drawdown.
- Every trial should also record cumulative return, monthly returns, yearly returns, annualized volatility, downside volatility, maximum monthly loss, drawdown recovery days, Sortino ratio, Calmar ratio, information ratio, trade count, win rate, profit/loss ratio, profit factor, average trade return, median trade return, average win return, average loss return, maximum win trade, maximum loss trade, average holding days, average holding count, maximum holding count, average cash ratio, average exposure, turnover, fee/slippage ratio, single-symbol maximum weight, industry concentration, and funnel blockage counts.
- The workflow outputs complete Pareto frontier artifacts.
- The workflow outputs `balanced`, `aggressive`, and `defensive` recommended parameter sets.
- Balanced selection filters for baseline outperformance, drawdown control, minimum trade count, and positive excess return, then ranks by Sharpe, Calmar, yearly stability, and reasonable turnover.
- Aggressive selection allows a wider drawdown band but still requires positive excess return, enough trades, and acceptable risk-adjusted behavior.
- Defensive selection focuses on low drawdown, Calmar, and worst-month control, but must still trade enough and preserve acceptable return.
- Stage A baseline is broad high-capacity unscored filling.
- Stage B baseline is realistic-constraint unscored portfolio simulation.
- Stage B unscored baseline orders same-day candidates by fixed stock-pool file order.
- Minimum trade-count gates are train-per-year 50, test-per-year 20, and full out-of-sample total 120.
- The report must include a Scored Entry Funnel for every major output.
- Scored Entry Funnel counts must include raw entry candidates, score gate blocks, ranking-capacity blocks, max-holding blocks, max-new-position blocks, industry-concentration blocks, cash blocks, tradability blocks, board-lot/min-order blocks, and executed entries.
- The report must clearly separate Stage A pre-tuning evidence, Stage B training evidence, and test-window out-of-sample evidence.
- Final conclusions should be based on Stage B/C out-of-sample scored portfolio results, not Stage A pre-tuning results.
- Exit tuning, add-on tuning, scale-out tuning, and lifecycle rule tuning are future work and must not be silently included in this scope.

## Testing Decisions

- Tests should verify external behavior at the highest useful seam and avoid asserting implementation details of internal helpers.
- Decision event table generation tests should use a small deterministic strategy fixture and verify that actionable decision events and decision-time evidence are captured without completed trade or equity result data.
- Scorer tests should verify single-factor bucket weights, negative soft penalties, two-factor interaction weights, z-score normalization, quantile gates, and score gate blocking.
- Scorer tests should verify that raw numeric indicator magnitudes do not directly control score unless they are represented as declared buckets.
- Portfolio simulation tests should use a small deterministic decision event table to verify same-day candidate ranking, max holding count, daily new-position cap, cash checks, industry limits, board-lot behavior, tradability checks, exit priority, equity curve generation, and blockage reasons.
- Stage A tests should verify broad-constraint simulation, multi-objective trial recording, elite-trial extraction, sign-stability classification, and Stage B search-space narrowing.
- Stage B tests should verify realistic-constraint walk-forward tuning, use of Stage A narrowed ranges, Pareto frontier output, and `balanced`, `aggressive`, and `defensive` parameter selection.
- Report tests should verify that return, annualized return, maximum drawdown, Sharpe, Sortino, Calmar, information ratio, win rate, profit/loss ratio, profit factor, average trade return, trade count, turnover, cash ratio, concentration, yearly stability, market-stage stability, and funnel counts are present.
- CLI tests should verify dry-run, smoke configuration, standard configuration, fold listing, cache identity display, output path display, and clear optional-dependency failure when Optuna is unavailable.
- Cache tests should verify that scorer weights and trial IDs do not invalidate the strategy decision cache, while data snapshot identity, stock pool identity, strategy signal parameters, factor field set, date range, and event schema version do.
- Simulation cache tests should verify that parameter hashes, portfolio-control hashes, fold IDs, and simulator versions are included when trial results are reused.
- Baseline tests should verify that Stage A and Stage B compare against baselines under matching constraints, and that Stage B unscored ordering uses fixed stock-pool order.
- Walk-forward tests should verify that test windows are never used to derive thresholds, z-score statistics, quantile gates, scorer weights, or Stage A search-space narrowing.
- Default automated tests should use synthetic data, fake providers, or tiny persisted fixtures. Live Tushare and long-running 2015-2024 studies are manual acceptance checks, not default test requirements.
- Prior test patterns should follow existing run-plan execution, entry-factor validation, report-builder, CLI smoke, and artifact comparison tests.

## Out of Scope

- Optimizing exits, add-ons, scale-out thresholds, stop-loss thresholds, or lifecycle rules.
- Market-stage-specific scorer weights in the first version.
- Treating Stage A trade-sample pre-tuning results as final portfolio validation.
- Using completed trade deletion as the main validation method.
- Using raw continuous indicator values directly as scorer inputs.
- Recutting factor bucket boundaries during the first scored allocation tuning workflow.
- Automatically promoting tuned parameters into the default strategy.
- Live trading integration or production brokerage execution.
- Guaranteeing profitability or making investment recommendations.
- Fetching new provider data inside report builders.
- Replacing the existing entry-factor validation workflow.

## Further Notes

The current repository already has entry-factor discovery, single-factor validation, and A-anchored pairwise combination validation artifacts. Those artifacts are useful priors and should seed the first scorer universe, but the new workflow must validate scorer behavior under scored portfolio constraints.

Expected standard runtime depends on the decision-event cache and portfolio simulator speed. The current full persisted validation runs take roughly tens of minutes each, so per-trial full backtests are not viable. With a reusable Strategy Decision Event Table, standard mode is expected to be hours rather than days, but the implementation should benchmark smoke trials before launching standard studies.

The first useful implementation should focus on a deterministic, auditable research pipeline rather than a sophisticated optimizer UI. The value of this stage is not simply finding a higher historical return; it is proving whether entry-factor scoring improves real portfolio candidate allocation under out-of-sample walk-forward validation.
