from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_RUN_PLAN = (
    REPO_ROOT
    / "reports"
    / "soil-with-industry-v1-baoma-v1-dynamic-hs300-only-2006-2025"
    / "run_plan_hs300_only_liquidity_low_turnover_gate_v1_lean.json"
)
FORMAL_GATE_REPORT = (
    REPO_ROOT
    / "reports"
    / "formal-regime-gate-walk-forward-hs300-only-2006-2025"
    / "formal_gate_period_metrics.csv"
)
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "reports"
    / "formal-strategy-gate-config-hs300-only-2006-2025"
)


NEAR_HIGH_FIELD = "entry.price_position.near_high_60d_bucket"
INDUSTRY_ABOVE_MA60_FIELD = "industry.ma.price_above_ma60"
SOIL_SCORE_FIELD = "entry.soil.score_with_industry_v1"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _append_unique(values: list[str], *new_values: str) -> list[str]:
    result = list(values)
    for value in new_values:
        if value not in result:
            result.append(value)
    return result


def _with_common_backtest_output(plan: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    plan = copy.deepcopy(plan)
    plan["output"]["report_root"] = str(output_dir / "run-plan-backtests")
    plan["output"]["persist"] = True
    plan["output"]["artifact_detail"] = "full"
    plan["output"]["signal_audit_sample_limit"] = 0
    return plan


def _near_high_run_plan(base_plan: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    plan = _with_common_backtest_output(base_plan, output_dir)
    plan["run"]["id"] = "baoma-v1-dynamic-hs300-only-2006-2025-near-high-60d-gate-v1"

    attribution = plan["analysis"]["attribution"]
    attribution["enabled"] = True
    attribution["include"] = _append_unique(
        list(attribution.get("include", [])),
        NEAR_HIGH_FIELD,
    )

    entry_attribution = plan["analysis"]["entry_attribution"]
    entry_attribution["enabled"] = True
    entry_attribution["factors"] = _append_unique(
        list(entry_attribution.get("factors", [])),
        NEAR_HIGH_FIELD,
    )
    entry_attribution["entry_filter"] = {
        "enabled": True,
        "require_checks": [],
        "conditions": [
            {
                "field": NEAR_HIGH_FIELD,
                "operator": "eq",
                "value": "near_high",
                "action": "keep",
            }
        ],
        "missing_policy": "block",
        "reason_code": "ENTRY_NEAR_HIGH_60D_GATE_FILTERED",
        "blocked_by": "ENTRY_NEAR_HIGH_60D_GATE_V1",
    }
    return plan


def _gate_candidate_config(output_dir: Path) -> dict[str, Any]:
    return {
        "version": "hs300_only_gate_candidate_v1",
        "scope": "backtest_only",
        "created_from": {
            "formal_gate_report": str(FORMAL_GATE_REPORT),
            "base_run_plan": str(BASE_RUN_PLAN),
        },
        "live_trading": {
            "enabled": False,
            "note": "These gate definitions are materialized for backtest and review only; no live trading config is changed.",
        },
        "runner_integration": {
            "near_high_60d": "run_plan_ready",
            "soil_industry": "needs_attribution_field",
            "missing_field": SOIL_SCORE_FIELD,
            "available_support_field": INDUSTRY_ABOVE_MA60_FIELD,
        },
        "gates": [
            {
                "id": "near_high_60d",
                "label_zh": "60日接近高位",
                "mode": "entry_filter",
                "conditions": [
                    {
                        "field": NEAR_HIGH_FIELD,
                        "operator": "eq",
                        "value": "near_high",
                        "action": "keep",
                    }
                ],
                "missing_policy": "block",
            },
            {
                "id": "soil_ge_8_and_industry_above_ma60",
                "label_zh": "强土壤且行业在MA60上方",
                "mode": "entry_filter",
                "conditions": [
                    {
                        "field": SOIL_SCORE_FIELD,
                        "operator": "gte",
                        "value": 8,
                        "action": "keep",
                    },
                    {
                        "field": INDUSTRY_ABOVE_MA60_FIELD,
                        "operator": "eq",
                        "value": True,
                        "action": "keep",
                    },
                ],
                "missing_policy": "block",
                "runner_note": "Exact formal runner support requires adding the soil score attribution factor first.",
            },
        ],
        "output_dir": str(output_dir),
    }


def _format_pct(value: float) -> str:
    if pd.isna(value):
        return ""
    return f"{value:.2f}%"


def _metrics_table(metrics_path: Path) -> str:
    df = pd.read_csv(metrics_path)
    subset = df[
        (df["strategy_id"].str.startswith("wf_total."))
        & (df["max_new_per_day"] == 3)
        & (df["max_holding_count"] == 10)
        & (df["period_zh"].isin(["2013-2025", "2006-2014", "2015-2021", "2022-2025"]))
        & (df["gate_id"].isin(["no_gate", "near_high_60d", "soil_ge_8_and_industry_above_ma60"]))
    ].copy()
    subset["gate_sort"] = subset["gate_id"].map(
        {
            "no_gate": 0,
            "near_high_60d": 1,
            "soil_ge_8_and_industry_above_ma60": 2,
        }
    )
    subset["period_sort"] = subset["period_zh"].map(
        {
            "2013-2025": 0,
            "2006-2014": 1,
            "2015-2021": 2,
            "2022-2025": 3,
        }
    )
    subset = subset.sort_values(["period_sort", "gate_sort"])

    rows = [
        "| 时期 | Gate | 年化 | 最大回撤 | 交易数 | 胜率 | PF |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in subset.itertuples(index=False):
        rows.append(
            "| {period} | {gate} | {annualized} | {drawdown} | {trades} | {win_rate} | {pf:.2f} |".format(
                period=row.period_zh,
                gate=row.gate_label_zh,
                annualized=_format_pct(row.annualized_return_pct),
                drawdown=_format_pct(row.max_drawdown_pct),
                trades=int(row.trade_count),
                win_rate=_format_pct(row.win_rate_pct),
                pf=float(row.profit_factor),
            )
        )
    return "\n".join(rows)


def _write_report(output_dir: Path, metrics_path: Path) -> Path:
    report_path = output_dir / "formal_strategy_gate_config_report.zh.md"
    report = f"""# HS300-only 正式候选 Gate 配置报告

## 本次落地

- 已生成可直接被 run_plan 加载的 near_high_60d 回测配置：`run_plan_near_high_60d_gate_v1.json`
- 已生成 soil+industry 候选 gate 定义：`strategy_gate_candidates_v1.json`
- 本次范围是 backtest only，没有修改实盘配置。

## 接入状态

- `near_high_60d`：正式 runner 已有字段 `{NEAR_HIGH_FIELD}`，可以直接进入 run_plan entry_filter。
- `soil+industry`：行业字段 `{INDUSTRY_ABOVE_MA60_FIELD}` 已有；土壤分字段 `{SOIL_SCORE_FIELD}` 尚未进入正式 attribution declaration，因此先作为候选配置和离线 walk-forward 证据保留。

## 已有离线 Walk-forward 证据

口径：`wf_calibrated_total_score`，每日最多买入 3 只，最多持仓 10 只，资金/持仓/重复买入约束已计入。

{_metrics_table(metrics_path)}

## 判断

`near_high_60d` 可以先进入正式回测配置并跑真实 runner 回测。`soil+industry` 的证据也成立，但要先补 `entry.soil.score_with_industry_v1`，否则正式 runner 无法按同一口径过滤候选池。
"""
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-run-plan", type=Path, default=BASE_RUN_PLAN)
    parser.add_argument("--formal-gate-metrics", type=Path, default=FORMAL_GATE_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    base_plan = _load_json(args.base_run_plan)

    near_high_plan = _near_high_run_plan(base_plan, output_dir)
    _write_json(output_dir / "run_plan_near_high_60d_gate_v1.json", near_high_plan)
    _write_json(output_dir / "strategy_gate_candidates_v1.json", _gate_candidate_config(output_dir))
    report_path = _write_report(output_dir, args.formal_gate_metrics)

    print(f"Wrote {output_dir / 'run_plan_near_high_60d_gate_v1.json'}")
    print(f"Wrote {output_dir / 'strategy_gate_candidates_v1.json'}")
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()
