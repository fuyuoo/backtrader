import json
from pathlib import Path

from attbacktrader.cli import compare_environment_fit as compare_environment_fit_cli
from attbacktrader.reports import (
    build_environment_fit_comparison,
    render_environment_fit_comparison_markdown_zh,
    write_environment_fit_comparison,
)


def test_environment_fit_comparison_detects_stability_and_sample_risk(tmp_path: Path) -> None:
    baseline = _environment_fit_report(
        run_id="baseline",
        industry_true_net_pnl=1000.0,
        industry_true_return=0.10,
        industry_true_sample_count=3,
        best_capital_key="combination",
        best_capital_sample_count=1,
    )
    expanded = _environment_fit_report(
        run_id="expanded",
        industry_true_net_pnl=1600.0,
        industry_true_return=0.12,
        industry_true_sample_count=4,
        best_capital_key="single",
        best_capital_sample_count=1,
    )

    comparison = build_environment_fit_comparison((baseline, expanded), common_limit=5)
    markdown = render_environment_fit_comparison_markdown_zh(comparison)
    json_path, markdown_path = write_environment_fit_comparison(comparison, output_dir=tmp_path / "comparison")

    assert comparison["schema"] == "attbacktrader.environment_fit_comparison.v1"
    assert comparison["baseline_run_id"] == "baseline"
    assert comparison["source_count"] == 2
    assert comparison["best_environment_stability"][0]["status"] == "stable"
    assert comparison["best_environment_stability"][1]["status"] == "changed_with_sample_risk"
    assert comparison["common_environment_count"] >= 2
    assert comparison["drill_down_sample_count"] > 0
    assert comparison["drill_down_sample_refs"][0]["kind"] == "trade"
    assert comparison["drill_down_sample_refs"][0]["reason"] == "best_environment_representative_trade"
    first_common = comparison["common_environment_deltas"][0]
    assert first_common["deltas"][0]["run_id"] == "expanded"
    assert "环境适配对比" in markdown
    assert "稳定线索" in markdown
    assert "建议下钻样本" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def test_compare_environment_fit_cli_writes_outputs(tmp_path: Path, capsys) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    _write_json(first / "environment_fit.json", _environment_fit_report(run_id="first"))
    _write_json(second / "environment_fit.json", _environment_fit_report(run_id="second", industry_true_net_pnl=1200.0))

    exit_code = compare_environment_fit_cli.main(
        [
            "--run-dir",
            str(first),
            "--run-dir",
            str(second),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["schema"] == "attbacktrader.environment_fit_comparison.v1"
    assert stdout["source_count"] == 2
    assert stdout["drill_down_sample_count"] > 0
    assert stdout["best_environment_statuses"][0]["status"] == "stable"
    assert (tmp_path / "out" / "environment_fit_comparison.json").exists()
    assert (tmp_path / "out" / "environment_fit_comparison.zh.md").exists()


def _environment_fit_report(
    *,
    run_id: str,
    industry_true_net_pnl: float = 1000.0,
    industry_true_return: float = 0.10,
    industry_true_sample_count: int = 3,
    best_capital_key: str = "single",
    best_capital_sample_count: int = 3,
) -> dict:
    industry_true = {
        "summary_kind": "single_factor",
        "field": "industry.kdj.j_below_threshold",
        "value": True,
        "label_zh": "行业 KDJ J 低于阈值=是",
        "sample_count": industry_true_sample_count,
        "win_rate": 0.66,
        "average_return_pct": 0.08,
        "net_pnl": industry_true_net_pnl,
        "return_on_entry_value": industry_true_return,
        "trade_indexes": [1, 2, 3],
    }
    industry_false = {
        "summary_kind": "single_factor",
        "field": "industry.kdj.j_below_threshold",
        "value": False,
        "label_zh": "行业 KDJ J 低于阈值=否",
        "sample_count": 2,
        "win_rate": 0.5,
        "average_return_pct": 0.02,
        "net_pnl": 100.0,
        "return_on_entry_value": 0.01,
        "trade_indexes": [4, 5],
    }
    combination = {
        "summary_kind": "combination",
        "fields": {"industry.kdj.j_below_threshold": True, "market.hs300.bullish_trend": True},
        "label_zh": "行业 KDJ J 低于阈值=是；沪深300多头趋势=是",
        "sample_count": best_capital_sample_count,
        "win_rate": 1.0,
        "average_return_pct": 0.15,
        "net_pnl": 900.0,
        "return_on_entry_value": 0.2,
        "trade_indexes": [2],
    }
    best_capital = industry_true if best_capital_key == "single" else combination
    return {
        "schema": "attbacktrader.environment_fit.v1",
        "run_id": run_id,
        "source_dir": f"reports/{run_id}",
        "min_sample_count": 2,
        "trade_count": 5,
        "contribution_available_count": 5,
        "overall": {
            "net_pnl": industry_true_net_pnl + 100.0,
            "return_on_entry_value": industry_true_return,
        },
        "best_environments": {
            "best_by_net_pnl": industry_true,
            "best_by_return_on_entry_value": dict(best_capital, sample_count=best_capital_sample_count),
        },
        "sample_warnings": {
            "min_sample_count": 2,
            "low_sample_single_factor_count": 0,
            "low_sample_combination_count": 1,
        },
        "single_factor_summaries": [industry_true, industry_false],
        "combination_summaries": [combination],
        "trade_contributions": [],
    }


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
