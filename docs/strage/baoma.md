# 宝马策略 V1 草案

本文档用于把用户原始买卖想法整理成可接入 ATTbacktrader 的
`Strategy Definition`。当前阶段只完善规则和漏洞，不评价策略收益，不做参数调优。

## 当前状态

| 项目 | 状态 |
|---|---|
| 策略名称 | `baoma_v1` |
| 文档状态 | 草案，标的池、股票池快照、成交时点、T+1、分批减仓、最终清仓、单股满仓、最大市值、成交样本口径和环境发现目标已确认 |
| 接入模板 | `trend_template_v1` |
| 目标 | 先跑真实策略回测，用结果发现策略适合和不适合的环境，同时反推框架缺口 |
| 非目标 | 不做自动调参，不从报告层后验归因反推买卖规则 |

## 回测类型

第一版按 `Trade-Sample Backtest` 处理：

- 目标是尽量让符合策略和交易约束的信号成交，用成交股票样本分析策略特征。
- 总目标是 `Strategy Environment Discovery`：找到该策略适合的土壤和不适合的场景，用于后续趋利避害，而不是得到一个完美或券商级精确的收益结果。
- 不用组合总盈利作为主要评价依据。
- 起始金额、最终金额、总收益率和权益曲线会因为超大资金设置而失真，只作为执行过程记录，不作为策略优劣结论。
- 核心统计对象是成交股票、完整交易、分批减仓事件、最终清仓事件、胜率、单笔收益、持有期、入场/退出归因和环境分组。
- 报告成功标准是能说明哪些环境下胜率高、盈利贡献高、亏损集中，以及哪些条件组合应该回避。
- 第一版 `Environment Dimension` 暂定为大盘环境、行业环境、个股入场结构、交易执行状态；维度集合和每个维度里的字段都需要可扩展，后续可以继续新增和细化。
- 第一版 `Environment Factor` 先采用少量但有解释力的字段：大盘趋势/市场温度，行业名称/行业趋势，个股 MA60/MA25/DEA 上水/阴线，执行拒绝或挂起状态。
- 环境发现属于 `Post-Trade Environment Lookup`：先由策略和执行层生成交易记录，再按交易记录反查入场日、退出日或持有区间的指数、行业、个股和执行环境；这些字段不得作为第一版入场/退出过滤条件。

已确认资金口径：

| 项目 | 口径 |
|---|---|
| 总资产 | 100 亿 |
| 最大持仓数量 | 200，既是每股最大市值分母，也是同时持仓股票数上限 |
| 每个股票最大市值 | 总资产 / 最大持仓数量 = 5000 万 |
| 单次买入目标市值 | 每个股票最大市值 * 33% = 1650 万 |
| 仓位不足阻止买入 | 不因现金或组合仓位不足阻止买入；若同时持仓股票数达到 200，则新开仓被阻止并记录 |
| 已有持仓加仓 | 即使同时持仓数已达到 200，已有持仓仍允许按规则加仓 |

## 当前版封板清单

当前版封板对象是 `baoma_v1` 真实回测基线，不是策略收益封板，也不是券商级成交仿真封板。封板后允许进入真实策略研究：用固定股票池回测结果观察策略适合和不适合的环境。

封板证据来自 `reports/baoma-v1-fixed-sample-2023-2024/`：

| 项目 | 结果 |
|---|---:|
| 原始固定股票池 | 800 |
| 自动过滤后回测标的 | 769 |
| 保留但带 warning | 34 |
| 自动剔除 | 31 |
| 已平仓交易 | 3567 |
| 期末未平仓 | 104 |
| 生命周期事件 | 19089 |
| 生命周期快照 | 66395 |

当前可用能力：

| 编号 | 能力 | 当前状态 | 说明 |
|---|---|---|---|
| `B-01` | 策略信号合同 | 已完成 | `baoma_entry`、`baoma_add_on`、`baoma_ma60_stop`、`baoma_ma25_profit_exit` 均输出稳定 `TradeIntent`、`reason_code`、`checks` 和 `attribution`。 |
| `B-02` | 生命周期执行 | 已完成首版 | 支持开盘买入/加仓、尾盘清仓、T+1 lot、曾盈利禁加仓、5%/15% 分批减仓、成本重算、挂起清仓和期末未完成。 |
| `B-03` | baoma 专用执行入口 | 已完成 | RunPlan/CLI 可选择 `baoma_v1_business`；执行顺序固定为 `Pending Full Exit > Exit Watch > Full Exit > Scale-Out > Add-On > Entry`。 |
| `B-04` | 固定股票池 | 已完成 | `examples/stock-pools/baoma-hs300-csi500-20260607.csv` 固定 800 只，RunPlan 只引用文件，不在运行时动态换池。 |
| `B-05` | 数据预热和指标覆盖 | 已完成 | 回测前自动 data preflight；优先读缓存，缺什么补什么；`ok/warning` 进入回测，`error` 自动剔除；报告写入过滤统计。 |
| `B-06` | 交易样本报告 | 已完成首版 | 输出 `trades.json`、`trade_lifecycle.json`、`trade_review.json`、`report.zh.md`，可查看完整交易、生命周期、分批减仓、拒绝/挂起和未平仓。 |
| `B-07` | AI 可读审计包 | 已完成首版 | 输出 `signal_audit.json`、`execution_audit.json`、`result_diagnostics.json`、`environment_fit.json`、`strategy_environment_profile.json`；`execution_audit` 已包含 `BAOMA_SCALE_OUT_*` 分批减仓事件。 |
| `B-08` | 环境发现框架 | 已完成首版 | `environment_fit` 和 `strategy_environment_profile` 已能消费 baoma 交易样本；当前环境因子信息量仍偏少，后续按因子扩展。 |
| `B-09` | 最小真实回测样本 | 已完成 | 固定池 2023-2024 真实回测已跑通，作为当前 baoma 回测基线。 |

当前已知待接/近期修复项：

| 编号 | 缺口 | 影响 | 下一步处理原则 |
|---|---|---|---|
| `G-01` | baoma 专用 runner 未完整接入停牌/涨跌停成交约束 | 个别买入拒绝、卖出失败和挂起清仓原因可能低估 | 等需要精确解释执行失败时再接；不能用当前结果评价涨跌停卖不出风险。 |
| `G-02` | 成本、税费、滑点尚未完全驱动 baoma 生命周期净口径 | 当前更适合作为前复权价差和交易样本分析，不适合当作真实资金收益结论 | 费用继续保留为配置项；后续从同一批成交记录派生毛/净视图，不单独重跑策略。 |
| `G-03` | 期末强制清仓视图和剔除未完成视图仍需独立报告化 | 当前能看到 104 个期末未平仓，但双视图口径还不够清晰 | 进入稳定性分析前补；当前不要把未平仓混入完整交易胜率结论。 |
| `G-04` | 环境因子还不够有区分度 | 当前环境报告能跑，但分组主要集中在少数字段，不能充分回答牛市/震荡/熊市适配 | 下一阶段只补环境因子，不重建归因框架。 |
| `G-05` | 归因 reference 准备入口 | 已新增 `att-prepare-attribution-reference` 第一版，从已准备好的全 A 日频基础表生成 `reference.json`、`reference_values.parquet` 和 `metadata.json`；Tushare 大规模拉取后续接入该入口前置数据源 | 当前第一版先固化计算口径、分位桶、固定解释桶和异常记录，不在命令内强行联网拉取。 |
| `G-06` | Tushare reference 前置数据源 | 已新增 `att-prepare-attribution-reference --provider tushare`，可拉取 daily、daily_basic、stock_basic、suspend_d、namechange 并合成 reference 输入表；历史 ST 优先基于 namechange 有效区间判断 | 申万一级行业可通过 `--fetch-industry-memberships` 显式逐股缓存并按有效区间合并；默认不开启，避免全 A 首次准备时调用量过大。 |
| `G-05` | 原始入场价与分批减仓后的剩余成本口径拆分 | 已修复；`ClosedTrade.entry_price` / `original_entry_price` 保留首笔入场价，`remaining_cost_basis_at_exit` 单独记录最终清仓前剩余成本 | `300803.SZ` 这类减仓后剩余成本为负的交易不再显示为负入场价；负值只出现在剩余成本字段，用于解释成本已被分批卖出覆盖。 |
| `G-06` | 分批减仓事件作为可核验交易事件完整落盘 | 已修复；`BAOMA_SCALE_OUT_*` 已进入 `execution_audit.json`、`trade_lifecycle.json` 和人工核验样本 | full run 中 `execution_audit` 已包含分批减仓事件，并记录成交日、成交价、成交数量、事件后持仓数量和事件后剩余成本。 |

当前明确暂不做：

- 不做参数自动优化。
- 不做历史成分股动态切换。
- 不做券商级现金分红、送转、未复权真实持仓核算。
- 不把环境发现字段作为第一版买卖过滤条件。
- 不继续扩展卖飞原因，除非它影响交易记录可信度。
- 不继续大规模扩展报告工具，除非是为了让已有交易样本更容易被 AI 或人工读取。

当前版封板结论：

- 可以开始用 `baoma_v1` 固定池真实回测结果开发和复盘。
- 当前结果可以用于发现策略入场/退出样本特征、亏损集中点和初步环境候选。
- 当前结果不用于证明策略收益率，也不用于判断真实现金账户收益。
- 下一阶段主线应从“继续搭框架”切到“用真实回测结果验证策略适合的环境”。

## 日线归因封板记录

本节封板的是 `baoma_v1` 的日线级交易反查归因框架，不是策略收益封板，也不是新因子封板。封板后，当前阶段不再继续扩展卖飞原因、行业报告形态或日线矩阵展示；下一阶段从新增因子开始。

封板报告来自：

```text
reports/_tmp-baoma-100-industry-attribution-check/
  baoma-v1-100-industry-expanded-attribution-check-2023-2024/
    attribution_summary.json
    attribution_summary.zh.md
    attribution_matrix.json
    trade_attribution.json
```

当前样本口径：

| 项目 | 结果 |
|---|---:|
| 固定样本股票 | 100 |
| 自动过滤后回测标的 | 98 |
| 完整交易 | 583 |
| 入场事件 | 583 |
| 加仓事件 | 395 |
| 出场事件 | 583 |
| 盈利交易 | 270 |
| 亏损交易 | 313 |
| 胜率 | 46.31% |
| MA60 止损退出 | 319 |
| MA25 止盈退出 | 264 |

当前已经可用的归因链路：

| 能力 | 状态 | 说明 |
|---|---|---|
| 交易后反查归因 | 已封板 | 先由买卖策略和生命周期生成交易记录，再按交易记录反查入场、加仓、出场和卖出后 5 日状态。 |
| 因子选择 | 已封板 | `analysis.attribution.include` 控制本次启用因子，系统补全 `not_include`，避免不知道哪些因子有但没用。 |
| 缺失值语义 | 已封板 | 指标或环境缺失必须记录为 missing，不得补成 `false`、`0` 或默认分桶。 |
| 个股日线归因 | 已封板 | 已覆盖个股 MA、价格相对 MA、KDJ、DEA 上水天数等入场/加仓/出场反查字段。 |
| 大盘日线归因 | 已封板 | 已覆盖沪深300等指数趋势、KDJ 和相关入场/出场环境字段。 |
| 行业日线归因 | 已封板 | 已覆盖行业 KDJ、行业 MA 趋势、行业相对沪深300强弱。 |
| 归因矩阵 | 已封板 | 已能按入场、加仓、止损入场时机、止盈后 5 日卖飞线索输出分桶矩阵。 |
| 中文总览报告 | 已封板 | `attribution_summary.zh.md` 已把交易概览、行业归因专章、重点结论卡片和矩阵摘要集中展示。 |

当前报告必须优先看的问题：

| 问题 | 当前报告入口 |
|---|---|
| 这个策略入场时什么环境胜率和平均收益更好 | `重点结论卡片 / 入场环境线索` |
| 亏损交易集中在哪些入场时机 | `重点结论卡片 / 负向入场线索` 和 `止损入场时机` |
| 加仓在什么行业/DEA/KDJ 状态下更有效 | `重点结论卡片 / 加仓环境线索` 和 `行业归因专章 / 加仓行业相对强弱` |
| 止盈后是否卖飞 | `止盈后卖飞概览` 和 `止盈后 5 日卖飞线索` |
| 行业是否影响策略土壤 | `行业归因专章` |

当前明确不从报告中做的结论：

- 不把出场时仍在 MA60 上方、指数多头等后验结果当成有效买入因果线索。
- 不用止盈退出本身反推“退出环境更好”，因为止盈是策略动作导致的结果，容易先射箭后画靶。
- 不根据 100 只样本直接修改 Baoma 买卖规则；这些结果只作为下一阶段因子和大样本验证的候选线索。
- 不用当前结果评价组合总收益、真实资金曲线或真实券商成交收益。

下一阶段新增因子边界：

| 因子方向 | 第一批候选 | 说明 |
|---|---|---|
| 周线个股因子 | `symbol.kdj.week.j_bucket`、`symbol.kdj.week.state` | 用于观察日线入场叠加周线强弱时，胜率和亏损集中是否变化。 |
| 周线行业因子 | `industry.kdj.week.j_bucket`、`industry.kdj.week.state` | 用于观察行业周线是否比行业日线更能解释策略土壤。 |
| 周线指数因子 | `market.hs300.kdj.week.j_bucket`、`market.csi500.kdj.week.j_bucket` | 用于观察大盘周线是否过滤掉日线噪音。 |
| 行业细化因子 | 行业 MA 周期、行业相对强弱周期、行业强弱连续天数 | 在周线 KDJ 后再接，避免一次性把矩阵切太碎。 |
| 市值因子 | 总市值分桶、流通市值分桶 | 同时保留绝对金额桶和全 A 历史横截面分位桶；用于观察策略是否更适合大/中/小市值股票，并支持未来扩到全 A 后跨 run 比较。 |
| 估值因子 | PE、PE_TTM、PB 分桶 | 同时保留绝对值桶和全 A 历史横截面分位桶；负 PE/PE_TTM 进入单独亏损估值桶，缺数据才是 `missing`；PB 小于等于 0 进入 `non_positive`。 |
| 波动率因子 | 20 日收益波动率、60 日收益波动率、ATR 百分比、近 20 日最大振幅 | 同时保留个股绝对波动和相对申万一级行业波动；固定止盈/止损对不同波动股票敏感，优先作为后验归因，不进入买卖规则。 |
| 行业适配因子 | 申万一级行业名称、行业自身波动桶、个股相对行业波动桶 | 用于观察策略是否适合某些一级行业，以及固定减仓对高/低波动行业是否过紧或过松。 |
| 流动性因子 | 成交额、20 日平均成交额、成交额分位、换手率、量比、相对行业成交活跃度 | 用于观察交易结果是否集中在流动性过低或过高的入场环境；先作为归因，不作为入场过滤。 |
| 价格位置因子 | 距 MA25/MA60、距近 20 日高点、距近 60 日高点 | 和当前 baoma 入场结构接近，先进入宽表和字段索引，避免直接放入环境矩阵造成重复解释。 |
| 止盈适配因子 | 固定 5% 约等于多少个 ATR | 底层计算为 `5% / ATR%`，用于判断固定 5% 止盈对不同波动股票是否过紧或过松。 |
| 止损适配因子 | 入场价距离 MA60 的 ATR 倍数 | 公式为 `(实际入场成交价 - 入场信号日 MA60) / 入场信号日 ATR`，用于观察止损空间是否和个股真实波动匹配。 |

