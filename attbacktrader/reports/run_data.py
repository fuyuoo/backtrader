"""Run artifact data dictionary, overview, and drill-down helpers."""

from __future__ import annotations

import json
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping, Sequence

from attbacktrader.reports.ai_review import REVIEW_SAMPLE_KINDS, build_review_sample


RUN_DATA_DICTIONARY_SCHEMA = "attbacktrader.run_data_dictionary.v1"
RUN_DATA_OVERVIEW_SCHEMA = "attbacktrader.run_data_overview.v1"
RUN_DATA_DRILLDOWN_SCHEMA = "attbacktrader.run_data_drilldown.v1"
RUN_DATA_DRILLDOWN_BATCH_SCHEMA = "attbacktrader.run_data_drilldown_batch.v1"
RUN_DATA_ATTRIBUTION_INDEX_SCHEMA = "attbacktrader.run_data_attribution_index.v1"
RUN_DATA_ATTRIBUTION_SUMMARY_SCHEMA = "attbacktrader.run_data_attribution_summary.v1"

_ATTRIBUTION_FILTER_OPERATORS = (">=", "<=", "!=", "=", ">", "<")
_NUMERIC_BUCKET_FIELD_NAMES = (
    "industry.kdj.j",
    "symbol.kdj.j",
    "market.hs300.kdj.j",
    "symbol.macd.dea",
    "industry.macd.dea",
    "market.hs300.macd.dea",
    "symbol.macd.dea_waterline_age_trading_days",
    "industry.macd.dea_waterline_age_trading_days",
    "market.hs300.macd.dea_waterline_age_trading_days",
)

REASON_CODE_LABELS = {
    "BOARD_LOT_TOO_SMALL": "不足一手，无法下单",
    "MAX_HOLDING_COUNT": "达到最大持仓数量",
    "ATR_RISK_UNAVAILABLE": "ATR 风险数据不可用",
    "SIZING_ZERO_QUANTITY": "仓位计算为 0",
    "ENTRY_ATTRIBUTION_FILTER": "入场归因过滤",
    "KDJ_J_BELOW_13": "KDJ J 值低于 13 入场",
    "KDJ_J_NOT_BELOW_13": "KDJ J 值未低于 13，继续观察",
    "KDJ_J_ABOVE_100": "KDJ J 值高于 100 止盈",
    "FIXED_5_PERCENT_STOP": "固定百分比止损",
    "FIXED_5_PERCENT_STOP_NOT_HIT": "固定百分比止损未命中",
    "KDJ_OVERSOLD_ADD_ON": "KDJ 超卖加仓",
}

