import json
import numpy as np
import pandas as pd
from pathlib import Path


def load_config(config_path=None):
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent / 'config.json'
    with open(config_path, 'r') as f:
        return json.load(f)


# ── 原子指标计算函数 ──────────────────────────────────────────────────────────

def add_ma(df: pd.DataFrame) -> pd.DataFrame:
    """添加 MA25/60/144/180 + circ_mv 换算。"""
    df = df.copy()
    df['ma25'] = df['close'].rolling(window=25, min_periods=25).mean().round(2)
    df['ma60'] = df['close'].rolling(window=60, min_periods=60).mean().round(2)
    df['ma144'] = df['close'].rolling(window=144, min_periods=144).mean().round(2)
    df['ma180'] = df['close'].rolling(window=180, min_periods=180).mean().round(2)
    if 'circ_mv' in df.columns:
        df['circ_mv'] = (df['circ_mv'] / 10000).round(2)
    return df


def add_macd(df: pd.DataFrame) -> pd.DataFrame:
    """添加 DIF/DEA/MACD。"""
    df = df.copy()
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['dif'] = (ema12 - ema26).round(2)
    df['dea'] = df['dif'].ewm(span=9, adjust=False).mean().round(2)
    df['macd'] = (2 * (df['dif'] - df['dea'])).round(2)
    return df


def add_kdj(df: pd.DataFrame) -> pd.DataFrame:
    """添加 KDJ_J。"""
    df = df.copy()
    low9 = df['low'].rolling(window=9, min_periods=9).min()
    high9 = df['high'].rolling(window=9, min_periods=9).max()
    denom = (high9 - low9).where(high9 != low9, np.nan)
    rsv = ((df['close'] - low9) / denom * 100).clip(0, 100)
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    df['kdj_j'] = (3 * k - 2 * d).round(2)
    return df


