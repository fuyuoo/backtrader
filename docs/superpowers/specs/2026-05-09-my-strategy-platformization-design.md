# `my_strategy` 策略研究平台化改造设计

**日期**：2026-05-09  
**状态**：设计草案，待评审  
**范围**：只改造 `my_strategy/`，不修改原版 `backtrader/` 内核  

---

## 1. 背景

当前项目是在原版 `backtrader` 大项目之上，新增了自己的研究目录：

```text
my_strategy/
```

实际策略研发、数据下载、指标计算、回测、归因、报告输出主要都在 `my_strategy/` 内完成。原版 `backtrader/` 应视为底层交易模拟框架，后续原则上不改动。

当前核心策略文件是：

```text
my_strategy/src/strategy.py
```

这个文件现在承担了太多职责：

- 策略入场条件
- 策略出场条件
- 止盈、止损、加仓逻辑
- 仓位计算
- 涨跌停过滤
- 订单状态处理
- `trade_list.csv` / `trade_summary.csv` 所需的中间记录
- `signals_log.csv` 所需的信号记录
- 部分归因字段的原始数据准备

因此代码复杂度越来越高。后续如果继续把新策略、新因子、新统计逻辑都堆进 `strategy.py`，系统会越来越难维护，也很难变成通用回测系统。

本设计的目标是：在不破坏当前策略行为的前提下，逐步把 `my_strategy/` 改造成一个可复用的策略研究平台。

---

## 2. 总目标

最终系统应支持：

```text
输入：
  1. 策略规则代码
  2. 参数范围
  3. 股票池定义
  4. 回测区间
  5. 标签/归因维度配置

系统自动完成：
  1. 生成历史可用股票池
  2. 加载数据与指标
  3. 执行回测
  4. 记录交易、信号、持仓曲线
  5. 生成大盘/行业/个股标签
  6. 生成多维归因报告
  7. 批量参数实验
  8. 样本外验证

输出：
  1. 策略是否有效
  2. 适合什么大盘环境
  3. 适合什么行业环境
  4. 适合什么个股特征
  5. 什么阶段应该加仓/减仓/停用
  6. 推荐参数区间
```

重点不是单纯找最高收益参数，而是诊断策略的适用性。

---

## 3. 非目标

本次平台化设计不包含：

- 不修改原版 `backtrader/` 框架代码。
- 不接入实盘交易。
- 不做 UI Dashboard。
- 不立即引入复杂机器学习模型。
- 不一开始就重构全部代码。
- 不在第一阶段改变现有策略收益结果。

第一目标是把系统边界、数据流、目录结构和抽象层次理顺。

---

## 4. 架构边界

### 4.1 原版 `backtrader/`

定位：底层回测执行引擎。

职责：

- 数据 feed 推进
- broker 模拟
- commission/slippage 支持
- order/trade 生命周期
- analyzer 基础能力

原则：

- 尽量不改。
- 作为第三方库使用。
- 自定义逻辑放到 `my_strategy/`。

### 4.2 `my_strategy/`

定位：自己的策略研究平台。

职责：

- 股票池管理
- 数据下载
- 指标计算
- 策略规则
- 回测编排
- 交易记录
- 标签生成
- 归因分析
- 参数实验
- 自动调参

后续所有新增能力都优先放在这里。

---

## 5. 当前主要问题

### 5.1 `strategy.py` 没有平台化

当前 `strategy.py` 是一个深度定制策略，不是通用策略接口。

问题：

- 新策略接入成本高。
- 归因字段与交易逻辑耦合。
- 仓位逻辑与信号逻辑耦合。
- 止盈止损逻辑难以独立测试。
- 不容易做多策略对比。

后续方向：

```text
strategy.py
  只保留 backtrader 适配逻辑

strategy_rules/
  放买入、卖出、加仓、止盈止损规则

recorders/
  放订单、交易、信号记录

position_sizing/
  放仓位计算

attribution/
  放归因字段定义与报告
```

### 5.2 回测运行隔离不完整

当前已有 `--tag` 可以隔离部分输出：

```text
results/<tag>/
reports/<tag>/
```

但仍存在风险：

- `signals_log.csv` 默认写到全局 `data/signals_log.csv`。
- 并行回测时，不同参数组可能覆盖同一份信号日志。
- 缺少每次运行的参数快照。
- 缺少每次运行使用的股票池快照。

