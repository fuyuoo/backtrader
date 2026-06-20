# GoalStock Backtesting

This context defines the language for a data-driven quantitative research and backtesting system for Chinese equities.

## Language

**Backtest Engine**:
The component that simulates orders, positions, cash, fills, commissions, and portfolio state during a historical run.
_Avoid_: Trading system, backtrader framework

**Research Pipeline**:
The data-driven flow that prepares market data, computes features, produces strategy decisions, and evaluates whether a strategy fits a market scenario.
_Avoid_: Strategy engine, trading system

**Strategy Definition**:
A testable description of when and why a portfolio should enter, exit, size, or avoid positions.
_Avoid_: Backtrader strategy

**Strategy Configuration**:
A declared strategy recipe that selects the data scope, active components, thresholds, switches, and evaluation dimensions for a run.
_Avoid_: Script strategy, hard-coded strategy

**Strategy Template**:
A fixed code-backed strategy implementation that declares which entry, profit-taking, stop-loss, sizing, execution, and analysis options it supports.
_Avoid_: Free-form strategy, strategy script

**Trend Template V1**:
The first strategy template used to validate the full framework flow for portfolio backtesting, entry, profit-taking, stop-loss, sizing, A-share constraints, reporting, and scenario fit.
_Avoid_: Demo strategy

**Registered Component**:
A named strategy, indicator, risk, sizing, or analysis capability that can be selected by a strategy configuration.
_Avoid_: Plugin, custom function

**Component Binding**:
The relationship between a strategy template and the registered components that are valid for that template.
_Avoid_: Loose plugin, arbitrary component

**Configuration Switch**:
A named on/off control that includes or excludes a component or rule from a strategy run.
_Avoid_: Flag, toggle

**Run Plan**:
The resolved, immutable plan for one strategy run after all strategy configuration switches and component selections have been evaluated.
_Avoid_: Runtime config, dynamic config

**Data Provider**:
An external or local service that supplies market, industry, index, and reference data to the system.
_Avoid_: Data source

**Tushare Provider**:
The current data provider implementation used to collect Chinese market data.
_Avoid_: Tushare source

**Data Snapshot**:
A local, versioned copy of market, industry, index, or reference data used by cleaning, feature calculation, backtesting, analysis, and tests.
_Avoid_: Raw data, cache

**Run Artifact**:
A persisted output of one completed run, such as the resolved run plan, full execution result, standard report, trade records, and snapshot references.
_Avoid_: Data snapshot, cache

**Execution Ledger**:
A normalized record of account value and position state produced by a backtest engine during a run.
_Avoid_: Backtrader analyzer dump, broker printout

**Execution Audit**:
A chronological order-level audit trail that records submitted, accepted, completed, failed, and constraint-rejected execution events.
_Avoid_: Trade list, broker log

**Execution Cost Summary**:
A report section derived from the execution audit that summarizes order counts, fill rate, rejection rate, commissions, slippage cost, and rejection reasons.
_Avoid_: Raw order log, hidden broker cost

**Equity Curve**:
The per-date account-value series for a completed run, including cash, position value, total value, drawdown, holding count, and exposure.
_Avoid_: Closed-trade return proxy

**Position Snapshot**:
A per-date, per-symbol holding record that captures size, mark price, market value, cost basis, and unrealized profit or loss.
_Avoid_: Open position summary

**Per-Symbol Full Position**:
The intended full exposure for one symbol after all planned entry tranches have been filled. It is distinct from the current position, a single entry tranche, or the whole portfolio.
_Avoid_: Current holding, one buy order, portfolio full position

**Tradable Series**:
A configured OHLCV time series that can be traded by a strategy run, regardless of whether it represents a stock, broad index, industry index, ETF, or a future asset class.
_Avoid_: Stock list, symbol list

**Universe Selection**:
A run-level selection layer that resolves fixed or time-varying eligible symbols for each trading date before strategy methods evaluate entry or exit decisions. It is separate from strategy rules, which only act on the candidates supplied by the run plan.
_Avoid_: Strategy-internal stock filter, hard-coded symbol list, buy-method constituent lookup

**Component Stock Universe**:
A stock universe formed from the constituent stocks of one or more indexes, such as the CSI 300 and CSI 500 constituents. It defines the eligible stocks for a strategy run and is distinct from directly trading the index, an ETF, or an index future.
_Avoid_: Index trade, ETF proxy, vague symbol pool

**Fixed Component Stock Universe**:
A component stock universe frozen to a specific symbol list for a strategy run instead of changing with historical index membership over time. It is useful for first real-run validation, but reports must disclose the fixed-sample limitation and survivor-bias risk.
_Avoid_: Historical constituent backtest, unbiased universe

**Stock Universe Manifest**:
A versioned file that lists the fixed symbols eligible for a strategy run, along with source metadata such as symbol code, name, source index, and freeze date.
_Avoid_: Live constituent query, implicit sample, strategy filter

