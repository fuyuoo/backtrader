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
  reference data as local snapshots. Existing tradable bar snapshots can be
  discovered across compatible date ranges, reused offline when they cover the
  requested run, and incrementally filled at missing leading or trailing ranges.
- Derive a Trading Calendar V1 from configured decision or benchmark index
  bars. Prepared data quality checks use it to report missing trading sessions
  instead of relying only on natural-day gap heuristics.
- Store calculated indicators separately from raw bars and join by
  `(symbol, trade_date)` at run time. Strategy methods declare required
  indicators with a timeframe; the current set includes KDJ, MACD, MA20,
  MA25, MA60, RSI14, and ATR14. Indicators with a warmup window stay unavailable
  until enough bars exist; they are not filled with default values.
- Plan indicator updates by `symbol/timeframe` using the longest required
  warmup and recompute window among selected indicators. Indicator snapshot
  writes persist metadata with version fingerprint, coverage, and rolling
  states. KDJ, MACD, RSI14, and ATR14 can append exactly from saved state when
  the selected indicator group is fully stateful; mixed groups fall back to the
  configured recompute window or full rebuild. Indicator snapshots can be
  discovered across compatible ranges with the same calculation start, then
  reused or materialized for the requested run range.
- Run `Trend Template V1` with configured entry, profit-taking, and stop-loss
  methods. Method parameters can be configured through `entry_params`,
  `profit_taking_params`, and `stop_loss_params`. Composite decisions such as
  MA trend plus MACD confirmation live in strategy methods, not indicator
  calculation.
- Size entries with the `equal_weight` sizing rule. The default behavior
  preserves fixed `execution.stake`; optional `sizing_params` can cap max
  holdings, max position value, total exposure, risk-group exposure, cash
  reserve, turnover, rebalance interval, and ATR-based risk.
- Run through either the business engine or the backtrader adapter.
  The business engine now keeps deterministic portfolio cash, position value,
  equity curve, and position snapshots; backtrader remains the broker/cost and
  A-share constraint execution path.
- Apply first-version A-share constraints: board lot sizing, suspension,
  limit-up buy block, limit-down sell block, and T+1 sell block.
- Persist JSON artifacts plus lightweight English and Chinese Markdown reports.
  `snapshots.json` records snapshot provenance and prepared data quality
  warnings. The market-temperature section displays configured benchmark,
  industry-index, and timeframe inputs without calculating a hot/cold label.
  `result_diagnostics.json` records completed-trade entry and exit attribution
  detail, per-symbol and portfolio-level summaries, factor coverage,
  winning-vs-losing factor contrasts, and add-on lifecycle attribution. Exit
  attribution now consumes the same decision-time symbol, industry, and market
  evidence payload as entries and add-ons.
  `trade_lifecycle.json` records each completed trade's entry/add-on/exit
  timeline with linked execution events and filter indexes.
  `trade_review.json` combines lifecycle, post-exit follow-up, and
  opportunity/block evidence into a single trade-review surface.
  `att-review-packet` can then read those persisted artifacts and write a
  focus-specific AI review packet without rerunning the backtest.
  `post_exit_analysis.json` observes configured windows after completed
  stop-loss/profit-taking exits from prepared bars, so sold-too-early review
  stays downstream of trading decisions. Current examples use 3/5/10/20
  trading-day windows with 5 days as the primary review window, and the Chinese
  review ranks sold-too-early samples for quick inspection. Entry attribution
  factors and optional entry filters are configurable under
  `analysis.entry_attribution`; current factors include symbol KDJ, symbol
  MA20/MA25/MA60, symbol MA trend checks, industry KDJ, CSI 300 trend, and
  sizing risk group evidence.

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
  report.zh.md
  trades.json
  signal_audit.json
  sizing_audit.json
  result_diagnostics.json
  trade_lifecycle.json
  trade_lifecycle.zh.md
  trade_review.json
  trade_review.zh.md
  post_exit_analysis.json
  post_exit_analysis.zh.md
  evidence_validation.json
  equity_curve.json
  positions.json
  execution_audit.json
  snapshots.json
