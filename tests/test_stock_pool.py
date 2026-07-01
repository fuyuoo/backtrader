from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from attbacktrader.cli import dynamic_stock_pool as dynamic_stock_pool_cli
from attbacktrader.cli import stock_pool as stock_pool_cli
from attbacktrader.data.stock_pool import (
    DynamicStockPool,
    DynamicStockPoolEntry,
    IndexConstituent,
    dynamic_stock_pool_entries_from_index_constituents,
    fixed_stock_pool_members_from_index_constituents,
    fixed_stock_pool_members_from_dynamic_entries,
    latest_index_constituents,
    read_dynamic_stock_pool_parquet,
    read_fixed_stock_pool_csv,
    write_dynamic_stock_pool_parquet,
    write_fixed_stock_pool_csv,
)


def test_read_fixed_stock_pool_csv_parses_members_and_compact_freeze_dates(tmp_path: Path) -> None:
    pool_path = tmp_path / "pool.csv"
    pool_path.write_text(
        "\n".join(
            [
                "ts_code,name,source_index,freeze_date,weight",
                "000001.SZ,Ping An Bank,HS300,20260607,1.0",
                "600036.SH,China Merchants Bank,HS300,2026-06-07,1.0",
            ]
        ),
        encoding="utf-8",
    )

    members = read_fixed_stock_pool_csv(pool_path)

    assert [member.symbol for member in members] == ["000001.SZ", "600036.SH"]
    assert members[0].name == "Ping An Bank"
    assert members[0].source_index == "HS300"
    assert members[0].freeze_date == date(2026, 6, 7)