新增因子先产出 `Attribution Field Index` 和 `Attribution Wide Sample`：每笔 completed trade 一行，同时保留原始数值和分桶值。`environment_fit` 只消费筛选后的默认字段，避免一次性把组合矩阵切碎。

默认进入 `environment_fit` 的新增字段总览：

| 因子 | 字段形态 | 默认进入 `environment_fit` | 说明 |
|---|---|---:|---|
| 申万一级行业名称 | bucket/category | 是 | 用于回答策略是否适合某些一级行业。 |
| 个股 ATR 行业内分位桶 | bucket | 是 | 同一交易日、同一申万一级行业内按 ATR 百分比做 5 档分位，优先解释固定 5% 减仓在高/低波动股票中是否过紧或过松。 |
| 个股 ATR / 行业 ATR 中位数桶 | bucket | 是 | 保留原始倍数并按固定解释桶分组，用于观察个股波动是否显著高于/低于本行业。 |
| 行业自身波动桶 | bucket | 否 | 已实现行业指数 ATR%、20/60 日收益波动、距 60 日高点；进入宽表和字段索引，先不默认进入组合矩阵，避免与行业名称重复切样本。 |
| 总市值绝对金额桶 | bucket | 否 | 已实现，按 0-100 亿、100-300 亿、300-600 亿、600-1000 亿、1000-1500 亿、1500 亿以上分桶。 |
| 总市值全 A 横截面分位桶 | bucket | 否 | 已实现；用于跨股票池、跨 run 比较大/中/小市值适配，第一版不默认切分。 |
| 流通市值绝对金额桶 | bucket | 否 | 已实现，按 0-100 亿、100-300 亿、300-600 亿、600-1000 亿、1000-1500 亿、1500 亿以上分桶。 |
| 流通市值全 A 横截面分位桶 | bucket | 否 | 已实现；用于跨股票池、跨 run 比较流通盘适配，第一版不默认切分。 |
| PE/PE_TTM/PB 原始值 | raw numeric | 否 | 只进宽表，用于核验和重切分桶。 |
| PE_TTM 桶 | bucket | 是 | 负值单独进亏损估值桶；缺数据才是 `missing`。 |
| PE 桶 | bucket | 否 | 第一版只进宽表和字段索引，避免 PE 和 PE_TTM 同时默认切分。 |
| PB 桶 | bucket | 否 | 第一版只进宽表和字段索引；PB 小于等于 0 单独进 `non_positive`。 |
| ATR 百分比桶 | bucket | 是 | 固定止盈/止损适配的核心波动口径。 |
| 20 日收益波动率桶 | bucket | 否 | 先进入字段索引，和 ATR 百分比做候选对比。 |
| 60 日收益波动率桶 | bucket | 否 | 先进入字段索引，用于观察较慢波动环境。 |
| 近 20 日最大振幅桶 | bucket | 否 | 先进入字段索引，用于观察极端振幅。 |
| 固定 5% 对应 ATR 倍数桶 | bucket | 是 | 直接解释固定 5% 止盈是否太紧或太松。 |
| 入场价距 MA60 的 ATR 倍数桶 | bucket | 是 | 直接解释止损空间是否贴近 MA60。 |
| 20 日平均成交额分位桶 | bucket | 否 | 已实现，先进入字段索引，避免流动性和市值同时默认切分造成样本过碎。 |
| 成交额、换手率、量比、成交额相对20日均额、行业内成交额分位 | raw/bucket | 否 | 已实现，进入宽表和字段索引，后续按覆盖率和归因效果决定是否默认展示。 |
| 距近 20 日高点/近 60 日高点 | raw/bucket | 是 | 用于观察入场是否集中在追高或突破后回落；默认进入 `environment_fit`。 |
| 近 20 日/60 日区间位置 | raw/bucket | 是 | 用于观察入场处在阶段区间底部、中部还是顶部；默认进入 `environment_fit`，并与距高点字段一起检查样本切分风险。 |
| 距 MA25/MA60 | raw/bucket | 否 | 和 baoma 入场结构及止损适配接近，先进入宽表和字段索引，不默认进入 `environment_fit`。 |
| 个股周线 KDJ 状态 | category | 是 | 已实现；使用信号日前最近一根已完成周线，默认进入 `environment_fit`。 |
| 个股周线 KDJ J、周线均线趋势、周线收盘价相对 MA20 | raw/bucket | 否 | 已实现，进入宽表和字段索引，先不默认切分。 |
| 行业周线 KDJ 状态 | category | 是 | 已实现；使用申万一级行业指数信号日前最近一根已完成周线，默认进入 `environment_fit`。 |
| 行业周线 KDJ J、行业周线均线趋势、行业周线相对强度 | raw/bucket | 否 | 已实现，进入宽表和字段索引，行业周线相对强度按同周行业指数 4 周收益分位计算。 |

已确认的下一批五类因子 backlog：

| backlog | 因子方向 | 第一批字段候选 | 状态 |
|---|---|---|---|
| `NEXT-01` | 大盘环境因子 | 沪深300/中证500日线趋势、周线 KDJ/MACD、20/60 日指数波动率、个股来源指数环境、市场宽度 | 待实现；先用现有 92 字段完成归因解读封板，再开始。 |
| `NEXT-02` | 亏损/盈利质量因子 | `loss_making`、扣非净利润同比、营收同比、ROE、毛利率、净利率、经营现金流质量 | 待实现；需要新增财务数据源，不依赖实时 PE/PB。 |
| `NEXT-03` | 相对强弱/动量因子 | 个股 20/60 日收益率、相对沪深300/中证500强弱、相对所属行业强弱、行业相对大盘强弱、20/60/120 日新高 | 待实现。 |
| `NEXT-04` | 成交活跃度趋势因子 | 5/20 日换手均值、成交额连续放大/萎缩、成交额相对 60 日均额、放量突破/缩量回踩 | 待实现。 |
| `NEXT-05` | 更细出场后验因子 | 最大浮盈/浮亏对应 ATR 倍数、是否达到 10%/15%、止盈后继续上涨、止损后反弹、卖飞幅度、错杀幅度 | 待实现；只用于路径诊断，不能作为入场环境因子。 |

现有 92 字段归因解读封板记录：

| 项目 | 封板内容 |
|---|---|
| 报告入口 | `reports/baoma-v1-fixed-sample-2023-2024/full_entry_scope_environment_fit_review/environment_attribution_review.zh.md`、`strategy_stage_attribution_review.zh.md` |
| 数据口径 | 只使用已落盘 `attribution_wide_samples.json`、`attribution_field_index.json`、`environment_fit.enriched.json`；不重新拉行情，不重新跑策略。 |
| 样本口径 | 3567 笔 completed trades；默认 `environment_fit` 字段 19 个，字段索引 92 个。 |
| 解读边界 | 入场环境只看信号日/入场时可见字段；`trade.path.*` 只用于路径诊断；MA25/MA60 退出原因不得反推为利润/亏损原因。 |
| 当前结论用途 | 用于决定下一批归因因子和人工复盘重点；不直接输出参数优化建议。 |

下一阶段新增因子的实现规则：

