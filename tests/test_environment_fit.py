import json
from pathlib import Path

import pytest

from attbacktrader.cli import environment_fit as environment_fit_cli
from attbacktrader.reports import (
    build_environment_fit_report_from_artifacts,
    build_environment_fit_report_from_run_dir,
    render_environment_fit_markdown_zh,
    write_environment_fit_report,
)


def test_environment_fit_summarizes_environment_and_profit_contribution() -> None:
    report = build_environment_fit_report_from_artifacts(
        run_id="environment-fit-test",
        source_dir="reports/environment-fit-test",
        trade_review=_trade_review(),
        trade_lifecycle=_trade_lifecycle(),
        min_sample_count=2,
    )
    markdown = render_environment_fit_markdown_zh(report)

    assert report["schema"] == "attbacktrader.environment_fit.v1"
    assert report["trade_count"] == 3
    assert report["contribution_available_count"] == 3
    assert report["overall"]["net_pnl"] == pytest.approx(35.4)
    assert report["overall"]["return_on_entry_value"] == pytest.approx(35.4 / 3000.0)

    industry_true = next(
        summary
        for summary in report["single_factor_summaries"]
        if summary["field"] == "industry.kdj.j_below_threshold" and summary["value"] is True
    )
    assert industry_true["sample_count"] == 2
    assert industry_true["win_rate"] == pytest.approx(0.5)
    assert industry_true["net_pnl"] == pytest.approx(35.8)
    assert industry_true["return_on_entry_value"] == pytest.approx(35.8 / 2000.0)

    combo = next(
        summary
        for summary in report["combination_summaries"]
        if summary["fields"]["industry.kdj.j_below_threshold"] is True
        and summary["fields"]["market.hs300.bullish_trend"] is False
    )
    assert combo["sample_count"] == 2
    assert combo["take_profit_count"] == 1
    assert combo["stop_loss_count"] == 1
    assert report["best_environments"]["best_by_net_pnl"]["sample_count"] == 2
    assert report["sample_warnings"]["low_sample_combination_count"] == 1

    assert "# 策略环境适配与利润贡献" in markdown
    assert "## 结论摘要" in markdown
    assert "## 样本不足警告" in markdown
    assert "## 单因子环境表现" in markdown
    assert "## 组合环境表现" in markdown
    assert "## 交易利润贡献明细" in markdown
    assert "行业 KDJ J 低于阈值" in markdown


def test_environment_fit_run_dir_writer_and_cli(tmp_path: Path, capsys) -> None:
    run_dir = tmp_path / "environment-fit-test"
    run_dir.mkdir()
    _write_json(run_dir / "run_plan.json", {"run": {"id": "environment-fit-test"}})
    _write_json(run_dir / "trade_review.json", _trade_review())
    _write_json(run_dir / "trade_lifecycle.json", _trade_lifecycle())

    report = build_environment_fit_report_from_run_dir(run_dir, min_sample_count=1)
    json_path, markdown_path = write_environment_fit_report(report, output_dir=tmp_path / "out")
    exit_code = environment_fit_cli.main(
        [
            "--run-dir",
            str(run_dir),
            "--min-sample-count",
            "1",
            "--output-dir",
            str(tmp_path / "cli-out"),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert report["run_id"] == "environment-fit-test"
    assert json_path.exists()
    assert markdown_path.exists()
    assert exit_code == 0
    assert stdout["schema"] == "attbacktrader.environment_fit.v1"
    assert stdout["trade_count"] == 3
    assert (tmp_path / "cli-out" / "environment_fit.json").exists()
    assert (tmp_path / "cli-out" / "environment_fit.zh.md").exists()


def _trade_review() -> dict:
    return {
        "trade_count": 3,
        "trades": [
            {
                "trade_index": 1,
                "symbol": "000001.SZ",
                "outcome": "loss",
                "entry_date": "2024-01-02",
                "exit_date": "2024-01-05",
                "exit_reason": "FIXED_5_PERCENT_STOP",
                "return_pct": -0.06,
                "entry_checks": {
                    "industry.kdj.j_below_threshold": True,
                    "market.hs300.bullish_trend": False,
                    "symbol.ma.bullish_trend": False,
                    "symbol.ma.price_above_ma25": False,
                    "symbol.ma.price_above_ma60": False,
                },
            },
            {
                "trade_index": 2,
                "symbol": "600519.SH",
                "outcome": "win",
                "entry_date": "2024-01-03",
                "exit_date": "2024-01-08",
                "exit_reason": "KDJ_J_ABOVE_100",
                "return_pct": 0.10,
                "entry_checks": {
                    "industry.kdj.j_below_threshold": True,
                    "market.hs300.bullish_trend": False,
                    "symbol.ma.bullish_trend": False,
                    "symbol.ma.price_above_ma25": False,
                    "symbol.ma.price_above_ma60": False,
                },
            },
            {
                "trade_index": 3,
                "symbol": "000333.SZ",
                "outcome": "loss",
                "entry_date": "2024-01-04",
                "exit_date": "2024-01-09",
                "exit_reason": "FIXED_5_PERCENT_STOP",
                "return_pct": -0.005,
                "entry_checks": {
                    "industry.kdj.j_below_threshold": False,
                    "market.hs300.bullish_trend": True,
                    "symbol.ma.bullish_trend": True,
                    "symbol.ma.price_above_ma25": True,
                    "symbol.ma.price_above_ma60": True,
                },
            },
        ],
    }


def _trade_lifecycle() -> dict:
    return {
        "trade_count": 3,
        "lifecycles": [
            _lifecycle(
                1,
                symbol="000001.SZ",
                entry_date="2024-01-02",
                exit_date="2024-01-05",
                buy_price=10.0,
                sell_price=9.4,
                commission=1.0,
            ),
            _lifecycle(
                2,
                symbol="600519.SH",
                entry_date="2024-01-03",
                exit_date="2024-01-08",
                buy_price=10.0,
                sell_price=10.98,
                commission=0.1,
            ),
            _lifecycle(
                3,
                symbol="000333.SZ",
                entry_date="2024-01-04",
                exit_date="2024-01-09",
                buy_price=10.0,
                sell_price=10.0,
                commission=0.2,
            ),
        ],
    }


def _lifecycle(
    trade_index: int,
    *,
    symbol: str,
    entry_date: str,
    exit_date: str,
    buy_price: float,
    sell_price: float,
    commission: float,
) -> dict:
    quantity = 100.0
    return {
        "trade_index": trade_index,
        "symbol": symbol,
        "entry_date": entry_date,
        "exit_date": exit_date,
        "events": [
            {
                "event_type": "entry",
                "trade_date": entry_date,
                "executions": [
                    {
                        "event_date": entry_date,
                        "signal_date": entry_date,
                        "side": "buy",
                        "event_type": "completed",
                        "status": "Completed",
                        "reason_code": "KDJ_J_BELOW_13",
                        "executed_quantity": quantity,
                        "executed_price": buy_price,
                        "commission": commission,
                        "gross_value": quantity * buy_price,
                    }
                ],
            },
            {
                "event_type": "exit",
                "trade_date": exit_date,
                "executions": [
                    {
                        "event_date": exit_date,
                        "signal_date": exit_date,
                        "side": "sell",
                        "event_type": "completed",
                        "status": "Completed",
                        "reason_code": "EXIT",
                        "executed_quantity": quantity,
                        "executed_price": sell_price,
                        "commission": commission,
                        "gross_value": quantity * sell_price,
                    }
                ],
            },
        ],
    }


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
