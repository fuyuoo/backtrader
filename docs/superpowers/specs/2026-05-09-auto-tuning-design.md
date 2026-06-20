# Auto-Tuning Skill 设计规格

**日期**: 2026-05-09  
**状态**: 待实现  
**作者**: fuyuoo + Claude

---

## 1. 目标

为 `my_strategy/` 下的量化交易策略开发一个 **AI 驱动的自动参数优化系统**，以 Claude Code Skill（`/auto-tune`）形式实现。系统在一个 Claude Code 会话中全程自主运行，无需人工干预，通过迭代回测+归因分析找到最优策略参数。

---

## 2. 核心架构：Master-Worker Skill

### 2.1 角色分工

| 角色 | 实现方式 | 职责 |
|------|---------|------|
| **主 Agent** | Claude Code 会话本身 | 持有优化历史、决策下一批参数、判断终止 |
| **子 Agent** | `Agent` 工具并行派生 | 运行单组参数回测 + 读取全部归因 + 生成分析摘要 |
| **编排层** | Skill 指令 | 管理轮次循环、传递结果、写 checkpoint |

### 2.2 运行流程

```
用户: /auto-tune
      │
      ▼
主 Agent（Claude Code 会话）
      │
      ├── 读取 tune_config.json（参数范围、时间窗口）
      ├── 读取 checkpoint.json（已有历史，支持续跑）
      │
      └── 循环（IS 阶段，最多 max_rounds 轮）:
          ├── 主 Agent 推理 → 输出本轮 N 组参数（JSON）
          ├── 同时派生 N 个子 Agent（Agent 工具，并行）
          │   每个子 Agent:
          │   ├── 创建独立工作目录 runs/round_XX_setY/
          │   ├── 写临时 config.json（IS 时间窗口 + 当前参数）
          │   ├── Bash: python backtest.py --workdir runs/round_XX_setY/
          │   ├── Read: 读取 runs/round_XX_setY/reports/ 全部 CSV
          │   └── 返回结构化分析 JSON 给主 Agent
          ├── 主 Agent 收集所有子 Agent 结果
          ├── 更新 checkpoint.json
          └── 判断: 继续 / 切换 OOS / 结束
      │
      ├── OOS 阶段:
      │   ├── 取 Top 3 参数组
      │   ├── 派生 3 个子 Agent（OOS 时间窗口，完整归因）
      │   └── 主 Agent 选出最优参数
      │
      └── 输出最终结果到 tune/best_params.json
```

---

## 3. 时间窗口

| 阶段 | 时间窗口 | 市场覆盖 | 用途 |
|------|---------|---------|------|
| IS（样本内） | 2013-01-01 → 2018-12-31 | 杠杆牛市、2015 股灾、慢牛、贸易战熊市 | 参数优化 |
| OOS（样本外） | 2019-01-01 → 2023-12-31 | 基金牛市、疫情 V 形、熊市、震荡 | 最终验证 |

两段各 5 年，均覆盖牛/熊/震荡三种市场环境，非重叠。

---

## 4. 优化参数空间

| 参数 | 默认值 | 搜索范围 | 含义 |
|------|-------|---------|------|
| `take_profit_1_pct` | 0.05 | [0.03, 0.10] | 第一档止盈比例 |
| `take_profit_2_pct` | 0.10 | [0.08, 0.20] | 第二档止盈比例 |
| `dea_lookback_days` | 5 | [3, 10] | DEA 回看天数 |
| `atr_period` | 20 | [10, 30] | ATR 周期 |
| `atr_multiplier` | 1.5 | [1.0, 3.0] | ATR 止损乘数 |
| `take_profit_min_pct` | 0.03 | [0.02, 0.06] | 动态止盈下限 |
| `take_profit_max_pct` | 0.12 | [0.08, 0.20] | 动态止盈上限 |
| `max_positions` | 200 | [50, 300] | 最大持仓数 |

---

## 5. 子 Agent 详细流程

### 5.1 输入
主 Agent 传入：一组参数值 + IS 时间窗口 + 工作目录路径

### 5.2 执行步骤

```
Step 1 — 环境准备
  创建目录: my_strategy/tune/runs/round_{N}_set{M}/
  写入 config.json（继承 my_strategy/config.json，覆盖参数和时间窗口）

Step 2 — 运行回测
  Bash: cd my_strategy && python backtest.py --workdir tune/runs/round_{N}_set{M}/
  等待完成（预计 ~6 分钟/次）

Step 3 — 读取全部归因报告
  Read: tune/runs/round_{N}_set{M}/reports/ 下所有 CSV（数量随 attribution 模块演进）
  包含: entry_condition_stats, exit_reason_stats, factor_alpha,
        loss_attribution, yearly_stats, trade_profile 等全部输出

Step 4 — 生成结构化分析
  Claude 综合所有报告，输出标准 JSON：
  {
    "params": {...},
    "metrics": {
      "sharpe": float,
      "annual_return": float,
      "max_drawdown": float,
      "win_rate": float,
      "total_trades": int
    },
    "insights": ["MA60止损触发率下降至12%", "KDJ入场在2015熊市完全失效"],
    "weakness": ["2015股灾最大回撤达31%，超过阈值"],
    "recommendation": "atr_multiplier 可继续加大，take_profit_1_pct 无需调整"
  }
```