1. 新因子先进入因子注册和 `include/not_include`，不能直接写死进报告。
2. 新因子必须说明 timing、owner、dependencies、missing policy 和是否策略专属。
3. 新因子先通过交易记录反查，不进入第一版买卖策略。
4. 新因子先用当前 100 只样本做缺失检查，再扩到更大固定股票池。
5. 矩阵新增必须服务于“入场胜率/收益、加仓成败、止损入场时机、止盈后卖飞”这四类问题。
6. 市值、估值、波动率、行业适配、流动性、价格位置、止盈适配和止损适配因子已经确认要做，但先进入宽表和字段索引，再选择少量默认字段进入 `environment_fit`。
7. PE/PB、市值和流动性等来自数据提供方的字段必须使用历史数据快照按入场信号日对齐，不得在报告层读取实时数据；分位桶默认基于全 A 历史横截面参考数据计算，回测交易范围仍由 RunPlan 指定股票池决定。
8. 历史基本面和流动性字段允许有限向前取最近可用值，最多 5 个交易日；超过 5 个交易日仍记为 `missing`。
9. 任何向前取值都必须在宽表和字段索引里记录 `asof_date` 和 `staleness_trading_days`，归因报告需要能看出该样本使用的不是信号日同日数据。
10. 全 A 横截面分位参考集合先只包含沪深主板、创业板、科创板，并需要按历史日期排除 ST、停牌当日、上市未满 60 个交易日、北交所和不可交易普通股；ST 判断必须使用 `Historical ST Status`，不能用当前股票名或当前 `stock_basic` 名称回填历史。
11. `Historical ST Status` 数据源优先级为：优先使用历史 ST 状态接口快照；如果接口不可用或权限不足，再用历史更名记录的 `name/start_date/end_date/change_reason` 区间重建 ST 状态，并在 snapshot provenance 里记录来源和局限。
12. 上市未满 60 个交易日、ST、停牌、北交所或不可交易普通股等排除规则只影响全 A 分位参考集合，不自动改变 RunPlan 指定的回测股票池。
13. 所有异常情况都必须记录为 `Attribution Data Exception`，包括但不限于 reference 集合排除、字段缺失、超过 5 个交易日的历史取值、数据源不可用、历史 ST 状态来源降级、行业映射缺失、分位参考样本不足和非正/负估值特殊桶。
14. 异常记录采用两层结构：每个字段保留自己的 `exception_code`，用于机器筛选；每笔交易保留 `attribution_exceptions[]` 汇总列表，用于人工样本核验和报告摘要。
15. 第一版全 A 横截面分位桶统一使用 5 档：`p0_p20`、`p20_p40`、`p40_p60`、`p60_p80`、`p80_p100`；原始 percentile 数值仍进入宽表，后续可重切分桶。
16. PE、PE_TTM、PB 的全 A 分位只对有效正值计算；PE/PE_TTM 负值进入 `negative`，缺失进入 `missing`；PB 小于等于 0 进入 `non_positive`，缺失进入 `missing`。
17. ATR 百分比、20 日收益波动率、60 日收益波动率、近 20 日最大振幅等波动因子第一版也使用全 A 横截面 5 档分位桶，并在宽表保留原始值；固定绝对阈值桶后续按需要再补。
18. 流动性因子第一版同时保留固定解释桶和分位桶：20 日平均成交额使用全 A 横截面 5 档分位桶；当日成交额、换手率、量比、当日成交额/20 日均额使用固定解释桶；行业内成交额分位按同日同申万一级行业内 5 档分位计算。成交额使用历史实际成交额，换手率和量比优先来自历史 `daily_basic`，缺失时记录 `missing`，不在报告层用成交量和流通股本临时拼出口径。
19. 个股相对行业波动同时保留原始比值和行业内分位桶：原始值使用 `symbol_atr_pct / industry_median_atr_pct`，默认进入 `environment_fit` 的桶使用同日同申万一级行业内 ATR 百分比 5 档分位。
20. 固定 5% 止盈适配因子使用固定解释桶，不使用分位桶；原始值为 `5% / ATR%`，桶为 `<1 ATR`、`1-2 ATR`、`2-3 ATR`、`>=3 ATR`。
21. 入场价距离 MA60 的 ATR 倍数使用固定解释桶，不使用分位桶；默认字段 `entry.price_position.ma60_atr_multiple_bucket` 的原始值为 `(实际入场成交价 - 入场信号日 MA60) / 入场信号日 ATR`，用于识别信号次日开盘下杀后是否已经贴近或跌破 MA60；宽表另保留 `entry.price_position.signal_close_ma60_atr_multiple_bucket`，原始值为 `(入场信号日 close - 入场信号日 MA60) / 入场信号日 ATR`，用于核验信号本身的位置。
22. 距近 20 日高点和近 60 日高点默认进入 `environment_fit`，使用入场信号日 close 计量，使用固定解释桶，不使用分位桶；宽表保留原始距离百分比 `signal_day_close / rolling_high - 1`，桶为 `at_high`（0% 到 -1%）、`near_high`（-1% 到 -3%）、`moderate_pullback`（-3% 到 -8%）、`deep_pullback`（-8% 到 -15%）、`far_from_high`（小于 -15%）。全 A 参考快照按信号日对齐，`entry_date` 仅保留为实际成交日。
23. 近 20 日和 60 日区间位置默认进入 `environment_fit`，使用入场信号日 close 计量；原始值为 `(signal_day_close - rolling_low) / (rolling_high - rolling_low)`，桶为 `bottom`（0-20%）、`lower_mid`（20-40%）、`middle`（40-60%）、`upper_mid`（60-80%）、`top`（80-100%）。当 `rolling_high == rolling_low` 时记录 `flat_range` 异常，不默认填充。
24. 行业适配使用入场信号日的历史申万一级行业；行业映射不套用 5 个交易日 staleness 限制，而是按历史行业关系有效区间判断，`start_date <= signal_date <= end_date` 时视为有效。若只有变更点数据，则最近一次变更后的行业有效到下一次变更前；完全找不到覆盖区间时记录 `industry_missing`。当数据源只给出单条无 `out_date` 的未来行业区间、且信号日早于该区间 `in_date` 时，可以通过 `--backfill-missing-industry-memberships` 显式启用前推填充；前推结果必须记录 `industry_membership_backfilled`，不得静默当作原始历史行业。
25. `environment_fit` 第一版默认只输出入场前或入场时可见因子的单因子统计和白名单二因子组合；三因子及以上组合先留给字段索引、样本 drilldown 或后续专项报告，避免默认矩阵样本切分过碎。第二批归因字段加入交易路径诊断和入场信号强度归因：交易路径字段包括 `trade.path.holding_days_bucket`、`trade.path.max_favorable_return_before_exit_bucket`、`trade.path.max_adverse_return_before_exit_bucket`、`trade.path.max_drawdown_from_peak_bucket`、`trade.path.first_profit_5pct_days_bucket`；这些是事后路径结果，只能用于解释交易如何结束，不能进入 `environment_fit` 排名，也不能当作入场可见因子。入场信号强度字段包括 `entry.signal_strength.dea_waterline_age_trading_days_bucket`、`entry.signal_strength.dea_value_bucket`、`entry.signal_strength.macd_bar_bucket`、`entry.signal_strength.dif_dea_distance_bucket`、`entry.signal_strength.ma25_above_ma60_spread_bucket`、`entry.signal_strength.ma60_slope_20d_bucket`、`entry.signal_strength.signal_candle_body_bucket`、`entry.signal_strength.signal_upper_lower_shadow_bucket`，这些字段可以进入 `environment_fit`。
26. 第一版二因子组合白名单为：申万一级行业 x 个股相对行业波动桶、申万一级行业 x 行业周线 KDJ 状态、申万一级行业 x 固定 5% 对应 ATR 倍数桶、申万一级行业 x 入场距 MA60 ATR 倍数桶、ATR 百分比桶 x 固定 5% 对应 ATR 倍数桶、ATR 百分比桶 x 入场距 MA60 ATR 倍数桶、个股行业内 ATR 分位 x 个股周线 KDJ 状态、个股周线 KDJ 状态 x 行业周线 KDJ 状态、流通市值分位桶 x 20 日平均成交额分位桶、距 20 日高点桶 x 20 日区间位置桶、距 60 日高点桶 x 60 日区间位置桶；PE/PB 先只进宽表和字段索引，PE_TTM 作为第一版默认估值主轴。`trade.exit.reason` x 入场因子白名单组合单独作为 `outcome_diagnostic`，用于回答止损/止盈分别在哪些入场环境高发；它不是 `environment_fit` 组合，不参与最佳/最差环境排名，也不自动生成过滤或参数优化建议。
27. `environment_fit` 第一版低样本阈值为：单因子分组少于 10 笔、二因子组合少于 20 笔时标记 `low_sample`。低样本分组仍保留在 JSON 中，但中文报告首页最佳/最差结论候选不采用低样本分组。
28. `Attribution Wide Sample` 同时输出 JSON 和 CSV：JSON 保留嵌套字段、exception、asof、provenance，供程序和 AI review 使用；CSV 使用扁平字段名，供人工用 Excel/WPS/脚本筛选。
29. 新增归因产物文件名固定为：`attribution_wide_samples.json`、`attribution_wide_samples.csv`、`attribution_field_index.json`、`attribution_field_index.zh.md`。
30. 第一版新增归因产物通过独立命令从已落盘 run artifacts 和全 A 参考快照生成，不直接塞进 `run_plan` 主执行流程；这样可以回填旧 run，并降低回测执行阶段的数据依赖和耗时。
31. 独立命令拆成两步：`att-attribution-wide-samples` 负责生成 `Attribution Wide Sample` 和 `Attribution Field Index`；`att-environment-fit --wide-samples ...` 负责从宽表选择默认字段并刷新 `environment_fit`。
32. `att-attribution-wide-samples` 只消费已存在的全 A 参考快照和 run artifacts；如果所需快照缺失，命令应失败并提示先运行数据准备流程，不在归因命令中自动联网拉取大规模全 A 数据。
33. 新增全 A 参考数据准备命令 `att-prepare-attribution-reference`：负责拉取或复用全 A daily_basic、历史 ST 状态或 namechange 降级数据、历史行业分类、停牌/上市天数/板块过滤所需参考数据，并计算保存全 A 横截面分位参考；该命令不跑回测，也不生成策略适配结论。
34. `att-prepare-attribution-reference` 显式接收 `--start-date` 和 `--end-date`；日期范围需要覆盖 run 的 warmup 起点到回测结束日期，以支持 ATR、20/60 日收益波动率、近 20/60 日高低点等窗口指标。归因宽表只对实际入场信号日输出样本，warmup 区间仅用于计算参考指标。
35. 全 A 参考快照存放在 `data/snapshots/attribution_reference/<reference_universe>/<start_date>_<end_date>/`，例如 `data/snapshots/attribution_reference/full_a_main_chinext_star/2022-10-01_2024-12-31/`；该目录属于 `Data Snapshot`，不属于 run-specific `reports/`。
36. 全 A 参考快照中表格数据使用 Parquet，metadata/provenance/参数/字段版本/异常统计使用 JSON。
37. 全 A 横截面 percentile reference 在 `att-prepare-attribution-reference` 阶段预计算并保存；归因宽表生成阶段只读取并 join 已保存的 percentile/bucket，不临时重算分位。
38. 当需要严格全 A 横截面时，`att-prepare-attribution-reference` 必须使用 `--reference-fetch-scope all` 拉取全 A 行情/基础字段，同时用 `--emit-run-entry-scope` 只输出本次 run 实际入场样本；不能用 run 股票池白名单作为 reference 截面。
39. 第一版参考字段版本为 `attribution_reference_fields.v1`；metadata 必须记录字段清单、计算公式、分桶规则、reference universe 过滤规则、历史 ST 数据源策略、percentile 计算方法、生成时间和数据范围。后续改桶或新增字段时升级版本，不覆盖 v1 语义。
40. Percentile 使用平均名次法处理同值，等价于 `rank(pct=True, method="average")`；同值样本获得相同 percentile。5 档桶边界为 `[0,0.2]`、`(0.2,0.4]`、`(0.4,0.6]`、`(0.6,0.8]`、`(0.8,1.0]`。每个 percentile/bucket 记录 `reference_count`；某日某字段有效参考样本数少于 100 时标记 `reference_low_count`。
41. 如果回测交易样本的入场信号日股票因停牌等原因被全 A reference universe 排除，宽表仍保留该交易样本；对应 percentile/bucket 字段标记 `reference_excluded_suspended` 等排除原因，不给分位桶。原始指标值是否可用按各字段自己的历史取值规则处理。
42. 如果回测交易样本的入场信号日股票处于历史 ST 状态，宽表仍保留该交易样本；全 A percentile/bucket 字段标记 `reference_excluded_st`，交易级 `attribution_exceptions[]` 汇总该异常。
43. `Attribution Wide Sample` 第一版只包含 completed trades，对齐 `environment_fit` 的利润归因口径；blocked/rejected/opportunity 样本后续做单独 opportunity attribution，不混入同一张宽表。
44. 期末强制清仓样本进入 `Attribution Wide Sample`，但标记 `exit_type=forced_end_liquidation`，默认不进入 `environment_fit` 首页最佳/最差结论候选；自然退出 completed trades 默认进入。Open-position excluded 样本不混入 completed-trade 宽表，后续单独做 open position attribution。
45. `Attribution Wide Sample` 保留收益与持有期解释列：`return_pct`、`net_pnl`、`gross_pnl`（如已有毛口径）、`return_on_entry_value`、`holding_days`、`max_favorable_excursion_pct`、`max_adverse_excursion_pct`。`environment_fit` 第一版排序仍主要使用 win rate、average return、net PnL 和 return on entry value。
46. `max_favorable_excursion_pct` 和 `max_adverse_excursion_pct` 第一版使用持有期日线 high/low 路径计算：MFE 为 `(holding_high_max - entry_price) / entry_price`，MAE 为 `(holding_low_min - entry_price) / entry_price`。若 high/low 缺失则记录 missing，不退化为 close 路径。
47. MFE/MAE 持有期范围包含实际入场成交日到退出成交日之间的整日 high/low；由于日线无法精确切分开盘成交前后路径，metadata 必须标记为 `daily_bar_path_approximation`。
48. 从宽表生成的增强版 `environment_fit` 第一版写新文件，不覆盖旧口径：`environment_fit.enriched.json` 和 `environment_fit.enriched.zh.md`。验证稳定后再决定是否替换默认 `environment_fit.json`。
49. `attribution_field_index.zh.md` 首先作为可用性审计报告：先展示覆盖率低和异常最多的字段，再单列默认进入 `environment_fit` 的字段，最后列候选但未默认进入的字段。每个字段展示覆盖率、missing 数、exception top codes、主要桶分布和代表 `trade_index` refs。
50. 字段索引代表样本每个字段每个主要桶最多保留 5 条 `trade_index`，优先选择最高正收益、最大亏损、最大净 PnL、最大负 PnL 和中位收益附近样本，避免随机样本不利于核验。
51. `environment_fit.enriched.zh.md` 首页按高胜率环境候选、高净 PnL 贡献环境候选、亏损集中环境候选、固定止盈/止损适配归因、低样本和数据异常提醒组织；当前阶段只做归因和证据展示，不输出 deterministic risk label，也不自动改策略参数。固定止盈/止损适配归因只展示分组交易数、胜率、平均收益、净 PnL、MFE/MAE 中位数、止损退出占比等事实，不写“太紧/太松/应该调整”的判断结论。
52. 止损退出占比在每个归因桶内计算，分母为该桶自然退出 completed trades，分子为 `exit_reason` 属于 MA60 止损的交易数；期末强制清仓样本不进入默认分母。
53. 固定 5% 分批减仓触发统计作为归因事实输出：`scale_out_5pct_trade_count`、`scale_out_5pct_trade_rate`、`scale_out_any_trade_rate`、`median_first_scale_out_days`、`median_mfe_pct`。默认分母为自然退出 completed trades，期末强制清仓单独标记。
54. `median_first_scale_out_days` 从实际入场成交日到第一笔 5% scale-out 成交日按交易日数计算；未触发 5% scale-out 的样本该字段为 missing，不用退出日替代。桶内中位数只对已触发 5% scale-out 的样本计算，并同时展示触发样本数。
55. `median_first_scale_out_days`、`holding_days` 等持续时间字段使用交易日数，优先读取 run artifact 或 prepared data 的交易日历；如果交易日历缺失，记录 `trading_calendar_missing`，不退化为自然日差。
56. `holding_days` 优先沿用现有 run artifact 中已可信的值；如缺失则按交易日历计算并标记来源 `computed_from_calendar`。若现有值与按交易日历计算值不一致，记录 `holding_days_mismatch`，不静默覆盖。
56. `Attribution Wide Sample` JSON 需要保留字段级或分组级 provenance，至少可追溯到 `trade_lifecycle.json`、`trade_review.json` 等 run artifact、attribution reference snapshot path/version、measurement date 和 factor timing；CSV 保持扁平字段，优先服务人工筛选。
57. `Attribution Wide Sample` CSV 中异常信息只扁平化保留每个字段的 `*.exception_code`、适用字段的 `*.asof_date` / `*.staleness_trading_days`，以及交易级 `attribution_exception_codes`（用 `;` 拼接）；完整 exception detail 只放 JSON。
58. `attribution_field_index.json` 同时作为机器可读字段目录和统计结果；每个字段包含 `field_key`、`label_zh`、`value_type`、`timing`、`scope`、`bucket_rule`、`default_in_environment_fit`、`source`、`missing_policy`、`coverage_stats`、`bucket_distribution` 和 `sample_refs`。
59. 字段 key 前缀按 timing/scope 命名：`entry.market_cap.*`、`entry.valuation.*`、`entry.volatility.*`、`entry.liquidity.*`、`entry.industry.*`、`entry.price_position.*`、`entry.profit_fit.*`、`entry.stop_fit.*`、`trade.outcome.*`、`trade.lifecycle.*`。入场时点因子统一放 `entry.*`，交易结果和生命周期字段放 `trade.*`。
60. `environment_fit.enriched` 默认字段和二因子组合由 `attribution_field_index.json` 声明：字段级 `default_in_environment_fit` 表示单字段默认是否进入，顶层 `environment_fit_default_fields` 汇总默认字段清单，顶层 `environment_fit_pair_whitelist` 声明默认二因子组合白名单。`att-environment-fit --wide-samples ...` 默认读取这些声明，并允许用 `--field` / `--pair` 做本次命令临时覆盖。
61. `att-environment-fit --wide-samples ...` 中 `--field` / `--pair` 默认追加到 `attribution_field_index.json` 声明的默认字段和默认白名单；只有显式传 `--replace-default-fields` 时才替换默认字段集合。

下一阶段 MACD/KDJ 因子口径：

| 因子 | 口径 | 说明 |
|---|---|---|
| MACD 归因柱 | `2 * (DIF - DEA)` | 归因展示和分桶使用中文股票软件常见 MACD 柱口径；内部指标快照里的 histogram 仍可作为原始计算输入。 |
| 日线 MACD 能量区间 | 使用信号日前一根已完成日线 | 入场、加仓、离场归因都不得使用未完成周期。 |
| 周线 KDJ / MACD 因子 | 使用信号日前最近一根已完成周线 | 例如周三触发信号时，只能使用上周五收完的周线，不能使用本周未完成周线。 |

MACD 能量区间第一版采用互斥分桶：

| 分桶 | 公式 | 中文含义 |
|---|---|---|
| `red_bar_wrapping_lines` | `MACD归因柱 > 0 AND MACD归因柱 > DIF AND MACD归因柱 > DEA` | 红柱为正，DIF 和 DEA 都在红柱体内。 |
| `red_bar_one_line_escape` | `MACD归因柱 > 0 AND exactly_one(DIF > MACD归因柱, DEA > MACD归因柱)` | 红柱为正，DIF/DEA 有且只有一根线高出红柱。 |
| `red_bar_two_line_escape` | `MACD归因柱 > 0 AND DIF > MACD归因柱 AND DEA > MACD归因柱` | 红柱为正，DIF 和 DEA 两根线都高出红柱。 |
| `green_bar_or_zero` | `MACD归因柱 <= 0` | 绿柱或零轴附近，不进入前三个红柱能量区间。 |
| `missing` | 任一必需字段缺失 | 缺失必须记录为 missing，不补默认值。 |

