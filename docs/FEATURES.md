# 功能总览（FEATURES）

> 范围：本仓库 `my_strategy/` 目录下的 A 股量化回测流水线。
> 仓库内 `backtrader/`（框架源码）与 `learn_backtrader/`（教程）不在本文档范围内。
> 维护规则见 `CLAUDE.md` 的「文档维护规则」章节。

## 1. 项目目标

基于 backtrader 框架，构建一套面向 A 股的端到端量化回测流水线：
**数据下载 → 因子/指标计算 → 策略回测 → 归因分析 → 交易合规验证**。

## 2. 目录结构

```
my_strategy/
├── config.json / config.example.json   # 全局配置
├── stock_list.csv / a_stock_list.txt   # 股票池
├── download_all.py                      # 数据下载主入口（拉指数成分股 + 调用 downloader）
├── backtest.py                          # 回测主入口
├── src/
│   ├── downloader.py                   # 日线/周线/月线下载（pro_bar 前复权）
│   ├── downloader_extra.py             # daily_basic / fina_indicator / 申万行业指数
│   ├── calc_indicators.py              # MA/MACD/KDJ + 多周期合并 + 因子合成
│   └── strategy.py                     # MyStrategy + StockData feed + 佣金模型
├── tools/
│   ├── attribution.py                  # 多角度归因报告（旧）
│   ├── verify_trades.py                # 逐 episode 信号合规校验
│   ├── stats_helpers.py                # 统计工具（置信区间、t 检验、分桶统计）
│   ├── rebuild_position_history.py     # 重建逐日持仓 PnL + 组合快照
│   ├── trade_attribution_extra.py      # 扩展归因报告（7 张：payoff/signal_stability/.../signal_importance_ranking/loss_attribution）
│   ├── portfolio_attribution.py        # 组合层归因（6 张：sharpe/sortino/drawdown_periods/.../rolling_metrics）
│   ├── position_curve_attribution.py   # 持仓曲线归因（4 张：holding_curve/mfe_timing/...）
│   ├── attribution_runner.py           # Phase A 顶层编排（统一驱动 14 张报告 + 2 个中间文件）
│   └── data_integrity_check.py        # 数据健康自检（一次性，输出 integrity_report.csv）
├── data/                               # 下载产物
│   ├── daily/                          # 日线
│   ├── weekly/, monthly/               # 周线、月线
│   ├── daily_basic/                    # 估值/市值/换手率
│   ├── fina/                           # 财务指标
│   ├── sw_index/                       # 申万行业指数
│   ├── stock_sector.csv                # 股票↔行业映射
│   ├── indicators/                     # calc_indicators 产物（已合并所有因子）
│   └── signals_log.csv                 # 策略每次买入信号快照
├── results/                            # 回测产物（trade_list、equity 曲线等）
├── reports/                            # 归因分析输出
├── logs/                               # 下载错误日志
└── tests/                              # pytest 单元测试
```

## 3. 数据下载（download_all.py + src/downloader*.py）

**职责**：从 Tushare 拉取所有需要的数据并按股票切分到本地 CSV。

> 注：横截面分位排名功能（`pct_*` 因子）目前未启用，相关脚本已移除，待后续开发。

- **入口**：`python my_strategy/download_all.py`
- **股票池**：根据 `config.json.index_codes`（默认 沪深300 + 中证500）调用
  `pro.index_weight` 取最近一次成分股快照，写入 `a_stock_list.txt`，再串联调用下游下载器。
- **基础行情**（`src/downloader.py`）：
  - `pro.pro_bar` 前复权日线，按 10 年切片避免 6000 行限制；
  - 周线 / 月线同步下载；
  - `_call_with_timeout` 单笔超时保护，超时不阻塞后续；
  - 错误进入 `logs/download_errors.log`，不静默吞错。
- **辅助数据**（`src/downloader_extra.py`）：
  - `daily_basic`：`pe_ttm, pb, total_mv, circ_mv, turnover_rate`
  - `fina_indicator`：`roe, netprofit_yoy, ann_date, end_date` 等（保留 ann_date 以做 PIT 对齐）
  - 申万一级行业指数：按 `config.sw_index_codes` 全量拉取
  - 已存在文件默认跳过（`force=True` 强制覆盖）
- **关键配置**：`tushare_token`、`start_date/end_date`、`index_codes`、`sw_index_codes`、
  `data_paths.*`、`api_rate_per_min`。

## 4. 指标 / 因子计算（src/calc_indicators.py）

**职责**：把多份原始 CSV 合并成"每只股票一张完整指标表"，输出到 `data/indicators/`。

### 4.1 原子计算函数（可独立调用）