后续需要：

```text
runs/<run_id>/
  config.json
  run_manifest.json
  universe_snapshot.csv
  results/
    trade_list.csv
    trade_summary.csv
    signals_log.csv
    skipped_signals.csv
    equity_curve.png
  reports/
    *.csv
```

### 5.3 股票池存在历史偏差风险

沪深300、中证500、中证1000都会定期调整成分股。

如果用当前成分股回测历史区间，会产生幸存者偏差。例如，用 2026 年的沪深300成分股回测 2019 年，等于提前知道哪些股票未来还留在指数里。

需要建设历史股票池映射。

### 5.4 标签体系还不够完整

当前已经有部分标签：

- 沪深300 DIF 是否大于 0
- 沪深300 是否多头排列
- 个股是否多头排列
- 行业是否多头排列
- 周线/月线 MACD 区间
- MA60 距离

但这些还只是散落在 `trade_summary.csv` 上的字段，没有形成独立的标签引擎。

后续应该把大盘、行业、个股标签独立生成，再由回测结果按入场日 join。

---

## 6. 历史股票池设计

### 6.1 目标

让系统在任意回测日期都能回答：

```text
这一天，某个指数真实包含哪些股票？
```

例如：

```text
2019-03-01 的沪深300成分股
2021-06-30 的中证500成分股
2023-12-01 的中证1000成分股
```

### 6.2 建议文件

```text
my_strategy/data/universe/index_membership_history.csv
```

字段：

```text
index_code
ts_code
effective_start_date
effective_end_date
weight
source_date
```

含义：

| 字段 | 含义 |
|---|---|
| `index_code` | 指数代码，如 `000300.SH` |
| `ts_code` | 成分股代码 |
| `effective_start_date` | 成分生效开始日期 |
| `effective_end_date` | 成分生效结束日期，仍在成分内则为空 |
| `weight` | 权重，可选 |
| `source_date` | 原始数据发布日期或快照日期 |

### 6.3 使用逻辑

回测某一天 `date` 时，股票池取：

```text
effective_start_date <= date
and (effective_end_date is null or date < effective_end_date)
```

再叠加：

```text
已上市
未退市
有行情数据
非停牌
满足流动性要求
```

### 6.4 Universe Resolver

建议新增模块：

```text
my_strategy/src/universe.py
```

职责：

- 根据配置生成回测股票池。
- 支持指数历史成分股。
- 支持固定 CSV 股票池。
- 支持全 A 股票池。
- 支持行业股票池。
- 输出本次运行的 `universe_snapshot.csv`。

配置示例：

```json
{
  "universe": {
    "type": "index_history",
    "index_code": "000300.SH",
    "start_date": "20190101",
    "end_date": "20240101"
  }
}
```

---

## 7. 标签体系设计

标签不应该只服务当前策略，而应该服务所有策略。

建议生成三类基础标签表：

```text
my_strategy/data/regime/market_regime.csv
my_strategy/data/regime/sector_regime.csv
my_strategy/data/regime/stock_regime.csv
```

回测后再根据 `entry_date + ts_code + sector_code` join 到 `trade_summary.csv`。

### 7.1 大盘标签

用于回答：当前市场环境适不适合做多？

| 标签 | 含义 |
|---|---|
| `market_trend_regime` | 牛市 / 震荡 / 熊市 / 反弹 / 退潮 |
| `market_above_ma25` | 指数是否站上 MA25 |
| `market_above_ma60` | 指数是否站上 MA60 |
| `market_above_ma120` | 指数是否站上 MA120 |
| `market_ma_bull_align` | 是否均线多头排列 |
| `market_macd_zone` | 日线 MACD 区间 |
| `market_week_macd_zone` | 周线 MACD 区间 |
| `market_month_macd_zone` | 月线 MACD 区间 |
| `market_return_20d` | 20 日涨跌幅 |
| `market_return_60d` | 60 日涨跌幅 |
| `market_drawdown_60d` | 近 60 日最大回撤 |
| `market_volatility_20d` | 近 20 日波动率 |
| `market_volume_ratio_20d` | 当前成交额 / 20 日均成交额 |
| `market_breadth_ma60` | 全市场站上 MA60 的股票比例 |
| `market_limit_up_count` | 当日涨停数量 |
| `market_limit_down_count` | 当日跌停数量 |

