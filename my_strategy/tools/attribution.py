import pandas as pd
import numpy as np
from pathlib import Path


def _spearman_r(x, y):
    """Spearman rank correlation using numpy (no scipy dependency)."""
    rx = pd.Series(x).rank()
    ry = pd.Series(y).rank()
    return float(np.corrcoef(rx, ry)[0, 1])


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
    """按收益分桶统计因子均值/中位数/25%/75%分位数。"""
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
            valid = sub[c].dropna()
            if valid.empty:
                row[f'mean_{c}'] = None
                row[f'median_{c}'] = None
                row[f'q25_{c}'] = None
                row[f'q75_{c}'] = None
            else:
                row[f'mean_{c}'] = round(valid.mean(), 6)
                row[f'median_{c}'] = round(valid.median(), 6)
                row[f'q25_{c}'] = round(valid.quantile(0.25), 6)
                row[f'q75_{c}'] = round(valid.quantile(0.75), 6)
        rows.append(row)
    return pd.DataFrame(rows).sort_values('bucket')


def compute_top_bottom_trades(trades, signals, n=10):
    j = _join_trades_with_signals(trades, signals)
    j_sorted = j.sort_values('return_pct', ascending=False)
    return j_sorted.head(n).reset_index(drop=True), j_sorted.tail(n).iloc[::-1].reset_index(drop=True)


def compute_sector_winrate(trades, signals):
    j = _join_trades_with_signals(trades, signals)
    if 'sector' not in j.columns or j['sector'].dropna().empty:
        return pd.DataFrame(columns=['sector', 'count', 'win_rate', 'avg_return'])
    rows = []
    for sector, sub in j.groupby('sector'):
        rows.append({
            'sector': sector,
            'count': len(sub),
            'win_rate': round((sub['return_pct'] > 0).mean(), 4),
            'avg_return': round(sub['return_pct'].mean(), 4),
        })
    return pd.DataFrame(rows).sort_values('avg_return', ascending=False)


def compute_exit_reason_stats(trades):
    """按 exit_reason 分组统计 count/win_rate/avg_return/avg_holding_days/avg_add_count。

    NaN return_pct（如未平仓）会从 win_rate / avg_return 计算中剔除，
    但仍计入 count。排序：count 降序。
    """
    cols = ['exit_reason', 'count', 'win_rate', 'avg_return',
            'avg_holding_days', 'avg_add_count']
    if trades.empty or 'exit_reason' not in trades.columns:
        return pd.DataFrame(columns=cols)
    rows = []
    for reason, sub in trades.groupby('exit_reason'):
        ret = sub['return_pct'].dropna() if 'return_pct' in sub.columns else pd.Series(dtype=float)
        hold = sub['holding_days'].dropna() if 'holding_days' in sub.columns else pd.Series(dtype=float)
        addc = sub['add_count'].dropna() if 'add_count' in sub.columns else pd.Series(dtype=float)
        rows.append({
            'exit_reason': reason,
            'count': len(sub),
            'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
            'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
            'avg_holding_days': round(hold.mean(), 1) if len(hold) else float('nan'),
            'avg_add_count': round(addc.mean(), 2) if len(addc) else float('nan'),
        })
    return pd.DataFrame(rows, columns=cols).sort_values('count', ascending=False).reset_index(drop=True)


def compute_add_count_stats(trades):
    """按 add_count 分组（0/1/2/3+），统计胜率/平均收益/已平仓比例。

    排序：add_count 升序（'0' → '1' → '2' → '3+'）。
    """
    cols = ['add_count', 'count', 'win_rate', 'avg_return',
            'avg_holding_days', 'pct_completed']
    if trades.empty or 'add_count' not in trades.columns:
        return pd.DataFrame(columns=cols)
    t = trades.copy()
    t['add_count_bucket'] = t['add_count'].apply(
        lambda x: str(int(x)) if pd.notna(x) and x < 3 else '3+')
    rows = []
    for bucket, sub in t.groupby('add_count_bucket'):
        ret = sub['return_pct'].dropna() if 'return_pct' in sub.columns else pd.Series(dtype=float)
        hold = sub['holding_days'].dropna() if 'holding_days' in sub.columns else pd.Series(dtype=float)
        completed = ((sub['status'] == 'completed').sum()
                     if 'status' in sub.columns else 0)
        rows.append({
            'add_count': bucket,
            'count': len(sub),
            'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
            'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
            'avg_holding_days': round(hold.mean(), 1) if len(hold) else float('nan'),
            'pct_completed': round(completed / len(sub), 4) if len(sub) else float('nan'),
        })
    order = {'0': 0, '1': 1, '2': 2, '3+': 3}
    df = pd.DataFrame(rows, columns=cols)
    df['_ord'] = df['add_count'].map(order)
    return df.sort_values('_ord').drop(columns='_ord').reset_index(drop=True)


