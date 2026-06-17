import json
from pathlib import Path

from attbacktrader.cli import entry_factor_validation_classification as classification_cli
from attbacktrader.reports import (
    ENTRY_FACTOR_VALIDATION_CLASSIFICATION_SCHEMA,
    build_entry_factor_validation_classification,
    render_entry_factor_validation_classification_markdown_zh,
    write_entry_factor_validation_classification,
)


def test_entry_factor_validation_classification_stratifies_year_and_objective_stage(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    baseline_dir = report_root / "baseline"
    stable_dir = report_root / "candidate-stable"
    dependent_dir = report_root / "candidate-dependent"
    noise_dir = report_root / "candidate-noise"
    small_dir = report_root / "candidate-small"

    _write_run_artifacts(
        baseline_dir,
        [
            _trade(1, "2023-01-05", -100, 1000, "bullish"),
            _trade(2, "2023-02-05", -50, 1000, "mixed"),
            _trade(3, "2024-01-05", -60, 1000, "bullish"),
            _trade(4, "2024-02-05", -90, 1000, "mixed"),
        ],
    )
    _write_run_artifacts(
        stable_dir,
        [
            _trade(1, "2023-01-05", 120, 1000, "bullish"),
            _trade(2, "2023-02-05", 80, 1000, "mixed"),
            _trade(3, "2024-01-05", 90, 1000, "bullish"),
            _trade(4, "2024-02-05", 70, 1000, "mixed"),
        ],
    )
    _write_run_artifacts(
        dependent_dir,
        [
            _trade(1, "2023-01-05", 120, 1000, "bullish"),
            _trade(2, "2023-02-05", -200, 1000, "mixed"),
            _trade(3, "2024-01-05", 110, 1000, "bullish"),
            _trade(4, "2024-02-05", -190, 1000, "mixed"),
        ],
    )
    _write_run_artifacts(
        noise_dir,
        [
            _trade(1, "2023-01-05", -150, 1000, "bullish"),
            _trade(2, "2023-02-05", -90, 1000, "mixed"),
            _trade(3, "2024-01-05", -120, 1000, "bullish"),
            _trade(4, "2024-02-05", -130, 1000, "mixed"),
        ],
    )
    _write_run_artifacts(
        small_dir,
        [
            _trade(1, "2023-01-05", 120, 1000, "bullish"),
        ],
    )

    matrix = _matrix(
        [
            _row(1, "positive", "keep", "industry.macd.energy_zone", "red", stable_dir, "supports_candidate", 4),
            _row(2, "negative", "exclude", "symbol.ma.price_above_ma60", False, dependent_dir, "supports_candidate", 4),
            _row(3, "positive", "keep", "symbol.kdj.state", "low", noise_dir, "rejects_candidate", 4),
            _row(4, "positive", "keep", "industry.sw_l1.code", "801150.SI", small_dir, "supports_candidate", 1),
        ]
    )

    report = build_entry_factor_validation_classification(
        matrix,
        report_root=report_root,
        min_total_trades=2,
        min_year_trades=1,
        min_stage_trades=1,
    )

    assert report["schema"] == ENTRY_FACTOR_VALIDATION_CLASSIFICATION_SCHEMA
    by_index = {row["candidate_index"]: row for row in report["rows"]}
    assert by_index[1]["classification"] == "stable_favorable"
    assert by_index[2]["classification"] == "market_stage_dependent"
    assert by_index[3]["classification"] == "noise"
    assert by_index[4]["classification"] == "insufficient_sample"
    assert by_index[1]["stage_source"] == "objective_wide_samples"
    assert by_index[1]["year_slices"][0]["slice_key"] == "2023"
    assert by_index[2]["market_stage_slices"][1]["status"] == "fails_candidate"
    assert report["classification_counts"]["stable_favorable"] == 1
    assert report["classification_counts"]["market_stage_dependent"] == 1

    markdown = render_entry_factor_validation_classification_markdown_zh(report)
    assert "入场因子分层分类报告" in markdown
    assert "稳定有利" in markdown
    assert "阶段依赖" in markdown


def test_entry_factor_validation_classification_cli_writes_outputs(tmp_path: Path, capsys) -> None:
    report_root = tmp_path / "reports"
    baseline_dir = report_root / "baseline"
    candidate_dir = report_root / "candidate"
    _write_run_artifacts(
        baseline_dir,
        [
            _trade(1, "2023-01-05", -100, 1000, "bullish"),
            _trade(2, "2024-01-05", -100, 1000, "mixed"),
        ],
    )
    _write_run_artifacts(
        candidate_dir,
        [
            _trade(1, "2023-01-05", 100, 1000, "bullish"),
            _trade(2, "2024-01-05", 100, 1000, "mixed"),
        ],
    )
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(_matrix([_row(1, "positive", "keep", "symbol.factor", "x", candidate_dir, "supports_candidate", 2)])),
        encoding="utf-8",
    )

    exit_code = classification_cli.main(
        [
            "--matrix",
            str(matrix_path),
            "--report-root",
            str(report_root),
            "--output-dir",
            str(tmp_path / "out"),
            "--min-total-trades",
            "1",
            "--min-year-trades",
            "1",
            "--min-stage-trades",
            "1",
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["schema"] == ENTRY_FACTOR_VALIDATION_CLASSIFICATION_SCHEMA
    assert stdout["rows"][0]["classification"] == "stable_favorable"
    assert Path(stdout["artifacts"]["classification_json"]).exists()
    assert Path(stdout["artifacts"]["classification_markdown_zh"]).exists()

    json_path, markdown_path, payload = write_entry_factor_validation_classification(
        stdout,
        output_dir=tmp_path / "manual",
    )
    assert json_path.exists()
    assert markdown_path.exists()
    assert payload["artifacts"]["classification_json"].endswith("entry_factor_validation_classification.json")


def _matrix(rows: list[dict]) -> dict:
    return {
        "schema": "attbacktrader.entry_factor_validation_matrix.v1",
        "source_manifest": "manifest.json",
        "baseline": {
            "run_id": "baseline",
            "metrics": {"trade_count": 4, "cumulative_return": -0.03, "max_drawdown": 0.02},
        },
        "record_count": len(rows),
        "rows": rows,
        "rankings": {"by_validation_score": rows},
    }


def _row(
    index: int,
    direction: str,
    action: str,
    field_key: str,
    value: object,
    run_dir: Path,
    status: str,
    trade_count: int,
) -> dict:
    return {
        "candidate_index": index,
        "candidate_rank": index,
        "direction": direction,
        "action": action,
        "field_key": field_key,
        "field_label_zh": field_key,
        "value": value,
        "value_label_zh": str(value),
        "run_id": run_dir.name,
        "status": status,
        "validation_score": 2.0 if status == "supports_candidate" else -2.0,
        "metrics": {"trade_count": trade_count, "cumulative_return": 0.02, "max_drawdown": 0.01},
        "artifacts": {
            "output_dir": str(run_dir),
            "trades": str(run_dir / "trades.json"),
        },
    }


def _trade(index: int, entry_date: str, net_pnl: float, entry_value: float, stage: str) -> dict:
    return {
        "trade_index": index,
        "symbol": f"00000{index}.SZ",
        "entry_date": entry_date,
        "exit_date": entry_date,
        "entry_gross_value": entry_value,
        "net_pnl": net_pnl,
        "realized_return_pct": net_pnl / entry_value,
        "entry_stage": stage,
    }


def _write_run_artifacts(run_dir: Path, trades: list[dict]) -> None:
    run_dir.mkdir(parents=True)
    (run_dir / "trades.json").write_text(
        json.dumps({"schema": "test.trades", "closed_trades": trades}),
        encoding="utf-8",
    )
    wide_dir = run_dir / "full_entry_scope_environment_fit_review"
    wide_dir.mkdir()
    (wide_dir / "attribution_wide_samples.json").write_text(
        json.dumps(
            {
                "schema": "attbacktrader.attribution_wide_samples.v1",
                "run_id": run_dir.name,
                "sample_count": len(trades),
                "samples": [
                    {
                        "trade_index": trade["trade_index"],
                        "field_values": {
                            "market.objective.entry_stage": {
                                "bucket": trade["entry_stage"],
                                "raw": {"stage": trade["entry_stage"]},
                            }
                        },
                    }
                    for trade in trades
                ],
            }
        ),
        encoding="utf-8",
    )
