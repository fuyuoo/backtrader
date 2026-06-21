"""Batch orchestration for entry-factor validation candidates."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ENTRY_FACTOR_VALIDATION_BATCH_STATUS_SCHEMA = "attbacktrader.entry_factor_validation_batch_status.v1"


@dataclass(frozen=True)
class EntryFactorValidationCandidateStatus:
    candidate_index: int
    run_id: str | None
    field_key: str | None
    value: Any
    action: str | None
    status: str
    validation_json: Path


@dataclass(frozen=True)
class EntryFactorValidationBatchResult:
    records: tuple[dict[str, Any], ...]
    record_paths: tuple[Path, ...]
    statuses: tuple[EntryFactorValidationCandidateStatus, ...]
    status_path: Path

    @property
    def status_counts(self) -> dict[str, int]:
        return dict(Counter(status.status for status in self.statuses))


def run_entry_factor_validation_batch(
    *,
    manifest: Mapping[str, Any],
    manifest_path: str | Path,
    output_dir: str | Path,
    execute_candidate: Callable[[dict[str, Any], Path], Mapping[str, Any]],
    from_index: int | None = None,
    to_index: int | None = None,
    max_candidates: int | None = None,
    resume: bool = False,
) -> EntryFactorValidationBatchResult:
    """Run selected manifest candidates and write a compact batch status file."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    status_path = output_path / "entry_factor_validation_batch_status.json"
    selected = selected_entry_factor_validation_candidates(
        manifest,
        from_index=from_index,
        to_index=to_index,
        max_candidates=max_candidates,
    )
    selected_indexes = [int(candidate.get("candidate_index")) for candidate in selected]
    records: list[dict[str, Any]] = []
    record_paths: list[Path] = []
    statuses: list[EntryFactorValidationCandidateStatus] = []

    _write_batch_status(
        status_path,
        _status_payload(
            manifest_path=manifest_path,
            output_dir=output_path,
            selected_indexes=selected_indexes,
            statuses=statuses,
        ),
    )

    for candidate in selected:
        candidate_index = int(candidate.get("candidate_index"))
        validation_output_dir = output_path / f"candidate-{candidate_index:03d}"
        validation_json_path = validation_output_dir / "entry_factor_validation_run.json"
        if resume and validation_json_path.exists():
            record = _load_json_mapping(validation_json_path)
            status = "resumed"
        else:
            record = dict(execute_candidate(dict(candidate), validation_output_dir))
            status = "completed"
        records.append(record)
        record_paths.append(validation_json_path)
        statuses.append(
            _candidate_status(
                candidate,
                status=status,
                validation_json_path=validation_json_path,
            )
        )
        _write_batch_status(
            status_path,
            _status_payload(
                manifest_path=manifest_path,
                output_dir=output_path,
                selected_indexes=selected_indexes,
                statuses=statuses,
            ),
        )

    result = EntryFactorValidationBatchResult(
        records=tuple(records),
        record_paths=tuple(record_paths),
        statuses=tuple(statuses),
        status_path=status_path,
    )
    _write_batch_status(
        status_path,
        _status_payload(
            manifest_path=manifest_path,
            output_dir=output_path,
            selected_indexes=selected_indexes,
            statuses=statuses,
            finished_at=_now_iso(),
        ),
    )
    return result


def selected_entry_factor_validation_candidates(
    manifest: Mapping[str, Any],
    *,
    from_index: int | None,
    to_index: int | None,
    max_candidates: int | None,
) -> list[dict[str, Any]]:
    candidates = sorted(
        (dict(_as_mapping(candidate)) for candidate in _as_sequence(manifest.get("candidates"))),
        key=lambda candidate: int(candidate.get("candidate_index") or 0),
    )
    selected: list[dict[str, Any]] = []
    for candidate in candidates:
        index = int(candidate.get("candidate_index") or 0)
        if from_index is not None and index < from_index:
            continue
        if to_index is not None and index > to_index:
            continue
        selected.append(candidate)
        if max_candidates is not None and len(selected) >= max_candidates:
            break
    if not selected:
        raise ValueError("no manifest candidates selected")
    return selected


def _candidate_status(
    candidate: Mapping[str, Any],
    *,
    status: str,
    validation_json_path: Path,
) -> EntryFactorValidationCandidateStatus:
    return EntryFactorValidationCandidateStatus(
        candidate_index=int(candidate.get("candidate_index")),
        run_id=str(candidate.get("run_id")) if candidate.get("run_id") is not None else None,
        field_key=str(candidate.get("field_key")) if candidate.get("field_key") is not None else None,
        value=candidate.get("value"),
        action=str(candidate.get("action")) if candidate.get("action") is not None else None,
        status=status,
        validation_json=validation_json_path,
    )


def _status_payload(
    *,
    manifest_path: str | Path,
    output_dir: Path,
    selected_indexes: Sequence[int],
    statuses: Sequence[EntryFactorValidationCandidateStatus],
    finished_at: str | None = None,
) -> dict[str, Any]:
    status_counts = dict(Counter(status.status for status in statuses))
    payload: dict[str, Any] = {
        "schema": ENTRY_FACTOR_VALIDATION_BATCH_STATUS_SCHEMA,
        "manifest": str(manifest_path),
        "output_dir": str(output_dir),
        "selected_indexes": list(selected_indexes),
        "selected_count": len(selected_indexes),
        "status": "complete" if finished_at else "running",
        "status_counts": status_counts,
        "candidates": [
            {
                "candidate_index": status.candidate_index,
                "run_id": status.run_id,
                "field_key": status.field_key,
                "value": status.value,
                "action": status.action,
                "status": status.status,
                "validation_json": str(status.validation_json),
            }
            for status in statuses
        ],
        "updated_at": _now_iso(),
    }
    if finished_at is not None:
        payload["finished_at"] = finished_at
    return payload


def _write_batch_status(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _load_json_mapping(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{target} must contain a JSON object")
    return payload


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: object) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()