_KDJ_BINS = [-np.inf, 40, 80, 100, np.inf]
_KDJ_LABELS = ['[0,40)', '[40,80)', '[80,100)', '[100+)']
_MA60_BINS = [-np.inf, 0, 5, 10, 20, np.inf]
_MA60_LABELS = ['[<0%)', '[0%,5%)', '[5%,10%)', '[10%,20%)', '[20%+)']

_NUMERIC_BUCKETS = {
    'entry_kdj_j':         (_KDJ_BINS,  _KDJ_LABELS),
    'entry_week_kdj_j':    (_KDJ_BINS,  _KDJ_LABELS),
    'entry_ma60_dist_pct': (_MA60_BINS, _MA60_LABELS),
}
_CATEGORICAL_FIELDS = [
    'ma_alignment',
    'macd_zone',
    'entry_week_macd_zone',
    'entry_month_macd_zone',
]


def _bucket_aggregate(field, sub):
    """对一个 (condition_field, bucket) 子集计算 count/win_rate/avg_return/avg_holding_days。"""
    ret = sub['return_pct'].dropna() if 'return_pct' in sub.columns else pd.Series(dtype=float)
    hold = sub['holding_days'].dropna() if 'holding_days' in sub.columns else pd.Series(dtype=float)
    return {
        'count': len(sub),
        'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
        'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
        'avg_holding_days': round(hold.mean(), 1) if len(hold) else float('nan'),
    }


def compute_entry_condition_stats(trades):
    """对 7 个入场快照字段分别 group，输出长表（每条件多行）。"""
    cols = ['condition_field', 'bucket', 'count', 'win_rate',
            'avg_return', 'avg_holding_days']
    if trades.empty:
        return pd.DataFrame(columns=cols)

    rows = []

    # 数值字段
    for field, (bins, labels) in _NUMERIC_BUCKETS.items():
        if field not in trades.columns:
            continue
        sub = trades.dropna(subset=[field]).copy()
        if sub.empty:
            continue
        sub['_bucket'] = pd.cut(sub[field], bins=bins, labels=labels,
                                 right=False, include_lowest=False)
        for bucket in labels:
            chunk = sub[sub['_bucket'] == bucket]
            if chunk.empty:
                continue
            row = {'condition_field': field, 'bucket': bucket}
            row.update(_bucket_aggregate(field, chunk))
            rows.append(row)

    # 类别字段
    for field in _CATEGORICAL_FIELDS:
        if field not in trades.columns:
            continue
        sub = trades.dropna(subset=[field])
        if sub.empty:
            continue
        for bucket, chunk in sub.groupby(field):
            row = {'condition_field': field, 'bucket': str(bucket)}
            row.update(_bucket_aggregate(field, chunk))
            rows.append(row)

    if not rows:
        return pd.DataFrame(columns=cols)

    df = pd.DataFrame(rows, columns=cols)
    return df.sort_values(['condition_field', 'bucket']).reset_index(drop=True)


def compute_yearly_stats(trades):
    """按 entry_date.year 分组：count / win_rate / avg_return / median_return /
    total_pnl_yuan / avg_holding_days。total_pnl_yuan 单位为元。

    跨年可比性：策略不复利（position_limit = initial_cash / max_positions
    在 strategy.__init__ 中只算一次），单仓位金额常数。
    """
    cols = ['year', 'count', 'win_rate', 'avg_return', 'median_return',
            'total_pnl_yuan', 'avg_holding_days']
    if trades.empty or 'entry_date' not in trades.columns:
        return pd.DataFrame(columns=cols)
    t = trades.copy()
    t['entry_date'] = pd.to_datetime(t['entry_date'], errors='coerce')
    t = t.dropna(subset=['entry_date'])
    if t.empty:
        return pd.DataFrame(columns=cols)
    t['year'] = t['entry_date'].dt.year
    rows = []
    for year, sub in t.groupby('year'):
        ret = sub['return_pct'].dropna() if 'return_pct' in sub.columns else pd.Series(dtype=float)
        pnl = sub['gross_pnl'].dropna() if 'gross_pnl' in sub.columns else pd.Series(dtype=float)
        hold = sub['holding_days'].dropna() if 'holding_days' in sub.columns else pd.Series(dtype=float)
        rows.append({
            'year': int(year),
            'count': len(sub),
            'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
            'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
            'median_return': round(ret.median(), 4) if len(ret) else float('nan'),
            'total_pnl_yuan': round(pnl.sum(), 2) if len(pnl) else 0.0,
            'avg_holding_days': round(hold.mean(), 1) if len(hold) else float('nan'),
        })
    return pd.DataFrame(rows, columns=cols).sort_values('year').reset_index(drop=True)


