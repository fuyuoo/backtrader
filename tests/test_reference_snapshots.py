import json
from datetime import date

import pandas as pd

from attbacktrader.data import IndexBar, ShenwanIndustryClassification, StockIndustryMembership
from attbacktrader.data.snapshots import (
    apply_industry_memberships_to_frame,
    attribution_reference_snapshot_dir,
    build_attribution_reference_snapshot_from_frame,
    load_or_fetch_industry_memberships_for_symbols,
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
    mv_abs_row = next(row for row in target_rows if row["field_key"] == "entry.market_cap.total_mv_abs_bucket")
    turnover_row = next(row for row in target_rows if row["field_key"] == "entry.liquidity.turnover_rate_bucket")
    volume_ratio_row = next(row for row in target_rows if row["field_key"] == "entry.liquidity.volume_ratio_bucket")
    amount_row = next(row for row in target_rows if row["field_key"] == "entry.liquidity.amount_bucket")
    amount_vs_row = next(row for row in target_rows if row["field_key"] == "entry.liquidity.amount_vs_20d_bucket")
    industry_atr_row = next(
        row for row in target_rows if row["field_key"] == "entry.volatility.industry_atr_percentile_bucket"
    )
    industry_atr_ratio_row = next(
        row for row in target_rows if row["field_key"] == "entry.volatility.symbol_atr_to_industry_median_bucket"
    )
    industry_amount_row = next(
        row for row in target_rows if row["field_key"] == "entry.liquidity.industry_amount_percentile_bucket"
    )
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
    assert mv_abs_row["bucket"] == "0_100yi"
    assert turnover_row["bucket"] == "lt_1pct"
    assert volume_ratio_row["bucket"] == "0p8_1p2x"
    assert amount_row["bucket"] == "1_3yi"
    assert amount_vs_row["bucket"] in {"0p8_1p2x", "1p2_1p6x"}
    assert industry_atr_row["bucket"] in {"p0_p20", "p20_p40", "p40_p60", "p60_p80", "p80_p100"}
    assert industry_atr_ratio_row["bucket"] in {"lt_0p8x", "0p8_1p2x", "1p2_1p6x", "1p6_2x", "gte_2x"}
    assert industry_amount_row["bucket"] in {"p0_p20", "p20_p40", "p40_p60", "p60_p80", "p80_p100"}
    assert st_row["bucket"] is None
    assert "reference_excluded_st" in st_row["exception_codes"]
    assert metadata_path.exists()
    assert reference_path.exists()
    assert values_path.exists()
    assert exit_code == 0
    assert "reference_values_parquet_path" in capsys.readouterr().out


def test_attribution_reference_snapshot_can_emit_only_target_entries() -> None:
    snapshot = build_attribution_reference_snapshot_from_frame(
        _all_a_feature_frame(),
        start_date=date(2024, 1, 1),
        end_date=date(2024, 3, 29),
        min_reference_count=2,
        emit_symbols=["000001.SZ", "600000.SH"],
        emit_dates=["2024-01-01", "2024-03-29"],
        emit_symbol_date_pairs=[("000001.SZ", "2024-03-29"), ("600000.SH", "2024-01-01")],
    )

    assert snapshot["rows"]
    assert {
        (row["symbol"], row["trade_date"])
        for row in snapshot["rows"]
    } == {("000001.SZ", "2024-03-29"), ("600000.SH", "2024-01-01")}
    assert snapshot["metadata"]["emit_symbol_count"] == 2
    assert snapshot["metadata"]["emit_date_count"] == 2
    assert snapshot["metadata"]["emit_pair_count"] == 2


def test_prepare_attribution_reference_cli_fetches_tushare_provider(tmp_path, monkeypatch, capsys) -> None:
    class FakeProvider:
        def __init__(self, token, *, rate_limit=None):
            self.token = token
            self.rate_limit = rate_limit

        def fetch_attribution_reference_frame(self, *, start_date, end_date):
            raise AssertionError("CLI should call symbol-aware provider method")

        def fetch_attribution_reference_frame_for_symbols(self, *, start_date, end_date, symbols):
            assert symbols is None
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


def test_prepare_attribution_reference_cli_fetches_and_applies_industry_memberships(tmp_path, monkeypatch) -> None:
    calls = []

    class FakeProvider:
        def __init__(self, token, *, rate_limit=None):
            self.token = token

        def fetch_attribution_reference_frame(self, *, start_date, end_date):
            raise AssertionError("CLI should call symbol-aware provider method")

        def fetch_attribution_reference_frame_for_symbols(self, *, start_date, end_date, symbols):
            assert symbols is None
            frame = _all_a_feature_frame()
            return frame.drop(columns=["sw_l1_code"])

        def fetch_stock_industry_memberships(self, *, symbol, source="SW2021"):
            calls.append((symbol, source))
            return (
                StockIndustryMembership(
                    symbol=symbol,
                    stock_name=symbol,
                    level1_code="801780.SI" if symbol == "000001.SZ" else "801180.SI",
                    level1_name="银行" if symbol == "000001.SZ" else "房地产",
                    level2_code="801781.SI",
                    level2_name="二级",
                    level3_code="801782.SI",
                    level3_name="三级",
                    in_date=date(1990, 1, 1),
                    out_date=None,
                    is_new=True,
                    source=source,
                ),
            )

    monkeypatch.setattr(prepare_attribution_reference_cli, "read_tushare_token", lambda path: "test-token")
    monkeypatch.setattr(prepare_attribution_reference_cli, "TushareProvider", FakeProvider)

    prepare_attribution_reference_cli.main(
        [
            "--provider",
            "tushare",
            "--fetch-industry-memberships",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-03-29",
            "--min-reference-count",
            "2",
            "--snapshot-root",
            str(tmp_path / "snapshots"),
            "--output-dir",
            str(tmp_path / "provider-reference"),
        ]
    )

    reference = (tmp_path / "provider-reference" / "reference.json").read_text(encoding="utf-8")
    assert calls
    assert "801780.SI" in reference
    assert (tmp_path / "snapshots" / "industries" / "sw" / "SW2021" / "memberships" / "000001_SZ.parquet").exists()


def test_prepare_attribution_reference_cli_accepts_symbol_whitelist(tmp_path, monkeypatch) -> None:
    seen = {}

    class FakeProvider:
        def __init__(self, token, *, rate_limit=None):
            pass

        def fetch_attribution_reference_frame_for_symbols(self, *, start_date, end_date, symbols):
            seen["symbols"] = symbols
            return _all_a_feature_frame()

    monkeypatch.setattr(prepare_attribution_reference_cli, "read_tushare_token", lambda path: "test-token")
    monkeypatch.setattr(prepare_attribution_reference_cli, "TushareProvider", FakeProvider)

    prepare_attribution_reference_cli.main(
        [
            "--provider",
            "tushare",
            "--symbol",
            "000001.SZ",
            "--symbol",
            "000001.SZ",
            "--symbol",
            "600000.SH",
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

    assert seen["symbols"] == ["000001.SZ", "600000.SH"]


def test_prepare_attribution_reference_cli_derives_scope_from_run_dir(tmp_path, monkeypatch, capsys) -> None:
    seen = {}
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    stock_pool = tmp_path / "pool.csv"
    stock_pool.write_text("ts_code,name\n000001.SZ,平安银行\n600000.SH,浦发银行\n", encoding="utf-8")
    (run_dir / "run_plan.json").write_text(
        json.dumps(
            {
                "run": {"from_date": "2024-01-10", "to_date": "2024-03-29"},
                "data": {"stock_pool_file": str(stock_pool)},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    class FakeProvider:
        def __init__(self, token, *, rate_limit=None):
            pass

        def fetch_attribution_reference_frame_for_symbols(self, *, start_date, end_date, symbols):
            seen["start_date"] = start_date
            seen["end_date"] = end_date
            seen["symbols"] = symbols
            return _all_a_feature_frame()

    monkeypatch.setattr(prepare_attribution_reference_cli, "read_tushare_token", lambda path: "test-token")
    monkeypatch.setattr(prepare_attribution_reference_cli, "TushareProvider", FakeProvider)

    prepare_attribution_reference_cli.main(
        [
            "--provider",
            "tushare",
            "--run-dir",
            str(run_dir),
            "--run-warmup-trading-days",
            "3",
            "--min-reference-count",
            "2",
            "--output-dir",
            str(tmp_path / "provider-reference"),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert seen["symbols"] == ["000001.SZ", "600000.SH"]
    assert seen["start_date"] == date(2024, 1, 5)
    assert seen["end_date"] == date(2024, 3, 29)
    assert stdout["effective_start_date"] == "2024-01-05"
    assert stdout["effective_end_date"] == "2024-03-29"
    assert stdout["symbol_count"] == 2


def test_prepare_attribution_reference_cli_can_emit_run_entry_scope(tmp_path, monkeypatch, capsys) -> None:
    seen = {}
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run_plan.json").write_text(
        json.dumps(
            {
                "run": {"from_date": "2024-01-01", "to_date": "2024-03-29"},
                "data": {"symbols": ["000001.SZ", "600000.SH"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "trade_attribution.json").write_text(
        json.dumps(
            {
                "attributions": [
                    {"trade_index": 1, "symbol": "000001.SZ", "entry_date": "2024-03-29"},
                    {"trade_index": 2, "symbol": "600000.SH", "entry_date": "2024-01-01"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "trade_lifecycle.json").write_text(
        json.dumps(
            {
                "lifecycles": [
                    {
                        "trade_index": 1,
                        "events": [
                            {
                                "event_type": "entry",
                                "values": {"signal_trade_date": "2024-03-28"},
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    class FakeProvider:
        def __init__(self, token, *, rate_limit=None):
            pass

        def fetch_attribution_reference_frame_for_symbols(self, *, start_date, end_date, symbols):
            seen["symbols"] = symbols
            return _all_a_feature_frame()

    monkeypatch.setattr(prepare_attribution_reference_cli, "read_tushare_token", lambda path: "test-token")
    monkeypatch.setattr(prepare_attribution_reference_cli, "TushareProvider", FakeProvider)

    prepare_attribution_reference_cli.main(
        [
            "--provider",
            "tushare",
            "--run-dir",
            str(run_dir),
            "--emit-run-entry-scope",
            "--reference-fetch-scope",
            "all",
            "--min-reference-count",
            "2",
            "--output-dir",
            str(tmp_path / "provider-reference"),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)
    reference = json.loads((tmp_path / "provider-reference" / "reference.json").read_text(encoding="utf-8"))

    assert stdout["emit_run_entry_scope"] is True
    assert stdout["reference_fetch_scope"] == "all"
    assert stdout["emit_symbol_count"] == 2
    assert stdout["emit_date_count"] == 3
    assert stdout["emit_pair_count"] == 3
    assert seen["symbols"] is None
    assert {
        (row["symbol"], row["trade_date"])
        for row in reference["rows"]
    } == {("000001.SZ", "2024-03-28"), ("000001.SZ", "2024-03-29"), ("600000.SH", "2024-01-01")}


def test_prepare_attribution_reference_cli_bulk_fetches_industry_memberships_for_all_scope(
    tmp_path,
    monkeypatch,
) -> None:
    seen = {}
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run_plan.json").write_text(
        json.dumps(
            {
                "run": {"from_date": "2024-01-01", "to_date": "2024-03-29"},
                "data": {"symbols": ["000001.SZ", "600000.SH"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "trade_attribution.json").write_text(
        json.dumps(
            {
                "attributions": [
                    {"trade_index": 1, "symbol": "000001.SZ", "entry_date": "2024-03-29"},
                    {"trade_index": 2, "symbol": "600000.SH", "entry_date": "2024-01-01"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    class FakeProvider:
        def __init__(self, token, *, rate_limit=None):
            pass

        def fetch_attribution_reference_frame_for_symbols(self, *, start_date, end_date, symbols):
            seen["symbols"] = symbols
            return _all_a_feature_frame().drop(columns=["sw_l1_code"])

        def fetch_stock_industry_memberships(self, *, symbol, source="SW2021"):
            raise AssertionError("full-A industry memberships should use the bulk provider method")

        def fetch_all_stock_industry_memberships(self, *, source="SW2021"):
            seen["bulk_source"] = source
            return (
                StockIndustryMembership(
                    symbol="000001.SZ",
                    stock_name="平安银行",
                    level1_code="801780.SI",
                    level1_name="银行",
                    level2_code="801781.SI",
                    level2_name="二级",
                    level3_code="801782.SI",
                    level3_name="三级",
                    in_date=date(1990, 1, 1),
                    out_date=None,
                    is_new=True,
                    source=source,
                ),
                StockIndustryMembership(
                    symbol="600000.SH",
                    stock_name="浦发银行",
                    level1_code="801180.SI",
                    level1_name="房地产",
                    level2_code="801181.SI",
                    level2_name="二级",
                    level3_code="801182.SI",
                    level3_name="三级",
                    in_date=date(1990, 1, 1),
                    out_date=None,
                    is_new=True,
                    source=source,
                ),
            )

    monkeypatch.setattr(prepare_attribution_reference_cli, "read_tushare_token", lambda path: "test-token")
    monkeypatch.setattr(prepare_attribution_reference_cli, "TushareProvider", FakeProvider)

    prepare_attribution_reference_cli.main(
        [
            "--provider",
            "tushare",
            "--run-dir",
            str(run_dir),
            "--emit-run-entry-scope",
            "--reference-fetch-scope",
            "all",
            "--fetch-industry-memberships",
            "--min-reference-count",
            "2",
            "--snapshot-root",
            str(tmp_path / "snapshots"),
            "--output-dir",
            str(tmp_path / "provider-reference"),
        ]
    )
    reference = json.loads((tmp_path / "provider-reference" / "reference.json").read_text(encoding="utf-8"))

    assert seen["symbols"] is None
    assert seen["bulk_source"] == "SW2021"
    assert "801780.SI" in (tmp_path / "provider-reference" / "reference.json").read_text(encoding="utf-8")
    assert (tmp_path / "snapshots" / "industries" / "sw" / "SW2021" / "memberships" / "000001_SZ.parquet").exists()
    assert {
        (row["symbol"], row["trade_date"])
        for row in reference["rows"]
    } == {("000001.SZ", "2024-03-29"), ("600000.SH", "2024-01-01")}


def test_industry_memberships_apply_by_effective_interval(tmp_path) -> None:
    frame = pd.DataFrame(
        [
            {"symbol": "000001.SZ", "trade_date": "2024-01-15", "close": 10, "high": 11, "low": 9},
            {"symbol": "000001.SZ", "trade_date": "2024-02-15", "close": 10, "high": 11, "low": 9},
        ]
    )
    memberships = {
        "000001.SZ": (
            StockIndustryMembership(
                symbol="000001.SZ",
                stock_name="平安银行",
                level1_code="801780.SI",
                level1_name="银行",
                level2_code="801781.SI",
                level2_name="二级",
                level3_code="801782.SI",
                level3_name="三级",
                in_date=date(2024, 1, 1),
                out_date=date(2024, 1, 31),
                is_new=True,
                source="SW2021",
            ),
            StockIndustryMembership(
                symbol="000001.SZ",
                stock_name="平安银行",
                level1_code="801180.SI",
                level1_name="房地产",
                level2_code="801181.SI",
                level2_name="二级",
                level3_code="801182.SI",
                level3_name="三级",
                in_date=date(2024, 2, 1),
                out_date=None,
                is_new=True,
                source="SW2021",
            ),
        )
    }

    enriched = apply_industry_memberships_to_frame(frame, memberships)

    assert list(enriched["sw_l1_code"]) == ["801780.SI", "801180.SI"]


def test_industry_membership_backfill_is_explicit_and_audited() -> None:
    frame = pd.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "trade_date": "2024-01-15",
                "open": 10,
                "close": 10,
                "high": 11,
                "low": 9,
                "amount": 100000,
                "turnover_rate": 1.0,
                "volume_ratio": 1.0,
                "total_mv": 100,
                "circ_mv": 80,
                "pe": 10,
                "pe_ttm": 11,
                "pb": 1.2,
                "is_st": False,
                "is_suspended": False,
                "exchange": "SZSE",
                "listing_trading_days": 200,
                "is_tradable": True,
            }
        ]
    )
    memberships = {
        "000001.SZ": (
            StockIndustryMembership(
                symbol="000001.SZ",
                stock_name="平安银行",
                level1_code="801780.SI",
                level1_name="银行",
                level2_code="801781.SI",
                level2_name="二级",
                level3_code="801782.SI",
                level3_name="三级",
                in_date=date(2024, 3, 1),
                out_date=None,
                is_new=True,
                source="SW2021",
            ),
        )
    }

    without_backfill = apply_industry_memberships_to_frame(frame, memberships)
    with_backfill = apply_industry_memberships_to_frame(frame, memberships, backfill_missing=True)
    snapshot = build_attribution_reference_snapshot_from_frame(
        with_backfill,
        start_date=date(2024, 1, 15),
        end_date=date(2024, 1, 15),
        min_reference_count=1,
    )
    industry_row = next(row for row in snapshot["rows"] if row["field_key"] == "industry.sw_l1.code")

    assert without_backfill["sw_l1_code"].iloc[0] is None
    assert bool(without_backfill["industry_membership_missing"].iloc[0]) is True
    assert with_backfill["sw_l1_code"].iloc[0] == "801780.SI"
    assert bool(with_backfill["industry_membership_missing"].iloc[0]) is False
    assert bool(with_backfill["industry_membership_backfilled"].iloc[0]) is True
    assert industry_row["bucket"] == "801780.SI"
    assert "industry_membership_backfilled" in industry_row["exception_codes"]
    assert snapshot["metadata"]["industry_membership_backfilled_count"] == 1


def _all_a_feature_frame() -> pd.DataFrame:
    rows = []
    symbols = [
        ("000001.SZ", False, False, "SZSE", 200, True, "801780.SI", -12.0),
        ("000002.SZ", False, False, "SZSE", 200, True, "801180.SI", 18.0),
        ("600000.SH", True, False, "SSE", 200, True, "801780.SI", 20.0),
        ("000003.SZ", False, False, "SZSE", 200, True, "801780.SI", 25.0),
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
                    "turnover_rate": 0.8 + symbol_index * 1.2,
                    "volume_ratio": 0.9 + symbol_index * 0.4,
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
