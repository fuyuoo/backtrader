# `my_strategy` 平台化改造开发准备说明

**日期**：2026-05-09  
**状态**：准备开发  
**依据文档**：`docs/superpowers/specs/2026-05-09-my-strategy-platformization-design.md`  
**适用范围**：仅限 `my_strategy/` 下的平台化改造准备，不修改 `backtrader/` 原版框架源码  

---

## 1. 文档定位

本文件用于把已经完成的“平台化改造设计”转成开发前的边界说明和检查清单。

当前状态是：

- 设计文档已经存在，见 `docs/superpowers/specs/2026-05-09-my-strategy-platformization-design.md`。
- 本阶段尚未开始代码改动。
- 下一步应进入 implementation plan，而不是直接改代码。

因此，本文件不重复完整架构设计，只回答开发前必须明确的几个问题：

- 第一阶段先做什么，不做什么。
- 哪些文件和输出目录会受到影响。
- 开发前需要记录哪些基线。
- 怎么判断第一阶段改造成功。
- 哪些风险不能静默处理。

---

## 2. 核心假设

开发前默认采用以下假设。

1. 原版 `backtrader/` 目录作为第三方回测内核看待，本轮不修改。
2. 平台化能力全部落在 `my_strategy/` 内。
3. 第一阶段目标不是提升收益，而是提升运行隔离、结果可追溯和后续扩展能力。
4. 同一份输入数据、同一组参数下，第一阶段改造不应改变交易行为。
5. 当前 `strategy.py` 暂不大拆，先解决输出污染和运行追溯问题。

如果后续发现这些假设不成立，应先更新设计或计划，再进入实现。

---

## 3. 开发原则

### 3.1 只做平台底座

第一阶段只建设运行隔离底座，不引入新交易规则、不新增调参逻辑、不改变现有策略参数含义。

优先级如下：

```text
1. 运行隔离
2. 运行清单
3. 输出路径收敛
4. 结果可复盘
5. 再进入历史股票池、标签引擎、策略拆分
```

### 3.2 不改变策略语义

以下行为不应在第一阶段被改动：

- 买入条件。
- 卖出条件。
- 加仓条件。
- 止盈止损条件。
- 仓位计算。
- 涨跌停过滤。
- 交易记录字段含义。

如果实现过程中必须触碰这些逻辑，应把它视为范围变更，并单独确认。

### 3.3 不静默降级

平台化改造中任何失败都应暴露真实错误。

禁止：

- 路径不存在时悄悄写到默认目录。
- 报告缺文件时跳过并继续。
- `run_manifest.json` 写入失败但回测继续。
- `signals_log.csv` 写入失败但不报错。
- 回测参数缺失时使用不明确的隐式默认值。

允许的兼容行为必须显式记录，例如保留旧 `--tag` 参数时，应说明它如何映射到新 run 目录。

---

## 4. Phase 1 开发边界

Phase 1 的主题是“运行隔离”。目标是让每一次回测都有独立、完整、可审计的输出目录。

### 4.1 目标输出结构

建议第一阶段形成以下结构：

