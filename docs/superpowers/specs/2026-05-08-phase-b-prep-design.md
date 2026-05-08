# Phase B-prep — 统计基础与数据可信度建设设计文档

**日期**：2026-05-08
**作者**：Claude Opus 4.7（与 fuyuoo 协作 brainstorm）
**状态**：design approved，pending plan
**前置依赖**：Phase A 已完成（commit `019c479`，`master` 已 push 到 origin）

---

## 1. 目标

让现有 42 张报告 + 2 个中间数据**真实、完整、可信**地反映策略的实际表现，让用户在做调参前对策略本身有信心。

**核心问题**：当前回测报告漂亮（Sharpe 0.32、payoff_ratio 2.15），但能不能直接基于这些数字调参？答案是：**不能**。原因：

- 数据存在 A 股特有偏差（涨跌停成交、停牌期信号、universe 时间不一致）
- 报告本身有 bug（`cost_breakdown.csv` overall 行空列）
- 信号体系混入了不可信的财务因子
- 缺关键解释维度：失败归因、出场效率、信号 IC 排名、滚动绩效

**目标产出**：8 个核心交付物 + 1 个前置准备步骤（共 9 项），分 3 层（数据层 / 策略层 / 报告层）。

---

## 2. 非目标（Non-goals）

明确不在本次范围内：

- ❌ Train/Val 切分框架（Phase B）
- ❌ Walk-forward 调参基础设施（Phase B）
- ❌ 参数扫描骨架 / Optuna 集成（Phase B）
- ❌ 滑点模型升级（缓做：调参出候选后再做 sensitivity）
- ❌ 容量分析 / Kelly / VaR / 风险预算（Phase C，实盘前再做）
- ❌ 财务因子相关任何处理（用户确认不用：1 无法验证真伪、2 实盘没精力跟、3 消息利空利好不好判断）
- ❌ 重做 PIT 财务数据下载（同上）

---

## 3. 决策记录（Why & Trade-offs）

### 3.1 为什么先做基础建设而不是直接进 Phase B 调参

用户表态：未来可能小额实盘。在被污染的数据上做 walk-forward 与单切一样会过拟合 —— 有效的 Phase B 必须站在干净数据 + 可信报告上。

### 3.2 为什么不重做 PIT 财务部分（澄清：仍需补 stock_basic 的 list_date / delist_date）

用户决定**只走技术面信号**：DIF/MACD/KDJ/MA/动量/距离/regime flag 等只用 close[t-N:t] 计算，本身不带 lookback 风险。财务因子（PE/ROE/净利润同比）从信号体系彻底移除即可，**不必重做财务（fina_indicator / daily_basic）部分的下载**。

**澄清**：但 `stock_basic`（含 `list_date` / `delist_date`）是**结构性元数据**，不属于"财务因子"范畴；PIT universe 集成（§5.3）需要它。如果当前 `stock_list.csv` 不含这两列，本期工作必须先重下 `pro.stock_basic` 一次。这部分代价小（一次 API 调用），与"重做财务下载"不在同一量级。

### 3.3 为什么数据完整性自检独立成模块、不集成进每次回测

用户洞察：数据健康检验属于"数据层"，频率低（数据更新后跑一次即可），不应每次回测都跑。位置：`download_all.py` → `calc_indicators.py` → **`data_integrity_check.py`**。

### 3.4 为什么涨跌停过滤放在策略层而不是数据层

涨跌停是"当天信号触发但实际买不到 / 卖不掉"的策略行为修正，应在 strategy 下单逻辑里处理。数据层只提供 `pct_chg` 字段，策略层做判断。

### 3.5 为什么把 trade_summary 增列而不是新建报告

`mfe_minus_realized` / `exit_efficiency` / `benchmark_return_during_holding` / `per_trade_alpha` 是**每笔交易的属性**，应在 trade_summary 上原地增列。下游所有 attribution 报告自动按 exit_reason / sector / regime 切片这 4 列，无需重复造表。

