import json
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
    rsv = ((df['close'] - low9) / (high9 - low9).replace(0, 1) * 100).clip(0, 100)
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    df['kdj_j'] = (3 * k - 2 * d).round(2)

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
        result.to_csv(dst, index=False)
        print(f"[{i+1}/{len(stocks)}] {ts_code} OK")


if __name__ == '__main__':
    main()