## 通用回测框架方向

`baoma_v1` 不能把框架带成单策略专用实现。当前确认的通用边界如下：

| 层 | 负责内容 | 不负责内容 |
|---|---|---|
| `Universe Selection` | 按 RunPlan 配置解析固定或随时间变化的候选标的 | 不在买入/卖出方法里查询或筛选成分股 |
| `Strategy Definition` | 定义 entry、exit、add-on、sizing 等策略决策 | 不负责股票池来源、行业/指数通用归因、报告分组 |
| `Execution Lifecycle` | 把 intent 转成成交、拒绝、挂起、lot、成本和完整交易 | 不从报告层反推成交状态 |
| `Attribution` | 在交易后基于本次 run 的 artifacts 反查入场、出场和环境状态 | 不重新拉取 Tushare，不用当前数据解释旧回测 |

新增策略时，目标路径是：

1. 新增或复用买入、卖出、加仓、仓位方法。
2. 在 RunPlan 中配置固定或动态股票池。
3. 在因子注册表中声明框架通用或策略专属归因因子。
4. 在 RunPlan 中通过 `include` 勾选本次要分析的因子。
5. 系统根据当前策略、数据、指标和 artifacts 自动计算 `not_include = applicable_factors - include`。
6. 交易先由策略和执行层生成，再由 `Artifact-Bound Attribution Lookup` 反查统一归因和策略专属归因。

当前最小实现已经接入 `analysis.attribution.include`：

```yaml
analysis:
  attribution:
    enabled: true
    include:
      - symbol.ma.price_above_ma25
      - market.hs300.bullish_trend
```

执行后会写出 `attribution_factor_selection.json`，并在 `snapshots.json.attribution_factor_selection` 中同步记录：

- `include`：本次配置或默认启用的因子。
- `not_include`：当前适用但未启用的因子，由系统补全。
- `factors`：当前适用因子的声明清单，包含 owner、timing、依赖、来源、缺失策略和是否 selected。
- `entry_attribution.runtime_include`：旧入场归因上下文实际参与计算的因子，和全局选择分开记录。

旧字段 `analysis.entry_attribution.factors` 暂时保留为兼容入口；新策略优先使用 `analysis.attribution.include`。

报告产物默认采用 AI 友好的 compact 落盘：

```yaml
output:
  artifact_detail: compact
  signal_audit_sample_limit: 200
```

- `result.json` 默认写 `attbacktrader.compact_result.v1` 摘要，不再持久化完整运行结果。
- `signal_audit.json` 默认写 `attbacktrader.compact_signal_audit.v1`，包含总数、分组计数、日期范围和前 N 条样本。
- `trade_lifecycle.json`、`trade_review.json`、`environment_fit.json`、`post_exit_analysis.json` 等下游分析仍基于内存里的完整交易和信号证据生成。
- 需要调试完整原始明细时，将 `output.artifact_detail` 改为 `full`。

归因因子分为两类：

| 类型 | 例子 | 规则 |
|---|---|---|
| 框架通用归因因子 | 入场均线多头、行业情况、指数情况、距离 MA25/MA60、出场时指数/行业/均线状态 | 多个策略可复用，作为 `Framework Attribution Factor` 注册 |
| 策略专属归因因子 | `baoma` 入场距离 MA60、DEA 上水周期天数、阴线入场结构 | 只对声明该因子的策略适用，作为 `Strategy Attribution Factor` 注册 |

每个归因因子必须有 `Attribution Factor Applicability Declaration`，至少说明：

- owner：框架或具体策略。
- timing：entry、exit、holding 或 post_exit。
- dependencies：需要的指标、行情、行业、指数或生命周期 artifact。
- applicable strategy/method：适用的策略或方法。
- source：来自策略 intent、执行生命周期，还是交易后 artifact-bound lookup。
- value type：boolean、numeric、category 或 text。
- missing policy：缺失值如何记录；缺失不能补成 false、0 或中性。

归因 timing 必须支持以下四类：

| timing | 作用 | 示例 |
|---|---|---|
| `entry` | 解释入场时环境和结构 | 入场均线多头、行业趋势、指数趋势、入场价距离 MA60 |
| `exit` | 解释出场时环境和结构 | 出场时是否跌破均线、指数是否转弱、行业是否走弱 |
| `holding` | 解释持有期间经历的环境和风险 | 持有期最大浮盈、最大回撤、期间指数环境、期间行业环境 |
| `post_exit` | 解释卖出后的后续走势 | 止损/止盈卖出后 5 天反弹、是否卖飞 |

这些 timing 使用同一套 `Attribution Factor Registry` 和 `Attribution Factor Selection`，不能为某个 timing 单独写一套报告逻辑。

动态股票池第一版采用配置化 manifest，不在策略运行时临时查成分股：

```yaml
data:
  universe:
    type: time_varying_manifest
    effective_unit: month
    manifest_file: examples/stock-pools/hs300-csi500-monthly-map.yaml
```

对应 manifest 显式映射月份和股票池文件：

```yaml
schema: attbacktrader.time_varying_stock_universe.v1
effective_unit: month
periods:
  2023-01:
    stock_pool_file: examples/stock-pools/hs300-csi500-202301.csv
  2023-02:
    stock_pool_file: examples/stock-pools/hs300-csi500-202302.csv
```

这个动态股票池 manifest 是 `Universe Selection` 输入，不是策略过滤条件。

归因样本边界：

| 样本类型 | 进入胜率/收益归因 | 进入哪里 |
|---|---|---|
| 完整买入并已清仓的交易 | 是 | completed trade attribution |
| 期末仍未平仓 | 否，除非启用期末强制平仓视图 | open-position evidence 或 forced end-liquidation view |
| 买入信号被拒绝 | 否 | opportunity / execution evidence |
| 清仓挂起且未完成 | 否 | lifecycle / pending-exit evidence |
| 分批减仓事件 | 否，不单独作为完整交易 | lifecycle event evidence |

期末未平仓通过 RunPlan 配置开关处理：

```yaml
execution:
  baoma:
    force_exit_at_end: true
```

- `false`：期末未平仓保留为 open position，不进入完整交易胜率/收益归因。
- `true`：按回测结束日收盘价生成 `Forced End Liquidation View`，并明确标记为人工期末处理，不是策略自然退出信号。
- 如果期末停牌、跌停或缺少结束日价格，不能伪造成已完成交易，需要记录 end-liquidation failure。

## 核心口径

### 决策阶段

已确认口径：

- 不是所有条件都组合判断。
- 入场条件只在当前标的没有持仓时使用。
- 加仓条件只在当前标的已有持仓、且没有进入离场观察或离场确认时使用。
- 离场条件只在当前标的已有持仓时使用。
- 一旦当前标的进入离场观察或满足离场确认，当天不再判断入场或加仓。
- 同一天发生离场后，不再重新入场；下一交易日可以作为新的交易生命周期重新判断入场。

决策顺序：

1. 没有持仓：只判断入场。
2. 已有持仓：先判断 MA60/MA25 离场观察和确认。
3. 如果存在离场观察或离场确认：不判断加仓。
4. 如果没有离场观察或离场确认：再判断分批减仓。
5. 如果没有离场、分批减仓、盈利后禁加仓等阻断：才判断加仓。

### 决策日与成交日

已确认口径：

- `T-1` 是信号观察日，只使用已经收盘的数据。
- `T` 是交易执行日。
- 买入和加仓：在 `T` 开盘价成交。
- 止损和止盈：如果 `T-1` 触发观察条件，并且 `T` 仍未收回，则在 `T` 尾盘成交。
- 最低持有期：买入或加仓当天不能卖出，至少持有 1 个交易日，也就是遵守 A 股 `T+1`；首次买入后最早在下一交易日尾盘卖出。
- 同一标的在 `T` 开盘发生买入或加仓后，`T` 当天跳过所有卖出判断，最早 `T+1` 再判断卖出。
- 第一版所有指标判断、交易收益、分批止盈、成本重算和费用/滑点模拟都基于前复权日线价格差。
- 第一版报告必须明确标记：这是前复权价差口径，不是严格现金分红、送转、未复权真实成交和完整公司行为核算口径。
- 第一版继续计算费用、税费和滑点，但必须标记为 `Adjusted Price Cost Simulation`：这是前复权成交金额上的成本敏感性模拟，不是券商真实现金扣费。
- 第一版继续用前复权价格模拟下单数量、1 手约束、T+1 可卖数量和分批减仓数量，但必须标记为 `Adjusted Price Quantity Simulation`：这是前复权名义数量模拟，不是券商真实股数。
- 指标不足 warmup 时不触发，不填默认值。

原因：原始规则写了“当天选昨日”和“开盘价买”，同时卖出写了“第二天尾盘卖出”。如果直接用当天收盘信号和当天收盘成交，会改变策略含义；如果允许买入当天卖出，也会违背 A 股 T+1 和最低持有期。

### 标的池

原始规则：

- 沪深300
- 中证500

已确认口径：

- 解释为“沪深300和中证500的成分股股票池”，不是直接交易指数。
- 第一版先使用固定股票列表跑通真实策略回测，不使用随时间变化的历史成分股快照。
- 固定股票列表可以来自当前沪深300和中证500成分股，也可以来自人工指定列表；RunPlan 必须记录具体 symbol 列表或引用文件。
- 第一版报告必须标注这是固定样本，存在幸存者偏差风险，不能当作严格历史成分回测结论。
- 如果后续要直接交易指数、ETF 或股指期货，需要单独定义资产类型和交易约束。

### 数据和指标

需要的可复用指标：

| 指标 | 周期 | 用途 | warmup 要求 |
|---|---|---|---|
| `ma60` | D | 入场过滤、止损观察 | 至少 60 根日线 |
| `ma25` | D | 盈利后的止盈观察 | 至少 25 根日线 |
| `macd` | D | DEA 上水周期入场过滤 | 至少 MACD warmup |

指标层只计算数值，例如 `ma60`、`ma25`、`macd_signal`。下面这些不是指标计算结果，而是策略/归因层的判断：

- `symbol.price_above_ma60`
- `symbol.yesterday_bearish_candle`
- `symbol.macd.dea_recent_waterline`
- `position.ever_profitable`
- `position.scale_out_stage`

## 买入选股

在交易日 `T` 开盘前，用 `T-1` 的收盘数据判断：

| 条件 | 推荐实现口径 | 触发值 |
|---|---|---|
| 收盘价在 MA60 上方 | `close[T-1] > ma60[T-1]` | true |
| MACD DEA 最近上水 | `dea[T-1] > 0`，且当前 DEA 上水周期的上水天数 `<= 14` 个交易日 | true |
| 昨日阴线 | `close[T-1] < open[T-1]` | true |

入场触发：

- 三个条件全部满足时，输出 `ENTER`。
- 任一指标缺失或 warmup 不足时，输出 `HOLD`，reason 使用 unavailable/not triggered，不填默认值。

DEA 上水计算：

- 只使用 `T-1` 及以前的已完成日线。
- `dea[T-1]` 必须 `> 0`。
- 从 `T-1` 往前找当前 DEA 上水周期的上水日：上水日满足 `dea[上水日] > 0`，且上一个已完成交易日 `dea <= 0`。
- `0` 按未上水/水下处理，所以 `-0.01 -> 0 -> 0.02` 的上水日是 `0.02` 这一天。
- 上水天数使用交易日间隔计算：`dea_waterline_age_trading_days = T-1 与上水日之间的交易日差`，上水日就是 `T-1` 时记为 `0`。
- 只有 `dea_waterline_age_trading_days <= 14` 时，才满足 DEA 最近上水条件。
- 如果历史数据中找不到当前上水周期的上水日，即使 `dea[T-1] > 0`，也视为不满足，不默认通过。

建议 reason code：

| 场景 | reason_code |
|---|---|
| 入场触发 | `BAOMA_ENTRY_TRIGGERED` |
| 指标或上一日数据缺失 | `BAOMA_ENTRY_UNAVAILABLE` |
| 条件未满足 | `BAOMA_ENTRY_NOT_TRIGGERED` |

## 买入和加仓方式

原始规则：

1. 一个标的分三次满仓，每次买单股满仓目标的 33%。
2. 每次买入价格是开盘价。
3. 一个标的可以开仓 1 次，加仓 2 次。
4. 后两次加仓条件和买入选股条件一样，需要昨日阴线才能买。
5. 出现盈利之后不再补仓，且这个优先级最高。

已确认口径：

| 项目 | 口径 |
|---|---|
| 最大买入次数 | 3 次：首次入场 1 次，加仓最多 2 次 |
| 单股满仓 | 一个标的分三次买满，三次完成后视为该标的满仓 |
| 每次买入比例 | 每次买入该标的单股满仓目标的 33% |
| 单股满仓目标 | 每个股票最大市值 = 总资产 / 最大持仓数量；第一版为 5000 万 |
| 三次完成后的仓位 | 三次各 33%，合计 99%，按满仓处理，不再为剩余 1% 单独补单 |
| 整手处理 | 每次计算出的买入数量按 1 手向下取整；不足 1 手则不买 |
| 加仓触发 | 当前持仓存在，且 `T-1` 仍满足完整入场条件 |
| 止损观察期禁止加仓 | 如果 `T-1` 已跌破 MA60，则 `T` 不允许加仓，只等待 `T` 收盘是否确认止损 |
| 止盈观察期禁止加仓 | 如果 `T-1` 已跌破 MA25，则 `T` 不允许加仓，只等待 `T` 收盘是否确认 MA25 止盈 |
| 盈利后禁止加仓 | 当前交易生命周期内，只要曾经出现 `T-1 close > 当前剩余成本`，后续永久不再加仓 |
| 加仓成交价 | `T` 开盘价 |
| 加仓最低持有期 | 加仓买入部分也遵守 T+1，买入当天不能卖出 |
| 当天卖出判断 | 同一标的当天发生买入或加仓后，当天不执行止损、分批减仓或 MA25 止盈 |

注意：

