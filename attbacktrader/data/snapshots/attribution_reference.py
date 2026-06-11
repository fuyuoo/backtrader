"""Attribution reference snapshot preparation."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from attbacktrader.data import StockIndustryMembership
from attbacktrader.data.snapshots.industry_store import (
    read_stock_industry_memberships_parquet,
    stock_industry_membership_snapshot_path,
    write_stock_industry_memberships_parquet,
)


ATTRIBUTION_REFERENCE_FIELDS_VERSION = "attribution_reference_fields.v1"
DEFAULT_REFERENCE_UNIVERSE = "full_a_main_chinext_star"
PERCENTILE_BUCKETS = ("p0_p20", "p20_p40", "p40_p60", "p60_p80", "p80_p100")

FIELD_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {"field_key": "entry.market_cap.total_mv_bucket", "label_zh": "总市值分位桶", "scope": "market_cap", "value_type": "bucket"},
    {"field_key": "entry.market_cap.circulating_mv_bucket", "label_zh": "流通市值分位桶", "scope": "market_cap", "value_type": "bucket"},
    {"field_key": "entry.market_cap.total_mv_abs_bucket", "label_zh": "总市值绝对金额桶（亿元）", "scope": "market_cap", "value_type": "bucket", "bucket_rule": "fixed_explain_bucket"},
    {"field_key": "entry.market_cap.circulating_mv_abs_bucket", "label_zh": "流通市值绝对金额桶（亿元）", "scope": "market_cap", "value_type": "bucket", "bucket_rule": "fixed_explain_bucket"},
    {"field_key": "entry.valuation.pe_bucket", "label_zh": "PE桶", "scope": "valuation", "value_type": "bucket"},
    {"field_key": "entry.valuation.pe_ttm_bucket", "label_zh": "PE_TTM桶", "scope": "valuation", "value_type": "bucket", "default_in_environment_fit": True},
    {"field_key": "entry.valuation.pb_bucket", "label_zh": "PB桶", "scope": "valuation", "value_type": "bucket"},
    {"field_key": "entry.volatility.return_vol_20d_bucket", "label_zh": "20日收益波动率分位桶", "scope": "volatility", "value_type": "bucket"},
    {"field_key": "entry.volatility.return_vol_60d_bucket", "label_zh": "60日收益波动率分位桶", "scope": "volatility", "value_type": "bucket"},
    {"field_key": "entry.volatility.atr_20d_bucket", "label_zh": "ATR百分比分位桶", "scope": "volatility", "value_type": "bucket", "default_in_environment_fit": True},
    {"field_key": "entry.volatility.industry_atr_percentile_bucket", "label_zh": "个股ATR在行业内分位桶", "scope": "volatility", "value_type": "bucket", "default_in_environment_fit": True},
    {"field_key": "entry.volatility.symbol_atr_to_industry_median_bucket", "label_zh": "个股ATR相对行业中位数桶", "scope": "volatility", "value_type": "bucket", "bucket_rule": "fixed_explain_bucket", "default_in_environment_fit": True},
    {"field_key": "entry.volatility.max_amplitude_20d_bucket", "label_zh": "近20日最大振幅分位桶", "scope": "volatility", "value_type": "bucket"},
    {"field_key": "entry.liquidity.amount_20d_bucket", "label_zh": "20日平均成交额分位桶", "scope": "liquidity", "value_type": "bucket"},
    {"field_key": "entry.liquidity.turnover_rate_bucket", "label_zh": "换手率桶", "scope": "liquidity", "value_type": "bucket", "bucket_rule": "fixed_explain_bucket"},
    {"field_key": "entry.liquidity.volume_ratio_bucket", "label_zh": "量比桶", "scope": "liquidity", "value_type": "bucket", "bucket_rule": "fixed_explain_bucket"},
    {"field_key": "entry.liquidity.amount_bucket", "label_zh": "当日成交额桶（亿元）", "scope": "liquidity", "value_type": "bucket", "bucket_rule": "fixed_explain_bucket"},
    {"field_key": "entry.liquidity.amount_vs_20d_bucket", "label_zh": "当日成交额相对20日均额桶", "scope": "liquidity", "value_type": "bucket", "bucket_rule": "fixed_explain_bucket"},
    {"field_key": "entry.liquidity.industry_amount_percentile_bucket", "label_zh": "成交额在行业内分位桶", "scope": "liquidity", "value_type": "bucket"},
    {"field_key": "entry.price_position.near_high_20d_bucket", "label_zh": "距近20日高点桶", "scope": "price_position", "value_type": "bucket", "bucket_rule": "fixed_explain_bucket", "default_in_environment_fit": True},
    {"field_key": "entry.price_position.near_high_60d_bucket", "label_zh": "距近60日高点桶", "scope": "price_position", "value_type": "bucket", "bucket_rule": "fixed_explain_bucket", "default_in_environment_fit": True},
    {"field_key": "entry.price_position.interval_20d_bucket", "label_zh": "20日区间位置桶", "scope": "price_position", "value_type": "bucket", "bucket_rule": "fixed_explain_bucket"},
    {"field_key": "entry.price_position.interval_60d_bucket", "label_zh": "60日区间位置桶", "scope": "price_position", "value_type": "bucket", "bucket_rule": "fixed_explain_bucket"},
    {"field_key": "entry.price_position.ma60_atr_multiple_bucket", "label_zh": "入场价距MA60的ATR倍数桶", "scope": "price_position", "value_type": "bucket", "bucket_rule": "fixed_explain_bucket", "default_in_environment_fit": True},
    {"field_key": "entry.price_position.signal_close_ma60_atr_multiple_bucket", "label_zh": "信号日close距MA60的ATR倍数桶", "scope": "price_position", "value_type": "bucket", "bucket_rule": "fixed_explain_bucket"},
    {"field_key": "entry.stop_fit.fixed_atr_multiple_bucket", "label_zh": "固定5%对应ATR倍数桶", "scope": "stop_fit", "value_type": "bucket", "bucket_rule": "fixed_explain_bucket", "default_in_environment_fit": True},
    {"field_key": "industry.sw_l1.code", "label_zh": "申万一级行业", "scope": "industry", "value_type": "category", "bucket_rule": "effective_interval", "default_in_environment_fit": True},
)

DEFAULT_ENVIRONMENT_FIT_PAIR_WHITELIST = (
    ("industry.sw_l1.code", "entry.volatility.industry_atr_percentile_bucket"),
    ("industry.sw_l1.code", "industry.weekly.kdj_state"),
    ("industry.sw_l1.code", "entry.volatility.atr_20d_bucket"),
    ("industry.sw_l1.code", "entry.stop_fit.fixed_atr_multiple_bucket"),
    ("industry.sw_l1.code", "entry.price_position.ma60_atr_multiple_bucket"),
    ("entry.volatility.atr_20d_bucket", "entry.stop_fit.fixed_atr_multiple_bucket"),
    ("entry.volatility.atr_20d_bucket", "entry.price_position.ma60_atr_multiple_bucket"),
    ("entry.volatility.industry_atr_percentile_bucket", "entry.volatility.symbol_atr_to_industry_median_bucket"),
    ("entry.volatility.industry_atr_percentile_bucket", "entry.weekly.symbol_kdj_state"),
    ("entry.weekly.symbol_kdj_state", "industry.weekly.kdj_state"),
    ("entry.market_cap.circulating_mv_bucket", "entry.liquidity.amount_20d_bucket"),
    ("entry.price_position.near_high_20d_bucket", "entry.price_position.interval_20d_bucket"),
    ("entry.price_position.near_high_60d_bucket", "entry.price_position.interval_60d_bucket"),
)


def attribution_reference_snapshot_dir(
    snapshot_root: str | Path,
    *,
    reference_universe: str,
    start_date: date,
    end_date: date,
) -> Path:
    return (
        Path(snapshot_root)
        / "attribution_reference"
        / reference_universe
        / f"{start_date:%Y-%m-%d}_{end_date:%Y-%m-%d}"
    )


def build_attribution_reference_snapshot_from_frame(
    frame: pd.DataFrame,
    *,
    start_date: date,
    end_date: date,
    reference_universe: str = DEFAULT_REFERENCE_UNIVERSE,
    min_reference_count: int = 100,
    emit_symbols: Sequence[str] | None = None,
    emit_dates: Sequence[date | str] | None = None,
    emit_symbol_date_pairs: Sequence[tuple[str, date | str]] | None = None,
) -> dict[str, Any]:
    """Build long-form attribution reference rows from daily all-A data."""

    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")
    required = {"symbol", "trade_date", "close", "high", "low"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"missing required attribution reference columns: {missing}")

    data = frame.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"]).dt.date
    data = data[(data["trade_date"] >= start_date) & (data["trade_date"] <= end_date)].copy()
    data = data.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    data = _derive_symbol_features(data)

    rows: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []
    percentile_specs = _percentile_specs()
    emit_symbol_set = {str(symbol) for symbol in emit_symbols or []}
    emit_date_set = {_coerce_date(value) for value in emit_dates or []}
    emit_date_set.discard(None)
    emit_pair_dates: dict[date, set[str]] = {}
    for symbol, value in emit_symbol_date_pairs or ():
        pair_date = _coerce_date(value)
        if pair_date is not None:
            emit_pair_dates.setdefault(pair_date, set()).add(str(symbol))
    for trade_date, day in data.groupby("trade_date", sort=True):
        if emit_pair_dates and trade_date not in emit_pair_dates:
            continue
        if emit_date_set and trade_date not in emit_date_set:
            continue
        reference_mask = _reference_universe_mask(day)
        reference_day = day[reference_mask]
        exclusion_codes = _exclusion_codes(day)
        percentiles = _day_percentiles(reference_day, percentile_specs)
        industry_stats = _day_industry_stats(reference_day)
        reference_counts = {
            spec["column"]: int(reference_day[spec["column"]].notna().sum())
            for spec in percentile_specs
        }
        emit_day = day
        if emit_pair_dates:
            emit_day = emit_day[emit_day["symbol"].astype(str).isin(emit_pair_dates[trade_date])]
        elif emit_symbol_set:
            emit_day = emit_day[emit_day["symbol"].astype(str).isin(emit_symbol_set)]
        for _, record in emit_day.iterrows():
            symbol = str(record["symbol"])
            symbol_exclusions = exclusion_codes.get(record.name, [])
            rows.extend(_field_rows_for_record(
                record,
                symbol=symbol,
                trade_date=trade_date,
                percentiles=percentiles,
                industry_stats=industry_stats,
                reference_counts=reference_counts,
                min_reference_count=min_reference_count,
                excluded_codes=symbol_exclusions,
            ))
            for code in symbol_exclusions:
                exceptions.append({"symbol": symbol, "trade_date": trade_date.isoformat(), "code": code})

    metadata = {
        "schema": ATTRIBUTION_REFERENCE_FIELDS_VERSION,
        "reference_universe": reference_universe,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "fields": [dict(item, timing="entry", source="attribution_reference_snapshot", missing_policy="missing") for item in FIELD_DEFINITIONS],
        "environment_fit_default_fields": [
            item["field_key"] for item in FIELD_DEFINITIONS if item.get("default_in_environment_fit") is True
        ],
        "environment_fit_pair_whitelist": [list(pair) for pair in DEFAULT_ENVIRONMENT_FIT_PAIR_WHITELIST],
        "percentile_method": "rank(pct=True, method='average') by trade_date full-A reference universe",
        "percentile_buckets": list(PERCENTILE_BUCKETS),
        "reference_universe_filters": [
            "exclude historical ST",
            "exclude suspended trade date",
            "exclude listed trading days < 60",
            "exclude Beijing Stock Exchange",
            "exclude non-tradable ordinary shares",
        ],
        "emit_symbol_count": len(emit_symbol_set) if emit_symbol_set else None,
        "emit_date_count": len(emit_date_set) if emit_date_set else None,
        "emit_pair_count": sum(len(symbols) for symbols in emit_pair_dates.values()) if emit_pair_dates else None,
        "exception_count": len(exceptions),
        "exceptions": exceptions[:1000],
    }
    return {
        "metadata": metadata,
        "rows": rows,
        "row_count": len(rows),
    }


def load_or_fetch_industry_memberships_for_symbols(
    symbols: Sequence[str],
    *,
    snapshot_root: str | Path,
    provider: Any | None,
    source: str = "SW2021",
    refresh: bool = False,
) -> dict[str, tuple[StockIndustryMembership, ...]]:
    """Load cached stock industry memberships or fetch them from provider."""

    result: dict[str, tuple[StockIndustryMembership, ...]] = {}
    for symbol in sorted(set(str(item) for item in symbols if item)):
        path = stock_industry_membership_snapshot_path(snapshot_root, symbol=symbol, source=source)
        if path.exists() and not refresh:
            result[symbol] = read_stock_industry_memberships_parquet(path)
            continue
        if provider is None:
            result[symbol] = ()
            continue
        memberships = tuple(provider.fetch_stock_industry_memberships(symbol=symbol, source=source))
        if memberships:
            write_stock_industry_memberships_parquet(memberships, path)
        result[symbol] = memberships
    return result


def load_or_fetch_all_industry_memberships(
    *,
    snapshot_root: str | Path,
    provider: Any | None,
    source: str = "SW2021",
    refresh: bool = False,
) -> dict[str, tuple[StockIndustryMembership, ...]]:
    """Fetch full-universe stock industry memberships and persist per-symbol snapshots."""

    fetch_all = getattr(provider, "fetch_all_stock_industry_memberships", None) if provider is not None else None
    if not callable(fetch_all):
        return {}

    memberships = tuple(fetch_all(source=source))
    grouped: dict[str, list[StockIndustryMembership]] = {}
    for membership in memberships:
        grouped.setdefault(membership.symbol, []).append(membership)

    result: dict[str, tuple[StockIndustryMembership, ...]] = {}
    for symbol, symbol_memberships in sorted(grouped.items()):
        ordered = tuple(sorted(symbol_memberships, key=lambda item: (item.in_date, item.level3_code)))
        path = stock_industry_membership_snapshot_path(snapshot_root, symbol=symbol, source=source)
        if refresh or not path.exists():
            write_stock_industry_memberships_parquet(ordered, path)
        result[symbol] = ordered
    return result


def apply_industry_memberships_to_frame(
    frame: pd.DataFrame,
    memberships_by_symbol: Mapping[str, Sequence[StockIndustryMembership]],
) -> pd.DataFrame:
    """Attach historical SW L1 industry by effective membership interval."""

    if frame.empty:
        return frame.copy()
    data = frame.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"]).dt.date
    l1_codes: list[str | None] = []
    l1_names: list[str | None] = []
    missing_flags: list[bool] = []
    for row in data.itertuples(index=False):
        membership = _active_membership_for(str(row.symbol), row.trade_date, memberships_by_symbol)
        if membership is None:
            l1_codes.append(None)
            l1_names.append(None)
            missing_flags.append(True)
        else:
            l1_codes.append(membership.level1_code)
            l1_names.append(membership.level1_name)
            missing_flags.append(False)
    data["sw_l1_code"] = l1_codes
    data["sw_l1_name"] = l1_names
    data["industry_membership_missing"] = missing_flags
    return data


def write_attribution_reference_snapshot(snapshot: Mapping[str, Any], output_dir: str | Path) -> tuple[Path, Path, Path]:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = target_dir / "metadata.json"
    reference_json_path = target_dir / "reference.json"
    values_path = target_dir / "reference_values.parquet"

    metadata = dict(_as_mapping(snapshot.get("metadata")))
    rows = list(_as_sequence(snapshot.get("rows")))
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    reference_json_path.write_text(
        json.dumps({"metadata": metadata, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    frame = pd.DataFrame(rows)
    if not frame.empty:
        for column in ("value", "bucket"):
            if column in frame.columns:
                frame[column] = frame[column].map(lambda value: json.dumps(value, ensure_ascii=False))
        if "exception_codes" in frame.columns:
            frame["exception_codes"] = frame["exception_codes"].map(lambda value: ";".join(str(item) for item in _as_sequence(value)))
    frame.to_parquet(values_path, index=False)
    return metadata_path, reference_json_path, values_path


def _active_membership_for(
    symbol: str,
    trade_date: date,
    memberships_by_symbol: Mapping[str, Sequence[StockIndustryMembership]],
) -> StockIndustryMembership | None:
    memberships = tuple(memberships_by_symbol.get(symbol, ()))
    active = [membership for membership in memberships if membership.active_on(trade_date)]
    if active:
        return sorted(active, key=lambda item: (item.in_date, item.level1_code))[-1]
    return None


def _derive_symbol_features(data: pd.DataFrame) -> pd.DataFrame:
    if "total_mv" in data.columns:
        data["total_mv_yi"] = pd.to_numeric(data["total_mv"], errors="coerce") / 10000.0
    if "circ_mv" in data.columns:
        data["circ_mv_yi"] = pd.to_numeric(data["circ_mv"], errors="coerce") / 10000.0
    if "amount" in data.columns:
        data["amount"] = pd.to_numeric(data["amount"], errors="coerce")
        data["amount_yi"] = data["amount"] / 100000.0
    grouped = data.groupby("symbol", sort=False)
    data["return_1d"] = grouped["close"].pct_change()
    data["return_vol_20d"] = grouped["return_1d"].transform(lambda value: value.rolling(20, min_periods=20).std())
    data["return_vol_60d"] = grouped["return_1d"].transform(lambda value: value.rolling(60, min_periods=60).std())
    data["prev_close"] = grouped["close"].shift(1)
    true_range = pd.concat(
        [
            data["high"] - data["low"],
            (data["high"] - data["prev_close"]).abs(),
            (data["low"] - data["prev_close"]).abs(),
        ],
        axis=1,
    ).max(axis=1)
    data["true_range"] = true_range
    data["atr_20d"] = grouped["true_range"].transform(lambda value: value.rolling(20, min_periods=20).mean())
    data["atr_pct"] = data["atr_20d"] / data["close"]
    data["ma60"] = grouped["close"].transform(lambda value: value.rolling(60, min_periods=60).mean())
    data["rolling_high_20d"] = grouped["high"].transform(lambda value: value.rolling(20, min_periods=20).max())
    data["rolling_low_20d"] = grouped["low"].transform(lambda value: value.rolling(20, min_periods=20).min())
    data["rolling_high_60d"] = grouped["high"].transform(lambda value: value.rolling(60, min_periods=60).max())
    data["rolling_low_60d"] = grouped["low"].transform(lambda value: value.rolling(60, min_periods=60).min())
    data["near_high_20d"] = data["close"] / data["rolling_high_20d"] - 1.0
    data["near_high_60d"] = data["close"] / data["rolling_high_60d"] - 1.0
    data["interval_20d"] = (data["close"] - data["rolling_low_20d"]) / (data["rolling_high_20d"] - data["rolling_low_20d"])
    data["interval_60d"] = (data["close"] - data["rolling_low_60d"]) / (data["rolling_high_60d"] - data["rolling_low_60d"])
    data["max_amplitude_20d"] = data["rolling_high_20d"] / data["rolling_low_20d"] - 1.0
    data["ma60_atr_multiple"] = (data["close"] - data["ma60"]) / data["atr_20d"]
    data["fixed_atr_multiple"] = 0.05 / data["atr_pct"]
    if "amount" in data.columns:
        data["amount_20d"] = grouped["amount"].transform(lambda value: value.rolling(20, min_periods=20).mean())
        data["amount_vs_20d"] = data["amount"] / data["amount_20d"]
    return data


def _percentile_specs() -> tuple[dict[str, str], ...]:
    return (
        {"column": "total_mv", "field_key": "entry.market_cap.total_mv_bucket"},
        {"column": "circ_mv", "field_key": "entry.market_cap.circulating_mv_bucket"},
        {"column": "return_vol_20d", "field_key": "entry.volatility.return_vol_20d_bucket"},
        {"column": "return_vol_60d", "field_key": "entry.volatility.return_vol_60d_bucket"},
        {"column": "atr_pct", "field_key": "entry.volatility.atr_20d_bucket"},
        {"column": "max_amplitude_20d", "field_key": "entry.volatility.max_amplitude_20d_bucket"},
        {"column": "amount_20d", "field_key": "entry.liquidity.amount_20d_bucket"},
    )


def _day_percentiles(day: pd.DataFrame, specs: Sequence[Mapping[str, str]]) -> dict[str, Mapping[str, float]]:
    result: dict[str, Mapping[str, float]] = {}
    for spec in specs:
        column = spec["column"]
        if column not in day.columns:
            result[column] = {}
            continue
        ranks = day[column].rank(pct=True, method="average")
        result[column] = {str(symbol): float(value) for symbol, value in zip(day["symbol"], ranks) if pd.notna(value)}
    return result


def _day_industry_stats(day: pd.DataFrame) -> dict[str, dict[str, float | int]]:
    if day.empty or "sw_l1_code" not in day.columns:
        return {}
    data = day.copy()
    data["sw_l1_code"] = data["sw_l1_code"].map(lambda value: str(value).strip() if pd.notna(value) else "")
    data = data[data["sw_l1_code"] != ""]
    if data.empty:
        return {}

    result: dict[str, dict[str, float | int]] = {}
    for _, group in data.groupby("sw_l1_code", sort=False):
        stats_by_symbol: dict[str, dict[str, float | int]] = {
            str(symbol): {} for symbol in group["symbol"]
        }
        if "atr_pct" in group.columns:
            atr_values = pd.to_numeric(group["atr_pct"], errors="coerce")
            atr_count = int(atr_values.notna().sum())
            atr_median = _optional_float(atr_values.median()) if atr_count else None
            atr_ranks = atr_values.rank(pct=True, method="average")
            for symbol, value, percentile in zip(group["symbol"], atr_values, atr_ranks):
                symbol_key = str(symbol)
                stats_by_symbol[symbol_key]["industry_atr_reference_count"] = atr_count
                if pd.notna(percentile):
                    stats_by_symbol[symbol_key]["industry_atr_percentile"] = float(percentile)
                if atr_median is not None and atr_median > 0 and pd.notna(value):
                    stats_by_symbol[symbol_key]["symbol_atr_to_industry_median"] = float(value) / atr_median

        amount_column = "amount_20d" if "amount_20d" in group.columns else "amount"
        if amount_column in group.columns:
            amount_values = pd.to_numeric(group[amount_column], errors="coerce")
            amount_count = int(amount_values.notna().sum())
            amount_ranks = amount_values.rank(pct=True, method="average")
            for symbol, percentile in zip(group["symbol"], amount_ranks):
                symbol_key = str(symbol)
                stats_by_symbol[symbol_key]["industry_amount_reference_count"] = amount_count
                if pd.notna(percentile):
                    stats_by_symbol[symbol_key]["industry_amount_percentile"] = float(percentile)
        result.update(stats_by_symbol)
    return result


def _field_rows_for_record(
    record: pd.Series,
    *,
    symbol: str,
    trade_date: date,
    percentiles: Mapping[str, Mapping[str, float]],
    industry_stats: Mapping[str, Mapping[str, float | int]],
    reference_counts: Mapping[str, int],
    min_reference_count: int,
    excluded_codes: Sequence[str],
) -> list[dict[str, Any]]:
    rows = []
    for spec in _percentile_specs():
        column = spec["column"]
        if column not in record:
            continue
        value = _optional_float(record.get(column))
        percentile = percentiles.get(column, {}).get(symbol)
        exceptions = list(excluded_codes)
        reference_count = int(reference_counts.get(column, 0))
        if reference_count < min_reference_count:
            exceptions.append("reference_low_count")
        rows.append(_row(
            symbol=symbol,
            trade_date=trade_date,
            field_key=spec["field_key"],
            value=value,
            bucket=_percentile_bucket(percentile) if percentile is not None else None,
            percentile=percentile,
            reference_count=reference_count,
            exception_codes=exceptions,
        ))

    stats = _as_mapping(industry_stats.get(symbol))
    industry_reference_fields = (
        (
            "entry.volatility.industry_atr_percentile_bucket",
            stats.get("industry_atr_percentile"),
            _percentile_bucket(_optional_float(stats.get("industry_atr_percentile"))),
            _optional_float(stats.get("industry_atr_percentile")),
            _optional_int(stats.get("industry_atr_reference_count")),
        ),
        (
            "entry.volatility.symbol_atr_to_industry_median_bucket",
            stats.get("symbol_atr_to_industry_median"),
            _relative_ratio_bucket(stats.get("symbol_atr_to_industry_median")),
            None,
            _optional_int(stats.get("industry_atr_reference_count")),
        ),
        (
            "entry.liquidity.industry_amount_percentile_bucket",
            stats.get("industry_amount_percentile"),
            _percentile_bucket(_optional_float(stats.get("industry_amount_percentile"))),
            _optional_float(stats.get("industry_amount_percentile")),
            _optional_int(stats.get("industry_amount_reference_count")),
        ),
    )
    for field_key, value, bucket, percentile, reference_count in industry_reference_fields:
        exceptions = list(excluded_codes)
        if _is_missing_text(record.get("sw_l1_code")):
            exceptions.append("industry_missing")
        if reference_count is not None and reference_count < min_reference_count:
            exceptions.append("industry_reference_low_count")
        rows.append(_row(
            symbol=symbol,
            trade_date=trade_date,
            field_key=field_key,
            value=_optional_float(value),
            bucket=bucket,
            percentile=percentile,
            reference_count=reference_count,
            exception_codes=exceptions,
        ))

    fixed_fields = (
        ("entry.market_cap.total_mv_abs_bucket", record.get("total_mv_yi"), _market_cap_abs_bucket(record.get("total_mv_yi"))),
        ("entry.market_cap.circulating_mv_abs_bucket", record.get("circ_mv_yi"), _market_cap_abs_bucket(record.get("circ_mv_yi"))),
        ("entry.valuation.pe_bucket", record.get("pe"), _pe_bucket(record.get("pe"))),
        ("entry.valuation.pe_ttm_bucket", record.get("pe_ttm"), _pe_bucket(record.get("pe_ttm"))),
        ("entry.valuation.pb_bucket", record.get("pb"), _pb_bucket(record.get("pb"))),
        ("entry.liquidity.turnover_rate_bucket", record.get("turnover_rate"), _turnover_rate_bucket(record.get("turnover_rate"))),
        ("entry.liquidity.volume_ratio_bucket", record.get("volume_ratio"), _volume_ratio_bucket(record.get("volume_ratio"))),
        ("entry.liquidity.amount_bucket", record.get("amount_yi"), _amount_abs_bucket(record.get("amount_yi"))),
        ("entry.liquidity.amount_vs_20d_bucket", record.get("amount_vs_20d"), _relative_ratio_bucket(record.get("amount_vs_20d"))),
        ("entry.price_position.near_high_20d_bucket", record.get("near_high_20d"), _near_high_bucket(record.get("near_high_20d"))),
        ("entry.price_position.near_high_60d_bucket", record.get("near_high_60d"), _near_high_bucket(record.get("near_high_60d"))),
        ("entry.price_position.interval_20d_bucket", record.get("interval_20d"), _interval_bucket(record.get("interval_20d"))),
        ("entry.price_position.interval_60d_bucket", record.get("interval_60d"), _interval_bucket(record.get("interval_60d"))),
        ("entry.price_position.signal_close_ma60_atr_multiple_bucket", record.get("ma60_atr_multiple"), _atr_multiple_bucket(record.get("ma60_atr_multiple"))),
        ("entry.stop_fit.fixed_atr_multiple_bucket", record.get("fixed_atr_multiple"), _fixed_atr_multiple_bucket(record.get("fixed_atr_multiple"))),
        ("industry.sw_l1.code", record.get("sw_l1_code"), record.get("sw_l1_code")),
    )
    for field_key, value, bucket in fixed_fields:
        exceptions = list(excluded_codes)
        if field_key == "industry.sw_l1.code" and _is_missing_text(bucket):
            exceptions.append("industry_missing")
        if field_key.endswith("pe_bucket") and _optional_float(value) is not None and (_optional_float(value) or 0.0) < 0:
            exceptions.append("negative_pe")
        if field_key == "entry.liquidity.amount_vs_20d_bucket" and bucket is None:
            exceptions.append("liquidity_lookback_missing")
        rows.append(_row(
            symbol=symbol,
            trade_date=trade_date,
            field_key=field_key,
            value=_optional_float(value) if field_key != "industry.sw_l1.code" else value,
            bucket=bucket,
            percentile=None,
            reference_count=None,
            exception_codes=exceptions,
        ))
    return rows


def _row(
    *,
    symbol: str,
    trade_date: date,
    field_key: str,
    value: Any,
    bucket: Any,
    percentile: float | None,
    reference_count: int | None,
    exception_codes: Sequence[str],
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "trade_date": trade_date.isoformat(),
        "field_key": field_key,
        "value": _jsonable(value),
        "bucket": _jsonable(bucket),
        "percentile": percentile,
        "asof_date": trade_date.isoformat(),
        "staleness_trading_days": 0,
        "reference_count": reference_count,
        "exception_codes": sorted(set(str(code) for code in exception_codes if code)),
    }


def _reference_universe_mask(day: pd.DataFrame) -> pd.Series:
    mask = pd.Series(True, index=day.index)
    if "is_st" in day.columns:
        mask &= ~day["is_st"].fillna(False).astype(bool)
    if "is_suspended" in day.columns:
        mask &= ~day["is_suspended"].fillna(False).astype(bool)
    if "listing_trading_days" in day.columns:
        mask &= day["listing_trading_days"].fillna(0).astype(int) >= 60
    if "exchange" in day.columns:
        mask &= ~day["exchange"].fillna("").astype(str).str.upper().isin({"BSE", "BJ", "北交所"})
    if "is_tradable" in day.columns:
        mask &= day["is_tradable"].fillna(True).astype(bool)
    return mask


def _exclusion_codes(day: pd.DataFrame) -> dict[int, list[str]]:
    result: dict[int, list[str]] = {}
    for index, row in day.iterrows():
        codes = []
        if bool(row.get("is_st", False)):
            codes.append("reference_excluded_st")
        if bool(row.get("is_suspended", False)):
            codes.append("reference_excluded_suspended")
        if _optional_float(row.get("listing_trading_days")) is not None and (_optional_float(row.get("listing_trading_days")) or 0) < 60:
            codes.append("reference_excluded_new_listing")
        if str(row.get("exchange", "")).upper() in {"BSE", "BJ", "北交所"}:
            codes.append("reference_excluded_bse")
        if row.get("is_tradable") is not None and not bool(row.get("is_tradable")):
            codes.append("reference_excluded_untradable")
        result[index] = codes
    return result


def _percentile_bucket(value: float | None) -> str | None:
    if value is None:
        return None
    if value <= 0.2:
        return "p0_p20"
    if value <= 0.4:
        return "p20_p40"
    if value <= 0.6:
        return "p40_p60"
    if value <= 0.8:
        return "p60_p80"
    return "p80_p100"


def _near_high_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number >= -0.01:
        return "at_high"
    if number >= -0.03:
        return "near_high"
    if number >= -0.08:
        return "moderate_pullback"
    if number >= -0.15:
        return "deep_pullback"
    return "far_from_high"


def _interval_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number <= 0.2:
        return "low_0_20"
    if number <= 0.4:
        return "low_mid_20_40"
    if number <= 0.6:
        return "mid_40_60"
    if number <= 0.8:
        return "high_mid_60_80"
    return "high_80_100"


def _pe_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number < 0:
        return "negative"
    if number == 0:
        return "zero"
    if number <= 15:
        return "0_15"
    if number <= 30:
        return "15_30"
    if number <= 60:
        return "30_60"
    return "gt_60"


def _pb_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number <= 0:
        return "non_positive"
    if number <= 1:
        return "0_1"
    if number <= 2:
        return "1_2"
    if number <= 5:
        return "2_5"
    return "gt_5"


def _market_cap_abs_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None or number < 0:
        return None
    if number < 100:
        return "0_100yi"
    if number < 300:
        return "100_300yi"
    if number < 600:
        return "300_600yi"
    if number < 1000:
        return "600_1000yi"
    if number < 1500:
        return "1000_1500yi"
    return "gte_1500yi"


def _amount_abs_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None or number < 0:
        return None
    if number < 0.5:
        return "0_0p5yi"
    if number < 1:
        return "0p5_1yi"
    if number < 3:
        return "1_3yi"
    if number < 10:
        return "3_10yi"
    return "gte_10yi"


def _turnover_rate_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None or number < 0:
        return None
    if number < 1:
        return "lt_1pct"
    if number < 3:
        return "1_3pct"
    if number < 5:
        return "3_5pct"
    if number < 10:
        return "5_10pct"
    return "gte_10pct"


def _volume_ratio_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None or number < 0:
        return None
    if number < 0.8:
        return "lt_0p8x"
    if number < 1.2:
        return "0p8_1p2x"
    if number < 2:
        return "1p2_2x"
    if number < 4:
        return "2_4x"
    return "gte_4x"


def _relative_ratio_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None or number < 0:
        return None
    if number < 0.8:
        return "lt_0p8x"
    if number < 1.2:
        return "0p8_1p2x"
    if number < 1.6:
        return "1p2_1p6x"
    if number < 2:
        return "1p6_2x"
    return "gte_2x"


def _atr_multiple_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number < -2:
        return "below_ma60_gt_2atr"
    if number < -1:
        return "below_ma60_1_2atr"
    if number < 0:
        return "below_ma60_0_1atr"
    if number <= 1:
        return "above_ma60_0_1atr"
    if number <= 2:
        return "above_ma60_1_2atr"
    return "above_ma60_gt_2atr"


def _fixed_atr_multiple_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number < 1:
        return "lt_1atr"
    if number < 2:
        return "1_2atr"
    if number < 3:
        return "2_3atr"
    return "gte_3atr"


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool) or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool) or pd.isna(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_missing_text(value: Any) -> bool:
    if value is None or pd.isna(value):
        return True
    return not str(value).strip()


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _coerce_date(value: date | str | Any) -> date | None:
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, (list, tuple)) else ()
