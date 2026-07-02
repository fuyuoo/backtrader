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

## 2026-07-02 — RunPlan 离线只读阶段共享 SnapshotReadCache

- 需求：`data_preflight_symbols` 和 `prepare_run_data_symbols` 都会读取同一批日线、指标和可交易状态快照；正式离线回测应避免重复读盘。
- 改动：
  - `attbacktrader/runners/run_plan.py`：在只读快照模式下自动创建共享 `SnapshotReadCache`，并同时传给股票池 preflight 与正式 prepared data；如果 `refresh_before_stock_pool_filter=true`，默认不自动共享，避免边写边读造成缓存陈旧。
  - `attbacktrader/runners/data_preflight.py`：新增 `snapshot_read_cache` 参数，并下传到 index、industry index 和 symbol 级准备逻辑。
  - `attbacktrader/features/snapshots.py`、`attbacktrader/data/snapshots/tradability_store.py`：指标快照和可交易状态 Parquet reader 支持可选 read cache。
  - `attbacktrader/runners/prepared_data.py`：指标、可交易状态候选读取接入共享 cache；性能画像新增 `source_snapshot_reference_count`，旧的 `source_snapshot_read_count_lower_bound` 暂保留兼容。
  - `tests/test_run_plan_executor.py`、`tests/test_indicator_snapshots.py`、`tests/test_parquet_snapshots.py`、`tests/test_prepared_run_data.py`：覆盖跨阶段 cache 传递和 reader cache 复用。
- 影响：不改变策略信号、数据刷新策略或回测结果口径；2023-2024 固定 800 股票池离线基线从约 746.9 秒降到约 473.5 秒，但第二次运行保留标的数从 768 增至 797，耗时对比仅作为工程基线，不作为策略证据。

## 2026-07-02 — 数据准备与 Decision Event Table 增加性能画像

- 需求：优先处理架构报告里的效率问题，先补可观测性，定位数据准备和大表构建的主要耗时/重复读取来源。
- 改动：
  - `attbacktrader/runners/prepared_data.py`：`PreparedRunData` 新增 `performance_profile()`，数据准备完成时通过 progress callback 写出 `prepare_run_data_profile` 事件，记录股票数、benchmark/行业引用数量、快照来源动作统计、provider fetch 次数下界、指标快照复用/构建统计等。
  - `attbacktrader/reports/scored_entry_allocation_tuning.py`：Strategy Decision Event Table 构建结果新增 `build_profile`，progress completed 事件同步输出扫描行数、actionable 行数、事件数和因子字段数。
  - `tests/test_prepared_run_data.py`、`tests/test_scored_entry_allocation_tuning.py`：覆盖性能画像事件和构建画像字段。
  - `docs/FEATURES.md`：补充 RunPlan 数据准备性能画像和 Decision Event Table 构建画像说明。
- 影响：不改变策略信号、回测结果、数据刷新逻辑或 artifact schema 的核心含义；这次只增加长任务诊断信息，为后续减少重复 snapshot 读取和 provider fetch 做基线。

## 2026-07-01 — 可交易状态快照支持区间复用

- 需求：长窗口回测和后续 20 年全 A 回测前，先减少重复 Tushare 请求；回测期间不应为了可交易状态反复联网。
- 改动：
  - `attbacktrader/cli/data_preflight.py`：新增 `--offline-data`，正式回测前的数据校验也可以强制只读本地快照，不读取 token、不构建 Tushare provider。
  - `attbacktrader/data/snapshots/tradability_store.py`：新增可交易状态快照候选发现，支持按文件名日期区间识别本地 Parquet 覆盖范围。
  - `attbacktrader/runners/prepared_data.py`：准备数据时优先复用已有可交易状态区间快照；覆盖完整时直接裁剪写出目标快照，覆盖不足时只请求缺口区间。
  - `tests/test_data_preflight.py`、`tests/test_parquet_snapshots.py`、`tests/test_prepared_run_data.py`：覆盖离线 preflight、区间发现、宽区间复用不请求 provider、以及只补缺口的行为。
  - `docs/FEATURES.md`：补充长窗口数据准备和离线回测的数据复用口径。
- 影响：默认策略信号和交易逻辑不变；数据准备阶段减少重复联网，正式回测配合 `--offline-data` 可保证缺数据直接失败。

## 2026-07-01 — RunPlan CLI 增加离线数据模式

- 需求：正式回测期间不允许请求 Tushare；数据准备和回测执行需要硬隔离，缺本地数据时应直接失败。
- 改动：
  - `attbacktrader/cli/run_plan.py`：新增 `--offline-data`，强制 `data.refresh_snapshots=false` 和 `data.refresh_before_stock_pool_filter=false`，不读取 Tushare token、不创建 Tushare provider。
  - `tests/test_run_execution_summary.py`：覆盖离线模式不会读取 token/构建 provider，并把离线 RunPlan 传入执行器。
  - `docs/FEATURES.md`：补充离线回测命令和长窗口数据准备建议。
- 影响：默认 RunPlan 行为不变；只有显式加 `--offline-data` 时启用离线只读本地快照口径。

## 2026-07-01 — RunPlan 支持动态指数成分股入场门槛

