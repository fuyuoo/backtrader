# 更新记录（CHANGELOG）

> 维护规则：每次新需求/功能改动后，**在本文件顶部追加一条**记录。
> 同时检查 `docs/FEATURES.md` 是否需要更新对应章节。
> 详见 `CLAUDE.md` 的「文档维护规则」章节。

格式：

```
## YYYY-MM-DD — 一句话标题
- 需求：用户原始需求摘要
- 改动：新增/修改/删除的文件与要点
- 影响：对其他模块的影响（可选）
```

## 2026-05-08 — Phase B-prep Task 7: rolling_metrics report
- 需求：滚动 252 日窗口的关键绩效指标，识别策略衰减 / regime 切换
- 改动：`my_strategy/tools/portfolio_attribution.py`（compute_rolling_metrics 新增）、`my_strategy/tests/test_rolling_metrics.py`（4 个测试）
- 影响：reports/ 新增 rolling_metrics.csv

---

## 2026-05-08 — Phase B-prep Task 6: signal_importance_ranking + forward_return_5d/20d/60d
- 需求：给 trade_summary 增加 forward_return_5d/20d/60d 列；新建 signal_importance_ranking.csv 报告
- 改动：`my_strategy/backtest.py` 新增 `_add_forward_returns()`，在写入 trade_summary.csv 前调用；`my_strategy/tools/trade_attribution_extra.py` 新增 `compute_signal_importance_ranking()` + `_compute_ic_monthly()` + `_classify_signal_type()` 三个函数，`run()` 追加调用；新增 `my_strategy/tests/test_forward_return_enrichment.py`（3 个测试）和 `my_strategy/tests/test_signal_importance_ranking.py`（4 个测试）
- 影响：trade_summary.csv 末尾新增 3 列；reports/ 新增 signal_importance_ranking.csv；同时补全了 run() 中缺失的 compute_significance_summary 调用

---

## 2026-05-08 — Phase B-prep Task 5: trade_summary 新增 4 个交易质量指标列
- 需求：在 trade_summary.csv 中新增 mfe_minus_realized、exit_efficiency、benchmark_return_during_holding、per_trade_alpha 4 列，用于评估出场效率和单笔超额收益
- 改动：`backtest.py` 新增 `_add_trade_summary_metrics()` 函数，在写入 trade_summary.csv 前调用；`my_strategy/tests/test_trade_summary_enrichment.py` 新增 6 个 TDD 测试；`docs/FEATURES.md` §5.4 补充新列说明
- 影响：trade_summary.csv 末尾多 4 列，下游归因读取时按列名访问不受影响

## 2026-05-08 — Phase B-prep Task 4: 移除财务因子消费侧 + 修复 cost_breakdown overall 行
- 需求：从所有消费侧彻底移除 factor_pe_ttm / factor_roe / factor_netprofit_yoy；修复 cost_breakdown.csv overall 行 gross_pnl/net_pnl/cost_pct_of_gross 为 null 的 bug
- 改动：`backtest.py` 清空 `_FACTOR_RENAME`，`_FACTOR_COLS` 仅保留技术因子；`attribution.py` `compute_factor_alpha` 自动发现逻辑排除财务因子；存量 reports/bottom_trades.csv、top_trades.csv 直接删除旧财务因子列；新增 `tests/test_factor_cleanup.py`（6 个测试）
- 影响：signals_log.csv 下次回测起不再写入三个财务因子列；attribution 报告 factor_alpha.csv 不再评估财务因子

## 2026-05-08 — Phase B-prep Task 3: PIT universe 过滤
- 需求：避免在股票上市前将其纳入回测宇宙（前瞻偏差）
- 改动：backtest.py 新增 `_resolve_pit_window()`；`load_feeds` 数据加载循环按 `list_date`/`delist_date` 剪裁每股有效窗口；新增 `tests/test_pit_universe.py`（7 个测试）
- 影响：实际加载股票数可能略减少（较新上市股票在早期窗口被跳过）；本次跳过 11 / 802 股

---

## 2026-05-08 — Phase B-prep Task 2: A 股涨跌停过滤
- 需求：涨停日不开仓/加仓，跌停日不卖出，避免虚假成交
- 改动：`my_strategy/src/strategy.py` 新增 `_is_limit_up` / `_is_limit_down` / `_log_skipped_signal` 三个方法及 `LIMIT_UP_THRESHOLD` / `LIMIT_DOWN_THRESHOLD` 常量，`next()` 各下单点加防护；`my_strategy/backtest.py` 新增 `skipped_signals.csv` 输出；新增 `my_strategy/tests/test_strategy_limit_filter.py`（5 个单元测试）
- 影响：输出 `results/skipped_signals.csv`；实际交易次数可能略有减少

## 2026-05-08 — Phase B-prep Task 1: 数据健康自检模块
- 需求：扫描全量 daily CSV + stock_list.csv，输出问题清单供人工决策
- 改动：新增 my_strategy/tools/data_integrity_check.py（8 个检查函数 + run()），新增 my_strategy/tests/test_data_integrity_check.py（8 个测试）
- 影响：输出 results/integrity_report.csv（不进入 backtest 主循环）