### 3.6 为什么不升级滑点模型

当前 `set_slippage_perc(0.0001)` flat 1bps 偏低（A 股小盘实际可能 3-5bps + 市场冲击）。但**调参出候选前升级没意义** —— 真正应该做的是：等 Phase B 选出几组候选参数，再用多滑点假设（1/3/5/8bps）做 sensitivity 一次跑；现在升级会让本次基线报告与历史不可比。

---

## 4. 架构

### 4.1 总体分层

```
┌─────────────────────────────────────────┐
│ 数据层 (Data Layer)                      │
│  download_all.py                         │
│    ↓                                     │
│  calc_indicators.py                      │
│    ↓                                     │
│  data_integrity_check.py  ← 新增（一次性）│
│    输出 results/integrity_report.csv     │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ 策略层 (Strategy Layer)                  │
│  src/strategy.py  (修改：涨跌停过滤)     │
│  backtest.py      (修改：PIT universe)   │
│    ↓                                     │
│  cerebro 主循环 + 持仓管理               │
│    ↓                                     │
│  results/trade_list.csv                  │
│  results/trade_summary.csv  ← 增 4 列    │
│  results/daily_position_pnl.csv          │
│  results/daily_portfolio_snapshot.csv    │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ 报告层 (Report Layer)                    │
│  attribution_runner.run()                │
│  ├── 旧 attribution.run()                │
│  ├── trade_attribution_extra.run()       │
│  ├── portfolio_attribution.run()         │
│  ├── position_curve_attribution.run()    │
│  └── 新增：                              │
│      ├── signal_importance_ranking.csv   │
│      ├── rolling_metrics.csv             │
│      └── loss_attribution.csv            │
│  另外修复：                              │
│      └── cost_breakdown.csv overall bug  │
└─────────────────────────────────────────┘
```

### 4.2 8 个交付物（按层次分组）

| 层 | # | 模块 / 修改 | 类型 |
|---|---|---|---|
| 数据 | 0 | 补 stock_list.csv 的 list_date / delist_date 列（如缺） | 一次性脚本 |
| 数据 | 1 | `tools/data_integrity_check.py` | 新建模块 |
| 策略 | 2 | `src/strategy.py` 涨跌停过滤 | 修改 |
| 策略 | 3 | `backtest.py` PIT universe 集成 | 修改 |
| 清理 | 4 | 财务因子移除 + cost_breakdown bug 修 | 修改 + 移除 |
| 数据 | 5 | `trade_summary.csv` 增 4 列 | 修改写入逻辑 |
| 报告 | 6 | `signal_importance_ranking.csv` + 全量 IC | 新建报告 |
| 报告 | 7 | `rolling_metrics.csv` | 新建报告 |
| 报告 | 8 | `loss_attribution.csv` | 新建报告 |

---

## 5. 各交付物详细设计

### 5.1 模块 1：`tools/data_integrity_check.py`

**职责**：扫描 `data/daily/*.csv` 和 `stock_list.csv`，输出问题清单。不修复数据本身。

**入口函数**：
```python
def run(project_root: Path, cfg: dict) -> None:
    """扫描数据健康；输出 results/integrity_report.csv。"""
```

**输出文件**：`results/integrity_report.csv`

**检查项**：

| issue_type | severity | 检测逻辑 |
|---|---|---|
| `missing_trading_day` | warning | 与 benchmark `000300.SH` 的交易日历对比，找出缺日的 ts_code+date |
| `duplicate_date` | error | 同一 ts_code 同一日期出现多行 |
| `non_monotonic_date` | error | date 列不是单调递增 |
| `abnormal_close_jump` | warning | 单日 close 变化超过 ±25%（前复权下不应该出现，提示数据质量问题） |
| `qfq_break` | warning | 单日 close = 0 或 NaN |
| `suspended_period` | info | 连续 5 天以上 OHLCV 全相同（可疑停牌） |
| `delisted_after_last_bar` | info | 该 ts_code 最后一个 bar 距今超过 90 天，可能已退市 |
| `not_in_stock_list` | warning | daily/ 下有 csv 但 stock_list.csv 不含此 ts_code |
| `in_list_no_data` | warning | stock_list.csv 含此 ts_code 但 daily/ 下无文件 |
| `list_date_mismatch` | warning | stock_list.csv 的 list_date 早于 daily 第一个 bar 的 date |