- 需求：2005-2014 回测不能用 2026 年固定沪深300/中证500成分股池；股票池需要按历史成分股快照变化。
- 改动：
  - `attbacktrader/data/stock_pool.py`：新增动态股票池模型、PIT as-of membership 查询、Parquet 读写和历史并集 CSV 生成。
  - `attbacktrader/cli/dynamic_stock_pool.py`：新增 `att-generate-dynamic-stock-pool`，默认生成 HS300(`399300.SZ`) + CSI500(`000905.SH`) 的动态成分股 Parquet 和历史并集 CSV。
  - `attbacktrader/config/models.py`、`attbacktrader/runners/run_plan.py`、`attbacktrader/engines/business/baoma.py`：RunPlan 支持 `data.dynamic_stock_pool_file`，Baoma 入场用 T-1 `signal_trade_date` 做动态成分股门槛；新增 `data.refresh_before_stock_pool_filter`，用于首次跑历史窗口时先刷新快照再做股票池预检。
  - `docs/baoma-v1-score5-date-contract.md`：记录 T-1 证据日与动态成分股池的使用契约。
- 影响：`stock_pool_file` 只负责准备历史并集行情；真正的“当时是否属于沪深300/中证500”由 `dynamic_stock_pool_file` 在入场时判断。

## 2026-06-29 — 入场归因证据改为信号日口径

- 需求：策略语义是 T-1 满足入场条件、T 日买入，归因/过滤/打分证据不能使用 T 日收盘后才知道的信息。
- 改动：
  - `attbacktrader/strategies/attribution.py`：`with_entry_attribution_controls` 支持显式 `evidence_date`。
  - `attbacktrader/engines/business/portfolio.py`、`attbacktrader/engines/business/baoma.py`、`attbacktrader/engines/backtrader/strategy_bridge.py`：入场和加仓归因改用上一交易日证据；出场归因仍用当前交易日证据。
  - `tests/test_entry_attribution.py`、`tests/test_baoma_business_runner.py`：补充 T-1 证据回归覆盖。
- 影响：旧的土壤/种子 Scored Portfolio 结果需要重建 decision event table 后重跑，不能继续当作严格实盘口径证据。

## 2026-06-28 — 大表 artifact 改为 Parquet 存储

- 需求：十年全 A RunPlan 已在写 `signal_audit.json` 时触发 MemoryError，后续不需要人工手读大表，统一优先使用 Parquet 降低体积和写盘内存压力。
- 改动：
  - `attbacktrader/reports/writer.py`：`trades`、`signal_audit`、`sizing_audit`、`equity_curve`、`positions`、`execution_audit` 改写为 zstd Parquet；`run_plan.json`、`result.json`、报告和索引类小文件继续保留 JSON。
  - `attbacktrader/cli/scored_entry_allocation_tuning.py`：`--signal-audit` 支持读取 `.parquet`；`--build-decision-event-table` 默认把事件明细写入 `decision_events.parquet`，`decision_event_table.json` 仅保留元数据和事件文件路径；`--run-full-study` 可从 Parquet 事件存储读回。
  - `tests/test_report_writer.py`、`tests/test_scored_entry_allocation_tuning.py`：覆盖大表 Parquet 写出、Parquet signal audit 输入和 Parquet decision events 读回。
- 影响：历史 JSON signal audit 仍可作为输入读取；新的真实长跑不再写巨型 `signal_audit.json`。

## 2026-06-27 — 全 A reference 支持按交易日分片输出

- 需求：全量全 A 数据准备前，避免一次性写单个巨大 Parquet 或在内存里累积全部 reference rows，同时保留 rolling 指标和历史行业映射口径。
- 改动：
  - `attbacktrader/cli/prepare_attribution_reference.py`：新增 `--partition-by-trade-date` 和 `--emit-start-date`；分片输出必须配合 `--parquet-only`。
  - `attbacktrader/data/snapshots/attribution_reference.py`：构建器支持 warmup 计算起点与输出起点分离，并按交易日写 `reference_values/trade_year=YYYY/trade_date=YYYY-MM-DD.parquet`；读取和发现快照兼容单文件与分片目录。
  - `attbacktrader/reports/attribution_wide_samples.py`：reference snapshot loader 兼容分片目录。
  - `tests/test_reference_snapshots.py`：覆盖分片输出、按日期读取和快照发现。
- 影响：默认仍写旧单文件格式；显式分片时不生成 `reference_values.parquet`，读取端会读取 `reference_values/` 分片目录。

## 2026-06-27 — 全 A reference 准备支持 Parquet-only 输出

- 需求：准备全量全 A 数据拉取时，避免 `reference.json` 体积过大，改用 Parquet 存储。
- 改动：
  - `attbacktrader/cli/prepare_attribution_reference.py`：新增 `--parquet-only`，只写 `metadata.json` 和 `reference_values.parquet`。
  - `attbacktrader/data/snapshots/attribution_reference.py`：快照写入支持跳过 `reference.json`，并清理同输出目录中的旧 `reference.json`。
  - `tests/test_reference_snapshots.py`：覆盖 Parquet-only CLI 输出。
- 影响：默认行为不变；只有显式加 `--parquet-only` 时不生成 `reference.json`。

## 2026-06-27 — 固定分数组合回测支持保守同日资金口径