**Time-Varying Stock Universe Manifest**:
A versioned universe manifest that maps effective dates or months to the eligible symbols for those periods within one strategy run. It is a configuration input to universe selection, not a strategy signal or a live provider lookup.
_Avoid_: Strategy-time constituent query, implicit monthly filter, dynamic buy rule

**Asset Type**:
The declared market category of a tradable or analysis series, such as `stock`, `index`, or `industry_index`. It controls provider fetch behavior and analysis eligibility, not strategy logic.
_Avoid_: Hard-coded instrument branch

**Price Adjustment**:
The price basis used for stored daily bars and derived indicators. Stock daily bars default to front-adjusted `qfq`; indicator snapshots must record or inherit the same price basis.
_Avoid_: Hidden data correction, implicit price mode

**Adjusted Price-Difference Return**:
A trade return measured from front-adjusted price differences over the holding interval, not from strict cash settlement with dividends, split handling, and unadjusted market prices.
_Avoid_: Cash-settled return, corporate-action-complete accounting, unadjusted execution return

**Adjusted Price Cost Simulation**:
A disclosed cost lens that applies configured fees, taxes, and slippage to front-adjusted simulated order values to study cost sensitivity.
_Avoid_: Broker cash settlement, hidden real-cost claim, no-cost return

**Adjusted Price Quantity Simulation**:
A disclosed quantity lens that derives share counts and board-lot execution from front-adjusted simulated prices to preserve position lifecycle rules.
_Avoid_: Broker-accurate share count, pure notional return, hidden real-execution claim

**Tradability Status**:
A per-symbol, per-date state record used by trading constraints, including suspension, limit-up, limit-down, raw close, and daily limit prices.
_Avoid_: Indicator, trading signal

**Historical ST Status**:
A per-symbol, per-date historical special-treatment state used for data-universe filtering and attribution reference sets. It must be determined for the historical trade date, not from the symbol's current name or current listing metadata.
_Avoid_: Current ST flag, current stock name filter, retroactive ST assumption

**Industry Classification**:
A historical relationship that identifies the Shenwan first-level, second-level, and third-level industry for a stock at a point in time.
_Avoid_: Backtest filter, stock universe rule

**Industry Attribution**:
An explanation of backtest results by Shenwan industry after a strategy run has completed.
_Avoid_: Industry strategy, industry selection

**Industry Index Series**:
A Shenwan industry index OHLCV time series used as analysis evidence for attribution and market-regime evaluation. It is not automatically tradable unless also declared as a `Tradable Series`.
_Avoid_: Industry membership, industry label

**Benchmark Series**:
An index time series used to compare and explain a completed strategy run.
_Avoid_: Market data, signal data

**Benchmark Comparison**:
A post-run analysis that compares strategy return with configured benchmark index returns over the same run window and reports excess return where benchmark history exists.
_Avoid_: Trading signal, index strategy

**Decision Series**:
A time series that is explicitly included in a run plan and may influence strategy decisions during a backtest.
_Avoid_: Benchmark, analysis data

**Market Regime**:
A classified market environment used to explain whether a strategy fits the current market context after a run, based on observable market evidence such as trend, breadth, volatility, liquidity, and industry diffusion.
_Avoid_: Water temperature, market feeling

**Environment Dimension**:
A named axis used to group trade evidence when discovering strategy fit, such as market environment, industry environment, entry structure, or execution state.
_Avoid_: One-off AI prompt, hard-coded conclusion, strategy rule

**Environment Factor**:
A measured field inside an environment dimension that can be grouped, summarized, or expanded in an environment discovery matrix.
_Avoid_: Strategy condition, hard-coded report column, free-form AI note

**Post-Trade Environment Lookup**:
A post-run attribution step that looks up market, industry, symbol, or execution context for completed trade records after the strategy has produced trades.
_Avoid_: Entry filter, decision input, look-ahead signal

**Artifact-Bound Attribution Lookup**:
A post-run lookup that derives attribution only from the data snapshots and run artifacts recorded by the completed run, not from fresh provider calls or unrelated recalculation inputs.
_Avoid_: Live-data explanation, current-data replay, unpinned post-hoc lookup

**Water Temperature**:
The user-facing interpretation of `Market Regime`, expressed as deterministic labels such as `cold`, `neutral`, `warm`, `hot`, or `insufficient_evidence`.
_Avoid_: Unstructured AI opinion

**Parameter Tuning**:
The process of searching strategy configuration values to improve a chosen objective across historical runs.
_Avoid_: Smart tuning, auto optimization

**Tuning Set**:
The historical data partition visible to a parameter tuning process.
_Avoid_: Training group, tuning group

**Test Set**:
The historical data partition reserved for final out-of-sample evaluation.
_Avoid_: Testing group

**Portfolio Backtest**:
A strategy run that can hold, enter, exit, and evaluate multiple stocks in one portfolio.
_Avoid_: Multi-stock demo

**Holding Count Cap**:
The maximum number of different symbols that may be open at the same time in a strategy run. It can also be used as the denominator for deriving a per-symbol full position target.
_Avoid_: Cash limit, fixed stock universe size, trade count

