# ATTbacktrader

ATTbacktrader is the business-layer backtesting framework in this backtrader
fork. The first version focuses on a small, repeatable research pipeline:
validated YAML run plans, local data snapshots, configurable strategy method
bindings, a backtrader engine adapter, A-share execution constraints, execution
audit records, and standard report artifacts.

This repository still contains the upstream `backtrader` package. New business
code lives under `attbacktrader/`.

## Current Scope

- Parse one immutable run plan before a backtest starts.
- Fetch stock, index, and Shenwan industry data through a provider abstraction.
- Use Tushare as the current provider.
- Store qfq stock daily bars, indexes, industry indexes, tradability, and
  reference data as local snapshots.
- Store calculated indicators separately from raw bars and join by
  `(symbol, trade_date)` at run time.
- Run `Trend Template V1` with configured entry, profit-taking, and stop-loss
  methods.
- Run through either the business engine or the backtrader adapter.
- Apply first-version A-share constraints: board lot sizing, suspension,
  limit-up buy block, limit-down sell block, and T+1 sell block.
- Persist JSON artifacts plus a lightweight Markdown report.

Deferred from this version: Bayesian parameter tuning, optimization/test groups,
and richer report presentation.

The first-version closure boundary is tracked in
`docs/mvp-checklist.md`.

## Setup

Verified locally with Python 3.12.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e . pytest
```

Create the local Tushare token file:

```powershell
New-Item -ItemType Directory -Force .secrets
Set-Content .secrets\tushare_token.txt "<your_tushare_token>"
```

Do not commit `.secrets/`, `data/snapshots/`, or `reports/`.

## Run A Tushare Smoke Backtest

```powershell
.\.venv\Scripts\python.exe -m attbacktrader.cli.run_plan --config examples\run-tushare-smoke.yaml
```

The smoke run writes artifacts to:

```text
reports/tushare-smoke-2024q1/
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

Open `report.md` first when reviewing a run. Use the JSON files when debugging
or building further analysis.

## Acceptance Checks

Run the curated ATTbacktrader business regression suite:

```powershell
.\.venv\Scripts\python.exe scripts\acceptance_smoke.py
```

Run the same suite plus the real Tushare smoke:

```powershell
.\.venv\Scripts\python.exe scripts\acceptance_smoke.py --with-tushare
```

The script intentionally runs only ATTbacktrader tests. The repository also
contains many upstream backtrader tests with different maintenance scope.

## Main Configuration File

Start from `examples/run-tushare-smoke.yaml`.

Important switches:

- `data.refresh_snapshots`: fetch fresh Tushare data when true; reuse local
  snapshots when false.
- `data.tradable_series`: stocks, indexes, or industry indexes to trade.
- `data.benchmark_series.indexes`: indexes used for comparison only.
- `data.industry_series`: Shenwan industry indexes used for attribution and
  market-regime analysis.
- `strategy.entry_method`, `strategy.profit_taking_method`,
  `strategy.stop_loss_method`: one-to-one method bindings for the current
  strategy template.
- `constraints.ashare`: business-layer A-share trading constraint switches.
- `analysis.*.enabled`: report analysis switches.
- `execution.engine`: `backtrader` or `business`.

## First Report Review Order

1. `report.md`: human-readable summary.
2. `execution_audit.json`: submitted, accepted, completed, failed, and rejected
   order events.
3. `equity_curve.json`: account value by date.
4. `positions.json`: position snapshots by date and symbol.
5. `snapshots.json`: data snapshot references used by the run.