_FIRST_BUY_BINS = [-np.inf, -1, -0.5, 0, 0.5, 1, 1.5, 2, 3, 5, 10, np.inf]
_FIRST_BUY_LABELS = ['[<-1%)', '[-1%,-0.5%)', '[-0.5%,0%)',
                     '[0%,0.5%)', '[0.5%,1%)', '[1%,1.5%)',
                     '[1.5%,2%)', '[2%,3%)', '[3%,5%)',
                     '[5%,10%)', '[10%+)']


def _scan_bucket_aggregate(sub):
    """对一个桶子集计算 count/win_rate/avg_return/median_return/avg_holding_days/avg_add_count/pct_completed。"""
    ret = sub['return_pct'].dropna() if 'return_pct' in sub.columns else pd.Series(dtype=float)
    hold = sub['holding_days'].dropna() if 'holding_days' in sub.columns else pd.Series(dtype=float)
    addc = sub['add_count'].dropna() if 'add_count' in sub.columns else pd.Series(dtype=float)
    completed = ((sub['status'] == 'completed').sum()
                 if 'status' in sub.columns else 0)
    n = len(sub)
    return {
        'count': n,
        'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
        'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
        'median_return': round(ret.median(), 4) if len(ret) else float('nan'),
        'avg_holding_days': round(hold.mean(), 1) if len(hold) else float('nan'),
        'avg_add_count': round(addc.mean(), 2) if len(addc) else float('nan'),
        'pct_completed': round(completed / n, 4) if n else float('nan'),
    }


def compute_first_buy_size_stats(trades):
    """按 entry_ma60_dist_pct 11 桶扫描，评估首仓尺寸阈值（当前 1%）的合理性。

    输入字段 entry_ma60_dist_pct 单位为百分点（例 0.5 表示 0.5%）。
    """
    cols = ['bucket', 'count', 'win_rate', 'avg_return', 'median_return',
            'avg_holding_days', 'avg_add_count', 'pct_completed']
    if trades.empty or 'entry_ma60_dist_pct' not in trades.columns:
        return pd.DataFrame(columns=cols)
    sub = trades.dropna(subset=['entry_ma60_dist_pct']).copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    sub['_bucket'] = pd.cut(sub['entry_ma60_dist_pct'],
                             bins=_FIRST_BUY_BINS, labels=_FIRST_BUY_LABELS,
                             right=False, include_lowest=False)
    rows = []
    for bucket in _FIRST_BUY_LABELS:
        chunk = sub[sub['_bucket'] == bucket]
        if chunk.empty:
            continue
        row = {'bucket': bucket}
        row.update(_scan_bucket_aggregate(chunk))
        rows.append(row)
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols).reset_index(drop=True)


_ADD_BLOCK_BINS = [-np.inf, 0, 0.005, 0.01, 0.015, 0.02, 0.03, 0.05, 0.10, np.inf]
_ADD_BLOCK_LABELS = ['[<0%)', '[0%,0.5%)', '[0.5%,1%)',
                     '[1%,1.5%)', '[1.5%,2%)', '[2%,3%)',
                     '[3%,5%)', '[5%,10%)', '[10%+)']


def compute_add_block_stats(trades):
    """按 max_bullish_candle_pct 9 桶扫描，评估加仓阻断阈值（当前 1%）的合理性。

    输入字段 max_bullish_candle_pct 单位为小数（例 0.0083 表示 0.83%）。
    """
    cols = ['bucket', 'count', 'win_rate', 'avg_return', 'median_return',
            'avg_holding_days', 'avg_add_count', 'pct_completed']
    if trades.empty or 'max_bullish_candle_pct' not in trades.columns:
        return pd.DataFrame(columns=cols)
    sub = trades.dropna(subset=['max_bullish_candle_pct']).copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    sub['_bucket'] = pd.cut(sub['max_bullish_candle_pct'],
                             bins=_ADD_BLOCK_BINS, labels=_ADD_BLOCK_LABELS,
                             right=False, include_lowest=False)
    rows = []
    for bucket in _ADD_BLOCK_LABELS:
        chunk = sub[sub['_bucket'] == bucket]
        if chunk.empty:
            continue
        row = {'bucket': bucket}
        row.update(_scan_bucket_aggregate(chunk))
        rows.append(row)
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols).reset_index(drop=True)


