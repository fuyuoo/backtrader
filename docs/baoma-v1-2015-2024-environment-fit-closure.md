# Baoma V1 2015-2024 Environment Fit Closure

本文档封板当前 Baoma V1 十年回测与入场环境归因阶段。封板对象是
2015-2024、`max_holding_count=800` 的已落盘证据链、因子宽表和
`environment_fit` 统计观察，不是策略参数调优结果，也不是上线结论。

机器可读 baseline 存在：

```text
examples/baoma-v1-2015-2024-environment-fit-baseline.json
```

## Closure Statement

当前阶段已经完成以下闭环：

```text
800 股票池
  -> 历史回测 2015-01-01 到 2024-12-31
  -> 全 A 参考数据与 percentile reference
  -> 入场因子宽表
  -> 单因子和白名单双因子 environment_fit 归因
  -> 人工解读与封板 baseline
```

封板后的默认解读边界是：这些结论是本次 run 的统计归因观察，只能作为后续
验证方向，不直接变成买入、卖出、行业黑名单或参数规则。

## Accepted Evidence

| evidence | path |
|---|---|
| run artifacts | `reports/baoma-v1-fixed-sample-2015-2024-maxhold800/` |
| run config | `reports/baoma-v1-fixed-sample-2015-2024-maxhold800/run_plan.json` |
| evidence validation | `reports/baoma-v1-fixed-sample-2015-2024-maxhold800/evidence_validation.json` |
| data validation note | `reports/baoma-v1-fixed-sample-2015-2024-maxhold800/data_validation_check.zh.md` |
| attribution wide samples | `reports/baoma-v1-fixed-sample-2015-2024-maxhold800/full_entry_scope_environment_fit_review/attribution_wide_samples.json` |
| attribution field index | `reports/baoma-v1-fixed-sample-2015-2024-maxhold800/full_entry_scope_environment_fit_review/attribution_field_index.json` |
| enriched environment fit | `reports/baoma-v1-fixed-sample-2015-2024-maxhold800/full_entry_scope_environment_fit_review/environment_fit.enriched.json` |
| enriched environment fit report | `reports/baoma-v1-fixed-sample-2015-2024-maxhold800/full_entry_scope_environment_fit_review/environment_fit.enriched.zh.md` |
| reference snapshot | `data/snapshots/attribution_reference/full_a_main_chinext_star/2015-01-01_2024-12-31_baoma-v1-maxhold800-entry-scope-full-a-industry-backfilled/` |

`reports/` 和 `data/snapshots/` 是本地输出目录，通常被 Git ignore。版本化封板
只保存关键数字、路径和边界，不保存大体积 JSON/CSV。

## Accepted Run Scope

| item | value |
|---|---:|
| run_id | `baoma-v1-fixed-sample-2015-2024-maxhold800` |
| 回测区间 | `2015-01-01` 到 `2024-12-31` |
| 股票池原始数量 | 800 |
| 过滤后股票数量 | 671 |
| 排除股票数量 | 129 |
| 最大持仓数 | 800 |
| 初始资金 | 10,000,000,000 |
| 引擎 | `baoma_v1_business` |
| 入场方法 | `baoma_entry` |
| 止盈方法 | `baoma_ma25_profit_exit` |
| 止损方法 | `baoma_ma60_stop` |
| 加仓方法 | `baoma_add_on` |

## Accepted Verification

| check | result |
|---|---:|
| `evidence_validation.status` | `ok` |
| evidence error / warning | 0 / 0 |
| 闭合交易数 | 18,349 |
| open position count | 109 |
| signal intent count | 2,163,527 |
| execution event count | 61,468 |
| wide sample count | 18,349 |
| wide field count | 176 |
| environment_fit default fields | 31 |
| 单因子汇总 | 161 |
| 双因子组合汇总 | 831 |
| 低样本单因子 / 组合 | 1 / 42 |

已执行的代码校验：

```text
python -m py_compile attbacktrader/cli/prepare_attribution_reference.py attbacktrader/data/providers/tushare.py attbacktrader/data/snapshots/attribution_reference.py
python -m pytest tests/test_reference_snapshots.py tests/test_tushare_provider.py -q
python -m pytest tests/test_backtest_report.py tests/test_run_plan_executor.py -q
```

## Accepted Metrics

| metric | value |
|---|---:|
| final_equity | 11,285,797,727 |
| cumulative_return | 12.86% |
| max_drawdown | 1.83% |
| win_rate | 48.32% |
| profit_loss_ratio | 1.66 |
| environment_fit net_pnl | 1,285,797,727 |
| return_on_entry_value | 1.10% |

收益口径说明：`baoma_v1_business` 当前没有完整 cash/equity curve，本封板使用
已闭合交易的 `net_pnl` 归因口径；109 个未平仓持仓没有在该口径里做市值重估。

## Accepted Observations

### 趋势和位置

- `entry.price_position.ma60_atr_multiple_bucket=above_ma60_gt_2atr`
  表现明显好于整体：4,234 笔，胜率 61.8%，入场资金收益率 1.92%，
  净 PnL 6.07 亿。样例交易：`1, 5, 10, 13, 26`。
