from datetime import date

import pandas as pd

from attbacktrader.data import IndexBar, ShenwanIndustryClassification, StockIndustryMembership
from attbacktrader.data.snapshots import (
    attribution_reference_snapshot_dir,
    build_attribution_reference_snapshot_from_frame,
    discover_index_bars_snapshot_paths,
    discover_industry_index_bars_snapshot_paths,
    index_bars_snapshot_path,
    industry_index_bars_snapshot_path,
    read_index_bars_parquet,
    read_shenwan_classifications_parquet,
    read_stock_industry_memberships_parquet,
    shenwan_classification_snapshot_path,
    stock_industry_membership_snapshot_path,
    write_index_bars_parquet,
    write_shenwan_classifications_parquet,
    write_stock_industry_memberships_parquet,
    write_attribution_reference_snapshot,
)
from attbacktrader.cli import prepare_attribution_reference as prepare_attribution_reference_cli


def test_index_bars_parquet_round_trip(tmp_path) -> None:
    bars = (
        IndexBar("000001.SH", date(2024, 1, 2), 2950.0, 2960.0, 2940.0, 2955.0, 1000.0, 2000.0),
        IndexBar("000001.SH", date(2024, 1, 3), 2960.0, 2970.0, 2950.0, 2965.0, 2000.0, 3000.0),
    )
    path = index_bars_snapshot_path(
        tmp_path,
        symbol="000001.SH",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 3),
    )

    written_path = write_index_bars_parquet(bars, path)

    assert written_path == path
    assert path.parent.name == "indexes"
    assert path.name == "000001_SH_20240102_20240103.parquet"
    assert read_index_bars_parquet(path) == bars


def test_empty_index_bars_parquet_round_trip(tmp_path) -> None:
    path = index_bars_snapshot_path(
        tmp_path,
        symbol="000510.SH",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 3),
    )

    written_path = write_index_bars_parquet((), path)

    assert written_path == path
    assert read_index_bars_parquet(path) == ()


def test_industry_index_bars_path_includes_shenwan_source(tmp_path) -> None:
    path = industry_index_bars_snapshot_path(
        tmp_path,
        symbol="801780.SI",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 3),
        source="SW2021",
    )

    assert path.parts[-4:-1] == ("sw", "SW2021", "index_bars")
    assert path.name == "801780_SI_20240102_20240103.parquet"


def test_discovers_broader_index_bar_snapshots(tmp_path) -> None:
    index_path = index_bars_snapshot_path(
        tmp_path,
        symbol="000300.SH",
        start_date=date(2023, 10, 1),
        end_date=date(2024, 3, 31),
    )
    industry_path = industry_index_bars_snapshot_path(
        tmp_path,
        symbol="801780.SI",
        start_date=date(2023, 12, 1),
        end_date=date(2024, 3, 31),
        source="SW2021",
    )
    write_index_bars_parquet(
        (
            IndexBar("000300.SH", date(2023, 10, 1), 100.0, 101.0, 99.0, 100.0),
            IndexBar("000300.SH", date(2024, 3, 31), 110.0, 111.0, 109.0, 110.0),
        ),
        index_path,
    )
    write_index_bars_parquet(
        (
            IndexBar("801780.SI", date(2023, 12, 1), 100.0, 101.0, 99.0, 100.0),
            IndexBar("801780.SI", date(2024, 3, 31), 110.0, 111.0, 109.0, 110.0),
        ),
        industry_path,
    )

    index_candidates = discover_index_bars_snapshot_paths(
        tmp_path,
        symbol="000300.SH",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 3, 31),
    )
    industry_candidates = discover_industry_index_bars_snapshot_paths(
        tmp_path,
        symbol="801780.SI",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 3, 31),
        source="SW2021",
    )

    assert index_candidates[0].path == index_path
    assert industry_candidates[0].path == industry_path


def test_shenwan_classifications_parquet_round_trip(tmp_path) -> None:
    classifications = (
        ShenwanIndustryClassification("801780.SI", "银行", 1, "480000", "0", "SW2021"),
        ShenwanIndustryClassification("801783.SI", "股份制银行Ⅱ", 2, "480200", "801780.SI", "SW2021"),
    )
    path = shenwan_classification_snapshot_path(tmp_path, source="SW2021")

    written_path = write_shenwan_classifications_parquet(classifications, path)

    assert written_path == path
    assert path.name == "classifications.parquet"
    assert read_shenwan_classifications_parquet(path) == classifications


def test_stock_industry_memberships_parquet_round_trip(tmp_path) -> None:
    memberships = (
        StockIndustryMembership(
            symbol="000001.SZ",
            stock_name="平安银行",
            level1_code="801780.SI",
            level1_name="银行",
            level2_code="801783.SI",
            level2_name="股份制银行Ⅱ",
            level3_code="857831.SI",
            level3_name="股份制银行Ⅲ",
            in_date=date(1991, 4, 3),
            out_date=None,
            is_new=True,
            source="SW2021",
        ),
    )
    path = stock_industry_membership_snapshot_path(tmp_path, symbol="000001.SZ", source="SW2021")

    written_path = write_stock_industry_memberships_parquet(memberships, path)

    assert written_path == path
    assert path.parent.name == "memberships"
    assert path.name == "000001_SZ.parquet"
    assert read_stock_industry_memberships_parquet(path) == memberships


