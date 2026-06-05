import json
from pathlib import Path


def test_strategy_integration_closure_records_real_backtest_handoff() -> None:
    baseline = json.loads(Path("examples/strategy-integration-v1-baseline.json").read_text(encoding="utf-8"))
    doc = Path("docs/strategy-integration-v1-closure.md").read_text(encoding="utf-8")

    assert baseline["schema"] == "attbacktrader.strategy_integration_v1_closure.v1"
    assert baseline["sealed_on"] == "2026-06-05"
    assert baseline["mvp_base_commit"] == "d339bfc"
    assert baseline["accepted_verification"][0]["command"].startswith(
        "python -m attbacktrader.cli.strategy_integration_validation"
    )
    assert baseline["accepted_verification"][2]["expected"] == "336 passed"
    assert {item["item"] for item in baseline["sealed_scope"]} == {
        "strategy_output_contract",
        "strategy_integration_template",
        "strategy_integration_validation",
        "ai_strategy_integration_skill",
    }
    assert any("当前 KDJ/MA/add-on 策略仍然只是 framework fixture" in item for item in baseline["active_non_goals"])
    assert [item["direction_zh"] for item in baseline["next_stage"]] == [
        "真实策略接入",
        "回测配置",
        "真实回测",
    ]
    assert "Strategy Integration V1 Closure" in doc
    assert "Real Backtest Entry Gate" in doc
    assert "不是策略收益评分" in doc
