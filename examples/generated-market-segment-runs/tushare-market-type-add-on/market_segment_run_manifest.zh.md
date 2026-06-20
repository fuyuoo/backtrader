# 人工行情段验证 Run 草稿

- schema: `attbacktrader.market_segment_run_manifest.v1`
- base_run_id: `tushare-market-type-add-on-validation`
- generated_count: `9`

## 使用规则
- 这些行情段来自人工资料整理，不是代码自动识别的市场状态。
- 生成器只改 RunPlan 的 run.id、run.from_date 和 run.to_date，并校验 YAML 合法。
- 先比较同一行情类型下的多个样本，再跨类型比较 environment_fit 和 strategy_environment_profile。
- 如果某个行情段交易样本不足，应标记为不确定，而不是补默认值或扩大解释。

## 行情类型

| 类型 | 切换作用 | 人工选择规则 | 样本数 |
|---|---|---|---|
| 牛市 | 验证趋势持有、放宽止盈、顺势加仓是否比快进快出更有效。 | 指数中期趋势向上，回撤后仍能继续向上推进或创阶段高点。 | 3 |
| 震荡市 | 验证超卖反弹、快进快出、严格止盈是否更适合区间波动。 | 指数在较宽区间内反复波动，突破和跌破都缺少持续性。 | 3 |
| 熊市 | 验证是否需要少做、降仓、暂停交易或只保留极强反弹信号。 | 指数中期趋势向下，反弹后难以创新高，阶段重心持续下移。 | 3 |

## 行情段


### 牛市

| 行情段 | 日期 | 作用 | RunPlan | 人工相似理由 | 来源 |
|---|---|---|---|---|---|
| 2014-2015 年杠杆牛市主升 | 2014-08-01 至 2015-06-12 | bull_market | `examples\generated-market-segment-runs\tushare-market-type-add-on\tushare-market-type-add-on-market-segment-2014_2015_bull_market.run.yaml` | 这段代表大级别牛市主升，指数从 2000 点附近持续上攻至 5178 点。 | 2014 年 8 月至 2015 年 6 月沪指由 2000 点附近上涨至 5178 点 https://cs.com.cn/gppd/201806/t20180612_5822313.html；2015 年 6 月 12 日上证指数盘中冲上 5178.19 点 https://jingji.cctv.com/2017/06/13/ARTIi6f4i2ch2iia6Zn0lpMN170613.shtml |
| 2019 年一季度单边上攻 | 2019-01-04 至 2019-04-08 | bull_market | `examples\generated-market-segment-runs\tushare-market-type-add-on\tushare-market-type-add-on-market-segment-2019_q1_bull_market.run.yaml` | 这段代表低位启动后的单边上攻，指数在短期内持续扩张涨幅。 | 2019 年 1 月至 4 月上证指数从 2493.90 涨至 3288.45 https://www.jwview.com/jingwei/12-31/284713.shtml；春季躁动历史统计关注指数涨幅和持续交易日 https://wallstreetcn.com/articles/3645427 |
| 2020-2021 年结构性牛市推进 | 2020-03-23 至 2021-02-18 | bull_market | `examples\generated-market-segment-runs\tushare-market-type-add-on\tushare-market-type-add-on-market-segment-2020_2021_structural_bull_market.run.yaml` | 这段代表急跌后进入结构性牛市，指数震荡上行并在 2021 年春节后冲高。 | 2020 年上证指数从年内低点 2646.8 点震荡反弹并快速上冲 3400 点以上 https://www.yicai.com/news/100897955.html；上交所统计月报记录 2021 年 2 月 18 日上证综指最高 3731.69 点 https://www.sse.com.cn/aboutus/publication/monthly/documents/c/10061128/files/da61d7f306674a03902e0b847ce34fae.pdf |

### 震荡市