- 需求：第一版固定 score>=5 的 Scored Portfolio Backtest 先补保守执行顺序，避免同日卖出资金被立刻用于同日新买。
- 改动：
  - `attbacktrader/reports/scored_entry_allocation_tuning.py`：score gate 支持 `minimum_score` 固定绝对分数；组合模拟器新增 `allow_same_day_exit_cash_reuse` 组合控制，设为 `false` 时卖出资金当天入账但不参与当天新买现金检查；新增 `prefer_unheld_industries` 排序控制，优先选择当前持仓尚未覆盖的行业。
  - `tests/test_scored_entry_allocation_tuning.py`：覆盖固定绝对分数门槛、保守口径下同日卖出资金不能买入新候选，以及当前未持仓行业优先排序。
  - `CONTEXT.md`、`docs/FEATURES.md`：同步固定参数组合验证与保守同日资金口径说明。
- 影响：默认仍保留旧模拟器行为；只有显式设置 `allow_same_day_exit_cash_reuse=false` 或 `prefer_unheld_industries=true` 的固定规则验证会使用新口径。

## 2026-06-26 — 贝叶斯入场分数目标函数加入训练年覆盖惩罚

- 需求：Slim 框架多 seed 验证出现部分测试年份 0 笔或极少笔，继续改目标函数，避免贝叶斯学出过严择时参数。
- 改动：
  - `attbacktrader/reports/entry_score_bayesian_walk_forward.py`：新增 `min_train_yearly_pass_count`，目标函数加入 `yearly_sample_penalty`，只按训练窗每一年通过数惩罚，不使用测试年信息；trial details 记录 `selected_count_by_year`、`min_selected_count_by_year` 和年度惩罚。
  - `attbacktrader/cli/entry_score_bayesian_walk_forward.py`：新增 `--min-train-yearly-pass-count` 参数。
  - `tests/test_entry_score_bayesian_walk_forward.py`：覆盖 CLI 参数透传和训练年通过数惩罚。
  - `docs/FEATURES.md`：同步 walk-forward 目标函数和参数说明。
- 影响：默认值为 0，不改变旧命令行为；设为正数时可降低训练窗年度覆盖不足导致的过严 score gate。

## 2026-06-26 — 扩展入场打分负面因子

- 需求：把 2023 失效诊断里显著负向的字段加入入场打分，作为减分项或准门槛项。
- 改动：
  - `attbacktrader/reports/entry_score_trade_sample_backtest.py`：默认打分框架新增弱20/60日动量、DEA水上持续天数、固定ATR止损适配、个股相对行业波动、个股/行业/中证500周线 KDJ 和中证500趋势等负面权重，并用大负分 interaction 表达准门槛组合。
  - `tests/test_entry_score_trade_sample_backtest.py`：覆盖弱动量和市场/行业过热组合会被大幅扣分。
  - `docs/FEATURES.md`：同步默认打分框架说明。
- 影响：贝叶斯 walk-forward 会自动把这些新增因子权重和 interaction 权重纳入搜索空间；当前仍是 completed-trade 样本过滤，不是真实组合层硬风控。

## 2026-06-26 — 新增贝叶斯因子分数 Walk-Forward

- 需求：因子组合分数不再只用人工固定权重，而是用贝叶斯方法寻找各因子加减分权重，并使用 walk-forward 做训练窗调参、下一年样本外验证。
- 改动：
  - `attbacktrader/reports/entry_score_bayesian_walk_forward.py`：新增 `entry_score_bayesian_walk_forward.json/.zh.md` 报表构建，读取已落盘 `environment_fit.trade_contributions`，基于默认强趋势阴线回踩打分框架生成权重搜索空间，用 Optuna/TPE 在训练年份优化因子 bucket 权重、interaction 权重和最低入场分，再冻结参数评估下一年 OOS 样本。
  - `attbacktrader/cli/entry_score_bayesian_walk_forward.py`：新增 `att-entry-score-bayesian-walk-forward` 命令，支持配置训练窗年数、测试年份范围、trial 数、随机种子、训练样本数/通过率约束、优化器和输出目录。
  - `tests/test_entry_score_bayesian_walk_forward.py`：覆盖 walk-forward 构建、CLI 写盘、artifact payload 和 Optuna 缺失时显式失败。
  - `setup.py`、`attbacktrader/reports/__init__.py`、`docs/FEATURES.md`：导出新能力和命令说明。
- 影响：该报告是 completed-trade 样本上的权重寻优和样本外过滤验证，不包含未成交候选、现金竞争、真实持仓上限和每日容量约束；真实组合收益仍需 full signal_audit 或 Strategy Decision Event Table 驱动的 Scored Portfolio Backtest。

## 2026-06-26 — 新增固定因子打分一年 trade-sample 验证

- 需求：把“强趋势阴线回踩”的组合因子框架固化为加减分规则，按分数降序排序，设置最低入场分数，在无持仓上限口径下先回测一年。
- 改动：
  - `attbacktrader/reports/entry_score_trade_sample_backtest.py`：新增 `entry_score_trade_sample_backtest.json/.zh.md` 报表构建，读取已落盘 `environment_fit.trade_contributions`，按默认因子权重和 interaction 权重计算入场分数，输出分数达标/未达标样本、阈值扫描、月度表现、最高分交易、最差达标交易和被挡掉的盈利交易样本。
  - `attbacktrader/cli/entry_score_trade_sample_backtest.py`：新增 `att-entry-score-trade-sample-backtest` 命令，支持选择年份、最低入场分数、输出目录和样本数量。
  - `tests/test_entry_score_trade_sample_backtest.py`：覆盖默认打分过滤、CLI 写盘和 artifact payload。
  - `setup.py`、`attbacktrader/reports/__init__.py`、`docs/FEATURES.md`：导出新能力和命令说明。
