"""Fixed stock pool readers."""

from __future__ import annotations

import csv
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd


@dataclass(frozen=True)
class FixedStockPoolMember:
    symbol: str
    name: str
    source_index: str
    freeze_date: date


@dataclass(frozen=True)
class IndexConstituent:
    symbol: str
    source_index: str
    trade_date: date
    weight: float | None = None


@dataclass(frozen=True)
class DynamicStockPoolEntry:
    trade_date: date
    symbol: str
    source_index: str
    source_label: str
    weight: float | None = None


@dataclass(frozen=True)
class DynamicStockPoolMembership:
    symbol: str
    as_of_date: date
    is_member: bool
    active_sources: tuple[str, ...]
    source_snapshot_dates: Mapping[str, date]


@dataclass(frozen=True)
class DynamicStockPool:
    entries: tuple[DynamicStockPoolEntry, ...]

    def __post_init__(self) -> None:
        by_source_date: dict[tuple[str, date], set[str]] = {}
        source_dates: dict[str, set[date]] = {}
        for entry in self.entries:
            by_source_date.setdefault((entry.source_label, entry.trade_date), set()).add(entry.symbol)
            source_dates.setdefault(entry.source_label, set()).add(entry.trade_date)

        object.__setattr__(
            self,
            "_symbols_by_source_date",
            {key: frozenset(symbols) for key, symbols in by_source_date.items()},
        )
        object.__setattr__(
            self,
            "_dates_by_source",
            {source: tuple(sorted(dates)) for source, dates in source_dates.items()},
        )

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted({entry.symbol for entry in self.entries}))

    @property
    def source_labels(self) -> tuple[str, ...]:
        return tuple(sorted({entry.source_label for entry in self.entries}))

    def membership(self, symbol: str, as_of_date: date) -> DynamicStockPoolMembership:
        source_snapshot_dates: dict[str, date] = {}
        active_sources: list[str] = []
        for source_label in self.source_labels:
            snapshot_date = self._latest_snapshot_date(source_label, as_of_date)
            if snapshot_date is None:
                continue
            source_snapshot_dates[source_label] = snapshot_date
            source_symbols = self._symbols_by_source_date[(source_label, snapshot_date)]
            if symbol in source_symbols:
                active_sources.append(source_label)

        return DynamicStockPoolMembership(
            symbol=symbol,
            as_of_date=as_of_date,
            is_member=bool(active_sources),
            active_sources=tuple(active_sources),
            source_snapshot_dates=source_snapshot_dates,
        )

    def as_of_symbols(self, as_of_date: date) -> tuple[str, ...]:
        symbols: set[str] = set()
        for source_label in self.source_labels:
            snapshot_date = self._latest_snapshot_date(source_label, as_of_date)
            if snapshot_date is None:
                continue
            symbols.update(self._symbols_by_source_date[(source_label, snapshot_date)])
        return tuple(sorted(symbols))

    def _latest_snapshot_date(self, source_label: str, as_of_date: date) -> date | None:
        dates = self._dates_by_source.get(source_label, ())
        index = bisect_right(dates, as_of_date)
        if index == 0:
            return None
        return dates[index - 1]


def read_fixed_stock_pool_csv(path: str | Path) -> tuple[FixedStockPoolMember, ...]:
    pool_path = Path(path)
    with pool_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        _validate_headers(pool_path, reader.fieldnames)
        members = tuple(
            _member_from_row(pool_path, row_number=row_number, row=row)
            for row_number, row in enumerate(reader, start=2)
        )

    if not members:
        raise ValueError(f"{pool_path} must contain at least one stock pool member")

    duplicates = _duplicate_symbols(members)
    if duplicates:
        raise ValueError(f"duplicate stock pool symbols in {pool_path}: {duplicates}")

    return members


def write_fixed_stock_pool_csv(path: str | Path, members: Sequence[FixedStockPoolMember]) -> Path:
    pool_path = Path(path)
    pool_path.parent.mkdir(parents=True, exist_ok=True)
    with pool_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=("ts_code", "name", "source_index", "freeze_date"))
        writer.writeheader()
        for member in members:
            writer.writerow(
                {
                    "ts_code": member.symbol,
                    "name": member.name,
                    "source_index": member.source_index,
                    "freeze_date": member.freeze_date.isoformat(),
                }
            )
    return pool_path


def latest_index_constituents(
    constituents: Sequence[IndexConstituent],
) -> tuple[date, tuple[IndexConstituent, ...]]:
    if not constituents:
        raise ValueError("index constituents cannot be empty")
    latest_date = max(constituent.trade_date for constituent in constituents)
    return latest_date, tuple(
        sorted(
            (constituent for constituent in constituents if constituent.trade_date == latest_date),
            key=lambda constituent: constituent.symbol,
        )
    )


def fixed_stock_pool_members_from_index_constituents(
    constituents_by_source_index: Mapping[str, Sequence[IndexConstituent]],
    *,
    stock_names: Mapping[str, str],
    freeze_date: date,
) -> tuple[FixedStockPoolMember, ...]:
    members_by_symbol: dict[str, FixedStockPoolMember] = {}
    for source_index, constituents in constituents_by_source_index.items():
        for constituent in sorted(constituents, key=lambda value: value.symbol):
            existing = members_by_symbol.get(constituent.symbol)
            if existing is None:
                members_by_symbol[constituent.symbol] = FixedStockPoolMember(
                    symbol=constituent.symbol,
                    name=stock_names.get(constituent.symbol, constituent.symbol),
                    source_index=source_index,
                    freeze_date=freeze_date,
                )
                continue

            sources = existing.source_index.split("+")
            if source_index not in sources:
                members_by_symbol[constituent.symbol] = FixedStockPoolMember(
                    symbol=existing.symbol,
                    name=existing.name,
                    source_index="+".join((*sources, source_index)),
                    freeze_date=existing.freeze_date,
                )
    return tuple(members_by_symbol.values())


