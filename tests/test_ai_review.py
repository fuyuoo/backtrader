import json
from pathlib import Path

from attbacktrader.cli import review_brief as review_brief_cli
from attbacktrader.cli import review_experiment_confirm as review_experiment_confirm_cli
from attbacktrader.cli import review_experiment_drafts as review_experiment_drafts_cli
from attbacktrader.cli import review_expand_samples as review_expand_samples_cli
from attbacktrader.cli import review_experiment_candidates as review_experiment_candidates_cli
from attbacktrader.cli import review_findings as review_findings_cli
from attbacktrader.cli import review_result as review_result_cli
from attbacktrader.cli import review_sample as review_sample_cli
from attbacktrader.config import RunPlan
from attbacktrader.reports import (
    build_ai_review_brief,
    build_ai_review_findings,
    build_ai_review_result,
    build_review_experiment_confirmed_run_plan,
    build_review_packet,
    build_review_sample,
    build_review_experiment_candidates,
    build_review_experiment_drafts,
    expand_review_samples_from_findings,
    write_ai_review_brief,
    write_ai_review_findings,
    write_ai_review_result,
    write_review_experiment_confirmed_run_plan,
    write_review_experiment_candidates,
    write_review_experiment_drafts,
    write_review_sample_batch,
    write_review_sample,
)


