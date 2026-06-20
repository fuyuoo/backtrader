# Current Backtest Baseline

This document fixes the current result-driven backtest baseline for the next
development loop. It is a framework baseline, not a strategy approval.

## Baseline Run

| Field | Value |
|---|---|
| Baseline date | 2026-06-05 |
| Run ID | `tushare-expanded-add-on-2023-2024` |
| Config | `examples/run-tushare-expanded-add-on.yaml` |
| Artifact dir | `reports/tushare-expanded-add-on-2023-2024` |
| Engine | `backtrader` |
| Period | `2023-01-01` to `2024-12-31` |
| Symbols | 10 |

## Strategy Fixture Role

The current KDJ/MA/add-on strategy is a framework regression fixture. It is
kept because it exercises the full workbench chain:

```text
data preparation -> indicator warmup -> strategy intent -> sizing/constraints
-> execution -> lifecycle -> attribution -> AI review
```

Do not use this baseline to evaluate whether the strategy itself should be
improved, tuned, or deployed. Future strategy work should satisfy
`docs/architecture/strategy-output-contract.md` so existing reports and AI
review artifacts keep working after the strategy changes.

## Accepted Result Snapshot

| Metric | Value |
|---|---:|
| Final equity | `985642.2497650513` |
| Cumulative return | `-0.014357750234948674` |
| Max drawdown | `0.1886705986935961` |
| Closed trades | `129` |
| Win rate | `0.4418604651162791` |
| Completed orders | `266` |
| Rejected orders | `0` |
| Evidence validation | `ok`, errors `0`, warnings `0` |

The real-run regression gate passed with `4` runs, `56` checks, and `0`
failures:

```text
reports/run-regression-check/run_regression.zh.md
```

## AI Review Inputs

Use these artifacts before making review claims:

```text
reports/run-catalog/run_catalog.json
reports/experiment-lifecycle/experiment_lifecycle.json
reports/experiment-decisions/experiment_decisions.json
reports/tushare-expanded-add-on-2023-2024/run_data_overview.json
reports/tushare-expanded-add-on-2023-2024/run_data_dictionary.json
reports/tushare-expanded-add-on-2023-2024/review_brief.all.json
reports/tushare-expanded-add-on-2023-2024/ai_review_result.all.json
reports/environment-fit-comparison-tushare-expanded-baseline-2023-2024__vs__tushare-expanded-add-on-2023-2024/environment_fit_comparison.json
```

The framework-check sample packet is:

```text
reports/tushare-expanded-add-on-2023-2024/baseline-framework-check/run_data_drilldown_batch.json
```

It covers sold-too-early, stop-loss rebound, opportunity cost, add-on, and
environment-fit representative trade samples.

## Boundary Rules

- Do not treat this baseline as proof that the strategy is good or bad.
- Do not tune multiple variables in one follow-up run.
- Do not turn post-exit rebound or opportunity-cost evidence into trading
  rules directly.
- Do not recalculate indicators or infer missing evidence during review.
- Every future experiment must name this baseline, the single changed variable,
  the comparison artifact, and the evidence-validation status.
- Strategy-fit claims must cite `environment_fit` or comparison artifacts plus
  representative `trade_index` or `sample_index`.

## Allowed Next Experiment Shape

Each next experiment should fit this shape:

```text
baseline_run_id: tushare-expanded-add-on-2023-2024
changed_variable: one config or method change only
comparison_required: true
evidence_validation_required: ok
accepted_outputs:
  - result metrics
  - run comparison
  - environment-fit comparison when discussing fit
  - sample drill-downs for representative claims
```

This keeps the next loop focused on the backtest workbench: run, validate,
compare, review, and only then decide whether a new experiment is worth
confirming.