**Trade-Sample Backtest**:
A backtest run configured to capture as many valid executed trade samples as possible, often with intentionally large notional capital so capital scarcity does not block entries. Its portfolio-level starting value, ending value, total return, and equity curve are not the primary evidence.
_Avoid_: Portfolio performance test, capital-realistic backtest

**Single-Stock Fixture**:
A small deterministic data snapshot for one stock used to test strategy and engine behavior.
_Avoid_: Single-stock backtest

**Golden Backtest**:
A deterministic backtest against a fixed data snapshot with expected outputs used for regression testing.
_Avoid_: Example run, smoke test

**Regression Test**:
A test that protects previously accepted behavior, including configuration validation, component output, engine adaptation, and golden backtest results.
_Avoid_: Retest

**Timeframe Resampling**:
The deterministic aggregation of daily OHLCV bars into weekly or monthly bars using first open, max high, min low, last close, and summed volume or amount.
_Avoid_: Dynamic timeframe magic

**Warmup Data Range**:
The pre-backtest data range loaded only to make indicators and lookback-dependent strategy checks valid before statistics begin.
_Avoid_: Backtest period, counted trading sample, default-filled indicator rows

**Indicator Coverage Alarm**:
A run-level data quality alert raised when required indicator values are missing beyond an accepted threshold for the configured backtest window.
_Avoid_: Default-filled indicator, silent missing data, strategy signal

**Indicator Coverage Eligible Date**:
A symbol-date included in indicator missing-value checks only after the symbol has base daily bars and the required indicator warmup window is available.
_Avoid_: Listing-before data gap, warmup row, market-wide calendar denominator

**Signal Rule**:
A rule that converts prepared data and features into an entry, exit, hold, or avoid decision.
_Avoid_: Buy rule, sell rule, order rule

**Entry Method**:
A code-backed method bound to a strategy template that determines when the strategy should enter a position.
_Avoid_: Buy strategy

**Profit-Taking Method**:
A code-backed method bound to a strategy template that determines when the strategy should exit a profitable position.
_Avoid_: Take-profit setting

**Scale-Out**:
A partial profitable sell that reduces an open position while keeping the remaining position alive for later profit-taking or stop-loss decisions.
_Avoid_: Full exit, closed trade, cost-basis rewrite

**ATR-Based Scale-Out**:
A scale-out whose profit trigger is expressed as the adjusted remaining cost basis before sale plus a multiple of the entry signal-day ATR14 volatility distance instead of as a fixed percentage return.
When the entry signal-day ATR14 is missing, the position does not use ATR-based scale-out and the missing evidence is recorded.
KDJ J, CCI, and Bollinger upper-band values may be recorded as scale-out evidence without blocking the scale-out decision.
_Avoid_: Fixed-percent scale-out, ART scale-out, full exit

**Full Exit**:
A sell decision that closes all remaining quantity of an open position and ends that position's trade lifecycle.
_Avoid_: Scale-out, partial sell, cost reduction

**DEA Waterline Cycle**:
A decision-layer MACD state where DEA has moved above the zero line and remains above it until DEA returns to zero or below. It is strategy evidence, not a separate reusable indicator.
_Avoid_: MACD calculation, permanent bullish state

**MACD Attribution Bar**:
The MACD bar value used for attribution language and bucket classification, aligned with common Chinese charting software as twice the distance between DIF and DEA.
_Avoid_: Raw indicator histogram, unstated MACD scaling

**MACD Energy Zone**:
A daily or weekly attribution category that explains where DIF, DEA, and the MACD attribution bar sit relative to each other and whether red-bar energy is expanding or weakening.
_Avoid_: Buy signal, sell signal, causal proof

**Stop-Loss Method**:
A code-backed method bound to a strategy template that determines when the strategy should exit a losing position.
_Avoid_: Stop-loss setting

**Stop-Loss Watch**:
A risk state after a stop-loss observation condition has been met but before the next completed bar confirms whether the position should be exited.
_Avoid_: Immediate stop order, add-on opportunity

**Profit-Exit Watch**:
A profit-protection state after a profit-taking observation condition has been met but before the next completed bar confirms whether the position should be exited.
_Avoid_: Add-on opportunity, immediate full exit

**Trade Intent**:
A standardized decision emitted by an entry, profit-taking, or stop-loss method before sizing and execution, such as enter, exit profit, exit loss, hold, or avoid. It includes explanatory evidence such as the method name, reason code, signal values, risk price, target price, confidence, and any blocking constraint.
_Avoid_: Order, buy/sell command

**Entry Attribution**:
A post-run explanation that links a completed trade back to its entry date and the entry decision evidence that was visible on that date.
_Avoid_: Report recalculation, hindsight indicator calculation

**Entry Signal Date**:
The trading date whose completed bar provides the entry decision evidence for an entry that executes on the following trading date. For a trade executed on day T, the entry signal date is T-1 in the Baoma entry flow.
_Avoid_: Entry execution date, same-day open evidence, post-entry evidence

**Entry Attribution Configuration**:
The run-plan section that selects which declared entry attribution factors are retained, configures market and industry attribution parameters, and optionally enables decision-layer entry filters before sizing.
_Avoid_: Indicator config, report-only option

