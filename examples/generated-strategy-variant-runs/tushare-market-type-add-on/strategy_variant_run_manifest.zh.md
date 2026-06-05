# 策略变体 RunPlan Manifest

- schema: `attbacktrader.strategy_variant_run_manifest.v1`
- base_run_id: `tushare-market-type-add-on-validation`
- generated_count: `9`
- reuse_snapshots: `False`

## 规则
- 每个 YAML 都由原始 market segment RunPlan 合并对应市场类型的 strategy variant patch 得到。
- 只合并合法 RunPlan 顶层字段；review_candidate 等元数据保留在 manifest，不写入可执行 YAML。
- 市场类型仍来自人工 manifest；本生成器不识别行情、不自动切换策略。
- 生成的 RunPlan 已通过 RunPlan.from_mapping 校验；执行前仍需人工确认样本范围。

## RunPlan

| 市场类型 | 行情段 | 变体 | run_id | YAML |
|---|---|---|---|---|
| 牛市 | 2014-2015 年杠杆牛市主升 | bull_market_let_winners_run | `tushare-market-type-add-on-market-segment-2014_2015_bull_market__variant__bull_market_let_winners_run` | `examples\generated-strategy-variant-runs\tushare-market-type-add-on\tushare-market-type-add-on-market-segment-2014_2015_bull_market__variant__bull_market_let_winners_run.run.yaml` |
| 牛市 | 2019 年一季度单边上攻 | bull_market_let_winners_run | `tushare-market-type-add-on-market-segment-2019_q1_bull_market__variant__bull_market_let_winners_run` | `examples\generated-strategy-variant-runs\tushare-market-type-add-on\tushare-market-type-add-on-market-segment-2019_q1_bull_market__variant__bull_market_let_winners_run.run.yaml` |
| 牛市 | 2020-2021 年结构性牛市推进 | bull_market_let_winners_run | `tushare-market-type-add-on-market-segment-2020_2021_structural_bull_market__variant__bull_market_let_winners_run` | `examples\generated-strategy-variant-runs\tushare-market-type-add-on\tushare-market-type-add-on-market-segment-2020_2021_structural_bull_market__variant__bull_market_let_winners_run.run.yaml` |
| 震荡市 | 2016 年熔断后区间震荡 | range_market_range_no_add_on_fast_review | `tushare-market-type-add-on-market-segment-2016_post_crash_range_market__variant__range_market_range_no_add_on_fast_review` | `examples\generated-strategy-variant-runs\tushare-market-type-add-on\tushare-market-type-add-on-market-segment-2016_post_crash_range_market__variant__range_market_range_no_add_on_fast_review.run.yaml` |
| 震荡市 | 2020 年下半年高位震荡 | range_market_range_no_add_on_fast_review | `tushare-market-type-add-on-market-segment-2020_h2_high_range_market__variant__range_market_range_no_add_on_fast_review` | `examples\generated-strategy-variant-runs\tushare-market-type-add-on\tushare-market-type-add-on-market-segment-2020_h2_high_range_market__variant__range_market_range_no_add_on_fast_review.run.yaml` |
| 震荡市 | 2021 年全年箱体震荡 | range_market_range_no_add_on_fast_review | `tushare-market-type-add-on-market-segment-2021_box_range_market__variant__range_market_range_no_add_on_fast_review` | `examples\generated-strategy-variant-runs\tushare-market-type-add-on\tushare-market-type-add-on-market-segment-2021_box_range_market__variant__range_market_range_no_add_on_fast_review.run.yaml` |
| 熊市 | 2015 年高点后的股灾熊市 | bear_market_defensive_sizing | `tushare-market-type-add-on-market-segment-2015_2016_bear_market__variant__bear_market_defensive_sizing` | `examples\generated-strategy-variant-runs\tushare-market-type-add-on\tushare-market-type-add-on-market-segment-2015_2016_bear_market__variant__bear_market_defensive_sizing.run.yaml` |
| 熊市 | 2018 年单边熊市 | bear_market_defensive_sizing | `tushare-market-type-add-on-market-segment-2018_bear_market__variant__bear_market_defensive_sizing` | `examples\generated-strategy-variant-runs\tushare-market-type-add-on\tushare-market-type-add-on-market-segment-2018_bear_market__variant__bear_market_defensive_sizing.run.yaml` |
| 熊市 | 2022 年年初快速熊市 | bear_market_defensive_sizing | `tushare-market-type-add-on-market-segment-2022_q1_q2_bear_market__variant__bear_market_defensive_sizing` | `examples\generated-strategy-variant-runs\tushare-market-type-add-on\tushare-market-type-add-on-market-segment-2022_q1_q2_bear_market__variant__bear_market_defensive_sizing.run.yaml` |
