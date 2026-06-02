from datetime import date

from attbacktrader.data import DailyBar, TradabilityStatus
from attbacktrader.data.snapshots import (
    daily_bars_snapshot_path,
    read_daily_bars_parquet,
    read_tradability_statuses_parquet,
    tradable_bars_snapshot_path,
    tradability_status_snapshot_path,
    write_daily_bars_parquet,
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
