# EW Seed Only V2 回测 Runner 分数接口

## 结论

`ew_seed_only_v2` 可以从研究脚本验证推进到 backtest-only 的 runner 分数接口。

下一步实现不应改动实盘交易。它应该新增一个 runner-level adapter：加载预计算分数 artifact，按 `symbol + trade_date` 把分数挂到 enter 候选上，然后把组合排序和容量约束交给现有 scored allocation 模块。

当前已验证的实现 seam 是：

```text
Decision events + precomputed score rows
  -> simulate_precomputed_score_portfolio(...)
  -> ranked backtest portfolio simulation
```

## 路线图位置

这属于路线图第 6 步的准备工作：

```text
1. Factor evidence scorecard
2. Generate seed/soil score v2 evidence-weighted
3. Offline ranking validation
4. Portfolio proxy validation with TopN + MaxHold
5. Formal strategy/candidate-pool validation
6. Runner-level interface design
```

第 5 步的验证已经足够支撑接口设计：

- 正式事件流：真实 HS300-only `signal_audit.parquet`。
- 分数 artifact 覆盖率：`11004 / 11061` enter events，`99.48%`。
- 缺失分数事件：`57` 条，且集中在 `2022-2023` 之外。
- `2022-2023` 的弱点是市场暴露问题，不是 score contract 缺口。

## 非目标

本切片不要做这些事：

- 不启用实盘交易。
- 不把 `soil` 加为主排序分数。
- 不为了修复熊市暴露而新增短期硬 gate。
- 不重写策略 entry 规则。
- 不让 runner 代码读取未来字段，例如 exit date、return、PnL、holding days、win/loss 或 exit reason。

## 接口

backtest runner 应暴露一个小接口：

```yaml
entry_score:
  enabled: true
  scope: backtest_only
  score_id: ew_seed_only_v2
  score_field: entry.score.ew_seed_only_v2
  source_score_field: ew_seed_only_score
  artifact_path: reports/evidence-weighted-ranking-validation-hs300-only-2006-2025/evidence_weighted_scored_trade_detail.parquet
  key:
    symbol: symbol
    trade_date: entry_date
  replay_start_date: 2013-01-01
  replay_end_date: 2025-12-31
  replay_initial_cash: 10000000
  missing_score_policy: skip
```

字段语义：

| Field | Meaning |
|---|---|
| `enabled` | 只在回测运行中启用按分数排序的 entry selection。 |
| `scope` | 必须是 `backtest_only`；其他值应直接失败。 |
| `score_id` | 人类可读的分数合同 id，当前为 `ew_seed_only_v2`。 |
| `score_field` | 用于候选排序的数值分数字段。 |
| `source_score_field` | score artifact 中实际读取的分数字段。若上游 artifact 列名与 runner 注入字段不同，用它做映射。 |
| `artifact_path` | 预计算分数行。第一版 adapter 可以只支持 Parquet。 |
| `key.symbol` | 分数 artifact 中的 symbol 列。 |
| `key.trade_date` | 分数 artifact 中与 decision `trade_date` 对齐的日期列。 |
| `replay_start_date` | 可选。只把该日期及之后的 decision events 和 score rows 纳入 entry_score replay contract。 |
| `replay_end_date` | 可选。只把该日期及之前的 decision events 和 score rows 纳入 entry_score replay contract。 |
| `replay_initial_cash` | 可选。只用于 entry_score replay 的组合本金；不改变 baoma engine 事件生成本金。未配置时使用 `broker.initial_cash`。 |
| `missing_score_policy` | `skip` 或 `fail`。 |

`replay_start_date` / `replay_end_date` 不改变 engine 的起跑窗口。它们只改变 entry_score replay 的计分窗口，用来支持“先用更长历史窗口恢复策略状态，再只审计目标测试窗”的回测口径。

`replay_initial_cash` 不改变 engine 的事件生成口径。它只改变 `simulate_precomputed_score_portfolio(...)` 的 `portfolio_controls.initial_cash`，用于复现“旧事件源 + 新组合 replay”的 formal result。

## 缺失分数策略

第一版研究/回测验证默认使用 `skip`。

策略行为：

| Policy | Behavior |
|---|---|
| `skip` | 候选保留在 audit trail 中，但通过 `SCORE_GATE` 阻塞。 |
| `fail` | 只要任意 enter event 没有分数，runner 在模拟前失败。 |

不要把缺失分数静默填成 0。0 分是真实排序值；缺失分数是 contract 状态。