**Entry Attribution Factor**:
A structured piece of entry-time evidence used by entry attribution, such as a boolean condition check or numeric market feature value observed on the trade's entry date. Each factor is scoped by what it describes, such as the traded symbol, its industry, the broader market, or sizing context.
_Avoid_: Calculated-after-the-fact metric, default-filled indicator

**Entry Attribution Factor Declaration**:
An explicit declaration of an entry attribution factor's key, type, human label, scope, dependencies, and missing-data behavior.
_Avoid_: Ad hoc signal key, implicit report field

**Attribution Factor Registry**:
The shared declaration catalog for framework-owned and strategy-owned attribution factors that may be enabled by a run plan and summarized after trades exist.
_Avoid_: Separate report logic, one-off strategy column, implicit factor list

**Attribution Factor Selection**:
A run-plan choice that explicitly lists which declared attribution factors are included in post-run analysis and which known factors are intentionally not included. Included factors are calculated and summarized; explicitly not-included factors are recorded for audit visibility but do not affect the run.
_Avoid_: Factor bundle, hidden default report fields, analyze-everything mode, implicit unused factor list

**Attribution Field Index**:
A persisted wide-table style index of available attribution fields and sample values used to inspect, filter, and choose candidate environment factors before adding a smaller default field set to an environment fit report.
_Avoid_: Environment fit report, strategy signal table, implicit factor selection

**Attribution Wide Sample**:
A completed-trade attribution sample row that preserves both raw numeric factor values and derived bucket values for inspection, bucket redesign, and downstream field selection.
_Avoid_: Bucket-only sample, report-only aggregate, recalculated factor row

**Attribution Data Staleness**:
The age, in trading days, between an attribution sample's measurement date and the as-of date of the historical data used for that factor. Limited forward-fill is allowed only when staleness is recorded and remains within the declared maximum.
_Avoid_: Silent forward-fill, realtime backfill, treating stale data as same-day evidence

**Attribution Data Exception**:
A recorded reason that explains why an attribution factor value, bucket, or reference percentile is missing, excluded, stale, or otherwise not comparable for a sample.
_Avoid_: Silent missing value, dropped sample, unexplained exclusion

**Resolved Attribution Factor Selection**:
The run-specific attribution factor set after applying strategy, data, and indicator applicability. It records included factors and derives not-included factors as the applicable factor set minus the configured include list.
_Avoid_: Hand-maintained unused list, all-registry dump, undocumented factor availability

**Attribution Factor Applicability Declaration**:
The metadata that states when an attribution factor can be used, including its owner, timing, required indicators or artifacts, compatible strategy methods, value type, source, and missing-data policy.
_Avoid_: Report-time guess, factor key only, undocumented dependency

**Attribution Factor Timing**:
The lifecycle point or window where an attribution factor is measured, such as entry, exit, holding, or post-exit.
_Avoid_: Entry-only attribution, unlabeled report field, mixed timing bucket

**Framework Attribution Factor**:
An attribution factor owned by the framework and reusable across strategies, such as market trend, industry state, moving-average structure, distance to moving averages, or exit-time context.
_Avoid_: Strategy-specific signal, hard-coded report metric

**Strategy Attribution Factor**:
An attribution factor owned by a specific strategy definition and meaningful only for strategies that declare it, such as a baoma-specific distance to MA60 or DEA waterline-cycle age.
_Avoid_: Framework-wide metric, hidden strategy signal, report-only special case

**Entry Attribution Evidence**:
The structured evidence captured with an entry decision so completed trades can later be explained by the conditions, values, and categories visible at entry time.
_Avoid_: Free-form signal dump, report-only evidence

**Entry Attribution Evidence Producer**:
The strategy method or shared evidence builder that captures entry attribution evidence at decision time and owns the declarations for the factors it emits.
_Avoid_: Report owner, implicit statistics owner

**Entry Attribution Filter**:
A decision-layer rule that requires selected attribution check factors to be true before an entry intent can reach sizing. Missing checks follow an explicit policy and remain missing in statistics.
_Avoid_: Indicator, report filter, default false check

**Entry Attribution Scope**:
The source domain described by an entry attribution factor, such as symbol, industry, market, or sizing.
_Avoid_: Flat factor bucket, unlabeled evidence

**Entry Attribution Sample**:
A completed trade used as one observation in entry attribution statistics. Rejected, blocked, or unfilled entry intents are execution or opportunity evidence, not profit/loss attribution samples.
_Avoid_: Entry signal sample, rejected-trade attribution sample

**Primary Entry Attribution**:
Entry attribution based on the initial successful entry that opens a completed trade's position. Add-on entries are separate position-lifecycle evidence, not blended into the primary entry sample.
_Avoid_: Blended entry attribution

**Entry Attribution Summary**:
A post-run aggregation of entry attribution samples, grouped by outcome and optionally by symbol or portfolio-wide scope.
_Avoid_: Raw trade list, ungrouped signal count

