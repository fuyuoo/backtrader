# Exit Method Attribution Missing Evidence Check

本文档记录 Exit Method Attribution 第一刀实现前的证据可用性检查。检查只读
已落盘 run artifacts，不重跑策略、不重算指标、不抓取行情数据、不填默认值。

## Scope

检查对象：

- `market_type_id`: `bull_market`
- baseline manifest:
  `examples/generated-market-segment-runs/tushare-market-type-add-on/market_segment_run_manifest.json`
- variant manifest:
  `examples/generated-strategy-variant-runs/tushare-market-type-add-on/strategy_variant_run_manifest.json`
- selected variant: `bull_market_let_winners_run`
- selected exit method: `ma_macd_weakening_exit`

检查目标：

1. 确认 `trade_lifecycle.json` 的 exit event 是否携带退出方法、原因、checks、
   values、categories。
2. 确认 `ma_macd_weakening_exit` 是否已经能拆成 MA/MACD 子条件。
3. 确认 `post_exit_analysis.json` 和 `trade_review.json` 是否能支撑卖飞和重入
   复盘。
4. 明确哪些证据缺失必须在后续 artifact 中作为 missing 处理。

## Artifact Presence

三段 bull-market baseline/variant 配对 run 的必要 artifacts 均存在：

| segment_id | side | trade_lifecycle | post_exit_analysis | trade_review | report |
|---|---|---:|---:|---:|---:|
| `2014_2015_bull_market` | baseline | 38 | 38 | 38 | 38 |
| `2014_2015_bull_market` | variant | 104 | 104 | 104 | 104 |
| `2019_q1_bull_market` | baseline | 4 | 4 | 4 | 4 |
| `2019_q1_bull_market` | variant | 0 | 0 | 0 | 0 |
| `2020_2021_structural_bull_market` | baseline | 46 | 46 | 46 | 46 |
| `2020_2021_structural_bull_market` | variant | 158 | 158 | 158 | 158 |

The `2019_q1_bull_market` variant has zero completed trades. This is valid
evidence and must remain a zero-sample segment, not a missing artifact.

## Variant Exit Evidence

Bull-market variant exit method counts:

| exit_method_name | count |
|---|---:|
| `ma_macd_weakening_exit` | 258 |
| `fixed_percent_stop` | 4 |

`ma_macd_weakening_exit` has complete direct component evidence for all 258
exit events:

| evidence key | coverage |
|---|---:|
| `required_values_available` | 258 / 258 |
| `price_below_fast_ma` | 258 / 258 |
| `fast_ma_below_slow_ma` | 258 / 258 |
| `macd_line_below_signal` | 258 / 258 |
| `macd_bearish_crossover` | 258 / 258 |
| `close` | 258 / 258 |
| `ma20` | 258 / 258 |
| `ma60` | 258 / 258 |
| `macd_line` | 258 / 258 |
| `macd_signal` | 258 / 258 |
| `macd_histogram` | 258 / 258 |
| `previous_macd_line` | 258 / 258 |
| `previous_macd_signal` | 258 / 258 |
| `previous_macd_histogram` | 258 / 258 |

This means the first implementation can split `ma_macd_weakening_exit` by:

- MA price condition: `price_below_fast_ma`;
- MA trend condition: `fast_ma_below_slow_ma`;
- MACD weak state: `macd_line_below_signal`;
- MACD crossover: `macd_bearish_crossover`;
- supporting numeric values and previous MACD values.

The implementation does not need to recalculate MA or MACD in reports.

## Baseline Exit Evidence

Bull-market baseline exit method counts:

| exit_method_name | count |
|---|---:|
| `kdj_overheated_exit` | 59 |
| `fixed_percent_stop` | 29 |

`kdj_overheated_exit` carries direct KDJ evidence:

| evidence key | coverage |
|---|---:|
| `kdj_j_above_threshold` | 59 / 59 |
| `kdj_k` | 59 / 59 |
| `kdj_d` | 59 / 59 |
| `kdj_j` | 59 / 59 |
| `threshold` | 59 / 59 |

This is enough to compare the baseline's primary profit-taking method against
the variant's primary `ma_macd_weakening_exit` behavior.

## Shared Context Coverage

Shared symbol, market, and industry context is available but not always complete
because longer-window evidence can be unavailable during warmup. These gaps
must remain missing in the new artifact.

Variant bull-market exits:

| evidence key | coverage |
|---|---:|
| `symbol.ma.price_above_ma25` | 262 / 262 |
| `industry.kdj.j_below_threshold` | 262 / 262 |
| `symbol.ma.price_above_ma60` | 260 / 262 |
| `symbol.ma.ma20_above_ma60` | 260 / 262 |
| `symbol.ma.bullish_trend` | 260 / 262 |
| `market.hs300.bullish_trend` | 260 / 262 |

Baseline bull-market exits:

| evidence key | coverage |
|---|---:|
| `industry.kdj.j_below_threshold` | 88 / 88 |
| `symbol.ma.price_above_ma25` | 87 / 88 |
| `market.hs300.bullish_trend` | 72 / 88 |
| `symbol.ma.price_above_ma60` | 71 / 88 |
| `symbol.ma.ma20_above_ma60` | 71 / 88 |
| `symbol.ma.bullish_trend` | 71 / 88 |

These missing counts are expected warmup/availability gaps. The report layer
must not treat them as `false`, `0`, or neutral.

## Decision

The first `att-exit-method-attribution` implementation can start from existing
artifacts. It should not begin with upstream evidence capture.

Reason:

- `ma_macd_weakening_exit` already records MA and MACD component checks;
- supporting numeric MA/MACD values and previous MACD values are present;
- baseline KDJ exit evidence is present;
- post-exit and trade-review artifacts exist for all paired bull-market runs;
- the only gaps are shared long-window context coverage, which should be
  counted as missing.

## Implementation Implications

The first slice should:

- group exit events by `exit_method_name` and `reason_code`;
- split `ma_macd_weakening_exit` by the four direct component checks;
- join post-exit and trade-review samples by `run_id + trade_index`;
- preserve the zero-trade `2019_q1_bull_market` variant segment;
- count missing shared context fields explicitly;
- avoid any report-layer MA/MACD recalculation.

## Non-Claims

This check does not claim:

- `ma_macd_weakening_exit` is wrong in every environment;
- a new exit rule should be generated now;
- the MA condition or MACD condition is already proven to be the cause;
- missing shared context should be filled or inferred.

The next step is implementation of the attribution artifact, not strategy
tuning.