_ARTIFACT_SPECS: tuple[dict[str, Any], ...] = (
    {
        "artifact": "run_plan",
        "filename": "run_plan.json",
        "role_zh": "回测配置入口，描述数据范围、股票池、策略方法、资金、约束和分析开关。",
        "row_shape_zh": "单个对象。",
        "primary_ids": ["run.id"],
        "fields": [
            {"path": "run.id", "meaning_zh": "run 标识，也是默认报告目录名。"},
            {"path": "run.from_date", "meaning_zh": "回测开始日期。"},
            {"path": "run.to_date", "meaning_zh": "回测结束日期。"},
            {"path": "data.tradable_series", "meaning_zh": "实际交易标的列表。"},
            {"path": "data.benchmark_series.indexes", "meaning_zh": "基准指数列表，只用于分析/展示。"},
            {"path": "data.industry_series.indexes", "meaning_zh": "行业指数列表，只用于归因/分析。"},
            {"path": "strategy.*", "meaning_zh": "策略模板、入场、止盈、止损、加仓、仓位规则和参数。"},
            {"path": "constraints.ashare.*", "meaning_zh": "A 股交易约束，例如 T+1、涨跌停、一手数量。"},
            {"path": "broker.*", "meaning_zh": "初始资金、佣金、印花税、过户费和滑点。"},
            {"path": "analysis.*", "meaning_zh": "回测后的分析开关，不应反向改变交易事实。"},
        ],
    },
    {
        "artifact": "report",
        "filename": "report.json",
        "role_zh": "面向人的核心绩效报告，保存收益、风险、交易质量和分析摘要。",
        "row_shape_zh": "单个对象。",
        "primary_ids": ["report_id"],
        "fields": [
            {"path": "returns.starting_equity", "meaning_zh": "初始权益。"},
            {"path": "returns.final_equity", "meaning_zh": "期末权益。"},
            {"path": "returns.cumulative_return", "meaning_zh": "累计收益率。"},
            {"path": "risk.max_drawdown", "meaning_zh": "最大回撤。"},
            {"path": "trade_quality.trade_count", "meaning_zh": "闭合交易数量。"},
            {"path": "trade_quality.win_rate", "meaning_zh": "闭合交易胜率。"},
            {"path": "market_regime.primary_label", "meaning_zh": "市场温度/市场状态展示值；当前可为 input_only。"},
        ],
    },
    {
        "artifact": "result",
        "filename": "result.json",
        "role_zh": "运行结果入口。默认 compact 模式只保存摘要；full 模式才保存完整原始运行结果。",
        "row_shape_zh": "单个对象。compact 模式为摘要对象，full 模式为完整大对象。",
        "primary_ids": ["run_id"],
        "fields": [
            {"path": "run_id", "meaning_zh": "运行标识。"},
            {"path": "symbols", "meaning_zh": "参与回测的标的。"},
            {"path": "counts.*", "meaning_zh": "compact 模式下的关键数量。"},
            {"path": "report", "meaning_zh": "compact 模式内嵌核心报告。"},
            {"path": "raw_detail_note", "meaning_zh": "若未持久化完整明细，说明如何打开 full 模式。"},
        ],
    },
    {
        "artifact": "trades",
        "filename": "trades.json",
        "role_zh": "交易结果入口，保存闭合交易和期末未平仓持仓。",
        "row_shape_zh": "对象，包含 closed_trades 和 open_positions 两个数组。",
        "primary_ids": ["closed_trades.symbol+entry_date+exit_date", "open_positions.symbol+entry_date"],
        "fields": [
            {"path": "closed_trades[].symbol", "meaning_zh": "股票代码。"},
            {"path": "closed_trades[].entry_date", "meaning_zh": "入场日期。"},
            {"path": "closed_trades[].exit_date", "meaning_zh": "退出日期。"},
            {"path": "closed_trades[].entry_price", "meaning_zh": "原始首笔入场成交价。"},
            {"path": "closed_trades[].original_entry_price", "meaning_zh": "原始首笔入场成交价，保留用于区别分批减仓后的剩余成本。"},
            {"path": "closed_trades[].remaining_cost_basis_at_exit", "meaning_zh": "最终清仓前剩余仓位成本单价；分批减仓后可能低于原始入场价，成本收回后可能为负。"},
            {"path": "closed_trades[].entry_quantity", "meaning_zh": "本轮交易累计买入数量。"},
            {"path": "closed_trades[].quantity", "meaning_zh": "最终清仓成交数量。"},
            {"path": "closed_trades[].exit_price", "meaning_zh": "退出成交价。"},
            {"path": "closed_trades[].exit_reason", "meaning_zh": "退出原因，例如固定止损或 KDJ 过热止盈。"},
            {"path": "open_positions[].size", "meaning_zh": "期末持仓数量。"},
            {"path": "open_positions[].add_on_count", "meaning_zh": "该持仓已加仓次数。"},
        ],
    },
    {
        "artifact": "equity_curve",
        "filename": "equity_curve.json",
        "role_zh": "每日权益曲线，用于看资金、仓位市值、回撤和暴露度。",
        "row_shape_zh": "数组，每行一个交易日。",
        "primary_ids": ["trade_date"],
        "fields": [
            {"path": "[].trade_date", "meaning_zh": "交易日。"},
            {"path": "[].cash", "meaning_zh": "现金。"},
            {"path": "[].position_value", "meaning_zh": "持仓市值。"},
            {"path": "[].total_value", "meaning_zh": "总权益。"},
            {"path": "[].drawdown", "meaning_zh": "当日回撤。"},
            {"path": "[].holding_count", "meaning_zh": "持仓数量。"},
            {"path": "[].exposure", "meaning_zh": "仓位暴露度。"},
        ],
    },
    {
        "artifact": "signal_audit",
        "filename": "signal_audit.json",
        "role_zh": "策略决策证据。默认 compact 模式保存计数、日期范围和样本；full 模式保存全量意图数组。",
        "row_shape_zh": "compact 模式为单个摘要对象；full 模式为数组，每行一个信号意图。",
        "primary_ids": ["symbol+trade_date+intent_type+reason_code"],
        "fields": [
            {"path": "total_count", "meaning_zh": "compact 模式下的全量信号意图数量。"},
            {"path": "intent_type_counts", "meaning_zh": "compact 模式下按意图类型计数。"},
            {"path": "reason_code_counts", "meaning_zh": "compact 模式下按原因代码计数。"},
            {"path": "samples", "meaning_zh": "compact 模式下保留的前 N 条样本。"},
            {"path": "[].intent_type", "meaning_zh": "意图类型：hold、enter、exit_loss、exit_profit、add_on。"},
            {"path": "[].symbol", "meaning_zh": "股票代码。"},
            {"path": "[].trade_date", "meaning_zh": "信号日期。"},
            {"path": "[].method_name", "meaning_zh": "产生该意图的策略方法。"},
            {"path": "[].reason_code", "meaning_zh": "信号原因代码。"},
            {"path": "[].blocked_by", "meaning_zh": "若被上层规则阻断，记录阻断原因。"},
            {"path": "[].signal_values.checks", "meaning_zh": "该方法输出的检查项。"},
            {"path": "[].signal_values.attribution", "meaning_zh": "入场/退出/加仓时的归因证据。"},
        ],
    },
    {
        "artifact": "sizing_audit",
        "filename": "sizing_audit.json",
        "role_zh": "仓位计算证据。解释信号进入 sizing 后请求数量、风险组和阻断原因。",
        "row_shape_zh": "数组，每行一个 sizing 决策。",
        "primary_ids": ["symbol+trade_date+intent_type"],
        "fields": [
            {"path": "[].symbol", "meaning_zh": "股票代码。"},
            {"path": "[].trade_date", "meaning_zh": "仓位决策日期。"},
            {"path": "[].intent_type", "meaning_zh": "原始意图类型。"},
            {"path": "[].blocked_by", "meaning_zh": "仓位层阻断原因。"},
            {"path": "[].sizing", "meaning_zh": "仓位计算细节，例如目标金额、可执行数量、风险组。"},
        ],
    },
    {
        "artifact": "execution_audit",
        "filename": "execution_audit.json",
        "role_zh": "订单执行证据。记录 submitted、accepted、completed、rejected。",
        "row_shape_zh": "数组，每行一个执行事件。",
        "primary_ids": ["order_ref", "symbol+event_date+side+event_type"],
        "fields": [
            {"path": "[].event_date", "meaning_zh": "执行事件日期。"},
            {"path": "[].signal_date", "meaning_zh": "对应信号日期。"},
            {"path": "[].symbol", "meaning_zh": "股票代码。"},
            {"path": "[].side", "meaning_zh": "买入或卖出。"},
            {"path": "[].event_type", "meaning_zh": "submitted、accepted、completed 或 rejected。"},
            {"path": "[].blocked_by", "meaning_zh": "执行拒绝原因，例如不足一手。"},
            {"path": "[].requested_quantity", "meaning_zh": "请求数量。"},
            {"path": "[].executable_quantity", "meaning_zh": "约束调整后的可执行数量。"},
            {"path": "[].executed_quantity", "meaning_zh": "实际成交数量。"},
            {"path": "[].executed_price", "meaning_zh": "实际成交价格。"},
            {"path": "[].reason_code", "meaning_zh": "执行原因；`BAOMA_SCALE_OUT_*` 表示分批减仓，不对应完整 closed_trade 退出。"},
            {"path": "[].position_quantity_after", "meaning_zh": "该执行事件后的剩余持仓数量。"},
            {"path": "[].remaining_cost_value_after", "meaning_zh": "该执行事件后的剩余成本总额。"},
            {"path": "[].remaining_cost_basis_after", "meaning_zh": "该执行事件后的剩余成本单价。"},
            {"path": "[].cost_recovered_after", "meaning_zh": "该执行事件后是否已经通过分批卖出覆盖剩余成本。"},
        ],
    },
    {
        "artifact": "positions",
        "filename": "positions.json",
        "role_zh": "每日持仓快照，用于复盘持仓暴露和个股持仓变化。",
        "row_shape_zh": "数组，每行一个日期/标的持仓快照。",
        "primary_ids": ["trade_date+symbol"],
        "fields": [
            {"path": "[].trade_date", "meaning_zh": "交易日。"},
            {"path": "[].symbol", "meaning_zh": "股票代码。"},
            {"path": "[].size", "meaning_zh": "持仓数量。"},
            {"path": "[].price", "meaning_zh": "估值价格。"},
            {"path": "[].value", "meaning_zh": "持仓市值。"},
        ],
    },
    {
        "artifact": "snapshots",
        "filename": "snapshots.json",
        "role_zh": "数据快照索引，连接股票、基准、行业和指标快照路径。",
        "row_shape_zh": "单个对象，内部按 symbols/benchmarks/industry_indexes 分组。",
        "primary_ids": ["symbols[].symbol", "benchmarks[].symbol", "industry_indexes[].symbol"],
        "fields": [
            {"path": "symbols[].snapshot_path", "meaning_zh": "股票日线快照路径。"},
            {"path": "symbols[].indicator_snapshot_paths", "meaning_zh": "指标快照路径集合。"},
            {"path": "benchmarks", "meaning_zh": "基准指数快照。"},
            {"path": "industry_indexes", "meaning_zh": "行业指数快照。"},
        ],
    },
    {
        "artifact": "result_diagnostics",
        "filename": "result_diagnostics.json",
        "role_zh": "按标的聚合的诊断证据，包含入场/退出归因、执行拒绝和加仓概览。",
        "row_shape_zh": "单个对象，通常按 symbol 分组。",
        "primary_ids": ["symbols[].symbol"],
        "fields": [
            {"path": "symbols[].symbol", "meaning_zh": "股票代码。"},
            {"path": "symbols[].entry_attribution", "meaning_zh": "入场归因汇总。"},
            {"path": "symbols[].exit_attribution", "meaning_zh": "退出归因汇总。"},
            {"path": "symbols[].execution_rejections", "meaning_zh": "执行拒绝汇总。"},
            {"path": "symbols[].add_on_attribution", "meaning_zh": "加仓归因汇总。"},
        ],
    },
    {
        "artifact": "trade_lifecycle",
        "filename": "trade_lifecycle.json",
        "role_zh": "单笔交易生命周期，串起入场、加仓、退出和执行事件。",
        "row_shape_zh": "对象，lifecycles 是数组，每行一笔闭合交易。",
        "primary_ids": ["lifecycles[].trade_index"],
        "fields": [
            {"path": "lifecycles[].trade_index", "meaning_zh": "交易索引，AI 下钻的主键。"},
            {"path": "lifecycles[].symbol", "meaning_zh": "股票代码。"},
            {"path": "lifecycles[].entry_date", "meaning_zh": "入场日期。"},
            {"path": "lifecycles[].exit_date", "meaning_zh": "退出日期。"},
            {"path": "lifecycles[].events", "meaning_zh": "生命周期事件，包括信号和执行。"},
        ],
    },
    {
        "artifact": "trade_attribution",
        "filename": "trade_attribution.json",
        "role_zh": "统一后验归因入口，从闭合交易生命周期反查入场、出场和加仓时点因子并按盈亏统计。",
        "row_shape_zh": "单个对象，attributions 是每笔闭合交易归因，factor_summaries 是按 timing+factor 聚合。",
        "primary_ids": ["attributions[].trade_index", "factor_summaries[].timing+key"],
        "fields": [
            {"path": "trade_count", "meaning_zh": "参与后验归因的闭合交易数量。"},
            {"path": "attributions[].entry.factors", "meaning_zh": "入场当天反查到的因子；缺失因子显式 missing。"},
            {"path": "attributions[].exit.factors", "meaning_zh": "出场当天反查到的因子；缺失因子显式 missing。"},
            {"path": "attributions[].add_ons[].factors", "meaning_zh": "加仓当天反查到的因子。"},
            {"path": "factor_summaries[].win_rate", "meaning_zh": "该 timing+factor 下非缺失样本的胜率。"},
            {"path": "factor_summaries[].average_return_pct", "meaning_zh": "该 timing+factor 下非缺失样本的平均整笔交易收益。"},
            {"path": "factor_summaries[].value_buckets", "meaning_zh": "该因子不同取值的样本、胜率和代表 trade_index。"},
        ],
    },
    {
        "artifact": "trade_review",
        "filename": "trade_review.json",
        "role_zh": "复盘分析入口，包含交易归因、卖飞、机会成本、加仓点和 profile 汇总。",
        "row_shape_zh": "单个对象，内部有 trades/opportunities/add_on_entry_points 数组。",
        "primary_ids": ["trades[].trade_index", "opportunities[].sample_index", "add_on_entry_points[].sample_index"],
        "fields": [
            {"path": "trades[].entry_checks", "meaning_zh": "入场当天检查项。"},
            {"path": "trades[].exit_checks", "meaning_zh": "退出当天检查项。"},
            {"path": "trades[].sold_too_early", "meaning_zh": "后验卖飞观察标签。"},
            {"path": "opportunities[].blocked_by", "meaning_zh": "机会未成交或被阻断原因。"},
            {"path": "opportunities[].follow_up", "meaning_zh": "机会出现后的窗口表现。"},
            {"path": "add_on_entry_points[].checks", "meaning_zh": "加仓当天检查项。"},
            {"path": "add_on_entry_points[].follow_up", "meaning_zh": "加仓后的窗口表现。"},
        ],
    },
    {
        "artifact": "environment_fit",
        "filename": "environment_fit.json",
        "role_zh": "策略环境适配和利润贡献报告，按入场环境统计胜率、收益率、实际成交净 PnL 和资金收益率。",
        "row_shape_zh": "单个对象，包含 single_factor_summaries、combination_summaries 和 trade_contributions。",
        "primary_ids": ["single_factor_summaries[].field+value", "combination_summaries[].profile_key", "trade_contributions[].trade_index"],
        "fields": [
            {"path": "environment_fields[]", "meaning_zh": "参与环境适配统计的入场检查字段。"},
            {"path": "overall", "meaning_zh": "全部交易的胜率、平均收益和利润贡献汇总。"},
            {"path": "best_environments", "meaning_zh": "按净 PnL、资金收益率、胜率筛出的适配候选环境。"},
            {"path": "single_factor_summaries[]", "meaning_zh": "单个环境因子的分组表现。"},
            {"path": "combination_summaries[]", "meaning_zh": "多个环境因子同时成立时的组合表现。"},
            {"path": "trade_contributions[]", "meaning_zh": "每笔交易的入场成交额、退出成交额、佣金、净 PnL 和入场环境。"},
        ],
    },
    {
        "artifact": "strategy_environment_profile",
        "filename": "strategy_environment_profile.json",
        "role_zh": "策略环境画像，把 environment_fit 统计收敛为适合、规避和不确定环境候选，供 AI 先读结论再下钻样本。",
        "row_shape_zh": "单个对象，包含 preferred_environments、avoid_environments 和 uncertain_environments。",
        "primary_ids": [
            "preferred_environments[].summary_key",
            "avoid_environments[].summary_key",
            "uncertain_environments[].summary_key",
        ],
        "fields": [
            {"path": "overall", "meaning_zh": "全部交易的整体胜率、平均收益、净 PnL 和入场资金收益率。"},
            {"path": "profile_summary", "meaning_zh": "适合、规避、不确定候选数量和证据强度分布。"},
            {"path": "preferred_environments[]", "meaning_zh": "适合环境候选，不代表因果或自动调参结论。"},
            {"path": "avoid_environments[]", "meaning_zh": "规避环境候选，用于设计验证或过滤实验。"},
            {"path": "uncertain_environments[]", "meaning_zh": "样本不足、证据不完整或指标方向混合的环境。"},
            {"path": "[].sample_refs", "meaning_zh": "代表交易下钻引用。"},
        ],
    },
    {
        "artifact": "post_exit_analysis",
        "filename": "post_exit_analysis.json",
        "role_zh": "止盈/止损后观察，反查卖出后 3/5/10/20 天表现。",
        "row_shape_zh": "单个对象，observations 是每笔闭合交易的后验窗口。",
        "primary_ids": ["observations[].trade_index", "observations[].symbol+entry_date+exit_date"],
        "fields": [
            {"path": "window_days", "meaning_zh": "主窗口天数。"},
            {"path": "configured_window_days", "meaning_zh": "配置的所有观察窗口。"},
            {"path": "observations[].sold_too_early", "meaning_zh": "是否超过卖飞阈值。"},
            {"path": "observations[].max_high_return_pct", "meaning_zh": "主窗口内最大高点收益。"},
            {"path": "observations[].primary_window_close_return_pct", "meaning_zh": "主窗口收盘收益。"},
        ],
    },
    {
        "artifact": "evidence_validation",
        "filename": "evidence_validation.json",
        "role_zh": "证据门禁，检查关键 artifact 间数量和引用是否一致。",
        "row_shape_zh": "单个对象。",
        "primary_ids": ["status"],
        "fields": [
            {"path": "status", "meaning_zh": "ok 表示可以继续复盘。"},
            {"path": "counts.*", "meaning_zh": "关键 artifact 数量。"},
            {"path": "error_count", "meaning_zh": "错误数量。"},
            {"path": "warning_count", "meaning_zh": "警告数量。"},
            {"path": "issues", "meaning_zh": "具体问题列表。"},
        ],
    },
)

_OVERVIEW_ARTIFACTS = {
    "run_plan": "run_plan.json",
    "report": "report.json",
    "evidence_validation": "evidence_validation.json",
    "trades": "trades.json",
    "equity_curve": "equity_curve.json",
    "signal_audit": "signal_audit.json",
    "sizing_audit": "sizing_audit.json",
    "execution_audit": "execution_audit.json",
    "positions": "positions.json",
    "snapshots": "snapshots.json",
    "trade_lifecycle": "trade_lifecycle.json",
    "trade_attribution": "trade_attribution.json",
    "trade_review": "trade_review.json",
    "environment_fit": "environment_fit.json",
    "strategy_environment_profile": "strategy_environment_profile.json",
    "post_exit_analysis": "post_exit_analysis.json",
}


