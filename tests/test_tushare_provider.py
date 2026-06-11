import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from attbacktrader.data.providers.tushare import (
    TushareProvider,
    TushareRateLimitConfig,
    _date_windows,
    _daily_bars_from_frame,
    _index_constituents_from_frame,
    _index_bars_from_frame,
    _month_windows,
    _shenwan_classifications_from_frame,
    _stock_names_from_frame,
    _stock_industry_memberships_from_frame,
    _tradability_statuses_from_frames,
    read_tushare_token,
)


def test_tushare_provider_fetches_qfq_daily_bars_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {}
    fake_api = object()
    frame = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "20240102",
                "open": 8.76,
                "high": 8.91,
                "low": 8.69,
                "close": 8.88,
                "vol": 900,
            }
        ]
    )

    def pro_api(token: str) -> object:
        calls["token"] = token
        return fake_api

    def pro_bar(**kwargs) -> pd.DataFrame:
        calls["pro_bar"] = kwargs
        return frame

    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=pro_api, pro_bar=pro_bar))

    provider = TushareProvider("test-token")
    bars = provider.fetch_daily_bars(
        symbol="000001.SZ",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 3),
    )

    assert calls["token"] == "test-token"
    assert calls["pro_bar"]["api"] is fake_api
    assert calls["pro_bar"]["adj"] == "qfq"
    assert calls["pro_bar"]["freq"] == "D"
    assert calls["pro_bar"]["asset"] == "E"
    assert bars[0].close == 8.88


def test_tushare_provider_retries_transient_rate_limit_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"index_daily": 0}
    sleeps = []
    now = [0.0]
    frame = pd.DataFrame(
        [
            {
                "ts_code": "000001.SH",
                "trade_date": "20240102",
                "open": 2950.0,
                "high": 2960.0,
                "low": 2940.0,
                "close": 2955.0,
                "vol": 1000,
                "amount": 2000,
            }
        ]
    )

    class FakeApi:
        def index_daily(self, **kwargs):
            calls["index_daily"] += 1
            if calls["index_daily"] == 1:
                raise Exception("每分钟最多访问该接口200次")
            return frame

    def sleeper(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=lambda token: FakeApi()))

    provider = TushareProvider(
        "test-token",
        rate_limit=TushareRateLimitConfig(
            requests_per_minute=60,
            retry_attempts=1,
            retry_base_seconds=0.5,
            retry_max_seconds=0.5,
        ),
        sleeper=sleeper,
        clock=lambda: now[0],
    )

    bars = provider.fetch_index_daily_bars(
        symbol="000001.SH",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 2),
    )

    assert calls["index_daily"] == 2
    assert sleeps == [0.5, 0.5]
    assert bars[0].close == 2955.0


def test_tushare_provider_does_not_retry_permission_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"index_daily": 0}

    class FakeApi:
        def index_daily(self, **kwargs):
            calls["index_daily"] += 1
            raise Exception("抱歉，您没有权限访问该接口")

    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=lambda token: FakeApi()))

    provider = TushareProvider(
        "test-token",
        rate_limit=TushareRateLimitConfig(requests_per_minute=600, retry_attempts=3),
        sleeper=lambda seconds: None,
    )

    with pytest.raises(RuntimeError, match="index_daily failed"):
        provider.fetch_index_daily_bars(
            symbol="000001.SH",
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 2),
        )

    assert calls["index_daily"] == 1


def test_tushare_provider_splits_index_daily_by_configured_date_window(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    class FakeApi:
        def index_daily(self, **kwargs):
            calls.append(kwargs)
            return pd.DataFrame(
                [
                    {
                        "ts_code": "000001.SH",
                        "trade_date": kwargs["start_date"],
                        "open": 2950.0,
                        "high": 2960.0,
                        "low": 2940.0,
                        "close": 2955.0,
                        "vol": 1000,
                        "amount": 2000,
                    }
                ]
            )

    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=lambda token: FakeApi()))

    provider = TushareProvider(
        "test-token",
        rate_limit=TushareRateLimitConfig(requests_per_minute=600, date_window_days=2),
        sleeper=lambda seconds: None,
    )

    bars = provider.fetch_index_daily_bars(
        symbol="000001.SH",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 5),
    )

    assert [(call["start_date"], call["end_date"]) for call in calls] == [
        ("20240101", "20240102"),
        ("20240103", "20240104"),
        ("20240105", "20240105"),
    ]
    assert len(bars) == 3


