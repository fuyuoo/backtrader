import json
from pathlib import Path

import pytest

from attbacktrader.cli import market_type_summary as market_type_summary_cli
from attbacktrader.cli import strategy_variant_validation as strategy_variant_validation_cli
from attbacktrader.reports import (
    build_market_type_summary,
    build_strategy_variant_validation,
    render_market_type_summary_markdown_zh,
    render_strategy_variant_validation_markdown_zh,
    write_strategy_variant_validation,
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


def test_strategy_variant_validation_compares_market_type_summaries(tmp_path: Path, capsys) -> None:
    baseline = _market_type_summary_payload(
        [
            _market_type("bull_market", "牛市", 0.20, 0.06, 0.60, 10),
            _market_type("bear_market", "熊市", -0.12, 0.15, 0.20, 8),
        ],
        warnings=["牛市 有 1 段交易样本不足"],
    )
    variant = _market_type_summary_payload(
        [
            _market_type("bull_market", "牛市", 0.12, 0.04, 0.50, 18),
            _market_type("bear_market", "熊市", -0.05, 0.08, 0.25, 6),
        ],
        warnings=["牛市 有 1 段交易样本不足"],
    )
    baseline_path = tmp_path / "baseline.json"
    variant_path = tmp_path / "variant.json"
    baseline_path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")
    variant_path.write_text(json.dumps(variant, ensure_ascii=False), encoding="utf-8")

    validation = build_strategy_variant_validation(baseline_path, variant_path)
    markdown = render_strategy_variant_validation_markdown_zh(validation)
    json_path, markdown_path = write_strategy_variant_validation(validation, output_dir=tmp_path / "validation")
    exit_code = strategy_variant_validation_cli.main(
        [
            "--baseline-summary",
            str(baseline_path),
            "--variant-summary",
            str(variant_path),
            "--output-dir",
            str(tmp_path / "cli-validation"),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    bull = next(row for row in validation["rows"] if row["market_type_id"] == "bull_market")
    bear = next(row for row in validation["rows"] if row["market_type_id"] == "bear_market")
    assert validation["schema"] == "attbacktrader.strategy_variant_validation.v1"
    assert bull["delta"]["average_return_pct"] == pytest.approx(-0.08)
    assert bull["direction_zh"] == "收益和胜率下降"
    assert bear["delta"]["average_return_pct"] == pytest.approx(0.07)
    assert bear["direction_zh"] == "收益提升且回撤未扩大"
    assert "策略变体验证对比" in markdown
    assert "基线: 牛市 有 1 段交易样本不足" in validation["validation_warnings"]
    assert json_path.exists()
    assert markdown_path.exists()
    assert exit_code == 0
    assert stdout["schema"] == "attbacktrader.strategy_variant_validation.v1"
    assert (tmp_path / "cli-validation" / "strategy_variant_validation.json").exists()


def _market_type_summary_payload(market_types: list[dict], *, warnings: list[str] | None = None) -> dict:
    return {
        "schema": "attbacktrader.market_type_summary.v1",
        "base_run_id": "summary-test",
        "market_types": market_types,
        "validation_warnings": warnings or [],
    }


def _market_type(
    market_type_id: str,
    label_zh: str,
    average_return: float,
    average_drawdown: float,
    win_rate: float,
    trade_count: int,
) -> dict:
    return {
        "market_type_id": market_type_id,
        "market_type_label_zh": label_zh,
        "segment_count": 3,
        "total_trade_count": trade_count,
        "average_return_pct": average_return,
        "average_max_drawdown": average_drawdown,
        "weighted_win_rate": win_rate,
        "profitable_segment_count": 2,
        "loss_segment_count": 1,
        "low_sample_segment_count": 0,
        "average_sold_too_early_rate_5d": 0.9,
    }


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