**Entry Attribution Coverage**:
The proportion of entry attribution samples where a factor is present. Missing evidence is measured separately and is never treated as false, zero, neutral, or a report-time default.
_Avoid_: Default-filled coverage, implicit false evidence

**Negative PE Bucket**:
An explicit valuation bucket for entry attribution samples whose PE value is negative. It represents loss-making valuation evidence and is separate from missing PE evidence.
_Avoid_: Missing PE, low PE, default-filled PE

**Market Capitalization Bucket**:
A pair of entry attribution buckets for total market value or free-float market value: an absolute-amount bucket for human interpretation and a full-A-share historical cross-sectional percentile bucket for comparing symbols across runs and stock universes.
_Avoid_: One-size market cap label, hidden universe-relative size, run-universe-only percentile, real-time market cap

**Valuation Bucket**:
A pair of entry attribution buckets for PE, PE_TTM, or PB: an absolute-value bucket for human interpretation and a full-A-share historical cross-sectional percentile bucket for comparing symbols across runs and stock universes. Negative PE and PE_TTM values use a separate loss-making bucket; missing values remain missing. Non-positive PB values use a separate non-positive bucket rather than a low-PB bucket.
_Avoid_: Realtime valuation, default-filled valuation, run-universe-only percentile, treating negative PE as missing, treating non-positive PB as cheap

**Volatility Bucket**:
An entry attribution bucket that describes a symbol's volatility using both absolute symbol-level measures and measures relative to the symbol's Shenwan first-level industry. It supports fixed profit-taking and stop-loss fit review without becoming a strategy decision rule.
_Avoid_: Hidden volatility filter, default-filled volatility, industry-agnostic volatility label

**Industry Fit Factor**:
An entry attribution factor that groups completed trades by Shenwan first-level industry and may compare symbol-level volatility with industry-level volatility to review whether a strategy fits some industries better than others.
_Avoid_: Industry entry filter, industry strategy, post-hoc industry signal

**Liquidity Fit Factor**:
An entry attribution factor that describes entry-time trading activity, such as turnover rate, amount, average amount, or amount percentile, to review whether results differ across liquidity environments.
_Avoid_: Liquidity entry filter, execution rule, default-filled liquidity

**Profit-Taking Fit Factor**:
An entry attribution factor that compares a fixed profit-taking threshold with entry-time volatility, displayed as how many ATR units the fixed threshold represents. For a fixed 5 percent threshold, the underlying measure is `5% / ATR%`.
_Avoid_: Profit-taking rule, optimized target, hidden sell condition

**Stop-Loss Fit Factor**:
An entry attribution factor that compares the executed entry price with the signal-day MA60 using signal-day ATR units. The standard measure is `(entry_price - signal_day_ma60) / signal_day_atr`.
_Avoid_: Stop-loss rule, optimized stop distance, using future-day indicators

**Entry Attribution Contrast**:
A comparison between winning and losing entry attribution samples that ranks factors by differences such as true-rate gap, average-value gap, or category-rate gap.
_Avoid_: Predictive signal proof, statistical causality claim

**Bayesian Factor Discovery**:
A post-run statistical lens that classifies persisted attribution evidence into favorable, unfavorable, or weak candidate factor buckets using completed-trade outcomes. It is research evidence only and does not create live entry, exit, scale-out, or sizing rules.
_Avoid_: Bayesian parameter tuning, live trading model, causal proof

**Factor Quality Score**:
A research scoring objective for Bayesian factor discovery that balances capital return, per-trade expected return, profit factor, win rate, drawdown risk, and sample reliability when ranking factor buckets. It is not a portfolio Sharpe ratio and is not an automatic parameter-tuning target.
_Avoid_: Sharpe ratio proxy, win-rate-only score, optimization objective

**Tradable Pre-Entry Factor Discovery**:
The part of Bayesian factor discovery that only uses evidence visible at or before the entry decision, making it eligible for later review as a candidate strategy rule.
_Avoid_: Full-lifecycle diagnosis, future-data factor, post-trade filter

**All Entry Single-Factor Attribution Analysis**:
A pre-entry attribution review that examines all individual entry-time factors directly to screen candidate entry factor values. Candidate screening happens at the factor-value level, such as keeping or excluding a specific `field=value`, while the factor-field level is only used for summary ranking and navigation. Values that satisfy the full candidate threshold form separate keep-filter and exclude-filter validation candidate pools; values with visible but incomplete evidence stay on direction-specific watchlists instead of being promoted. It does not try to explain every source of returns, compress factors into broader themes, or combine multiple factors into a rule. It is research evidence for understanding each factor value's standalone relationship with completed-trade outcomes, not a validation run or a strategy change.
_Avoid_: Whole-field rule, return-source explanation, theme compression, multi-factor rule search, real validation matrix, treating watchlist evidence as validated

**Entry Single-Factor Candidate Screening Report**:
A derived report that screens the all-entry single-factor attribution facts into keep-filter candidates, exclude-filter candidates, direction-specific watchlists, execution factors, and exposure watchlists. It is separate from the base all-entry single-factor attribution report so factual attribution and candidate screening decisions remain distinct.
_Avoid_: Replacing the base attribution report, theme report, validation matrix, strategy rule file