### 7.2 行业标签

用于回答：策略适合什么行业阶段？

| 标签 | 含义 |
|---|---|
| `sector_trend_regime` | 行业趋势状态 |
| `sector_above_ma25` | 行业指数是否站上 MA25 |
| `sector_above_ma60` | 行业指数是否站上 MA60 |
| `sector_ma_bull_align` | 行业是否均线多头排列 |
| `sector_macd_zone` | 行业日线 MACD 区间 |
| `sector_week_macd_zone` | 行业周线 MACD 区间 |
| `sector_month_macd_zone` | 行业月线 MACD 区间 |
| `sector_return_20d` | 行业 20 日涨跌幅 |
| `sector_return_60d` | 行业 60 日涨跌幅 |
| `sector_excess_return_20d` | 行业相对大盘 20 日超额收益 |
| `sector_excess_return_60d` | 行业相对大盘 60 日超额收益 |
| `sector_rank_momentum_60d` | 行业 60 日动量排名 |
| `sector_strength_percentile` | 行业强度分位数 |
| `sector_volume_ratio_20d` | 行业成交额放大倍数 |
| `sector_drawdown_60d` | 行业近 60 日最大回撤 |
| `sector_rotation_stage` | 启动 / 加速 / 过热 / 回落 / 弱势 |

### 7.3 个股标签

用于回答：策略适合什么类型的股票？

| 标签 | 含义 |
|---|---|
| `stock_trend_regime` | 趋势股 / 震荡股 / 破位股 / 超跌反弹 |
| `stock_above_ma25` | 个股是否站上 MA25 |
| `stock_above_ma60` | 个股是否站上 MA60 |
| `stock_ma_bull_align` | 个股是否均线多头排列 |
| `stock_ma60_dist_pct` | 收盘价距离 MA60 百分比 |
| `stock_ma60_dist_bucket` | MA60 距离分桶 |
| `stock_macd_zone` | 个股日线 MACD 区间 |
| `stock_week_macd_zone` | 个股周线 MACD 区间 |
| `stock_month_macd_zone` | 个股月线 MACD 区间 |
| `stock_kdj_j` | KDJ J 值 |
| `stock_return_20d` | 个股 20 日涨跌幅 |
| `stock_return_60d` | 个股 60 日涨跌幅 |
| `stock_excess_vs_market_60d` | 个股相对大盘 60 日超额收益 |
| `stock_excess_vs_sector_60d` | 个股相对行业 60 日超额收益 |
| `stock_atr_pct` | ATR / close |
| `stock_volatility_20d` | 20 日波动率 |
| `stock_drawdown_60d` | 近 60 日最大回撤 |
| `stock_near_120d_high` | 是否接近 120 日新高 |
| `stock_circ_mv_bucket` | 流通市值分桶 |
| `stock_liquidity_bucket` | 成交额/流动性分桶 |
| `stock_limit_up_recent_20d` | 近 20 日涨停次数 |

### 7.4 三层共振标签

用于回答：大盘、行业、个股是否共振？

| 标签 | 含义 |
|---|---|
| `market_sector_stock_align` | 大盘、行业、个股是否同向多头 |
| `sector_leads_market` | 行业是否强于大盘 |
| `stock_leads_sector` | 个股是否强于行业 |
| `triple_strength_score` | 大盘 + 行业 + 个股综合强度 |
| `strong_phase_type` | 大盘强 / 行业强 / 个股强 / 三层共振 |
| `risk_phase_type` | 大盘弱 / 行业弱 / 个股弱 / 全部退潮 |

初版 `triple_strength_score` 可以简单设计为 0-100 分：

```text
大盘趋势：30 分
行业强度：30 分
个股强度：30 分
流动性/波动率：10 分
```

后续归因重点观察：

```text
triple_strength_score > 70 的交易是否显著更好？
大盘弱但行业强时，策略是否还能赚钱？
行业弱但个股强时，是假强还是机会？
三层共振时是否应该提高仓位？
```

### 7.5 交易过程标签

用于优化止盈、止损、加仓。

