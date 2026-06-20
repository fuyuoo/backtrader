"""Overall attribution summary for AI-readable strategy environment review."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from attbacktrader.strategies.attribution import attribution_declaration_by_key


ATTRIBUTION_SUMMARY_SCHEMA = "attbacktrader.attribution_summary.v1"
_ATTRIBUTION_DECLARATIONS = attribution_declaration_by_key()

_FOCUS_MATRIX_IDS = (
    "entry_kdj_stack",
    "entry_symbol_daily_weekly_kdj",
    "entry_industry_daily_weekly_kdj",
    "entry_symbol_daily_weekly_macd_zone",
    "entry_industry_daily_weekly_macd_zone",
    "entry_industry_trend_market_kdj",
    "entry_industry_relative_strength",
    "add_on_dea_symbol_kdj",
    "add_on_industry_relative_strength",
    "stop_loss_entry_timing",
    "profit_exit_kdj_post_5d",
)


def build_attribution_summary(
    run_dir: str | Path,
    *,
    top_n: int = 5,
) -> dict[str, Any]:
    """Build a compact, evidence-backed summary from attribution artifacts."""

    if top_n <= 0:
        raise ValueError("top_n must be greater than 0")

    run_path = Path(run_dir)
    trade_attribution = _read_json(run_path / "trade_attribution.json")
    attribution_matrix = _read_json(run_path / "attribution_matrix.json")
    post_exit = _read_optional_json(run_path / "post_exit_analysis.json")
    attributions = tuple(_as_mapping(item) for item in _as_sequence(trade_attribution.get("attributions")))
    matrix_by_id = {
        str(matrix.get("matrix_id")): _as_mapping(matrix)
        for matrix in _as_sequence(attribution_matrix.get("matrices"))
    }

    return {
        "schema": ATTRIBUTION_SUMMARY_SCHEMA,
        "run_id": _run_id(run_path, attribution_matrix),
        "source_dir": str(run_path),
        "source_artifacts": [
            "trade_attribution.json",
            "attribution_matrix.json",
            "post_exit_analysis.json",
        ],
        "overview": _overview(trade_attribution, attributions, post_exit),
        "industry_attribution": _industry_attribution_chapter(matrix_by_id, top_n=top_n),
        "environment_factor_chapters": _environment_factor_chapters(matrix_by_id, top_n=top_n),
        "matrix_focus": [
            _matrix_focus(matrix_by_id[matrix_id], top_n=top_n)
            for matrix_id in _FOCUS_MATRIX_IDS
            if matrix_id in matrix_by_id
        ],
        "summary_cards": _summary_cards(matrix_by_id, post_exit, top_n=top_n),
        "ai_usage_rules": [
            "这份报告只做后验归因总结，不代表因果关系，也不自动修改策略条件。",
            "优先比较同一矩阵内的样本数、胜率、平均收益和止损率，不跨矩阵直接比较收益。",
            "低样本组合只作为线索，不能直接作为策略规则。",
            "收益金额和最终权益在大资金全买验证配置下可能失真，优先看成交交易的相对表现。",
        ],
    }


def render_attribution_summary_markdown_zh(report: Mapping[str, Any]) -> str:
    """Render overall attribution summary in Chinese Markdown."""

    overview = _as_mapping(report.get("overview"))
    lines = [
        "# 归因总览报告",
        "",
        f"- schema: `{report.get('schema')}`",
        f"- run_id: `{report.get('run_id')}`",
        f"- source_dir: `{report.get('source_dir')}`",
        "",
        "## 使用规则",
    ]
    for rule in _as_sequence(report.get("ai_usage_rules")):
        lines.append(f"- {rule}")

    lines.extend(
        [
            "",
            "## 交易概览",
            "",
            "| 指标 | 值 |",
            "|---|---:|",
            f"| 交易数 | {overview.get('trade_count', 0)} |",
            f"| 入场事件 | {overview.get('entry_event_count', 0)} |",
            f"| 加仓事件 | {overview.get('add_on_event_count', 0)} |",
            f"| 出场事件 | {overview.get('exit_event_count', 0)} |",
            f"| 盈利交易 | {overview.get('win_count', 0)} |",
            f"| 亏损交易 | {overview.get('loss_count', 0)} |",
            f"| 胜率 | {_format_percent(overview.get('win_rate'))} |",
        ]
    )
    exit_reasons = _as_mapping(overview.get("exit_reasons"))
    if exit_reasons:
        lines.extend(["", "### 出场原因", "", "| 原因 | 次数 |", "|---|---:|"])
        for reason, count in exit_reasons.items():
            lines.append(f"| `{reason}` | {count} |")

    post_exit = _as_mapping(overview.get("post_exit"))
    if post_exit:
        lines.extend(
            [
                "",
                "### 止盈后卖飞概览",
                "",
                "| 分组 | 样本 | 5日最高均值 | >=2% | >=5% | >=10% |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for item in _as_sequence(post_exit.get("threshold_summary")):
            item_map = _as_mapping(item)
            lines.append(
                "| "
                f"{item_map.get('group')} | "
                f"{item_map.get('sample_count')} | "
                f"{_format_percent(item_map.get('average_max_high_return_pct'))} | "
                f"{_format_percent(item_map.get('rebound_rate_2pct'))} | "
                f"{_format_percent(item_map.get('rebound_rate_5pct'))} | "
                f"{_format_percent(item_map.get('rebound_rate_10pct'))} |"
            )

    industry_attribution = _as_mapping(report.get("industry_attribution"))
    if industry_attribution:
        lines.extend(["", "## 行业归因专章", ""])
        for section in _as_sequence(industry_attribution.get("sections")):
            section_map = _as_mapping(section)
            lines.extend(
                [
                    f"### {section_map.get('title')}",
                    "",
                    str(section_map.get("description") or ""),
                    "",
                    "正向线索：",
                ]
            )
            _append_rows_table(lines, _as_sequence(section_map.get("positive_rows")))
            lines.append("")
            lines.append("负向线索：")
            _append_rows_table(lines, _as_sequence(section_map.get("negative_rows")))
            lines.append("")

    environment_chapters = _as_sequence(report.get("environment_factor_chapters"))
    if environment_chapters:
        lines.extend(["", "## 周期因子专章", ""])
        for chapter in environment_chapters:
            chapter_map = _as_mapping(chapter)
            lines.extend(
                [
                    f"### {chapter_map.get('title')}",
                    "",
                    str(chapter_map.get("description") or ""),
                    "",
                    "正向线索：",
                ]
            )
            _append_rows_table(lines, _as_sequence(chapter_map.get("positive_rows")))
            lines.append("")
            lines.append("负向线索：")
            _append_rows_table(lines, _as_sequence(chapter_map.get("negative_rows")))
            lines.append("")

    lines.extend(["", "## 重点结论卡片"])
    for card in _as_sequence(report.get("summary_cards")):
        card_map = _as_mapping(card)
        lines.extend(["", f"### {card_map.get('title')}", "", card_map.get("description", "")])
        _append_rows_table(lines, _as_sequence(card_map.get("rows")))

    lines.extend(["", "## 矩阵摘要"])
    for focus in _as_sequence(report.get("matrix_focus")):
        focus_map = _as_mapping(focus)
        lines.extend(
            [
                "",
                f"### {focus_map.get('title')}",
                "",
                f"- matrix_id: `{focus_map.get('matrix_id')}`",
                f"- shown_rows: `{focus_map.get('shown_row_count')}`",
                "",
                "正向线索：",
            ]
        )
        _append_rows_table(lines, _as_sequence(focus_map.get("positive_rows")))
        lines.append("")
        lines.append("负向线索：")
        _append_rows_table(lines, _as_sequence(focus_map.get("negative_rows")))

    lines.append("")
    return "\n".join(lines)


def write_attribution_summary(
    report: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write attribution summary JSON and Chinese Markdown."""

    target_dir = Path(output_dir) if output_dir is not None else Path(str(report["source_dir"]))
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / "attribution_summary.json"
    markdown_path = target_dir / "attribution_summary.zh.md"
    json_path.write_text(_to_pretty_json(report), encoding="utf-8")
    markdown_path.write_text(render_attribution_summary_markdown_zh(report), encoding="utf-8")
    return json_path, markdown_path