## 2026-05-08 — Phase A 统计分析框架（13 项 / 14 张报告，全量上线）

- 需求：进入 Phase B 自动调参前补齐统计盲区（风险调整收益、显著性、组合层、时间稳定性、持仓期曲线等）。
- 改动：
  - 新增 6 模块：`my_strategy/tools/{stats_helpers, rebuild_position_history, trade_attribution_extra, portfolio_attribution, position_curve_attribution, attribution_runner}.py`。
  - 新增 14 张报告 CSV（`my_strategy/reports/`）+ 2 个中间数据文件（`my_strategy/results/{daily_position_pnl, daily_portfolio_snapshot}.csv`）。
  - `my_strategy/backtest.py`：`main()` 末尾入口由 `attribution.run` 改为 `attribution_runner.run`，新增 benchmark 日数据加载（按 `cfg.benchmark_codes` 从 `data/daily/{code}.csv` 读 close 算 pct_change）；同时把 `time_return = pd.Series(r.analyzers._TimeReturn.get_analysis())` 上移到归因调用之前；顶部注入 `sys.path` 让 `attribution_runner` 内部 `from my_strategy.tools import ...` 在 `cd my_strategy && python backtest.py` 上下文也能解析。
  - `my_strategy/tools/trade_attribution_extra.py`：修复 `_enumerate_signal_values` 在 pandas 3.x 下漏判字符串 dtype 的 bug（字符串列原本错误地落到 qcut 分支抛 `TypeError`）；新增 `pd.api.types.is_string_dtype` 与 `is_numeric_dtype` 守卫。
- 影响：
  - 现有 28 张归因报告 schema 不变；`my_strategy/tools/attribution.py` 不变。
  - 端到端 `python backtest.py` 跑通：14 张新报告 + 2 个中间文件全部产出；3 个抽样指标合理（Sharpe 0.32、max_dd -10.99%、payoff_ratio 2.15）。
  - 全套 pytest：148 passed, 1 skipped，无回归。

## 2026-05-08 — Phase A Task 13：position_curve_attribution 追加 mfe_timing（补登）

- 需求：Phase A Task 13，在 `position_curve_attribution.py` 追加 `compute_mfe_timing`（按 MFE 出现位置分早/中/晚期三档）。
- 改动：`my_strategy/tools/position_curve_attribution.py` 追加 `compute_mfe_timing`；`my_strategy/tests/test_position_curve_attribution.py` 追加测试。
- 备注：原 Task 13 实施 commit (`06d1d81`) 因 cwd 误判遗漏 docs 更新，本次在 Phase A 收尾文档中补登。

## 2026-05-08 — Phase A Task 16：attribution_runner 顶层编排

- 需求：Phase A 统计分析框架 Task 16，新建 `attribution_runner.py` 顶层编排模块，依次调用 rebuild_position_history → old_attribution → trade_attribution_extra → portfolio_attribution → position_curve_attribution，统一产出全部 14 张新报告 + 2 个中间文件。
- 改动：
  - `my_strategy/tools/attribution_runner.py`：新建，公开 `run()` 入口，含 `DEFAULT_SIGNALS_WHITELIST`（14 列）和 `DEFAULT_COMBOS`（3 个三元组）。
  - `my_strategy/tests/test_attribution_runner.py`：新建集成测试，修正 fixture 日线路径为 `data/daily/{code}.csv`（Deviation 1），mock `old_attribution.run`（Deviation 3b）。
  - `my_strategy/tools/position_curve_attribution.py`：修复 `run()` 中 `pd.read_csv(..., errors='ignore')` 调用（该参数在新版 pandas 中已删除，导致 TypeError）。
  - `docs/FEATURES.md`：新增第 13 节，记录顶层编排模块。
- 影响：Phase A 全部 16 个 Task 完成；全套 148 passed 1 skipped。

## 2026-05-08 — Phase A Task 15：position_curve_attribution 追加 compute_cost_breakdown + run() 模块入口（模块完成）

- 需求：Phase A 统计分析框架 Task 15，在 `position_curve_attribution.py` 追加 `_cost_block`、`compute_cost_breakdown`（支持模式 A 直接读取 commission/stamp_duty 列，或模式 B 由 turnover/sell_amount 反推）和 `run()` 模块入口（统一写出 4 张报告：holding_period_curve / mfe_timing / sector_concentration_stats / cost_breakdown）。
- 改动：
  - `my_strategy/tools/position_curve_attribution.py`：文件末尾追加 `_cost_block`、`compute_cost_breakdown`、`run()`；模块至此完成全部 4 张报告。
  - `my_strategy/tests/test_position_curve_attribution.py`：import 行扩充 `compute_cost_breakdown`；追加 `test_compute_cost_breakdown_with_explicit_commission_column`（模式 A）和 `test_compute_cost_breakdown_fallback_estimate_from_turnover`（模式 B）共 2 个新测试。
  - `docs/FEATURES.md`：第 12 节函数表更新为含 `run()` 的完整 5 行，新增 `compute_cost_breakdown` 输出列说明表和数据源模式说明。
- 影响：无破坏性变更；全套测试 147 passed 1 skipped。position_curve_attribution 模块完成。

## 2026-05-08 — Phase A Task 14：position_curve_attribution 追加 compute_sector_concentration_stats

