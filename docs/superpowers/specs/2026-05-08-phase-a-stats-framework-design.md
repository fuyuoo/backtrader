# Phase A 统计分析框架设计

**日期**：2026-05-08
**作者**：Claude + 用户
**目标**：在进入 Phase B（自动训练/验证集切分 + 自动调参）之前，把当前 28 张归因报告的统计能力补齐，覆盖三大盲区：风险调整收益、统计显著性、组合层指标。

---

## 1. 背景与现状

### 1.1 现有 28 张报告盘点

按维度分类：
- **时间**：`yearly_stats`, `monthly_stats`
- **交易分级**：`trade_profile`（4 桶），`top_trades`/`bottom_trades`（前后 10）
- **出场/生命周期**：`exit_reason_stats`, `mfe_distribution`, `mfe_mae_by_exit`
- **加仓/仓位**：`add_count_stats`, `add_block_stats`, `first_buy_size_stats`, `dea_lookback_stats`
- **入场单因子**：`entry_condition_stats`（kdj_j、ma60_dist_pct、week_macd_zone、month_macd_zone、week_kdj_j、ma_alignment、macd_zone）
- **大盘 regime**：`hs300_dif_stats`, `hs300_bull_align_stats`
- **个股 regime**：`stock_bull_align_stats`, `stock_above_ma25_stats`
- **行业 regime（Phase 2 已上线）**：`sector_bull_align/above_ma25/dif/week_macd/month_macd/momentum_60d/industry/winrate` 共 8 张
- **组合**：`regime_combo_stats`（大盘×个股 2×2），`sector_stock_combo_stats`（行业×个股 2×2）
- **因子 α**：`factor_alpha`（IC/IR）

### 1.2 已识别盲区

1. **风险调整收益完全缺失**：所有报告只看 win_rate 和 avg_return，无 Sharpe / Sortino / 最大回撤 / Calmar
2. **盈亏对称性 / 期望值缺失**：无 payoff ratio / profit factor / expectancy
3. **统计显著性缺失**：n=78 的 bucket 和 n=2832 的 bucket 在报告中地位等同，进入 Phase B 必拟合到噪声
4. **时间稳定性未量化**：年度报告只看汇总，无关键信号按年的稳定性 / 衰减检测
5. **持仓期收益曲线未拆解**：MFE/MAE 仅记录极值，无逐日累积收益曲线
6. **回撤序列与连亏未分析**
7. **多因子交互仅做 2×2，无 3 因子交叉**
8. **组合层指标未量化**：最大同时持仓、行业集中度
9. **成本影响未拆解**：佣金/印花税占比未知
10. **基准超额未按时段拆解**：仅有日级 IC，无年/月级 α/β/IR

### 1.3 用户决策

- 选择 **方案 C**：三档全做
- 显著性走 **方案 B**：独立 `significance_summary.csv`，不动现有 28 张报告 schema
- 报告主要由 AI 消费，宽表 / 长表 / 列多均可，不追求人眼可读
- 数据补齐走 **方案 A**：post-hoc 后处理重建 daily_position_pnl，不改 backtest.py
- 文件格式统一保持 **CSV**（不引入 parquet）
- 代码组织走 **方案 A**：按数据源拆 6 个模块

---

## 2. 范围

**包含**：13 项新统计成果（产出 14 个 CSV 文件，因 §3.2.4 同一模块输出 `losing_streak_stats.csv` + `drawdown_periods.csv` 两个文件）、2 个新中间数据文件（daily_position_pnl, daily_portfolio_snapshot）、6 个新代码模块、`backtest.py` 入口调整 1 处。

**不包含（Phase B 处理）**：
- 训练/验证集自动切分
- 滚动窗口前向验证
- 参数自动调参（Optuna / 网格搜索）
- 信号过滤器回灌策略代码

---

## 3. 新增报告清单（共 13 张）

### 3.1 一档：风险调整、期望值、显著性（3 张）

#### 3.1.1 `portfolio_risk_metrics.csv`

组合层风险调整收益（按 overall / yearly / monthly 三粒度）

| 列 | 类型 | 说明 |
|---|---|---|
| period_type | str | overall / yearly / monthly |
| period_label | str | "2019-2023" / "2019" / "2019-02" |
| sharpe | float | 年化夏普（无风险利率默认 0） |
| sortino | float | 年化索提诺（仅惩罚下行波动） |
| calmar | float | 年化收益 / 最大回撤 |
| max_drawdown | float | 最大回撤百分比（负值） |
| max_dd_duration_days | int | 最大回撤区间持续天数 |
| annualized_return | float | 年化收益率 |
| annualized_vol | float | 年化波动率 |
| downside_vol | float | 年化下行波动率 |

