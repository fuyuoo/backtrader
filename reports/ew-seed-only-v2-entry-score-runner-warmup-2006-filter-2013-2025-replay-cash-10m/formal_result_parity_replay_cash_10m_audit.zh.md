# 新 runner 旧 formal 数值 parity 审计

## 结论

通过。

这次 run 使用新 runner 接口复现旧 formal result 的真实口径：

```text
engine window: 2006-01-01 -> 2025-12-31
entry_score replay window: 2013-01-01 -> 2025-12-31
engine_initial_cash: 10,000,000,000
replay_initial_cash: 10,000,000
```

关键点是不要把 `broker.initial_cash` 直接改成 10M。旧 formal 是用 10B source run 生成 decision events，然后用 10M 做 portfolio replay。

## Contract parity

| 字段 | 旧 formal | 新 runner | 差异 |
|---|---:|---:|---:|
| enter_event_count | 11061 | 11061 | 0 |
| matched_enter_score_count | 11004 | 11004 | 0 |
| missing_enter_score_count | 57 | 57 | 0 |
| score_keys_not_in_enter_events_count | 0 | 0 | 0 |

## Result parity

| 检查项 | 旧 formal | 新 runner | 差异 |
|---|---:|---:|---:|
| selected entries | 2842 | 2842 | 0 |
| blocked entries | 8219 | 8219 | 0 |
| equity rows | 2854 | 2854 | 0 |
| equity date mismatches | 0 | 0 | 0 |

`selected` key 集合完全一致，`blocked` key 集合完全一致。

`entry_score_equity_curve.parquet` 与旧 `formal_backtest_equity_curves.parquet` 中对应参数组合在以下字段上最大差异均为 0：

```text
cash
position_value
total_value
drawdown
holding_count
exposure
cash_ratio
```

## Metric parity

核心指标与旧 formal 完全一致，只有浮点尾差：

| 指标 | 旧 formal | 新 runner |
|---|---:|---:|
| cumulative_return | -0.0480068 | -0.048006800000000016 |
| annualized_return | -0.0480068 | -0.048006800000000016 |
| max_drawdown | 0.489458114161362 | 0.48945811416136203 |
| sharpe_ratio | 0.0463467004669561 | 0.04634670046695619 |
| trade_count | 2842 | 2842 |
| closed_trade_count | 2842 | 2842 |
| average_holding_count | 16.852838121934127 | 16.852838121934127 |
| maximum_holding_count | 20 | 20 |
| average_cash_ratio | 0.2047251220678501 | 0.2047251220678501 |
| turnover | 126.2086516 | 126.2086516 |

## Artifacts

本次新 runner 输出目录：

```text
reports/ew-seed-only-v2-entry-score-runner-warmup-2006-filter-2013-2025-replay-cash-10m
```

关键文件：

- `entry_score_contract.json`
- `entry_score_replay_summary.json`
- `entry_score_selected_entries.parquet`
- `entry_score_blocked_entries.parquet`
- `entry_score_equity_curve.parquet`