def build_run_data_dictionary(run_dir: str | Path | None = None) -> dict[str, Any]:
    """Build a machine-readable dictionary for persisted run artifacts."""

    run_path = Path(run_dir) if run_dir is not None else None
    if run_path is not None and not run_path.exists():
        raise FileNotFoundError(f"Run artifact directory does not exist: {run_path}")

    artifacts = []
    for spec in _ARTIFACT_SPECS:
        artifact = _copy_jsonable(spec)
        if run_path is not None:
            path = run_path / str(spec["filename"])
            artifact["source"] = {
                "path": str(path),
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else None,
            }
        artifacts.append(artifact)

    run_id = None
    if run_path is not None:
        run_plan = _load_json_if_exists(run_path / "run_plan.json")
        run_id = _run_id(run_path, _as_mapping(run_plan))

    return {
        "schema": RUN_DATA_DICTIONARY_SCHEMA,
        "run_id": run_id,
        "source_dir": str(run_path) if run_path is not None else None,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "sample_lookup": {
            "trade": (
                "trade_index -> trade_attribution.attributions / trade_review.trades / "
                "trade_lifecycle.lifecycles / post_exit_analysis.observations"
            ),
            "opportunity": "sample_index -> trade_review.opportunities",
            "add_on": "sample_index -> trade_review.add_on_entry_points",
        },
        "reason_code_labels": REASON_CODE_LABELS,
        "ai_usage_rules": [
            "先读取 evidence_validation；status 不是 ok 时先修证据链。",
            "优先从 run_data_overview 看总量，再用 trade_index 或 sample_index 下钻。",
            "不要重新计算指标、不要重跑策略、不要把缺失值补成 0 或 False。",
            "signal_audit 是决策证据，execution_audit 是执行证据，trade_lifecycle/trade_attribution 是后验归因证据。",
            "卖飞、机会成本和止损后反弹都是后验线索，不是交易因果结论。",
        ],
    }


def render_run_data_dictionary_markdown_zh(dictionary: Mapping[str, Any]) -> str:
    """Render the run artifact dictionary in Chinese Markdown."""

    lines = [
        "# 回测数据字典",
        "",
        f"- schema: `{dictionary.get('schema')}`",
        f"- run_id: `{dictionary.get('run_id')}`",
        f"- source_dir: `{dictionary.get('source_dir')}`",
        f"- artifact_count: `{dictionary.get('artifact_count')}`",
        "",
        "## AI 使用规则",
    ]
    for rule in _as_sequence(dictionary.get("ai_usage_rules")):
        lines.append(f"- {rule}")

    lines.extend(
        [
            "",
            "## Artifact 总览",
            "| artifact | 文件 | 作用 | 主键 |",
            "|---|---|---|---|",
        ]
    )
    for artifact in _as_sequence(dictionary.get("artifacts")):
        artifact_map = _as_mapping(artifact)
        lines.append(
            "| "
            f"`{artifact_map.get('artifact')}` | "
            f"`{artifact_map.get('filename')}` | "
            f"{artifact_map.get('role_zh')} | "
            f"`{', '.join(str(item) for item in _as_sequence(artifact_map.get('primary_ids')))}` |"
        )

    for artifact in _as_sequence(dictionary.get("artifacts")):
        artifact_map = _as_mapping(artifact)
        lines.extend(
            [
                "",
                f"## {artifact_map.get('filename')}",
                "",
                f"- artifact: `{artifact_map.get('artifact')}`",
                f"- row_shape: {artifact_map.get('row_shape_zh')}",
                f"- role: {artifact_map.get('role_zh')}",
            ]
        )
        source = _as_mapping(artifact_map.get("source"))
        if source:
            lines.append(
                f"- exists: `{source.get('exists')}` size_bytes: `{source.get('size_bytes')}` path: `{source.get('path')}`"
            )
        lines.extend(["", "| 字段 | 含义 |", "|---|---|"])
        for field in _as_sequence(artifact_map.get("fields")):
            field_map = _as_mapping(field)
            lines.append(f"| `{field_map.get('path')}` | {field_map.get('meaning_zh')} |")

    lines.extend(
        [
            "",
            "## 原因代码中文",
            "| code | 中文 |",
            "|---|---|",
        ]
    )
    for code, label in _as_mapping(dictionary.get("reason_code_labels")).items():
        lines.append(f"| `{code}` | {label} |")
    lines.append("")
    return "\n".join(lines)


