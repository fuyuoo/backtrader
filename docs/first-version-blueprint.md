# First Version Blueprint

This blueprint defines the first usable version of `attbacktrader`: a data-driven, testable quantitative research and portfolio backtesting framework that uses backtrader through an engine adapter.

## Scope

The first version will support deterministic multi-stock portfolio backtests for Chinese A-shares. It will use local data snapshots, YAML configuration, fixed code-backed strategy templates, configurable entry/profit-taking/stop-loss methods, business-layer trading constraints, standardized reports, and regression tests.

The first version will not implement Bayesian parameter tuning. Parameter tuning is a later capability recorded in ADR 0003.

## Package Layout

The authoritative placement guide for new modules, commands, scripts, and tests is `docs/architecture/project-structure.md`. The layout below records the first-version target shape, while the architecture guide explains where future additions belong.

```text
attbacktrader/
  __init__.py
  config/
    models.py
    loader.py
    validation.py
  data/
    bars.py
    indexes.py
    industries.py
    resampling.py
    tradability.py
    providers/
      base.py
      tushare.py
    snapshots/
      index_store.py
      industry_store.py
      parquet_store.py
      csv_store.py
  features/
    aggregation.py
    frame.py
    indicators.py
    snapshots.py
  strategies/
    bindings.py
    intents.py
    templates/
      trend_template_v1.py
    methods/
      entry.py
      profit_taking.py
      stop_loss.py
  constraints/
    ashare.py
  engines/
    ledger.py
    backtrader/
      adapter.py
      strategy_bridge.py
      feeds.py
  analysis/
    benchmarks.py
    attribution.py
    pipeline.py
    regime.py
    scenario_fit.py
  reports/
    assembly.py
    models.py
    writer.py
  runners/
    prepared_data.py
    run_plan.py
  cli/
    run_plan.py
    tushare_backtest.py
```

The existing `backtrader/` package remains the engine library. `attbacktrader/` owns the business framework.

## Configuration

The first version uses one YAML file, `run.yaml`, validated into an immutable run plan before execution. Configuration switches are resolved before the backtest starts and do not change during the run.

Example shape:

```yaml
run:
  id: trend-v1-example
  from_date: "2021-01-01"
  to_date: "2023-12-31"

data:
  snapshot_root: data/snapshots
  provider: tushare
  price_adjustment: qfq
  refresh_snapshots: true
  tradable_series:
    - symbol: "000001.SZ"
      asset_type: stock
      price_adjustment: qfq
    - symbol: "600519.SH"
      asset_type: stock
      price_adjustment: qfq
    - symbol: "000001.SH"
      asset_type: index
  decision_series:
    indexes: []
  benchmark_series:
    indexes: ["000001.SH", "000300.SH", "399006.SZ", "000510.SH"]
  industry_series:
    source: SW2021
    indexes: ["801780.SI", "801120.SI"]

strategy:
  template: trend_template_v1
  entry_method: kdj_oversold_entry
  profit_taking_method: kdj_overheated_exit
  stop_loss_method: fixed_percent_stop
  sizing_rule: equal_weight

constraints:
  ashare:
    enabled: true
    t_plus_one: true
    limit_up_down: true
    suspension: true
    board_lot_size: 100

broker:
  initial_cash: 1000000
  commission_rate: 0.0003
  stamp_tax_rate: 0.001
  transfer_fee_rate: 0.00001
  slippage:
    type: percent
    value: 0.0005

execution:
  engine: backtrader
  stake: 100

output:
  persist: true
  report_root: reports

analysis:
  industry_attribution:
    enabled: true
    source: SW2021
    levels: [1, 2, 3]
  market_regime:
    enabled: true
    timeframes: ["D", "W", "M"]
  scenario_fit:
    enabled: true
    min_trades: 3
```

## Data Snapshots

`Data Provider` implementations collect data. Research, backtesting, reporting, and tests consume `Data Snapshot` files.