**Entry Execution Factor**:
An entry candidate factor that is observable at the entry execution moment, such as the opening gap from the entry signal date close to the entry execution price. It may be screened together with entry-time factors when the intended rule can act at the execution moment, but it must be labeled separately from T-1 pre-selection evidence.
_Avoid_: Previous-night stock selection factor, post-entry evidence, hidden future data

**Entry Exposure Watchlist Factor**:
An entry attribution factor value that describes exposure sensitivity, such as a Shenwan industry code, and is useful for risk review but should not become a formal keep or exclude candidate without separate stability evidence across periods or market stages.
_Avoid_: Immediate hard industry rule, generic entry factor, validated filter

**Entry Factor Optimization Experiment**:
A validation experiment that turns tradable pre-entry factor findings into candidate entry filters and tests them with separate backtest evidence before any strategy rule is changed. It only concerns entry-time factors and does not optimize exits, scale-outs, sizing, or lifecycle diagnostics.
_Avoid_: Bayesian parameter tuning system, live rule change, lifecycle optimization

**Market-Stage Stratified Entry Validation**:
An entry-factor validation lens that compares candidate filters by year and by objective entry market stage so market-regime differences are not mistaken for factor quality. It treats stage-specific results as conditional evidence rather than universal entry rules.
_Avoid_: Simple year split, bull-market overfit, unconditioned validation

**Single-Factor Entry Filter Experiment**:
An entry optimization experiment that tests one tradable pre-entry factor bucket at a time as either a keep filter for favorable buckets or an exclude filter for unfavorable buckets. It deliberately avoids multi-factor rule search, threshold retuning, ranking, and sizing changes in its first version.
_Avoid_: Multi-factor optimizer, parameter search, position ranking

**Offline Entry Filter Screening**:
A pre-backtest screening step that applies candidate entry filters to already persisted completed-trade samples to estimate directional impact before spending full backtest runs. It is not a substitute for real backtest validation because it cannot model freed capital, changed holding pressure, or replacement trades.
_Avoid_: Final validation, real portfolio simulation, strategy proof

**Single-Factor Real Validation Matrix**:
A validation matrix that tests each candidate tradable pre-entry factor as its own real strategy variant against the same baseline before any factor is combined with another. It classifies factors as stable favorable, stable unfavorable, market-stage dependent, or noise.
_Avoid_: Sequential lock-in, offline-only screening, multi-factor search

**Stable Entry Factor Combination Validation**:
A second-stage validation that combines only factors that survived single-factor real validation and re-runs the strategy after each added filter. It checks whether individually useful entry factors still improve the strategy when combined.
_Avoid_: Exhaustive combination search, unvalidated factor stacking, permanent default rule

**Full-Lifecycle Attribution Diagnosis**:
A comprehensive Bayesian attribution view that may include entry, exit, holding-path, post-exit, and scale-out evidence to explain where a strategy works or fails across the trade lifecycle. It is diagnostic evidence and must not be treated as an entry signal when it uses information unavailable at entry time.
_Avoid_: Tradable pre-entry factor, future-function buy rule, automatic strategy change

**Lifecycle Diagnostic Factor**:
A factor bucket from exit, holding-path, post-exit, scale-out, or other post-entry evidence that explains trade outcomes but is not eligible to become an entry rule without a separate pre-entry proxy.
_Avoid_: Entry signal, tradable factor, future-function filter

**Exit Attribution**:
A post-run explanation that links a completed trade back to the exit intent that closed it and summarizes the decision evidence visible at exit time.
_Avoid_: Entry attribution, report-time exit calculation

**Scale-Out Attribution**:
A post-run explanation that starts from executed scale-out events and uses the actual execution date to look up context such as KDJ J, CCI, Bollinger upper band, and pre-sale profit evidence without treating those fields as scale-out decision inputs.
_Avoid_: Exit attribution, scale-out signal condition, closed-trade-only attribution

**Add-On Attribution Output**:
The lifecycle-attribution output that links successful add-on intents to the completed trade that was open after primary entry and before exit. It keeps primary entry attribution separate while summarizing add-on evidence by winning and losing trade outcomes.
_Avoid_: Blended entry attribution, hidden scale-in evidence

**Trade Lifecycle Artifact**:
A run artifact that stores each completed trade's entry, successful add-on, and exit timeline with linked signal evidence and execution audit events.
_Avoid_: Recalculated trade explanation, report-only timeline

**Trade Lifecycle Index**:
A navigation index inside the trade lifecycle artifact, grouping completed trades by evidence fields such as outcome, add-on count, entry checks, categories, and rejection reasons without creating new analysis facts.
_Avoid_: New strategy metric, inferred trade state

**Trade Review Artifact**:
A consolidated downstream run artifact that joins completed-trade lifecycle, post-exit sold-too-early labels, stop-loss rebound profiles, opportunity/block samples, and add-on entry-point follow-up without rerunning strategy logic.
_Avoid_: New strategy source, report-time trade inference

