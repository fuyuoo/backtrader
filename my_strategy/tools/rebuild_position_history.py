"""Post-hoc 重建逐日持仓快照。
输入:
    trades: results/trade_summary.csv
    dailies: data/daily/{ts_code}.csv 集合
    sector_map: data/stock_sector.csv
输出:
    results/daily_position_pnl.csv
    results/daily_portfolio_snapshot.csv
不修改 backtest.py。
"""
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd


def build_daily_position_pnl(
    trades: pd.DataFrame,
    dailies: Dict[str, pd.DataFrame],
    sector_map: pd.DataFrame,
) -> pd.DataFrame:
    """逐笔交易展开成 (trade_id, date) 长表，含 cum_return_pct / drawdown_from_peak_pct / sector_code。"""
    sec_lookup = dict(zip(sector_map['ts_code'], sector_map['sw_index_code']))
    rows = []
    for trade_id, t in trades.reset_index(drop=True).iterrows():
        ts_code = t['ts_code']
        entry = pd.to_datetime(t['entry_date'])
        exit_ = pd.to_datetime(t['exit_date']) if pd.notna(t.get('exit_date')) else None
        cost = float(t['avg_cost'])

        if ts_code not in dailies:
            raise KeyError(f"daily data missing for {ts_code} (trade_id={trade_id})")
        df = dailies[ts_code].copy()
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)

        if exit_ is None:
            sub = df[df['date'] >= entry]
        else:
            sub = df[(df['date'] >= entry) & (df['date'] <= exit_)]
        if sub.empty:
            raise ValueError(f"no daily rows in [{entry}, {exit_}] for {ts_code}")

        cum_return_pct = (sub['close'].values - cost) / cost * 100.0
        running_peak = np.maximum.accumulate(sub['close'].values)
        drawdown_from_peak_pct = (sub['close'].values - running_peak) / running_peak * 100.0

        for i, (_, r) in enumerate(sub.iterrows()):
            rows.append({
                'trade_id': trade_id,
                'ts_code': ts_code,
                'entry_date': entry,
                'holding_day_n': i,
                'date': r['date'],
                'close': float(r['close']),
                'cum_return_pct': float(cum_return_pct[i]),
                'drawdown_from_peak_pct': float(drawdown_from_peak_pct[i]),
                'sector_code': sec_lookup.get(ts_code),
            })
    return pd.DataFrame(rows)


def build_daily_portfolio_snapshot(daily_position_pnl: pd.DataFrame) -> pd.DataFrame:
    """按 date 聚合，输出每日组合层指标：n_positions, sectors_held, top_sector_share, herfindahl_index。"""
    rows = []
    for date, g in daily_position_pnl.groupby('date'):
        n = len(g)
        sec_counts = g['sector_code'].value_counts(dropna=False)
        sectors_held = sec_counts[sec_counts.index.notna()].shape[0]
        if n == 0:
            continue
        shares = (sec_counts / n).values
        herfindahl = float((shares ** 2).sum())
        top_sec = sec_counts.index[0]
        top_share = float(sec_counts.iloc[0] / n)
        rows.append({
            'date': date,
            'n_positions': n,
            'sectors_held': int(sectors_held),
            'top_sector_code': top_sec,
            'top_sector_share': top_share,
            'herfindahl_index': herfindahl,
        })
    return pd.DataFrame(rows).sort_values('date').reset_index(drop=True)


def build(project_root: Path, cfg: dict) -> None:
    """从 results/trade_summary.csv + data/daily/{ts_code}.csv + stock_sector.csv 重建并写盘。

    注：实际 daily CSV 使用 trade_date 列名（非 date），此函数读取后重命名再传入。
    daily 文件路径为 data/daily/{ts_code}.csv（非 data/{ts_code}_daily.csv）。
    """
    project_root = Path(project_root)
    results_dir = project_root / cfg.get('results_dir', 'results/')
    trades_path = results_dir / 'trade_summary.csv'
    if not trades_path.exists():
        raise FileNotFoundError(f"trade_summary not found at {trades_path}")
    trades = pd.read_csv(trades_path, parse_dates=['entry_date', 'exit_date'])

    data_dir = project_root / cfg.get('data_dir', 'data/')
    sector_csv = project_root / cfg['data_paths']['stock_sector_csv']
    sector_map = pd.read_csv(sector_csv)

    dailies = {}
    for ts_code in trades['ts_code'].unique():
        # 实际路径为 data/daily/{ts_code}.csv，不是 data/{ts_code}_daily.csv
        path = data_dir / 'daily' / f'{ts_code}.csv'
        if not path.exists():
            raise FileNotFoundError(f"daily file missing: {path}")
        df = pd.read_csv(path)
        # 磁盘文件用 trade_date 列；统一重命名为 date 供 build_daily_position_pnl 使用
        df = df.rename(columns={'trade_date': 'date'})
        dailies[ts_code] = df[['date', 'close']]

    pnl = build_daily_position_pnl(trades, dailies, sector_map)
    snap = build_daily_portfolio_snapshot(pnl)

    pnl.to_csv(results_dir / 'daily_position_pnl.csv', index=False)
    snap.to_csv(results_dir / 'daily_portfolio_snapshot.csv', index=False)