def write_run_data_dictionary(
    dictionary: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Write the run data dictionary JSON and Chinese Markdown."""

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / "run_data_dictionary.json"
    markdown_path = target_dir / "run_data_dictionary.zh.md"
    json_path.write_text(_to_pretty_json(dictionary), encoding="utf-8")
    markdown_path.write_text(render_run_data_dictionary_markdown_zh(dictionary), encoding="utf-8")
    return json_path, markdown_path


def build_run_data_overview(
    run_dir: str | Path,
    *,
    top_symbols: int = 10,
) -> dict[str, Any]:
    """Build a compact overview from already persisted run artifacts."""

    if top_symbols <= 0:
        raise ValueError("top_symbols must be greater than 0")
    run_path = Path(run_dir)
    if not run_path.exists():
        raise FileNotFoundError(f"Run artifact directory does not exist: {run_path}")

    artifacts = _load_overview_artifacts(run_path)
    run_plan = _as_mapping(artifacts.get("run_plan"))
    report = _as_mapping(artifacts.get("report"))
    validation = _as_mapping(artifacts.get("evidence_validation"))
    trades_artifact = _as_mapping(artifacts.get("trades"))
    trade_attribution = _as_mapping(artifacts.get("trade_attribution"))
    trade_review = _as_mapping(artifacts.get("trade_review"))
    post_exit = _as_mapping(artifacts.get("post_exit_analysis"))
    signal_audit_artifact = artifacts.get("signal_audit")
    signal_audit = _as_sequence(signal_audit_artifact)
    sizing_audit = _as_sequence(artifacts.get("sizing_audit"))
    execution_audit = _as_sequence(artifacts.get("execution_audit"))
    equity_curve = _as_sequence(artifacts.get("equity_curve"))
    positions = _as_sequence(artifacts.get("positions"))
    snapshots = _as_mapping(artifacts.get("snapshots"))

    closed_trades = _as_sequence(trades_artifact.get("closed_trades"))
    open_positions = _as_sequence(trades_artifact.get("open_positions"))
    validation_counts = _as_mapping(validation.get("counts"))

    overview = {
        "schema": RUN_DATA_OVERVIEW_SCHEMA,
        "run_id": _run_id(run_path, run_plan),
        "source_dir": str(run_path),
        "evidence_validation": {
            "status": validation.get("status"),
            "error_count": validation.get("error_count"),
            "warning_count": validation.get("warning_count"),
            "counts": validation_counts,
        },
        "run": _pick_present(_as_mapping(run_plan.get("run")), ("id", "from_date", "to_date")),
        "data": _data_summary(run_plan, snapshots),
        "strategy": _strategy_summary(run_plan),
        "broker": _broker_summary(run_plan),
        "metrics": {
            "returns": _as_mapping(report.get("returns")),
            "risk": _as_mapping(report.get("risk")),
            "trade_quality": _as_mapping(report.get("trade_quality")),
            "market_regime": _as_mapping(report.get("market_regime")),
        },
        "artifacts": _artifact_runtime_summaries(run_path, artifacts),
        "equity_curve": {
            "point_count": len(equity_curve),
            "first_point": _as_mapping(equity_curve[0]) if equity_curve else {},
            "last_point": _as_mapping(equity_curve[-1]) if equity_curve else {},
        },
        "trades": {
            "closed_trade_count": len(closed_trades),
            "open_position_count": len(open_positions),
            "exit_reason_counts": _reason_counts(closed_trades, "exit_reason"),
            "symbol_trade_counts": _value_counts(closed_trades, "symbol", top=top_symbols),
            "open_positions": list(open_positions),
        },
        "signals": _signal_audit_summary(signal_audit_artifact, signal_audit),
        "sizing": {
            "decision_count": len(sizing_audit),
            "blocked_by_counts": _reason_counts(_rows_with_value(sizing_audit, "blocked_by"), "blocked_by"),
            "date_range": _date_range(sizing_audit, "trade_date"),
        },
        "execution": {
            "event_count": len(execution_audit),
            "event_type_counts": _value_counts(execution_audit, "event_type"),
            "blocked_by_counts": _reason_counts(_rows_with_value(execution_audit, "blocked_by"), "blocked_by"),
            "date_range": _date_range(execution_audit, "event_date"),
        },
        "positions": {
            "snapshot_count": len(positions),
            "date_range": _date_range(positions, "trade_date"),
        },
        "review": {
            "trade_count": trade_review.get("trade_count"),
            "sold_too_early_count": trade_review.get("sold_too_early_count"),
            "opportunity_count": trade_review.get("opportunity_count"),
            "add_on_entry_count": trade_review.get("add_on_entry_count"),
            "sold_too_early_profile_count": len(_as_sequence(trade_review.get("sold_too_early_profiles"))),
            "stop_loss_rebound_profile_count": len(_as_sequence(trade_review.get("stop_loss_rebound_profiles"))),
            "opportunity_cost_summary_count": len(_as_sequence(trade_review.get("opportunity_cost_summaries"))),
            "add_on_entry_summary_count": len(_as_sequence(trade_review.get("add_on_entry_summaries"))),
        },
        "trade_attribution": {
            "trade_count": trade_attribution.get("trade_count"),
            "entry_event_count": trade_attribution.get("entry_event_count"),
            "exit_event_count": trade_attribution.get("exit_event_count"),
            "add_on_event_count": trade_attribution.get("add_on_event_count"),
            "factor_summary_count": len(_as_sequence(trade_attribution.get("factor_summaries"))),
        },
        "post_exit": {
            "window_days": post_exit.get("window_days"),
            "configured_window_days": post_exit.get("configured_window_days"),
            "rebound_thresholds": post_exit.get("rebound_thresholds"),
            "observation_count": len(_as_sequence(post_exit.get("observations"))),
            "summary_count": len(_as_sequence(post_exit.get("summaries"))),
            "window_summary_count": len(_as_sequence(post_exit.get("window_summaries"))),
            "threshold_summary_count": len(_as_sequence(post_exit.get("threshold_summaries"))),
        },
        "drill_down_entrypoints": {
            "trade": "att-run-data-drilldown --kind trade --trade-index <trade_index>",
            "opportunity": "att-run-data-drilldown --kind opportunity --sample-index <sample_index>",
            "add_on": "att-run-data-drilldown --kind add_on --sample-index <sample_index>",
        },
    }
    return overview


def render_run_data_overview_markdown_zh(overview: Mapping[str, Any]) -> str:
    """Render run data overview in Chinese Markdown."""

    metrics = _as_mapping(overview.get("metrics"))
    returns = _as_mapping(metrics.get("returns"))
    risk = _as_mapping(metrics.get("risk"))
    trade_quality = _as_mapping(metrics.get("trade_quality"))
    equity = _as_mapping(overview.get("equity_curve"))
    trades = _as_mapping(overview.get("trades"))
    signals = _as_mapping(overview.get("signals"))
    execution = _as_mapping(overview.get("execution"))
    review = _as_mapping(overview.get("review"))
    trade_attribution = _as_mapping(overview.get("trade_attribution"))

    lines = [
        "# 回测数据总览",
        "",
        f"- schema: `{overview.get('schema')}`",
        f"- run_id: `{overview.get('run_id')}`",
        f"- source_dir: `{overview.get('source_dir')}`",
        (
            "- evidence_validation: "
            f"`{_nested(overview, 'evidence_validation', 'status')}` "
            f"errors=`{_nested(overview, 'evidence_validation', 'error_count')}` "
            f"warnings=`{_nested(overview, 'evidence_validation', 'warning_count')}`"
        ),
        "",
        "## 核心指标",
        "",
        f"- 初始权益: `{returns.get('starting_equity')}`",
        f"- 期末权益: `{returns.get('final_equity')}`",
        f"- 累计收益: `{returns.get('cumulative_return')}`",
        f"- 最大回撤: `{risk.get('max_drawdown')}`",
        f"- 闭合交易: `{trade_quality.get('trade_count', trades.get('closed_trade_count'))}`",
        f"- 胜率: `{trade_quality.get('win_rate')}`",
        f"- 权益点数: `{equity.get('point_count')}`",
        "",
        "## 数据与策略",
        "```json",
        _to_pretty_json(
            {
                "run": overview.get("run"),
                "data": overview.get("data"),
                "strategy": overview.get("strategy"),
                "broker": overview.get("broker"),
            }
        ),
        "```",
        "",
        "## Artifact 状态",
        "| artifact | exists | count | size_bytes | role |",
        "|---|---:|---:|---:|---|",
    ]
    for artifact in _as_sequence(overview.get("artifacts")):
        artifact_map = _as_mapping(artifact)
        lines.append(
            "| "
            f"`{artifact_map.get('artifact')}` | "
            f"`{artifact_map.get('exists')}` | "
            f"`{artifact_map.get('count')}` | "
            f"`{artifact_map.get('size_bytes')}` | "
            f"{artifact_map.get('role_zh')} |"
        )

    lines.extend(
        [
            "",
            "## 交易",
            "```json",
            _to_pretty_json(trades),
            "```",
            "",
            "## 信号与执行",
            "```json",
            _to_pretty_json({"signals": signals, "sizing": overview.get("sizing"), "execution": execution}),
            "```",
            "",
            "## 复盘层",
            "```json",
            _to_pretty_json(
                {
                    "trade_attribution": trade_attribution,
                    "review": review,
                    "post_exit": overview.get("post_exit"),
                }
            ),
            "```",
            "",
            "## 下钻入口",
        ]
    )
    for kind, command in _as_mapping(overview.get("drill_down_entrypoints")).items():
        lines.append(f"- `{kind}`: `{command}`")
    lines.append("")
    return "\n".join(lines)


def write_run_data_overview(
    overview: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write run data overview JSON and Chinese Markdown."""

    target_dir = Path(output_dir) if output_dir is not None else Path(str(overview["source_dir"]))
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / "run_data_overview.json"
    markdown_path = target_dir / "run_data_overview.zh.md"
    json_path.write_text(_to_pretty_json(overview), encoding="utf-8")
    markdown_path.write_text(render_run_data_overview_markdown_zh(overview), encoding="utf-8")
    return json_path, markdown_path


def build_run_data_drilldown(
    run_dir: str | Path,
    *,
    kind: str,
    sample_index: int | None = None,
    trade_index: int | None = None,
    context_limit: int = 20,
) -> dict[str, Any]:
    """Build a concise drill-down surface for one trade/review sample."""

    if kind not in REVIEW_SAMPLE_KINDS:
        raise ValueError(f"Unsupported drill-down kind: {kind}")
    packet = build_review_sample(
        run_dir,
        kind=kind,
        sample_index=sample_index,
        trade_index=trade_index,
        context_limit=context_limit,
    )
    sample = _as_mapping(packet.get("sample"))
    related = _as_mapping(packet.get("related"))
    summary = _sample_summary(kind, sample, related)
    return {
        "schema": RUN_DATA_DRILLDOWN_SCHEMA,
        "run_id": packet.get("run_id"),
        "source_dir": packet.get("source_dir"),
        "sample_kind": kind,
        "sample_id": packet.get("sample_id"),
        "lookup": packet.get("lookup"),
        "summary": summary,
        "sections": {
            "sample": sample,
            "entry": _entry_section(sample, related),
            "exit": _exit_section(sample, related),
            "add_on": _add_on_section(sample, related),
            "opportunity": _opportunity_section(sample),
            "post_exit": related.get("post_exit_observation"),
            "trade_lifecycle": related.get("trade_lifecycle"),
            "closed_trade": related.get("closed_trade"),
            "signal_intents": related.get("signal_intents", []),
            "signal_intent_match_count": related.get("signal_intent_match_count"),
            "execution_events": related.get("execution_events", []),
            "execution_event_match_count": related.get("execution_event_match_count"),
            "drill_down_hints": related.get("drill_down_hints", []),
        },
        "source_sample_packet": packet,
        "ai_usage_rules": [
            "引用结论时必须带 sample_id，并优先带 trade_index 或 sample_index。",
            "本下钻结果只展示已有证据；不要在这里重算指标或推导新交易事实。",
            "blocked_by_zh 只是中文标签，原始 code 仍以 blocked_by/reason_code 为准。",
        ],
    }


def render_run_data_drilldown_markdown_zh(drilldown: Mapping[str, Any]) -> str:
    """Render a one-sample drill-down in Chinese Markdown."""

    sections = _as_mapping(drilldown.get("sections"))
    summary = _as_mapping(drilldown.get("summary"))
    lines = [
        "# 回测样本下钻",
        "",
        f"- schema: `{drilldown.get('schema')}`",
        f"- run_id: `{drilldown.get('run_id')}`",
        f"- sample_kind: `{drilldown.get('sample_kind')}`",
        f"- sample_id: `{drilldown.get('sample_id')}`",
        f"- source_dir: `{drilldown.get('source_dir')}`",
        "",
        "## 摘要",
        "```json",
        _to_pretty_json(summary),
        "```",
        "",
        "## 入场",
        "```json",
        _to_pretty_json(sections.get("entry", {})),
        "```",
        "",
        "## 退出",
        "```json",
        _to_pretty_json(sections.get("exit", {})),
        "```",
        "",
        "## 机会/加仓",
        "```json",
        _to_pretty_json({"opportunity": sections.get("opportunity", {}), "add_on": sections.get("add_on", {})}),
        "```",
        "",
        "## 止盈止损后观察",
        "```json",
        _to_pretty_json(sections.get("post_exit", {})),
        "```",
        "",
        "## 信号与执行证据",
        "```json",
        _to_pretty_json(
            {
                "signal_intent_match_count": sections.get("signal_intent_match_count"),
                "signal_intents": sections.get("signal_intents", []),
                "execution_event_match_count": sections.get("execution_event_match_count"),
                "execution_events": sections.get("execution_events", []),
            }
        ),
        "```",
        "",
        "## 原始样本",
        "```json",
        _to_pretty_json(sections.get("sample", {})),
        "```",
        "",
        "## AI 使用规则",
    ]
    for rule in _as_sequence(drilldown.get("ai_usage_rules")):
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def write_run_data_drilldown(
    drilldown: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write one drill-down JSON and Chinese Markdown."""

    target_dir = Path(output_dir) if output_dir is not None else Path(str(drilldown["source_dir"]))
    target_dir.mkdir(parents=True, exist_ok=True)
    sample_id = str(drilldown["sample_id"])
    json_path = target_dir / f"run_data_drilldown.{sample_id}.json"
    markdown_path = target_dir / f"run_data_drilldown.{sample_id}.zh.md"
    json_path.write_text(_to_pretty_json(drilldown), encoding="utf-8")
    markdown_path.write_text(render_run_data_drilldown_markdown_zh(drilldown), encoding="utf-8")
    return json_path, markdown_path


def build_run_data_drilldown_batch(
    run_dir: str | Path,
    *,
    sample_refs: Sequence[Mapping[str, Any]],
    context_limit: int = 20,
) -> dict[str, Any]:
    """Build concise drill-down surfaces for several review samples."""

    if context_limit <= 0:
        raise ValueError("context_limit must be greater than 0")
    if not sample_refs:
        raise ValueError("sample_refs cannot be empty")

    drilldowns = [
        build_run_data_drilldown(
            run_dir,
            kind=str(_as_mapping(ref).get("kind")),
            trade_index=_optional_int(_as_mapping(ref).get("trade_index")),
            sample_index=_optional_int(_as_mapping(ref).get("sample_index")),
            context_limit=context_limit,
        )
        for ref in sample_refs
    ]
    first = drilldowns[0]
    samples = [_compact_drilldown(drilldown) for drilldown in drilldowns]
    return {
        "schema": RUN_DATA_DRILLDOWN_BATCH_SCHEMA,
        "run_id": first.get("run_id"),
        "source_dir": first.get("source_dir"),
        "context_limit": context_limit,
        "requested_sample_refs": [dict(_as_mapping(ref)) for ref in sample_refs],
        "sample_count": len(samples),
        "samples": samples,
        "ai_usage_rules": [
            "先看每个 sample.summary，再按需要读取 sections 的入场、退出、机会、加仓和执行证据。",
            "批量下钻用于横向比较样本，不代表样本之间存在因果关系。",
            "引用结论时必须带 sample_id，并优先带 trade_index 或 sample_index。",
        ],
    }


def render_run_data_drilldown_batch_markdown_zh(batch: Mapping[str, Any]) -> str:
    """Render a batch drill-down in Chinese Markdown."""

    lines = [
        "# 回测批量样本下钻",
        "",
        f"- schema: `{batch.get('schema')}`",
        f"- run_id: `{batch.get('run_id')}`",
        f"- source_dir: `{batch.get('source_dir')}`",
        f"- sample_count: `{batch.get('sample_count')}`",
        "",
        "## 样本摘要",
        "```json",
        _to_pretty_json(
            [
                {
                    "sample_id": _as_mapping(sample).get("sample_id"),
                    "sample_kind": _as_mapping(sample).get("sample_kind"),
                    "summary": _as_mapping(sample).get("summary"),
                }
                for sample in _as_sequence(batch.get("samples"))
            ]
        ),
        "```",
    ]
    for sample in _as_sequence(batch.get("samples")):
        sample_map = _as_mapping(sample)
        lines.extend(
            [
                "",
                f"## {sample_map.get('sample_id')}",
                "",
                "```json",
                _to_pretty_json(
                    {
                        "lookup": sample_map.get("lookup"),
                        "summary": sample_map.get("summary"),
                        "sections": sample_map.get("sections"),
                    }
                ),
                "```",
            ]
        )
    lines.extend(["", "## AI 使用规则"])
    for rule in _as_sequence(batch.get("ai_usage_rules")):
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def write_run_data_drilldown_batch(
    batch: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write a batch drill-down JSON and Chinese Markdown."""

    target_dir = Path(output_dir) if output_dir is not None else Path(str(batch["source_dir"]))
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / "run_data_drilldown_batch.json"
    markdown_path = target_dir / "run_data_drilldown_batch.zh.md"
    json_path.write_text(_to_pretty_json(batch), encoding="utf-8")
    markdown_path.write_text(render_run_data_drilldown_batch_markdown_zh(batch), encoding="utf-8")
    return json_path, markdown_path


def build_run_data_attribution_index(
    run_dir: str | Path,
    *,
    filters: Sequence[str] = (),
    max_samples: int = 100,
    top_samples_per_value: int = 20,
) -> dict[str, Any]:
    """Build a queryable index over persisted attribution/check fields."""

    if max_samples <= 0:
        raise ValueError("max_samples must be greater than 0")
    if top_samples_per_value <= 0:
        raise ValueError("top_samples_per_value must be greater than 0")
    run_path = Path(run_dir)
    if not run_path.exists():
        raise FileNotFoundError(f"Run artifact directory does not exist: {run_path}")

    run_plan = _as_mapping(_load_json_if_exists(run_path / "run_plan.json"))
    trade_attribution = _as_mapping(_load_json_if_exists(run_path / "trade_attribution.json"))
    trade_review = _as_mapping(_load_json_if_exists(run_path / "trade_review.json"))
    rows = _attribution_rows(trade_attribution=trade_attribution, trade_review=trade_review)
    parsed_filters = [_parse_attribution_filter(item) for item in filters]
    matches = [row for row in rows if _row_matches_filters(row, parsed_filters)]
    fields = _field_summaries(rows, top_samples_per_value=top_samples_per_value)
    return {
        "schema": RUN_DATA_ATTRIBUTION_INDEX_SCHEMA,
        "run_id": _run_id(run_path, run_plan),
        "source_dir": str(run_path),
        "filters": [
            {
                "raw": parsed["raw"],
                "scope": parsed["scope"],
                "field": parsed["field"],
                "operator": parsed["operator"],
                "value": parsed["value"],
            }
            for parsed in parsed_filters
        ],
        "row_count": len(rows),
        "field_count": len(fields),
        "source_artifacts": {
            "trade_attribution": bool(trade_attribution),
            "trade_review": bool(trade_review),
        },
        "match_count": len(matches),
        "matching_samples": matches[:max_samples],
        "fields": fields,
        "query_examples": [
            "entry.symbol.ma.bullish_trend=true",
            "entry.market.hs300.bullish_trend=false",
            "entry.industry.kdj.j_below_threshold=true",
            "entry.industry.kdj.j<13",
            "entry.symbol.macd.dea_waterline_age_trading_days<=14",
            "add_on.symbol.ma.price_above_ma60=true",
            "exit.industry.sw_l1.code=801880.SI",
            "exit.current_price_at_or_below_stop=true",
            "opportunity.blocked_by=BOARD_LOT_TOO_SMALL",
        ],
        "ai_usage_rules": [
            "优先使用 trade_attribution 的后验归因因子；旧报告缺失该文件时回退到 trade_review。",
            "opportunity 样本仍来自 trade_review.opportunities。",
            "筛选条件支持 =、!=、>、>=、<、<=；多个 --filter 是同一行内的 AND 条件。",
            "数值比较只在字段值和筛选值都能转成数字时成立；字段缺失不会被当成 0。",
            "复盘结论应引用 matching_samples 中的 sample_id、trade_index 或 sample_index。",
            "字段缺失就是缺失，不要当成 false、0 或中性值。",
        ],
    }


def render_run_data_attribution_index_markdown_zh(index: Mapping[str, Any]) -> str:
    """Render attribution index in Chinese Markdown."""

    lines = [
        "# 回测归因字段索引",
        "",
        f"- schema: `{index.get('schema')}`",
        f"- run_id: `{index.get('run_id')}`",
        f"- source_dir: `{index.get('source_dir')}`",
        f"- row_count: `{index.get('row_count')}`",
        f"- field_count: `{index.get('field_count')}`",
        f"- match_count: `{index.get('match_count')}`",
        "",
        "## 筛选条件",
        "```json",
        _to_pretty_json(index.get("filters", [])),
        "```",
        "",
        "## 匹配样本",
        "```json",
        _to_pretty_json(index.get("matching_samples", [])),
        "```",
        "",
        "## 字段摘要",
        "| scope | field | value_count | sample_count |",
        "|---|---|---:|---:|",
    ]
    for field in _as_sequence(index.get("fields")):
        field_map = _as_mapping(field)
        lines.append(
            "| "
            f"`{field_map.get('scope')}` | "
            f"`{field_map.get('field')}` | "
            f"`{len(_as_sequence(field_map.get('value_counts')))}` | "
            f"`{field_map.get('sample_count')}` |"
        )
    lines.extend(
        [
            "",
            "## 字段明细",
            "```json",
            _to_pretty_json(index.get("fields", [])),
            "```",
            "",
            "## AI 使用规则",
        ]
    )
    for rule in _as_sequence(index.get("ai_usage_rules")):
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def write_run_data_attribution_index(
    index: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write attribution index JSON and Chinese Markdown."""

    target_dir = Path(output_dir) if output_dir is not None else Path(str(index["source_dir"]))
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / "run_data_attribution_index.json"
    markdown_path = target_dir / "run_data_attribution_index.zh.md"
    json_path.write_text(_to_pretty_json(index), encoding="utf-8")
    markdown_path.write_text(render_run_data_attribution_index_markdown_zh(index), encoding="utf-8")
    return json_path, markdown_path


def build_run_data_attribution_summary(
    run_dir: str | Path,
    *,
    min_sample_count: int = 30,
    top_n: int = 20,
    combination_size: int = 2,
) -> dict[str, Any]:
    """Build a compact AI-first summary from persisted trade attribution factors."""

    if min_sample_count <= 0:
        raise ValueError("min_sample_count must be greater than 0")
    if top_n <= 0:
        raise ValueError("top_n must be greater than 0")
    if combination_size < 2:
        raise ValueError("combination_size must be at least 2")
    run_path = Path(run_dir)
    if not run_path.exists():
        raise FileNotFoundError(f"Run artifact directory does not exist: {run_path}")

    run_plan = _as_mapping(_load_json_if_exists(run_path / "run_plan.json"))
    trade_attribution = _as_mapping(_load_json_if_exists(run_path / "trade_attribution.json"))
    if not trade_attribution:
        raise FileNotFoundError(f"trade_attribution.json does not exist: {run_path / 'trade_attribution.json'}")

    overall = _trade_attribution_overall(trade_attribution)
    summaries = [_factor_summary_item(summary) for summary in _as_sequence(trade_attribution.get("factor_summaries"))]
    bucket_candidates = _bucket_candidates(
        summaries,
        overall=overall,
        min_sample_count=min_sample_count,
    )
    combination_candidates = _combination_candidates(
        _trade_attribution_rows(trade_attribution),
        overall=overall,
        min_sample_count=min_sample_count,
        combination_size=combination_size,
    )
    return {
        "schema": RUN_DATA_ATTRIBUTION_SUMMARY_SCHEMA,
        "run_id": _run_id(run_path, run_plan),
        "source_dir": str(run_path),
        "source_artifact": "trade_attribution.json",
        "parameters": {
            "min_sample_count": min_sample_count,
            "top_n": top_n,
            "combination_size": combination_size,
            "candidate_value_kinds": ("check", "category", "text"),
            "numeric_bucket_fields": _NUMERIC_BUCKET_FIELD_NAMES,
        },
        "overall": overall,
        "coverage": _attribution_coverage(summaries),
        "preferred_candidates": bucket_candidates["preferred"][:top_n],
        "avoid_candidates": bucket_candidates["avoid"][:top_n],
        "preferred_combination_candidates": combination_candidates["preferred"][:top_n],
        "avoid_combination_candidates": combination_candidates["avoid"][:top_n],
        "largest_win_rate_edges": bucket_candidates["win_rate_edges"][:top_n],
        "largest_average_return_edges": bucket_candidates["average_return_edges"][:top_n],
        "high_missing_factors": _high_missing_factors(summaries, top_n=top_n),
        "ai_usage_rules": [
            "这是 AI 首读摘要，用于发现候选环境，不代表因果结论。",
            "preferred/avoid 只来自已成交交易的后验归因，后续应按 trade_index 下钻样本。",
            "缺失率高的因子不能直接得出环境结论；先检查 coverage。",
            "单因子和组合候选里的 query_filter/query_filters 可直接复制到 run_data_attribution_index 验证样本。",
        ],
    }


def render_run_data_attribution_summary_markdown_zh(summary: Mapping[str, Any]) -> str:
    """Render compact attribution summary in Chinese Markdown."""

    overall = _as_mapping(summary.get("overall"))
    lines = [
        "# 回测归因摘要",
        "",
        f"- schema: `{summary.get('schema')}`",
        f"- run_id: `{summary.get('run_id')}`",
        f"- source_dir: `{summary.get('source_dir')}`",
        f"- trade_count: `{overall.get('trade_count')}`",
        f"- win_rate: `{overall.get('win_rate')}`",
        f"- average_return_pct: `{overall.get('average_return_pct')}`",
        "",
        "## 覆盖率",
        "```json",
        _to_pretty_json(summary.get("coverage", {})),
        "```",
        "",
        "## 适合候选",
        _candidate_table(_as_sequence(summary.get("preferred_candidates"))),
        "",
        "## 规避候选",
        _candidate_table(_as_sequence(summary.get("avoid_candidates"))),
        "",
        "## 适合组合候选",
        _candidate_table(_as_sequence(summary.get("preferred_combination_candidates"))),
        "",
        "## 规避组合候选",
        _candidate_table(_as_sequence(summary.get("avoid_combination_candidates"))),
        "",
        "## 胜率差异最大",
        _candidate_table(_as_sequence(summary.get("largest_win_rate_edges"))),
        "",
        "## 平均收益差异最大",
        _candidate_table(_as_sequence(summary.get("largest_average_return_edges"))),
        "",
        "## 高缺失因子",
        "```json",
        _to_pretty_json(summary.get("high_missing_factors", [])),
        "```",
        "",
        "## AI 使用规则",
    ]
    for rule in _as_sequence(summary.get("ai_usage_rules")):
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def write_run_data_attribution_summary(
    summary: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write compact attribution summary JSON and Chinese Markdown."""

    target_dir = Path(output_dir) if output_dir is not None else Path(str(summary["source_dir"]))
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / "run_data_attribution_summary.json"
    markdown_path = target_dir / "run_data_attribution_summary.zh.md"
    json_path.write_text(_to_pretty_json(summary), encoding="utf-8")
    markdown_path.write_text(render_run_data_attribution_summary_markdown_zh(summary), encoding="utf-8")
    return json_path, markdown_path


def _trade_attribution_overall(trade_attribution: Mapping[str, Any]) -> dict[str, Any]:
    attributions = [_as_mapping(item) for item in _as_sequence(trade_attribution.get("attributions"))]
    returns = [
        float(item["return_pct"])
        for item in attributions
        if item.get("return_pct") is not None
    ]
    win_count = sum(1 for item in attributions if item.get("outcome") == "win")
    loss_count = sum(1 for item in attributions if item.get("outcome") == "loss")
    return {
        "trade_count": len(attributions),
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": win_count / len(attributions) if attributions else None,
        "average_return_pct": sum(returns) / len(returns) if returns else None,
    }


def _factor_summary_item(summary: Any) -> dict[str, Any]:
    summary_map = _as_mapping(summary)
    sample_count = int(summary_map.get("sample_count") or 0)
    missing_count = int(summary_map.get("missing_count") or 0)
    present_count = max(0, sample_count - missing_count)
    return {
        "timing": summary_map.get("timing"),
        "key": summary_map.get("key"),
        "value_kind": summary_map.get("value_kind"),
        "sample_count": sample_count,
        "missing_count": missing_count,
        "present_count": present_count,
        "missing_ratio": missing_count / sample_count if sample_count else None,
        "win_rate": summary_map.get("win_rate"),
        "average_return_pct": summary_map.get("average_return_pct"),
        "value_buckets": _as_sequence(summary_map.get("value_buckets")),
    }


def _bucket_candidates(
    summaries: Sequence[Mapping[str, Any]],
    *,
    overall: Mapping[str, Any],
    min_sample_count: int,
) -> dict[str, list[dict[str, Any]]]:
    overall_win_rate = _optional_float(overall.get("win_rate"))
    overall_average_return = _optional_float(overall.get("average_return_pct"))
    candidates: list[dict[str, Any]] = []
    for summary in summaries:
        if summary.get("value_kind") not in {"check", "category", "text"}:
            continue
        timing = summary.get("timing")
        key = summary.get("key")
        for bucket in _as_sequence(summary.get("value_buckets")):
            bucket_map = _as_mapping(bucket)
            count = int(bucket_map.get("count") or 0)
            if count < min_sample_count:
                continue
            win_rate = _optional_float(bucket_map.get("win_rate"))
            average_return = _optional_float(bucket_map.get("average_return_pct"))
            delta_win_rate = (
                win_rate - overall_win_rate
                if win_rate is not None and overall_win_rate is not None
                else None
            )
            delta_average_return = (
                average_return - overall_average_return
                if average_return is not None and overall_average_return is not None
                else None
            )
            candidates.append(
                {
                    "timing": timing,
                    "field": key,
                    "value": bucket_map.get("value"),
                    "sample_count": count,
                    "win_count": bucket_map.get("win_count"),
                    "loss_count": bucket_map.get("loss_count"),
                    "win_rate": win_rate,
                    "average_return_pct": average_return,
                    "delta_win_rate": delta_win_rate,
                    "delta_average_return_pct": delta_average_return,
                    "trade_indexes": _as_sequence(bucket_map.get("trade_indexes"))[:50],
                    "query_filter": f"{timing}.{key}={bucket_map.get('value')}",
                }
            )

    return {
        "preferred": sorted(
            candidates,
            key=lambda item: (
                -_score_optional(item.get("delta_average_return_pct")),
                -_score_optional(item.get("delta_win_rate")),
                -int(item.get("sample_count") or 0),
            ),
        ),
        "avoid": sorted(
            candidates,
            key=lambda item: (
                _score_optional(item.get("delta_average_return_pct")),
                _score_optional(item.get("delta_win_rate")),
                -int(item.get("sample_count") or 0),
            ),
        ),
        "win_rate_edges": sorted(
            candidates,
            key=lambda item: (
                -abs(_score_optional(item.get("delta_win_rate"))),
                -int(item.get("sample_count") or 0),
            ),
        ),
        "average_return_edges": sorted(
            candidates,
            key=lambda item: (
                -abs(_score_optional(item.get("delta_average_return_pct"))),
                -int(item.get("sample_count") or 0),
            ),
        ),
    }


def _combination_candidates(
    rows: Sequence[Mapping[str, Any]],
    *,
    overall: Mapping[str, Any],
    min_sample_count: int,
    combination_size: int,
) -> dict[str, list[dict[str, Any]]]:
    overall_win_rate = _optional_float(overall.get("win_rate"))
    overall_average_return = _optional_float(overall.get("average_return_pct"))
    buckets: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
    for row in rows:
        row_map = _as_mapping(row)
        if row_map.get("sample_kind") != "trade":
            continue
        scope = row_map.get("scope")
        fields = _as_mapping(row_map.get("fields"))
        trade_index = row_map.get("trade_index")
        outcome = fields.get("trade.outcome")
        return_pct = _optional_float(fields.get("trade.return_pct"))
        conditions = _conditions_for_row(row_map)
        if len(conditions) < combination_size:
            continue
        for combo in combinations(conditions, combination_size):
            query_filters = tuple(
                filter_text
                for condition in combo
                for filter_text in _as_sequence(condition.get("query_filters"))
            )
            key = (str(scope), tuple(sorted(query_filters)))
            bucket = buckets.setdefault(
                key,
                {
                    "timing": scope,
                    "conditions": combo,
                    "query_filters": tuple(sorted(query_filters)),
                    "sample_count": 0,
                    "win_count": 0,
                    "loss_count": 0,
                    "returns": [],
                    "trade_indexes": [],
                },
            )
            bucket["sample_count"] += 1
            if outcome == "win":
                bucket["win_count"] += 1
            elif outcome == "loss":
                bucket["loss_count"] += 1
            if return_pct is not None:
                bucket["returns"].append(return_pct)
            if trade_index is not None and len(bucket["trade_indexes"]) < 50:
                bucket["trade_indexes"].append(trade_index)

    candidates: list[dict[str, Any]] = []
    for bucket in buckets.values():
        count = int(bucket["sample_count"])
        if count < min_sample_count:
            continue
        win_count = int(bucket["win_count"])
        returns = bucket["returns"]
        win_rate = win_count / count if count else None
        average_return = sum(returns) / len(returns) if returns else None
        delta_win_rate = (
            win_rate - overall_win_rate
            if win_rate is not None and overall_win_rate is not None
            else None
        )
        delta_average_return = (
            average_return - overall_average_return
            if average_return is not None and overall_average_return is not None
            else None
        )
        query_filters = list(bucket["query_filters"])
        candidates.append(
            {
                "timing": bucket["timing"],
                "field": " && ".join(str(_as_mapping(condition).get("field")) for condition in bucket["conditions"]),
                "value": " && ".join(str(_as_mapping(condition).get("label")) for condition in bucket["conditions"]),
                "conditions": [_as_mapping(condition) for condition in bucket["conditions"]],
                "sample_count": count,
                "win_count": win_count,
                "loss_count": int(bucket["loss_count"]),
                "win_rate": win_rate,
                "average_return_pct": average_return,
                "delta_win_rate": delta_win_rate,
                "delta_average_return_pct": delta_average_return,
                "trade_indexes": bucket["trade_indexes"],
                "query_filters": query_filters,
                "query_filter": " && ".join(query_filters),
            }
        )

    return {
        "preferred": sorted(
            candidates,
            key=lambda item: (
                -_score_optional(item.get("delta_average_return_pct")),
                -_score_optional(item.get("delta_win_rate")),
                -int(item.get("sample_count") or 0),
            ),
        ),
        "avoid": sorted(
            candidates,
            key=lambda item: (
                _score_optional(item.get("delta_average_return_pct")),
                _score_optional(item.get("delta_win_rate")),
                -int(item.get("sample_count") or 0),
            ),
        ),
    }


def _conditions_for_row(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    scope = str(row.get("scope"))
    conditions: list[dict[str, Any]] = []
    for field, value in sorted(_as_mapping(row.get("fields")).items()):
        if str(field).startswith("trade."):
            continue
        condition = _condition_for_field(scope=scope, field=str(field), value=value)
        if condition is not None:
            conditions.append(condition)
    return conditions[:24]


def _condition_for_field(*, scope: str, field: str, value: Any) -> dict[str, Any] | None:
    numeric_condition = _numeric_bucket_condition(scope=scope, field=field, value=value)
    if numeric_condition is not None:
        return numeric_condition
    if isinstance(value, bool):
        label = _condition_value_label(value)
        return _condition(scope=scope, field=field, label=label, query_filters=(f"{scope}.{field}={label}",))
    if isinstance(value, (int, float)):
        return None
    if value is None or isinstance(value, (list, tuple, dict)):
        return None
    label = _condition_value_label(value)
    return _condition(scope=scope, field=field, label=label, query_filters=(f"{scope}.{field}={label}",))


def _numeric_bucket_condition(*, scope: str, field: str, value: Any) -> dict[str, Any] | None:
    number = _optional_float(value)
    if number is None:
        return None
    if field.endswith(".kdj.j") or field == "industry.kdj.j":
        if number < 13:
            return _condition(scope=scope, field=field, label="<13", query_filters=(f"{scope}.{field}<13",))
        if number < 50:
            return _condition(
                scope=scope,
                field=field,
                label="[13,50)",
                query_filters=(f"{scope}.{field}>=13", f"{scope}.{field}<50"),
            )
        if number < 80:
            return _condition(
                scope=scope,
                field=field,
                label="[50,80)",
                query_filters=(f"{scope}.{field}>=50", f"{scope}.{field}<80"),
            )
        return _condition(scope=scope, field=field, label=">=80", query_filters=(f"{scope}.{field}>=80",))
    if field.endswith(".dea_waterline_age_trading_days"):
        if number <= 5:
            return _condition(scope=scope, field=field, label="<=5", query_filters=(f"{scope}.{field}<=5",))
        if number <= 14:
            return _condition(
                scope=scope,
                field=field,
                label="(5,14]",
                query_filters=(f"{scope}.{field}>5", f"{scope}.{field}<=14"),
            )
        return _condition(scope=scope, field=field, label=">14", query_filters=(f"{scope}.{field}>14",))
    if field.endswith(".macd.dea"):
        if number > 0:
            return _condition(scope=scope, field=field, label=">0", query_filters=(f"{scope}.{field}>0",))
        return _condition(scope=scope, field=field, label="<=0", query_filters=(f"{scope}.{field}<=0",))
    return None


def _condition(*, scope: str, field: str, label: str, query_filters: Sequence[str]) -> dict[str, Any]:
    return {
        "scope": scope,
        "field": field,
        "label": label,
        "query_filters": tuple(query_filters),
    }


def _condition_value_label(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _attribution_coverage(summaries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_timing: dict[str, dict[str, Any]] = {}
    for summary in summaries:
        timing = str(summary.get("timing"))
        bucket = by_timing.setdefault(
            timing,
            {
                "factor_count": 0,
                "fully_missing_factor_count": 0,
                "partially_or_fully_present_factor_count": 0,
            },
        )
        bucket["factor_count"] += 1
        if int(summary.get("present_count") or 0) == 0:
            bucket["fully_missing_factor_count"] += 1
        else:
            bucket["partially_or_fully_present_factor_count"] += 1
    return {"by_timing": by_timing}


def _high_missing_factors(summaries: Sequence[Mapping[str, Any]], *, top_n: int) -> list[dict[str, Any]]:
    rows = [
        {
            "timing": summary.get("timing"),
            "field": summary.get("key"),
            "sample_count": summary.get("sample_count"),
            "missing_count": summary.get("missing_count"),
            "missing_ratio": summary.get("missing_ratio"),
        }
        for summary in summaries
        if _optional_float(summary.get("missing_ratio")) not in (None, 0.0)
    ]
    return sorted(
        rows,
        key=lambda item: (
            -_score_optional(item.get("missing_ratio")),
            -int(item.get("missing_count") or 0),
            str(item.get("field")),
        ),
    )[:top_n]


def _candidate_table(candidates: Sequence[Any]) -> str:
    lines = [
        "| timing | field | value | 样本 | 胜率差 | 收益差 | filter |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for candidate in candidates:
        item = _as_mapping(candidate)
        lines.append(
            "| "
            f"`{item.get('timing')}` | "
            f"`{item.get('field')}` | "
            f"`{item.get('value')}` | "
            f"{item.get('sample_count')} | "
            f"{_format_decimal(item.get('delta_win_rate'))} | "
            f"{_format_decimal(item.get('delta_average_return_pct'))} | "
            f"`{item.get('query_filter')}` |"
        )
    return "\n".join(lines)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _score_optional(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _format_decimal(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):.4f}"


def _compact_drilldown(drilldown: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sample_kind": drilldown.get("sample_kind"),
        "sample_id": drilldown.get("sample_id"),
        "lookup": drilldown.get("lookup"),
        "summary": drilldown.get("summary"),
        "sections": drilldown.get("sections"),
    }


def _attribution_rows(*, trade_attribution: Mapping[str, Any], trade_review: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = _trade_attribution_rows(trade_attribution)
    if rows:
        rows.extend(_opportunity_attribution_rows(trade_review))
        return rows
    return _trade_review_attribution_rows(trade_review)


def _trade_attribution_rows(trade_attribution: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for attribution in _as_sequence(trade_attribution.get("attributions")):
        attribution_map = _as_mapping(attribution)
        context = _drop_empty(
            {
                "trade.outcome": attribution_map.get("outcome"),
                "trade.exit_reason": attribution_map.get("exit_reason"),
                "trade.return_pct": attribution_map.get("return_pct"),
            }
        )
        for scope in ("entry", "exit"):
            event = _as_mapping(attribution_map.get(scope))
            fields = _merge_fields(context, _factor_fields(event))
            if fields:
                rows.append(
                    _attribution_row(
                        scope=scope,
                        sample_kind="trade",
                        sample=attribution_map,
                        date_value=event.get("trade_date") or attribution_map.get(f"{scope}_date"),
                        fields=fields,
                    )
                )
        for event in _as_sequence(attribution_map.get("add_ons")):
            event_map = _as_mapping(event)
            fields = _merge_fields(context, _factor_fields(event_map))
            if fields:
                rows.append(
                    _attribution_row(
                        scope="add_on",
                        sample_kind="trade",
                        sample=attribution_map,
                        date_value=event_map.get("trade_date"),
                        fields=fields,
                    )
                )
    return rows


def _factor_fields(event: Mapping[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for factor in _as_sequence(event.get("factors")):
        factor_map = _as_mapping(factor)
        if factor_map.get("missing") is True:
            continue
        key = factor_map.get("key")
        if key is None:
            continue
        fields[str(key)] = _jsonable_value(factor_map.get("value"))
    return fields


def _trade_review_attribution_rows(trade_review: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trade in _as_sequence(trade_review.get("trades")):
        trade_map = _as_mapping(trade)
        context = _drop_empty(
            {
                "trade.outcome": trade_map.get("outcome"),
                "trade.exit_reason": trade_map.get("exit_reason"),
                "trade.sold_too_early": trade_map.get("sold_too_early"),
                "trade.review_flags": tuple(_as_sequence(trade_map.get("review_flags"))),
            }
        )
        entry_fields = _merge_fields(context, _as_mapping(trade_map.get("entry_checks")))
        if entry_fields:
            rows.append(
                _attribution_row(
                    scope="entry",
                    sample_kind="trade",
                    sample=trade_map,
                    date_value=trade_map.get("entry_date"),
                    fields=entry_fields,
                )
            )
        exit_fields = _merge_fields(context, _as_mapping(trade_map.get("exit_checks")))
        if exit_fields:
            rows.append(
                _attribution_row(
                    scope="exit",
                    sample_kind="trade",
                    sample=trade_map,
                    date_value=trade_map.get("exit_date"),
                    fields=exit_fields,
                )
            )

    rows.extend(_opportunity_attribution_rows(trade_review))

    for add_on in _as_sequence(trade_review.get("add_on_entry_points")):
        add_on_map = _as_mapping(add_on)
        context = _drop_empty(
            {
                "trade.outcome": add_on_map.get("outcome"),
                "reason_code": add_on_map.get("reason_code"),
                "follow_up.complete": _as_mapping(add_on_map.get("follow_up")).get("complete"),
            }
        )
        fields = _merge_fields(context, _as_mapping(add_on_map.get("checks")), _as_mapping(add_on_map.get("categories")))
        if fields:
            rows.append(
                _attribution_row(
                    scope="add_on",
                    sample_kind="add_on",
                    sample=add_on_map,
                    date_value=add_on_map.get("add_on_date"),
                    fields=fields,
                )
            )
    return rows


def _opportunity_attribution_rows(trade_review: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for opportunity in _as_sequence(trade_review.get("opportunities")):
        opportunity_map = _as_mapping(opportunity)
        context = _drop_empty(
            {
                "source": opportunity_map.get("source"),
                "opportunity_group": opportunity_map.get("opportunity_group"),
                "reason_code": opportunity_map.get("reason_code"),
                "blocked_by": opportunity_map.get("blocked_by"),
                "follow_up.complete": _as_mapping(opportunity_map.get("follow_up")).get("complete"),
            }
        )
        fields = _merge_fields(context, _as_mapping(opportunity_map.get("checks")))
        if fields:
            rows.append(
                _attribution_row(
                    scope="opportunity",
                    sample_kind="opportunity",
                    sample=opportunity_map,
                    date_value=opportunity_map.get("trade_date"),
                    fields=fields,
                )
            )
    return rows


def _attribution_row(
    *,
    scope: str,
    sample_kind: str,
    sample: Mapping[str, Any],
    date_value: Any,
    fields: Mapping[str, Any],
) -> dict[str, Any]:
    sample_ref = _sample_ref(sample_kind, sample)
    return {
        "scope": scope,
        "sample_kind": sample_kind,
        "sample_id": _sample_id_from_ref(sample_ref),
        "sample_ref": sample_ref,
        "symbol": sample.get("symbol"),
        "trade_index": sample.get("trade_index"),
        "sample_index": sample.get("sample_index"),
        "date": date_value,
        "fields": dict(fields),
    }


def _field_summaries(rows: Sequence[Mapping[str, Any]], *, top_samples_per_value: int) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    sample_counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        row_map = _as_mapping(row)
        scope = str(row_map.get("scope"))
        sample_ref = _as_mapping(row_map.get("sample_ref"))
        for field, value in _as_mapping(row_map.get("fields")).items():
            key = (scope, str(field))
            sample_counts[key] += 1
            value_key = _stable_value_key(value)
            values = buckets.setdefault(key, {})
            bucket = values.setdefault(
                value_key,
                {
                    "value": _jsonable_value(value),
                    "label_zh": _reason_label(value),
                    "count": 0,
                    "sample_refs": [],
                },
            )
            bucket["count"] += 1
            if len(bucket["sample_refs"]) < top_samples_per_value:
                bucket["sample_refs"].append(sample_ref)

    summaries = []
    for (scope, field), values in sorted(buckets.items(), key=lambda item: (item[0][0], item[0][1])):
        value_counts = sorted(values.values(), key=lambda item: (-int(item["count"]), str(item["value"])))
        summaries.append(
            {
                "scope": scope,
                "field": field,
                "sample_count": sample_counts[(scope, field)],
                "value_counts": value_counts,
            }
        )
    return summaries


def _parse_attribution_filter(text: str) -> dict[str, Any]:
    operator = None
    left = ""
    raw_value = ""
    for candidate in _ATTRIBUTION_FILTER_OPERATORS:
        if candidate in text:
            left, raw_value = text.split(candidate, 1)
            operator = candidate
            break
    if operator is None:
        raise ValueError(f"Attribution filter must use field=value or numeric comparison syntax: {text}")
    if not left or not raw_value:
        raise ValueError(f"Attribution filter must use field=value or numeric comparison syntax: {text}")
    scope = None
    field = left
    for candidate in ("entry", "exit", "add_on", "opportunity"):
        prefix = f"{candidate}."
        if left.startswith(prefix):
            scope = candidate
            field = left[len(prefix) :]
            break
    if not field:
        raise ValueError(f"Attribution filter field cannot be empty: {text}")
    return {
        "raw": text,
        "scope": scope,
        "field": field,
        "operator": operator,
        "value": _parse_filter_value(raw_value),
    }


def _row_matches_filters(row: Mapping[str, Any], filters: Sequence[Mapping[str, Any]]) -> bool:
    if not filters:
        return True
    row_scope = row.get("scope")
    fields = _as_mapping(row.get("fields"))
    for filter_item in filters:
        filter_map = _as_mapping(filter_item)
        scope = filter_map.get("scope")
        field = filter_map.get("field")
        if scope is not None and row_scope != scope:
            return False
        if field not in fields:
            return False
        if not _field_matches_filter(
            fields[field],
            str(filter_map.get("operator") or "="),
            filter_map.get("value"),
        ):
            return False
    return True


def _sample_ref(sample_kind: str, sample: Mapping[str, Any]) -> dict[str, Any]:
    if sample_kind == "trade":
        return _drop_empty(
            {
                "kind": "trade",
                "trade_index": sample.get("trade_index"),
                "symbol": sample.get("symbol"),
                "entry_date": sample.get("entry_date"),
                "exit_date": sample.get("exit_date"),
            }
        )
    return _drop_empty(
        {
            "kind": sample_kind,
            "sample_index": sample.get("sample_index"),
            "trade_index": sample.get("trade_index"),
            "symbol": sample.get("symbol"),
            "trade_date": _first_present(sample.get("trade_date"), sample.get("add_on_date")),
        }
    )


def _sample_id_from_ref(ref: Mapping[str, Any]) -> str:
    kind = ref.get("kind")
    if kind == "trade":
        return f"trade.{ref.get('trade_index')}"
    return f"{kind}.{ref.get('sample_index')}"


def _merge_fields(*sources: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for source in sources:
        for key, value in source.items():
            if value is None:
                continue
            merged[str(key)] = _jsonable_value(value)
    return merged


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _parse_filter_value(value: str) -> Any:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _values_equal(left: Any, right: Any) -> bool:
    if left == right:
        return True
    return str(left) == str(right)


def _field_matches_filter(value: Any, operator: str, expected: Any) -> bool:
    if operator == "=":
        return _values_equal(value, expected)
    if operator == "!=":
        return not _values_equal(value, expected)
    left = _optional_float(value)
    right = _optional_float(expected)
    if left is None or right is None:
        return False
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    raise ValueError(f"Unsupported attribution filter operator: {operator}")


def _stable_value_key(value: Any) -> str:
    return json.dumps(_jsonable_value(value), ensure_ascii=False, sort_keys=True)


def _jsonable_value(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, list):
        return [_jsonable_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _jsonable_value(item) for key, item in value.items()}
    return value


def _load_overview_artifacts(run_path: Path) -> dict[str, Any]:
    return {
        key: _load_json_if_exists(run_path / filename)
        for key, filename in _OVERVIEW_ARTIFACTS.items()
    }


def _data_summary(run_plan: Mapping[str, Any], snapshots: Mapping[str, Any]) -> dict[str, Any]:
    data = _as_mapping(run_plan.get("data"))
    tradable_series = _as_sequence(data.get("tradable_series"))
    symbols = _as_sequence(data.get("symbols"))
    if tradable_series:
        symbol_values = [str(_as_mapping(row).get("symbol")) for row in tradable_series]
    else:
        symbol_values = [str(symbol) for symbol in symbols]
    return {
        "provider": data.get("provider"),
        "price_adjustment": data.get("price_adjustment"),
        "symbol_count": len([symbol for symbol in symbol_values if symbol and symbol != "None"]),
        "symbols": symbol_values,
        "benchmark_symbols": _as_mapping(data.get("benchmark_series")).get("indexes", []),
        "industry_source": _as_mapping(data.get("industry_series")).get("source"),
        "industry_index_symbols": _as_mapping(data.get("industry_series")).get("indexes", []),
        "snapshot_symbol_count": len(_as_sequence(snapshots.get("symbols"))),
        "benchmark_snapshot_count": len(_as_sequence(snapshots.get("benchmarks"))),
        "industry_snapshot_count": len(_as_sequence(snapshots.get("industry_indexes"))),
    }


def _strategy_summary(run_plan: Mapping[str, Any]) -> dict[str, Any]:
    strategy = _as_mapping(run_plan.get("strategy"))
    return _pick_present(
        strategy,
        (
            "template",
            "entry_method",
            "profit_taking_method",
            "stop_loss_method",
            "add_on_method",
            "sizing_rule",
            "entry_params",
            "profit_taking_params",
            "stop_loss_params",
            "add_on_params",
            "sizing_params",
        ),
    )


def _broker_summary(run_plan: Mapping[str, Any]) -> dict[str, Any]:
    broker = _as_mapping(run_plan.get("broker"))
    return _pick_present(
        broker,
        ("initial_cash", "commission_rate", "stamp_tax_rate", "transfer_fee_rate", "slippage"),
    )


def _artifact_runtime_summaries(run_path: Path, artifacts: Mapping[str, Any]) -> list[dict[str, Any]]:
    summaries = []
    for spec in _ARTIFACT_SPECS:
        artifact = str(spec["artifact"])
        path = run_path / str(spec["filename"])
        payload = artifacts.get(artifact)
        summaries.append(
            {
                "artifact": artifact,
                "filename": spec["filename"],
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else None,
                "count": _artifact_count(artifact, payload),
                "role_zh": spec["role_zh"],
            }
        )
    return summaries


def _artifact_count(artifact: str, payload: Any) -> Any:
    if payload is None:
        return None
    if isinstance(payload, list):
        return len(payload)
    payload_map = _as_mapping(payload)
    if artifact == "trades":
        return {
            "closed_trades": len(_as_sequence(payload_map.get("closed_trades"))),
            "open_positions": len(_as_sequence(payload_map.get("open_positions"))),
        }
    if artifact == "trade_lifecycle":
        return len(_as_sequence(payload_map.get("lifecycles")))
    if artifact == "trade_attribution":
        return {
            "trades": payload_map.get("trade_count"),
            "factor_summaries": len(_as_sequence(payload_map.get("factor_summaries"))),
        }
    if artifact == "trade_review":
        return {
            "trades": len(_as_sequence(payload_map.get("trades"))),
            "opportunities": len(_as_sequence(payload_map.get("opportunities"))),
            "add_on_entry_points": len(_as_sequence(payload_map.get("add_on_entry_points"))),
        }
    if artifact == "environment_fit":
        return {
            "trades": payload_map.get("trade_count"),
            "single_factor_summaries": len(_as_sequence(payload_map.get("single_factor_summaries"))),
            "combination_summaries": len(_as_sequence(payload_map.get("combination_summaries"))),
            "trade_contributions": len(_as_sequence(payload_map.get("trade_contributions"))),
        }
    if artifact == "strategy_environment_profile":
        return {
            "preferred_environments": len(_as_sequence(payload_map.get("preferred_environments"))),
            "avoid_environments": len(_as_sequence(payload_map.get("avoid_environments"))),
            "uncertain_environments": len(_as_sequence(payload_map.get("uncertain_environments"))),
        }
    if artifact == "post_exit_analysis":
        return len(_as_sequence(payload_map.get("observations")))
    if artifact == "snapshots":
        return {
            "symbols": len(_as_sequence(payload_map.get("symbols"))),
            "benchmarks": len(_as_sequence(payload_map.get("benchmarks"))),
            "industry_indexes": len(_as_sequence(payload_map.get("industry_indexes"))),
        }
    if artifact == "evidence_validation":
        return payload_map.get("counts")
    if artifact == "signal_audit" and payload_map.get("schema") == "attbacktrader.compact_signal_audit.v1":
        return payload_map.get("total_count")
    if artifact == "result" and payload_map.get("schema") == "attbacktrader.compact_result.v1":
        return payload_map.get("counts")
    return None


def _signal_audit_summary(signal_audit_artifact: Any, signal_audit_rows: Sequence[Any]) -> dict[str, Any]:
    signal_audit_map = _as_mapping(signal_audit_artifact)
    if signal_audit_map.get("schema") == "attbacktrader.compact_signal_audit.v1":
        return {
            "signal_intent_count": signal_audit_map.get("total_count"),
            "intent_type_counts": _as_sequence(signal_audit_map.get("intent_type_counts")),
            "reason_code_counts": _as_sequence(signal_audit_map.get("reason_code_counts")),
            "blocked_by_counts": _as_sequence(signal_audit_map.get("blocked_by_counts")),
            "method_counts": _as_sequence(signal_audit_map.get("method_counts")),
            "date_range": signal_audit_map.get("date_range"),
            "artifact_detail": "compact",
            "sample_count": len(_as_sequence(signal_audit_map.get("samples"))),
        }
    return {
        "signal_intent_count": len(signal_audit_rows),
        "intent_type_counts": _value_counts(signal_audit_rows, "intent_type"),
        "reason_code_counts": _reason_counts(signal_audit_rows, "reason_code"),
        "blocked_by_counts": _reason_counts(_rows_with_value(signal_audit_rows, "blocked_by"), "blocked_by"),
        "date_range": _date_range(signal_audit_rows, "trade_date"),
        "artifact_detail": "full",
    }


def _sample_summary(kind: str, sample: Mapping[str, Any], related: Mapping[str, Any]) -> dict[str, Any]:
    base = {
        "kind": kind,
        "symbol": sample.get("symbol"),
        "trade_index": sample.get("trade_index"),
        "sample_index": sample.get("sample_index"),
        "reason_code": sample.get("reason_code"),
        "reason_code_zh": _reason_label(sample.get("reason_code")),
        "blocked_by": sample.get("blocked_by"),
        "blocked_by_zh": _reason_label(sample.get("blocked_by")),
        "signal_intent_match_count": related.get("signal_intent_match_count"),
        "execution_event_match_count": related.get("execution_event_match_count"),
    }
    if kind == "trade":
        base.update(
            {
                "entry_date": sample.get("entry_date"),
                "exit_date": sample.get("exit_date"),
                "outcome": sample.get("outcome"),
                "exit_reason": sample.get("exit_reason"),
                "exit_reason_zh": _reason_label(sample.get("exit_reason")),
                "return_pct": sample.get("return_pct"),
                "sold_too_early": sample.get("sold_too_early"),
                "max_high_return_pct": sample.get("max_high_return_pct"),
                "primary_window_close_return_pct": sample.get("primary_window_close_return_pct"),
            }
        )
    elif kind == "opportunity":
        follow_up = _as_mapping(sample.get("follow_up"))
        base.update(
            {
                "trade_date": sample.get("trade_date"),
                "opportunity_group": sample.get("opportunity_group"),
                "opportunity_price": sample.get("opportunity_price"),
                "follow_up": _pick_present(
                    follow_up,
                    ("window_days", "observed_day_count", "complete", "window_close_return_pct", "max_high_return_pct"),
                ),
            }
        )
    else:
        follow_up = _as_mapping(sample.get("follow_up"))
        base.update(
            {
                "add_on_date": sample.get("add_on_date"),
                "outcome": sample.get("outcome"),
                "trade_return_pct": sample.get("trade_return_pct"),
                "add_on_price": sample.get("add_on_price"),
                "follow_up": _pick_present(
                    follow_up,
                    ("window_days", "observed_day_count", "complete", "window_close_return_pct", "max_high_return_pct"),
                ),
            }
        )
    return {key: value for key, value in base.items() if value is not None}


def _entry_section(sample: Mapping[str, Any], related: Mapping[str, Any]) -> dict[str, Any]:
    trade = _as_mapping(related.get("trade_review_trade"))
    return _drop_empty(
        {
            "entry_date": _first_present(sample.get("entry_date"), trade.get("entry_date")),
            "entry_method_name": _first_present(sample.get("entry_method_name"), trade.get("entry_method_name")),
            "entry_price": _as_mapping(related.get("closed_trade")).get("entry_price"),
            "entry_checks": _first_present(sample.get("entry_checks"), trade.get("entry_checks")),
        }
    )


def _exit_section(sample: Mapping[str, Any], related: Mapping[str, Any]) -> dict[str, Any]:
    trade = _as_mapping(related.get("trade_review_trade"))
    exit_reason = _first_present(sample.get("exit_reason"), trade.get("exit_reason"))
    return _drop_empty(
        {
            "exit_date": _first_present(sample.get("exit_date"), trade.get("exit_date")),
            "exit_method_name": _first_present(sample.get("exit_method_name"), trade.get("exit_method_name")),
            "exit_price": _as_mapping(related.get("closed_trade")).get("exit_price"),
            "exit_reason": exit_reason,
            "exit_reason_zh": _reason_label(exit_reason),
            "exit_checks": _first_present(sample.get("exit_checks"), trade.get("exit_checks")),
        }
    )


def _add_on_section(sample: Mapping[str, Any], related: Mapping[str, Any]) -> dict[str, Any]:
    if "add_on_date" not in sample and "add_on_checks" not in sample:
        return {}
    reason = sample.get("reason_code")
    return _drop_empty(
        {
            "sample_index": sample.get("sample_index"),
            "add_on_date": sample.get("add_on_date"),
            "method_name": sample.get("method_name"),
            "reason_code": reason,
            "reason_code_zh": _reason_label(reason),
            "add_on_price": sample.get("add_on_price"),
            "checks": _first_present(sample.get("checks"), sample.get("add_on_checks")),
            "categories": sample.get("categories"),
            "follow_up": sample.get("follow_up"),
            "trade_lifecycle": _pick_present(
                _as_mapping(related.get("trade_lifecycle")),
                ("trade_index", "symbol", "outcome", "entry_date", "exit_date", "exit_reason", "return_pct"),
            ),
        }
    )


def _opportunity_section(sample: Mapping[str, Any]) -> dict[str, Any]:
    if "opportunity_group" not in sample:
        return {}
    return _drop_empty(
        {
            "sample_index": sample.get("sample_index"),
            "source": sample.get("source"),
            "opportunity_group": sample.get("opportunity_group"),
            "trade_date": sample.get("trade_date"),
            "method_name": sample.get("method_name"),
            "reason_code": sample.get("reason_code"),
            "reason_code_zh": _reason_label(sample.get("reason_code")),
            "blocked_by": sample.get("blocked_by"),
            "blocked_by_zh": _reason_label(sample.get("blocked_by")),
            "checks": sample.get("checks"),
            "failed_checks": sample.get("failed_checks"),
            "opportunity_price": sample.get("opportunity_price"),
            "follow_up": sample.get("follow_up"),
        }
    )


def _value_counts(rows: Sequence[Any], key: str, *, top: int | None = None) -> list[dict[str, Any]]:
    counter: Counter[Any] = Counter()
    for row in rows:
        row_map = _as_mapping(row)
        value = row_map.get(key)
        if value is None:
            continue
        counter[value] += 1
    items = sorted(counter.items(), key=lambda item: (-item[1], str(item[0])))
    if top is not None:
        items = items[:top]
    return [{"value": value, "count": count} for value, count in items]


def _reason_counts(rows: Sequence[Any], key: str) -> list[dict[str, Any]]:
    return [
        {
            "code": item["value"],
            "label_zh": _reason_label(item["value"]),
            "count": item["count"],
        }
        for item in _value_counts(rows, key)
    ]


def _rows_with_value(rows: Sequence[Any], key: str) -> list[Mapping[str, Any]]:
    return [row_map for row in rows if (row_map := _as_mapping(row)).get(key) is not None]


def _date_range(rows: Sequence[Any], key: str) -> dict[str, Any]:
    values = [row_map.get(key) for row in rows if (row_map := _as_mapping(row)).get(key) is not None]
    if not values:
        return {}
    sorted_values = sorted(str(value) for value in values)
    return {"first": sorted_values[0], "last": sorted_values[-1]}


def _reason_label(value: Any) -> str | None:
    if value is None:
        return None
    return REASON_CODE_LABELS.get(str(value))


def _load_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _run_id(run_path: Path, run_plan: Mapping[str, Any]) -> str:
    return str(_as_mapping(run_plan.get("run")).get("id", run_path.name))


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _as_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, (list, tuple)):
        return value
    return ()


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _nested(source: Mapping[str, Any], *keys: str) -> Any:
    current: Any = source
    for key in keys:
        current = _as_mapping(current).get(key)
    return current


def _pick_present(source: Mapping[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    return {key: source[key] for key in keys if key in source}


def _drop_empty(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in source.items()
        if value is not None and value != {} and value != []
    }


def _copy_jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _to_pretty_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
