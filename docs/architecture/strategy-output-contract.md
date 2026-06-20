# Strategy Output Contract

This contract keeps future strategy implementations independent from reports,
attribution, market-type validation, and AI review. The current KDJ/MA strategy
is only a framework regression fixture; it is not a strategy approval.

## Purpose

Every strategy method must emit standard `TradeIntent` evidence so downstream
artifacts can continue to work when the strategy changes.

The downstream chain is:

```text
Strategy method
  -> TradeIntent
  -> signal_audit.json
  -> sizing_audit.json / execution_audit.json
  -> trade_lifecycle.json
  -> trade_review / environment_fit / strategy_adaptation_matrix / review_packet
```

Reports and AI review consume the persisted evidence. They must not rerun
strategy methods, refetch data, recalculate indicators, or infer missing
strategy decisions.

## Required Intent Fields

Each emitted intent must provide:

| Field | Role |
|---|---|
| `intent_type` | One of `enter`, `add_on`, `exit_profit`, `exit_loss`, `hold`, `avoid`. |
| `symbol` | Tradable symbol. |
| `trade_date` | Decision date used to join signal, execution, and lifecycle evidence. |
| `method_name` | Stable method identifier, for example `kdj_oversold_entry`. |
| `reason_code` | Stable machine-readable decision reason. |
| `signal_values` | JSON-safe evidence payload consumed by attribution and review. |

Optional fields are `target_price`, `risk_price`, `confidence`, and
`blocked_by`.

## Signal Values

`signal_values` may contain scalar evidence directly, but structured evidence
has reserved shapes:

| Key | Shape | Consumer |
|---|---|---|
| `checks` | `dict[str, bool]` | signal audit, lifecycle, diagnostics |
| `attribution.checks` | `dict[str, bool]` | entry attribution, environment fit, matrix |
| `attribution.values` | `dict[str, scalar]` | sample drill-down, review packet |
| `attribution.categories` | `dict[str, scalar]` | grouping by market/industry/sizing state |
| `sizing` | `dict[str, scalar]` | sizing audit and rejection context |

Examples of decision-layer checks:

```text
symbol.ma.price_above_ma25=true
symbol.ma.bullish_trend=false
market.hs300.bullish_trend=false
industry.kdj.j_below_threshold=true
```

These are not indicator calculations. The indicator layer calculates reusable
raw values such as MA, KDJ, MACD, RSI, and ATR. Trend state, price-above-MA, and
market-type labels are decision or attribution evidence.

## Lifecycle Matching

`trade_lifecycle.json` links completed trades back to existing intent evidence:

| Lifecycle event | Match rule |
|---|---|
| `entry` | successful `enter` intent by symbol and entry date |
| `add_on` | successful `add_on` intents inside the holding window |
| `exit` | successful `exit_profit` or `exit_loss` intent by symbol, exit date, and exit reason |

If evidence is missing, lifecycle reports the absence. It must not synthesize
method names, reasons, checks, categories, or values.

## Baseline Role

The current KDJ/MA strategy remains useful as a deterministic framework fixture:

- It validates indicator preparation and warmup behavior.
- It exercises entry, exit, add-on, sizing, constraints, and rejection evidence.
- It proves the report and AI review chain can consume a complete run.

It must not be used as evidence that the trading logic is good, bad, or ready
for production trading.

## Implementation

The executable contract lives in:

```text
attbacktrader/strategies/contract.py
tests/test_strategy_output_contract.py
```

The acceptance smoke includes the contract test so future strategy changes
cannot silently break downstream artifact compatibility.
