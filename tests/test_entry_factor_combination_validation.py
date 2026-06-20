import json
from pathlib import Path
from types import SimpleNamespace

import yaml

from attbacktrader.cli import entry_factor_combination_validation as combo_cli
from attbacktrader.config import RunPlan
from attbacktrader.reports import (
    ENTRY_FACTOR_COMBINATION_MANIFEST_SCHEMA,
    ENTRY_FACTOR_COMBINATION_VALIDATION_SCHEMA,
    build_entry_factor_combination_manifest,
    build_entry_factor_combination_validation_report,
    render_entry_factor_combination_validation_markdown_zh,
    write_entry_factor_combination_manifest,
)


def test_entry_factor_combination_manifest_uses_only_stage1_survivors_stepwise() -> None:
    manifest = build_entry_factor_combination_manifest(
        _classification_fixture(),
        _baseline_run_plan_fixture(),
        reuse_snapshots=True,
    )

    assert manifest["schema"] == ENTRY_FACTOR_COMBINATION_MANIFEST_SCHEMA
    assert manifest["survivor_count"] == 3
    assert manifest["generated_count"] == 3
    assert manifest["skipped_count"] == 1

    steps = manifest["candidates"]
    assert [len(step["filter_conditions"]) for step in steps] == [1, 2, 3]
    assert [step["latest_source_survivor"]["field_key"] for step in steps] == [
        "symbol.ma.trend_state",
        "symbol.macd.energy_zone",
        "entry.momentum.return_120d_bucket",
    ]
    assert [condition["action"] for condition in steps[1]["filter_conditions"]] == ["keep", "exclude"]
    assert "entry.noise" not in json.dumps(steps, ensure_ascii=False)

    first_plan = steps[0]["run_plan"]
    last_plan = steps[-1]["run_plan"]
    assert first_plan["data"]["refresh_snapshots"] is False
    assert len(last_plan["analysis"]["entry_attribution"]["entry_filter"]["conditions"]) == 3
    assert first_plan["run"]["id"].startswith("baoma-baseline-efc-step001-")
    assert last_plan["run"]["id"].startswith("baoma-baseline-efc-step003-")
    for step in steps:
        RunPlan.from_mapping(step["run_plan"])


def test_entry_factor_combination_manifest_writes_run_plans(tmp_path: Path) -> None:
    manifest = build_entry_factor_combination_manifest(
        _classification_fixture(),
        _baseline_run_plan_fixture(),
        max_steps=2,
    )

    json_path, markdown_path, run_plan_paths, payload = write_entry_factor_combination_manifest(
        manifest,
        output_dir=tmp_path / "combo",
    )

    assert json_path.exists()
    assert markdown_path.exists()
    assert len(run_plan_paths) == 2
    assert payload["generated_count"] == 2
    assert "入场因子组合验证 Manifest" in markdown_path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(run_plan_paths[1].read_text(encoding="utf-8"))
    assert len(loaded["analysis"]["entry_attribution"]["entry_filter"]["conditions"]) == 2


def test_entry_factor_combination_validation_report_classifies_additivity() -> None:
    report = build_entry_factor_combination_validation_report(
        [
            _validation_record(1, cumulative_return=0.030),
            _validation_record(2, cumulative_return=0.025),
            _validation_record(3, cumulative_return=0.005),
        ],
        baseline_metrics={"cumulative_return": 0.010, "max_drawdown": 0.020, "trade_count": 100, "win_rate": 0.50},
        baseline_run_id="baoma-baseline",
        source_manifest="combo-manifest.json",
    )

    assert report["schema"] == ENTRY_FACTOR_COMBINATION_VALIDATION_SCHEMA
    assert [row["combination_status"] for row in report["rows"]] == [
        "additive",
        "non_additive",
        "unstable",
    ]
    assert report["rows"][1]["previous_step_deltas"]["cumulative_return"] < 0
    assert report["rows"][0]["slice_comparisons"]["year_slices"][0]["slice_key"] == "2023"
    assert report["status_counts"]["additive"] == 1

    markdown = render_entry_factor_combination_validation_markdown_zh(report)
    assert "入场因子组合验证报告" in markdown
    assert "non_additive" in markdown