def test_tushare_provider_fetches_industry_index_bars_from_sw_daily(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {}
    frame = pd.DataFrame(
        [
            {
                "ts_code": "801780.SI",
                "trade_date": "20240102",
                "open": 3200.0,
                "high": 3210.0,
                "low": 3190.0,
                "close": 3205.0,
                "vol": 1000.0,
                "amount": 2000.0,
            }
        ]
    )

    class FakeApi:
        def sw_daily(self, **kwargs):
            calls["sw_daily"] = kwargs
            return frame

    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=lambda token: FakeApi()))

    provider = TushareProvider("test-token")
    bars = provider.fetch_industry_index_daily_bars(
        symbol="801780.SI",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 3),
        source="SW2021",
    )

    assert calls["sw_daily"]["ts_code"] == "801780.SI"
    assert calls["sw_daily"]["start_date"] == "20240102"
    assert bars[0].symbol == "801780.SI"
    assert bars[0].close == 3205.0


def test_tushare_provider_fetches_index_constituents_from_index_weight(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {}
    frame = pd.DataFrame(
        [
            {
                "index_code": "000300.SH",
                "con_code": "000001.SZ",
                "trade_date": "20240601",
                "weight": 0.5,
            }
        ]
    )

    class FakeApi:
        def index_weight(self, **kwargs):
            calls["index_weight"] = kwargs
            return frame

    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=lambda token: FakeApi()))

    provider = TushareProvider(
        "test-token",
        rate_limit=TushareRateLimitConfig(requests_per_minute=600),
        sleeper=lambda seconds: None,
    )
    constituents = provider.fetch_index_constituents(
        index_symbol="000300.SH",
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 7),
    )

    assert calls["index_weight"]["index_code"] == "000300.SH"
    assert calls["index_weight"]["start_date"] == "20240601"
    assert calls["index_weight"]["end_date"] == "20240607"
    assert constituents[0].symbol == "000001.SZ"
    assert constituents[0].source_index == "000300.SH"
    assert constituents[0].trade_date == date(2024, 6, 1)
    assert constituents[0].weight == 0.5


def test_tushare_provider_fetches_index_constituents_by_month(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    class FakeApi:
        def index_weight(self, **kwargs):
            calls.append(kwargs)
            return pd.DataFrame(
                [
                    {
                        "index_code": kwargs["index_code"],
                        "con_code": "000001.SZ",
                        "trade_date": kwargs["end_date"],
                        "weight": 0.5,
                    }
                ]
            )

    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=lambda token: FakeApi()))

    provider = TushareProvider(
        "test-token",
        rate_limit=TushareRateLimitConfig(requests_per_minute=600),
        sleeper=lambda seconds: None,
    )

    constituents = provider.fetch_index_constituents(
        index_symbol="000300.SH",
        start_date=date(2024, 1, 15),
        end_date=date(2024, 3, 5),
    )

    assert [(call["start_date"], call["end_date"]) for call in calls] == [
        ("20240115", "20240131"),
        ("20240201", "20240229"),
        ("20240301", "20240305"),
    ]
    assert len(constituents) == 3


def test_tushare_provider_fetches_stock_names(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {}
    frame = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "name": "平安银行"},
            {"ts_code": "600519.SH", "name": "贵州茅台"},
        ]
    )

    class FakeApi:
        def stock_basic(self, **kwargs):
            calls["stock_basic"] = kwargs
            return frame

    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=lambda token: FakeApi()))

    provider = TushareProvider("test-token")
    names = provider.fetch_stock_names()

    assert calls["stock_basic"]["fields"] == "ts_code,name"
    assert names == {"000001.SZ": "平安银行", "600519.SH": "贵州茅台"}


