from datetime import date
from pathlib import Path

import pytest

from attbacktrader.data import DailyBar
from attbacktrader.data.snapshots import read_daily_bars_csv
from attbacktrader.features import (
    build_indicator_snapshots,
    indicator_frame_from_snapshots,
    indicator_snapshot_path,
    join_bars_with_indicators,
    read_indicator_snapshots_parquet,
    write_indicator_snapshots_parquet,
)
from attbacktrader.strategies.templates import TrendTemplateV1


def test_indicator_snapshots_round_trip_and_join_with_bars(tmp_path: Path) -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    snapshots = build_indicator_snapshots(bars)
    path = indicator_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 11),
    )

    written_path = write_indicator_snapshots_parquet(snapshots, path)
    loaded_snapshots = read_indicator_snapshots_parquet(written_path)
    rows = join_bars_with_indicators(bars, loaded_snapshots)

    assert written_path == path
    assert path.parent.name == "qfq"
    assert path.name == "000001_SZ_20240102_20240111.parquet"
    assert loaded_snapshots == snapshots
    assert rows[1].symbol == "000001.SZ"
    assert rows[1].trade_date == date(2024, 1, 3)
    assert rows[1].bar.close == 8.0
    assert rows[1].indicators.kdj_j == pytest.approx(11.1111111111)

    result = TrendTemplateV1().run_single_symbol_rows(rows)
    assert len(result.closed_trades) == 2


def test_join_bars_with_indicators_requires_matching_stock_and_date() -> None:
    bars = [
        DailyBar("000001.SZ", date(2024, 1, 2), 10.0, 10.0, 10.0, 10.0),
    ]
    snapshots = build_indicator_snapshots(
        [DailyBar("000001.SZ", date(2024, 1, 3), 10.0, 10.0, 10.0, 10.0)]
    )

    with pytest.raises(KeyError, match="indicator snapshot is missing"):
        join_bars_with_indicators(bars, snapshots)


def test_indicator_frame_can_be_rebuilt_from_indicator_snapshot_data() -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    snapshots = build_indicator_snapshots(bars)

    frame = indicator_frame_from_snapshots(snapshots)

    assert frame.symbol == "000001.SZ"
    assert frame.kdj_at(date(2024, 1, 3)).j == pytest.approx(11.1111111111)
