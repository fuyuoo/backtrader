import json
from pathlib import Path

import pandas as pd

from scripts.run_industry_gate_replay_from_signal_audit import (
    build_industry_gate_replay_comparison,
    render_industry_gate_replay_comparison_markdown_zh,
    write_industry_gate_replay_comparison,
)


def test_industry_gate_replay_comparison_builds_from_signal_audit(tmp_path: Path) -> None:
    source_dir, industry_dir, balanced_dir, baseline_dir = _write_fixture(tmp_path)

    report = build_industry_gate_replay_comparison(
        source_run_dir=source_dir,
        industry_run_dir=industry_dir,
        balanced_run_dir=balanced_dir,
        no_industry_run_dir=baseline_dir,
        initial_cash=100_000,
        max_holding_count=2,
        max_new_positions_per_day=2,
        cash_reserve_ratio=0.0,
        industry_max_new_per_day=None,
    )

    candidates = {item["candidate_id"]: item for item in report["candidates"]}
    assert report["event_extraction"]["enter_event_count"] == 3
    assert candidates["industry_very_strong"]["precomputed_score_contract"]["matched_enter_score_count"] == 2
    assert candidates["industry_balanced"]["precomputed_score_contract"]["matched_enter_score_count"] == 3
    assert candidates["no_industry_strong"]["precomputed_score_contract"]["matched_enter_score_count"] == 3
    assert candidates["industry_very_strong"]["metrics"]["final_value"] is not None
    assert {item["tested_candidate_id"] for item in report["comparison"]["candidate_comparisons"]} == {
        "industry_very_strong",
        "industry_balanced",
    }


def test_industry_gate_replay_comparison_writes_outputs(tmp_path: Path) -> None:
    source_dir, industry_dir, balanced_dir, baseline_dir = _write_fixture(tmp_path)
    report = build_industry_gate_replay_comparison(
        source_run_dir=source_dir,
        industry_run_dir=industry_dir,
        balanced_run_dir=balanced_dir,
        no_industry_run_dir=baseline_dir,
        initial_cash=100_000,
        max_holding_count=2,
        max_new_positions_per_day=2,
        cash_reserve_ratio=0.0,
        industry_max_new_per_day=None,
    )

    markdown = render_industry_gate_replay_comparison_markdown_zh(report)
    json_path, markdown_path = write_industry_gate_replay_comparison(report, output_dir=tmp_path / "out")

    assert "含行业 Gate Runner Replay 对照" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def _write_fixture(root: Path) -> tuple[Path, Path, Path, Path]:
    source_dir = root / "source"
    industry_dir = root / "industry"
    balanced_dir = root / "balanced"
    baseline_dir = root / "baseline"
    for path in (source_dir, industry_dir, balanced_dir, baseline_dir):
        path.mkdir()

    stock_pool = root / "stock_pool.csv"
    pd.DataFrame({"symbol": ["000001.SZ", "000002.SZ", "000003.SZ"]}).to_csv(stock_pool, index=False)
    (source_dir / "run_plan.json").write_text(
        json.dumps({"data": {"stock_pool_file": str(stock_pool)}}, ensure_ascii=False),
        encoding="utf-8",
    )
    signal_rows = [
        _signal("enter", "000001.SZ", "2024-01-02", 10.0),
        _signal("enter", "000002.SZ", "2024-01-02", 10.0),
        _signal("enter", "000003.SZ", "2024-01-03", 10.0),
        _signal("exit_profit", "000001.SZ", "2024-01-05", 12.0),
        _signal("exit_loss", "000002.SZ", "2024-01-05", 9.0),
        _signal("hold", "000003.SZ", "2024-01-06", 11.0),
    ]
    pd.DataFrame(signal_rows).to_parquet(source_dir / "signal_audit.parquet", index=False)

    pd.DataFrame(
        [
            {"symbol": "000001.SZ", "entry_date": "2024-01-02", "entry.score.industry_very_strong_soil_v1": 20},
            {"symbol": "000003.SZ", "entry_date": "2024-01-03", "entry.score.industry_very_strong_soil_v1": 18},
        ]
    ).to_parquet(industry_dir / "entry_score_artifact.parquet", index=False)
    pd.DataFrame(
        [
            {"symbol": "000001.SZ", "entry_date": "2024-01-02", "entry.score.industry_balanced_soil_v1": 20},
            {"symbol": "000002.SZ", "entry_date": "2024-01-02", "entry.score.industry_balanced_soil_v1": 14},
            {"symbol": "000003.SZ", "entry_date": "2024-01-03", "entry.score.industry_balanced_soil_v1": 18},
        ]
    ).to_parquet(balanced_dir / "entry_score_artifact.parquet", index=False)
    pd.DataFrame(
        [
            {"symbol": "000001.SZ", "entry_date": "2024-01-02", "entry.score.no_industry_strong_soil_v2": 10},
            {"symbol": "000002.SZ", "entry_date": "2024-01-02", "entry.score.no_industry_strong_soil_v2": 12},
            {"symbol": "000003.SZ", "entry_date": "2024-01-03", "entry.score.no_industry_strong_soil_v2": 8},
        ]
    ).to_parquet(baseline_dir / "entry_score_artifact.parquet", index=False)
    return source_dir, industry_dir, balanced_dir, baseline_dir


def _signal(intent_type: str, symbol: str, trade_date: str, close: float) -> dict:
    return {
        "intent_type": intent_type,
        "symbol": symbol,
        "trade_date": trade_date,
        "signal_values": json.dumps({"attribution": {"values": {"symbol.close": close}}}, ensure_ascii=False),
    }