- 影响：该验证是 completed-trade 样本上的 score gate，不包含未成交候选、现金竞争、真实持仓上限和每日容量约束；完整组合回测仍需要 full signal_audit 或 Strategy Decision Event Table。

## 2026-06-26 — 新增 Score Gate 反事实漏斗

- 需求：先用年度矩阵筛“平均单笔收益 + 胜率 + 最大亏损”更实操的因子，再做 score gate 反事实漏斗，观察 gate 能挡掉多少亏损、漏掉多少盈利。
- 改动：
  - `attbacktrader/reports/score_gate_counterfactual_funnel.py`：新增 `score_gate_counterfactual_funnel.json/.zh.md` 报表构建，读取已落盘 `environment_fit.trade_contributions` 和 `segmented_factor_contribution_matrix.json`，按样本数、正向年份、平均单笔收益、胜率、最大亏损筛正向 gate 候选，按负收益/低胜率等筛风险候选，并在 completed-trade 样本上输出 gate 通过/阻断、阻断亏损、漏掉盈利、年度漏斗和代表交易样本。
  - `attbacktrader/cli/score_gate_counterfactual_funnel.py`：新增 `att-score-gate-counterfactual-funnel` 命令，支持配置正向因子筛选阈值、风险因子阈值、命中数要求、候选数量和样本数量。
  - `tests/test_score_gate_counterfactual_funnel.py`：覆盖矩阵派生 gate、反事实漏斗、CLI 写盘和 artifact payload。
  - `setup.py`、`attbacktrader/reports/__init__.py`、`docs/FEATURES.md`：导出新能力和命令说明。
- 影响：该漏斗是已完成交易样本上的反事实过滤，不是现金再分配后的真实组合回测；结论只能用于判断 gate 是否值得进入 Scored Portfolio Backtest。

## 2026-06-25 — 新增 10 年分区间与逐年因子贡献矩阵

- 需求：把 2015-2024 十年样本切成几个区间，并补充逐年多指标矩阵，观察各入场因子桶在不同区间和不同年份的贡献能力，用于判断因子更适合的环境。
- 改动：
  - `attbacktrader/reports/segmented_factor_contribution_matrix.py`：新增 `segmented_factor_contribution_matrix.json/.zh.md` 报表构建，读取已落盘 `environment_fit.trade_contributions`，按入场日期默认切成 2015-2016、2017-2018、2019-2020、2021-2022、2023-2024 五个研究区间，输出各因子桶的平均单笔收益、最大单笔盈利、最大单笔亏损/回撤、胜率、净 PnL、资金收益率、相对区间 lift、稳定正向/环境型/偏负向评估；同时自动生成按自然年份切分的 `annual_segment_overall`、`annual_factor_bucket_matrix` 和 `annual_rankings`，Markdown 展示年度概览和稳定正向因子桶年度多指标矩阵，默认指标包括样本数、平均单笔收益、胜率、资金收益率、最大单笔盈利、最大单笔亏损/回撤；默认候选榜单排除 `entry_to_exit`、`exit`、`trade` 等事后诊断字段。
  - `attbacktrader/cli/segmented_factor_contribution_matrix.py`：新增 `att-segmented-factor-contribution-matrix` 命令，支持从 `environment_fit.enriched.json`、`environment_fit.json` 或所在目录生成矩阵，可传入自定义区间，可用 `--annual-matrix-metric` 裁剪年度矩阵展示维度，并在摘要中输出年度因子桶数量与年度矩阵指标。
  - `tests/test_segmented_factor_contribution_matrix.py`：覆盖稳定正向、环境型、偏负向分类、年度多指标矩阵、CLI 指标参数、写盘和 artifact payload。
  - `docs/FEATURES.md`：补充分区间因子贡献矩阵命令和口径说明。
- 影响：该报告只消费已落盘归因证据，不重跑策略、不重新计算指标；区间是人工研究镜头，不是自动市场识别，结论不能直接作为策略开关。

## 2026-06-25 — Decision Event Table 流式构建与进度日志

- 需求：真实 full source RunPlan 已生成 17GB+ `signal_audit.json`，继续推进 standard study 前需要可观测、低内存风险地构建 `decision_event_table.json`。
- 改动：
  - `attbacktrader/cli/scored_entry_allocation_tuning.py`：`--build-decision-event-table` 改为流式扫描 full `signal_audit.json` 顶层数组，新增 `--progress-log` 和 `--progress-interval-rows`，输出扫描行数、actionable 行数、事件数和写盘阶段；`--run-full-study` 复用 `--progress-log` 并新增 `--progress-interval-trials`，记录 decision table 读取、fold、Stage A/B trial、run/report 写盘阶段。
  - `attbacktrader/reports/scored_entry_allocation_tuning.py`：`build_strategy_decision_event_table_from_signal_audit` 支持 iterable 行输入、进度回调，并可在构建阶段补齐 cache identity 的 factor field set；full walk-forward runner 和 Stage A/B 单 fold runner 新增可选进度回调。
  - `tests/test_scored_entry_allocation_tuning.py`：覆盖 CLI 不再整体加载 signal audit、NDJSON 进度事件、pretty JSON 数组流式读取和 full-study progress log。