def test_tushare_provider_fetches_attribution_reference_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {}
    daily_frame = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "trade_date": "20240102", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.2, "vol": 1000, "amount": 2000},
            {"ts_code": "600000.SH", "trade_date": "20240102", "open": 20.0, "high": 20.5, "low": 19.8, "close": 20.2, "vol": 2000, "amount": 3000},
        ]
    )
    daily_basic_frame = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "trade_date": "20240102", "turnover_rate": 1.2, "volume_ratio": 1.1, "pe": 10.0, "pe_ttm": 11.0, "pb": 1.3, "total_mv": 100.0, "circ_mv": 90.0},
            {"ts_code": "600000.SH", "trade_date": "20240102", "turnover_rate": 2.2, "volume_ratio": 1.5, "pe": 20.0, "pe_ttm": 21.0, "pb": 2.3, "total_mv": 200.0, "circ_mv": 180.0},
        ]
    )
    stock_basic_frame = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "name": "平安银行", "exchange": "SZSE", "market": "主板", "list_date": "19910403"},
            {"ts_code": "600000.SH", "name": "浦发银行", "exchange": "SSE", "market": "主板", "list_date": "19991110"},
        ]
    )
    suspend_frame = pd.DataFrame(
        [{"ts_code": "600000.SH", "trade_date": "20240102", "suspend_timing": "全天停牌", "suspend_type": "停牌"}]
    )
    namechange_frame = pd.DataFrame(
        [{"ts_code": "000001.SZ", "name": "ST平安", "start_date": "20240101", "end_date": "20240131", "change_reason": "ST"}]
    )

    class FakeApi:
        def daily(self, **kwargs):
            calls["daily"] = kwargs
            return daily_frame

        def daily_basic(self, **kwargs):
            calls["daily_basic"] = kwargs
            return daily_basic_frame

        def stock_basic(self, **kwargs):
            calls["stock_basic"] = kwargs
            return stock_basic_frame

        def suspend_d(self, **kwargs):
            calls["suspend_d"] = kwargs
            return suspend_frame

        def namechange(self, **kwargs):
            calls["namechange"] = kwargs
            return namechange_frame

    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=lambda token: FakeApi()))

    provider = TushareProvider("test-token", rate_limit=TushareRateLimitConfig(requests_per_minute=600))
    frame = provider.fetch_attribution_reference_frame(start_date=date(2024, 1, 2), end_date=date(2024, 1, 2))

    assert calls["daily"]["fields"] == "ts_code,trade_date,open,high,low,close,vol,amount"
    assert calls["daily_basic"]["fields"] == "ts_code,trade_date,turnover_rate,volume_ratio,pe,pe_ttm,pb,total_mv,circ_mv"
    assert calls["stock_basic"]["fields"] == "ts_code,name,exchange,market,list_date"
    assert calls["namechange"]["fields"] == "ts_code,name,start_date,end_date,change_reason"
    assert set(frame["symbol"]) == {"000001.SZ", "600000.SH"}
    assert bool(frame.loc[frame["symbol"] == "000001.SZ", "is_st"].iloc[0]) is True
    assert bool(frame.loc[frame["symbol"] == "600000.SH", "is_suspended"].iloc[0]) is True
    assert frame.loc[frame["symbol"] == "000001.SZ", "listing_trading_days"].iloc[0] > 60
    assert "total_mv" in frame.columns


def test_tushare_reference_listing_days_uses_stock_list_date(monkeypatch: pytest.MonkeyPatch) -> None:
    daily_frame = pd.DataFrame(
        [
            {"ts_code": "301999.SZ", "trade_date": "20240110", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.2, "vol": 1000, "amount": 2000},
        ]
    )
    daily_basic_frame = pd.DataFrame(
        [
            {"ts_code": "301999.SZ", "trade_date": "20240110", "turnover_rate": 1.2, "volume_ratio": 1.1, "pe": 10.0, "pe_ttm": 11.0, "pb": 1.3, "total_mv": 100.0, "circ_mv": 90.0},
        ]
    )
    stock_basic_frame = pd.DataFrame(
        [{"ts_code": "301999.SZ", "name": "新股", "exchange": "SZSE", "market": "创业板", "list_date": "20240102"}]
    )

    class FakeApi:
        def daily(self, **kwargs):
            return daily_frame

        def daily_basic(self, **kwargs):
            return daily_basic_frame

        def stock_basic(self, **kwargs):
            return stock_basic_frame

        def suspend_d(self, **kwargs):
            return pd.DataFrame()

        def namechange(self, **kwargs):
            return pd.DataFrame()

    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=lambda token: FakeApi()))

    provider = TushareProvider("test-token", rate_limit=TushareRateLimitConfig(requests_per_minute=600))
    frame = provider.fetch_attribution_reference_frame(start_date=date(2024, 1, 10), end_date=date(2024, 1, 10))

    assert frame["listing_trading_days"].iloc[0] < 60