**输出列**：
```
ts_code, issue_type, severity, date_or_range, detail
```

**示例行**：
```
000001.SZ, missing_trading_day, warning, 2020-04-08, "benchmark 当日交易，本股缺数据"
000002.SZ, suspended_period, info, "2019-05-15~2019-06-12", "21 个 bar OHLCV 全相同"
```

**实现要点**：
- 使用 `000300.SH` 的交易日历作为基准（`data/daily/000300.SH.csv` 已存在）
- 不需要 stock_list.csv 必须有 list_date 列；如果没有，跳过相关检查并在 detail 里说明
- 严格抛错策略：检测逻辑本身的异常（如文件读取失败）必须 raise，不能静默
- 性能：800 只股票 × 25 年 daily ≈ 50 万行；用 pandas 批处理，目标 < 1 分钟

**触发方式**：手动运行 `python -m my_strategy.tools.data_integrity_check`，或通过新建一个 CLI wrapper。**不集成进 backtest.py 主循环**。

**测试**：
- 构造合成数据（缺日 / 重复日期 / 异常 close / 停牌期），断言相应 issue_type 被捕获
- 不需要 e2e 集成测试

---

### 5.2 修改 2：策略层涨跌停过滤（`src/strategy.py`）

**问题**：A 股每日涨跌停 ±10%；当前 backtest 在涨停日 fire 买入信号会"虚假成交"。

**修改位置**：`MyStrategy.next()` 的下单决策段。

**逻辑**：
```python
def _is_limit_up(self, data) -> bool:
    """当日 close 已涨停（≥ +9.9%）。"""
    if len(data) < 1:
        return False
    pct_chg = (data.close[0] - data.close[-1]) / data.close[-1] * 100
    return pct_chg >= 9.9


def _is_limit_down(self, data) -> bool:
    """当日 close 已跌停（≤ -9.9%）。"""
    if len(data) < 1:
        return False
    pct_chg = (data.close[0] - data.close[-1]) / data.close[-1] * 100
    return pct_chg <= -9.9
```

**应用规则**：
- **开仓 / 加仓**：当天 `_is_limit_up()` 返回 True 时，**跳过**且记录到 `signals_log.csv` 的 skip_reason 列（值 = `"limit_up"`）
- **止损 / 止盈 / 清仓**：当天 `_is_limit_down()` 返回 True 时，**当日不卖**（顺延到下一个非跌停日）

**注意事项**：
- 涨跌停判断使用前一日 close 计算，与 Tushare `pct_chg` 字段一致
- ST / *ST 股涨跌幅是 ±5%，本期暂不区分（用户的 stock_list.csv 可能已剔除 ST）；后续可加 `cfg.st_limit_pct` 配置
- 北交所涨跌幅 ±30%，同上后续可处理
- 修改影响：`signals_log.csv` 增 skip_reason 类别 `"limit_up"` / `"limit_down"`；trade_list.csv 没有变化（被过滤的信号本就不入交易）

**测试**：单元测试构造连续 3 天的 close 序列（[10, 11, 11.05]，第二天涨停），断言策略不开仓。

---

### 5.3 修改 3：PIT universe 集成（`backtest.py`）

**问题**：`stock_list.csv` 是当前快照，2010 年回测时该列表含 2018 年才上市的股票（look-ahead）。

**修改位置**：`backtest.py` 数据加载段。