- 影响：真实 full `signal_audit.json` 不再需要一次性读入内存才能生成 Strategy Decision Event Table；standard full study 长跑也可观察 fold/trial 进度；compact signal audit 仍会明确失败。

## 2026-06-25 — 新增 RunPlan 长跑进度日志

- 需求：真实 standard study 的 full source RunPlan 运行时间较长，需要可观测的日志和进度后再重新跑。
- 改动：
  - `attbacktrader/cli/run_plan.py`：新增 `--progress-log` 和 `--progress-interval-days`，把 CLI / runner / engine 阶段写入 NDJSON，不污染 `--summary-json` stdout。
  - `attbacktrader/runners/run_plan.py`：新增可选 `progress_callback`，记录数据准备、策略模板、引擎、结果组装和报告构建阶段。
  - `attbacktrader/runners/data_preflight.py`：新增结构化 `event_progress`，让 stock pool auto filter 可记录 index 准备、industry index 准备和逐股票 preflight 进度。
  - `attbacktrader/runners/prepared_data.py`：新增结构化 `event_progress`，记录 common index、逐股票 prepared data、industry data 和 attribution reference 准备进度。
  - `attbacktrader/reports/writer.py`：artifact writer 新增写文件进度事件；`artifact_detail=full` 时 `result.json` 改为 compact manifest，不再重复持久化完整 `signal_audit`，完整信号仍写入专用 `signal_audit.json`。
  - `attbacktrader/strategies/attribution.py`：`build_entry_attribution_context` 新增可选进度回调，记录 market、industry、cross-section、industry-relative 和逐股票 evidence 构建进度。
  - `attbacktrader/engines/business/baoma.py`：Baoma v1 business engine 先输出 rows / previous rows 预处理进度，再按交易日进度输出 processed/total days、symbol slots、intent/trade/holding 数量。
  - `tests/test_baoma_business_runner.py`、`tests/test_data_preflight.py`、`tests/test_entry_attribution.py`、`tests/test_prepared_run_data.py`、`tests/test_run_execution_summary.py`：覆盖日级进度事件、preflight/prepared data/entry attribution 结构化进度和 CLI progress log 写出。
- 影响：长回测可以通过 progress NDJSON 文件实时判断是否卡在数据准备、引擎循环或 artifact 写出；失败会保留 `failed` 事件并抛出原异常。

## 2026-06-24 — 新增 Decision Event Table artifact 构建入口

- 需求：继续推进真实 standard study 输入链路，让 `--run-full-study` 不再只能依赖手工准备的 `decision_event_table.json`。
- 改动：
  - `attbacktrader/reports/scored_entry_allocation_tuning.py`：新增 `build_strategy_decision_event_table_from_signal_audit`，可从 full `signal_audit.json` 生成 Strategy Decision Event Table；compact signal audit 会明确失败。
  - `attbacktrader/cli/scored_entry_allocation_tuning.py`：新增 `--build-decision-event-table`、`--signal-audit`、`--run-plan` 和 `--stock-pool-file`，从 run artifacts 写出 `decision_event_table.json`。
  - `tests/test_scored_entry_allocation_tuning.py`：覆盖 full signal audit JSON、compact 拒绝、CLI artifact 写出和 stock pool 顺序。
- 影响：仍需先用 `output.artifact_detail=full` 的 RunPlan 生成真实 full `signal_audit.json`；compact artifact 不能还原完整候选漏斗。

## 2026-06-24 — 补齐 Stage B 样本外组合评估输出

- 需求：继续推进真实 standard study 前的证据纠偏，避免 full walk-forward 报告只记录测试窗边界，却没有真正用测试窗事件评估 Stage B 推荐参数。
- 改动：
  - `attbacktrader/reports/scored_entry_allocation_tuning.py`：Stage B 单 fold tuning 在训练窗选出 balanced/aggressive/defensive 后，新增测试窗 scored portfolio OOS evaluation；score gate 阈值仍由训练窗拟合，测试窗只做评估；报告包新增 `stage_b_oos_scored`、`stage_b_oos_unscored_baseline`、OOS recommendation/baseline 详情和 OOS funnel。
  - `tests/test_scored_entry_allocation_tuning.py`：补充 OOS evaluation、报告包 schema、Markdown 和训练窗阈值复用断言。
  - `docs/FEATURES.md`：更新 scored allocation report package 说明。
- 影响：#30 真实 standard study 仍需要真实 `decision_event_table.json` 和 trial 参数输入；本改动解决的是已有 full-study runner 的样本外组合收益证据口径问题。

## 2026-06-24 — 新增 Scored Allocation full study CLI 入口