- 需求：Phase A 统计分析框架 Task 14，在 `position_curve_attribution.py` 追加 `compute_sector_concentration_stats`，统计组合逐日行业集中度的 summary 指标（avg/p95/max 最大行业占比、avg/p95 Herfindahl 指数）和 top_n 高集中日明细。
- 改动：
  - `my_strategy/tools/position_curve_attribution.py`：文件末尾追加 `compute_sector_concentration_stats`，输入 `daily_portfolio_snapshot`（需含 `top_sector_share` / `herfindahl_index` / `top_sector_code` / `n_positions`），输出含 `metric_type`（summary / top_concentrated_day）的长格式 DataFrame。
  - `my_strategy/tests/test_position_curve_attribution.py`：import 行扩充新函数；追加 `test_compute_sector_concentration_stats_summary_and_top_n`（验证 summary/top_concentrated_day 均存在、avg_max_sector_share≈0.58）。
  - `docs/FEATURES.md`：第 12 节函数表扩充 Task 13–14 两个新函数，新增 `compute_sector_concentration_stats` 输出列说明表。
- 影响：无破坏性变更；全套测试 145 passed 1 skipped。

## 2026-05-08 — Phase A Task 12：新增 position_curve_attribution.py，实现 compute_holding_period_curve

- 需求：Phase A 统计分析框架 Task 12，新建 `position_curve_attribution.py` 模块，实现持仓期曲线首张报告 `compute_holding_period_curve`。
- 改动：
  - 新建 `my_strategy/tools/position_curve_attribution.py`：`compute_holding_period_curve`，按 16 个采样日（0/1/2/3/5/7/10/15/20/25/30/40/50/60/75/90）汇总活跃交易的 avg/median/win_rate/p25/p75/drawdown 统计。
  - 新建 `my_strategy/tests/test_position_curve_attribution.py`：`test_compute_holding_period_curve_emits_sample_points`，验证列集合、day 0 的 n_active_trades==2、day 3 的 n_active_trades==1。
  - `docs/FEATURES.md`：新增第 12 节 position_curve_attribution，说明采样点、输出列和职责。
- 影响：无破坏性变更；全套测试 143 passed 1 skipped。Tasks 13-15 将继续在此模块追加函数。

## 2026-05-08 — Phase A Task 11：portfolio_attribution 追加 period_alpha + run() 模块入口（模块完成）

- 需求：Phase A 统计分析框架 Task 11，在 `portfolio_attribution.py` 追加 `compute_period_alpha`（对比基准的 alpha / beta / info_ratio / tracking_error）和 `run()` 模块入口（统一写出 5 张报告）。
- 改动：
  - `my_strategy/tools/portfolio_attribution.py`：追加 `_alpha_block`（单期 alpha 计算辅助）、`compute_period_alpha`（overall/yearly/monthly 三维度对比任意数量 benchmark）、`run()`（模块入口，写出 5 个 CSV）。
  - `my_strategy/tests/test_portfolio_attribution.py`：import 行扩充 `compute_period_alpha`；追加 `test_compute_period_alpha_with_benchmark`（验证列集合、benchmark_code 存在、overall/yearly 两种 period_type 均存在）。
  - `docs/FEATURES.md`：第 10 节补充 Task 11 追加函数说明，标注模块完成（5 张报告 + run() 入口）。
- 影响：无破坏性变更；全套测试 142 passed 1 skipped。portfolio_attribution.py 模块至此全部完成。

## 2026-05-08 — Phase A Task 10：portfolio_attribution 追加 concurrent_positions_stats

- 需求：Phase A 统计分析框架 Task 10，在 `portfolio_attribution.py` 追加 `compute_concurrent_positions_stats`，统计逐日并发持仓数的 summary 指标（max/avg/median/p95/pct_at_cap/pct_below_50）和分桶分布（6 个 position_count_bucket）。
- 改动：
  - `my_strategy/tools/portfolio_attribution.py`：文件末尾追加 `compute_concurrent_positions_stats`；支持 `list[int]`（生产格式）/ `list[(date,count)]` / `DataFrame[date,count]` 三种输入形式。
  - `my_strategy/tests/test_portfolio_attribution.py`：import 行扩充新函数；追加 `test_compute_concurrent_positions_stats_summary_and_buckets`（验证 summary/bucket 两种 metric_type 均存在、max==200、pct_at_cap==0.2）和 `test_compute_concurrent_positions_stats_accepts_list_of_ints`（验证生产输入格式）。
  - `docs/FEATURES.md`：第 10 节补充 Task 10 追加函数说明，含输入格式偏差说明。
- 偏差说明：Task 0 投研确认 `r.position_count_log` 为 `list[int]`（非计划所述 `list[(date,count)]`）；实现增加 `list[int]` 分支，测试新增一个专门验证此路径的用例。
- 影响：无破坏性变更；全套测试 141 passed 1 skipped。

## 2026-05-08 — Phase A Task 9：portfolio_attribution 追加 losing_streak_stats + drawdown_periods

