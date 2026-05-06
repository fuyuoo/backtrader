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

---

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
