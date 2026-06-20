"""Fixed stock pool readers."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping, Sequence


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


def _validate_headers(path: Path, fieldnames: list[str] | None) -> None:
    required_headers = {"ts_code", "name", "source_index", "freeze_date"}
    actual_headers = set(fieldnames or ())
    missing_headers = sorted(required_headers - actual_headers)
    if missing_headers:
        raise ValueError(f"{path} is missing stock pool columns: {missing_headers}")


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


def _duplicate_symbols(members: tuple[FixedStockPoolMember, ...]) -> list[str]:
    symbols = [member.symbol for member in members]
    return sorted({symbol for symbol in symbols if symbols.count(symbol) > 1})