def _overview(
    trade_attribution: Mapping[str, Any],
    attributions: Sequence[Mapping[str, Any]],
    post_exit: Mapping[str, Any] | None,
) -> dict[str, Any]:
    returns = [_optional_float(item.get("return_pct")) for item in attributions]
    returns = [value for value in returns if value is not None]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value <= 0]
    exit_reasons = Counter(str(item.get("exit_reason")) for item in attributions if item.get("exit_reason"))
    return {
        "trade_count": int(trade_attribution.get("trade_count") or len(attributions)),
        "entry_event_count": int(trade_attribution.get("entry_event_count") or 0),
        "add_on_event_count": int(trade_attribution.get("add_on_event_count") or 0),
        "exit_event_count": int(trade_attribution.get("exit_event_count") or 0),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": _rate(len(wins), len(returns)),
        "average_return_pct": _mean(returns),
        "average_win_pct": _mean(wins),
        "average_loss_pct": _mean(losses),
        "exit_reasons": dict(exit_reasons.most_common()),
        "post_exit": _post_exit_overview(post_exit),
    }


def _post_exit_overview(post_exit: Mapping[str, Any] | None) -> dict[str, Any]:
    if not post_exit:
        return {}
    by_group: dict[str, dict[str, Any]] = {}
    for item in _as_sequence(post_exit.get("threshold_summaries")):
        item_map = _as_mapping(item)
        group = str(item_map.get("group"))
        threshold = _optional_float(item_map.get("threshold"))
        if threshold is None:
            continue
        target = by_group.setdefault(
            group,
            {
                "group": group,
                "sample_count": item_map.get("sample_count"),
                "average_max_high_return_pct": item_map.get("average_max_high_return_pct"),
            },
        )
        target[f"rebound_rate_{int(threshold * 100)}pct"] = item_map.get("rebound_rate")
    return {"threshold_summary": tuple(by_group.values())}