| 函数 | 产出列 |
|------|--------|
| `add_ma(df)` | ma25 / ma60 / ma144 / ma180；同时把 circ_mv 万元→亿元 |
| `add_macd(df)` | dif / dea / macd |
| `add_kdj(df)` | kdj_j；high==low 时分母置 NaN 避免假信号 |
| `add_week_macd_zone(df, path)` | week_kdj_j / week_macd_zone（文件不存在填 None） |
| `add_month_macd_zone(df, path)` | month_macd_zone（文件不存在填 None） |
| `add_factor_momentum_60d(df)` | factor_momentum_60d |
| `add_factor_ma60_dist(df)` | factor_ma60_dist |
| `add_factor_macd_strength(df)` | factor_macd_strength（= dea） |

### 4.2 参数化主入口

```python
compute_indicators(code, src_dirs, dst_dir, groups, ...)
```

- `groups` 为字符串列表，支持：`'ma'`、`'macd'`、`'kdj'`、`'week_macd'`、`'month_macd'`、
  `'fundamentals'`、`'sector_momentum'`、`'factor_momentum_60d'`、`'factor_ma60_dist'`、`'factor_macd_strength'`；
- 只计算 groups 中声明的项，输出 CSV 仅含对应列，方便按场景裁剪（如行业指数无需基本面）；
- `src_dirs` 必须含 `'daily'` 键，可选 `'weekly'` / `'monthly'`；
- 文件不存在时抛 `FileNotFoundError`，不静默跳过。

### 4.3 CLI

```bash
python my_strategy/src/calc_indicators.py --mode stock   # 股票模式
python my_strategy/src/calc_indicators.py --mode sector  # 行业指数模式
```

`config.json` 新增 `indicator_profiles.{stock,sector}`，分别定义两种模式的 groups 列表。

### 4.4 其他公开函数（向后兼容）

- `compute_all_indicators(df)`：原 `compute_indicators(df)` 的全量计算别名（ma+macd+kdj）；
- `compute_weekly_monthly_indicators(ts_code, df, data_dir)`：仍保留，供 backtest.py 调用；
- `merge_fundamentals(daily_df, daily_basic_df, fina_df)`：按 ann_date PIT 对齐合并财务数据；
- `merge_daily_basic_fina(daily_df, code, daily_basic_dir, fina_dir)`：路径型包装器；
- `add_single_stock_factors(df)`：一次性添加 3 个单股因子（向后兼容旧调用）；
- `merge_sector_momentum(daily_df, sector_index_df)`：行业指数 60 日动量 merge。

- **产物**：`data/indicators/<ts_code>.csv`，列含 OHLCV + groups 所选指标 + 因子。

## 5. 策略与回测（src/strategy.py + backtest.py）

**入口**：`python my_strategy/backtest.py`

### 5.1 MyStrategy 入场条件（5 条同时成立）

1. `close < prev_close`（收阴）
2. `close > MA60`（趋势之上）
3. `DEA > 0`（处于多头宏观区）
4. 过去 `dea_lookback_days` 内出现过 `DEA < 0`（刚刚翻多）
5. 当前未持仓或满足加仓条件

### 5.2 仓位与卖出

- 仓位规模按 `initial_cash / max_positions` 等额分配；
- 止盈分级：`take_profit_1_pct`、`take_profit_2_pct` 两档；
- ATR 动态止盈：`atr_period`、`atr_multiplier`，最终止盈幅度被
  `take_profit_min_pct` / `take_profit_max_pct` 截断；
- MA25 跌破止损（仅在已经触发过 take_profit_1 之后生效）；
- `cerebro.broker.set_coc(True)`：市价单当日收盘成交，**信号日 == 执行日**。
- **涨跌停过滤**：`_is_limit_up` / `_is_limit_down` 检测当日涨跌幅 ≥ ±9.9%；涨停日不开仓/加仓，跌停日不止损/止盈（无法成交），跳过的信号写入 `skipped_log` 并于回测结束后输出 `results/skipped_signals.csv`。

### 5.3 回测组件

- `StockData`（PandasData 子类）暴露 `ma25/ma60/dea` 三条预计算线；
- `StockCommission`：买入只收佣金，卖出佣金 + 印花税；
- 自定义 `BacktestProgressAnalyzer`：按 bar 进度打印百分比；
- 数据预过滤：剔除上市过晚 / 中途退市 / 指标文件缺失的股票，跳过原因汇总打印；
- PIT universe 过滤：按 `stock_list.csv` 中的 `list_date` / `delist_date` 剪裁每只股票的有效回测窗口，避免将未上市股票纳入回测宇宙（前瞻偏差）；`list_date` 缺失时退化为 bt_start（保守）。

