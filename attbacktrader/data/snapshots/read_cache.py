"""Small explicit cache for immutable snapshot reads."""

from __future__ import annotations

from collections.abc import Callable, Hashable
from pathlib import Path
from threading import RLock
from typing import Any


class SnapshotReadCache:
    """Cache snapshot read results by explicit, immutable keys."""

    def __init__(self) -> None:
        self._items: dict[Hashable, Any] = {}
        self._lock = RLock()

    def get_or_read(self, key: Hashable, reader: Callable[[], Any]) -> Any:
        with self._lock:
            if key in self._items:
                return self._items[key]
        value = reader()
        with self._lock:
            if key not in self._items:
                self._items[key] = value
            return self._items[key]

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


def snapshot_path_cache_key(kind: str, path: str | Path, *parts: Hashable) -> tuple[Hashable, ...]:
    return (kind, str(Path(path).resolve()), *parts)
