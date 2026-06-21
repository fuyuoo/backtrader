"""Parity checks for entry-factor validation matrix outputs."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EntryFactorValidationParityMismatch:
    """One observable difference between two validation matrix outputs."""

    candidate_index: int | None
    path: str
    reference: Any
    candidate: Any


@dataclass(frozen=True)
class EntryFactorValidationParityReport:
    """Summary of old-path versus new-path validation matrix parity."""

    equivalent: bool
    mismatches: tuple[EntryFactorValidationParityMismatch, ...]


_CORE_METRICS = ("cumulative_return", "max_drawdown", "trade_count", "win_rate", "profit_loss_ratio")
_ROW_FIELDS = (
    "status",
    "direction",
    "action",
    "field_key",
    "value",
    "value_label_zh",
    "sample_count",
    "factor_quality_score",
    "validation_score",
)
_RANKING_KEYS = ("by_validation_score", "supports_candidate", "mixed", "rejects_candidate", "invalid")


def compare_entry_factor_validation_matrix_parity(
    reference_matrix: Mapping[str, Any] | str | Path,
    candidate_matrix: Mapping[str, Any] | str | Path,
    *,
    abs_tol: float = 1e-12,
) -> EntryFactorValidationParityReport:
    """Compare two entry-factor validation matrices by stable external behavior."""

    reference = _load_matrix(reference_matrix)
    candidate = _load_matrix(candidate_matrix)
    mismatches: list[EntryFactorValidationParityMismatch] = []

    _compare_value(mismatches, None, "schema", reference.get("schema"), candidate.get("schema"), abs_tol=abs_tol)
    _compare_value(
        mismatches,
        None,
        "record_count",
        reference.get("record_count"),
        candidate.get("record_count"),
        abs_tol=abs_tol,
    )
    _compare_value(
        mismatches,
        None,
        "status_counts",
        _as_mapping(reference.get("status_counts")),
        _as_mapping(candidate.get("status_counts")),
        abs_tol=abs_tol,
    )

    _compare_baseline(mismatches, reference, candidate, abs_tol=abs_tol)
    _compare_rows(mismatches, reference, candidate, abs_tol=abs_tol)
    _compare_rankings(mismatches, reference, candidate, abs_tol=abs_tol)

    return EntryFactorValidationParityReport(
        equivalent=not mismatches,
        mismatches=tuple(mismatches),
    )


def _compare_baseline(
    mismatches: list[EntryFactorValidationParityMismatch],
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    abs_tol: float,
) -> None:
    reference_baseline = _as_mapping(reference.get("baseline"))
    candidate_baseline = _as_mapping(candidate.get("baseline"))
    _compare_value(
        mismatches,
        None,
        "baseline.run_id",
        reference_baseline.get("run_id"),
        candidate_baseline.get("run_id"),
        abs_tol=abs_tol,
    )
    reference_metrics = _as_mapping(reference_baseline.get("metrics"))
    candidate_metrics = _as_mapping(candidate_baseline.get("metrics"))
    for key in _CORE_METRICS:
        _compare_value(
            mismatches,
            None,
            f"baseline.metrics.{key}",
            reference_metrics.get(key),
            candidate_metrics.get(key),
            abs_tol=abs_tol,
        )


def _compare_rows(
    mismatches: list[EntryFactorValidationParityMismatch],
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    abs_tol: float,
) -> None:
    reference_rows = _rows_by_candidate_index(reference)
    candidate_rows = _rows_by_candidate_index(candidate)
    _compare_value(
        mismatches,
        None,
        "rows.candidate_indexes",
        tuple(reference_rows),
        tuple(candidate_rows),
        abs_tol=abs_tol,
    )

    for candidate_index in sorted(reference_rows.keys() & candidate_rows.keys()):
        reference_row = reference_rows[candidate_index]
        candidate_row = candidate_rows[candidate_index]
        for field in _ROW_FIELDS:
            _compare_value(
                mismatches,
                candidate_index,
                f"rows[{candidate_index}].{field}",
                reference_row.get(field),
                candidate_row.get(field),
                abs_tol=abs_tol,
            )
        _compare_nested_metrics(
            mismatches,
            candidate_index,
            "metrics",
            _as_mapping(reference_row.get("metrics")),
            _as_mapping(candidate_row.get("metrics")),
            abs_tol=abs_tol,
        )
        _compare_nested_metrics(
            mismatches,
            candidate_index,
            "deltas",
            _as_mapping(reference_row.get("deltas")),
            _as_mapping(candidate_row.get("deltas")),
            abs_tol=abs_tol,
        )
        _compare_value(
            mismatches,
            candidate_index,
            f"rows[{candidate_index}].evidence",
            _as_mapping(reference_row.get("evidence")),
            _as_mapping(candidate_row.get("evidence")),
            abs_tol=abs_tol,
        )
        _compare_value(
            mismatches,
            candidate_index,
            f"rows[{candidate_index}].benchmark_excess.average",
            _as_mapping(reference_row.get("benchmark_excess")).get("average"),
            _as_mapping(candidate_row.get("benchmark_excess")).get("average"),
            abs_tol=abs_tol,
        )


def _compare_nested_metrics(
    mismatches: list[EntryFactorValidationParityMismatch],
    candidate_index: int,
    prefix: str,
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    abs_tol: float,
) -> None:
    for key in _CORE_METRICS:
        _compare_value(
            mismatches,
            candidate_index,
            f"rows[{candidate_index}].{prefix}.{key}",
            reference.get(key),
            candidate.get(key),
            abs_tol=abs_tol,
        )


def _compare_rankings(
    mismatches: list[EntryFactorValidationParityMismatch],
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    abs_tol: float,
) -> None:
    reference_rankings = _as_mapping(reference.get("rankings"))
    candidate_rankings = _as_mapping(candidate.get("rankings"))
    for key in _RANKING_KEYS:
        _compare_value(
            mismatches,
            None,
            f"rankings.{key}.candidate_indexes",
            _candidate_index_sequence(reference_rankings.get(key)),
            _candidate_index_sequence(candidate_rankings.get(key)),
            abs_tol=abs_tol,
        )


def _compare_value(
    mismatches: list[EntryFactorValidationParityMismatch],
    candidate_index: int | None,
    path: str,
    reference: Any,
    candidate: Any,
    *,
    abs_tol: float,
) -> None:
    if _equivalent_value(reference, candidate, abs_tol=abs_tol):
        return
    mismatches.append(
        EntryFactorValidationParityMismatch(
            candidate_index=candidate_index,
            path=path,
            reference=reference,
            candidate=candidate,
        )
    )


def _equivalent_value(reference: Any, candidate: Any, *, abs_tol: float) -> bool:
    if _is_number(reference) and _is_number(candidate):
        return math.isclose(float(reference), float(candidate), rel_tol=0.0, abs_tol=abs_tol)
    return reference == candidate


def _rows_by_candidate_index(matrix: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    rows: dict[int, Mapping[str, Any]] = {}
    for row in _as_sequence(matrix.get("rows")):
        item = _as_mapping(row)
        candidate_index = item.get("candidate_index")
        if candidate_index is None:
            continue
        rows[int(candidate_index)] = item
    return dict(sorted(rows.items()))


def _candidate_index_sequence(value: Any) -> tuple[int, ...]:
    result: list[int] = []
    for row in _as_sequence(value):
        item = _as_mapping(row)
        candidate_index = item.get("candidate_index")
        if candidate_index is not None:
            result.append(int(candidate_index))
    return tuple(result)


def _load_matrix(value: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    path = Path(value)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()