**前提条件**：`stock_list.csv` 必须含 `list_date` 列（YYYYMMDD 字符串）。如果当前没有，本次工作的第一步是从 Tushare `pro.stock_basic` 重下一份完整含 `list_date / delist_date` 的版本。

**逻辑**：
```python
# 数据加载循环里加：
if 'list_date' in stock_list.columns:
    list_date = pd.to_datetime(row['list_date'], format='%Y%m%d')
    if list_date > pd.to_datetime(cfg['start_date'], format='%Y%m%d'):
        # 该股票在 backtest 起始日期之后才上市；用其上市日做该股的有效起始
        bt_start = max(list_date, pd.to_datetime(cfg['start_date'], format='%Y%m%d'))
    else:
        bt_start = pd.to_datetime(cfg['start_date'], format='%Y%m%d')
    # delist_date 同理设置 bt_end
```

**关键设计：在数据 feed 层过滤 vs 在策略 next() 里过滤**

选 **数据 feed 层过滤**（更彻底）：每只股票只把"已上市未退市"的 bar 加进 cerebro。理由：
- 策略 next() 里检查会让代码繁琐
- 数据 feed 切片符合直觉
- 已退市的股票后续 bar 就是 NaN / 缺失，cerebro 默认就停止该股的循环

**反直觉点**：已退市股票的早期 bar 仍然要算（当时是可投资的）。回测的"hindsight"问题不在退市股本身，而在"现在已知它会退市，所以不买"。我们要避免的是"用了未来的 list_date 信息"，所以只在 list_date < trade_date 的条件下才把该股加入 universe。

**测试**：构造 mini-fixture（2 只股票，一只 list_date=2010-01-01，一只 list_date=2015-06-01），backtest 从 2012 开始，断言只有第一只股票从 2012 开始有交易，第二只从 2015-06-01 开始。

---

### 5.4 修改 4：清理类（财务因子移除 + cost_breakdown bug 修）

**子任务 4.1：财务因子移除**

涉及文件：
- [my_strategy/tools/attribution_runner.py](my_strategy/tools/attribution_runner.py)：从 `DEFAULT_SIGNALS_WHITELIST` 删除`factor_pe_ttm` `factor_roe` `factor_netprofit_yoy`（如有；目前白名单已不含，但要确认）
- [my_strategy/tools/attribution.py](my_strategy/tools/attribution.py)：`factor_alpha.csv` 生成逻辑里只保留 `factor_momentum_60d` / `factor_ma60_dist` / `factor_macd_strength` 这 3 列；不再尝试 PE/ROE/netprofit_yoy
- [my_strategy/src/calc_indicators.py](my_strategy/src/calc_indicators.py)：检查是否仍在生成 PE/ROE/netprofit_yoy 列；若是，从输出列表删除（这一步可保守地保留生成但下游不消费）
- 各报告：`bottom_trades.csv` / `top_trades.csv` / `trade_profile.csv` 等含 `factor_pe_ttm` / `factor_roe` / `factor_netprofit_yoy` 列的，移除这些列
- 测试：相关测试断言里如有这几个 factor 列，移除

**实施保守原则**：财务数据源代码不删（保留下载逻辑），只在**消费侧**移除。下载产物可继续生成，避免影响其他可能的消费者。

**子任务 4.2：cost_breakdown bug 修**

当前 [reports/cost_breakdown.csv](my_strategy/reports/cost_breakdown.csv) overall 行：
```
overall,all,20314,,1076063.53,1792081.34,,,0.0008
```
`gross_pnl` / `net_pnl` / `cost_pct_of_gross` 三列空。原因：trade_list.csv 没有 `gross_pnl` 列，`_cost_block` 里 `if 'gross_pnl' in sub.columns` 条件不满足。

