"""Attribution wide samples and field index artifacts."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from attbacktrader.features import calculate_kdj


ATTRIBUTION_WIDE_SAMPLES_SCHEMA = "attbacktrader.attribution_wide_samples.v1"
ATTRIBUTION_FIELD_INDEX_SCHEMA = "attbacktrader.attribution_field_index.v1"

DEFAULT_WIDE_SAMPLE_JSON = "attribution_wide_samples.json"
DEFAULT_WIDE_SAMPLE_CSV = "attribution_wide_samples.csv"
DEFAULT_FIELD_INDEX_JSON = "attribution_field_index.json"
DEFAULT_FIELD_INDEX_MARKDOWN = "attribution_field_index.zh.md"

DEFAULT_ENVIRONMENT_FIT_PAIR_WHITELIST: tuple[tuple[str, str], ...] = (
    ("industry.sw_l1.code", "entry.volatility.industry_atr_percentile_bucket"),
    ("industry.sw_l1.code", "industry.weekly.kdj_state"),
    ("industry.sw_l1.code", "entry.stop_fit.fixed_atr_multiple_bucket"),
    ("industry.sw_l1.code", "entry.price_position.ma60_atr_multiple_bucket"),
    ("entry.volatility.atr_20d_bucket", "entry.stop_fit.fixed_atr_multiple_bucket"),
    ("entry.volatility.atr_20d_bucket", "entry.price_position.ma60_atr_multiple_bucket"),
    ("entry.volatility.industry_atr_percentile_bucket", "entry.weekly.symbol_kdj_state"),
    ("entry.weekly.symbol_kdj_state", "industry.weekly.kdj_state"),
    ("entry.market_cap.circulating_mv_bucket", "entry.liquidity.amount_20d_bucket"),
    ("entry.price_position.near_high_20d_bucket", "entry.price_position.interval_20d_bucket"),
    ("entry.price_position.near_high_60d_bucket", "entry.price_position.interval_60d_bucket"),
    ("entry.market.source_index", "market.hs300.trend_state"),
    ("entry.market.source_index", "market.csi500.trend_state"),
    ("market.hs300.trend_state", "market.csi500.trend_state"),
    ("market.objective.entry_stage", "entry.market.source_index"),
    ("market.objective.entry_stage", "market.objective.entry_breadth_ma60_ratio_bucket"),
    ("entry.momentum.return_20d_bucket", "entry.liquidity.amount_5d_vs_20d_bucket"),
    ("entry.momentum.return_20d_bucket", "market.hs300.trend_state"),
    ("entry.momentum.return_20d_bucket", "market.objective.entry_stage"),
)

MA60_ATR_MULTIPLE_FIELD = "entry.price_position.ma60_atr_multiple_bucket"
SIGNAL_CLOSE_MA60_ATR_MULTIPLE_FIELD = "entry.price_position.signal_close_ma60_atr_multiple_bucket"
SIGNAL_TO_ENTRY_RETURN_FIELD = "entry.execution.signal_to_entry_return_bucket"
EXIT_REASON_FIELD = "trade.exit.reason"
HOLDING_DAYS_FIELD = "trade.path.holding_days_bucket"
MAX_FAVORABLE_FIELD = "trade.path.max_favorable_return_before_exit_bucket"
MAX_ADVERSE_FIELD = "trade.path.max_adverse_return_before_exit_bucket"
MAX_DRAWDOWN_FIELD = "trade.path.max_drawdown_from_peak_bucket"
FIRST_PROFIT_5PCT_FIELD = "trade.path.first_profit_5pct_days_bucket"
DEA_WATERLINE_AGE_FIELD = "entry.signal_strength.dea_waterline_age_trading_days_bucket"
DEA_VALUE_FIELD = "entry.signal_strength.dea_value_bucket"
MACD_BAR_FIELD = "entry.signal_strength.macd_bar_bucket"
DIF_DEA_DISTANCE_FIELD = "entry.signal_strength.dif_dea_distance_bucket"
MA25_MA60_SPREAD_FIELD = "entry.signal_strength.ma25_above_ma60_spread_bucket"
MA60_SLOPE_20D_FIELD = "entry.signal_strength.ma60_slope_20d_bucket"
SIGNAL_CANDLE_BODY_FIELD = "entry.signal_strength.signal_candle_body_bucket"
SIGNAL_SHADOW_FIELD = "entry.signal_strength.signal_upper_lower_shadow_bucket"
SYMBOL_WEEKLY_KDJ_J_FIELD = "entry.weekly.symbol_kdj_j_bucket"
SYMBOL_WEEKLY_KDJ_STATE_FIELD = "entry.weekly.symbol_kdj_state"
SYMBOL_WEEKLY_MA_TREND_FIELD = "entry.weekly.symbol_ma_trend_bucket"
SYMBOL_WEEKLY_CLOSE_VS_MA20_FIELD = "entry.weekly.symbol_close_vs_week_ma20_bucket"
INDUSTRY_ATR_20D_FIELD = "industry.volatility.atr_20d_bucket"
INDUSTRY_RETURN_VOL_20D_FIELD = "industry.volatility.return_vol_20d_bucket"
INDUSTRY_RETURN_VOL_60D_FIELD = "industry.volatility.return_vol_60d_bucket"
INDUSTRY_NEAR_HIGH_60D_FIELD = "industry.price_position.near_high_60d_bucket"
INDUSTRY_WEEKLY_KDJ_J_FIELD = "industry.weekly.kdj_j_bucket"
INDUSTRY_WEEKLY_KDJ_STATE_FIELD = "industry.weekly.kdj_state"
INDUSTRY_WEEKLY_MA_TREND_FIELD = "industry.weekly.ma_trend_bucket"
INDUSTRY_WEEKLY_RELATIVE_STRENGTH_FIELD = "industry.weekly.relative_strength_bucket"
SOURCE_INDEX_FIELD = "entry.market.source_index"
SYMBOL_HS300_RS_20D_FIELD = "entry.momentum.symbol_vs_hs300_return_20d_bucket"
SYMBOL_CSI500_RS_20D_FIELD = "entry.momentum.symbol_vs_csi500_return_20d_bucket"
SYMBOL_INDUSTRY_RS_20D_FIELD = "entry.momentum.symbol_vs_industry_return_20d_bucket"
MAX_FAVORABLE_ATR_MULTIPLE_FIELD = "trade.path.max_favorable_atr_multiple_bucket"
MAX_ADVERSE_ATR_MULTIPLE_FIELD = "trade.path.max_adverse_atr_multiple_bucket"
REACHED_10PCT_FIELD = "trade.path.reached_10pct_bucket"
REACHED_15PCT_FIELD = "trade.path.reached_15pct_bucket"
POST_EXIT_MAX_HIGH_5D_FIELD = "trade.path.post_exit_5d_max_high_return_bucket"
POST_EXIT_MAX_CLOSE_5D_FIELD = "trade.path.post_exit_5d_max_close_return_bucket"
POST_EXIT_MIN_LOW_5D_FIELD = "trade.path.post_exit_5d_min_low_return_bucket"
SOLD_TOO_EARLY_5D_FIELD = "trade.path.sold_too_early_5d_bucket"
STOP_LOSS_REBOUND_5D_FIELD = "trade.path.stop_loss_rebound_5d_bucket"
MARKET_INDEX_SPECS: tuple[tuple[str, str, str], ...] = (
    ("hs300", "000300.SH", "沪深300"),
    ("csi500", "000905.SH", "中证500"),
)
OBJECTIVE_PRIMARY_INDEX_SPECS: tuple[tuple[str, str, str], ...] = (
    ("all_share", "000985.CSI", "中证全指"),
    *MARKET_INDEX_SPECS,
)
OBJECTIVE_ENTRY_STAGE_FIELD = "market.objective.entry_stage"
OBJECTIVE_EXIT_STAGE_FIELD = "market.objective.exit_stage"
OBJECTIVE_ENTRY_TO_EXIT_STAGE_FIELD = "market.objective.entry_to_exit_stage"
OBJECTIVE_ENTRY_BREADTH_FIELD = "market.objective.entry_breadth_ma60_ratio_bucket"
OBJECTIVE_EXIT_BREADTH_FIELD = "market.objective.exit_breadth_ma60_ratio_bucket"
OBJECTIVE_ENTRY_DRAWDOWN_FIELD = "market.objective.entry_index_drawdown_250d_bucket"
OBJECTIVE_EXIT_DRAWDOWN_FIELD = "market.objective.exit_index_drawdown_250d_bucket"
OBJECTIVE_ENTRY_MA60_SLOPE_FIELD = "market.objective.entry_index_ma60_slope_20d_bucket"
OBJECTIVE_EXIT_MA60_SLOPE_FIELD = "market.objective.exit_index_ma60_slope_20d_bucket"
OBJECTIVE_ENTRY_MA250_POSITION_FIELD = "market.objective.entry_index_ma250_position"
OBJECTIVE_EXIT_MA250_POSITION_FIELD = "market.objective.exit_index_ma250_position"
OBJECTIVE_MARKET_STAGE_FIELDS: tuple[str, ...] = (
    OBJECTIVE_ENTRY_STAGE_FIELD,
    OBJECTIVE_EXIT_STAGE_FIELD,
    OBJECTIVE_ENTRY_TO_EXIT_STAGE_FIELD,
    OBJECTIVE_ENTRY_BREADTH_FIELD,
    OBJECTIVE_EXIT_BREADTH_FIELD,
    OBJECTIVE_ENTRY_DRAWDOWN_FIELD,
    OBJECTIVE_EXIT_DRAWDOWN_FIELD,
    OBJECTIVE_ENTRY_MA60_SLOPE_FIELD,
    OBJECTIVE_EXIT_MA60_SLOPE_FIELD,
    OBJECTIVE_ENTRY_MA250_POSITION_FIELD,
    OBJECTIVE_EXIT_MA250_POSITION_FIELD,
)
MARKET_INDEX_FIELDS: tuple[str, ...] = tuple(
    f"market.{key}.{suffix}"
    for key, _symbol, _label in MARKET_INDEX_SPECS
    for suffix in (
        "trend_state",
        "return_vol_20d_bucket",
        "return_vol_60d_bucket",
        "weekly.kdj_state",
        "weekly.ma_trend_bucket",
    )
)
MARKET_STAGE_FIELDS: tuple[str, ...] = tuple(
    f"market.{key}.{suffix}"
    for key, _symbol, _label in MARKET_INDEX_SPECS
    for suffix in (
        "entry_stage",
        "exit_stage",
        "entry_to_exit_stage",
    )
)
MOMENTUM_RELATIVE_FIELDS = (
    SYMBOL_HS300_RS_20D_FIELD,
    SYMBOL_CSI500_RS_20D_FIELD,
    SYMBOL_INDUSTRY_RS_20D_FIELD,
)
POST_TRADE_DIAGNOSTIC_FIELDS = (
    MAX_FAVORABLE_ATR_MULTIPLE_FIELD,
    MAX_ADVERSE_ATR_MULTIPLE_FIELD,
    REACHED_10PCT_FIELD,
    REACHED_15PCT_FIELD,
    POST_EXIT_MAX_HIGH_5D_FIELD,
    POST_EXIT_MAX_CLOSE_5D_FIELD,
    POST_EXIT_MIN_LOW_5D_FIELD,
    SOLD_TOO_EARLY_5D_FIELD,
    STOP_LOSS_REBOUND_5D_FIELD,
)
DERIVED_ONLY_FIELDS = {
    EXIT_REASON_FIELD,
    MA60_ATR_MULTIPLE_FIELD,
    SIGNAL_CLOSE_MA60_ATR_MULTIPLE_FIELD,
    SIGNAL_TO_ENTRY_RETURN_FIELD,
    HOLDING_DAYS_FIELD,
    MAX_FAVORABLE_FIELD,
    MAX_ADVERSE_FIELD,
    MAX_DRAWDOWN_FIELD,
    FIRST_PROFIT_5PCT_FIELD,
    DEA_WATERLINE_AGE_FIELD,
    DEA_VALUE_FIELD,
    MACD_BAR_FIELD,
    DIF_DEA_DISTANCE_FIELD,
    MA25_MA60_SPREAD_FIELD,
    MA60_SLOPE_20D_FIELD,
    SIGNAL_CANDLE_BODY_FIELD,
    SIGNAL_SHADOW_FIELD,
    SYMBOL_WEEKLY_KDJ_J_FIELD,
    SYMBOL_WEEKLY_KDJ_STATE_FIELD,
    SYMBOL_WEEKLY_MA_TREND_FIELD,
    SYMBOL_WEEKLY_CLOSE_VS_MA20_FIELD,
    INDUSTRY_ATR_20D_FIELD,
    INDUSTRY_RETURN_VOL_20D_FIELD,
    INDUSTRY_RETURN_VOL_60D_FIELD,
    INDUSTRY_NEAR_HIGH_60D_FIELD,
    INDUSTRY_WEEKLY_KDJ_J_FIELD,
    INDUSTRY_WEEKLY_KDJ_STATE_FIELD,
    INDUSTRY_WEEKLY_MA_TREND_FIELD,
    INDUSTRY_WEEKLY_RELATIVE_STRENGTH_FIELD,
    SOURCE_INDEX_FIELD,
    *MARKET_INDEX_FIELDS,
    *MARKET_STAGE_FIELDS,
    *OBJECTIVE_MARKET_STAGE_FIELDS,
    *MOMENTUM_RELATIVE_FIELDS,
    *POST_TRADE_DIAGNOSTIC_FIELDS,
}

EXIT_REASON_ENTRY_FACTOR_PAIRS: tuple[tuple[str, str], ...] = (
    (EXIT_REASON_FIELD, MA60_ATR_MULTIPLE_FIELD),
    (EXIT_REASON_FIELD, "entry.price_position.near_high_60d_bucket"),
    (EXIT_REASON_FIELD, "entry.volatility.atr_20d_bucket"),
    (EXIT_REASON_FIELD, "entry.stop_fit.fixed_atr_multiple_bucket"),
    (EXIT_REASON_FIELD, DEA_WATERLINE_AGE_FIELD),
    (EXIT_REASON_FIELD, DEA_VALUE_FIELD),
    (EXIT_REASON_FIELD, MACD_BAR_FIELD),
    (EXIT_REASON_FIELD, DIF_DEA_DISTANCE_FIELD),
    (EXIT_REASON_FIELD, MA25_MA60_SPREAD_FIELD),
    (EXIT_REASON_FIELD, MA60_SLOPE_20D_FIELD),
    (EXIT_REASON_FIELD, SIGNAL_CANDLE_BODY_FIELD),
    (EXIT_REASON_FIELD, SIGNAL_SHADOW_FIELD),
)
MARKET_STAGE_DIAGNOSTIC_PAIRS: tuple[tuple[str, str], ...] = tuple(
    (EXIT_REASON_FIELD, f"market.{key}.{suffix}")
    for key, _symbol, _label in MARKET_INDEX_SPECS
    for suffix in (
        "entry_stage",
        "exit_stage",
        "entry_to_exit_stage",
    )
) + tuple(
    (EXIT_REASON_FIELD, field_key)
    for field_key in (
        OBJECTIVE_ENTRY_STAGE_FIELD,
        OBJECTIVE_EXIT_STAGE_FIELD,
        OBJECTIVE_ENTRY_TO_EXIT_STAGE_FIELD,
    )
)

DERIVED_FIELD_CATALOG: dict[str, dict[str, Any]] = {
    EXIT_REASON_FIELD: {
        "field_key": EXIT_REASON_FIELD,
        "label_zh": "退出原因",
        "value_type": "category",
        "timing": "exit",
        "scope": "exit",
        "bucket_rule": "reason_code",
        "default_in_environment_fit": False,
        "source": "closed_trade",
        "missing_policy": "missing",
    },
    MA60_ATR_MULTIPLE_FIELD: {
        "field_key": MA60_ATR_MULTIPLE_FIELD,
        "label_zh": "入场价距MA60的ATR倍数桶",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "price_position",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": True,
        "source": "trade_lifecycle+attribution_reference",
        "missing_policy": "missing",
    },
    SIGNAL_CLOSE_MA60_ATR_MULTIPLE_FIELD: {
        "field_key": SIGNAL_CLOSE_MA60_ATR_MULTIPLE_FIELD,
        "label_zh": "信号日close距MA60的ATR倍数桶",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "price_position",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": False,
        "source": "trade_lifecycle+attribution_reference",
        "missing_policy": "missing",
    },
    SIGNAL_TO_ENTRY_RETURN_FIELD: {
        "field_key": SIGNAL_TO_ENTRY_RETURN_FIELD,
        "label_zh": "信号日close到入场成交价涨跌桶",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "execution",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": False,
        "source": "trade_lifecycle",
        "missing_policy": "missing",
    },
    HOLDING_DAYS_FIELD: {
        "field_key": HOLDING_DAYS_FIELD,
        "label_zh": "持仓交易日数桶",
        "value_type": "bucket",
        "timing": "post_trade",
        "scope": "path",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": False,
        "source": "daily_price_cache",
        "missing_policy": "missing",
    },
    MAX_FAVORABLE_FIELD: {
        "field_key": MAX_FAVORABLE_FIELD,
        "label_zh": "退出前最大浮盈桶",
        "value_type": "bucket",
        "timing": "post_trade",
        "scope": "path",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": False,
        "source": "daily_price_cache",
        "missing_policy": "missing",
    },
    MAX_ADVERSE_FIELD: {
        "field_key": MAX_ADVERSE_FIELD,
        "label_zh": "退出前最大浮亏桶",
        "value_type": "bucket",
        "timing": "post_trade",
        "scope": "path",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": False,
        "source": "daily_price_cache",
        "missing_policy": "missing",
    },
    MAX_DRAWDOWN_FIELD: {
        "field_key": MAX_DRAWDOWN_FIELD,
        "label_zh": "持仓最高点后最大回撤桶",
        "value_type": "bucket",
        "timing": "post_trade",
        "scope": "path",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": False,
        "source": "daily_price_cache",
        "missing_policy": "missing",
    },
    FIRST_PROFIT_5PCT_FIELD: {
        "field_key": FIRST_PROFIT_5PCT_FIELD,
        "label_zh": "首次达到5%浮盈交易日数桶",
        "value_type": "bucket",
        "timing": "post_trade",
        "scope": "path",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": False,
        "source": "daily_price_cache",
        "missing_policy": "missing",
    },
    DEA_WATERLINE_AGE_FIELD: {
        "field_key": DEA_WATERLINE_AGE_FIELD,
        "label_zh": "DEA上水后交易日数桶",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "signal_strength",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": True,
        "source": "trade_lifecycle",
        "missing_policy": "missing",
    },
    DEA_VALUE_FIELD: {
        "field_key": DEA_VALUE_FIELD,
        "label_zh": "DEA强弱桶（DEA/信号日close）",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "signal_strength",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": True,
        "source": "trade_lifecycle",
        "missing_policy": "missing",
    },
    MACD_BAR_FIELD: {
        "field_key": MACD_BAR_FIELD,
        "label_zh": "MACD柱强弱桶（MACD柱/信号日close）",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "signal_strength",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": True,
        "source": "trade_lifecycle",
        "missing_policy": "missing",
    },
    DIF_DEA_DISTANCE_FIELD: {
        "field_key": DIF_DEA_DISTANCE_FIELD,
        "label_zh": "DIF-DEA距离桶（/信号日close）",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "signal_strength",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": True,
        "source": "trade_lifecycle",
        "missing_policy": "missing",
    },
    MA25_MA60_SPREAD_FIELD: {
        "field_key": MA25_MA60_SPREAD_FIELD,
        "label_zh": "MA25相对MA60乖离桶",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "signal_strength",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": True,
        "source": "trade_lifecycle",
        "missing_policy": "missing",
    },
    MA60_SLOPE_20D_FIELD: {
        "field_key": MA60_SLOPE_20D_FIELD,
        "label_zh": "MA60近20日斜率桶",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "signal_strength",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": True,
        "source": "daily_price_cache",
        "missing_policy": "missing",
    },
    SIGNAL_CANDLE_BODY_FIELD: {
        "field_key": SIGNAL_CANDLE_BODY_FIELD,
        "label_zh": "信号日阴线实体大小桶",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "signal_strength",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": True,
        "source": "trade_lifecycle",
        "missing_policy": "missing",
    },
    SIGNAL_SHADOW_FIELD: {
        "field_key": SIGNAL_SHADOW_FIELD,
        "label_zh": "信号日上下影线结构桶",
        "value_type": "bucket",
        "timing": "entry",
        "scope": "signal_strength",
        "bucket_rule": "fixed_explain_bucket",
        "default_in_environment_fit": True,
        "source": "daily_price_cache",
        "missing_policy": "missing",
    },
}

DERIVED_FIELD_CATALOG.update(
    {
        SOURCE_INDEX_FIELD: {
            "field_key": SOURCE_INDEX_FIELD,
            "label_zh": "股票池来源指数",
            "value_type": "category",
            "timing": "entry",
            "scope": "market",
            "bucket_rule": "stock_pool_membership",
            "default_in_environment_fit": True,
            "source": "run_plan.stock_pool_file",
            "missing_policy": "missing",
        },
        SYMBOL_HS300_RS_20D_FIELD: {
            "field_key": SYMBOL_HS300_RS_20D_FIELD,
            "label_zh": "个股20日收益相对沪深300桶",
            "value_type": "bucket",
            "timing": "entry",
            "scope": "momentum",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": True,
            "source": "daily_price_cache+index_snapshot",
            "missing_policy": "missing",
        },
        SYMBOL_CSI500_RS_20D_FIELD: {
            "field_key": SYMBOL_CSI500_RS_20D_FIELD,
            "label_zh": "个股20日收益相对中证500桶",
            "value_type": "bucket",
            "timing": "entry",
            "scope": "momentum",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "daily_price_cache+index_snapshot",
            "missing_policy": "missing",
        },
        SYMBOL_INDUSTRY_RS_20D_FIELD: {
            "field_key": SYMBOL_INDUSTRY_RS_20D_FIELD,
            "label_zh": "个股20日收益相对所属行业桶",
            "value_type": "bucket",
            "timing": "entry",
            "scope": "momentum",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": True,
            "source": "daily_price_cache+industry_index_snapshot",
            "missing_policy": "missing",
        },
        SYMBOL_WEEKLY_KDJ_J_FIELD: {
            "field_key": SYMBOL_WEEKLY_KDJ_J_FIELD,
            "label_zh": "个股周线KDJ J桶",
            "value_type": "bucket",
            "timing": "entry",
            "scope": "weekly",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "daily_price_cache",
            "missing_policy": "missing",
        },
        SYMBOL_WEEKLY_KDJ_STATE_FIELD: {
            "field_key": SYMBOL_WEEKLY_KDJ_STATE_FIELD,
            "label_zh": "个股周线KDJ状态",
            "value_type": "category",
            "timing": "entry",
            "scope": "weekly",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": True,
            "source": "daily_price_cache",
            "missing_policy": "missing",
        },
        SYMBOL_WEEKLY_MA_TREND_FIELD: {
            "field_key": SYMBOL_WEEKLY_MA_TREND_FIELD,
            "label_zh": "个股周线均线趋势桶",
            "value_type": "bucket",
            "timing": "entry",
            "scope": "weekly",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "daily_price_cache",
            "missing_policy": "missing",
        },
        SYMBOL_WEEKLY_CLOSE_VS_MA20_FIELD: {
            "field_key": SYMBOL_WEEKLY_CLOSE_VS_MA20_FIELD,
            "label_zh": "个股周线收盘价相对MA20桶",
            "value_type": "bucket",
            "timing": "entry",
            "scope": "weekly",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "daily_price_cache",
            "missing_policy": "missing",
        },
        INDUSTRY_ATR_20D_FIELD: {
            "field_key": INDUSTRY_ATR_20D_FIELD,
            "label_zh": "行业指数ATR百分比桶",
            "value_type": "bucket",
            "timing": "entry",
            "scope": "industry",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "industry_index_snapshot",
            "missing_policy": "missing",
        },
        INDUSTRY_RETURN_VOL_20D_FIELD: {
            "field_key": INDUSTRY_RETURN_VOL_20D_FIELD,
            "label_zh": "行业指数20日收益波动率桶",
            "value_type": "bucket",
            "timing": "entry",
            "scope": "industry",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "industry_index_snapshot",
            "missing_policy": "missing",
        },
        INDUSTRY_RETURN_VOL_60D_FIELD: {
            "field_key": INDUSTRY_RETURN_VOL_60D_FIELD,
            "label_zh": "行业指数60日收益波动率桶",
            "value_type": "bucket",
            "timing": "entry",
            "scope": "industry",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "industry_index_snapshot",
            "missing_policy": "missing",
        },
        INDUSTRY_NEAR_HIGH_60D_FIELD: {
            "field_key": INDUSTRY_NEAR_HIGH_60D_FIELD,
            "label_zh": "行业指数距60日高点桶",
            "value_type": "bucket",
            "timing": "entry",
            "scope": "industry",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "industry_index_snapshot",
            "missing_policy": "missing",
        },
        INDUSTRY_WEEKLY_KDJ_J_FIELD: {
            "field_key": INDUSTRY_WEEKLY_KDJ_J_FIELD,
            "label_zh": "行业周线KDJ J桶",
            "value_type": "bucket",
            "timing": "entry",
            "scope": "industry",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "industry_index_snapshot",
            "missing_policy": "missing",
        },
        INDUSTRY_WEEKLY_KDJ_STATE_FIELD: {
            "field_key": INDUSTRY_WEEKLY_KDJ_STATE_FIELD,
            "label_zh": "行业周线KDJ状态",
            "value_type": "category",
            "timing": "entry",
            "scope": "industry",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": True,
            "source": "industry_index_snapshot",
            "missing_policy": "missing",
        },
        INDUSTRY_WEEKLY_MA_TREND_FIELD: {
            "field_key": INDUSTRY_WEEKLY_MA_TREND_FIELD,
            "label_zh": "行业周线均线趋势桶",
            "value_type": "bucket",
            "timing": "entry",
            "scope": "industry",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "industry_index_snapshot",
            "missing_policy": "missing",
        },
        INDUSTRY_WEEKLY_RELATIVE_STRENGTH_FIELD: {
            "field_key": INDUSTRY_WEEKLY_RELATIVE_STRENGTH_FIELD,
            "label_zh": "行业周线相对强度分位桶",
            "value_type": "bucket",
            "timing": "entry",
            "scope": "industry",
            "bucket_rule": "industry_weekly_cross_section",
            "default_in_environment_fit": False,
            "source": "industry_index_snapshot",
            "missing_policy": "missing",
        },
    }
)

for market_key, _symbol, label in MARKET_INDEX_SPECS:
    DERIVED_FIELD_CATALOG.update(
        {
            f"market.{market_key}.trend_state": {
                "field_key": f"market.{market_key}.trend_state",
                "label_zh": f"{label}日线趋势状态",
                "value_type": "category",
                "timing": "entry",
                "scope": "market",
                "bucket_rule": "fixed_explain_bucket",
                "default_in_environment_fit": True,
                "source": "index_snapshot",
                "missing_policy": "missing",
            },
            f"market.{market_key}.return_vol_20d_bucket": {
                "field_key": f"market.{market_key}.return_vol_20d_bucket",
                "label_zh": f"{label}20日收益波动率桶",
                "value_type": "bucket",
                "timing": "entry",
                "scope": "market",
                "bucket_rule": "fixed_explain_bucket",
                "default_in_environment_fit": False,
                "source": "index_snapshot",
                "missing_policy": "missing",
            },
            f"market.{market_key}.return_vol_60d_bucket": {
                "field_key": f"market.{market_key}.return_vol_60d_bucket",
                "label_zh": f"{label}60日收益波动率桶",
                "value_type": "bucket",
                "timing": "entry",
                "scope": "market",
                "bucket_rule": "fixed_explain_bucket",
                "default_in_environment_fit": False,
                "source": "index_snapshot",
                "missing_policy": "missing",
            },
            f"market.{market_key}.weekly.kdj_state": {
                "field_key": f"market.{market_key}.weekly.kdj_state",
                "label_zh": f"{label}周线KDJ状态",
                "value_type": "category",
                "timing": "entry",
                "scope": "market",
                "bucket_rule": "fixed_explain_bucket",
                "default_in_environment_fit": True,
                "source": "index_snapshot",
                "missing_policy": "missing",
            },
            f"market.{market_key}.weekly.ma_trend_bucket": {
                "field_key": f"market.{market_key}.weekly.ma_trend_bucket",
                "label_zh": f"{label}周线均线趋势桶",
                "value_type": "bucket",
                "timing": "entry",
                "scope": "market",
                "bucket_rule": "fixed_explain_bucket",
                "default_in_environment_fit": False,
                "source": "index_snapshot",
                "missing_policy": "missing",
            },
            f"market.{market_key}.entry_stage": {
                "field_key": f"market.{market_key}.entry_stage",
                "label_zh": f"{label}入场信号日市场阶段",
                "value_type": "category",
                "timing": "entry",
                "scope": "market_stage",
                "bucket_rule": "close_ma20_ma60_trend_state",
                "default_in_environment_fit": False,
                "source": "index_snapshot",
                "missing_policy": "missing",
            },
            f"market.{market_key}.exit_stage": {
                "field_key": f"market.{market_key}.exit_stage",
                "label_zh": f"{label}出场日市场阶段",
                "value_type": "category",
                "timing": "exit",
                "scope": "market_stage",
                "bucket_rule": "close_ma20_ma60_trend_state",
                "default_in_environment_fit": False,
                "source": "index_snapshot+closed_trade",
                "missing_policy": "missing",
            },
            f"market.{market_key}.entry_to_exit_stage": {
                "field_key": f"market.{market_key}.entry_to_exit_stage",
                "label_zh": f"{label}入场到出场市场阶段迁移",
                "value_type": "category",
                "timing": "post_trade",
                "scope": "market_stage",
                "bucket_rule": "entry_exit_stage_transition",
                "default_in_environment_fit": False,
                "source": "index_snapshot+closed_trade",
                "missing_policy": "missing",
            },
        }
    )

DERIVED_FIELD_CATALOG.update(
    {
        OBJECTIVE_ENTRY_STAGE_FIELD: {
            "field_key": OBJECTIVE_ENTRY_STAGE_FIELD,
            "label_zh": "客观市场阶段-入场信号日",
            "value_type": "category",
            "timing": "entry",
            "scope": "market_stage",
            "bucket_rule": "index_ma250_ma60_drawdown_breadth",
            "default_in_environment_fit": True,
            "source": "index_snapshot+daily_price_cache",
            "missing_policy": "missing",
        },
        OBJECTIVE_EXIT_STAGE_FIELD: {
            "field_key": OBJECTIVE_EXIT_STAGE_FIELD,
            "label_zh": "客观市场阶段-出场日",
            "value_type": "category",
            "timing": "exit",
            "scope": "market_stage",
            "bucket_rule": "index_ma250_ma60_drawdown_breadth",
            "default_in_environment_fit": False,
            "source": "index_snapshot+daily_price_cache+closed_trade",
            "missing_policy": "missing",
        },
        OBJECTIVE_ENTRY_TO_EXIT_STAGE_FIELD: {
            "field_key": OBJECTIVE_ENTRY_TO_EXIT_STAGE_FIELD,
            "label_zh": "客观市场阶段-入场到出场迁移",
            "value_type": "category",
            "timing": "post_trade",
            "scope": "market_stage",
            "bucket_rule": "objective_entry_exit_stage_transition",
            "default_in_environment_fit": True,
            "source": "index_snapshot+daily_price_cache+closed_trade",
            "missing_policy": "missing",
        },
        OBJECTIVE_ENTRY_BREADTH_FIELD: {
            "field_key": OBJECTIVE_ENTRY_BREADTH_FIELD,
            "label_zh": "入场日全A站上MA60股票占比桶",
            "value_type": "bucket",
            "timing": "entry",
            "scope": "market_breadth",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "daily_price_cache",
            "missing_policy": "missing",
        },
        OBJECTIVE_EXIT_BREADTH_FIELD: {
            "field_key": OBJECTIVE_EXIT_BREADTH_FIELD,
            "label_zh": "出场日全A站上MA60股票占比桶",
            "value_type": "bucket",
            "timing": "exit",
            "scope": "market_breadth",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "daily_price_cache+closed_trade",
            "missing_policy": "missing",
        },
        OBJECTIVE_ENTRY_DRAWDOWN_FIELD: {
            "field_key": OBJECTIVE_ENTRY_DRAWDOWN_FIELD,
            "label_zh": "入场日基准指数距250日高点回撤桶",
            "value_type": "bucket",
            "timing": "entry",
            "scope": "market_stage",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "index_snapshot",
            "missing_policy": "missing",
        },
        OBJECTIVE_EXIT_DRAWDOWN_FIELD: {
            "field_key": OBJECTIVE_EXIT_DRAWDOWN_FIELD,
            "label_zh": "出场日基准指数距250日高点回撤桶",
            "value_type": "bucket",
            "timing": "exit",
            "scope": "market_stage",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "index_snapshot+closed_trade",
            "missing_policy": "missing",
        },
        OBJECTIVE_ENTRY_MA60_SLOPE_FIELD: {
            "field_key": OBJECTIVE_ENTRY_MA60_SLOPE_FIELD,
            "label_zh": "入场日基准指数MA60斜率桶",
            "value_type": "bucket",
            "timing": "entry",
            "scope": "market_stage",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "index_snapshot",
            "missing_policy": "missing",
        },
        OBJECTIVE_EXIT_MA60_SLOPE_FIELD: {
            "field_key": OBJECTIVE_EXIT_MA60_SLOPE_FIELD,
            "label_zh": "出场日基准指数MA60斜率桶",
            "value_type": "bucket",
            "timing": "exit",
            "scope": "market_stage",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "index_snapshot+closed_trade",
            "missing_policy": "missing",
        },
        OBJECTIVE_ENTRY_MA250_POSITION_FIELD: {
            "field_key": OBJECTIVE_ENTRY_MA250_POSITION_FIELD,
            "label_zh": "入场日基准指数相对MA250位置",
            "value_type": "category",
            "timing": "entry",
            "scope": "market_stage",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "index_snapshot",
            "missing_policy": "missing",
        },
        OBJECTIVE_EXIT_MA250_POSITION_FIELD: {
            "field_key": OBJECTIVE_EXIT_MA250_POSITION_FIELD,
            "label_zh": "出场日基准指数相对MA250位置",
            "value_type": "category",
            "timing": "exit",
            "scope": "market_stage",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "index_snapshot+closed_trade",
            "missing_policy": "missing",
        },
    }
)

DERIVED_FIELD_CATALOG.update(
    {
        MAX_FAVORABLE_ATR_MULTIPLE_FIELD: {
            "field_key": MAX_FAVORABLE_ATR_MULTIPLE_FIELD,
            "label_zh": "退出前最大浮盈ATR倍数桶",
            "value_type": "bucket",
            "timing": "post_trade",
            "scope": "path",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "daily_price_cache+attribution_reference",
            "missing_policy": "missing",
        },
        MAX_ADVERSE_ATR_MULTIPLE_FIELD: {
            "field_key": MAX_ADVERSE_ATR_MULTIPLE_FIELD,
            "label_zh": "退出前最大浮亏ATR倍数桶",
            "value_type": "bucket",
            "timing": "post_trade",
            "scope": "path",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "daily_price_cache+attribution_reference",
            "missing_policy": "missing",
        },
        REACHED_10PCT_FIELD: {
            "field_key": REACHED_10PCT_FIELD,
            "label_zh": "持仓期是否达到10%浮盈",
            "value_type": "bucket",
            "timing": "post_trade",
            "scope": "path",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "daily_price_cache",
            "missing_policy": "missing",
        },
        REACHED_15PCT_FIELD: {
            "field_key": REACHED_15PCT_FIELD,
            "label_zh": "持仓期是否达到15%浮盈",
            "value_type": "bucket",
            "timing": "post_trade",
            "scope": "path",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "daily_price_cache",
            "missing_policy": "missing",
        },
        POST_EXIT_MAX_HIGH_5D_FIELD: {
            "field_key": POST_EXIT_MAX_HIGH_5D_FIELD,
            "label_zh": "退出后5交易日最大High收益桶",
            "value_type": "bucket",
            "timing": "post_trade",
            "scope": "path",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "daily_price_cache",
            "missing_policy": "missing",
        },
        POST_EXIT_MAX_CLOSE_5D_FIELD: {
            "field_key": POST_EXIT_MAX_CLOSE_5D_FIELD,
            "label_zh": "退出后5交易日最大Close收益桶",
            "value_type": "bucket",
            "timing": "post_trade",
            "scope": "path",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "daily_price_cache",
            "missing_policy": "missing",
        },
        POST_EXIT_MIN_LOW_5D_FIELD: {
            "field_key": POST_EXIT_MIN_LOW_5D_FIELD,
            "label_zh": "退出后5交易日最小Low收益桶",
            "value_type": "bucket",
            "timing": "post_trade",
            "scope": "path",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "daily_price_cache",
            "missing_policy": "missing",
        },
        SOLD_TOO_EARLY_5D_FIELD: {
            "field_key": SOLD_TOO_EARLY_5D_FIELD,
            "label_zh": "止盈后5交易日是否继续上涨",
            "value_type": "bucket",
            "timing": "post_trade",
            "scope": "path",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "daily_price_cache",
            "missing_policy": "missing",
        },
        STOP_LOSS_REBOUND_5D_FIELD: {
            "field_key": STOP_LOSS_REBOUND_5D_FIELD,
            "label_zh": "止损后5交易日是否反弹",
            "value_type": "bucket",
            "timing": "post_trade",
            "scope": "path",
            "bucket_rule": "fixed_explain_bucket",
            "default_in_environment_fit": False,
            "source": "daily_price_cache",
            "missing_policy": "missing",
        },
    }
)


def build_attribution_wide_samples(
    run_dir: str | Path,
    *,
    reference_snapshot: str | Path,
    daily_price_cache_dir: str | Path | None = None,
    snapshot_root: str | Path | None = None,
    industry_source: str = "SW2021",
    max_staleness_trading_days: int = 5,
) -> dict[str, Any]:
    """Build completed-trade attribution wide samples from persisted run artifacts."""

    if max_staleness_trading_days < 0:
        raise ValueError("max_staleness_trading_days must be greater than or equal to 0")

    run_path = Path(run_dir)
    if not run_path.exists():
        raise FileNotFoundError(f"Run artifact directory does not exist: {run_path}")

    run_plan = _as_mapping(_load_json_if_exists(run_path / "run_plan.json"))
    trade_attribution = _as_mapping(_load_json_if_exists(run_path / "trade_attribution.json"))
    trade_lifecycle = _as_mapping(_load_json_if_exists(run_path / "trade_lifecycle.json"))
    reference = _load_reference_snapshot(reference_snapshot)
    reference_rows = _reference_rows_by_symbol_field(reference["rows"])
    field_catalog = _field_catalog(reference)
    field_catalog.update(DERIVED_FIELD_CATALOG)
    completed_trades = _completed_trade_rows(trade_attribution, trade_lifecycle=trade_lifecycle)
    price_context = _load_daily_price_context(daily_price_cache_dir, completed_trades)
    market_breadth_context = _load_market_breadth_context(daily_price_cache_dir)
    industry_context = _load_industry_index_context(snapshot_root, industry_source=industry_source)
    market_context = _load_market_index_context(snapshot_root)
    source_index_by_symbol = _source_index_by_symbol_from_run_plan(run_path, run_plan)

    samples = []
    for trade in completed_trades:
        trade_index = _optional_int(trade.get("trade_index"))
        symbol = _as_str(trade.get("symbol"))
        entry_date = _as_str(trade.get("entry_date"))
        signal_date = _as_str(trade.get("signal_date")) or entry_date
        if trade_index is None or not symbol or not entry_date:
            continue

        field_values: dict[str, dict[str, Any]] = {}
        exception_codes: set[str] = set()
        for field_key in field_catalog:
            if field_key in DERIVED_ONLY_FIELDS:
                continue
            row = _reference_row_for(
                reference_rows.get((symbol, field_key), ()),
                entry_date=signal_date,
                max_staleness_trading_days=max_staleness_trading_days,
            )
            if row is None:
                exception_codes.add("reference_record_missing")
                field_values[field_key] = _missing_field_payload("reference_record_missing")
                continue

            field_exceptions = _exception_codes(row.get("exception_codes"))
            exception_codes.update(field_exceptions)
            field_values[field_key] = {
                "raw": _jsonable(_decode_reference_cell(row.get("value"))),
                "bucket": _jsonable(_decode_reference_cell(row.get("bucket"))),
                "percentile": _optional_float(row.get("percentile")),
                "asof_date": _as_str(row.get("asof_date")) or _as_str(row.get("trade_date")),
                "staleness_trading_days": _optional_int(row.get("staleness_trading_days")),
                "reference_count": _optional_int(row.get("reference_count")),
                "exception_codes": field_exceptions,
            }

        for key, value in _entry_factor_values(trade).items():
            if key not in field_values and key not in field_catalog:
                field_catalog[key] = _fallback_field_catalog_item(key)
            field_values.setdefault(
                key,
                {
                    "raw": value,
                    "bucket": None,
                    "percentile": None,
                    "asof_date": entry_date,
                    "staleness_trading_days": 0,
                    "reference_count": None,
                    "exception_codes": [],
                },
            )

        _add_execution_derived_fields(field_values, trade=trade, signal_date=signal_date)
        _add_trade_path_fields(field_values, trade=trade, price_context=price_context)
        _add_entry_signal_strength_fields(field_values, trade=trade, signal_date=signal_date, price_context=price_context)
        _add_weekly_symbol_fields(field_values, trade=trade, signal_date=signal_date, price_context=price_context)
        _add_industry_index_fields(field_values, signal_date=signal_date, industry_context=industry_context)
        _add_market_source_index_field(
            field_values,
            symbol=symbol,
            signal_date=signal_date,
            source_index_by_symbol=source_index_by_symbol,
        )
        _add_market_index_fields(field_values, signal_date=signal_date, market_context=market_context)
        _add_market_stage_fields(
            field_values,
            signal_date=signal_date,
            exit_date=_as_str(trade.get("exit_date")),
            market_context=market_context,
        )
        _add_objective_market_stage_fields(
            field_values,
            signal_date=signal_date,
            exit_date=_as_str(trade.get("exit_date")),
            market_context=market_context,
            market_breadth_context=market_breadth_context,
        )
        _add_relative_momentum_fields(
            field_values,
            trade=trade,
            signal_date=signal_date,
            price_context=price_context,
            industry_context=industry_context,
            market_context=market_context,
        )
        _add_exit_reason_field(field_values, trade=trade)
        for payload in field_values.values():
            exception_codes.update(_exception_codes(_as_mapping(payload).get("exception_codes")))

        samples.append(
            {
                "trade_index": trade_index,
                "symbol": symbol,
                "signal_date": signal_date,
                "entry_date": entry_date,
                "exit_date": _as_str(trade.get("exit_date")),
                "exit_type": _as_str(trade.get("exit_type")) or "natural",
                "outcome": _as_str(trade.get("outcome")),
                "exit_reason": _as_str(trade.get("exit_reason")),
                "return_pct": _optional_float(trade.get("return_pct")),
                "profit_contribution": _as_mapping(trade.get("profit_contribution")),
                "attribution_exception_codes": sorted(exception_codes),
                "field_values": field_values,
            }
        )

    payload = {
        "schema": ATTRIBUTION_WIDE_SAMPLES_SCHEMA,
        "run_id": _run_id(run_path, run_plan),
        "source_dir": str(run_path),
        "reference_path": str(reference["source_path"]),
        "daily_price_cache_path": str(daily_price_cache_dir) if daily_price_cache_dir is not None else None,
        "industry_index_snapshot_root": str(snapshot_root) if snapshot_root is not None else None,
        "market_index_snapshot_root": str(snapshot_root) if snapshot_root is not None else None,
        "industry_source": industry_source,
        "sample_count": len(samples),
        "field_count": len(field_catalog),
        "environment_fit_default_fields": _environment_default_fields(field_catalog, reference["metadata"]),
        "environment_fit_pair_whitelist": _environment_pair_whitelist(reference["metadata"]),
        "outcome_diagnostic_pair_whitelist": _outcome_diagnostic_pair_whitelist(),
        "samples": samples,
        "reference_metadata": reference["metadata"],
    }
    payload["field_index"] = build_attribution_field_index(payload, field_catalog=field_catalog)
    return payload


def _field_index_value(field_key: str, field_catalog_item: Mapping[str, Any], payload: Mapping[str, Any]) -> Any:
    if _is_bucket_field(field_key, field_catalog_item):
        return payload.get("bucket")
    bucket = payload.get("bucket")
    return bucket if bucket is not None else payload.get("raw")


def _is_bucket_field(field_key: str, field_catalog_item: Mapping[str, Any]) -> bool:
    return field_catalog_item.get("value_type") == "bucket" or str(field_key).endswith("_bucket")


def build_attribution_field_index(
    wide_samples: Mapping[str, Any],
    *,
    field_catalog: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the machine-readable field index from attribution wide samples."""

    samples = [_as_mapping(item) for item in _as_sequence(wide_samples.get("samples"))]
    catalog = {str(k): dict(v) for k, v in (field_catalog or {}).items()}
    for sample in samples:
        for field_key in _as_mapping(sample.get("field_values")):
            catalog.setdefault(str(field_key), _fallback_field_catalog_item(str(field_key)))

    stats = {
        key: {
            "sample_count": 0,
            "missing_count": 0,
            "exception_codes": Counter(),
            "buckets": defaultdict(list),
        }
        for key in catalog
    }
    for sample in samples:
        trade_index = _optional_int(sample.get("trade_index"))
        return_pct = _optional_float(sample.get("return_pct"))
        net_pnl = _optional_float(_as_mapping(sample.get("profit_contribution")).get("net_pnl"))
        for field_key, payload in _as_mapping(sample.get("field_values")).items():
            if field_key not in stats:
                continue
            item = _as_mapping(payload)
            value = _field_index_value(field_key, _as_mapping(catalog.get(field_key)), item)
            value_key = _stable_value_key(value if value is not None else "__missing__")
            stats[field_key]["sample_count"] += 1
            if value is None:
                stats[field_key]["missing_count"] += 1
            for code in _exception_codes(item.get("exception_codes")):
                stats[field_key]["exception_codes"][code] += 1
            stats[field_key]["buckets"][value_key].append(
                {
                    "trade_index": trade_index,
                    "value": value,
                    "return_pct": return_pct,
                    "net_pnl": net_pnl,
                }
            )

    fields = []
    for field_key in sorted(catalog):
        item = catalog[field_key]
        sample_count = int(stats[field_key]["sample_count"])
        missing_count = int(stats[field_key]["missing_count"])
        bucket_distribution = [
            {
                "value": rows[0]["value"] if rows else None,
                "count": len(rows),
                "sample_refs": _representative_refs(rows),
            }
            for _, rows in sorted(
                stats[field_key]["buckets"].items(),
                key=lambda pair: (-len(pair[1]), str(pair[0])),
            )
        ]
        fields.append(
            {
                "field_key": field_key,
                "label_zh": item.get("label_zh", field_key),
                "value_type": item.get("value_type", "value"),
                "timing": item.get("timing", "entry"),
                "scope": item.get("scope", _scope_from_field(field_key)),
                "bucket_rule": item.get("bucket_rule", "reference_snapshot"),
                "default_in_environment_fit": bool(item.get("default_in_environment_fit")),
                "source": item.get("source", "attribution_reference"),
                "missing_policy": item.get("missing_policy", "missing"),
                "coverage_stats": {
                    "sample_count": sample_count,
                    "missing_count": missing_count,
                    "valid_count": sample_count - missing_count,
                    "missing_ratio": missing_count / sample_count if sample_count else None,
                    "exception_count": sum(stats[field_key]["exception_codes"].values()),
                },
                "exception_top_codes": [
                    {"code": code, "count": count}
                    for code, count in stats[field_key]["exception_codes"].most_common()
                ],
                "bucket_distribution": bucket_distribution,
                "sample_refs": _representative_refs(
                    [row for rows in stats[field_key]["buckets"].values() for row in rows]
                ),
            }
        )

    defaults = [
        field["field_key"]
        for field in fields
        if field.get("default_in_environment_fit") is True
    ]
    return {
        "schema": ATTRIBUTION_FIELD_INDEX_SCHEMA,
        "run_id": wide_samples.get("run_id"),
        "source_dir": wide_samples.get("source_dir"),
        "reference_path": wide_samples.get("reference_path"),
        "sample_count": len(samples),
        "field_count": len(fields),
        "environment_fit_default_fields": defaults,
        "environment_fit_pair_whitelist": _environment_pair_whitelist(
            _as_mapping(wide_samples.get("reference_metadata"))
        ),
        "outcome_diagnostic_pair_whitelist": _outcome_diagnostic_pair_whitelist(),
        "fields": fields,
        "ai_usage_rules": [
            "字段缺失必须按 missing 处理，不能补成 false、0 或中性桶。",
            "default_in_environment_fit 表示第一版默认进入 environment_fit.enriched 的单因子统计。",
            "environment_fit_pair_whitelist 只声明入场前或入场时可见因子的默认二因子组合，三因子以上不在第一版默认输出。",
            "timing=post_trade 或 exit 的字段用于事后诊断归因；只有显式 default_in_environment_fit=true 的字段才进入默认 environment_fit 排名。",
        ],
    }


