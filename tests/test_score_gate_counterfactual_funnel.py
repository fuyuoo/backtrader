import json
from pathlib import Path

import pytest

from attbacktrader.cli import score_gate_counterfactual_funnel as funnel_cli
from attbacktrader.reports import (
    SCORE_GATE_COUNTERFACTUAL_FUNNEL_SCHEMA,
    build_score_gate_counterfactual_funnel,
    build_segmented_factor_contribution_matrix,
    render_score_gate_counterfactual_funnel_markdown_zh,
    write_score_gate_counterfactual_funnel,
)


def test_score_gate_counterfactual_funnel_blocks_non_positive_factor_trades() -> None:
    matrix = build_segmented_factor_contribution_matrix(
        _environment_fit_payload(),
        min_segment_sample_count=1,
        min_total_sample_count=2,
    )

    report = build_score_gate_counterfactual_funnel(
        _environment_fit_payload(),
        matrix,
        min_positive_sample_count=4,
        min_positive_years=2,
        min_positive_average_return_pct=0.02,
        min_positive_win_rate=0.60,
        min_positive_max_loss_pct=-0.10,
        min_risk_sample_count=2,
    )
    markdown = render_score_gate_counterfactual_funnel_markdown_zh(report)

    assert report["schema"] == SCORE_GATE_COUNTERFACTUAL_FUNNEL_SCHEMA
    assert report["funnel"]["raw_completed_trades"] == 9
    assert report["funnel"]["gate_passed_trades"] == 6
    assert report["funnel"]["gate_blocked_trades"] == 3
    assert report["funnel"]["gate_blocked_losses"] == 3
    positive_labels = [item["label_zh"] for item in report["factor_screen"]["positive_gate_candidates"]]
    assert "趋势质量=good" in positive_labels
    assert "风险形态=calm" in positive_labels
    assert report["summary"]["gate_passed"]["min_return_pct"] == pytest.approx(-0.01)
    assert report["summary"]["gate_blocked"]["average_return_pct"] == pytest.approx(-0.06)
    assert report["summary"]["counterfactual_delta"]["blocked_loss_count"] == 3
    assert "## 正向 Gate 候选" in markdown
    assert "## 漏斗质量" in markdown


def test_score_gate_counterfactual_funnel_cli_writes_outputs(tmp_path: Path, capsys) -> None:
    source_path = tmp_path / "environment_fit.enriched.json"
    source_path.write_text(json.dumps(_environment_fit_payload(), ensure_ascii=False), encoding="utf-8")
    matrix = build_segmented_factor_contribution_matrix(
        _environment_fit_payload(),
        min_segment_sample_count=1,
        min_total_sample_count=2,
    )
    matrix_path = tmp_path / "segmented_factor_contribution_matrix.json"
    matrix_path.write_text(json.dumps(matrix, ensure_ascii=False), encoding="utf-8")

    exit_code = funnel_cli.main(
        [
            "--environment-fit",
            str(source_path),
            "--factor-matrix",
            str(matrix_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--min-positive-sample-count",
            "4",
            "--min-positive-years",
            "2",
            "--min-positive-average-return-pct",
            "0.02",
            "--min-positive-win-rate",
            "0.60",
            "--min-positive-max-loss-pct",
            "-0.10",
            "--min-risk-sample-count",
            "2",
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["schema"] == SCORE_GATE_COUNTERFACTUAL_FUNNEL_SCHEMA
    assert stdout["funnel"]["gate_passed_trades"] == 6
    assert stdout["positive_gate_candidate_count"] == 2
    assert (tmp_path / "out" / "score_gate_counterfactual_funnel.json").exists()
    assert (tmp_path / "out" / "score_gate_counterfactual_funnel.zh.md").exists()


def test_write_score_gate_counterfactual_funnel_returns_payload_with_artifacts(tmp_path: Path) -> None:
    matrix = build_segmented_factor_contribution_matrix(
        _environment_fit_payload(),
        min_segment_sample_count=1,
        min_total_sample_count=2,
    )
    report = build_score_gate_counterfactual_funnel(
        _environment_fit_payload(),
        matrix,
        min_positive_sample_count=4,
        min_positive_years=2,
        min_positive_average_return_pct=0.02,
        min_positive_win_rate=0.60,
        min_positive_max_loss_pct=-0.10,
        min_risk_sample_count=2,
    )

    json_path, markdown_path, payload = write_score_gate_counterfactual_funnel(report, output_dir=tmp_path)

    assert json_path.exists()
    assert markdown_path.exists()
    assert payload["artifacts"]["funnel_markdown_zh"].endswith("score_gate_counterfactual_funnel.zh.md")


def _environment_fit_payload() -> dict:
    return {
        "schema": "attbacktrader.environment_fit.v1",
        "run_id": "score-gate-test",
        "source_dir": "reports/score-gate-test",
        "environment_fields": [
            {"field": "entry.trend_quality", "label_zh": "趋势质量"},
            {"field": "entry.risk_shape", "label_zh": "风险形态"},
        ],
        "trade_contributions": [
            _trade(1, "2015-01-05", 0.10, "good", "calm"),
            _trade(2, "2015-02-05", 0.05, "good", "calm"),
            _trade(3, "2015-03-05", -0.05, "bad", "fragile"),
            _trade(4, "2016-01-05", 0.08, "good", "calm"),
            _trade(5, "2016-02-05", -0.01, "good", "calm"),
            _trade(6, "2016-03-05", -0.03, "neutral", "fragile"),
            _trade(7, "2017-01-05", 0.04, "good", "calm"),
            _trade(8, "2017-02-05", 0.03, "good", "calm"),
            _trade(9, "2017-03-05", -0.10, "bad", "fragile"),
        ],
    }


def _trade(trade_index: int, entry_date: str, return_pct: float, trend: str, risk: str) -> dict:
    return {
        "trade_index": trade_index,
        "symbol": f"00000{trade_index}.SZ",
        "entry_date": entry_date,
        "exit_date": entry_date,
        "outcome": "win" if return_pct > 0 else "loss",
        "exit_reason": "TAKE_PROFIT" if return_pct > 0 else "STOP_LOSS",
        "return_pct": return_pct,
        "environment": {
            "entry.trend_quality": trend,
            "entry.risk_shape": risk,
        },
        "contribution_available": True,
        "entry_gross_value": 1000.0,
        "exit_gross_value": 1000.0 * (1.0 + return_pct),
        "net_pnl": 1000.0 * return_pct,
        "return_on_entry_value": return_pct,
    }
