from pathlib import Path

import pandas as pd

from scripts.audit_industry_enhanced_scorer_gate_candidates import (
    build_industry_enhanced_scorer_gate_audit,
    render_industry_enhanced_scorer_gate_audit_markdown_zh,
    write_industry_enhanced_scorer_gate_audit,
)


def test_industry_enhanced_scorer_gate_audit_builds_candidate_lifts(tmp_path: Path) -> None:
    report_dir = _write_trade_report(tmp_path)

    audit = build_industry_enhanced_scorer_gate_audit(industry_report_dir=report_dir)

    candidates = {item["candidate_id"]: item for item in audit["candidates"]}
    assert audit["schema"] == "attbacktrader.industry_enhanced_scorer_gate_audit.v1"
    assert audit["trade_count"] == 8
    assert candidates["conservative"]["metrics"]["trade_count"] == 3
    assert candidates["balanced"]["metrics"]["trade_count"] == 5
    assert candidates["aggressive"]["metrics"]["trade_count"] == 6
    assert candidates["conservative"]["lift"]["avg_return_pct_vs_all_trades"] > 0
    assert audit["recommendation"]["first_replay_candidate_id"] == "conservative"


def test_industry_enhanced_scorer_gate_audit_writes_json_and_markdown(tmp_path: Path) -> None:
    report_dir = _write_trade_report(tmp_path)
    audit = build_industry_enhanced_scorer_gate_audit(industry_report_dir=report_dir)

    markdown = render_industry_enhanced_scorer_gate_audit_markdown_zh(audit)
    json_path, markdown_path = write_industry_enhanced_scorer_gate_audit(audit, output_dir=tmp_path / "out")

    assert "含行业 Scorer/Gate 候选审计" in markdown
    assert "三档候选" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def _write_trade_report(root: Path) -> Path:
    report_dir = root / "industry-report"
    report_dir.mkdir()
    rows = [
        _row(2020, "very_strong_soil", "strong_seed", "strong_soil", 5.0, 500.0),
        _row(2020, "very_strong_soil", "neutral_seed", "strong_soil", 3.0, 300.0),
        _row(2021, "very_strong_soil", "weak_seed", "strong_soil", -1.0, -100.0),
        _row(2020, "strong_soil", "strong_seed", "strong_soil", 2.0, 200.0),
        _row(2021, "strong_soil", "strong_seed", "neutral_soil", -0.5, -50.0),
        _row(2021, "neutral_soil", "strong_seed", "neutral_soil", 1.0, 100.0),
        _row(2020, "very_weak_soil", "strong_seed", "weak_soil", -3.0, -300.0),
        _row(2021, "weak_soil", "weak_seed", "weak_soil", -2.0, -200.0),
    ]
    pd.DataFrame(rows).to_parquet(report_dir / "trade_soil_with_industry_v1.parquet", index=False)
    return report_dir


def _row(
    entry_year: int,
    soil: str,
    seed: str,
    no_industry_soil: str,
    return_pct: float,
    net_pnl: float,
) -> dict:
    return {
        "entry_year": entry_year,
        "return_pct": return_pct,
        "is_win": return_pct > 0,
        "net_pnl": net_pnl,
        "holding_days": 10,
        "soil_layer5_with_industry_v1": soil,
        "seed_layer_no_industry_v1": seed,
        "soil_layer_no_industry_v2": no_industry_soil,
    }
