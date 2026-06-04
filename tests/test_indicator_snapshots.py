from datetime import date, timedelta
from pathlib import Path

import pytest

from attbacktrader.data import DailyBar
from attbacktrader.data.snapshots import read_daily_bars_csv
from attbacktrader.features import (
    IndicatorSnapshotMetadata,
    IndicatorRequirement,
    IndicatorSnapshot,
    build_indicator_snapshots_from_state,
    build_indicator_snapshots,
    build_indicator_snapshots_for_requirements,
    build_indicator_update_plans,
    discover_indicator_snapshot_paths,
    indicator_frame_from_snapshots,
    indicator_spec,
    indicator_snapshot_metadata_path,
    indicator_snapshot_path,
    indicator_states_from_bars,
    join_bars_with_indicators,
    merge_indicator_snapshots,
    read_indicator_snapshot_metadata,
    read_indicator_snapshots_parquet,
    write_indicator_snapshot_metadata,
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


def test_macd_indicator_snapshots_round_trip(tmp_path: Path) -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    snapshots = build_indicator_snapshots(bars, indicator_names=("macd",))
    path = indicator_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 11),
        indicator_names=("macd",),
    )

    written_path = write_indicator_snapshots_parquet(snapshots, path)
    loaded_snapshots = read_indicator_snapshots_parquet(written_path)
    frame = indicator_frame_from_snapshots(loaded_snapshots)

    assert path.parts[-3:-1] == ("macd", "qfq")
    assert loaded_snapshots == snapshots
    assert loaded_snapshots[0].has_indicator("macd")
    assert not loaded_snapshots[0].has_indicator("kdj")
    assert frame.macd_at(date(2024, 1, 3)).line != 0.0
    with pytest.raises(KeyError, match="KDJ is missing"):
        frame.kdj_at(date(2024, 1, 3))


def test_weekly_indicator_snapshots_align_to_latest_completed_bar(tmp_path: Path) -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    requirement = IndicatorRequirement("macd", "W")
    snapshots = build_indicator_snapshots_for_requirements(
        bars,
        indicator_requirements=(requirement,),
    )
    path = indicator_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 11),
        indicator_names=("macd",),
        timeframe="W",
    )

    frame = indicator_frame_from_snapshots(snapshots)
    rows = join_bars_with_indicators(
        bars,
        snapshots,
        indicator_requirements=(requirement,),
    )

    assert path.parts[-4:-1] == ("macd", "W", "qfq")
    assert {snapshot.timeframe for snapshot in snapshots} == {"W"}
    assert rows[0].trade_date == date(2024, 1, 2)
    with pytest.raises(KeyError, match="indicator is missing"):
        rows[0].indicators.macd_at("W")
    assert rows[3].trade_date == date(2024, 1, 5)
    assert rows[4].trade_date == date(2024, 1, 8)
    assert rows[4].indicators.macd_at("W") == frame.macd_at(date(2024, 1, 5), timeframe="W")
    assert rows[-1].indicators.macd_at("W") == frame.macd_at(date(2024, 1, 11), timeframe="W")


def test_monthly_indicator_snapshots_align_to_latest_completed_bar(tmp_path: Path) -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    requirement = IndicatorRequirement("macd", "M")
    snapshots = build_indicator_snapshots_for_requirements(
        bars,
        indicator_requirements=(requirement,),
    )
    path = indicator_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 11),
        indicator_names=("macd",),
        timeframe="M",
    )

    frame = indicator_frame_from_snapshots(snapshots)
    rows = join_bars_with_indicators(
        bars,
        snapshots,
        indicator_requirements=(requirement,),
    )

    assert path.parts[-4:-1] == ("macd", "M", "qfq")
    assert {snapshot.timeframe for snapshot in snapshots} == {"M"}
    assert rows[0].trade_date == date(2024, 1, 2)
    with pytest.raises(KeyError, match="indicator is missing"):
        rows[0].indicators.macd_at("M")
    assert rows[-1].trade_date == date(2024, 1, 11)
    assert rows[-1].indicators.macd_at("M") == frame.macd_at(date(2024, 1, 11), timeframe="M")


def test_warmup_indicator_snapshot_values_remain_unavailable() -> None:
    bars = read_daily_bars_csv(Path("tests/fixtures/single_stock_kdj.csv"))
    requirement = IndicatorRequirement("ma60", "D")

    snapshots = build_indicator_snapshots_for_requirements(
        bars,
        indicator_requirements=(requirement,),
    )
    rows = join_bars_with_indicators(
        bars,
        snapshots,
        indicator_requirements=(requirement,),
    )

    assert len(snapshots) == len(bars)
    assert all(snapshot.ma60 is None for snapshot in snapshots)
    assert len(rows) == len(bars)
    with pytest.raises(KeyError, match="MA is missing"):
        rows[-1].indicators.ma_at(60)


def test_ma25_indicator_snapshot_is_available_after_warmup() -> None:
    bars = _stateful_bars("000001.SZ", count=30)
    requirement = IndicatorRequirement("ma25", "D")

    snapshots = build_indicator_snapshots_for_requirements(
        bars,
        indicator_requirements=(requirement,),
    )
    rows = join_bars_with_indicators(
        bars,
        snapshots,
        indicator_requirements=(requirement,),
    )
    frame = indicator_frame_from_snapshots(snapshots)

    assert all(snapshot.ma25 is None for snapshot in snapshots[:24])
    assert snapshots[24].ma25 is not None
    assert rows[-1].indicators.ma_at(25).value == pytest.approx(frame.ma_at(bars[-1].trade_date, period=25).value)