def dynamic_stock_pool_entries_from_index_constituents(
    constituents_by_source_label: Mapping[str, Sequence[IndexConstituent]],
) -> tuple[DynamicStockPoolEntry, ...]:
    entries: list[DynamicStockPoolEntry] = []
    for source_label, constituents in constituents_by_source_label.items():
        for constituent in constituents:
            entries.append(
                DynamicStockPoolEntry(
                    trade_date=constituent.trade_date,
                    symbol=constituent.symbol,
                    source_index=constituent.source_index,
                    source_label=source_label,
                    weight=constituent.weight,
                )
            )
    return tuple(
        sorted(
            entries,
            key=lambda item: (item.trade_date, item.source_label, item.symbol),
        )
    )


def fixed_stock_pool_members_from_dynamic_entries(
    entries: Sequence[DynamicStockPoolEntry],
    *,
    stock_names: Mapping[str, str],
    freeze_date: date,
) -> tuple[FixedStockPoolMember, ...]:
    sources_by_symbol: dict[str, set[str]] = {}
    for entry in entries:
        sources_by_symbol.setdefault(entry.symbol, set()).add(entry.source_label)

    return tuple(
        FixedStockPoolMember(
            symbol=symbol,
            name=stock_names.get(symbol, symbol),
            source_index="+".join(sorted(sources)),
            freeze_date=freeze_date,
        )
        for symbol, sources in sorted(sources_by_symbol.items())
    )


def write_dynamic_stock_pool_parquet(entries: Sequence[DynamicStockPoolEntry], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        [
            {
                "trade_date": entry.trade_date.isoformat(),
                "symbol": entry.symbol,
                "source_index": entry.source_index,
                "source_label": entry.source_label,
                "weight": entry.weight,
            }
            for entry in entries
        ],
        columns=("trade_date", "symbol", "source_index", "source_label", "weight"),
    )
    frame.to_parquet(output_path, index=False, compression="zstd")
    return output_path


def read_dynamic_stock_pool_parquet(path: str | Path) -> DynamicStockPool:
    pool_path = Path(path)
    if not pool_path.exists():
        raise FileNotFoundError(f"dynamic stock pool file does not exist: {pool_path}")
    frame = pd.read_parquet(pool_path)
    _validate_dynamic_stock_pool_columns(pool_path, frame.columns)
    entries = tuple(
        DynamicStockPoolEntry(
            trade_date=_parse_dynamic_trade_date(pool_path, raw_value=str(row.trade_date)),
            symbol=str(row.symbol),
            source_index=str(row.source_index),
            source_label=str(row.source_label),
            weight=None if pd.isna(row.weight) else float(row.weight),
        )
        for row in frame.itertuples(index=False)
    )
    if not entries:
        raise ValueError(f"{pool_path} must contain at least one dynamic stock pool row")
    return DynamicStockPool(entries)


def _validate_headers(path: Path, fieldnames: list[str] | None) -> None:
    required_headers = {"ts_code", "name", "source_index", "freeze_date"}
    actual_headers = set(fieldnames or ())
    missing_headers = sorted(required_headers - actual_headers)
    if missing_headers:
        raise ValueError(f"{path} is missing stock pool columns: {missing_headers}")


def _validate_dynamic_stock_pool_columns(path: Path, columns) -> None:
    required = {"trade_date", "symbol", "source_index", "source_label", "weight"}
    actual = set(columns)
    missing = sorted(required - actual)
    if missing:
        raise ValueError(f"{path} is missing dynamic stock pool columns: {missing}")


def _member_from_row(path: Path, *, row_number: int, row: dict[str, str | None]) -> FixedStockPoolMember:
    symbol = _required_cell(path, row_number=row_number, row=row, column="ts_code")
    return FixedStockPoolMember(
        symbol=symbol,
        name=_required_cell(path, row_number=row_number, row=row, column="name"),
        source_index=_required_cell(path, row_number=row_number, row=row, column="source_index"),
        freeze_date=_parse_freeze_date(
            path,
            row_number=row_number,
            raw_value=_required_cell(path, row_number=row_number, row=row, column="freeze_date"),
        ),
    )


def _required_cell(path: Path, *, row_number: int, row: dict[str, str | None], column: str) -> str:
    value = (row.get(column) or "").strip()
    if not value:
        raise ValueError(f"{path} row {row_number} has empty {column}")
    return value


def _parse_freeze_date(path: Path, *, row_number: int, raw_value: str) -> date:
    if len(raw_value) == 8 and raw_value.isdigit():
        raw_value = f"{raw_value[:4]}-{raw_value[4:6]}-{raw_value[6:]}"
    try:
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        raise ValueError(f"{path} row {row_number} has invalid freeze_date: {raw_value!r}") from exc


def _parse_dynamic_trade_date(path: Path, *, raw_value: str) -> date:
    value = raw_value.strip()
    if len(value) == 8 and value.isdigit():
        value = f"{value[:4]}-{value[4:6]}-{value[6:]}"
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ValueError(f"{path} has invalid trade_date: {raw_value!r}") from exc


def _duplicate_symbols(members: tuple[FixedStockPoolMember, ...]) -> list[str]:
    symbols = [member.symbol for member in members]
    return sorted({symbol for symbol in symbols if symbols.count(symbol) > 1})
