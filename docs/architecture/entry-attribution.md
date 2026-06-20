# Entry Attribution Design

This document defines the next entry-attribution slice. It extends the current
`result_diagnostics.json` output from a KDJ-only summary into a reusable
attribution contract for future factors such as MA25 position, industry KDJ, or
CSI 300 trend state. It now also defines the first exit-attribution and add-on
attribution output boundary.

## Goal

Entry attribution explains completed trades by looking back to the primary
entry date and the evidence visible when the entry decision was made.

It must answer:

- for winning trades, what entry-time conditions and values were present;
- for losing trades, what entry-time conditions and values were present;
- which factors differ most between winning and losing entry samples;
- how much evidence coverage each factor has.

The same diagnostics layer also explains the exit intent that closed a trade.
Exit intents may carry the same shared symbol, industry, and market attribution
payload as entries, so later post-exit review can group sold-too-early samples
by decision-time context without recalculating indicators.
Add-on attribution is a lifecycle output hook: current runs can emit real
`ADD_ON` intents, expose the add-on signal count, and group successful add-on
intents with the completed trade they belong to. The grouping uses the period
after the primary entry date and before the exit date, so add-on evidence is
explained as part of the trade lifecycle instead of as a standalone signal.
Post-exit follow-up is a separate downstream review: it starts from completed
trade exits, matched exit intents, and prepared bars after sale to observe
configured windows such as 3/5/10/20 trading days. It reports whether price
rebounded after stop-loss or profit-taking and groups those observations by
exit-day evidence. The same downstream lookup rule is used for opportunity
review: sizing blocks, entry-filter blocks, signal blocks, and execution
rejections can be looked up against later bars to show missed follow-up
movement, without turning those blocked intents into completed-trade
attribution samples.

Entry attribution must not recalculate indicators in reports, fill missing
values with defaults, or turn missing evidence into `false`, `0`, or neutral.
Post-exit follow-up follows the same evidence rule: missing future bars remain
missing and are not converted into default returns.

## Current Boundary

The current implementation records winning and losing trade entry evidence from
`signal_audit.json` into `result_diagnostics.json` and renders concise
portfolio/symbol contrasts in Markdown.

New entry evidence is written under the explicit attribution structure. Legacy
top-level `signal_values` fields are still read for backward compatibility.
The configured entry-attribution factor set can also be used as a decision-layer
entry filter before sizing.

## Data Contract

New entry methods and shared evidence builders should write attribution evidence
under `TradeIntent.signal_values["attribution"]`.

Recommended shape:

```python
{
    "checks": {
        "symbol.kdj.j_below_threshold": True,
        "symbol.ma.price_above_ma25": False,
        "industry.kdj.j_below_threshold": True,
        "market.hs300.bullish_trend": True,
    },
    "values": {
        "symbol.kdj.j": 8.2,
        "symbol.ma.ma25": 12.35,
        "symbol.close": 12.8,
        "industry.kdj.j": 10.4,
        "market.hs300.ma20": 3420.55,
        "market.hs300.ma60": 3368.91,
    },
    "categories": {
        "sizing.risk_group": "normal",
        "market.temperature.label": "cold",
        "market.hs300.trend_state": "bullish",
    },
}
```

Factor keys must be namespaced by scope:

| Scope | Example |
|---|---|
| `symbol` | `symbol.ma.price_above_ma25` |
| `industry` | `industry.kdj.j_below_threshold` |
| `market` | `market.hs300.bullish_trend` |
| `sizing` | `sizing.risk_group` |

Composite checks such as bullish trend are decision-layer evidence. Indicator
calculation should only provide reusable numeric values such as close, MA20,
MA25, MA60, or KDJ J.

## Factor Declarations

Every entry attribution factor should be explicitly declared before it is
emitted. A declaration should include:

- key;
- type: `check`, `value`, or `category`;
- Chinese label;
- English label if useful for `report.md`;
- scope: `symbol`, `industry`, `market`, or `sizing`;
- dependency names, such as `ma25`, `kdj:D`, or configured benchmark series;
- missing-data behavior, which should be `missing`.

Ownership:

- entry methods declare factors they directly emit;
- shared evidence builders declare cross-cutting factors such as market or
  industry context;
- reports and diagnostics consume declarations but do not own factor meaning;
- indicators declare numeric indicator capabilities, not composite decisions.

This keeps later additions like `market.hs300.bullish_trend` localized to the
producer that prepares market-context evidence.