def _matrix_focus(matrix: Mapping[str, Any], *, top_n: int) -> dict[str, Any]:
    rows = tuple(_as_mapping(row) for row in _as_sequence(matrix.get("rows")))
    positive_rows = sorted(rows, key=_positive_sort_key)[:top_n]
    negative_rows = sorted(rows, key=_negative_sort_key)[:top_n]
    return {
        "matrix_id": matrix.get("matrix_id"),
        "title": matrix.get("title"),
        "shown_row_count": len(rows),
        "positive_rows": tuple(_compact_row(row, matrix=matrix) for row in positive_rows),
        "negative_rows": tuple(_compact_row(row, matrix=matrix) for row in negative_rows),
    }


def _industry_attribution_chapter(
    matrix_by_id: Mapping[str, Mapping[str, Any]],
    *,
    top_n: int,
) -> dict[str, Any]:
    sections = []
    section_specs = (
        (
            "industry_kdj_stack",
            "行业 KDJ 共振",
            "观察入场时个股 KDJ、行业 KDJ、沪深300 KDJ 是否形成共振。",
            "entry_kdj_stack",
        ),
        (
            "industry_trend",
            "行业 MA 趋势",
            "观察入场时所属行业是否处在 MA 多头趋势，以及指数 KDJ 是否配合。",
            "entry_industry_trend_market_kdj",
        ),
        (
            "industry_relative_strength_entry",
            "入场行业相对强弱",
            "观察入场时所属行业相对沪深300的 60 日强弱状态。",
            "entry_industry_relative_strength",
        ),
        (
            "industry_relative_strength_add_on",
            "加仓行业相对强弱",
            "观察加仓时行业相对强弱是否能改善加仓胜率和收益。",
            "add_on_industry_relative_strength",
        ),
    )
    for section_id, title, description, matrix_id in section_specs:
        matrix = _as_mapping(matrix_by_id.get(matrix_id))
        if not matrix:
            continue
        focus = _matrix_focus(matrix, top_n=top_n)
        sections.append(
            {
                "section_id": section_id,
                "matrix_id": matrix_id,
                "title": title,
                "description": description,
                "positive_rows": focus["positive_rows"],
                "negative_rows": focus["negative_rows"],
            }
        )
    return {
        "section_count": len(sections),
        "sections": tuple(sections),
    }


