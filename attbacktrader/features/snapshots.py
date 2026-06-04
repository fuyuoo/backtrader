"""Indicator snapshots and storage helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from attbacktrader.data.adjustments import DEFAULT_PRICE_ADJUSTMENT
from attbacktrader.features.indicators import ATRValue, KDJValue, MACDValue, MAValue, RSIValue
from attbacktrader.features.registry import DEFAULT_INDICATOR_NAMES, SUPPORTED_INDICATOR_TIMEFRAMES, indicator_set_name


@dataclass(frozen=True)
class IndicatorSnapshot:
    symbol: str
    trade_date: date
    timeframe: str = "D"
    kdj_k: float | None = None
    kdj_d: float | None = None
    kdj_j: float | None = None
    macd_line: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    ma20: float | None = None
    ma25: float | None = None
    ma60: float | None = None
    rsi14: float | None = None
    atr14: float | None = None

    @property
    def kdj(self) -> KDJValue:
        if self.kdj_k is None or self.kdj_d is None or self.kdj_j is None:
            raise KeyError(f"KDJ is missing for {self.symbol} on {self.trade_date.isoformat()}")
        return KDJValue(k=self.kdj_k, d=self.kdj_d, j=self.kdj_j)

    @property
    def macd(self) -> MACDValue:
        if self.macd_line is None or self.macd_signal is None or self.macd_histogram is None:
            raise KeyError(f"MACD is missing for {self.symbol} on {self.trade_date.isoformat()}")
        return MACDValue(
            line=self.macd_line,
            signal=self.macd_signal,
            histogram=self.macd_histogram,
        )

    def ma(self, period: int) -> MAValue:
        value = getattr(self, f"ma{period}", None)
        if value is None:
            raise KeyError(f"MA{period} is missing for {self.symbol} on {self.trade_date.isoformat()}")
        return MAValue(period=period, value=value)

    def rsi(self, period: int) -> RSIValue:
        value = getattr(self, f"rsi{period}", None)
        if value is None:
            raise KeyError(f"RSI{period} is missing for {self.symbol} on {self.trade_date.isoformat()}")
        return RSIValue(period=period, value=value)

    def atr(self, period: int) -> ATRValue:
        value = getattr(self, f"atr{period}", None)
        if value is None:
            raise KeyError(f"ATR{period} is missing for {self.symbol} on {self.trade_date.isoformat()}")
        return ATRValue(period=period, value=value)

    def has_indicator(self, name: str) -> bool:
        if name == "kdj":
            return self.kdj_k is not None and self.kdj_d is not None and self.kdj_j is not None
        if name == "macd":
            return self.macd_line is not None and self.macd_signal is not None and self.macd_histogram is not None
        if name == "ma20":
            return self.ma20 is not None
        if name == "ma25":
            return self.ma25 is not None
        if name == "ma60":
            return self.ma60 is not None
        if name == "rsi14":
            return self.rsi14 is not None
        if name == "atr14":
            return self.atr14 is not None
        raise ValueError(f"unsupported indicator: {name}")


@dataclass(frozen=True)
class IndicatorSnapshotMetadata:
    symbol: str
    timeframe: str
    indicator_names: tuple[str, ...]
    version_fingerprint: str
    start_date: date | None
    end_date: date | None
    warmup_bars: int
    recompute_lookback_bars: int
    requires_state: bool
    states: Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True)
class IndicatorSnapshotCandidate:
    path: Path
    symbol: str
    start_date: date
    end_date: date
    adjustment: str
    asset_type: str
    indicator_names: tuple[str, ...]
    timeframe: str

    def overlaps(self, *, start_date: date, end_date: date) -> bool:
        return self.start_date <= end_date and self.end_date >= start_date


def indicator_snapshot_path(
    snapshot_root: str | Path,
    *,
    symbol: str,
    start_date: date,
    end_date: date,
    adjustment: str = DEFAULT_PRICE_ADJUSTMENT,
    asset_type: str = "stock",
    indicator_names: Sequence[str] = DEFAULT_INDICATOR_NAMES,
    timeframe: str = "D",
) -> Path:
    if timeframe not in SUPPORTED_INDICATOR_TIMEFRAMES:
        raise ValueError("indicator timeframe must be D, W, or M")

    safe_symbol = _safe_symbol(symbol)
    indicator_set = indicator_set_name(indicator_names)
    base_path = Path(snapshot_root) / "indicators" / indicator_set
    if timeframe != "D":
        base_path = base_path / timeframe

    if asset_type == "stock":
        return (
            base_path
            / adjustment
            / f"{safe_symbol}_{start_date:%Y%m%d}_{end_date:%Y%m%d}.parquet"
        )

    return (
        base_path
        / asset_type
        / adjustment
        / f"{safe_symbol}_{start_date:%Y%m%d}_{end_date:%Y%m%d}.parquet"
    )


def discover_indicator_snapshot_paths(
    snapshot_root: str | Path,
    *,
    symbol: str,
    start_date: date,
    end_date: date,
    adjustment: str = DEFAULT_PRICE_ADJUSTMENT,
    asset_type: str = "stock",
    indicator_names: Sequence[str] = DEFAULT_INDICATOR_NAMES,
    timeframe: str = "D",
) -> tuple[IndicatorSnapshotCandidate, ...]:
    directory = _indicator_snapshot_directory(
        snapshot_root,
        adjustment=adjustment,
        asset_type=asset_type,
        indicator_names=indicator_names,
        timeframe=timeframe,
    )
    if not directory.exists():
        return ()

    normalized_names = tuple(indicator_set_name(indicator_names).split("_"))
    candidates: list[IndicatorSnapshotCandidate] = []
    for path in directory.glob(f"{_safe_symbol(symbol)}_*.parquet"):
        candidate = _candidate_from_indicator_snapshot_path(
            path,
            symbol=symbol,
            adjustment=adjustment,
            asset_type=asset_type,
            indicator_names=normalized_names,
            timeframe=timeframe,
        )
        if candidate is not None and candidate.overlaps(start_date=start_date, end_date=end_date):
            candidates.append(candidate)

    return tuple(sorted(candidates, key=lambda candidate: (candidate.start_date, candidate.end_date, candidate.path.name)))


def indicator_snapshot_metadata_path(snapshot_path: str | Path) -> Path:
    return Path(snapshot_path).with_suffix(".metadata.json")


def write_indicator_snapshot_metadata(
    snapshot_path: str | Path,
    metadata: IndicatorSnapshotMetadata,
) -> Path:
    metadata_path = indicator_snapshot_metadata_path(snapshot_path)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(_metadata_to_payload(metadata), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return metadata_path


def read_indicator_snapshot_metadata(snapshot_path: str | Path) -> IndicatorSnapshotMetadata | None:
    metadata_path = indicator_snapshot_metadata_path(snapshot_path)
    if not metadata_path.exists():
        return None

    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    return IndicatorSnapshotMetadata(
        symbol=str(payload["symbol"]),
        timeframe=str(payload["timeframe"]),
        indicator_names=tuple(str(name) for name in payload["indicator_names"]),
        version_fingerprint=str(payload["version_fingerprint"]),
        start_date=_optional_date_from_payload(payload.get("start_date")),
        end_date=_optional_date_from_payload(payload.get("end_date")),
        warmup_bars=int(payload["warmup_bars"]),
        recompute_lookback_bars=int(payload["recompute_lookback_bars"]),
        requires_state=bool(payload["requires_state"]),
        states=dict(payload.get("states") or {}),
    )


def write_indicator_snapshots_parquet(snapshots: Sequence[IndicatorSnapshot], path: str | Path) -> Path:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas and pyarrow are required to write indicator snapshots") from exc

    parquet_path = Path(path)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        [
            {
                "symbol": snapshot.symbol,
                "trade_date": snapshot.trade_date.isoformat(),
                "timeframe": snapshot.timeframe,
                "kdj_k": snapshot.kdj_k,
                "kdj_d": snapshot.kdj_d,
                "kdj_j": snapshot.kdj_j,
                "macd_line": snapshot.macd_line,
                "macd_signal": snapshot.macd_signal,
                "macd_histogram": snapshot.macd_histogram,
                "ma20": snapshot.ma20,
                "ma25": snapshot.ma25,
                "ma60": snapshot.ma60,
                "rsi14": snapshot.rsi14,
                "atr14": snapshot.atr14,
            }
            for snapshot in snapshots
        ]
    )
    frame.to_parquet(parquet_path, index=False)
    return parquet_path


def write_merged_indicator_snapshots_parquet(
    existing_snapshots: Sequence[IndicatorSnapshot],
    new_snapshots: Sequence[IndicatorSnapshot],
    path: str | Path,
    *,
    overwrite_from: date | None = None,
) -> Path:
    merged_snapshots = merge_indicator_snapshots(
        existing_snapshots,
        new_snapshots,
        overwrite_from=overwrite_from,
    )
    return write_indicator_snapshots_parquet(merged_snapshots, path)


def merge_indicator_snapshots(
    existing_snapshots: Sequence[IndicatorSnapshot],
    new_snapshots: Sequence[IndicatorSnapshot],
    *,
    overwrite_from: date | None = None,
) -> tuple[IndicatorSnapshot, ...]:
    if not new_snapshots:
        return tuple(sorted(existing_snapshots, key=_snapshot_sort_key))

    effective_new_snapshots = [
        snapshot
        for snapshot in new_snapshots
        if overwrite_from is None or snapshot.trade_date >= overwrite_from
    ]
    if not effective_new_snapshots:
        return tuple(sorted(existing_snapshots, key=_snapshot_sort_key))

    replacement_groups = {
        (snapshot.symbol, snapshot.timeframe)
        for snapshot in effective_new_snapshots
    }
    kept_snapshots = [
        snapshot
        for snapshot in existing_snapshots
        if (snapshot.symbol, snapshot.timeframe) not in replacement_groups
        or overwrite_from is None
        or snapshot.trade_date < overwrite_from
    ]
    merged_by_key = {
        (snapshot.symbol, snapshot.timeframe, snapshot.trade_date): snapshot
        for snapshot in kept_snapshots
    }
    for snapshot in effective_new_snapshots:
        merged_by_key[(snapshot.symbol, snapshot.timeframe, snapshot.trade_date)] = snapshot

    return tuple(sorted(merged_by_key.values(), key=_snapshot_sort_key))


def read_indicator_snapshots_parquet(path: str | Path) -> tuple[IndicatorSnapshot, ...]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas and pyarrow are required to read indicator snapshots") from exc

    frame = pd.read_parquet(Path(path))
    snapshots = [
        IndicatorSnapshot(
            symbol=str(row.symbol),
            trade_date=date.fromisoformat(str(row.trade_date)),
            timeframe=str(getattr(row, "timeframe", "D")),
            kdj_k=_optional_float(row, "kdj_k", pd),
            kdj_d=_optional_float(row, "kdj_d", pd),
            kdj_j=_optional_float(row, "kdj_j", pd),
            macd_line=_optional_float(row, "macd_line", pd),
            macd_signal=_optional_float(row, "macd_signal", pd),
            macd_histogram=_optional_float(row, "macd_histogram", pd),
            ma20=_optional_float(row, "ma20", pd),
            ma25=_optional_float(row, "ma25", pd),
            ma60=_optional_float(row, "ma60", pd),
            rsi14=_optional_float(row, "rsi14", pd),
            atr14=_optional_float(row, "atr14", pd),
        )
        for row in frame.itertuples(index=False)
    ]
    return tuple(sorted(snapshots, key=_snapshot_sort_key))


def _optional_float(row, field_name: str, pd) -> float | None:
    if not hasattr(row, field_name):
        return None
    value = getattr(row, field_name)
    if pd.isna(value):
        return None
    return float(value)


def _metadata_to_payload(metadata: IndicatorSnapshotMetadata) -> dict[str, Any]:
    return {
        "symbol": metadata.symbol,
        "timeframe": metadata.timeframe,
        "indicator_names": list(metadata.indicator_names),
        "version_fingerprint": metadata.version_fingerprint,
        "start_date": metadata.start_date.isoformat() if metadata.start_date is not None else None,
        "end_date": metadata.end_date.isoformat() if metadata.end_date is not None else None,
        "warmup_bars": metadata.warmup_bars,
        "recompute_lookback_bars": metadata.recompute_lookback_bars,
        "requires_state": metadata.requires_state,
        "states": metadata.states,
    }


def _optional_date_from_payload(value: object) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(str(value))


def _indicator_snapshot_directory(
    snapshot_root: str | Path,
    *,
    adjustment: str,
    asset_type: str,
    indicator_names: Sequence[str],
    timeframe: str,
) -> Path:
    if timeframe not in SUPPORTED_INDICATOR_TIMEFRAMES:
        raise ValueError("indicator timeframe must be D, W, or M")

    base_path = Path(snapshot_root) / "indicators" / indicator_set_name(indicator_names)
    if timeframe != "D":
        base_path = base_path / timeframe
    if asset_type == "stock":
        return base_path / adjustment
    return base_path / asset_type / adjustment


def _candidate_from_indicator_snapshot_path(
    path: Path,
    *,
    symbol: str,
    adjustment: str,
    asset_type: str,
    indicator_names: tuple[str, ...],
    timeframe: str,
) -> IndicatorSnapshotCandidate | None:
    safe_symbol = _safe_symbol(symbol)
    stem = path.stem
    prefix = f"{safe_symbol}_"
    if not stem.startswith(prefix):
        return None

    date_parts = stem.removeprefix(prefix).split("_")
    if len(date_parts) != 2:
        return None

    try:
        start_date = date.fromisoformat(_compact_date_to_iso(date_parts[0]))
        end_date = date.fromisoformat(_compact_date_to_iso(date_parts[1]))
    except ValueError:
        return None

    return IndicatorSnapshotCandidate(
        path=path,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        adjustment=adjustment,
        asset_type=asset_type,
        indicator_names=indicator_names,
        timeframe=timeframe,
    )


def _compact_date_to_iso(value: str) -> str:
    if len(value) != 8 or not value.isdigit():
        raise ValueError(f"invalid compact date: {value}")
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"


def _safe_symbol(symbol: str) -> str:
    return symbol.replace(".", "_")


def _snapshot_sort_key(snapshot: IndicatorSnapshot) -> tuple[str, str, date]:
    return snapshot.symbol, snapshot.timeframe, snapshot.trade_date