- `entry.price_position.near_high_60d_bucket=near_high`
  表现较强：1,602 笔，胜率 57.9%，入场资金收益率 2.06%，
  净 PnL 2.34 亿。样例交易：`1, 28, 33, 44, 69`。

当前策略更像趋势/动量适配，不像低位抄底适配。

### 估值

- PE_TTM `gt_60`：3,302 笔，胜率 49.8%，入场资金收益率 1.57%。
- PE_TTM `0_15`：4,125 笔，胜率 46.1%，入场资金收益率 0.56%。

低估值不是本策略的优势环境。PE_TTM 有 1,174 笔缺失，这个 caveat 必须保留。

### 止盈和波动适配

- `entry.stop_fit.fixed_atr_multiple_bucket=lt_1atr`：1,873 笔，胜率 54.0%，
  入场资金收益率 1.25%。
- `entry.stop_fit.fixed_atr_multiple_bucket=1_2atr`：11,260 笔，胜率 49.4%，
  入场资金收益率 1.19%。
- `entry.stop_fit.fixed_atr_multiple_bucket=2_3atr`：3,951 笔，胜率 43.8%，
  入场资金收益率 0.84%。

固定 5% 止盈和 ATR 的关系有解释价值，但这里只封板为归因观察，不直接改止盈规则。

### 行业

较强行业观察：

- 电力设备 `801730.SI`：1,124 笔，胜率 54.4%，入场资金收益率 2.76%。
- 食品饮料 `801120.SI`：530 笔，入场资金收益率 2.20%。
- 汽车 `801880.SI`：816 笔，入场资金收益率 2.00%。
- 电子 `801080.SI`：1,644 笔，入场资金收益率 1.92%。
- 计算机 `801750.SI`：827 笔，入场资金收益率 1.92%。

较弱行业观察：

- 非银金融 `801790.SI`：1,491 笔，胜率 41.4%，入场资金收益率 -0.52%。
- 交通运输 `801170.SI`：893 笔，入场资金收益率 -0.12%。
- 环保 `801970.SI`：215 笔，入场资金收益率 -0.20%。

行业映射有 2,788 笔 backfilled，行业结论只能作为后续验证线索。

### 双因子

较强组合：

- `MA60 上方超过 2ATR + 电力设备`：271 笔，胜率 73.4%，
  入场资金收益率 4.85%，净 PnL 1.02 亿。样例交易：`55, 103, 119, 178, 180`。
- `MA60 上方超过 2ATR + 电子`：394 笔，胜率 70.1%，
  入场资金收益率 3.87%，净 PnL 1.15 亿。
- `中证500 bullish + 沪深300 bullish`：4,304 笔，胜率 49.8%，
  入场资金收益率 1.61%，净 PnL 4.55 亿。

较弱组合：

- `固定5%止盈=1_2atr + 非银金融`：833 笔，胜率 42.0%，
  入场资金收益率 -1.08%，净 PnL -5,720 万。样例交易：`60, 106, 126, 154, 155`。
- `ATR20=p20_p40 + 非银金融`：363 笔，入场资金收益率 -1.32%，
  净 PnL -3,090 万。

## Known Caveats

- `data_preflight.status=error`，原因是原始 800 只股票中 129 只被排除，
  587 只有 warning；本次证据链 `evidence_validation.status=ok`。
- PE_TTM 缺失 1,174 笔，利润质量字段缺失 715 笔。
- 行业相对波动字段有 7,243 笔 `industry_reference_low_count`。
- 行业映射有 2,788 笔 `industry_membership_backfilled`。
- `entry.momentum.new_high_60d_bucket` 全部落在 `not_new_high`，
  本次不能用于分层解释。
- 当前结论来自 671 只保留股票和 2015-2024 固定样本，不声明全 A 稳定，
  也不声明未来样本稳定。

## Explicit Non-Claims

本封板不声明：

- 策略已经可以上线或适合实盘。
- 任何因子已经是因果规则。
- 行业强弱可以直接变成黑白名单。
- 固定 5% 止盈已经应该改成 ATR 止盈。
- 当前结果已经覆盖全 A。
- 当前策略应做自动参数调优、自动策略搜索或自动策略切换。

## Frozen Boundaries

不要在这个封板阶段继续扩展：

- 不继续临时新增因子。
- 不直接根据本报告改策略参数。
- 不用低样本组合当稳定结论。
- 不把缺失值填成 0、false 或中性。
- 不在报告层重新计算策略决策语义。
- 不把行情阶段识别混入当前封板；行情阶段归因作为下一阶段处理。

## Next Allowed Actions

1. **最推荐：两年 vs 十年归因稳定性比较。**
   目的：比较 2023-2024 与 2015-2024 的强弱因子是否一致，避免只按十年排序或只按两年排序做结论。

2. **补齐标准 AI 入口 artifact。**
   目的：为这个 run 生成或刷新 `run_data_overview`、`run_data_dictionary` 和 `run_catalog`，让后续复盘不用手工读大文件。

3. **市场阶段归因接入。**
   目的：把入场和出场所在市场阶段作为归因维度，检查强趋势因子是否只在特定市场阶段有效。