**数据源**：`_TimeReturn` analyzer（`backtest.py:833`）的日收益序列。

#### 3.1.2 `payoff_metrics.csv`

盈亏对称性 / 期望值，按多维度分组

| 列 | 类型 | 说明 |
|---|---|---|
| dimension | str | overall / exit_reason / year / sector / regime |
| bucket | str | 维度内具体桶名 |
| n | int | 笔数 |
| win_rate | float | 胜率 |
| avg_win | float | 盈利交易平均收益（%） |
| avg_loss | float | 亏损交易平均收益（%，负值） |
| payoff_ratio | float | avg_win / abs(avg_loss) |
| profit_factor | float | sum_win / abs(sum_loss) |
| expectancy | float | 每笔交易期望收益 = win_rate × avg_win + (1-win_rate) × avg_loss |
| max_win | float | 最大单笔盈利 |
| max_loss | float | 最大单笔亏损 |

**数据源**：`results/trade_summary.csv`。

#### 3.1.3 `significance_summary.csv`

把现有 + 新增的 bucket 报告全部拍平到长表 + 加显著性判定

| 列 | 类型 | 说明 |
|---|---|---|
| report_name | str | 来源报告名（如 `entry_condition_stats`） |
| bucket_field | str | 分组字段名（如 `entry_kdj_j`） |
| bucket_value | str | 桶值 |
| n | int | 样本量 |
| mean_return | float | 平均收益 |
| std_return | float | 标准差 |
| std_err | float | 标准误 = std / √n |
| ci_low_95 | float | 95% 置信区间下界 |
| ci_high_95 | float | 95% 置信区间上界 |
| t_stat_vs_zero | float | 该桶均值是否显著非零的 t 统计量 |
| p_value_vs_zero | float | 对应 p 值 |
| t_stat_vs_overall | float | 该桶均值 vs 全样本均值的 Welch t 统计量 |
| p_value_vs_overall | float | 对应 p 值 |
| low_sample_warning | bool | n < 100 |
| significant_flag | bool | (n ≥ 100) AND (p_value_vs_overall < 0.05) |

**数据源**：从 `trade_summary.csv` 重新分组聚合（**不**复用现有 CSV，避免精度损失和列对齐问题）。

**覆盖的 bucket 报告**（约 25 类）：所有 entry_condition 子分组、yearly、monthly、exit_reason、add_count、add_block、first_buy_size、dea_lookback、所有 sector_*、stock_*、hs300_*、regime_combo、新增的 multi_factor_combo 等。

### 3.2 二档：时间稳定性、持仓期、回撤、多因子（5 张）

#### 3.2.1 `signal_stability.csv`

关键信号按年稳定性

| 列 | 类型 | 说明 |
|---|---|---|
| signal_name | str | 信号名 + 取值（如 `sector_dif_above_zero=True`） |
| period_year | int | 年份 |
| n | int | 该年该信号出现笔数 |
| win_rate | float | |
| avg_return | float | |
| t_stat_vs_zero | float | |
| p_value | float | |
| rank_within_signal | int | 该信号在所有年份中按 avg_return 的排名 |

**追踪信号清单**（13 个，固定白名单）：

布尔类（直接 True/False）：
1. `hs300_dif_above_zero`
2. `hs300_bull_align`
3. `stock_bull_align`
4. `stock_above_ma25`
5. `sector_dif_above_zero`
6. `sector_above_ma25`
7. `sector_bull_align`

分类类（取每个值）：
8. `sector_week_macd_zone`（区间 0/1/2/3）
9. `sector_month_macd_zone`（区间 0/1/2/3）
10. `entry_month_macd_zone`（区间 0/1/2/3）
11. `entry_week_macd_zone`（区间 0/1/2/3）
12. `ma_alignment`（全多头/局部多头/混合/局部空头/全空头）

数值类（按全样本 5 分位 Q1-Q5 切桶）：
13. `factor_momentum_60d`、`factor_ma60_dist`（每个一行 signal_name 形如 `factor_momentum_60d=Q1`）

**数据源**：`trade_summary.csv` 按 `entry_date` 取年份分组。

#### 3.2.2 `holding_period_curve.csv`

持仓期累积收益曲线