def _environment_factor_chapters(
    matrix_by_id: Mapping[str, Mapping[str, Any]],
    *,
    top_n: int,
) -> tuple[dict[str, Any], ...]:
    chapters: list[dict[str, Any]] = []
    chapter_specs = (
        (
            "weekly_kdj",
            "周线 KDJ 联动",
            "观察入场时个股/行业日线 KDJ 与已完成周线 KDJ 是否一致，重点看胜率、平均收益和止损率。",
            ("entry_symbol_daily_weekly_kdj", "entry_industry_daily_weekly_kdj"),
        ),
        (
            "macd_energy_zone",
            "MACD 日周能量区间",
            "观察入场时个股/行业 MACD 日线区间与已完成周线区间的组合，MACD 柱使用 2*(DIF-DEA)。",
            ("entry_symbol_daily_weekly_macd_zone", "entry_industry_daily_weekly_macd_zone"),
        ),
    )
    for chapter_id, title, description, matrix_ids in chapter_specs:
        positive_rows = _top_rows_from_matrices(matrix_by_id, matrix_ids, top_n=top_n, positive=True)
        negative_rows = _top_rows_from_matrices(matrix_by_id, matrix_ids, top_n=top_n, positive=False)
        if not positive_rows and not negative_rows:
            continue
        chapters.append(
            {
                "chapter_id": chapter_id,
                "title": title,
                "description": description,
                "matrix_ids": tuple(matrix_ids),
                "positive_rows": positive_rows,
                "negative_rows": negative_rows,
            }
        )
    return tuple(chapters)


def _summary_cards(
    matrix_by_id: Mapping[str, Mapping[str, Any]],
    post_exit: Mapping[str, Any] | None,
    *,
    top_n: int,
) -> tuple[dict[str, Any], ...]:
    cards: list[dict[str, Any]] = []
    cards.append(
        {
            "card_id": "entry_environment",
            "title": "入场环境线索",
            "description": "优先观察个股、行业和指数共振时的入场表现。",
            "rows": _top_rows_from_matrices(
                matrix_by_id,
                (
                    "entry_kdj_stack",
                    "entry_symbol_daily_weekly_kdj",
                    "entry_industry_daily_weekly_kdj",
                    "entry_symbol_daily_weekly_macd_zone",
                    "entry_industry_daily_weekly_macd_zone",
                    "entry_industry_trend_market_kdj",
                    "entry_industry_relative_strength",
                ),
                top_n=top_n,
                positive=True,
            ),
        }
    )
    cards.append(
        {
            "card_id": "add_on_environment",
            "title": "加仓环境线索",
            "description": "观察加仓是否需要 DEA 上水天数和行业强弱共同确认。",
            "rows": _top_rows_from_matrices(
                matrix_by_id,
                ("add_on_dea_symbol_kdj", "add_on_industry_relative_strength"),
                top_n=top_n,
                positive=True,
            ),
        }
    )
    cards.append(
        {
            "card_id": "negative_entry_risk",
            "title": "负向入场线索",
            "description": "这些组合更像需要人工复核的亏损土壤，不能直接当过滤规则。",
            "rows": _top_rows_from_matrices(
                matrix_by_id,
                (
                    "entry_kdj_stack",
                    "entry_symbol_daily_weekly_kdj",
                    "entry_industry_daily_weekly_kdj",
                    "entry_symbol_daily_weekly_macd_zone",
                    "entry_industry_daily_weekly_macd_zone",
                    "entry_industry_trend_market_kdj",
                    "entry_industry_relative_strength",
                ),
                top_n=top_n,
                positive=False,
            ),
        }
    )
    cards.append(
        {
            "card_id": "stop_loss_timing",
            "title": "止损入场时机",
            "description": "只看最终止损交易的入场状态，用于定位亏损交易来自哪些时机。",
            "rows": _top_rows_from_matrices(
                matrix_by_id,
                ("stop_loss_entry_timing",),
                top_n=top_n,
                positive=False,
            ),
        }
    )
    if post_exit:
        cards.append(
            {
                "card_id": "profit_exit_post_5d",
                "title": "止盈后 5 日卖飞线索",
                "description": "只观察止盈后 5 日反弹程度，优先看 5% 和 10% 阈值。",
                "rows": _top_rows_from_matrices(
                    matrix_by_id,
                    ("profit_exit_kdj_post_5d",),
                    top_n=top_n,
                    positive=True,
                ),
            }
        )
    return tuple(cards)