**修复方案**：
- `position_curve_attribution.run()` 在调 `compute_cost_breakdown` 前，把 `trade_summary.csv` 的 `gross_pnl` 列按 episode 拼到 trade_list（每个 episode 一个 gross_pnl 值，或按 sell 行分摊；最简单是只对 sell 行 attach gross_pnl，buy 行留 0）
- 或者：把 `compute_cost_breakdown` 的输入从 `trade_list` 改为 `trade_summary`（trade_summary 已经有 gross_pnl，且每个 episode 一行更合适做"per-trade cost"）

选 **后者**：改输入源，更简洁。但 trade_summary 没有 `price` / `size` 列，需要从 trade_list 把 turnover 反推后 join 到 trade_summary。具体改造在 plan 阶段细化。

**测试**：跑一次 e2e，断言 `reports/cost_breakdown.csv` overall 行 4 个值都不为空，且 `gross_pnl ≈ trade_summary.gross_pnl.sum()`。

---

### 5.5 修改 5：trade_summary 增 4 列

**修改位置**：`my_strategy/backtest.py` 的 `_enrich_trade_summary` 函数。

**新增列**：

| 列名 | 计算 | 说明 |
|---|---|---|
| `mfe_minus_realized` | `mfe_pct - return_pct` | "桌上留下的钱"，正值表示出场没拿到峰值 |
| `exit_efficiency` | `return_pct / mfe_pct` 当 `mfe_pct > 0` 时；否则 NaN | 实际兑现比例（0-1）；负 mfe 不算 |
| `benchmark_return_during_holding` | `(close[exit] - close[entry]) / close[entry]`，使用 HS300（000300.SH） | 同期基准累计收益（百分比） |
| `per_trade_alpha` | `return_pct - benchmark_return_during_holding` | 单笔 alpha |

**实现要点**：
- `benchmark_return_during_holding` 需要加载 `data/daily/000300.SH.csv`；若 entry_date 在 HS300 数据范围外，记录为 NaN
- 4 列都允许 NaN（出场未发生 / mfe ≤ 0 / 数据缺失）
- 严格不抛错降级：HS300 文件不存在 → 整个 4 列计算可降级为只填前两列；但要 print 一行警告
- 实际上 HS300 文件已经在 cfg.benchmark_codes 里加载了，复用即可

**下游影响**：
- 旧 [attribution.py](my_strategy/tools/attribution.py) 的所有按维度切片报告会自动包含这 4 列（如果它们 select 了 trade_summary 全列）—— 需要 review 一下哪些报告需要"也展示新列的均值"
- 至少 `trade_profile.csv`、各 regime 报告应当展示 `avg_per_trade_alpha`、`avg_exit_efficiency`，作为旧 `avg_return_pct` 的补充
- 不需要新建报告；现有切片报告自动受益

**测试**：构造 2 笔交易（一笔 mfe=10, return=5；一笔 mfe=3, return=-2），断言计算正确；HS300 文件缺失时不抛错且前两列正常。

---

### 5.6 报告 6：`signal_importance_ranking.csv` + 全量 IC

**职责**：把分散在各 entry_*_stats / signal_stability / factor_alpha / significance_summary 的信息合并成一张排名表。

**位置**：扩展 `tools/trade_attribution_extra.py`，新增 `compute_signal_importance_ranking()` 函数；在 `run()` 里写出 `signal_importance_ranking.csv`。

**输入**：trade_summary（含已扩展的 4 新列）+ signals_whitelist（来自 cfg 或默认）

**输出列**：
```
signal_name             - 信号字段名
signal_type             - bool / numeric / categorical
n                       - 该信号有效样本数
mean_return_when_true   - 信号为真时的平均收益（bool/cat：取该桶；numeric：上 quintile 均值）
mean_return_when_false  - 同上反向
effect_size             - mean_when_true - mean_when_false
t_stat                  - 两侧均值差的 t-stat（Welch）
p_value                 - 双尾 p
ic_mean_5d              - 与 forward_return_5d 的 spearman 相关均值
ic_mean_20d             - 同上 20d
ic_mean_60d             - 同上 60d
ic_ir_60d               - ic_mean_60d / ic_std_60d（按月分桶）
stability_yearly_mean   - signal_stability.csv 里该信号每年 avg_return 的均值
stability_yearly_std    - 同上 std
rank_by_effect_size     - 综合排名（按 effect_size 降序）
rank_by_ic              - 按 |ic_mean_60d| 降序
rank_combined           - 综合排名（effect_size 和 IC 各 50%）
```

