# Baoma V1 Score 5 Date Contract

## Conclusion

The original strong `score >= 5` portfolio result used the correct Baoma entry-date relationship:

```text
T-1: signal / selection day
T: buy / execution day, stored as trade_date in the old scored portfolio selected entries
```

Do not reinterpret that result as same-day signal and same-day buy just because the old selected-entry artifact only contains `trade_date`.

More precisely, the live workflow is:

```text
T day: run the selector and place the buy order.
T-1 day: the completed bar used as the selection/evidence date.
```

So the action happens on T, but the selected shape is yesterday's shape.

## Validated Run

- Original result directory: `reports/scored-portfolio-fixed-score5-conservative-prefer-unheld-industry-2015-2024`
- Selected entries: `reports/scored-portfolio-fixed-score5-conservative-prefer-unheld-industry-2015-2024/scored_selected_entries.csv`
- Source decision table: `reports/strategy-decision-event-table-baoma-v1-fixed-sample-2015-2024-full-signal/decision_event_table.json`
- Validation output: `reports/original-good-score5-prev-day-check`

## Validation Result

The validation checked each selected buy against the previous trading day's bars and indicators, not against the entry price.

| Check | Passed |
|---|---:|
| Selected buy rows | 1882 |
| Previous trading day close > MA60 | 1882 / 1882 |
| Previous trading day DEA recently crossed above zero within 14 trading days | 1882 / 1882 |
| Previous trading day bearish candle | 1882 / 1882 |
| All Baoma entry requirements passed on previous trading day | 1882 / 1882 |

## Important Reading Rule

For this old artifact:

- `trade_date` in `scored_selected_entries.csv` is the buy date.
- The signal/selection date is the previous trading day for that symbol.
- The artifact does not persist a separate `signal_date`, so the relationship must be verified from prior-day bars and indicators or from future artifacts that explicitly write both dates.

For current RunPlan artifacts:

- `signal_audit.trade_date` is the T-day decision/buy-attempt date.
- `signal_audit.signal_values.signal_trade_date` is the T-1 evidence date used by `baoma_entry`.
- `execution_audit.signal_date` currently follows the intent date and can equal the T-day buy-attempt date; do not treat it as the shape/evidence date.

## Dynamic Index-Membership Stock Pool

For pre-2015 validation against HS300/CSI500 constituents, use two separate artifacts:

- Historical union CSV: all symbols that ever appeared in the selected indexes during the research window. This is only the data-preparation universe.
- Dynamic membership Parquet: point-in-time index constituent snapshots. This is the actual entry gate.

The dynamic gate must evaluate membership on `signal_values.signal_trade_date` (T-1 evidence date), not on the T-day buy/intent date. A candidate can only keep `BAOMA_ENTRY_TRIGGERED` if it belonged to HS300 or CSI500 as of the latest available constituent snapshot on or before that T-1 date.

Current generated artifacts:

- `reports/pre2015-2005-2014/input/hs300-csi500-dynamic-constituents-2005-2014.parquet`
- `reports/pre2015-2005-2014/input/hs300-csi500-dynamic-union-2005-2014.csv`
- `reports/pre2015-2005-2014/input/hs300-csi500-dynamic-constituents-2005-2014.json`

## Anti-Regression Note

Future scored portfolio outputs should persist both fields explicitly:

- `signal_date`: the completed bar used for entry evidence and score.
- `buy_date`: the execution date when the portfolio attempts to enter.

When comparing old and new results, do not use entry price equality with close/open to infer the signal date. The correct validation is whether the previous trading day satisfied the Baoma entry requirements.
