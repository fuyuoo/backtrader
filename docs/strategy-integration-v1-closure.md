# Strategy Integration V1 Closure

本文档封板当前策略接入框架阶段。封板对象是策略接入边界、契约、
校验入口和 AI 协作方式，不是当前 KDJ/MA/add-on 测试策略。

## Closure Statement

Strategy Integration V1 is accepted as the handoff point from framework
construction to real strategy backtesting.

下一阶段从真实策略开始：先接入最小真实策略，再跑静态校验，再跑真实回测。

## Accepted Scope

| item | direction | purpose | evidence |
|---|---|---|---|
| `strategy_output_contract` | 策略输出契约 | 固定 `TradeIntent` 和 `signal_values` 形状，让报告、归因、环境适配和 AI 复盘不依赖具体策略实现。 | `attbacktrader/strategies/contract.py`; `docs/architecture/strategy-output-contract.md`; `tests/test_strategy_output_contract.py` |
| `strategy_integration_template` | 策略接入模板 | 给未来策略提供可复制的接入步骤、文件边界、方法骨架和验收命令。 | `attbacktrader/strategies/integration_template.py`; `docs/strategy-integration-template.md`; `tests/test_strategy_integration_template.py` |
| `strategy_integration_validation` | 策略接入校验 | 在完整回测前静态加载 RunPlan、绑定组件、采样调用方法，并检查 `TradeIntent` 输出契约。 | `attbacktrader/strategies/integration_validation.py`; `attbacktrader/cli/strategy_integration_validation.py`; `tests/test_strategy_integration_validation.py` |
| `ai_strategy_integration_skill` | AI 协作 | 让 AI 后续按固定边界新增真实策略，不把框架接入、策略评价和调参混在一起。 | `C:/Users/fff/.agents/skills/attbacktrader-strategy-integration/SKILL.md` |

## Accepted Verification

| check | command | expected |
|---|---|---|
| `strategy_integration_validation_cli` | `python -m attbacktrader.cli.strategy_integration_validation --config examples/run-tushare-expanded-add-on.yaml --json` | `status ok`; required indicators `atr14:D`, `kdj:D`; entry/profit/stop/add-on output contract ok |
| `strategy_integration_tests` | `python -m pytest tests/test_strategy_integration_template.py tests/test_strategy_integration_validation.py tests/test_strategy_output_contract.py tests/test_strategy_bindings.py tests/test_acceptance_smoke.py -q` | `20 passed` |
| `full_pytest` | `python -m pytest -q` | `336 passed` |

## Active Non-Goals

- 当前 KDJ/MA/add-on 策略仍然只是 framework fixture，不代表真实策略方向。
- 不继续调优当前 fixture 的买卖条件、参数或收益表现。
- 不在指标层计算多头趋势、突破、卖飞、市场适配等决策语义。
- 不默认填充 warmup 不足、缺失指标、缺失证据或缺失未来窗口。
- 不做自动参数调优、自动策略搜索或自动策略切换。
- 不把报告层后验归因直接变成交易规则。

## Real Backtest Entry Gate

| gate | rule |
|---|---|
| `strategy_method_contract` | 真实策略先声明 entry/profit_taking/stop_loss/add_on/sizing 的方法名、required indicators、reason_code 和 checks。 |
| `static_validation` | 真实策略 RunPlan 必须先通过 `python -m attbacktrader.cli.strategy_integration_validation --config <yaml> --json`。 |
| `artifact_review` | 真实回测后只从 persisted artifacts 做报告、归因、环境适配和 AI 复盘，不在报告层重跑策略。 |

## Next Stage

| name | direction | purpose |
|---|---|---|
| 接入第一个真实策略最小版 | 真实策略接入 | 用真实买卖逻辑验证策略接入模板、输出契约、静态校验和回测链路。 |
| 为真实策略补 RunPlan 样本 | 回测配置 | 提供一个可重复执行的 YAML 入口，作为静态校验和真实回测的共同输入。 |
| 跑第一版真实回测并落盘 artifacts | 真实回测 | 从结果反推框架缺口，而不是继续抽象扩展框架。 |

## Rules

- Strategy Integration V1 Closure 是框架接入封板，不是策略收益评分。
- 真实策略开发先走模板和静态校验，再跑回测。
- 后续优化应来自真实 run 的 `evidence_validation`、`trade_lifecycle`、`environment_fit`、`review_packet` 和 comparison artifacts。
- 每次完成一个功能后的推荐必须给出三个下一步，并标明方向、作用、最推荐项和原因。
