import json
from pathlib import Path

from attbacktrader.runners import run_entry_factor_validation_batch


def test_entry_factor_validation_batch_runner_resumes_existing_records_and_writes_status(tmp_path: Path) -> None:
    manifest = _manifest((1, 2))
    output_dir = tmp_path / "validation"
    _write_record(output_dir, 1)
    executed_indexes: list[int] = []

    def execute_candidate(candidate: dict, validation_output_dir: Path) -> dict:
        candidate_index = int(candidate["candidate_index"])
        executed_indexes.append(candidate_index)
        return _write_record(output_dir, candidate_index)

    result = run_entry_factor_validation_batch(
        manifest=manifest,
        manifest_path=tmp_path / "manifest.json",
        output_dir=output_dir,
        resume=True,
        execute_candidate=execute_candidate,
    )

    assert executed_indexes == [2]
    assert result.status_counts == {"resumed": 1, "completed": 1}
    assert [status.candidate_index for status in result.statuses] == [1, 2]
    assert [Path(path).name for path in result.record_paths] == [
        "entry_factor_validation_run.json",
        "entry_factor_validation_run.json",
    ]

    status = json.loads((output_dir / "entry_factor_validation_batch_status.json").read_text(encoding="utf-8"))
    assert status["status"] == "complete"
    assert status["status_counts"] == {"resumed": 1, "completed": 1}
    assert status["candidates"][0]["status"] == "resumed"
    assert status["candidates"][1]["status"] == "completed"


def _manifest(candidate_indexes: tuple[int, ...]) -> dict:
    return {
        "schema": "attbacktrader.entry_factor_validation_manifest.v1",
        "base_run_id": "baoma-baseline",
        "candidates": [
            {
                "candidate_index": index,
                "candidate_rank": index,
                "direction": "positive",
                "action": "keep",
                "field_key": f"entry.factor_{index}",
                "value": "x",
                "value_label_zh": "x",
                "sample_count": 100 + index,
                "run_id": f"candidate-run-{index}",
            }
            for index in candidate_indexes
        ],
    }


def _write_record(output_dir: Path, candidate_index: int) -> dict:
    record_dir = output_dir / f"candidate-{candidate_index:03d}"
    record_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "schema": "attbacktrader.entry_factor_validation_run.v1",
        "candidate": {
            "candidate_index": candidate_index,
            "candidate_rank": candidate_index,
            "direction": "positive",
            "action": "keep",
            "field_key": f"entry.factor_{candidate_index}",
            "value": "x",
            "value_label_zh": "x",
            "sample_count": 100 + candidate_index,
            "run_id": f"candidate-run-{candidate_index}",
        },
        "run": {"id": f"candidate-run-{candidate_index}"},
        "run_summary": {
            "metrics": {
                "cumulative_return": 0.01,
                "max_drawdown": 0.01,
                "trade_count": 10,
                "win_rate": 0.55,
                "profit_loss_ratio": 1.2,
            },
            "evidence": {"status": "ok"},
        },
        "artifacts": {
            "validation_json": str(record_dir / "entry_factor_validation_run.json"),
        },
    }
    (record_dir / "entry_factor_validation_run.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record