def add_factor_momentum_60d(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out['factor_momentum_60d'] = out['close'].pct_change(60).round(6)
    return out


def add_factor_ma60_dist(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out['factor_ma60_dist'] = ((out['close'] - out['ma60']) / out['ma60']).round(6)
    return out


def add_factor_macd_strength(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out['factor_macd_strength'] = out['dea'].round(6)
    return out


# ── 多周期指标内部工具函数 ────────────────────────────────────────────────────

def _kdj_j(ohlc: pd.DataFrame) -> pd.Series:
    low9 = ohlc['low'].rolling(9, min_periods=9).min()
    high9 = ohlc['high'].rolling(9, min_periods=9).max()
    denom = (high9 - low9).where(high9 != low9, np.nan)
    rsv = ((ohlc['close'] - low9) / denom * 100).clip(0, 100)
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    return (3 * k - 2 * d).round(2)


def _macd_zone(ohlc: pd.DataFrame) -> pd.Series:
    ema12 = ohlc['close'].ewm(span=12, adjust=False).mean()
    ema26 = ohlc['close'].ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    macd = 2 * (dif - dea)

    def _zone(row):
        m, di, de = row['macd'], row['dif'], row['dea']
        if pd.isna(m) or m <= 0:
            return '区间0'
        if m > di and m > de:
            return '区间1'
        if di > m and de > m:
            return '区间3'
        return '区间2'

    return pd.DataFrame({'macd': macd, 'dif': dif, 'dea': dea}).apply(_zone, axis=1)


def add_week_macd_zone(df: pd.DataFrame, weekly_csv_path) -> pd.DataFrame:
    """从周线 CSV 计算 week_kdj_j + week_macd_zone，merge_asof 到日线 df。文件不存在则填 None。"""
    df = df.copy()
    weekly_csv_path = Path(weekly_csv_path)
    daily_dates = df[['trade_date']].sort_values('trade_date')
    if weekly_csv_path.exists():
        wdf = pd.read_csv(weekly_csv_path, parse_dates=['trade_date']).sort_values('trade_date')
        wdf['week_kdj_j'] = _kdj_j(wdf)
        wdf['week_macd_zone'] = _macd_zone(wdf)
        wdf = wdf[['trade_date', 'week_kdj_j', 'week_macd_zone']]
        wdf_aligned = pd.merge_asof(daily_dates, wdf, on='trade_date', direction='backward')
        df = df.merge(wdf_aligned, on='trade_date', how='left')
    else:
        df['week_kdj_j'] = None
        df['week_macd_zone'] = None
    return df


def add_month_macd_zone(df: pd.DataFrame, monthly_csv_path) -> pd.DataFrame:
    """从月线 CSV 计算 month_macd_zone，merge_asof 到日线 df。文件不存在则填 None。"""
    df = df.copy()
    monthly_csv_path = Path(monthly_csv_path)
    daily_dates = df[['trade_date']].sort_values('trade_date')
    if monthly_csv_path.exists():
        mdf = pd.read_csv(monthly_csv_path, parse_dates=['trade_date']).sort_values('trade_date')
        mdf['month_macd_zone'] = _macd_zone(mdf)
        mdf = mdf[['trade_date', 'month_macd_zone']]
        mdf_aligned = pd.merge_asof(daily_dates, mdf, on='trade_date', direction='backward')
        df = df.merge(mdf_aligned, on='trade_date', how='left')
    else:
        df['month_macd_zone'] = None
    return df


# ── 旧接口（向后兼容）────────────────────────────────────────────────────────

def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """原 compute_indicators(df) 的全量计算，保留向后兼容。"""
    df = add_ma(df)
    df = add_macd(df)
    df = add_kdj(df)
    return df


def compute_weekly_monthly_indicators(ts_code, df_daily, data_dir):
    """读取周线/月线 CSV，计算 KDJ_J 和 MACD 区间，merge 回日线 df（ffill 填充）。"""
    data_dir = Path(data_dir)
    df = df_daily.copy()
    daily_dates = df[['trade_date']].sort_values('trade_date')

    weekly_path = data_dir / 'weekly' / f"{ts_code}.csv"
    if weekly_path.exists():
        wdf = pd.read_csv(weekly_path, parse_dates=['trade_date']).sort_values('trade_date')
        wdf['week_kdj_j'] = _kdj_j(wdf)
        wdf['week_macd_zone'] = _macd_zone(wdf)
        wdf = wdf[['trade_date', 'week_kdj_j', 'week_macd_zone']]
        wdf_aligned = pd.merge_asof(daily_dates, wdf, on='trade_date', direction='backward')
        df = df.merge(wdf_aligned, on='trade_date', how='left')
    else:
        df['week_kdj_j'] = None
        df['week_macd_zone'] = None

    monthly_path = data_dir / 'monthly' / f"{ts_code}.csv"
    if monthly_path.exists():
        mdf = pd.read_csv(monthly_path, parse_dates=['trade_date']).sort_values('trade_date')
        mdf['month_macd_zone'] = _macd_zone(mdf)
        mdf = mdf[['trade_date', 'month_macd_zone']]
        mdf_aligned = pd.merge_asof(daily_dates, mdf, on='trade_date', direction='backward')
        df = df.merge(mdf_aligned, on='trade_date', how='left')
    else:
        df['month_macd_zone'] = None

    return df


def add_single_stock_factors(df: pd.DataFrame) -> pd.DataFrame:
    """添加单股票内可计算的打分因子。"""
    out = df.copy()
    out['factor_momentum_60d'] = out['close'].pct_change(60).round(6)
    out['factor_ma60_dist'] = ((out['close'] - out['ma60']) / out['ma60']).round(6)
    out['factor_macd_strength'] = out['dea'].round(6)
    return out


def merge_sector_momentum(daily_df: pd.DataFrame,
                          sector_index_df: pd.DataFrame) -> pd.DataFrame:
    """合并所属行业指数过去 60 日动量。"""
    out = daily_df.copy()
    if sector_index_df is None or sector_index_df.empty:
        out['factor_sector_momentum_60d'] = pd.NA
        return out
    s = sector_index_df.sort_values('trade_date').copy()
    s['factor_sector_momentum_60d'] = s['close'].pct_change(60).round(6)
    s = s[['trade_date', 'factor_sector_momentum_60d']]
    return out.merge(s, on='trade_date', how='left')


def merge_fundamentals(daily_df: pd.DataFrame,
                       daily_basic_df: pd.DataFrame,
                       fina_df: pd.DataFrame) -> pd.DataFrame:
    """按 ann_date 对齐合并财务数据，按 trade_date 对齐合并日频估值数据。

    daily_df: 至少含 trade_date 列，已按 trade_date 升序
    daily_basic_df: pe_ttm/pb/total_mv 等日频估值
    fina_df: 季度财务指标，必须含 ann_date 列
    """
    out = daily_df.copy()
    if not daily_basic_df.empty:
        db = daily_basic_df.sort_values('trade_date')
        out = out.merge(db, on='trade_date', how='left')
    else:
        for col in ['pe_ttm', 'pb', 'total_mv']:
            out[col] = pd.NA

    if fina_df is not None and not fina_df.empty:
        f = fina_df.sort_values('ann_date').rename(columns={'ann_date': 'trade_date'})
        f = f[['trade_date', 'roe', 'netprofit_yoy']]
        out = pd.merge_asof(
            out.sort_values('trade_date'),
            f,
            on='trade_date',
            direction='backward',
        )
    else:
        out['roe'] = pd.NA
        out['netprofit_yoy'] = pd.NA

    return out


def merge_daily_basic_fina(daily_df: pd.DataFrame, code: str,
                            daily_basic_dir, fina_dir) -> pd.DataFrame:
    """路径型包装器，读取 CSV 后调用 merge_fundamentals。"""
    db_path = Path(daily_basic_dir) / f"{code}.csv" if daily_basic_dir else None
    fi_path = Path(fina_dir) / f"{code}.csv" if fina_dir else None

    db = (pd.read_csv(db_path, parse_dates=['trade_date'])
          if db_path and db_path.exists() else pd.DataFrame())
    fi = (pd.read_csv(fi_path, parse_dates=['ann_date', 'end_date'])
          if fi_path and fi_path.exists() else pd.DataFrame())
    return merge_fundamentals(daily_df, db, fi)


# ── 新接口：按 groups 选择性计算 ──────────────────────────────────────────────

def compute_indicators(code, src_dirs, dst_dir, groups,
                       sector_map=None, sw_dir=None,
                       daily_basic_dir=None, fina_dir=None):
    """按 groups 列表选择性计算指标，写入 dst_dir/{code}.csv。

    src_dirs: dict 必须含 'daily'，可选 'weekly'/'monthly'。
    groups: 支持 'ma', 'macd', 'kdj', 'week_macd', 'month_macd',
            'fundamentals', 'sector_momentum',
            'factor_momentum_60d', 'factor_ma60_dist', 'factor_macd_strength'
    """
    src_daily = Path(src_dirs['daily'])
    daily_path = src_daily / f"{code}.csv"
    if not daily_path.exists():
        raise FileNotFoundError(f"daily 数据缺失：{daily_path}")
    df = pd.read_csv(daily_path, parse_dates=['trade_date']).sort_values('trade_date')

    if 'ma' in groups:
        df = add_ma(df)
    if 'macd' in groups:
        df = add_macd(df)
    if 'kdj' in groups:
        df = add_kdj(df)
    if 'week_macd' in groups:
        weekly_path = Path(src_dirs.get('weekly', '')) / f"{code}.csv"
        df = add_week_macd_zone(df, weekly_path)
    if 'month_macd' in groups:
        monthly_path = Path(src_dirs.get('monthly', '')) / f"{code}.csv"
        df = add_month_macd_zone(df, monthly_path)
    if 'fundamentals' in groups:
        df = merge_daily_basic_fina(df, code, daily_basic_dir, fina_dir)
    if 'sector_momentum' in groups:
        sw_code = (sector_map or {}).get(code) if sector_map else None
        if sw_code and sw_dir is not None:
            sw_path = Path(sw_dir) / f"{sw_code}.csv"
            if sw_path.exists():
                sw_df = pd.read_csv(sw_path, parse_dates=['trade_date'])
                df = merge_sector_momentum(df, sw_df)
            else:
                df['factor_sector_momentum_60d'] = pd.NA
        else:
            df['factor_sector_momentum_60d'] = pd.NA
    if 'factor_momentum_60d' in groups:
        df = add_factor_momentum_60d(df)
    if 'factor_ma60_dist' in groups:
        df = add_factor_ma60_dist(df)
    if 'factor_macd_strength' in groups:
        df = add_factor_macd_strength(df)

    Path(dst_dir).mkdir(parents=True, exist_ok=True)
    df.to_csv(Path(dst_dir) / f"{code}.csv", index=False)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['stock', 'sector'], default='stock')
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2] / 'my_strategy'
    cfg = json.loads((project_root / 'config.json').read_text(encoding='utf-8'))
    profile = cfg['indicator_profiles'][args.mode]
    data_dir = project_root / cfg.get('data_dir', 'data/').rstrip('/')

    if args.mode == 'stock':
        codes = pd.read_csv(project_root / cfg['stock_list_path'])['ts_code'].tolist()
        src_dirs = {'daily': data_dir / 'daily',
                    'weekly': data_dir / 'weekly',
                    'monthly': data_dir / 'monthly'}
        dst_dir = data_dir / 'indicators'
        sector_csv = project_root / cfg['data_paths']['stock_sector_csv']
        sec_df = pd.read_csv(sector_csv)
        sector_map = (dict(zip(sec_df['ts_code'], sec_df['sw_index_code']))
                      if 'sw_index_code' in sec_df.columns else {})
        sw_dir = data_dir / 'sw_index'
        daily_basic_dir = data_dir / 'daily_basic'
        fina_dir = data_dir / 'fina'
    else:  # sector
        codes = cfg['sw_index_codes']
        src_dirs = {'daily': data_dir / 'sw_index',
                    'weekly': data_dir / 'sw_weekly',
                    'monthly': data_dir / 'sw_monthly'}
        dst_dir = data_dir / 'sw_indicators'
        sector_map = None
        sw_dir = None
        daily_basic_dir = None
        fina_dir = None

    for i, code in enumerate(codes):
        try:
            compute_indicators(code, src_dirs, dst_dir, profile,
                               sector_map=sector_map, sw_dir=sw_dir,
                               daily_basic_dir=daily_basic_dir, fina_dir=fina_dir)
            if (i + 1) % 100 == 0:
                print(f"[{i+1}/{len(codes)}] indicators")
        except FileNotFoundError as e:
            print(f"  跳过 {code}: {e}")


if __name__ == '__main__':
    main()
