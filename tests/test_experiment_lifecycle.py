import json
from pathlib import Path

from attbacktrader.cli import experiment_lifecycle as experiment_lifecycle_cli
from attbacktrader.reports import (
    build_experiment_lifecycle,
    render_experiment_lifecycle_markdown_zh,
    write_experiment_lifecycle,
)


def test_experiment_lifecycle_links_review_and_strategy_variant_chains(tmp_path: Path) -> None:
    candidate_path = _write_review_candidates(tmp_path)
    review_drafts_path = _write_review_drafts(tmp_path)
    confirmation_path = _write_review_confirmation(tmp_path)
    strategy_drafts_path = _write_strategy_variant_drafts(tmp_path)
    manifest_path = _write_strategy_variant_manifest(tmp_path)
    validation_path = _write_strategy_variant_validation(tmp_path)
    attribution_path = _write_strategy_variant_attribution(tmp_path)
    run_catalog_path = _write_run_catalog(tmp_path)

    lifecycle = build_experiment_lifecycle(
        candidates=[candidate_path],
        drafts=[review_drafts_path, strategy_drafts_path],
        confirmations=[confirmation_path],
        variant_manifests=[manifest_path],
        validations=[validation_path],
        attributions=[attribution_path],
        run_catalog=run_catalog_path,
    )
    markdown = render_experiment_lifecycle_markdown_zh(lifecycle)
    json_path, markdown_path = write_experiment_lifecycle(lifecycle, output_dir=tmp_path / "lifecycle")

    assert lifecycle["schema"] == "attbacktrader.experiment_lifecycle.v1"
    assert lifecycle["chain_count"] == 2
    chains = {chain["chain_id"]: chain for chain in lifecycle["chains"]}
    review_chain = chains["review:candidate.environment_fit.sample_stability"]
    assert review_chain["status"] == "executed"
    assert review_chain["missing_stages"] == ["comparison"]
    assert review_chain["run_ids"] == ["review-sample-stability"]
    strategy_chain = chains["strategy_variant:bull_market_let_winners_run"]
    assert strategy_chain["status"] == "attributed"
    assert strategy_chain["missing_stages"] == ["decision"]
    assert strategy_chain["executed_run_ids"] == ["baseline-bull-segment__variant__bull_market_let_winners_run"]
    assert sorted(strategy_chain["planned_run_ids"]) == [
        "baseline-bull-segment__variant__bull_market_let_winners_run",
        "tushare-market-type-add-on-validation__strategy_variant__bull_market_let_winners_run",
    ]
    stage_counts = {row["key"]: row["count"] for row in lifecycle["stage_counts"]}
    assert stage_counts["candidate"] == 1
    assert stage_counts["draft"] == 2
    assert stage_counts["executed_run"] == 2
    assert stage_counts["comparison"] == 1
    assert stage_counts["attribution"] == 1
    assert "实验 Lifecycle" in markdown
    assert "记录 accepted / rejected / parked 决策" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def test_experiment_lifecycle_cli_writes_outputs(tmp_path: Path, capsys) -> None:
    candidate_path = _write_review_candidates(tmp_path)
    review_drafts_path = _write_review_drafts(tmp_path)
    confirmation_path = _write_review_confirmation(tmp_path)
    run_catalog_path = _write_run_catalog(tmp_path)
    output_dir = tmp_path / "lifecycle"

    exit_code = experiment_lifecycle_cli.main(
        [
            "--no-default-sources",
            "--candidate",
            str(candidate_path),
            "--drafts",
            str(review_drafts_path),
            "--confirmation",
            str(confirmation_path),
            "--run-catalog",
            str(run_catalog_path),
            "--output-dir",
            str(output_dir),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["schema"] == "attbacktrader.experiment_lifecycle.v1"
    assert stdout["chain_count"] == 1
    assert stdout["artifacts"]["experiment_lifecycle_json_path"] == str(output_dir / "experiment_lifecycle.json")
    assert (output_dir / "experiment_lifecycle.zh.md").exists()


def _write_review_candidates(root: Path) -> Path:
    path = root / "review_experiment_candidates.all.json"
    _write_json(
        path,
        {
            "schema": "attbacktrader.review_experiment_candidates.v1",
            "run_id": "source-run",
            "candidates": [
                {
                    "candidate_id": "candidate.environment_fit.sample_stability",
                    "status": "candidate",
                    "direction": "environment_fit_validation",
                    "candidate_type": "sample_stability_probe",
                    "title_zh": "环境样本稳定性验证",
                    "purpose_zh": "验证环境分组是否稳定。",
                    "validation_plan_zh": "生成对比 run。",
                    "evidence_refs": [{"artifact": "environment_fit"}],
                    "sample_refs": [{"kind": "trade", "trade_index": 1}],
                }
            ],
        },
    )
    return path


def _write_review_drafts(root: Path) -> Path:
    path = root / "review_experiment_drafts.all.json"
    _write_json(
        path,
        {
            "schema": "attbacktrader.review_experiment_drafts.v1",
            "drafts": [
                {
                    "draft_id": "environment_fit_sample_stability",
                    "status": "draft_requires_manual_confirmation",
                    "source_candidate_id": "candidate.environment_fit.sample_stability",
                    "title_zh": "环境样本稳定性验证",
                    "purpose_zh": "验证环境分组是否稳定。",
                    "suggested_run_id": "review-sample-stability",
                    "validation_plan_zh": "生成对比 run。",
                }
            ],
        },
    )
    return path


def _write_review_confirmation(root: Path) -> Path:
    path = root / "review_experiment_confirmed.environment_fit_sample_stability.json"
    _write_json(
        path,
        {
            "schema": "attbacktrader.review_experiment_confirmed_run_plan.v1",
            "status": "confirmed_run_plan_generated",
            "source_candidate_id": "candidate.environment_fit.sample_stability",
            "draft_id": "environment_fit_sample_stability",
            "run_id": "review-sample-stability",
            "legal_run_plan": {"run": {"id": "review-sample-stability"}},
        },
    )
    return path


def _write_strategy_variant_drafts(root: Path) -> Path:
    path = root / "strategy_variant_drafts.json"
    _write_json(
        path,
        {
            "schema": "attbacktrader.strategy_variant_drafts.v1",
            "drafts": [
                {
                    "draft_id": "bull_market_let_winners_run",
                    "status": "draft_requires_manual_confirmation",
                    "market_type_id": "bull_market",
                    "market_type_label_zh": "牛市",
                    "title_zh": "牛市：放宽过早止盈验证",
                    "purpose_zh": "验证牛市是否应该让盈利单多持有。",
                    "suggested_run_id": "tushare-market-type-add-on-validation__strategy_variant__bull_market_let_winners_run",
                    "validation_plan_zh": "按牛市段对比 baseline 和 variant。",
                    "evidence_factors": [
                        {
                            "factor_key": "entry.check.symbol.ma.price_above_ma60",
                            "factor_label_zh": "价格在 MA60 上方",
                            "sample_count": 12,
                            "win_rate": 0.75,
                        }
                    ],
                    "metrics": {"trade_count": 12},
                }
            ],
        },
    )
    return path


def _write_strategy_variant_manifest(root: Path) -> Path:
    path = root / "strategy_variant_run_manifest.json"
    _write_json(
        path,
        {
            "schema": "attbacktrader.strategy_variant_run_manifest.v1",
            "segments": [
                {
                    "segment_id": "test_bull_segment",
                    "segment_label_zh": "测试牛市段",
                    "market_type_id": "bull_market",
                    "market_type_label_zh": "牛市",
                    "baseline_run_id": "baseline-bull-segment",
                    "draft_id": "bull_market_let_winners_run",
                    "run_id": "baseline-bull-segment__variant__bull_market_let_winners_run",
                    "run_plan_path": "generated.run.yaml",
                }
            ],
        },
    )
    return path


def _write_strategy_variant_validation(root: Path) -> Path:
    path = root / "strategy_variant_validation.json"
    _write_json(
        path,
        {
            "schema": "attbacktrader.strategy_variant_validation.v1",
            "rows": [
                {
                    "market_type_id": "bull_market",
                    "market_type_label_zh": "牛市",
                    "delta": {"average_return_pct": 0.02},
                    "direction_zh": "收益提升且回撤未扩大",
                }
            ],
        },
    )
    return path


def _write_strategy_variant_attribution(root: Path) -> Path:
    path = root / "strategy_variant_attribution.json"
    _write_json(
        path,
        {
            "schema": "attbacktrader.strategy_variant_attribution.v1",
            "market_type_id": "bull_market",
            "market_type_label_zh": "牛市",
            "segment_count": 1,
            "overall": {"delta": {"average_holding_days": 5.0}},
        },
    )
    return path


def _write_run_catalog(root: Path) -> Path:
    path = root / "run_catalog.json"
    _write_json(
        path,
        {
            "schema": "attbacktrader.run_catalog.v1",
            "runs": [
                _run_catalog_row("review-sample-stability", "experiment_run"),
                _run_catalog_row(
                    "baseline-bull-segment__variant__bull_market_let_winners_run",
                    "strategy_variant_segment",
                ),
            ],
        },
    )
    return path


def _run_catalog_row(run_id: str, role: str) -> dict:
    return {
        "run_id": run_id,
        "role": role,
        "source_dir": f"reports/{run_id}",
        "source_dir_exists": True,
        "evidence_validation": {"status": "ok", "error_count": 0, "warning_count": 0},
        "missing_required_artifacts": [],
        "metrics": {"cumulative_return": 0.1, "trade_count": 3},
    }


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
