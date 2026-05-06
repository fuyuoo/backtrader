import pandas as pd
import numpy as np
from pathlib import Path


def _bucket(return_pct):
    if return_pct > 10: return '大盈'
    if return_pct > 0: return '小盈'
    if return_pct == 0: return '持平'
    if return_pct > -10: return '小亏'
    return '大亏'


def _join_trades_with_signals(trades, signals):
    """按 (ts_code, entry_date) 关联 trade_log 和 signals_log。"""
    s = signals.copy()
    s['date'] = pd.to_datetime(s['date'])
    t = trades.copy()
    t['entry_date'] = pd.to_datetime(t['entry_date'])
    return t.merge(s, left_on=['ts_code', 'entry_date'],
                   right_on=['ts_code', 'date'], how='left')


def compute_trade_profile(trades, signals):
    """按收益分桶统计因子均值/中位数。"""
    j = _join_trades_with_signals(trades, signals)
    j['bucket'] = j['return_pct'].apply(_bucket)
    factor_cols = [c for c in j.columns
                   if c.startswith('pct_') or c.startswith('factor_')]
    rows = []
    for bucket, sub in j.groupby('bucket'):
        row = {'bucket': bucket, 'count': len(sub),
               'avg_return': round(sub['return_pct'].mean(), 4),
               'avg_holding_days': round(sub['holding_days'].mean(), 1)
               if 'holding_days' in sub.columns else None}
        for c in factor_cols:
            row[f'mean_{c}'] = round(sub[c].mean(), 6) if not sub[c].dropna().empty else None
            row[f'median_{c}'] = round(sub[c].median(), 6) if not sub[c].dropna().empty else None
        rows.append(row)
    return pd.DataFrame(rows).sort_values('bucket')


def compute_top_bottom_trades(trades, signals, n=10):
    j = _join_trades_with_signals(trades, signals)
    j_sorted = j.sort_values('return_pct', ascending=False)
    return j_sorted.head(n).reset_index(drop=True), j_sorted.tail(n).iloc[::-1].reset_index(drop=True)


def compute_sector_winrate(trades, signals):
    j = _join_trades_with_signals(trades, signals)
    rows = []
    for sector, sub in j.groupby('sector'):
        rows.append({
            'sector': sector,
            'count': len(sub),
            'win_rate': round((sub['return_pct'] > 0).mean(), 4),
            'avg_return': round(sub['return_pct'].mean(), 4),
        })
    return pd.DataFrame(rows).sort_values('avg_return', ascending=False)


def compute_factor_alpha(signals, top_n=3, factors=None,
                         horizon='forward_return_20d'):
    """对每个因子，按当日截面排序取 Top-N，计算事后 forward_return 平均收益。

    与"全部信号平均"基准对比，超额部分即该因子的 alpha 贡献。
    """
    s = signals.copy()
    if factors is None:
        factors = [c for c in s.columns if c.startswith('pct_')]

    s = s.dropna(subset=[horizon])
    baseline_avg = s[horizon].mean()

    rows = []
    for factor in factors:
        if factor not in s.columns:
            continue
        sub = s.dropna(subset=[factor])
        top = (sub.sort_values(['date', factor], ascending=[True, False])
                  .groupby('date').head(top_n))
        if top.empty:
            continue
        top_avg = top[horizon].mean()
        rows.append({
            'factor': factor,
            'top_n_avg': round(top_avg, 6),
            'baseline_avg': round(baseline_avg, 6),
            'alpha': round(top_avg - baseline_avg, 6),
            'sample_size': len(top),
        })
    return pd.DataFrame(rows).sort_values('alpha', ascending=False)


def main():
    import json
    project_root = Path(__file__).resolve().parent.parent
    cfg = json.loads((project_root / 'config.json').read_text())
    sig_path = project_root / cfg['signals_log_path']
    trade_path = project_root / 'results' / 'trade_log.csv'
    out_dir = project_root / cfg['attribution_report_dir']
    out_dir.mkdir(parents=True, exist_ok=True)

    signals = pd.read_csv(sig_path, parse_dates=['date'])
    trades = pd.read_csv(trade_path, parse_dates=['entry_date'])

    profile = compute_trade_profile(trades, signals)
    profile.to_csv(out_dir / 'trade_profile.csv', index=False)

    top, bottom = compute_top_bottom_trades(trades, signals, n=10)
    top.to_csv(out_dir / 'top_trades.csv', index=False)
    bottom.to_csv(out_dir / 'bottom_trades.csv', index=False)

    sector = compute_sector_winrate(trades, signals)
    sector.to_csv(out_dir / 'sector_winrate.csv', index=False)

    factor_alpha = compute_factor_alpha(signals)
    factor_alpha.to_csv(out_dir / 'factor_alpha.csv', index=False)

    print(f"attribution reports written to {out_dir}")


if __name__ == '__main__':
    main()
