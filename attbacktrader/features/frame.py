"""Reusable indicator frame for strategy and engine consumers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence

from attbacktrader.data import DailyBar, resample_daily_bars
from attbacktrader.features.indicators import (
    ATRValue,
    CCIValue,
    KDJValue,
    MACDValue,
    MAValue,
    RSIValue,
    calculate_atr,
    calculate_bollinger,
    calculate_cci,
    calculate_kdj,
    calculate_macd,
    calculate_rsi,
    calculate_sma,
)
from attbacktrader.features.registry import (
    DEFAULT_INDICATOR_NAMES,
    IndicatorRequirement,
    SUPPORTED_MA_PERIODS,
    boll_up_indicator_name,
    boll_up_indicator_params,
    indicator_period,
    indicator_names_for_timeframe,
    normalize_indicator_names,
    normalize_indicator_requirements,
)
from attbacktrader.features.snapshots import IndicatorSnapshot


@dataclass(frozen=True)
class IndicatorFrame:
    symbol: str
    kdj_by_key: Mapping[tuple[str, date], KDJValue] | None = None
    macd_by_key: Mapping[tuple[str, date], MACDValue] | None = None
    ma_by_key: Mapping[tuple[str, int, date], MAValue] | None = None
    rsi_by_key: Mapping[tuple[str, int, date], RSIValue] | None = None
    atr_by_key: Mapping[tuple[str, int, date], ATRValue] | None = None
    cci_by_key: Mapping[tuple[str, int, date], CCIValue] | None = None
    boll_up_by_key: Mapping[tuple[str, int, float, date], float] | None = None

    def kdj_at(self, trade_date: date, *, timeframe: str = "D") -> KDJValue:
        if self.kdj_by_key is None:
            raise KeyError(f"KDJ is missing for {self.symbol}")
        try:
            return self.kdj_by_key[(timeframe, trade_date)]
        except KeyError as exc:
            raise KeyError(f"KDJ {timeframe} is missing for {self.symbol} on {trade_date.isoformat()}") from exc

    def kdj_at_or_before(self, trade_date: date, *, timeframe: str = "D") -> KDJValue:
        if self.kdj_by_key is None:
            raise KeyError(f"KDJ is missing for {self.symbol}")
        aligned_date = _latest_available_date(self.kdj_by_key, timeframe=timeframe, trade_date=trade_date)
        return self.kdj_by_key[(timeframe, aligned_date)]

    def macd_at(self, trade_date: date, *, timeframe: str = "D") -> MACDValue:
        if self.macd_by_key is None:
            raise KeyError(f"MACD is missing for {self.symbol}")
        try:
            return self.macd_by_key[(timeframe, trade_date)]
        except KeyError as exc:
            raise KeyError(f"MACD {timeframe} is missing for {self.symbol} on {trade_date.isoformat()}") from exc

    def macd_at_or_before(self, trade_date: date, *, timeframe: str = "D") -> MACDValue:
        if self.macd_by_key is None:
            raise KeyError(f"MACD is missing for {self.symbol}")
        aligned_date = _latest_available_date(self.macd_by_key, timeframe=timeframe, trade_date=trade_date)
        return self.macd_by_key[(timeframe, aligned_date)]

    def ma_at(self, trade_date: date, *, period: int, timeframe: str = "D") -> MAValue:
        if self.ma_by_key is None:
            raise KeyError(f"MA is missing for {self.symbol}")
        try:
            return self.ma_by_key[(timeframe, period, trade_date)]
        except KeyError as exc:
            raise KeyError(
                f"MA{period} {timeframe} is missing for {self.symbol} on {trade_date.isoformat()}"
            ) from exc

    def ma_at_or_before(self, trade_date: date, *, period: int, timeframe: str = "D") -> MAValue:
        if self.ma_by_key is None:
            raise KeyError(f"MA is missing for {self.symbol}")
        aligned_date = _latest_available_date(self.ma_by_key, timeframe=timeframe, trade_date=trade_date, period=period)
        return self.ma_by_key[(timeframe, period, aligned_date)]

    def rsi_at(self, trade_date: date, *, period: int, timeframe: str = "D") -> RSIValue:
        if self.rsi_by_key is None:
            raise KeyError(f"RSI is missing for {self.symbol}")
        try:
            return self.rsi_by_key[(timeframe, period, trade_date)]
        except KeyError as exc:
            raise KeyError(
                f"RSI{period} {timeframe} is missing for {self.symbol} on {trade_date.isoformat()}"
            ) from exc

    def rsi_at_or_before(self, trade_date: date, *, period: int, timeframe: str = "D") -> RSIValue:
        if self.rsi_by_key is None:
            raise KeyError(f"RSI is missing for {self.symbol}")
        aligned_date = _latest_available_date(self.rsi_by_key, timeframe=timeframe, trade_date=trade_date, period=period)
        return self.rsi_by_key[(timeframe, period, aligned_date)]

    def atr_at(self, trade_date: date, *, period: int, timeframe: str = "D") -> ATRValue:
        if self.atr_by_key is None:
            raise KeyError(f"ATR is missing for {self.symbol}")
        try:
            return self.atr_by_key[(timeframe, period, trade_date)]
        except KeyError as exc:
            raise KeyError(
                f"ATR{period} {timeframe} is missing for {self.symbol} on {trade_date.isoformat()}"
            ) from exc

    def atr_at_or_before(self, trade_date: date, *, period: int, timeframe: str = "D") -> ATRValue:
        if self.atr_by_key is None:
            raise KeyError(f"ATR is missing for {self.symbol}")
        aligned_date = _latest_available_date(self.atr_by_key, timeframe=timeframe, trade_date=trade_date, period=period)
        return self.atr_by_key[(timeframe, period, aligned_date)]

    def cci_at(self, trade_date: date, *, period: int, timeframe: str = "D") -> CCIValue:
        if self.cci_by_key is None:
            raise KeyError(f"CCI is missing for {self.symbol}")
        try:
            return self.cci_by_key[(timeframe, period, trade_date)]
        except KeyError as exc:
            raise KeyError(
                f"CCI{period} {timeframe} is missing for {self.symbol} on {trade_date.isoformat()}"
            ) from exc

    def cci_at_or_before(self, trade_date: date, *, period: int, timeframe: str = "D") -> CCIValue:
        if self.cci_by_key is None:
            raise KeyError(f"CCI is missing for {self.symbol}")
        aligned_date = _latest_available_date(self.cci_by_key, timeframe=timeframe, trade_date=trade_date, period=period)
        return self.cci_by_key[(timeframe, period, aligned_date)]

    def boll_up_at(self, trade_date: date, *, period: int, devfactor: float, timeframe: str = "D") -> float:
        if self.boll_up_by_key is None:
            raise KeyError(f"BOLL_UP is missing for {self.symbol}")
        try:
            return self.boll_up_by_key[(timeframe, period, float(devfactor), trade_date)]
        except KeyError as exc:
            raise KeyError(
                f"BOLL_UP{period}_{devfactor:g} {timeframe} is missing for {self.symbol} on {trade_date.isoformat()}"
            ) from exc

    def boll_up_at_or_before(
        self,
        trade_date: date,
        *,
        period: int,
        devfactor: float,
        timeframe: str = "D",
    ) -> float:
        if self.boll_up_by_key is None:
            raise KeyError(f"BOLL_UP is missing for {self.symbol}")
        aligned_date = _latest_available_date(
            self.boll_up_by_key,
            timeframe=timeframe,
            trade_date=trade_date,
            period=period,
        )
        return self.boll_up_by_key[(timeframe, period, float(devfactor), aligned_date)]

    def indicator_date(self, name: str, trade_date: date, *, timeframe: str = "D") -> date:
        period = indicator_period(name)
        if name == "kdj":
            values_by_key = self.kdj_by_key
        elif name == "macd":
            values_by_key = self.macd_by_key
        elif name.startswith("ma"):
            values_by_key = self.ma_by_key
        elif name.startswith("rsi"):
            values_by_key = self.rsi_by_key
        elif name.startswith("atr"):
            values_by_key = self.atr_by_key
        elif name.startswith("cci"):
            values_by_key = self.cci_by_key
        elif name.startswith("boll_up"):
            values_by_key = self.boll_up_by_key
        else:
            raise ValueError(f"unsupported indicator: {name}")

        if values_by_key is None:
            raise KeyError(f"{name} is missing for {self.symbol}")
        return _latest_available_date(values_by_key, timeframe=timeframe, trade_date=trade_date, period=period)


def build_indicator_frame(
    bars: Sequence[DailyBar],
    *,
    indicator_names: Sequence[str] = DEFAULT_INDICATOR_NAMES,
    timeframe: str = "D",
) -> IndicatorFrame:
    if not bars:
        raise ValueError("bars cannot be empty")

    indicator_names = normalize_indicator_names(indicator_names)
    ordered_bars = tuple(sorted(bars, key=lambda bar: bar.trade_date))
    symbol = ordered_bars[0].symbol
    if any(bar.symbol != symbol for bar in ordered_bars):
        raise ValueError("build_indicator_frame requires one symbol")

    if "kdj" in indicator_names:
        kdj_values = calculate_kdj(
            [bar.high for bar in ordered_bars],
            [bar.low for bar in ordered_bars],
            [bar.close for bar in ordered_bars],
        )
        kdj_by_key = {(timeframe, bar.trade_date): value for bar, value in zip(ordered_bars, kdj_values)}
    else:
        kdj_by_key = None

    if "macd" in indicator_names:
        macd_values = calculate_macd([bar.close for bar in ordered_bars])
        macd_by_key = {(timeframe, bar.trade_date): value for bar, value in zip(ordered_bars, macd_values)}
    else:
        macd_by_key = None

    ma_by_key: dict[tuple[str, int, date], MAValue] = {}
    for period in _indicator_periods(indicator_names, prefix="ma"):
        ma_values = calculate_sma([bar.close for bar in ordered_bars], period=period)
        ma_by_key.update(
            {
                (timeframe, period, bar.trade_date): value
                for bar, value in zip(ordered_bars, ma_values)
                if value is not None
            }
        )

    rsi_by_key: dict[tuple[str, int, date], RSIValue] = {}
    for period in _indicator_periods(indicator_names, prefix="rsi"):
        rsi_values = calculate_rsi([bar.close for bar in ordered_bars], period=period)
        rsi_by_key.update(
            {
                (timeframe, period, bar.trade_date): value
                for bar, value in zip(ordered_bars, rsi_values)
                if value is not None
            }
        )

    atr_by_key: dict[tuple[str, int, date], ATRValue] = {}
    for period in _indicator_periods(indicator_names, prefix="atr"):
        atr_values = calculate_atr(
            [bar.high for bar in ordered_bars],
            [bar.low for bar in ordered_bars],
            [bar.close for bar in ordered_bars],
            period=period,
        )
        atr_by_key.update(
            {
                (timeframe, period, bar.trade_date): value
                for bar, value in zip(ordered_bars, atr_values)
                if value is not None
            }
        )

    cci_by_key: dict[tuple[str, int, date], CCIValue] = {}
    for period in _indicator_periods(indicator_names, prefix="cci"):
        cci_values = calculate_cci(
            [bar.high for bar in ordered_bars],
            [bar.low for bar in ordered_bars],
            [bar.close for bar in ordered_bars],
            period=period,
        )
        cci_by_key.update(
            {
                (timeframe, period, bar.trade_date): value
                for bar, value in zip(ordered_bars, cci_values)
                if value is not None
            }
        )

    boll_up_by_key: dict[tuple[str, int, float, date], float] = {}
    for period, devfactor in _boll_up_specs(indicator_names):
        bollinger_values = calculate_bollinger(
            [bar.close for bar in ordered_bars],
            period=period,
            devfactor=devfactor,
        )
        boll_up_by_key.update(
            {
                (timeframe, period, float(devfactor), bar.trade_date): value.upper
                for bar, value in zip(ordered_bars, bollinger_values)
                if value is not None
            }
        )

    return IndicatorFrame(
        symbol=symbol,
        kdj_by_key=kdj_by_key,
        macd_by_key=macd_by_key,
        ma_by_key=ma_by_key or None,
        rsi_by_key=rsi_by_key or None,
        atr_by_key=atr_by_key or None,
        cci_by_key=cci_by_key or None,
        boll_up_by_key=boll_up_by_key or None,
    )


def build_indicator_snapshots(
    bars: Sequence[DailyBar],
    *,
    indicator_names: Sequence[str] = DEFAULT_INDICATOR_NAMES,
    timeframe: str = "D",
) -> tuple[IndicatorSnapshot, ...]:
    indicator_names = normalize_indicator_names(indicator_names)
    frame = build_indicator_frame(bars, indicator_names=indicator_names, timeframe=timeframe)
    ordered_bars = tuple(sorted(bars, key=lambda bar: bar.trade_date))
    return tuple(
        IndicatorSnapshot(
            symbol=bar.symbol,
            trade_date=bar.trade_date,
            timeframe=timeframe,
            **_indicator_snapshot_values(frame, bar.trade_date, indicator_names, timeframe=timeframe),
        )
        for bar in ordered_bars
    )


def build_indicator_snapshots_for_requirements(
    bars: Sequence[DailyBar],
    *,
    indicator_requirements: Sequence[IndicatorRequirement | tuple[str, str] | str],
) -> tuple[IndicatorSnapshot, ...]:
    requirements = normalize_indicator_requirements(indicator_requirements)
    snapshots: list[IndicatorSnapshot] = []

    for timeframe in ("D", "W", "M"):
        indicator_names = indicator_names_for_timeframe(requirements, timeframe=timeframe)
        if not indicator_names:
            continue
        timeframe_bars = tuple(bars) if timeframe == "D" else resample_daily_bars(bars, frequency=timeframe)
        snapshots.extend(
            build_indicator_snapshots(
                timeframe_bars,
                indicator_names=indicator_names,
                timeframe=timeframe,
            )
        )

    return tuple(sorted(snapshots, key=lambda snapshot: (snapshot.symbol, snapshot.timeframe, snapshot.trade_date)))


def indicator_frame_from_snapshots(snapshots: Sequence[IndicatorSnapshot]) -> IndicatorFrame:
    if not snapshots:
        raise ValueError("indicator snapshots cannot be empty")

    ordered_snapshots = tuple(sorted(snapshots, key=lambda snapshot: snapshot.trade_date))
    symbol = ordered_snapshots[0].symbol
    if any(snapshot.symbol != symbol for snapshot in ordered_snapshots):
        raise ValueError("indicator_frame_from_snapshots requires one symbol")

    return IndicatorFrame(
        symbol=symbol,
        kdj_by_key=(
            {
                (snapshot.timeframe, snapshot.trade_date): snapshot.kdj
                for snapshot in ordered_snapshots
                if snapshot.has_indicator("kdj")
            }
            if any(snapshot.has_indicator("kdj") for snapshot in ordered_snapshots)
            else None
        ),
        macd_by_key=(
            {
                (snapshot.timeframe, snapshot.trade_date): snapshot.macd
                for snapshot in ordered_snapshots
                if snapshot.has_indicator("macd")
            }
            if any(snapshot.has_indicator("macd") for snapshot in ordered_snapshots)
            else None
        ),
        ma_by_key=(
            _ma_values_from_snapshots(ordered_snapshots)
            if any(
                snapshot.has_indicator(f"ma{period}")
                for period in SUPPORTED_MA_PERIODS
                for snapshot in ordered_snapshots
            )
            else None
        ),
        rsi_by_key=(
            {
                (snapshot.timeframe, 14, snapshot.trade_date): snapshot.rsi(14)
                for snapshot in ordered_snapshots
                if snapshot.has_indicator("rsi14")
            }
            if any(snapshot.has_indicator("rsi14") for snapshot in ordered_snapshots)
            else None
        ),
        atr_by_key=(
            {
                (snapshot.timeframe, 14, snapshot.trade_date): snapshot.atr(14)
                for snapshot in ordered_snapshots
                if snapshot.has_indicator("atr14")
            }
            if any(snapshot.has_indicator("atr14") for snapshot in ordered_snapshots)
            else None
        ),
        cci_by_key=(
            {
                (snapshot.timeframe, 14, snapshot.trade_date): snapshot.cci(14)
                for snapshot in ordered_snapshots
                if snapshot.has_indicator("cci14")
            }
            if any(snapshot.has_indicator("cci14") for snapshot in ordered_snapshots)
            else None
        ),
        boll_up_by_key=(
            {
                (snapshot.timeframe, 20, 2.0, snapshot.trade_date): float(snapshot.boll_up20_2)
                for snapshot in ordered_snapshots
                if snapshot.has_indicator("boll_up20_2")
            }
            if any(snapshot.has_indicator("boll_up20_2") for snapshot in ordered_snapshots)
            else None
        ),
    )


def indicator_snapshots_from_frame(
    frame: IndicatorFrame,
    bars: Sequence[DailyBar],
    *,
    indicator_names: Sequence[str] = DEFAULT_INDICATOR_NAMES,
    timeframe: str = "D",
) -> tuple[IndicatorSnapshot, ...]:
    indicator_names = normalize_indicator_names(indicator_names)
    ordered_bars = tuple(sorted(bars, key=lambda bar: bar.trade_date))
    return tuple(
        IndicatorSnapshot(
            symbol=bar.symbol,
            trade_date=bar.trade_date,
            timeframe=timeframe,
            **_indicator_snapshot_values(frame, bar.trade_date, indicator_names, timeframe=timeframe),
        )
        for bar in ordered_bars
    )


def indicator_snapshots_from_frame_for_requirements(
    frame: IndicatorFrame,
    bars: Sequence[DailyBar],
    *,
    indicator_requirements: Sequence[IndicatorRequirement | tuple[str, str] | str],
) -> tuple[IndicatorSnapshot, ...]:
    requirements = normalize_indicator_requirements(indicator_requirements)
    snapshots: list[IndicatorSnapshot] = []

    for timeframe in ("D", "W", "M"):
        indicator_names = indicator_names_for_timeframe(requirements, timeframe=timeframe)
        if not indicator_names:
            continue
        timeframe_bars = tuple(bars) if timeframe == "D" else resample_daily_bars(bars, frequency=timeframe)
        snapshots.extend(
            indicator_snapshots_from_frame(
                frame,
                timeframe_bars,
                indicator_names=indicator_names,
                timeframe=timeframe,
            )
        )

    return tuple(sorted(snapshots, key=lambda snapshot: (snapshot.symbol, snapshot.timeframe, snapshot.trade_date)))


def _indicator_snapshot_values(
    frame: IndicatorFrame,
    trade_date: date,
    indicator_names: Sequence[str],
    *,
    timeframe: str,
) -> dict[str, float]:
    values: dict[str, float] = {}
    if "kdj" in indicator_names:
        kdj = frame.kdj_at(trade_date, timeframe=timeframe)
        values.update({"kdj_k": kdj.k, "kdj_d": kdj.d, "kdj_j": kdj.j})
    if "macd" in indicator_names:
        macd = frame.macd_at(trade_date, timeframe=timeframe)
        values.update(
            {
                "macd_line": macd.line,
                "macd_signal": macd.signal,
                "macd_histogram": macd.histogram,
            }
        )
    for period in _indicator_periods(indicator_names, prefix="ma"):
        try:
            values[f"ma{period}"] = frame.ma_at(trade_date, period=period, timeframe=timeframe).value
        except KeyError:
            pass
    for period in _indicator_periods(indicator_names, prefix="rsi"):
        try:
            values[f"rsi{period}"] = frame.rsi_at(trade_date, period=period, timeframe=timeframe).value
        except KeyError:
            pass
    for period in _indicator_periods(indicator_names, prefix="atr"):
        try:
            values[f"atr{period}"] = frame.atr_at(trade_date, period=period, timeframe=timeframe).value
        except KeyError:
            pass
    for period in _indicator_periods(indicator_names, prefix="cci"):
        try:
            values[f"cci{period}"] = frame.cci_at(trade_date, period=period, timeframe=timeframe).value
        except KeyError:
            pass
    for period, devfactor in _boll_up_specs(indicator_names):
        try:
            values[boll_up_indicator_name(period, devfactor)] = frame.boll_up_at(
                trade_date,
                period=period,
                devfactor=devfactor,
                timeframe=timeframe,
            )
        except KeyError:
            pass
    return values


def _latest_available_date(
    values_by_key: Mapping[tuple, object],
    *,
    timeframe: str,
    trade_date: date,
    period: int | None = None,
) -> date:
    available_dates = [
        key[-1]
        for key in values_by_key
        if key[0] == timeframe
        and (period is None or (len(key) > 2 and key[1] == period))
        and key[-1] <= trade_date
    ]
    if not available_dates:
        raise KeyError(f"{timeframe} indicator is missing on or before {trade_date.isoformat()}")
    return max(available_dates)


def _indicator_periods(indicator_names: Sequence[str], *, prefix: str) -> tuple[int, ...]:
    return tuple(
        sorted(
            int(name.removeprefix(prefix))
            for name in indicator_names
            if name.startswith(prefix) and name.removeprefix(prefix).isdigit()
        )
    )


def _boll_up_specs(indicator_names: Sequence[str]) -> tuple[tuple[int, float], ...]:
    return tuple(
        sorted(
            boll_up_indicator_params(name)
            for name in indicator_names
            if name.startswith("boll_up")
        )
    )


def _ma_values_from_snapshots(snapshots: Sequence[IndicatorSnapshot]) -> dict[tuple[str, int, date], MAValue]:
    values: dict[tuple[str, int, date], MAValue] = {}
    for snapshot in snapshots:
        for period in SUPPORTED_MA_PERIODS:
            if snapshot.has_indicator(f"ma{period}"):
                values[(snapshot.timeframe, period, snapshot.trade_date)] = snapshot.ma(period)
    return values