### 5.4 产物

- `results/trade_list.csv`：逐笔（每次买卖）明细；
- `results/trade_summary.csv`：以 episode（一次完整开仓→平仓）为单位的汇总；新增列 `mfe_pct` / `mae_pct`（持仓期相对首买入价的最高浮盈 / 最深浮亏，单位百分点）、`dea_neg_distance_days`（首买时距上次 DEA<0 的 bar 数）；这些字段为只读观测，不参与买卖判定；新增 4 个入场环境布尔快照列 `entry_hs300_dif_above_zero` / `entry_hs300_bull_align` / `entry_stock_bull_align` / `entry_stock_above_ma25`，分别表示进场当日 HS300 MACD DIF 是否水上、HS300 是否完整多头排列（ma25>ma60>ma144>ma180）、个股是否完整多头排列、个股是否站上 MA25；新增 4 个交易质量指标列：`mfe_minus_realized`（mfe_pct - return_pct，衡量潜在盈利未实现部分）、`exit_efficiency`（return_pct / mfe_pct，mfe=0 时为 NaN，衡量出场时机效率）、`benchmark_return_during_holding`（持仓期 HS300 同期累计收益 %，数据来自 `data/daily/000300.SH.csv`）、`per_trade_alpha`（return_pct 减去同期 HS300 收益，即单笔超额）；未平仓行（exit_date 为 NaT）的 4 列均为 NaN；新增 3 个前瞻收益列：`forward_return_5d` / `forward_return_20d` / `forward_return_60d`（入场后 N 个交易日的累计收益 %，从 `data/daily/<ts_code>.csv` 读取，数据不足或股票缺失则 NaN）；
- `results/equity_curve.png`：净值曲线；
- `results/skipped_signals.csv`：被涨跌停过滤的信号明细（列：date / ts_code / skip_reason / close）；仅当有跳过信号时生成；
- `data/signals_log.csv`：每次入场信号当时的因子快照（供归因使用）；
- 终端打印：总收益、Sharpe、最大回撤、胜率等。

## 6. 归因分析（tools/attribution.py）

**职责**：把交易明细 + 信号日志 join 起来，从五个角度评估策略。

输入两份：`results/trade_summary.csv` + `data/signals_log.csv`。
**触发方式**：`backtest.py` 跑完后自动调用 `attribution.run(project_root, cfg)`，无需单独执行；也可手动 `python my_strategy/tools/attribution.py`。
输出到 `reports/`：

1. **trade_profile**：按收益分桶（大盈/小盈/持平/小亏/大亏）统计因子均值、分位；
2. **top_trades / bottom_trades**：收益最高 / 最低各 10 笔；
3. **sector_winrate**：按申万一级行业统计交易数、胜率、平均收益；
4. **factor_alpha**：每个 `factor_*` 因子的 IC（Spearman）与多空分组超额；
5. **exit_reason_stats**：按出场原因（MA25清仓 / take_profit_1/2 / 未平仓 ...）统计胜率、收益、持仓天数、加仓次数；
6. **add_count_stats**：按加仓次数（0/1/2/3+）统计胜率、收益、已平仓比例；
7. **entry_condition_stats**：7 个入场快照字段（kdj_j / ma60_dist / ma_alignment / macd_zone / week/month）的单条件长表，固定阈值分桶；
8. **yearly_stats**：按 `entry_date.year` 统计 count / win_rate / avg_return / median_return / total_pnl_yuan（绝对盈亏，元）/ avg_holding_days；
9. **first_buy_size_stats**：按 `entry_ma60_dist_pct` 11 桶扫描首仓尺寸阈值（当前 1%）的合理性；输出 count / win_rate / avg_return / median_return / avg_holding_days / avg_add_count / pct_completed；
10. **add_block_stats**：按 `max_bullish_candle_pct`（持仓期最大阳线，由 strategy.py 记录到 trade_summary）9 桶扫描加仓阻断阈值（当前 1%）的合理性；同口径输出；
11. **mfe_mae_by_exit**：按出场原因聚合 MFE（持仓期最高浮盈）/ MAE（最深浮亏）画像，列含 avg_return / avg_mfe / avg_mae / avg_pullback (mfe-return) / avg_underwater (-mae)；
12. **mfe_distribution**：按 mfe_pct 6 桶分布，看曾浮盈过 X% 的笔最终落地胜率/avg_return；
13. **dea_lookback_stats**：按 `dea_neg_distance_days`（距上次 DEA<0 的 bar 数，由 strategy.py 入场时记录）11 桶扫描，评估 `dea_lookback_days`（默认 5）阈值的合理性；
14. **monthly_stats**：按 `entry_date` 年月分组，列与 yearly_stats 同口径（count / win_rate / avg_return / median_return / total_pnl_yuan / avg_holding_days）；
15. **hs300_dif_stats**：按 HS300 MACD DIF 水上/水下二桶统计胜率与收益（flag_value × count / win_rate / avg_return / avg_holding_days）；
16. **hs300_bull_align_stats**：按 HS300 多头排列（ma25>ma60>ma144>ma180）True/False 二桶统计；
17. **stock_bull_align_stats**：按个股多头排列 True/False 二桶统计；
18. **stock_above_ma25_stats**：按个股是否站上 MA25 二桶统计；
19. **regime_combo_stats**：HS300 DIF × 个股多头排列 2x2 共振表（4 个 combo：大盘水上+个股多头 / 大盘水上+个股非多头 / 大盘水下+个股多头 / 大盘水下+个股非多头）。
20. **sector_bull_align_stats**：按行业指数多头排列 True/False 二桶统计；
21. **sector_above_ma25_stats**：按行业指数站上 MA25 二桶统计；
22. **sector_dif_stats**：按行业 MACD DIF 水上/水下二桶统计；
23. **sector_week_macd_stats**：按行业周线 MACD zone 分桶统计；
24. **sector_month_macd_stats**：按行业月线 MACD zone 分桶统计；
25. **sector_momentum_60d_stats**：按行业 60 日动量五分桶（Q1～Q5）统计；
26. **sector_industry_stats**：按 ts_code → sw_index_code 映射后，按 SW 一级行业分桶聚合（count / win_rate / avg_return / avg_holding_days），按交易笔数降序排列；未映射股票自动跳过。
27. **sector_stock_combo_stats**：行业多头排列 × 个股多头排列 2×2 共振表（≤4 行，空桶跳过）；列含 combo / count / win_rate / avg_return / avg_holding_days。

