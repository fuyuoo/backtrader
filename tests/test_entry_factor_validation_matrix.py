import json
from pathlib import Path
from types import SimpleNamespace

from attbacktrader.cli import entry_factor_validation_matrix as matrix_cli
from attbacktrader.reports import (
    ENTRY_FACTOR_VALIDATION_MATRIX_SCHEMA,
    build_entry_factor_validation_manifest,
    build_entry_factor_validation_matrix,
    render_entry_factor_validation_matrix_markdown_zh,
    write_entry_factor_validation_manifest,
)


def test_entry_factor_validation_matrix_ranks_real_validation_records() -> None:
    matrix = build_entry_factor_validation_matrix(
        [_validation_record(1, cumulative_return=0.02, max_drawdown=0.01), _validation_record(2, cumulative_return=0.05, max_drawdown=0.02)],
        baseline_metrics={"cumulative_return": 0.01, "max_drawdown": 0.015, "win_rate": 0.50, "profit_loss_ratio": 1.0},
        baseline_run_id="baoma-baseline",
    )

    assert matrix["schema"] == ENTRY_FACTOR_VALIDATION_MATRIX_SCHEMA
    assert matrix["baseline"]["run_id"] == "baoma-baseline"
    assert matrix["record_count"] == 2
    assert [row["candidate_index"] for row in matrix["rankings"]["by_validation_score"]] == [2, 1]
    assert matrix["rows"][0]["deltas"]["cumulative_return"] == 0.01
    assert matrix["rows"][0]["status"] in {"supports_candidate", "mixed", "rejects_candidate"}

    markdown = render_entry_factor_validation_matrix_markdown_zh(matrix)
    assert "入场单因子真实验证矩阵" in markdown
    assert "baoma-baseline" in markdown