| 标签 | 含义 |
|---|---|
| `entry_signal_set` | 入场触发了哪些条件 |
| `entry_strength_score` | 入场强度分 |
| `entry_pullback_depth` | 入场回踩幅度 |
| `entry_ma60_dist_pct` | 入场距离 MA60 |
| `max_favorable_excursion` | 最大浮盈 |
| `max_adverse_excursion` | 最大浮亏 |
| `mfe_day` | 最大浮盈出现在第几天 |
| `exit_efficiency` | 实际收益 / 最大浮盈 |
| `profit_giveback_pct` | 从最大浮盈回吐比例 |
| `take_profit_hit_count` | 止盈触发次数 |
| `stop_loss_triggered` | 是否止损 |
| `exit_reason` | 出场原因 |
| `holding_days` | 持仓天数 |

这些标签直接服务以下问题：

- 盈利多少开始止盈最好？
- 强趋势里是否止盈太早？
- MA60 止损是否太慢？
- 加仓是否发生在错误阶段？
- 出现大阳线后禁止加仓是否有效？

---

## 8. `strategy.py` 抽象方向

### 8.1 现阶段原则

第一阶段不改变策略行为，只做搬迁和分层。

目标：

```text
同样输入数据 + 同样参数
重构前后交易结果一致
```

### 8.2 建议模块拆分

未来目录结构：

```text
my_strategy/src/
  strategy.py                  # backtrader adapter，保留 MyStrategy
  rules/
    base.py                    # 策略规则接口
    ma60_pullback.py           # 当前策略规则
  execution/
    broker_rules.py            # 涨跌停、成交限制、T+1 等
    position_sizer.py          # 仓位计算
  recorders/
    order_recorder.py          # order_log
    trade_recorder.py          # trade_log
    signal_recorder.py         # signals_log
  regime/
    market_labels.py
    sector_labels.py
    stock_labels.py
    join_trade_labels.py
  universe.py
```

### 8.3 策略规则接口草案

后续希望策略规则像这样：

```python
class StrategyRule:
    name = "ma60_pullback"

    def build_indicators(self, data):
        pass

    def should_buy(self, ctx):
        pass

    def should_sell(self, ctx, position):
        pass

    def should_add(self, ctx, position):
        pass

    def position_size(self, ctx, portfolio):
        pass
```

其中 `ctx` 应该包含：

```text
date
ts_code
open/high/low/close
indicators
market_labels
sector_labels
stock_labels
current_position
portfolio_state
```

这样以后新增策略时，不需要复制整份 `MyStrategy`。

---

## 9. 运行目录设计

### 9.1 当前问题

目前输出分散在：

```text
data/signals_log.csv
results/
reports/
results/<tag>/
reports/<tag>/
```

并行运行时容易互相覆盖。

### 9.2 目标结构

建议最终统一为：

```text
my_strategy/runs/
  20260509_153000_v3_ma_bull/
    config.json
    run_manifest.json
    universe_snapshot.csv
    results/
      trade_list.csv
      trade_summary.csv
      signals_log.csv
      skipped_signals.csv
      daily_position_pnl.csv
      daily_portfolio_snapshot.csv
      equity_curve.png
    reports/
      *.csv
```

### 9.3 `run_manifest.json`

每次运行必须保存：

```json
{
  "run_id": "20260509_153000_v3_ma_bull",
  "created_at": "2026-05-09T15:30:00+08:00",
  "strategy_name": "ma60_pullback",
  "backtest_start": "20190101",
  "backtest_end": "20240101",
  "universe": {
    "type": "index_history",
    "index_code": "000300.SH"
  },
  "params": {
    "min_ma60_dist_pct": 0.05,
    "max_add_count": 0,
    "require_stock_ma_bull": true
  },
  "paths": {
    "results_dir": "runs/.../results",
    "reports_dir": "runs/.../reports"
  }
}
```

这样后续任何一份报告都能追溯来源。

---

## 10. 分阶段开发计划

### Phase 1：运行隔离

目标：让每次回测输出完全独立。

任务：

- 增加 `--workdir` 或统一 `runs/<run_id>` 输出。
- `signals_log.csv` 移入本次 `results/`。
- `reports/` 从本次 `results/` 读取信号与交易。
- 保存 `run_manifest.json`。
- 保存 `universe_snapshot.csv`。

