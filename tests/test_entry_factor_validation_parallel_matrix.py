import json
from pathlib import Path

from attbacktrader.cli import entry_factor_validation_parallel_matrix as parallel_cli
from attbacktrader.reports import ENTRY_FACTOR_VALIDATION_MATRIX_SCHEMA


def test_parallel_matrix_cli_balances_workers_and_writes_matrix(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path, candidate_indexes=(1, 2, 3))
    output_dir = tmp_path / "matrix"
    fake_popen = _FakePopenFactory()

    args = parallel_cli._parse_args(
        [
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
            "--from-index",
            "1",
            "--to-index",
            "3",
            "--max-workers",
            "2",
            "--poll-seconds",
            "0",
            "--no-persist",
            "--quiet-progress",
        ]
    )
    payload = parallel_cli.run_parallel_matrix(
        args,
        popen_factory=fake_popen,
        sleep=lambda _: None,
        monotonic=fake_popen.monotonic,
    )

    assert fake_popen.launched_indexes == [1, 2, 3]
    assert fake_popen.max_active == 2
    assert payload["schema"] == ENTRY_FACTOR_VALIDATION_MATRIX_SCHEMA
    assert payload["record_count"] == 3
    assert Path(payload["artifacts"]["matrix_json"]).exists()
    assert Path(payload["artifacts"]["matrix_markdown_zh"]).exists()
    assert Path(payload["artifacts"]["parallel_status"]).exists()

    status = json.loads(Path(payload["artifacts"]["parallel_status"]).read_text(encoding="utf-8"))
    assert status["status"] == "complete"
    assert status["status_counts"] == {"completed": 3}


def test_parallel_matrix_cli_resumes_existing_records_without_launching(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path, candidate_indexes=(1, 2))
    output_dir = tmp_path / "matrix"
    _write_record(output_dir, 1)
    _write_record(output_dir, 2)
    fake_popen = _FakePopenFactory()

    args = parallel_cli._parse_args(
        [
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
            "--from-index",
            "1",
            "--to-index",
            "2",
            "--max-workers",
            "2",
            "--poll-seconds",
            "0",
            "--resume",
            "--quiet-progress",
        ]
    )
    payload = parallel_cli.run_parallel_matrix(
        args,
        popen_factory=fake_popen,
        sleep=lambda _: None,
        monotonic=fake_popen.monotonic,
    )

    assert fake_popen.launched_indexes == []
    assert payload["record_count"] == 2
    status = json.loads(Path(payload["artifacts"]["parallel_status"]).read_text(encoding="utf-8"))
    assert status["status_counts"] == {"resumed": 2}


class _FakePopenFactory:
    def __init__(self) -> None:
        self.launched_indexes: list[int] = []
        self.active = 0
        self.max_active = 0
        self._clock = 0.0

    def monotonic(self) -> float:
        self._clock += 1.0
        return self._clock

    def __call__(self, command, *, stdout, stderr, cwd):
        process = _FakeProcess(command, owner=self)
        self.launched_indexes.append(process.candidate_index)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        return process


class _FakeProcess:
    def __init__(self, command, *, owner: _FakePopenFactory) -> None:
        self.command = list(command)
        self.owner = owner
        self.returncode = None
        self.remaining_polls = 1
        self.candidate_index = int(self.command[self.command.index("--candidate-index") + 1])
        self.output_dir = Path(self.command[self.command.index("--output-dir") + 1])

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        if self.remaining_polls > 0:
            self.remaining_polls -= 1
            return None
        _write_record(self.output_dir.parent, self.candidate_index)
        self.returncode = 0
        self.owner.active -= 1
        return self.returncode


def _write_manifest(tmp_path: Path, *, candidate_indexes: tuple[int, ...]) -> Path:
    manifest = {
        "schema": "attbacktrader.entry_factor_validation_manifest.v1",
        "base_run_id": "baoma-baseline",
        "candidates": [
            {
                "candidate_index": index,
                "candidate_rank": index,
                "direction": "positive",
                "action": "keep",
                "field_key": f"entry.factor_{index}",
                "field_label_zh": f"entry.factor_{index}",
                "value": "x",
                "value_label_zh": "x",
                "sample_count": 100 + index,
                "run_id": f"candidate-run-{index}",
            }
            for index in candidate_indexes
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_record(output_dir: Path, candidate_index: int) -> Path:
    record_dir = output_dir / f"candidate-{candidate_index:03d}"
    record_dir.mkdir(parents=True, exist_ok=True)
    path = record_dir / "entry_factor_validation_run.json"
    path.write_text(
        json.dumps(_validation_record(candidate_index), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _validation_record(candidate_index: int) -> dict:
    cumulative_return = 0.01 + candidate_index / 1000
    return {
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
            "factor_quality_score": None,
            "run_id": f"candidate-run-{candidate_index}",
        },
        "run": {"id": f"candidate-run-{candidate_index}"},
        "run_summary": {
            "metrics": {
                "cumulative_return": cumulative_return,
                "max_drawdown": 0.01,
                "trade_count": 10 + candidate_index,
                "win_rate": 0.55,
                "profit_loss_ratio": 1.2,
            },
            "benchmarks": [{"symbol": "000300.SH", "excess_return": cumulative_return - 0.01}],
            "evidence": {"status": "ok"},
        },
        "artifacts": {
            "validation_json": f"candidate-{candidate_index:03d}/entry_factor_validation_run.json",
        },
    }