def test_read_fixed_stock_pool_csv_rejects_duplicate_symbols(tmp_path: Path) -> None:
    pool_path = tmp_path / "pool.csv"
    pool_path.write_text(
        "\n".join(
            [
                "ts_code,name,source_index,freeze_date",
                "000001.SZ,Ping An Bank,HS300,2026-06-07",
                "000001.SZ,Ping An Bank,HS300,2026-06-07",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate stock pool symbols"):
        read_fixed_stock_pool_csv(pool_path)


def test_read_fixed_stock_pool_csv_requires_traceable_columns(tmp_path: Path) -> None:
    pool_path = tmp_path / "pool.csv"
    pool_path.write_text("ts_code\n000001.SZ\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing stock pool columns"):
        read_fixed_stock_pool_csv(pool_path)


def test_latest_index_constituents_selects_latest_trade_date() -> None:
    _, latest = latest_index_constituents(
        (
            IndexConstituent("000001.SZ", "HS300", date(2024, 5, 1), 0.1),
            IndexConstituent("600519.SH", "HS300", date(2024, 6, 1), 1.0),
            IndexConstituent("000001.SZ", "HS300", date(2024, 6, 1), 0.2),
        )
    )

    assert [member.symbol for member in latest] == ["000001.SZ", "600519.SH"]
    assert {member.trade_date for member in latest} == {date(2024, 6, 1)}


def test_fixed_stock_pool_members_merge_duplicate_index_sources() -> None:
    members = fixed_stock_pool_members_from_index_constituents(
        {
            "HS300": (
                IndexConstituent("000001.SZ", "HS300", date(2024, 6, 1), 1.0),
                IndexConstituent("600519.SH", "HS300", date(2024, 6, 1), 1.0),
            ),
            "CSI500": (
                IndexConstituent("000001.SZ", "CSI500", date(2024, 6, 1), 1.0),
                IndexConstituent("000002.SZ", "CSI500", date(2024, 6, 1), 1.0),
            ),
        },
        stock_names={"000001.SZ": "平安银行", "600519.SH": "贵州茅台", "000002.SZ": "万科A"},
        freeze_date=date(2026, 6, 7),
    )

    assert [(member.symbol, member.name, member.source_index) for member in members] == [
        ("000001.SZ", "平安银行", "HS300+CSI500"),
        ("600519.SH", "贵州茅台", "HS300"),
        ("000002.SZ", "万科A", "CSI500"),
    ]


def test_write_fixed_stock_pool_csv_round_trips(tmp_path: Path) -> None:
    pool_path = tmp_path / "pool.csv"
    members = fixed_stock_pool_members_from_index_constituents(
        {"HS300": (IndexConstituent("000001.SZ", "HS300", date(2024, 6, 1), 1.0),)},
        stock_names={"000001.SZ": "平安银行"},
        freeze_date=date(2026, 6, 7),
    )

    write_fixed_stock_pool_csv(pool_path, members)

    loaded = read_fixed_stock_pool_csv(pool_path)
    assert loaded == members


def test_dynamic_stock_pool_membership_uses_latest_snapshot_not_after_as_of_date() -> None:
    entries = dynamic_stock_pool_entries_from_index_constituents(
        {
            "HS300": (
                IndexConstituent("000001.SZ", "399300.SZ", date(2024, 1, 1), 1.0),
                IndexConstituent("000002.SZ", "399300.SZ", date(2024, 1, 3), 1.0),
            ),
            "CSI500": (
                IndexConstituent("000003.SZ", "000905.SH", date(2024, 1, 2), 1.0),
            ),
        }
    )
    pool = DynamicStockPool(entries)

    assert pool.as_of_symbols(date(2023, 12, 31)) == ()
    assert pool.as_of_symbols(date(2024, 1, 1)) == ("000001.SZ",)
    assert pool.as_of_symbols(date(2024, 1, 2)) == ("000001.SZ", "000003.SZ")
    assert pool.as_of_symbols(date(2024, 1, 3)) == ("000002.SZ", "000003.SZ")

    membership = pool.membership("000003.SZ", date(2024, 1, 3))

    assert membership.is_member is True
    assert membership.active_sources == ("CSI500",)
    assert membership.source_snapshot_dates == {
        "CSI500": date(2024, 1, 2),
        "HS300": date(2024, 1, 3),
    }


def test_dynamic_stock_pool_parquet_round_trips(tmp_path: Path) -> None:
    pool_path = tmp_path / "dynamic.parquet"
    entries = (
        DynamicStockPoolEntry(date(2024, 1, 1), "000001.SZ", "399300.SZ", "HS300", 1.0),
        DynamicStockPoolEntry(date(2024, 1, 2), "000002.SZ", "000905.SH", "CSI500", None),
    )

    write_dynamic_stock_pool_parquet(entries, pool_path)
    loaded = read_dynamic_stock_pool_parquet(pool_path)

    assert loaded.entries == entries
    assert loaded.as_of_symbols(date(2024, 1, 2)) == ("000001.SZ", "000002.SZ")


def test_fixed_stock_pool_members_from_dynamic_entries_merges_sources() -> None:
    members = fixed_stock_pool_members_from_dynamic_entries(
        (
            DynamicStockPoolEntry(date(2024, 1, 1), "000001.SZ", "399300.SZ", "HS300", 1.0),
            DynamicStockPoolEntry(date(2024, 1, 2), "000001.SZ", "000905.SH", "CSI500", 1.0),
            DynamicStockPoolEntry(date(2024, 1, 1), "000002.SZ", "399300.SZ", "HS300", 1.0),
        ),
        stock_names={"000001.SZ": "平安银行", "000002.SZ": "万科A"},
        freeze_date=date(2024, 12, 31),
    )

    assert [(member.symbol, member.name, member.source_index) for member in members] == [
        ("000001.SZ", "平安银行", "CSI500+HS300"),
        ("000002.SZ", "万科A", "HS300"),
    ]


def test_stock_pool_cli_generates_fixed_pool_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    output_path = tmp_path / "baoma.csv"

    class FakeProvider:
        def __init__(self, token: str, **kwargs) -> None:
            self.token = token

        def fetch_stock_names(self):
            return {"000001.SZ": "平安银行", "600519.SH": "贵州茅台"}

        def fetch_index_constituents(self, *, index_symbol, start_date, end_date):
            if index_symbol == "000300.SH":
                return (
                    IndexConstituent("000001.SZ", index_symbol, date(2024, 5, 1), 0.1),
                    IndexConstituent("000001.SZ", index_symbol, date(2024, 6, 1), 0.2),
                )
            return (
                IndexConstituent("600519.SH", index_symbol, date(2024, 6, 1), 1.0),
            )

    monkeypatch.setattr(stock_pool_cli, "read_tushare_token", lambda path: "test-token")
    monkeypatch.setattr(stock_pool_cli, "TushareProvider", FakeProvider)

    exit_code = stock_pool_cli.main(
        [
            "--output",
            str(output_path),
            "--freeze-date",
            "2026-06-07",
            "--json",
        ]
    )

    assert exit_code == 0
    loaded = read_fixed_stock_pool_csv(output_path)
    assert [(member.symbol, member.source_index) for member in loaded] == [
        ("000001.SZ", "HS300"),
        ("600519.SH", "CSI500"),
    ]
    assert '"member_count": 2' in capsys.readouterr().out


def test_dynamic_stock_pool_cli_generates_parquet_and_union_csv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    dynamic_path = tmp_path / "dynamic.parquet"
    union_path = tmp_path / "union.csv"
    metadata_path = tmp_path / "dynamic.json"

    class FakeProvider:
        def __init__(self, token: str, **kwargs) -> None:
            self.token = token

        def fetch_stock_names(self):
            return {"000001.SZ": "平安银行", "000002.SZ": "万科A", "000003.SZ": "招商银行"}

        def fetch_index_constituents(self, *, index_symbol, start_date, end_date):
            if index_symbol == "399300.SZ":
                return (
                    IndexConstituent("000001.SZ", index_symbol, date(2024, 1, 1), 1.0),
                    IndexConstituent("000002.SZ", index_symbol, date(2024, 1, 3), 1.0),
                )
            return (
                IndexConstituent("000003.SZ", index_symbol, date(2024, 1, 2), 1.0),
            )

    monkeypatch.setattr(dynamic_stock_pool_cli, "read_tushare_token", lambda path: "test-token")
    monkeypatch.setattr(dynamic_stock_pool_cli, "TushareProvider", FakeProvider)

    exit_code = dynamic_stock_pool_cli.main(
        [
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-01-03",
            "--output-parquet",
            str(dynamic_path),
            "--union-output",
            str(union_path),
            "--metadata-output",
            str(metadata_path),
            "--json",
        ]
    )

    assert exit_code == 0
    pool = read_dynamic_stock_pool_parquet(dynamic_path)
    assert pool.as_of_symbols(date(2024, 1, 2)) == ("000001.SZ", "000003.SZ")
    assert [member.symbol for member in read_fixed_stock_pool_csv(union_path)] == [
        "000001.SZ",
        "000002.SZ",
        "000003.SZ",
    ]
    assert '"union_member_count": 3' in capsys.readouterr().out
    assert metadata_path.read_text(encoding="utf-8")
