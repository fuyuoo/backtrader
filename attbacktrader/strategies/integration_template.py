"""Machine-readable template for integrating future strategy methods."""

from __future__ import annotations

from typing import Any

from .contract import STRATEGY_OUTPUT_CONTRACT_SCHEMA


STRATEGY_INTEGRATION_TEMPLATE_SCHEMA = "attbacktrader.strategy_integration_template.v1"


def build_strategy_integration_template() -> dict[str, Any]:
    """Return the strategy integration template used by docs, tests, and AI review."""

    return {
        "schema": STRATEGY_INTEGRATION_TEMPLATE_SCHEMA,
        "strategy_output_contract_schema": STRATEGY_OUTPUT_CONTRACT_SCHEMA,
        "purpose_zh": "让未来新策略按固定输出接入回测、归因、市场验证和 AI 复盘。",
        "integration_boundary_zh": "新增策略只负责声明指标需求并输出 TradeIntent；报告层只消费已落盘证据。",
        "files_to_touch": [
            {
                "path": "attbacktrader/strategies/methods/<entry|profit_taking|stop_loss|add_on>.py",
                "purpose_zh": "实现策略方法，声明 required_indicators，并返回 TradeIntent。",
            },
            {
                "path": "attbacktrader/strategies/methods/__init__.py",
                "purpose_zh": "导出新方法，便于绑定和测试引用。",
            },
            {
                "path": "attbacktrader/strategies/bindings.py",
                "purpose_zh": "把方法名绑定到 trend_template_v1 的可选组件。",
            },
            {
                "path": "tests/test_strategy_methods.py",
                "purpose_zh": "验证触发/不触发路径、reason_code、checks 和指标缺失路径。",
            },
            {
                "path": "tests/test_strategy_bindings.py",
                "purpose_zh": "验证配置可选值、参数校验和 required_indicators 汇总。",
            },
            {
                "path": "tests/test_strategy_output_contract.py",
                "purpose_zh": "确认新方法输出符合策略输出契约。",
            },
            {
                "path": "examples/<strategy-run>.yaml",
                "purpose_zh": "提供一个可运行 RunPlan，作为后续回测入口。",
            },
        ],
        "method_contract": [
            "method_name 必须是稳定字符串，不能由 RunPlan 参数覆盖。",
            "required_indicators 必须声明所有需要预热和增量计算的指标。",
            "evaluate(...) 必须返回 TradeIntent，不能直接下单、写报告或拉数据。",
            "reason_code 必须覆盖触发和不触发路径，便于 signal_audit 解释。",
            "signal_values.checks 只放 bool 判断。",
            "signal_values.attribution.checks/categories/values 使用完整命名空间。",
            "决策语义放在方法或归因层，不能放回指标计算层。",
        ],
        "entry_method_skeleton": [
            "定义 dataclass 方法对象。",
            "声明 method_name 和 required_indicators。",
            "从 MarketFeatureRow 读取已准备好的指标。",
            "先处理指标缺失路径，返回 HOLD + *_UNAVAILABLE。",
            "计算布尔 checks。",
            "构造 attribution payload。",
            "触发时返回 ENTER，否则返回 HOLD。",
        ],
        "run_plan_strategy_snippet": {
            "strategy": {
                "template": "trend_template_v1",
                "entry_method": "<new_entry_method>",
                "profit_taking_method": "<profit_taking_method>",
                "stop_loss_method": "<stop_loss_method>",
                "add_on_method": "none",
                "sizing_rule": "equal_weight",
            }
        },
        "acceptance_checks": [
            "python -m pytest tests/test_strategy_methods.py tests/test_strategy_bindings.py tests/test_strategy_output_contract.py -q",
            "python -m pytest tests/test_run_plan_executor.py tests/test_report_writer.py tests/test_evidence_validation.py -q",
            "python scripts/acceptance_smoke.py",
        ],
        "non_goals": [
            "模板不评价策略收益好坏。",
            "模板不生成自动调参逻辑。",
            "模板不让报告层重新计算策略条件。",
            "模板不把 attribution factor 直接变成交易规则。",
        ],
    }


def render_strategy_integration_template_markdown_zh(template: dict[str, Any] | None = None) -> str:
    payload = template or build_strategy_integration_template()
    lines = [
        "# 策略接入模板",
        "",
        f"- schema: `{payload['schema']}`",
        f"- 输出契约: `{payload['strategy_output_contract_schema']}`",
        f"- 目的: {payload['purpose_zh']}",
        f"- 边界: {payload['integration_boundary_zh']}",
        "",
        "## 需要修改的文件",
        "",
        "| 文件 | 作用 |",
        "|---|---|",
    ]
    for item in payload["files_to_touch"]:
        lines.append(f"| `{item['path']}` | {item['purpose_zh']} |")

    lines.extend(["", "## 方法契约", ""])
    lines.extend(f"- {item}" for item in payload["method_contract"])
    lines.extend(["", "## Entry 方法骨架", ""])
    lines.extend(f"- {item}" for item in payload["entry_method_skeleton"])
    lines.extend(["", "## 验收命令", ""])
    lines.extend(f"- `{item}`" for item in payload["acceptance_checks"])
    lines.extend(["", "## 非目标", ""])
    lines.extend(f"- {item}" for item in payload["non_goals"])
    return "\n".join(lines).rstrip() + "\n"
