"""Attribution wide samples and field index artifacts."""

from __future__ import annotations

import csv
import json
import math
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

MA60_ATR_MULTIPLE_FIELD = "entry.price_position.ma60_atr_multiple_bucket"
SIGNAL_CLOSE_MA60_ATR_MULTIPLE_FIELD = "entry.price_position.signal_close_ma60_atr_multiple_bucket"
SIGNAL_TO_ENTRY_RETURN_FIELD = "entry.execution.signal_to_entry_return_bucket"
EXIT_REASON_FIELD = "trade.exit.reason"
HOLDING_DAYS_FIELD = "trade.path.holding_days_bucket"
MAX_FAVORABLE_FIELD = "trade.path.max_favorable_return_before_exit_bucket"
MAX_ADVERSE_FIELD = "trade.path.max_adverse_return_before_exit_bucket"
MAX_DRAWDOWN_FIELD = "trade.path.max_drawdown_from_peak_bucket"
FIRST_PROFIT_5PCT_FIELD = "trade.path.first_profit_5pct_days_bucket"
DEA_WATERLINE_AGE_FIELD = "entry.signal_strength.dea_waterline_age_trading_days_bucket"
DEA_VALUE_FIELD = "entry.signal_strength.dea_value_bucket"
MACD_BAR_FIELD = "entry.signal_strength.macd_bar_bucket"
DIF_DEA_DISTANCE_FIELD = "entry.signal_strength.dif_dea_distance_bucket"
MA25_MA60_SPREAD_FIELD = "entry.signal_strength.ma25_above_ma60_spread_bucket"
MA60_SLOPE_20D_FIELD = "entry.signal_strength.ma60_slope_20d_bucket"
SIGNAL_CANDLE_BODY_FIELD = "entry.signal_strength.signal_candle_body_bucket"
SIGNAL_SHADOW_FIELD = "entry.signal_strength.signal_upper_lower_shadow_bucket"
DERIVED_ONLY_FIELDS = {
    EXIT_REASON_FIELD,
    MA60_ATR_MULTIPLE_FIELD,
    SIGNAL_CLOSE_MA60_ATR_MULTIPLE_FIELD,
    SIGNAL_TO_ENTRY_RETURN_FIELD,
    HOLDING_DAYS_FIELD,
    MAX_FAVORABLE_FIELD,
    MAX_ADVERSE_FIELD,
    MAX_DRAWDOWN_FIELD,
    FIRST_PROFIT_5PCT_FIELD,
    DEA_WATERLINE_AGE_FIELD,
    DEA_VALUE_FIELD,
    MACD_BAR_FIELD,
    DIF_DEA_DISTANCE_FIELD,
    MA25_MA60_SPREAD_FIELD,
    MA60_SLOPE_20D_FIELD,
    SIGNAL_CANDLE_BODY_FIELD,
    SIGNAL_SHADOW_FIELD,
}

EXIT_REASON_ENTRY_FACTOR_PAIRS: tuple[tuple[str, str], ...] = (
    (EXIT_REASON_FIELD, MA60_ATR_MULTIPLE_FIELD),
    (EXIT_REASON_FIELD, "entry.price_position.near_high_60d_bucket"),
    (EXIT_REASON_FIELD, "entry.volatility.atr_20d_bucket"),
    (EXIT_REASON_FIELD, "entry.stop_fit.fixed_atr_multiple_bucket"),
    (EXIT_REASON_FIELD, DEA_WATERLINE_AGE_FIELD),
    (EXIT_REASON_FIELD, DEA_VALUE_FIELD),
    (EXIT_REASON_FIELD, MACD_BAR_FIELD),
    (EXIT_REASON_FIELD, DIF_DEA_DISTANCE_FIELD),
    (EXIT_REASON_FIELD, MA25_MA60_SPREAD_FIELD),
    (EXIT_REASON_FIELD, MA60_SLOPE_20D_FIELD),
    (EXIT_REASON_FIELD, SIGNAL_CANDLE_BODY_FIELD),
    (EXIT_REASON_FIELD, SIGNAL_SHADOW_FIELD),
)