```text
my_strategy/runs/
  <run_id>/
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

其中：

- `config.json` 是本次运行使用的配置快照。
- `run_manifest.json` 是本次运行的元数据。
- `universe_snapshot.csv` 是本次运行实际使用的股票池快照。
- `results/` 保存回测原始产物。
- `reports/` 保存归因分析产物。

### 4.2 最小必做内容

Phase 1 最小范围：

1. 增加统一的 run 输出目录。
2. 将 `signals_log.csv` 从全局路径迁移到本次 run 的 `results/` 下。
3. 让归因报告从本次 run 的 `results/` 读取数据。
4. 写入 `run_manifest.json`。
5. 写入或复制本次使用的配置快照。
6. 保留足够兼容，确保现有单次回测入口仍能运行。

### 4.3 暂不做内容

Phase 1 不做：

- 历史指数成分股动态切换。
- 新标签字段计算。
- `strategy.py` 大规模拆分。
- 自动调参。
- 样本外验证。
- UI 或 Dashboard。
- 实盘交易接口。

这些内容留到后续 Phase。

---

## 5. 预计受影响文件

以下是开发前预判，不代表最终必须全部修改。

| 文件 / 目录 | 预计变化 |
|---|---|
| `my_strategy/backtest.py` | 增加 run 目录解析、配置快照、manifest 写入、结果路径传递 |
| `my_strategy/src/strategy.py` | 只允许做输出路径注入相关的小改动，不改策略条件 |
| `my_strategy/tools/attribution_runner.py` | 从指定 run 的 `results/` 读取，输出到指定 run 的 `reports/` |
| `my_strategy/tools/attribution.py` | 如存在硬编码路径，需要收敛到传入路径 |
| `my_strategy/tools/trade_attribution_extra.py` | 如存在硬编码路径，需要收敛到传入路径 |
| `my_strategy/tools/portfolio_attribution.py` | 如存在硬编码路径，需要收敛到传入路径 |
| `my_strategy/tools/position_curve_attribution.py` | 如存在硬编码路径，需要收敛到传入路径 |
| `my_strategy/tests/` | 增加或更新路径隔离、manifest、signals log 输出相关测试 |
| `docs/FEATURES.md` | Phase 1 完成后更新功能总览 |
| `docs/CHANGELOG.md` | Phase 1 完成后追加更新记录 |

注意：文档维护规则只在完成 `my_strategy/` 功能改动后触发。本文档本身只是开发准备说明，不代表功能已实现。

---

## 6. 开发前基线检查

进入实现前应先记录当前行为，避免平台化改造改变策略结果却没有被发现。

### 6.1 Git 状态

开发前必须确认工作区状态，至少记录：

```powershell
git status --short
git log --oneline -5
```

如果存在未提交修改，应先提交、暂存，或由用户明确确认忽略范围。

### 6.2 测试基线

建议先运行：

```powershell
python -m pytest my_strategy/tests
```

若测试失败，不应直接开始改造。需要先确认失败是否为已知问题，或单独修复。

### 6.3 回测输出基线

建议至少保存一组现有默认回测结果作为对照：

```powershell
python my_strategy/backtest.py
```

需要关注：

- `trade_list.csv` 行数。
- `trade_summary.csv` 行数和核心字段。
- `signals_log.csv` 行数。
- 组合最终权益。
- 年化收益、最大回撤、胜率等核心指标。

如果默认回测耗时过长，可以使用现有支持的较小股票池或较短时间窗口，但必须在计划中写清楚对照范围。

---

## 7. Phase 1 验收标准

Phase 1 完成时，应同时满足以下标准。

### 7.1 运行隔离

- 连续运行两次回测，不会互相覆盖输出。
- 并行运行不同参数组，不会写同一个 `signals_log.csv`。
- 每次运行都生成独立 `runs/<run_id>/`。

### 7.2 可追溯

每个 run 目录至少能回答：

- 本次运行使用了哪些参数。
- 本次运行使用了哪个回测区间。
- 本次运行输出路径在哪里。
- 本次运行使用了哪些股票。
- 本次运行是否生成了完整 results 和 reports。

### 7.3 策略结果不漂移

在相同输入和相同参数下，Phase 1 改造前后的核心交易结果应保持一致。

至少对比：

- 交易笔数。
- 入场日期和股票代码。
- 出场日期和出场原因。
- 每笔收益。
- 最终权益。

如果有差异，必须解释差异来源。不能把差异归因于“路径改造”后直接接受。

### 7.4 测试覆盖

至少应覆盖：

- run 目录创建。
- `run_manifest.json` 内容。
- `signals_log.csv` 写入到 run 内。
- 报告从 run 内读取输入。
- 缺少必要文件时抛出清晰异常。

---

## 8. 主要风险

### 8.1 旧路径硬编码

当前系统可能在多个位置默认读取：

```text
my_strategy/results/
my_strategy/reports/
my_strategy/data/signals_log.csv
```

如果只改入口，不改下游工具，可能出现“回测写到了 run 目录，但报告仍读取旧目录”的错误。

处理原则：

- 找出硬编码路径。
- 统一通过参数或运行上下文传递。
- 不允许读取失败后自动回退旧目录。

### 8.2 `--tag` 与新 run 目录关系

当前已有 `--tag` 隔离部分输出。Phase 1 需要明确它与新 run 目录的关系。

推荐处理：

- 保留 `--tag` 作为 run_id 的可选组成部分。
- 新增或统一使用 `--workdir` 指定完整输出根目录。
- 所有输出最终都归入同一个 run 目录。

### 8.3 归因报告输入来源不一致

归因工具较多，可能有的读 `results/`，有的读 `data/`，有的读默认配置。

处理原则：

- 每个报告函数都应明确输入文件。
- 顶层 runner 负责把 run 内路径传给各报告。
- 缺文件时直接报错，暴露具体路径。

### 8.4 历史结果对比困难

路径变化后，旧报告位置和新报告位置不同，人工对比容易混乱。

处理原则：

- 首次改造时保留一份基线 run。
- 在文档或测试中写明对比对象。
- 不把旧目录和新目录混合读取。

---

## 9. 后续衔接

本准备文档确认后，下一步应进入 implementation plan。

implementation plan 应进一步拆到可执行任务，例如：

1. 梳理现有输出路径调用点。
2. 设计 run context / path resolver。
3. 修改 `backtest.py` 输出目录。
4. 修改 `strategy.py` 信号日志路径注入。
5. 修改 attribution runner 输入输出路径。
6. 补充测试。
7. 跑基线对比。
8. 更新 `docs/FEATURES.md` 和 `docs/CHANGELOG.md`。

在 implementation plan 被确认前，不应开始代码实现。

---

## 10. 开发前最终检查清单

开始 Phase 1 实现前，确认以下事项：

- [ ] 用户已确认从 Phase 1“运行隔离”开始。
- [ ] 工作区状态已检查，未提交改动已处理或明确忽略。
- [ ] 当前测试基线已记录。
- [ ] 当前回测输出基线已记录。
- [ ] 已确认不修改 `backtrader/` 原版框架源码。
- [ ] 已确认第一阶段不改变策略交易语义。
- [ ] 已确认缺文件、缺配置、路径错误必须抛出异常。
- [ ] 已确认 Phase 1 完成后更新 `docs/FEATURES.md` 和 `docs/CHANGELOG.md`。