- “出现盈利之后不再补仓”是持仓生命周期状态，不是单日信号。也就是只要曾经盈利过，后续即使回落亏损，也不能再加仓。
- 当前剩余成本不是固定的原始买入均价。分批止盈真实卖出后，需要用卖出后的新成本继续判断后续盈利、分批止盈和 MA25 止盈。
- 当前框架已有 add-on 证据链，但需要新增 `baoma_add_on` 方法，并让它记录 `add_on_count`、`ever_profitable`、入场条件和成交参考价。
- 如果进入 `Stop-Loss Watch`，即 `T-1 close < ma60[T-1]`，`T` 开盘不再加仓，只等待 `T` 收盘是否仍未收回 MA60。
- 如果进入 `Profit-Exit Watch`，即 `T-1 close < ma25[T-1]`，`T` 开盘不再加仓，只等待 `T` 收盘是否仍未收回 MA25 且仍然盈利。

## 卖出方式

卖出执行优先级已确认固定为：

1. 止损
2. MA25 跌破卖出
3. 分批止盈/降低成本
4. 持有

说明：

- MA60 跌破卖出和 MA25 跌破卖出本质上都是 `Full Exit`。
- 如果同一天同时满足 MA60 和 MA25 卖出条件，不需要在执行层纠结止损还是止盈；先执行清仓。
- 结算后按该笔交易实际收益判断盈利卖出还是亏损卖出。
- 报告和归因可以同时记录 MA60/MA25 两个触发证据。
- `Full Exit` 优先于分批减仓；如果同一天既满足 MA25 清仓又满足分批减仓，直接清仓，不做分批减仓。

### 止损

原始规则：

- 跌破 MA60，第二天未收回，第二天尾盘卖出。

推荐实现口径：

| 步骤 | 口径 |
|---|---|
| 观察日 | `S = T-1` |
| 跌破判断 | `close[S] < ma60[S]` |
| 未收回判断 | `close[T] < ma60[T]`，如果 `ma60[T]` 不可用则不触发 |
| 观察期行为 | `S` 跌破后，`T` 不允许加仓，只等待 `T` 收盘确认是否止损 |
| 成交时点 | `T` 尾盘 |
| 成交价格 | `close[T]`，叠加配置的费用和滑点 |
| 卖出数量 | 剩余全部仓位 |
| 最低持有期 | 如果当前仓位买入日或加仓日为 `T`，对应未满 T+1 的数量不得卖出 |

连续两日确认口径：

- 当前实现不持久化 `Stop Watch` 标记。
- MA60 止损按 `previous_price_below_ma && current_price_below_ma` 判断：前一交易日收盘低于 MA60，当前交易日收盘仍低于 MA60，才在当前交易日尾盘清仓止损。
- 如果第一次跌破后下一交易日重新站上 MA60，则不触发清仓，继续持有。

建议 reason code：

| 场景 | reason_code |
|---|---|
| 止损触发 | `BAOMA_MA60_STOP_TRIGGERED` |
| MA60 或上一日数据缺失 | `BAOMA_MA60_STOP_UNAVAILABLE` |
| 未跌破或已收回 | `BAOMA_MA60_STOP_NOT_TRIGGERED` |

### 分批止盈/降低成本

原始规则：

- 持有收益 `> 5%`，卖总仓位的 `1/3`。
- 持有收益 `> 15%`，再卖出一半。

已确认口径：

- 分批止盈必须真实减仓，也就是 `Scale-Out`。
- `Scale-Out` 后保留剩余仓位，交易生命周期继续存在。
- 后续 MA25 止盈和 MA60 止损只作用于剩余仓位。
- 完整 `ClosedTrade` 只在剩余仓位 `Full Exit` 时生成；分批减仓需要作为生命周期事件记录。
- 分批减仓卖出数量按 1 手向下取整；不足 1 手时跳过该次减仓，并记录 `SCALE_OUT_TOO_SMALL`。
- 如果分批减仓目标数量大于当天可卖数量，但当天可卖数量仍不少于 1 手，则当天卖出全部可卖数量，并标记该分批阶段完成一次，不挂起补卖差额。
- 最终清仓时卖出全部剩余仓位。
- 同一天最多执行一个分批减仓阶段；如果 5% 和 15% 同时满足，先执行尚未完成的最低阶段。
- 分批减仓只由收益涨幅或 `cost_recovered=true` 触发，不因为下跌触发；下跌相关卖出只进入 MA60/MA25 的 `Full Exit` 逻辑。
- 分批止盈后，后续策略触发使用卖出后重新计算的当前剩余成本，不继续使用原始买入均价。
- 分批减仓不是挂起事件。只有真实成交后，该分批阶段才标记完成；如果因 T+1、停牌或可卖数量不足 1 手没有成交，记录失败原因，阶段保持未完成，下一交易日重新判断是否仍满足触发条件。

| 阶段 | 触发条件 | 卖出数量 | 只触发一次 |
|---|---|---:|---|
| 第一段 | `unrealized_return > 5%` | 触发当时当前持仓数量的 `1/3` | 是 |
| 第二段 | `unrealized_return > 15%` | 触发当时当前持仓数量的 `1/2` | 是 |

收益计算：

- `unrealized_return = close[T] / 当前剩余成本 - 1`
- 如果当前剩余成本 `<= 0`，不再用除法计算百分比，改为 `cost_recovered=true`。
- 使用当前尾盘判断并尾盘卖出。
- 如果同一天已经触发止损，则不做分批止盈。
- 如果同一天两个分批减仓阶段都满足，只执行一个阶段，优先执行尚未完成的最低阶段。
- 分批减仓数量按触发当时的当前持仓数量计算，不按单股满仓目标计算。
- 如果同一标的当天发生买入或加仓，则当天不执行分批减仓。
- 只卖出满足 T+1 的可卖数量。
- 分批减仓实际卖出数量 = `min(目标卖出数量, 当天可卖数量)`，再按 1 手向下取整。
- 如果实际卖出数量不少于 1 手，则当天卖出全部实际可卖数量，并标记该分批阶段完成一次。
- 如果实际卖出数量不足 1 手，则跳过本次 `Scale-Out`，记录失败原因，阶段保持未完成；如果是最终清仓，则卖出全部剩余可卖数量。

剩余成本计算：

- 首次买入或加仓后，当前剩余成本按买入后的持仓成本重新加权。
- 分批止盈后，当前剩余成本按卖出后的新成本重新计算。
- 公式：`new_remaining_cost_value = previous_remaining_cost * previous_quantity - net_scale_out_sell_value`。
- 公式：`new_remaining_cost = new_remaining_cost_value / remaining_quantity`。
- `net_scale_out_sell_value` 是扣除费用、税费、滑点后的净卖出金额。
- 后续 `ever_profitable`、`unrealized_return`、MA25 止盈确认，都使用这个卖出后重算的当前剩余成本。
- 如果当前剩余成本 `<= 0`，标记 `cost_recovered=true`：盈利前置视为满足，未完成的分批止盈阶段在下一个可判断交易日视为满足触发条件，但仍遵守一天只执行一个阶段和 `Full Exit` 优先级。
- 原始加权买入成本仍需要保留，用于报告复盘和比较“原始买入成本 vs 降低后的剩余成本”。

当前框架缺口：

- 现有 `TradeIntentType.EXIT_PROFIT` 表示整仓止盈退出，不表示“部分卖出后继续持仓”。
- 现有 backtrader/business 执行桥在 profit/stop 触发时卖出全部仓位，并生成一笔 `ClosedTrade`。
- 因此此规则要真实落地，需要先补 `Scale-Out` 执行语义，不能只新增一个普通 profit-taking 方法。

### MA25 止盈

原始规则：

- 出现盈利的时候，价格跌破 MA25，第二天未收回，则卖出止盈。

推荐实现口径：

| 步骤 | 口径 |
|---|---|
| 盈利前置 | 卖出确认日 `T` 收盘仍然盈利，即 `close[T] > 当前剩余成本` |
| 观察日 | `S = T-1` |
| 跌破判断 | `close[S] < ma25[S]` |
| 未收回判断 | `close[T] < ma25[T]`，如果 `ma25[T]` 不可用则不触发 |
| 观察期行为 | `S` 跌破后，`T` 不允许加仓，只等待 `T` 收盘确认是否 MA25 止盈 |
| 成交时点 | `T` 尾盘 |
| 成交价格 | `close[T]`，叠加配置的费用和滑点 |
| 卖出数量 | `Full Exit`，卖出全部剩余可卖仓位 |
| 最低持有期 | 只卖出满足 T+1 的可卖数量；未满 T+1 的数量不得卖出 |

连续两日确认口径：

- 当前实现不持久化 `Profit Exit Watch` 标记。
- MA25 止盈按 `previous_price_below_ma && current_price_below_ma && confirmed_profitable` 判断：前一交易日收盘低于 MA25，当前交易日收盘仍低于 MA25，并且当前交易日收盘仍有盈利，才在当前交易日尾盘清仓止盈。
- 如果第一次跌破后下一交易日重新站上 MA25，则不触发清仓，继续持有。
- MA25 止盈不要求此前发生过加仓；只要满足连续两日跌破 MA25 且确认日仍盈利即可触发。

建议 reason code：

| 场景 | reason_code |
|---|---|
| MA25 止盈触发 | `BAOMA_MA25_PROFIT_EXIT_TRIGGERED` |
| MA25 或盈利状态缺失 | `BAOMA_MA25_PROFIT_EXIT_UNAVAILABLE` |
| 未跌破、已收回或未曾盈利 | `BAOMA_MA25_PROFIT_EXIT_NOT_TRIGGERED` |

## 归因证据

每次 Entry/Add-On/Exit 都应写入 `signal_values.checks` 和
`signal_values.attribution`，以便后续 `trade_lifecycle`、`trade_review`、
`environment_fit` 和 AI review 反查。

建议入场/加仓 checks：

| key | 类型 | 中文含义 |
|---|---|---|
| `symbol.price_above_ma60` | check | 昨收在 MA60 上方 |
| `symbol.macd.dea_recent_waterline` | check | DEA 当前上水周期天数不超过 14 个交易日 |
| `symbol.candle.previous_bearish` | check | 昨日阴线 |
| `position.add_on_count_available` | check | 加仓次数未超限 |
| `position.ever_profitable` | check | 当前生命周期曾经盈利 |
| `position.add_on_blocked_by_profit` | check | 因曾经盈利禁止加仓 |
| `position.add_on_blocked_by_stop_watch` | check | 因 MA60 止损观察期禁止加仓 |
| `position.add_on_blocked_by_profit_exit_watch` | check | 因 MA25 止盈观察期禁止加仓 |

建议数值：

| key | 类型 | 中文含义 |
|---|---|---|
| `symbol.open.previous` | value | 昨日开盘价 |
| `symbol.close.previous` | value | 昨日收盘价 |
| `symbol.ma60.previous` | value | 昨日 MA60 |
| `symbol.ma25.previous` | value | 昨日 MA25 |
| `symbol.macd.dea.previous` | value | 昨日 DEA |
| `symbol.macd.dea_waterline_date` | value | 当前 DEA 上水日 |
| `symbol.macd.dea_waterline_age_trading_days` | value | 当前 DEA 上水天数 |
| `symbol.macd.dea_waterline_max_age_days` | value | DEA 上水天数阈值，第一版为 14 |
| `position.raw_weighted_entry_cost` | value | 原始加权买入成本 |
| `position.adjusted_remaining_cost_basis` | value | 按费用/滑点净口径卖出后重算的当前剩余成本 |
| `position.cost_recovered` | check | 剩余成本是否已被分批止盈净卖出金额覆盖 |
| `position.unrealized_return` | value | 当前未实现收益 |
| `position.profit_exit_confirmed_profitable` | check | MA25 止盈确认日仍然盈利 |
| `position.add_on_count` | value | 已加仓次数 |
| `position.scale_out_stage` | category | 分批减仓阶段 |
| `position.remaining_quantity` | value | 减仓后剩余数量 |
| `position.full_exit` | check | 是否最终清仓退出 |

## 当前漏洞和需要补齐的能力

