import json
from pathlib import Path

from scripts import acceptance_smoke


def test_acceptance_smoke_runs_strategy_adaptation_v1_golden_check(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    calls = []

    def fake_run(command, *, cwd, capture_stdout=False):
        calls.append({"command": command, "cwd": cwd, "capture_stdout": capture_stdout})
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

    monkeypatch.setattr(acceptance_smoke, "_run", fake_run)

    acceptance_smoke._run_strategy_adaptation_v1_golden_check(python=Path("python"), repo_root=tmp_path)

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
        }
    ]
    stdout = capsys.readouterr().out
    assert "Strategy Adaptation V1 golden check summary" in stdout
    assert "failed_count: 0" in stdout
