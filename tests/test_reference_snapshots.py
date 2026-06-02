from datetime import date

from attbacktrader.data import IndexBar, ShenwanIndustryClassification, StockIndustryMembership
from attbacktrader.data.snapshots import (
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
)


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