def test_entry_factor_validation_matrix_cli_executes_manifest_candidates_and_resumes(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    manifest = build_entry_factor_validation_manifest(
        _discovery_report_fixture(),
        _baseline_run_plan_fixture(),
        positive_limit=1,
        negative_limit=1,
        reuse_snapshots=True,
    )
    manifest_path, _, _ = write_entry_factor_validation_manifest(manifest, output_dir=tmp_path / "manifest")
    calls: list[str] = []

    def fake_execute(run_plan, provider=None, prepared_data_cache=None, snapshot_read_cache=None):
        calls.append(run_plan.run.id)
        return SimpleNamespace(run_id=run_plan.run.id)

    def fake_write_artifacts(run_plan, result, *, output_root):
        output_dir = Path(output_root) / result.run_id
        output_dir.mkdir(parents=True)
        evidence_path = output_dir / "evidence_validation.json"
        evidence_path.write_text(json.dumps({"status": "ok", "error_count": 0, "warning_count": 0}), encoding="utf-8")
        return SimpleNamespace(
            output_dir=output_dir,
            report_chinese_markdown_path=output_dir / "report.zh.md",
            report_path=output_dir / "report.json",
            trades_path=output_dir / "trades.json",
            environment_fit_path=output_dir / "environment_fit.json",
            trade_review_path=output_dir / "trade_review.json",
            trade_attribution_path=output_dir / "trade_attribution.json",
            post_exit_analysis_path=output_dir / "post_exit_analysis.json",
            evidence_validation_path=evidence_path,
            attribution_factor_selection_path=output_dir / "attribution_factor_selection.json",
        )

    def fake_summary(run_plan, result, artifact_paths=None):
        return_value = 0.03 if "neg" in result.run_id else 0.02
        return {
            "schema": "attbacktrader.run_execution_summary.v1",
            "run": {"id": result.run_id, "from_date": "2023-01-01", "to_date": "2024-12-31"},
            "metrics": {
                "cumulative_return": return_value,
                "max_drawdown": 0.01,
                "trade_count": 12,
                "win_rate": 0.58,
                "profit_loss_ratio": 1.3,
            },
            "benchmarks": [{"symbol": "000300.SH", "excess_return": 0.01}],
            "evidence": {"status": "ok", "error_count": 0, "warning_count": 0},
        }

    monkeypatch.setattr(matrix_cli, "execute_run_plan", fake_execute)
    monkeypatch.setattr(matrix_cli, "write_run_artifacts", fake_write_artifacts)
    monkeypatch.setattr(matrix_cli, "build_run_execution_summary", fake_summary)

    exit_code = matrix_cli.main(
        [
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(tmp_path / "matrix"),
            "--output-root",
            str(tmp_path / "reports"),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert len(calls) == 2
    assert stdout["schema"] == ENTRY_FACTOR_VALIDATION_MATRIX_SCHEMA
    assert stdout["record_count"] == 2
    assert Path(stdout["artifacts"]["matrix_json"]).exists()
    assert Path(stdout["artifacts"]["matrix_markdown_zh"]).exists()
    assert Path(stdout["artifacts"]["batch_status"]).exists()
    assert len(stdout["artifacts"]["validation_records"]) == 2

    calls.clear()
    exit_code = matrix_cli.main(
        [
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(tmp_path / "matrix"),
            "--output-root",
            str(tmp_path / "reports"),
            "--resume",
        ]
    )
    resumed = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert calls == []
    assert resumed["record_count"] == 2


def _validation_record(candidate_index: int, *, cumulative_return: float, max_drawdown: float) -> dict:
    return {
        "schema": "attbacktrader.entry_factor_validation_run.v1",
        "candidate": {
            "candidate_index": candidate_index,
            "candidate_rank": candidate_index,
            "direction": "positive" if candidate_index == 1 else "negative",
            "action": "keep" if candidate_index == 1 else "exclude",
            "field_key": f"symbol.factor_{candidate_index}",
            "value": "x",
            "value_label_zh": "x",
            "sample_count": 100 + candidate_index,
            "factor_quality_score": 1.0 / candidate_index,
            "run_id": f"run-{candidate_index}",
        },
        "run": {"id": f"run-{candidate_index}", "from_date": "2023-01-01", "to_date": "2024-12-31"},
        "run_summary": {
            "metrics": {
                "cumulative_return": cumulative_return,
                "max_drawdown": max_drawdown,
                "trade_count": 10 + candidate_index,
                "win_rate": 0.55,
                "profit_loss_ratio": 1.2,
            },
            "benchmarks": [{"symbol": "000300.SH", "excess_return": cumulative_return - 0.01}],
            "evidence": {"status": "ok"},
        },
        "artifacts": {"validation_json": f"candidate-{candidate_index}/entry_factor_validation_run.json"},
    }


def _discovery_report_fixture() -> dict:
    return {
        "schema": "attbacktrader.bayesian_factor_discovery.v1",
        "run_id": "discovery-test",
        "rankings": {
            "tradable_pre_entry": {
                "positive": [_candidate("symbol.ma.trend_state", "bullish", "positive", 1.5, 8)],
                "negative": [_candidate("symbol.macd.energy_zone", "green_bar_or_zero", "negative", -1.4, 8)],
            },
        },
    }


def _candidate(field_key: str, value: str, direction: str, score: float, sample_count: int) -> dict:
    return {
        "field_key": field_key,
        "field_label_zh": field_key,
        "value": value,
        "value_label_zh": value,
        "direction": direction,
        "factor_quality_score": score,
        "sample_count": sample_count,
        "future_function_guard": {"eligible_for_entry_rule_review": True},
        "flags": [],
    }


def _baseline_run_plan_fixture() -> dict:
    return {
        "run": {"id": "baoma-baseline", "from_date": "2023-01-01", "to_date": "2024-12-31"},
        "data": {
            "snapshot_root": "data/snapshots",
            "refresh_snapshots": True,
            "symbols": ["000001.SZ"],
            "benchmark_series": {"indexes": ["000300.SH"]},
        },
        "strategy": {
            "template": "trend_template_v1",
            "entry_method": "baoma_entry",
            "profit_taking_method": "baoma_ma25_profit_exit",
            "stop_loss_method": "baoma_ma60_stop",
            "add_on_method": "baoma_add_on",
            "sizing_rule": "equal_weight",
            "sizing_params": {"max_holding_count": 800, "min_order_quantity": 100},
        },
        "constraints": {"ashare": {"enabled": True, "board_lot_size": 100}},
        "broker": {
            "initial_cash": 1_200_000,
            "commission_rate": 0.0003,
            "stamp_tax_rate": 0.001,
            "transfer_fee_rate": 0.00001,
            "slippage": {"type": "percent", "value": 0.0005},
        },
        "execution": {
            "engine": "baoma_v1_business",
            "stake": 100,
            "baoma": {
                "buy_slice_fraction": 0.25,
                "first_scale_out_return": 0.04,
                "second_scale_out_return": 0.12,
                "scale_out_mode": "atr_multiple",
                "first_scale_out_atr_multiple": 2.0,
                "second_scale_out_atr_multiple": 4.0,
            },
        },
        "analysis": {
            "industry_attribution": {"enabled": False},
            "market_regime": {"enabled": False},
            "scenario_fit": {"enabled": False},
        },
    }
