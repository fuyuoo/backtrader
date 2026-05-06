import json
import numpy as np
import pandas as pd
from pathlib import Path


def load_config(config_path=None):
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent / 'config.json'
    with open(config_path, 'r') as f:
        return json.load(f)


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['ma25'] = df['close'].rolling(window=25, min_periods=25).mean().round(2)
    df['ma60'] = df['close'].rolling(window=60, min_periods=60).mean().round(2)
    df['ma144'] = df['close'].rolling(window=144, min_periods=144).mean().round(2)
    df['ma180'] = df['close'].rolling(window=180, min_periods=180).mean().round(2)

    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['dif'] = (ema12 - ema26).round(2)
    df['dea'] = df['dif'].ewm(span=9, adjust=False).mean().round(2)
    df['macd'] = (2 * (df['dif'] - df['dea'])).round(2)

    low9 = df['low'].rolling(window=9, min_periods=9).min()
    high9 = df['high'].rolling(window=9, min_periods=9).max()
    # 9 日内 high==low（停牌或一字板）→ 分母 NaN 自然产生 NaN，避免假信号
    denom = (high9 - low9).where(high9 != low9, np.nan)
    rsv = ((df['close'] - low9) / denom * 100).clip(0, 100)
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    df['kdj_j'] = (3 * k - 2 * d).round(2)

    if 'circ_mv' in df.columns:
        df['circ_mv'] = (df['circ_mv'] / 10000).round(2)

    return df


def compute_weekly_monthly_indicators(ts_code, df_daily, data_dir):
    """读取周线/月线 CSV，计算 KDJ_J 和 MACD 区间，merge 回日线 df（ffill 填充）。"""
    data_dir = Path(data_dir)
    df = df_daily.copy()

    def _kdj_j(ohlc):
        low9 = ohlc['low'].rolling(9, min_periods=9).min()
        high9 = ohlc['high'].rolling(9, min_periods=9).max()
        denom = (high9 - low9).where(high9 != low9, np.nan)
        rsv = ((ohlc['close'] - low9) / denom * 100).clip(0, 100)
        k = rsv.ewm(com=2, adjust=False).mean()
        d = k.ewm(com=2, adjust=False).mean()
        return (3 * k - 2 * d).round(2)

    def _macd_zone(ohlc):
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


def main():
    cfg = load_config()
    project_root = Path(__file__).resolve().parent.parent
    data_dir = project_root / cfg['data_dir']
    stocks_df = pd.read_csv(project_root / cfg['stock_list_path'])
    stocks = stocks_df['ts_code'].tolist()

    paths = cfg.get('data_paths', {})
    db_dir = data_dir / Path(paths.get('daily_basic_dir', 'daily_basic')).name
    fi_dir = data_dir / Path(paths.get('fina_indicator_dir', 'fina')).name
    sw_dir = data_dir / Path(paths.get('sw_index_dir', 'sw_index')).name
    sector_csv = project_root / paths.get('stock_sector_csv', 'data/stock_sector.csv')

    sector_map = {}
    if sector_csv.exists():
        sec_df = pd.read_csv(sector_csv)
        if 'sw_index_code' in sec_df.columns and 'ts_code' in sec_df.columns:
            sector_map = dict(zip(sec_df['ts_code'], sec_df['sw_index_code']))

    indicators_dir = data_dir / 'indicators'
    indicators_dir.mkdir(parents=True, exist_ok=True)
    for i, ts_code in enumerate(stocks):
        src = data_dir / 'daily' / f"{ts_code}.csv"
        dst = indicators_dir / f"{ts_code}.csv"
        if not src.exists():
            print(f"[{i+1}/{len(stocks)}] {ts_code} SKIP (no raw data)")
            continue
        df = pd.read_csv(src, parse_dates=['trade_date'])
        df = df.sort_values('trade_date').reset_index(drop=True)
        df = compute_indicators(df)
        df = compute_weekly_monthly_indicators(ts_code, df, data_dir)

        db_path = db_dir / f"{ts_code}.csv"
        db = pd.read_csv(db_path, parse_dates=['trade_date']) if db_path.exists() else pd.DataFrame()
        fi_path = fi_dir / f"{ts_code}.csv"
        if fi_path.exists():
            fi = pd.read_csv(fi_path, parse_dates=['ann_date', 'end_date'])
        else:
            fi = pd.DataFrame()
        df = merge_fundamentals(df, db, fi)

        df = add_single_stock_factors(df)

        sw_code = sector_map.get(ts_code)
        if sw_code:
            sw_path = sw_dir / f"{sw_code}.csv"
            if sw_path.exists():
                sw_df = pd.read_csv(sw_path, parse_dates=['trade_date'])
                df = merge_sector_momentum(df, sw_df)
            else:
                df['factor_sector_momentum_60d'] = pd.NA
        else:
            df['factor_sector_momentum_60d'] = pd.NA

        df.to_csv(dst, index=False)
        if (i + 1) % 100 == 0:
            print(f"[{i+1}/{len(stocks)}] {ts_code} OK")


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


if __name__ == '__main__':
    main()