def test_ai_review_findings_builds_structured_task_from_packet(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    packet = build_review_packet(run_dir, focus="all", top=5)

    findings = build_ai_review_findings(packet, top=1)
    json_path, markdown_path = write_ai_review_findings(findings, output_dir=tmp_path / "findings")

    assert findings["schema"] == "attbacktrader.ai_review_findings.v1"
    assert findings["run_id"] == "ai-review-run"
    assert findings["ai_task"]["required_output_schema"]["summary_zh"] == "string"
    assert findings["finding_count"] == 6
    assert findings["findings"][2]["direction"] == "opportunity_review"
    assert findings["findings"][2]["sample_refs"][0]["sample_index"] == 2
    assert findings["findings"][4]["direction"] == "environment_fit_review"
    assert json_path.exists()
    assert "AI 复盘 Findings" in markdown_path.read_text(encoding="utf-8")


def test_review_sample_drills_down_add_on_evidence(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)

    packet = build_review_sample(run_dir, kind="add_on", sample_index=1, context_limit=5)
    json_path, markdown_path = write_review_sample(packet, output_dir=tmp_path / "samples")

    assert packet["schema"] == "attbacktrader.review_sample.v1"
    assert packet["sample_id"] == "add_on.1"
    assert packet["related"]["trade_review_trade"]["trade_index"] == 7
    assert packet["related"]["trade_lifecycle"]["trade_index"] == 7
    assert packet["related"]["post_exit_observation"]["trade_index"] == 99
    assert packet["related"]["closed_trade"]["symbol"] == "000001.SZ"
    assert packet["related"]["signal_intent_match_count"] == 1
    assert packet["related"]["execution_event_match_count"] == 1
    assert packet["related"]["signal_intents"][0]["reason_code"] == "KDJ_OVERSOLD_ADD_ON"
    assert json_path.exists()
    assert "AI 样本反查包" in markdown_path.read_text(encoding="utf-8")


def test_expand_samples_and_brief_build_skill_ready_inputs(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    findings = build_ai_review_findings(build_review_packet(run_dir, focus="all", top=5), top=2)

    batch = expand_review_samples_from_findings(findings, limit_per_finding=1)
    batch_json_path, batch_markdown_path = write_review_sample_batch(batch, output_dir=tmp_path / "batch")
    brief = build_ai_review_brief(findings, sample_batch=batch, limit_per_finding=1)
    brief_json_path, brief_markdown_path = write_ai_review_brief(brief, output_dir=tmp_path / "brief")

    assert batch["schema"] == "attbacktrader.review_sample_batch.v1"
    assert batch["expanded_sample_count"] == 3
    assert {sample["sample_id"] for sample in batch["samples"]} == {"trade.7", "opportunity.2", "add_on.1"}
    assert batch_json_path.exists()
    assert "AI 批量样本展开" in batch_markdown_path.read_text(encoding="utf-8")
    assert brief["schema"] == "attbacktrader.ai_review_brief.v1"
    assert brief["skill_contract"]["expected_output_schema"]["summary_zh"] == "string"
    assert brief["section_count"] == 6
    assert brief["environment_fit_summary"]["best_by_net_pnl_label_zh"] == "行业 KDJ J 低于阈值=是"
    assert brief["environment_fit_summary"]["low_sample_combination_count"] == 1
    assert brief["sections"][0]["expanded_samples"][0]["sample_id"] == "trade.7"
    assert brief_json_path.exists()
    brief_markdown = brief_markdown_path.read_text(encoding="utf-8")
    assert "AI 自动复盘 Brief" in brief_markdown
    assert "环境适配摘要" in brief_markdown
    assert "行业 KDJ J 低于阈值=是" in brief_markdown


def test_review_experiment_candidates_keep_validation_boundary(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    findings = build_ai_review_findings(build_review_packet(run_dir, focus="all", top=5), top=2)
    batch = expand_review_samples_from_findings(findings, limit_per_finding=1)

    candidates = build_review_experiment_candidates(findings, sample_batch=batch)
    json_path, markdown_path = write_review_experiment_candidates(candidates, output_dir=tmp_path / "candidates")
    directions = {candidate["direction"] for candidate in candidates["candidates"]}

    assert candidates["schema"] == "attbacktrader.review_experiment_candidates.v1"
    assert candidates["candidate_count"] == 6
    assert "execution_constraint_review" in directions
    assert "environment_fit_validation" in directions
    assert candidates["candidates"][0]["status"] == "candidate"
    assert candidates["rules"][0].startswith("候选只用于下一轮验证设计")
    assert json_path.exists()
    assert "复盘实验候选" in markdown_path.read_text(encoding="utf-8")


def test_ai_review_result_persists_brief_output_schema(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    findings = build_ai_review_findings(build_review_packet(run_dir, focus="all", top=5), top=2)
    batch = expand_review_samples_from_findings(findings, limit_per_finding=1)
    brief = build_ai_review_brief(findings, sample_batch=batch, limit_per_finding=1)

    result = build_ai_review_result(brief, reviewer="unit-test")
    json_path, markdown_path = write_ai_review_result(result, output_dir=tmp_path / "result")

    assert result["schema"] == "attbacktrader.ai_review_result.v1"
    assert result["reviewer"] == "unit-test"
    assert result["status"] == "draft_from_brief"
    assert result["finding_result_count"] == 6
    assert result["findings"][0]["supporting_sample_ids"] == ["trade.7"]
    assert json_path.exists()
    assert "AI 复盘结果" in markdown_path.read_text(encoding="utf-8")


def test_ai_review_result_can_embed_environment_fit_comparison(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    findings = build_ai_review_findings(build_review_packet(run_dir, focus="all", top=5), top=2)
    batch = expand_review_samples_from_findings(findings, limit_per_finding=1)
    brief = build_ai_review_brief(findings, sample_batch=batch, limit_per_finding=1)
    comparison = _environment_fit_comparison()

    result = build_ai_review_result(brief, environment_fit_comparison=comparison, reviewer="unit-test")
    json_path, markdown_path = write_ai_review_result(result, output_dir=tmp_path / "comparison-result")

    assert result["finding_result_count"] == 7
    comparison_finding = result["findings"][-1]
    assert comparison_finding["finding_id"] == "environment-fit-comparison-001"
    assert comparison_finding["sample_refs"][0]["trade_index"] == 7
    assert "环境适配对比覆盖 2 个 run" in comparison_finding["claim_zh"]
    assert result["environment_fit_comparison_review"]["risk_zh"] == "最佳环境存在变化或样本风险，不能声明稳定适配。"
    assert json_path.exists()
    assert "environment-fit-comparison-001" in markdown_path.read_text(encoding="utf-8")


def test_review_experiment_drafts_write_manifest_and_yaml(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    findings = build_ai_review_findings(build_review_packet(run_dir, focus="all", top=5), top=2)
    batch = expand_review_samples_from_findings(findings, limit_per_finding=1)
    candidates = build_review_experiment_candidates(findings, sample_batch=batch)
    base_config = tmp_path / "base.yaml"
    base_config.write_text("run:\n  id: base-run\n", encoding="utf-8")

    drafts = build_review_experiment_drafts(candidates, base_config_path=base_config)
    json_path, markdown_path, yaml_paths = write_review_experiment_drafts(drafts, output_dir=tmp_path / "drafts")

    assert drafts["schema"] == "attbacktrader.review_experiment_drafts.v1"
    assert drafts["draft_count"] == 6
    assert drafts["drafts"][0]["status"] == "draft_requires_manual_confirmation"
    assert drafts["drafts"][0]["suggested_run_id"].startswith("base-run__review__")
    environment_draft = next(draft for draft in drafts["drafts"] if draft["candidate_direction"] == "environment_fit_validation")
    assert "environment_fit.json" in environment_draft["run_plan_patch"]["review_candidate"]["inspect_artifacts"]
    assert json_path.exists()
    assert markdown_path.exists()
    assert len(yaml_paths) == 6
    assert "manual_confirmation_required" in yaml_paths[0].read_text(encoding="utf-8")


def test_review_experiment_confirm_generates_valid_run_plan(tmp_path: Path, capsys) -> None:
    run_dir = _run_dir(tmp_path)
    findings = build_ai_review_findings(build_review_packet(run_dir, focus="all", top=5), top=2)
    batch = expand_review_samples_from_findings(findings, limit_per_finding=1)
    candidates = build_review_experiment_candidates(findings, sample_batch=batch)
    base_config = _base_run_plan_yaml(tmp_path)
    drafts = build_review_experiment_drafts(candidates, base_config_path=base_config)
    _, _, yaml_paths = write_review_experiment_drafts(drafts, output_dir=tmp_path / "drafts")
    draft_path = next(path for path in yaml_paths if path.name == "environment_fit_sample_stability.yaml")

    confirmation = build_review_experiment_confirmed_run_plan(draft_path, confirmed_by="unit-test")
    json_path, markdown_path, run_plan_path = write_review_experiment_confirmed_run_plan(
        confirmation,
        output_dir=tmp_path / "confirmed",
    )
    cli_exit = review_experiment_confirm_cli.main(
        [
            "--draft",
            str(draft_path),
            "--confirm",
            "--confirmed-by",
            "cli-test",
            "--output-dir",
            str(tmp_path / "cli-confirmed"),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert confirmation["schema"] == "attbacktrader.review_experiment_confirmed_run_plan.v1"
    assert confirmation["status"] == "confirmed_run_plan_generated"
    assert "review_candidate" in confirmation["omitted_patch_keys"]
    assert "review_candidate" not in confirmation["legal_run_plan"]
    RunPlan.from_mapping(confirmation["legal_run_plan"])
    assert json_path.exists()
    assert markdown_path.exists()
    assert run_plan_path.exists()
    assert cli_exit == 0
    assert stdout["run_id"].startswith("base-run__review__environment_fit_sample_stability")
    assert (tmp_path / "cli-confirmed" / "environment_fit_sample_stability.run.yaml").exists()


def test_ai_review_clis_write_outputs(tmp_path: Path, capsys) -> None:
    run_dir = _run_dir(tmp_path)
    output_dir = tmp_path / "out"

    findings_exit = review_findings_cli.main(
        ["--run-dir", str(run_dir), "--focus", "add_on", "--top", "1", "--output-dir", str(output_dir)]
    )
    findings_stdout = json.loads(capsys.readouterr().out)
    sample_exit = review_sample_cli.main(
        [
            "--run-dir",
            str(run_dir),
            "--kind",
            "opportunity",
            "--sample-index",
            "2",
            "--output-dir",
            str(output_dir),
        ]
    )
    sample_stdout = json.loads(capsys.readouterr().out)

    assert findings_exit == 0
    assert sample_exit == 0
    assert findings_stdout["artifacts"]["review_findings_json_path"] == str(output_dir / "review_findings.add_on.json")
    assert sample_stdout["artifacts"]["review_sample_json_path"] == str(output_dir / "review_sample.opportunity.2.json")
    assert (output_dir / "review_findings.add_on.zh.md").exists()
    assert (output_dir / "review_sample.opportunity.2.zh.md").exists()


def test_ai_review_workflow_clis_write_outputs(tmp_path: Path, capsys) -> None:
    run_dir = _run_dir(tmp_path)
    packet = build_review_packet(run_dir, focus="all", top=5)
    findings = build_ai_review_findings(packet, top=2)
    findings_path, _ = write_ai_review_findings(findings, output_dir=tmp_path)
    output_dir = tmp_path / "workflow"

    expand_exit = review_expand_samples_cli.main(
        [
            "--findings",
            str(findings_path),
            "--limit-per-finding",
            "1",
            "--output-dir",
            str(output_dir),
        ]
    )
    expand_stdout = json.loads(capsys.readouterr().out)
    batch_path = output_dir / "review_sample_batch.all.json"
    brief_exit = review_brief_cli.main(
        [
            "--findings",
            str(findings_path),
            "--sample-batch",
            str(batch_path),
            "--output-dir",
            str(output_dir),
        ]
    )
    brief_stdout = json.loads(capsys.readouterr().out)
    candidates_exit = review_experiment_candidates_cli.main(
        [
            "--findings",
            str(findings_path),
            "--sample-batch",
            str(batch_path),
            "--output-dir",
            str(output_dir),
        ]
    )
    candidates_stdout = json.loads(capsys.readouterr().out)

    assert expand_exit == 0
    assert brief_exit == 0
    assert candidates_exit == 0
    assert expand_stdout["expanded_sample_count"] == 3
    assert brief_stdout["artifacts"]["review_brief_json_path"] == str(output_dir / "review_brief.all.json")
    assert candidates_stdout["candidate_count"] == 6
    assert (output_dir / "review_sample.add_on.1.json").exists()
    assert (output_dir / "review_experiment_candidates.all.zh.md").exists()


def test_ai_review_result_and_draft_clis_write_outputs(tmp_path: Path, capsys) -> None:
    run_dir = _run_dir(tmp_path)
    packet = build_review_packet(run_dir, focus="all", top=5)
    findings = build_ai_review_findings(packet, top=2)
    batch = expand_review_samples_from_findings(findings, limit_per_finding=1)
    brief = build_ai_review_brief(findings, sample_batch=batch)
    candidates = build_review_experiment_candidates(findings, sample_batch=batch)
    brief_path, _ = write_ai_review_brief(brief, output_dir=tmp_path)
    candidates_path, _ = write_review_experiment_candidates(candidates, output_dir=tmp_path)
    base_config = tmp_path / "base.yaml"
    base_config.write_text("run:\n  id: base-run\n", encoding="utf-8")
    output_dir = tmp_path / "cli-out"

    result_exit = review_result_cli.main(["--brief", str(brief_path), "--output-dir", str(output_dir)])
    result_stdout = json.loads(capsys.readouterr().out)
    drafts_exit = review_experiment_drafts_cli.main(
        [
            "--candidates",
            str(candidates_path),
            "--base-config",
            str(base_config),
            "--output-dir",
            str(output_dir),
        ]
    )
    drafts_stdout = json.loads(capsys.readouterr().out)

    assert result_exit == 0
    assert drafts_exit == 0
    assert result_stdout["artifacts"]["ai_review_result_json_path"] == str(output_dir / "ai_review_result.all.json")
    assert drafts_stdout["draft_count"] == 6
    assert (output_dir / "review_experiment_drafts.all.zh.md").exists()
    assert len(drafts_stdout["artifacts"]["review_experiment_draft_yaml_paths"]) == 6


def _run_dir(root: Path) -> Path:
    path = root / "ai-review-run"
    path.mkdir()
    _write_json(
        path / "run_plan.json",
        {
            "run": {"id": "ai-review-run", "from_date": "2024-01-01", "to_date": "2024-03-31"},
            "data": {"symbols": ["000001.SZ"]},
            "execution": {"engine": "business"},
        },
    )
    _write_json(
        path / "report.json",
        {
            "returns": {"final_equity": 1010000.0, "cumulative_return": 0.01},
            "risk": {"max_drawdown": 0.03},
            "trade_quality": {"trade_count": 1, "win_rate": 1.0},
        },
    )
    _write_json(
        path / "evidence_validation.json",
        {
            "status": "ok",
            "counts": {"symbol_count": 1, "closed_trade_count": 1},
            "error_count": 0,
            "warning_count": 0,
            "issues": [],
        },
    )
    _write_json(
        path / "post_exit_analysis.json",
        {
            "window_days": 5,
            "configured_window_days": [3, 5, 10],
            "sold_too_early_threshold": 0.02,
            "rebound_thresholds": [0.0, 0.02, 0.05],
            "trade_count": 1,
            "observations": [
                {
                    "trade_index": 99,
                    "symbol": "000001.SZ",
                    "entry_date": "2024-01-05",
                    "exit_date": "2024-02-01",
                    "exit_reason": "FIXED_5_PERCENT_STOP",
                    "sold_too_early": True,
                    "max_high_return_pct": 0.07,
                }
            ],
        },
    )
    _write_json(
        path / "trade_lifecycle.json",
        {
            "trade_count": 1,
            "lifecycles": [
                {
                    "trade_index": 7,
                    "symbol": "000001.SZ",
                    "entry_date": "2024-01-05",
                    "exit_date": "2024-02-01",
                    "events": [
                        {"event_type": "entry", "trade_date": "2024-01-05"},
                        {"event_type": "add_on", "trade_date": "2024-01-12"},
                        {"event_type": "exit", "trade_date": "2024-02-01"},
                    ],
                }
            ],
        },
    )
    _write_json(
        path / "trades.json",
        {
            "closed_trades": [
                {
                    "symbol": "000001.SZ",
                    "entry_date": "2024-01-05",
                    "exit_date": "2024-02-01",
                    "entry_price": 10.0,
                    "exit_price": 11.2,
                    "exit_reason": "FIXED_5_PERCENT_STOP",
                }
            ],
            "open_positions": [],
        },
    )
    _write_json(
        path / "signal_audit.json",
        [
            {
                "intent_type": "add_on",
                "symbol": "000001.SZ",
                "trade_date": "2024-01-12",
                "method_name": "kdj_oversold_add_on",
                "reason_code": "KDJ_OVERSOLD_ADD_ON",
                "signal_values": {"checks": {"kdj_j_below_threshold": True}},
                "blocked_by": None,
            },
            {
                "intent_type": "enter",
                "symbol": "000001.SZ",
                "trade_date": "2024-01-04",
                "method_name": "kdj_oversold_entry",
                "reason_code": "KDJ_J_BELOW_13",
                "blocked_by": "BOARD_LOT_TOO_SMALL",
            },
        ],
    )
    _write_json(
        path / "execution_audit.json",
        [
            {
                "event_date": "2024-01-12",
                "signal_date": "2024-01-12",
                "symbol": "000001.SZ",
                "side": "buy",
                "event_type": "completed",
                "status": "completed",
                "reason_code": "KDJ_OVERSOLD_ADD_ON",
            },
            {
                "event_date": "2024-01-04",
                "signal_date": "2024-01-04",
                "symbol": "000001.SZ",
                "side": "buy",
                "event_type": "rejected",
                "status": "rejected",
                "reason_code": "KDJ_J_BELOW_13",
                "blocked_by": "BOARD_LOT_TOO_SMALL",
            },
        ],
    )
    _write_json(
        path / "trade_review.json",
        {
            "trade_count": 1,
            "sold_too_early_count": 1,
            "opportunity_count": 2,
            "opportunity_window_days": 5,
            "add_on_entry_count": 1,
            "add_on_window_days": 5,
            "sold_too_early_profiles": [
                {
                    "profile_key": "exit.group=stop_loss",
                    "sample_count": 1,
                    "sold_too_early_rate": 1.0,
                    "average_max_high_return_pct": 0.07,
                    "trade_indexes": [7],
                }
            ],
            "stop_loss_rebound_profiles": [
                {
                    "profile_key": "exit.group=stop_loss",
                    "threshold": 0.05,
                    "sample_count": 1,
                    "rebound_rate": 1.0,
                    "average_max_high_return_pct": 0.07,
                    "trade_indexes": [7],
                }
            ],
            "opportunity_cost_summaries": [
                {
                    "opportunity_group": "execution_rejection",
                    "blocked_by": "BOARD_LOT_TOO_SMALL",
                    "sample_count": 2,
                    "positive_max_high_rate": 1.0,
                    "average_max_high_return_pct": 0.06,
                    "sample_indexes": [1, 2],
                }
            ],
            "add_on_entry_summaries": [
                {
                    "profile_key": "trade.outcome=win|symbol.ma.bullish_trend=true",
                    "sample_count": 1,
                    "positive_max_high_rate": 1.0,
                    "average_max_high_return_pct": 0.08,
                    "sample_indexes": [1],
                    "trade_indexes": [7],
                }
            ],
            "trades": [
                {
                    "trade_index": 7,
                    "symbol": "000001.SZ",
                    "outcome": "win",
                    "entry_date": "2024-01-05",
                    "exit_date": "2024-02-01",
                    "exit_reason": "FIXED_5_PERCENT_STOP",
                    "return_pct": 0.12,
                    "sold_too_early": True,
                    "max_high_return_pct": 0.07,
                    "entry_checks": {"symbol.ma.bullish_trend": True},
                    "exit_checks": {"current_price_at_or_below_stop": True},
                }
            ],
            "opportunities": [
                {
                    "sample_index": 1,
                    "source": "execution",
                    "opportunity_group": "execution_rejection",
                    "symbol": "000001.SZ",
                    "trade_date": "2024-01-03",
                    "reason_code": "KDJ_J_BELOW_13",
                    "blocked_by": "BOARD_LOT_TOO_SMALL",
                    "opportunity_price": 10.0,
                    "follow_up": {"window_days": 5, "max_high_return_pct": 0.02},
                },
                {
                    "sample_index": 2,
                    "source": "execution",
                    "opportunity_group": "execution_rejection",
                    "symbol": "000001.SZ",
                    "trade_date": "2024-01-04",
                    "reason_code": "KDJ_J_BELOW_13",
                    "blocked_by": "BOARD_LOT_TOO_SMALL",
                    "opportunity_price": 9.8,
                    "follow_up": {"window_days": 5, "max_high_return_pct": 0.06},
                },
            ],
            "add_on_entry_points": [
                {
                    "sample_index": 1,
                    "trade_index": 7,
                    "symbol": "000001.SZ",
                    "outcome": "win",
                    "trade_return_pct": 0.12,
                    "add_on_date": "2024-01-12",
                    "method_name": "kdj_oversold_add_on",
                    "reason_code": "KDJ_OVERSOLD_ADD_ON",
                    "checks": {"symbol.ma.bullish_trend": True},
                    "add_on_price": 10.5,
                    "follow_up": {"window_days": 5, "max_high_return_pct": 0.08},
                }
            ],
        },
    )
    _write_json(
        path / "environment_fit.json",
        {
            "schema": "attbacktrader.environment_fit.v1",
            "run_id": "ai-review-run",
            "source_dir": str(path),
            "environment_fields": [
                {"field": "industry.kdj.j_below_threshold", "label_zh": "行业 KDJ J 低于阈值"},
                {"field": "market.hs300.bullish_trend", "label_zh": "沪深300多头趋势"},
            ],
            "min_sample_count": 5,
            "trade_count": 1,
            "contribution_available_count": 1,
            "overall": {
                "sample_count": 1,
                "win_rate": 1.0,
                "average_return_pct": 0.12,
                "net_pnl": 1180.0,
                "return_on_entry_value": 0.118,
            },
            "best_environments": {
                "best_by_net_pnl": {
                    "summary_kind": "single_factor",
                    "field": "industry.kdj.j_below_threshold",
                    "value": True,
                    "label_zh": "行业 KDJ J 低于阈值=是",
                    "sample_count": 1,
                    "win_rate": 1.0,
                    "average_return_pct": 0.12,
                    "net_pnl": 1180.0,
                    "return_on_entry_value": 0.118,
                    "trade_indexes": [7],
                },
                "best_by_return_on_entry_value": {
                    "summary_kind": "single_factor",
                    "field": "industry.kdj.j_below_threshold",
                    "value": True,
                    "label_zh": "行业 KDJ J 低于阈值=是",
                    "sample_count": 1,
                    "win_rate": 1.0,
                    "average_return_pct": 0.12,
                    "net_pnl": 1180.0,
                    "return_on_entry_value": 0.118,
                    "trade_indexes": [7],
                },
            },
            "sample_warnings": {
                "min_sample_count": 5,
                "low_sample_single_factor_count": 1,
                "low_sample_combination_count": 1,
                "low_sample_candidates": [],
            },
            "single_factor_summaries": [
                {
                    "summary_kind": "single_factor",
                    "field": "industry.kdj.j_below_threshold",
                    "label_zh": "行业 KDJ J 低于阈值=是",
                    "sample_count": 1,
                    "win_rate": 1.0,
                    "average_return_pct": 0.12,
                    "net_pnl": 1180.0,
                    "return_on_entry_value": 0.118,
                    "trade_indexes": [7],
                }
            ],
            "combination_summaries": [
                {
                    "summary_kind": "combination",
                    "fields": {"industry.kdj.j_below_threshold": True, "market.hs300.bullish_trend": False},
                    "profile_key": "industry.kdj.j_below_threshold=true|market.hs300.bullish_trend=false",
                    "label_zh": "行业 KDJ J 低于阈值=是；沪深300多头趋势=否",
                    "sample_count": 1,
                    "win_rate": 1.0,
                    "average_return_pct": 0.12,
                    "net_pnl": 1180.0,
                    "return_on_entry_value": 0.118,
                    "trade_indexes": [7],
                }
            ],
            "trade_contributions": [
                {
                    "trade_index": 7,
                    "symbol": "000001.SZ",
                    "entry_date": "2024-01-05",
                    "exit_date": "2024-02-01",
                    "outcome": "win",
                    "exit_reason": "FIXED_5_PERCENT_STOP",
                    "return_pct": 0.12,
                    "net_pnl": 1180.0,
                    "return_on_entry_value": 0.118,
                    "environment": {
                        "industry.kdj.j_below_threshold": True,
                        "market.hs300.bullish_trend": False,
                    },
                }
            ],
        },
    )
    return path


def _environment_fit_comparison() -> dict:
    return {
        "schema": "attbacktrader.environment_fit_comparison.v1",
        "baseline_run_id": "baseline",
        "run_ids": ["baseline", "expanded"],
        "source_count": 2,
        "common_environment_count": 1,
        "best_environment_stability": [
            {
                "criterion": "best_by_net_pnl",
                "criterion_zh": "净利润最高",
                "status": "changed",
                "status_zh": "环境变化",
                "run_environments": [],
                "sample_risk_run_ids": [],
            }
        ],
        "common_environment_deltas": [],
        "drill_down_sample_count": 1,
        "drill_down_sample_refs": [
            {
                "run_id": "baseline",
                "kind": "trade",
                "trade_index": 7,
                "criterion": "best_by_net_pnl",
                "criterion_zh": "净利润最高",
                "summary_key": "single:industry.kdj.j_below_threshold=true",
                "label_zh": "行业 KDJ J 低于阈值=是",
                "reason": "best_environment_representative_trade",
            }
        ],
    }


def _base_run_plan_yaml(root: Path) -> Path:
    path = root / "base-run.yaml"
    path.write_text(
        "\n".join(
            [
                "run:",
                "  id: base-run",
                "  from_date: '2024-01-01'",
                "  to_date: '2024-03-31'",
                "data:",
                "  snapshot_root: data/snapshots",
                "  provider: tushare",
                "  refresh_snapshots: true",
                "  symbols: ['000001.SZ']",
                "strategy:",
                "  template: trend_template_v1",
                "  entry_method: kdj_oversold_entry",
                "  profit_taking_method: kdj_overheated_exit",
                "  stop_loss_method: fixed_percent_stop",
                "  add_on_method: none",
                "  sizing_rule: equal_weight",
                "constraints:",
                "  ashare:",
                "    enabled: true",
                "broker:",
                "  initial_cash: 1000000",
                "  commission_rate: 0.0003",
                "  stamp_tax_rate: 0.001",
                "  transfer_fee_rate: 0.00001",
                "  slippage:",
                "    type: percent",
                "    value: 0.0005",
                "execution:",
                "  engine: business",
                "  stake: 100",
                "output:",
                "  persist: true",
                "  report_root: reports",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
