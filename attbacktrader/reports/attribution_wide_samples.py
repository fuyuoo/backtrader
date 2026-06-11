"""Attribution wide samples and field index artifacts."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd


ATTRIBUTION_WIDE_SAMPLES_SCHEMA = "attbacktrader.attribution_wide_samples.v1"
ATTRIBUTION_FIELD_INDEX_SCHEMA = "attbacktrader.attribution_field_index.v1"

DEFAULT_WIDE_SAMPLE_JSON = "attribution_wide_samples.json"
DEFAULT_WIDE_SAMPLE_CSV = "attribution_wide_samples.csv"
DEFAULT_FIELD_INDEX_JSON = "attribution_field_index.json"
DEFAULT_FIELD_INDEX_MARKDOWN = "attribution_field_index.zh.md"

DEFAULT_ENVIRONMENT_FIT_PAIR_WHITELIST: tuple[tuple[str, str], ...] = (
    ("industry.sw_l1.code", "entry.volatility.industry_atr_percentile_bucket"),
    ("industry.sw_l1.code", "entry.stop_fit.fixed_atr_multiple_bucket"),
    ("industry.sw_l1.code", "entry.price_position.ma60_atr_multiple_bucket"),
    ("entry.volatility.atr_20d_bucket", "entry.stop_fit.fixed_atr_multiple_bucket"),
    ("entry.volatility.atr_20d_bucket", "entry.price_position.ma60_atr_multiple_bucket"),
    ("entry.market_cap.circulating_mv_bucket", "entry.liquidity.amount_20d_bucket"),
    ("entry.price_position.near_high_20d_bucket", "entry.price_position.interval_20d_bucket"),
    ("entry.price_position.near_high_60d_bucket", "entry.price_position.interval_60d_bucket"),
)


def build_attribution_wide_samples(
    run_dir: str | Path,
    *,
    reference_snapshot: str | Path,
    max_staleness_trading_days: int = 5,
) -> dict[str, Any]:
    """Build completed-trade attribution wide samples from persisted run artifacts."""

    if max_staleness_trading_days < 0:
        raise ValueError("max_staleness_trading_days must be greater than or equal to 0")

    run_path = Path(run_dir)
    if not run_path.exists():
        raise FileNotFoundError(f"Run artifact directory does not exist: {run_path}")

    run_plan = _as_mapping(_load_json_if_exists(run_path / "run_plan.json"))
    trade_attribution = _as_mapping(_load_json_if_exists(run_path / "trade_attribution.json"))
    trade_lifecycle = _as_mapping(_load_json_if_exists(run_path / "trade_lifecycle.json"))
    reference = _load_reference_snapshot(reference_snapshot)
    reference_rows = _reference_rows_by_symbol_field(reference["rows"])
    field_catalog = _field_catalog(reference)

    samples = []
    for trade in _completed_trade_rows(trade_attribution, trade_lifecycle=trade_lifecycle):
        trade_index = _optional_int(trade.get("trade_index"))
        symbol = _as_str(trade.get("symbol"))
        entry_date = _as_str(trade.get("entry_date"))
        if trade_index is None or not symbol or not entry_date:
            continue

        field_values: dict[str, dict[str, Any]] = {}
        exception_codes: set[str] = set()
        for field_key in field_catalog:
            row = _reference_row_for(
                reference_rows.get((symbol, field_key), ()),
                entry_date=entry_date,
                max_staleness_trading_days=max_staleness_trading_days,
            )
            if row is None:
                exception_codes.add("reference_record_missing")
                field_values[field_key] = _missing_field_payload("reference_record_missing")
                continue

            field_exceptions = _exception_codes(row.get("exception_codes"))
            exception_codes.update(field_exceptions)
            field_values[field_key] = {
                "raw": _jsonable(_decode_reference_cell(row.get("value"))),
                "bucket": _jsonable(_decode_reference_cell(row.get("bucket"))),
                "percentile": _optional_float(row.get("percentile")),
                "asof_date": _as_str(row.get("asof_date")) or _as_str(row.get("trade_date")),
                "staleness_trading_days": _optional_int(row.get("staleness_trading_days")),
                "reference_count": _optional_int(row.get("reference_count")),
                "exception_codes": field_exceptions,
            }

        for key, value in _entry_factor_values(trade).items():
            if key not in field_values:
                field_catalog[key] = _fallback_field_catalog_item(key)
            field_values.setdefault(
                key,
                {
                    "raw": value,
                    "bucket": None,
                    "percentile": None,
                    "asof_date": entry_date,
                    "staleness_trading_days": 0,
                    "reference_count": None,
                    "exception_codes": [],
                },
            )

        samples.append(
            {
                "trade_index": trade_index,
                "symbol": symbol,
                "entry_date": entry_date,
                "exit_date": _as_str(trade.get("exit_date")),
                "exit_type": _as_str(trade.get("exit_type")) or "natural",
                "outcome": _as_str(trade.get("outcome")),
                "exit_reason": _as_str(trade.get("exit_reason")),
                "return_pct": _optional_float(trade.get("return_pct")),
                "profit_contribution": _as_mapping(trade.get("profit_contribution")),
                "attribution_exception_codes": sorted(exception_codes),
                "field_values": field_values,
            }
        )

    payload = {
        "schema": ATTRIBUTION_WIDE_SAMPLES_SCHEMA,
        "run_id": _run_id(run_path, run_plan),
        "source_dir": str(run_path),
        "reference_path": str(reference["source_path"]),
        "sample_count": len(samples),
        "field_count": len(field_catalog),
        "environment_fit_default_fields": _environment_default_fields(field_catalog, reference["metadata"]),
        "environment_fit_pair_whitelist": _environment_pair_whitelist(reference["metadata"]),
        "samples": samples,
        "reference_metadata": reference["metadata"],
    }
    payload["field_index"] = build_attribution_field_index(payload, field_catalog=field_catalog)
    return payload


def build_attribution_field_index(
    wide_samples: Mapping[str, Any],
    *,
    field_catalog: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the machine-readable field index from attribution wide samples."""

    samples = [_as_mapping(item) for item in _as_sequence(wide_samples.get("samples"))]
    catalog = {str(k): dict(v) for k, v in (field_catalog or {}).items()}
    for sample in samples:
        for field_key in _as_mapping(sample.get("field_values")):
            catalog.setdefault(str(field_key), _fallback_field_catalog_item(str(field_key)))

    stats = {
        key: {
            "sample_count": 0,
            "missing_count": 0,
            "exception_codes": Counter(),
            "buckets": defaultdict(list),
        }
        for key in catalog
    }
    for sample in samples:
        trade_index = _optional_int(sample.get("trade_index"))
        return_pct = _optional_float(sample.get("return_pct"))
        net_pnl = _optional_float(_as_mapping(sample.get("profit_contribution")).get("net_pnl"))
        for field_key, payload in _as_mapping(sample.get("field_values")).items():
            if field_key not in stats:
                continue
            item = _as_mapping(payload)
            bucket = item.get("bucket")
            raw = item.get("raw")
            value = bucket if bucket is not None else raw
            value_key = _stable_value_key(value if value is not None else "__missing__")
            stats[field_key]["sample_count"] += 1
            if value is None:
                stats[field_key]["missing_count"] += 1
            for code in _exception_codes(item.get("exception_codes")):
                stats[field_key]["exception_codes"][code] += 1
            stats[field_key]["buckets"][value_key].append(
                {
                    "trade_index": trade_index,
                    "value": value,
                    "return_pct": return_pct,
                    "net_pnl": net_pnl,
                }
            )

    fields = []
    for field_key in sorted(catalog):
        item = catalog[field_key]
        sample_count = int(stats[field_key]["sample_count"])
        missing_count = int(stats[field_key]["missing_count"])
        bucket_distribution = [
            {
                "value": rows[0]["value"] if rows else None,
                "count": len(rows),
                "sample_refs": _representative_refs(rows),
            }
            for _, rows in sorted(
                stats[field_key]["buckets"].items(),
                key=lambda pair: (-len(pair[1]), str(pair[0])),
            )
        ]
        fields.append(
            {
                "field_key": field_key,
                "label_zh": item.get("label_zh", field_key),
                "value_type": item.get("value_type", "value"),
                "timing": item.get("timing", "entry"),
                "scope": item.get("scope", _scope_from_field(field_key)),
                "bucket_rule": item.get("bucket_rule", "reference_snapshot"),
                "default_in_environment_fit": bool(item.get("default_in_environment_fit")),
                "source": item.get("source", "attribution_reference"),
                "missing_policy": item.get("missing_policy", "missing"),
                "coverage_stats": {
                    "sample_count": sample_count,
                    "missing_count": missing_count,
                    "valid_count": sample_count - missing_count,
                    "missing_ratio": missing_count / sample_count if sample_count else None,
                    "exception_count": sum(stats[field_key]["exception_codes"].values()),
                },
                "exception_top_codes": [
                    {"code": code, "count": count}
                    for code, count in stats[field_key]["exception_codes"].most_common()
                ],
                "bucket_distribution": bucket_distribution,
                "sample_refs": _representative_refs(
                    [row for rows in stats[field_key]["buckets"].values() for row in rows]
                ),
            }
        )

    defaults = [
        field["field_key"]
        for field in fields
        if field.get("default_in_environment_fit") is True
    ]
    return {
        "schema": ATTRIBUTION_FIELD_INDEX_SCHEMA,
        "run_id": wide_samples.get("run_id"),
        "source_dir": wide_samples.get("source_dir"),
        "reference_path": wide_samples.get("reference_path"),
        "sample_count": len(samples),
        "field_count": len(fields),
        "environment_fit_default_fields": defaults,
        "environment_fit_pair_whitelist": _environment_pair_whitelist(
            _as_mapping(wide_samples.get("reference_metadata"))
        ),
        "fields": fields,
        "ai_usage_rules": [
            "字段缺失必须按 missing 处理，不能补成 false、0 或中性桶。",
            "default_in_environment_fit 表示第一版默认进入 environment_fit.enriched 的单因子统计。",
            "environment_fit_pair_whitelist 只声明默认二因子组合，三因子以上不在第一版默认输出。",
        ],
    }