| 行情段 | 日期 | 作用 | RunPlan | 人工相似理由 | 来源 |
|---|---|---|---|---|---|
| 2016 年熔断后区间震荡 | 2016-01-27 至 2016-12-30 | range_market | `examples\generated-market-segment-runs\tushare-market-type-add-on\tushare-market-type-add-on-market-segment-2016_post_crash_range_market.run.yaml` | 这段代表大跌后的修复震荡，指数底部抬高但没有形成单边牛市。 | 2016 年上证指数 2638 点之后基本处于区间震荡 https://www.scfund.com.cn/news/2017/01/10/26059/1.shtml；2016 年 1 月 27 日低点至 11 月 29 日高点累计最大涨幅约 25% https://www.cs.com.cn/gppd/201704/t20170424_5255738.html |
| 2020 年下半年高位震荡 | 2020-07-13 至 2020-12-31 | range_market | `examples\generated-market-segment-runs\tushare-market-type-add-on\tushare-market-type-add-on-market-segment-2020_h2_high_range_market.run.yaml` | 这段代表快速上冲后的高位箱体，指数围绕 3200-3500 区间反复震荡。 | 2020 年 7 月中旬以来 A 股高位震荡，沪指在 3200 与 3400 附近反复 https://finance.sina.cn/2020-08-06/detail-iivhuipn7075128.d.html；机构预判上证综指维持在 3100-3500 点之间横盘震荡 https://sh.people.com.cn/n2/2020/1203/c139965-34453547.html |
| 2021 年全年箱体震荡 | 2021-01-04 至 2021-12-31 | range_market | `examples\generated-market-segment-runs\tushare-market-type-add-on\tushare-market-type-add-on-market-segment-2021_box_range_market.run.yaml` | 这段代表全年指数箱体震荡，指数多次冲高但未能形成持续突破。 | 2021 年 A 股整体呈现箱体震荡 https://stock.finance.sina.com.cn/stock/go.php/vReport_Show/kind/search/rptid/696284870836/index.phtml；2021 年上证指数最低 3312.72、最高 3731.69，全年振幅 12.06% https://newsxmwb.xinmin.cn/minsheng/finance/2021/12/31/32090754.html |

### 熊市

| 行情段 | 日期 | 作用 | RunPlan | 人工相似理由 | 来源 |
|---|---|---|---|---|---|
| 2015 年高点后的股灾熊市 | 2015-06-12 至 2016-01-27 | bear_market | `examples\generated-market-segment-runs\tushare-market-type-add-on\tushare-market-type-add-on-market-segment-2015_2016_bear_market.run.yaml` | 这段代表牛市高点之后的快速熊市，指数从 5178 点大幅下跌至 2638 点附近。 | 2015 年 6 月 12 日上证指数盘中冲上 5178.19 点 https://jingji.cctv.com/2017/06/13/ARTIi6f4i2ch2iia6Zn0lpMN170613.shtml；2016 年 1 月 27 日上证指数创出 2638.30 点低点 https://www.cs.com.cn/gppd/201704/t20170424_5255738.html |
| 2018 年单边熊市 | 2018-01-29 至 2019-01-04 | bear_market | `examples\generated-market-segment-runs\tushare-market-type-add-on\tushare-market-type-add-on-market-segment-2018_bear_market.run.yaml` | 这段代表年初高点之后的持续下跌，指数重心一路下移至 2019 年初阶段低点。 | 2018 年上证指数从 3587.03 点进入单边熊市 https://www.cnfin.com/stock-xh08/a/20181228/1791327.shtml?f=arelated；2019 年 1 月 4 日上证指数到达 2440.91 点阶段低位 https://www.chnfund.com/article/AR20231210120748171 |
| 2022 年年初快速熊市 | 2022-01-04 至 2022-04-27 | bear_market | `examples\generated-market-segment-runs\tushare-market-type-add-on\tushare-market-type-add-on-market-segment-2022_q1_q2_bear_market.run.yaml` | 这段代表年初高位后快速下跌，指数在四个月内跌破 3000 点并触及年内低位。 | 2022 年 A 股由年初 3600 点高位一度下探到 4 月 27 日 2863 点 https://finance.sina.com.cn/stock/jsy/2022-12-30/doc-imxymwii2630248.shtml；截至 2022 年 4 月 26 日上证指数年内下挫 20.7% https://finance.sina.com.cn/jjxw/2022-04-27/doc-imcwipii6645283.shtml |