| 编号 | 漏洞 | 影响 | 推荐处理 |
|---|---|---|---|
| 1 | 标的池没有说明是指数成分股还是指数本身 | 数据拉取、资产类型、交易规则完全不同 | 已确认为沪深300和中证500成分股股票池 |
| 2 | 股票池没有说明固定列表还是历史成分股快照 | 影响幸存者偏差和数据准备复杂度 | 第一版使用固定股票列表，报告标注样本限制 |
| 3 | “当天选昨日”没有形式化成 `T-1` 信号、`T` 执行 | 容易误用当天收盘数据，产生未来函数或成交口径偏差 | 文档固定为 `T-1` 决策、`T` 成交 |
| 4 | 当前执行桥默认信号价多处使用 close，且 broker 使用 cheat-on-close | 与“开盘买、尾盘卖”的真实口径不一致 | 已确认第一版必须支持开盘买、尾盘卖 |
| 5 | 分批止盈需要部分卖出并继续持仓 | 现有 `EXIT_PROFIT` 是整仓退出 | 已确认必须扩展 `Scale-Out` 执行语义 |
| 6 | “每次占个股仓位”没有定义个股目标仓位 | sizing 无法稳定计算下单数量 | 已确认每个股票最大市值 = 总资产 / 最大持仓数量，一个标的三次买满，每次买单股满仓目标的 33% |
| 7 | “出现盈利”没有说明是当前盈利还是曾经盈利 | 直接影响是否允许后续加仓 | 已确认当前生命周期只要曾经盈利过，后续永久不再加仓 |
| 8 | DEA 最近上水没有说明如何计算 | 会造成信号偏移，或错误排除 5 天外但仍属最近上水周期的股票 | 已确认用当前 DEA 上水周期计算，上水天数 `<= 14` 个交易日，且 `dea[T-1] > 0` |
| 9 | 跌破后第二天未收回没有说明用盘中还是收盘判断 | 影响退出日期和价格 | 已确认用第二天收盘价判断未收回，尾盘成交 |
| 10 | 同一天可能同时触发 MA60 卖出、分批止盈、MA25 卖出 | 不固定优先级会产生不稳定结果 | 已确认 Full Exit 优先于分批减仓；MA60/MA25 都是卖出触发，最终盈亏按交易结算结果判断 |
| 11 | 指标缺失、停牌、涨跌停、T+1 没有写入策略口径 | 影响信号和成交是否可执行 | 已确认 T+1 最低持有期；策略只发 intent，A 股约束层处理成交拒绝 |
| 12 | 加仓后的 T+1 需要按买入批次计算可卖数量 | 如果只看最早开仓日，会错误卖出当天新加仓部分 | 执行层需要记录 lot-level 或 available_quantity |
| 13 | 第一版不是资金真实组合回测 | 起始金额、最终金额和总收益率会失真 | 已确认为 `Trade-Sample Backtest`，核心统计成交股票和交易样本 |
| 14 | 当前 sizing 的最大持仓数可能被实现成硬上限 | 如果超过 200 个同时持仓，需要知道这是异常还是规则 | 已确认 200 既是分母也是新开仓硬上限；若触发则记录 `MAX_HOLDING_COUNT`，已有持仓加仓不受该上限阻止 |
| 15 | T-1 跌破 MA60 后 T 开盘可能又满足加仓条件 | 如果先加仓，会挡住当天止损确认后的卖出 | 已确认跌破 MA60 后不加仓，只等待是否止损 |
| 16 | T-1 跌破 MA25 后 T 开盘可能又满足加仓条件 | 如果先加仓，会挡住当天 MA25 止盈确认后的清仓 | 已确认止盈观察期也不加仓，只等待是否止盈 |
| 17 | 入场、加仓、离场条件被错误组合 | 会出现一边触发离场一边入场/加仓的错误生命周期 | 已确认按持仓状态分阶段判断，离场观察或确认存在时不入场、不加仓 |
| 18 | 同一天多个无持仓股票同时满足入场条件时没有固定成交口径 | 如果隐含排序或只买部分股票，会把第一版样本回测变成选股排序优化 | 已确认全部买入，直到达到 200 个不同股票持仓上限；超过上限记录 `MAX_HOLDING_COUNT` |
| 19 | 只保留含费用或只保留不含费用结果都会丢失一部分判断依据 | 不含费用会高估真实交易，含费用又不利于观察原始信号质量 | 已确认主计算使用含费用/滑点的净口径；不含费用视图从同一批成交记录派生，不单独重跑 |
| 20 | 费用、税费、滑点如果写死在代码里 | 后续回测无法复现实验假设，也无法比较不同成本口径 | 已确认全部作为 RunPlan/配置项，代码不得硬编码成本参数 |
| 21 | 固定股票池如果每次运行时动态拉取 | 同一策略在不同日期运行会得到不同样本，无法复现第一版结果 | 已确认使用固定股票池清单文件，RunPlan 引用该文件 |
| 22 | 买入和卖出不可成交如果使用同一种顺延规则 | 入场会产生过期信号，离场又可能丢失已经确认的风险控制 | 已确认买入不可成交不顺延；卖出不可成交保留 `Pending Exit Intent` 并继续尝试卖出 |
| 23 | 已确认的卖出意图如果允许后续行情收回后取消 | 会把离场确认和后续市场约束混在一起，导致回测结果不可解释 | 已确认 `Pending Exit Intent` 不取消，直到清仓完成 |
| 24 | 回测结束仍未清仓的持仓如果只用一种统计口径 | 强制清仓会引入人工假设，剔除又会看不到期末风险 | 已确认同时输出强制清仓报告和剔除未完成交易报告 |
| 25 | 强制清仓报告如果完全忽略跌停 | 会把期末真实卖不出的持仓伪造成已成交退出 | 已确认除跌停外按期末收盘价卖出；跌停视为清仓交易失败并标记 |
| 26 | 期末停牌或缺少回测结束日收盘价时如果用最后可用价清仓 | 会把非期末成交伪造成期末清仓，破坏强制清仓报告口径 | 已确认不强制清仓，记录 `END_LIQUIDATION_SUSPENDED` 或 `END_LIQUIDATION_PRICE_MISSING` |
| 27 | 策略层自行推算涨跌停和停牌状态 | ST、科创/创业板涨跌幅和特殊状态容易算错，且会和数据层约束不一致 | 已确认以 `TradabilityStatus` 快照为准，策略不自行计算 |
| 28 | 分批止盈后如果继续用原始买入成本判断盈利 | 会违背“降低成本”的策略含义，也会影响后续分批止盈和 MA25 止盈触发 | 已确认按卖出后重算的新成本作为当前剩余成本 |
| 29 | 卖出后重算的新成本如果不计费用/滑点 | 成本状态和主净口径结果不一致，也会让费用配置无法真实影响后续触发 | 已确认当前剩余成本按带费用/滑点的净口径计算；无费用结果只是派生视图 |
| 30 | 当前剩余成本小于等于 0 时继续用收益率除法 | 会得到无意义或无限收益，影响后续分批止盈判断 | 已确认标记 `cost_recovered=true`，不再用除法计算百分比 |
| 31 | 把下跌或跌停误解为分批减仓触发原因 | 会把收益管理和风险清仓混在一起，导致执行优先级错误 | 已确认分批减仓只因收益涨幅或成本收回触发，下跌只可能进入 `Full Exit` 逻辑 |
| 32 | 分批减仓不可成交时如果像清仓一样挂起 | 会把收益管理变成风险退出，且可能在不再满足收益条件时继续卖 | 已确认分批减仓不挂起，只有真实成交才标记阶段完成，未成交则次日重新判断 |
| 33 | 分批减仓目标数量大于当天可卖数量时没有固定成交口径 | 可能因为 T+1 可卖数量不足导致阶段完成状态不稳定 | 已确认当天卖出全部可卖数量，只要不少于 1 手就标记该分批阶段完成一次 |
| 34 | 同一天入场候选超过剩余持仓名额时如果没有稳定顺序 | 超过 200 上限时哪些股票成交会不可复现，也可能误引入排序优化 | 已确认第一版默认按固定股票池清单顺序；RunPlan 预留排序配置但默认不开启 |
| 35 | 回测开始前没有预热数据区间 | MA60、MACD 和 DEA 上水判断会在回测前期大量缺失，样本被人为压少 | 已确认 `data_start` 固定为 `backtest_start` 往前一年，回测统计只从 `backtest_start` 开始 |
| 36 | 关键指标大量为空时如果静默继续回测 | 会把数据异常误当作策略不触发，导致样本和胜率失真 | 已确认需要 `Indicator Coverage Alarm`；必需指标按 `symbol + indicator` 统计，空值率超过 5% 则本次回测失败 |
| 37 | 指标空值率分母如果包含上市前、无基础行情或 warmup 期 | 会把正常不可计算误报为指标异常 | 已确认只在有基础日线且已满足 warmup 后的日期统计空值率；覆盖限制单独诊断 |
| 38 | 指标与交易收益使用不同价格口径会让第一版实现复杂化 | 未复权真实成交需要处理分红、送转和公司行为，否则短线收益与指标口径不一致 | 已确认第一版使用前复权价差口径；报告标记不是严格现金分红/真实成交核算 |
| 39 | 前复权价差口径下继续计算费用如果不说明性质 | 容易把成本敏感性模拟误读成券商真实现金扣费 | 已确认继续计算费用和滑点，但报告标记为 `Adjusted Price Cost Simulation`；主结论看带成本净口径，去成本视图从同一批成交派生 |
| 40 | 前复权价差口径下继续模拟股数如果不说明性质 | 容易把前复权名义股数误读成券商真实成交股数 | 已确认继续模拟订单数量、一手约束、T+1 和分批减仓数量，但报告标记为 `Adjusted Price Quantity Simulation` |
| 41 | 把第一版回测目标理解成追求完美收益率 | 会把开发方向带到参数优化或资金曲线精修，而不是找到策略适合和不适合的环境 | 已确认总目标是 `Strategy Environment Discovery`：用成交样本找到高胜率、高盈利贡献和亏损集中的环境 |
| 42 | 环境维度如果被写死成一次性报告字段 | 后续新增环境因子或细化维度内容会变成反复改报告结构 | 已确认第一版先固定大盘环境、行业环境、个股入场结构、交易执行状态，但维度集合和维度字段都必须可扩展 |
| 43 | 第一版环境字段过少或过多 | 太少找不到土壤，太多会把样本切碎并拖慢第一版实现 | 已确认每类先放少量但有解释力的 `Environment Factor`：大盘趋势/市场温度、行业名称/行业趋势、个股 MA60/MA25/DEA 上水/阴线、执行拒绝或挂起状态 |
| 44 | 环境字段如果接入到买卖决策前置 | 会把归因分析变成策略过滤条件，导致无法判断原始策略本身适合什么环境 | 已确认环境发现是 `Post-Trade Environment Lookup`：先生成交易记录，再反查指数、行业、个股和执行环境 |
| 45 | 大盘环境只反查一个指数 | 沪深300和中证500环境可能背离，会掩盖大盘股和中盘股策略土壤差异 | 已确认每笔交易同时反查沪深300和中证500的大盘趋势/市场温度，并额外记录该股票来源指数对应环境 |
| 46 | 先接 `baoma_v1` 信号但执行/生命周期能力不足 | 交易记录会不符合开盘买、尾盘卖、T+1、真实减仓和卖出挂起规则，后续归因也会失真 | 已确认先补 `Execution Lifecycle Foundation`，再接 `baoma_v1` 信号 |
| 47 | 把执行生命周期规则直接塞进 Backtrader strategy bridge | 会让桥变成策略、执行、持仓生命周期和报告证据的混合体，难以单测和复用 | 已确认新增业务层 `Execution Lifecycle Component`，由现有 Backtrader 桥调用；建议放在 `attbacktrader/engines/business/` |
| 48 | 先定组件抽象但没有验收场景 | 容易继续空谈架构，不知道什么叫“交易记录可信” | 已确认先定义 `Lifecycle Golden Scenario`，再让业务层 `Authoritative Lifecycle Output` 成为报告、环境反查和 AI review 的权威证据 |
| 49 | 没对齐 `baoma` 状态机就开始枚举黄金场景 | 黄金场景会变成零散例子，无法保证覆盖“能否入场/加仓/分批/清仓/挂起”的状态冲突 | 已确认先对齐 `Strategy Lifecycle State Machine`，再从状态机生成 `Lifecycle Golden Scenario` |
| 50 | 先命名状态但没有动作权限表 | 状态名可能看起来合理，但仍不清楚每个状态下能不能入场、加仓、减仓、清仓或继续挂起卖出 | 已确认先列 `Lifecycle Action Permission Table`，再收敛成 `Strategy Lifecycle State Machine` 状态名 |
| 51 | 动作权限表没有固定优先级 | 同一交易日多个情况同时成立时，仍无法判断应该加仓、分批减仓、清仓还是继续挂起卖出 | 已确认当前权限表作为第一版，并固定优先级：清仓挂起 > 离场观察 > T+1 未满足 > 曾经盈利禁加仓 > 普通持仓 |
| 52 | 状态名只用中文或只用英文 | 只用中文不利于代码和测试稳定；只用英文不利于中文报告理解 | 已确认主状态用英文枚举，报告通过 `Lifecycle State Label` 显示中文标签 |
| 53 | 状态只有名称但没有转换表 | 代码仍可能用隐含 if/else 顺序处理状态跳转，黄金场景无法系统生成 | 已确认第一版 `Lifecycle Transition Table` 按权限优先级转换：清仓挂起优先，其次离场观察、T+1、盈利禁加仓、分批减仓和加仓 |
| 54 | 第一批黄金场景范围不固定 | 后续实现可能只覆盖主路径，漏掉挂起清仓、分批成本重算或期末未完成 | 已确认第一批 8 个 `Lifecycle Golden Scenario`，覆盖 T+1、加仓、禁加仓、分批减仓、清仓成功、清仓挂起、挂起后清仓和期末未完成 |
| 55 | 黄金场景只写在文档里 | 规则仍然靠人工阅读，后续实现可能偏离状态机 | 已确认第一批黄金场景同时落文档表和 pytest golden tests，先写 `tests/test_execution_lifecycle_component.py`，再实现业务层组件 |

## 接入前置任务

如果按本文推荐口径真实实现，需要先做下面几件事：

当前实现主线：

1. 先列 `Lifecycle Action Permission Table`：明确每种情况下允许入场、加仓、分批减仓、清仓、继续挂起卖出和期末处理。
2. 再把动作权限表收敛成 `Strategy Lifecycle State Machine` 状态名。
3. 再从状态机生成 `Lifecycle Golden Scenario`，把开盘买、尾盘卖、T+1、分批减仓、成本重算、跌停挂起、次日继续卖和期末清仓这些验收例子钉死。
4. 再补业务层 `Execution Lifecycle Component`，形成 `Execution Lifecycle Foundation`，并让它产出 `Authoritative Lifecycle Output`。
5. 再接 `baoma_v1` 策略信号：入场、加仓、MA60 清仓、MA25 盈利清仓。
6. 再接固定股票池、RunPlan、交易记录报告和 `Post-Trade Environment Lookup`。

