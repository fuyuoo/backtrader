import json
from pathlib import Path

import pandas as pd

from scripts.check_entry_score_formal_parity import (
    DEFAULT_EXPECTED_CONTRACT,
    build_entry_score_formal_parity_report,
    parity_report_to_jsonable,
    render_entry_score_formal_parity_markdown_zh,
    write_entry_score_formal_parity_report,
)


def test_entry_score_formal_parity_check_accepts_matching_artifacts(tmp_path: Path) -> None:
    old_dir, new_dir = _write_artifacts(tmp_path)

    report = build_entry_score_formal_parity_report(old_formal_dir=old_dir, new_run_dir=new_dir)
    payload = parity_report_to_jsonable(report)
    markdown = render_entry_score_formal_parity_markdown_zh(report)
    json_path, markdown_path = write_entry_score_formal_parity_report(report, output_dir=tmp_path / "out")

    assert report.status == "ok"
    assert report.failed_count == 0
    assert payload["status"] == "ok"
    assert "Entry Score Formal Parity" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def test_entry_score_formal_parity_check_flags_selected_key_drift(tmp_path: Path) -> None:
    old_dir, new_dir = _write_artifacts(tmp_path)
    selected = pd.read_parquet(new_dir / "entry_score_selected_entries.parquet")
    selected.loc[0, "symbol"] = "000999.SZ"
    selected.to_parquet(new_dir / "entry_score_selected_entries.parquet", index=False)

    report = build_entry_score_formal_parity_report(old_formal_dir=old_dir, new_run_dir=new_dir)
    failed = {check.name: check for check in report.checks if check.status != "ok"}

    assert report.status == "failed"
    assert failed["selected.old_only_count"].actual == 1
    assert failed["selected.new_only_count"].actual == 1


def _write_artifacts(root: Path) -> tuple[Path, Path]:
    old_dir = root / "old"
    new_dir = root / "new"
    old_dir.mkdir()
    new_dir.mkdir()

    metrics = {
        "strategy_id": "ew_seed_only_v2",
        "max_new_positions_per_day": 5,
        "max_holding_count": 20,
        "cumulative_return": -0.0480068,
        "annualized_return": -0.0480068,
        "max_drawdown": 0.489458114161362,
        "sharpe_ratio": 0.0463467004669561,
        "sortino_ratio": 0.0421925578002602,
        "calmar_ratio": -0.0980815285537862,
        "trade_count": 2,
        "closed_trade_count": 2,
        "win_rate": 0.5,
        "profit_factor": 1.2,
        "average_trade_return": 0.01,
        "median_trade_return": 0.005,
        "average_win_return": 0.04,
        "average_loss_return": -0.02,
        "maximum_win_trade": 0.04,
        "maximum_loss_trade": -0.02,
        "average_holding_count": 1.5,
        "maximum_holding_count": 2,
        "average_cash_ratio": 0.2,
        "average_exposure": 0.8,
        "turnover": 3.0,
    }
    pd.DataFrame([metrics]).to_csv(old_dir / "formal_backtest_metrics.csv", index=False)

    selected = _parameter_rows(
        [
            {"symbol": "000001.SZ", "trade_date": "2024-01-05"},
            {"symbol": "000002.SZ", "trade_date": "2024-01-08"},
        ]
    )
    blocked = _parameter_rows([{"symbol": "000003.SZ", "trade_date": "2024-01-09"}])
    equity = _parameter_rows(
        [
            {
                "trade_date": "2024-01-05",
                "cash": 900.0,
                "position_value": 100.0,
                "total_value": 1000.0,
                "drawdown": 0.0,
                "holding_count": 1,
                "exposure": 0.1,
                "cash_ratio": 0.9,
            },
            {
                "trade_date": "2024-01-08",
                "cash": 800.0,
                "position_value": 210.0,
                "total_value": 1010.0,
                "drawdown": 0.0,
                "holding_count": 2,
                "exposure": 0.2079207920792079,
                "cash_ratio": 0.7920792079207921,
            },
        ]
    )
    selected.to_parquet(old_dir / "formal_backtest_selected_entries.parquet", index=False)
    blocked.to_parquet(old_dir / "formal_backtest_blocked_entries.parquet", index=False)
    equity.to_parquet(old_dir / "formal_backtest_equity_curves.parquet", index=False)

    contract = dict(DEFAULT_EXPECTED_CONTRACT)
    contract.update(
        {
            "schema": "attbacktrader.precomputed_score_portfolio_run.v1",
            "scope": "backtest_only",
            "score_id": "ew_seed_only_v2",
            "score_field": "entry.score.ew_seed_only_v2",
            "missing_score_policy": "skip",
        }
    )
    _write_json(new_dir / "entry_score_contract.json", contract)
    _write_json(
        new_dir / "entry_score_replay_summary.json",
        {
            "source": {"scope": "backtest_only"},
            "precomputed_score_contract": contract,
            "metrics": {key: metrics[key] for key in metrics if key not in {"strategy_id", "max_new_positions_per_day", "max_holding_count"}},
            "funnel": {"executed_entries": len(selected), "blocked_entries": len(blocked)},
        },
    )
    selected[["symbol", "trade_date"]].to_parquet(new_dir / "entry_score_selected_entries.parquet", index=False)
    blocked[["symbol", "trade_date"]].to_parquet(new_dir / "entry_score_blocked_entries.parquet", index=False)
    equity.drop(columns=["strategy_id", "max_new_positions_per_day", "max_holding_count"]).to_parquet(
        new_dir / "entry_score_equity_curve.parquet",
        index=False,
    )
    return old_dir, new_dir


def _parameter_rows(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["strategy_id"] = "ew_seed_only_v2"
    frame["max_new_positions_per_day"] = 5
    frame["max_holding_count"] = 20
    return frame


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
