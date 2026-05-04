import json
import time
import logging
import pandas as pd
import tushare as ts
from pathlib import Path

logging.basicConfig(filename='download_errors.log', level=logging.ERROR,
                    format='%(asctime)s %(message)s')


def load_config(config_path='config.json'):
    with open(config_path, 'r') as f:
        return json.load(f)


def get_last_date(csv_path):
    """读取本地 CSV 最后一条交易日期，用于增量下载。"""
    df = pd.read_csv(csv_path, usecols=['trade_date'])
    return df['trade_date'].max()


def download_stock(pro, ts_code, start_date, end_date, data_dir):
    """下载单只股票数据，支持增量更新。"""
    csv_path = Path(data_dir) / f"{ts_code}.csv"

    if csv_path.exists():
        last_date = get_last_date(csv_path)
        next_date = pd.Timestamp(last_date) + pd.Timedelta(days=1)
        actual_start = next_date.strftime('%Y%m%d')
        if actual_start >= end_date:
            return
    else:
        actual_start = start_date

    df = ts.pro_bar(
        ts_code=ts_code,
        adj='qfq',
        start_date=actual_start,
        end_date=end_date,
        fields='trade_date,open,high,low,close,vol'
    )
    if df is None or df.empty:
        return

    df = df.rename(columns={'vol': 'volume'})
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.sort_values('trade_date').reset_index(drop=True)

    if csv_path.exists():
        existing = pd.read_csv(csv_path, parse_dates=['trade_date'])
        df = pd.concat([existing, df], ignore_index=True)
        df = df.drop_duplicates(subset='trade_date').sort_values('trade_date')

    df.to_csv(csv_path, index=False)


def main():
    cfg = load_config()
    ts.set_token(cfg['tushare_token'])
    pro = ts.pro_api()

    stocks = pd.read_csv(cfg['stock_list_path'])['ts_code'].tolist()
    data_dir = cfg['data_dir']
    Path(data_dir).mkdir(exist_ok=True)

    for i, ts_code in enumerate(stocks):
        try:
            download_stock(pro, ts_code, cfg['start_date'], cfg['end_date'], data_dir)
            print(f"[{i+1}/{len(stocks)}] {ts_code} OK")
        except Exception as e:
            logging.error(f"{ts_code}: {e}")
            print(f"[{i+1}/{len(stocks)}] {ts_code} FAILED: {e}")
        time.sleep(0.3)


if __name__ == '__main__':
    main()