- 需求：Phase A 统计分析框架 Task 9，在 `portfolio_attribution.py` 追加 `compute_losing_streak_stats`（连败/连胜统计）和 `compute_drawdown_periods`（Top-N 回撤区间）两个函数。
- 改动：
  - `my_strategy/tools/portfolio_attribution.py`：文件末尾追加 `compute_losing_streak_stats` 和 `compute_drawdown_periods`；原有 `compute_portfolio_risk_metrics` 及辅助函数不变。
  - `my_strategy/tests/test_portfolio_attribution.py`：import 行扩充两个新函数；追加 `test_compute_losing_streak_stats_finds_longest_streaks`（验证 longest_loss==3, longest_win==2）和 `test_compute_drawdown_periods_returns_top_n_with_durations`（验证列集合、len≤3、drawdown_pct<0）。
  - `docs/FEATURES.md`：第 10 节补充 Task 9 追加函数说明表。
- 影响：无破坏性变更；全套 3 个 portfolio_attribution 测试全部通过。

## 2026-05-08 — Phase A Task 8：新增 portfolio_attribution.py，实现 compute_portfolio_risk_metrics

- 需求：Phase A 统计分析框架 Task 8，新建 `portfolio_attribution.py`，计算组合层面 Sharpe / Sortino / Calmar / 最大回撤 / 年化收益等风险指标，按 overall / yearly / monthly 三维度输出。
- 改动：
  - 新增 `my_strategy/tools/portfolio_attribution.py`：实现 `_max_drawdown`、`_risk_block`、`compute_portfolio_risk_metrics` 三个函数；年化因子 252 交易日；下行波动率仅取负收益；Calmar 仅在 max_dd < 0 时有值。
  - 新增 `my_strategy/tests/test_portfolio_attribution.py`：1 个测试，验证输出列集合、三种 period_type 均存在、overall max_drawdown ≤ 0。
  - `docs/FEATURES.md`：新增第 10 节（portfolio_attribution），原"配置文件"节顺移为第 11 节。
- 影响：无，Tasks 9-11 将在此文件中追加函数。

## 2026-05-08 — Phase A Task 7：trade_attribution_extra 新增 significance_summary + 模块入口 run()

- 需求：Phase A 统计分析框架 Task 7（最终任务），在 `trade_attribution_extra.py` 追加 `compute_significance_summary` 和 `run()` 模块入口，至此该模块产出 5 张报告。
- 改动：
  - `my_strategy/tools/trade_attribution_extra.py`：
    - import 行扩充 `bucket_stats_with_significance`（合并入已有的 stats_helpers import 行）；
    - 追加 `_SIGNIFICANCE_TARGETS` 常量（11 个分析目标）；
    - 追加 `compute_significance_summary`：直接调用 `extractor(trades)` 不加 try/except 包装，遵循 CLAUDE.md "不允许静默降级" 政策，删除了计划中原有的 silent except；
    - 追加 `run(trades, out_dir, signals_whitelist, combos)`：写出全部 5 张 CSV；
    - `exit_reason_stats` 的 extractor 补充 `'exit_reason' in t.columns` 守卫，与其他 lambda 保持一致（harmless harmonization，让缺列时返回 `{}` 而非 KeyError）。
  - `my_strategy/tests/test_trade_attribution_extra.py`：import 行补充 `compute_significance_summary`；追加 `test_compute_significance_summary_long_format_with_significance_columns`。
  - `docs/FEATURES.md`：第 8 节全面更新，新增 `compute_significance_summary` / `run()` 函数说明及输出文件对应关系。
- 偏差说明：计划代码含 `try/except Exception: grouped = {}`（silent except），已按 CLAUDE.md 政策移除；各 lambda 已有列存在性守卫（`if col in t.columns else {}`），实际不需要 try/except。
- 影响：无破坏性变更；全套测试 136 passed 1 skipped。

## 2026-05-08 — Phase A Task 6：trade_attribution_extra 新增 multi_factor_combo_stats（三因子交叉聚合）

- 需求：Phase A 统计分析框架 Task 6，在 `trade_attribution_extra.py` 追加 `compute_multi_factor_combo_stats`，对任意三因子组合做 groupby 交叉聚合，计算每个格子的 win_rate / avg_return 及与全样本的 Welch t 检验。
- 改动：
  - `my_strategy/tools/trade_attribution_extra.py`：import 行扩充 `t_test_welch`；文件末尾追加 `compute_multi_factor_combo_stats`。
  - `my_strategy/tests/test_trade_attribution_extra.py`：import 行补充 `compute_multi_factor_combo_stats`；追加 `test_compute_multi_factor_combo_stats_3way_crosstab`。
  - `docs/FEATURES.md`：第 8 节公开函数表新增 `compute_multi_factor_combo_stats` 一行及行为说明。
- 影响：无破坏性变更，既有 4 个测试仍通过，新增 1 个测试，全套 135 passed 1 skipped。

## 2026-05-08 — Phase A Task 5：trade_attribution_extra 新增 signal_correlation_matrix 报告

- 需求：Phase A 统计分析框架 Task 5，在 `trade_attribution_extra.py` 追加 `compute_signal_correlation_matrix`，对信号列两两计算 Pearson + Spearman 相关系数，输出 long format。
- 改动：`my_strategy/tools/trade_attribution_extra.py` 追加函数；`my_strategy/tests/test_trade_attribution_extra.py` 追加测试；`docs/FEATURES.md` 第 8 节更新。
- 影响：无破坏性变更，现有 3 个测试仍通过，新增 1 个测试。