def compute_mfe_mae_by_exit(trades):
    """按 exit_reason 聚合 MFE/MAE 画像。

    - mfe_pct / mae_pct 单位为百分点（与 return_pct 同口径）
    - avg_pullback = avg(mfe_pct - return_pct) ，平均利润回吐
    - avg_underwater = avg(-mae_pct)，平均浮亏深度
    """
    cols = ['exit_reason', 'count', 'avg_return',
            'avg_mfe', 'avg_mae', 'avg_pullback', 'avg_underwater']
    required = {'exit_reason', 'return_pct', 'mfe_pct', 'mae_pct'}
    if trades.empty or not required.issubset(trades.columns):
        return pd.DataFrame(columns=cols)
    sub = trades.dropna(subset=['exit_reason', 'mfe_pct', 'mae_pct']).copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    for exit_reason, chunk in sub.groupby('exit_reason'):
        ret = chunk['return_pct'].dropna()
        mfe = chunk['mfe_pct']
        mae = chunk['mae_pct']
        pullback = (mfe - chunk['return_pct']).dropna()
        rows.append({
            'exit_reason': exit_reason,
            'count': len(chunk),
            'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
            'avg_mfe': round(mfe.mean(), 4) if len(mfe) else float('nan'),
            'avg_mae': round(mae.mean(), 4) if len(mae) else float('nan'),
            'avg_pullback': round(pullback.mean(), 4) if len(pullback) else float('nan'),
            'avg_underwater': round((-mae).mean(), 4) if len(mae) else float('nan'),
        })
    df = pd.DataFrame(rows, columns=cols)
    return df.sort_values('count', ascending=False).reset_index(drop=True)


_MFE_BINS = [-np.inf, 0, 2, 5, 10, 20, np.inf]
_MFE_LABELS = ['[<0%)', '[0%,2%)', '[2%,5%)', '[5%,10%)', '[10%,20%)', '[20%+)']


def compute_mfe_distribution(trades):
    """按 mfe_pct（持仓期最高浮盈，百分点）分 6 桶，看曾浮盈过 X% 的笔最终落地多少。"""
    cols = ['bucket', 'count', 'win_rate', 'avg_return',
            'median_return', 'pct_completed']
    if trades.empty or 'mfe_pct' not in trades.columns:
        return pd.DataFrame(columns=cols)
    sub = trades.dropna(subset=['mfe_pct']).copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    sub['_bucket'] = pd.cut(sub['mfe_pct'], bins=_MFE_BINS, labels=_MFE_LABELS,
                             right=False, include_lowest=False)
    rows = []
    for bucket in _MFE_LABELS:
        chunk = sub[sub['_bucket'] == bucket]
        if chunk.empty:
            continue
        ret = chunk['return_pct'].dropna() if 'return_pct' in chunk.columns else pd.Series(dtype=float)
        completed = ((chunk['status'] == 'completed').sum()
                     if 'status' in chunk.columns else 0)
        n = len(chunk)
        rows.append({
            'bucket': bucket,
            'count': n,
            'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
            'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
            'median_return': round(ret.median(), 4) if len(ret) else float('nan'),
            'pct_completed': round(completed / n, 4) if n else float('nan'),
        })
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols).reset_index(drop=True)


_DEA_LOOKBACK_BINS = [0, 1, 2, 3, 4, 5, 7, 10, 15, 30, 60, np.inf]
_DEA_LOOKBACK_LABELS = ['[0,1)', '[1,2)', '[2,3)', '[3,4)', '[4,5)',
                         '[5,7)', '[7,10)', '[10,15)', '[15,30)',
                         '[30,60)', '[60+)']


