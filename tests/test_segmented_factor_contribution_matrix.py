import json
from pathlib import Path

import pytest

from attbacktrader.cli import segmented_factor_contribution_matrix as segmented_cli
from attbacktrader.reports import (
    SEGMENTED_FACTOR_CONTRIBUTION_MATRIX_SCHEMA,
    build_segmented_factor_contribution_matrix,
    render_segmented_factor_contribution_matrix_markdown_zh,
    write_segmented_factor_contribution_matrix,
)


def test_segmented_factor_contribution_matrix_classifies_factor_environment_fit() -> None:
    report = build_segmented_factor_contribution_matrix(
        _environment_fit_payload(),
        segments=_segments(),
        min_segment_sample_count=2,
        min_total_sample_count=4,
    )
    markdown = render_segmented_factor_contribution_matrix_markdown_zh(report, ranking_limit=10)

    assert report["schema"] == SEGMENTED_FACTOR_CONTRIBUTION_MATRIX_SCHEMA
    assert report["trade_count"] == 12
    assert report["field_count"] == 3
    assert len(report["segment_overall"]) == 3
    assert "## 稳定正向候选" in markdown
    assert "区间是研究镜头" in report["segment_policy"]["caveat_zh"]

    bull = _bucket(report, "entry.trend_state", "bullish")
    assert bull["assessment"] == "stable_positive"
    assert bull["positive_segment_count"] == 3
    assert bull["outperform_segment_count"] == 3
    assert bull["summary"]["return_on_entry_value"] == pytest.approx(0.075)
    assert bull["segments"][0]["lift_vs_segment"]["return_on_entry_value"] == pytest.approx(0.05)

    not_bull = _bucket(report, "entry.trend_state", "not_bullish")
    assert not_bull["assessment"] == "mostly_negative"
    assert not_bull["negative_segment_count"] == 3

    far = _bucket(report, "entry.ma60_distance", "far")
    assert far["assessment"] == "environment_specific"
    assert far["best_segment"]["segment_id"] == "seg_a"
    assert far["worst_segment"]["segment_id"] == "seg_b"

    stable_labels = [item["label_zh"] for item in report["rankings"]["stable_positive"]]
    assert "趋势状态=bullish" in stable_labels
    assert not any("入场到出场阶段" in label for label in stable_labels)
    assert any(item["field_usage"] == "diagnostic_only" for item in report["rankings"]["diagnostic_only"])


def test_segmented_factor_contribution_matrix_cli_writes_outputs(tmp_path: Path, capsys) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source_path = source_dir / "environment_fit.enriched.json"
    source_path.write_text(json.dumps(_environment_fit_payload(), ensure_ascii=False), encoding="utf-8")

    exit_code = segmented_cli.main(
        [
            "--environment-fit",
            str(source_dir),
            "--output-dir",
            str(tmp_path / "out"),
            "--segment",
            "seg_a:2015-01-01:2015-12-31:区间A",
            "--segment",
            "seg_b:2016-01-01:2016-12-31:区间B",
            "--segment",
            "seg_c:2017-01-01:2017-12-31:区间C",
            "--min-segment-sample-count",
            "2",
            "--min-total-sample-count",
            "4",
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["schema"] == SEGMENTED_FACTOR_CONTRIBUTION_MATRIX_SCHEMA
    assert stdout["trade_count"] == 12
    assert (tmp_path / "out" / "segmented_factor_contribution_matrix.json").exists()
    assert (tmp_path / "out" / "segmented_factor_contribution_matrix.zh.md").exists()

    payload = json.loads((tmp_path / "out" / "segmented_factor_contribution_matrix.json").read_text(encoding="utf-8"))
    assert payload["artifacts"]["matrix_json"].endswith("segmented_factor_contribution_matrix.json")


def test_write_segmented_factor_contribution_matrix_returns_payload_with_artifacts(tmp_path: Path) -> None:
    report = build_segmented_factor_contribution_matrix(
        _environment_fit_payload(),
        segments=_segments(),
        min_segment_sample_count=2,
        min_total_sample_count=4,
    )
    json_path, markdown_path, payload = write_segmented_factor_contribution_matrix(report, output_dir=tmp_path)

    assert json_path.exists()
    assert markdown_path.exists()
    assert payload["artifacts"]["matrix_markdown_zh"].endswith("segmented_factor_contribution_matrix.zh.md")


def _bucket(report: dict, field: str, value: str) -> dict:
    return next(
        row
        for row in report["factor_bucket_matrix"]
        if row["field"] == field and row["value"] == value
    )


def _segments() -> list[dict]:
    return [
        {"segment_id": "seg_a", "label_zh": "区间A", "start": "2015-01-01", "end": "2015-12-31"},
        {"segment_id": "seg_b", "label_zh": "区间B", "start": "2016-01-01", "end": "2016-12-31"},
        {"segment_id": "seg_c", "label_zh": "区间C", "start": "2017-01-01", "end": "2017-12-31"},
    ]


def _environment_fit_payload() -> dict:
    return {
        "schema": "attbacktrader.environment_fit.v1",
        "run_id": "segmented-test",
        "source_dir": "reports/segmented-test",
        "environment_fields": [
            {"field": "entry.trend_state", "label_zh": "趋势状态"},
            {"field": "entry.ma60_distance", "label_zh": "MA60距离"},
            {"field": "market.objective.entry_to_exit_stage", "label_zh": "入场到出场阶段"},
        ],
        "trade_contributions": [
            _trade(1, "2015-01-05", 0.10, "bullish", "far"),
            _trade(2, "2015-02-05", 0.05, "bullish", "far"),
            _trade(3, "2015-03-05", -0.02, "not_bullish", "near"),
            _trade(4, "2015-04-05", -0.03, "not_bullish", "near"),
            _trade(5, "2016-01-05", 0.10, "bullish", "near"),
            _trade(6, "2016-02-05", 0.05, "bullish", "near"),
            _trade(7, "2016-03-05", -0.02, "not_bullish", "far"),
            _trade(8, "2016-04-05", -0.03, "not_bullish", "far"),
            _trade(9, "2017-01-05", 0.10, "bullish", "far"),
            _trade(10, "2017-02-05", 0.05, "bullish", "far"),
            _trade(11, "2017-03-05", -0.02, "not_bullish", "near"),
            _trade(12, "2017-04-05", -0.03, "not_bullish", "near"),
        ],
    }


def _trade(trade_index: int, entry_date: str, return_pct: float, trend: str, distance: str) -> dict:
    return {
        "trade_index": trade_index,
        "symbol": "000001.SZ",
        "entry_date": entry_date,
        "exit_date": entry_date,
        "outcome": "win" if return_pct > 0 else "loss",
        "exit_reason": "TAKE_PROFIT" if return_pct > 0 else "STOP_LOSS",
        "return_pct": return_pct,
        "environment": {
            "entry.trend_state": trend,
            "entry.ma60_distance": distance,
            "market.objective.entry_to_exit_stage": "mixed_to_bullish" if return_pct > 0 else "mixed_to_bearish",
        },
        "contribution_available": True,
        "entry_gross_value": 1000.0,
        "exit_gross_value": 1000.0 * (1.0 + return_pct),
        "net_pnl": 1000.0 * return_pct,
        "return_on_entry_value": return_pct,
    }