**Environment Fit Report**:
A downstream artifact that groups completed trades by decision-time entry environment and summarizes win rate, return, completed-order net PnL, and return on entry value. It consumes persisted trade review and lifecycle evidence only.
_Avoid_: Indicator calculation, causal environment proof, auto filter recommendation

**Environment Fit Comparison**:
A cross-run review artifact that compares existing `environment_fit.json` files for best-environment stability, low-sample risk, common-environment deltas, and representative `trade_index` drill-down refs.
_Avoid_: Strategy tuning result, rerun trigger, parameter leaderboard

**AI Review Packet**:
A focus-specific, AI/Skill-friendly view generated from persisted run artifacts. It includes source artifact pointers, an evidence-use contract, summaries, and capped samples with `trade_index` or `sample_index` for backtracking.
_Avoid_: AI-generated evidence, recalculated analysis layer

**AI Review Findings**:
A structured finding draft generated from an AI review packet. It carries citation-ready finding IDs, evidence references, sample references, caveats, and next checks for an AI reviewer.
_Avoid_: Final strategy judgment, unsupported AI conclusion

**Review Sample Drill-Down**:
A focused evidence packet for one trade, opportunity, or add-on sample, built from persisted artifacts using `trade_index` or `sample_index`.
_Avoid_: Whole-run report, recalculated sample evidence

**Review Sample Batch**:
A downstream artifact that expands sample references from AI review findings into a compact batch of sample evidence summaries and optional individual sample packet paths.
_Avoid_: New metric table, strategy sample generator

**AI Review Brief**:
A Skill-ready artifact that combines AI review findings, expanded sample summaries, evidence-use rules, a first-page environment-fit summary, and an expected output schema.
_Avoid_: Free-form AI prompt, final strategy report

**AI Review Result**:
A persisted structured review output derived from an AI review brief, optionally enriched with environment-fit comparison evidence, keeping claims, evidence references, sample references, risks, and next checks.
_Avoid_: Uncited AI summary, strategy tuning result

**Review Experiment Candidate**:
A validation idea derived from review findings and sample evidence, such as an evidence grouping probe or blocked-reason investigation. It is not a parameter change by itself.
_Avoid_: Tuning recommendation, strategy change request

**Review Experiment Draft**:
A manually confirmable YAML planning artifact generated from a review experiment candidate. It is not an executable RunPlan until reviewed and converted.
_Avoid_: Auto-generated strategy config, accepted experiment

**Confirmed Review Experiment RunPlan**:
A validated RunPlan YAML generated from exactly one manually confirmed review experiment draft. Review metadata is stripped from the executable YAML and kept in the confirmation manifest.
_Avoid_: Automatic tuning, unreviewed draft execution, mixed evidence/config YAML

**Post-Exit Follow-Up**:
A downstream evidence view that starts from completed trades, matched exit intents, and prepared market bars, then observes configured windows after an exit to review what happened after stop-loss or profit-taking. It does not rerun strategy methods or recalculate indicators.
_Avoid_: Exit signal calculation, post-hoc strategy rule

**Sold Too Early**:
An explanatory post-exit review label applied when price rebounds above the exit price within the configured follow-up window after sale. It is a review aid, not proof that the strategy should have held or a causality claim.
_Avoid_: Optimization target, hindsight sell rule

**Sizing Rule**:
A rule that converts a signal and portfolio state into target exposure or order size.
_Avoid_: Position sizing function

**Execution Rule**:
A rule that converts target exposure or order intent into instructions for a backtest engine.
_Avoid_: Buy/sell method

**Trading Constraint**:
A market rule or simulation rule that can allow, reject, resize, or reprice an intended trade during a strategy run.
_Avoid_: Broker setting

**Pending Exit Intent**:
A confirmed exit decision that could not be fully executed because of trading constraints and remains active until the position is cleared.
_Avoid_: Fresh exit signal, entry retry, cancelled sell order

**Execution Lifecycle Foundation**:
The execution and position-state behavior required before strategy signals can produce trustworthy trade records, including trade timing, sellable lots, partial exits, pending exits, and cost basis.
_Avoid_: Strategy signal, report-only attribution, broker default behavior

**Execution Lifecycle Component**:
A business-layer component that turns accepted strategy intents and trading constraints into position lifecycle state, execution events, and trade records before report attribution.
_Avoid_: Backtrader-only bridge logic, report reconstruction, strategy method

**Lifecycle Golden Scenario**:
A deterministic execution-lifecycle example used to define and verify expected trade timing, lot state, partial exits, pending exits, and cost-basis behavior.
_Avoid_: Vague behavior note, performance target, strategy optimization case

**Strategy Lifecycle State Machine**:
A finite set of position lifecycle states and transitions that defines which entry, add-on, scale-out, full-exit, pending-exit, and end-of-run actions are allowed.
_Avoid_: Loose rule list, report-only phase label, indicator state