输出目录由 `config.attribution_report_dir` 控制。

## 7. 逐日持仓重建（tools/rebuild_position_history.py）

**职责**：不修改 `backtest.py`，从 `trade_summary.csv` + `data/daily/` + `stock_sector.csv` 事后重建两张宽表。

### 公开函数

| 函数 | 输入 | 输出 |
|------|------|------|
| `build_daily_position_pnl(trades, dailies, sector_map)` | DataFrame × dict × DataFrame | `(trade_id, date)` 长表，含 `cum_return_pct` / `drawdown_from_peak_pct` / `sector_code` |
| `build_daily_portfolio_snapshot(daily_position_pnl)` | 上表 | 按 date 聚合的组合层指标：`n_positions` / `sectors_held` / `top_sector_code` / `top_sector_share` / `herfindahl_index` |
| `build(project_root, cfg)` | 路径 + 配置字典 | 从磁盘读取并写 `results/daily_position_pnl.csv` / `results/daily_portfolio_snapshot.csv` |

**注**：磁盘 daily CSV 使用 `trade_date` 列名，`build()` 内部读取后重命名为 `date` 再传入纯函数，不影响单元测试签名。

## 8. 扩展归因报告（tools/trade_attribution_extra.py）

**职责**：Phase A 统计分析框架扩展模块，从 `trade_summary.csv` 计算多维度 payoff 指标。共 7 张报告，通过 `run()` 模块入口统一写出。

### 公开函数

| 函数 | 输入 | 输出文件 |
|------|------|------|
| `compute_payoff_metrics(trades)` | trade_summary DataFrame | `payoff_metrics.csv` |
| `compute_signal_stability(trades, signals_whitelist)` | trade_summary DataFrame + 信号列名列表 | `signal_stability.csv` |
| `compute_signal_correlation_matrix(trades, signals_whitelist)` | trade_summary DataFrame + 信号列名列表 | `signal_correlation_matrix.csv` |
| `compute_multi_factor_combo_stats(trades, combos, min_sample)` | trade_summary DataFrame + `[(name_a, name_b, name_c), ...]` 三元组列表 | `multi_factor_combo_stats.csv` |
| `compute_significance_summary(trades)` | trade_summary DataFrame | `significance_summary.csv` |
| `compute_signal_importance_ranking(trades, signals)` | trade_summary DataFrame + 信号列名列表 | `signal_importance_ranking.csv` |
| `compute_loss_attribution(trades, signals, heavy_loss_threshold)` | trade_summary DataFrame + 信号列名列表 + 重亏阈值（默认 -5.0%） | `loss_attribution.csv` |
| `run(trades, out_dir, signals_whitelist, combos)` | 上述所有参数 + 输出目录路径 | 写出以上 7 个 CSV |

