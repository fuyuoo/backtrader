"""顶层编排：依次调用 rebuild_position_history → 旧 attribution → 3 个新模块。"""
from pathlib import Path

import pandas as pd

from my_strategy.tools import (
    attribution as old_attribution,
    rebuild_position_history,
    trade_attribution_extra,
    portfolio_attribution,
    position_curve_attribution,
)


# 默认信号白名单（Task 0 调研后可替换）
DEFAULT_SIGNALS_WHITELIST = [
    'entry_hs300_dif_above_zero', 'entry_hs300_bull_align',
    'entry_stock_bull_align', 'entry_stock_above_ma25',
    'entry_sector_bull_align', 'entry_sector_above_ma25',
    'entry_sector_dif_above_zero',
    'entry_sector_week_macd_zone', 'entry_sector_month_macd_zone',
    'entry_month_macd_zone', 'entry_week_macd_zone',
    'ma_alignment',
    'factor_momentum_60d', 'factor_ma60_dist',
]

DEFAULT_COMBOS = [
    ('entry_hs300_dif_above_zero', 'entry_sector_dif_above_zero', 'entry_stock_bull_align'),
    ('entry_sector_above_ma25', 'entry_stock_above_ma25', 'entry_month_macd_zone'),
    ('entry_hs300_bull_align', 'entry_sector_bull_align', 'entry_stock_bull_align'),
]


def run(
    project_root: Path,
    cfg: dict,
    daily_ret: pd.Series,
    position_count_log,
    benchmarks: dict,
) -> None:
    project_root = Path(project_root)
    out_dir = project_root / cfg['attribution_report_dir']

    # 1) 数据补齐
    rebuild_position_history.build(project_root, cfg)

    # 2) 旧归因（保持原行为）
    old_attribution.run(project_root, cfg)

    # 3) trade-level 扩展
    trades_path = project_root / cfg.get('results_dir', 'results/') / 'trade_summary.csv'
    trades = pd.read_csv(trades_path, parse_dates=['entry_date'])
    trade_attribution_extra.run(
        trades, out_dir, DEFAULT_SIGNALS_WHITELIST, DEFAULT_COMBOS
    )

    # 4) portfolio-level
    portfolio_attribution.run(
        daily_ret, position_count_log, benchmarks, trades, cfg, out_dir
    )

    # 5) position-curve
    position_curve_attribution.run(project_root, cfg)