1. 新增 `baoma_entry`：用 `T-1` 的 MA60、DEA、阴线判断，在 `T` 发入场 intent。
2. 新增 `baoma_add_on`：复用入场条件，加上最多两次和曾经盈利后禁加仓状态。
3. 新增 `baoma_ma60_stop` 和 `baoma_ma25_profit_exit`：支持“前一日跌破、当日未收回、尾盘卖出”。
4. 扩展执行层支持开盘买入和尾盘卖出，而不是全都按 close 信号价。
5. 扩展执行层支持 T+1 可卖数量约束，买入或加仓当天不能卖出。
6. 扩展执行/生命周期支持 `Scale-Out`，否则 5%/15% 分批卖出不能真实表达。
7. 扩展执行/生命周期区分 `Scale-Out` 和 `Full Exit`，最终清仓卖出全部剩余仓位。
8. 扩展执行层区分买入不可成交和卖出不可成交：买入拒绝不顺延，卖出失败保留 `Pending Exit Intent`，下一交易日继续尝试。
9. 扩展执行/生命周期让 `Pending Exit Intent` 不可撤销：挂起期间不再重新判断 MA 是否收回，不允许加仓、分批止盈或重新入场，只继续卖到清仓完成。
10. 新增固定股票池清单文件，至少包含 `ts_code`、名称、来源指数、冻结日期；RunPlan 引用该文件，不在策略运行时动态拉取成分股。
11. 新增 RunPlan 样本，固定股票列表、回测区间、初始资金 100 亿、最大持仓数量 200、费用、滑点和 A 股约束；费用、税费、滑点必须来自配置项。
12. 报告层标注本次是 `Trade-Sample Backtest`，总金额和组合总收益失真，优先展示成交股票和交易样本统计。
13. 报告层展示 `Net Trade View` 和派生的 `Gross Trade View`：主计算和交易路径使用净口径，毛口径从同一批成交记录中去掉费用/滑点派生，不单独重跑策略；报告必须披露本次实际使用的费用/滑点配置，并标记收益属于前复权价差口径。
14. 报告层统计 `MAX_HOLDING_COUNT` 阻断次数；第一版预期不会出现，若出现需要在结果中单独提示。
15. 报告层统计 `Pending Exit Intent` 的原始触发日、实际卖出日、挂起交易日数和最终成交结果。
16. 报告层对回测结束仍未清仓的持仓输出两份结果：`Forced End Liquidation View` 将期末持仓按显式假设人工清仓；`Open-Position Excluded View` 将期末未完成交易从已完成交易胜率/盈亏统计中剔除，并单独列出 `open_positions_at_end`。
17. 强制清仓报告中，期末持仓除跌停外按回测结束日收盘价卖出；如果期末跌停导致不能卖出，记录 `END_LIQUIDATION_LIMIT_DOWN`，作为 `End Liquidation Failure` 单独统计。
18. 强制清仓报告中，如果期末停牌或没有回测结束日收盘价，不使用更早的最后可用价清仓，记录 `END_LIQUIDATION_SUSPENDED` 或 `END_LIQUIDATION_PRICE_MISSING`。
19. 买入、卖出和强制清仓的停牌/涨跌停判断统一读取 `TradabilityStatus` 快照；策略方法只输出 intent，不自行根据价格推算可交易状态。
20. 执行/生命周期需要维护 `Adjusted Remaining Cost Basis`：分批止盈后用扣除费用/税费/滑点后的净卖出金额降低剩余仓位成本，并让后续盈利判断、分批止盈和 MA25 止盈使用该成本；同时保留原始加权买入成本用于复盘。
21. 执行/生命周期需要维护 `Cost Recovered Position`：当前剩余成本 `<= 0` 时标记 `cost_recovered=true`，后续不再用收益率除法，未完成分批止盈阶段视为已满足触发条件但仍受执行优先级约束。
22. 执行/生命周期需要让分批减仓保持非挂起：未成交只记录失败原因，不创建 `Pending Exit Intent`，阶段保持未完成并等待下一交易日重新判断触发条件。
23. 执行/生命周期需要支持分批减仓部分可卖成交：目标数量大于当天可卖数量时，卖出全部可卖数量；只要实际成交不少于 1 手，就标记该分批阶段完成一次。
24. RunPlan 需要预留 `Entry Candidate Ordering` 配置：第一版默认使用固定股票池清单顺序，排序配置默认关闭；如果未来开启信号强弱、行业或其他排序，应作为单独实验口径。
25. RunPlan 需要区分 `backtest_start` 和自动解析出的 `data_start`：`data_start` 固定为 `backtest_start` 往前一年，数据从 `data_start` 拉取和计算指标，交易统计和报告只从 `backtest_start` 开始；resolved RunPlan 和报告必须记录最终 `data_start`。
26. 数据准备/报告需要新增 `Indicator Coverage Alarm`：对 `ma60`、`ma25`、`macd/dea` 等必需指标按 `symbol + indicator` 统计空值率；回测统计区间内空值率超过 5% 时，本次回测失败，输出问题最严重的标的和指标诊断。
27. `Indicator Coverage Alarm` 只在有效日期上统计空值率：该标的有基础日线且已满足对应指标 warmup 后才进入分母；上市前、无基础行情、warmup 期不计入指标异常，但需要在诊断中列出覆盖限制。
28. 第一版价格口径需要统一为 `Adjusted Price-Difference Return`：指标、交易收益、分批止盈、成本重算和费用/滑点模拟都使用前复权价格；报告必须披露这不是严格现金分红、送转、未复权真实成交和完整公司行为核算口径。
29. 第一版费用口径需要标记为 `Adjusted Price Cost Simulation`：费用、税费、滑点仍按 RunPlan 配置在前复权模拟成交金额上计算，用于观察成本敏感性；主结论使用带成本净口径，去成本毛口径只从同一批成交事件派生。
30. 第一版数量口径需要标记为 `Adjusted Price Quantity Simulation`：订单数量、1 手约束、T+1 可卖数量和分批减仓数量仍按前复权价格模拟，用于保留执行生命周期；报告不得把这些数量描述成券商真实股数。
31. 报告层需要围绕 `Strategy Environment Discovery` 组织结论：优先输出高胜率环境、高盈利贡献环境、亏损集中环境和应回避环境，而不是把组合总收益率当作第一结论。
32. 报告层需要输出 `Environment Discovery Matrix`：第一版按大盘环境、行业环境、个股入场结构、交易执行状态四类维度汇总胜率、平均收益、盈利贡献、亏损贡献和样本数；维度集合和维度字段必须允许后续扩展。
33. 环境矩阵第一版字段集采用少量 `Environment Factor`：大盘趋势/市场温度，行业名称/行业趋势，个股 MA60/MA25/DEA 上水/阴线，执行拒绝或挂起状态；后续新增字段必须作为环境因子扩展，不得写死成一次性报告逻辑。
34. 报告层需要在交易记录生成后执行 `Post-Trade Environment Lookup`：按每笔交易的入场日、退出日和必要持有区间反查指数、行业、个股和执行环境；环境字段只用于归因和环境矩阵，不参与第一版买卖决策。
35. 大盘环境反查需要同时覆盖沪深300和中证500：每笔交易都记录两个指数的大盘趋势/市场温度，并根据股票池清单里的来源指数标记 `source_index_environment`。
36. `Execution Lifecycle Foundation` 第一版需要新增业务层 `Execution Lifecycle Component`，建议放在 `attbacktrader/engines/business/`；现有 Backtrader 桥负责调用它并转接结果，不把 T+1 lot、分批减仓、挂起卖出和成本重算规则直接写死在 strategy bridge 里。
37. 实现 `Execution Lifecycle Component` 前，需要先定义 `Lifecycle Golden Scenario`；通过黄金场景反推数据模型和验收测试，再让业务层 `Authoritative Lifecycle Output` 成为报告、环境反查和 AI review 的权威证据，包括 accepted/rejected execution events、lot 状态、position lifecycle、closed/open trade records 和 cost basis 状态。
38. 定义 `Lifecycle Golden Scenario` 前，需要先对齐 `Strategy Lifecycle State Machine`；状态机需要覆盖无持仓、可加仓持仓、盈利后禁加仓、离场观察、挂起清仓、已清仓和期末未完成等状态，以及每个状态允许或禁止的动作。
39. 对齐 `Strategy Lifecycle State Machine` 前，需要先列 `Lifecycle Action Permission Table`；先用动作权限发现状态冲突，再命名状态和生成黄金场景。
40. 第一版 `Lifecycle Action Permission Table` 已确认；状态冲突优先级固定为：清仓挂起 > 离场观察 > T+1 未满足 > 曾经盈利禁加仓 > 普通持仓。
41. 第一版 `Strategy Lifecycle State Machine` 状态名采用英文枚举，中文报告通过 `Lifecycle State Label` 显示中文标签；状态枚举和中文标签映射必须稳定记录，不能在报告里临时翻译。
42. 第一版 `Lifecycle Transition Table` 已确认：状态转换按权限优先级执行，`PENDING_FULL_EXIT` 只重试清仓；普通持仓先判断离场观察，再判断 T+1 锁定，再判断曾经盈利/成本收回，再判断分批减仓和加仓。
43. 第一批 `Lifecycle Golden Scenario` 已确认，共 8 个：入场到 T+1 锁定、可加仓到加仓锁定、曾经盈利禁加仓、5%/15% 分批减仓和成本重算、离场观察后清仓成功、离场观察后卖出失败进入挂起、挂起后继续卖到清仓、期末未完成的强制清仓视图和剔除未完成视图。
44. 第一批 `Lifecycle Golden Scenario` 需要先落成 pytest golden tests，测试文件为 `tests/test_execution_lifecycle_component.py`；再实现业务层 `Execution Lifecycle Component` 让这些测试通过。

## 生命周期动作权限表草案

第一版先用动作权限反推状态名。下表是当前草案：

| 生命周期情况 | 入场 | 加仓 | 分批减仓 | 清仓确认/下单 | 继续挂起卖出 | 期末处理 |
|---|---|---|---|---|---|---|
| 无持仓 | 允许 | 禁止 | 禁止 | 禁止 | 禁止 | 无 |
| 当天新买入或加仓，未满足 T+1 | 禁止 | 禁止 | 禁止 | 禁止 | 禁止 | 可进入期末未完成 |
| 持仓中，未曾盈利，未进入离场观察 | 禁止 | 允许 | 禁止 | 禁止 | 禁止 | 可进入期末未完成 |
| 持仓中，曾经盈利，未进入离场观察 | 禁止 | 禁止 | 允许 | 禁止 | 禁止 | 可进入期末未完成 |
| 持仓中，T-1 跌破 MA60 或 MA25，等待 T 确认 | 禁止 | 禁止 | 禁止 | 允许 | 禁止 | 可进入期末未完成 |
| 已确认 `Full Exit`，但卖出失败或未全部卖完 | 禁止 | 禁止 | 禁止 | 禁止 | 允许 | 可进入期末未完成 |
| 已清仓 | 下一交易日可重新入场 | 禁止 | 禁止 | 禁止 | 禁止 | 无 |
| 回测结束仍有持仓 | 禁止 | 禁止 | 禁止 | 按强制清仓口径处理 | 若强制清仓失败则记录失败 | 输出强制清仓视图和剔除未完成视图 |

## 生命周期状态名

第一版代码使用英文枚举，中文报告显示 `Lifecycle State Label`：

| 状态枚举 | 中文标签 | 含义 |
|---|---|---|
| `FLAT` | 无持仓 | 当前标的没有活跃持仓，可以按入场条件开新生命周期 |
| `ENTRY_LOCKED_T1` | T+1 锁定 | 当天发生买入或加仓，对应新买入 lot 未满足 T+1，不允许卖出或再加仓 |
| `OPEN_ADDABLE` | 持仓可加仓 | 已有持仓，当前生命周期尚未曾盈利，且没有离场观察或挂起清仓 |
| `OPEN_NO_ADD_ON` | 持仓禁加仓 | 已有持仓，当前生命周期曾经盈利或成本已收回，不再允许加仓 |
| `EXIT_WATCH` | 离场观察 | `T-1` 跌破 MA60 或 MA25，等待 `T` 收盘确认是否清仓 |
| `PENDING_FULL_EXIT` | 清仓挂起 | `Full Exit` 已确认，但因跌停、停牌、T+1 等约束未能全部卖出，只能继续尝试清仓 |
| `CLOSED` | 已清仓 | 当前生命周期已结束；下一交易日若重新满足入场条件，可以开启新生命周期 |
| `OPEN_AT_END` | 期末未完成 | 回测结束仍有持仓，需要进入强制清仓视图和剔除未完成视图 |

## 生命周期状态转换表

第一版状态转换按权限优先级执行：清仓挂起 > 离场观察 > T+1 未满足 > 曾经盈利禁加仓 > 普通持仓。

| 当前状态 | 触发条件 | 动作 | 下一状态 |
|---|---|---|---|
| `FLAT` | 入场条件满足且买入成交 | 开新生命周期，记录买入 lot | `ENTRY_LOCKED_T1` |
| `FLAT` | 入场条件不满足或买入被拒绝 | 不持仓；买入拒绝不顺延 | `FLAT` |
| `ENTRY_LOCKED_T1` | 到下一交易日且不存在离场观察/挂起 | 根据是否曾经盈利或成本收回进入普通持仓状态 | `OPEN_ADDABLE` 或 `OPEN_NO_ADD_ON` |
| `ENTRY_LOCKED_T1` | 回测结束仍有持仓 | 进入期末处理 | `OPEN_AT_END` |
| `OPEN_ADDABLE` | `T-1` 跌破 MA60 或 MA25 | 禁止加仓和分批减仓，等待 `T` 收盘确认 | `EXIT_WATCH` |
| `OPEN_ADDABLE` | 当前生命周期曾经盈利或成本收回 | 禁止后续加仓 | `OPEN_NO_ADD_ON` |
| `OPEN_ADDABLE` | 加仓条件满足且加仓成交 | 记录新买入 lot，进入 T+1 锁定 | `ENTRY_LOCKED_T1` |
| `OPEN_ADDABLE` | 无离场、无加仓成交 | 保持持仓可加仓 | `OPEN_ADDABLE` |
| `OPEN_NO_ADD_ON` | `T-1` 跌破 MA60 或 MA25 | 禁止分批减仓，等待 `T` 收盘确认 | `EXIT_WATCH` |
| `OPEN_NO_ADD_ON` | 达到 5% 或 15% 分批减仓条件且成交 | 标记对应阶段完成，重算剩余成本 | `OPEN_NO_ADD_ON` 或 `PENDING_FULL_EXIT` |
| `OPEN_NO_ADD_ON` | 无离场、无分批减仓成交 | 保持持仓禁加仓 | `OPEN_NO_ADD_ON` |
| `EXIT_WATCH` | `T` 收盘确认仍满足 MA60/MA25 清仓条件且卖出全部成交 | 结束生命周期 | `CLOSED` |
| `EXIT_WATCH` | `T` 收盘确认仍满足 MA60/MA25 清仓条件但卖出失败或未全部卖完 | 保留不可撤销清仓意图 | `PENDING_FULL_EXIT` |
| `EXIT_WATCH` | `T` 收盘不再满足清仓确认 | 退出离场观察，按盈利/成本状态回到普通持仓 | `OPEN_ADDABLE` 或 `OPEN_NO_ADD_ON` |
| `PENDING_FULL_EXIT` | 下一交易日卖出全部剩余仓位成功 | 结束生命周期 | `CLOSED` |
| `PENDING_FULL_EXIT` | 下一交易日仍卖出失败或未全部卖完 | 继续挂起清仓，不重新判断持有条件 | `PENDING_FULL_EXIT` |
| 任意持仓状态 | 回测结束仍有持仓 | 输出强制清仓视图和剔除未完成视图 | `OPEN_AT_END` |
| `OPEN_AT_END` | 强制清仓成功 | 仅在强制清仓视图中形成结束记录 | `CLOSED` |
| `OPEN_AT_END` | 强制清仓失败 | 记录期末清仓失败，剔除未完成视图保留未完成状态 | `OPEN_AT_END` |
| `CLOSED` | 下一交易日重新满足入场条件且买入成交 | 开启新的交易生命周期 | `ENTRY_LOCKED_T1` |