def test_indicator_update_plan_uses_longest_required_window() -> None:
    plans = build_indicator_update_plans(
        symbol="000001.SZ",
        indicator_requirements=(
            IndicatorRequirement("ma20", "D"),
            IndicatorRequirement("ma60", "D"),
            IndicatorRequirement("rsi14", "D"),
        ),
    )

    assert len(plans) == 1
    plan = plans[0]
    assert plan.indicator_names == ("ma20", "ma60", "rsi14")
    assert plan.warmup_bars == 60
    assert plan.recompute_lookback_bars == 59
    assert plan.requires_state is True
    assert indicator_spec("ma60").warmup_bars == 60


def test_merge_indicator_snapshots_overwrites_tail_and_appends() -> None:
    existing_snapshots = (
        IndicatorSnapshot("000001.SZ", date(2024, 1, 1), ma20=1.0),
        IndicatorSnapshot("000001.SZ", date(2024, 1, 2), ma20=2.0),
        IndicatorSnapshot("000001.SZ", date(2024, 1, 3), ma20=999.0),
    )
    new_snapshots = (
        IndicatorSnapshot("000001.SZ", date(2024, 1, 2), ma20=222.0),
        IndicatorSnapshot("000001.SZ", date(2024, 1, 3), ma20=3.0),
        IndicatorSnapshot("000001.SZ", date(2024, 1, 4), ma20=4.0),
    )

    merged = merge_indicator_snapshots(
        existing_snapshots,
        new_snapshots,
        overwrite_from=date(2024, 1, 3),
    )

    assert [(snapshot.trade_date, snapshot.ma20) for snapshot in merged] == [
        (date(2024, 1, 1), 1.0),
        (date(2024, 1, 2), 2.0),
        (date(2024, 1, 3), 3.0),
        (date(2024, 1, 4), 4.0),
    ]


def test_indicator_snapshot_metadata_round_trip(tmp_path: Path) -> None:
    path = indicator_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        indicator_names=("macd",),
    )
    metadata = IndicatorSnapshotMetadata(
        symbol="000001.SZ",
        timeframe="D",
        indicator_names=("macd",),
        version_fingerprint="macd:v1:{}",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        warmup_bars=34,
        recompute_lookback_bars=33,
        requires_state=True,
        states={"macd": {"fast_ema": 10.0, "slow_ema": 9.0, "signal_ema": 1.0}},
    )

    written_path = write_indicator_snapshot_metadata(path, metadata)

    assert written_path == indicator_snapshot_metadata_path(path)
    assert read_indicator_snapshot_metadata(path) == metadata


def test_discover_indicator_snapshot_paths_finds_compatible_ranges(tmp_path: Path) -> None:
    matching_path = indicator_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        indicator_names=("macd", "ma20"),
    )
    outside_path = indicator_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=date(2024, 3, 1),
        end_date=date(2024, 3, 31),
        indicator_names=("macd", "ma20"),
    )
    wrong_set_path = indicator_snapshot_path(
        tmp_path,
        symbol="000001.SZ",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        indicator_names=("macd",),
    )
    matching_path.parent.mkdir(parents=True, exist_ok=True)
    matching_path.write_text("", encoding="utf-8")
    outside_path.write_text("", encoding="utf-8")
    wrong_set_path.parent.mkdir(parents=True, exist_ok=True)
    wrong_set_path.write_text("", encoding="utf-8")

    candidates = discover_indicator_snapshot_paths(
        tmp_path,
        symbol="000001.SZ",
        start_date=date(2024, 1, 15),
        end_date=date(2024, 2, 15),
        indicator_names=("ma20", "macd"),
    )

    assert tuple(candidate.path for candidate in candidates) == (matching_path,)
    assert candidates[0].indicator_names == ("ma20", "macd")
    assert candidates[0].start_date == date(2024, 1, 1)
    assert candidates[0].end_date == date(2024, 1, 31)


def test_stateful_indicator_append_matches_full_batch() -> None:
    bars = _stateful_bars("000001.SZ", count=40)
    indicator_names = ("kdj", "macd", "rsi14", "atr14")
    initial_bars = bars[:25]
    append_bars = bars[25:]
    initial_snapshots = build_indicator_snapshots(initial_bars, indicator_names=indicator_names)
    append_snapshots, states = build_indicator_snapshots_from_state(
        append_bars,
        indicator_names=indicator_names,
        states=indicator_states_from_bars(indicator_names, initial_bars),
    )
    full_snapshots = build_indicator_snapshots(bars, indicator_names=indicator_names)

    merged_snapshots = merge_indicator_snapshots(
        initial_snapshots,
        append_snapshots,
        overwrite_from=append_bars[0].trade_date,
    )

    assert merged_snapshots == full_snapshots
    assert states["kdj"]["k"] == pytest.approx(full_snapshots[-1].kdj_k)
    assert states["macd"]["signal_ema"] == pytest.approx(full_snapshots[-1].macd_signal)
    assert states["rsi14"]["previous_close"] == bars[-1].close
    assert states["atr14"]["previous_close"] == bars[-1].close


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


def _stateful_bars(symbol: str, *, count: int) -> tuple[DailyBar, ...]:
    return tuple(
        DailyBar(
            symbol=symbol,
            trade_date=date(2024, 1, 1) + timedelta(days=index),
            open=10.0 + index * 0.4,
            high=11.0 + index * 0.5,
            low=9.0 + index * 0.3,
            close=10.0 + ((index % 7) - 3) * 0.2 + index * 0.35,
            volume=1000.0 + index,
        )
        for index in range(count)
    )
