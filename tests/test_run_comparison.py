import json
from pathlib import Path

from attbacktrader.reports import (
    build_run_comparison,
    render_run_comparison_markdown_zh,
    run_comparison_to_jsonable,
    write_run_comparison,
)


def test_build_run_comparison_summarizes_runs_and_deltas(tmp_path: Path) -> None:
    first = _run_dir(
        tmp_path,
        run_id="baseline",
        final_equity=1000000.0,
        cumulative_return=0.0,
        max_drawdown=0.05,
        trade_count=10,
        filtered_entries=0,
        add_on_signals=0,
    )
    second = _run_dir(
        tmp_path,
        run_id="filtered",
        final_equity=1015000.0,
        cumulative_return=0.015,
        max_drawdown=0.04,
        trade_count=6,
        filtered_entries=12,
        add_on_signals=2,
    )

    comparison = build_run_comparison((first, second))
    payload = run_comparison_to_jsonable(comparison)
    markdown = render_run_comparison_markdown_zh(comparison)
    json_path, markdown_path = write_run_comparison(comparison, output_dir=tmp_path / "comparison")

    assert comparison.baseline_run_id == "baseline"
    assert comparison.rows[1].entry_filter_count == 12
    assert comparison.rows[1].add_on_signal_count == 2
    assert comparison.rows[1].execution_rejection_reason_counts[0].reason == "BOARD_LOT_TOO_SMALL"
    assert comparison.rows[1].execution_rejection_reason_counts[0].count == 1
    assert comparison.deltas[0].final_value_delta == 15000.0
    assert comparison.deltas[0].trade_count_delta == -4
    assert payload["rows"][1]["run_id"] == "filtered"
    assert payload["rows"][1]["execution_rejection_reason_counts"][0]["reason"] == "BOARD_LOT_TOO_SMALL"
    assert "## 相对基准差异" in markdown
    assert "不足一手 (BOARD_LOT_TOO_SMALL):1" in markdown
    assert "filtered" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def _run_dir(
    root: Path,
    *,
    run_id: str,
    final_equity: float,
    cumulative_return: float,
    max_drawdown: float,
    trade_count: int,
    filtered_entries: int,
    add_on_signals: int,
) -> Path:
    path = root / run_id
    path.mkdir()
    _write_json(
        path / "run_plan.json",
        {
            "run": {"id": run_id, "from_date": "2024-01-01", "to_date": "2024-12-31"},
            "data": {"symbols": ["000001.SZ"]},
            "execution": {"engine": "business"},
        },
    )
    _write_json(
        path / "report.json",
        {
            "returns": {"final_equity": final_equity, "cumulative_return": cumulative_return},
            "risk": {"max_drawdown": max_drawdown},
            "trade_quality": {
                "trade_count": trade_count,
                "win_rate": 0.5,
                "profit_loss_ratio": 1.2,
            },
        },
    )
    _write_json(
        path / "result_diagnostics.json",
        {
            "symbols": [
                {
                    "symbol": "000001.SZ",
                    "execution_rejection_count": 1,
                    "execution_rejection_counts": [{"reason": "BOARD_LOT_TOO_SMALL", "count": 1}],
                    "sizing_blocked_count": 2,
                }
            ],
        },
    )
    _write_json(
        path / "signal_audit.json",
        [
            {"intent_type": "avoid", "reason_code": "ENTRY_ATTRIBUTION_FILTERED"}
            for _ in range(filtered_entries)
        ]
        + [
            {"intent_type": "add_on", "reason_code": "KDJ_OVERSOLD_ADD_ON"}
            for _ in range(add_on_signals)
        ],
    )
    return path


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