**全量 IC 实现**：
- 对每个数值信号（如 `entry_kdj_j`、`entry_ma60_dist_pct`、`entry_circ_mv`、`entry_sector_momentum_60d`、`entry_week_kdj_j`）和每个 forward window：
  1. 按入场月份分组（`entry_date.dt.to_period('M')`）
  2. 每个月内算一次 spearman(signal, forward_return)，得到一组月度 IC
  3. `ic_mean_<window>` = 月度 IC 序列的均值
  4. `ic_std_<window>` = 月度 IC 序列的标准差
  5. `ic_ir_<window>` = `ic_mean_<window> / ic_std_<window>`（std=0 时填 NaN）
- 对 bool 信号，IC 退化为 point-biserial 相关，按同样的月度分组聚合
- 对 categorical 信号（macd_zone, ma_alignment），不算 IC，IC 列填 NaN

**前置改动**：
- forward_return_5d / 20d / 60d 列需要扩到全量 trade_summary，不只 top/bottom_trades。这是已有数据流的扩展（[bottom_trades.csv](my_strategy/reports/bottom_trades.csv) 已经包含这几列，说明数据可得）
- 实现：在 `_enrich_trade_summary` 里，对每个 trade 用其 ts_code + entry_date 查同期 +5/+20/+60 个交易日的 close，算 forward_return；缺数据填 NaN

**测试**：构造合成数据（信号全 true 时 return 高、全 false 时 return 低），断言 ranking 第一名是该信号；IC 计算针对单调相关数据应接近 ±1。

---

### 5.7 报告 7：`rolling_metrics.csv`

**职责**：滚动 252 交易日窗口的关键指标，识别策略衰减 / regime 切换。

**位置**：扩展 `tools/portfolio_attribution.py`，新增 `compute_rolling_metrics()` 函数。

**输入**：daily 收益序列（来自 `_TimeReturn`）+ daily_portfolio_snapshot（用于 n_positions）+ HS300 收益（用于 alpha）

**输出列**：
```
window_end_date         - 窗口最后一日
window_size_days        - 252 (默认；可配置)
n_trading_days          - 该窗口实际交易日数（边缘窗口可能 < 252）
sharpe                  - 窗口内 Sharpe（年化）
sortino                 - 窗口内 Sortino
win_rate_daily          - 窗口内 daily 收益 > 0 的占比
n_trades_in_window      - 窗口内开仓笔数（来自 trade_summary 的 entry_date）
avg_n_positions         - 窗口内日均持仓数
alpha_vs_hs300          - 窗口内年化 alpha
max_dd_in_window        - 窗口内最大回撤
```

**实现要点**：
- 用 `pandas.Series.rolling(window=252).apply(...)` 对每个指标分别计算
- 起始 251 天数据不足，可输出 NaN 或截断（截断更直观）
- 输出 dataframe 索引从第 252 个交易日开始

**测试**：构造一段持续上升的 daily_ret（如全 +0.001），断言滚动 Sharpe > 0 且趋于稳定；构造前半上升后半下降，断言 max_dd 出现在后半窗口。

---

### 5.8 报告 8：`loss_attribution.csv`

**职责**：识别"亏损交易里哪些信号最常一起 fire"，区别于"信号 overall mean return"。

**位置**：扩展 `tools/trade_attribution_extra.py`，新增 `compute_loss_attribution()` 函数。