def test_tushare_provider_fetches_tradability_statuses(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {}
    limit_frame = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "trade_date": "20240102", "up_limit": 11.0, "down_limit": 9.0},
        ]
    )
    close_frame = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "trade_date": "20240102", "close": 11.0},
        ]
    )
    suspend_frame = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "20240103",
                "suspend_timing": "全天停牌",
                "suspend_type": "停牌",
            },
        ]
    )

    class FakeApi:
        def stk_limit(self, **kwargs):
            calls["stk_limit"] = kwargs
            return limit_frame

        def daily(self, **kwargs):
            calls["daily"] = kwargs
            return close_frame

        def suspend_d(self, **kwargs):
            calls["suspend_d"] = kwargs
            return suspend_frame

    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=lambda token: FakeApi()))

    provider = TushareProvider("test-token")
    statuses = provider.fetch_tradability_statuses(
        symbol="000001.SZ",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 3),
    )

    assert calls["stk_limit"]["fields"] == "ts_code,trade_date,up_limit,down_limit"
    assert calls["daily"]["fields"] == "ts_code,trade_date,close"
    assert calls["suspend_d"]["fields"] == "ts_code,trade_date,suspend_timing,suspend_type"
    assert statuses[0].trade_date == date(2024, 1, 2)
    assert statuses[0].is_limit_up is True
    assert statuses[1].trade_date == date(2024, 1, 3)
    assert statuses[1].is_suspended is True


def test_tushare_qfq_frame_maps_to_sorted_daily_bars() -> None:
    frame = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "20240103",
                "open": 9.2,
                "high": 9.5,
                "low": 9.1,
                "close": 9.4,
                "vol": 1000,
            },
            {
                "ts_code": "000001.SZ",
                "trade_date": "20240102",
                "open": 9.0,
                "high": 9.3,
                "low": 8.9,
                "close": 9.2,
                "vol": 900,
            },
        ]
    )

    bars = _daily_bars_from_frame(frame)

    assert [bar.trade_date.isoformat() for bar in bars] == ["2024-01-02", "2024-01-03"]
    assert bars[0].symbol == "000001.SZ"
    assert bars[0].open == 9.0
    assert bars[1].close == 9.4
    assert bars[1].volume == 1000.0


def test_tushare_index_daily_frame_maps_to_sorted_index_bars() -> None:
    frame = pd.DataFrame(
        [
            {
                "ts_code": "000001.SH",
                "trade_date": "20240103",
                "open": 2960.0,
                "high": 2970.0,
                "low": 2950.0,
                "close": 2965.0,
                "vol": 2000,
                "amount": 3000,
            },
            {
                "ts_code": "000001.SH",
                "trade_date": "20240102",
                "open": 2950.0,
                "high": 2960.0,
                "low": 2940.0,
                "close": 2955.0,
                "vol": 1000,
                "amount": 2000,
            },
        ]
    )

    bars = _index_bars_from_frame(frame)

    assert [bar.trade_date.isoformat() for bar in bars] == ["2024-01-02", "2024-01-03"]
    assert bars[0].symbol == "000001.SH"
    assert bars[0].close == 2955.0
    assert bars[1].amount == 3000.0


def test_tushare_index_daily_frame_expands_high_low_to_cover_open_close() -> None:
    frame = pd.DataFrame(
        [
            {
                "ts_code": "801780.SI",
                "trade_date": "20151230",
                "open": 3374.05,
                "high": 3392.81,
                "low": 3336.22,
                "close": 3392.82,
                "vol": 121589,
                "amount": 1097753,
            },
            {
                "ts_code": "801780.SI",
                "trade_date": "20151231",
                "open": 3335.00,
                "high": 3370.00,
                "low": 3335.01,
                "close": 3350.00,
                "vol": 121589,
                "amount": 1097753,
            },
        ]
    )

    bars = _index_bars_from_frame(frame)

    assert bars[0].high == 3392.82
    assert bars[0].close == 3392.82
    assert bars[1].low == 3335.00
    assert bars[1].open == 3335.00


def test_tushare_index_weight_frame_maps_to_sorted_constituents() -> None:
    frame = pd.DataFrame(
        [
            {"index_code": "000905.SH", "con_code": "000002.SZ", "trade_date": "20240601", "weight": 0.2},
            {"index_code": "000300.SH", "con_code": "000001.SZ", "trade_date": "20240501", "weight": None},
        ]
    )

    constituents = _index_constituents_from_frame(frame, source_index="fallback")

    assert [item.symbol for item in constituents] == ["000001.SZ", "000002.SZ"]
    assert constituents[0].source_index == "000300.SH"
    assert constituents[0].weight is None
    assert constituents[1].trade_date == date(2024, 6, 1)


def test_tushare_stock_basic_frame_maps_stock_names() -> None:
    frame = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "name": "平安银行"},
            {"ts_code": "600519.SH", "name": "贵州茅台"},
        ]
    )

    assert _stock_names_from_frame(frame) == {"000001.SZ": "平安银行", "600519.SH": "贵州茅台"}


