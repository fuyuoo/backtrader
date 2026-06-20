import json
from pathlib import Path

import pytest

from attbacktrader.cli import strategy_environment_profile as strategy_environment_profile_cli
from attbacktrader.reports import (
    build_strategy_environment_profile_from_artifacts,
    build_strategy_environment_profile_from_run_dir,
    render_strategy_environment_profile_markdown_zh,
    write_strategy_environment_profile,
)


def test_strategy_environment_profile_classifies_environment_candidates() -> None:
    profile = build_strategy_environment_profile_from_artifacts(
        environment_fit=_environment_fit(),
        environment_fit_comparison=_environment_fit_comparison(),
        top=10,
    )
    markdown = render_strategy_environment_profile_markdown_zh(profile)

    assert profile["schema"] == "attbacktrader.strategy_environment_profile.v1"
    assert profile["run_id"] == "profile-test"
    assert profile["profile_summary"]["preferred_count"] == 1
    assert profile["profile_summary"]["avoid_count"] == 1
    assert profile["profile_summary"]["uncertain_count"] == 1

    preferred = profile["preferred_environments"][0]
    assert preferred["classification"] == "preferred"
    assert preferred["summary_key"] == "single:industry.kdj.j_below_threshold=true"
    assert preferred["evidence_strength"] == "strong"
    assert preferred["metrics"]["net_pnl"] == pytest.approx(120.0)
    assert preferred["deltas_vs_overall"]["return_on_entry_value"] == pytest.approx(0.05)
    assert preferred["sample_refs"][0]["trade_index"] == 1
    assert preferred["comparison_stability"][0]["status"] == "stable"

    avoid = profile["avoid_environments"][0]
    assert avoid["classification"] == "avoid"
    assert avoid["summary_key"] == "single:industry.kdj.j_below_threshold=false"
    assert avoid["risk_flags"] == []

    uncertain = profile["uncertain_environments"][0]
    assert uncertain["classification"] == "uncertain"
    assert uncertain["risk_flags"] == ["low_sample"]

    assert "# 策略环境画像" in markdown
    assert "## 适合环境候选" in markdown
    assert "## 规避环境候选" in markdown
    assert "## 不确定环境" in markdown
    assert "## 跨 Run 稳定性" in markdown


def test_strategy_environment_profile_run_dir_writer_and_cli(tmp_path: Path, capsys) -> None:
    run_dir = tmp_path / "profile-test"
    run_dir.mkdir()
    _write_json(run_dir / "environment_fit.json", _environment_fit())
    comparison_path = tmp_path / "environment_fit_comparison.json"
    _write_json(comparison_path, _environment_fit_comparison())

    profile = build_strategy_environment_profile_from_run_dir(
        run_dir,
        environment_fit_comparison=comparison_path,
        top=5,
    )
    json_path, markdown_path = write_strategy_environment_profile(profile, output_dir=tmp_path / "out")
    exit_code = strategy_environment_profile_cli.main(
        [
            "--run-dir",
            str(run_dir),
            "--environment-fit-comparison",
            str(comparison_path),
            "--top",
            "5",
            "--output-dir",
            str(tmp_path / "cli-out"),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert profile["run_id"] == "profile-test"
    assert json_path.exists()
    assert markdown_path.exists()
    assert exit_code == 0
    assert stdout["schema"] == "attbacktrader.strategy_environment_profile.v1"
    assert stdout["preferred_count"] == 1
    assert (tmp_path / "cli-out" / "strategy_environment_profile.json").exists()
    assert (tmp_path / "cli-out" / "strategy_environment_profile.zh.md").exists()


def _environment_fit() -> dict:
    return {
        "schema": "attbacktrader.environment_fit.v1",
        "run_id": "profile-test",
        "source_dir": "reports/profile-test",
        "min_sample_count": 2,
        "trade_count": 6,
        "overall": {
            "win_rate": 0.4,
            "average_return_pct": 0.0,
            "net_pnl": -100.0,
            "return_on_entry_value": -0.01,
        },
        "single_factor_summaries": [
            {
                "summary_kind": "single_factor",
                "field": "industry.kdj.j_below_threshold",
                "value": True,
                "label_zh": "行业 KDJ J 低于阈值=是",
                "sample_count": 3,
                "win_rate": 2 / 3,
                "average_return_pct": 0.03,
                "net_pnl": 120.0,
                "return_on_entry_value": 0.04,
                "trade_indexes": [1, 2, 3],
            },
            {
                "summary_kind": "single_factor",
                "field": "industry.kdj.j_below_threshold",
                "value": False,
                "label_zh": "行业 KDJ J 低于阈值=否",
                "sample_count": 2,
                "win_rate": 0.0,
                "average_return_pct": -0.04,
                "net_pnl": -220.0,
                "return_on_entry_value": -0.05,
                "trade_indexes": [4, 5],
            },
        ],
        "combination_summaries": [
            {
                "summary_kind": "combination",
                "fields": {
                    "industry.kdj.j_below_threshold": True,
                    "market.hs300.bullish_trend": True,
                },
                "profile_key": "industry.kdj.j_below_threshold=true|market.hs300.bullish_trend=true",
                "label_zh": "行业 KDJ J 低于阈值=是；沪深300多头趋势=是",
                "sample_count": 1,
                "win_rate": 1.0,
                "average_return_pct": 0.08,
                "net_pnl": 80.0,
                "return_on_entry_value": 0.08,
                "trade_indexes": [6],
            }
        ],
    }


def _environment_fit_comparison() -> dict:
    return {
        "schema": "attbacktrader.environment_fit_comparison.v1",
        "run_ids": ["baseline", "profile-test"],
        "best_environment_stability": [
            {
                "criterion": "best_by_net_pnl",
                "criterion_zh": "净利润最高",
                "status": "stable",
                "status_zh": "稳定线索",
                "sample_risk_run_ids": [],
                "run_environments": [
                    {
                        "run_id": "profile-test",
                        "summary_key": "single:industry.kdj.j_below_threshold=true",
                        "label_zh": "行业 KDJ J 低于阈值=是",
                        "sample_count": 3,
                        "low_sample": False,
                        "trade_indexes": [1, 2, 3],
                    }
                ],
            }
        ],
    }


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
