import json
from pathlib import Path

from attbacktrader.cli import strategy_variant_attribution as strategy_variant_attribution_cli
from attbacktrader.reports import (
    build_strategy_variant_attribution,
    render_strategy_variant_attribution_markdown_zh,
    write_strategy_variant_attribution,
)


def test_strategy_variant_attribution_explains_fast_reentry_behavior(tmp_path: Path) -> None:
    baseline_manifest = _write_manifest(tmp_path, run_id="base-bull", variant=False)
    variant_manifest = _write_manifest(tmp_path, run_id="variant-bull", variant=True)
    _run_dir(
        tmp_path,
        "base-bull",
        cumulative_return=0.20,
        max_drawdown=0.05,
        trades=[
            _trade(1, "000001.SZ", "2020-01-01", "2020-01-20", 0.10, "kdj_overheated_exit", "KDJ_J_ABOVE_100"),
            _trade(2, "000001.SZ", "2020-02-15", "2020-03-01", 0.08, "kdj_overheated_exit", "KDJ_J_ABOVE_100"),
        ],
    )
    _run_dir(
        tmp_path,
        "variant-bull",
        cumulative_return=0.08,
        max_drawdown=0.03,
        trades=[
            _trade(1, "000001.SZ", "2020-01-01", "2020-01-02", 0.01, "ma_macd_weakening_exit", "MA_MACD_WEAKENING"),
            _trade(2, "000001.SZ", "2020-01-04", "2020-01-05", 0.02, "ma_macd_weakening_exit", "MA_MACD_WEAKENING"),
            _trade(3, "000001.SZ", "2020-01-07", "2020-01-08", -0.01, "ma_macd_weakening_exit", "MA_MACD_WEAKENING"),
            _trade(4, "000001.SZ", "2020-01-10", "2020-01-11", 0.01, "ma_macd_weakening_exit", "MA_MACD_WEAKENING"),
        ],
    )

    attribution = build_strategy_variant_attribution(
        baseline_manifest,
        variant_manifest,
        market_type_id="bull_market",
        report_root=tmp_path,
        short_reentry_days=5,
    )
    markdown = render_strategy_variant_attribution_markdown_zh(attribution)
    json_path, markdown_path = write_strategy_variant_attribution(attribution, output_dir=tmp_path / "out")

    segment = attribution["segments"][0]
    assert attribution["schema"] == "attbacktrader.strategy_variant_attribution.v1"
    assert attribution["overall"]["delta"]["trade_count"] == 2
    assert attribution["overall"]["delta"]["short_reentry_count"] == 3
    assert attribution["overall"]["delta"]["average_holding_days"] < 0
    assert segment["primary_exit_change_zh"] == "kdj_overheated_exit -> ma_macd_weakening_exit"
    assert "holding_period_compressed" in segment["diagnosis_flags"]
    assert "trade_count_increased" in segment["diagnosis_flags"]
    assert segment["variant"]["short_reentry_samples"][0]["run_id"] == "variant-bull"
    assert "策略变体归因复盘" in markdown
    assert "交易数增加主要候选原因" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def test_strategy_variant_attribution_cli_writes_outputs(tmp_path: Path, capsys) -> None:
    baseline_manifest = _write_manifest(tmp_path, run_id="base-bull", variant=False)
    variant_manifest = _write_manifest(tmp_path, run_id="variant-bull", variant=True)
    for run_id, exit_method, exit_reason in (
        ("base-bull", "kdj_overheated_exit", "KDJ_J_ABOVE_100"),
        ("variant-bull", "ma_macd_weakening_exit", "MA_MACD_WEAKENING"),
    ):
        _run_dir(
            tmp_path,
            run_id,
            cumulative_return=0.05,
            max_drawdown=0.02,
            trades=[
                _trade(1, "000001.SZ", "2020-01-01", "2020-01-03", 0.02, exit_method, exit_reason),
            ],
        )

    exit_code = strategy_variant_attribution_cli.main(
        [
            "--baseline-manifest",
            str(baseline_manifest),
            "--variant-manifest",
            str(variant_manifest),
            "--market-type-id",
            "bull_market",
            "--report-root",
            str(tmp_path),
            "--output-dir",
            str(tmp_path / "cli-out"),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["schema"] == "attbacktrader.strategy_variant_attribution.v1"
    assert stdout["market_type_id"] == "bull_market"
    assert (tmp_path / "cli-out" / "strategy_variant_attribution.json").exists()
    assert (tmp_path / "cli-out" / "strategy_variant_attribution.zh.md").exists()


def _write_manifest(root: Path, *, run_id: str, variant: bool) -> Path:
    segment = {
        "segment_id": "bull_a",
        "market_type_id": "bull_market",
        "market_type_label_zh": "牛市",
        "from_date": "2020-01-01",
        "to_date": "2020-03-31",
        "run_id": run_id,
    }
    if variant:
        segment["segment_label_zh"] = "牛市 A"
        segment["baseline_run_id"] = "base-bull"
    else:
        segment["label_zh"] = "牛市 A"
    payload = {
        "schema": "attbacktrader.strategy_variant_run_manifest.v1" if variant else "attbacktrader.market_segment_run_manifest.v1",
        "market_types": [{"market_type_id": "bull_market", "label_zh": "牛市"}],
        "segments": [segment],
    }
    path = root / ("variant_manifest.json" if variant else "baseline_manifest.json")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _run_dir(
    root: Path,
    run_id: str,
    *,
    cumulative_return: float,
    max_drawdown: float,
    trades: list[dict],
) -> None:
    path = root / run_id
    path.mkdir()
    win_count = sum(1 for trade in trades if trade["return_pct"] > 0)
    loss_count = sum(1 for trade in trades if trade["return_pct"] < 0)
    wins = [trade["return_pct"] for trade in trades if trade["return_pct"] > 0]
    losses = [trade["return_pct"] for trade in trades if trade["return_pct"] < 0]
    _write_json(
        path / "report.json",
        {
            "returns": {"cumulative_return": cumulative_return},
            "risk": {"max_drawdown": max_drawdown},
            "trade_quality": {
                "trade_count": len(trades),
                "win_count": win_count,
                "loss_count": loss_count,
                "win_rate": win_count / len(trades) if trades else None,
                "average_win": sum(wins) / len(wins) if wins else None,
                "average_loss": sum(losses) / len(losses) if losses else None,
            },
        },
    )
    _write_json(path / "trade_lifecycle.json", {"trade_count": len(trades), "indexes": {}, "lifecycles": trades})


def _trade(
    trade_index: int,
    symbol: str,
    entry_date: str,
    exit_date: str,
    return_pct: float,
    exit_method: str,
    exit_reason: str,
) -> dict:
    return {
        "trade_index": trade_index,
        "symbol": symbol,
        "outcome": "win" if return_pct > 0 else "loss",
        "entry_date": entry_date,
        "exit_date": exit_date,
        "exit_reason": exit_reason,
        "return_pct": return_pct,
        "events": [
            {
                "event_type": "entry",
                "trade_date": entry_date,
                "method_name": "kdj_oversold_entry",
                "reason_code": "KDJ_J_BELOW_13",
                "checks": {"kdj_j_below_threshold": True},
                "categories": {},
                "values": {},
                "sizing_context": {},
                "executions": [],
            },
            {
                "event_type": "exit",
                "trade_date": exit_date,
                "method_name": exit_method,
                "reason_code": exit_reason,
                "checks": {},
                "categories": {},
                "values": {},
                "sizing_context": {},
                "executions": [],
            },
        ],
    }


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