Time-series snapshots use Parquet:

```text
data/snapshots/
  daily_bars/
    qfq/
      000001_SZ_20240101_20240331.parquet
  tradable_bars/
    index/
      none/
        000001_SH_20240101_20240331.parquet
  tradability/
    stock/
      000001_SZ_20240101_20240331.parquet
  indicators/
    kdj/
      qfq/
        000001_SZ_20240101_20240331.parquet
      index/
        none/
          000001_SH_20240101_20240331.parquet
  indexes/
    000001_SH_20240101_20240331.parquet
    000300_SH_20240101_20240331.parquet
    399006_SZ_20240101_20240331.parquet
  industries/
    sw/
      SW2021/
        classifications.parquet
        index_bars/
          801780_SI_20240101_20240331.parquet
        memberships/
          000001_SZ.parquet
          600519_SH.parquet
```

SQLite may be used for metadata and reference lookups where relational access is useful:

```text
data/snapshots/metadata.sqlite
```

Backtests must not call Tushare directly. The Tushare provider only creates or updates snapshots. Stock daily bar snapshots default to front-adjusted `qfq` prices.

Raw daily bars, tradability status snapshots, and calculated indicator snapshots are stored separately. Runtime code joins market bars and indicators by `(symbol, trade_date)` into `MarketFeatureRow` objects before strategy execution, while order constraints read `Tradability Status` by the same key. Indicator snapshots use the same asset type and price adjustment namespace as their source daily bars, for example `daily_bars/qfq/...`, `tradable_bars/index/none/...`, `indicators/kdj/qfq/...`, and `indicators/kdj/index/none/...`. This keeps fetched source data immutable and lets tradability and indicator snapshots be recalculated, cached, or versioned independently.

Current local CLI slice:

```powershell
.venv\Scripts\python.exe -m attbacktrader.cli.tushare_backtest --symbol 000001.SZ --start-date 20240101 --end-date 20240331
```

Use `--engine backtrader` to run the same strategy through the current backtrader engine adapter:

```powershell
.venv\Scripts\python.exe -m attbacktrader.cli.tushare_backtest --engine backtrader --symbol 000001.SZ --start-date 20240101 --end-date 20240331 --initial-cash 1000000 --stake 100
```

These commands read the token from `.secrets/tushare_token.txt`, fetch Tushare front-adjusted daily bars, write a local raw Parquet snapshot under `data/snapshots/daily_bars/qfq/`, write a KDJ indicator snapshot under `data/snapshots/indicators/kdj/qfq/`, join raw bars and indicators by `(symbol, trade_date)`, run `Trend Template V1`, and print a JSON `Backtest Report`. Token files and snapshots are local artifacts and are ignored by Git.

The preferred config-driven entry point is:

```powershell
.venv\Scripts\att-run-plan.exe --config examples/run-tushare-smoke.yaml
```

or equivalently:

```powershell
.venv\Scripts\python.exe -m attbacktrader.cli.run_plan --config examples/run-tushare-smoke.yaml
```

This command parses `run.yaml` once before execution, uses `data.refresh_snapshots` to decide whether to fetch from Tushare or reuse existing Parquet snapshots, prepares tradable OHLCV snapshots for stocks, indexes, or industry indexes, KDJ indicator snapshots, benchmark index snapshots, Shenwan industry index snapshots, and Shenwan industry reference snapshots, then runs the configured `execution.engine`.

Benchmark index snapshots are allowed to be empty for a requested date range. This keeps a benchmark with insufficient history, such as an index whose series starts after the backtest window, from blocking the stock backtest. Empty benchmark series are listed in the run result with `bar_count: 0` and skipped by benchmark comparison.

When `output.persist` is true, the CLI persists run artifacts under `reports/{run_id}/`:

```text
reports/{run_id}/
  run_plan.json
  result.json
  report.json
  report.md
  trades.json
  equity_curve.json
  positions.json
  execution_audit.json
  snapshots.json
```