def compute_dea_lookback_stats(trades):
    """按 dea_neg_distance_days 11 桶扫描，评估 dea_lookback_days 阈值的合理性。

    - 函数最小返回 1，所以 [0,1) 桶永远为空（防御桶）
    - 现行 dea_lookback_days = 5 下，[1,2)..[4,5) 必有数据，[5,7) 含距离=5 触发
    - 后段桶在阈值放宽并重跑回测后才会出现数据
    """
    cols = ['bucket', 'count', 'win_rate', 'avg_return', 'median_return',
            'avg_holding_days', 'avg_add_count', 'pct_completed']
    if trades.empty or 'dea_neg_distance_days' not in trades.columns:
        return pd.DataFrame(columns=cols)
    sub = trades.dropna(subset=['dea_neg_distance_days']).copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    sub['_bucket'] = pd.cut(sub['dea_neg_distance_days'],
                             bins=_DEA_LOOKBACK_BINS, labels=_DEA_LOOKBACK_LABELS,
                             right=False, include_lowest=True)
    rows = []
    for bucket in _DEA_LOOKBACK_LABELS:
        chunk = sub[sub['_bucket'] == bucket]
        if chunk.empty:
            continue
        row = {'bucket': bucket}
        row.update(_scan_bucket_aggregate(chunk))
        rows.append(row)
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols).reset_index(drop=True)


def compute_monthly_stats(trades):
    """按 entry_date 的年月分组，与 yearly_stats 同口径细化到月。

    没入场的月份不补 0 行（与现 yearly_stats 同款）。
    """
    cols = ['year_month', 'count', 'win_rate', 'avg_return',
            'median_return', 'total_pnl_yuan', 'avg_holding_days']
    if trades.empty or 'entry_date' not in trades.columns:
        return pd.DataFrame(columns=cols)
    sub = trades.dropna(subset=['entry_date']).copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    sub['entry_date'] = pd.to_datetime(sub['entry_date'])
    sub['_year_month'] = sub['entry_date'].dt.to_period('M').astype(str)
    rows = []
    for ym, chunk in sub.groupby('_year_month'):
        ret = chunk['return_pct'].dropna() if 'return_pct' in chunk.columns else pd.Series(dtype=float)
        pnl = chunk['gross_pnl'].dropna() if 'gross_pnl' in chunk.columns else pd.Series(dtype=float)
        hold = chunk['holding_days'].dropna() if 'holding_days' in chunk.columns else pd.Series(dtype=float)
        rows.append({
            'year_month': ym,
            'count': len(chunk),
            'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
            'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
            'median_return': round(ret.median(), 4) if len(ret) else float('nan'),
            'total_pnl_yuan': round(pnl.sum(), 0) if len(pnl) else float('nan'),
            'avg_holding_days': round(hold.mean(), 1) if len(hold) else float('nan'),
        })
    df = pd.DataFrame(rows, columns=cols)
    return df.sort_values('year_month').reset_index(drop=True)


def _compute_bool_flag_stats(trades, flag_col):
    """对单个布尔标志列做 2 桶聚合（True/False，NA dropna 跳过）。"""
    cols = ['flag_value', 'count', 'win_rate', 'avg_return', 'avg_holding_days']
    if trades.empty or flag_col not in trades.columns:
        return pd.DataFrame(columns=cols)
    sub = trades.dropna(subset=[flag_col]).copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    for value in [True, False]:
        chunk = sub[sub[flag_col] == value]
        if chunk.empty:
            continue
        ret = chunk['return_pct'].dropna() if 'return_pct' in chunk.columns else pd.Series(dtype=float)
        hold = chunk['holding_days'].dropna() if 'holding_days' in chunk.columns else pd.Series(dtype=float)
        rows.append({
            'flag_value': str(value),
            'count': len(chunk),
            'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
            'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
            'avg_holding_days': round(hold.mean(), 1) if len(hold) else float('nan'),
        })
    return pd.DataFrame(rows, columns=cols).reset_index(drop=True)


def compute_hs300_dif_stats(trades):
    """按 entry_hs300_dif_above_zero 分桶（HS300 MACD DIF 水上/水下）。"""
    return _compute_bool_flag_stats(trades, 'entry_hs300_dif_above_zero')


def compute_hs300_bull_align_stats(trades):
    """按 entry_hs300_bull_align 分桶（HS300 多头排列：ma25>ma60>ma144>ma180）。"""
    return _compute_bool_flag_stats(trades, 'entry_hs300_bull_align')


def compute_stock_bull_align_stats(trades):
    """按 entry_stock_bull_align 分桶（个股多头排列）。"""
    return _compute_bool_flag_stats(trades, 'entry_stock_bull_align')


def compute_stock_above_ma25_stats(trades):
    """按 entry_stock_above_ma25 分桶（个股 close > ma25）。"""
    return _compute_bool_flag_stats(trades, 'entry_stock_above_ma25')