- 需求：继续推进 #30 前置证据缺口，让已实现的 full walk-forward runner 和报告包可以从本地 artifact 直接生成标准研究包。
- 改动：
  - `attbacktrader/cli/scored_entry_allocation_tuning.py`：新增 `--run-full-study`、`--decision-event-table`、`--stage-a-trials`、`--stage-b-trials`、`--completed-artifacts` 和 `--minimum-train-trades-per-year` 参数，串联 contract、full walk-forward run 与 scored allocation report package 写出。
  - `tests/test_scored_entry_allocation_tuning.py`：新增 CLI full-study 测试，使用 deterministic decision event table 和 Stage A / Stage B trial 参数 JSON 验证 full run、报告包和推荐参数文件落盘。
  - `docs/FEATURES.md`：补充 full study CLI 示例和能力说明。
- 影响：#30 仍需要真实标准研究输入数据；新入口解决的是从已缓存决策事件和 trial 参数生成可审报告包的问题，不把 contract 输出误当研究结论。

## 2026-06-24 — 新增 Scored Allocation 完整报告包

- 需求：继续推进 `#29 Complete scored allocation report package`，生成机器可读 JSON 与中文 Markdown 报告包，汇总 Stage A、Stage B、样本外边界、Pareto、推荐参数、baseline、稳定性和漏斗诊断。
- 改动：
  - `attbacktrader/reports/scored_entry_allocation_tuning.py`：新增 `build_scored_allocation_report_package`、中文 Markdown renderer 和写出函数，输出 package JSON、中文 Markdown、Pareto frontier JSON，以及 balanced/aggressive/defensive 参数文件。
  - `attbacktrader/reports/__init__.py`：导出报告包 schema、builder、renderer 和 writer。
  - `tests/test_scored_entry_allocation_tuning.py`：新增 deterministic full-run fixture 报告测试，验证 schema、关键中文章节、Stage A 风险提示、指标目录、缺失指标显式列出、稳定性/漏斗切片和 artifact 文件。
  - `docs/FEATURES.md`：更新完整报告包能力说明。
- 影响：报告层会显式警告 Stage A 只是预调优证据；当前 fixture 缺少 market-stage 与 factor-combination 切片时会在报告中明示缺失原因，不静默伪造数据。

## 2026-06-24 — 新增 full walk-forward tuning runner

- 需求：继续推进 `#28 Full walk-forward standard runner`，把单 fold Stage A / Stage B 扩展为 5Y train / 1Y test / 1Y step 的完整 walk-forward 调度。
- 改动：
  - `attbacktrader/reports/scored_entry_allocation_tuning.py`：新增 `run_full_walk_forward_tuning` 和写出函数，按合同生成 2020-2024 五个测试 fold，调度 Stage A / Stage B，复用同一个 decision cache identity，并记录 test window 只做样本外评估、不调参、不重拟合阈值、不更新 Stage A search-space。
  - `attbacktrader/reports/__init__.py`：导出 full walk-forward runner schema、runner 和 writer。
  - `tests/test_scored_entry_allocation_tuning.py`：新增离线 walk-forward fixture，验证 fold 年份、smoke/standard trial schedule、cache key 复用、resume/skip completed artifact，以及 test-window leakage 边界。
  - `docs/FEATURES.md`：更新 full walk-forward runner 能力说明。
- 影响：后续报告包可直接消费 fold-level Stage A / Stage B 输出；本 slice 仍使用小 trial fixture，不启动长标准研究。

## 2026-06-24 — 新增单 fold Stage B scored portfolio tuning

- 需求：继续推进 `#27 Single-fold Stage B scored portfolio tuning`，在真实组合约束下运行单 fold Stage B 多目标参数调优，并输出候选推荐。
- 改动：
  - `attbacktrader/reports/scored_entry_allocation_tuning.py`：新增 `run_single_fold_stage_b_tuning` 和写出函数，使用 Stage B strict score gate、真实组合约束和 Stage A narrowed search space 跑 trial study，并与 Stage B unscored baseline 对照。
  - `attbacktrader/reports/__init__.py`：导出 Stage B tuning schema、runner 和 writer。
  - `tests/test_scored_entry_allocation_tuning.py`：新增小 fixture，验证默认 train-per-year 交易数门槛、Stage B baseline、Pareto 输出、balanced/aggressive/defensive 推荐、search-space 越界失败和 JSON artifact 写出。
  - `docs/FEATURES.md`：更新 Stage B tuning 能力说明。
- 影响：为后续 full walk-forward runner 提供单 fold Stage B 纵切；默认交易数门槛仍按合同执行，测试通过显式小门槛避免长运行。

## 2026-06-24 — 新增单 fold Stage A pre-tuning

- 需求：继续推进 `#26 Single-fold Stage A pre-tuning`，用宽 score gate 与高容量约束跑通单训练窗的 Stage A 参数预调优。
- 改动：
  - `attbacktrader/reports/scored_entry_allocation_tuning.py`：新增 `run_single_fold_stage_a_pre_tuning` 和写出函数，按 fold 训练窗过滤决策事件，执行小 trial study，记录四目标、trial metrics、Pareto、balanced top 20%、elite trial、方向稳定性和 Stage B 搜索空间收窄建议。
  - `attbacktrader/reports/__init__.py`：导出 Stage A pre-tuning schema、runner 和 writer。
  - `tests/test_scored_entry_allocation_tuning.py`：新增离线 fixture，验证 Stage A 宽 gate、高容量约束、四目标记录、elite 规则、factor/interaction 方向稳定性与 JSON artifact 写出。
  - `docs/FEATURES.md`：更新 Stage A pre-tuning 能力说明。