**Lifecycle State Label**:
A user-facing display label for a lifecycle state, usually localized for reports while the code keeps a stable enum value.
_Avoid_: Separate state, translated business rule, free-form report text

**Lifecycle Action Permission Table**:
A pre-state-machine matrix that lists whether each lifecycle situation allows entry, add-on, scale-out, full exit, pending-exit retry, or end-of-run handling.
_Avoid_: Free-form rule list, hidden branch logic, report-only table

**Lifecycle Transition Table**:
A state-machine table that defines how lifecycle states change after signals, executions, rejections, cost-basis updates, and end-of-run handling.
_Avoid_: Hidden if/else order, report-side inference, undocumented transition

**Authoritative Lifecycle Output**:
The lifecycle evidence source that downstream reports, environment lookup, and AI review must trust for execution events, lot state, position lifecycle, trade records, and cost-basis state.
_Avoid_: Broker-only inference, report-side reconstruction, duplicate evidence source

**China A-Share Constraint Set**:
The trading constraints needed to simulate Chinese A-share behavior, including T+1 selling, limit-up and limit-down behavior, suspension, board-lot sizing, fees, slippage, and cash checks.
_Avoid_: A-share mode

**Backtest Report**:
A standard result model for a completed strategy run, covering return, risk, trade quality, portfolio behavior, execution costs, industry attribution, benchmark comparison, and market regime fit.
_Avoid_: Analyzer output, result dict

**Real-Run Regression Baseline**:
An accepted metric snapshot for persisted real Tushare run artifacts, used to detect framework drift without rerunning strategy search or treating the numbers as optimization targets.
_Avoid_: Parameter tuning objective, performance leaderboard

**Portfolio Behavior**:
A post-run summary of how the portfolio behaved across symbols, including open holding count, open symbols, cash ratio when broker state is available, closed-symbol count, and per-symbol trade contribution.
_Avoid_: Raw broker dump, position printout

**Adjusted Remaining Cost Basis**:
The per-share cost basis used for a remaining position after cost-inclusive realized scale-out proceeds are applied to reduce that position's cost.
_Avoid_: Raw average buy cost, report-only realized PnL

**Cost Recovered Position**:
A remaining position whose adjusted remaining cost basis is zero or below after scale-out proceeds have recovered the original position cost.
_Avoid_: Infinite return, free shares, completed trade

**Scenario Fit**:
A rule-based post-run judgment that combines return, drawdown, win rate, profit/loss ratio, benchmark excess return, industry attribution, and market regime evidence into a deterministic fit label.
_Avoid_: AI conclusion, suitability opinion

**Strategy Environment Discovery**:
The use of backtest evidence to identify the market, industry, and entry-condition environments where a strategy tends to work or fail.
_Avoid_: Perfect return proof, parameter optimization, leaderboard result

**Environment Discovery Matrix**:
A post-run grouping table that compares trade outcomes across configured environment dimensions to identify favorable and unfavorable strategy contexts.
_Avoid_: Parameter tuning grid, free-form AI notes, optimized strategy rule

**Engine Adapter**:
The boundary that translates a strategy definition and prepared data into a specific backtest engine's native objects.
_Avoid_: Strategy wrapper, glue code

**All-Eligible Entry Fill**:
A sample-collection entry policy that opens every no-position symbol whose entry signal is eligible, stopping only when a holding-count cap is reached.
_Avoid_: Ranking model, signal-strength selector, portfolio optimizer

**Entry Candidate Ordering**:
A run-level rule for ordering same-day eligible entry candidates when the remaining holding-count capacity is smaller than the candidate set.
_Avoid_: Hidden sort, implicit alpha model, nondeterministic candidate order

**Net Trade View**:
A primary trade-sample result view that includes configured fees, taxes, slippage, and execution costs.
_Avoid_: Raw signal return, no-cost benchmark

**Gross Trade View**:
A derived trade-sample result view that removes fees, taxes, slippage, and execution costs from the same executed trade events.
_Avoid_: Separate rerun, alternate trade path, replacement for net results

**Execution Cost Assumption**:
A run-level configurable assumption for commissions, taxes, slippage, and other execution costs that must be disclosed with the backtest result.
_Avoid_: Hard-coded cost model, hidden broker default

**Forced End Liquidation View**:
A result view that converts positions still open at the end of a backtest into artificial exits under explicit end-of-run assumptions.
_Avoid_: Strategy exit signal, real sell confirmation, hidden mark-to-market

**Open-Position Excluded View**:
A result view that excludes positions still open at the end of a backtest from completed-trade statistics while reporting them separately.
_Avoid_: Forced liquidation result, ignored open risk, incomplete trade counted as completed

**End-of-Run Liquidation Switch**:
A run-plan configuration switch that controls whether open positions at the end of a run are converted into forced end-liquidation records under explicit closing-price assumptions.
_Avoid_: Strategy natural exit, hidden cleanup, default completed trade

**End Liquidation Failure**:
A failed forced end liquidation attempt where an open position cannot be converted into an artificial exit under the configured end-of-run assumptions.
_Avoid_: Completed trade, strategy exit signal, ignored open position