## 2026-05-08 — Phase A Task 4：trade_attribution_extra 新增 signal_stability 报告

- 需求：Phase A 统计分析框架 Task 4，在 `trade_attribution_extra.py` 追加 `compute_signal_stability`，按信号值 × 年份分组计算 win_rate / avg_return / t_stat / p_value / rank_within_signal。
- 改动：
  - `my_strategy/tools/trade_attribution_extra.py`：追加 `_enumerate_signal_values` / `compute_signal_stability`；顶部补充 `from my_strategy.tools.stats_helpers import t_test_one_sample`。
  - `my_strategy/tests/test_trade_attribution_extra.py`：追加 `test_compute_signal_stability_outputs_per_signal_per_year`；import 行补充 `compute_signal_stability`。
  - `docs/FEATURES.md`：第 8 节公开函数表新增 `compute_signal_stability` 一行并补充行为说明。
- 影响：无，未改动任何已有函数。

## 2026-05-08 — Phase A Task 3：trade_attribution_extra 模块（payoff_metrics）

- 需求：Phase A 统计分析框架 Task 3，新建 `trade_attribution_extra.py`，实现 `compute_payoff_metrics`，按 overall / exit_reason / year / sector / regime 五个维度计算 payoff 画像（win_rate / avg_win / avg_loss / payoff_ratio / profit_factor / expectancy）。
- 改动：
  - `my_strategy/tools/trade_attribution_extra.py`（新建）：`_payoff_block` / `compute_payoff_metrics` 两个函数；`payoff_ratio` / `profit_factor` 保留完整精度（未 round），以通过 1e-6 精度断言。
  - `my_strategy/tests/test_trade_attribution_extra.py`（新建）：2 个单元测试覆盖 overall 行数值与维度完整性。
  - `docs/FEATURES.md`：新增第 8 节"扩展归因报告"，目录结构补充新模块。
- 影响：无，未改动任何已有文件。

## 2026-05-08 — Phase A Task 2：rebuild_position_history 模块（逐日持仓 PnL + 组合快照）

- 需求：Phase A 统计分析框架 Task 2，事后重建 `daily_position_pnl.csv` 与 `daily_portfolio_snapshot.csv`，不修改 backtest.py。
- 改动：
  - `my_strategy/tools/rebuild_position_history.py`（新建）：`build_daily_position_pnl` / `build_daily_portfolio_snapshot` / `build` 三个公开函数；`build()` 内处理磁盘 `trade_date` → `date` 列名转换，daily 路径修正为 `data/daily/{ts_code}.csv`。
  - `my_strategy/tests/test_rebuild_position_history.py`（新建）：3 个单元测试覆盖逐日展开、组合聚合、缺失数据报错。
  - `docs/FEATURES.md`：新增第 7 节"逐日持仓重建"，目录结构补充两个新模块，章节编号更新。
- 影响：无，未改动任何已有文件。

## 2026-05-08 — 行业多空环境快照与归因（第二阶段）完成

- 需求：在入场时刻快照行业指数的多空状态（多头排列、站上MA25、DIF水上水下、周/月线MACD zone、60日动量），并生成 8 张新归因报告分析行业环境对交易胜率/收益的影响。
- 改动：
  - `my_strategy/src/downloader_extra.py`：新增 `download_sw_bars`（申万行业指数周/月线，asset='I'）；`main()` 新增 SW 周线/月线下载循环。
  - `my_strategy/src/build_sector_mapping.py`（新建）：`fetch_mapping(stock_list, sector_csv)` + `merge_to_csv`，从 tushare `stock_basic` 接口构建 ts_code → sw_index_code 映射，写出 `stock_sector.csv`。
  - `my_strategy/tools/attribution.py`：
    - 新增 6 个计算函数：`compute_sector_bull_align_stats` / `compute_sector_above_ma25_stats` / `compute_sector_dif_stats` / `compute_sector_week_macd_stats` / `compute_sector_month_macd_stats` / `compute_sector_momentum_60d_stats`；
    - 新增辅助函数 `_compute_zone_stats`（按字符串 zone 分桶）；
    - 新增 `compute_sector_industry_stats`（按 SW 行业代码分桶）；
    - 新增 `_SECTOR_STOCK_COMBO_LABELS` + `compute_sector_stock_combo_stats`（行业×个股多头排列 2×2 交叉）；
    - `run()` tri-state 还原列从 4 个扩展至 7 个；载入 `sector_map_industry` 并写出 8 张新报告（20→28 张）。
  - `my_strategy/tests/test_attribution.py`：新增 13 个测试（54 个总计）。
  - `my_strategy/tests/test_attribution_run.py`：`EXPECTED_FILES` 从 20 扩展至 28（新增 8 个 sector 文件名）。
  - `docs/FEATURES.md`：第 6 节报告列表补全至 27 条（items 20-27）。
- 影响：归因报告从 19 张增至 28 张；所有行业数据均软失败（stock_sector.csv 缺失或 sw_index_code 列缺失时返回空表，不影响其余报告）；Tasks 5-6（实际下载 SW 数据）仍待线上执行。