- 影响：Stage A 结果只用于预调优与收窄 Stage B 搜索空间，不作为最终组合收益证据。

## 2026-06-24 — 补齐 score gate 训练窗泄漏护栏

- 需求：继续推进 `#25 Scored entry gates and cache leakage guards`，确保 score gate 阈值只由训练窗拟合，测试窗不能影响阈值、权重或缓存构造。
- 改动：
  - `attbacktrader/reports/scored_entry_allocation_tuning.py`：新增 `fit_training_score_gate_statistics` 与 `apply_fitted_score_gate_to_candidates`，将训练窗阈值拟合和候选打分应用拆开；拟合入口会拒绝带 `test/oos/out_of_sample/validation` 窗口标记的事件。
  - `attbacktrader/reports/__init__.py`：导出训练窗 score gate 拟合与应用入口。
  - `tests/test_scored_entry_allocation_tuning.py`：新增确定性测试，验证训练窗 mean/std/quantile/z-threshold 被复用于测试窗，并捕获使用测试窗候选拟合阈值的错误；扩展 decision cache identity 测试，确认 scorer weights、trial id、score gate 和 score thresholds 不进入决策缓存 key。
  - `docs/FEATURES.md`：更新 score gate 与缓存泄漏护栏说明。
- 影响：后续 Stage A/B tuning 可复用已拟合训练窗阈值，降低样本外测试窗泄漏和参数过拟合风险。

## 2026-06-23 — 新增 scored/unscored baseline comparison

- 需求：继续推进 `#24 Unscored baselines and core metrics`，为 scored portfolio smoke path 增加匹配的不打分基线和核心组合指标。
- 改动：
  - `attbacktrader/reports/scored_entry_allocation_tuning.py`：新增 `run_scored_portfolio_baseline_comparison` 和写出函数，按 Stage A / Stage B 分别输出 scored 与 unscored baseline；baseline 使用固定股票池顺序，不使用分数排序。
  - `attbacktrader/reports/__init__.py`：导出 baseline comparison schema、runner 和 writer。
  - `tests/test_scored_entry_allocation_tuning.py`：新增确定性 fixture，验证 Stage A 高容量基线、Stage B 真实约束基线、固定股票池排序、核心指标字段与单笔交易指标计算。
  - `docs/FEATURES.md`：更新 baseline comparison 能力说明。
- 影响：后续 Stage A/B tuning 可用同一 artifact 对比 scored 与 unscored 口径，避免把容量约束或股票池顺序收益误判为打分器收益。

## 2026-06-23 — 新增固定参数 Scored Portfolio smoke run

- 需求：继续推进 `#23 Fixed-parameter scored portfolio smoke run`，用缓存的决策事件跑通固定参数组合模拟闭环。
- 改动：
  - `attbacktrader/reports/scored_entry_allocation_tuning.py`：新增 `run_fixed_parameter_scored_portfolio_smoke` 和写出函数，消费 Strategy Decision Event Table，产出 selected entries、cash movements、position snapshots、equity curve、blocked entries、funnel 和 metrics。
  - `attbacktrader/reports/__init__.py`：导出 smoke run schema、runner 和 writer。
  - `tests/test_scored_entry_allocation_tuning.py`：新增离线 fixture，覆盖同日 score 排序、确定性 tie-break、score/capacity/holding/cash/tradability 阻塞、现金流水、持仓快照和 JSON artifact 写出。
  - `docs/FEATURES.md`：更新 Scored Portfolio Simulation 能力说明。
- 影响：为后续 Stage A/B tuning 提供固定参数下的组合级 smoke evidence；不访问实时数据，不改变策略执行逻辑。

## 2026-06-23 — 补齐 Strategy Decision Event Table 的 TradeIntent 输入路径

- 需求：继续推进 `#22 Minimal decision-event cache for actionable intents`，让决策事件缓存能消费策略实际输出的意图对象。
- 改动：
  - `attbacktrader/reports/scored_entry_allocation_tuning.py`：新增 `build_strategy_decision_event_table_from_intents`，从 `TradeIntent` 与同日 market context 生成事件表，只抽取 `attribution.values/categories/checks` 等决策时证据。
  - `attbacktrader/reports/__init__.py`：导出新的事件表构建入口。
  - `tests/test_scored_entry_allocation_tuning.py`：新增真实 `TradeIntent` fixture，验证 actionable intent 保留、`hold` 过滤、sizing/execution/completed-trade 状态不进入事件 rows、缺 market context 明确失败。
  - `docs/FEATURES.md`：更新 Strategy Decision Event Table 能力说明。
- 影响：为后续 scored portfolio simulation 消费真实策略决策输出提供缓存边界；不改变现有回测执行语义。

## 2026-06-23 — 新增 Scored Entry Allocation Tuning 本地纵切

