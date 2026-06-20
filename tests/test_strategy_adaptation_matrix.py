import json
from pathlib import Path

import pytest

from attbacktrader.cli import strategy_adaptation_drilldown as strategy_adaptation_drilldown_cli
from attbacktrader.cli import strategy_adaptation_matrix as strategy_adaptation_matrix_cli
from attbacktrader.cli import strategy_variant_drafts as strategy_variant_drafts_cli
from attbacktrader.cli import strategy_variant_runs as strategy_variant_runs_cli
from attbacktrader.config import RunPlan
from attbacktrader.reports import (
    build_strategy_adaptation_drilldown,
    build_strategy_adaptation_matrix,
    build_strategy_variant_run_manifest,
    build_strategy_variant_drafts,
    render_strategy_adaptation_drilldown_markdown_zh,
    render_strategy_adaptation_matrix_markdown_zh,
    render_strategy_variant_run_manifest_markdown_zh,
    render_strategy_variant_drafts_markdown_zh,
    write_strategy_adaptation_drilldown,
    write_strategy_adaptation_matrix,
    write_strategy_variant_run_manifest,
    write_strategy_variant_drafts,
)


def test_strategy_adaptation_matrix_reverse_looks_up_trade_entry_evidence(tmp_path: Path) -> None:
    summary_path = _write_market_type_summary(tmp_path)
    _run_dir(
        tmp_path,
        "bull-a",
        [
            _trade(1, "000001.SZ", "win", "2020-01-02", "2020-01-10", 0.10, ma25=True, hs300=True),
            _trade(2, "000002.SZ", "loss", "2020-01-03", "2020-01-11", -0.03, ma25=False, hs300=True),
        ],
        sold_too_early_by_key={
            ("000001.SZ", "2020-01-02", "2020-01-10", "KDJ_J_ABOVE_100"): True,
            ("000002.SZ", "2020-01-03", "2020-01-11", "STOP_LOSS"): False,
        },
    )
    _run_dir(
        tmp_path,
        "bull-b",
        [
            _trade(1, "000003.SZ", "win", "2020-02-02", "2020-02-10", 0.08, ma25=True, hs300=True),
            _trade(2, "000004.SZ", "win", "2020-02-03", "2020-02-11", 0.04, ma25=True, hs300=True),
        ],
        sold_too_early_by_key={
            ("000003.SZ", "2020-02-02", "2020-02-10", "KDJ_J_ABOVE_100"): True,
            ("000004.SZ", "2020-02-03", "2020-02-11", "KDJ_J_ABOVE_100"): False,
        },
    )
    _run_dir(
        tmp_path,
        "bear-a",
        [
            _trade(1, "000005.SZ", "loss", "2021-01-02", "2021-01-10", -0.07, ma25=False, hs300=False),
            _trade(2, "000006.SZ", "loss", "2021-01-03", "2021-01-11", -0.05, ma25=False, hs300=False),
        ],
        sold_too_early_by_key={
            ("000005.SZ", "2021-01-02", "2021-01-10", "STOP_LOSS"): False,
            ("000006.SZ", "2021-01-03", "2021-01-11", "STOP_LOSS"): False,
        },
    )

    matrix = build_strategy_adaptation_matrix(summary_path, min_factor_trades=1, top_factors=5)
    markdown = render_strategy_adaptation_matrix_markdown_zh(matrix)
    json_path, markdown_path = write_strategy_adaptation_matrix(matrix, output_dir=tmp_path / "out")

    bull = matrix["market_types"][0]
    bear = matrix["market_types"][1]
    ma25_true = _factor(bull, "entry.check.symbol.ma.price_above_ma25", "true")

    assert matrix["schema"] == "attbacktrader.strategy_adaptation_matrix.v1"
    assert matrix["trade_count"] == 6
    assert bull["adaptation"] == "preferred"
    assert bear["adaptation"] == "avoid"
    assert ma25_true["sample_count"] == 3
    assert ma25_true["win_count"] == 3
    assert ma25_true["win_rate"] == pytest.approx(1.0)
    assert ma25_true["sold_too_early_count"] == 2
    assert ma25_true["sample_refs"][0]["run_id"] == "bull-a"
    assert ma25_true["sample_refs"][0]["trade_index"] == 1
    assert "策略适配矩阵" in markdown
    assert "价格在 MA25 上方" in markdown
    assert "不重算指标" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def test_strategy_adaptation_matrix_cli_writes_outputs(tmp_path: Path, capsys) -> None:
    summary_path = _write_market_type_summary(tmp_path)
    for run_id in ("bull-a", "bull-b", "bear-a"):
        _run_dir(
            tmp_path,
            run_id,
            [_trade(1, "000001.SZ", "win", "2020-01-02", "2020-01-10", 0.05, ma25=True, hs300=True)],
            sold_too_early_by_key={
                ("000001.SZ", "2020-01-02", "2020-01-10", "KDJ_J_ABOVE_100"): True,
            },
        )

    exit_code = strategy_adaptation_matrix_cli.main(
        [
            "--market-type-summary",
            str(summary_path),
            "--output-dir",
            str(tmp_path / "matrix"),
            "--min-factor-trades",
            "1",
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert stdout["schema"] == "attbacktrader.strategy_adaptation_matrix.v1"
    assert stdout["trade_count"] == 3
    assert (tmp_path / "matrix" / "strategy_adaptation_matrix.json").exists()
    assert (tmp_path / "matrix" / "strategy_adaptation_matrix.zh.md").exists()


def test_strategy_adaptation_drilldown_expands_matrix_factor_to_review_samples(
    tmp_path: Path,
    capsys,
) -> None:
    summary_path = _write_market_type_summary(tmp_path)
    _run_dir(
        tmp_path,
        "bull-a",
        [
            _trade(1, "000001.SZ", "win", "2020-01-02", "2020-01-10", 0.10, ma25=True, hs300=True),
            _trade(2, "000002.SZ", "loss", "2020-01-03", "2020-01-11", -0.03, ma25=False, hs300=True),
        ],
        sold_too_early_by_key={
            ("000001.SZ", "2020-01-02", "2020-01-10", "KDJ_J_ABOVE_100"): True,
            ("000002.SZ", "2020-01-03", "2020-01-11", "STOP_LOSS"): False,
        },
    )
    _run_dir(
        tmp_path,
        "bull-b",
        [
            _trade(1, "000003.SZ", "win", "2020-02-02", "2020-02-10", 0.08, ma25=True, hs300=True),
            _trade(2, "000004.SZ", "win", "2020-02-03", "2020-02-11", 0.04, ma25=True, hs300=True),
        ],
        sold_too_early_by_key={
            ("000003.SZ", "2020-02-02", "2020-02-10", "KDJ_J_ABOVE_100"): True,
            ("000004.SZ", "2020-02-03", "2020-02-11", "KDJ_J_ABOVE_100"): False,
        },
    )
    _run_dir(
        tmp_path,
        "bear-a",
        [_trade(1, "000005.SZ", "loss", "2021-01-02", "2021-01-10", -0.07, ma25=False, hs300=False)],
        sold_too_early_by_key={
            ("000005.SZ", "2021-01-02", "2021-01-10", "STOP_LOSS"): False,
        },
    )
    matrix = build_strategy_adaptation_matrix(summary_path, min_factor_trades=1, top_factors=5)
    matrix_path, _ = write_strategy_adaptation_matrix(matrix, output_dir=tmp_path / "matrix")

    drilldown = build_strategy_adaptation_drilldown(
        matrix_path,
        market_type_id="bull_market",
        section="winning_entry_factors",
        factor_key="entry.check.symbol.ma.price_above_ma25",
        factor_value="true",
        limit=2,
    )
    markdown = render_strategy_adaptation_drilldown_markdown_zh(drilldown)
    json_path, markdown_path = write_strategy_adaptation_drilldown(drilldown, output_dir=tmp_path / "drilldown")
    cli_exit = strategy_adaptation_drilldown_cli.main(
        [
            "--matrix",
            str(matrix_path),
            "--market-type-id",
            "bull_market",
            "--section",
            "winning_entry_factors",
            "--factor-key",
            "entry.check.symbol.ma.price_above_ma25",
            "--factor-value",
            "true",
            "--limit",
            "1",
            "--output-dir",
            str(tmp_path / "cli-drilldown"),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert drilldown["schema"] == "attbacktrader.strategy_adaptation_drilldown.v1"
    assert drilldown["sample_count"] == 2
    assert drilldown["sample_packets"][0]["schema"] == "attbacktrader.review_sample.v1"
    assert drilldown["sample_packets"][0]["sample_id"] == "trade.1"
    assert drilldown["sample_summaries"][0]["sample_ref"]["run_id"] == "bull-a"
    assert "策略适配矩阵下钻" in markdown
    assert json_path.exists()
    assert markdown_path.exists()
    assert cli_exit == 0
    assert stdout["sample_count"] == 1
    assert (tmp_path / "cli-drilldown" / "strategy_adaptation_drilldown.json").exists()


def test_strategy_variant_drafts_from_matrix_write_manifest_and_yaml(tmp_path: Path, capsys) -> None:
    summary_path = _write_market_type_summary(tmp_path)
    for run_id, outcome, return_pct in (
        ("bull-a", "win", 0.10),
        ("bull-b", "win", 0.08),
        ("bear-a", "loss", -0.07),
    ):
        _run_dir(
            tmp_path,
            run_id,
            [_trade(1, "000001.SZ", outcome, "2020-01-02", "2020-01-10", return_pct, ma25=True, hs300=True)],
            sold_too_early_by_key={
                (
                    "000001.SZ",
                    "2020-01-02",
                    "2020-01-10",
                    "KDJ_J_ABOVE_100" if outcome == "win" else "STOP_LOSS",
                ): outcome == "win",
            },
        )
    matrix = build_strategy_adaptation_matrix(summary_path, min_factor_trades=1, top_factors=5)
    matrix_path, _ = write_strategy_adaptation_matrix(matrix, output_dir=tmp_path / "matrix")
    base_config = tmp_path / "base.yaml"
    base_config.write_text("run:\n  id: base-run\n", encoding="utf-8")

    drafts = build_strategy_variant_drafts(matrix_path, base_config_path=base_config, top_factor_refs=2)
    markdown = render_strategy_variant_drafts_markdown_zh(drafts)
    json_path, markdown_path, yaml_paths = write_strategy_variant_drafts(drafts, output_dir=tmp_path / "drafts")
    cli_exit = strategy_variant_drafts_cli.main(
        [
            "--matrix",
            str(matrix_path),
            "--base-config",
            str(base_config),
            "--output-dir",
            str(tmp_path / "cli-drafts"),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert drafts["schema"] == "attbacktrader.strategy_variant_drafts.v1"
    assert drafts["draft_count"] == 2
    bull = next(draft for draft in drafts["drafts"] if draft["market_type_id"] == "bull_market")
    bear = next(draft for draft in drafts["drafts"] if draft["market_type_id"] == "bear_market")
    assert bull["run_plan_patch"]["strategy"]["profit_taking_method"] == "ma_macd_weakening_exit"
    assert bear["run_plan_patch"]["strategy"]["sizing_params"]["max_total_exposure_percent"] == 0.3
    assert "策略变体验证草案" in markdown
    assert json_path.exists()
    assert markdown_path.exists()
    assert len(yaml_paths) == 2
    assert cli_exit == 0
    assert stdout["draft_count"] == 2
    assert (tmp_path / "cli-drafts" / "strategy_variant_drafts.zh.md").exists()


def test_strategy_variant_run_manifest_writes_legal_segment_run_plans(tmp_path: Path, capsys) -> None:
    summary_path = _write_market_type_summary(tmp_path)
    for run_id, outcome, return_pct in (
        ("bull-a", "win", 0.10),
        ("bull-b", "win", 0.08),
        ("bear-a", "loss", -0.07),
    ):
        _run_dir(
            tmp_path,
            run_id,
            [_trade(1, "000001.SZ", outcome, "2020-01-02", "2020-01-10", return_pct, ma25=True, hs300=True)],
            sold_too_early_by_key={
                (
                    "000001.SZ",
                    "2020-01-02",
                    "2020-01-10",
                    "KDJ_J_ABOVE_100" if outcome == "win" else "STOP_LOSS",
                ): outcome == "win",
            },
        )
    matrix = build_strategy_adaptation_matrix(summary_path, min_factor_trades=1, top_factors=5)
    matrix_path, _ = write_strategy_adaptation_matrix(matrix, output_dir=tmp_path / "matrix")
    base_config = tmp_path / "base.yaml"
    base_config.write_text((Path.cwd() / "examples" / "run.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    drafts = build_strategy_variant_drafts(matrix_path, base_config_path=base_config, top_factor_refs=2)
    drafts_path, _, _ = write_strategy_variant_drafts(drafts, output_dir=tmp_path / "drafts")
    manifest_path = _write_variant_segment_manifest(tmp_path, base_config)

    manifest = build_strategy_variant_run_manifest(drafts_path, manifest_path, reuse_snapshots=True)
    markdown = render_strategy_variant_run_manifest_markdown_zh(manifest)
    json_path, markdown_path, yaml_paths = write_strategy_variant_run_manifest(manifest, output_dir=tmp_path / "runs")
    cli_exit = strategy_variant_runs_cli.main(
        [
            "--drafts",
            str(drafts_path),
            "--market-segment-manifest",
            str(manifest_path),
            "--output-dir",
            str(tmp_path / "cli-runs"),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert manifest["schema"] == "attbacktrader.strategy_variant_run_manifest.v1"
    assert manifest["generated_count"] == 2
    assert manifest["segments"][0]["omitted_patch_keys"] == ["review_candidate"]
    assert manifest["segments"][0]["run_plan"]["data"]["refresh_snapshots"] is False
    assert "review_candidate" not in manifest["segments"][0]["run_plan"]
    assert "策略变体 RunPlan Manifest" in markdown
    assert json_path.exists()
    assert markdown_path.exists()
    assert len(yaml_paths) == 2
    generated_plans = [json.loads(json.dumps(segment["run_plan"])) for segment in manifest["segments"]]
    for generated in generated_plans:
        RunPlan.from_mapping(generated)
    no_add_on_plans = [
        plan
        for plan in generated_plans
        if plan["strategy"].get("add_on_method") == "none"
    ]
    assert no_add_on_plans
    assert all(plan["strategy"]["add_on_params"] == {} for plan in no_add_on_plans)
    assert cli_exit == 0
    assert stdout["generated_count"] == 2
    assert (tmp_path / "cli-runs" / "strategy_variant_run_manifest.json").exists()


def _write_market_type_summary(root: Path) -> Path:
    payload = {
        "schema": "attbacktrader.market_type_summary.v1",
        "base_run_id": "matrix-test",
        "market_types": [
            {
                "market_type_id": "bull_market",
                "market_type_label_zh": "牛市",
                "segment_count": 2,
                "total_trade_count": 4,
                "average_return_pct": 0.12,
                "average_max_drawdown": 0.03,
                "weighted_win_rate": 0.75,
                "profitable_segment_count": 2,
                "loss_segment_count": 0,
                "low_sample_segment_count": 0,
            },
            {
                "market_type_id": "bear_market",
                "market_type_label_zh": "熊市",
                "segment_count": 1,
                "total_trade_count": 2,
                "average_return_pct": -0.10,
                "average_max_drawdown": 0.15,
                "weighted_win_rate": 0.0,
                "profitable_segment_count": 0,
                "loss_segment_count": 1,
                "low_sample_segment_count": 0,
            },
        ],
        "segments": [
            _segment("bull-a", "bull_market", "牛市", root / "bull-a"),
            _segment("bull-b", "bull_market", "牛市", root / "bull-b"),
            _segment("bear-a", "bear_market", "熊市", root / "bear-a"),
        ],
    }
    path = root / "market_type_summary.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _segment(run_id: str, market_type_id: str, market_type_label_zh: str, report_dir: Path) -> dict:
    return {
        "segment_id": run_id,
        "segment_label_zh": run_id,
        "market_type_id": market_type_id,
        "market_type_label_zh": market_type_label_zh,
        "from_date": "2020-01-01",
        "to_date": "2020-12-31",
        "run_id": run_id,
        "report_dir": str(report_dir),
        "cumulative_return": 0.05,
        "max_drawdown": 0.03,
    }


def _write_variant_segment_manifest(root: Path, base_config: Path) -> Path:
    manifest = {
        "schema": "attbacktrader.market_segment_run_manifest.v1",
        "base_run_id": "variant-base",
        "market_types": [
            {"market_type_id": "bull_market", "label_zh": "牛市"},
            {"market_type_id": "bear_market", "label_zh": "熊市"},
        ],
        "segments": [
            {
                "segment_id": "bull-a",
                "label_zh": "牛市 A",
                "market_type_id": "bull_market",
                "market_type_label_zh": "牛市",
                "from_date": "2020-01-01",
                "to_date": "2020-06-30",
                "run_id": "bull-a",
                "run_plan_path": str(base_config),
            },
            {
                "segment_id": "bear-a",
                "label_zh": "熊市 A",
                "market_type_id": "bear_market",
                "market_type_label_zh": "熊市",
                "from_date": "2020-07-01",
                "to_date": "2020-12-31",
                "run_id": "bear-a",
                "run_plan_path": str(base_config),
            },
        ],
    }
    path = root / "market_segment_run_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _run_dir(
    root: Path,
    run_id: str,
    trades: list[dict],
    *,
    sold_too_early_by_key: dict[tuple[str, str, str, str], bool],
) -> None:
    path = root / run_id
    path.mkdir()
    _write_json(
        path / "run_plan.json",
        {
            "run": {"id": run_id, "from_date": "2020-01-01", "to_date": "2020-12-31"},
            "execution": {"engine": "business"},
        },
    )
    _write_json(
        path / "report.json",
        {
            "returns": {"final_equity": 1000000.0, "cumulative_return": 0.01},
            "risk": {"max_drawdown": 0.03},
            "trade_quality": {"trade_count": len(trades), "win_rate": 0.5},
        },
    )
    _write_json(path / "trade_lifecycle.json", {"trade_count": len(trades), "indexes": {}, "lifecycles": trades})
    observations = []
    for index, (key, sold_too_early) in enumerate(reversed(tuple(sold_too_early_by_key.items())), start=99):
        symbol, entry_date, exit_date, exit_reason = key
        observations.append(
            {
                "trade_index": index,
                "symbol": symbol,
                "outcome": "win" if sold_too_early else "loss",
                "entry_date": entry_date,
                "exit_date": exit_date,
                "exit_reason": exit_reason,
                "sold_too_early": sold_too_early,
                "max_high_return_pct": 0.06 if sold_too_early else 0.0,
                "primary_window_close_return_pct": 0.01 if sold_too_early else -0.01,
            }
        )
    _write_json(path / "post_exit_analysis.json", {"window_days": 5, "observations": observations})
    _write_json(path / "evidence_validation.json", {"status": "ok"})
    _write_json(
        path / "trade_review.json",
        {
            "trade_count": len(trades),
            "sold_too_early_count": sum(1 for item in observations if item["sold_too_early"]),
            "opportunity_count": 0,
            "add_on_entry_count": 0,
            "trades": [_review_trade(trade, observations) for trade in trades],
            "opportunities": [],
            "add_on_entry_points": [],
        },
    )
    _write_json(
        path / "trades.json",
        {
            "closed_trades": [
                {
                    "symbol": trade["symbol"],
                    "entry_date": trade["entry_date"],
                    "exit_date": trade["exit_date"],
                    "entry_price": trade["entry_price"],
                    "exit_price": trade["exit_price"],
                    "exit_reason": trade["exit_reason"],
                    "return_pct": trade["return_pct"],
                }
                for trade in trades
            ],
            "open_positions": [],
        },
    )
    _write_json(path / "signal_audit.json", [])
    _write_json(path / "execution_audit.json", [])


def _review_trade(trade: dict, observations: list[dict]) -> dict:
    post_exit = next(
        (
            item
            for item in observations
            if item["symbol"] == trade["symbol"]
            and item["entry_date"] == trade["entry_date"]
            and item["exit_date"] == trade["exit_date"]
        ),
        {},
    )
    entry_event = next(event for event in trade["events"] if event["event_type"] == "entry")
    return {
        "trade_index": trade["trade_index"],
        "symbol": trade["symbol"],
        "outcome": trade["outcome"],
        "entry_date": trade["entry_date"],
        "exit_date": trade["exit_date"],
        "exit_reason": trade["exit_reason"],
        "return_pct": trade["return_pct"],
        "entry_method_name": entry_event["method_name"],
        "exit_method_name": "kdj_overheated_exit",
        "add_on_count": 0,
        "sold_too_early": post_exit.get("sold_too_early"),
        "max_high_return_pct": post_exit.get("max_high_return_pct"),
        "entry_checks": entry_event["checks"],
        "exit_checks": {},
        "add_on_checks": {},
    }


def _trade(
    trade_index: int,
    symbol: str,
    outcome: str,
    entry_date: str,
    exit_date: str,
    return_pct: float,
    *,
    ma25: bool,
    hs300: bool,
) -> dict:
    exit_reason = "KDJ_J_ABOVE_100" if outcome == "win" else "STOP_LOSS"
    return {
        "trade_index": trade_index,
        "symbol": symbol,
        "outcome": outcome,
        "entry_date": entry_date,
        "exit_date": exit_date,
        "exit_reason": exit_reason,
        "entry_price": 10.0,
        "exit_price": 10.0 * (1.0 + return_pct),
        "return_pct": return_pct,
        "events": [
            {
                "event_type": "entry",
                "trade_date": entry_date,
                "intent_type": "enter",
                "method_name": "kdj_oversold_entry",
                "reason_code": "KDJ_J_BELOW_13",
                "checks": {
                    "kdj_j_below_threshold": True,
                    "symbol.ma.price_above_ma25": ma25,
                    "market.hs300.bullish_trend": hs300,
                },
                "values": {
                    "symbol.close": 10.0,
                    "symbol.ma.ma25": 9.8 if ma25 else 10.2,
                    "market.hs300.close": 4000.0,
                },
                "categories": {
                    "industry.sw_l1.code": "801010.SI",
                },
                "sizing_context": {},
                "executions": [],
            },
            {
                "event_type": "exit",
                "trade_date": exit_date,
                "intent_type": "exit_profit" if outcome == "win" else "exit_loss",
                "method_name": "kdj_overheated_exit" if outcome == "win" else "atr_stop_loss",
                "reason_code": exit_reason,
                "checks": {},
                "values": {},
                "categories": {},
                "sizing_context": {},
                "executions": [],
            },
        ],
    }


def _factor(market_type: dict, key: str, value: str) -> dict:
    return next(
        item
        for item in market_type["entry_factor_summaries"]
        if item["factor_key"] == key and item["factor_value"] == value
    )


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
