import json
from pathlib import Path

from attbacktrader.reports import (
    build_attribution_summary,
    render_attribution_summary_markdown_zh,
    write_attribution_summary,
)


def test_attribution_summary_builds_ai_readable_cards(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "trade_attribution.json",
        {
            "schema": "attbacktrader.trade_attribution.v1",
            "trade_count": 2,
            "entry_event_count": 2,
            "add_on_event_count": 1,
            "exit_event_count": 2,
            "attributions": [
                {
                    "trade_index": 1,
                    "symbol": "000001.SZ",
                    "outcome": "win",
                    "entry_date": "2024-01-02",
                    "exit_date": "2024-01-10",
                    "exit_reason": "BAOMA_MA25_PROFIT_EXIT_TRIGGERED",
                    "return_pct": 0.12,
                },
                {
                    "trade_index": 2,
                    "symbol": "000002.SZ",
                    "outcome": "loss",
                    "entry_date": "2024-01-03",
                    "exit_date": "2024-01-11",
                    "exit_reason": "BAOMA_MA60_STOP_TRIGGERED",
                    "return_pct": -0.04,
                },
            ],
        },
    )
    _write_json(
        tmp_path / "attribution_matrix.json",
        {
            "schema": "attbacktrader.attribution_matrix.v1",
            "run_id": "summary-test",
            "source_dir": str(tmp_path),
            "matrices": [
                _matrix(
                    "entry_kdj_stack",
                    "入场 个股 KDJ J x 行业 KDJ J x 沪深300 KDJ J",
                    [
                        _row({"symbol_kdj_j": ">=80", "industry_kdj_j": ">=80"}, 10, 0.7, 0.20, 0.2),
                        _row({"symbol_kdj_j": "13-30", "industry_kdj_j": "50-80"}, 8, 0.2, -0.03, 0.8),
                    ],
                ),
                _matrix(
                    "add_on_industry_relative_strength",
                    "加仓 行业相对沪深300强弱 x DEA 上水天数",
                    [_row({"industry_relative_strength": "strong_outperform", "dea_age": "3-5"}, 6, 0.8, 0.18, 0.2)],
                ),
                _matrix(
                    "entry_industry_trend_market_kdj",
                    "入场 行业趋势 x 沪深300 KDJ J",
                    [_row({"industry_trend_state": "bullish", "market_hs300_kdj_j": "50-80"}, 9, 0.66, 0.16, 0.3)],
                ),
                _matrix(
                    "entry_industry_relative_strength",
                    "入场 行业相对沪深300强弱 x 个股 KDJ J",
                    [_row({"industry_relative_strength": "weak_underperform", "symbol_kdj_j": ">=80"}, 7, 0.14, -0.06, 0.7)],
                ),
                _matrix(
                    "stop_loss_entry_timing",
                    "止损交易的入场 DEA 上水天数 x 个股 KDJ J",
                    [_row({"dea_age": "0-2", "symbol_kdj_j": ">=80"}, 7, 0.0, -0.07, 1.0)],
                ),
                _matrix(
                    "profit_exit_kdj_post_5d",
                    "止盈退出 KDJ J x 卖出后 5 天表现",
                    [_row({"symbol_kdj_j": "<13"}, 5, 1.0, 0.3, 0.0, rebound_5=0.4, rebound_10=0.2)],
                ),
            ],
        },
    )
    _write_json(
        tmp_path / "post_exit_analysis.json",
        {
            "threshold_summaries": [
                _threshold("take_profit", 0.02, 10, 0.6),
                _threshold("take_profit", 0.05, 10, 0.4),
                _threshold("take_profit", 0.10, 10, 0.2),
            ]
        },
    )

    report = build_attribution_summary(tmp_path, top_n=3)
    markdown = render_attribution_summary_markdown_zh(report)
    json_path, markdown_path = write_attribution_summary(report)

    assert report["schema"] == "attbacktrader.attribution_summary.v1"
    assert report["overview"]["trade_count"] == 2
    assert report["industry_attribution"]["section_count"] == 4
    assert report["summary_cards"][0]["card_id"] == "entry_environment"
    assert report["summary_cards"][0]["rows"][0]["dimensions"]["symbol_kdj_j"] == ">=80"
    assert "归因总览报告" in markdown
    assert "行业归因专章" in markdown
    assert "行业 MA 趋势" in markdown
    assert "重点结论卡片" in markdown
    assert json_path.exists()
    assert markdown_path.exists()


def _matrix(matrix_id: str, title: str, rows: list[dict]) -> dict:
    return {
        "matrix_id": matrix_id,
        "title": title,
        "rows": rows,
    }


def _row(
    dimensions: dict,
    sample_count: int,
    win_rate: float,
    average_return_pct: float,
    stop_loss_rate: float,
    *,
    rebound_5: float | None = None,
    rebound_10: float | None = None,
) -> dict:
    return {
        "dimensions": dimensions,
        "sample_count": sample_count,
        "win_rate": win_rate,
        "average_return_pct": average_return_pct,
        "average_win_pct": 0.25,
        "average_loss_pct": -0.05,
        "stop_loss_rate": stop_loss_rate,
        "average_max_high_return_pct_5d": 0.04,
        "post_exit_rebound_rate_5pct": rebound_5,
        "post_exit_rebound_rate_10pct": rebound_10,
        "trade_indexes": [1, 2],
    }


def _threshold(group: str, threshold: float, sample_count: int, rebound_rate: float) -> dict:
    return {
        "threshold": threshold,
        "group": group,
        "sample_count": sample_count,
        "rebound_rate": rebound_rate,
        "average_max_high_return_pct": 0.05,
    }


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
