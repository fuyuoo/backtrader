"""Audit scorer/gate candidates from the industry-enhanced soil matrix."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_INDUSTRY_REPORT_DIR = Path(
    "reports/soil-with-industry-v1-sw-akshare-historical-mixed-warmup-stitch-index-warmup-earliest-membership-backfill-experimental-baoma-v1-dynamic-hs300-csi500-2006-2025"
)
DEFAULT_OUTPUT_DIR = Path("reports/industry-enhanced-scorer-gate-audit-baoma-v1-dynamic-hs300-csi500-2006-2025")
TRADE_FILE_NAME = "trade_soil_with_industry_v1.parquet"
SOIL_COLUMN = "soil_layer5_with_industry_v1"
NO_INDUSTRY_SOIL_COLUMN = "soil_layer_no_industry_v2"
SEED_COLUMN = "seed_layer_no_industry_v1"


@dataclass(frozen=True)
class CandidateDefinition:
    candidate_id: str
    label_zh: str
    rule_zh: str
    rule: str


CANDIDATES = (
    CandidateDefinition(
        candidate_id="conservative",
        label_zh="保守",
        rule_zh="只允许 very_strong_soil",
        rule="soil == very_strong_soil",
    ),
    CandidateDefinition(
        candidate_id="balanced",
        label_zh="均衡",
        rule_zh="very_strong_soil，或 strong_soil 且 strong_seed",
        rule="soil == very_strong_soil OR (soil == strong_soil AND seed == strong_seed)",
    ),
    CandidateDefinition(
        candidate_id="aggressive",
        label_zh="进攻",
        rule_zh="very_strong_soil，或 strong/neutral_soil 且 strong_seed",
        rule="soil == very_strong_soil OR (soil in {strong_soil, neutral_soil} AND seed == strong_seed)",
    ),
)

DIAGNOSTIC_OVERLAYS = (
    CandidateDefinition(
        candidate_id="very_strong_strong_seed_overlay",
        label_zh="very_strong + strong_seed overlay",
        rule_zh="very_strong_soil 且 strong_seed",
        rule="soil == very_strong_soil AND seed == strong_seed",
    ),
)


def build_industry_enhanced_scorer_gate_audit(
    *,
    industry_report_dir: str | Path = DEFAULT_INDUSTRY_REPORT_DIR,
) -> dict[str, Any]:
    report_dir = Path(industry_report_dir)
    trades = pd.read_parquet(report_dir / TRADE_FILE_NAME)
    _require_columns(
        trades,
        (
            "entry_year",
            "return_pct",
            "is_win",
            "net_pnl",
            "holding_days",
            SOIL_COLUMN,
            NO_INDUSTRY_SOIL_COLUMN,
            SEED_COLUMN,
        ),
    )

    baseline_all = _metrics(trades)
    baseline_no_industry_strong = _metrics(trades[trades[NO_INDUSTRY_SOIL_COLUMN] == "strong_soil"])

    candidate_reports = [
        _candidate_report(candidate, trades, baseline_all, baseline_no_industry_strong)
        for candidate in CANDIDATES
    ]
    overlay_reports = [
        _candidate_report(candidate, trades, baseline_all, baseline_no_industry_strong)
        for candidate in DIAGNOSTIC_OVERLAYS
    ]

    return {
        "schema": "attbacktrader.industry_enhanced_scorer_gate_audit.v1",
        "industry_report_dir": str(report_dir),
        "trade_file": str(report_dir / TRADE_FILE_NAME),
        "trade_count": int(len(trades)),
        "baselines": {
            "all_trades": baseline_all,
            "no_industry_strong_soil": baseline_no_industry_strong,
        },
        "candidates": candidate_reports,
        "diagnostic_overlays": overlay_reports,
        "recommendation": _recommendation(candidate_reports, overlay_reports),
    }


def write_industry_enhanced_scorer_gate_audit(
    audit: dict[str, Any],
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> tuple[Path, Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "industry_enhanced_scorer_gate_audit.json"
    markdown_path = out / "industry_enhanced_scorer_gate_audit.zh.md"
    json_path.write_text(json.dumps(_jsonable(audit), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_industry_enhanced_scorer_gate_audit_markdown_zh(audit), encoding="utf-8")
    return json_path, markdown_path


def render_industry_enhanced_scorer_gate_audit_markdown_zh(audit: dict[str, Any]) -> str:
    baselines = audit["baselines"]
    lines = [
        "# 含行业 Scorer/Gate 候选审计",
        "",
        "## 结论",
        "",
        str(audit["recommendation"]["summary_zh"]),
        "",
        "## 输入",
        "",
        f"- 行业报告目录：`{audit['industry_report_dir']}`",
        f"- trade rows：{_fmt_int(audit['trade_count'])}",
        "",
        "## Baseline",
        "",
        "| baseline | trades | win rate | avg return | median return | PF | net pnl | positive years | worst year avg |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, metrics in baselines.items():
        lines.append(_metrics_row(name, metrics))

    lines.extend(
        [
            "",
            "## 三档候选",
            "",
            "| 档位 | 规则 | trades | win rate | avg return | median return | PF | net pnl | positive years | worst year avg | avg lift vs all | avg lift vs no-ind strong |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in audit["candidates"]:
        metrics = item["metrics"]
        lift = item["lift"]
        lines.append(
            "| "
            f"{item['label_zh']} | "
            f"{item['rule_zh']} | "
            f"{_fmt_int(metrics['trade_count'])} | "
            f"{_fmt_pct(metrics['win_rate_pct'])} | "
            f"{_fmt_pct(metrics['avg_return_pct'])} | "
            f"{_fmt_pct(metrics['median_return_pct'])} | "
            f"{_fmt_num(metrics['profit_factor_ret'])} | "
            f"{_fmt_int(metrics['net_pnl_sum'])} | "
            f"{metrics['positive_avg_return_year_count']}/{metrics['year_count']} | "
            f"{_fmt_pct(metrics['min_year_avg_return_pct'])} | "
            f"{_fmt_pct(lift['avg_return_pct_vs_all_trades'])} | "
            f"{_fmt_pct(lift['avg_return_pct_vs_no_industry_strong_soil'])} |"
        )

    lines.extend(
        [
            "",
            "## Seed Overlay 诊断",
            "",
            "| overlay | 规则 | trades | win rate | avg return | PF | positive years | 说明 |",
            "|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for item in audit["diagnostic_overlays"]:
        metrics = item["metrics"]
        lines.append(
            "| "
            f"{item['label_zh']} | "
            f"{item['rule_zh']} | "
            f"{_fmt_int(metrics['trade_count'])} | "
            f"{_fmt_pct(metrics['win_rate_pct'])} | "
            f"{_fmt_pct(metrics['avg_return_pct'])} | "
            f"{_fmt_num(metrics['profit_factor_ret'])} | "
            f"{metrics['positive_avg_return_year_count']}/{metrics['year_count']} | "
            "提高胜率，但样本和年度稳定性需要与纯 very_strong 对照。 |"
        )

    lines.extend(
        [
            "",
            "## 分年稳定性",
            "",
        ]
    )
    for item in audit["candidates"]:
        lines.extend(
            [
                f"### {item['label_zh']}",
                "",
                "| year | trades | win rate | avg return | PF | net pnl |",
                "|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for year in item["yearly"]:
            lines.append(
                "| "
                f"{year['entry_year']} | "
                f"{_fmt_int(year['trade_count'])} | "
                f"{_fmt_pct(year['win_rate_pct'])} | "
                f"{_fmt_pct(year['avg_return_pct'])} | "
                f"{_fmt_num(year['profit_factor_ret'])} | "
                f"{_fmt_int(year['net_pnl_sum'])} |"
            )
        lines.append("")

    lines.extend(
        [
            "## 下一步",
            "",
            "- 先用保守档做 runner replay，验证资金竞争下 `very_strong_soil` 是否仍保持结果级 lift。",
            "- 均衡档作为第二组 replay，对照扩大样本后 PF 和回撤是否可接受。",
            "- 进攻档暂不直接定主线，只作为容量上限和风险边界测试。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    audit = build_industry_enhanced_scorer_gate_audit(industry_report_dir=args.industry_report_dir)
    json_path, markdown_path = write_industry_enhanced_scorer_gate_audit(audit, output_dir=args.output_dir)
    print(
        json.dumps(
            {
                "status": "ok",
                "json": str(json_path),
                "markdown": str(markdown_path),
                "candidate_count": len(audit["candidates"]),
                "recommended_first_replay": audit["recommendation"]["first_replay_candidate_id"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit industry-enhanced scorer/gate candidates")
    parser.add_argument("--industry-report-dir", type=Path, default=DEFAULT_INDUSTRY_REPORT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def _candidate_report(
    candidate: CandidateDefinition,
    trades: pd.DataFrame,
    baseline_all: dict[str, Any],
    baseline_no_industry_strong: dict[str, Any],
) -> dict[str, Any]:
    selected = trades[_candidate_mask(candidate.candidate_id, trades)].copy()
    metrics = _metrics(selected)
    return {
        "candidate_id": candidate.candidate_id,
        "label_zh": candidate.label_zh,
        "rule_zh": candidate.rule_zh,
        "rule": candidate.rule,
        "metrics": metrics,
        "lift": {
            "avg_return_pct_vs_all_trades": _delta(metrics, baseline_all, "avg_return_pct"),
            "profit_factor_ret_vs_all_trades": _delta(metrics, baseline_all, "profit_factor_ret"),
            "win_rate_pct_vs_all_trades": _delta(metrics, baseline_all, "win_rate_pct"),
            "avg_return_pct_vs_no_industry_strong_soil": _delta(metrics, baseline_no_industry_strong, "avg_return_pct"),
            "profit_factor_ret_vs_no_industry_strong_soil": _delta(metrics, baseline_no_industry_strong, "profit_factor_ret"),
            "win_rate_pct_vs_no_industry_strong_soil": _delta(metrics, baseline_no_industry_strong, "win_rate_pct"),
        },
        "seed_breakdown": _group_reports(selected, SEED_COLUMN),
        "no_industry_breakdown": _group_reports(selected, NO_INDUSTRY_SOIL_COLUMN),
        "yearly": _yearly_reports(selected),
    }


def _candidate_mask(candidate_id: str, trades: pd.DataFrame) -> pd.Series:
    soil = trades[SOIL_COLUMN]
    seed = trades[SEED_COLUMN]
    if candidate_id == "conservative":
        return soil == "very_strong_soil"
    if candidate_id == "balanced":
        return (soil == "very_strong_soil") | ((soil == "strong_soil") & (seed == "strong_seed"))
    if candidate_id == "aggressive":
        return (soil == "very_strong_soil") | (soil.isin(["strong_soil", "neutral_soil"]) & (seed == "strong_seed"))
    if candidate_id == "very_strong_strong_seed_overlay":
        return (soil == "very_strong_soil") & (seed == "strong_seed")
    raise ValueError(f"unknown candidate_id: {candidate_id}")


def _metrics(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "trade_count": 0,
            "win_rate_pct": None,
            "avg_return_pct": None,
            "median_return_pct": None,
            "profit_factor_ret": None,
            "net_pnl_sum": 0.0,
            "avg_holding_days": None,
            "year_count": 0,
            "positive_avg_return_year_count": 0,
            "min_year_avg_return_pct": None,
        }
    returns = pd.to_numeric(frame["return_pct"], errors="coerce")
    wins = frame["is_win"].astype(bool)
    gross_profit = float(returns[returns > 0].sum())
    gross_loss = float(-returns[returns < 0].sum())
    yearly = _yearly_reports(frame)
    return {
        "trade_count": int(len(frame)),
        "win_rate_pct": float(wins.mean() * 100.0),
        "avg_return_pct": float(returns.mean()),
        "median_return_pct": float(returns.median()),
        "profit_factor_ret": gross_profit / gross_loss if gross_loss else None,
        "net_pnl_sum": float(pd.to_numeric(frame["net_pnl"], errors="coerce").sum()),
        "avg_holding_days": float(pd.to_numeric(frame["holding_days"], errors="coerce").mean()),
        "year_count": len(yearly),
        "positive_avg_return_year_count": sum(1 for item in yearly if _number(item["avg_return_pct"]) and item["avg_return_pct"] > 0),
        "min_year_avg_return_pct": min((item["avg_return_pct"] for item in yearly), default=None),
    }


def _yearly_reports(frame: pd.DataFrame) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    if frame.empty:
        return reports
    for year, group in frame.groupby("entry_year", sort=True):
        metrics = _metrics_without_year(group)
        metrics["entry_year"] = int(year)
        reports.append(metrics)
    return reports


def _group_reports(frame: pd.DataFrame, column: str) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    if frame.empty:
        return reports
    for value, group in frame.groupby(column, dropna=False, sort=True):
        metrics = _metrics_without_year(group)
        metrics[column] = None if pd.isna(value) else str(value)
        reports.append(metrics)
    return reports


def _metrics_without_year(frame: pd.DataFrame) -> dict[str, Any]:
    returns = pd.to_numeric(frame["return_pct"], errors="coerce")
    wins = frame["is_win"].astype(bool)
    gross_profit = float(returns[returns > 0].sum())
    gross_loss = float(-returns[returns < 0].sum())
    return {
        "trade_count": int(len(frame)),
        "win_rate_pct": float(wins.mean() * 100.0),
        "avg_return_pct": float(returns.mean()),
        "median_return_pct": float(returns.median()),
        "profit_factor_ret": gross_profit / gross_loss if gross_loss else None,
        "net_pnl_sum": float(pd.to_numeric(frame["net_pnl"], errors="coerce").sum()),
        "avg_holding_days": float(pd.to_numeric(frame["holding_days"], errors="coerce").mean()),
    }


def _recommendation(candidates: list[dict[str, Any]], overlays: list[dict[str, Any]]) -> dict[str, Any]:
    conservative = next(item for item in candidates if item["candidate_id"] == "conservative")
    balanced = next(item for item in candidates if item["candidate_id"] == "balanced")
    overlay = next(item for item in overlays if item["candidate_id"] == "very_strong_strong_seed_overlay")
    return {
        "first_replay_candidate_id": "conservative",
        "second_replay_candidate_id": "balanced",
        "capacity_boundary_candidate_id": "aggressive",
        "summary_zh": (
            "建议先 replay 保守档：它直接验证含行业主轴 `very_strong_soil`，"
            f"全样本 {conservative['metrics']['trade_count']:,} 笔，PF "
            f"{_fmt_num(conservative['metrics']['profit_factor_ret'])}，"
            f"分年正收益 {conservative['metrics']['positive_avg_return_year_count']}/"
            f"{conservative['metrics']['year_count']}。均衡档作为第二组容量扩展；"
            f"`very_strong + strong_seed` overlay 胜率更高但只有 {overlay['metrics']['trade_count']:,} 笔，"
            "不应先替代主轴。"
        ),
    }


def _delta(left: dict[str, Any], right: dict[str, Any], key: str) -> float | None:
    left_value = left.get(key)
    right_value = right.get(key)
    if not _number(left_value) or not _number(right_value):
        return None
    return float(left_value) - float(right_value)


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isnan(float(value))


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")


def _metrics_row(name: str, metrics: dict[str, Any]) -> str:
    return (
        "| "
        f"{name} | "
        f"{_fmt_int(metrics['trade_count'])} | "
        f"{_fmt_pct(metrics['win_rate_pct'])} | "
        f"{_fmt_pct(metrics['avg_return_pct'])} | "
        f"{_fmt_pct(metrics['median_return_pct'])} | "
        f"{_fmt_num(metrics['profit_factor_ret'])} | "
        f"{_fmt_int(metrics['net_pnl_sum'])} | "
        f"{metrics['positive_avg_return_year_count']}/{metrics['year_count']} | "
        f"{_fmt_pct(metrics['min_year_avg_return_pct'])} |"
    )


def _fmt_int(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):,.0f}"


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


def _fmt_num(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if hasattr(value, "item"):
        return value.item()
    return value


if __name__ == "__main__":
    raise SystemExit(main())
