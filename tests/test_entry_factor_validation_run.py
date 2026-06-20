import json
from pathlib import Path
from types import SimpleNamespace

import yaml

from attbacktrader.cli import entry_factor_validation_run as run_cli
from attbacktrader.config import RunPlan
from attbacktrader.reports import (
    ENTRY_FACTOR_VALIDATION_RUN_SCHEMA,
    build_entry_factor_validation_manifest,
    render_entry_factor_validation_run_markdown_zh,
    write_entry_factor_validation_manifest,
)


def test_entry_factor_validation_run_cli_executes_one_manifest_candidate(tmp_path: Path, monkeypatch, capsys) -> None:
    manifest = build_entry_factor_validation_manifest(
        _discovery_report_fixture(),
        _baseline_run_plan_fixture(),
        positive_limit=1,
        negative_limit=1,
        reuse_snapshots=True,
    )
    manifest_path, _, _ = write_entry_factor_validation_manifest(
        manifest,
        output_dir=tmp_path / "manifest",
    )

    calls = {}

    def fake_execute(run_plan, provider=None):
        calls["run_plan"] = run_plan
        calls["provider"] = provider
        return SimpleNamespace(run_id=run_plan.run.id)

    def fake_write_artifacts(run_plan, result, *, output_root):
        output_dir = Path(output_root) / result.run_id
        output_dir.mkdir(parents=True)
        evidence_path = output_dir / "evidence_validation.json"
        evidence_path.write_text(
            json.dumps({"status": "ok", "error_count": 0, "warning_count": 0}),
            encoding="utf-8",
        )
        return SimpleNamespace(
            output_dir=output_dir,
            report_chinese_markdown_path=output_dir / "report.zh.md",
            report_path=output_dir / "report.json",
            trades_path=output_dir / "trades.json",
            environment_fit_path=output_dir / "environment_fit.json",
            trade_review_path=output_dir / "trade_review.json",
            post_exit_analysis_path=output_dir / "post_exit_analysis.json",
            evidence_validation_path=evidence_path,
            attribution_factor_selection_path=output_dir / "attribution_factor_selection.json",
        )

    monkeypatch.setattr(run_cli, "execute_run_plan", fake_execute)
    monkeypatch.setattr(run_cli, "write_run_artifacts", fake_write_artifacts)
    monkeypatch.setattr(
        run_cli,
        "build_run_execution_summary",
        lambda run_plan, result, artifact_paths=None: {
            "schema": "attbacktrader.run_execution_summary.v1",
            "run": {"id": result.run_id},
            "metrics": {"cumulative_return": 0.07, "max_drawdown": 0.03, "win_rate": 0.6},
            "artifacts": {"output_dir": str(artifact_paths.output_dir)},
        },
    )

    exit_code = run_cli.main(
        [
            "--manifest",
            str(manifest_path),
            "--candidate-index",
            "2",
            "--output-dir",
            str(tmp_path / "validation"),
            "--output-root",
            str(tmp_path / "reports"),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["schema"] == ENTRY_FACTOR_VALIDATION_RUN_SCHEMA
    assert stdout["candidate"]["candidate_index"] == 2
    assert stdout["candidate"]["action"] == "exclude"
    assert stdout["run_plan_path"].endswith(".run.yaml")
    assert stdout["run_summary"]["metrics"]["cumulative_return"] == 0.07
    assert Path(stdout["artifacts"]["validation_json"]).exists()
    assert Path(stdout["artifacts"]["validation_markdown_zh"]).exists()

    run_plan = calls["run_plan"]
    assert calls["provider"] is None
    condition = run_plan.analysis.entry_attribution.entry_filter.conditions[0]
    assert condition.action == "exclude"
    assert run_plan.data.refresh_snapshots is False

    persisted = json.loads(Path(stdout["artifacts"]["validation_json"]).read_text(encoding="utf-8"))
    assert persisted["candidate"]["run_id"] == stdout["candidate"]["run_id"]
    markdown = Path(stdout["artifacts"]["validation_markdown_zh"]).read_text(encoding="utf-8")
    assert "入场单因子真实验证" in markdown
    assert "exclude" in markdown


def test_entry_factor_validation_run_can_select_candidate_by_run_id(tmp_path: Path) -> None:
    manifest = build_entry_factor_validation_manifest(
        _discovery_report_fixture(),
        _baseline_run_plan_fixture(),
        positive_limit=1,
        negative_limit=1,
    )
    target_run_id = manifest["candidates"][1]["run_id"]

    candidate = run_cli.select_entry_factor_validation_candidate(manifest, run_id=target_run_id)

    assert candidate["candidate_index"] == 2
    assert candidate["run_id"] == target_run_id


def test_entry_factor_validation_run_supports_embedded_run_plan_markdown() -> None:
    manifest = build_entry_factor_validation_manifest(
        _discovery_report_fixture(),
        _baseline_run_plan_fixture(),
        positive_limit=1,
        negative_limit=0,
    )
    candidate = manifest["candidates"][0]
    run_plan = RunPlan.from_mapping(yaml.safe_load(yaml.safe_dump(candidate["run_plan"], allow_unicode=True, sort_keys=False)))
    record = run_cli.build_entry_factor_validation_run_record(
        manifest=manifest,
        candidate=candidate,
        run_plan=run_plan,
        run_plan_path=None,
        run_summary={
            "schema": "attbacktrader.run_execution_summary.v1",
            "run": {"id": run_plan.run.id, "symbols": ["000001.SZ"]},
            "metrics": {"trade_count": 3},
            "data_windows": {"items": [{"symbol": "000001.SZ"}]},
        },
        artifact_paths=None,
        validation_output_dir=Path("reports/validation"),
    )

    assert record["schema"] == ENTRY_FACTOR_VALIDATION_RUN_SCHEMA
    assert record["run_plan_path"] is None
    assert record["candidate"]["action"] == "keep"
    assert record["entry_filter"]["conditions"][0]["action"] == "keep"
    assert record["run_summary"]["metrics"]["trade_count"] == 3
    assert "symbols" not in record["run_summary"]["run"]
    assert record["run_summary"]["data_windows"]["item_count"] == 1
    assert "items" not in record["run_summary"]["data_windows"]
    assert "keep" in render_entry_factor_validation_run_markdown_zh(record)


def _discovery_report_fixture() -> dict:
    return {
        "schema": "attbacktrader.bayesian_factor_discovery.v1",
        "run_id": "discovery-test",
        "source_artifacts": {"wide_samples": "wide.json", "field_index": None},
        "rankings": {
            "tradable_pre_entry": {
                "positive": [
                    _candidate("symbol.ma.trend_state", "bullish", "positive", 1.5, 8),
                ],
                "negative": [
                    _candidate("symbol.macd.energy_zone", "green_bar_or_zero", "negative", -1.4, 8),
                ],
                "weak": [],
            },
        },
    }


def _candidate(field_key: str, value: str, direction: str, score: float, sample_count: int) -> dict:
    return {
        "field_key": field_key,
        "field_label_zh": field_key,
        "value": value,
        "value_label_zh": value,
        "label_zh": f"{field_key}={value}",
        "direction": direction,
        "factor_quality_score": score,
        "sample_count": sample_count,
        "future_function_guard": {"eligible_for_entry_rule_review": not field_key.startswith("trade.")},
        "flags": [],
    }


def _baseline_run_plan_fixture() -> dict:
    return {
        "run": {
            "id": "baoma-baseline",
            "from_date": "2023-01-01",
            "to_date": "2024-12-31",
        },
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