### 5.3 并行隔离

每个子 Agent 使用独立工作目录，避免并发写冲突：
- config.json → `tune/runs/round_{N}_set{M}/config.json`
- 归因报告 → `tune/runs/round_{N}_set{M}/reports/`
- 回测结果 → `tune/runs/round_{N}_set{M}/results/`

---

## 6. 主 Agent 决策逻辑

### 6.1 系统角色
量化策略参数优化专家，目标：在 IS 期最大化夏普比率，同时约束最大回撤 < 30%。

### 6.2 每轮输入（传给主 Agent）
- 历史所有轮次：参数组 + 核心指标摘要
- 本轮所有子 Agent 的完整分析 JSON

### 6.3 每轮输出（主 Agent 严格 JSON）
```json
{
  "round": 3,
  "reasoning": "atr_multiplier 从 1.5→2.0 止损触发率下降 8pp，继续探索更大值；take_profit_1_pct 在 0.05-0.06 表现稳定，暂不调整",
  "next_params": [
    {"take_profit_1_pct": 0.06, "atr_multiplier": 2.5, "dea_lookback_days": 5, ...},
    {"take_profit_1_pct": 0.05, "atr_multiplier": 3.0, "dea_lookback_days": 7, ...}
  ],
  "done": false
}
```

### 6.4 每轮子 Agent 数量
- 推荐并行数：4-6 组（物理核心 12，每次回测约 6 分钟，保留系统余量）
- 最大并行数：10（i7-12700，64GB RAM）

---

## 7. 终止条件

以下任一触发时，IS 阶段结束，进入 OOS：

| 条件 | 阈值 |
|------|------|
| 主 Agent 判断收敛 | `"done": true` |
| 达到最大轮次 | `max_rounds = 15`（tune_config.json 配置） |
| 连续平台期 | 连续 3 轮最优夏普提升 < 0.05 |

---

## 8. Checkpoint 机制

每轮结束后写入 `my_strategy/tune/checkpoint.json`：

```json
{
  "phase": "IS",
  "current_round": 5,
  "history": [
    {"round": 1, "params": {...}, "sharpe": 1.12, "max_drawdown": -0.24},
    ...
  ],
  "best_params_so_far": {...},
  "best_sharpe_so_far": 1.38
}
```

重新运行 `/auto-tune` 时，若 checkpoint 存在，主 Agent 从当前轮次续跑。

---

## 9. 文件清单

### 新增文件

```
.claude/commands/
└── auto-tune.md                  ← Skill 定义（主循环指令 + 子 Agent 提示模板）

my_strategy/tune/
├── tune_config.json              ← IS/OOS 时间窗口、参数范围、max_rounds
├── checkpoint.json               ← 运行时自动创建/更新
├── best_params.json              ← 最终输出
└── runs/                         ← 运行时自动创建
    └── round_{N}_set{M}/
        ├── config.json
        ├── results/
        └── reports/
```

### 改动现有文件

```
my_strategy/backtest.py           ← 加 --workdir 参数（读写目录从默认路径改为指定路径）
```

`--workdir` 语义：backtest.py 从 `{workdir}/config.json` 读取配置，将 `results/` 和 `reports/` 写入 `{workdir}/` 下。子 Agent 在运行前负责写好 `{workdir}/config.json`。

---

## 10. IS → OOS 两阶段

```
IS 阶段完成后:
  主 Agent 选出历史最优 Top 3 参数组

OOS 阶段:
  派生 3 个子 Agent（时间窗口改为 2019-2023，完整归因）
  主 Agent 对比 3 组 OOS 结果
  选出 OOS 夏普最优的参数组

最终输出:
  tune/best_params.json  ← 最终推荐参数
  tune/oos_comparison.json  ← 3 组 OOS 对比报告
```

---

## 11. 不在本次范围内

- 多策略同时优化（只针对当前 MyStrategy）
- 基因算法/贝叶斯优化（主 Agent 自主推理替代）
- 实盘对接
- 结果可视化 Dashboard

---

## 12. 成功标准

- `/auto-tune` 单次调用后，无需用户干预完成全部 IS 轮次和 OOS 验证
- 最终输出 `best_params.json`，包含 OOS 夏普、最大回撤等核心指标
- checkpoint 机制确保会话中断后可续跑
- 并行子 Agent 无文件冲突
