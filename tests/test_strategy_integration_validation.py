import json
from pathlib import Path

from attbacktrader.cli import strategy_integration_validation as strategy_integration_validation_cli
from attbacktrader.config import load_run_plan
from attbacktrader.strategies.integration_validation import (
    STRATEGY_INTEGRATION_VALIDATION_SCHEMA,
    render_strategy_integration_validation_text_zh,
    validate_run_plan_strategy_integration,
)


def test_strategy_integration_validation_checks_run_plan_methods() -> None:
    run_plan = load_run_plan("examples/run-tushare-expanded-add-on.yaml")

    result = validate_run_plan_strategy_integration(run_plan)
    payload = result.to_dict()
    components = {component["component_role"]: component for component in payload["components"]}

    assert result.status == "ok"
    assert payload["schema"] == STRATEGY_INTEGRATION_VALIDATION_SCHEMA
    assert payload["run_id"] == "tushare-expanded-add-on-2023-2024"
    assert payload["template"] == "trend_template_v1"
    assert payload["required_indicators"] == ["atr14:D", "kdj:D"]
    assert components["entry_method"]["output_contract_status"] == "ok"
    assert components["profit_taking_method"]["output_contract_status"] == "ok"
    assert components["stop_loss_method"]["output_contract_status"] == "ok"
    assert components["add_on_method"]["output_contract_status"] == "ok"
    assert components["sizing_rule"]["output_contract_status"] == "not_trade_intent"
    assert "策略接入校验: 通过" in render_strategy_integration_validation_text_zh(result)


def test_strategy_integration_validation_cli_prints_json(capsys) -> None:
    exit_code = strategy_integration_validation_cli.main(
        ["--config", "examples/run-tushare-expanded-add-on.yaml", "--json"]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["schema"] == STRATEGY_INTEGRATION_VALIDATION_SCHEMA
    assert stdout["status"] == "ok"
    assert [component["component_role"] for component in stdout["components"]] == [
        "entry_method",
        "profit_taking_method",
        "stop_loss_method",
        "add_on_method",
        "sizing_rule",
    ]


def test_strategy_integration_validation_cli_reports_invalid_run_plan(tmp_path: Path, capsys) -> None:
    invalid_config = tmp_path / "invalid.yaml"
    invalid_config.write_text("run:\n  id: missing-required-fields\n", encoding="utf-8")

    exit_code = strategy_integration_validation_cli.main(["--config", str(invalid_config), "--json"])
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert stdout["status"] == "fail"
    assert stdout["issues"][0]["component_role"] == "run_plan"
    assert stdout["issues"][0]["code"] == "load_run_plan_failed"