## 模块形状

深模块应保持在：

```text
attbacktrader.reports.scored_entry_allocation_tuning
```

当前公开接口：

```python
simulate_precomputed_score_portfolio(
    events,
    score_rows=...,
    score_field="entry.score.ew_seed_only_v2",
    portfolio_controls=...,
    missing_score_policy="skip",
    score_id="ew_seed_only_v2",
)
```

runner-level 代码应该是 adapter，而不是新的模拟模块。它只负责：

- 校验 `scope == backtest_only`。
- 加载 score artifact。
- 把列归一化为 `symbol`、`trade_date` 和 `score_field`。
- 按 `replay_start_date` / `replay_end_date` 同步过滤 decision events 和 score rows。
- 把 decision events 和 score rows 传给 `simulate_precomputed_score_portfolio`。
- 落盘返回的 `precomputed_score_contract`。

runner adapter 不应重复实现排序、现金、持仓上限、行业上限或缺失分数逻辑。

## Artifact 合同

最小 score artifact 行包含：

```text
symbol
trade_date or entry_date
entry.score.ew_seed_only_v2
```

允许的元数据字段：

```text
fold_id
train_start_year
train_end_year
test_year
seed_v2_candidate_score
```

runner 输入禁止使用的字段：

```text
exit_date
exit_price
return_pct
realized_return_pct
net_pnl
is_win
holding_days
exit_reason
```

这些字段可以存在于上游研究 artifact 中，但 runner adapter 必须在调用分数接口前丢弃它们。

## 起跑边界与 replay window

旧 contract 的口径不是直接从 2013 年起跑，而是：

```text
engine window: 2006-01-01 -> 2025-12-31
entry_score replay window: 2013-01-01 -> 2025-12-31
```

也就是说，旧回测在 2013 年进入测试窗时，已经继承了 2006-2012 形成的持仓、现金和生命周期状态。

因此，`2013-01-01 -> 2025-12-31` 直跑新 runner 不应被拿来和旧 contract 做强等价比较。直跑口径会丢掉 2013 年初之前的策略状态，实际审计结果已经显示差异集中在 `2013-01`：

| 指标 | 旧 contract | 2013 直跑新 runner |
|---|---:|---:|
| enter_event_count | 11061 | 11011 |
| matched_enter_score_count | 11004 | 10953 |
| missing_enter_score_count | 57 | 58 |
| score_keys_not_in_enter_events_count | 0 | 51 |

enter key 差异审计结论：

- 51 个旧有、新无的 enter keys 全部集中在 `2013-01-04` 到 `2013-01-17`。
- 这 51 个 keys 全部有 score。
- 新 runner 直跑额外多出 1 个 `601398.SH @ 2024-01-08`，且没有 score。

这说明差异来自起跑边界状态，不是 score contract 接口错误。

要复现旧 contract，新 runner 应使用：

```yaml
run:
  from_date: 2006-01-01
  to_date: 2025-12-31

execution:
  entry_score:
    replay_start_date: 2013-01-01
    replay_end_date: 2025-12-31
```

同口径复现结果：

| 指标 | 旧 contract | 新 runner 同口径复现 |
|---|---:|---:|
| enter_event_count | 11061 | 11061 |
| matched_enter_score_count | 11004 | 11004 |
| missing_enter_score_count | 57 | 57 |
| score_keys_not_in_enter_events_count | 0 | 0 |

复现输出目录：

```text
reports/ew-seed-only-v2-entry-score-runner-warmup-2006-filter-2013-2025
```

关键产物：

- `entry_score_contract.json`
- `entry_score_replay_summary.json`
- `entry_score_selected_entries.parquet`
- `entry_score_blocked_entries.parquet`
- `entry_score_equity_curve.parquet`

## 事件生成本金与 replay 本金

旧 formal result 的真实口径分成两段：

```text
event generation: broker.initial_cash = 10,000,000,000
portfolio replay: initial_cash = 10,000,000
```

旧 formal 的 `decision_events_ew_seed_only_v2.parquet` 来自 10B 本金的 baoma source run；随后 formal 脚本在 `simulate_precomputed_score_portfolio(...)` 中使用 10M 本金做组合 replay。

因此，不能通过把新 runner 的 `broker.initial_cash` 直接改成 10M 来复现旧 formal 数值。这样会让 baoma engine 用 10M 重新生成事件流，合同会从旧口径的 `11061` 个 enter events 变成另一条路径。

要复现旧 formal 数值，新 runner 应使用：