## 生命周期黄金场景

第一批 `Lifecycle Golden Scenario` 用于验收 `Execution Lifecycle Component`。这些场景后续应直接转成测试。

| 场景 | 覆盖转换 | 核心验收 |
|---|---|---|
| `LGS-01` 入场到 T+1 锁定 | `FLAT -> ENTRY_LOCKED_T1` | `T` 开盘买入成交后记录买入 lot；`T` 当天禁止卖出、加仓和分批减仓 |
| `LGS-02` 可加仓到加仓锁定 | `OPEN_ADDABLE -> ENTRY_LOCKED_T1` | 未曾盈利且满足加仓条件时允许加仓；加仓成交后新 lot 进入 T+1 锁定 |
| `LGS-03` 曾经盈利禁加仓 | `OPEN_ADDABLE -> OPEN_NO_ADD_ON` | 当前生命周期一旦曾经盈利或成本收回，后续永久禁止加仓，即使后来回落亏损 |
| `LGS-04` 分批减仓和成本重算 | `OPEN_NO_ADD_ON -> OPEN_NO_ADD_ON` | 5% 和 15% 分批减仓按当前持仓数量执行；真实成交才标记阶段完成，并按净卖出金额重算剩余成本 |
| `LGS-05` 离场观察后清仓成功 | `OPEN_ADDABLE/OPEN_NO_ADD_ON -> EXIT_WATCH -> CLOSED` | `T-1` 跌破 MA60/MA25 后禁止加仓和分批减仓；`T` 收盘确认后尾盘清仓成功 |
| `LGS-06` 清仓失败进入挂起 | `EXIT_WATCH -> PENDING_FULL_EXIT` | `Full Exit` 已确认但因跌停、停牌或 T+1 未能全部卖出时，记录不可撤销挂起清仓 |
| `LGS-07` 挂起后继续卖到清仓 | `PENDING_FULL_EXIT -> CLOSED` | 挂起期间不重新判断 MA 是否收回，不允许加仓/分批减仓；只继续卖，直到清仓 |
| `LGS-08` 期末未完成双视图 | `任意持仓状态 -> OPEN_AT_END` | 回测结束仍有持仓时输出强制清仓视图和剔除未完成视图；跌停/停牌/缺价格时记录强制清仓失败 |

## 口径确认记录

已确认：

- `沪深300，中证500` 指两个指数的成分股股票池，不是直接交易指数或 ETF。
- 第一版先使用固定股票列表跑通真实策略回测，不使用历史成分股快照；报告需要标注固定样本和幸存者偏差风险。
- 第一版必须按 `T` 开盘价买入/加仓，按 `T` 尾盘价卖出，并且遵守至少持有 1 个交易日的 T+1。
- 同一标的在 `T` 开盘发生买入或加仓后，`T` 当天跳过所有卖出判断，最早 `T+1` 再判断卖出。
- 5% 和 15% 的分批止盈必须真实减仓，并保留剩余仓位继续参与后续止盈/止损。
- 一个标的分三次买满，每次买单股满仓目标的 33%；计算数量按 1 手向下取整，不足 1 手则不买。
- 分批减仓卖出数量按 1 手向下取整；不足 1 手跳过本次减仓。最终清仓时卖出全部剩余可卖仓位。
- 第一版是 `Trade-Sample Backtest`：总资产 100 亿，最大持仓数量 200，每个股票最大市值 5000 万，单次买入目标市值 1650 万；不看总盈利，只统计成交股票和交易样本。
- 最大持仓数量 200 既是每股最大市值分母，也是同时持仓股票数硬上限；如果触发上限，新开仓不成交并记录 `MAX_HOLDING_COUNT`。
- 当前同时持仓数达到 200 时，已有持仓仍允许加仓，因为加仓不增加不同股票持仓数量。
- 当前交易生命周期只要曾经盈利过，后续永久不再加仓；即使后来回落亏损，也不恢复加仓资格。
- MACD DEA 最近上水：`dea[T-1] > 0`，当前 DEA 上水周期的上水天数 `<= 14` 个交易日；`0` 按未上水/水下处理。
- 如果历史数据里找不到 DEA 上水日，即使 `dea[T-1] > 0`，也视为不满足。
- 止损和 MA25 止盈的“第二天未收回”都用第二天收盘价判断；即 `T-1` 跌破，`T` 收盘仍在 MA 下方，才在 `T` 尾盘卖出。
- 同一天如果同时满足 MA60 卖出和 MA25 卖出，执行清仓即可；报告同时记录两个触发证据，最终盈亏按交易结算结果判断。
- 同一天如果同时满足 `Full Exit` 和分批减仓，执行清仓，不做分批减仓。
- 分批减仓同一天最多执行一个阶段；如果 5% 和 15% 同时满足，先执行尚未完成的最低阶段。
- 分批减仓数量按触发当时的当前持仓数量计算，不按单股满仓目标计算。
- MA25 止盈必须在卖出确认日 `T` 收盘仍然盈利，才允许清仓；如果 `close[T] <= 当前剩余成本`，即使跌破 MA25 也不按 MA25 止盈卖出。
- `T-1` 跌破 MA60 后，`T` 不加仓，只等待 `T` 收盘是否确认止损。
- `T-1` 跌破 MA25 后，`T` 不加仓，只等待 `T` 收盘是否确认 MA25 止盈。
- 入场、加仓、离场不是一个大组合条件；无持仓才判断入场，有持仓先判断离场，离场观察或确认存在时不判断入场/加仓。
- 离场清仓后的下一交易日，如果重新满足入场条件，允许作为新的交易生命周期重新开仓。
- 同一天多个无持仓股票满足入场条件时，全部买入，直到达到 200 个不同股票持仓上限；第一版不做排序、不做信号强弱筛选。
- 第一版主计算只跑含费用和滑点的净口径；不带手续费、印花税、滑点等成本的毛口径从同一批成交记录去掉成本项派生，用于对照信号本身，不单独驱动策略。
- 费用、税费、滑点都必须是 RunPlan/配置项，不能硬编码；报告需要披露本次实际使用的成本配置。
- 第一版使用固定股票池清单文件，RunPlan 只引用该文件；清单至少包含 `ts_code`、名称、来源指数、冻结日期，不在策略运行时动态拉取当前成分股。
- 买入当天如果停牌、涨停、数据缺失或其他约束导致不可成交，本次入场不顺延，直接拒绝并记录原因；后续必须重新满足入场条件才可再次买入。
- 卖出当天如果停牌、跌停、T+1 可卖数量不足或其他约束导致未能全部卖出，保留退出意图和持仓，下一交易日继续尝试卖出，直到可卖数量清仓完成。
- `Full Exit` 一旦确认，后续即进入不可撤销的 `Pending Exit Intent`；即使价格重新收回 MA 线上，也不取消卖出，不允许加仓、分批止盈或重新判断是否继续持有，只继续卖到清仓完成。
- 回测结束仍未清仓的持仓需要输出两份结果：一份强制清仓报告，一份剔除未完成交易报告；两份报告必须明确标注口径，不能混在同一个胜率/盈亏统计里。
- 强制清仓报告中，除跌停外都按回测结束日收盘价卖出；如果期末跌停，则卖不出，视为强制清仓交易失败，标记 `END_LIQUIDATION_LIMIT_DOWN`，不能伪造成已完成清仓交易。
- 强制清仓报告中，如果期末停牌或没有回测结束日收盘价，不使用最后可用价伪造成期末成交，记录 `END_LIQUIDATION_SUSPENDED` 或 `END_LIQUIDATION_PRICE_MISSING`，作为强制清仓交易失败单独统计。
- 涨停、跌停、停牌等可交易状态以 `TradabilityStatus` 快照为准；策略不自行计算涨跌停，买入、卖出和强制清仓都读取同一份按 `symbol + trade_date` 的可交易状态。
- 分批止盈后，后续策略触发按卖出后重算的新成本计算，不按原始买入成本计算；原始加权买入成本仍保留为复盘字段。
- 卖出后重算的新成本按带费用/滑点的净口径计算；无费用结果不重新驱动策略，只从已成交记录去掉成本项派生。
- 如果卖出后重算的新成本 `<= 0`，标记 `cost_recovered=true`，不再用除法计算百分比；后续盈利前置视为满足，未完成的分批止盈阶段在下一个可判断交易日视为达到触发条件，但仍遵守一天只执行一个阶段和 `Full Exit` 优先级。
- 分批减仓只因为收益涨幅或成本收回触发，不因为下跌触发；跌破 MA60/MA25 属于 `Full Exit`，不是分批减仓。
- 分批减仓不挂起。只有真实成交才标记该阶段完成；如果因为 T+1、停牌或可卖数量不足 1 手没有成交，就记录失败原因，阶段保持未完成，下一交易日重新判断是否仍满足收益涨幅或 `cost_recovered=true`。
- 分批减仓目标数量大于当天可卖数量时，当天卖出全部可卖数量；只要实际卖出不少于 1 手，就标记该分批阶段完成一次，不挂起补卖差额。
- 同一天入场候选超过剩余持仓名额时，第一版默认按固定股票池清单顺序买入，直到达到 200 个持仓上限；RunPlan 预留排序配置，但默认不开启，后续如开启排序必须作为单独实验口径。
- 回测需要预热数据区间：`data_start` 固定为 `backtest_start` 往前一年，数据拉取和指标计算从 `data_start` 开始，交易统计和报告只从 `backtest_start` 开始；resolved RunPlan 和报告必须记录最终 `data_start`。
- 关键指标需要做空值覆盖率检查：`ma60`、`ma25`、`macd/dea` 等必需指标按 `symbol + indicator` 统计；如果回测统计区间内空值率超过 5%，触发 `Indicator Coverage Alarm` 并让本次回测失败，诊断输出问题最严重的标的和指标，不能静默继续并把缺失当作策略不触发。
- 指标空值率只在有效日期上统计：该标的有基础日线且已满足对应指标 warmup 后才进入分母；上市前、无基础行情、warmup 期不计入异常，但要在诊断里单独列出样本覆盖限制。
- 固定股票池回测前必须自动执行数据预检过滤：`ok` 和 `warning` 标的进入回测，`error` 标的自动剔除；最终报告必须披露原始股票数、保留数、warning 数、剔除数和剔除原因，不能要求人工先生成过滤后的股票池。
- 第一版使用前复权价差口径：指标、交易收益、分批止盈、成本重算和费用/滑点模拟都使用前复权价格；报告必须明确标记这不是严格现金分红、送转、未复权真实成交和完整公司行为核算口径。
- 第一版继续计算费用、税费和滑点，但这是 `Adjusted Price Cost Simulation`：在前复权模拟成交金额上应用配置成本，主结论看带成本净口径，去成本毛口径从同一批成交事件派生；报告不得把它描述成券商真实现金扣费。
- 第一版继续用前复权价格模拟订单数量、一手约束、T+1 可卖数量和分批减仓数量；报告标记为 `Adjusted Price Quantity Simulation`，不得描述成券商真实股数。
- 当前回测框架的目的不是得到完美收益结果，而是 `Strategy Environment Discovery`：找到策略适合的土壤和不适合的地方，用于后续趋利避害、提高实际使用收益。
- 当前阶段只做归因和环境证据积累，不做参数优化、过滤规则优化或买卖逻辑调整；所有优化建议先作为 `Attribution Candidate` 记录，等归因样本、字段和稳定性判断足够后，再进入独立优化实验。
- 第一版环境发现报告先固定大盘环境、行业环境、个股入场结构、交易执行状态四类 `Environment Dimension`；这些维度只是第一版起点，后续可以新增维度，也可以把每个维度里的字段继续细化。
- 第一版环境字段先采用少量但有解释力的 `Environment Factor`：大盘趋势/市场温度，行业名称/行业趋势，个股 MA60/MA25/DEA 上水/阴线，执行拒绝或挂起状态；后续可以继续新增字段。
- 环境字段通过 `Post-Trade Environment Lookup` 产生：先有交易记录，再反查该笔交易对应的指数、行业、个股和执行环境；这些字段只做归因和环境矩阵，不进入第一版买卖规则。
- 大盘环境反查同时记录沪深300和中证500的大盘趋势/市场温度，并额外记录该股票来源指数对应的环境。
- 第一版实现顺序先补 `Execution Lifecycle Foundation`，再接 `baoma_v1` 信号；否则交易记录不可信，环境反查和报告都会失真。
- `Execution Lifecycle Foundation` 通过新增业务层 `Execution Lifecycle Component` 实现，由现有 Backtrader 桥调用；组件建议放在 `attbacktrader/engines/business/`，避免把规则直接塞进 Backtrader strategy bridge。
- 当前按 `4 -> 1` 推进：先定义 `Lifecycle Golden Scenario`，明确什么叫交易记录可信；再实现业务层 `Execution Lifecycle Component`，并让它产出的 `Authoritative Lifecycle Output` 成为报告、环境反查和 AI review 的权威证据。
- 在定义 `Lifecycle Golden Scenario` 之前，先和用户对齐 `Strategy Lifecycle State Machine`；黄金场景必须从状态机推导，避免遗漏状态冲突。
- 在命名 `Strategy Lifecycle State Machine` 之前，先列 `Lifecycle Action Permission Table`；用动作权限发现冲突，再收敛状态名。
- 第一版 `Lifecycle Action Permission Table` 已确认，优先级为：清仓挂起 > 离场观察 > T+1 未满足 > 曾经盈利禁加仓 > 普通持仓。
- 第一版状态机主状态使用英文枚举，中文报告通过 `Lifecycle State Label` 显示中文标签。
- 第一版 `Lifecycle Transition Table` 已确认：状态转换按权限优先级执行，`PENDING_FULL_EXIT` 只重试清仓；普通持仓先判断离场观察，再判断 T+1 锁定，再判断曾经盈利/成本收回，再判断分批减仓和加仓。
- 第一批 `Lifecycle Golden Scenario` 已确认，共 8 个，覆盖入场 T+1、加仓锁定、盈利禁加仓、分批减仓/成本重算、清仓成功、清仓挂起、挂起后清仓和期末未完成双视图。
- 第一批黄金场景同时落文档表和 pytest golden tests；先写 `tests/test_execution_lifecycle_component.py`，再实现业务层 `Execution Lifecycle Component` 让测试通过。