`compute_payoff_metrics` 按 overall / exit_reason / year / sector / regime 五个维度各产一组行，列含 `n` / `win_rate` / `avg_win` / `avg_loss` / `payoff_ratio` / `profit_factor` / `expectancy` / `max_win` / `max_loss`。

`compute_signal_stability` 对每个信号的每个值（bool 型展开为 True/False，object 型按唯一值，数值型按五分位）× 每个年份各产一行，`rank_within_signal` 按 `avg_return` 降序排名（相同信号内）。

`compute_signal_correlation_matrix` 对 `signals_whitelist` 中存在于 trades 的列两两计算 Pearson 和 Spearman 相关系数，布尔列自动转 0/1，object 列用 factorize 编码，输出仅含上三角对（i < j）。

`compute_multi_factor_combo_stats` 对 `combos` 中每个三元组 (a, b, c)，按 `trades.groupby([a, b, c])` 遍历所有组合格，计算每格的 win_rate / avg_return 及与全样本的 Welch t 检验；`min_sample` 控制 `low_sample_warning` 阈值（默认 100）。

`compute_significance_summary` 对 `_SIGNIFICANCE_TARGETS`（11 类报告：exit_reason / hs300_dif / hs300_bull_align / stock_bull_align / stock_above_ma25 / sector_bull_align / sector_above_ma25 / sector_dif / sector_week_macd / sector_month_macd / yearly）逐类调用 `bucket_stats_with_significance`，输出统一 long format，列含 `report_name` / `bucket_field` / `bucket_value` / `n` / `mean_return` / `std_return` / `std_err` / `ci_low_95` / `ci_high_95` / `t_stat_vs_zero` / `p_value_vs_zero` / `t_stat_vs_overall` / `p_value_vs_overall` / `low_sample_warning` / `significant_flag`；对应列不存在时该目标组自动跳过（返回空行），不做静默降级。

`compute_signal_importance_ranking` 对 `signals` 列表中每个信号综合计算 effect_size（True/False 或上/下半各组平均收益之差）、Welch t 检验、以及月度 Spearman IC（分别对 forward_return_5d/20d/60d），输出含 `signal_name` / `signal_type` / `n` / `mean_return_when_true` / `mean_return_when_false` / `effect_size` / `t_stat` / `p_value` / `ic_mean_5d` / `ic_mean_20d` / `ic_mean_60d` / `ic_ir_60d` / `rank_by_effect_size` / `rank_by_ic` / `rank_combined` 的宽表，按 `rank_combined`（effect_size 排名 × 0.5 + IC 排名 × 0.5）升序排列；信号不在 trades 列中时自动跳过；依赖 trade_summary 中的 `forward_return_5d/20d/60d` 列（Task 6 新增）。

`compute_loss_attribution` 对每个信号的每个枚举值（bool 展 True/False，数值按 5 分位，categorical 按唯一值）计算在全集 / 亏损交易 / 重亏交易中的出现频率 `freq_in_universe` / `freq_in_losses` / `freq_in_heavy_losses`、提升倍率 `lift_loss` / `lift_heavy_loss`，以及卡方独立性检验 `chi2_stat` / `p_value`；无亏损时 freq/lift 列为 NaN，仍输出行（`n_losses=0`）；`heavy_loss_threshold` 默认 -5.0%。

## 9. 交易验证（tools/verify_trades.py）

**职责**：独立工具，不依赖回测产物以外的状态，逐 episode 校验：

- **L1 一致性**：买入笔数 == add_count + 1；shares 累计相等；avg_cost / return_pct
  与原始明细一致；take_profit_1 必须早于 take_profit_2；MA25 止损前提是已触发过 TP1。
- **L1 信号合规**：每笔 initial_buy / add_on 在执行日（即信号日，因 set_coc=True）
  必须满足上文 5.1 的 5 条入场条件；卖出端同理校验。
- **当前状态**：196 个 episode 全部通过买入/卖出双向合规校验。

## 10. 组合风险指标（tools/portfolio_attribution.py）

**职责**：Phase A 统计分析框架，从日收益序列计算组合层面的风险指标，分 overall / yearly / monthly 三个维度输出。

### 公开函数

| 函数 | 输入 | 输出 |
|------|------|------|
| `compute_portfolio_risk_metrics(daily_ret)` | `pd.Series`（日收益，DatetimeIndex） | DataFrame，列含下表指标 |

### 输出列