| 列 | 类型 | 说明 |
|---|---|---|
| holding_day_n | int | 持仓第 N 天（0 = 入场日） |
| n_active_trades | int | 持仓到第 N 天仍未平仓的交易数 |
| avg_cum_return | float | 平均累积收益 |
| median_cum_return | float | 中位数累积收益 |
| win_rate_at_day_n | float | 第 N 天为正的占比 |
| p25_cum_return | float | 25 分位 |
| p75_cum_return | float | 75 分位 |
| avg_drawdown_from_peak | float | 距持仓期内峰值的平均回撤 |

**采样点**：1, 2, 3, 5, 7, 10, 15, 20, 25, 30, 40, 50, 60, 75, 90 天。

**数据源**：`results/daily_position_pnl.csv`（新中间产物，见 §4）。

#### 3.2.3 `mfe_timing.csv`

MFE 出现时点分布

| 列 | 类型 | 说明 |
|---|---|---|
| mfe_timing_bucket | str | "早期(前 1/3)" / "中期(中 1/3)" / "晚期(后 1/3)" |
| n | int | |
| win_rate | float | |
| avg_return | float | |
| avg_holding_days | float | |
| avg_mfe_pct | float | |

**数据源**：`daily_position_pnl.csv`，逐笔交易找 cum_return_pct 的 argmax 位置 / 总持仓天数。

#### 3.2.4 `losing_streak_stats.csv` + `drawdown_periods.csv`（同模块输出 2 个文件）

**`losing_streak_stats.csv`**（汇总指标，单行多列或长表）

| 列 | 类型 | 说明 |
|---|---|---|
| metric | str | longest_losing_streak / longest_winning_streak / avg_losing_streak_length / pct_losing_streaks_ge_5 |
| value | float | |

**`drawdown_periods.csv`**（前 10 大回撤）

| 列 | 类型 | 说明 |
|---|---|---|
| rank | int | 1-10 |
| start_date | date | 峰值日期 |
| trough_date | date | 谷底日期 |
| recovery_date | date | 恢复到峰值的日期（NaT 表示未恢复） |
| peak_value | float | |
| trough_value | float | |
| drawdown_pct | float | |
| duration_days | int | start → trough |
| recovery_days | int | trough → recovery |

**数据源**：`_TimeReturn` 日收益累积成 equity 序列。

#### 3.2.5 `signal_correlation_matrix.csv`

信号冗余度（长表）

| 列 | 类型 | 说明 |
|---|---|---|
| signal_a | str | |
| signal_b | str | |
| pearson_r | float | |
| spearman_r | float | |
| n | int | |

覆盖所有 boolean / numeric 信号字段两两组合。

**数据源**：`trade_summary.csv` 的入场快照字段。

#### 3.2.6 `multi_factor_combo_stats.csv`

3 因子交叉

| 列 | 类型 | 说明 |
|---|---|---|
| signal_a_name | str | |
| signal_a_value | str | |
| signal_b_name | str | |
| signal_b_value | str | |
| signal_c_name | str | |
| signal_c_value | str | |
| n | int | |
| win_rate | float | |
| avg_return | float | |
| t_stat_vs_overall | float | |
| p_value_vs_overall | float | |
| low_sample_warning | bool | |

**默认 3 因子组合**（先做这 3 套）：
1. `hs300_dif_above_zero × sector_dif_above_zero × stock_bull_align`
2. `sector_above_ma25 × stock_above_ma25 × entry_month_macd_zone`
3. `hs300_bull_align × sector_bull_align × stock_bull_align`

**数据源**：`trade_summary.csv`。

### 3.3 三档：组合层、成本、时段 α（4 张）

#### 3.3.1 `concurrent_positions_stats.csv`

同时持仓数分布（长表）

| 列 | 类型 | 说明 |
|---|---|---|
| metric_type | str | summary / position_count_bucket |
| bucket | str | 对 summary：max/avg/median/p95/pct_at_cap/pct_below_50；对 bucket：0/1-25/26-50/... |
| value | float | |
| days_at_level | int | 仅 bucket 类型 |
| pct_of_time | float | 仅 bucket 类型 |

**数据源**：`r.position_count_log`（已存在，`backtest.py:828`）

#### 3.3.2 `sector_concentration_stats.csv`

行业集中度（汇总 + Top-N 最集中日期）

| 列 | 类型 | 说明 |
|---|---|---|
| metric_type | str | summary / top_concentrated_day |
| label | str | summary 类：avg_max_sector_share/p95/max/avg_herfindahl/p95_herfindahl；top 类：日期 |
| value | float | |
| top_sector_code | str | 仅 top 类 |
| top_sector_share | float | 仅 top 类 |
| herfindahl_index | float | 仅 top 类 |
| n_positions | int | 仅 top 类 |