def _top_rows_from_matrices(
    matrix_by_id: Mapping[str, Mapping[str, Any]],
    matrix_ids: Sequence[str],
    *,
    top_n: int,
    positive: bool,
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for matrix_id in matrix_ids:
        matrix = _as_mapping(matrix_by_id.get(matrix_id))
        for row in _as_sequence(matrix.get("rows")):
            compact = _compact_row(_as_mapping(row), matrix=matrix)
            compact["matrix_id"] = matrix_id
            compact["matrix_title"] = matrix.get("title")
            rows.append(compact)
    key_func = _positive_compact_sort_key if positive else _negative_compact_sort_key
    return tuple(sorted(rows, key=key_func)[:top_n])


def _compact_row(row: Mapping[str, Any], *, matrix: Mapping[str, Any] | None = None) -> dict[str, Any]:
    dimensions = dict(_as_mapping(row.get("dimensions")))
    sample_count = row.get("sample_count")
    return {
        "dimensions": dimensions,
        "dimension_labels_zh": _dimension_labels_zh(dimensions, matrix=matrix),
        "sample_count": sample_count,
        "sample_risk": _sample_risk(sample_count),
        "win_rate": row.get("win_rate"),
        "average_return_pct": row.get("average_return_pct"),
        "average_win_pct": row.get("average_win_pct"),
        "average_loss_pct": row.get("average_loss_pct"),
        "stop_loss_rate": row.get("stop_loss_rate"),
        "average_max_high_return_pct_5d": row.get("average_max_high_return_pct_5d"),
        "post_exit_rebound_rate_5pct": row.get("post_exit_rebound_rate_5pct"),
        "post_exit_rebound_rate_10pct": row.get("post_exit_rebound_rate_10pct"),
        "trade_indexes": tuple(_as_sequence(row.get("trade_indexes"))[:10]),
    }


def _positive_sort_key(row: Mapping[str, Any]) -> tuple[float, float, float]:
    return (
        -float(row.get("average_return_pct") or 0.0),
        -float(row.get("win_rate") or 0.0),
        -float(row.get("sample_count") or 0.0),
    )


def _negative_sort_key(row: Mapping[str, Any]) -> tuple[float, float, float]:
    return (
        float(row.get("average_return_pct") or 0.0),
        float(row.get("win_rate") or 0.0),
        -float(row.get("sample_count") or 0.0),
    )


def _positive_compact_sort_key(row: Mapping[str, Any]) -> tuple[float, float, float]:
    return (
        -float(row.get("average_return_pct") or 0.0),
        -float(row.get("win_rate") or 0.0),
        -float(row.get("sample_count") or 0.0),
    )


def _negative_compact_sort_key(row: Mapping[str, Any]) -> tuple[float, float, float]:
    return (
        float(row.get("average_return_pct") or 0.0),
        float(row.get("win_rate") or 0.0),
        -float(row.get("sample_count") or 0.0),
    )


def _append_rows_table(lines: list[str], rows: Sequence[Any]) -> None:
    if not rows:
        lines.append("")
        lines.append("_暂无样本数达标的行。_")
        return
    lines.extend(
        [
            "",
            "| 分桶 | 样本 | 样本风险 | 胜率 | 平均收益 | 止损率 | 5日最高均值 | >=5% | >=10% |",
            "|---|---:|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        row_map = _as_mapping(row)
        lines.append(
            "| "
            f"{_format_dimensions(row_map.get('dimensions'))} | "
            f"{row_map.get('sample_count')} | "
            f"{_sample_risk_label(row_map.get('sample_risk'))} | "
            f"{_format_percent(row_map.get('win_rate'))} | "
            f"{_format_percent(row_map.get('average_return_pct'))} | "
            f"{_format_percent(row_map.get('stop_loss_rate'))} | "
            f"{_format_percent(row_map.get('average_max_high_return_pct_5d'))} | "
            f"{_format_percent(row_map.get('post_exit_rebound_rate_5pct'))} | "
            f"{_format_percent(row_map.get('post_exit_rebound_rate_10pct'))} |"
        )


def _run_id(run_path: Path, attribution_matrix: Mapping[str, Any]) -> str:
    return str(attribution_matrix.get("run_id") or run_path.name)


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


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
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
    return " / ".join(_dimension_pair_label_zh(key, item) for key, item in dimensions.items())


def _dimension_pair_label_zh(key: Any, value: Any) -> str:
    label = _dimension_label_zh(key)
    value_label = _dimension_value_label_zh(value)
    if str(value).startswith(("<", ">")):
        return f"{label} {value_label}"
    return f"{label}={value_label}"


def _dimension_labels_zh(
    dimensions: Mapping[str, Any],
    *,
    matrix: Mapping[str, Any] | None,
) -> dict[str, str]:
    matrix_dimensions = _matrix_dimension_factor_keys(matrix)
    labels: dict[str, str] = {}
    for key in dimensions:
        factor_key = matrix_dimensions.get(key)
        declaration = _ATTRIBUTION_DECLARATIONS.get(factor_key or "")
        labels[str(key)] = declaration.label_zh if declaration is not None else _dimension_label_zh(key)
    return labels


def _matrix_dimension_factor_keys(matrix: Mapping[str, Any] | None) -> dict[str, str]:
    matrix_map = _as_mapping(matrix)
    result: dict[str, str] = {}
    for item in _as_sequence(matrix_map.get("dimensions")):
        item_map = _as_mapping(item)
        name = item_map.get("name")
        factor_key = item_map.get("factor_key")
        if name is not None and factor_key is not None:
            result[str(name)] = str(factor_key)
    return result


def _dimension_label_zh(key: Any) -> str:
    text = str(key)
    return {
        "dea_age": "DEA 上水天数",
        "symbol_kdj_j": "个股 KDJ J",
        "symbol_weekly_kdj_j": "个股周线 KDJ J",
        "industry_kdj_j": "行业 KDJ J",
        "industry_weekly_kdj_j": "行业周线 KDJ J",
        "market_hs300_kdj_j": "沪深300 KDJ J",
        "symbol_macd_zone": "个股日线 MACD 能量区间",
        "symbol_weekly_macd_zone": "个股周线 MACD 能量区间",
        "industry_macd_zone": "行业日线 MACD 能量区间",
        "industry_weekly_macd_zone": "行业周线 MACD 能量区间",
        "industry_trend_state": "行业均线趋势状态",
        "industry_relative_strength": "行业相对沪深300强弱状态",
    }.get(text, text)


def _dimension_value_label_zh(value: Any) -> str:
    text = str(value)
    return {
        "missing": "缺失",
        "true": "是",
        "false": "否",
        "bullish": "多头",
        "not_bullish": "非多头",
        "strong_outperform": "强于沪深300",
        "outperform": "略强于沪深300",
        "weak_underperform": "略弱于沪深300",
        "underperform": "弱于沪深300",
        "red_bar_wrapping_lines": "红柱包住 DIF/DEA",
        "red_bar_one_line_escape": "红柱一线飘出",
        "red_bar_two_line_escape": "红柱两线飘出",
        "red_bar_uncategorized": "红柱未分型",
        "green_bar_or_zero": "绿柱或零轴",
    }.get(text, text)


def _sample_risk(value: Any) -> str:
    count = _optional_int(value)
    if count is None:
        return "unknown"
    if count < 30:
        return "low_sample"
    if count < 100:
        return "medium_sample"
    return "sufficient_sample"


def _sample_risk_label(value: Any) -> str:
    return {
        "low_sample": "低样本，仅作线索",
        "medium_sample": "中样本，需复核",
        "sufficient_sample": "样本较足",
        "unknown": "未知",
    }.get(str(value), str(value))


def _format_percent(value: Any) -> str:
    number = _optional_float(value)
    return "-" if number is None else f"{number * 100:.2f}%"


def _to_pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)
