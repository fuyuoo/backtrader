import json
from pathlib import Path

from scripts import acceptance_smoke


def test_acceptance_smoke_runs_sealed_golden_checks(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    calls = []

    def fake_run(command, *, cwd, capture_stdout=False):
        calls.append({"command": command, "cwd": cwd, "capture_stdout": capture_stdout})
        if "attbacktrader.cli.review_golden_check" in command:
            markdown_path = (
                tmp_path
                / acceptance_smoke.STRATEGY_ADAPTATION_V1_GOLDEN_CHECK_OUTPUT
                / "ai_review_golden_check.zh.md"
            )
            markdown_path.parent.mkdir(parents=True)
            markdown_path.write_text("# AI 复盘 Golden Check\n", encoding="utf-8")
            return json.dumps(
                {
                    "status": "ok",
                    "check_count": 72,
                    "failed_count": 0,
                    "artifacts": {
                        "ai_review_golden_check_chinese_markdown_path": str(
                            acceptance_smoke.STRATEGY_ADAPTATION_V1_GOLDEN_CHECK_OUTPUT
                            / "ai_review_golden_check.zh.md"
                        )
                    },
                }
            )
        markdown_path = (
            tmp_path
            / acceptance_smoke.WORKBENCH_CLOSURE_GOLDEN_CHECK_OUTPUT
            / "workbench_closure_golden_check.zh.md"
        )
        markdown_path.parent.mkdir(parents=True)
        markdown_path.write_text("# Workbench Closure Golden Check\n", encoding="utf-8")
        return json.dumps(
            {
                "status": "ok",
                "check_count": 124,
                "failed_count": 0,
                "artifacts": {
                    "workbench_closure_golden_check_chinese_markdown_path": str(
                        acceptance_smoke.WORKBENCH_CLOSURE_GOLDEN_CHECK_OUTPUT
                        / "workbench_closure_golden_check.zh.md"
                    )
                },
            }
        )

    monkeypatch.setattr(acceptance_smoke, "_run", fake_run)

    acceptance_smoke._run_strategy_adaptation_v1_golden_check(python=Path("python"), repo_root=tmp_path)
    acceptance_smoke._run_workbench_closure_golden_check(python=Path("python"), repo_root=tmp_path)

    assert calls == [
        {
            "command": [
                "python",
                "-m",
                "attbacktrader.cli.review_golden_check",
                "--review",
                str(acceptance_smoke.STRATEGY_ADAPTATION_V1_REVIEW),
                "--golden",
                str(acceptance_smoke.STRATEGY_ADAPTATION_V1_GOLDEN),
                "--output-dir",
                str(acceptance_smoke.STRATEGY_ADAPTATION_V1_GOLDEN_CHECK_OUTPUT),
            ],
            "cwd": tmp_path,
            "capture_stdout": True,
        },
        {
            "command": [
                "python",
                "-m",
                "attbacktrader.cli.workbench_closure_golden_check",
                "--baseline",
                str(acceptance_smoke.WORKBENCH_CLOSURE_BASELINE),
                "--closure-doc",
                str(acceptance_smoke.WORKBENCH_CLOSURE_DOC),
                "--output-dir",
                str(acceptance_smoke.WORKBENCH_CLOSURE_GOLDEN_CHECK_OUTPUT),
            ],
            "cwd": tmp_path,
            "capture_stdout": True,
        },
    ]
    stdout = capsys.readouterr().out
    assert "Strategy Adaptation V1 golden check summary" in stdout
    assert "Workbench Closure golden check summary" in stdout
    assert "failed_count: 0" in stdout


def test_acceptance_smoke_includes_strategy_output_contract_baseline() -> None:
    assert "tests/test_strategy_output_contract.py" in acceptance_smoke.BUSINESS_TESTS
    assert "tests/test_strategy_integration_template.py" in acceptance_smoke.BUSINESS_TESTS
    assert "tests/test_strategy_integration_validation.py" in acceptance_smoke.BUSINESS_TESTS
    assert "tests/test_strategy_integration_closure.py" in acceptance_smoke.BUSINESS_TESTS
    assert "tests/test_trend_template_v1_golden.py" in acceptance_smoke.BUSINESS_TESTS


def test_acceptance_smoke_tushare_run_requests_full_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    token_path = tmp_path / ".secrets" / "tushare_token.txt"
    token_path.parent.mkdir()
    token_path.write_text("token", encoding="utf-8")
    report_path = tmp_path / "reports" / "smoke" / "report.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# report\n", encoding="utf-8")
    calls = []

    def fake_run(command, *, cwd, capture_stdout=False):
        calls.append({"command": command, "cwd": cwd, "capture_stdout": capture_stdout})
        return json.dumps(
            {
                "run_id": "smoke",
                "engine": "backtrader",
                "final_value": 1000000.0,
                "report": {
                    "returns": {"cumulative_return": 0.0},
                    "execution_costs": {"completed_count": 1},
                },
                "artifacts": {"report_markdown_path": "reports/smoke/report.md"},
            }
        )

    monkeypatch.setattr(acceptance_smoke, "_run", fake_run)

    acceptance_smoke._run_tushare_smoke(
        python=Path("python"),
        repo_root=tmp_path,
        config_path=Path("examples/run-tushare-smoke.yaml"),
        token_file=Path(".secrets/tushare_token.txt"),
    )

    command = calls[0]["command"]
    assert "--full-json" in command
    assert command[command.index("--token-file") + 1] == str(token_path)