| 列名 | 说明 |
|------|------|
| `period_type` | `'overall'` / `'yearly'` / `'monthly'` |
| `period_label` | 全局区间字符串 / 年份 / YYYY-MM |
| `sharpe` | 年化 Sharpe（rf=0，252 交易日） |
| `sortino` | 年化 Sortino（仅负收益计下行波动率） |
| `calmar` | Calmar = 年化收益 / abs(最大回撤) |
| `max_drawdown` | 最大回撤（负值，≤ 0） |
| `max_dd_duration_days` | 最大回撤持续天数（峰→谷日历天数） |
| `annualized_return` | 年化收益（复利） |
| `annualized_vol` | 年化波动率 |
| `downside_vol` | 年化下行波动率（负收益标准差 × √252） |

### 内部辅助

- `_max_drawdown(equity)` — 从累计净值计算 `(max_dd, dd_duration_days)`；
- `_risk_block(daily_ret, period_type, period_label)` — 计算单期所有指标并返回 dict，少于 2 个有效数据点时返回 `None`（自动过滤）。

### Task 9 追加函数

| 函数 | 输入 | 输出 |
|------|------|------|
| `compute_losing_streak_stats(trades)` | trade_summary DataFrame（需含 `return_pct` / `entry_date`） | 4 行 long format（metric / value）：longest_losing_streak / longest_winning_streak / avg_losing_streak_length / pct_losing_streaks_ge_5 |
| `compute_drawdown_periods(daily_ret, top_n)` | `pd.Series`（日收益，DatetimeIndex）+ `top_n`（默认 10） | 最深 top_n 个回撤区间 DataFrame，列含 rank / start_date / trough_date / recovery_date / peak_value / trough_value / drawdown_pct / duration_days / recovery_days |

### Task 10 追加函数

| 函数 | 输入 | 输出 |
|------|------|------|
| `compute_concurrent_positions_stats(position_count_log, max_positions)` | `list[int]`（每根 Bar 的并发持仓数，生产格式）/ `list[(date, count)]` / `DataFrame[date, count]` + `max_positions`（满仓上限） | long format DataFrame，列含 metric_type / bucket / value / days_at_level / pct_of_time |

**输出结构**：
- `metric_type == 'summary'`（6 行）：max / avg / median / p95 / pct_at_cap / pct_below_50
- `metric_type == 'position_count_bucket'`（6 行）：`0` / `1-25` / `26-50` / `51-100` / `101-150` / `151-200`，各桶 days_at_level 和 pct_of_time

**输入格式偏差说明**：Task 0 投研确认生产格式为 `list[int]`（per bar 持仓数，无日期配对），与计划文档描述不同；实现增加了 `list[int]` 分支，原有 DataFrame 和 `list[(date,count)]` 分支保留向前兼容。

### Task 11 追加函数（模块完成）

| 函数 | 输入 | 输出 |
|------|------|------|
| `compute_period_alpha(strat, benchmarks)` | `pd.Series`（日收益）+ `{benchmark_code: pd.Series}` 字典 | DataFrame，列含 period_type / period_label / benchmark_code / strategy_return / benchmark_return / alpha / beta / info_ratio / tracking_error / n_trading_days |
| `compute_rolling_metrics(daily_ret, window=252)` | `pd.Series`（日收益） | DataFrame，每行为一个滚动窗口末日；列含 window_end_date / window_size_days / n_trading_days / sharpe / sortino / win_rate_daily / max_dd_in_window / annualized_return / annualized_vol |
| `run(daily_ret, position_count_log, benchmarks, trades, cfg, out_dir)` | 上述所有参数 + 配置字典 + 输出目录路径 | 写出 6 个 CSV（portfolio_risk_metrics / losing_streak_stats / drawdown_periods / concurrent_positions_stats / period_alpha / rolling_metrics） |

`compute_period_alpha` 按 overall / yearly / monthly 三个周期，对每个 benchmark 计算累计收益 / alpha（年化，CAPM 定义）/ beta / tracking error / information ratio，少于 5 个对齐数据点的子期自动跳过。
`compute_rolling_metrics` 以默认 252 日为窗口对日收益做滚动统计，输出年化 Sharpe / Sortino / 最大回撤，可用于识别策略衰减和 regime 切换。
`run()` 为 portfolio_attribution 模块入口，统一写出全部 6 张组合层报告。

## 12. 持仓曲线归因（tools/position_curve_attribution.py）

**职责**：Phase A 统计分析框架，基于 `daily_position_pnl` / `daily_portfolio_snapshot` / `trade_list` 计算持仓期曲线（4 张报告，Task 12-15 逐步追加）。

### 公开函数（Task 12–15，模块完成）