```yaml
broker:
  initial_cash: 10000000000

execution:
  entry_score:
    replay_initial_cash: 10000000
```

这个配置含义是：engine 仍按旧 source run 的 10B 口径生成 decision events；entry_score replay 按旧 formal 的 10M 组合本金计算 selected、blocked、equity 和 metrics。

10B 事件生成 + 10M replay 本金的全量复现已经通过旧 formal 结果级 parity 审计：

```text
engine window: 2006-01-01 -> 2025-12-31
entry_score replay window: 2013-01-01 -> 2025-12-31
engine_initial_cash: 10,000,000,000
replay_initial_cash: 10,000,000
```

结果级审计结论：

| 检查项 | 旧 formal | 新 runner | 差异 |
|---|---:|---:|---:|
| enter_event_count | 11061 | 11061 | 0 |
| matched_enter_score_count | 11004 | 11004 | 0 |
| missing_enter_score_count | 57 | 57 | 0 |
| score_keys_not_in_enter_events_count | 0 | 0 | 0 |
| selected entries | 2842 | 2842 | 0 |
| blocked entries | 8219 | 8219 | 0 |
| equity rows | 2854 | 2854 | 0 |

`selected`、`blocked` 和 `equity_curve` 均为 key/日期/数值级等价。指标差异只剩浮点尾差，最大量级约 `1e-16`。

确认输出目录：

```text
reports/ew-seed-only-v2-entry-score-runner-warmup-2006-filter-2013-2025-replay-cash-10m
```

## 验收检查

第一版 runner-level 实现满足以下条件即可接受：

- 单元测试覆盖 `skip`、`fail`、重复 score key 和非有限分数。
- 使用 `scope: backtest_only` 且 `2006-2025 engine window + 2013-2025 replay window` 的回测配置，能产出与旧 contract 相同的覆盖合同：`11061 enter`，`11004 matched`，`57 missing`，`0 extra score keys`。
- `missing_score_policy: skip` 会把缺失候选记录为 `SCORE_GATE`。
- `missing_score_policy: fail` 会在模拟前失败，并报告一组缺失的 `symbol@trade_date` 样例。
- 实盘运行配置会拒绝 `entry_score.enabled: true`。
- 报告写出 `precomputed_score_contract`，包含 enter count、matched count、missing count、extra score keys、score id、score field 和 missing policy。
- 报告写出 replay source 元数据，至少包含 `replay_start_date`、`replay_end_date`、原始 decision event count 和 replay 后 decision event count。
- 若配置了 `replay_initial_cash`，报告写出的 replay source 元数据应同时包含 `engine_initial_cash` 和 `replay_initial_cash`。

## 实现顺序

1. 在 backtest runner 路径下新增 `entry_score` 配置模型。
2. 新增 Parquet score artifact loader adapter。
3. 在 adapter seam 丢弃禁止的未来字段。
4. 把 adapter 接入 backtest-only entry ranking。
5. 增加 runner-level 测试，覆盖 `skip`、`fail` 和实盘拒绝。
6. 通过 runner-level 路径重新跑 HS300-only formal validation。
7. 对旧 contract 使用 `2006-2025 engine window + 2013-2025 replay window` 做同口径复现。

## 当前参考

- 公开分数模拟接口：
  `attbacktrader/reports/scored_entry_allocation_tuning.py`
- 当前 formal validation 脚本：
  `scripts/ew_seed_only_v2_formal_backtest.py`
- 当前 formal report：
  `reports/ew-seed-only-v2-formal-backtest-hs300-only-2013-2025/ew_seed_only_v2_formal_backtest.zh.md`
- 缺失分数审计：
  `reports/ew-seed-only-v2-formal-backtest-hs300-only-2013-2025/missing_score_enter_events_audit.zh.md`
- 起跑边界差异审计：
  `reports/ew-seed-only-v2-entry-score-runner-full-hs300-only-2013-2025/entry_score_contract_boundary_audit_note.zh.md`
- 新 runner 同口径复现：
  `reports/ew-seed-only-v2-entry-score-runner-warmup-2006-filter-2013-2025/entry_score_contract.json`
- 新 runner 旧 formal 数值 parity：
  `reports/ew-seed-only-v2-entry-score-runner-warmup-2006-filter-2013-2025-replay-cash-10m/formal_result_parity_replay_cash_10m_audit.zh.md`
- 新 runner 旧 formal 数值 parity 回归命令：
  `python scripts/check_entry_score_formal_parity.py`
