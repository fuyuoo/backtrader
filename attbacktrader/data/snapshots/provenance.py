"""Snapshot provenance records for run artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class SnapshotProvenance:
    snapshot_type: str
    action: str
    path: Path
    source_paths: tuple[Path, ...] = ()
    start_date: date | None = None
    end_date: date | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_paths", tuple(Path(path) for path in self.source_paths))
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))
