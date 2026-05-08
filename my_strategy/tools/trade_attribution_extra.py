"""Trade-level 扩展归因报告（5 张）。输入: trade_summary.csv。"""
from pathlib import Path

import numpy as np
import pandas as pd

from my_strategy.tools.stats_helpers import t_test_one_sample, t_test_welch, bucket_stats_with_significance


def _payoff_block(sub: pd.DataFrame, dimension: str, bucket: str) -> dict:
    n = len(sub)
    if n == 0:
        return None
    r = sub['return_pct']
    wins = r[r > 0]
    losses = r[r < 0]
    n_wins = len(wins)
    n_losses = len(losses)
    avg_win = wins.mean() if n_wins > 0 else 0.0
    avg_loss = losses.mean() if n_losses > 0 else 0.0
    sum_win = wins.sum() if n_wins > 0 else 0.0
    sum_loss = losses.sum() if n_losses > 0 else 0.0
    payoff = (avg_win / abs(avg_loss)) if avg_loss < 0 else np.nan
    profit_factor = (sum_win / abs(sum_loss)) if sum_loss < 0 else np.nan
    win_rate = n_wins / n if n > 0 else 0.0
    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
    return {
        'dimension': dimension,
        'bucket': bucket,
        'n': n,
        'win_rate': round(win_rate, 4),
        'avg_win': round(float(avg_win), 4),
        'avg_loss': round(float(avg_loss), 4),
        'payoff_ratio': float(payoff) if pd.notna(payoff) else np.nan,
        'profit_factor': float(profit_factor) if pd.notna(profit_factor) else np.nan,
        'expectancy': round(float(expectancy), 4),
        'max_win': round(float(r.max()), 4),
        'max_loss': round(float(r.min()), 4),
    }