`run_plan.json` stores the resolved configuration, `result.json` stores the complete execution result, `report.json` stores the standard report, `report.md` stores a lightweight human-readable report, `trades.json` stores closed trades and open positions, `equity_curve.json` stores per-date account value, `positions.json` stores per-date holding snapshots, `execution_audit.json` stores submitted, accepted, completed, failed, and constraint-rejected order events, and `snapshots.json` stores the raw and indicator snapshot references used by the run. The root `reports/` directory is a local artifact and is ignored by Git.

## Strategy Model

The first strategy template is `Trend Template V1`. It is a fixed code-backed strategy template used to validate the full framework flow.

Indicators are calculated before strategy execution into indicator snapshots. Strategy templates and engine adapters consume `MarketFeatureRow` values that join raw market data and indicator data by `(symbol, trade_date)`. The current snapshot includes KDJ values; later slices can add more indicators without changing raw market snapshots.

Tradable inputs are configured as `data.tradable_series`. Strategy logic should not branch on whether a series is a stock, broad index, or industry index; asset type only controls data-provider fetch behavior, price-adjustment defaults, snapshot layout, and which post-run analyses are eligible. `data.symbols` remains as a backward-compatible shorthand for stock tradable series.

Daily OHLCV bars can be deterministically resampled to weekly or monthly bars. The aggregation rule is first open, max high, min low, last close, summed volume, and for index bars summed amount. Weekly and monthly bars are derived snapshots, not a separate provider responsibility.

Each run selects exactly one method of each type:

- one `Entry Method`
- one `Profit-Taking Method`
- one `Stop-Loss Method`
- one `Sizing Rule`

Multiple signal conditions are allowed inside a method. The framework does not globally compose arbitrary buy/sell rules in the first version.

Methods emit `Trade Intent` objects instead of orders. A trade intent includes:

- intent type
- symbol
- trade date
- method name
- reason code
- signal values
- target price, when applicable
- risk price, when applicable
- confidence, when applicable
- blocking constraint, when applicable

Sizing and execution consume trade intents and portfolio state to produce engine instructions.

## Trading Constraints

China A-share constraints are modeled in the business layer and covered by tests. The first version supports:

- T+1 selling
- limit-up and limit-down behavior
- suspension
- board-lot sizing
- commission, stamp tax, and transfer fee
- slippage model
- cash checks

Backtrader may execute the resulting orders, but these rules must remain visible and testable in `attbacktrader`.

The first constraint slice covers board-lot sizing, cash checks, suspension, and limit-up/limit-down rejection. T+1, fees, and slippage remain later slices before the backtrader adapter is complete.

The current backtrader adapter slice applies configured commission, stamp tax, transfer fee, and slippage through the broker. It also runs A-share board-lot, cash, T+1, suspension, limit-up, and limit-down pre-checks before submitting orders when `constraints.ashare.enabled` is true. Suspension and limit-up/limit-down checks are data-driven from `tradability/stock/...` snapshots keyed by `(symbol, trade_date)`.

## Engine Adapter

The backtrader adapter maps a run plan into backtrader-native objects:

- Parquet-backed pandas frames into backtrader data feeds
- strategy template and selected methods into a backtrader strategy bridge
- broker settings into backtrader broker configuration
- trading constraints into pre-order checks, sizing, commission, slippage, and rejection behavior
- analyzers into standardized report inputs

Business logic should not depend on backtrader classes outside the adapter boundary.

The first backtrader adapter slice uses `cheat-on-close` to match the business runner's close-price execution. It supports both the original single-symbol adapter and a portfolio adapter that loads multiple stock data feeds into one Cerebro instance with one broker cash account. Backtrader only finalizes an order after the engine advances, so a signal generated on the final available bar may remain open until another bar is available.

