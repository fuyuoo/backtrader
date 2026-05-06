import json
import numpy as np
import pandas as pd
from pathlib import Path


def load_config(config_path='config.json'):
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

    weekly_path = data_dir / f"{ts_code}_weekly.csv"
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

    monthly_path = data_dir / f"{ts_code}_monthly.csv"
    if monthly_path.exists():
        mdf = pd.read_csv(monthly_path, parse_dates=['trade_date']).sort_values('trade_date')
        mdf['month_macd_zone'] = _macd_zone(mdf)
        mdf = mdf[['trade_date', 'month_macd_zone']]
        mdf_aligned = pd.merge_asof(daily_dates, mdf, on='trade_date', direction='backward')
        df = df.merge(mdf_aligned, on='trade_date', how='left')
    else:
        df['month_macd_zone'] = None

    return df


def main():
    cfg = load_config()
    data_dir = Path(cfg['data_dir'])
    stocks = pd.read_csv(cfg['stock_list_path'])['ts_code'].tolist()

    for i, ts_code in enumerate(stocks):
        src = data_dir / f"{ts_code}.csv"
        dst = data_dir / f"{ts_code}_indicators.csv"
        if not src.exists():
            print(f"[{i+1}/{len(stocks)}] {ts_code} SKIP (no raw data)")
            continue
        df = pd.read_csv(src, parse_dates=['trade_date'])
        df = df.sort_values('trade_date').reset_index(drop=True)
        result = compute_indicators(df)
        result = compute_weekly_monthly_indicators(ts_code, result, data_dir)
        result.to_csv(dst, index=False)
        print(f"[{i+1}/{len(stocks)}] {ts_code} OK")


if __name__ == '__main__':
    main()