| 函数 | 输入 | 输出文件 |
|------|------|------|
| `compute_holding_period_curve(daily_position_pnl)` | `daily_position_pnl` DataFrame（含 `holding_day_n` / `cum_return_pct` / `drawdown_from_peak_pct`） | `holding_period_curve.csv` |
| `compute_mfe_timing(daily_position_pnl)` | 同上 | `mfe_timing.csv` |
| `compute_sector_concentration_stats(daily_portfolio_snapshot, top_n)` | `daily_portfolio_snapshot` DataFrame（含 `top_sector_share` / `herfindahl_index` / `top_sector_code` / `n_positions`） | `sector_concentration_stats.csv` |
| `compute_cost_breakdown(trades, cfg)` | trade_list（或 trade_summary）DataFrame + `cfg`（含 `commission_rate` / `stamp_duty`） | `cost_breakdown.csv` |
| `run(project_root, cfg)` | 路径 + 配置字典 | 写出以上 4 个 CSV |

**采样点**（`compute_holding_period_curve`）：`[0, 1, 2, 3, 5, 7, 10, 15, 20, 25, 30, 40, 50, 60, 75, 90]`（含第 0 天入场时刻）。

### 输出列（compute_holding_period_curve）

| 列名 | 说明 |
|------|------|
| `holding_day_n` | 持仓第 N 天 |
| `n_active_trades` | 该天仍活跃（有 pnl 记录）的交易笔数 |
| `avg_cum_return` | 累计收益率均值（百分点） |
| `median_cum_return` | 累计收益率中位数 |
| `win_rate_at_day_n` | 当天盈利笔比例（cum_return > 0） |
| `p25_cum_return` | 25 分位累计收益率 |
| `p75_cum_return` | 75 分位累计收益率 |
| `avg_drawdown_from_peak` | 均值回撤（从峰值，通常为负值） |

### 输出列（compute_sector_concentration_stats）

| 列名 | 说明 |
|------|------|
| `metric_type` | `summary`（汇总行）或 `top_concentrated_day`（高集中日） |
| `label` | summary 时为指标名（avg/p95/max_max_sector_share、avg/p95_herfindahl_index）；top 时为日期字符串 |
| `value` | summary 行的指标值；top 行为 NaN |
| `top_sector_code` | top 行的最大行业代码；summary 行为空字符串 |
| `top_sector_share` | top 行最大行业占比；summary 行为 NaN |
| `herfindahl_index` | top 行 Herfindahl 指数；summary 行为 NaN |
| `n_positions` | top 行的总持仓数；summary 行为 NaN |

### 输出列（compute_cost_breakdown）

| 列名 | 说明 |
|------|------|
| `dimension` | `overall` / `year` / `exit_reason` |
| `bucket` | 分桶值（`all` / 年份字符串 / 出场原因字符串） |
| `n_trades` | 该桶交易笔数 |
| `gross_pnl` | 毛利润（元） |
| `total_commission` | 佣金合计（元） |
| `total_stamp_duty` | 印花税合计（元） |
| `net_pnl` | 净利润 = gross_pnl - commission - stamp_duty |
| `cost_pct_of_gross` | 总成本 / abs(gross_pnl) |
| `cost_pct_of_turnover` | 总成本 / turnover（有 turnover 时才有值） |

**数据源模式**：自动检测列名：
- 模式 A（trade_list 含 `commission` + `stamp_duty` 列）：直接 sum；
- 模式 B（仅有 `turnover` / `sell_amount`）：按 `commission_rate × turnover + stamp_duty × sell_amount` 反推；
- 两种列均缺失时 cost 列返回 NaN（不抛异常）。

## 13. 顶层编排（tools/attribution_runner.py）

**职责**：Phase A 统计分析框架顶层编排，依次调用所有子模块并产出全部 14 张新报告 + 2 个中间文件。

### 公开函数

| 函数 | 输入 | 行为 |
|------|------|------|
| `run(project_root, cfg, daily_ret, position_count_log, benchmarks)` | 路径 + 配置字典 + 日收益序列 + 持仓数日志 + 基准字典 | 依次调用 5 个子模块，写出全部报告 |

### 执行顺序

1. `rebuild_position_history.build()` — 重建 `daily_position_pnl.csv` / `daily_portfolio_snapshot.csv`
2. `old_attribution.run()` — 旧归因报告（27 张，保持原行为）
3. `trade_attribution_extra.run()` — trade-level 扩展（7 张）
4. `portfolio_attribution.run()` — 组合层风险指标（6 张）
5. `position_curve_attribution.run()` — 持仓曲线归因（4 张）

### 内置常量

- `DEFAULT_SIGNALS_WHITELIST`：14 个信号列名白名单，供 `compute_signal_stability` / `compute_signal_correlation_matrix` 使用
- `DEFAULT_COMBOS`：3 个三元组，供 `compute_multi_factor_combo_stats` 使用

