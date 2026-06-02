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

**Tradable Series**:
A configured OHLCV time series that can be traded by a strategy run, regardless of whether it represents a stock, broad index, industry index, ETF, or a future asset class.
_Avoid_: Stock list, symbol list

**Asset Type**:
The declared market category of a tradable or analysis series, such as `stock`, `index`, or `industry_index`. It controls provider fetch behavior and analysis eligibility, not strategy logic.
_Avoid_: Hard-coded instrument branch

**Price Adjustment**:
The price basis used for stored daily bars and derived indicators. Stock daily bars default to front-adjusted `qfq`; indicator snapshots must record or inherit the same price basis.
_Avoid_: Hidden data correction, implicit price mode

**Tradability Status**:
A per-symbol, per-date state record used by trading constraints, including suspension, limit-up, limit-down, raw close, and daily limit prices.
_Avoid_: Indicator, trading signal

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

**Signal Rule**:
A rule that converts prepared data and features into an entry, exit, hold, or avoid decision.
_Avoid_: Buy rule, sell rule, order rule

**Entry Method**:
A code-backed method bound to a strategy template that determines when the strategy should enter a position.
_Avoid_: Buy strategy

**Profit-Taking Method**:
A code-backed method bound to a strategy template that determines when the strategy should exit a profitable position.
_Avoid_: Take-profit setting

**Stop-Loss Method**:
A code-backed method bound to a strategy template that determines when the strategy should exit a losing position.
_Avoid_: Stop-loss setting

**Trade Intent**:
A standardized decision emitted by an entry, profit-taking, or stop-loss method before sizing and execution, such as enter, exit profit, exit loss, hold, or avoid. It includes explanatory evidence such as the method name, reason code, signal values, risk price, target price, confidence, and any blocking constraint.
_Avoid_: Order, buy/sell command

**Sizing Rule**:
A rule that converts a signal and portfolio state into target exposure or order size.
_Avoid_: Position sizing function

**Execution Rule**:
A rule that converts target exposure or order intent into instructions for a backtest engine.
_Avoid_: Buy/sell method

**Trading Constraint**:
A market rule or simulation rule that can allow, reject, resize, or reprice an intended trade during a strategy run.
_Avoid_: Broker setting

**China A-Share Constraint Set**:
The trading constraints needed to simulate Chinese A-share behavior, including T+1 selling, limit-up and limit-down behavior, suspension, board-lot sizing, fees, slippage, and cash checks.
_Avoid_: A-share mode

**Backtest Report**:
A standard result model for a completed strategy run, covering return, risk, trade quality, portfolio behavior, execution costs, industry attribution, benchmark comparison, and market regime fit.
_Avoid_: Analyzer output, result dict

**Portfolio Behavior**:
A post-run summary of how the portfolio behaved across symbols, including open holding count, open symbols, cash ratio when broker state is available, closed-symbol count, and per-symbol trade contribution.
_Avoid_: Raw broker dump, position printout

**Scenario Fit**:
A rule-based post-run judgment that combines return, drawdown, win rate, profit/loss ratio, benchmark excess return, industry attribution, and market regime evidence into a deterministic fit label.
_Avoid_: AI conclusion, suitability opinion

**Engine Adapter**:
The boundary that translates a strategy definition and prepared data into a specific backtest engine's native objects.
_Avoid_: Strategy wrapper, glue code