def write_attribution_wide_samples(
    wide_samples: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path, Path, Path]:
    """Write wide sample JSON/CSV and field index JSON/Markdown."""

    target_dir = Path(output_dir) if output_dir is not None else Path(str(wide_samples["source_dir"]))
    target_dir.mkdir(parents=True, exist_ok=True)
    field_index = _as_mapping(wide_samples.get("field_index")) or build_attribution_field_index(wide_samples)

    wide_path = target_dir / DEFAULT_WIDE_SAMPLE_JSON
    csv_path = target_dir / DEFAULT_WIDE_SAMPLE_CSV
    index_path = target_dir / DEFAULT_FIELD_INDEX_JSON
    markdown_path = target_dir / DEFAULT_FIELD_INDEX_MARKDOWN

    wide_path.write_text(_to_pretty_json(dict(wide_samples, field_index=field_index)), encoding="utf-8")
    _write_wide_csv(_as_sequence(wide_samples.get("samples")), _field_keys(field_index), csv_path)
    index_path.write_text(_to_pretty_json(field_index), encoding="utf-8")
    markdown_path.write_text(render_attribution_field_index_markdown_zh(field_index), encoding="utf-8")
    return wide_path, csv_path, index_path, markdown_path


def render_attribution_field_index_markdown_zh(index: Mapping[str, Any]) -> str:
    """Render attribution field index as Chinese Markdown."""

    fields = [_as_mapping(item) for item in _as_sequence(index.get("fields"))]
    low_coverage = sorted(
        fields,
        key=lambda item: (
            -float(_as_mapping(item.get("coverage_stats")).get("missing_ratio") or 0.0),
            -int(_as_mapping(item.get("coverage_stats")).get("exception_count") or 0),
            str(item.get("field_key")),
        ),
    )
    default_fields = set(str(item) for item in _as_sequence(index.get("environment_fit_default_fields")))
    lines = [
        "# 归因字段索引",
        "",
        f"- schema: `{index.get('schema')}`",
        f"- run_id: `{index.get('run_id')}`",
        f"- sample_count: `{index.get('sample_count')}`",
        f"- field_count: `{index.get('field_count')}`",
        "",
        "## 覆盖率和异常优先检查",
        "",
        "| 字段 | 样本 | 缺失 | 缺失率 | 异常 | 默认进入 environment_fit | Top桶 |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for field in low_coverage:
        coverage = _as_mapping(field.get("coverage_stats"))
        lines.append(
            "| "
            f"`{field.get('field_key')}` | "
            f"{coverage.get('sample_count')} | "
            f"{coverage.get('missing_count')} | "
            f"{_format_percent(coverage.get('missing_ratio'))} | "
            f"{coverage.get('exception_count')} | "
            f"{'是' if field.get('field_key') in default_fields else '否'} | "
            f"{_escape_cell(_top_bucket(field))} |"
        )

    lines.extend(["", "## 默认进入 environment_fit", ""])
    for field_key in sorted(default_fields):
        lines.append(f"- `{field_key}`")

    lines.extend(["", "## 候选但未默认进入", ""])
    for field in fields:
        field_key = str(field.get("field_key"))
        if field_key not in default_fields:
            lines.append(f"- `{field_key}`")

    lines.extend(["", "## AI 使用规则"])
    for rule in _as_sequence(index.get("ai_usage_rules")):
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def load_attribution_wide_samples(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    """Load attribution_wide_samples.json from a file, directory, or payload."""

    if isinstance(source, Mapping):
        payload = dict(source)
    else:
        path = Path(source)
        if path.is_dir():
            path = path / DEFAULT_WIDE_SAMPLE_JSON
        if not path.exists():
            raise FileNotFoundError(f"attribution wide samples not found: {path}")
        payload = _as_mapping(_load_json_if_exists(path))
    if payload.get("schema") != ATTRIBUTION_WIDE_SAMPLES_SCHEMA:
        raise ValueError(f"invalid attribution wide samples schema: {payload.get('schema')}")
    return payload


def load_attribution_field_index(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    """Load attribution_field_index.json from a file, directory, or payload."""

    if isinstance(source, Mapping):
        payload = dict(source)
    else:
        path = Path(source)
        if path.is_dir():
            path = path / DEFAULT_FIELD_INDEX_JSON
        if not path.exists():
            raise FileNotFoundError(f"attribution field index not found: {path}")
        payload = _as_mapping(_load_json_if_exists(path))
    if payload.get("schema") != ATTRIBUTION_FIELD_INDEX_SCHEMA:
        raise ValueError(f"invalid attribution field index schema: {payload.get('schema')}")
    return payload


def _completed_trade_rows(
    trade_attribution: Mapping[str, Any],
    *,
    trade_lifecycle: Mapping[str, Any],
) -> list[dict[str, Any]]:
    lifecycle_by_index = {
        int(row["trade_index"]): _as_mapping(row)
        for row in _as_sequence(trade_lifecycle.get("lifecycles"))
        if _as_mapping(row).get("trade_index") is not None
    }
    rows = []
    for attribution in _as_sequence(trade_attribution.get("attributions")):
        trade = dict(_as_mapping(attribution))
        trade_index = _optional_int(trade.get("trade_index"))
        lifecycle = lifecycle_by_index.get(trade_index, {}) if trade_index is not None else {}
        trade["profit_contribution"] = _profit_contribution(lifecycle)
        rows.append(trade)
    return rows


def _profit_contribution(lifecycle: Mapping[str, Any]) -> dict[str, Any]:
    buy = 0.0
    sell = 0.0
    commission = 0.0
    for event in _as_sequence(lifecycle.get("events")):
        for execution in _as_sequence(_as_mapping(event).get("executions")):
            row = _as_mapping(execution)
            if str(row.get("event_type", "")).lower() != "completed":
                continue
            gross = _optional_float(row.get("gross_value"))
            if gross is None:
                quantity = _optional_float(row.get("executed_quantity"))
                price = _optional_float(row.get("executed_price"))
                gross = abs(quantity * price) if quantity is not None and price is not None else None
            if gross is None:
                continue
            side = str(row.get("side", "")).lower()
            if side == "buy":
                buy += abs(gross)
            elif side == "sell":
                sell += abs(gross)
            commission += _optional_float(row.get("commission")) or 0.0
    available = buy > 0 and sell > 0
    net_pnl = sell - buy - commission if available else None
    return {
        "contribution_available": available,
        "entry_gross_value": buy if buy else None,
        "exit_gross_value": sell if sell else None,
        "net_pnl": net_pnl,
        "total_commission": commission if commission else None,
        "return_on_entry_value": net_pnl / buy if net_pnl is not None and buy else None,
    }


def _entry_factor_values(trade: Mapping[str, Any]) -> dict[str, Any]:
    event = _as_mapping(trade.get("entry"))
    values = {}
    for factor in _as_sequence(event.get("factors")):
        item = _as_mapping(factor)
        if item.get("missing") is True or item.get("key") is None:
            continue
        values[str(item["key"])] = _jsonable(item.get("value"))
    return values


def _load_reference_snapshot(path_like: str | Path) -> dict[str, Any]:
    path = Path(path_like)
    if not path.exists():
        raise FileNotFoundError(f"reference snapshot does not exist: {path}")
    if path.is_dir():
        json_path = path / "reference.json"
        parquet_path = path / "reference_values.parquet"
        metadata_path = path / "metadata.json"
        metadata = _as_mapping(_load_json_if_exists(metadata_path)) if metadata_path.exists() else {}
        if json_path.exists():
            payload = _as_mapping(_load_json_if_exists(json_path))
            metadata = _as_mapping(payload.get("metadata")) or metadata
            rows = _as_sequence(payload.get("rows") or payload.get("samples"))
        elif parquet_path.exists():
            rows = _parquet_rows(parquet_path)
        else:
            raise FileNotFoundError(f"reference snapshot directory lacks reference.json or reference_values.parquet: {path}")
        return {"source_path": path, "metadata": metadata, "rows": [_as_mapping(row) for row in rows]}

    if path.suffix.lower() in {".parquet", ".pq"}:
        return {"source_path": path, "metadata": {}, "rows": _parquet_rows(path)}
    payload = _load_json_if_exists(path)
    if isinstance(payload, list):
        return {"source_path": path, "metadata": {}, "rows": [_as_mapping(row) for row in payload]}
    payload_map = _as_mapping(payload)
    rows = _as_sequence(payload_map.get("rows") or payload_map.get("samples"))
    if not rows:
        raise ValueError(f"reference snapshot contains no rows: {path}")
    return {"source_path": path, "metadata": _as_mapping(payload_map.get("metadata")), "rows": [_as_mapping(row) for row in rows]}


def _parquet_rows(path: Path) -> list[dict[str, Any]]:
    frame = pd.read_parquet(path)
    return [row.dropna().to_dict() for _, row in frame.iterrows()]


def _field_catalog(reference: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    metadata = _as_mapping(reference.get("metadata"))
    fields = metadata.get("fields")
    catalog: dict[str, dict[str, Any]] = {}
    if isinstance(fields, Mapping):
        for key, value in fields.items():
            catalog[str(key)] = dict(_fallback_field_catalog_item(str(key)), **_as_mapping(value))
    elif isinstance(fields, list):
        for value in fields:
            item = _as_mapping(value)
            key = _as_str(item.get("field_key"))
            if key:
                catalog[key] = dict(_fallback_field_catalog_item(key), **item)
    for row in _as_sequence(reference.get("rows")):
        key = _as_str(_as_mapping(row).get("field_key"))
        if key:
            catalog.setdefault(key, _fallback_field_catalog_item(key))
    return catalog


def _fallback_field_catalog_item(field_key: str) -> dict[str, Any]:
    return {
        "field_key": field_key,
        "label_zh": field_key,
        "value_type": "bucket" if field_key.endswith("_bucket") else "value",
        "timing": "entry" if field_key.startswith("entry.") or "." not in field_key else field_key.split(".", 1)[0],
        "scope": _scope_from_field(field_key),
        "bucket_rule": "reference_snapshot",
        "default_in_environment_fit": field_key in {
            "industry.sw_l1.code",
            "entry.price_position.near_high_20d_bucket",
            "entry.price_position.near_high_60d_bucket",
        },
        "source": "attribution_reference",
        "missing_policy": "missing",
    }


def _environment_default_fields(catalog: Mapping[str, Mapping[str, Any]], metadata: Mapping[str, Any]) -> list[str]:
    configured = [str(item) for item in _as_sequence(metadata.get("environment_fit_default_fields"))]
    if configured:
        return configured
    return sorted(key for key, item in catalog.items() if _as_mapping(item).get("default_in_environment_fit") is True)


def _environment_pair_whitelist(metadata: Mapping[str, Any]) -> list[list[str]]:
    configured = _as_sequence(metadata.get("environment_fit_pair_whitelist"))
    if configured:
        return [[str(part) for part in _as_sequence(pair)] for pair in configured if len(_as_sequence(pair)) == 2]
    return [[left, right] for left, right in DEFAULT_ENVIRONMENT_FIT_PAIR_WHITELIST]


def _reference_rows_by_symbol_field(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        row_map = _as_mapping(row)
        symbol = _as_str(row_map.get("symbol"))
        field_key = _as_str(row_map.get("field_key"))
        if symbol and field_key:
            grouped[(symbol, field_key)].append(row_map)
    for key in grouped:
        grouped[key].sort(key=lambda row: _as_str(row.get("trade_date")) or _as_str(row.get("asof_date")))
    return grouped


def _reference_row_for(
    rows: Sequence[Mapping[str, Any]],
    *,
    entry_date: str,
    max_staleness_trading_days: int,
) -> Mapping[str, Any] | None:
    exact = [row for row in rows if _as_str(row.get("trade_date")) == entry_date]
    if exact:
        return exact[-1]
    valid = [
        row for row in rows
        if (_optional_int(row.get("staleness_trading_days")) is not None
            and (_optional_int(row.get("staleness_trading_days")) or 0) <= max_staleness_trading_days
            and (_as_str(row.get("trade_date")) <= entry_date or not _as_str(row.get("trade_date"))))
    ]
    return valid[-1] if valid else None


def _write_wide_csv(samples: Sequence[Any], field_keys: Sequence[str], path: Path) -> None:
    columns = [
        "trade_index", "symbol", "entry_date", "exit_date", "exit_type", "outcome",
        "exit_reason", "return_pct", "attribution_exception_codes",
    ]
    for field_key in field_keys:
        columns.extend([
            field_key,
            f"{field_key}.bucket",
            f"{field_key}.percentile",
            f"{field_key}.asof_date",
            f"{field_key}.staleness_trading_days",
            f"{field_key}.exception_code",
        ])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for sample in samples:
            sample_map = _as_mapping(sample)
            row = {key: sample_map.get(key) for key in columns if key in sample_map}
            row["attribution_exception_codes"] = ";".join(str(item) for item in _as_sequence(sample_map.get("attribution_exception_codes")))
            field_values = _as_mapping(sample_map.get("field_values"))
            for field_key in field_keys:
                payload = _as_mapping(field_values.get(field_key))
                row[field_key] = payload.get("raw")
                row[f"{field_key}.bucket"] = payload.get("bucket")
                row[f"{field_key}.percentile"] = payload.get("percentile")
                row[f"{field_key}.asof_date"] = payload.get("asof_date")
                row[f"{field_key}.staleness_trading_days"] = payload.get("staleness_trading_days")
                row[f"{field_key}.exception_code"] = ";".join(str(item) for item in _as_sequence(payload.get("exception_codes")))
            writer.writerow(row)


def _field_keys(field_index: Mapping[str, Any]) -> list[str]:
    return [str(_as_mapping(field).get("field_key")) for field in _as_sequence(field_index.get("fields"))]


def _representative_refs(rows: Sequence[Mapping[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    clean = [_as_mapping(row) for row in rows if _as_mapping(row).get("trade_index") is not None]
    if not clean:
        return []
    selected: list[Mapping[str, Any]] = []
    for key, reverse in (("return_pct", True), ("return_pct", False), ("net_pnl", True), ("net_pnl", False)):
        candidates = [row for row in clean if _optional_float(row.get(key)) is not None]
        if candidates:
            selected.append(sorted(candidates, key=lambda row: float(row[key]), reverse=reverse)[0])
    selected.extend(clean)
    refs = []
    seen = set()
    for row in selected:
        trade_index = _optional_int(row.get("trade_index"))
        if trade_index is None or trade_index in seen:
            continue
        seen.add(trade_index)
        refs.append({"kind": "trade", "trade_index": trade_index})
        if len(refs) >= limit:
            break
    return refs


def _top_bucket(field: Mapping[str, Any]) -> str:
    buckets = _as_sequence(field.get("bucket_distribution"))
    if not buckets:
        return "-"
    item = _as_mapping(buckets[0])
    return f"{item.get('value')}({item.get('count')})"


def _missing_field_payload(code: str) -> dict[str, Any]:
    return {
        "raw": None,
        "bucket": None,
        "percentile": None,
        "asof_date": None,
        "staleness_trading_days": None,
        "reference_count": None,
        "exception_codes": [code],
    }


def _scope_from_field(field_key: str) -> str:
    parts = field_key.split(".")
    return parts[1] if parts and parts[0] == "entry" and len(parts) > 1 else parts[0]


def _exception_codes(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item for item in value.split(";") if item]
    return [str(item) for item in _as_sequence(value)]


def _decode_reference_cell(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _stable_value_key(value: Any) -> str:
    return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True)


def _jsonable(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _format_percent(value: Any) -> str:
    number = _optional_float(value)
    if number is None:
        return "-"
    return f"{number * 100:.2f}%"


def _escape_cell(value: Any) -> str:
    return str(value).replace("|", "/") if value is not None else "-"


def _run_id(run_path: Path, run_plan: Mapping[str, Any]) -> str:
    return str(_as_mapping(run_plan.get("run")).get("id", run_path.name))


def _load_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, (list, tuple)) else ()


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_pretty_json(payload: Any) -> str:
    return json.dumps(_jsonable(payload), ensure_ascii=False, indent=2)
