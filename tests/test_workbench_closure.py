import json
from pathlib import Path

from attbacktrader.cli import workbench_closure_snapshot as workbench_closure_cli
from attbacktrader.reports import (
    build_workbench_closure_snapshot,
    render_workbench_closure_markdown_zh,
    write_workbench_closure_snapshot,
)


def test_workbench_closure_snapshot_records_boundary_contract(tmp_path: Path) -> None:
    run_catalog = _write_run_catalog(tmp_path)
    lifecycle = _write_experiment_lifecycle(tmp_path)
    golden_check = _write_golden_check(tmp_path)
    doc = tmp_path / "sealed-doc.md"
    doc.write_text("# sealed\n", encoding="utf-8")

    snapshot = build_workbench_closure_snapshot(
        sealed_on="2026-06-05",
        run_catalog=run_catalog,
        experiment_lifecycle=lifecycle,
        strategy_adaptation_golden_check=golden_check,
        sealed_docs=[doc],
    )
    markdown = render_workbench_closure_markdown_zh(snapshot)
    baseline_path, doc_path = write_workbench_closure_snapshot(
        snapshot,
        baseline_path=tmp_path / "baseline.json",
        closure_doc_path=tmp_path / "closure.md",
    )

    assert snapshot["schema"] == "attbacktrader.backtest_workbench_v1_baseline.v1"
    assert snapshot["sealed_on"] == "2026-06-05"
    assert snapshot["run_catalog_summary"]["run_count"] == 2
    assert snapshot["experiment_lifecycle_summary"]["chain_count"] == 2
    assert snapshot["experiment_lifecycle_summary"]["decision_gap_count"] == 1
    assert snapshot["strategy_adaptation_golden_summary"]["status"] == "ok"
    commands = {command["command"] for command in snapshot["accepted_commands"]}
    assert "att-run-catalog" in commands
    assert "att-experiment-lifecycle" in commands
    assert "att-experiment-decisions" in commands
    assert "att-workbench-closure-snapshot" in commands
    assert snapshot["ai_first_read_order"][2]["artifact"] == "reports/experiment-decisions/experiment_decisions.json"
    assert any("自动参数调优" in item for item in snapshot["active_non_goals"])
    assert "Backtest Workbench V1 Closure" in markdown
    assert "Run Catalog 可作为第一入口" in markdown
    assert baseline_path.exists()
    assert doc_path.exists()


def test_workbench_closure_snapshot_cli_writes_outputs(tmp_path: Path, capsys) -> None:
    run_catalog = _write_run_catalog(tmp_path)
    lifecycle = _write_experiment_lifecycle(tmp_path)
    golden_check = _write_golden_check(tmp_path)
    baseline_output = tmp_path / "baseline.json"
    doc_output = tmp_path / "closure.md"

    exit_code = workbench_closure_cli.main(
        [
            "--sealed-on",
            "2026-06-05",
            "--run-catalog",
            str(run_catalog),
            "--experiment-lifecycle",
            str(lifecycle),
            "--strategy-adaptation-golden-check",
            str(golden_check),
            "--baseline-output",
            str(baseline_output),
            "--doc-output",
            str(doc_output),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["schema"] == "attbacktrader.backtest_workbench_v1_baseline.v1"
    assert stdout["run_count"] == 2
    assert stdout["chain_count"] == 2
    assert stdout["decision_gap_count"] == 1
    assert stdout["artifacts"]["workbench_closure_baseline_path"] == str(baseline_output)
    assert doc_output.exists()


def _write_run_catalog(root: Path) -> Path:
    path = root / "run_catalog.json"
    _write_json(
        path,
        {
            "schema": "attbacktrader.run_catalog.v1",
            "run_count": 2,
            "group_count": 1,
            "missing_required_artifact_run_count": 0,
            "missing_run_dir_count": 0,
            "role_counts": [{"key": "experiment_run", "count": 2}],
            "evidence_status_counts": [{"key": "ok", "count": 2}],
        },
    )
    return path


def _write_experiment_lifecycle(root: Path) -> Path:
    path = root / "experiment_lifecycle.json"
    _write_json(
        path,
        {
            "schema": "attbacktrader.experiment_lifecycle.v1",
            "item_count": 5,
            "chain_count": 2,
            "lineage_counts": [{"key": "strategy_variant", "count": 5}],
            "stage_counts": [{"key": "comparison", "count": 1}],
            "status_counts": [{"key": "compared", "count": 1}],
            "chains": [
                {
                    "chain_id": "strategy_variant:bull",
                    "missing_stages": ["decision"],
                },
                {
                    "chain_id": "review:candidate.validation",
                    "missing_stages": ["executed_run", "comparison"],
                },
            ],
        },
    )
    return path


def _write_golden_check(root: Path) -> Path:
    path = root / "ai_review_golden_check.json"
    _write_json(
        path,
        {
            "schema": "attbacktrader.ai_review_golden_check.v1",
            "status": "ok",
            "check_count": 72,
            "passed_count": 72,
            "failed_count": 0,
            "golden_for": "Strategy Adaptation V1 sealed AI review",
        },
    )
    return path


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