def compute_sector_bull_align_stats(trades):
    """按 entry_sector_bull_align 分桶（行业指数多头排列）。"""
    return _compute_bool_flag_stats(trades, 'entry_sector_bull_align')


def compute_sector_above_ma25_stats(trades):
    """按 entry_sector_above_ma25 分桶（行业指数 close > ma25）。"""
    return _compute_bool_flag_stats(trades, 'entry_sector_above_ma25')


def compute_sector_dif_stats(trades):
    """按 entry_sector_dif_above_zero 分桶（行业 MACD DIF > 0）。"""
    return _compute_bool_flag_stats(trades, 'entry_sector_dif_above_zero')


def _compute_zone_stats(trades, zone_col):
    """对字符串桶（如 '多头'/'空头'/'震荡'）做聚合。"""
    cols = ['zone', 'count', 'win_rate', 'avg_return', 'avg_holding_days']
    if trades.empty or zone_col not in trades.columns:
        return pd.DataFrame(columns=cols)
    sub = trades.dropna(subset=[zone_col]).copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    for zone, chunk in sub.groupby(zone_col):
        ret = chunk['return_pct'].dropna() if 'return_pct' in chunk.columns else pd.Series(dtype=float)
        hold = chunk['holding_days'].dropna() if 'holding_days' in chunk.columns else pd.Series(dtype=float)
        rows.append({
            'zone': zone,
            'count': len(chunk),
            'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
            'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
            'avg_holding_days': round(hold.mean(), 1) if len(hold) else float('nan'),
        })
    return pd.DataFrame(rows, columns=cols).reset_index(drop=True)


def compute_sector_week_macd_stats(trades):
    """按 entry_sector_week_macd_zone 字符串桶聚合。"""
    return _compute_zone_stats(trades, 'entry_sector_week_macd_zone')


def compute_sector_month_macd_stats(trades):
    """按 entry_sector_month_macd_zone 字符串桶聚合。"""
    return _compute_zone_stats(trades, 'entry_sector_month_macd_zone')


def compute_sector_momentum_60d_stats(trades):
    """按 entry_sector_momentum_60d 五分桶（Q1=最低, Q5=最高）聚合。"""
    cols = ['quintile', 'momentum_lo', 'momentum_hi',
            'count', 'win_rate', 'avg_return', 'avg_holding_days']
    if trades.empty or 'entry_sector_momentum_60d' not in trades.columns:
        return pd.DataFrame(columns=cols)
    sub = trades.dropna(subset=['entry_sector_momentum_60d']).copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    try:
        sub['_q'] = pd.qcut(sub['entry_sector_momentum_60d'],
                           q=5, labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'],
                           duplicates='drop')
    except ValueError:
        return pd.DataFrame(columns=cols)
    rows = []
    for q in ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']:
        chunk = sub[sub['_q'] == q]
        if chunk.empty:
            continue
        ret = chunk['return_pct'].dropna() if 'return_pct' in chunk.columns else pd.Series(dtype=float)
        hold = chunk['holding_days'].dropna() if 'holding_days' in chunk.columns else pd.Series(dtype=float)
        rows.append({
            'quintile': q,
            'momentum_lo': round(chunk['entry_sector_momentum_60d'].min(), 4),
            'momentum_hi': round(chunk['entry_sector_momentum_60d'].max(), 4),
            'count': len(chunk),
            'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
            'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
            'avg_holding_days': round(hold.mean(), 1) if len(hold) else float('nan'),
        })
    return pd.DataFrame(rows, columns=cols).reset_index(drop=True)


_REGIME_COMBO_LABELS = [
    ('大盘水上+个股多头', True, True),
    ('大盘水上+个股非多头', True, False),
    ('大盘水下+个股多头', False, True),
    ('大盘水下+个股非多头', False, False),
]


