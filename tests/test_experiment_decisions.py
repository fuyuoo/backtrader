import json
from pathlib import Path

from attbacktrader.cli import experiment_decisions as experiment_decisions_cli
from attbacktrader.reports import (
    build_experiment_decisions,
    build_experiment_lifecycle,
    render_experiment_decisions_markdown_zh,
    write_experiment_decisions,
)


def test_experiment_decisions_record_explicit_decisions_and_close_lifecycle_gap(tmp_path: Path) -> None:
    lifecycle = _lifecycle()
    decision_input = [
        {
            "chain_id": "strategy_variant:bull_market_let_winners_run",
            "decision": "rejected",
            "decided_on": "2026-06-05",
            "decided_by": "codex",
            "reason_zh": "变体收益和胜率下降，不继续沿这个方向优化。",
            "evidence_refs": [{"artifact": "strategy_variant_validation"}],
            "next_allowed_action_zh": "不继续调这个变体；如需推进，另开新实验方向。",
        }
    ]

    decision_log = build_experiment_decisions(
        lifecycle=lifecycle,
        decisions=decision_input,
        source_lifecycle="reports/experiment-lifecycle/experiment_lifecycle.json",
        source_decisions="examples/experiment-decisions/current.json",
    )
    markdown = render_experiment_decisions_markdown_zh(decision_log)
    json_path, markdown_path = write_experiment_decisions(decision_log, output_dir=tmp_path / "decisions")

    assert decision_log["schema"] == "attbacktrader.experiment_decisions.v1"
    assert decision_log["recorded_decision_count"] == 1
    assert decision_log["invalid_decision_count"] == 0
    assert decision_log["open_decision_gap_count"] == 0
    record = decision_log["records"][0]
    assert record["status"] == "recorded"
    assert record["decision"] == "rejected"
    assert record["chain_snapshot"]["current_stage"] == "comparison"
    assert "实验 Decision Records" in markdown
    assert json_path.exists()
    assert markdown_path.exists()

    decision_path = tmp_path / "decisions" / "experiment_decisions.json"
    lifecycle_with_decision = build_experiment_lifecycle(decisions=[decision_path])
    chains = {chain["chain_id"]: chain for chain in lifecycle_with_decision["chains"]}
    assert chains["strategy_variant:bull_market_let_winners_run"]["status"] == "decided"
    assert "decision" not in chains["strategy_variant:bull_market_let_winners_run"]["missing_stages"]


def test_experiment_decisions_cli_writes_outputs(tmp_path: Path, capsys) -> None:
    lifecycle_path = tmp_path / "experiment_lifecycle.json"
    decision_file = tmp_path / "decisions.json"
    output_dir = tmp_path / "out"
    _write_json(lifecycle_path, _lifecycle())
    _write_json(
        decision_file,
        {
            "schema": "attbacktrader.experiment_decision_inputs.v1",
            "decisions": [
                {
                    "chain_id": "strategy_variant:bull_market_let_winners_run",
                    "decision": "parked",
                    "decided_on": "2026-06-05",
                    "decided_by": "codex",
                    "reason_zh": "当前不是优先方向。",
                    "evidence_refs": [{"artifact": "experiment_lifecycle"}],
                    "next_allowed_action_zh": "保留证据，不继续分析。",
                }
            ],
        },
    )

    exit_code = experiment_decisions_cli.main(
        [
            "--lifecycle",
            str(lifecycle_path),
            "--decision-file",
            str(decision_file),
            "--output-dir",
            str(output_dir),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["schema"] == "attbacktrader.experiment_decisions.v1"
    assert stdout["recorded_decision_count"] == 1
    assert stdout["open_decision_gap_count"] == 0
    assert (output_dir / "experiment_decisions.zh.md").exists()


def _lifecycle() -> dict:
    return {
        "schema": "attbacktrader.experiment_lifecycle.v1",
        "chains": [
            {
                "chain_id": "strategy_variant:bull_market_let_winners_run",
                "lineage_type": "strategy_variant",
                "title_zh": "牛市：放宽过早止盈验证",
                "current_stage": "comparison",
                "status": "compared",
                "stages_present": ["draft", "generated_run", "executed_run", "comparison"],
                "missing_stages": ["decision"],
                "run_ids": ["variant-run"],
                "executed_run_ids": ["variant-run"],
                "market_type_id": "bull_market",
            }
        ],
    }


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
