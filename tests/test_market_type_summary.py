import json
from pathlib import Path

import pytest

from attbacktrader.cli import market_type_summary as market_type_summary_cli
from attbacktrader.reports import (
    build_market_type_summary,
    render_market_type_summary_markdown_zh,
    write_market_type_summary,
)


def test_market_type_summary_groups_segments_from_manifest(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path)
    _run_dir(
        tmp_path,
        run_id="bull-a",
        cumulative_return=0.10,
        max_drawdown=0.03,
        trade_count=10,
        win_rate=0.6,
        sold_too_early_rate=0.8,
    )
    _run_dir(
        tmp_path,
        run_id="bull-b",
        cumulative_return=0.20,
        max_drawdown=0.05,
        trade_count=5,
        win_rate=0.8,
        sold_too_early_rate=1.0,
    )
    _run_dir(
        tmp_path,
        run_id="bear-a",
        cumulative_return=-0.12,
        max_drawdown=0.15,
        trade_count=3,
        win_rate=0.0,
        sold_too_early_rate=0.5,
    )

    summary = build_market_type_summary(manifest_path, report_root=tmp_path, min_segment_trades=5)
    markdown = render_market_type_summary_markdown_zh(summary)
    json_path, markdown_path = write_market_type_summary(summary, output_dir=tmp_path / "summary")

    bull = summary["market_types"][0]
    bear = summary["market_types"][1]
    assert summary["schema"] == "attbacktrader.market_type_summary.v1"
    assert summary["segment_count"] == 3
    assert bull["market_type_id"] == "bull_market"
    assert bull["segment_count"] == 2
    assert bull["total_trade_count"] == 15
    assert bull["average_return_pct"] == pytest.approx(0.15)
    assert round(bull["weighted_win_rate"], 4) == 0.6667
    assert bull["average_sold_too_early_rate_5d"] == pytest.approx(0.9)
    assert bear["low_sample_segment_count"] == 1
    assert "熊市 有 1 段交易样本不足" in summary["validation_warnings"]
    assert "市场类型验证汇总" in markdown
    assert "类型汇总" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def test_market_type_summary_cli_writes_outputs(tmp_path: Path, capsys) -> None:
    manifest_path = _write_manifest(tmp_path)
    for run_id, value in (("bull-a", 0.10), ("bull-b", 0.20), ("bear-a", -0.12)):
        _run_dir(
            tmp_path,
            run_id=run_id,
            cumulative_return=value,
            max_drawdown=0.05,
            trade_count=8,
            win_rate=0.5,
            sold_too_early_rate=0.75,
        )

    exit_code = market_type_summary_cli.main(
        [
            "--manifest",
            str(manifest_path),
            "--report-root",
            str(tmp_path),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["schema"] == "attbacktrader.market_type_summary.v1"
    assert stdout["segment_count"] == 3
    assert stdout["artifacts"]["market_type_summary_json_path"].endswith("market_type_summary.json")
    assert (tmp_path / "out" / "market_type_summary.json").exists()
    assert (tmp_path / "out" / "market_type_summary.zh.md").exists()


def _write_manifest(root: Path) -> Path:
    manifest = {
        "schema": "attbacktrader.market_segment_run_manifest.v1",
        "base_run_id": "base",
        "market_types": [
            {
                "market_type_id": "bull_market",
                "label_zh": "牛市",
                "strategy_switching_use_zh": "验证趋势持有。",
                "selection_rule_zh": "指数中期趋势向上。",
            },
            {
                "market_type_id": "bear_market",
                "label_zh": "熊市",
                "strategy_switching_use_zh": "验证降仓或暂停。",
                "selection_rule_zh": "指数中期趋势向下。",
            },
        ],
        "segments": [
            {
                "segment_id": "bull_a",
                "label_zh": "牛市 A",
                "market_type_id": "bull_market",
                "market_type_label_zh": "牛市",
                "validation_role": "bull_market",
                "from_date": "2020-01-01",
                "to_date": "2020-06-30",
                "run_id": "bull-a",
            },
            {
                "segment_id": "bull_b",
                "label_zh": "牛市 B",
                "market_type_id": "bull_market",
                "market_type_label_zh": "牛市",
                "validation_role": "bull_market",
                "from_date": "2020-07-01",
                "to_date": "2020-12-31",
                "run_id": "bull-b",
            },
            {
                "segment_id": "bear_a",
                "label_zh": "熊市 A",
                "market_type_id": "bear_market",
                "market_type_label_zh": "熊市",
                "validation_role": "bear_market",
                "from_date": "2021-01-01",
                "to_date": "2021-06-30",
                "run_id": "bear-a",
            },
        ],
    }
    path = root / "market_segment_run_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _run_dir(
    root: Path,
    *,
    run_id: str,
    cumulative_return: float,
    max_drawdown: float,
    trade_count: int,
    win_rate: float,
    sold_too_early_rate: float,
) -> Path:
    path = root / run_id
    path.mkdir()
    _write_json(
        path / "report.json",
        {
            "returns": {
                "final_equity": 1000000.0 * (1.0 + cumulative_return),
                "cumulative_return": cumulative_return,
            },
            "risk": {"max_drawdown": max_drawdown},
            "trade_quality": {
                "trade_count": trade_count,
                "win_rate": win_rate,
                "average_win": 0.08,
                "average_loss": -0.03,
                "profit_loss_ratio": 2.0,
            },
        },
    )
    _write_json(
        path / "post_exit_analysis.json",
        {
            "window_days": 5,
            "summaries": [
                {
                    "group": "all",
                    "sample_count": trade_count,
                    "sold_too_early_rate": sold_too_early_rate,
                    "average_max_high_return_pct": 0.04,
                    "average_fifth_day_close_return_pct": 0.01,
                }
            ],
        },
    )
    _write_json(
        path / "environment_fit.json",
        {
            "trade_count": trade_count,
            "overall": {
                "net_pnl": cumulative_return * 1000000.0,
                "return_on_entry_value": cumulative_return,
            },
        },
    )
    _write_json(
        path / "strategy_environment_profile.json",
        {
            "profile_summary": {
                "preferred_count": 1,
                "avoid_count": 0,
                "uncertain_count": 2,
            }
        },
    )
    return path


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