def compute_regime_combo_stats(trades):
    """大盘 DIF 水上水下 × 个股多头排列 2x2 共振分析。

    缺 entry_hs300_dif_above_zero 或 entry_stock_bull_align 的行被 dropna 跳过。
    输出固定 4 行（按 _REGIME_COMBO_LABELS 顺序），空桶跳过。
    """
    cols = ['combo', 'count', 'win_rate', 'avg_return', 'avg_holding_days']
    required = ['entry_hs300_dif_above_zero', 'entry_stock_bull_align']
    if trades.empty or any(c not in trades.columns for c in required):
        return pd.DataFrame(columns=cols)
    sub = trades.dropna(subset=required).copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    for label, dif_v, bull_v in _REGIME_COMBO_LABELS:
        chunk = sub[(sub['entry_hs300_dif_above_zero'] == dif_v) &
                    (sub['entry_stock_bull_align'] == bull_v)]
        if chunk.empty:
            continue
        ret = chunk['return_pct'].dropna() if 'return_pct' in chunk.columns else pd.Series(dtype=float)
        hold = chunk['holding_days'].dropna() if 'holding_days' in chunk.columns else pd.Series(dtype=float)
        rows.append({
            'combo': label,
            'count': len(chunk),
            'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
            'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
            'avg_holding_days': round(hold.mean(), 1) if len(hold) else float('nan'),
        })
    return pd.DataFrame(rows, columns=cols).reset_index(drop=True)