The adapter also emits an engine-neutral execution ledger. The current ledger includes an `Equity Curve`, per-symbol `Position Snapshot` records, and an `Execution Audit`. When these are available, the standard report uses the broker account-value curve for return and drawdown instead of reconstructing risk from closed trades only, while `Execution Cost Summary` explains order acceptance, rejection, fill price, commission, and slippage at report level.

## Analysis Outputs

The first version produces a standard `Backtest Report`, not raw analyzer dictionaries.

The first report slice assembles return, max drawdown, trade quality, portfolio behavior, execution costs, benchmark comparison, Shenwan industry attribution, market-regime evidence, and scenario fit scoring from completed trades, open positions, the execution ledger, broker state, and prepared index snapshots.

Required report sections:

- return: cumulative return, annualized return, excess return
- risk: max drawdown, volatility, downside volatility, drawdown duration
- risk-return: Sharpe, Calmar, return-to-drawdown ratio
- trade quality: win rate, profit/loss ratio, average win, average loss, trade count, turnover
- portfolio behavior: open holding count, open symbols, closed-symbol count, max symbol trade share, cash ratio when broker state is available, and per-symbol trade contribution
- execution costs: order count, submitted, accepted, completed, failed, rejected, fill rate, rejection rate, total and average commission, total and average slippage cost, and rejection reason distribution
- industry attribution: Shenwan level 1, 2, and 3 contribution
- benchmark comparison: SSE Composite, CSI 300, ChiNext, A500 where index history is available for the run window
- market regime performance: deterministic water-temperature labels by daily, weekly, and monthly windows; later slices will add return, drawdown, win rate, and profit/loss ratio by regime
- scenario fit: rule-based `fit`, `conditional_fit`, `not_fit`, or `insufficient_evidence`

`Scenario Fit` is a structured judgment derived from report evidence. First-version labels:

- `fit`
- `conditional_fit`
- `not_fit`
- `insufficient_evidence`

The first version uses rule scoring for scenario fit. It requires at least `analysis.scenario_fit.min_trades` closed trades, then scores positive cumulative return, max drawdown within 12%, win rate at least 50%, profit/loss ratio at least 1, positive average benchmark excess return, and a `warm` or `hot` market regime. AI-generated explanation is not part of the core judgment.

Market regime labels are derived from configured benchmark indexes and Shenwan industry index series. The first version calculates benchmark return, benchmark max drawdown, benchmark volatility, and industry positive-return ratio for `D`, `W`, and `M` windows. Labels are `hot`, `warm`, `neutral`, `cold`, or `insufficient_evidence`.

## Testing

The first version must include regression coverage at four levels:

1. Configuration tests: invalid `run.yaml` fails before execution.
2. Component tests: fixed data frames produce deterministic method, indicator, sizing, and constraint outputs.
3. Adapter tests: fixed run plans create expected backtrader feeds, strategy bridge, broker configuration, and analyzers.
4. Golden backtests: fixed single-stock fixture runs end to end and asserts accepted outputs such as trade count, final equity, max drawdown, and reason codes.

Large historical datasets are not required in CI for the first version. Golden fixtures must be small, deterministic, and stored locally.

The first golden backtest slice uses a CSV single-stock fixture to avoid binary test data and external data dependencies. Production time-series snapshots still target Parquet; the CSV fixture exists only for deterministic regression coverage.

## Implementation Slices

1. Create `attbacktrader` package skeleton and config models.
2. Implement snapshot interfaces and a minimal Parquet reader.
3. Implement `Trend Template V1` with KDJ J-value entry below 13, KDJ J-value profit exit above 100, fixed 5% stop loss, and one sizing rule.
4. Implement China A-share constraint checks.
5. Implement the backtrader engine adapter and strategy bridge.
6. Implement `Backtest Report` models and report assembly.
7. Implement industry attribution, benchmark comparison, market regime labels, and scenario fit scoring.
8. Add regression tests and one golden single-stock fixture.