- 需求：按 PRD 将 Scored Entry Allocation Tuning 全部实现为可测试的本地纵切，并使用 TDD 推进。
- 改动：
  - 新增 `attbacktrader/reports/scored_entry_allocation_tuning.py`：tuning 合同、walk-forward fold、Strategy Decision Event Table、cache identity、entry scoring、scored portfolio simulation、Stage A 搜索空间收窄、Stage B 推荐报告、Optuna optional gate、合同写出。
  - 新增 `attbacktrader/cli/scored_entry_allocation_tuning.py`：`att-scored-entry-allocation-tuning --mode dry-run` 生成合同 JSON/Markdown。
  - 更新 `setup.py`：新增 `tuning` extra（Optuna）和 console script。
  - 新增 `tests/test_scored_entry_allocation_tuning.py`：覆盖 dry-run 合同、cache identity、禁存字段、评分器、组合模拟、Stage A/B 报告、simulation cache、Optuna gate 和 CLI 写出。
  - 更新 `docs/FEATURES.md`：记录当前 attbacktrader tuning 能力与命令入口。
- 影响：新增能力不触发真实 2015-2024 标准研究；默认测试使用合成数据，不依赖 Tushare 或长回测。

## 2026-05-09 — 新增 3 个可选入场过滤开关（个股均线多头 + 周线/月线 MACD 区间）

- 需求：探索个股均线多空、周/月线 MACD 区间对入场质量的影响，需将这些条件参数化以便对比回测。
- 改动：
  - `my_strategy/src/strategy.py`：StockData 新增 `ma144 / week_macd_zone / month_macd_zone` 三条 lines；MyStrategy.params 新增 `require_stock_ma_bull / require_week_macd_above_zero / require_month_macd_above_zero`（默认均为 False）；next() 入场区在 min_ma60_dist_pct 过滤之后新增 3 个可选过滤块；
  - `my_strategy/backtest.py`：load_feeds() 将 `week_macd_zone / month_macd_zone` 字符串编码为整数（区间0→0…区间3→3）；两处 addstrategy 均透传新参数；
  - `my_strategy/config.json`：新增 `require_stock_ma_bull / require_week_macd_above_zero / require_month_macd_above_zero`，默认 false；
  - `docs/FEATURES.md`：§5.1 新增"可选过滤"章节，配置参数表新增 3 行。
- 影响：默认 false，不影响既有回测结果；开启后入场数量会减少，可通过 --tag 对比不同组合。

## 2026-05-09 — 新增入场 MA60 最小距离过滤 + 禁用加仓配置

- 需求：归因发现 57% 交易入场时距 MA60 ≤ 5%，命中率极低；加仓逻辑加重亏损；需过滤假突破并禁止加仓。
- 改动：
  - `my_strategy/src/strategy.py`：新增 `min_ma60_dist_pct`（默认 0.05）和 `max_add_count`（默认 0）两个参数；入场条件从 5 条增至 6 条（新增距离≥5% 过滤）；加仓上限由硬编码 2 改为 `self.p.max_add_count`；
  - `my_strategy/config.json`：写入 `"min_ma60_dist_pct": 0.05`、`"max_add_count": 0`；
  - `my_strategy/backtest.py`：两处 `addstrategy` 调用均透传新参数（`cfg.get` 带默认值）；
  - `docs/FEATURES.md`：§5.1 条件数 5→6，§5.3 参数表新增两行。
- 影响：回测入场信号大幅减少（过滤近 MA60 假突破）；加仓逻辑对 `max_add_count=0` 时完全跳过，无额外买单。

## 2026-05-09 — 新增三张入场条件观察报告（分布 / 集中度 / 年度交叉）

- 需求：在调参前把统计数据补全，增加 return_pct 分布形态、PnL 集中度、年度×条件交叉三个维度。
- 改动：
  - `tools/attribution.py`：新增 `compute_return_distribution_by_condition` / `compute_pnl_concentration` / `compute_yearly_condition_stats` 三个函数，并在 `run()` 中接入；
  - `tests/test_attribution.py`：新增 11 个测试覆盖三个新函数（空输入/列名/数值约束）；
  - `docs/FEATURES.md`：§6 追加第 28/29/30 条报告说明。
- 影响：reports/ 下报告数 27 → 30；全套测试 197 → 208。

## 2026-05-08 — Phase B-prep 统计基础与数据可信度建设（9 项）

- 需求：调参（Phase B）启动前先把现有报告做对、做完整。
- 改动：
  - 新增 1 个数据层模块：tools/data_integrity_check.py
  - 修改 2 处策略 / 数据加载：strategy.py 涨跌停过滤、backtest.py PIT universe
  - 清理：财务因子从消费侧彻底移除；cost_breakdown.csv overall 行 bug 修复
  - trade_summary.csv 新增 7 列（mfe_minus_realized / exit_efficiency /
    benchmark_return_during_holding / per_trade_alpha / forward_return_5d/20d/60d）
  - 新增 3 张报告：signal_importance_ranking / rolling_metrics / loss_attribution
- 影响：
  - reports/ 下报告数 14 → 17（不破坏现有 14 张）
  - 全套测试 148 → 约 175
  - 一次 backtest 时间 6:08 → 预期 6-7 分钟（PIT 过滤微增）

---

## 2026-05-08 — Phase B-prep Task 8: loss_attribution report
- 需求：识别亏损交易中哪些信号值最常出现（lift 分析 + chi-square 检验）
- 改动：my_strategy/tools/trade_attribution_extra.py（compute_loss_attribution 新增）、my_strategy/tests/test_loss_attribution.py（3 测试）
- 影响：reports/ 新增 loss_attribution.csv

---

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
