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
| Strategy method binding | Done | Entry, profit-taking, stop-loss, and sizing choices are selected one-to-one from registered bindings. |
| MVP trading rule | Done | KDJ J < 13 enters, KDJ J > 100 exits profit, and fixed 5% stop-loss exits loss. |
| Portfolio backtest | Done | Multi-symbol portfolio runs share one broker cash account through the backtrader adapter. |
| Business engine path | Done | The business runner remains available for deterministic component-level behavior. |
| Backtrader adapter | Done | Prepared data, strategy methods, broker settings, and constraints are mapped into backtrader. |
| A-share constraints | Done | Board lot, cash, T+1, suspension, limit-up buy block, and limit-down sell block are covered. |
| Broker costs | Done | Commission, stamp tax, transfer fee, and slippage are applied through the adapter. |
| Execution ledger | Done | Equity curve and position snapshots are emitted by the backtrader path. |
| Execution audit | Done | Submitted, accepted, completed, failed, and rejected order events are persisted. |
| Standard report model | Done | Returns, risk, trade quality, portfolio behavior, benchmark comparison, industry attribution, market regime, scenario fit, and execution costs are represented. |
| Markdown report | Done | `report.md` is generated beside `report.json` for first-pass review. |
| Run artifacts | Done | `run_plan.json`, `result.json`, `report.json`, `report.md`, `trades.json`, `equity_curve.json`, `positions.json`, `execution_audit.json`, and `snapshots.json` are persisted. |
| Acceptance script | Done | `scripts/acceptance_smoke.py` runs the curated ATTbacktrader regression suite and optional real Tushare smoke. |
| Documentation | Done | `README.md`, `CONTEXT.md`, ADRs, architecture guide, blueprint, and this checklist define current behavior and boundaries. |

## Accepted MVP Limitations

These are acceptable for first-version closure because the goal is to stabilize
the framework boundary before expanding research depth.

| Limitation | Current Choice | Later Direction |
|---|---|---|
| One strategy template | Only `Trend Template V1` is implemented. | Add more templates after bindings and report contracts remain stable. |
| One-to-one method selection | Each run selects exactly one entry, profit-taking, stop-loss, and sizing method. | Add richer composition only after method semantics are explicit. |
| Limited indicators | KDJ is the only calculated indicator snapshot. | Add indicators through `features/` and snapshot tests. |
| Basic sizing | Current sizing is enough for framework validation. | Add risk-budget, equal-weight rebalance, and portfolio exposure controls later. |
| Report metrics are first-slice | Current report covers cumulative return, max drawdown, trade quality, attribution, regime, scenario fit, portfolio behavior, and execution costs. | Add annualized return, volatility, Sharpe, Calmar, drawdown duration, turnover, and net trade PnL metrics later. |
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

Expected result:

```text
81 passed
Acceptance smoke passed.
```

Run the same suite plus real Tushare data:

```powershell
.\.venv\Scripts\python.exe scripts\acceptance_smoke.py --with-tushare
```

Expected first smoke artifacts:

```text
reports/tushare-smoke-2024q1/
  report.json
  report.md
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
3. `reports/tushare-smoke-2024q1/report.md`
4. `reports/tushare-smoke-2024q1/execution_audit.json`
5. `docs/first-version-blueprint.md`
6. `docs/architecture/project-structure.md`

## Recommended Next Slice After MVP Closure

Start with one narrow reporting improvement: net trade PnL and turnover in the
standard report. This improves real strategy evaluation without changing the
provider, engine, strategy binding, or snapshot architecture.