def compute_factor_alpha(signals, top_n=3, factors=None,
                         horizon='forward_return_20d'):
    """对每个因子计算：Top-N alpha、Bottom-N spread、Spearman IC。

    - top_n_alpha: 当日截面 Top-N 均值 - 全体均值
    - top_bottom_spread: Top-quintile 均值 - Bottom-quintile 均值
    - ic_mean: 每日 Spearman(因子值, 远期收益) 序列的均值
    - ic_ir: ic_mean / ic_std（信息比率）
    """
    s = signals.copy()
    if factors is None:
        factors = [c for c in s.columns if c.startswith('factor_')]

    s = s.dropna(subset=[horizon])
    baseline_avg = s[horizon].mean()

    rows = []
    for factor in factors:
        if factor not in s.columns:
            continue
        sub = s.dropna(subset=[factor, horizon])
        if sub.empty:
            continue

        # Top-N alpha
        top = (sub.sort_values(['date', factor], ascending=[True, False])
                  .groupby('date').head(top_n))
        top_avg = top[horizon].mean() if not top.empty else float('nan')

        # Top-Bottom quintile spread
        def _quintile_spread(grp):
            n = len(grp)
            if n < 5:
                return None
            sorted_grp = grp.sort_values(factor)
            q_size = max(1, n // 5)
            bottom_ret = sorted_grp.head(q_size)[horizon].mean()
            top_ret = sorted_grp.tail(q_size)[horizon].mean()
            return top_ret - bottom_ret

        spreads = sub.groupby('date').apply(_quintile_spread).dropna()
        top_bottom_spread = spreads.mean() if not spreads.empty else float('nan')

        # Spearman IC per day
        def _spearman_ic(grp):
            if len(grp) < 4:
                return None
            r = _spearman_r(grp[factor], grp[horizon])
            return r if not np.isnan(r) else None

        ics = sub.groupby('date').apply(_spearman_ic).dropna()
        ic_mean = ics.mean() if not ics.empty else float('nan')
        ic_std = ics.std() if len(ics) > 1 else float('nan')
        ic_ir = ic_mean / ic_std if ic_std and ic_std != 0 else float('nan')

        alpha = round(top_avg - baseline_avg, 6)
        rows.append({
            'factor': factor,
            'top_n_avg': round(top_avg, 6),
            'baseline_avg': round(baseline_avg, 6),
            'alpha': alpha,
            'top_bottom_spread': round(top_bottom_spread, 6) if not np.isnan(top_bottom_spread) else None,
            'ic_mean': round(ic_mean, 6) if not np.isnan(ic_mean) else None,
            'ic_ir': round(ic_ir, 4) if not np.isnan(ic_ir) else None,
            'sample_size': len(top),
        })
    if not rows:
        return pd.DataFrame(columns=['factor', 'top_n_avg', 'baseline_avg',
                                      'alpha', 'top_bottom_spread',
                                      'ic_mean', 'ic_ir', 'sample_size'])
    return pd.DataFrame(rows).sort_values('alpha', ascending=False)


def run(project_root, cfg):
    """根据 cfg 执行全部归因分析并写出报告。供 backtest.py 直接调用。"""
    project_root = Path(project_root)
    sig_path = project_root / cfg['signals_log_path']
    trade_path = project_root / 'results' / 'trade_summary.csv'
    out_dir = project_root / cfg['attribution_report_dir']

    if not sig_path.exists():
        raise FileNotFoundError(
            f"signals_log not found at {sig_path}. Run backtest.py first.")
    if not trade_path.exists():
        raise FileNotFoundError(
            f"trade_summary not found at {trade_path}. Run backtest.py first.")

    out_dir.mkdir(parents=True, exist_ok=True)

    signals = pd.read_csv(sig_path, parse_dates=['date'])
    trades = pd.read_csv(trade_path, parse_dates=['entry_date'])

    # 7 个 regime flag 列从 csv 读回是 "True"/"False"/空 字符串，转回 Optional[bool]
    for col in ['entry_hs300_dif_above_zero', 'entry_hs300_bull_align',
                'entry_stock_bull_align', 'entry_stock_above_ma25',
                'entry_sector_bull_align', 'entry_sector_above_ma25',
                'entry_sector_dif_above_zero']:
        if col in trades.columns:
            trades[col] = trades[col].map(
                {'True': True, 'False': False, True: True, False: False}
            )

    profile = compute_trade_profile(trades, signals)
    profile.to_csv(out_dir / 'trade_profile.csv', index=False)

    top, bottom = compute_top_bottom_trades(trades, signals, n=10)
    top.to_csv(out_dir / 'top_trades.csv', index=False)
    bottom.to_csv(out_dir / 'bottom_trades.csv', index=False)

    sector = compute_sector_winrate(trades, signals)
    sector.to_csv(out_dir / 'sector_winrate.csv', index=False)

    exit_reason = compute_exit_reason_stats(trades)
    exit_reason.to_csv(out_dir / 'exit_reason_stats.csv', index=False)

    add_count = compute_add_count_stats(trades)
    add_count.to_csv(out_dir / 'add_count_stats.csv', index=False)

    entry_cond = compute_entry_condition_stats(trades)
    entry_cond.to_csv(out_dir / 'entry_condition_stats.csv', index=False)

    yearly = compute_yearly_stats(trades)
    yearly.to_csv(out_dir / 'yearly_stats.csv', index=False)

    first_buy = compute_first_buy_size_stats(trades)
    first_buy.to_csv(out_dir / 'first_buy_size_stats.csv', index=False)

    add_block = compute_add_block_stats(trades)
    add_block.to_csv(out_dir / 'add_block_stats.csv', index=False)

    mfe_mae = compute_mfe_mae_by_exit(trades)
    mfe_mae.to_csv(out_dir / 'mfe_mae_by_exit.csv', index=False)

    mfe_dist = compute_mfe_distribution(trades)
    mfe_dist.to_csv(out_dir / 'mfe_distribution.csv', index=False)

    dea_lookback = compute_dea_lookback_stats(trades)
    dea_lookback.to_csv(out_dir / 'dea_lookback_stats.csv', index=False)

    monthly = compute_monthly_stats(trades)
    monthly.to_csv(out_dir / 'monthly_stats.csv', index=False)

    hs300_dif = compute_hs300_dif_stats(trades)
    hs300_dif.to_csv(out_dir / 'hs300_dif_stats.csv', index=False)

    hs300_bull = compute_hs300_bull_align_stats(trades)
    hs300_bull.to_csv(out_dir / 'hs300_bull_align_stats.csv', index=False)

    stock_bull = compute_stock_bull_align_stats(trades)
    stock_bull.to_csv(out_dir / 'stock_bull_align_stats.csv', index=False)

    stock_above = compute_stock_above_ma25_stats(trades)
    stock_above.to_csv(out_dir / 'stock_above_ma25_stats.csv', index=False)

    regime_combo = compute_regime_combo_stats(trades)
    regime_combo.to_csv(out_dir / 'regime_combo_stats.csv', index=False)

    compute_sector_bull_align_stats(trades).to_csv(out_dir / 'sector_bull_align_stats.csv', index=False)
    compute_sector_above_ma25_stats(trades).to_csv(out_dir / 'sector_above_ma25_stats.csv', index=False)
    compute_sector_dif_stats(trades).to_csv(out_dir / 'sector_dif_stats.csv', index=False)
    compute_sector_week_macd_stats(trades).to_csv(out_dir / 'sector_week_macd_stats.csv', index=False)
    compute_sector_month_macd_stats(trades).to_csv(out_dir / 'sector_month_macd_stats.csv', index=False)
    compute_sector_momentum_60d_stats(trades).to_csv(out_dir / 'sector_momentum_60d_stats.csv', index=False)

    factor_alpha = compute_factor_alpha(signals)
    factor_alpha.to_csv(out_dir / 'factor_alpha.csv', index=False)

    print(f"attribution reports written to {out_dir}")


def main():
    import json
    project_root = Path(__file__).resolve().parent.parent
    cfg = json.loads((project_root / 'config.json').read_text())
    run(project_root, cfg)


if __name__ == '__main__':
    main()
