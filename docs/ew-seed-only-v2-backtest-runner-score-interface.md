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
  artifact_path: reports/evidence-weighted-ranking-validation-hs300-only-2006-2025/evidence_weighted_scored_trade_detail.parquet
  key:
    symbol: symbol
    trade_date: entry_date
  missing_score_policy: skip
```

字段语义：

| Field | Meaning |
|---|---|
| `enabled` | 只在回测运行中启用按分数排序的 entry selection。 |
| `scope` | 必须是 `backtest_only`；其他值应直接失败。 |
| `score_id` | 人类可读的分数合同 id，当前为 `ew_seed_only_v2`。 |
| `score_field` | 用于候选排序的数值分数字段。 |
| `artifact_path` | 预计算分数行。第一版 adapter 可以只支持 Parquet。 |
| `key.symbol` | 分数 artifact 中的 symbol 列。 |
| `key.trade_date` | 分数 artifact 中与 decision `trade_date` 对齐的日期列。 |
| `missing_score_policy` | `skip` 或 `fail`。 |

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

## 验收检查

第一版 runner-level 实现满足以下条件即可接受：

- 单元测试覆盖 `skip`、`fail`、重复 score key 和非有限分数。
- 使用 `scope: backtest_only` 的回测配置能产出与当前验证相同的覆盖合同：`11004 matched`，`57 missing`。
- `missing_score_policy: skip` 会把缺失候选记录为 `SCORE_GATE`。
- `missing_score_policy: fail` 会在模拟前失败，并报告一组缺失的 `symbol@trade_date` 样例。
- 实盘运行配置会拒绝 `entry_score.enabled: true`。
- 报告写出 `precomputed_score_contract`，包含 enter count、matched count、missing count、extra score keys、score id、score field 和 missing policy。

## 实现顺序

1. 在 backtest runner 路径下新增 `entry_score` 配置模型。
2. 新增 Parquet score artifact loader adapter。
3. 在 adapter seam 丢弃禁止的未来字段。
4. 把 adapter 接入 backtest-only entry ranking。
5. 增加 runner-level 测试，覆盖 `skip`、`fail` 和实盘拒绝。
6. 通过 runner-level 路径重新跑 HS300-only formal validation。

## 当前参考

- 公开分数模拟接口：
  `attbacktrader/reports/scored_entry_allocation_tuning.py`
- 当前 formal validation 脚本：
  `scripts/ew_seed_only_v2_formal_backtest.py`
- 当前 formal report：
  `reports/ew-seed-only-v2-formal-backtest-hs300-only-2013-2025/ew_seed_only_v2_formal_backtest.zh.md`
- 缺失分数审计：
  `reports/ew-seed-only-v2-formal-backtest-hs300-only-2013-2025/missing_score_enter_events_audit.zh.md`