```

Open `report.zh.md` first for Chinese review, or `report.md` for the English
summary. Use the JSON files when debugging or building further analysis.

## Run Expanded Result-Driven Backtests

Use the expanded baseline run to inspect strategy signal behavior across a
larger universe while keeping the original fixed `execution.stake` sizing:

```powershell
.\.venv\Scripts\python.exe -m attbacktrader.cli.run_plan --config examples\run-tushare-expanded-baseline.yaml
```

Use the sized run to keep the same symbols and time range while enabling
portfolio controls:

```powershell
.\.venv\Scripts\python.exe -m attbacktrader.cli.run_plan --config examples\run-tushare-expanded-sized.yaml
```

The sized example uses max holding count, single-position cap, total exposure
cap, Shenwan risk-group cap, cash reserve, daily turnover cap, and ATR risk.
Compare its `report.zh.md`, `signal_audit.json`, `sizing_audit.json`, and
`result_diagnostics.json` against the baseline before changing strategy
methods.

Use the attribution-filter example to test decision-layer filters derived from
the attribution contrasts. It records symbol MA20/MA25/MA60 evidence and
symbol MA trend checks, then requires both price above MA25 and CSI 300
bullish trend before an entry can reach sizing:

```powershell
.\.venv\Scripts\python.exe -m attbacktrader.cli.run_plan --config examples\run-tushare-attribution-filter.yaml
```

Validate the accepted real-run metric baseline after refreshing the expanded
run artifacts:

```powershell
.\.venv\Scripts\python.exe -m attbacktrader.cli.validate_run_regression --baseline examples\real-run-regression-baseline.json --output-dir reports\real-run-regression-2023-2024
```

Build a focused AI review packet from an existing run directory:

```powershell
.\.venv\Scripts\python.exe -m attbacktrader.cli.review_packet --run-dir reports\tushare-expanded-add-on-2023-2024 --focus all
```

Available focuses are `all`, `sold_too_early`, `stop_loss_rebound`,
`opportunity_cost`, `add_on`, and `validation`. The command writes
`review_packet.<focus>.json` plus `review_packet.<focus>.zh.md` beside the run
artifacts by default. The packet includes an `ai_contract`, run overview,
source artifact paths, summaries, and capped samples with `trade_index` or
`sample_index` for exact backtracking.

Build structured findings from a packet or directly from a run directory:

```powershell
.\.venv\Scripts\python.exe -m attbacktrader.cli.review_findings --packet reports\tushare-expanded-add-on-2023-2024\review_packet.all.json
```

Drill into one sample when an AI review needs exact evidence:

```powershell
.\.venv\Scripts\python.exe -m attbacktrader.cli.review_sample --run-dir reports\tushare-expanded-add-on-2023-2024 --kind add_on --sample-index 1
.\.venv\Scripts\python.exe -m attbacktrader.cli.review_sample --run-dir reports\tushare-expanded-add-on-2023-2024 --kind trade --trade-index 120
.\.venv\Scripts\python.exe -m attbacktrader.cli.review_sample --run-dir reports\tushare-expanded-add-on-2023-2024 --kind opportunity --sample-index 2
```

`att-review-findings` writes `review_findings.<focus>.json` plus Chinese
Markdown. `att-review-sample` writes `review_sample.<kind>.<id>.json` plus
Chinese Markdown and links the sample back to trade lifecycle, post-exit,
signal audit, execution audit, and closed-trade evidence when available.

Expand the sample refs from findings, build a Skill-ready review brief, and
generate validation candidates:

```powershell
.\.venv\Scripts\python.exe -m attbacktrader.cli.review_expand_samples --findings reports\tushare-expanded-add-on-2023-2024\review_findings.all.json --limit-per-finding 3
.\.venv\Scripts\python.exe -m attbacktrader.cli.review_brief --findings reports\tushare-expanded-add-on-2023-2024\review_findings.all.json --sample-batch reports\tushare-expanded-add-on-2023-2024\review_sample_batch.all.json
.\.venv\Scripts\python.exe -m attbacktrader.cli.review_experiment_candidates --findings reports\tushare-expanded-add-on-2023-2024\review_findings.all.json --sample-batch reports\tushare-expanded-add-on-2023-2024\review_sample_batch.all.json
.\.venv\Scripts\python.exe -m attbacktrader.cli.review_experiment_drafts --candidates reports\tushare-expanded-add-on-2023-2024\review_experiment_candidates.all.json --base-config examples\run-tushare-expanded-add-on.yaml
```

The brief is the preferred input for the ATTbacktrader AI review Skill. It
includes `environment_fit_summary` so the reviewing agent can see the first-pass
strategy-fit environment before drilling into full JSON. Experiment candidates
are review hypotheses only: they point to evidence gaps, grouping probes, or
next validation runs, and should not directly change strategy parameters.
`att-review-result` persists the current structured review as
`ai_review_result.<focus>.json` plus Chinese Markdown. `att-review-experiment-drafts`
writes manually confirmable YAML drafts under
`examples/generated-review-experiments/<run_id>/` by default; those drafts are
not executable RunPlan files until reviewed and converted.

Compare environment-fit reports across runs before treating a strategy-fit
environment as stable:

```powershell
.\.venv\Scripts\python.exe -m attbacktrader.cli.compare_environment_fit --run-id tushare-expanded-baseline-2023-2024 --run-id tushare-expanded-add-on-2023-2024
```

The command writes `environment_fit_comparison.json` plus
`environment_fit_comparison.zh.md`. It only compares existing
`environment_fit.json` artifacts, and flags changed or low-sample best
environments as validation risks rather than strategy conclusions. The JSON
also includes `drill_down_sample_refs`, which are the preferred `trade_index`
refs for AI sample drill-down.

Build an AI-first strategy environment profile for one run:

```powershell
.\.venv\Scripts\python.exe -m attbacktrader.cli.strategy_environment_profile --run-dir reports\tushare-expanded-add-on-2023-2024
```

The command writes `strategy_environment_profile.json` plus
`strategy_environment_profile.zh.md`, grouping environment-fit evidence into
suitable, avoid, and uncertain candidates with evidence strength and sample refs.

Generate validation run plans from manually curated market segments:

```powershell
.\.venv\Scripts\python.exe -m attbacktrader.cli.market_segment_runs --catalog examples\manual-market-segments\a-share-market-type-validation.yaml --base-config examples\run-tushare-market-type-add-on.yaml --output-dir examples\generated-market-segment-runs\tushare-market-type-add-on --run-id-prefix tushare-market-type-add-on
```

The market segment catalog is manually sourced and reviewed; the generator does
not classify market states. It only copies the base RunPlan, changes
`run.id/from_date/to_date`, validates the YAML, and writes a manifest with
source URLs and the manual similarity thesis. When the catalog declares market
types, each type must have at least three historical segments, so reviews compare
group-level behavior before drawing switching-rule conclusions. The market-type
base config uses a long-history stock universe so early segments such as
2014-2015 can run against the same tradable list.

After running the generated market-type RunPlans, aggregate the persisted
artifacts by market type:

```powershell
.\.venv\Scripts\python.exe -m attbacktrader.cli.market_type_summary --manifest examples\generated-market-segment-runs\tushare-market-type-add-on\market_segment_run_manifest.json --report-root reports
```

The command writes `market_type_summary.json` plus
`market_type_summary.zh.md`. It reads existing run artifacts only and reports
group-level metrics for bull, range, and bear markets without producing strategy
switching conclusions.

Persist a structured review result with the environment comparison evidence:

```powershell
.\.venv\Scripts\python.exe -m attbacktrader.cli.review_result --brief reports\tushare-expanded-add-on-2023-2024\review_brief.all.json --environment-fit-comparison reports\environment-fit-comparison-tushare-expanded-baseline-2023-2024__vs__tushare-expanded-add-on-2023-2024\environment_fit_comparison.json
```

After a draft is manually accepted, convert exactly one draft into a validated
RunPlan YAML:

```powershell
.\.venv\Scripts\python.exe -m attbacktrader.cli.review_experiment_confirm --draft examples\generated-review-experiments\tushare-expanded-add-on-2023-2024\environment_fit_sample_stability.yaml --confirm
```

The confirmation command strips review metadata such as `review_candidate`
from the executable RunPlan and keeps it in a confirmation manifest. It does
not auto-tune strategy parameters.

## Acceptance Checks

Run the curated ATTbacktrader business regression suite plus the sealed
Strategy Adaptation V1 AI review golden check:

```powershell
.\.venv\Scripts\python.exe scripts\acceptance_smoke.py
```

Run the same suite plus the real Tushare smoke:

```powershell
.\.venv\Scripts\python.exe scripts\acceptance_smoke.py --with-tushare
```

The script intentionally runs only ATTbacktrader tests plus sealed-stage
golden checks. The repository also contains many upstream backtrader tests with
different maintenance scope.

## Main Configuration File

Start from `examples/run-tushare-smoke.yaml`. For result-driven development,
compare `examples/run-tushare-expanded-baseline.yaml` with
`examples/run-tushare-expanded-sized.yaml`.

Important switches:

- `data.refresh_snapshots`: fetch fresh Tushare data when true; reuse local
  snapshots when false.
- `data.tradable_series`: stocks, indexes, or industry indexes to trade.
- `data.benchmark_series.indexes`: indexes used for comparison only.
- `data.industry_series`: Shenwan industry indexes used for attribution and
  market-temperature input display.
- `strategy.entry_method`, `strategy.profit_taking_method`,
  `strategy.stop_loss_method`: one-to-one method bindings for the current
  strategy template.
- `strategy.entry_params`, `strategy.profit_taking_params`,
  `strategy.stop_loss_params`: parameters for the selected method, such as
  timeframe, threshold, stop multiple, or loss percent.
- `strategy.sizing_rule`, `strategy.sizing_params`: entry sizing rule and
  optional portfolio/risk controls. `risk_group_level` selects the Shenwan
  membership level used by risk-group exposure caps.
- `constraints.ashare`: business-layer A-share trading constraint switches.
- `analysis.*.enabled`: report enrichment switches. `analysis.market_regime`
  controls the market-temperature input section only; it does not calculate a
  temperature label.
- `analysis.entry_attribution`: enables attribution factor selection,
  market/industry attribution parameters, and optional decision-layer entry
  filters such as requiring `symbol.ma.price_above_ma25` or
  `market.hs300.bullish_trend`.
- `analysis.post_exit`: configures sold-too-early follow-up windows such as
  `[3, 5, 10, 20]`, the primary review window, the sold-too-early threshold,
  and rebound threshold layers such as `0%`, `2%`, `5%`, and `10%`.
- `execution.engine`: `backtrader` or `business`.

## First Report Review Order

1. `report.zh.md`: Chinese human-readable summary.
2. `report.md`: English human-readable summary.
3. `execution_audit.json`: submitted, accepted, completed, failed, and rejected
   order events.
4. `signal_audit.json`: strategy method decisions, signal evidence, and
   per-condition checks.
5. `sizing_audit.json`: extracted sizing/risk decisions for each sized entry.
6. `result_diagnostics.json`: per-symbol PnL, exit, rejection, sizing block,
   winning/losing trade entry/exit attribution detail, factor coverage,
   winning-vs-losing contrast, and add-on lifecycle summaries. Markdown reports
   keep a concise add-on entry-point detail table while JSON retains full
   factor payloads.
7. `trade_lifecycle.json`: per-completed-trade entry/add-on/exit timeline and
   filter indexes.
8. `trade_lifecycle.zh.md`: Chinese lifecycle review when JSON is too verbose.
9. `trade_review.zh.md`: unified Chinese trade review combining lifecycle,
   sold-too-early grouping, stop-loss rebound attribution, and
   opportunity/block opportunity-cost attribution plus add-on entry-point
   follow-up.
10. `trade_review.json`: full unified trade review for programmatic analysis.
11. `review_packet.<focus>.json` and `review_packet.<focus>.zh.md`: generated
   by `att-review-packet` when the next step is AI/Skill-assisted review.
12. `review_findings.<focus>.json` and `review_findings.<focus>.zh.md`:
   structured AI review findings generated from a review packet.
13. `review_sample_batch.<focus>.json` and `review_sample_batch.<focus>.zh.md`:
   batch expansion of finding sample refs for AI/Skill review.
14. `review_brief.<focus>.json` and `review_brief.<focus>.zh.md`: Skill-ready
   brief combining findings and expanded sample evidence.
15. `ai_review_result.<focus>.json` and `ai_review_result.<focus>.zh.md`:
   persisted structured AI review result.
16. `review_experiment_candidates.<focus>.json` and
   `review_experiment_candidates.<focus>.zh.md`: review-derived validation
   candidates, not tuning conclusions.
17. `review_experiment_drafts.<focus>.json`,
   `review_experiment_drafts.<focus>.zh.md`, and individual YAML draft files:
   manually confirmable next-run draft plans.
18. `review_sample.<kind>.<id>.json` and `review_sample.<kind>.<id>.zh.md`:
   focused sample drill-down generated from `trade_index` or `sample_index`.
19. `post_exit_analysis.zh.md`: stop-loss/profit-taking exits followed by
   configured windows, with window comparison, rebound threshold layers,
   ranked sold-too-early samples, and exit-evidence grouping.
20. `post_exit_analysis.json`: full post-exit observations per completed trade,
   including exit-day checks, values, threshold summaries, and factor group
   summaries.
21. `evidence_validation.json`: cross-artifact evidence consistency checks.
22. `equity_curve.json`: account value by date.
23. `positions.json`: position snapshots by date and symbol.
24. `snapshots.json`: data snapshot references, provenance, and quality warnings
   used by the run.
