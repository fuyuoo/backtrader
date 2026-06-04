# Project Structure

This document is the placement guide for new `attbacktrader` code. It should be used with `CONTEXT.md` and the ADRs before adding a new module, command, strategy method, provider, analysis, or test.

## Top-Level Ownership

```text
/
  backtrader/          # upstream backtest engine library
  attbacktrader/       # business framework owned by this project
  docs/                # domain, ADR, architecture, and agent docs
  examples/            # runnable configuration examples
  tests/               # regression tests and fixtures
  data/snapshots/      # local Data Snapshot artifacts, ignored by Git
  reports/             # local Run Artifact output, ignored by Git
  .secrets/            # local secrets such as Tushare token, ignored by Git
```

The `backtrader/` package is treated as the current Backtest Engine implementation. New framework behavior belongs in `attbacktrader/` unless the change is intentionally modifying the engine library itself.

## Business Package Layout

```text
attbacktrader/
  config/              # Strategy Configuration -> immutable Run Plan
  data/                # market/reference models, Data Providers, Data Snapshots
  features/            # indicator calculation, indicator snapshots, feature rows
  strategies/          # Strategy Definitions, Strategy Binding, entry/exit/add-on methods, templates, Trade Intents
  sizing/              # Sizing Rules and risk-budget entry sizing decisions
  constraints/         # Trading Constraints such as China A-Share rules
  engines/             # Engine Adapters, including business and backtrader paths
  analysis/            # post-run analysis, analysis pipeline, and scenario evidence
  reports/             # Backtest Report models, assembly, persistence
  runners/             # Run Plan orchestration and Prepared Run Data
  cli/                 # command-line entry points
```

## Placement Rules

### Configuration

Put Run Plan models, YAML loading, and validation in `attbacktrader/config/`.

Rules:

- `config/` may validate names, switches, shapes, and allowed Component Bindings.
- Component Binding names and method construction belong in `attbacktrader/strategies/bindings.py`; configuration validation should call that module instead of duplicating binding tables.
- Attribution factor selection and entry-attribution filter switches are parsed in `analysis.entry_attribution`; the filter is a decision-layer rule, not an indicator calculation.
- `config/` must not fetch market data, build indicators, run a Backtest Engine, or write Run Artifacts.
- New configuration switches must be parsed before the backtest starts.

Tests:

- Put validation tests in `tests/test_attbacktrader_config.py` or a focused `tests/test_<config_area>.py`.

### Data Providers

Put Data Provider interfaces and adapters in `attbacktrader/data/providers/`.

Rules:

- `base.py` owns provider interfaces.
- `tushare.py` owns Tushare-specific request and response mapping.
- New providers should satisfy the existing provider interface or introduce a clearly named interface when the seam is real.
- Strategy code, analysis code, and Backtest Engine adapters must not call Tushare directly.

Tests:

- Put provider mapping tests in `tests/test_tushare_provider.py` or `tests/test_<provider>_provider.py`.
- Tests should use fake frames or fake providers unless explicitly marked as a live smoke path.

### Data Snapshots

Put Data Snapshot path layout, schema handling, and persistence in `attbacktrader/data/snapshots/`.

Rules:

- Time-series snapshots are Parquet by default.
- Metadata and reference lookup storage may use SQLite later.
- Snapshot path rules should not be duplicated in runners, strategies, analysis, or CLI modules.
- Snapshot range discovery and compatible snapshot reuse belong here; runners may call those helpers but must not parse snapshot filenames directly.
- Snapshot provenance records belong here; runners attach them to Prepared Run Data and report writers serialize them.
- Price Adjustment and Asset Type must remain visible in snapshot identity.

Tests:

- Put snapshot read/write tests in `tests/test_parquet_snapshots.py`, `tests/test_reference_snapshots.py`, or a focused snapshot test file.

### Data Quality

Put reusable prepared-data quality checks in `attbacktrader/data/quality.py`.

Rules:

- Quality checks should emit structured issues, not mutate bars or fetch missing data.
- Non-fatal issues such as duplicate dates, symbol mismatches, missing edge coverage, and large calendar gaps should be serializable into Run Artifacts.
- Trading Calendar V1 belongs in `attbacktrader/data/calendar.py` and should be derived from prepared market sessions such as decision or benchmark index bars.
- Runner orchestration decides where to attach quality issues for a run.

Tests:

- Put focused quality tests in `tests/test_prepared_run_data.py` or a dedicated `tests/test_data_quality.py`.

### Features And Indicators

Put indicator calculation, indicator snapshots, and market feature aggregation in `attbacktrader/features/`.

Rules:

- Raw market bars and indicator snapshots stay separate.
- Runtime joins raw bars and indicator snapshots by `(symbol, trade_date)`.
- New indicators should be calculated before strategy execution, stored as indicator snapshots when reusable, and exposed through feature rows or an indicator frame.
- Indicator calculation should produce reusable numeric values only. Composite decisions such as bullish trend, breakout, or sell conditions belong in strategy methods or another decision layer, not as calculated indicators.
- Windowed indicators must remain unavailable until their required data window exists; do not fill warmup rows with zero, neutral, or default calculated values.
- Strategy methods declare required indicator names and timeframes. Run preparation uses those declarations to build or reuse the matching indicator snapshot set.
- Daily feature rows use exact daily indicators and align weekly/monthly indicators to the latest completed higher-timeframe snapshot on or before the daily trade date.
- Every supported indicator must have an `IndicatorSpec` declaring warmup bars, recompute lookback bars, parameters, version, and whether exact incremental continuation requires saved state.
- Indicator update planning groups requirements by `symbol/timeframe` and uses the longest required warmup/lookback in that group.
- Indicator snapshot range discovery belongs here. To preserve warmup semantics, runners may reuse compatible indicator snapshots only when the calculation start matches the requested prepared bars.
- Strategy methods should consume prepared features; they should not rebuild reusable indicators on every call.

Tests:

- Put indicator math tests in `tests/test_<indicator>_indicator.py` when needed.
- Put snapshot and aggregation tests in `tests/test_indicator_snapshots.py`, `tests/test_indicator_frame.py`, or a focused feature test.

### Strategy Definitions

Put Strategy Templates, Entry Methods, Profit-Taking Methods, Stop-Loss Methods, and Trade Intents in `attbacktrader/strategies/`.

Rules:

- `strategies/bindings.py` owns the relationship between Strategy Templates, selectable method names, and concrete code-backed methods.
- `strategies/attribution.py` owns entry attribution factor declarations, shared entry-time evidence builders, factor filtering, and entry-attribution filter application.
- `strategies/templates/` owns fixed code-backed Strategy Templates.
- `strategies/methods/` owns code-backed Entry, Profit-Taking, Stop-Loss, and Add-On methods.
- `strategies/intents.py` owns Trade Intent models.
- A Strategy Template may call multiple signal conditions inside one selected method.
- Composite entry/exit methods should record the individual condition checks in `signal_values` so `signal_audit.json` explains both triggered and non-triggered decisions.
- Add-on methods run only after a position exists, emit `TradeIntentType.ADD_ON` when they request an additional buy, and should consume prepared features rather than recalculating indicators.
- The framework does not globally compose arbitrary buy/sell rules in the first version.
- New methods must be bound to a Strategy Template through Strategy Configuration validation before they are selectable.

Tests:

- Put method tests in `tests/test_strategy_methods.py` or a focused method test.
- Put template behavior tests in `tests/test_trend_template_v1_golden.py` or a template-specific test.

### Sizing And Trading Constraints

Put Sizing Rules in `attbacktrader/sizing/` and Trading Constraints in `attbacktrader/constraints/`.

Rules:

- Sizing Rules decide requested entry quantity from strategy intent, account state, and prepared features.
- China A-Share Constraint Set behavior stays in the business layer.
- Board-lot resizing, cash rejection, suspension, limit-up/down, and T+1 remain Trading Constraints, not Sizing Rules.
- Backtrader configuration must not hide A-share rules.
- Board-lot sizing, cash checks, suspension, limit-up/down, T+1, fees, slippage, and related rejections should be testable without running backtrader.

Tests:

- Put sizing rule tests in `tests/test_sizing_rules.py`.
- Put constraint tests in `tests/test_ashare_constraints.py` or a focused constraint test.
- Add golden coverage when a constraint changes portfolio behavior.

### Engine Adapters

Put Backtest Engine adapters in `attbacktrader/engines/`.

Rules:

- `engines/business/` owns deterministic business-level portfolio simulation: cash, position value, sizing consumption, equity curve, and position snapshots without broker-specific costs.
- `engines/backtrader/` owns translation into backtrader-native data feeds, strategies, brokers, and run results.
- Business logic should not depend on backtrader classes outside `engines/backtrader/`.
- A future engine gets its own directory, for example `attbacktrader/engines/<engine_name>/`.
- Engine adapters should consume prepared data and Strategy Definitions; they should not fetch data or decide scenario fit.

Tests:

- Put adapter tests in `tests/test_backtrader_adapter.py` or `tests/test_<engine>_adapter.py`.
- Compare adapter output against business-level golden behavior where possible.

### Analysis

Put post-run analysis in `attbacktrader/analysis/`.

Rules:

- Benchmark Comparison, Industry Attribution, market input summaries, and Scenario Fit belong here.
- `analysis/pipeline.py` owns the ordering that enriches a Backtest Report with configured analysis evidence.
- Analysis consumes completed trades, prepared analysis series, industry evidence, and reports.
- Analysis must not emit orders or alter strategy decisions unless a series is explicitly configured as a Decision Series and handled by a Strategy Definition.

Tests:

- Put analysis tests in focused files such as `tests/test_market_regime.py`, `tests/test_scenario_fit.py`, or `tests/test_<analysis_name>.py`.

### Reports And Run Artifacts

Put Backtest Report models, report assembly, and Run Artifact writing in `attbacktrader/reports/`.

Rules:

- `reports/models.py` owns stable report shapes.
- `reports/assembly.py` converts execution output and analysis evidence into reports.
- `reports/renderer.py` owns human-readable Markdown report presentation.
- `reports/writer.py` persists Run Artifacts under `reports/{run_id}/`.
- `reports/comparison.py` reads persisted run artifacts and writes comparison artifacts; it must not rerun backtests.
- `reports/regression.py` reads persisted run artifacts and compares them with accepted metric baselines; it must not rerun backtests.
- `reports/lifecycle.py` builds `trade_lifecycle.json` from completed trades, signal audit, and execution audit; it must not infer missing strategy decisions.
- `reports/post_exit.py` builds `post_exit_analysis.json` and `post_exit_analysis.zh.md` from completed trades, matched exit intents, and prepared bars after exit; it may aggregate by configured windows and exit evidence, but it must not rerun strategy methods, recalculate indicators, or default-fill missing future bars.
- `signal_audit.json` records strategy method decisions and signal evidence; it is upstream execution evidence, not report-only data.
- `result_diagnostics.json` summarizes existing run evidence by symbol, including winning/losing trade entry attribution, exit attribution, successful add-on lifecycle attribution, add-on signal counts, sizing blocks, and execution rejections from `signal_audit.json`/`execution_audit.json`; it should not rerun strategies, refetch data, or recalculate indicators.
- `trade_lifecycle.json` keeps detailed per-trade entry/add-on/exit timelines and filter indexes; reports should link or summarize rather than expand every lifecycle once the data grows.
- `evidence_validation.json` checks cross-artifact consistency across signal, sizing, execution, rejection reasons, trades, diagnostics, equity, and report outputs; it should not mutate results or act as a substitute for upstream evidence.
- Entry/exit attribution detail and statistics should follow `docs/architecture/entry-attribution.md`: evidence is captured at decision time, factor declarations are owned by the evidence producer, and reports consume summaries without recalculating indicators.
- Report writers should not rerun analysis, refetch data, or mutate Run Plans.

Tests:

- Put report model, renderer, and writer tests in `tests/test_backtest_report.py`, `tests/test_report_renderer.py`, `tests/test_report_writer.py`, or a focused report test.

### Runners

Put Run Plan orchestration in `attbacktrader/runners/`.

Rules:

