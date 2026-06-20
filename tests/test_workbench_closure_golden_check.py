import json
from pathlib import Path

from attbacktrader.cli import workbench_closure_golden_check as workbench_closure_golden_check_cli
from attbacktrader.reports import (
    build_workbench_closure_golden_check,
    build_workbench_closure_snapshot,
    render_workbench_closure_markdown_zh,
    write_workbench_closure_golden_check,
)


def test_workbench_closure_golden_check_validates_closure_doc_against_baseline(tmp_path: Path) -> None:
    baseline_path, closure_doc_path = _write_closure_pair(tmp_path)

    check = build_workbench_closure_golden_check(
        baseline=baseline_path,
        closure_doc=closure_doc_path,
    )
    json_path, markdown_path = write_workbench_closure_golden_check(check, output_dir=tmp_path / "golden-check")

    assert check["schema"] == "attbacktrader.workbench_closure_golden_check.v1"
    assert check["status"] == "ok"
    assert check["failed_count"] == 0
    check_ids = {row["check_id"] for row in check["checks"]}
    assert "accepted_command.att_experiment_decisions" in check_ids
    assert "ai_first_read_order.sequence" in check_ids
    assert json_path.exists()
    assert "Workbench Closure Golden Check" in markdown_path.read_text(encoding="utf-8")


def test_workbench_closure_golden_check_cli_fails_when_doc_omits_command(tmp_path: Path, capsys) -> None:
    baseline_path, closure_doc_path = _write_closure_pair(tmp_path)
    bad_doc_path = tmp_path / "bad-closure.md"
    bad_doc_path.write_text(
        closure_doc_path.read_text(encoding="utf-8").replace("att-experiment-decisions", "att-exp-decisions-missing"),
        encoding="utf-8",
    )

    exit_code = workbench_closure_golden_check_cli.main(
        [
            "--baseline",
            str(baseline_path),
            "--closure-doc",
            str(bad_doc_path),
            "--output-dir",
            str(tmp_path / "bad-check"),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert stdout["schema"] == "attbacktrader.workbench_closure_golden_check.v1"
    assert stdout["status"] == "failed"
    assert stdout["failed_count"] >= 1
    assert (tmp_path / "bad-check" / "workbench_closure_golden_check.json").exists()


def _write_closure_pair(root: Path) -> tuple[Path, Path]:
    snapshot = build_workbench_closure_snapshot(
        sealed_on="2026-06-05",
        run_catalog=_write_run_catalog(root),
        experiment_lifecycle=_write_experiment_lifecycle(root),
        strategy_adaptation_golden_check=_write_golden_check(root),
        sealed_docs=[],
    )
    baseline_path = root / "backtest-workbench-v1-baseline.json"
    closure_doc_path = root / "backtest-workbench-v1-closure.md"
    baseline_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    closure_doc_path.write_text(render_workbench_closure_markdown_zh(snapshot), encoding="utf-8")
    return baseline_path, closure_doc_path


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
            "item_count": 8,
            "chain_count": 2,
            "lineage_counts": [{"key": "strategy_variant", "count": 8}],
            "stage_counts": [{"key": "decision", "count": 2}],
            "status_counts": [{"key": "parked", "count": 1}, {"key": "rejected", "count": 1}],
            "chains": [
                {"chain_id": "strategy_variant:bull", "missing_stages": []},
                {"chain_id": "strategy_variant:range", "missing_stages": []},
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
