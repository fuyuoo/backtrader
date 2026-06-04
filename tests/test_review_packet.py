import json
from pathlib import Path

from attbacktrader.cli import review_packet as review_packet_cli
from attbacktrader.reports import build_review_packet, render_review_packet_markdown_zh, write_review_packet


def test_build_review_packet_keeps_ai_contract_and_add_on_samples(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)

    packet = build_review_packet(run_dir, focus="add_on", top=5)
    markdown = render_review_packet_markdown_zh(packet)
    json_path, markdown_path = write_review_packet(packet, output_dir=tmp_path / "packet")

    assert packet["schema"] == "attbacktrader.review_packet.v1"
    assert packet["run_id"] == "packet-run"
    assert packet["focus"] == "add_on"
    assert packet["ai_contract"]["rules"][2].startswith("缺失字段保持缺失")
    assert packet["overview"]["evidence_validation"]["status"] == "ok"
    assert packet["source_artifacts"]["environment_fit"]["exists"] is True
    assert packet["sections"][0]["name"] == "add_on"
    assert packet["sections"][0]["samples"][0]["sample_index"] == 1
    assert packet["sections"][0]["samples"][0]["trade_index"] == 7
    assert packet["sections"][0]["samples"][0]["follow_up"]["max_high_return_pct"] == 0.08
    assert "AI 复盘包" in markdown
    assert "加仓入场点" in markdown
    assert "sample_index" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def test_review_packet_includes_environment_fit_for_ai_review(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)

    packet = build_review_packet(run_dir, focus="environment_fit", top=3)
    markdown = render_review_packet_markdown_zh(packet)

    assert packet["focus"] == "environment_fit"
    assert packet["overview"]["environment_fit"]["best_by_net_pnl"]["label_zh"] == "行业 KDJ J 低于阈值=是"
    assert packet["sections"][0]["name"] == "environment_fit"
    assert packet["sections"][0]["context"]["sample_warnings"]["low_sample_combination_count"] == 1
    assert packet["sections"][0]["samples"][0]["trade_index"] == 7
    assert "环境适配与利润贡献" in markdown


def test_review_packet_cli_writes_focused_opportunity_packet(tmp_path: Path, capsys) -> None:
    run_dir = _run_dir(tmp_path)
    output_dir = tmp_path / "out"

    exit_code = review_packet_cli.main(
        [
            "--run-dir",
            str(run_dir),
            "--focus",
            "opportunity_cost",
            "--top",
            "1",
            "--output-dir",
            str(output_dir),
        ]
    )
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    packet_path = output_dir / "review_packet.opportunity_cost.json"
    markdown_path = output_dir / "review_packet.opportunity_cost.zh.md"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["focus"] == "opportunity_cost"
    assert payload["artifacts"]["review_packet_json_path"] == str(packet_path)
    assert packet["sections"][0]["samples"][0]["sample_index"] == 2
    assert markdown_path.exists()


def _run_dir(root: Path) -> Path:
    path = root / "packet-run"
    path.mkdir()
    _write_json(
        path / "run_plan.json",
        {
            "run": {"id": "packet-run", "from_date": "2024-01-01", "to_date": "2024-03-31"},
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
            "counts": {
                "symbol_count": 1,
                "closed_trade_count": 1,
                "trade_review_add_on_entry_count": 1,
            },
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
        },
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
                    "average_trade_return_pct": 0.12,
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
                    "review_flags": ["sold_too_early"],
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
                    "checks": {"symbol.ma.bullish_trend": False},
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
                    "checks": {"symbol.ma.bullish_trend": True},
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
                    "categories": {"market.hs300.trend_state": "bullish"},
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
            "run_id": "packet-run",
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
                "low_sample_candidates": [
                    {
                        "summary_kind": "combination",
                        "label_zh": "行业 KDJ J 低于阈值=是；沪深300多头趋势=否",
                        "sample_count": 1,
                        "win_rate": 1.0,
                        "average_return_pct": 0.12,
                        "net_pnl": 1180.0,
                        "return_on_entry_value": 0.118,
                    }
                ],
            },
            "single_factor_summaries": [
                {
                    "summary_kind": "single_factor",
                    "field": "industry.kdj.j_below_threshold",
                    "field_label_zh": "行业 KDJ J 低于阈值",
                    "value": True,
                    "value_label_zh": "是",
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


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