## 2026-05-08 — feat(attribution): sector_industry_stats — 按 SW 一级行业分桶聚合

- 需求：在 attribution.py 中新增 compute_sector_industry_stats，按 ts_code → sw_index_code 映射后对 SW 31 个一级行业分桶统计交易胜率/收益/持仓天数，并在 run() 中写出 sector_industry_stats.csv。
- 改动：`my_strategy/tools/attribution.py`（新增函数 + run() 接入）、`my_strategy/tests/test_attribution.py`（新增 2 个测试）、`docs/FEATURES.md`（补全 Phase 2 行业报告列表）。
- 影响：归因报告从 25 张增至 26 张；stock_sector.csv 缺失时跳过（返回空表），不影响其余报告。

## 2026-05-07 — calc_indicators 参数化重构：按 groups 选择性计算指标

- 需求：将 calc_indicators.py 的硬编码主循环改为按 groups 列表参数化，支持 stock/sector 两种 CLI 模式。
- 改动：
  - `my_strategy/src/calc_indicators.py`：新增 `add_ma` / `add_macd` / `add_kdj` / `add_week_macd_zone` / `add_month_macd_zone` / `add_factor_*` 原子函数；新增 `compute_indicators(code, src_dirs, dst_dir, groups, ...)` 参数化主入口；新增 `merge_daily_basic_fina` 路径型包装器；原 `compute_indicators(df)` 重命名为 `compute_all_indicators(df)`（向后兼容）；`main()` 改用 argparse + `config.indicator_profiles`。
  - `my_strategy/config.json`：新增 `indicator_profiles.{stock,sector}` 字段。
  - `my_strategy/tests/test_calc_indicators.py`：新增 3 个测试（only_ma_group / macd_group / regression_skip）；旧的 6 处 `compute_indicators(df)` 调用改为 `compute_all_indicators(df)`。
  - `docs/FEATURES.md`：第 4 节全面更新，补充原子函数表、参数化接口说明、CLI 用法。
- 影响：所有现有测试原样通过（104 passed，1 skipped）；backtest.py 调用 `compute_weekly_monthly_indicators` 未变，不受影响。

## 2026-05-07 — 入场环境快照与归因（第一阶段）

- 需求：在 trade_summary 写入入场时刻 4 个环境布尔标志（HS300 DIF 水上水下、HS300 多头排列、个股多头排列、个股站上 MA25），attribution 加 5 张新报告分析环境对胜率的影响。
- 改动：
  - `my_strategy/backtest.py` 新增 `_compute_regime_flags`；`_enrich_trade_summary` 加载 HS300 indicators 并写入 4 个新列（缺文件 raise FileNotFoundError，不静默降级）。
  - `my_strategy/tools/attribution.py` 新增 `_compute_bool_flag_stats` helper + 5 个 compute 函数 + run() dtype 转换 + 5 个 to_csv。
  - `my_strategy/tests/test_backtest.py` 新建/扩展，覆盖 `_compute_regime_flags` 与 `_enrich_trade_summary` 集成（13 个用例）。
  - `my_strategy/tests/test_attribution.py` 新增 7 个测试。
  - `my_strategy/tests/test_attribution_run.py` `EXPECTED_FILES` 15→20。
- 影响：trade_summary.csv 新增 4 列；reports/ 目录新增 5 个 CSV；strategy.py 未改，回测笔数与收益不变（5,911 笔，与上一版一致）。

## 2026-05-07 — 归因报告新增 4 张表（持仓画像/参数扫描/月度细化）+ strategy 采集 mfe/mae/dea 距离

- 需求：标准量化诊断缺失——持仓期 MFE/MAE 未跟踪、dea_lookback_days 这个魔数未做扫描归因、yearly_stats 5 行样本太薄。
- 改动：
  - `my_strategy/src/strategy.py`：模块函数 `_scan_dea_neg_distance(d, max_lookback=200)`；state 增 `first_buy_price / mfe_pct / mae_pct / dea_neg_distance_days`；首买时锁定基准并记录 dea 距离；持仓期更新 mfe/mae（基准 = 首买入价，加仓不变）；trade_summary.csv 新增 3 列。MFE/MAE/dea 距离均为只读观测，不参与买卖判定。
  - `my_strategy/tools/attribution.py` 新增 4 个 compute_ 函数：`compute_mfe_mae_by_exit`（按出场原因聚合）、`compute_mfe_distribution`（6 桶）、`compute_dea_lookback_stats`（11 桶）、`compute_monthly_stats`（年月分组），并在 `run()` 末尾追加 4 个 to_csv。
  - `my_strategy/tests/test_strategy.py` 追加 4 个用例验证行为不变性 + 数据采集正确性。
  - `my_strategy/tests/test_attribution.py` 追加 12 个单元测试。
  - `my_strategy/tests/test_attribution_run.py` `EXPECTED_FILES` 11 → 15。
  - `docs/FEATURES.md` §6 同步至 14 项。