DERIVED_FIELD_CATALOG: dict[str, dict[str, Any]] = {
    EXIT_REASON_FIELD: {
        "field_key": EXIT_REASON_FIELD,
        "label_zh": "退出原因",
        "value_type": "category",
        "timing": "exit",
        "scope": "exit",
        "bucket_rule": "reason_code",
        "default_in_environment_fit": False,
        "source": "closed_trade",
        "missing_policy": "missing",
    },
    MA60_ATR_MULTIPLE_FIELD: {
        "field_key": MA60_ATR_MULTIPLE_FIELD,
        "label_zh": "入场价距MA60的ATR倍数桶",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "price_position",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": True,
        "source": "trade_lifecycle+attribution_reference",
        "missing_policy": "missing",
    },
    SIGNAL_CLOSE_MA60_ATR_MULTIPLE_FIELD: {
        "field_key": SIGNAL_CLOSE_MA60_ATR_MULTIPLE_FIELD,
        "label_zh": "信号日close距MA60的ATR倍数桶",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "price_position",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": False,
        "source": "trade_lifecycle+attribution_reference",
        "missing_policy": "missing",
    },
    SIGNAL_TO_ENTRY_RETURN_FIELD: {
        "field_key": SIGNAL_TO_ENTRY_RETURN_FIELD,
        "label_zh": "信号日close到入场成交价涨跌桶",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "execution",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": False,
        "source": "trade_lifecycle",
        "missing_policy": "missing",
    },
    HOLDING_DAYS_FIELD: {
        "field_key": HOLDING_DAYS_FIELD,
        "label_zh": "持仓交易日数桶",
        "value_type": "bucket",
        "timing": "post_trade",
        "scope": "path",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": False,
        "source": "daily_price_cache",
        "missing_policy": "missing",
    },
    MAX_FAVORABLE_FIELD: {
        "field_key": MAX_FAVORABLE_FIELD,
        "label_zh": "退出前最大浮盈桶",
        "value_type": "bucket",
        "timing": "post_trade",
        "scope": "path",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": False,
        "source": "daily_price_cache",
        "missing_policy": "missing",
    },
    MAX_ADVERSE_FIELD: {
        "field_key": MAX_ADVERSE_FIELD,
        "label_zh": "退出前最大浮亏桶",
        "value_type": "bucket",
        "timing": "post_trade",
        "scope": "path",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": False,
        "source": "daily_price_cache",
        "missing_policy": "missing",
    },
    MAX_DRAWDOWN_FIELD: {
        "field_key": MAX_DRAWDOWN_FIELD,
        "label_zh": "持仓最高点后最大回撤桶",
        "value_type": "bucket",
        "timing": "post_trade",
        "scope": "path",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": False,
        "source": "daily_price_cache",
        "missing_policy": "missing",
    },
    FIRST_PROFIT_5PCT_FIELD: {
        "field_key": FIRST_PROFIT_5PCT_FIELD,
        "label_zh": "首次达到5%浮盈交易日数桶",
        "value_type": "bucket",
        "timing": "post_trade",
        "scope": "path",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": False,
        "source": "daily_price_cache",
        "missing_policy": "missing",
    },
    DEA_WATERLINE_AGE_FIELD: {
        "field_key": DEA_WATERLINE_AGE_FIELD,
        "label_zh": "DEA上水后交易日数桶",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "signal_strength",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": True,
        "source": "trade_lifecycle",
        "missing_policy": "missing",
    },
    DEA_VALUE_FIELD: {
        "field_key": DEA_VALUE_FIELD,
        "label_zh": "DEA强弱桶（DEA/信号日close）",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "signal_strength",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": True,
        "source": "trade_lifecycle",
        "missing_policy": "missing",
    },
    MACD_BAR_FIELD: {
        "field_key": MACD_BAR_FIELD,
        "label_zh": "MACD柱强弱桶（MACD柱/信号日close）",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "signal_strength",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": True,
        "source": "trade_lifecycle",
        "missing_policy": "missing",
    },
    DIF_DEA_DISTANCE_FIELD: {
        "field_key": DIF_DEA_DISTANCE_FIELD,
        "label_zh": "DIF-DEA距离桶（/信号日close）",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "signal_strength",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": True,
        "source": "trade_lifecycle",
        "missing_policy": "missing",
    },
    MA25_MA60_SPREAD_FIELD: {
        "field_key": MA25_MA60_SPREAD_FIELD,
        "label_zh": "MA25相对MA60乖离桶",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "signal_strength",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": True,
        "source": "trade_lifecycle",
        "missing_policy": "missing",
    },
    MA60_SLOPE_20D_FIELD: {
        "field_key": MA60_SLOPE_20D_FIELD,
        "label_zh": "MA60近20日斜率桶",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "signal_strength",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": True,
        "source": "daily_price_cache",
        "missing_policy": "missing",
    },
    SIGNAL_CANDLE_BODY_FIELD: {
        "field_key": SIGNAL_CANDLE_BODY_FIELD,
        "label_zh": "信号日阴线实体大小桶",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "signal_strength",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": True,
        "source": "trade_lifecycle",
        "missing_policy": "missing",
    },
    SIGNAL_SHADOW_FIELD: {
        "field_key": SIGNAL_SHADOW_FIELD,
        "label_zh": "信号日上下影线结构桶",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "signal_strength",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": True,
        "source": "daily_price_cache",
        "missing_policy": "missing",
    },
}


