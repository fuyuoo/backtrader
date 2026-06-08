"""Bucketed attribution matrices for persisted trade attribution artifacts."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any


ATTRIBUTION_MATRIX_SCHEMA = "attbacktrader.attribution_matrix.v1"

_KDJ_BUCKETS = ("<13", "13-30", "30-50", "50-80", ">=80")
_DEA_AGE_BUCKETS = ("0-2", "3-5", "6-10", "11-14", ">14")
_POST_EXIT_THRESHOLDS = (0.02, 0.05, 0.10)


def build_attribution_matrix(
    run_dir: str | Path,
    *,
    min_sample_count: int = 5,
    top_n: int = 50,
) -> dict[str, Any]:
    """Build bucketed entry/add-on/post-exit attribution matrices for AI review."""

    if min_sample_count <= 0:
        raise ValueError("min_sample_count must be greater than 0")
    if top_n <= 0:
        raise ValueError("top_n must be greater than 0")

    run_path = Path(run_dir)
    trade_attribution = _read_json(run_path / "trade_attribution.json")
    post_exit = _read_optional_json(run_path / "post_exit_analysis.json")
    attributions = [_as_mapping(item) for item in _as_sequence(trade_attribution.get("attributions"))]
    post_exit_by_key = _post_exit_by_trade_key(post_exit)

    matrices = [
        _matrix(
            "entry_dea_symbol_kdj",
            "入场 DEA 上水天数 x 个股 KDJ J",
            _event_records(attributions, timing="entry", post_exit_by_key=post_exit_by_key),
            dimensions=(
                _dimension("dea_age", "symbol.macd.dea_waterline_age_trading_days", _dea_age_bucket),
                _dimension("symbol_kdj_j", "symbol.kdj.j", _kdj_j_bucket),
            ),
            min_sample_count=min_sample_count,
            top_n=top_n,
        ),
        _matrix(
            "entry_kdj_stack",
            "入场 个股 KDJ J x 行业 KDJ J x 沪深300 KDJ J",
            _event_records(attributions, timing="entry", post_exit_by_key=post_exit_by_key),
            dimensions=(
                _dimension("symbol_kdj_j", "symbol.kdj.j", _kdj_j_bucket),
                _dimension("industry_kdj_j", "industry.kdj.j", _kdj_j_bucket),
                _dimension("market_hs300_kdj_j", "market.hs300.kdj.j", _kdj_j_bucket),
            ),
            min_sample_count=min_sample_count,
            top_n=top_n,
        ),
        _matrix(
            "add_on_dea_symbol_kdj",
            "加仓 DEA 上水天数 x 个股 KDJ J",
            _event_records(attributions, timing="add_on", post_exit_by_key=post_exit_by_key),
            dimensions=(
                _dimension("dea_age", "symbol.macd.dea_waterline_age_trading_days", _dea_age_bucket),
                _dimension("symbol_kdj_j", "symbol.kdj.j", _kdj_j_bucket),
            ),
            min_sample_count=min_sample_count,
            top_n=top_n,
        ),
        _matrix(
            "entry_industry_trend_market_kdj",
            "入场 行业趋势 x 沪深300 KDJ J",
            _event_records(attributions, timing="entry", post_exit_by_key=post_exit_by_key),
            dimensions=(
                _dimension("industry_trend_state", "industry.ma.trend_state", _category_bucket),
                _dimension("market_hs300_kdj_j", "market.hs300.kdj.j", _kdj_j_bucket),
            ),
            min_sample_count=min_sample_count,
            top_n=top_n,
        ),
        _matrix(
            "entry_industry_relative_strength",
            "入场 行业相对沪深300强弱 x 个股 KDJ J",
            _event_records(attributions, timing="entry", post_exit_by_key=post_exit_by_key),
            dimensions=(
                _dimension(
                    "industry_relative_strength",
                    "industry.relative.hs300.strength_state",
                    _category_bucket,
                ),
                _dimension("symbol_kdj_j", "symbol.kdj.j", _kdj_j_bucket),
            ),
            min_sample_count=min_sample_count,
            top_n=top_n,
        ),
        _matrix(
            "add_on_industry_relative_strength",
            "加仓 行业相对沪深300强弱 x DEA 上水天数",
            _event_records(attributions, timing="add_on", post_exit_by_key=post_exit_by_key),
            dimensions=(
                _dimension(
                    "industry_relative_strength",
                    "industry.relative.hs300.strength_state",
                    _category_bucket,
                ),
                _dimension("dea_age", "symbol.macd.dea_waterline_age_trading_days", _dea_age_bucket),
            ),
            min_sample_count=min_sample_count,
            top_n=top_n,
        ),
        _matrix(
            "stop_loss_entry_timing",
            "止损交易的入场 DEA 上水天数 x 个股 KDJ J",
            (
                record
                for record in _event_records(attributions, timing="entry", post_exit_by_key=post_exit_by_key)
                if _is_stop_loss(record)
            ),
            dimensions=(
                _dimension("dea_age", "symbol.macd.dea_waterline_age_trading_days", _dea_age_bucket),
                _dimension("symbol_kdj_j", "symbol.kdj.j", _kdj_j_bucket),
            ),
            min_sample_count=min_sample_count,
            top_n=top_n,
        ),
        _matrix(
            "profit_exit_kdj_post_5d",
            "止盈退出 KDJ J x 卖出后 5 天表现",
            (
                record
                for record in _event_records(attributions, timing="exit", post_exit_by_key=post_exit_by_key)
                if _is_profit_exit(record)
            ),
            dimensions=(
                _dimension("symbol_kdj_j", "symbol.kdj.j", _kdj_j_bucket),
                _dimension("market_hs300_kdj_j", "market.hs300.kdj.j", _kdj_j_bucket),
            ),
            min_sample_count=min_sample_count,
            top_n=top_n,
        ),
    ]

    return {
        "schema": ATTRIBUTION_MATRIX_SCHEMA,
        "run_id": _run_id(run_path),
        "source_dir": str(run_path),
        "source_artifacts": ["trade_attribution.json", "post_exit_analysis.json"],
        "parameters": {
            "min_sample_count": min_sample_count,
            "top_n": top_n,
            "kdj_j_buckets": _KDJ_BUCKETS,
            "dea_age_buckets": _DEA_AGE_BUCKETS,
            "post_exit_thresholds": _POST_EXIT_THRESHOLDS,
        },
        "matrices": matrices,
        "ai_usage_rules": [
            "矩阵只做后验分组统计，不代表因果结论，也不自动修改策略条件。",
            "entry/add_on 矩阵优先看样本数、胜率、平均收益和止损率，低样本行只作为线索。",
            "profit_exit_kdj_post_5d 用于观察止盈后 5 天卖飞程度，阈值 0% 噪音较大，优先看 2%、5%、10%。",
            "missing 是单独桶，不能当成 false、0 或中性值。",
        ],
    }


def render_attribution_matrix_markdown_zh(report: Mapping[str, Any]) -> str:
    """Render attribution matrix report in Chinese Markdown."""

    lines = [
        "# 归因分桶矩阵",
        "",
        f"- schema: `{report.get('schema')}`",
        f"- run_id: `{report.get('run_id')}`",
        f"- source_dir: `{report.get('source_dir')}`",
        "",
        "## 使用规则",
    ]
    for rule in _as_sequence(report.get("ai_usage_rules")):
        lines.append(f"- {rule}")

    for matrix in _as_sequence(report.get("matrices")):
        matrix_map = _as_mapping(matrix)
        lines.extend(
            [
                "",
                f"## {matrix_map.get('title')}",
                "",
                f"- matrix_id: `{matrix_map.get('matrix_id')}`",
                f"- total_rows: `{matrix_map.get('total_row_count')}`",
                f"- shown_rows: `{len(_as_sequence(matrix_map.get('rows')))}`",
                "",
                "| 分桶 | 样本 | 胜率 | 平均收益 | 平均盈利 | 平均亏损 | 止损率 | 5日最高均值 | >=2% | >=5% | >=10% |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in _as_sequence(matrix_map.get("rows")):
            row_map = _as_mapping(row)
            lines.append(
                "| "
                f"{_format_dimensions(row_map.get('dimensions'))} | "
                f"{row_map.get('sample_count')} | "
                f"{_format_percent(row_map.get('win_rate'))} | "
                f"{_format_percent(row_map.get('average_return_pct'))} | "
                f"{_format_percent(row_map.get('average_win_pct'))} | "
                f"{_format_percent(row_map.get('average_loss_pct'))} | "
                f"{_format_percent(row_map.get('stop_loss_rate'))} | "
                f"{_format_percent(row_map.get('average_max_high_return_pct_5d'))} | "
                f"{_format_percent(row_map.get('post_exit_rebound_rate_2pct'))} | "
                f"{_format_percent(row_map.get('post_exit_rebound_rate_5pct'))} | "
                f"{_format_percent(row_map.get('post_exit_rebound_rate_10pct'))} |"
            )
    lines.append("")
    return "\n".join(lines)


def write_attribution_matrix(
    report: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write attribution matrix JSON and Chinese Markdown."""

    target_dir = Path(output_dir) if output_dir is not None else Path(str(report["source_dir"]))
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / "attribution_matrix.json"
    markdown_path = target_dir / "attribution_matrix.zh.md"
    json_path.write_text(_to_pretty_json(report), encoding="utf-8")
    markdown_path.write_text(render_attribution_matrix_markdown_zh(report), encoding="utf-8")
    return json_path, markdown_path