- 影响：回测后归因 15 张报告（之前 11 张）。需重跑回测才能填充 trade_summary.csv 的 3 个新列；旧 trade_summary.csv 上 `mfe_mae_by_exit.csv` / `mfe_distribution.csv` / `dea_lookback_stats.csv` 为空表头（容错），`monthly_stats.csv` 仍可填充。详见 spec：`docs/superpowers/specs/2026-05-07-holding-excursion-attribution-design.md`。

## 2026-05-07 — 归因报告新增 2 张魔数扫描表 + strategy 记录持仓期最大阳线

- 需求：策略含 2 个 1% 魔数（首仓尺寸触发线、加仓阻断阈值），需要数据驱动评估其合理性。
- 改动：
  - `my_strategy/src/strategy.py`：`state['big_candle_seen']`(bool) → `state['max_bullish_candle_pct']`(float)；加仓判定从 `not big_candle_seen` 改为 `<= 0.01`（行为完全等价）；`_finalize_episode` 写入 `trade_summary.csv` 新列 `max_bullish_candle_pct`。
  - `my_strategy/tools/attribution.py` 新增 `compute_first_buy_size_stats`（11 桶扫描 entry_ma60_dist_pct）、`compute_add_block_stats`（9 桶扫描 max_bullish_candle_pct）两个函数，并在 `run()` 末尾追加 2 个 `to_csv`。
  - `my_strategy/tests/test_strategy.py` 追加 3 个用例验证行为不变性。
  - `my_strategy/tests/test_attribution.py` 追加 6 个单元测试。
  - `my_strategy/tests/test_attribution_run.py` `EXPECTED_FILES` 9→11。
  - `docs/FEATURES.md` §6 同步至 10 项。
- 影响：回测后归因 11 张报告（之前 9 张）。重跑回测后 `trade_summary.csv` 新增 `max_bullish_candle_pct` 列；初步数据：5911 笔交易中 max_bullish_candle_pct 中位数 3.8%，>1% 占 4932 笔（83%）。详见 spec：`docs/superpowers/specs/2026-05-07-magic-number-scan-design.md`。

## 2026-05-07 — 归因报告新增 4 张关键统计表

- 需求：现有归因仅覆盖行业/收益分桶/3 个因子三个维度，缺 exit_reason / add_count / 入场条件 / 年度稳定性，无法定位策略瓶颈。
- 改动：
  - `my_strategy/tools/attribution.py` 新增 `compute_exit_reason_stats / compute_add_count_stats / compute_entry_condition_stats / compute_yearly_stats` 四个函数，并在 `run()` 末尾追加 4 个 `to_csv`。
  - `my_strategy/tests/test_attribution.py` 新增 11 个单元测试覆盖正常/边界/空值。
  - `my_strategy/tests/test_attribution_run.py` 扩展 EXPECTED_FILES 至 9 个文件。
  - `docs/FEATURES.md` §6 同步更新输出清单。
- 影响：回测后自动产出 9 张归因报告（之前 5 张），新增 4 张提供策略优化所需的诊断维度。详见 spec：`docs/superpowers/specs/2026-05-07-attribution-extra-stats-design.md`。

## 2026-05-07 — 修复 factor_alpha 因子默认源 + 端到端归因测试脚本

- 需求：归因接着报 `KeyError: 'alpha'`；用户要求用现有 trade_summary.csv 直接测试。
- 改动：
  - `tools/attribution.py` `compute_factor_alpha` 默认因子从 `pct_*` 改为 `factor_*`（pct_ 已废弃）；空 rows 时返回带正确表头的空 DataFrame。
  - 新增 `tests/test_attribution_run.py`：用现有产物端到端跑一次归因并校验 5 份报告全部产出，可直接 `python my_strategy/tests/test_attribution_run.py` 运行。
- 影响：测试通过，5 份报告全部产出（factor_alpha 当前空，因 signals_log 是旧产物无 factor_ 列；下次重跑回测会自动填充）。

## 2026-05-07 — 修复 sector_map 列名错配导致归因 sector_winrate 崩溃

- 需求：归因自动跑起来后报 `KeyError: 'avg_return'`，需修正。
- 改动：
  - `my_strategy/backtest.py` `main()` 构建 `sector_map` 时把 `'sw_index_code'` 改成 `'industry'`（实际 CSV 的列名），让 `signals_log.sector` 不再全空。
  - `my_strategy/tools/attribution.py` `compute_sector_winrate` 增加空值防御：sector 列缺失或全空时返回带正确表头的空 DataFrame，避免 `sort_values` 报 KeyError。
- 影响：回测后 `signals_log.csv` 的 sector 列将正确填充行业名（如"银行"、"全国地产"），`reports/sector_winrate.csv` 也能正常产出。

## 2026-05-07 — 回测末尾自动触发归因分析

- 需求：归因功能此前未挂入主流程，每次得手动跑；改为 `backtest.py` 跑完直接产出归因报告。
- 改动：
  - `tools/attribution.py` 抽出 `run(project_root, cfg)` 公共入口；`main()` 仅做配置加载并转调；修正 `trade_log.csv` → `trade_summary.csv` 的文件名错配。
  - `my_strategy/backtest.py` `main()` 末尾新增 `attribution.run(...)` 调用。
- 影响：单跑 `python my_strategy/tools/attribution.py` 现在能正确读到 `trade_summary.csv`（之前找的是不存在的 `trade_log.csv`）。