def compute_payoff_metrics(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    rows.append(_payoff_block(trades, 'overall', 'all'))
    if 'exit_reason' in trades.columns:
        for v, sub in trades.groupby('exit_reason'):
            rows.append(_payoff_block(sub, 'exit_reason', str(v)))
    if 'entry_date' in trades.columns:
        years = pd.to_datetime(trades['entry_date']).dt.year
        for y, sub in trades.groupby(years):
            rows.append(_payoff_block(sub, 'year', str(int(y))))
    if 'industry' in trades.columns:
        for v, sub in trades.groupby('industry'):
            if pd.notna(v):
                rows.append(_payoff_block(sub, 'sector', str(v)))
    if {'entry_hs300_dif_above_zero', 'entry_stock_bull_align'}.issubset(trades.columns):
        for (a, b), sub in trades.groupby(
            ['entry_hs300_dif_above_zero', 'entry_stock_bull_align']
        ):
            label = f"hs300_dif={a}|stock_bull={b}"
            rows.append(_payoff_block(sub, 'regime', label))
    return pd.DataFrame([r for r in rows if r is not None])


def _enumerate_signal_values(trades: pd.DataFrame, signal: str) -> list:
    """对一个信号字段返回 [(value_label, mask_series), ...]"""
    s = trades[signal]
    if s.dtype == bool or set(s.dropna().unique()) <= {True, False, 'True', 'False'}:
        return [
            (f"{signal}=True", s.astype(str).isin(['True'])),
            (f"{signal}=False", s.astype(str).isin(['False'])),
        ]
    if s.dtype == 'object':
        return [(f"{signal}={v}", s == v) for v in sorted(s.dropna().unique().astype(str))]
    # 数值列 → 5 分位
    qs = pd.qcut(s, q=5, labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'], duplicates='drop')
    return [(f"{signal}={lbl}", qs == lbl) for lbl in qs.dropna().unique()]


def compute_signal_stability(trades: pd.DataFrame, signals_whitelist: list) -> pd.DataFrame:
    rows = []
    if 'entry_date' not in trades.columns:
        return pd.DataFrame()
    years = pd.to_datetime(trades['entry_date']).dt.year
    for signal in signals_whitelist:
        if signal not in trades.columns:
            continue
        for label, mask in _enumerate_signal_values(trades, signal):
            sub = trades[mask]
            sub_years = years[mask]
            for y, g in sub.groupby(sub_years):
                r = g['return_pct'].dropna()
                if len(r) == 0:
                    continue
                t_stat, p_val = t_test_one_sample(r) if len(r) >= 2 else (np.nan, np.nan)
                rows.append({
                    'signal_name': label,
                    'period_year': int(y),
                    'n': len(r),
                    'win_rate': round(float((r > 0).mean()), 4),
                    'avg_return': round(float(r.mean()), 4),
                    't_stat_vs_zero': round(t_stat, 4) if pd.notna(t_stat) else np.nan,
                    'p_value': round(p_val, 4) if pd.notna(p_val) else np.nan,
                })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df['rank_within_signal'] = (
        df.groupby('signal_name')['avg_return']
          .rank(method='dense', ascending=False).astype(int)
    )
    return df


def compute_signal_correlation_matrix(trades: pd.DataFrame, signals_whitelist: list) -> pd.DataFrame:
    """两两相关性（Pearson + Spearman），long format。布尔列先转 0/1。"""
    cols = [c for c in signals_whitelist if c in trades.columns]
    df = trades[cols].copy()
    for c in cols:
        if df[c].dtype == bool or set(df[c].dropna().astype(str).unique()) <= {'True', 'False'}:
            df[c] = df[c].astype(str).map({'True': 1, 'False': 0})
        elif df[c].dtype == 'object':
            df[c] = pd.factorize(df[c])[0]
        df[c] = pd.to_numeric(df[c], errors='coerce')
    rows = []
    for i, a in enumerate(cols):
        for b in cols[i+1:]:
            sub = df[[a, b]].dropna()
            if len(sub) < 2:
                continue
            pearson = sub[a].corr(sub[b], method='pearson')
            spearman = sub[a].corr(sub[b], method='spearman')
            rows.append({
                'signal_a': a, 'signal_b': b,
                'pearson_r': round(float(pearson), 4) if pd.notna(pearson) else np.nan,
                'spearman_r': round(float(spearman), 4) if pd.notna(spearman) else np.nan,
                'n': len(sub),
            })
    return pd.DataFrame(rows)


def compute_multi_factor_combo_stats(
    trades: pd.DataFrame,
    combos: list,
    min_sample: int = 100,
) -> pd.DataFrame:
    """对每个 (a, b, c) 三元组做交叉聚合。combos: [(name_a, name_b, name_c), ...]"""
    overall = trades['return_pct'].dropna()
    rows = []
    for a, b, c in combos:
        if not all(col in trades.columns for col in (a, b, c)):
            continue
        for (va, vb, vc), sub in trades.groupby([a, b, c], dropna=False):
            r = sub['return_pct'].dropna()
            n = len(r)
            if n == 0:
                continue
            t_stat, p_val = (np.nan, np.nan)
            if n >= 2:
                t_stat, p_val = t_test_welch(r, overall)
            rows.append({
                'signal_a_name': a, 'signal_a_value': str(va),
                'signal_b_name': b, 'signal_b_value': str(vb),
                'signal_c_name': c, 'signal_c_value': str(vc),
                'n': n,
                'win_rate': round(float((r > 0).mean()), 4),
                'avg_return': round(float(r.mean()), 4),
                't_stat_vs_overall': round(t_stat, 4) if pd.notna(t_stat) else np.nan,
                'p_value_vs_overall': round(p_val, 4) if pd.notna(p_val) else np.nan,
                'low_sample_warning': n < min_sample,
            })
    return pd.DataFrame(rows)


_SIGNIFICANCE_TARGETS = [
    # (report_name, bucket_field, value_extractor)
    # value_extractor 接收 trades，返回 {bucket_value: series_of_returns}
    ('exit_reason_stats', 'exit_reason',
     lambda t: {str(v): g['return_pct'] for v, g in t.groupby('exit_reason')}
        if 'exit_reason' in t.columns else {}),
    ('hs300_dif_stats', 'entry_hs300_dif_above_zero',
     lambda t: {str(v): g['return_pct'] for v, g in t.groupby('entry_hs300_dif_above_zero')}
        if 'entry_hs300_dif_above_zero' in t.columns else {}),
    ('hs300_bull_align_stats', 'entry_hs300_bull_align',
     lambda t: {str(v): g['return_pct'] for v, g in t.groupby('entry_hs300_bull_align')}
        if 'entry_hs300_bull_align' in t.columns else {}),
    ('stock_bull_align_stats', 'entry_stock_bull_align',
     lambda t: {str(v): g['return_pct'] for v, g in t.groupby('entry_stock_bull_align')}
        if 'entry_stock_bull_align' in t.columns else {}),
    ('stock_above_ma25_stats', 'entry_stock_above_ma25',
     lambda t: {str(v): g['return_pct'] for v, g in t.groupby('entry_stock_above_ma25')}
        if 'entry_stock_above_ma25' in t.columns else {}),
    ('sector_bull_align_stats', 'entry_sector_bull_align',
     lambda t: {str(v): g['return_pct'] for v, g in t.groupby('entry_sector_bull_align')}
        if 'entry_sector_bull_align' in t.columns else {}),
    ('sector_above_ma25_stats', 'entry_sector_above_ma25',
     lambda t: {str(v): g['return_pct'] for v, g in t.groupby('entry_sector_above_ma25')}
        if 'entry_sector_above_ma25' in t.columns else {}),
    ('sector_dif_stats', 'entry_sector_dif_above_zero',
     lambda t: {str(v): g['return_pct'] for v, g in t.groupby('entry_sector_dif_above_zero')}
        if 'entry_sector_dif_above_zero' in t.columns else {}),
    ('sector_week_macd_stats', 'entry_sector_week_macd_zone',
     lambda t: {str(v): g['return_pct'] for v, g in t.groupby('entry_sector_week_macd_zone')}
        if 'entry_sector_week_macd_zone' in t.columns else {}),
    ('sector_month_macd_stats', 'entry_sector_month_macd_zone',
     lambda t: {str(v): g['return_pct'] for v, g in t.groupby('entry_sector_month_macd_zone')}
        if 'entry_sector_month_macd_zone' in t.columns else {}),
    ('yearly_stats', 'year',
     lambda t: {str(int(y)): g['return_pct'] for y, g in t.groupby(pd.to_datetime(t['entry_date']).dt.year)}
        if 'entry_date' in t.columns else {}),
]


def compute_significance_summary(trades: pd.DataFrame) -> pd.DataFrame:
    overall = trades['return_pct'].dropna()
    out_rows = []
    for report_name, bucket_field, extractor in _SIGNIFICANCE_TARGETS:
        grouped = extractor(trades)   # NO try/except wrapper — real errors surface per CLAUDE.md policy
        if not grouped:
            continue
        sub = bucket_stats_with_significance(grouped, overall)
        if sub.empty:
            continue
        sub['report_name'] = report_name
        sub['bucket_field'] = bucket_field
        sub.rename(columns={'bucket': 'bucket_value'}, inplace=True)
        out_rows.append(sub)
    if not out_rows:
        return pd.DataFrame()
    return pd.concat(out_rows, ignore_index=True)[[
        'report_name', 'bucket_field', 'bucket_value',
        'n', 'mean_return', 'std_return', 'std_err',
        'ci_low_95', 'ci_high_95',
        't_stat_vs_zero', 'p_value_vs_zero',
        't_stat_vs_overall', 'p_value_vs_overall',
        'low_sample_warning', 'significant_flag',
    ]]


# 模块入口
def run(trades: pd.DataFrame, out_dir: Path, signals_whitelist: list, combos: list) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    compute_payoff_metrics(trades).to_csv(out_dir / 'payoff_metrics.csv', index=False)
    compute_signal_stability(trades, signals_whitelist).to_csv(out_dir / 'signal_stability.csv', index=False)
    compute_signal_correlation_matrix(trades, signals_whitelist).to_csv(out_dir / 'signal_correlation_matrix.csv', index=False)
    compute_multi_factor_combo_stats(trades, combos).to_csv(out_dir / 'multi_factor_combo_stats.csv', index=False)
    compute_significance_summary(trades).to_csv(out_dir / 'significance_summary.csv', index=False)
