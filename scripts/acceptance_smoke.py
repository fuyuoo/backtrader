"""Run the curated ATTbacktrader MVP acceptance checks."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


BUSINESS_TESTS = (
    "tests/test_indicator_snapshots.py",
    "tests/test_indicator_frame.py",
    "tests/test_backtrader_adapter.py",
    "tests/test_strategy_methods.py",
    "tests/test_add_on_execution.py",
    "tests/test_entry_attribution.py",
    "tests/test_trend_template_v1_golden.py",
    "tests/test_backtest_report.py",
    "tests/test_report_renderer.py",
    "tests/test_result_diagnostics.py",
    "tests/test_trade_lifecycle.py",
    "tests/test_trade_review.py",
    "tests/test_environment_fit.py",
    "tests/test_environment_fit_comparison.py",
    "tests/test_post_exit_analysis.py",
    "tests/test_tushare_provider.py",
    "tests/test_parquet_snapshots.py",
    "tests/test_reference_snapshots.py",
    "tests/test_trading_calendar.py",
    "tests/test_bar_resampling.py",
    "tests/test_market_regime.py",
    "tests/test_scenario_fit.py",
    "tests/test_portfolio_behavior.py",
    "tests/test_execution_costs.py",
    "tests/test_analysis_pipeline.py",
    "tests/test_report_writer.py",
    "tests/test_evidence_validation.py",
    "tests/test_correctness_golden_samples.py",
    "tests/test_execution_constraint_golden_samples.py",
    "tests/test_sizing_rules.py",
    "tests/test_ashare_constraints.py",
    "tests/test_attbacktrader_config.py",
    "tests/test_prepared_run_data.py",
    "tests/test_strategy_bindings.py",
    "tests/test_strategy_output_contract.py",
    "tests/test_strategy_integration_template.py",
    "tests/test_strategy_integration_validation.py",
    "tests/test_strategy_integration_closure.py",
    "tests/test_run_plan_executor.py",
    "tests/test_run_catalog.py",
    "tests/test_experiment_lifecycle.py",
    "tests/test_experiment_decisions.py",
    "tests/test_workbench_closure.py",
    "tests/test_workbench_closure_golden_check.py",
    "tests/test_ai_skill_entry_contract.py",
    "tests/test_run_comparison.py",
    "tests/test_run_regression.py",
    "tests/test_attribution_filter_experiments.py",
    "tests/test_market_segment_runs.py",
    "tests/test_market_type_summary.py",
    "tests/test_strategy_adaptation_matrix.py",
    "tests/test_strategy_variant_attribution.py",
    "tests/test_review_packet.py",
    "tests/test_ai_review.py",
    "tests/test_acceptance_smoke.py",
    "tests/test_run_data_tools.py",
)

STRATEGY_ADAPTATION_V1_REVIEW = Path("docs/strategy-adaptation-v1-ai-review.md")
STRATEGY_ADAPTATION_V1_GOLDEN = Path("examples/strategy-adaptation-v1-ai-review-golden.json")
STRATEGY_ADAPTATION_V1_GOLDEN_CHECK_OUTPUT = Path("reports/strategy-adaptation-v1-ai-review-golden-check")
WORKBENCH_CLOSURE_BASELINE = Path("examples/backtest-workbench-v1-baseline.json")
WORKBENCH_CLOSURE_DOC = Path("docs/backtest-workbench-v1-closure.md")
WORKBENCH_CLOSURE_GOLDEN_CHECK_OUTPUT = Path("reports/workbench-closure-golden-check")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    python = Path(args.python)

    _run([str(python), "-m", "pytest", *BUSINESS_TESTS, "-q"], cwd=repo_root)
    _run_strategy_adaptation_v1_golden_check(python=python, repo_root=repo_root)
    _run_workbench_closure_golden_check(python=python, repo_root=repo_root)

    if args.with_tushare:
        _run_tushare_smoke(
            python=python,
            repo_root=repo_root,
            config_path=Path(args.tushare_config),
            token_file=Path(args.token_file),
        )

    print("\nAcceptance smoke passed.", flush=True)
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ATTbacktrader acceptance checks")
    parser.add_argument(
        "--with-tushare",
        action="store_true",
        help="Also run examples/run-tushare-smoke.yaml against the real Tushare provider",
    )
    parser.add_argument("--token-file", default=".secrets/tushare_token.txt")
    parser.add_argument("--tushare-config", default="examples/run-tushare-smoke.yaml")
    parser.add_argument("--python", default=sys.executable, help="Python executable used for subprocesses")
    return parser.parse_args(argv)


def _run_tushare_smoke(
    *,
    python: Path,
    repo_root: Path,
    config_path: Path,
    token_file: Path,
) -> None:
    token_path = _resolve(repo_root, token_file)
    if not token_path.exists() or not token_path.read_text(encoding="utf-8").strip():
        raise SystemExit(f"Tushare token file is missing or empty: {token_file}")

    stdout = _run(
        [
            str(python),
            "-m",
            "attbacktrader.cli.run_plan",
            "--config",
            str(config_path),
            "--token-file",
            str(token_path),
            "--full-json",
        ],
        cwd=repo_root,
        capture_stdout=True,
    )
    payload = json.loads(stdout)
    artifacts = payload.get("artifacts", {})
    report_markdown_path = _resolve(repo_root, Path(artifacts["report_markdown_path"]))
    if not report_markdown_path.exists():
        raise SystemExit(f"Expected Markdown report was not written: {report_markdown_path}")

    print("\nTushare smoke summary", flush=True)
    print(f"run_id: {payload['run_id']}", flush=True)
    print(f"engine: {payload['engine']}", flush=True)
    print(f"final_value: {payload['final_value']}", flush=True)
    print(f"cumulative_return: {payload['report']['returns']['cumulative_return']}", flush=True)
    print(f"completed_orders: {payload['report']['execution_costs']['completed_count']}", flush=True)
    print(f"report_md: {artifacts['report_markdown_path']}", flush=True)


def _run_strategy_adaptation_v1_golden_check(
    *,
    python: Path,
    repo_root: Path,
) -> None:
    stdout = _run(
        [
            str(python),
            "-m",
            "attbacktrader.cli.review_golden_check",
            "--review",
            str(STRATEGY_ADAPTATION_V1_REVIEW),
            "--golden",
            str(STRATEGY_ADAPTATION_V1_GOLDEN),
            "--output-dir",
            str(STRATEGY_ADAPTATION_V1_GOLDEN_CHECK_OUTPUT),
        ],
        cwd=repo_root,
        capture_stdout=True,
    )
    payload = json.loads(stdout)
    if payload.get("status") != "ok":
        raise SystemExit(f"Strategy Adaptation V1 AI review golden check failed: {payload.get('failed_count')}")
    artifacts = payload.get("artifacts", {})
    check_markdown_path = _resolve(repo_root, Path(artifacts["ai_review_golden_check_chinese_markdown_path"]))
    if not check_markdown_path.exists():
        raise SystemExit(f"Expected AI review golden check Markdown was not written: {check_markdown_path}")

    print("\nStrategy Adaptation V1 golden check summary", flush=True)
    print(f"status: {payload['status']}", flush=True)
    print(f"check_count: {payload['check_count']}", flush=True)
    print(f"failed_count: {payload['failed_count']}", flush=True)
    print(f"check_md: {artifacts['ai_review_golden_check_chinese_markdown_path']}", flush=True)


def _run_workbench_closure_golden_check(
    *,
    python: Path,
    repo_root: Path,
) -> None:
    stdout = _run(
        [
            str(python),
            "-m",
            "attbacktrader.cli.workbench_closure_golden_check",
            "--baseline",
            str(WORKBENCH_CLOSURE_BASELINE),
            "--closure-doc",
            str(WORKBENCH_CLOSURE_DOC),
            "--output-dir",
            str(WORKBENCH_CLOSURE_GOLDEN_CHECK_OUTPUT),
        ],
        cwd=repo_root,
        capture_stdout=True,
    )
    payload = json.loads(stdout)
    if payload.get("status") != "ok":
        raise SystemExit(f"Workbench Closure golden check failed: {payload.get('failed_count')}")
    artifacts = payload.get("artifacts", {})
    check_markdown_path = _resolve(
        repo_root,
        Path(artifacts["workbench_closure_golden_check_chinese_markdown_path"]),
    )
    if not check_markdown_path.exists():
        raise SystemExit(f"Expected Workbench closure golden check Markdown was not written: {check_markdown_path}")

    print("\nWorkbench Closure golden check summary", flush=True)
    print(f"status: {payload['status']}", flush=True)
    print(f"check_count: {payload['check_count']}", flush=True)
    print(f"failed_count: {payload['failed_count']}", flush=True)
    print(f"check_md: {artifacts['workbench_closure_golden_check_chinese_markdown_path']}", flush=True)


def _run(
    command: list[str],
    *,
    cwd: Path,
    capture_stdout: bool = False,
) -> str:
    print(f"\n$ {' '.join(command)}", flush=True)
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=capture_stdout,
    )
    if completed.returncode != 0:
        if capture_stdout:
            if completed.stdout:
                print(completed.stdout)
            if completed.stderr:
                print(completed.stderr, file=sys.stderr)
        raise SystemExit(completed.returncode)

    if capture_stdout:
        return completed.stdout
    return ""


def _resolve(repo_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    return repo_root / path


if __name__ == "__main__":
    raise SystemExit(main())