def _matrix(
    matrix_id: str,
    title: str,
    records: Iterable[Mapping[str, Any]],
    *,
    dimensions: Sequence[Mapping[str, Any]],
    min_sample_count: int,
    top_n: int,
) -> dict[str, Any]:
    grouped: dict[tuple[tuple[str, str], ...], list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        key = tuple(
            (str(dimension["name"]), str(dimension["bucket_func"](record.get(str(dimension["factor_key"])))))
            for dimension in dimensions
        )
        grouped[key].append(record)

    rows = [
        _matrix_row(key, items)
        for key, items in grouped.items()
        if len(items) >= min_sample_count
    ]
    rows = sorted(rows, key=_matrix_row_sort_key)
    return {
        "matrix_id": matrix_id,
        "title": title,
        "dimensions": [
            {"name": dimension["name"], "factor_key": dimension["factor_key"]}
            for dimension in dimensions
        ],
        "total_row_count": len(rows),
        "rows": rows[:top_n],
    }


def _matrix_row(
    key: tuple[tuple[str, str], ...],
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    returns = [_optional_float(record.get("return_pct")) for record in records]
    returns = [value for value in returns if value is not None]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value <= 0]
    post_exit_records = [record for record in records if record.get("max_high_return_pct_5d") is not None]
    stop_loss_count = sum(1 for record in records if _is_stop_loss(record))
    rebound_rates = {
        f"post_exit_rebound_rate_{int(threshold * 100)}pct": _rate(
            sum(
                1
                for record in post_exit_records
                if (_optional_float(record.get("max_high_return_pct_5d")) or 0.0) >= threshold
            ),
            len(post_exit_records),
        )
        for threshold in _POST_EXIT_THRESHOLDS
    }
    return {
        "dimensions": dict(key),
        "sample_count": len(records),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": _rate(len(wins), len(returns)),
        "average_return_pct": _mean(returns),
        "average_win_pct": _mean(wins),
        "average_loss_pct": _mean(losses),
        "stop_loss_count": stop_loss_count,
        "stop_loss_rate": _rate(stop_loss_count, len(records)),
        "post_exit_observed_count": len(post_exit_records),
        "average_max_high_return_pct_5d": _mean(
            [
                _optional_float(record.get("max_high_return_pct_5d"))
                for record in post_exit_records
                if _optional_float(record.get("max_high_return_pct_5d")) is not None
            ]
        ),
        "average_window_close_return_pct_5d": _mean(
            [
                _optional_float(record.get("primary_window_close_return_pct_5d"))
                for record in post_exit_records
                if _optional_float(record.get("primary_window_close_return_pct_5d")) is not None
            ]
        ),
        **rebound_rates,
        "trade_indexes": [record.get("trade_index") for record in records[:20]],
    }


def _event_records(
    attributions: Sequence[Mapping[str, Any]],
    *,
    timing: str,
    post_exit_by_key: Mapping[tuple[str, str, str, str], Mapping[str, Any]],
) -> Iterable[dict[str, Any]]:
    for attribution in attributions:
        events = _events_for_timing(attribution, timing)
        for event in events:
            factors = _factor_values(_as_mapping(event).get("factors"))
            post_exit = post_exit_by_key.get(_trade_key(attribution))
            yield {
                "trade_index": attribution.get("trade_index"),
                "symbol": attribution.get("symbol"),
                "entry_date": attribution.get("entry_date"),
                "exit_date": attribution.get("exit_date"),
                "exit_reason": attribution.get("exit_reason"),
                "outcome": attribution.get("outcome"),
                "return_pct": attribution.get("return_pct"),
                "timing": timing,
                "event_date": _as_mapping(event).get("trade_date"),
                "sold_too_early": _as_mapping(post_exit).get("sold_too_early"),
                "max_high_return_pct_5d": _as_mapping(post_exit).get("max_high_return_pct"),
                "primary_window_close_return_pct_5d": _as_mapping(post_exit).get(
                    "primary_window_close_return_pct"
                ),
                **factors,
            }


def _events_for_timing(attribution: Mapping[str, Any], timing: str) -> tuple[Mapping[str, Any], ...]:
    if timing == "add_on":
        return tuple(_as_mapping(item) for item in _as_sequence(attribution.get("add_ons")))
    event = _as_mapping(attribution.get(timing))
    return (event,) if event else ()


def _factor_values(factors: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for factor in _as_sequence(factors):
        factor_map = _as_mapping(factor)
        key = factor_map.get("key")
        if key is None:
            continue
        values[str(key)] = None if factor_map.get("missing") is True else factor_map.get("value")
    return values


def _dimension(name: str, factor_key: str, bucket_func: Any) -> dict[str, Any]:
    return {"name": name, "factor_key": factor_key, "bucket_func": bucket_func}


def _kdj_j_bucket(value: Any) -> str:
    number = _optional_float(value)
    if number is None:
        return "missing"
    if number < 13:
        return "<13"
    if number < 30:
        return "13-30"
    if number < 50:
        return "30-50"
    if number < 80:
        return "50-80"
    return ">=80"


def _dea_age_bucket(value: Any) -> str:
    number = _optional_float(value)
    if number is None:
        return "missing"
    if number <= 2:
        return "0-2"
    if number <= 5:
        return "3-5"
    if number <= 10:
        return "6-10"
    if number <= 14:
        return "11-14"
    return ">14"


def _category_bucket(value: Any) -> str:
    if value is None:
        return "missing"
    text = str(value).strip()
    return text if text else "missing"


def _post_exit_by_trade_key(post_exit: Mapping[str, Any] | None) -> dict[tuple[str, str, str, str], Mapping[str, Any]]:
    if not post_exit:
        return {}
    return {
        _trade_key(item): _as_mapping(item)
        for item in _as_sequence(post_exit.get("observations"))
    }


def _trade_key(item: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(item.get("symbol")),
        str(item.get("entry_date")),
        str(item.get("exit_date")),
        str(item.get("exit_reason")),
    )


def _is_stop_loss(record: Mapping[str, Any]) -> bool:
    reason = str(record.get("exit_reason") or "").upper()
    return "STOP" in reason or "LOSS" in reason


def _is_profit_exit(record: Mapping[str, Any]) -> bool:
    reason = str(record.get("exit_reason") or "").upper()
    return "PROFIT" in reason


def _matrix_row_sort_key(row: Mapping[str, Any]) -> tuple[float, int, float]:
    return (
        -float(row.get("sample_count") or 0),
        -int(row.get("win_count") or 0),
        -float(row.get("average_return_pct") or 0.0),
    )


def _run_id(run_path: Path) -> str:
    run_plan = _read_optional_json(run_path / "run_plan.json")
    run = _as_mapping(_as_mapping(run_plan).get("run"))
    return str(run.get("id") or run_path.name)


def _read_json(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"required artifact does not exist: {path}")
    return _as_mapping(json.loads(path.read_text(encoding="utf-8")))


def _read_optional_json(path: Path) -> Mapping[str, Any] | None:
    if not path.exists():
        return None
    return _as_mapping(json.loads(path.read_text(encoding="utf-8")))


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> tuple[Any, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return ()


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _format_dimensions(value: Any) -> str:
    dimensions = _as_mapping(value)
    if not dimensions:
        return "-"
    return " / ".join(f"{key}={item}" for key, item in dimensions.items())


def _format_percent(value: Any) -> str:
    number = _optional_float(value)
    return "-" if number is None else f"{number * 100:.2f}%"


def _to_pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)
