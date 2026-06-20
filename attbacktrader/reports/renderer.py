"""Markdown renderers for completed backtest reports."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import TYPE_CHECKING

from attbacktrader.reports.diagnostics import build_result_diagnostics
from attbacktrader.strategies.attribution import entry_attribution_declaration_by_key

if TYPE_CHECKING:
    from attbacktrader.config import RunPlan
    from attbacktrader.runners import RunPlanExecutionResult


_LABEL_ZH = {
    "hot": "偏热",
    "warm": "偏暖",
    "neutral": "中性",
    "cold": "偏冷",
    "insufficient_evidence": "证据不足",
    "fit": "匹配",
    "conditional_fit": "有条件匹配",
    "not_fit": "不匹配",
}

_TIMEFRAME_ZH = {
    "D": "日线",
    "W": "周线",
    "M": "月线",
}

_EVIDENCE_ZH = {
    "positive cumulative return": "累计收益为正",
    "non-positive cumulative return": "累计收益非正",
    "max drawdown within 12%": "最大回撤不超过 12%",
    "max drawdown above 12%": "最大回撤超过 12%",
    "win rate at least 50%": "胜率不低于 50%",
    "win rate below 50%": "胜率低于 50%",
    "profit/loss ratio at least 1": "盈亏比不低于 1",
    "profit/loss ratio below 1": "盈亏比低于 1",
    "profit/loss ratio unavailable": "盈亏比不可用",
    "positive average benchmark excess return": "平均基准超额收益为正",
    "average benchmark excess return is non-positive": "平均基准超额收益非正",
    "benchmark comparison unavailable": "基准对比不可用",
    "market regime unavailable": "市场温度不可用",
}

_BLOCK_REASON_ZH = {
    "ATR_RISK_UNAVAILABLE": "ATR 风险值不可用",
    "BOARD_LOT_TOO_SMALL": "不足一手",
    "CASH_NOT_ENOUGH": "现金不足",
    "LIMIT_DOWN_SELL_BLOCKED": "跌停卖出受限",
    "LIMIT_UP_BUY_BLOCKED": "涨停买入受限",
    "MAX_HOLDING_COUNT": "达到最大持仓数量",
    "REBALANCE_INTERVAL": "再平衡间隔不足",
    "SIZING_ZERO_QUANTITY": "仓位计算为 0",
    "SUSPENDED": "停牌",
    "T_PLUS_ONE_SELL_BLOCKED": "T+1 卖出受限",
}

_ENTRY_CHECK_ZH = {
    "bullish_crossover": "MACD 金叉",
    "atr_available": "ATR 可用",
    "bearish_crossover": "MACD 死叉",
    "current_price_at_or_below_stop": "当前价触及止损价",
    "fast_ma_above_slow_ma": "快线均线高于慢线均线",
    "fast_ma_below_slow_ma": "快线均线低于慢线均线",
    "kdj_j_below_threshold": "KDJ J 低于阈值",
    "kdj_j_above_threshold": "KDJ J 高于阈值",
    "macd_available": "MACD 可用",
    "macd_bearish_crossover": "MACD 死叉",
    "macd_histogram_positive": "MACD 柱为正",
    "macd_line_above_signal": "MACD 线高于信号线",
    "macd_line_below_signal": "MACD 线低于信号线",
    "ma_values_available": "均线可用",
    "previous_macd_available": "前一周期 MACD 可用",
    "price_above_fast_ma": "价格在快线均线上方",
    "price_below_fast_ma": "价格在快线均线下方",
    "required_values_available": "所需指标可用",
    "rsi_at_or_above_threshold": "RSI 达到阈值",
    "rsi_available": "RSI 可用",
}

_ENTRY_VALUE_ZH = {
    "close": "收盘价",
    "kdj_d": "KDJ D",
    "kdj_j": "KDJ J",
    "kdj_k": "KDJ K",
    "ma20": "MA20",
    "ma25": "MA25",
    "ma60": "MA60",
    "macd_histogram": "MACD 柱",
    "macd_line": "MACD 线",
    "macd_signal": "MACD 信号线",
    "threshold": "阈值",
    "current_price": "当前价",
    "entry_price": "入场价",
    "loss_percent": "止损比例",
    "multiple": "ATR 倍数",
    "period": "周期",
    "stop_price": "止损价",
}

_ATTRIBUTION_DECLARATIONS = entry_attribution_declaration_by_key()


def render_backtest_report_markdown(run_plan: "RunPlan", result: "RunPlanExecutionResult") -> str:
    report = result.report
    lines = [
        f"# Backtest Report: {report.report_id}",
        "",
        "## Run",
        "",
        "| Field | Value |",
        "|---|---:|",
        f"| Window | {run_plan.run.from_date} to {run_plan.run.to_date} |",
        f"| Engine | {result.engine} |",
        f"| Adjustment | {result.adjustment} |",
        f"| Symbols | {', '.join(result.symbols)} |",
        f"| Final cash | {_format_optional_number(result.final_cash)} |",
        f"| Final value | {_format_optional_number(result.final_value)} |",
        "",
        "## Returns",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Starting equity | {_format_number(report.returns.starting_equity)} |",
        f"| Final equity | {_format_number(report.returns.final_equity)} |",
        f"| Cumulative return | {_format_percent(report.returns.cumulative_return)} |",
        f"| Max drawdown | {_format_percent(report.risk.max_drawdown)} |",
        "",
        "## Trade Quality",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Trades | {report.trade_quality.trade_count} |",
        f"| Wins | {report.trade_quality.win_count} |",
        f"| Losses | {report.trade_quality.loss_count} |",
        f"| Win rate | {_format_optional_percent(report.trade_quality.win_rate)} |",
        f"| Average win | {_format_optional_percent(report.trade_quality.average_win)} |",
        f"| Average loss | {_format_optional_percent(report.trade_quality.average_loss)} |",
        f"| Profit/loss ratio | {_format_optional_number(report.trade_quality.profit_loss_ratio)} |",
        "",
    ]
    _extend_stock_pool_filter_section(lines, result, zh=False)

    if report.portfolio_behavior is not None:
        portfolio = report.portfolio_behavior
        lines.extend(
            [
                "## Portfolio Behavior",
                "",
                "| Metric | Value |",
                "|---|---:|",
                f"| Open positions | {portfolio.open_position_count} |",
                f"| Open symbols | {', '.join(portfolio.open_symbols) if portfolio.open_symbols else '-'} |",
                f"| Closed symbols | {portfolio.closed_symbol_count} |",
                f"| Max symbol trade share | {_format_optional_percent(portfolio.max_symbol_trade_share)} |",
                f"| Cash ratio | {_format_optional_percent(portfolio.cash_ratio)} |",
                "",
            ]
        )
        if portfolio.symbol_contributions:
            lines.extend(
                [
                    "| Symbol | Trades | Cumulative return | Average return |",
                    "|---|---:|---:|---:|",
                ]
            )
            for contribution in portfolio.symbol_contributions:
                lines.append(
                    "| "
                    f"{contribution.symbol} | "
                    f"{contribution.trade_count} | "
                    f"{_format_percent(contribution.cumulative_return)} | "
                    f"{_format_percent(contribution.average_return)} |"
                )
            lines.append("")

    diagnostics = _diagnostics_for_result(result)
    if diagnostics.symbols:
        lines.extend(
            [
                "## Result Diagnostics",
                "",
                "| Symbol | Trades | Cumulative return | Realized PnL | Take profit | Stop loss | Rejections | Sizing blocks |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for symbol_diagnostic in diagnostics.symbols:
            lines.append(
                "| "
                f"{symbol_diagnostic.symbol} | "
                f"{symbol_diagnostic.closed_trade_count} | "
                f"{_format_optional_percent(symbol_diagnostic.cumulative_return)} | "
                f"{_format_optional_money(symbol_diagnostic.realized_pnl)} | "
                f"{symbol_diagnostic.take_profit_count} | "
                f"{symbol_diagnostic.stop_loss_count} | "
                f"{symbol_diagnostic.execution_rejection_count} | "
                f"{symbol_diagnostic.sizing_blocked_count} |"
            )
        lines.append("")
        _extend_entry_attribution_contrasts(lines, diagnostics, zh=False)
        _extend_exit_attribution_contrasts(lines, diagnostics, zh=False)
        _extend_add_on_attribution_contrasts(lines, diagnostics, zh=False)
        _extend_entry_attribution_summary(lines, diagnostics.symbols, zh=False)
        _extend_exit_attribution_summary(lines, diagnostics.symbols, zh=False)
        _extend_add_on_attribution_summary(lines, diagnostics, zh=False)
        _extend_add_on_attribution_details(lines, diagnostics, zh=False)

    if report.execution_costs is not None:
        execution = report.execution_costs
        lines.extend(
            [
                "## Execution Costs",
                "",
                "| Metric | Value |",
                "|---|---:|",
                f"| Orders | {execution.order_count} |",
                f"| Submitted | {execution.submitted_count} |",
                f"| Accepted | {execution.accepted_count} |",
                f"| Completed | {execution.completed_count} |",
                f"| Failed | {execution.failed_count} |",
                f"| Rejected | {execution.rejected_count} |",
                f"| Fill rate | {_format_optional_percent(execution.fill_rate)} |",
                f"| Rejection rate | {_format_optional_percent(execution.rejection_rate)} |",
                f"| Total commission | {_format_number(execution.total_commission)} |",
                f"| Average commission | {_format_optional_number(execution.average_commission)} |",
                f"| Total slippage cost | {_format_number(execution.total_slippage_cost)} |",
                f"| Average slippage cost | {_format_optional_number(execution.average_slippage_cost)} |",
                "",
            ]
        )
        if execution.rejections:
            lines.extend(["| Rejection reason | Count |", "|---|---:|"])
            for rejection in execution.rejections:
                lines.append(f"| {rejection.blocked_by} | {rejection.count} |")
            lines.append("")

    if report.benchmark_comparison:
        lines.extend(
            [
                "## Benchmark Comparison",
                "",
                "| Benchmark | Strategy return | Benchmark return | Excess return |",
                "|---|---:|---:|---:|",
            ]
        )
        for comparison in report.benchmark_comparison:
            lines.append(
                "| "
                f"{comparison.benchmark_symbol} | "
                f"{_format_percent(comparison.strategy_return)} | "
                f"{_format_percent(comparison.benchmark_return)} | "
                f"{_format_percent(comparison.excess_return)} |"
            )
        lines.append("")

    if report.industry_attribution:
        lines.extend(
            [
                "## Industry Attribution",
                "",
                "| Level | Code | Name | Trades | Average return | Contribution |",
                "|---:|---|---|---:|---:|---:|",
            ]
        )
        for attribution in report.industry_attribution:
            lines.append(
                "| "
                f"{attribution.level} | "
                f"{attribution.industry_code} | "
                f"{attribution.industry_name} | "
                f"{attribution.trade_count} | "
                f"{_format_percent(attribution.average_return)} | "
                f"{_format_percent(attribution.contribution_return)} |"
            )
        lines.append("")

    if report.market_regime is not None:
        regime = report.market_regime
        lines.extend(
            [
                "## Market Inputs",
                "",
                "| Field | Value |",
                "|---|---|",
                f"| Timeframes | {_join_or_dash(regime.timeframes)} |",
                f"| Benchmarks | {_join_or_dash(regime.benchmark_symbols)} |",
                f"| Industry indexes | {_join_or_dash(regime.industry_index_symbols)} |",
                "",
            ]
        )

    if report.scenario_fit is not None:
        scenario = report.scenario_fit
        lines.extend(
            [
                "## Scenario Fit",
                "",
                f"- Label: `{scenario.label}`",
                f"- Score: {scenario.score}",
            ]
        )
        if scenario.reasons:
            lines.append(f"- Reasons: {'; '.join(scenario.reasons)}")
        if scenario.warnings:
            lines.append(f"- Warnings: {'; '.join(scenario.warnings)}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_backtest_report_markdown_zh(run_plan: "RunPlan", result: "RunPlanExecutionResult") -> str:
    report = result.report
    lines = [
        f"# 回测报告：{report.report_id}",
        "",
        "## 运行概览",
        "",
        "| 字段 | 值 |",
        "|---|---:|",
        f"| 回测区间 | {run_plan.run.from_date} 至 {run_plan.run.to_date} |",
        f"| 执行引擎 | {result.engine} |",
        f"| 复权类型 | {result.adjustment} |",
        f"| 标的 | {_join_or_dash(result.symbols)} |",
        f"| 期末现金 | {_format_optional_number(result.final_cash)} |",
        f"| 期末总资产 | {_format_optional_number(result.final_value)} |",
        "",
        "## 收益与风险",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
        f"| 初始权益 | {_format_number(report.returns.starting_equity)} |",
        f"| 期末权益 | {_format_number(report.returns.final_equity)} |",
        f"| 累计收益率 | {_format_percent(report.returns.cumulative_return)} |",
        f"| 最大回撤 | {_format_percent(report.risk.max_drawdown)} |",
        "",
        "## 交易质量",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
        f"| 交易次数 | {report.trade_quality.trade_count} |",
        f"| 盈利次数 | {report.trade_quality.win_count} |",
        f"| 亏损次数 | {report.trade_quality.loss_count} |",
        f"| 胜率 | {_format_optional_percent(report.trade_quality.win_rate)} |",
        f"| 平均盈利 | {_format_optional_percent(report.trade_quality.average_win)} |",
        f"| 平均亏损 | {_format_optional_percent(report.trade_quality.average_loss)} |",
        f"| 盈亏比 | {_format_optional_number(report.trade_quality.profit_loss_ratio)} |",
        "",
    ]
    _extend_stock_pool_filter_section(lines, result, zh=True)

    if report.portfolio_behavior is not None:
        portfolio = report.portfolio_behavior
        lines.extend(
            [
                "## 组合行为",
                "",
                "| 指标 | 值 |",
                "|---|---:|",
                f"| 持仓数量 | {portfolio.open_position_count} |",
                f"| 持仓标的 | {_join_or_dash(portfolio.open_symbols)} |",
                f"| 已平仓标的数 | {portfolio.closed_symbol_count} |",
                f"| 单标的最大交易占比 | {_format_optional_percent(portfolio.max_symbol_trade_share)} |",
                f"| 现金占比 | {_format_optional_percent(portfolio.cash_ratio)} |",
                "",
            ]
        )
        if portfolio.symbol_contributions:
            lines.extend(
                [
                    "| 标的 | 交易次数 | 累计收益率 | 平均收益率 |",
                    "|---|---:|---:|---:|",
                ]
            )
            for contribution in portfolio.symbol_contributions:
                lines.append(
                    "| "
                    f"{contribution.symbol} | "
                    f"{contribution.trade_count} | "
                    f"{_format_percent(contribution.cumulative_return)} | "
                    f"{_format_percent(contribution.average_return)} |"
                )
            lines.append("")

    diagnostics = _diagnostics_for_result(result)
    if diagnostics.symbols:
        lines.extend(
            [
                "## 结果诊断",
                "",
                "| 标的 | 交易 | 累计收益 | 已实现盈亏 | 止盈 | 止损 | 拒单 | Sizing 拦截 |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for symbol_diagnostic in diagnostics.symbols:
            lines.append(
                "| "
                f"{symbol_diagnostic.symbol} | "
                f"{symbol_diagnostic.closed_trade_count} | "
                f"{_format_optional_percent(symbol_diagnostic.cumulative_return)} | "
                f"{_format_optional_money(symbol_diagnostic.realized_pnl)} | "
                f"{symbol_diagnostic.take_profit_count} | "
                f"{symbol_diagnostic.stop_loss_count} | "
                f"{symbol_diagnostic.execution_rejection_count} | "
                f"{symbol_diagnostic.sizing_blocked_count} |"
            )
        lines.append("")
        _extend_entry_attribution_contrasts(lines, diagnostics, zh=True)
        _extend_exit_attribution_contrasts(lines, diagnostics, zh=True)
        _extend_add_on_attribution_contrasts(lines, diagnostics, zh=True)
        _extend_entry_attribution_summary(lines, diagnostics.symbols, zh=True)
        _extend_exit_attribution_summary(lines, diagnostics.symbols, zh=True)
        _extend_add_on_attribution_summary(lines, diagnostics, zh=True)
        _extend_add_on_attribution_details(lines, diagnostics, zh=True)

    if report.execution_costs is not None:
        execution = report.execution_costs
        lines.extend(
            [
                "## 执行成本",
                "",
                "| 指标 | 值 |",
                "|---|---:|",
                f"| 订单数 | {execution.order_count} |",
                f"| 已提交 | {execution.submitted_count} |",
                f"| 已接受 | {execution.accepted_count} |",
                f"| 已成交 | {execution.completed_count} |",
                f"| 失败 | {execution.failed_count} |",
                f"| 拒绝 | {execution.rejected_count} |",
                f"| 成交率 | {_format_optional_percent(execution.fill_rate)} |",
                f"| 拒绝率 | {_format_optional_percent(execution.rejection_rate)} |",
                f"| 总佣金 | {_format_number(execution.total_commission)} |",
                f"| 平均佣金 | {_format_optional_number(execution.average_commission)} |",
                f"| 总滑点成本 | {_format_number(execution.total_slippage_cost)} |",
                f"| 平均滑点成本 | {_format_optional_number(execution.average_slippage_cost)} |",
                "",
            ]
        )
        if execution.rejections:
            lines.extend(["| 拒绝原因 | 次数 |", "|---|---:|"])
            for rejection in execution.rejections:
                lines.append(f"| {_translate_block_reason(rejection.blocked_by)} | {rejection.count} |")
            lines.append("")

    if report.benchmark_comparison:
        lines.extend(
            [
                "## 基准对比",
                "",
                "| 基准 | 策略收益率 | 基准收益率 | 超额收益率 |",
                "|---|---:|---:|---:|",
            ]
        )
        for comparison in report.benchmark_comparison:
            lines.append(
                "| "
                f"{comparison.benchmark_symbol} | "
                f"{_format_percent(comparison.strategy_return)} | "
                f"{_format_percent(comparison.benchmark_return)} | "
                f"{_format_percent(comparison.excess_return)} |"
            )
        lines.append("")

    if report.industry_attribution:
        lines.extend(
            [
                "## 行业归因",
                "",
                "| 级别 | 行业代码 | 行业名称 | 交易次数 | 平均收益率 | 贡献收益率 |",
                "|---:|---|---|---:|---:|---:|",
            ]
        )
        for attribution in report.industry_attribution:
            lines.append(
                "| "
                f"{attribution.level} | "
                f"{attribution.industry_code} | "
                f"{attribution.industry_name} | "
                f"{attribution.trade_count} | "
                f"{_format_percent(attribution.average_return)} | "
                f"{_format_percent(attribution.contribution_return)} |"
            )
        lines.append("")

    if report.market_regime is not None:
        regime = report.market_regime
        lines.extend(
            [
                "## 市场温度输入",
                "",
                "| 字段 | 值 |",
                "|---|---|",
                f"| 周期 | {_join_timeframes_zh(regime.timeframes)} |",
                f"| 基准指数 | {_join_or_dash(regime.benchmark_symbols)} |",
                f"| 行业指数 | {_join_or_dash(regime.industry_index_symbols)} |",
                "",
            ]
        )

    if report.scenario_fit is not None:
        scenario = report.scenario_fit
        lines.extend(
            [
                "## 场景匹配",
                "",
                f"- 标签：{_label_with_translation(scenario.label)}",
                f"- 分数：{scenario.score}",
            ]
        )
        if scenario.reasons:
            lines.append(f"- 支持理由：{'；'.join(_translate_evidence(reason) for reason in scenario.reasons)}")
        if scenario.warnings:
            lines.append(f"- 风险提示：{'；'.join(_translate_evidence(warning) for warning in scenario.warnings)}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _format_number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _format_optional_number(value: float | None) -> str:
    if value is None:
        return "-"
    return _format_number(value)


def _format_optional_money(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}"


def _format_percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def _format_optional_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return _format_percent(value)


def _join_or_dash(values: tuple[str, ...]) -> str:
    if not values:
        return "-"
    return ", ".join(values)


def _join_timeframes_zh(timeframes: tuple[str, ...]) -> str:
    if not timeframes:
        return "-"
    return ", ".join(_timeframe_with_translation(timeframe) for timeframe in timeframes)


def _extend_entry_attribution_summary(lines: list[str], symbol_diagnostics, *, zh: bool) -> None:
    rows: list[str] = []
    for diagnostic in symbol_diagnostics:
        if diagnostic.winning_trade_attributions:
            rows.append(_entry_attribution_summary_row(diagnostic, outcome="win", zh=zh))
        if diagnostic.losing_trade_attributions:
            rows.append(_entry_attribution_summary_row(diagnostic, outcome="loss", zh=zh))

    if not rows:
        return

    if zh:
        lines.extend(
            [
                "## 入场归因",
                "",
                "| 标的 | 结果 | 交易数 | 入场数值均值 | 入场检查 |",
                "|---|---|---:|---|---|",
            ]
        )
    else:
        lines.extend(
            [
                "## Entry Attribution",
                "",
                "| Symbol | Outcome | Trades | Entry value averages | Entry checks |",
                "|---|---|---:|---|---|",
            ]
        )
    lines.extend(rows)
    lines.append("")


def _extend_exit_attribution_summary(lines: list[str], symbol_diagnostics, *, zh: bool) -> None:
    rows: list[str] = []
    for diagnostic in symbol_diagnostics:
        if diagnostic.winning_exit_summary.sample_count:
            rows.append(_exit_attribution_summary_row(diagnostic, outcome="win", zh=zh))
        if diagnostic.losing_exit_summary.sample_count:
            rows.append(_exit_attribution_summary_row(diagnostic, outcome="loss", zh=zh))

    if not rows:
        return

    if zh:
        lines.extend(
            [
                "## 出场归因",
                "",
                "| 标的 | 结果 | 交易数 | 出场数值均值 | 出场检查 |",
                "|---|---|---:|---|---|",
            ]
        )
    else:
        lines.extend(
            [
                "## Exit Attribution",
                "",
                "| Symbol | Outcome | Trades | Exit value averages | Exit checks |",
                "|---|---|---:|---|---|",
            ]
        )
    lines.extend(rows)
    lines.append("")


def _extend_add_on_attribution_summary(lines: list[str], diagnostics, *, zh: bool) -> None:
    if (
        diagnostics.portfolio_add_on_signal_count <= 0
        and diagnostics.portfolio_winning_add_on_summary.sample_count <= 0
        and diagnostics.portfolio_losing_add_on_summary.sample_count <= 0
    ):
        return

    if zh:
        lines.extend(
            [
                "## 加仓归因",
                "",
                "| 范围 | 加仓信号 | 盈利加仓样本 | 亏损加仓样本 | 盈利加仓检查 | 亏损加仓检查 |",
                "|---|---:|---:|---:|---|---|",
                _add_on_attribution_summary_row(
                    scope="portfolio",
                    signal_count=diagnostics.portfolio_add_on_signal_count,
                    winning_summary=diagnostics.portfolio_winning_add_on_summary,
                    losing_summary=diagnostics.portfolio_losing_add_on_summary,
                    zh=zh,
                ),
            ]
        )
    else:
        lines.extend(
            [
                "## Add-On Attribution",
                "",
                "| Scope | Add-on signals | Winning add-on samples | Losing add-on samples | Winning checks | Losing checks |",
                "|---|---:|---:|---:|---|---|",
                _add_on_attribution_summary_row(
                    scope="portfolio",
                    signal_count=diagnostics.portfolio_add_on_signal_count,
                    winning_summary=diagnostics.portfolio_winning_add_on_summary,
                    losing_summary=diagnostics.portfolio_losing_add_on_summary,
                    zh=zh,
                ),
            ]
        )

    for diagnostic in diagnostics.symbols:
        if (
            diagnostic.add_on_signal_count
            or diagnostic.winning_add_on_summary.sample_count
            or diagnostic.losing_add_on_summary.sample_count
        ):
            lines.append(
                _add_on_attribution_summary_row(
                    scope=diagnostic.symbol,
                    signal_count=diagnostic.add_on_signal_count,
                    winning_summary=diagnostic.winning_add_on_summary,
                    losing_summary=diagnostic.losing_add_on_summary,
                    zh=zh,
                )
            )
    lines.append("")


def _extend_add_on_attribution_details(lines: list[str], diagnostics, *, zh: bool, limit: int = 20) -> None:
    attributions = tuple(
        sorted(
            (
                attribution
                for diagnostic in diagnostics.symbols
                for attribution in (
                    tuple(diagnostic.winning_trade_add_on_attributions)
                    + tuple(diagnostic.losing_trade_add_on_attributions)
                )
            ),
            key=lambda item: (item.add_on_date, item.symbol, item.outcome, item.exit_date),
        )
    )
    if not attributions:
        return

    if zh:
        lines.extend(
            [
                "## 加仓入场点明细",
                "",
                "| 标的 | 结果 | 主入场日 | 加仓日 | 退出日 | 交易收益 | 加仓方法 | 加仓检查 | 加仓数值 | Sizing |",
                "|---|---|---|---|---|---:|---|---|---|---|",
            ]
        )
    else:
        lines.extend(
            [
                "## Add-On Entry Point Details",
                "",
                "| Symbol | Outcome | Entry date | Add-on date | Exit date | Return | Add-on method | Add-on checks | Add-on values | Sizing |",
                "|---|---|---|---|---|---:|---|---|---|---|",
            ]
        )

    for attribution in attributions[:limit]:
        lines.append(
            "| "
            f"{attribution.symbol} | "
            f"{_outcome_label(attribution.outcome, zh=zh)} | "
            f"{attribution.entry_date.isoformat()} | "
            f"{attribution.add_on_date.isoformat()} | "
            f"{attribution.exit_date.isoformat()} | "
            f"{_format_percent(attribution.return_pct)} | "
            f"{attribution.add_on_method_name or '-'} | "
            f"{_format_raw_checks(attribution.add_on_checks, zh=zh)} | "
            f"{_format_raw_values(attribution.add_on_values, zh=zh)} | "
            f"{_format_raw_values(attribution.sizing_context, zh=zh)} |"
        )
    if len(attributions) > limit:
        lines.append("")
        if zh:
            lines.append(f"仅展示前 {limit} 条加仓样本，完整明细见 `result_diagnostics.json`。")
        else:
            lines.append(f"Only the first {limit} add-on samples are shown; see `result_diagnostics.json` for details.")
    lines.append("")


def _extend_add_on_attribution_contrasts(lines: list[str], diagnostics, *, zh: bool) -> None:
    rows: list[str] = []
    rows.extend(
        _entry_attribution_contrast_row(
            scope="portfolio",
            contrast=contrast,
            zh=zh,
        )
        for contrast in diagnostics.portfolio_add_on_contrasts[:8]
        if contrast.difference is not None
    )

    for diagnostic in diagnostics.symbols:
        rows.extend(
            _entry_attribution_contrast_row(
                scope=diagnostic.symbol,
                contrast=contrast,
                zh=zh,
            )
            for contrast in diagnostic.add_on_contrasts[:3]
            if contrast.difference is not None
        )

    if not rows:
        return

    if zh:
        lines.extend(
            [
                "## 加仓归因差异",
                "",
                "| 范围 | 因子 | 类型 | 盈利 | 亏损 | 差值 | 覆盖率 | 样本 |",
                "|---|---|---|---:|---:|---:|---|---|",
            ]
        )
    else:
        lines.extend(
            [
                "## Add-On Attribution Contrast",
                "",
                "| Scope | Factor | Type | Win | Loss | Gap | Coverage | Samples |",
                "|---|---|---|---:|---:|---:|---|---|",
            ]
        )
    lines.extend(rows)
    lines.append("")


def _add_on_attribution_summary_row(
    *,
    scope: str,
    signal_count: int,
    winning_summary,
    losing_summary,
    zh: bool,
) -> str:
    return (
        "| "
        f"{_contrast_scope(scope, zh=zh)} | "
        f"{signal_count} | "
        f"{winning_summary.sample_count} | "
        f"{losing_summary.sample_count} | "
        f"{_format_check_summaries(winning_summary.checks, zh=zh)} | "
        f"{_format_check_summaries(losing_summary.checks, zh=zh)} |"
    )


def _extend_entry_attribution_contrasts(lines: list[str], diagnostics, *, zh: bool) -> None:
    rows: list[str] = []
    rows.extend(
        _entry_attribution_contrast_row(
            scope="portfolio",
            contrast=contrast,
            zh=zh,
        )
        for contrast in diagnostics.portfolio_entry_contrasts[:8]
        if contrast.difference is not None
    )

    for diagnostic in diagnostics.symbols:
        rows.extend(
            _entry_attribution_contrast_row(
                scope=diagnostic.symbol,
                contrast=contrast,
                zh=zh,
            )
            for contrast in diagnostic.entry_contrasts[:3]
            if contrast.difference is not None
        )

    if not rows:
        return

    if zh:
        lines.extend(
            [
                "## 入场归因差异",
                "",
                "| 范围 | 因子 | 类型 | 盈利 | 亏损 | 差值 | 覆盖率 | 样本 |",
                "|---|---|---|---:|---:|---:|---|---|",
            ]
        )
    else:
        lines.extend(
            [
                "## Entry Attribution Contrast",
                "",
                "| Scope | Factor | Type | Win | Loss | Gap | Coverage | Samples |",
                "|---|---|---|---:|---:|---:|---|---|",
            ]
        )
    lines.extend(rows)
    lines.append("")


def _extend_exit_attribution_contrasts(lines: list[str], diagnostics, *, zh: bool) -> None:
    rows: list[str] = []
    rows.extend(
        _entry_attribution_contrast_row(
            scope="portfolio",
            contrast=contrast,
            zh=zh,
        )
        for contrast in diagnostics.portfolio_exit_contrasts[:8]
        if contrast.difference is not None
    )

    for diagnostic in diagnostics.symbols:
        rows.extend(
            _entry_attribution_contrast_row(
                scope=diagnostic.symbol,
                contrast=contrast,
                zh=zh,
            )
            for contrast in diagnostic.exit_contrasts[:3]
            if contrast.difference is not None
        )

    if not rows:
        return

    if zh:
        lines.extend(
            [
                "## 出场归因差异",
                "",
                "| 范围 | 因子 | 类型 | 盈利 | 亏损 | 差值 | 覆盖率 | 样本 |",
                "|---|---|---|---:|---:|---:|---|---|",
            ]
        )
    else:
        lines.extend(
            [
                "## Exit Attribution Contrast",
                "",
                "| Scope | Factor | Type | Win | Loss | Gap | Coverage | Samples |",
                "|---|---|---|---:|---:|---:|---|---|",
            ]
        )
    lines.extend(rows)
    lines.append("")


def _entry_attribution_contrast_row(*, scope: str, contrast, zh: bool) -> str:
    return (
        "| "
        f"{_contrast_scope(scope, zh=zh)} | "
        f"{_factor_label(contrast.key, zh=zh, category_value=contrast.category_value)} | "
        f"{_factor_type_label(contrast.factor_type, zh=zh)} | "
        f"{_format_contrast_value(contrast.win_value, factor_type=contrast.factor_type)} | "
        f"{_format_contrast_value(contrast.loss_value, factor_type=contrast.factor_type)} | "
        f"{_format_contrast_value(contrast.difference, factor_type=contrast.factor_type, signed=True)} | "
        f"{_format_contrast_coverage(contrast, zh=zh)} | "
        f"{_format_contrast_samples(contrast, zh=zh)} |"
    )


def _contrast_scope(scope: str, *, zh: bool) -> str:
    if not zh:
        return scope
    if scope == "portfolio":
        return "组合"
    return scope


def _factor_label(key: str, *, zh: bool, category_value: str | None = None) -> str:
    declaration = _ATTRIBUTION_DECLARATIONS.get(key)
    if declaration is not None:
        label = declaration.label_zh if zh else declaration.label_en
    elif zh:
        label = _ENTRY_CHECK_ZH.get(key, _ENTRY_VALUE_ZH.get(key, key))
    else:
        label = key

    if category_value is None:
        return label
    return f"{label}={category_value}"


def _factor_type_label(factor_type: str, *, zh: bool) -> str:
    if not zh:
        return factor_type
    return {
        "check": "检查",
        "value": "数值",
        "category": "分类",
    }.get(factor_type, factor_type)


def _format_contrast_value(value: float | None, *, factor_type: str, signed: bool = False) -> str:
    if value is None:
        return "-"
    prefix = "+" if signed and value > 0 else ""
    if factor_type in {"check", "category"}:
        return f"{prefix}{value * 100:.2f}%"
    return f"{prefix}{_format_number(value)}"


def _format_contrast_coverage(contrast, *, zh: bool) -> str:
    win_coverage = _coverage_from_missing_rate(contrast.win_missing_rate)
    loss_coverage = _coverage_from_missing_rate(contrast.loss_missing_rate)
    if zh:
        return f"盈 {_format_optional_percent(win_coverage)} / 亏 {_format_optional_percent(loss_coverage)}"
    return f"win {_format_optional_percent(win_coverage)} / loss {_format_optional_percent(loss_coverage)}"


def _format_contrast_samples(contrast, *, zh: bool) -> str:
    suffix = ""
    if contrast.low_sample:
        suffix = "；低样本" if zh else "; low sample"
    if zh:
        return f"盈 {contrast.win_present_count} / 亏 {contrast.loss_present_count}{suffix}"
    return f"win {contrast.win_present_count} / loss {contrast.loss_present_count}{suffix}"


def _coverage_from_missing_rate(missing_rate: float | None) -> float | None:
    if missing_rate is None:
        return None
    return 1.0 - missing_rate


def _entry_attribution_summary_row(diagnostic, *, outcome: str, zh: bool) -> str:
    if outcome == "win":
        trade_count = len(diagnostic.winning_trade_attributions)
        value_averages = diagnostic.winning_entry_value_averages
        check_counts = diagnostic.winning_entry_check_counts
    else:
        trade_count = len(diagnostic.losing_trade_attributions)
        value_averages = diagnostic.losing_entry_value_averages
        check_counts = diagnostic.losing_entry_check_counts

    return (
        "| "
        f"{diagnostic.symbol} | "
        f"{_outcome_label(outcome, zh=zh)} | "
        f"{trade_count} | "
        f"{_format_entry_value_averages(value_averages, zh=zh)} | "
        f"{_format_entry_check_counts(check_counts, zh=zh)} |"
    )


def _exit_attribution_summary_row(diagnostic, *, outcome: str, zh: bool) -> str:
    if outcome == "win":
        summary = diagnostic.winning_exit_summary
    else:
        summary = diagnostic.losing_exit_summary

    return (
        "| "
        f"{diagnostic.symbol} | "
        f"{_outcome_label(outcome, zh=zh)} | "
        f"{summary.sample_count} | "
        f"{_format_value_summaries(summary.values, zh=zh)} | "
        f"{_format_check_summaries(summary.checks, zh=zh)} |"
    )


def _outcome_label(outcome: str, *, zh: bool) -> str:
    if not zh:
        return outcome
    return {"win": "盈利", "loss": "亏损"}.get(outcome, outcome)


def _format_entry_value_averages(value_averages, *, zh: bool) -> str:
    if not value_averages:
        return "-"
    values = []
    for average in value_averages:
        label = _factor_label(average.name, zh=zh) if zh else _factor_label(average.name, zh=False)
        values.append(f"{label}={average.average:.4f}")
    return "; ".join(values[:6])


def _format_value_summaries(value_summaries, *, zh: bool) -> str:
    if not value_summaries:
        return "-"
    values = []
    for summary in value_summaries:
        if summary.average is None:
            continue
        label = _factor_label(summary.key, zh=zh) if zh else _factor_label(summary.key, zh=False)
        values.append(f"{label}={summary.average:.4f}")
    return "; ".join(values[:6]) if values else "-"


def _format_entry_check_counts(check_counts, *, zh: bool) -> str:
    if not check_counts:
        return "-"
    values = []
    for check_count in check_counts:
        label = _factor_label(check_count.check, zh=zh) if zh else _factor_label(check_count.check, zh=False)
        if zh:
            values.append(f"{label}: 是 {check_count.true_count} / 否 {check_count.false_count}")
        else:
            values.append(f"{label}: true {check_count.true_count} / false {check_count.false_count}")
    return "; ".join(values[:6])


def _format_check_summaries(check_summaries, *, zh: bool) -> str:
    if not check_summaries:
        return "-"
    values = []
    for summary in check_summaries:
        label = _factor_label(summary.key, zh=zh) if zh else _factor_label(summary.key, zh=False)
        if zh:
            values.append(f"{label}: 是 {summary.true_count} / 否 {summary.false_count}")
        else:
            values.append(f"{label}: true {summary.true_count} / false {summary.false_count}")
    return "; ".join(values[:6]) if values else "-"


def _format_raw_checks(checks: Mapping[str, bool], *, zh: bool) -> str:
    if not checks:
        return "-"
    values = []
    for key, value in sorted(checks.items()):
        label = _factor_label(key, zh=zh)
        values.append(f"{label}={_format_boolean(value, zh=zh)}")
    return "; ".join(values[:6])


def _format_raw_values(values_by_key: Mapping[str, object], *, zh: bool) -> str:
    if not values_by_key:
        return "-"
    values = []
    for key, value in sorted(values_by_key.items()):
        if isinstance(value, bool):
            formatted_value = _format_boolean(value, zh=zh)
        elif isinstance(value, (int, float)):
            formatted_value = _format_number(float(value))
        elif value is None:
            continue
        else:
            formatted_value = str(value)
        label = _factor_label(key, zh=zh)
        values.append(f"{label}={formatted_value}")
    return "; ".join(values[:6]) if values else "-"


def _format_boolean(value: bool, *, zh: bool) -> str:
    if zh:
        return "是" if value else "否"
    return "true" if value else "false"


def _translate_block_reason(reason: str) -> str:
    parts = [part.strip() for part in reason.split(",") if part.strip()]
    if not parts:
        return reason
    return "，".join(
        f"{_BLOCK_REASON_ZH.get(part, part)} ({part})"
        for part in parts
    )


def _diagnostics_for_result(result: "RunPlanExecutionResult"):
    return build_result_diagnostics(
        symbols=result.symbols,
        closed_trades=result.closed_trades,
        signal_audit=result.signal_audit,
        execution_audit=result.execution_audit,
        open_positions=result.open_positions,
    )


def _extend_stock_pool_filter_section(lines: list[str], result: "RunPlanExecutionResult", *, zh: bool) -> None:
    stock_pool_filter = getattr(result, "stock_pool_filter", None)
    if stock_pool_filter is None:
        return

    excluded_symbols = tuple(getattr(stock_pool_filter, "excluded_symbols", ()) or ())
    warning_symbols = tuple(getattr(stock_pool_filter, "warning_symbols", ()) or ())
    if zh:
        lines.extend(
            [
                "## 股票池过滤",
                "",
                "| 项目 | 值 |",
                "|---|---:|",
                f"| 原始股票数 | {getattr(stock_pool_filter, 'original_count', 0)} |",
                f"| 回测保留 | {getattr(stock_pool_filter, 'kept_count', 0)} |",
                f"| 保留但带 warning | {getattr(stock_pool_filter, 'warning_count', 0)} |",
                f"| 自动剔除 | {getattr(stock_pool_filter, 'excluded_count', 0)} |",
                "",
            ]
        )
        if excluded_symbols:
            lines.extend(["| 剔除标的 | 状态 | 原因 |", "|---|---|---|"])
            for item in excluded_symbols[:12]:
                lines.append(
                    "| "
                    f"{getattr(item, 'symbol', '-')} | "
                    f"{getattr(item, 'status', '-')} | "
                    f"{_stock_pool_filter_reason(item)} |"
                )
            if len(excluded_symbols) > 12:
                lines.append(f"| ... | ... | 另有 {len(excluded_symbols) - 12} 个，见 `stock_pool_filter.json` |")
            lines.append("")
        if warning_symbols:
            lines.append(f"保留的 warning 标的共 {len(warning_symbols)} 个，完整清单见 `stock_pool_filter.json`。")
            lines.append("")
        return

    lines.extend(
        [
            "## Stock Pool Filter",
            "",
            "| Item | Value |",
            "|---|---:|",
            f"| Original symbols | {getattr(stock_pool_filter, 'original_count', 0)} |",
            f"| Kept for backtest | {getattr(stock_pool_filter, 'kept_count', 0)} |",
            f"| Kept with warning | {getattr(stock_pool_filter, 'warning_count', 0)} |",
            f"| Excluded | {getattr(stock_pool_filter, 'excluded_count', 0)} |",
            "",
        ]
    )
    if excluded_symbols:
        lines.extend(["| Excluded symbol | Status | Reason |", "|---|---|---|"])
        for item in excluded_symbols[:12]:
            lines.append(
                "| "
                f"{getattr(item, 'symbol', '-')} | "
                f"{getattr(item, 'status', '-')} | "
                f"{_stock_pool_filter_reason(item)} |"
            )
        if len(excluded_symbols) > 12:
            lines.append(f"| ... | ... | {len(excluded_symbols) - 12} more; see `stock_pool_filter.json` |")
        lines.append("")
    if warning_symbols:
        lines.append(f"{len(warning_symbols)} warning symbols were kept; see `stock_pool_filter.json`.")
        lines.append("")


def _stock_pool_filter_reason(item) -> str:
    error_message = getattr(item, "error_message", None)
    if error_message:
        return str(error_message)
    indicator_alarms = tuple(getattr(item, "indicator_alarms", ()) or ())
    if indicator_alarms:
        return "; ".join(str(value) for value in indicator_alarms[:3])
    issue_codes = tuple(getattr(item, "data_quality_issue_codes", ()) or ())
    if issue_codes:
        return "; ".join(str(value) for value in issue_codes[:3])
    error_type = getattr(item, "error_type", None)
    if error_type:
        return str(error_type)
    return "-"


def _label_with_translation(label: str) -> str:
    translated = _LABEL_ZH.get(label)
    if translated is None:
        return f"`{label}`"
    return f"`{label}` ({translated})"


def _timeframe_with_translation(timeframe: str) -> str:
    translated = _TIMEFRAME_ZH.get(timeframe)
    if translated is None:
        return timeframe
    return f"{timeframe} ({translated})"


def _translate_evidence(value: str) -> str:
    translated = _EVIDENCE_ZH.get(value)
    if translated is not None:
        return translated

    match = re.fullmatch(r"market regime is (.+)", value)
    if match:
        label = match.group(1)
        return f"市场温度为{_LABEL_ZH.get(label, label)}"

    match = re.fullmatch(r"trade_count (\d+) is below minimum (\d+)", value)
    if match:
        trade_count, minimum = match.groups()
        return f"交易次数 {trade_count} 低于最小要求 {minimum}"

    return value