def write_attribution_wide_samples(
    wide_samples: Mapping[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path, Path, Path]:
    """Write wide sample JSON/CSV and field index JSON/Markdown."""

    target_dir = Path(output_dir) if output_dir is not None else Path(str(wide_samples["source_dir"]))
    target_dir.mkdir(parents=True, exist_ok=True)
    field_index = _as_mapping(wide_samples.get("field_index")) or build_attribution_field_index(wide_samples)

    wide_path = target_dir / DEFAULT_WIDE_SAMPLE_JSON
    csv_path = target_dir / DEFAULT_WIDE_SAMPLE_CSV
    index_path = target_dir / DEFAULT_FIELD_INDEX_JSON
    markdown_path = target_dir / DEFAULT_FIELD_INDEX_MARKDOWN

    wide_path.write_text(_to_pretty_json(dict(wide_samples, field_index=field_index)), encoding="utf-8")
    _write_wide_csv(_as_sequence(wide_samples.get("samples")), _field_keys(field_index), csv_path)
    index_path.write_text(_to_pretty_json(field_index), encoding="utf-8")
    markdown_path.write_text(render_attribution_field_index_markdown_zh(field_index), encoding="utf-8")
    return wide_path, csv_path, index_path, markdown_path


def render_attribution_field_index_markdown_zh(index: Mapping[str, Any]) -> str:
    """Render attribution field index as Chinese Markdown."""

    fields = [_as_mapping(item) for item in _as_sequence(index.get("fields"))]
    low_coverage = sorted(
        fields,
        key=lambda item: (
            -float(_as_mapping(item.get("coverage_stats")).get("missing_ratio") or 0.0),
            -int(_as_mapping(item.get("coverage_stats")).get("exception_count") or 0),
            str(item.get("field_key")),
        ),
    )
    default_fields = set(str(item) for item in _as_sequence(index.get("environment_fit_default_fields")))
    lines = [
        "# 归因字段索引",
        "",
        f"- schema: `{index.get('schema')}`",
        f"- run_id: `{index.get('run_id')}`",
        f"- sample_count: `{index.get('sample_count')}`",
        f"- field_count: `{index.get('field_count')}`",
        "",
        "## 覆盖率和异常优先检查",
        "",
        "| 字段 | 样本 | 缺失 | 缺失率 | 异常 | 默认进入 environment_fit | Top桶 |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for field in low_coverage:
        coverage = _as_mapping(field.get("coverage_stats"))
        lines.append(
            "| "
            f"`{field.get('field_key')}` | "
            f"{coverage.get('sample_count')} | "
            f"{coverage.get('missing_count')} | "
            f"{_format_percent(coverage.get('missing_ratio'))} | "
            f"{coverage.get('exception_count')} | "
            f"{'是' if field.get('field_key') in default_fields else '否'} | "
            f"{_escape_cell(_top_bucket(field))} |"
        )

    lines.extend(["", "## 默认进入 environment_fit", ""])
    for field_key in sorted(default_fields):
        lines.append(f"- `{field_key}`")

    lines.extend(["", "## 候选但未默认进入", ""])
    for field in fields:
        field_key = str(field.get("field_key"))
        if field_key not in default_fields:
            lines.append(f"- `{field_key}`")

    diagnostic_fields = [
        field
        for field in fields
        if str(field.get("timing")) in {"exit", "post_trade"} or str(field.get("field_key")).startswith("trade.")
    ]
    if diagnostic_fields:
        lines.extend(["", "## 事后诊断字段（不进入 environment_fit）", ""])
        for field in diagnostic_fields:
            lines.append(f"- `{field.get('field_key')}`: {field.get('label_zh', field.get('field_key'))}")

    outcome_pairs = _as_sequence(index.get("outcome_diagnostic_pair_whitelist"))
    if outcome_pairs:
        lines.extend(["", "## outcome_diagnostic 二因子白名单", ""])
        for pair in outcome_pairs:
            parts = [str(part) for part in _as_sequence(pair)]
            if len(parts) == 2:
                lines.append(f"- `{parts[0]}` x `{parts[1]}`")

    lines.extend(["", "## AI 使用规则"])
    for rule in _as_sequence(index.get("ai_usage_rules")):
        lines.append(f"- {rule}")
    lines.append("")
    return "\n".join(lines)


def load_attribution_wide_samples(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    """Load attribution_wide_samples.json from a file, directory, or payload."""

    if isinstance(source, Mapping):
        payload = dict(source)
    else:
        path = Path(source)
        if path.is_dir():
            path = path / DEFAULT_WIDE_SAMPLE_JSON
        if not path.exists():
            raise FileNotFoundError(f"attribution wide samples not found: {path}")
        payload = _as_mapping(_load_json_if_exists(path))
    if payload.get("schema") != ATTRIBUTION_WIDE_SAMPLES_SCHEMA:
        raise ValueError(f"invalid attribution wide samples schema: {payload.get('schema')}")
    return payload


def load_attribution_field_index(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    """Load attribution_field_index.json from a file, directory, or payload."""

    if isinstance(source, Mapping):
        payload = dict(source)
    else:
        path = Path(source)
        if path.is_dir():
            path = path / DEFAULT_FIELD_INDEX_JSON
        if not path.exists():
            raise FileNotFoundError(f"attribution field index not found: {path}")
        payload = _as_mapping(_load_json_if_exists(path))
    if payload.get("schema") != ATTRIBUTION_FIELD_INDEX_SCHEMA:
        raise ValueError(f"invalid attribution field index schema: {payload.get('schema')}")
    return payload


def _completed_trade_rows(
    trade_attribution: Mapping[str, Any],
    *,
    trade_lifecycle: Mapping[str, Any],
) -> list[dict[str, Any]]:
    lifecycle_by_index = {
        int(row["trade_index"]): _as_mapping(row)
        for row in _as_sequence(trade_lifecycle.get("lifecycles"))
        if _as_mapping(row).get("trade_index") is not None
    }
    rows = []
    for attribution in _as_sequence(trade_attribution.get("attributions")):
        trade = dict(_as_mapping(attribution))
        trade_index = _optional_int(trade.get("trade_index"))
        lifecycle = lifecycle_by_index.get(trade_index, {}) if trade_index is not None else {}
        trade["profit_contribution"] = _profit_contribution(lifecycle)
        trade.update(_entry_lifecycle_context(lifecycle))
        rows.append(trade)
    return rows


def _entry_lifecycle_context(lifecycle: Mapping[str, Any]) -> dict[str, Any]:
    result = {
        "signal_date": None,
        "signal_close": None,
        "signal_ma60": None,
        "entry_price": _optional_float(lifecycle.get("entry_price")),
        "entry_execution_price": None,
    }
    for event in _as_sequence(lifecycle.get("events")):
        row = _as_mapping(event)
        if str(row.get("event_type")) != "entry":
            continue
        values = _as_mapping(row.get("values"))
        result["signal_date"] = _as_str(values.get("signal_trade_date")) or None
        result["signal_close"] = _optional_float(values.get("close"))
        result["signal_ma60"] = _optional_float(values.get("ma60"))
        for execution in _as_sequence(row.get("executions")):
            execution_row = _as_mapping(execution)
            if str(execution_row.get("event_type", "")).lower() != "completed":
                continue
            result["entry_execution_price"] = _optional_float(execution_row.get("executed_price"))
            break
        break
    if result["entry_price"] is None:
        result["entry_price"] = result["entry_execution_price"]
    return result


def _profit_contribution(lifecycle: Mapping[str, Any]) -> dict[str, Any]:
    buy = 0.0
    sell = 0.0
    commission = 0.0
    for event in _as_sequence(lifecycle.get("events")):
        for execution in _as_sequence(_as_mapping(event).get("executions")):
            row = _as_mapping(execution)
            if str(row.get("event_type", "")).lower() != "completed":
                continue
            gross = _optional_float(row.get("gross_value"))
            if gross is None:
                quantity = _optional_float(row.get("executed_quantity"))
                price = _optional_float(row.get("executed_price"))
                gross = abs(quantity * price) if quantity is not None and price is not None else None
            if gross is None:
                continue
            side = str(row.get("side", "")).lower()
            if side == "buy":
                buy += abs(gross)
            elif side == "sell":
                sell += abs(gross)
            commission += _optional_float(row.get("commission")) or 0.0
    available = buy > 0 and sell > 0
    net_pnl = sell - buy - commission if available else None
    return {
        "contribution_available": available,
        "entry_gross_value": buy if buy else None,
        "exit_gross_value": sell if sell else None,
        "net_pnl": net_pnl,
        "total_commission": commission if commission else None,
        "return_on_entry_value": net_pnl / buy if net_pnl is not None and buy else None,
    }


def _entry_factor_values(trade: Mapping[str, Any]) -> dict[str, Any]:
    event = _as_mapping(trade.get("entry"))
    values = {}
    for factor in _as_sequence(event.get("factors")):
        item = _as_mapping(factor)
        if item.get("missing") is True or item.get("key") is None:
            continue
        values[str(item["key"])] = _jsonable(item.get("value"))
    return values


def _source_index_by_symbol_from_run_plan(run_path: Path, run_plan: Mapping[str, Any]) -> dict[str, str]:
    data = _as_mapping(run_plan.get("data"))
    stock_pool_file = _as_str(data.get("stock_pool_file"))
    if not stock_pool_file:
        return {}
    raw_path = Path(stock_pool_file)
    candidates = [raw_path] if raw_path.is_absolute() else [
        Path.cwd() / raw_path,
        run_path / raw_path,
        run_path.parent / raw_path,
    ]
    path = next((candidate for candidate in candidates if candidate.exists()), None)
    if path is None:
        return {}
    frame = pd.read_csv(path)
    symbol_column = next((column for column in ("ts_code", "symbol", "code") if column in frame.columns), None)
    source_column = next((column for column in ("source_index", "index", "source") if column in frame.columns), None)
    if symbol_column is None or source_column is None:
        return {}
    result = {}
    for row in frame[[symbol_column, source_column]].dropna().itertuples(index=False):
        symbol = str(row[0]).strip()
        source = str(row[1]).strip()
        if symbol and source:
            result[symbol] = source
    return result


def _load_daily_price_context(
    daily_price_cache_dir: str | Path | None,
    trades: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if daily_price_cache_dir is None:
        return {}
    root = Path(daily_price_cache_dir)
    daily_dir = root / "daily" if (root / "daily").exists() else root
    if not daily_dir.exists():
        return {}
    symbols = {
        _as_str(trade.get("symbol"))
        for trade in trades
        if _as_str(trade.get("symbol"))
    }
    if not symbols:
        return {}

    frames = []
    for path in sorted(daily_dir.glob("*.parquet")):
        frame = pd.read_parquet(path)
        if "symbol" not in frame.columns and "ts_code" in frame.columns:
            frame = frame.rename(columns={"ts_code": "symbol"})
        required = {"symbol", "trade_date", "open", "high", "low", "close"}
        if not required.issubset(frame.columns):
            continue
        frame = frame[["symbol", "trade_date", "open", "high", "low", "close"]]
        frame = frame[frame["symbol"].astype(str).isin(symbols)]
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return {}

    data = pd.concat(frames, ignore_index=True)
    data["symbol"] = data["symbol"].astype(str)
    data["trade_date"] = pd.to_datetime(data["trade_date"]).dt.strftime("%Y-%m-%d")
    for column in ("open", "high", "low", "close"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=["symbol", "trade_date", "open", "high", "low", "close"])
    data = data.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    grouped = data.groupby("symbol", sort=False)
    data["return_20d"] = grouped["close"].pct_change(20)
    data["return_60d"] = grouped["close"].pct_change(60)
    data["ma25"] = grouped["close"].transform(lambda value: value.rolling(25, min_periods=25).mean())
    data["ma60"] = grouped["close"].transform(lambda value: value.rolling(60, min_periods=60).mean())
    data["ma60_20d_ago"] = grouped["ma60"].shift(20)
    data["ma60_slope_20d"] = data["ma60"] / data["ma60_20d_ago"] - 1.0
    ema12 = grouped["close"].transform(lambda value: value.ewm(span=12, adjust=False).mean())
    ema26 = grouped["close"].transform(lambda value: value.ewm(span=26, adjust=False).mean())
    data["macd_dif"] = ema12 - ema26
    data["macd_dea"] = data.groupby("symbol", sort=False)["macd_dif"].transform(
        lambda value: value.ewm(span=9, adjust=False).mean()
    )
    data["macd_bar"] = 2.0 * (data["macd_dif"] - data["macd_dea"])

    by_symbol = {
        str(symbol): group.reset_index(drop=True)
        for symbol, group in data.groupby("symbol", sort=False)
    }
    by_symbol_date = {
        (str(row.symbol), str(row.trade_date)): row._asdict()
        for row in data.itertuples(index=False)
    }
    weekly = _weekly_feature_frame(data)
    weekly_by_symbol = {
        str(symbol): group.reset_index(drop=True)
        for symbol, group in weekly.groupby("symbol", sort=False)
    } if not weekly.empty else {}
    return {
        "source_path": str(daily_dir),
        "by_symbol": by_symbol,
        "by_symbol_date": by_symbol_date,
        "weekly_by_symbol": weekly_by_symbol,
    }


def _load_market_breadth_context(daily_price_cache_dir: str | Path | None) -> dict[str, Any]:
    if daily_price_cache_dir is None:
        return {}
    root = Path(daily_price_cache_dir)
    daily_dir = root / "daily" if (root / "daily").exists() else root
    if not daily_dir.exists():
        return {}

    frames = []
    for path in sorted(daily_dir.glob("*.parquet")):
        frame = pd.read_parquet(path)
        if "symbol" not in frame.columns and "ts_code" in frame.columns:
            frame = frame.rename(columns={"ts_code": "symbol"})
        required = {"symbol", "trade_date", "close"}
        if not required.issubset(frame.columns):
            continue
        frame = frame[["symbol", "trade_date", "close"]]
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return {"source_path": str(daily_dir)}

    data = pd.concat(frames, ignore_index=True)
    data["symbol"] = data["symbol"].astype(str)
    data["trade_date"] = pd.to_datetime(data["trade_date"]).dt.strftime("%Y-%m-%d")
    data["close"] = pd.to_numeric(data["close"], errors="coerce")
    data = data.dropna(subset=["symbol", "trade_date", "close"])
    data = data.drop_duplicates(subset=["symbol", "trade_date"], keep="last")
    data = data.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    grouped = data.groupby("symbol", sort=False)
    data["ma60"] = grouped["close"].transform(lambda value: value.rolling(60, min_periods=60).mean())
    valid = data.dropna(subset=["ma60"]).copy()
    if valid.empty:
        return {"source_path": str(daily_dir), "by_date": {}}

    valid["above_ma60"] = valid["close"] > valid["ma60"]
    breadth = (
        valid.groupby("trade_date", sort=True)
        .agg(
            ma60_above_ratio=("above_ma60", "mean"),
            symbol_count=("symbol", "nunique"),
            ma60_above_count=("above_ma60", "sum"),
        )
        .reset_index()
    )
    by_date = {
        str(row.trade_date): {
            "trade_date": str(row.trade_date),
            "ma60_above_ratio": float(row.ma60_above_ratio),
            "symbol_count": int(row.symbol_count),
            "ma60_above_count": int(row.ma60_above_count),
        }
        for row in breadth.itertuples(index=False)
    }
    return {"source_path": str(daily_dir), "by_date": by_date}


def _load_industry_index_context(
    snapshot_root: str | Path | None,
    *,
    industry_source: str,
) -> dict[str, Any]:
    if snapshot_root is None:
        return {}
    index_dir = Path(snapshot_root) / "industries" / "sw" / industry_source / "index_bars"
    if not index_dir.exists():
        return {}

    frames = []
    for path in sorted(index_dir.glob("*.parquet")):
        frame = pd.read_parquet(path)
        if "symbol" not in frame.columns and "ts_code" in frame.columns:
            frame = frame.rename(columns={"ts_code": "symbol"})
        required = {"symbol", "trade_date", "open", "high", "low", "close"}
        if not required.issubset(frame.columns):
            continue
        frame = frame[["symbol", "trade_date", "open", "high", "low", "close"]]
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return {"source_path": str(index_dir)}

    data = pd.concat(frames, ignore_index=True)
    data["symbol"] = data["symbol"].astype(str)
    data["trade_date"] = pd.to_datetime(data["trade_date"]).dt.strftime("%Y-%m-%d")
    for column in ("open", "high", "low", "close"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=["symbol", "trade_date", "open", "high", "low", "close"])
    data = data.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    grouped = data.groupby("symbol", sort=False)
    data["return_1d"] = grouped["close"].pct_change()
    data["return_20d"] = grouped["close"].pct_change(20)
    data["return_60d"] = grouped["close"].pct_change(60)
    data["return_vol_20d"] = grouped["return_1d"].transform(lambda value: value.rolling(20, min_periods=20).std())
    data["return_vol_60d"] = grouped["return_1d"].transform(lambda value: value.rolling(60, min_periods=60).std())
    data["prev_close"] = grouped["close"].shift(1)
    true_range = pd.concat(
        [
            data["high"] - data["low"],
            (data["high"] - data["prev_close"]).abs(),
            (data["low"] - data["prev_close"]).abs(),
        ],
        axis=1,
    ).max(axis=1)
    data["true_range"] = true_range
    data["atr_20d"] = grouped["true_range"].transform(lambda value: value.rolling(20, min_periods=20).mean())
    data["atr_pct"] = data["atr_20d"] / data["close"]
    data["rolling_high_60d"] = grouped["high"].transform(lambda value: value.rolling(60, min_periods=60).max())
    data["near_high_60d"] = data["close"] / data["rolling_high_60d"] - 1.0

    weekly = _weekly_feature_frame(data)
    if not weekly.empty:
        weekly["return_4w"] = weekly.groupby("symbol", sort=False)["close"].pct_change(4)
        weekly["relative_strength_percentile"] = weekly.groupby("trade_date", sort=False)["return_4w"].rank(
            pct=True,
            method="average",
        )

    return {
        "source_path": str(index_dir),
        "by_symbol": {
            str(symbol): group.reset_index(drop=True)
            for symbol, group in data.groupby("symbol", sort=False)
        },
        "weekly_by_symbol": {
            str(symbol): group.reset_index(drop=True)
            for symbol, group in weekly.groupby("symbol", sort=False)
        } if not weekly.empty else {},
    }


def _load_market_index_context(snapshot_root: str | Path | None) -> dict[str, Any]:
    if snapshot_root is None:
        return {}
    index_dir = Path(snapshot_root) / "indexes"
    if not index_dir.exists():
        return {}

    wanted = {symbol for _key, symbol, _label in OBJECTIVE_PRIMARY_INDEX_SPECS}
    frames = []
    for _key, symbol, _label in OBJECTIVE_PRIMARY_INDEX_SPECS:
        safe_symbol = symbol.replace(".", "_")
        for path in sorted(index_dir.glob(f"{safe_symbol}_*.parquet")):
            frame = pd.read_parquet(path)
            if "symbol" not in frame.columns and "ts_code" in frame.columns:
                frame = frame.rename(columns={"ts_code": "symbol"})
            required = {"symbol", "trade_date", "open", "high", "low", "close"}
            if not required.issubset(frame.columns):
                continue
            frame = frame[["symbol", "trade_date", "open", "high", "low", "close"]]
            frame = frame[frame["symbol"].astype(str).isin(wanted)]
            if not frame.empty:
                frames.append(frame)
    if not frames:
        return {"source_path": str(index_dir)}

    data = pd.concat(frames, ignore_index=True)
    data["symbol"] = data["symbol"].astype(str)
    data["trade_date"] = pd.to_datetime(data["trade_date"]).dt.strftime("%Y-%m-%d")
    for column in ("open", "high", "low", "close"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=["symbol", "trade_date", "open", "high", "low", "close"])
    data = data.drop_duplicates(subset=["symbol", "trade_date"], keep="last")
    data = data.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    grouped = data.groupby("symbol", sort=False)
    data["return_1d"] = grouped["close"].pct_change()
    data["return_20d"] = grouped["close"].pct_change(20)
    data["return_60d"] = grouped["close"].pct_change(60)
    data["return_vol_20d"] = grouped["return_1d"].transform(lambda value: value.rolling(20, min_periods=20).std())
    data["return_vol_60d"] = grouped["return_1d"].transform(lambda value: value.rolling(60, min_periods=60).std())
    data["ma20"] = grouped["close"].transform(lambda value: value.rolling(20, min_periods=20).mean())
    data["ma60"] = grouped["close"].transform(lambda value: value.rolling(60, min_periods=60).mean())
    data["ma250"] = grouped["close"].transform(lambda value: value.rolling(250, min_periods=250).mean())
    data["ma60_20d_ago"] = grouped["ma60"].shift(20)
    data["ma60_slope_20d"] = data["ma60"] / data["ma60_20d_ago"] - 1.0
    data["rolling_high_250d"] = grouped["high"].transform(lambda value: value.rolling(250, min_periods=250).max())
    data["drawdown_250d"] = data["close"] / data["rolling_high_250d"] - 1.0
    data["trend_state"] = [_daily_trend_state(row) for row in data[["close", "ma20", "ma60"]].to_dict("records")]

    weekly = _weekly_feature_frame(data)
    return {
        "source_path": str(index_dir),
        "by_symbol": {
            str(symbol): group.reset_index(drop=True)
            for symbol, group in data.groupby("symbol", sort=False)
        },
        "weekly_by_symbol": {
            str(symbol): group.reset_index(drop=True)
            for symbol, group in weekly.groupby("symbol", sort=False)
        } if not weekly.empty else {},
    }


def _weekly_feature_frame(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame()
    source = data[["symbol", "trade_date", "open", "high", "low", "close"]].copy()
    source["_trade_date_dt"] = pd.to_datetime(source["trade_date"])
    iso = source["_trade_date_dt"].dt.isocalendar()
    source["_iso_year"] = iso.year.astype(int)
    source["_iso_week"] = iso.week.astype(int)
    source = source.sort_values(["symbol", "_trade_date_dt"]).reset_index(drop=True)
    weekly = (
        source.groupby(["symbol", "_iso_year", "_iso_week"], sort=False)
        .agg(
            trade_date=("trade_date", "last"),
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
        )
        .reset_index()
        .drop(columns=["_iso_year", "_iso_week"])
    )
    if weekly.empty:
        return weekly

    frames = []
    for _, group in weekly.groupby("symbol", sort=False):
        item = group.reset_index(drop=True).copy()
        kdj_values = calculate_kdj(
            item["high"].astype(float).tolist(),
            item["low"].astype(float).tolist(),
            item["close"].astype(float).tolist(),
        )
        item["kdj_k"] = [value.k for value in kdj_values]
        item["kdj_d"] = [value.d for value in kdj_values]
        item["kdj_j"] = [value.j for value in kdj_values]
        item["ma5"] = item["close"].rolling(5, min_periods=5).mean()
        item["ma10"] = item["close"].rolling(10, min_periods=10).mean()
        item["ma20"] = item["close"].rolling(20, min_periods=20).mean()
        item["close_vs_ma20"] = item["close"] / item["ma20"] - 1.0
        item["ma_trend"] = [
            _weekly_ma_trend(row)
            for row in item[["close", "ma5", "ma10", "ma20"]].to_dict("records")
        ]
        frames.append(item)
    return pd.concat(frames, ignore_index=True).sort_values(["symbol", "trade_date"]).reset_index(drop=True)


def _add_trade_path_fields(
    field_values: dict[str, dict[str, Any]],
    *,
    trade: Mapping[str, Any],
    price_context: Mapping[str, Any],
) -> None:
    symbol = _as_str(trade.get("symbol"))
    entry_date = _as_str(trade.get("entry_date"))
    exit_date = _as_str(trade.get("exit_date"))
    entry_price = _optional_float(trade.get("entry_price")) or _optional_float(trade.get("entry_execution_price"))
    asof_date = exit_date or entry_date
    rows = _price_rows_for_trade(price_context, symbol=symbol, entry_date=entry_date, exit_date=exit_date)
    if rows is None or rows.empty or entry_price is None or entry_price <= 0:
        for field_key in (
            HOLDING_DAYS_FIELD,
            MAX_FAVORABLE_FIELD,
            MAX_ADVERSE_FIELD,
            MAX_DRAWDOWN_FIELD,
            FIRST_PROFIT_5PCT_FIELD,
            MAX_FAVORABLE_ATR_MULTIPLE_FIELD,
            MAX_ADVERSE_ATR_MULTIPLE_FIELD,
            REACHED_10PCT_FIELD,
            REACHED_15PCT_FIELD,
            POST_EXIT_MAX_HIGH_5D_FIELD,
            POST_EXIT_MAX_CLOSE_5D_FIELD,
            POST_EXIT_MIN_LOW_5D_FIELD,
            SOLD_TOO_EARLY_5D_FIELD,
            STOP_LOSS_REBOUND_5D_FIELD,
        ):
            field_values[field_key] = _derived_payload(
                raw=None,
                bucket=None,
                asof_date=asof_date,
                reference_count=None,
                exception_codes=["path_price_missing"],
            )
        return

    holding_days = int(len(rows))
    high = pd.to_numeric(rows["high"], errors="coerce")
    low = pd.to_numeric(rows["low"], errors="coerce")
    max_favorable = _optional_float(high.max()) / entry_price - 1.0 if not high.empty and pd.notna(high.max()) else None
    max_adverse = _optional_float(low.min()) / entry_price - 1.0 if not low.empty and pd.notna(low.min()) else None

    peak = None
    max_drawdown = 0.0
    for row in rows.itertuples(index=False):
        row_high = _optional_float(getattr(row, "high", None))
        row_low = _optional_float(getattr(row, "low", None))
        if row_high is None or row_low is None or row_high <= 0:
            continue
        peak = row_high if peak is None else max(peak, row_high)
        if peak and peak > 0:
            max_drawdown = max(max_drawdown, max(0.0, 1.0 - row_low / peak))

    first_profit_day = None
    target = entry_price * 1.05
    for index, row in enumerate(rows.itertuples(index=False), start=1):
        row_high = _optional_float(getattr(row, "high", None))
        if row_high is not None and row_high >= target:
            first_profit_day = index
            break

    field_values[HOLDING_DAYS_FIELD] = _derived_payload(
        raw=holding_days,
        bucket=_holding_days_bucket(holding_days),
        asof_date=asof_date,
        reference_count=holding_days,
        exception_codes=[],
    )
    field_values[MAX_FAVORABLE_FIELD] = _derived_payload(
        raw=max_favorable,
        bucket=_max_favorable_bucket(max_favorable),
        asof_date=asof_date,
        reference_count=holding_days,
        exception_codes=[] if max_favorable is not None else ["path_price_missing"],
    )
    field_values[MAX_ADVERSE_FIELD] = _derived_payload(
        raw=max_adverse,
        bucket=_max_adverse_bucket(max_adverse),
        asof_date=asof_date,
        reference_count=holding_days,
        exception_codes=[] if max_adverse is not None else ["path_price_missing"],
    )
    field_values[MAX_DRAWDOWN_FIELD] = _derived_payload(
        raw=max_drawdown,
        bucket=_drawdown_bucket(max_drawdown),
        asof_date=asof_date,
        reference_count=holding_days,
        exception_codes=[],
    )
    field_values[FIRST_PROFIT_5PCT_FIELD] = _derived_payload(
        raw=first_profit_day,
        bucket=_first_profit_days_bucket(first_profit_day),
        asof_date=asof_date,
        reference_count=holding_days,
        exception_codes=[],
    )

    atr_pct = _optional_float(_as_mapping(field_values.get("entry.volatility.atr_20d_bucket")).get("raw"))
    favorable_atr = max_favorable / atr_pct if max_favorable is not None and atr_pct and atr_pct > 0 else None
    adverse_atr = max_adverse / atr_pct if max_adverse is not None and atr_pct and atr_pct > 0 else None
    field_values[MAX_FAVORABLE_ATR_MULTIPLE_FIELD] = _derived_payload(
        raw=favorable_atr,
        bucket=_path_atr_multiple_bucket(favorable_atr),
        asof_date=asof_date,
        reference_count=holding_days,
        exception_codes=[] if favorable_atr is not None else ["atr_path_multiple_missing"],
    )
    field_values[MAX_ADVERSE_ATR_MULTIPLE_FIELD] = _derived_payload(
        raw=adverse_atr,
        bucket=_path_atr_multiple_bucket(adverse_atr),
        asof_date=asof_date,
        reference_count=holding_days,
        exception_codes=[] if adverse_atr is not None else ["atr_path_multiple_missing"],
    )
    field_values[REACHED_10PCT_FIELD] = _derived_payload(
        raw=(max_favorable is not None and max_favorable >= 0.10),
        bucket=_threshold_reached_bucket(max_favorable, threshold=0.10),
        asof_date=asof_date,
        reference_count=holding_days,
        exception_codes=[] if max_favorable is not None else ["path_price_missing"],
    )
    field_values[REACHED_15PCT_FIELD] = _derived_payload(
        raw=(max_favorable is not None and max_favorable >= 0.15),
        bucket=_threshold_reached_bucket(max_favorable, threshold=0.15),
        asof_date=asof_date,
        reference_count=holding_days,
        exception_codes=[] if max_favorable is not None else ["path_price_missing"],
    )

    _add_post_exit_path_fields(
        field_values,
        trade=trade,
        price_context=price_context,
        exit_date=exit_date,
        exit_price=_optional_float(trade.get("exit_price")),
    )


def _add_post_exit_path_fields(
    field_values: dict[str, dict[str, Any]],
    *,
    trade: Mapping[str, Any],
    price_context: Mapping[str, Any],
    exit_date: str,
    exit_price: float | None,
) -> None:
    symbol = _as_str(trade.get("symbol"))
    asof_date = exit_date or _as_str(trade.get("entry_date"))
    rows = _post_exit_price_rows(price_context, symbol=symbol, exit_date=exit_date, limit=5)
    if exit_price is None:
        exit_row = _as_mapping(_price_row_for(price_context, symbol=symbol, trade_date=exit_date))
        exit_price = _optional_float(exit_row.get("close"))
    if rows is None or rows.empty or exit_price is None or exit_price <= 0:
        for field_key in (
            POST_EXIT_MAX_HIGH_5D_FIELD,
            POST_EXIT_MAX_CLOSE_5D_FIELD,
            POST_EXIT_MIN_LOW_5D_FIELD,
            SOLD_TOO_EARLY_5D_FIELD,
            STOP_LOSS_REBOUND_5D_FIELD,
        ):
            field_values[field_key] = _derived_payload(
                raw=None,
                bucket=None,
                asof_date=asof_date,
                reference_count=0,
                exception_codes=["post_exit_price_missing"],
            )
        return

    high = pd.to_numeric(rows["high"], errors="coerce")
    close = pd.to_numeric(rows["close"], errors="coerce")
    low = pd.to_numeric(rows["low"], errors="coerce")
    max_high_return = _optional_float(high.max()) / exit_price - 1.0 if not high.empty and pd.notna(high.max()) else None
    max_close_return = _optional_float(close.max()) / exit_price - 1.0 if not close.empty and pd.notna(close.max()) else None
    min_low_return = _optional_float(low.min()) / exit_price - 1.0 if not low.empty and pd.notna(low.min()) else None
    reference_count = int(len(rows))
    exit_reason = _as_str(trade.get("exit_reason"))
    sold_too_early = exit_reason == "BAOMA_MA25_PROFIT_EXIT_TRIGGERED" and max_high_return is not None and max_high_return >= 0.05
    stop_rebound = exit_reason == "BAOMA_MA60_STOP_TRIGGERED" and max_high_return is not None and max_high_return >= 0.05

    field_values[POST_EXIT_MAX_HIGH_5D_FIELD] = _derived_payload(
        raw=max_high_return,
        bucket=_signed_return_bucket(max_high_return),
        asof_date=asof_date,
        reference_count=reference_count,
        exception_codes=[] if max_high_return is not None else ["post_exit_price_missing"],
    )
    field_values[POST_EXIT_MAX_CLOSE_5D_FIELD] = _derived_payload(
        raw=max_close_return,
        bucket=_signed_return_bucket(max_close_return),
        asof_date=asof_date,
        reference_count=reference_count,
        exception_codes=[] if max_close_return is not None else ["post_exit_price_missing"],
    )
    field_values[POST_EXIT_MIN_LOW_5D_FIELD] = _derived_payload(
        raw=min_low_return,
        bucket=_signed_return_bucket(min_low_return),
        asof_date=asof_date,
        reference_count=reference_count,
        exception_codes=[] if min_low_return is not None else ["post_exit_price_missing"],
    )
    field_values[SOLD_TOO_EARLY_5D_FIELD] = _derived_payload(
        raw=sold_too_early if exit_reason == "BAOMA_MA25_PROFIT_EXIT_TRIGGERED" else None,
        bucket=_diagnostic_bool_bucket(sold_too_early) if exit_reason == "BAOMA_MA25_PROFIT_EXIT_TRIGGERED" else None,
        asof_date=asof_date,
        reference_count=reference_count,
        exception_codes=[] if exit_reason == "BAOMA_MA25_PROFIT_EXIT_TRIGGERED" else ["not_take_profit_exit"],
    )
    field_values[STOP_LOSS_REBOUND_5D_FIELD] = _derived_payload(
        raw=stop_rebound if exit_reason == "BAOMA_MA60_STOP_TRIGGERED" else None,
        bucket=_diagnostic_bool_bucket(stop_rebound) if exit_reason == "BAOMA_MA60_STOP_TRIGGERED" else None,
        asof_date=asof_date,
        reference_count=reference_count,
        exception_codes=[] if exit_reason == "BAOMA_MA60_STOP_TRIGGERED" else ["not_stop_loss_exit"],
    )


def _add_entry_signal_strength_fields(
    field_values: dict[str, dict[str, Any]],
    *,
    trade: Mapping[str, Any],
    signal_date: str,
    price_context: Mapping[str, Any],
) -> None:
    entry_factors = _entry_factor_values(trade)
    signal_row = _as_mapping(
        _price_row_for(price_context, symbol=_as_str(trade.get("symbol")), trade_date=signal_date)
    )
    signal_close = (
        _optional_float(signal_row.get("close"))
        or _optional_float(trade.get("signal_close"))
        or _optional_float(entry_factors.get("symbol.close"))
    )
    signal_open = _optional_float(signal_row.get("open")) or _optional_float(entry_factors.get("symbol.open"))
    signal_ma60 = (
        _optional_float(trade.get("signal_ma60"))
        or _optional_float(entry_factors.get("symbol.ma.ma60"))
        or _optional_float(signal_row.get("ma60"))
    )
    dea = _optional_float(entry_factors.get("symbol.macd.dea")) or _optional_float(signal_row.get("macd_dea"))
    dif = _optional_float(entry_factors.get("symbol.macd.dif")) or _optional_float(signal_row.get("macd_dif"))
    macd_bar = _optional_float(entry_factors.get("symbol.macd.macd_bar")) or _optional_float(signal_row.get("macd_bar"))
    if macd_bar is None and dif is not None and dea is not None:
        macd_bar = 2.0 * (dif - dea)
    ma25 = _optional_float(entry_factors.get("symbol.ma.ma25")) or _optional_float(signal_row.get("ma25"))
    age = _optional_int(entry_factors.get("symbol.macd.dea_waterline_age_trading_days"))

    field_values[DEA_WATERLINE_AGE_FIELD] = _derived_payload(
        raw=age,
        bucket=_dea_waterline_age_bucket(age),
        asof_date=signal_date,
        reference_count=None,
        exception_codes=[] if age is not None else ["signal_strength_missing"],
    )

    dea_ratio = dea / signal_close if dea is not None and signal_close and signal_close > 0 else None
    field_values[DEA_VALUE_FIELD] = _derived_payload(
        raw=dea_ratio,
        bucket=_positive_strength_bucket(dea_ratio),
        asof_date=signal_date,
        reference_count=None,
        exception_codes=[] if dea_ratio is not None else ["signal_strength_missing"],
    )

    macd_bar_ratio = macd_bar / signal_close if macd_bar is not None and signal_close and signal_close > 0 else None
    field_values[MACD_BAR_FIELD] = _derived_payload(
        raw=macd_bar_ratio,
        bucket=_signed_strength_bucket(macd_bar_ratio),
        asof_date=signal_date,
        reference_count=None,
        exception_codes=[] if macd_bar_ratio is not None else ["signal_strength_missing"],
    )

    dif_dea_ratio = (dif - dea) / signal_close if dif is not None and dea is not None and signal_close and signal_close > 0 else None
    field_values[DIF_DEA_DISTANCE_FIELD] = _derived_payload(
        raw=dif_dea_ratio,
        bucket=_signed_strength_bucket(dif_dea_ratio),
        asof_date=signal_date,
        reference_count=None,
        exception_codes=[] if dif_dea_ratio is not None else ["signal_strength_missing"],
    )

    ma_spread = (ma25 - signal_ma60) / signal_ma60 if ma25 is not None and signal_ma60 and signal_ma60 > 0 else None
    field_values[MA25_MA60_SPREAD_FIELD] = _derived_payload(
        raw=ma_spread,
        bucket=_ma_spread_bucket(ma_spread),
        asof_date=signal_date,
        reference_count=None,
        exception_codes=[] if ma_spread is not None else ["signal_strength_missing"],
    )

    ma60_slope = _optional_float(_as_mapping(signal_row).get("ma60_slope_20d"))
    field_values[MA60_SLOPE_20D_FIELD] = _derived_payload(
        raw=ma60_slope,
        bucket=_ma60_slope_bucket(ma60_slope),
        asof_date=signal_date,
        reference_count=None,
        exception_codes=[] if ma60_slope is not None else ["path_price_missing"],
    )

    body = None
    if signal_open is not None and signal_close is not None and signal_close > 0:
        body = abs(signal_open - signal_close) / signal_close
    field_values[SIGNAL_CANDLE_BODY_FIELD] = _derived_payload(
        raw=body,
        bucket=_candle_body_bucket(body),
        asof_date=signal_date,
        reference_count=None,
        exception_codes=[] if body is not None else ["signal_strength_missing"],
    )

    shadow_payload, shadow_bucket = _signal_shadow_payload(signal_row, signal_open=signal_open, signal_close=signal_close)
    field_values[SIGNAL_SHADOW_FIELD] = _derived_payload(
        raw=shadow_payload,
        bucket=shadow_bucket,
        asof_date=signal_date,
        reference_count=None,
        exception_codes=[] if shadow_bucket is not None else ["path_price_missing"],
    )


def _add_weekly_symbol_fields(
    field_values: dict[str, dict[str, Any]],
    *,
    trade: Mapping[str, Any],
    signal_date: str,
    price_context: Mapping[str, Any],
) -> None:
    symbol = _as_str(trade.get("symbol"))
    entry_factors = _entry_factor_values(trade)
    weekly_row = _latest_context_row(
        _as_mapping(price_context.get("weekly_by_symbol")),
        symbol=symbol,
        trade_date=signal_date,
        strict_before=True,
    )

    factor_j = _optional_float(entry_factors.get("symbol.kdj.week.j"))
    row_j = _optional_float(_as_mapping(weekly_row).get("kdj_j"))
    kdj_j = factor_j if factor_j is not None else row_j
    kdj_bucket = (
        _as_str(entry_factors.get("symbol.kdj.week.j_bucket"))
        or _kdj_j_bucket(kdj_j)
    )
    kdj_state = (
        _as_str(entry_factors.get("symbol.kdj.week.state"))
        or _kdj_state(kdj_j)
    )
    weekly_asof = _as_str(_as_mapping(weekly_row).get("trade_date")) or signal_date
    weekly_exception = [] if weekly_row is not None or factor_j is not None else ["weekly_price_missing"]

    field_values[SYMBOL_WEEKLY_KDJ_J_FIELD] = _derived_payload(
        raw=kdj_j,
        bucket=kdj_bucket or None,
        asof_date=weekly_asof,
        reference_count=None,
        exception_codes=[] if kdj_j is not None else weekly_exception,
    )
    field_values[SYMBOL_WEEKLY_KDJ_STATE_FIELD] = _derived_payload(
        raw=kdj_state or None,
        bucket=kdj_state or None,
        asof_date=weekly_asof,
        reference_count=None,
        exception_codes=[] if kdj_state else weekly_exception,
    )

    ma_trend = _as_str(_as_mapping(weekly_row).get("ma_trend")) or None
    close_vs_ma20 = _optional_float(_as_mapping(weekly_row).get("close_vs_ma20"))
    field_values[SYMBOL_WEEKLY_MA_TREND_FIELD] = _derived_payload(
        raw=ma_trend,
        bucket=ma_trend,
        asof_date=weekly_asof,
        reference_count=None,
        exception_codes=[] if ma_trend else ["weekly_price_missing"],
    )
    field_values[SYMBOL_WEEKLY_CLOSE_VS_MA20_FIELD] = _derived_payload(
        raw=close_vs_ma20,
        bucket=_ma20_distance_bucket(close_vs_ma20),
        asof_date=weekly_asof,
        reference_count=None,
        exception_codes=[] if close_vs_ma20 is not None else ["weekly_price_missing"],
    )


def _add_industry_index_fields(
    field_values: dict[str, dict[str, Any]],
    *,
    signal_date: str,
    industry_context: Mapping[str, Any],
) -> None:
    industry_payload = _as_mapping(field_values.get("industry.sw_l1.code"))
    industry_code = _field_raw_or_bucket(industry_payload)
    inherited_exceptions = [
        code
        for code in _exception_codes(industry_payload.get("exception_codes"))
        if code == "industry_membership_backfilled"
    ]
    if not industry_code:
        _set_missing_fields(
            field_values,
            (
                INDUSTRY_ATR_20D_FIELD,
                INDUSTRY_RETURN_VOL_20D_FIELD,
                INDUSTRY_RETURN_VOL_60D_FIELD,
                INDUSTRY_NEAR_HIGH_60D_FIELD,
                INDUSTRY_WEEKLY_KDJ_J_FIELD,
                INDUSTRY_WEEKLY_KDJ_STATE_FIELD,
                INDUSTRY_WEEKLY_MA_TREND_FIELD,
                INDUSTRY_WEEKLY_RELATIVE_STRENGTH_FIELD,
            ),
            asof_date=signal_date,
            code="industry_missing",
        )
        return

    daily_row = _latest_context_row(
        _as_mapping(industry_context.get("by_symbol")),
        symbol=str(industry_code),
        trade_date=signal_date,
        strict_before=False,
    )
    weekly_row = _latest_context_row(
        _as_mapping(industry_context.get("weekly_by_symbol")),
        symbol=str(industry_code),
        trade_date=signal_date,
        strict_before=True,
    )

    daily_asof = _as_str(_as_mapping(daily_row).get("trade_date")) or signal_date
    daily_missing = [] if daily_row is not None else ["industry_index_missing"]
    atr_pct = _optional_float(_as_mapping(daily_row).get("atr_pct"))
    return_vol_20d = _optional_float(_as_mapping(daily_row).get("return_vol_20d"))
    return_vol_60d = _optional_float(_as_mapping(daily_row).get("return_vol_60d"))
    near_high_60d = _optional_float(_as_mapping(daily_row).get("near_high_60d"))

    field_values[INDUSTRY_ATR_20D_FIELD] = _derived_payload(
        raw=atr_pct,
        bucket=_volatility_pct_bucket(atr_pct),
        asof_date=daily_asof,
        reference_count=None,
        exception_codes=inherited_exceptions if atr_pct is not None else inherited_exceptions + daily_missing,
    )
    field_values[INDUSTRY_RETURN_VOL_20D_FIELD] = _derived_payload(
        raw=return_vol_20d,
        bucket=_volatility_pct_bucket(return_vol_20d),
        asof_date=daily_asof,
        reference_count=None,
        exception_codes=inherited_exceptions if return_vol_20d is not None else inherited_exceptions + daily_missing,
    )
    field_values[INDUSTRY_RETURN_VOL_60D_FIELD] = _derived_payload(
        raw=return_vol_60d,
        bucket=_volatility_pct_bucket(return_vol_60d),
        asof_date=daily_asof,
        reference_count=None,
        exception_codes=inherited_exceptions if return_vol_60d is not None else inherited_exceptions + daily_missing,
    )
    field_values[INDUSTRY_NEAR_HIGH_60D_FIELD] = _derived_payload(
        raw=near_high_60d,
        bucket=_near_high_bucket(near_high_60d),
        asof_date=daily_asof,
        reference_count=None,
        exception_codes=inherited_exceptions if near_high_60d is not None else inherited_exceptions + daily_missing,
    )

    weekly_asof = _as_str(_as_mapping(weekly_row).get("trade_date")) or signal_date
    weekly_missing = [] if weekly_row is not None else ["industry_weekly_missing"]
    weekly_j = _optional_float(_as_mapping(weekly_row).get("kdj_j"))
    weekly_state = _kdj_state(weekly_j)
    weekly_trend = _as_str(_as_mapping(weekly_row).get("ma_trend")) or None
    relative_strength = _optional_float(_as_mapping(weekly_row).get("relative_strength_percentile"))

    field_values[INDUSTRY_WEEKLY_KDJ_J_FIELD] = _derived_payload(
        raw=weekly_j,
        bucket=_kdj_j_bucket(weekly_j),
        asof_date=weekly_asof,
        reference_count=None,
        exception_codes=inherited_exceptions if weekly_j is not None else inherited_exceptions + weekly_missing,
    )
    field_values[INDUSTRY_WEEKLY_KDJ_STATE_FIELD] = _derived_payload(
        raw=weekly_state,
        bucket=weekly_state,
        asof_date=weekly_asof,
        reference_count=None,
        exception_codes=inherited_exceptions if weekly_state else inherited_exceptions + weekly_missing,
    )
    field_values[INDUSTRY_WEEKLY_MA_TREND_FIELD] = _derived_payload(
        raw=weekly_trend,
        bucket=weekly_trend,
        asof_date=weekly_asof,
        reference_count=None,
        exception_codes=inherited_exceptions if weekly_trend else inherited_exceptions + weekly_missing,
    )
    field_values[INDUSTRY_WEEKLY_RELATIVE_STRENGTH_FIELD] = _derived_payload(
        raw=relative_strength,
        bucket=_percentile_bucket(relative_strength),
        asof_date=weekly_asof,
        reference_count=None,
        exception_codes=inherited_exceptions if relative_strength is not None else inherited_exceptions + weekly_missing,
    )


def _add_market_source_index_field(
    field_values: dict[str, dict[str, Any]],
    *,
    symbol: str,
    signal_date: str,
    source_index_by_symbol: Mapping[str, str],
) -> None:
    source_index = source_index_by_symbol.get(symbol)
    field_values[SOURCE_INDEX_FIELD] = _derived_payload(
        raw=source_index,
        bucket=source_index,
        asof_date=signal_date,
        reference_count=None,
        exception_codes=[] if source_index else ["source_index_missing"],
    )


def _add_market_index_fields(
    field_values: dict[str, dict[str, Any]],
    *,
    signal_date: str,
    market_context: Mapping[str, Any],
) -> None:
    for market_key, symbol, _label in MARKET_INDEX_SPECS:
        daily_row = _latest_context_row(
            _as_mapping(market_context.get("by_symbol")),
            symbol=symbol,
            trade_date=signal_date,
            strict_before=False,
        )
        weekly_row = _latest_context_row(
            _as_mapping(market_context.get("weekly_by_symbol")),
            symbol=symbol,
            trade_date=signal_date,
            strict_before=True,
        )
        daily_asof = _as_str(_as_mapping(daily_row).get("trade_date")) or signal_date
        weekly_asof = _as_str(_as_mapping(weekly_row).get("trade_date")) or signal_date
        daily_missing = [] if daily_row is not None else ["market_index_missing"]
        weekly_missing = [] if weekly_row is not None else ["market_weekly_missing"]
        trend_state = _as_str(_as_mapping(daily_row).get("trend_state")) or None
        return_vol_20d = _optional_float(_as_mapping(daily_row).get("return_vol_20d"))
        return_vol_60d = _optional_float(_as_mapping(daily_row).get("return_vol_60d"))
        weekly_j = _optional_float(_as_mapping(weekly_row).get("kdj_j"))
        weekly_state = _kdj_state(weekly_j)
        weekly_trend = _as_str(_as_mapping(weekly_row).get("ma_trend")) or None

        field_values[f"market.{market_key}.trend_state"] = _derived_payload(
            raw=trend_state,
            bucket=trend_state,
            asof_date=daily_asof,
            reference_count=None,
            exception_codes=[] if trend_state else daily_missing,
        )
        field_values[f"market.{market_key}.return_vol_20d_bucket"] = _derived_payload(
            raw=return_vol_20d,
            bucket=_volatility_pct_bucket(return_vol_20d),
            asof_date=daily_asof,
            reference_count=None,
            exception_codes=[] if return_vol_20d is not None else daily_missing,
        )
        field_values[f"market.{market_key}.return_vol_60d_bucket"] = _derived_payload(
            raw=return_vol_60d,
            bucket=_volatility_pct_bucket(return_vol_60d),
            asof_date=daily_asof,
            reference_count=None,
            exception_codes=[] if return_vol_60d is not None else daily_missing,
        )
        field_values[f"market.{market_key}.weekly.kdj_state"] = _derived_payload(
            raw=weekly_state,
            bucket=weekly_state,
            asof_date=weekly_asof,
            reference_count=None,
            exception_codes=[] if weekly_state else weekly_missing,
        )
        field_values[f"market.{market_key}.weekly.ma_trend_bucket"] = _derived_payload(
            raw=weekly_trend,
            bucket=weekly_trend,
            asof_date=weekly_asof,
            reference_count=None,
            exception_codes=[] if weekly_trend else weekly_missing,
        )


def _add_market_stage_fields(
    field_values: dict[str, dict[str, Any]],
    *,
    signal_date: str,
    exit_date: str,
    market_context: Mapping[str, Any],
) -> None:
    by_symbol = _as_mapping(market_context.get("by_symbol"))
    for market_key, symbol, _label in MARKET_INDEX_SPECS:
        entry_row = _latest_context_row(
            by_symbol,
            symbol=symbol,
            trade_date=signal_date,
            strict_before=False,
        )
        exit_row = _latest_context_row(
            by_symbol,
            symbol=symbol,
            trade_date=exit_date,
            strict_before=False,
        )
        entry_asof = _as_str(_as_mapping(entry_row).get("trade_date")) or signal_date
        exit_asof = _as_str(_as_mapping(exit_row).get("trade_date")) or exit_date
        entry_stage = _as_str(_as_mapping(entry_row).get("trend_state")) or None
        exit_stage = _as_str(_as_mapping(exit_row).get("trend_state")) or None

        field_values[f"market.{market_key}.entry_stage"] = _derived_payload(
            raw=entry_stage,
            bucket=entry_stage,
            asof_date=entry_asof,
            reference_count=None,
            exception_codes=[] if entry_stage else ["market_entry_stage_missing"],
        )
        field_values[f"market.{market_key}.exit_stage"] = _derived_payload(
            raw=exit_stage,
            bucket=exit_stage,
            asof_date=exit_asof,
            reference_count=None,
            exception_codes=[] if exit_stage else ["market_exit_stage_missing"],
        )

        transition = f"{entry_stage}_to_{exit_stage}" if entry_stage and exit_stage else None
        transition_exceptions: list[str] = []
        if not entry_stage:
            transition_exceptions.append("market_entry_stage_missing")
        if not exit_stage:
            transition_exceptions.append("market_exit_stage_missing")
        field_values[f"market.{market_key}.entry_to_exit_stage"] = _derived_payload(
            raw={"entry_stage": entry_stage, "exit_stage": exit_stage} if transition else None,
            bucket=transition,
            asof_date=exit_asof,
            reference_count=None,
            exception_codes=transition_exceptions,
        )


def _add_objective_market_stage_fields(
    field_values: dict[str, dict[str, Any]],
    *,
    signal_date: str,
    exit_date: str,
    market_context: Mapping[str, Any],
    market_breadth_context: Mapping[str, Any],
) -> None:
    entry = _objective_market_stage_snapshot(
        market_context=market_context,
        market_breadth_context=market_breadth_context,
        trade_date=signal_date,
    )
    exit_ = _objective_market_stage_snapshot(
        market_context=market_context,
        market_breadth_context=market_breadth_context,
        trade_date=exit_date,
    )

    field_values[OBJECTIVE_ENTRY_STAGE_FIELD] = _derived_payload(
        raw=entry["raw"],
        bucket=entry["stage"],
        asof_date=entry["asof_date"] or signal_date,
        reference_count=entry["reference_count"],
        exception_codes=entry["exception_codes"],
    )
    field_values[OBJECTIVE_EXIT_STAGE_FIELD] = _derived_payload(
        raw=exit_["raw"],
        bucket=exit_["stage"],
        asof_date=exit_["asof_date"] or exit_date,
        reference_count=exit_["reference_count"],
        exception_codes=exit_["exception_codes"],
    )

    entry_stage = _as_str(entry["stage"])
    exit_stage = _as_str(exit_["stage"])
    transition = f"{entry_stage}_to_{exit_stage}" if entry_stage and exit_stage else None
    transition_exceptions = []
    if not entry_stage:
        transition_exceptions.extend(entry["exception_codes"] or ["objective_market_entry_stage_missing"])
    if not exit_stage:
        transition_exceptions.extend(exit_["exception_codes"] or ["objective_market_exit_stage_missing"])
    field_values[OBJECTIVE_ENTRY_TO_EXIT_STAGE_FIELD] = _derived_payload(
        raw={"entry_stage": entry_stage, "exit_stage": exit_stage} if transition else None,
        bucket=transition,
        asof_date=exit_["asof_date"] or exit_date,
        reference_count=None,
        exception_codes=sorted(set(transition_exceptions)),
    )

    _add_objective_component_fields(field_values, prefix="entry", snapshot=entry, asof_date=signal_date)
    _add_objective_component_fields(field_values, prefix="exit", snapshot=exit_, asof_date=exit_date)


def _add_objective_component_fields(
    field_values: dict[str, dict[str, Any]],
    *,
    prefix: str,
    snapshot: Mapping[str, Any],
    asof_date: str,
) -> None:
    if prefix == "entry":
        breadth_field = OBJECTIVE_ENTRY_BREADTH_FIELD
        drawdown_field = OBJECTIVE_ENTRY_DRAWDOWN_FIELD
        slope_field = OBJECTIVE_ENTRY_MA60_SLOPE_FIELD
        ma250_field = OBJECTIVE_ENTRY_MA250_POSITION_FIELD
    else:
        breadth_field = OBJECTIVE_EXIT_BREADTH_FIELD
        drawdown_field = OBJECTIVE_EXIT_DRAWDOWN_FIELD
        slope_field = OBJECTIVE_EXIT_MA60_SLOPE_FIELD
        ma250_field = OBJECTIVE_EXIT_MA250_POSITION_FIELD

    exceptions = _exception_codes(snapshot.get("exception_codes"))
    component_asof = _as_str(snapshot.get("asof_date")) or asof_date
    breadth_ratio = _optional_float(snapshot.get("breadth_ratio"))
    drawdown = _optional_float(snapshot.get("index_drawdown_250d"))
    slope = _optional_float(snapshot.get("index_ma60_slope_20d"))
    ma250_position = _as_str(snapshot.get("index_ma250_position")) or None

    field_values[breadth_field] = _derived_payload(
        raw=breadth_ratio,
        bucket=_breadth_ratio_bucket(breadth_ratio),
        asof_date=component_asof,
        reference_count=_optional_int(snapshot.get("breadth_reference_count")),
        exception_codes=[] if breadth_ratio is not None else ["market_breadth_missing"],
    )
    field_values[drawdown_field] = _derived_payload(
        raw=drawdown,
        bucket=_index_drawdown_bucket(drawdown),
        asof_date=component_asof,
        reference_count=None,
        exception_codes=[] if drawdown is not None else exceptions or ["objective_market_index_missing"],
    )
    field_values[slope_field] = _derived_payload(
        raw=slope,
        bucket=_ma60_slope_bucket(slope),
        asof_date=component_asof,
        reference_count=None,
        exception_codes=[] if slope is not None else exceptions or ["objective_market_index_missing"],
    )
    field_values[ma250_field] = _derived_payload(
        raw=ma250_position,
        bucket=ma250_position,
        asof_date=component_asof,
        reference_count=None,
        exception_codes=[] if ma250_position else exceptions or ["objective_market_index_missing"],
    )


def _objective_market_stage_snapshot(
    *,
    market_context: Mapping[str, Any],
    market_breadth_context: Mapping[str, Any],
    trade_date: str,
) -> dict[str, Any]:
    by_symbol = _as_mapping(market_context.get("by_symbol"))
    breadth_row = _latest_breadth_row(market_breadth_context, trade_date=trade_date)
    breadth_ratio = _optional_float(_as_mapping(breadth_row).get("ma60_above_ratio"))
    breadth_reference_count = _optional_int(_as_mapping(breadth_row).get("symbol_count"))
    breadth_asof = _as_str(_as_mapping(breadth_row).get("trade_date"))

    index_source = None
    index_components: list[dict[str, Any]] = []
    all_share_row = _latest_context_row(by_symbol, symbol="000985.CSI", trade_date=trade_date, strict_before=False)
    all_share_component = _objective_index_component("all_share", "000985.CSI", "中证全指", all_share_row)
    if all_share_component.get("complete"):
        index_source = "all_share"
        index_components = [all_share_component]
    else:
        fallback_components = [
            _objective_index_component(key, symbol, label, _latest_context_row(
                by_symbol,
                symbol=symbol,
                trade_date=trade_date,
                strict_before=False,
            ))
            for key, symbol, label in MARKET_INDEX_SPECS
        ]
        if all(component.get("complete") for component in fallback_components):
            index_source = "hs300_csi500"
            index_components = fallback_components

    exceptions: list[str] = []
    if not index_components:
        exceptions.append("objective_market_index_missing")
    if breadth_ratio is None:
        exceptions.append("market_breadth_missing")

    stage = None
    if index_components and breadth_ratio is not None:
        states = {_as_str(component.get("state")) for component in index_components}
        if states == {"bullish"} and breadth_ratio > 0.55:
            stage = "bullish"
        elif states == {"bearish"} and breadth_ratio < 0.45:
            stage = "bearish"
        else:
            stage = "mixed"

    drawdowns = [_optional_float(component.get("drawdown_250d")) for component in index_components]
    slopes = [_optional_float(component.get("ma60_slope_20d")) for component in index_components]
    positions = [_as_str(component.get("ma250_position")) for component in index_components]
    drawdown = _mean_float([value for value in drawdowns if value is not None])
    slope = _mean_float([value for value in slopes if value is not None])
    ma250_position = _combine_ma250_positions([value for value in positions if value])
    asof_dates = [_as_str(component.get("asof_date")) for component in index_components if _as_str(component.get("asof_date"))]
    asof_date = max([*asof_dates, breadth_asof] if breadth_asof else asof_dates, default=trade_date)

    return {
        "stage": stage,
        "asof_date": asof_date,
        "reference_count": breadth_reference_count,
        "breadth_ratio": breadth_ratio,
        "breadth_reference_count": breadth_reference_count,
        "index_drawdown_250d": drawdown,
        "index_ma60_slope_20d": slope,
        "index_ma250_position": ma250_position,
        "exception_codes": exceptions,
        "raw": {
            "stage": stage,
            "index_source": index_source,
            "index_components": index_components,
            "breadth_ma60_above_ratio": breadth_ratio,
            "breadth_symbol_count": breadth_reference_count,
            "rules": {
                "bullish": "all selected indexes close>MA250, MA60 slope>0, drawdown>-15%, breadth>55%",
                "bearish": "all selected indexes close<MA250, MA60 slope<0, drawdown<-20%, breadth<45%",
                "mixed": "otherwise",
            },
        } if stage else None,
    }


def _objective_index_component(
    key: str,
    symbol: str,
    label: str,
    row: Mapping[str, Any] | None,
) -> dict[str, Any]:
    row_map = _as_mapping(row)
    close = _optional_float(row_map.get("close"))
    ma250 = _optional_float(row_map.get("ma250"))
    ma60_slope = _optional_float(row_map.get("ma60_slope_20d"))
    drawdown = _optional_float(row_map.get("drawdown_250d"))
    asof_date = _as_str(row_map.get("trade_date"))
    complete = close is not None and ma250 is not None and ma60_slope is not None and drawdown is not None
    ma250_position = None
    state = None
    if close is not None and ma250 is not None:
        ma250_position = "above_ma250" if close > ma250 else "below_ma250"
    if complete:
        if close > ma250 and ma60_slope > 0 and drawdown > -0.15:
            state = "bullish"
        elif close < ma250 and ma60_slope < 0 and drawdown < -0.20:
            state = "bearish"
        else:
            state = "mixed"
    return {
        "key": key,
        "symbol": symbol,
        "label_zh": label,
        "asof_date": asof_date,
        "close": close,
        "ma250": ma250,
        "ma60_slope_20d": ma60_slope,
        "drawdown_250d": drawdown,
        "ma250_position": ma250_position,
        "state": state,
        "complete": complete,
    }


def _latest_breadth_row(market_breadth_context: Mapping[str, Any], *, trade_date: str) -> Mapping[str, Any] | None:
    by_date = _as_mapping(market_breadth_context.get("by_date"))
    if not by_date or not trade_date:
        return None
    candidates = [str(date_key) for date_key in by_date if str(date_key) <= trade_date]
    if not candidates:
        return None
    return _as_mapping(by_date[max(candidates)])


def _mean_float(values: Sequence[float]) -> float | None:
    present = [value for value in values if value is not None and math.isfinite(value)]
    if not present:
        return None
    return sum(present) / len(present)


def _combine_ma250_positions(values: Sequence[str]) -> str | None:
    if not values:
        return None
    unique = set(values)
    if unique == {"above_ma250"}:
        return "above_ma250"
    if unique == {"below_ma250"}:
        return "below_ma250"
    return "mixed_ma250"


def _add_relative_momentum_fields(
    field_values: dict[str, dict[str, Any]],
    *,
    trade: Mapping[str, Any],
    signal_date: str,
    price_context: Mapping[str, Any],
    industry_context: Mapping[str, Any],
    market_context: Mapping[str, Any],
) -> None:
    symbol = _as_str(trade.get("symbol"))
    signal_row = _as_mapping(_price_row_for(price_context, symbol=symbol, trade_date=signal_date))
    symbol_return_20d = _optional_float(signal_row.get("return_20d"))

    relative_specs = (
        (SYMBOL_HS300_RS_20D_FIELD, _market_daily_return(market_context, "000300.SH", signal_date, "return_20d"), "relative_market_missing"),
        (SYMBOL_CSI500_RS_20D_FIELD, _market_daily_return(market_context, "000905.SH", signal_date, "return_20d"), "relative_market_missing"),
        (SYMBOL_INDUSTRY_RS_20D_FIELD, _industry_daily_return(field_values, industry_context, signal_date, "return_20d"), "relative_industry_missing"),
    )
    for field_key, benchmark_return, missing_code in relative_specs:
        spread = (
            symbol_return_20d - benchmark_return
            if symbol_return_20d is not None and benchmark_return is not None
            else None
        )
        field_values[field_key] = _derived_payload(
            raw=spread,
            bucket=_relative_return_bucket(spread),
            asof_date=signal_date,
            reference_count=None,
            exception_codes=[] if spread is not None else [missing_code],
        )


def _add_exit_reason_field(field_values: dict[str, dict[str, Any]], *, trade: Mapping[str, Any]) -> None:
    exit_reason = _as_str(trade.get("exit_reason")) or None
    field_values[EXIT_REASON_FIELD] = _derived_payload(
        raw=exit_reason,
        bucket=exit_reason,
        asof_date=_as_str(trade.get("exit_date")),
        reference_count=None,
        exception_codes=[] if exit_reason else ["exit_reason_missing"],
    )


def _price_rows_for_trade(
    price_context: Mapping[str, Any],
    *,
    symbol: str,
    entry_date: str,
    exit_date: str,
) -> pd.DataFrame | None:
    by_symbol = _as_mapping(price_context.get("by_symbol"))
    frame = by_symbol.get(symbol)
    if not isinstance(frame, pd.DataFrame) or not entry_date or not exit_date:
        return None
    return frame[(frame["trade_date"] >= entry_date) & (frame["trade_date"] <= exit_date)]


def _post_exit_price_rows(
    price_context: Mapping[str, Any],
    *,
    symbol: str,
    exit_date: str,
    limit: int,
) -> pd.DataFrame | None:
    by_symbol = _as_mapping(price_context.get("by_symbol"))
    frame = by_symbol.get(symbol)
    if not isinstance(frame, pd.DataFrame) or frame.empty or not exit_date:
        return None
    return frame[frame["trade_date"] > exit_date].head(limit)


def _price_row_for(price_context: Mapping[str, Any], *, symbol: str, trade_date: str) -> Mapping[str, Any] | None:
    return _as_mapping(price_context.get("by_symbol_date")).get((symbol, trade_date))


def _add_execution_derived_fields(
    field_values: dict[str, dict[str, Any]],
    *,
    trade: Mapping[str, Any],
    signal_date: str,
) -> None:
    entry_factors = _entry_factor_values(trade)
    signal_close = _optional_float(trade.get("signal_close")) or _optional_float(entry_factors.get("symbol.close"))
    signal_ma60 = _optional_float(trade.get("signal_ma60")) or _optional_float(entry_factors.get("symbol.ma.ma60"))
    entry_price = _optional_float(trade.get("entry_execution_price")) or _optional_float(trade.get("entry_price"))
    atr_pct = _optional_float(_as_mapping(field_values.get("entry.volatility.atr_20d_bucket")).get("raw"))
    atr_abs = atr_pct * signal_close if atr_pct is not None and signal_close is not None else None

    signal_multiple = None
    if signal_close is not None and signal_ma60 is not None and atr_abs is not None and atr_abs > 0:
        signal_multiple = (signal_close - signal_ma60) / atr_abs
    else:
        signal_multiple = _optional_float(
            _as_mapping(field_values.get(SIGNAL_CLOSE_MA60_ATR_MULTIPLE_FIELD)).get("raw")
        )
        if signal_multiple is None:
            signal_multiple = _optional_float(_as_mapping(field_values.get(MA60_ATR_MULTIPLE_FIELD)).get("raw"))

    source_payload = dict(_as_mapping(field_values.get(SIGNAL_CLOSE_MA60_ATR_MULTIPLE_FIELD)))
    if not source_payload:
        source_payload = dict(_as_mapping(field_values.get(MA60_ATR_MULTIPLE_FIELD)))
    field_values[SIGNAL_CLOSE_MA60_ATR_MULTIPLE_FIELD] = _derived_payload(
        raw=signal_multiple,
        bucket=_atr_multiple_bucket(signal_multiple),
        asof_date=signal_date,
        reference_count=_optional_int(source_payload.get("reference_count")),
        exception_codes=[] if signal_multiple is not None else ["execution_derived_missing"],
    )

    actual_multiple = None
    if entry_price is not None and signal_ma60 is not None and atr_abs is not None and atr_abs > 0:
        actual_multiple = (entry_price - signal_ma60) / atr_abs
    field_values[MA60_ATR_MULTIPLE_FIELD] = _derived_payload(
        raw=actual_multiple,
        bucket=_atr_multiple_bucket(actual_multiple),
        asof_date=signal_date,
        reference_count=_optional_int(source_payload.get("reference_count")),
        exception_codes=[] if actual_multiple is not None else ["execution_derived_missing"],
    )

    signal_to_entry_return = None
    if entry_price is not None and signal_close is not None and signal_close > 0:
        signal_to_entry_return = entry_price / signal_close - 1.0
    field_values[SIGNAL_TO_ENTRY_RETURN_FIELD] = _derived_payload(
        raw=signal_to_entry_return,
        bucket=_signal_to_entry_return_bucket(signal_to_entry_return),
        asof_date=signal_date,
        reference_count=None,
        exception_codes=[] if signal_to_entry_return is not None else ["execution_derived_missing"],
    )


def _load_reference_snapshot(path_like: str | Path) -> dict[str, Any]:
    path = Path(path_like)
    if not path.exists():
        raise FileNotFoundError(f"reference snapshot does not exist: {path}")
    if path.is_dir():
        json_path = path / "reference.json"
        parquet_path = path / "reference_values.parquet"
        metadata_path = path / "metadata.json"
        metadata = _as_mapping(_load_json_if_exists(metadata_path)) if metadata_path.exists() else {}
        if json_path.exists():
            payload = _as_mapping(_load_json_if_exists(json_path))
            metadata = _as_mapping(payload.get("metadata")) or metadata
            rows = _as_sequence(payload.get("rows") or payload.get("samples"))
        elif parquet_path.exists():
            rows = _parquet_rows(parquet_path)
        else:
            raise FileNotFoundError(f"reference snapshot directory lacks reference.json or reference_values.parquet: {path}")
        return {"source_path": path, "metadata": metadata, "rows": [_as_mapping(row) for row in rows]}

    if path.suffix.lower() in {".parquet", ".pq"}:
        return {"source_path": path, "metadata": {}, "rows": _parquet_rows(path)}
    payload = _load_json_if_exists(path)
    if isinstance(payload, list):
        return {"source_path": path, "metadata": {}, "rows": [_as_mapping(row) for row in payload]}
    payload_map = _as_mapping(payload)
    rows = _as_sequence(payload_map.get("rows") or payload_map.get("samples"))
    if not rows:
        raise ValueError(f"reference snapshot contains no rows: {path}")
    return {"source_path": path, "metadata": _as_mapping(payload_map.get("metadata")), "rows": [_as_mapping(row) for row in rows]}


def _parquet_rows(path: Path) -> list[dict[str, Any]]:
    frame = pd.read_parquet(path)
    return [row.dropna().to_dict() for _, row in frame.iterrows()]


def _field_catalog(reference: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    metadata = _as_mapping(reference.get("metadata"))
    fields = metadata.get("fields")
    catalog: dict[str, dict[str, Any]] = {}
    if isinstance(fields, Mapping):
        for key, value in fields.items():
            catalog[str(key)] = dict(_fallback_field_catalog_item(str(key)), **_as_mapping(value))
    elif isinstance(fields, list):
        for value in fields:
            item = _as_mapping(value)
            key = _as_str(item.get("field_key"))
            if key:
                catalog[key] = dict(_fallback_field_catalog_item(key), **item)
    for row in _as_sequence(reference.get("rows")):
        key = _as_str(_as_mapping(row).get("field_key"))
        if key:
            catalog.setdefault(key, _fallback_field_catalog_item(key))
    return catalog


def _fallback_field_catalog_item(field_key: str) -> dict[str, Any]:
    return {
        "field_key": field_key,
        "label_zh": field_key,
        "value_type": "bucket" if field_key.endswith("_bucket") else "value",
        "timing": "entry" if field_key.startswith("entry.") or "." not in field_key else field_key.split(".", 1)[0],
        "scope": _scope_from_field(field_key),
        "bucket_rule": "reference_snapshot",
        "default_in_environment_fit": field_key in {
            "industry.sw_l1.code",
            "entry.price_position.near_high_20d_bucket",
            "entry.price_position.near_high_60d_bucket",
        },
        "source": "attribution_reference",
        "missing_policy": "missing",
    }


def _environment_default_fields(catalog: Mapping[str, Mapping[str, Any]], metadata: Mapping[str, Any]) -> list[str]:
    configured = [str(item) for item in _as_sequence(metadata.get("environment_fit_default_fields"))]
    defaults = configured or []
    for key in sorted(catalog):
        if _as_mapping(catalog[key]).get("default_in_environment_fit") is True and key not in defaults:
            defaults.append(key)
    return defaults


def _environment_pair_whitelist(metadata: Mapping[str, Any]) -> list[list[str]]:
    configured = _as_sequence(metadata.get("environment_fit_pair_whitelist"))
    pairs = []
    if configured:
        pairs.extend([[str(part) for part in _as_sequence(pair)] for pair in configured if len(_as_sequence(pair)) == 2])
    else:
        pairs.extend([[left, right] for left, right in DEFAULT_ENVIRONMENT_FIT_PAIR_WHITELIST])
    seen = {tuple(pair) for pair in pairs}
    for left, right in DEFAULT_ENVIRONMENT_FIT_PAIR_WHITELIST:
        pair = (left, right)
        if pair not in seen:
            pairs.append([left, right])
            seen.add(pair)
    return pairs


def _outcome_diagnostic_pair_whitelist() -> list[list[str]]:
    return [[left, right] for left, right in (*EXIT_REASON_ENTRY_FACTOR_PAIRS, *MARKET_STAGE_DIAGNOSTIC_PAIRS)]


def _reference_rows_by_symbol_field(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        row_map = _as_mapping(row)
        symbol = _as_str(row_map.get("symbol"))
        field_key = _as_str(row_map.get("field_key"))
        if symbol and field_key:
            grouped[(symbol, field_key)].append(row_map)
    for key in grouped:
        grouped[key].sort(key=lambda row: _as_str(row.get("trade_date")) or _as_str(row.get("asof_date")))
    return grouped


def _reference_row_for(
    rows: Sequence[Mapping[str, Any]],
    *,
    entry_date: str,
    max_staleness_trading_days: int,
) -> Mapping[str, Any] | None:
    exact = [row for row in rows if _as_str(row.get("trade_date")) == entry_date]
    if exact:
        return exact[-1]
    valid = []
    for row in rows:
        row_date = _as_str(row.get("trade_date")) or _as_str(row.get("asof_date"))
        if not row_date or row_date > entry_date:
            continue
        merge_staleness = _trading_day_distance(row_date, entry_date)
        if merge_staleness is not None and merge_staleness <= max_staleness_trading_days:
            valid.append(row)
    return valid[-1] if valid else None


def _trading_day_distance(start_date: str, end_date: str) -> int | None:
    if start_date > end_date:
        return None
    try:
        return max(len(pd.bdate_range(start=start_date, end=end_date)) - 1, 0)
    except (TypeError, ValueError):
        return None


def _write_wide_csv(samples: Sequence[Any], field_keys: Sequence[str], path: Path) -> None:
    columns = [
        "trade_index", "symbol", "signal_date", "entry_date", "exit_date", "exit_type", "outcome",
        "exit_reason", "return_pct", "attribution_exception_codes",
    ]
    for field_key in field_keys:
        columns.extend([
            field_key,
            f"{field_key}.bucket",
            f"{field_key}.percentile",
            f"{field_key}.asof_date",
            f"{field_key}.staleness_trading_days",
            f"{field_key}.exception_code",
        ])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for sample in samples:
            sample_map = _as_mapping(sample)
            row = {key: sample_map.get(key) for key in columns if key in sample_map}
            row["attribution_exception_codes"] = ";".join(str(item) for item in _as_sequence(sample_map.get("attribution_exception_codes")))
            field_values = _as_mapping(sample_map.get("field_values"))
            for field_key in field_keys:
                payload = _as_mapping(field_values.get(field_key))
                row[field_key] = payload.get("raw")
                row[f"{field_key}.bucket"] = payload.get("bucket")
                row[f"{field_key}.percentile"] = payload.get("percentile")
                row[f"{field_key}.asof_date"] = payload.get("asof_date")
                row[f"{field_key}.staleness_trading_days"] = payload.get("staleness_trading_days")
                row[f"{field_key}.exception_code"] = ";".join(str(item) for item in _as_sequence(payload.get("exception_codes")))
            writer.writerow(row)


def _field_keys(field_index: Mapping[str, Any]) -> list[str]:
    return [str(_as_mapping(field).get("field_key")) for field in _as_sequence(field_index.get("fields"))]


def _representative_refs(rows: Sequence[Mapping[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    clean = [_as_mapping(row) for row in rows if _as_mapping(row).get("trade_index") is not None]
    if not clean:
        return []
    selected: list[Mapping[str, Any]] = []
    for key, reverse in (("return_pct", True), ("return_pct", False), ("net_pnl", True), ("net_pnl", False)):
        candidates = [row for row in clean if _optional_float(row.get(key)) is not None]
        if candidates:
            selected.append(sorted(candidates, key=lambda row: float(row[key]), reverse=reverse)[0])
    selected.extend(clean)
    refs = []
    seen = set()
    for row in selected:
        trade_index = _optional_int(row.get("trade_index"))
        if trade_index is None or trade_index in seen:
            continue
        seen.add(trade_index)
        refs.append({"kind": "trade", "trade_index": trade_index})
        if len(refs) >= limit:
            break
    return refs


def _top_bucket(field: Mapping[str, Any]) -> str:
    buckets = _as_sequence(field.get("bucket_distribution"))
    if not buckets:
        return "-"
    item = _as_mapping(buckets[0])
    return f"{item.get('value')}({item.get('count')})"


def _missing_field_payload(code: str) -> dict[str, Any]:
    return {
        "raw": None,
        "bucket": None,
        "percentile": None,
        "asof_date": None,
        "staleness_trading_days": None,
        "reference_count": None,
        "exception_codes": [code],
    }


def _derived_payload(
    *,
    raw: Any,
    bucket: Any,
    asof_date: str,
    reference_count: int | None,
    exception_codes: Sequence[str],
) -> dict[str, Any]:
    return {
        "raw": _jsonable(raw),
        "bucket": _jsonable(bucket),
        "percentile": None,
        "asof_date": asof_date,
        "staleness_trading_days": 0,
        "reference_count": reference_count,
        "exception_codes": list(exception_codes),
    }


def _atr_multiple_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number < -2:
        return "below_ma60_gt_2atr"
    if number < -1:
        return "below_ma60_1_2atr"
    if number < 0:
        return "below_ma60_0_1atr"
    if number <= 1:
        return "above_ma60_0_1atr"
    if number <= 2:
        return "above_ma60_1_2atr"
    return "above_ma60_gt_2atr"


def _signal_to_entry_return_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number < -0.05:
        return "gap_down_gt_5pct"
    if number < -0.02:
        return "gap_down_2_5pct"
    if number <= 0.02:
        return "flat_minus2_to_plus2pct"
    if number <= 0.05:
        return "gap_up_2_5pct"
    return "gap_up_gt_5pct"


def _holding_days_bucket(value: Any) -> str | None:
    number = _optional_int(value)
    if number is None:
        return None
    if number <= 3:
        return "d1_3"
    if number <= 10:
        return "d4_10"
    if number <= 20:
        return "d11_20"
    if number <= 40:
        return "d21_40"
    return "gt_40d"


def _max_favorable_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number < 0:
        return "never_positive"
    if number < 0.05:
        return "0_5pct"
    if number < 0.10:
        return "5_10pct"
    if number < 0.20:
        return "10_20pct"
    if number < 0.40:
        return "20_40pct"
    return "gte_40pct"


def _max_adverse_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number >= 0:
        return "no_adverse"
    if number >= -0.05:
        return "0_to_minus5pct"
    if number >= -0.10:
        return "minus5_to_minus10pct"
    if number >= -0.20:
        return "minus10_to_minus20pct"
    return "lt_minus20pct"


def _drawdown_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number < 0.05:
        return "0_5pct"
    if number < 0.10:
        return "5_10pct"
    if number < 0.20:
        return "10_20pct"
    if number < 0.40:
        return "20_40pct"
    return "gte_40pct"


def _index_drawdown_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number > -0.05:
        return "drawdown_0_5pct"
    if number > -0.15:
        return "drawdown_5_15pct"
    if number > -0.20:
        return "drawdown_15_20pct"
    return "drawdown_gt_20pct"


def _breadth_ratio_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number < 0.35:
        return "lt_35pct"
    if number < 0.45:
        return "35_45pct"
    if number < 0.55:
        return "45_55pct"
    if number < 0.65:
        return "55_65pct"
    return "gte_65pct"


def _first_profit_days_bucket(value: Any) -> str | None:
    number = _optional_int(value)
    if number is None:
        return "never"
    if number <= 1:
        return "day_1"
    if number <= 3:
        return "day_2_3"
    if number <= 10:
        return "day_4_10"
    if number <= 20:
        return "day_11_20"
    return "gt_20d"


def _dea_waterline_age_bucket(value: Any) -> str | None:
    number = _optional_int(value)
    if number is None:
        return None
    if number <= 0:
        return "day_0"
    if number <= 3:
        return "day_1_3"
    if number <= 7:
        return "day_4_7"
    if number <= 14:
        return "day_8_14"
    return "gt_14d"


def _positive_strength_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number <= 0:
        return "lte_0"
    if number < 0.001:
        return "0_0p1pct"
    if number < 0.003:
        return "0p1_0p3pct"
    if number < 0.006:
        return "0p3_0p6pct"
    return "gte_0p6pct"


def _signed_strength_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number <= 0:
        return "lte_0"
    if number < 0.001:
        return "0_0p1pct"
    if number < 0.003:
        return "0p1_0p3pct"
    if number < 0.006:
        return "0p3_0p6pct"
    return "gte_0p6pct"


def _ma_spread_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number <= 0:
        return "ma25_lte_ma60"
    if number < 0.02:
        return "0_2pct"
    if number < 0.05:
        return "2_5pct"
    if number < 0.10:
        return "5_10pct"
    return "gte_10pct"


def _ma60_slope_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number < -0.05:
        return "down_gt_5pct"
    if number < 0:
        return "down_0_5pct"
    if number < 0.02:
        return "flat_0_2pct"
    if number < 0.05:
        return "up_2_5pct"
    return "up_gt_5pct"


def _candle_body_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number < 0.01:
        return "lt_1pct"
    if number < 0.03:
        return "1_3pct"
    if number < 0.05:
        return "3_5pct"
    return "gte_5pct"


def _signal_shadow_payload(
    signal_row: Mapping[str, Any] | None,
    *,
    signal_open: float | None,
    signal_close: float | None,
) -> tuple[dict[str, float] | None, str | None]:
    row = _as_mapping(signal_row)
    high = _optional_float(row.get("high"))
    low = _optional_float(row.get("low"))
    if high is None or low is None or signal_open is None or signal_close is None or signal_close <= 0:
        return None, None
    upper = max(0.0, high - max(signal_open, signal_close)) / signal_close
    lower = max(0.0, min(signal_open, signal_close) - low) / signal_close
    payload = {"upper_shadow_pct": upper, "lower_shadow_pct": lower}
    if upper < 0.01 and lower < 0.01:
        return payload, "short_shadows"
    if upper >= lower * 2 and upper >= 0.01:
        return payload, "long_upper_shadow"
    if lower >= upper * 2 and lower >= 0.01:
        return payload, "long_lower_shadow"
    if upper >= 0.01 and lower >= 0.01:
        return payload, "both_long_shadows"
    return payload, "balanced_shadows"


def _latest_context_row(
    by_symbol: Mapping[str, Any],
    *,
    symbol: str,
    trade_date: str,
    strict_before: bool,
) -> Mapping[str, Any] | None:
    frame = by_symbol.get(symbol)
    if not isinstance(frame, pd.DataFrame) or frame.empty or not trade_date:
        return None
    if strict_before:
        rows = frame[frame["trade_date"] < trade_date]
    else:
        rows = frame[frame["trade_date"] <= trade_date]
    if rows.empty:
        return None
    return rows.iloc[-1].dropna().to_dict()


def _field_raw_or_bucket(payload: Any) -> Any:
    item = _as_mapping(payload)
    raw = item.get("raw")
    return raw if raw not in (None, "") else item.get("bucket")


def _set_missing_fields(
    field_values: dict[str, dict[str, Any]],
    field_keys: Sequence[str],
    *,
    asof_date: str,
    code: str,
) -> None:
    for field_key in field_keys:
        field_values[field_key] = _derived_payload(
            raw=None,
            bucket=None,
            asof_date=asof_date,
            reference_count=None,
            exception_codes=[code],
        )


def _weekly_ma_trend(row: Mapping[str, Any]) -> str | None:
    close = _optional_float(row.get("close"))
    ma5 = _optional_float(row.get("ma5"))
    ma10 = _optional_float(row.get("ma10"))
    ma20 = _optional_float(row.get("ma20"))
    if close is None or ma5 is None or ma10 is None or ma20 is None:
        return None
    if close > ma20 and ma5 > ma10 > ma20:
        return "uptrend"
    if close < ma20 and ma5 < ma10 < ma20:
        return "downtrend"
    return "mixed"


def _daily_trend_state(row: Mapping[str, Any]) -> str | None:
    close = _optional_float(row.get("close"))
    ma20 = _optional_float(row.get("ma20"))
    ma60 = _optional_float(row.get("ma60"))
    if close is None or ma20 is None or ma60 is None:
        return None
    if close > ma20 > ma60:
        return "bullish"
    if close < ma20 < ma60:
        return "bearish"
    return "mixed"


def _market_daily_return(
    market_context: Mapping[str, Any],
    symbol: str,
    signal_date: str,
    column: str,
) -> float | None:
    row = _latest_context_row(
        _as_mapping(market_context.get("by_symbol")),
        symbol=symbol,
        trade_date=signal_date,
        strict_before=False,
    )
    return _optional_float(_as_mapping(row).get(column))


def _industry_daily_return(
    field_values: Mapping[str, Any],
    industry_context: Mapping[str, Any],
    signal_date: str,
    column: str,
) -> float | None:
    industry_payload = _as_mapping(field_values.get("industry.sw_l1.code"))
    industry_code = _field_raw_or_bucket(industry_payload)
    if not industry_code:
        return None
    row = _latest_context_row(
        _as_mapping(industry_context.get("by_symbol")),
        symbol=str(industry_code),
        trade_date=signal_date,
        strict_before=False,
    )
    return _optional_float(_as_mapping(row).get(column))


def _kdj_j_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number < 13:
        return "<13"
    if number < 30:
        return "13-30"
    if number < 50:
        return "30-50"
    if number < 80:
        return "50-80"
    return ">=80"


def _kdj_state(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number < 13:
        return "oversold"
    if number < 50:
        return "recovering"
    if number < 80:
        return "strong"
    return "overheated"


def _near_high_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number >= -0.01:
        return "at_high"
    if number >= -0.03:
        return "near_high"
    if number >= -0.08:
        return "moderate_pullback"
    if number >= -0.15:
        return "deep_pullback"
    return "far_from_high"


def _percentile_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number <= 0.2:
        return "p0_p20"
    if number <= 0.4:
        return "p20_p40"
    if number <= 0.6:
        return "p40_p60"
    if number <= 0.8:
        return "p60_p80"
    return "p80_p100"


def _volatility_pct_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None or number < 0:
        return None
    if number < 0.01:
        return "lt_1pct"
    if number < 0.02:
        return "1_2pct"
    if number < 0.03:
        return "2_3pct"
    if number < 0.05:
        return "3_5pct"
    return "gte_5pct"


def _ma20_distance_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number < -0.10:
        return "below_gt_10pct"
    if number < 0:
        return "below_0_10pct"
    if number < 0.05:
        return "above_0_5pct"
    if number < 0.15:
        return "above_5_15pct"
    return "above_gt_15pct"


def _relative_return_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number < -0.10:
        return "underperform_gt_10pct"
    if number < -0.03:
        return "underperform_3_10pct"
    if number < 0:
        return "underperform_0_3pct"
    if number < 0.03:
        return "outperform_0_3pct"
    if number < 0.10:
        return "outperform_3_10pct"
    return "outperform_gt_10pct"


def _path_atr_multiple_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number < -4:
        return "negative_gt_4atr"
    if number < -2:
        return "negative_2_4atr"
    if number < -1:
        return "negative_1_2atr"
    if number < 0:
        return "negative_0_1atr"
    if number < 1:
        return "positive_0_1atr"
    if number < 2:
        return "positive_1_2atr"
    if number < 4:
        return "positive_2_4atr"
    return "positive_gt_4atr"


def _threshold_reached_bucket(value: Any, *, threshold: float) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    return "reached" if number >= threshold else "not_reached"


def _signed_return_bucket(value: Any) -> str | None:
    number = _optional_float(value)
    if number is None:
        return None
    if number < -0.10:
        return "down_gt_10pct"
    if number < -0.05:
        return "down_5_10pct"
    if number < 0:
        return "down_0_5pct"
    if number < 0.03:
        return "up_0_3pct"
    if number < 0.05:
        return "up_3_5pct"
    if number < 0.10:
        return "up_5_10pct"
    return "up_gt_10pct"


def _diagnostic_bool_bucket(value: bool | None) -> str | None:
    if value is None:
        return None
    return "yes" if value else "no"


def _scope_from_field(field_key: str) -> str:
    parts = field_key.split(".")
    return parts[1] if parts and parts[0] == "entry" and len(parts) > 1 else parts[0]


def _exception_codes(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item for item in value.split(";") if item]
    return [str(item) for item in _as_sequence(value)]


def _decode_reference_cell(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _stable_value_key(value: Any) -> str:
    return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True)


def _jsonable(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _format_percent(value: Any) -> str:
    number = _optional_float(value)
    if number is None:
        return "-"
    return f"{number * 100:.2f}%"


def _escape_cell(value: Any) -> str:
    return str(value).replace("|", "/") if value is not None else "-"


def _run_id(run_path: Path, run_plan: Mapping[str, Any]) -> str:
    return str(_as_mapping(run_plan.get("run")).get("id", run_path.name))


def _load_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, (list, tuple)) else ()


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _to_pretty_json(payload: Any) -> str:
    return json.dumps(_jsonable(payload), ensure_ascii=False, indent=2)