def test_entry_factor_combination_validation_cli_executes_steps(tmp_path: Path, monkeypatch, capsys) -> None:
    classification_path = tmp_path / "classification.json"
    baseline_path = tmp_path / "baseline.yaml"
    classification_path.write_text(json.dumps(_classification_fixture(), ensure_ascii=False), encoding="utf-8")
    baseline_path.write_text(yaml.safe_dump(_baseline_run_plan_fixture(), allow_unicode=True, sort_keys=False), encoding="utf-8")
    calls: list[str] = []

    def fake_execute(run_plan, provider=None):
        calls.append(run_plan.run.id)
        return SimpleNamespace(run_id=run_plan.run.id)

    def fake_write_artifacts(run_plan, result, *, output_root):
        output_dir = Path(output_root) / result.run_id
        output_dir.mkdir(parents=True)
        evidence_path = output_dir / "evidence_validation.json"
        evidence_path.write_text(json.dumps({"status": "ok"}), encoding="utf-8")
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
        return_value = 0.030 if "step001" in result.run_id else 0.025
        return {
            "schema": "attbacktrader.run_execution_summary.v1",
            "run": {"id": result.run_id, "from_date": "2023-01-01", "to_date": "2024-12-31"},
            "metrics": {
                "cumulative_return": return_value,
                "max_drawdown": 0.010,
                "trade_count": 30,
                "win_rate": 0.60,
                "profit_loss_ratio": 1.4,
            },
            "evidence": {"status": "ok"},
        }

    monkeypatch.setattr(combo_cli, "execute_run_plan", fake_execute)
    monkeypatch.setattr(combo_cli, "write_run_artifacts", fake_write_artifacts)
    monkeypatch.setattr(combo_cli, "build_run_execution_summary", fake_summary)

    exit_code = combo_cli.main(
        [
            "--classification",
            str(classification_path),
            "--baseline-run-plan",
            str(baseline_path),
            "--output-dir",
            str(tmp_path / "combo"),
            "--output-root",
            str(tmp_path / "reports"),
            "--max-steps",
            "2",
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert len(calls) == 2
    assert stdout["schema"] == ENTRY_FACTOR_COMBINATION_VALIDATION_SCHEMA
    assert stdout["record_count"] == 2
    assert (tmp_path / "combo" / "entry_factor_combination_manifest.json").exists()
    assert (tmp_path / "combo" / "entry_factor_combination_validation.json").exists()
    assert stdout["rows"][0]["combination_status"] in {"additive", "mixed"}


def _classification_fixture() -> dict:
    return {
        "schema": "attbacktrader.entry_factor_validation_classification.v1",
        "source_matrix": "matrix.json",
        "source_manifest": "manifest.json",
        "baseline": {"run_id": "baoma-baseline"},
        "rows": [
            _classification_row(1, "stable_favorable", "keep", "symbol.ma.trend_state", "bullish", 4.0),
            _classification_row(2, "noise", "keep", "entry.noise", "x", 9.0),
            _classification_row(3, "stable_unfavorable", "exclude", "symbol.macd.energy_zone", "green_bar_or_zero", 3.5),
            _classification_row(4, "stable_favorable", "keep", "entry.momentum.return_120d_bucket", "p80_p100", 2.0),
        ],
    }


def _classification_row(
    index: int,
    classification: str,
    action: str,
    field_key: str,
    value: object,
    score: float,
) -> dict:
    return {
        "candidate_index": index,
        "candidate_rank": index,
        "classification": classification,
        "classification_label_zh": classification,
        "direction": "negative" if action == "exclude" else "positive",
        "action": action,
        "field_key": field_key,
        "field_label_zh": field_key,
        "value": value,
        "value_label_zh": str(value),
        "run_id": f"stage1-{index}",
        "validation_score": score,
    }


def _validation_record(step: int, *, cumulative_return: float) -> dict:
    conditions = [
        {"field": f"symbol.factor_{index}", "operator": "eq", "value": "x", "action": "keep"}
        for index in range(1, step + 1)
    ]
    return {
        "schema": "attbacktrader.entry_factor_validation_run.v1",
        "candidate": {
            "candidate_index": step,
            "candidate_rank": step,
            "combination_step": step,
            "direction": "combination",
            "action": "entry_filter_combo",
            "run_id": f"combo-step-{step}",
            "filter_conditions": conditions,
            "source_survivors": [{"candidate_index": index} for index in range(1, step + 1)],
        },
        "run": {"id": f"combo-step-{step}"},
        "run_summary": {
            "metrics": {
                "cumulative_return": cumulative_return,
                "max_drawdown": 0.02,
                "trade_count": 20,
                "win_rate": 0.55,
                "profit_loss_ratio": 1.2,
            },
            "evidence": {"status": "ok"},
        },
        "year_slices": [{"slice_key": "2023", "status": "supports_candidate"}],
        "market_stage_slices": [{"slice_key": "bullish", "status": "supports_candidate"}],
        "artifacts": {"validation_json": f"step-{step}/entry_factor_validation_run.json"},
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