def test_tushare_shenwan_classification_frame_maps_levels() -> None:
    frame = pd.DataFrame(
        [
            {
                "index_code": "801780.SI",
                "industry_name": "银行",
                "level": "L1",
                "industry_code": "480000",
                "is_pub": "1",
                "parent_code": "0",
                "src": "SW2021",
            },
            {
                "index_code": "801783.SI",
                "industry_name": "股份制银行Ⅱ",
                "level": "L2",
                "industry_code": "480200",
                "is_pub": "1",
                "parent_code": "801780.SI",
                "src": "SW2021",
            },
        ]
    )

    classifications = _shenwan_classifications_from_frame(frame)

    assert classifications[0].level == 1
    assert classifications[0].industry_name == "银行"
    assert classifications[1].parent_code == "801780.SI"


def test_tushare_stock_industry_membership_frame_maps_optional_out_date() -> None:
    frame = pd.DataFrame(
        [
            {
                "l1_code": "801780.SI",
                "l1_name": "银行",
                "l2_code": "801783.SI",
                "l2_name": "股份制银行Ⅱ",
                "l3_code": "857831.SI",
                "l3_name": "股份制银行Ⅲ",
                "ts_code": "000001.SZ",
                "name": "平安银行",
                "in_date": "19910403",
                "out_date": None,
                "is_new": "Y",
            }
        ]
    )

    memberships = _stock_industry_memberships_from_frame(frame, source="SW2021")

    assert memberships[0].symbol == "000001.SZ"
    assert memberships[0].level1_name == "银行"
    assert memberships[0].out_date is None
    assert memberships[0].is_new is True
    assert memberships[0].active_on(date(2024, 1, 2)) is True


def test_tushare_tradability_frames_map_limit_and_suspend_state() -> None:
    statuses = _tradability_statuses_from_frames(
        symbol="000001.SZ",
        limit_frame=pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "20240102", "up_limit": 11.0, "down_limit": 9.0},
                {"ts_code": "000001.SZ", "trade_date": "20240103", "up_limit": 12.1, "down_limit": 9.9},
            ]
        ),
        close_frame=pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "20240102", "close": 11.0},
                {"ts_code": "000001.SZ", "trade_date": "20240103", "close": 9.9},
            ]
        ),
        suspend_frame=pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20240104",
                    "suspend_timing": "全天停牌",
                    "suspend_type": "停牌",
                },
            ]
        ),
    )

    assert [status.trade_date for status in statuses] == [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
    ]
    assert statuses[0].is_limit_up is True
    assert statuses[1].is_limit_down is True
    assert statuses[2].is_suspended is True


def test_tushare_rate_limit_config_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATT_TUSHARE_REQUESTS_PER_MINUTE", "45")
    monkeypatch.setenv("ATT_TUSHARE_RETRY_ATTEMPTS", "7")
    monkeypatch.setenv("ATT_TUSHARE_DATE_WINDOW_DAYS", "31")

    config = TushareRateLimitConfig.from_env()

    assert config.requests_per_minute == 45
    assert config.retry_attempts == 7
    assert config.date_window_days == 31


def test_tushare_date_window_helpers_cover_full_range() -> None:
    assert list(_date_windows(date(2024, 1, 1), date(2024, 1, 5), window_days=2)) == [
        (date(2024, 1, 1), date(2024, 1, 2)),
        (date(2024, 1, 3), date(2024, 1, 4)),
        (date(2024, 1, 5), date(2024, 1, 5)),
    ]
    assert list(_month_windows(date(2024, 1, 15), date(2024, 3, 5))) == [
        (date(2024, 1, 15), date(2024, 1, 31)),
        (date(2024, 2, 1), date(2024, 2, 29)),
        (date(2024, 3, 1), date(2024, 3, 5)),
    ]


def test_read_tushare_token_rejects_placeholder(tmp_path: Path) -> None:
    token_file = tmp_path / "tushare_token.txt"
    token_file.write_text("paste-your-tushare-token-here\n", encoding="utf-8")

    with pytest.raises(ValueError, match="token"):
        read_tushare_token(token_file)


def test_read_tushare_token_trims_whitespace(tmp_path: Path) -> None:
    token_file = tmp_path / "tushare_token.txt"
    token_file.write_text("  abc123  \n", encoding="utf-8")

    assert read_tushare_token(token_file) == "abc123"