**数据源**：`results/daily_portfolio_snapshot.csv`（新中间产物）

#### 3.3.3 `cost_breakdown.csv`

交易成本影响（按年 + 按 exit_reason）

| 列 | 类型 | 说明 |
|---|---|---|
| dimension | str | overall / year / exit_reason |
| bucket | str | |
| n_trades | int | |
| gross_pnl | float | 元 |
| total_commission | float | 元 |
| total_stamp_duty | float | 元 |
| net_pnl | float | 元 |
| cost_pct_of_gross | float | abs(commission+stamp_duty) / abs(gross_pnl) |
| cost_pct_of_turnover | float | abs(commission+stamp_duty) / turnover |

**数据源**：优先 `trade_list.csv`（如有 commission 字段）；否则从 `trade_summary` × `commission_rate=0.0003` × `stamp_duty=0.001` 反推。

**实施前确认点**：检查 `trade_list.csv` 是否记录了 commission 字段。

#### 3.3.4 `period_alpha.csv`

按时段策略 α / β / 信息比率

| 列 | 类型 | 说明 |
|---|---|---|
| period_type | str | overall / yearly / monthly |
| period_label | str | |
| benchmark_code | str | 000300.SH / 000905.SH / 000001.SH |
| strategy_return | float | 该时段累积收益 |
| benchmark_return | float | |
| alpha | float | 年化超额收益 |
| beta | float | |
| info_ratio | float | (策略-基准) / tracking_error |
| tracking_error | float | |
| n_trading_days | int | |

**数据源**：`_TimeReturn` 日收益 + `data/index/{code}_daily.csv`。

---

## 4. 新增中间数据文件（2 个）

### 4.1 `results/daily_position_pnl.csv`

每笔交易的逐日持仓快照（长表）

| 列 | 类型 | 说明 |
|---|---|---|
| trade_id | int | trade_summary 行索引 |
| ts_code | str | |
| entry_date | date | |
| holding_day_n | int | 0 起 |
| date | date | 实际交易日 |
| close | float | |
| cum_return_pct | float | (close - avg_cost) / avg_cost × 100 |
| drawdown_from_peak_pct | float | 距**该笔交易持仓期内**累积收益峰值的回撤（非组合层峰值） |
| sector_code | str | SW Level-1 行业代码 |

**预估规模**：约 5911 笔 × 平均 33 天 ≈ 20 万行，CSV ~30MB。

### 4.2 `results/daily_portfolio_snapshot.csv`

每个交易日的组合快照

| 列 | 类型 | 说明 |
|---|---|---|
| date | date | |
| n_positions | int | |
| sectors_held | int | 不重复行业数 |
| top_sector_code | str | 持仓数最多的行业代码 |
| top_sector_share | float | top_sector 的持仓数占比 |
| herfindahl_index | float | Σ(s_i^2) where s_i = 行业 i 的持仓占比 |

**预估规模**：约 1200 个交易日，文件极小。

---

## 5. 模块组织（6 个新文件）

### 5.1 文件结构

```
my_strategy/tools/
├── attribution.py                   ← 不动（保留现有 9 张 trade-level 报告生成函数）
├── stats_helpers.py                 ← 新（纯统计工具）
├── trade_attribution_extra.py       ← 新（5 张 trade-level 新报告）
├── portfolio_attribution.py         ← 新（5 张 equity-curve / position_count 报告）
├── position_curve_attribution.py    ← 新（4 张 daily_position_pnl 报告）
├── rebuild_position_history.py      ← 新（数据补齐：post-hoc 重建 daily_position_pnl）
└── attribution_runner.py            ← 新（顶层编排）
```

### 5.2 各模块职责

#### `stats_helpers.py`（~120 行）

纯统计工具函数：
- `confidence_interval(series, alpha=0.05) -> (low, high)`
- `t_test_one_sample(series, mu=0) -> (t_stat, p_value)`
- `t_test_welch(series_a, series_b) -> (t_stat, p_value)`
- `bucket_stats_with_significance(series_grouped, overall_series) -> DataFrame`

#### `trade_attribution_extra.py`（~450 行）

输入：`trade_summary.csv`
输出：
- `payoff_metrics.csv`
- `signal_stability.csv`
- `signal_correlation_matrix.csv`
- `multi_factor_combo_stats.csv`
- `significance_summary.csv`

公开接口：`def run(trades: pd.DataFrame, out_dir: Path) -> None`