## Configuration

Run plans configure entry attribution under `analysis.entry_attribution`:

```yaml
analysis:
  entry_attribution:
    enabled: true
    factors:
      - symbol.ma.price_above_ma25
      - market.hs300.bullish_trend
      - industry.kdj.j_below_threshold
      - sizing.risk_group
    market_symbol: "000300.SH"
    market_fast_period: 20
    market_slow_period: 60
    industry_kdj_threshold: 13
    entry_filter:
      enabled: true
      require_checks:
        - symbol.ma.price_above_ma25
        - market.hs300.bullish_trend
      missing_policy: block
```

When `factors` is empty, all declared factors are enabled. When a subset is
provided, both shared context evidence and entry-method attribution payloads are
trimmed to that set before diagnostics consume them.

`entry_filter` is a decision-layer rule. It requires configured boolean check
factors to be true before an entry goes to sizing. Missing evidence follows the
configured `missing_policy`; it is never silently treated as false for
statistics.

## Sample Definition

The main attribution sample is one completed trade. Rejected, blocked, or
unfilled entry intents remain execution or opportunity evidence and must not be
mixed into winning/losing trade attribution.

V1 uses primary entry attribution for opened positions:

- match a completed trade to the successful entry intent that opened the
  position;
- use that entry intent's attribution evidence;
- match the completed trade to the exit intent on the close date;
- use that exit intent's signal evidence for exit attribution;
- match successful `ADD_ON` intents to the completed trade lifecycle when the
  intent has the same symbol and happened after the primary entry date and
  before the exit date;
- use that add-on intent's attribution evidence for winning/losing add-on
  summaries and contrasts;
- keep blocked, rejected, or unfilled add-on opportunities out of completed
  trade attribution samples while still counting emitted add-on signals.
- render concise add-on entry-point detail rows from the grouped samples, while
  keeping full add-on factor payloads in `result_diagnostics.json`.

## Statistics

Statistics should be calculated at three levels:

| Level | Purpose |
|---|---|
| Trade detail | Explain one completed trade's entry context. |
| Symbol summary | Compare winning and losing samples for one symbol. |
| Portfolio summary | Compare winning and losing samples across the full run. |

For each level, group samples by outcome:

- `win`: `return_pct > 0`;
- `loss`: `return_pct < 0`;
- `flat`: `return_pct == 0`, kept out of win/loss contrast unless explicitly
  requested.

### Check Factors

For boolean checks:

- `sample_count`;
- `present_count`;
- `missing_count`;
- `missing_rate = missing_count / sample_count`;
- `true_count`;
- `false_count`;
- `true_rate = true_count / present_count`.

`true_rate` uses `present_count` as the denominator. Missing checks are not
treated as false.

### Value Factors

For numeric values:

- `sample_count`;
- `present_count`;
- `missing_count`;
- `missing_rate`;
- `avg`;
- `min`;
- `max`.

Later slices can add `p25`, `p50`, and `p75` after the first contract is stable.

### Category Factors

For categorical values:

- `sample_count`;
- `present_count`;
- `missing_count`;
- `missing_rate`;
- per-category `count`;
- per-category `rate = count / present_count`.

## Contrast Ranking

The report should rank factors by winning-vs-losing differences:

- check factor: `win_true_rate - loss_true_rate`;
- value factor: `win_avg - loss_avg`;
- category factor: category-rate gap.

The contrast should include coverage fields so low-coverage factors are visible.
Low sample sizes should be marked instead of treated as strong conclusions.

This contrast is explanatory evidence from completed trades, not a causality
claim or proof of predictive power.

## Artifact Presentation

`result_diagnostics.json` should store the full detail:

- each completed trade's entry attribution evidence;
- each completed trade's exit attribution evidence;
- each completed trade lifecycle's successful add-on attribution evidence;
- symbol-level win/loss summaries;
- portfolio-level win/loss summaries;
- coverage statistics;
- contrast rankings;
- add-on signal counts;
- raw factor keys and translated labels where available.

`trade_lifecycle.json` should store the per-completed-trade timeline:

- entry event evidence;
- successful add-on events inside the trade's primary entry/exit window;
- exit event evidence;
- linked execution events for each lifecycle signal.

`trade_review.json` should store the unified review surface:

- one row per completed trade with entry, add-on, exit, and post-exit flags;
- sold-too-early profile groups that combine exit type, outcome, and selected
  decision-time checks;
