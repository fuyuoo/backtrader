"""基于 daily_position_pnl / daily_portfolio_snapshot / trade_list 的报告（4 张）。"""
from pathlib import Path

import numpy as np
import pandas as pd

_HOLDING_SAMPLE_DAYS = [1, 2, 3, 5, 7, 10, 15, 20, 25, 30, 40, 50, 60, 75, 90]


def compute_holding_period_curve(daily_position_pnl: pd.DataFrame) -> pd.DataFrame:
    sample_points = [0] + _HOLDING_SAMPLE_DAYS
    rows = []
    for n in sample_points:
        sub = daily_position_pnl[daily_position_pnl['holding_day_n'] == n]
        if sub.empty:
            continue
        r = sub['cum_return_pct'].dropna()
        dd = sub['drawdown_from_peak_pct'].dropna()
        rows.append({
            'holding_day_n': n,
            'n_active_trades': len(sub),
            'avg_cum_return': round(float(r.mean()), 4) if len(r) else np.nan,
            'median_cum_return': round(float(r.median()), 4) if len(r) else np.nan,
            'win_rate_at_day_n': round(float((r > 0).mean()), 4) if len(r) else np.nan,
            'p25_cum_return': round(float(r.quantile(0.25)), 4) if len(r) else np.nan,
            'p75_cum_return': round(float(r.quantile(0.75)), 4) if len(r) else np.nan,
            'avg_drawdown_from_peak': round(float(dd.mean()), 4) if len(dd) else np.nan,
        })
    return pd.DataFrame(rows)


