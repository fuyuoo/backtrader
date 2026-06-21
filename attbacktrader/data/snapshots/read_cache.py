"""Small explicit cache for immutable snapshot reads."""

from __future__ import annotations

from collections.abc import Callable, Hashable
from pathlib import Path
from typing import Any


class SnapshotReadCache:
    """Cache snapshot read results by explicit, immutable keys."""

    def __init__(self) -> None:
        self._items: dict[Hashable, Any] = {}

    def get_or_read(self, key: Hashable, reader: Callable[[], Any]) -> Any:
        if key not in self._items:
            self._items[key] = reader()
        return self._items[key]

    def clear(self) -> None:
        self._items.clear()


def snapshot_path_cache_key(kind: str, path: str | Path, *parts: Hashable) -> tuple[Hashable, ...]:
    return (kind, str(Path(path).resolve()), *parts)
