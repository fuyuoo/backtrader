"""Tushare data provider."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from attbacktrader.data.adjustments import DEFAULT_PRICE_ADJUSTMENT
from attbacktrader.data import (
    DailyBar,
    IndexBar,
    IndexConstituent,
    ShenwanIndustryClassification,
    StockIndustryMembership,
    TradabilityStatus,
)


DEFAULT_TUSHARE_TOKEN_FILE = Path(".secrets/tushare_token.txt")
BAR_FIELDS = "ts_code,trade_date,open,high,low,close,vol"
INDEX_FIELDS = "ts_code,trade_date,open,high,low,close,vol,amount"
LIMIT_FIELDS = "ts_code,trade_date,up_limit,down_limit"
RAW_CLOSE_FIELDS = "ts_code,trade_date,close"
SUSPEND_FIELDS = "ts_code,trade_date,suspend_timing,suspend_type"
INDEX_WEIGHT_FIELDS = "index_code,con_code,trade_date,weight"
STOCK_BASIC_FIELDS = "ts_code,name"
REFERENCE_STOCK_BASIC_FIELDS = "ts_code,name,exchange,market,list_date"
REFERENCE_DAILY_FIELDS = "ts_code,trade_date,open,high,low,close,vol,amount"
REFERENCE_DAILY_BASIC_FIELDS = (
    "ts_code,trade_date,turnover_rate,volume_ratio,pe,pe_ttm,pb,total_mv,circ_mv"
)
NAMECHANGE_FIELDS = "ts_code,name,start_date,end_date,change_reason"
DEFAULT_TUSHARE_REQUESTS_PER_MINUTE = 180.0
DEFAULT_TUSHARE_RETRY_ATTEMPTS = 5
DEFAULT_TUSHARE_RETRY_BASE_SECONDS = 2.0
DEFAULT_TUSHARE_RETRY_MAX_SECONDS = 60.0
DEFAULT_TUSHARE_DATE_WINDOW_DAYS = 366
TUSHARE_REQUESTS_PER_MINUTE_ENV = "ATT_TUSHARE_REQUESTS_PER_MINUTE"
TUSHARE_RETRY_ATTEMPTS_ENV = "ATT_TUSHARE_RETRY_ATTEMPTS"
TUSHARE_DATE_WINDOW_DAYS_ENV = "ATT_TUSHARE_DATE_WINDOW_DAYS"


def read_tushare_token(path: str | Path = DEFAULT_TUSHARE_TOKEN_FILE) -> str:
    token_path = Path(path)
    token = token_path.read_text(encoding="utf-8").strip()
    if not token or token == "paste-your-tushare-token-here":
        raise ValueError(f"Tushare token is missing in {token_path}")
    return token


@dataclass(frozen=True)
class TushareRateLimitConfig:
    """Rate limit and retry settings for Tushare Pro calls."""

    requests_per_minute: float = DEFAULT_TUSHARE_REQUESTS_PER_MINUTE
    retry_attempts: int = DEFAULT_TUSHARE_RETRY_ATTEMPTS
    retry_base_seconds: float = DEFAULT_TUSHARE_RETRY_BASE_SECONDS
    retry_max_seconds: float = DEFAULT_TUSHARE_RETRY_MAX_SECONDS
    date_window_days: int = DEFAULT_TUSHARE_DATE_WINDOW_DAYS

    def __post_init__(self) -> None:
        if self.requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be positive")
        if self.retry_attempts < 0:
            raise ValueError("retry_attempts must be non-negative")
        if self.retry_base_seconds < 0:
            raise ValueError("retry_base_seconds must be non-negative")
        if self.retry_max_seconds < self.retry_base_seconds:
            raise ValueError("retry_max_seconds must be greater than or equal to retry_base_seconds")
        if self.date_window_days <= 0:
            raise ValueError("date_window_days must be positive")

    @classmethod
    def from_env(cls) -> "TushareRateLimitConfig":
        return cls(
            requests_per_minute=_env_float(
                TUSHARE_REQUESTS_PER_MINUTE_ENV,
                DEFAULT_TUSHARE_REQUESTS_PER_MINUTE,
            ),
            retry_attempts=_env_int(
                TUSHARE_RETRY_ATTEMPTS_ENV,
                DEFAULT_TUSHARE_RETRY_ATTEMPTS,
            ),
            date_window_days=_env_int(
                TUSHARE_DATE_WINDOW_DAYS_ENV,
                DEFAULT_TUSHARE_DATE_WINDOW_DAYS,
            ),
        )

    @classmethod
    def from_overrides(
        cls,
        *,
        requests_per_minute: float | None = None,
        retry_attempts: int | None = None,
        date_window_days: int | None = None,
    ) -> "TushareRateLimitConfig":
        base = cls.from_env()
        return cls(
            requests_per_minute=base.requests_per_minute
            if requests_per_minute is None
            else requests_per_minute,
            retry_attempts=base.retry_attempts if retry_attempts is None else retry_attempts,
            retry_base_seconds=base.retry_base_seconds,
            retry_max_seconds=base.retry_max_seconds,
            date_window_days=base.date_window_days if date_window_days is None else date_window_days,
        )


class TushareProvider:
    """Fetch market data from the current Tushare provider."""

    def __init__(
        self,
        token: str,
        *,
        rate_limit: TushareRateLimitConfig | None = None,
        sleeper: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if not token:
            raise ValueError("token cannot be empty")

        try:
            import tushare as ts
        except ImportError as exc:
            raise RuntimeError("tushare is required to use TushareProvider") from exc

        self._ts: Any = ts
        self._pro: Any = ts.pro_api(token)
        self._rate_limit = rate_limit or TushareRateLimitConfig.from_env()
        self._sleeper = sleeper or time.sleep
        self._clock = clock or time.monotonic
        self._next_request_at: float | None = None

    def fetch_daily_bars(
        self,
        *,
        symbol: str,
        start_date: date,
        end_date: date,
        adjustment: str = DEFAULT_PRICE_ADJUSTMENT,
    ) -> tuple[DailyBar, ...]:
        """Fetch A-share daily bars.

        The first version stores and backtests front-adjusted (qfq) prices by default.
        """
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")

        frame = self._call_tushare(
            self._ts.pro_bar,
            api_name="pro_bar",
            ts_code=symbol,
            api=self._pro,
            start_date=_format_tushare_date(start_date),
            end_date=_format_tushare_date(end_date),
            freq="D",
            asset="E",
            adj=adjustment,
            fields=BAR_FIELDS,
        )

        if frame is None or frame.empty:
            return ()

        return _daily_bars_from_frame(frame)

    def fetch_index_daily_bars(self, *, symbol: str, start_date: date, end_date: date) -> tuple[IndexBar, ...]:
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")

        frame = self._fetch_date_windowed(
            self._pro.index_daily,
            api_name="index_daily",
            start_date=start_date,
            end_date=end_date,
            ts_code=symbol,
            fields=INDEX_FIELDS,
        )

        if frame is None or frame.empty:
            return ()

        return _index_bars_from_frame(frame)

    def fetch_industry_index_daily_bars(
        self,
        *,
        symbol: str,
        start_date: date,
        end_date: date,
        source: str = "SW2021",
    ) -> tuple[IndexBar, ...]:
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")

        frame = self._fetch_date_windowed(
            self._pro.sw_daily,
            api_name="sw_daily",
            start_date=start_date,
            end_date=end_date,
            ts_code=symbol,
            fields=INDEX_FIELDS,
        )

        if frame is None or frame.empty:
            return ()

        return _index_bars_from_frame(frame)

    def fetch_index_constituents(
        self,
        *,
        index_symbol: str,
        start_date: date,
        end_date: date,
    ) -> tuple[IndexConstituent, ...]:
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")

        frame = self._fetch_month_windowed(
            self._pro.index_weight,
            api_name="index_weight",
            start_date=start_date,
            end_date=end_date,
            index_code=index_symbol,
            fields=INDEX_WEIGHT_FIELDS,
        )
        if frame is None or frame.empty:
            return ()
        return _index_constituents_from_frame(frame, source_index=index_symbol)

    def fetch_stock_names(self) -> dict[str, str]:
        frame = self._call_tushare(self._pro.stock_basic, api_name="stock_basic", fields=STOCK_BASIC_FIELDS)
        if frame is None or frame.empty:
            return {}
        return _stock_names_from_frame(frame)

    def fetch_attribution_reference_frame(self, *, start_date: date, end_date: date) -> Any:
        """Fetch all-A daily rows needed by attribution reference preparation."""

        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")

        daily_frame = self._fetch_date_windowed(
            self._pro.daily,
            api_name="daily",
            start_date=start_date,
            end_date=end_date,
            fields=REFERENCE_DAILY_FIELDS,
        )
        daily_basic_frame = self._fetch_trade_date_windowed(
            self._pro.daily_basic,
            api_name="daily_basic",
            start_date=start_date,
            end_date=end_date,
            fields=REFERENCE_DAILY_BASIC_FIELDS,
        )
        stock_basic_frame = self._call_tushare(
            self._pro.stock_basic,
            api_name="stock_basic",
            fields=REFERENCE_STOCK_BASIC_FIELDS,
        )
        suspend_frame = self._fetch_date_windowed(
            self._pro.suspend_d,
            api_name="suspend_d",
            start_date=start_date,
            end_date=end_date,
            fields=SUSPEND_FIELDS,
        )
        namechange_frame = self._call_tushare(
            self._pro.namechange,
            api_name="namechange",
            fields=NAMECHANGE_FIELDS,
        )
        return _attribution_reference_frame_from_frames(
            daily_frame=daily_frame,
            daily_basic_frame=daily_basic_frame,
            stock_basic_frame=stock_basic_frame,
            suspend_frame=suspend_frame,
            namechange_frame=namechange_frame,
        )

    def fetch_shenwan_industry_classifications(
        self,
        *,
        source: str = "SW2021",
    ) -> tuple[ShenwanIndustryClassification, ...]:
        frame = self._call_tushare(self._pro.index_classify, api_name="index_classify", src=source)
        if frame is None or frame.empty:
            return ()

        return _shenwan_classifications_from_frame(frame)

    def fetch_stock_industry_memberships(
        self,
        *,
        symbol: str,
        source: str = "SW2021",
    ) -> tuple[StockIndustryMembership, ...]:
        frame = self._call_tushare(self._pro.index_member_all, api_name="index_member_all", ts_code=symbol)
        if frame is None or frame.empty:
            return ()

        return _stock_industry_memberships_from_frame(frame, source=source)

    def fetch_tradability_statuses(
        self,
        *,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> tuple[TradabilityStatus, ...]:
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")

        limit_frame = self._fetch_date_windowed(
            self._pro.stk_limit,
            api_name="stk_limit",
            start_date=start_date,
            end_date=end_date,
            ts_code=symbol,
            fields=LIMIT_FIELDS,
        )
        close_frame = self._fetch_date_windowed(
            self._pro.daily,
            api_name="daily",
            start_date=start_date,
            end_date=end_date,
            ts_code=symbol,
            fields=RAW_CLOSE_FIELDS,
        )
        suspend_frame = self._fetch_date_windowed(
            self._pro.suspend_d,
            api_name="suspend_d",
            start_date=start_date,
            end_date=end_date,
            ts_code=symbol,
            fields=SUSPEND_FIELDS,
        )

        return _tradability_statuses_from_frames(
            symbol=symbol,
            limit_frame=limit_frame,
            close_frame=close_frame,
            suspend_frame=suspend_frame,
        )

    def _fetch_date_windowed(
        self,
        call: Callable[..., Any],
        *,
        api_name: str,
        start_date: date,
        end_date: date,
        **kwargs: Any,
    ) -> Any:
        frames = [
            self._call_tushare(
                call,
                api_name=api_name,
                start_date=_format_tushare_date(window_start),
                end_date=_format_tushare_date(window_end),
                **kwargs,
            )
            for window_start, window_end in _date_windows(
                start_date,
                end_date,
                window_days=self._rate_limit.date_window_days,
            )
        ]
        return _concat_frames(frames)

    def _fetch_month_windowed(
        self,
        call: Callable[..., Any],
        *,
        api_name: str,
        start_date: date,
        end_date: date,
        **kwargs: Any,
    ) -> Any:
        frames = [
            self._call_tushare(
                call,
                api_name=api_name,
                start_date=_format_tushare_date(window_start),
                end_date=_format_tushare_date(window_end),
                **kwargs,
            )
            for window_start, window_end in _month_windows(start_date, end_date)
        ]
        return _concat_frames(frames)

    def _fetch_trade_date_windowed(
        self,
        call: Callable[..., Any],
        *,
        api_name: str,
        start_date: date,
        end_date: date,
        **kwargs: Any,
    ) -> Any:
        frames = [
            self._call_tushare(
                call,
                api_name=api_name,
                start_date=_format_tushare_date(window_start),
                end_date=_format_tushare_date(window_end),
                **kwargs,
            )
            for window_start, window_end in _date_windows(
                start_date,
                end_date,
                window_days=self._rate_limit.date_window_days,
            )
        ]
        return _concat_frames(frames)

    def _call_tushare(self, call: Callable[..., Any], *, api_name: str, **kwargs: Any) -> Any:
        attempt = 0
        while True:
            self._wait_for_request_slot()
            try:
                return call(**kwargs)
            except Exception as exc:
                if attempt >= self._rate_limit.retry_attempts or not _is_retryable_tushare_error(exc):
                    raise RuntimeError(f"Tushare API {api_name} failed") from exc
                self._sleeper(_retry_delay_seconds(attempt, self._rate_limit))
                attempt += 1

    def _wait_for_request_slot(self) -> None:
        interval_seconds = 60.0 / self._rate_limit.requests_per_minute
        now = self._clock()
        if self._next_request_at is not None and now < self._next_request_at:
            self._sleeper(self._next_request_at - now)
            now = self._clock()
        self._next_request_at = now + interval_seconds


def _daily_bars_from_frame(frame: Any) -> tuple[DailyBar, ...]:
    bars = [
        DailyBar(
            symbol=str(row.ts_code),
            trade_date=_parse_tushare_date(str(row.trade_date)),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.vol),
        )
        for row in frame.itertuples(index=False)
    ]

    return tuple(sorted(bars, key=lambda bar: bar.trade_date))


def _index_bars_from_frame(frame: Any) -> tuple[IndexBar, ...]:
    bars = []
    for row in frame.itertuples(index=False):
        open_price = float(row.open)
        high_price = float(row.high)
        low_price = float(row.low)
        close_price = float(row.close)
        # Tushare index feeds can report high/low that miss open/close by a
        # small rounding amount; keep IndexBar OHLC internally consistent.
        high_price = max(high_price, open_price, close_price)
        low_price = min(low_price, open_price, close_price)
        bars.append(
            IndexBar(
                symbol=str(row.ts_code),
                trade_date=_parse_tushare_date(str(row.trade_date)),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=float(row.vol),
                amount=float(row.amount),
            )
        )

    return tuple(sorted(bars, key=lambda bar: bar.trade_date))


def _index_constituents_from_frame(frame: Any, *, source_index: str) -> tuple[IndexConstituent, ...]:
    constituents = [
        IndexConstituent(
            symbol=str(row.con_code),
            source_index=str(getattr(row, "index_code", source_index)),
            trade_date=_parse_tushare_date(str(row.trade_date)),
            weight=_optional_float(row.weight),
        )
        for row in frame.itertuples(index=False)
    ]
    return tuple(sorted(constituents, key=lambda item: (item.source_index, item.trade_date, item.symbol)))


def _stock_names_from_frame(frame: Any) -> dict[str, str]:
    return {
        str(row.ts_code): str(row.name)
        for row in frame.itertuples(index=False)
    }


def _shenwan_classifications_from_frame(frame: Any) -> tuple[ShenwanIndustryClassification, ...]:
    classifications = [
        ShenwanIndustryClassification(
            index_code=str(row.index_code),
            industry_name=str(row.industry_name),
            level=_parse_shenwan_level(str(row.level)),
            industry_code=str(row.industry_code),
            parent_code=str(row.parent_code),
            source=str(row.src),
        )
        for row in frame.itertuples(index=False)
    ]

    return tuple(sorted(classifications, key=lambda item: (item.level, item.index_code)))


def _stock_industry_memberships_from_frame(frame: Any, *, source: str) -> tuple[StockIndustryMembership, ...]:
    memberships = [
        StockIndustryMembership(
            symbol=str(row.ts_code),
            stock_name=str(row.name),
            level1_code=str(row.l1_code),
            level1_name=str(row.l1_name),
            level2_code=str(row.l2_code),
            level2_name=str(row.l2_name),
            level3_code=str(row.l3_code),
            level3_name=str(row.l3_name),
            in_date=_parse_tushare_date(str(row.in_date)),
            out_date=_parse_optional_tushare_date(row.out_date),
            is_new=str(row.is_new).upper() == "Y",
            source=source,
        )
        for row in frame.itertuples(index=False)
    ]

    return tuple(sorted(memberships, key=lambda item: (item.symbol, item.in_date, item.level3_code)))


def _tradability_statuses_from_frames(
    *,
    symbol: str,
    limit_frame: Any,
    close_frame: Any,
    suspend_frame: Any,
) -> tuple[TradabilityStatus, ...]:
    limit_by_date = _limit_by_date(limit_frame)
    close_by_date = _close_by_date(close_frame)
    suspended_dates = _suspended_dates(suspend_frame)
    dates = sorted(set(limit_by_date) | set(close_by_date) | suspended_dates)

    statuses = []
    for trade_date in dates:
        up_limit, down_limit = limit_by_date.get(trade_date, (None, None))
        close = close_by_date.get(trade_date)
        statuses.append(
            TradabilityStatus(
                symbol=symbol,
                trade_date=trade_date,
                is_suspended=trade_date in suspended_dates,
                is_limit_up=_is_at_limit(close, up_limit, side="up"),
                is_limit_down=_is_at_limit(close, down_limit, side="down"),
                close=close,
                up_limit=up_limit,
                down_limit=down_limit,
            )
        )

    return tuple(statuses)


def _attribution_reference_frame_from_frames(
    *,
    daily_frame: Any,
    daily_basic_frame: Any,
    stock_basic_frame: Any,
    suspend_frame: Any,
    namechange_frame: Any,
) -> Any:
    import pandas as pd

    if daily_frame is None or daily_frame.empty:
        return pd.DataFrame()

    daily = daily_frame.copy()
    daily = daily.rename(columns={"ts_code": "symbol", "vol": "volume"})
    daily["trade_date"] = pd.to_datetime(daily["trade_date"], format="%Y%m%d").dt.date
    if daily_basic_frame is not None and not daily_basic_frame.empty:
        daily_basic = daily_basic_frame.copy().rename(columns={"ts_code": "symbol"})
        daily_basic["trade_date"] = pd.to_datetime(daily_basic["trade_date"], format="%Y%m%d").dt.date
        daily = daily.merge(daily_basic, on=["symbol", "trade_date"], how="left")

    if stock_basic_frame is not None and not stock_basic_frame.empty:
        stock_basic = stock_basic_frame.copy().rename(columns={"ts_code": "symbol"})
        if "list_date" in stock_basic:
            stock_basic["list_date"] = pd.to_datetime(stock_basic["list_date"], format="%Y%m%d", errors="coerce").dt.date
        daily = daily.merge(stock_basic, on="symbol", how="left")

    suspended = set()
    if suspend_frame is not None and not suspend_frame.empty:
        for row in suspend_frame.itertuples(index=False):
            suspended.add((str(row.ts_code), _parse_tushare_date(str(row.trade_date))))
    daily["is_suspended"] = [
        (str(row.symbol), row.trade_date) in suspended
        for row in daily.itertuples(index=False)
    ]
    daily["is_st"] = _historical_st_flags(daily, namechange_frame)
    daily["listing_trading_days"] = _listing_trading_days(daily)
    daily["is_tradable"] = True
    return daily.sort_values(["symbol", "trade_date"]).reset_index(drop=True)


def _historical_st_flags(daily: Any, namechange_frame: Any) -> list[bool]:
    if namechange_frame is None or namechange_frame.empty:
        return [False] * len(daily)

    intervals: dict[str, list[tuple[date, date | None, str]]] = {}
    for row in namechange_frame.itertuples(index=False):
        name = str(getattr(row, "name", "") or "")
        reason = str(getattr(row, "change_reason", "") or "")
        if "ST" not in name.upper() and "ST" not in reason.upper():
            continue
        symbol = str(row.ts_code)
        start = _parse_optional_tushare_date(getattr(row, "start_date", None))
        if start is None:
            continue
        end = _parse_optional_tushare_date(getattr(row, "end_date", None))
        intervals.setdefault(symbol, []).append((start, end, name))

    flags = []
    for row in daily.itertuples(index=False):
        trade_date = row.trade_date
        active = False
        for start, end, _name in intervals.get(str(row.symbol), ()):
            if start <= trade_date and (end is None or trade_date <= end):
                active = True
                break
        flags.append(active)
    return flags


def _listing_trading_days(daily: Any) -> list[int | None]:
    import pandas as pd

    if "list_date" not in daily.columns:
        return [None] * len(daily)
    values: list[int | None] = []
    for row in daily.itertuples(index=False):
        list_date = getattr(row, "list_date", None)
        trade_date = getattr(row, "trade_date", None)
        if list_date is None or trade_date is None or pd.isna(list_date):
            values.append(None)
            continue
        values.append(len(pd.bdate_range(start=list_date, end=trade_date)))
    return values


def _date_windows(start_date: date, end_date: date, *, window_days: int) -> Iterable[tuple[date, date]]:
    current = start_date
    while current <= end_date:
        window_end = min(end_date, current + timedelta(days=window_days - 1))
        yield current, window_end
        current = window_end + timedelta(days=1)


def _month_windows(start_date: date, end_date: date) -> Iterable[tuple[date, date]]:
    current = start_date
    while current <= end_date:
        if current.month == 12:
            next_month = date(current.year + 1, 1, 1)
        else:
            next_month = date(current.year, current.month + 1, 1)
        window_end = min(end_date, next_month - timedelta(days=1))
        yield current, window_end
        current = window_end + timedelta(days=1)


def _concat_frames(frames: Iterable[Any]) -> Any:
    non_empty_frames = [frame for frame in frames if frame is not None and not frame.empty]
    if not non_empty_frames:
        return None
    if len(non_empty_frames) == 1:
        return non_empty_frames[0]

    import pandas as pd

    return pd.concat(non_empty_frames, ignore_index=True)


def _retry_delay_seconds(attempt: int, config: TushareRateLimitConfig) -> float:
    if config.retry_base_seconds == 0:
        return 0.0
    return min(config.retry_max_seconds, config.retry_base_seconds * (2 ** attempt))


def _is_retryable_tushare_error(exc: Exception) -> bool:
    message = str(exc).lower()
    non_retryable_markers = (
        "积分不足",
        "没有权限",
        "无权限",
        "权限不足",
        "not permitted",
        "permission",
        "daily limit",
        "每天总量",
        "总量上限",
    )
    if any(marker in message for marker in non_retryable_markers):
        return False

    retryable_markers = (
        "每分钟",
        "频次",
        "太频繁",
        "rate limit",
        "too many",
        "timeout",
        "timed out",
        "connection",
        "temporarily",
        "502",
        "503",
        "504",
    )
    return any(marker in message for marker in retryable_markers)


def _env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    return float(raw_value)


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    return int(raw_value)


def _limit_by_date(frame: Any) -> dict[date, tuple[float | None, float | None]]:
    if frame is None or frame.empty:
        return {}

    return {
        _parse_tushare_date(str(row.trade_date)): (
            _optional_float(row.up_limit),
            _optional_float(row.down_limit),
        )
        for row in frame.itertuples(index=False)
    }


def _close_by_date(frame: Any) -> dict[date, float]:
    if frame is None or frame.empty:
        return {}

    return {
        _parse_tushare_date(str(row.trade_date)): float(row.close)
        for row in frame.itertuples(index=False)
    }


def _suspended_dates(frame: Any) -> set[date]:
    if frame is None or frame.empty:
        return set()

    return {
        _parse_tushare_date(str(row.trade_date))
        for row in frame.itertuples(index=False)
    }


def _is_at_limit(close: float | None, limit_price: float | None, *, side: str) -> bool:
    if close is None or limit_price is None:
        return False

    tolerance = 1e-6
    if side == "up":
        return close >= limit_price - tolerance
    return close <= limit_price + tolerance


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None

    text = str(value)
    if text in {"", "None", "NaT", "nan"}:
        return None

    return float(value)


def _format_tushare_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def _parse_tushare_date(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()


def _parse_optional_tushare_date(value: Any) -> date | None:
    if value is None:
        return None

    text = str(value)
    if text in {"", "None", "NaT", "nan"}:
        return None

    return _parse_tushare_date(text)


def _parse_shenwan_level(value: str) -> int:
    if value.startswith("L"):
        return int(value[1:])
    return int(value)