**输入**：trade_summary（要求含 entry_* 信号列 + return_pct）+ signals_whitelist

**逻辑**：
- 全样本：`P(signal=value)`（信号 value 在全样本里的频率）
- 亏损子集（return_pct < 0）：`P(signal=value | loss)`
- 重亏损子集（return_pct < -5%）：`P(signal=value | heavy_loss)`
- Lift = `P(signal=value | loss) / P(signal=value)`，> 1 说明该 signal_value 在亏损中更常见
- chi2 p_value：用 chi-square test 检验"该 signal 与亏损是否独立"

**输出列**：
```
signal_name             - 信号字段名
signal_value            - bool: True/False；categorical: 各唯一值；numeric: Q1-Q5 分位
freq_in_universe        - 全样本里该 signal_value 的频率
freq_in_losses          - 亏损交易里的频率
freq_in_heavy_losses    - 重亏损（< -5%）的频率
lift_loss               - freq_in_losses / freq_in_universe
lift_heavy_loss         - freq_in_heavy_losses / freq_in_universe
chi2_stat               - chi-square 统计量
p_value                 - 双尾 p
n_universe              - 全样本数
n_losses                - 亏损样本数
n_heavy_losses          - 重亏损样本数
```

**实现要点**：
- 数值信号用 5 分位；bool / categorical 直接枚举 unique values
- chi-square 要求 expected freq ≥ 5；不满足时填 NaN 并 set warning flag 列
- 严格不静默降级：低样本量必须显式标记

**测试**：构造合成数据（某 bool 信号 = False 时 return 全负），断言 lift_loss 接近 2.0、p_value < 0.001。

---

## 6. 实施顺序与依赖关系

```
第零波（前置准备，单步小任务）
└── 0. 重下 stock_basic 补 list_date/delist_date 列（如缺）

第一波（独立、可并行）
├── 1. data_integrity_check (新模块)
└── 4. 清理类（财务因子移除 + cost_breakdown bug）

第二波（依赖第零波，可并行）
├── 2. 涨跌停过滤（独立修改 strategy.py）
└── 3. PIT universe（依赖 stock_list.csv 含 list_date）

第三波（依赖第一+二波 + 数据干净）
└── 5. trade_summary 增 4 列

第四波（依赖第三波，三者可并行）
├── 6. signal_importance_ranking + 全量 IC
├── 7. rolling_metrics
└── 8. loss_attribution
```

**第零波说明**：先用 `pro.stock_basic(list_status='L,D,P')` 拉取一次包含 list_date / delist_date 的完整列表，与现有 `stock_list.csv` join 或替换。若已含这两列则跳过本步。预计代码量极小（<50 行），不单独成模块，作为 utility 脚本。

**关键节点**：第三波之前需要跑一次完整 e2e backtest，确保 0+1+2+3+4 改动都生效后回测仍 green。**第三波后再跑一次 e2e**，验证新增的 4 列写入正确。第四波结束再跑一次 e2e，最终验收。

---

## 7. 测试策略

每个交付物都遵循 TDD：测试先写、确认 fail、再写实现、再 pass、再 e2e 回归。

**单元测试**（新增）：
- `tests/test_data_integrity_check.py` — 各 issue_type 的合成数据检测
- `tests/test_strategy_limit_filter.py` — 涨跌停过滤逻辑（mock data feed）
- `tests/test_pit_universe.py` — list_date 过滤
- `tests/test_signal_importance_ranking.py` — ranking + IC 计算
- `tests/test_rolling_metrics.py` — 滚动指标
- `tests/test_loss_attribution.py` — 频率 lift + chi2

**集成测试**（修改）：
- `test_attribution_runner.py` — fixture 增加 forward_return 列、HS300 daily 数据；断言 3 张新报告产出

**E2E 验收**：每完成一波 commit 前跑 `python backtest.py`，确认 14 + 3 = 17 张 Phase 报告齐全 + cost_breakdown overall 行 4 列都不空。