#### `portfolio_attribution.py`（~400 行）

输入：`_TimeReturn` 日收益、`position_count_log`、benchmark 日数据
输出：
- `portfolio_risk_metrics.csv`
- `losing_streak_stats.csv`
- `drawdown_periods.csv`
- `concurrent_positions_stats.csv`
- `period_alpha.csv`

公开接口：`def run(time_return: pd.Series, position_count_log, cfg: dict, out_dir: Path) -> None`

#### `position_curve_attribution.py`（~350 行）

输入：`daily_position_pnl.csv`、`daily_portfolio_snapshot.csv`、`trade_list.csv`
输出：
- `holding_period_curve.csv`
- `mfe_timing.csv`
- `sector_concentration_stats.csv`
- `cost_breakdown.csv`

公开接口：`def run(project_root: Path, cfg: dict) -> None`

#### `rebuild_position_history.py`（~250 行）

输入：`trade_summary.csv` + `data/{ts_code}_daily.csv` + `data/stock_sector.csv`
输出：`daily_position_pnl.csv`、`daily_portfolio_snapshot.csv`

公开接口：`def build(project_root: Path, cfg: dict) -> None`

#### `attribution_runner.py`（~120 行）

顶层编排，依次调用 5 个生成模块。
公开接口：`def run(project_root: Path, cfg: dict, time_return: pd.Series, position_count_log) -> None`

### 5.3 调用链

```
backtest.py:978
  └─ attribution_runner.run(project_root, cfg, time_return, position_count_log)
     ├─ rebuild_position_history.build(project_root, cfg)
     ├─ attribution.run(project_root, cfg)                     ← 旧 9 张（不动）
     ├─ trade_attribution_extra.run(trades, out_dir)
     ├─ portfolio_attribution.run(time_return, position_count_log, cfg, out_dir)
     └─ position_curve_attribution.run(project_root, cfg)
```

### 5.4 backtest.py 改动

**仅 1 处**：`backtest.py:975-978` 区域
- 旧：`from tools import attribution; attribution.run(project_root, cfg)`
- 新：`from tools import attribution_runner; attribution_runner.run(project_root, cfg, time_return, position_count_log)`
- 配套：把现有 `time_return = pd.Series(r.analyzers._TimeReturn.get_analysis())` 计算位置上移到调用之前

---

## 6. 错误处理策略

按 `CLAUDE.md` 要求严格执行：
- 缺数据文件 → 抛 `FileNotFoundError` 并指明缺哪个
- benchmark 数据缺失 → 抛错而不是降级（这一点和 `backtest.py:849` 现有 "数据文件不存在" 的提示有冲突，需要确认是否保留旧行为；本设计倾向于 `period_alpha.csv` 缺基准时**抛错**而非跳过）
- 样本量为 0 的 bucket → 不输出该行（不写 NaN，避免 AI 误读）
- `daily_position_pnl.csv` 重建过程中某 ts_code 日线缺失 → 抛错，不静默跳过该笔交易

---

## 7. 开放问题 / 实施前确认点

1. **`trade_list.csv` 是否记录 commission/stamp_duty 字段** —— 实施 §3.3.3 前需要先扫一下；如果没有，要么从 backtrader broker 配置反推（精度足够），要么往 broker 注入记录器。
2. **`r.position_count_log` 的具体 schema** —— 看 backtest.py:828 是 `getattr(r, 'position_count_log', None)`，需要确认该字段的数据结构（list of dict？DataFrame？）。
3. **`signal_correlation_matrix` 的"信号"如何枚举** —— 自动从 trade_summary 中识别 boolean/numeric 列，还是写死一份白名单？建议白名单避免噪声列。
4. **股票分红/送股调整** —— `daily_position_pnl` 用的 close 价是否需要复权？建议用前复权（与现有 `daily_price.csv` 一致），但需确认 `data/{ts_code}_daily.csv` 的复权状态。

---

## 8. 不在本设计范围内（Phase B）

- 训练/验证集自动切分逻辑
- 滚动窗口前向验证
- Optuna / 网格搜索调参
- 把归因发现回灌策略代码

---

## 9. 后续步骤

1. 用户 review 本设计
2. 调用 `superpowers:writing-plans` 生成实施计划
3. 实施计划应至少包含 7 个独立任务（5 个生成模块 + 1 个数据重建模块 + 1 个 runner + backtest.py 接入）
4. 实施完成后运行回测，验证 13 张新报告 + 2 个中间文件均产出
5. 更新 `docs/FEATURES.md` 和 `docs/CHANGELOG.md`
