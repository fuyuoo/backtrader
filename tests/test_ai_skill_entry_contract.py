import json
from pathlib import Path

from attbacktrader.cli import ai_skill_entry_contract as ai_skill_entry_contract_cli
from attbacktrader.reports import (
    build_ai_skill_entry_contract,
    render_ai_skill_entry_contract_markdown_zh,
    write_ai_skill_entry_contract,
)


def test_ai_skill_entry_contract_records_fixed_review_flow(tmp_path: Path) -> None:
    closure = _write_workbench_closure(tmp_path)

    contract = build_ai_skill_entry_contract(
        generated_on="2026-06-05",
        source_workbench_closure=closure,
        skill_doc_path="C:/Users/fff/.agents/skills/attbacktrader-ai-review/SKILL.md",
    )
    markdown = render_ai_skill_entry_contract_markdown_zh(contract)
    json_path, markdown_path = write_ai_skill_entry_contract(
        contract,
        output_path=tmp_path / "contract.json",
        doc_output_path=tmp_path / "contract.md",
    )

    assert contract["schema"] == "attbacktrader.ai_skill_entry_contract.v1"
    assert contract["workbench_summary"]["run_count"] == 24
    assert contract["workbench_summary"]["decision_gap_count"] == 0
    assert [row["artifact"] for row in contract["entry_read_order"][:3]] == [
        "reports/run-catalog/run_catalog.json",
        "reports/experiment-lifecycle/experiment_lifecycle.json",
        "reports/experiment-decisions/experiment_decisions.json",
    ]
    gates = {gate["gate_id"] for gate in contract["preflight_gates"]}
    assert {"catalog_exists", "evidence_ok", "lifecycle_stage"} <= gates
    assert any("不宣称策略可上线" in action for action in contract["forbidden_actions"])
    recommendation_rules = contract["next_recommendation_contract"]["rules"]
    assert any("direction_zh" in rule for rule in recommendation_rules)
    assert any("most_recommended" in rule for rule in recommendation_rules)
    assert "ATTbacktrader AI Skill Entry Contract" in markdown
    assert "First Read Order" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def test_ai_skill_entry_contract_cli_writes_outputs(tmp_path: Path, capsys) -> None:
    closure = _write_workbench_closure(tmp_path)
    output = tmp_path / "contract.json"
    doc_output = tmp_path / "contract.md"

    exit_code = ai_skill_entry_contract_cli.main(
        [
            "--generated-on",
            "2026-06-05",
            "--source-workbench-closure",
            str(closure),
            "--output",
            str(output),
            "--doc-output",
            str(doc_output),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["schema"] == "attbacktrader.ai_skill_entry_contract.v1"
    assert stdout["entry_step_count"] == 7
    assert stdout["mode_count"] == 5
    assert stdout["artifacts"]["ai_skill_entry_contract_json_path"] == str(output)
    assert doc_output.exists()


def _write_workbench_closure(root: Path) -> Path:
    path = root / "backtest-workbench-v1-baseline.json"
    _write_json(
        path,
        {
            "schema": "attbacktrader.backtest_workbench_v1_baseline.v1",
            "sealed_on": "2026-06-05",
            "run_catalog_summary": {"run_count": 24},
            "experiment_lifecycle_summary": {"chain_count": 9, "decision_gap_count": 0},
            "active_non_goals": ["不做自动参数调优或贝叶斯优化。"],
            "next_allowed_slices": [
                {
                    "name_zh": "Workbench Closure Golden Check",
                    "direction_zh": "封板校验",
                    "purpose_zh": "校验 closure 是否漏掉边界。",
                }
            ],
        },
    )
    return path


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