## 2026-05-07 — 移除横截面分位（pct_*）功能

- 需求：横截面分位排名暂未开发到选股流程，先删除避免维护负担。
- 改动：
  - 删除 `my_strategy/src/build_cross_section_pct.py`
  - 删除 `my_strategy/tests/test_build_cross_section_pct.py`
  - `my_strategy/backtest.py` 的 `_FACTOR_COLS` 移除 7 个 `pct_*` 列名
  - `docs/FEATURES.md` 移除「横截面分位」章节，章节序号顺延
- 影响：`tools/attribution.py` 用 `startswith('pct_')` 过滤因子，列不存在时返回空，不报错；`factor_alpha` 默认 factors 退化为空列表，需要时改用 `factor_*` 列。

## 2026-05-06 — 建立功能文档与更新记录维护流程

- 需求：把当前功能整理成文档放在 `docs/`，再加一份更新记录文档，并在 `CLAUDE.md` 写入"每次需求都需更新这两个文件"的强制规则。
- 改动：
  - 新增 `docs/FEATURES.md`（当前流水线全景：下载 / 指标 / 横截面 / 回测 / 归因 / 验证 + 配置字段表 + 命令速查）
  - 新增 `docs/CHANGELOG.md`（本文件，回填近期 commit 作为初始记录）
  - 在 `CLAUDE.md` 末尾追加「文档维护规则」章节
- 影响：后续所有需求完成后必须同时更新 `FEATURES.md` 与 `CHANGELOG.md`，否则视为任务未完成。

## 2026-05-06 — 交易数据合规验证工具 verify_trades.py

- 需求：确认 `trade_list` / `trade_summary` 与 `strategy.py` 入场规则一致，排除 T+1 偏移嫌疑。
- 改动：新增 `my_strategy/tools/verify_trades.py`，包含 L1 一致性 + 买入/卖出双向信号合规检查；修复 `signal_day()` 的日期偏移错误（`set_coc=True` 下信号日==执行日）。
- 影响：196 个 episode 零错误，确认回测数据完全合规；为后续策略改动提供回归基线。

## 2026-05-06 — download_all 整合指数成分股拉取

- 需求：股票池来源由手工维护改为按指数成分股自动拉取。
- 改动：`download_all.py` 调用 `pro.index_weight` 拉取 `index_codes` 配置的指数最新成分股快照，写入 `a_stock_list.txt`，再串联下载流程；`config.example.json` 新增 `index_codes` 字段。
- 影响：股票池可通过修改 `config.json.index_codes` 一键切换（沪深300 / 中证500 / 中证1000 等）。

## 2026-05-06 — 回测进度显示与跳过原因摘要

- 需求：长回测过程中能看到进度，跳过股票的输出过于啰嗦。
- 改动：新增自定义 `BacktestProgressAnalyzer` 按 bar 推进打印百分比；跳过原因从逐条打印改为"按类别计数 + 抽样几个代码"的摘要式输出。
- 影响：仅影响 `backtest.py` 终端体验，不改变回测结果。

## 2026-05-06 — eec1e36 fix(review) 因子合并向量化 + IC/spread + ma25

- 需求：Code review 指出因子合并按行循环效率低，且缺少 IC 与多空 spread 指标。
- 改动：`calc_indicators` 因子合并改为向量化；归因新增 IC（Spearman）与多空分组 spread；ma25 列补充。
- 影响：管线吞吐提升；归因报告新增因子有效性指标。

## 2026-05-06 — e23bf0c feat(pipeline) 串联 downloader_extra 与 cross_section_pct

- 需求：把"下载 → 指标 → 截面分位"三步统一在 `download_all.py` 一次跑完。
- 改动：`download_all.py` 末尾追加 `downloader_extra.main()` 与 `build_cross_section_pct.process_indicators_dir(...)` 调用。
- 影响：用户只需运行一条命令即可获得回测就绪的 indicators 目录。

## 2026-05-06 — dcec5ef feat(attribution) 归因报告增强

- 需求：归因报告需要更细粒度——交易侧画像、行业胜率、因子 alpha。
- 改动：`tools/attribution.py` 新增 E-B/E-C trade profile、sector winrate、factor alpha 三类分析。
- 影响：`reports/` 目录产出增多，需配合 `attribution_report_dir` 配置。

## 2026-05-06 — 7907ac3 feat(backtest) 回填前向收益 + signals_log

- 需求：归因依赖每次入场时的因子快照与未来 N 日收益。
- 改动：策略入场时把当前因子值与上下文写入 `data/signals_log.csv`；回测结束后回填每条信号的前向收益。
- 影响：`signals_log.csv` 成为归因输入的主要来源之一。

## 2026-04 之前 — 数据下载与指标计算基础设施

- 累计建立：`downloader`（pro_bar 前复权 + 多周期 + 超时保护）、`downloader_extra`（daily_basic / fina_indicator / 申万行业指数）、`calc_indicators`（技术指标 + 多周期合并 + PIT 财务对齐 + 单股因子 + 行业动量）、`build_cross_section_pct`（横截面分位）。
- 详细 commit 记录见 `git log`，本文件不再展开历史。
