"""Tushare data provider."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from attbacktrader.data.adjustments import DEFAULT_PRICE_ADJUSTMENT
from attbacktrader.data import (
    DailyBar,
    IndexBar,
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


def read_tushare_token(path: str | Path = DEFAULT_TUSHARE_TOKEN_FILE) -> str:
    token_path = Path(path)
    token = token_path.read_text(encoding="utf-8").strip()
    if not token or token == "paste-your-tushare-token-here":
        raise ValueError(f"Tushare token is missing in {token_path}")
    return token


class TushareProvider:
    """Fetch market data from the current Tushare provider."""

    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError("token cannot be empty")

        try:
            import tushare as ts
        except ImportError as exc:
            raise RuntimeError("tushare is required to use TushareProvider") from exc

        self._ts: Any = ts
        self._pro: Any = ts.pro_api(token)

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

        frame = self._ts.pro_bar(
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

        frame = self._pro.index_daily(
            ts_code=symbol,
            start_date=_format_tushare_date(start_date),
            end_date=_format_tushare_date(end_date),
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

        frame = self._pro.sw_daily(
            ts_code=symbol,
            start_date=_format_tushare_date(start_date),
            end_date=_format_tushare_date(end_date),
            fields=INDEX_FIELDS,
        )

        if frame is None or frame.empty:
            return ()

        return _index_bars_from_frame(frame)

    def fetch_shenwan_industry_classifications(
        self,
        *,
        source: str = "SW2021",
    ) -> tuple[ShenwanIndustryClassification, ...]:
        frame = self._pro.index_classify(src=source)
        if frame is None or frame.empty:
            return ()

        return _shenwan_classifications_from_frame(frame)

    def fetch_stock_industry_memberships(
        self,
        *,
        symbol: str,
        source: str = "SW2021",
    ) -> tuple[StockIndustryMembership, ...]:
        frame = self._pro.index_member_all(ts_code=symbol)
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

        start = _format_tushare_date(start_date)
        end = _format_tushare_date(end_date)
        limit_frame = self._pro.stk_limit(
            ts_code=symbol,
            start_date=start,
            end_date=end,
            fields=LIMIT_FIELDS,
        )
        close_frame = self._pro.daily(
            ts_code=symbol,
            start_date=start,
            end_date=end,
            fields=RAW_CLOSE_FIELDS,
        )
        suspend_frame = self._pro.suspend_d(
            ts_code=symbol,
            start_date=start,
            end_date=end,
            fields=SUSPEND_FIELDS,
        )

        return _tradability_statuses_from_frames(
            symbol=symbol,
            limit_frame=limit_frame,
            close_frame=close_frame,
            suspend_frame=suspend_frame,
        )


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