- stop-loss rebound profile groups by configured threshold layers;
- opportunity/block samples for entry filters, sizing blocks, signal blocks,
  and execution rejections;
- post-opportunity follow-up windows and opportunity-cost summaries when
  prepared bars and an opportunity price are available;
- successful add-on entry-point samples, their follow-up windows, and grouped
  summaries by trade outcome and add-on evidence.

`post_exit_analysis.json` should store the per-completed-trade post-exit
observation:

- exit group such as stop-loss or profit-taking;
- the configured trading windows after exit when available;
- exit-day checks, values, and categories from the matched exit intent;
- close/high/low returns versus exit price;
- whether price rebounded above the configured sold-too-early threshold;
- rebound threshold summaries such as 0/2/5/10% by exit group;
- group summaries by all trades, stop-loss, profit-taking, and other exits;
- factor group summaries by exit evidence such as stop-hit or KDJ-overheated
  checks.

`post_exit_analysis.zh.md` should rank the most obvious sold-too-early samples
by rebound size before showing the full capped trade-detail table.

`report.zh.md` and `report.md` should stay concise:

- top portfolio-level contrast factors;
- top symbol-level contrast factors;
- entry and exit sections only from available evidence;
- add-on entry-point detail rows for successful add-on samples;
- sample count and coverage;
- pointer to `result_diagnostics.json` for full detail.

`trade_review.zh.md` is the preferred first deep-review Markdown once the normal
report has been read because it joins lifecycle, sold-too-early,
opportunity/block, and add-on entry-point evidence in one place.

`review_packet.<focus>.json` and `review_packet.<focus>.zh.md` are generated by
`att-review-packet` for AI/Skill-assisted review. The packet keeps a stable
`ai_contract`, `overview`, `source_artifacts`, and `sections` shape, then caps
summaries and samples for focuses such as `sold_too_early`,
`stop_loss_rebound`, `opportunity_cost`, `add_on`, and `validation`. It should
be treated as a navigable view over `trade_review.json`, `post_exit_analysis.json`,
`evidence_validation.json`, and related run artifacts, not as a new attribution
source.

`review_findings.<focus>.json` is a structured AI review draft generated from a
review packet. It stores citation-ready finding IDs, evidence refs, sample refs,
metrics, caveats, and next checks. `review_sample.<kind>.<id>.json` is a
focused drill-down generated from `trade_index` or `sample_index`, linking the
selected trade, opportunity, or add-on point back to lifecycle, post-exit,
signal, execution, and closed-trade evidence where available. Both artifacts
help AI review stay grounded; neither owns factor meaning or calculates new
attribution.

`review_sample_batch.<focus>.json` expands the sample refs in findings so a
Skill can inspect the top cases without manual `trade_index` or `sample_index`
selection. `review_brief.<focus>.json` is the preferred Skill input because it
combines findings, sample summaries, and an expected AI output schema.
`ai_review_result.<focus>.json` persists the structured review output from the
brief so it can be audited and compared later. `review_experiment_candidates`
and `review_experiment_drafts` turn findings into validation candidates and YAML
drafts such as grouping probes or evidence-coverage checks. They must not
directly produce parameter changes; new dimensions still need to be emitted by
strategy methods or shared attribution evidence builders before reports and AI
tools can consume them. YAML drafts are planning artifacts until manually
converted into legal RunPlan files.

Markdown should not expand every factor for every trade once the factor set
grows.

## Extension Example

To add "CSI 300 was in bullish trend on entry day":

1. Ensure CSI 300 is available as a configured benchmark or decision series.
2. Prepare numeric market values such as close, MA20, and MA60 before strategy
   execution.
3. Let a shared entry evidence builder evaluate the decision-layer check:
   `market.hs300.bullish_trend`.
4. Write the check, supporting numeric values, and optional category into
   `signal_values["attribution"]`.
5. Declare the factor key, labels, type, scope, dependencies, and missing
   behavior.
6. Let result diagnostics aggregate it automatically.

The report layer should not calculate the trend state after the run.

The same pattern is used for symbol MA trend evidence. Numeric MA20, MA25, and
MA60 values are reusable values; checks such as `symbol.ma.price_above_ma60`,
`symbol.ma.ma20_above_ma60`, and `symbol.ma.bullish_trend` are decision-layer
facts emitted by the attribution evidence producer only when the required MA
windows are available.