def build_attribution_wide_samples(
    run_dir: str | Path,
    *,
    reference_snapshot: str | Path,
    daily_price_cache_dir: str | Path | None = None,
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
    field_catalog.update(DERIVED_FIELD_CATALOG)
    completed_trades = _completed_trade_rows(trade_attribution, trade_lifecycle=trade_lifecycle)
    price_context = _load_daily_price_context(daily_price_cache_dir, completed_trades)

    samples = []
    for trade in completed_trades:
        trade_index = _optional_int(trade.get("trade_index"))
        symbol = _as_str(trade.get("symbol"))
        entry_date = _as_str(trade.get("entry_date"))
        signal_date = _as_str(trade.get("signal_date")) or entry_date
        if trade_index is None or not symbol or not entry_date:
            continue

        field_values: dict[str, dict[str, Any]] = {}
        exception_codes: set[str] = set()
        for field_key in field_catalog:
            if field_key in DERIVED_ONLY_FIELDS:
                continue
            row = _reference_row_for(
                reference_rows.get((symbol, field_key), ()),
                entry_date=signal_date,
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

        _add_execution_derived_fields(field_values, trade=trade, signal_date=signal_date)
        _add_trade_path_fields(field_values, trade=trade, price_context=price_context)
        _add_entry_signal_strength_fields(field_values, trade=trade, signal_date=signal_date, price_context=price_context)
        _add_exit_reason_field(field_values, trade=trade)
        for payload in field_values.values():
            exception_codes.update(_exception_codes(_as_mapping(payload).get("exception_codes")))

        samples.append(
            {
                "trade_index": trade_index,
                "symbol": symbol,
                "signal_date": signal_date,
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
        "daily_price_cache_path": str(daily_price_cache_dir) if daily_price_cache_dir is not None else None,
        "sample_count": len(samples),
        "field_count": len(field_catalog),
        "environment_fit_default_fields": _environment_default_fields(field_catalog, reference["metadata"]),
        "environment_fit_pair_whitelist": _environment_pair_whitelist(reference["metadata"]),
        "outcome_diagnostic_pair_whitelist": _outcome_diagnostic_pair_whitelist(),
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
        "outcome_diagnostic_pair_whitelist": _outcome_diagnostic_pair_whitelist(),
        "fields": fields,
        "ai_usage_rules": [
            "字段缺失必须按 missing 处理，不能补成 false、0 或中性桶。",
            "default_in_environment_fit 表示第一版默认进入 environment_fit.enriched 的单因子统计。",
            "environment_fit_pair_whitelist 只声明入场前或入场时可见因子的默认二因子组合，三因子以上不在第一版默认输出。",
            "timing=post_trade 或 exit 的字段只能用于事后诊断，不能进入 environment_fit 排名。",
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

    diagnostic_fields = [
        field
        for field in fields
        if str(field.get("timing")) in {"exit", "post_trade"} or str(field.get("field_key")).startswith("trade.")
    ]
    if diagnostic_fields:
        lines.extend(["", "## 事后诊断字段（不进入 environment_fit）", ""])
        for field in diagnostic_fields:
            lines.append(f"- `{field.get('field_key')}`: {field.get('label_zh', field.get('field_key'))}")

    outcome_pairs = _as_sequence(index.get("outcome_diagnostic_pair_whitelist"))
    if outcome_pairs:
        lines.extend(["", "## outcome_diagnostic 二因子白名单", ""])
        for pair in outcome_pairs:
            parts = [str(part) for part in _as_sequence(pair)]
            if len(parts) == 2:
                lines.append(f"- `{parts[0]}` x `{parts[1]}`")

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
        trade.update(_entry_lifecycle_context(lifecycle))
        rows.append(trade)
    return rows


def _entry_lifecycle_context(lifecycle: Mapping[str, Any]) -> dict[str, Any]:
    result = {
        "signal_date": None,
        "signal_close": None,
        "signal_ma60": None,
        "entry_price": _optional_float(lifecycle.get("entry_price")),
        "entry_execution_price": None,
    }
    for event in _as_sequence(lifecycle.get("events")):
        row = _as_mapping(event)
        if str(row.get("event_type")) != "entry":
            continue
        values = _as_mapping(row.get("values"))
        result["signal_date"] = _as_str(values.get("signal_trade_date")) or None
        result["signal_close"] = _optional_float(values.get("close"))
        result["signal_ma60"] = _optional_float(values.get("ma60"))
        for execution in _as_sequence(row.get("executions")):
            execution_row = _as_mapping(execution)
            if str(execution_row.get("event_type", "")).lower() != "completed":
                continue
            result["entry_execution_price"] = _optional_float(execution_row.get("executed_price"))
            break
        break
    if result["entry_price"] is None:
        result["entry_price"] = result["entry_execution_price"]
    return result


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


def _load_daily_price_context(
    daily_price_cache_dir: str | Path | None,
    trades: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if daily_price_cache_dir is None:
        return {}
    root = Path(daily_price_cache_dir)
    daily_dir = root / "daily" if (root / "daily").exists() else root
    if not daily_dir.exists():
        return {}
    symbols = {
        _as_str(trade.get("symbol"))
        for trade in trades
        if _as_str(trade.get("symbol"))
    }
    if not symbols:
        return {}

    frames = []
    for path in sorted(daily_dir.glob("*.parquet")):
        frame = pd.read_parquet(path)
        if "symbol" not in frame.columns and "ts_code" in frame.columns:
            frame = frame.rename(columns={"ts_code": "symbol"})
        required = {"symbol", "trade_date", "open", "high", "low", "close"}
        if not required.issubset(frame.columns):
            continue
        frame = frame[["symbol", "trade_date", "open", "high", "low", "close"]]
        frame = frame[frame["symbol"].astype(str).isin(symbols)]
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return {}

    data = pd.concat(frames, ignore_index=True)
    data["symbol"] = data["symbol"].astype(str)
    data["trade_date"] = pd.to_datetime(data["trade_date"]).dt.strftime("%Y-%m-%d")
    for column in ("open", "high", "low", "close"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=["symbol", "trade_date", "open", "high", "low", "close"])
    data = data.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    grouped = data.groupby("symbol", sort=False)
    data["ma25"] = grouped["close"].transform(lambda value: value.rolling(25, min_periods=25).mean())
    data["ma60"] = grouped["close"].transform(lambda value: value.rolling(60, min_periods=60).mean())
    data["ma60_20d_ago"] = grouped["ma60"].shift(20)
    data["ma60_slope_20d"] = data["ma60"] / data["ma60_20d_ago"] - 1.0
    ema12 = grouped["close"].transform(lambda value: value.ewm(span=12, adjust=False).mean())
    ema26 = grouped["close"].transform(lambda value: value.ewm(span=26, adjust=False).mean())
    data["macd_dif"] = ema12 - ema26
    data["macd_dea"] = data.groupby("symbol", sort=False)["macd_dif"].transform(
        lambda value: value.ewm(span=9, adjust=False).mean()
    )
    data["macd_bar"] = 2.0 * (data["macd_dif"] - data["macd_dea"])

    by_symbol = {
        str(symbol): group.reset_index(drop=True)
        for symbol, group in data.groupby("symbol", sort=False)
    }
    by_symbol_date = {
        (str(row.symbol), str(row.trade_date)): row._asdict()
        for row in data.itertuples(index=False)
    }
    return {
        "source_path": str(daily_dir),
        "by_symbol": by_symbol,
        "by_symbol_date": by_symbol_date,
    }


def _add_trade_path_fields(
    field_values: dict[str, dict[str, Any]],
    *,
    trade: Mapping[str, Any],
    price_context: Mapping[str, Any],
) -> None:
    symbol = _as_str(trade.get("symbol"))
    entry_date = _as_str(trade.get("entry_date"))
    exit_date = _as_str(trade.get("exit_date"))
    entry_price = _optional_float(trade.get("entry_price")) or _optional_float(trade.get("entry_execution_price"))
    asof_date = exit_date or entry_date
    rows = _price_rows_for_trade(price_context, symbol=symbol, entry_date=entry_date, exit_date=exit_date)
    if rows is None or rows.empty or entry_price is None or entry_price <= 0:
        for field_key in (HOLDING_DAYS_FIELD, MAX_FAVORABLE_FIELD, MAX_ADVERSE_FIELD, MAX_DRAWDOWN_FIELD, FIRST_PROFIT_5PCT_FIELD):
            field_values[field_key] = _derived_payload(
                raw=None,
                bucket=None,
                asof_date=asof_date,
                reference_count=None,
                exception_codes=["path_price_missing"],
            )
        return

    holding_days = int(len(rows))
    high = pd.to_numeric(rows["high"], errors="coerce")
    low = pd.to_numeric(rows["low"], errors="coerce")
    max_favorable = _optional_float(high.max()) / entry_price - 1.0 if not high.empty and pd.notna(high.max()) else None
    max_adverse = _optional_float(low.min()) / entry_price - 1.0 if not low.empty and pd.notna(low.min()) else None

    peak = None
    max_drawdown = 0.0
    for row in rows.itertuples(index=False):
        row_high = _optional_float(getattr(row, "high", None))
        row_low = _optional_float(getattr(row, "low", None))
        if row_high is None or row_low is None or row_high <= 0:
            continue
        peak = row_high if peak is None else max(peak, row_high)
        if peak and peak > 0:
            max_drawdown = max(max_drawdown, max(0.0, 1.0 - row_low / peak))

    first_profit_day = None
    target = entry_price * 1.05
    for index, row in enumerate(rows.itertuples(index=False), start=1):
        row_high = _optional_float(getattr(row, "high", None))
        if row_high is not None and row_high >= target:
            first_profit_day = index
            break

    field_values[HOLDING_DAYS_FIELD] = _derived_payload(
        raw=holding_days,
        bucket=_holding_days_bucket(holding_days),
        asof_date=asof_date,
        reference_count=holding_days,
        exception_codes=[],
    )
    field_values[MAX_FAVORABLE_FIELD] = _derived_payload(
        raw=max_favorable,
        bucket=_max_favorable_bucket(max_favorable),
        asof_date=asof_date,
        reference_count=holding_days,
        exception_codes=[] if max_favorable is not None else ["path_price_missing"],
    )
    field_values[MAX_ADVERSE_FIELD] = _derived_payload(
        raw=max_adverse,
        bucket=_max_adverse_bucket(max_adverse),
        asof_date=asof_date,
        reference_count=holding_days,
        exception_codes=[] if max_adverse is not None else ["path_price_missing"],
    )
    field_values[MAX_DRAWDOWN_FIELD] = _derived_payload(
        raw=max_drawdown,
        bucket=_drawdown_bucket(max_drawdown),
        asof_date=asof_date,
        reference_count=holding_days,
        exception_codes=[],
    )
    field_values[FIRST_PROFIT_5PCT_FIELD] = _derived_payload(
        raw=first_profit_day,
        bucket=_first_profit_days_bucket(first_profit_day),
        asof_date=asof_date,
        reference_count=holding_days,
        exception_codes=[],
    )


def _add_entry_signal_strength_fields(
    field_values: dict[str, dict[str, Any]],
    *,
    trade: Mapping[str, Any],
    signal_date: str,
    price_context: Mapping[str, Any],
) -> None:
    entry_factors = _entry_factor_values(trade)
    signal_row = _as_mapping(
        _price_row_for(price_context, symbol=_as_str(trade.get("symbol")), trade_date=signal_date)
    )
    signal_close = (
        _optional_float(signal_row.get("close"))
        or _optional_float(trade.get("signal_close"))
        or _optional_float(entry_factors.get("symbol.close"))
    )
    signal_open = _optional_float(signal_row.get("open")) or _optional_float(entry_factors.get("symbol.open"))
    signal_ma60 = (
        _optional_float(trade.get("signal_ma60"))
        or _optional_float(entry_factors.get("symbol.ma.ma60"))
        or _optional_float(signal_row.get("ma60"))
    )
    dea = _optional_float(entry_factors.get("symbol.macd.dea")) or _optional_float(signal_row.get("macd_dea"))
    dif = _optional_float(entry_factors.get("symbol.macd.dif")) or _optional_float(signal_row.get("macd_dif"))
    macd_bar = _optional_float(entry_factors.get("symbol.macd.macd_bar")) or _optional_float(signal_row.get("macd_bar"))
    if macd_bar is None and dif is not None and dea is not None:
        macd_bar = 2.0 * (dif - dea)
    ma25 = _optional_float(entry_factors.get("symbol.ma.ma25")) or _optional_float(signal_row.get("ma25"))
    age = _optional_int(entry_factors.get("symbol.macd.dea_waterline_age_trading_days"))

    field_values[DEA_WATERLINE_AGE_FIELD] = _derived_payload(
        raw=age,
        bucket=_dea_waterline_age_bucket(age),
        asof_date=signal_date,
        reference_count=None,
        exception_codes=[] if age is not None else ["signal_strength_missing"],
    )

    dea_ratio = dea / signal_close if dea is not None and signal_close and signal_close > 0 else None
    field_values[DEA_VALUE_FIELD] = _derived_payload(
        raw=dea_ratio,
        bucket=_positive_strength_bucket(dea_ratio),
        asof_date=signal_date,
        reference_count=None,
        exception_codes=[] if dea_ratio is not None else ["signal_strength_missing"],
    )

    macd_bar_ratio = macd_bar / signal_close if macd_bar is not None and signal_close and signal_close > 0 else None
    field_values[MACD_BAR_FIELD] = _derived_payload(
        raw=macd_bar_ratio,
        bucket=_signed_strength_bucket(macd_bar_ratio),
        asof_date=signal_date,
        reference_count=None,
        exception_codes=[] if macd_bar_ratio is not None else ["signal_strength_missing"],
    )

    dif_dea_ratio = (dif - dea) / signal_close if dif is not None and dea is not None and signal_close and signal_close > 0 else None
    field_values[DIF_DEA_DISTANCE_FIELD] = _derived_payload(
        raw=dif_dea_ratio,
        bucket=_signed_strength_bucket(dif_dea_ratio),
        asof_date=signal_date,
        reference_count=None,
        exception_codes=[] if dif_dea_ratio is not None else ["signal_strength_missing"],
    )

    ma_spread = (ma25 - signal_ma60) / signal_ma60 if ma25 is not None and signal_ma60 and signal_ma60 > 0 else None
    field_values[MA25_MA60_SPREAD_FIELD] = _derived_payload(
        raw=ma_spread,
        bucket=_ma_spread_bucket(ma_spread),
        asof_date=signal_date,
        reference_count=None,
        exception_codes=[] if ma_spread is not None else ["signal_strength_missing"],
    )

    ma60_slope = _optional_float(_as_mapping(signal_row).get("ma60_slope_20d"))
    field_values[MA60_SLOPE_20D_FIELD] = _derived_payload(
        raw=ma60_slope,
        bucket=_ma60_slope_bucket(ma60_slope),
        asof_date=signal_date,
        reference_count=None,
        exception_codes=[] if ma60_slope is not None else ["path_price_missing"],
    )

    body = None
    if signal_open is not None and signal_close is not None and signal_close > 0:
        body = abs(signal_open - signal_close) / signal_close
    field_values[SIGNAL_CANDLE_BODY_FIELD] = _derived_payload(
        raw=body,
        bucket=_candle_body_bucket(body),
        asof_date=signal_date,
        reference_count=None,
        exception_codes=[] if body is not None else ["signal_strength_missing"],
    )

    shadow_payload, shadow_bucket = _signal_shadow_payload(signal_row, signal_open=signal_open, signal_close=signal_close)
    field_values[SIGNAL_SHADOW_FIELD] = _derived_payload(
        raw=shadow_payload,
        bucket=shadow_bucket,
        asof_date=signal_date,
        reference_count=None,
        exception_codes=[] if shadow_bucket is not None else ["path_price_missing"],
    )


def _add_exit_reason_field(field_values: dict[str, dict[str, Any]], *, trade: Mapping[str, Any]) -> None:
    exit_reason = _as_str(trade.get("exit_reason")) or None
    field_values[EXIT_REASON_FIELD] = _derived_payload(
        raw=exit_reason,
        bucket=exit_reason,
        asof_date=_as_str(trade.get("exit_date")),
        reference_count=None,
        exception_codes=[] if exit_reason else ["exit_reason_missing"],
    )


def _price_rows_for_trade(
    price_context: Mapping[str, Any],
    *,
    symbol: str,
    entry_date: str,
    exit_date: str,
) -> pd.DataFrame | None:
    by_symbol = _as_mapping(price_context.get("by_symbol"))
    frame = by_symbol.get(symbol)
    if not isinstance(frame, pd.DataFrame) or not entry_date or not exit_date:
        return None
    return frame[(frame["trade_date"] >= entry_date) & (frame["trade_date"] <= exit_date)]


def _price_row_for(price_context: Mapping[str, Any], *, symbol: str, trade_date: str) -> Mapping[str, Any] | None:
    return _as_mapping(price_context.get("by_symbol_date")).get((symbol, trade_date))


def _add_execution_derived_fields(
    field_values: dict[str, dict[str, Any]],
    *,
    trade: Mapping[str, Any],
    signal_date: str,
) -> None:
    entry_factors = _entry_factor_values(trade)
    signal_close = _optional_float(trade.get("signal_close")) or _optional_float(entry_factors.get("symbol.close"))
    signal_ma60 = _optional_float(trade.get("signal_ma60")) or _optional_float(entry_factors.get("symbol.ma.ma60"))
    entry_price = _optional_float(trade.get("entry_execution_price")) or _optional_float(trade.get("entry_price"))
    atr_pct = _optional_float(_as_mapping(field_values.get("entry.volatility.atr_20d_bucket")).get("raw"))
    atr_abs = atr_pct * signal_close if atr_pct is not None and signal_close is not None else None

    signal_multiple = None
    if signal_close is not None and signal_ma60 is not None and atr_abs is not None and atr_abs > 0:
        signal_multiple = (signal_close - signal_ma60) / atr_abs
    else:
        signal_multiple = _optional_float(
            _as_mapping(field_values.get(SIGNAL_CLOSE_MA60_ATR_MULTIPLE_FIELD)).get("raw")
        )
        if signal_multiple is None:
            signal_multiple = _optional_float(_as_mapping(field_values.get(MA60_ATR_MULTIPLE_FIELD)).get("raw"))

    source_payload = dict(_as_mapping(field_values.get(SIGNAL_CLOSE_MA60_ATR_MULTIPLE_FIELD)))
    if not source_payload:
        source_payload = dict(_as_mapping(field_values.get(MA60_ATR_MULTIPLE_FIELD)))
    field_values[SIGNAL_CLOSE_MA60_ATR_MULTIPLE_FIELD] = _derived_payload(
        raw=signal_multiple,
        bucket=_atr_multiple_bucket(signal_multiple),
        asof_date=signal_date,
        reference_count=_optional_int(source_payload.get("reference_count")),
        exception_codes=[] if signal_multiple is not None else ["execution_derived_missing"],
    )

    actual_multiple = None
    if entry_price is not None and signal_ma60 is not None and atr_abs is not None and atr_abs > 0:
        actual_multiple = (entry_price - signal_ma60) / atr_abs
    field_values[MA60_ATR_MULTIPLE_FIELD] = _derived_payload(
        raw=actual_multiple,
        bucket=_atr_multiple_bucket(actual_multiple),
        asof_date=signal_date,
        reference_count=_optional_int(source_payload.get("reference_count")),
        exception_codes=[] if actual_multiple is not None else ["execution_derived_missing"],
    )

    signal_to_entry_return = None
    if entry_price is not None and signal_close is not None and signal_close > 0:
        signal_to_entry_return = entry_price / signal_close - 1.0
    field_values[SIGNAL_TO_ENTRY_RETURN_FIELD] = _derived_payload(
        raw=signal_to_entry_return,
        bucket=_signal_to_entry_return_bucket(signal_to_entry_return),
        asof_date=signal_date,
        reference_count=None,
        exception_codes=[] if signal_to_entry_return is not None else ["execution_derived_missing"],
    )


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
    defaults = configured or []
    for key in sorted(catalog):
        if _as_mapping(catalog[key]).get("default_in_environment_fit") is True and key not in defaults:
            defaults.append(key)
    return defaults


def _environment_pair_whitelist(metadata: Mapping[str, Any]) -> list[list[str]]:
    configured = _as_sequence(metadata.get("environment_fit_pair_whitelist"))
    pairs = []
    if configured:
        pairs.extend([[str(part) for part in _as_sequence(pair)] for pair in configured if len(_as_sequence(pair)) == 2])
    else:
        pairs.extend([[left, right] for left, right in DEFAULT_ENVIRONMENT_FIT_PAIR_WHITELIST])
    return pairs


def _outcome_diagnostic_pair_whitelist() -> list[list[str]]:
    return [[left, right] for left, right in EXIT_REASON_ENTRY_FACTOR_PAIRS]


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
    valid = []
    for row in rows:
        row_date = _as_str(row.get("trade_date")) or _as_str(row.get("asof_date"))
        if not row_date or row_date > entry_date:
            continue
        merge_staleness = _trading_day_distance(row_date, entry_date)
        if merge_staleness is not None and merge_staleness <= max_staleness_trading_days:
            valid.append(row)
    return valid[-1] if valid else None


def _trading_day_distance(start_date: str, end_date: str) -> int | None:
    if start_date > end_date:
        return None
    try:
        return max(len(pd.bdate_range(start=start_date, end=end_date)) - 1, 0)
    except (TypeError, ValueError):
        return None


def _write_wide_csv(samples: Sequence[Any], field_keys: Sequence[str], path: Path) -> None:
    columns = [
        "trade_index", "symbol", "signal_date", "entry_date", "exit_date", "exit_type", "outcome",
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


def _derived_payload(
    *,
    raw: Any,
    bucket: Any,
    asof_date: str,
    reference_count: int | None,
    exception_codes: Sequence[str],
) -> dict[str, Any]:
    return {
        "raw": _jsonable(raw),
        "bucket": _jsonable(bucket),
        "percentile": None,
        "asof_date": asof_date,
        "staleness_trading_days": 0,
        "reference_count": reference_count,
        "exception_codes": list(exception_codes),
    }


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


def _signal_to_entry_return_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number < -0.05:
        return "gap_down_gt_5pct"
    if number < -0.02:
        return "gap_down_2_5pct"
    if number <= 0.02:
        return "flat_minus2_to_plus2pct"
    if number <= 0.05:
        return "gap_up_2_5pct"
    return "gap_up_gt_5pct"


def _holding_days_bucket(value: Any) -> str | None:
    number = _optional_int(value)
    if number is None:
        return None
    if number <= 3:
        return "d1_3"
    if number <= 10:
        return "d4_10"
    if number <= 20:
        return "d11_20"
    if number <= 40:
        return "d21_40"
    return "gt_40d"


def _max_favorable_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number < 0:
        return "never_positive"
    if number < 0.05:
        return "0_5pct"
    if number < 0.10:
        return "5_10pct"
    if number < 0.20:
        return "10_20pct"
    if number < 0.40:
        return "20_40pct"
    return "gte_40pct"


def _max_adverse_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number >= 0:
        return "no_adverse"
    if number >= -0.05:
        return "0_to_minus5pct"
    if number >= -0.10:
        return "minus5_to_minus10pct"
    if number >= -0.20:
        return "minus10_to_minus20pct"
    return "lt_minus20pct"


def _drawdown_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number < 0.05:
        return "0_5pct"
    if number < 0.10:
        return "5_10pct"
    if number < 0.20:
        return "10_20pct"
    if number < 0.40:
        return "20_40pct"
    return "gte_40pct"


def _first_profit_days_bucket(value: Any) -> str | None:
    number = _optional_int(value)
    if number is None:
        return "never"
    if number <= 1:
        return "day_1"
    if number <= 3:
        return "day_2_3"
    if number <= 10:
        return "day_4_10"
    if number <= 20:
        return "day_11_20"
    return "gt_20d"


def _dea_waterline_age_bucket(value: Any) -> str | None:
    number = _optional_int(value)
    if number is None:
        return None
    if number <= 0:
        return "day_0"
    if number <= 3:
        return "day_1_3"
    if number <= 7:
        return "day_4_7"
    if number <= 14:
        return "day_8_14"
    return "gt_14d"


def _positive_strength_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number <= 0:
        return "lte_0"
    if number < 0.001:
        return "0_0p1pct"
    if number < 0.003:
        return "0p1_0p3pct"
    if number < 0.006:
        return "0p3_0p6pct"
    return "gte_0p6pct"


def _signed_strength_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number <= 0:
        return "lte_0"
    if number < 0.001:
        return "0_0p1pct"
    if number < 0.003:
        return "0p1_0p3pct"
    if number < 0.006:
        return "0p3_0p6pct"
    return "gte_0p6pct"


def _ma_spread_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number <= 0:
        return "ma25_lte_ma60"
    if number < 0.02:
        return "0_2pct"
    if number < 0.05:
        return "2_5pct"
    if number < 0.10:
        return "5_10pct"
    return "gte_10pct"


def _ma60_slope_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number < -0.05:
        return "down_gt_5pct"
    if number < 0:
        return "down_0_5pct"
    if number < 0.02:
        return "flat_0_2pct"
    if number < 0.05:
        return "up_2_5pct"
    return "up_gt_5pct"


def _candle_body_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number < 0.01:
        return "lt_1pct"
    if number < 0.03:
        return "1_3pct"
    if number < 0.05:
        return "3_5pct"
    return "gte_5pct"


def _signal_shadow_payload(
    signal_row: Mapping[str, Any] | None,
    *,
    signal_open: float | None,
    signal_close: float | None,
) -> tuple[dict[str, float] | None, str | None]:
    row = _as_mapping(signal_row)
    high = _optional_float(row.get("high"))
    low = _optional_float(row.get("low"))
    if high is None or low is None or signal_open is None or signal_close is None or signal_close <= 0:
        return None, None
    upper = max(0.0, high - max(signal_open, signal_close)) / signal_close
    lower = max(0.0, min(signal_open, signal_close) - low) / signal_close
    payload = {"upper_shadow_pct": upper, "lower_shadow_pct": lower}
    if upper < 0.01 and lower < 0.01:
        return payload, "short_shadows"
    if upper >= lower * 2 and upper >= 0.01:
        return payload, "long_upper_shadow"
    if lower >= upper * 2 and lower >= 0.01:
        return payload, "long_lower_shadow"
    if upper >= 0.01 and lower >= 0.01:
        return payload, "both_long_shadows"
    return payload, "balanced_shadows"


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
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _to_pretty_json(payload: Any) -> str:
    return json.dumps(_jsonable(payload), ensure_ascii=False, indent=2)