- `runners/` coordinates modules; it should not become the home for provider mapping, snapshot schema, strategy method logic, or analysis rules.
- `runners/prepared_data.py` owns Prepared Run Data: tradable snapshots, indicator snapshots, benchmark series, industry index series, industry evidence, and snapshot references.
- If orchestration starts owning detailed behavior from another area, deepen that area into its own module before adding more cases.
- `execute_run_plan` is the main first-version entry point.

Tests:

- Put end-to-end Run Plan tests in `tests/test_run_plan_executor.py`.
- Keep deterministic golden fixtures small and offline.

### CLI Commands And Scripts

Put supported command-line entry points in `attbacktrader/cli/`.

Rules:

- CLI modules parse arguments, load configuration, call a runner, and print or persist results.
- CLI modules must not contain core business logic.
- CLI helpers that generate example run matrices, compare persisted artifacts, or validate run-regression baselines should delegate domain work to `attbacktrader/reports/`, `attbacktrader/config/`, or another owned module.
- Do not add new framework scripts at the repo root.
- Do not add new `attbacktrader` scripts under upstream `backtrader/tools/` or `samples/`.
- Use `examples/` for runnable YAML configurations, not for Python business logic.

Tests:

- Prefer testing the runner or module behind the CLI.
- Add CLI smoke tests only when argument parsing or output contract is important.

## Example Placement Decisions

| New work | Put it here |
|---|---|
| New Tushare endpoint mapping | `attbacktrader/data/providers/tushare.py` |
| New provider such as AkShare | `attbacktrader/data/providers/akshare.py` |
| New snapshot layout or schema | `attbacktrader/data/snapshots/` |
| New indicator such as MACD | `attbacktrader/features/` |
| New Component Binding rule | `attbacktrader/strategies/bindings.py` |
| New Entry Method | `attbacktrader/strategies/methods/entry.py` or a focused method module |
| New Add-On Method | `attbacktrader/strategies/methods/add_on.py` |
| New Strategy Template | `attbacktrader/strategies/templates/` |
| New Sizing Rule | `attbacktrader/sizing/` once that module exists |
| New A-share rule | `attbacktrader/constraints/` |
| New Backtest Engine | `attbacktrader/engines/<engine_name>/` |
| New deterministic business-engine execution behavior | `attbacktrader/engines/business/` |
| New benchmark or attribution analysis | `attbacktrader/analysis/` |
| New report enrichment ordering | `attbacktrader/analysis/pipeline.py` |
| New report field or writer | `attbacktrader/reports/` |
| New persisted run comparison | `attbacktrader/reports/comparison.py` plus a thin `attbacktrader/cli/` entry point |
| New persisted run regression baseline | `attbacktrader/reports/regression.py` plus a thin `attbacktrader/cli/` entry point |
| New trade lifecycle artifact | `attbacktrader/reports/lifecycle.py` plus `attbacktrader/reports/writer.py` |
| New post-exit follow-up artifact | `attbacktrader/reports/post_exit.py` plus `attbacktrader/reports/writer.py` |
| New Run Plan data preparation behavior | `attbacktrader/runners/prepared_data.py` unless it belongs in a deeper data or feature module |
| New runnable config | `examples/` |
| New supported command | `attbacktrader/cli/` |

## Test Placement

Tests should mirror the module seam they verify:

- Pure module behavior: focused `tests/test_<module_area>.py`.
- Cross-module Run Plan behavior: `tests/test_run_plan_executor.py`.
- Backtest regression behavior: golden fixture plus template or adapter test.
- Data Provider mapping: fake provider/frame tests, not live network tests.
- Tushare live usage: CLI smoke runs outside the default regression suite.

## Do Not Add

- Business logic in `attbacktrader/cli/`.
- Tushare calls in strategies, analysis, reports, or engine adapters.
- Snapshot path construction outside `attbacktrader/data/snapshots/`.
- Backtrader-native imports outside `attbacktrader/engines/backtrader/`, except tests that directly verify the adapter.
- Python framework scripts at repo root.
- New project behavior under upstream `backtrader/`, `samples/`, or `tools/` unless the change is intentionally about the upstream engine library.