def compute_mfe_timing(daily_position_pnl: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for trade_id, g in daily_position_pnl.groupby('trade_id'):
        if g.empty:
            continue
        max_day = int(g['holding_day_n'].max())
        if max_day == 0:
            continue
        peak_idx = g['cum_return_pct'].idxmax()
        peak_day = int(g.loc[peak_idx, 'holding_day_n'])
        peak_value = float(g.loc[peak_idx, 'cum_return_pct'])
        ratio = peak_day / max_day
        if ratio <= 1/3:
            bucket = '早期(前 1/3)'
        elif ratio <= 2/3:
            bucket = '中期(中 1/3)'
        else:
            bucket = '晚期(后 1/3)'
        final_return = float(g.iloc[-1]['cum_return_pct'])
        rows.append({
            'trade_id': trade_id,
            'mfe_timing_bucket': bucket,
            'holding_days': max_day,
            'final_return': final_return,
            'mfe_pct': peak_value,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    out = df.groupby('mfe_timing_bucket').agg(
        n=('trade_id', 'count'),
        win_rate=('final_return', lambda s: (s > 0).mean()),
        avg_return=('final_return', 'mean'),
        avg_holding_days=('holding_days', 'mean'),
        avg_mfe_pct=('mfe_pct', 'mean'),
    ).reset_index()
    for c in ['win_rate', 'avg_return', 'avg_holding_days', 'avg_mfe_pct']:
        out[c] = out[c].round(4)
    return out


def compute_sector_concentration_stats(
    daily_portfolio_snapshot: pd.DataFrame,
    top_n: int = 10,
) -> pd.DataFrame:
    snap = daily_portfolio_snapshot
    rows = []
    summary_specs = [
        ('avg_max_sector_share', 'top_sector_share', lambda s: s.mean()),
        ('p95_max_sector_share', 'top_sector_share', lambda s: s.quantile(0.95)),
        ('max_max_sector_share', 'top_sector_share', lambda s: s.max()),
        ('avg_herfindahl_index', 'herfindahl_index', lambda s: s.mean()),
        ('p95_herfindahl_index', 'herfindahl_index', lambda s: s.quantile(0.95)),
    ]
    for label, col, fn in summary_specs:
        if col not in snap.columns:
            continue
        rows.append({
            'metric_type': 'summary',
            'label': label,
            'value': round(float(fn(snap[col])), 4),
            'top_sector_code': '',
            'top_sector_share': np.nan,
            'herfindahl_index': np.nan,
            'n_positions': np.nan,
        })
    top = snap.sort_values('top_sector_share', ascending=False).head(top_n)
    for _, r in top.iterrows():
        rows.append({
            'metric_type': 'top_concentrated_day',
            'label': str(pd.to_datetime(r['date']).date()),
            'value': np.nan,
            'top_sector_code': r['top_sector_code'],
            'top_sector_share': round(float(r['top_sector_share']), 4),
            'herfindahl_index': round(float(r['herfindahl_index']), 4),
            'n_positions': int(r['n_positions']),
        })
    return pd.DataFrame(rows)


def _cost_block(sub: pd.DataFrame, dimension: str, bucket: str, cfg: dict) -> dict:
    n = len(sub)
    if n == 0:
        return None
    if 'commission' in sub.columns and 'stamp_duty' in sub.columns:
        commission = float(sub['commission'].fillna(0).sum())
        stamp = float(sub['stamp_duty'].fillna(0).sum())
        turnover = float(sub['turnover'].fillna(0).sum()) if 'turnover' in sub.columns else np.nan
    else:
        comm_rate = float(cfg.get('commission_rate', 0.0003))
        stamp_rate = float(cfg.get('stamp_duty', 0.001))
        turnover = float(sub['turnover'].fillna(0).sum()) if 'turnover' in sub.columns else np.nan
        sell_amt = (float(sub['sell_amount'].fillna(0).sum())
                    if 'sell_amount' in sub.columns else turnover / 2 if pd.notna(turnover) else np.nan)
        commission = comm_rate * turnover if pd.notna(turnover) else np.nan
        stamp = stamp_rate * sell_amt if pd.notna(sell_amt) else np.nan
    gross = float(sub['gross_pnl'].fillna(0).sum()) if 'gross_pnl' in sub.columns else np.nan
    total_cost = (commission if pd.notna(commission) else 0.0) + (stamp if pd.notna(stamp) else 0.0)
    net = gross - total_cost if pd.notna(gross) else np.nan
    return {
        'dimension': dimension,
        'bucket': bucket,
        'n_trades': n,
        'gross_pnl': round(gross, 2) if pd.notna(gross) else np.nan,
        'total_commission': round(commission, 2) if pd.notna(commission) else np.nan,
        'total_stamp_duty': round(stamp, 2) if pd.notna(stamp) else np.nan,
        'net_pnl': round(net, 2) if pd.notna(net) else np.nan,
        'cost_pct_of_gross': round(total_cost / abs(gross), 4) if pd.notna(gross) and gross != 0 else np.nan,
        'cost_pct_of_turnover': round(total_cost / turnover, 6) if pd.notna(turnover) and turnover > 0 else np.nan,
    }


def compute_cost_breakdown(trades: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    rows = [_cost_block(trades, 'overall', 'all', cfg)]
    if 'entry_date' in trades.columns:
        for y, sub in trades.groupby(pd.to_datetime(trades['entry_date']).dt.year):
            rows.append(_cost_block(sub, 'year', str(int(y)), cfg))
    if 'exit_reason' in trades.columns:
        for v, sub in trades.groupby('exit_reason'):
            rows.append(_cost_block(sub, 'exit_reason', str(v), cfg))
    return pd.DataFrame([r for r in rows if r is not None])


# 模块入口
def run(project_root: Path, cfg: dict) -> None:
    project_root = Path(project_root)
    results_dir = project_root / cfg.get('results_dir', 'results/')
    out_dir = project_root / cfg['attribution_report_dir']
    out_dir.mkdir(parents=True, exist_ok=True)

    pnl_path = results_dir / 'daily_position_pnl.csv'
    snap_path = results_dir / 'daily_portfolio_snapshot.csv'
    if not pnl_path.exists():
        raise FileNotFoundError(f"daily_position_pnl missing: {pnl_path}")
    if not snap_path.exists():
        raise FileNotFoundError(f"daily_portfolio_snapshot missing: {snap_path}")
    pnl = pd.read_csv(pnl_path, parse_dates=['entry_date', 'date'])
    snap = pd.read_csv(snap_path, parse_dates=['date'])

    compute_holding_period_curve(pnl).to_csv(out_dir / 'holding_period_curve.csv', index=False)
    compute_mfe_timing(pnl).to_csv(out_dir / 'mfe_timing.csv', index=False)
    compute_sector_concentration_stats(snap).to_csv(out_dir / 'sector_concentration_stats.csv', index=False)

    trade_list_path = results_dir / 'trade_list.csv'
    if trade_list_path.exists():
        trade_list = pd.read_csv(trade_list_path, parse_dates=['entry_date']) \
                     if 'entry_date' in pd.read_csv(trade_list_path, nrows=0).columns \
                     else pd.read_csv(trade_list_path)
    else:
        # 退回到 trade_summary
        trade_list = pd.read_csv(results_dir / 'trade_summary.csv', parse_dates=['entry_date'])
    compute_cost_breakdown(trade_list, cfg).to_csv(out_dir / 'cost_breakdown.csv', index=False)