成功标准：

- 并行跑多组参数不会互相覆盖。
- 任意一个 run 目录可以独立复盘。

### Phase 2：历史股票池

目标：避免指数成分股幸存者偏差。

任务：

- 新增 `data/universe/index_membership_history.csv`。
- 新增 `src/universe.py`。
- 支持按日期获取沪深300、中证500、中证1000历史成分股。
- 回测时根据日期动态过滤可交易股票。

成功标准：

- 2019 年回测只使用 2019 当时真实指数成分。
- 股票池快照可导出和审计。

### Phase 3：标签引擎

目标：把大盘、行业、个股标签独立出来。

任务：

- 新增 `data/regime/market_regime.csv`。
- 新增 `data/regime/sector_regime.csv`。
- 新增 `data/regime/stock_regime.csv`。
- 回测后把入场日标签 join 到 `trade_summary.csv`。
- 归因报告按标签自动分组统计。

成功标准：

- 任意策略都能复用同一套标签。
- 不需要在 `strategy.py` 里临时计算归因标签。

### Phase 4：拆分 `strategy.py`

目标：把当前策略从巨型类拆成多个模块。

任务：

- 抽出买入规则。
- 抽出卖出规则。
- 抽出加仓规则。
- 抽出仓位计算。
- 抽出订单/交易/信号记录。
- 保留 `MyStrategy` 作为 backtrader adapter。

成功标准：

- 重构前后同参数回测结果一致。
- 新增策略不需要复制整份 `strategy.py`。

### Phase 5：参数实验系统

目标：自动运行多组参数并生成对比表。

任务：

- 支持参数网格配置。
- 自动生成多个 run。
- 自动汇总核心指标。
- 输出 `comparison.csv`。
- 按年度、市场标签、行业标签、个股标签对比。

成功标准：

- 可以一键比较多组参数。
- 能看出参数是否只在某一年或某类环境有效。

### Phase 6：自动优化与样本外验证

目标：从“跑参数”升级为“验证参数稳定性”。

任务：

- 样本内训练。
- 样本外验证。
- walk-forward。
- 参数稳定性分析。
- 输出推荐参数区间。

成功标准：

- 输出不只是单一最优参数，而是：
  - 推荐区间
  - 适用环境
  - 风险环境
  - 样本外表现

---

## 11. 优先级建议

建议顺序：

```text
1. 运行隔离
2. 历史股票池
3. 标签引擎
4. strategy.py 拆分
5. 参数实验
6. 自动优化
```

原因：

- 没有运行隔离，并行回测和参数搜索容易污染结果。
- 没有历史股票池，回测结果可能带幸存者偏差。
- 没有标签引擎，就无法准确回答“适合什么大盘、行业、个股”。
- `strategy.py` 拆分要在核心数据流稳定后做，避免一边改架构一边追报告 bug。

---

## 12. 最小可行版本

第一版平台化不需要一次做完。

最小可行版本只需完成：

```text
1. run 目录隔离
2. signals_log 跟随 run 输出
3. run_manifest.json
4. 历史指数成分股表结构
5. market/sector/stock 标签表结构
6. trade_summary 自动 join 标签
```

完成后，系统就能更可靠地回答：

```text
这个策略在哪些环境下强？
哪些环境下亏？
哪些行业更适合？
哪些个股特征更适合？
参数是不是只在某几年有效？
```

---

## 13. 待确认问题

后续实现前需要确认：

1. 历史指数成分股数据源是否全部使用 Tushare。
2. 初版股票池优先支持哪些指数：沪深300、中证500、中证1000，还是再加创业板/科创50。
3. 标签表是否按天全量预计算，还是回测后按需计算。
4. `strategy.py` 拆分时是否要求每一步都保持交易结果完全一致。
5. 参数实验第一阶段使用网格搜索，还是人工指定多组配置。

---

## 14. 结论

当前系统已经具备比较强的单策略回测和归因能力，但它还不是通用平台。

下一阶段最重要的不是继续增加零散报告，而是建设四个底座：

```text
运行隔离
历史股票池
标签引擎
策略抽象
```

这四个底座完成后，后续的参数优化、样本外验证、多策略扩展才会变得稳定、可信、可复用。