### backtest.py 接入点（Task 17）

`main()` 最末尾调用 `attribution_runner.run`，传入：
- `daily_ret = pd.Series(r.analyzers._TimeReturn.get_analysis())`（来自 cerebro 的 `_TimeReturn` 分析器）
- `position_count_log = getattr(r, 'position_count_log', None)`（策略累计的 `list[int]`）
- `benchmarks = {code: pct_change(close)}`（从 `data/daily/{code}.csv` 读 close 求日收益，按 `cfg.benchmark_codes` 列出的全部基准代码）

文件顶部注入 `sys.path.insert(0, project_root)` 以保证 `attribution_runner` 内部 `from my_strategy.tools import ...` 在 `cd my_strategy && python backtest.py` 上下文也能解析。

### 端到端验证（2026-05-08）

`python backtest.py` 跑通：
- 14 张报告 + 2 个中间文件全部产出
- 关键指标合理：Sharpe 0.32 / max_drawdown -10.99% / payoff_ratio 2.15
- 全套 pytest：148 passed, 1 skipped，无回归

Phase A 统计分析框架全部 18 个 Task（Task 0 调研 + 17 实施）至此完成。

## 11. 配置文件（config.json）核心字段

| 字段 | 说明 |
|---|---|
| `tushare_token` | Tushare API token |
| `start_date / end_date` | 数据下载区间 |
| `backTest_Start_data / backTest_end_data` | 回测区间 |
| `initial_cash` | 初始资金 |
| `max_positions` | 最大持仓数（决定单笔仓位） |
| `commission_rate / stamp_duty` | 佣金率 / 印花税率 |
| `dea_lookback_days` | 入场条件④的回看天数 |
| `take_profit_1_pct / take_profit_2_pct` | 两级止盈阈值 |
| `atr_period / atr_multiplier` | ATR 止盈参数 |
| `take_profit_min_pct / take_profit_max_pct` | ATR 止盈截断范围 |
| `index_codes` | 股票池来源指数（沪深300、中证500 等） |
| `sw_index_codes` | 申万一级行业指数列表 |
| `data_paths.*` | 各数据子目录路径 |
| `signals_log_path` | 入场信号日志输出路径 |
| `attribution_report_dir` | 归因报告输出目录 |

## 11. 运行命令速查

```bash
# 1. 一键拉取股票池 + 全部数据 + 计算指标
python my_strategy/download_all.py

# 2. 跑回测（产生 trade_list / trade_summary / signals_log / equity_curve）
python my_strategy/backtest.py

# 3. 跑归因分析（依赖步骤 2 的输出）
python my_strategy/tools/attribution.py

# 4. 验证交易合规
python my_strategy/tools/verify_trades.py

# 5. 跑测试
cd my_strategy && pytest

# 6. 数据健康自检（一次性）
python -m my_strategy.tools.data_integrity_check
```

## 14. 数据健康自检（`data_integrity_check.py`）

**职责**：一次性扫描 `data/daily/*.csv` + `stock_list.csv`，将所有发现的数据问题输出到 `results/integrity_report.csv`。不修复数据，只暴露问题供人工决策。不进入回测主循环。

### 调用方式

```bash
python -m my_strategy.tools.data_integrity_check
```

或在脚本中：

```python
from my_strategy.tools.data_integrity_check import run
run(project_root, cfg)
```

### 检查项（8 种 issue_type）

| issue_type | 说明 | severity |
|---|---|---|
| `missing_trading_day` | benchmark（000300.SH）有交易日但本股缺数据 | warning |
| `duplicate_date` | 同一 trade_date 出现多行 | error |
| `non_monotonic_date` | 日期不单调递增（存在回退） | error |
| `abnormal_close_jump` | 单日 close 变化超过阈值（默认 ±25%）；前复权下不应出现 | warning |
| `qfq_break` | close = 0 或 NaN；前复权数据不应为零 | warning |
| `suspended_period` | 连续 ≥5 个 bar 的 OHLCV 完全相同且 volume=0（疑似停牌） | info |
| `not_in_stock_list` | `data/daily/` 下有文件但 `stock_list.csv` 中不含该股票 | warning |
| `in_list_no_data` | `stock_list.csv` 中有该股票但 `data/daily/` 下无文件 | warning |

### 输出

- 文件：`results/integrity_report.csv`
- 列：`ts_code` / `issue_type` / `severity` / `date_or_range` / `detail`
- severity 分三档：`error`（数据严重损坏）/ `warning`（需关注）/ `info`（信息性提示）
