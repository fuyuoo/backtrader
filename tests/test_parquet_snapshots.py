from datetime import date

from attbacktrader.data import DailyBar, TradabilityStatus
from attbacktrader.data.snapshots import (
    SnapshotReadCache,
    daily_bars_snapshot_path,
    discover_tradable_bars_snapshot_paths,
    merge_daily_bars,
    read_daily_bars_parquet,
    read_tradability_statuses_parquet,
    tradable_bars_snapshot_path,
    tradability_status_snapshot_path,
    write_daily_bars_parquet,
    write_merged_daily_bars_parquet,
    write_tradability_statuses_parquet,
)


def test_daily_bars_parquet_round_trip(tmp_path) -> None:
    bars = (
        DailyBar(
            symbol="000001.SZ",
            trade_date=date(2024, 1, 2),
            open=9.0,
            high=9.3,
            low=8.9,
            close=9.2,
            volume=900.0,
        ),
        DailyBar(
            symbol="000001.SZ",
            trade_date=date(2024, 1, 3),
            open=9.2,
            high=9.5,
            low=9.1,
            close=9.4,
            volume=1000.0,
        ),
    )
    path = daily_bars_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 3),
    )

    written_path = write_daily_bars_parquet(bars, path)

    assert written_path == path
    assert path.parent.name == "qfq"
    assert path.name == "000001_SZ_20240102_20240103.parquet"
    assert read_daily_bars_parquet(path) == bars


def test_daily_bars_parquet_read_cache_reuses_by_path_and_isolates_new_cache(tmp_path) -> None:
    path = daily_bars_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 2),
    )
    original = (DailyBar("000001.SZ", date(2024, 1, 2), 9.0, 9.5, 8.8, 9.2),)
    updated = (DailyBar("000001.SZ", date(2024, 1, 2), 10.0, 10.5, 9.8, 10.2),)
    write_daily_bars_parquet(original, path)
    cache = SnapshotReadCache()

    first = read_daily_bars_parquet(path, cache=cache)
    write_daily_bars_parquet(updated, path)
    second = read_daily_bars_parquet(path, cache=cache)
    fresh = read_daily_bars_parquet(path, cache=SnapshotReadCache())

    assert first is second
    assert first == original
    assert fresh == updated


def test_tradable_index_bars_path_is_asset_neutral(tmp_path) -> None:
    path = tradable_bars_snapshot_path(
        tmp_path,
        symbol="000001.SH",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 3),
        asset_type="index",
        adjustment="none",
    )

    assert path.parts[-4:-1] == ("tradable_bars", "index", "none")
    assert path.name == "000001_SH_20240102_20240103.parquet"


def test_discover_tradable_bars_snapshot_paths_finds_overlapping_ranges(tmp_path) -> None:
    matching_path = daily_bars_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
    )
    outside_path = daily_bars_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=date(2024, 3, 1),
        end_date=date(2024, 3, 31),
    )
    other_symbol_path = daily_bars_snapshot_path(
        tmp_path,
        symbol="000002.SZ",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
    )
    matching_path.parent.mkdir(parents=True, exist_ok=True)
    matching_path.write_text("", encoding="utf-8")
    outside_path.write_text("", encoding="utf-8")
    other_symbol_path.write_text("", encoding="utf-8")

    candidates = discover_tradable_bars_snapshot_paths(
        tmp_path,
        symbol="000001.SZ",
        start_date=date(2024, 1, 15),
        end_date=date(2024, 2, 15),
    )

    assert tuple(candidate.path for candidate in candidates) == (matching_path,)
    assert candidates[0].start_date == date(2024, 1, 1)
    assert candidates[0].end_date == date(2024, 1, 31)


def test_merge_daily_bars_overwrites_and_filters(tmp_path) -> None:
    existing_bars = (
        DailyBar("000001.SZ", date(2024, 1, 1), 10.0, 11.0, 9.0, 10.5),
        DailyBar("000001.SZ", date(2024, 1, 2), 11.0, 12.0, 10.0, 11.5),
        DailyBar("000001.SZ", date(2024, 1, 3), 12.0, 13.0, 11.0, 12.9),
    )
    new_bars = (
        DailyBar("000001.SZ", date(2024, 1, 3), 12.0, 13.0, 11.0, 12.5),
        DailyBar("000001.SZ", date(2024, 1, 4), 13.0, 14.0, 12.0, 13.5),
    )
    path = daily_bars_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 4),
    )

    merged = merge_daily_bars(
        existing_bars,
        new_bars,
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 4),
    )
    write_merged_daily_bars_parquet(
        existing_bars,
        new_bars,
        path,
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 4),
    )

    assert [(bar.trade_date, bar.close) for bar in merged] == [
        (date(2024, 1, 2), 11.5),
        (date(2024, 1, 3), 12.5),
        (date(2024, 1, 4), 13.5),
    ]
    assert read_daily_bars_parquet(path) == merged


def test_tradability_status_parquet_round_trip(tmp_path) -> None:
    statuses = (
        TradabilityStatus(
            symbol="000001.SZ",
            trade_date=date(2024, 1, 2),
            is_suspended=False,
            is_limit_up=True,
            is_limit_down=False,
            close=11.0,
            up_limit=11.0,
            down_limit=9.0,
        ),
        TradabilityStatus(
            symbol="000001.SZ",
            trade_date=date(2024, 1, 3),
            is_suspended=True,
        ),
    )
    path = tradability_status_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 3),
    )

    written_path = write_tradability_statuses_parquet(statuses, path)

    assert written_path == path
    assert path.parts[-3:-1] == ("tradability", "stock")
    assert path.name == "000001_SZ_20240102_20240103.parquet"
    assert read_tradability_statuses_parquet(path) == statuses
