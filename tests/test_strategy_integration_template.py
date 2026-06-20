from attbacktrader.strategies import (
    STRATEGY_INTEGRATION_TEMPLATE_SCHEMA,
    STRATEGY_OUTPUT_CONTRACT_SCHEMA,
    build_strategy_integration_template,
    render_strategy_integration_template_markdown_zh,
)


def test_strategy_integration_template_names_required_touch_points() -> None:
    template = build_strategy_integration_template()
    paths = {item["path"] for item in template["files_to_touch"]}

    assert template["schema"] == STRATEGY_INTEGRATION_TEMPLATE_SCHEMA
    assert template["strategy_output_contract_schema"] == STRATEGY_OUTPUT_CONTRACT_SCHEMA
    assert "attbacktrader/strategies/bindings.py" in paths
    assert "tests/test_strategy_methods.py" in paths
    assert "tests/test_strategy_bindings.py" in paths
    assert "tests/test_strategy_output_contract.py" in paths
    assert any("required_indicators" in item for item in template["method_contract"])
    assert any("TradeIntent" in item for item in template["method_contract"])
    assert any("acceptance_smoke.py" in item for item in template["acceptance_checks"])


def test_strategy_integration_template_markdown_is_ai_readable() -> None:
    markdown = render_strategy_integration_template_markdown_zh()

    assert "# 策略接入模板" in markdown
    assert "## 需要修改的文件" in markdown
    assert "## 方法契约" in markdown
    assert "## 验收命令" in markdown
    assert "Strategy Output Contract" not in markdown
    assert "输出契约" in markdown
