from datetime import date
from types import SimpleNamespace

from attbacktrader.reports import (
    BacktestReport,
    BenchmarkComparisonSummary,
    ExecutionCostSummary,
    ExecutionRejectionSummary,
    IndustryAttributionSummary,
    MarketRegimeSummary,
    PortfolioBehaviorSummary,
    ReturnSummary,
    RiskSummary,
    ScenarioFitSummary,
    SymbolContributionSummary,
    TradeQualitySummary,
    render_backtest_report_markdown_zh,
)
from attbacktrader.strategies import TradeIntent, TradeIntentType
from attbacktrader.strategies.attribution import entry_attribution_payload
from attbacktrader.strategies.templates import ClosedTrade


def test_render_backtest_report_markdown_zh_covers_standard_sections() -> None:
    report = BacktestReport(
        report_id="zh-report",
        returns=ReturnSummary(
            starting_equity=1000000.0,
            final_equity=1000836.17205757,
            cumulative_return=0.0008361720575700282,
        ),
        risk=RiskSummary(max_drawdown=0.011115472704109968),
        trade_quality=TradeQualitySummary(
            trade_count=3,
            win_count=2,
            loss_count=1,
            win_rate=2.0 / 3.0,
            average_win=0.051010670803451785,
            average_loss=-0.05606723301021721,
            profit_loss_ratio=0.9098125244410766,
        ),
        benchmark_comparison=(
            BenchmarkComparisonSummary(
                benchmark_symbol="000001.SH",
                strategy_return=0.0008361720575700282,
                benchmark_return=0.026631784031482475,
                excess_return=-0.025795611973912447,
            ),
        ),
        industry_attribution=(
            IndustryAttributionSummary(
                level=1,
                industry_code="801780.SI",
                industry_name="银行",
                trade_count=1,
                average_return=0.04347283470099916,
                contribution_return=0.04347283470099916,
            ),
        ),
        market_regime=MarketRegimeSummary(
            primary_label="input_only",
            windows=(),
            benchmark_symbols=("000001.SH", "000300.SH"),
            industry_index_symbols=("801780.SI", "801120.SI"),
            timeframes=("D", "W", "M"),
        ),
        scenario_fit=ScenarioFitSummary(
            label="conditional_fit",
            score=4,
            reasons=("positive cumulative return",),
            warnings=("profit/loss ratio below 1",),
        ),
        portfolio_behavior=PortfolioBehaviorSummary(
            open_position_count=1,
            open_symbols=("000001.SZ",),
            closed_symbol_count=2,
            max_symbol_trade_share=2.0 / 3.0,
            cash_ratio=0.8288011516932423,
            symbol_contributions=(
                SymbolContributionSummary(
                    symbol="000001.SZ",
                    trade_count=1,
                    cumulative_return=0.04347283470099916,
                    average_return=0.04347283470099916,
                ),
            ),
        ),
        execution_costs=ExecutionCostSummary(
            order_count=2,
            submitted_count=2,
            accepted_count=2,
            completed_count=1,
            failed_count=0,
            rejected_count=1,
            fill_rate=0.5,
            rejection_rate=0.5,
            total_commission=10.0,
            average_commission=5.0,
            total_slippage_cost=3.0,
            average_slippage_cost=1.5,
            rejections=(ExecutionRejectionSummary(blocked_by="BOARD_LOT_TOO_SMALL", count=1),),
        ),
    )
    run_plan = SimpleNamespace(
        run=SimpleNamespace(
            from_date=date(2024, 1, 1),
            to_date=date(2024, 3, 31),
        )
    )
    result = SimpleNamespace(
        report=report,
        engine="backtrader",
        adjustment="qfq",
        symbols=("000001.SZ", "600519.SH"),
        closed_trades=(
            ClosedTrade("000001.SZ", date(2024, 1, 2), date(2024, 1, 5), 10.0, 11.0, "TAKE_PROFIT"),
            ClosedTrade("000001.SZ", date(2024, 1, 8), date(2024, 1, 10), 10.0, 9.0, "STOP_LOSS"),
        ),
        signal_audit=(
            TradeIntent(
                TradeIntentType.ENTER,
                "000001.SZ",
                date(2024, 1, 2),
                "entry",
                "ENTRY",
                signal_values={
                    "attribution": entry_attribution_payload(
                        checks={"symbol.ma.price_above_ma25": True},
                        values={"symbol.ma.ma25": 9.5},
                    )
                },
            ),
            TradeIntent(
                TradeIntentType.EXIT_PROFIT,
                "000001.SZ",
                date(2024, 1, 5),
                "profit",
                "TAKE_PROFIT",
                signal_values={
                    "kdj_j": 101.0,
                    "checks": {
                        "kdj_j_above_threshold": True,
                        "current_price_at_or_below_stop": False,
                    },
                    "attribution": entry_attribution_payload(
                        checks={
                            "symbol.ma.price_above_ma25": True,
                            "market.hs300.bullish_trend": True,
                        },
                        values={"symbol.ma.ma25": 9.8},
                    ),
                },
            ),
            TradeIntent(
                TradeIntentType.ADD_ON,
                "000001.SZ",
                date(2024, 1, 3),
                "kdj_oversold_add_on",
                "KDJ_OVERSOLD_ADD_ON",
                signal_values={
                    "position_action": "add_on",
                    "attribution": entry_attribution_payload(
                        checks={"position.add_on_count_available": True},
                        values={"position.unrealized_return": 0.08},
                    ),
                    "sizing": {"requested_quantity": 100},
                },
            ),
            TradeIntent(
                TradeIntentType.ENTER,
                "000001.SZ",
                date(2024, 1, 8),
                "entry",
                "ENTRY",
                signal_values={
                    "attribution": entry_attribution_payload(
                        checks={"symbol.ma.price_above_ma25": False},
                        values={"symbol.ma.ma25": 10.5},
                    )
                },
            ),
            TradeIntent(
                TradeIntentType.ADD_ON,
                "000001.SZ",
                date(2024, 1, 9),
                "kdj_oversold_add_on",
                "KDJ_OVERSOLD_ADD_ON",
                signal_values={
                    "position_action": "add_on",
                    "attribution": entry_attribution_payload(
                        checks={"position.add_on_count_available": True},
                        values={"position.unrealized_return": -0.02},
                    ),
                    "sizing": {"requested_quantity": 100},
                },
            ),
            TradeIntent(
                TradeIntentType.EXIT_LOSS,
                "000001.SZ",
                date(2024, 1, 10),
                "stop",
                "STOP_LOSS",
                signal_values={
                    "current_price": 9.0,
                    "stop_price": 9.5,
                    "checks": {"current_price_at_or_below_stop": True},
                    "attribution": entry_attribution_payload(
                        checks={
                            "symbol.ma.price_above_ma25": False,
                            "market.hs300.bullish_trend": False,
                        },
                        values={"symbol.ma.ma25": 10.2},
                    ),
                },
            ),
        ),
        execution_audit=(),
        open_positions=(),
        final_cash=829494.17205757,
        final_value=1000836.17205757,
    )

    markdown = render_backtest_report_markdown_zh(run_plan, result)

    assert "# 回测报告：zh-report" in markdown
    assert "| 回测区间 | 2024-01-01 至 2024-03-31 |" in markdown
    assert "## 收益与风险" in markdown
    assert "## 交易质量" in markdown
    assert "## 组合行为" in markdown
    assert "## 结果诊断" in markdown
    assert "## 入场归因差异" in markdown
    assert "价格在 MA25 上方" in markdown
    assert "## 出场归因差异" in markdown
    assert "## 出场归因" in markdown
    assert "沪深300多头趋势" in markdown
    assert "## 加仓归因差异" in markdown
    assert "## 加仓归因" in markdown
    assert "## 加仓入场点明细" in markdown
    assert "| 000001.SZ | 盈利 | 2024-01-02 | 2024-01-03 | 2024-01-05 | 10.00% |" in markdown
    assert "position.unrealized_return=0.08" in markdown
    assert "当前价触及止损价" in markdown
    assert "## 执行成本" in markdown
    assert "不足一手 (BOARD_LOT_TOO_SMALL)" in markdown
    assert "## 基准对比" in markdown
    assert "## 行业归因" in markdown
    assert "## 市场温度输入" in markdown
    assert "| 周期 | D (日线), W (周线), M (月线) |" in markdown
    assert "| 基准指数 | 000001.SH, 000300.SH |" in markdown
    assert "| 行业指数 | 801780.SI, 801120.SI |" in markdown
    assert "- 标签：`conditional_fit` (有条件匹配)" in markdown
    assert "累计收益为正" in markdown
    assert "盈亏比低于 1" in markdown