---

## 8. 已知风险与缓解

| 风险 | 缓解 |
|---|---|
| `stock_list.csv` 当前可能不含 `list_date` 列 | Phase B-prep 第一步重下；本期把这步纳入 plan |
| PIT universe 改造后回测时间显著拉长 | 实测：当前 6 分 8 秒；按目前 800 只股票，预期不会显著增加 |
| 涨跌停过滤后历史回测结果发生变化 | 这是预期行为；需用户接受"修复后的基线 ≠ 修复前的基线" |
| `trade_summary` 增 4 列后旧测试断言列集合可能挂 | 用 `set ⊇ {...}` 而非 `set == {...}`，已是大多数测试的写法 |
| 全量 IC 计算成本（每个数值信号 × 每月 spearman） | 一个 trade_summary 约 6000 行，几个数值信号 × 60 个月 × spearman ≈ 几秒，可接受 |

---

## 9. 验收标准

完成本次 Phase B-prep 后，应满足：

1. ✅ `python -m my_strategy.tools.data_integrity_check` 跑出 `integrity_report.csv`，无 `error` 级问题（或所有 error 都被用户标记为可接受）
2. ✅ 跑一次 `python backtest.py` 6 分钟内完成；`reports/` 下产出 14 + 3 = 17 张 Phase 报告
3. ✅ `cost_breakdown.csv` overall 行 `gross_pnl` / `net_pnl` / `cost_pct_of_gross` 三列均非空
4. ✅ `trade_summary.csv` 新增 4 列（`mfe_minus_realized` / `exit_efficiency` / `benchmark_return_during_holding` / `per_trade_alpha`），且 4 列在不同 status / exit_reason 下值合理
5. ✅ `signal_importance_ranking.csv` 给出每个白名单信号的综合排名，至少含 `entry_hs300_dif_above_zero` / `entry_stock_bull_align` / `ma_alignment` / `entry_sector_momentum_60d` 等
6. ✅ `rolling_metrics.csv` 给出从 2010 年（含足 252 交易日后）起的逐日滚动指标
7. ✅ `loss_attribution.csv` 给出每个信号的 freq_lift_loss + chi2 p_value
8. ✅ 全量测试通过（pytest -q），数量从 148 提升到约 165-175（新增 ~20 个测试）
9. ✅ 所有报告中**完全没有** `factor_pe_ttm` / `factor_roe` / `factor_netprofit_yoy` 出现
10. ✅ A 股操作过滤生效：`signals_log.csv` 中应含 skip_reason = `"limit_up"` 的若干条记录

---

## 10. 后续衔接（Phase B 入口）

Phase B-prep 完成后，下一阶段（Phase B）入口：

1. 用 `signal_importance_ranking.csv` 选定要调的核心信号 / 参数（用户判断："哪些信号 IC 高且稳定"）
2. 基于 `rolling_metrics.csv` 决定 train/val 切分点（避开 regime 拐点）
3. 基于 `loss_attribution.csv` 决定哪些信号该作为"过滤器"（exclude bucket）而非"开仓条件"
4. 基于 `trade_summary` 新增的 `exit_efficiency` 决定优先调出场逻辑（MA60 止损是已知瓶颈）
5. 然后才搭 train/val 框架 + 参数扫描骨架

Phase B 设计文档将在本期完成后另写。

---

## 附录 A：术语对齐

- **PIT (Point-In-Time)**：所有数据只能反映"当时可见"的信息；不带后视
- **lookback / look-ahead**：未来信息泄露
- **IC (Information Coefficient)**：信号与未来收益的相关系数（一般用 spearman）
- **IC IR**：IC 的均值 / 标准差，衡量 IC 稳定性
- **alpha**：策略相对基准的超额收益
- **walk-forward**：滚动 train/val 切分，每折独立训练独立验证
- **lift**：条件概率与无条件概率的比值
