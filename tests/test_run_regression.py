import json
from pathlib import Path

from attbacktrader.reports import (
    build_run_regression_report,
    render_run_regression_markdown_zh,
    run_ids_from_regression_baseline,
    run_regression_to_jsonable,
    write_run_regression_report,
)


def test_run_regression_validates_persisted_run_metrics(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path, final_value=1000000.0, add_on_signal_count=2)
    baseline = _baseline(final_value=1000000.0, add_on_signal_count=2)

    report = build_run_regression_report((run_dir,), baseline, baseline_path=tmp_path / "baseline.json")
    payload = run_regression_to_jsonable(report)
    markdown = render_run_regression_markdown_zh(report)
    json_path, markdown_path = write_run_regression_report(report, output_dir=tmp_path / "regression")

    assert report.status == "ok"
    assert report.failed_count == 0
    assert payload["checks"][0]["run_id"] == "baseline"
    assert "真实 Run 回归校验" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def test_run_regression_flags_metric_drift(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path, final_value=1000001.0, add_on_signal_count=2)
    baseline = _baseline(final_value=1000000.0, add_on_signal_count=2)

    report = build_run_regression_report((run_dir,), baseline)
    failed = [check for check in report.checks if check.status != "ok"]

    assert report.status == "failed"
    assert failed[0].metric == "final_value"
    assert failed[0].actual == 1000001.0


def test_run_regression_uses_baseline_run_ids_when_cli_does_not_specify_runs() -> None:
    baseline = _baseline(final_value=1000000.0, add_on_signal_count=2)

    assert run_ids_from_regression_baseline(baseline) == ("baseline",)


def _baseline(*, final_value: float, add_on_signal_count: int):
    return {
        "version": 1,
        "runs": {
            "baseline": {
                "metrics": {
                    "evidence_validation_status": "ok",
                    "evidence_validation_error_count": 0,
                    "final_value": final_value,
                    "trade_count": 1,
                    "execution_rejection_count": 1,
                    "rejection_reason_count.BOARD_LOT_TOO_SMALL": 1,
                    "add_on_signal_count": add_on_signal_count,
                },
                "tolerances": {"final_value": 0.000001},
            },
        },
    }


def _run_dir(root: Path, *, final_value: float, add_on_signal_count: int) -> Path:
    path = root / "baseline"
    path.mkdir()
    _write_json(path / "run_plan.json", {"run": {"id": "baseline"}})
    _write_json(
        path / "report.json",
        {
            "returns": {"final_equity": final_value, "cumulative_return": 0.0},
            "risk": {"max_drawdown": 0.0},
            "trade_quality": {"trade_count": 1, "win_rate": 1.0, "profit_loss_ratio": None},
            "execution_costs": {"completed_count": 2},
        },
    )
    _write_json(
        path / "result_diagnostics.json",
        {
            "portfolio_add_on_signal_count": add_on_signal_count,
            "symbols": [
                {
                    "execution_rejection_counts": [
                        {"reason": "BOARD_LOT_TOO_SMALL", "count": 1},
                    ],
                }
            ],
        },
    )
    _write_json(path / "signal_audit.json", [])
    _write_json(path / "evidence_validation.json", {"status": "ok", "error_count": 0, "warning_count": 0})
    return path


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