def test_attribution_reference_snapshot_builds_buckets_and_exceptions(tmp_path, capsys) -> None:
    frame = _all_a_feature_frame()
    snapshot = build_attribution_reference_snapshot_from_frame(
        frame,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 3, 29),
        min_reference_count=2,
    )
    output_dir = attribution_reference_snapshot_dir(
        tmp_path,
        reference_universe="full_a_main_chinext_star",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 3, 29),
    )
    metadata_path, reference_path, values_path = write_attribution_reference_snapshot(snapshot, output_dir)
    cli_input = tmp_path / "all_a.csv"
    frame.to_csv(cli_input, index=False)
    exit_code = prepare_attribution_reference_cli.main(
        [
            "--input",
            str(cli_input),
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-03-29",
            "--min-reference-count",
            "2",
            "--output-dir",
            str(tmp_path / "cli-reference"),
        ]
    )

    rows = snapshot["rows"]
    target_rows = [
        row for row in rows
        if row["symbol"] == "000001.SZ" and row["trade_date"] == "2024-03-29"
    ]
    pe_row = next(row for row in target_rows if row["field_key"] == "entry.valuation.pe_bucket")
    high_row = next(row for row in target_rows if row["field_key"] == "entry.price_position.near_high_20d_bucket")
    mv_row = next(row for row in target_rows if row["field_key"] == "entry.market_cap.total_mv_bucket")
    st_row = next(
        row for row in rows
        if row["symbol"] == "600000.SH"
        and row["trade_date"] == "2024-03-29"
        and row["field_key"] == "entry.market_cap.total_mv_bucket"
    )

    assert snapshot["metadata"]["schema"] == "attribution_reference_fields.v1"
    assert pe_row["bucket"] == "negative"
    assert "negative_pe" in pe_row["exception_codes"]
    assert high_row["bucket"] in {"at_high", "near_high", "moderate_pullback", "deep_pullback", "far_from_high"}
    assert mv_row["bucket"] in {"p0_p20", "p20_p40", "p40_p60", "p60_p80", "p80_p100"}
    assert st_row["bucket"] is None
    assert "reference_excluded_st" in st_row["exception_codes"]
    assert metadata_path.exists()
    assert reference_path.exists()
    assert values_path.exists()
    assert exit_code == 0
    assert "reference_values_parquet_path" in capsys.readouterr().out


def test_prepare_attribution_reference_cli_fetches_tushare_provider(tmp_path, monkeypatch, capsys) -> None:
    class FakeProvider:
        def __init__(self, token, *, rate_limit=None):
            self.token = token
            self.rate_limit = rate_limit

        def fetch_attribution_reference_frame(self, *, start_date, end_date):
            assert start_date == date(2024, 1, 1)
            assert end_date == date(2024, 3, 29)
            return _all_a_feature_frame()

    monkeypatch.setattr(prepare_attribution_reference_cli, "read_tushare_token", lambda path: "test-token")
    monkeypatch.setattr(prepare_attribution_reference_cli, "TushareProvider", FakeProvider)

    exit_code = prepare_attribution_reference_cli.main(
        [
            "--provider",
            "tushare",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-03-29",
            "--min-reference-count",
            "2",
            "--output-dir",
            str(tmp_path / "provider-reference"),
        ]
    )
    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert "reference_values_parquet_path" in stdout
    assert (tmp_path / "provider-reference" / "reference.json").exists()


def _all_a_feature_frame() -> pd.DataFrame:
    rows = []
    symbols = [
        ("000001.SZ", False, False, "SZSE", 200, True, "801780.SI", -12.0),
        ("000002.SZ", False, False, "SZSE", 200, True, "801180.SI", 18.0),
        ("600000.SH", True, False, "SSE", 200, True, "801780.SI", 20.0),
    ]
    days = pd.bdate_range("2024-01-01", "2024-03-29")
    for day_index, trade_date in enumerate(days):
        for symbol_index, (symbol, is_st, is_suspended, exchange, listing_days, is_tradable, industry, pe) in enumerate(symbols):
            base = 10 + symbol_index * 5 + day_index * (0.05 + symbol_index * 0.01)
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": trade_date.date().isoformat(),
                    "open": base,
                    "high": base * 1.02,
                    "low": base * 0.98,
                    "close": base * 1.01,
                    "amount": 100000 + symbol_index * 50000 + day_index * 1000,
                    "total_mv": 100 + symbol_index * 200 + day_index,
                    "circ_mv": 80 + symbol_index * 150 + day_index,
                    "pe": pe,
                    "pe_ttm": pe + 1,
                    "pb": 1.2 + symbol_index,
                    "sw_l1_code": industry,
                    "is_st": is_st,
                    "is_suspended": is_suspended,
                    "exchange": exchange,
                    "listing_trading_days": listing_days + day_index,
                    "is_tradable": is_tradable,
                }
            )
    return pd.DataFrame(rows)
