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


def _year_chunks(start_date: str, end_date: str):
    """按年切分日期区间，避免单次拉取数据量过大。"""
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    cur = start
    while cur <= end:
        year_end = min(pd.Timestamp(f"{cur.year}1231"), end)
        yield cur.strftime('%Y%m%d'), year_end.strftime('%Y%m%d')
        cur = pd.Timestamp(f"{cur.year + 1}0101")


def _apply_qfq(df, pro, ts_code, start_date):
    """对已拼接的原始日线 df 应用前复权，以今日 adj_factor 为基准。"""
    today = pd.Timestamp.today().strftime('%Y%m%d')
    fcts = pro.adj_factor(ts_code=ts_code, start_date=start_date, end_date=today)[['trade_date', 'adj_factor']]
    fcts['trade_date'] = pd.to_datetime(fcts['trade_date'])
    fcts = fcts.sort_values('trade_date').reset_index(drop=True)
    latest_factor = float(fcts['adj_factor'].iloc[-1])
    df = df.merge(fcts, on='trade_date', how='left')
    df['adj_factor'] = df['adj_factor'].ffill().bfill()
    for col in ['open', 'high', 'low', 'close']:
        df[col] = (df[col] * df['adj_factor'] / latest_factor).round(2)
    return df.drop(columns='adj_factor')


def download_stock(ts_code, start_date, end_date, data_dir):
    """下载单只股票前复权日线数据，全量重新下载以保证复权基准一致。"""
    csv_path = Path(data_dir) / f"{ts_code}.csv"
    pro = ts.pro_api()

    chunks = []
    for seg_start, seg_end in _year_chunks(start_date, end_date):
        seg = ts.pro_bar(
            ts_code=ts_code,
            adj=None,
            start_date=seg_start,
            end_date=seg_end,
        )
        if seg is not None and not seg.empty:
            chunks.append(seg)
        time.sleep(0.2)

    if not chunks:
        return

    df = pd.concat(chunks, ignore_index=True)
    df = df.rename(columns={'vol': 'volume'})
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.drop_duplicates(subset='trade_date').sort_values('trade_date').reset_index(drop=True)

    df = _apply_qfq(df, pro, ts_code, start_date)
    basic_chunks = []
    for seg_start, seg_end in _year_chunks(start_date, end_date):
        seg = pro.daily_basic(
            ts_code=ts_code,
            start_date=seg_start,
            end_date=seg_end,
            fields='trade_date,circ_mv',
        )
        if seg is not None and not seg.empty:
            basic_chunks.append(seg)
        time.sleep(0.2)
    if basic_chunks:
        basic_df = pd.concat(basic_chunks, ignore_index=True)
        basic_df['trade_date'] = pd.to_datetime(basic_df['trade_date'])
        basic_df = basic_df.drop_duplicates(subset='trade_date')
        df = df.merge(basic_df, on='trade_date', how='left')
    else:
        df['circ_mv'] = float('nan')
    df = df[['trade_date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg', 'circ_mv']]
    df.to_csv(csv_path, index=False)


def download_weekly(ts_code, start_date, end_date, data_dir):
    """下载周线 OHLC，存为 {ts_code}_weekly.csv。"""
    csv_path = Path(data_dir) / f"{ts_code}_weekly.csv"
    chunks = []
    for seg_start, seg_end in _year_chunks(start_date, end_date):
        seg = ts.pro_bar(ts_code=ts_code, adj=None, freq='W',
                         start_date=seg_start, end_date=seg_end)
        if seg is not None and not seg.empty:
            chunks.append(seg)
        time.sleep(0.2)
    if not chunks:
        return
    df = pd.concat(chunks, ignore_index=True)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.drop_duplicates(subset='trade_date').sort_values('trade_date').reset_index(drop=True)
    df[['trade_date', 'open', 'high', 'low', 'close']].to_csv(csv_path, index=False)


def download_monthly(ts_code, start_date, end_date, data_dir):
    """下载月线 OHLC，存为 {ts_code}_monthly.csv。"""
    csv_path = Path(data_dir) / f"{ts_code}_monthly.csv"
    chunks = []
    for seg_start, seg_end in _year_chunks(start_date, end_date):
        seg = ts.pro_bar(ts_code=ts_code, adj=None, freq='M',
                         start_date=seg_start, end_date=seg_end)
        if seg is not None and not seg.empty:
            chunks.append(seg)
        time.sleep(0.2)
    if not chunks:
        return
    df = pd.concat(chunks, ignore_index=True)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.drop_duplicates(subset='trade_date').sort_values('trade_date').reset_index(drop=True)
    df[['trade_date', 'open', 'high', 'low', 'close']].to_csv(csv_path, index=False)


def download_index(ts_code, start_date, end_date, data_dir):
    """下载指数日线数据（无复权，直接存为 {ts_code}.csv）。"""
    csv_path = Path(data_dir) / f"{ts_code}.csv"
    pro = ts.pro_api()
    chunks = []
    for seg_start, seg_end in _year_chunks(start_date, end_date):
        seg = pro.index_daily(ts_code=ts_code, start_date=seg_start, end_date=seg_end)
        if seg is not None and not seg.empty:
            chunks.append(seg)
        time.sleep(0.2)
    if not chunks:
        return
    df = pd.concat(chunks, ignore_index=True)
    df = df.rename(columns={'vol': 'volume'})
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.drop_duplicates(subset='trade_date').sort_values('trade_date').reset_index(drop=True)
    df[['trade_date', 'open', 'high', 'low', 'close', 'volume']].to_csv(csv_path, index=False)


def download_sector_info(data_dir, force=False):
    """从 Tushare 下载股票行业分类，存为 stock_sector.csv。
    行业分类基本不变，文件已存在时默认跳过；传 force=True 强制刷新。
    """
    csv_path = Path(data_dir) / 'stock_sector.csv'
    if csv_path.exists() and not force:
        print(f"行业分类已存在，跳过下载（如需刷新请传 force=True）")
        return
    pro = ts.pro_api()
    df = pro.stock_basic(fields='ts_code,industry')
    if df is None or df.empty:
        print("警告：未获取到行业分类数据")
        return
    df.to_csv(csv_path, index=False)
    print(f"行业分类已保存：{len(df)} 条 → {csv_path}")


def main():
    cfg = load_config()
    ts.set_token(cfg['tushare_token'])

    stocks = pd.read_csv(cfg['stock_list_path'])['ts_code'].tolist()
    data_dir = cfg['data_dir']
    Path(data_dir).mkdir(exist_ok=True)

    for i, ts_code in enumerate(stocks):
        try:
            download_stock(ts_code, cfg['start_date'], cfg['end_date'], data_dir)
            download_weekly(ts_code, cfg['start_date'], cfg['end_date'], data_dir)
            download_monthly(ts_code, cfg['start_date'], cfg['end_date'], data_dir)
            print(f"[{i+1}/{len(stocks)}] {ts_code} OK")
        except Exception as e:
            logging.error(f"{ts_code}: {e}")
            print(f"[{i+1}/{len(stocks)}] {ts_code} FAILED: {e}")

    # 下载基准指数（不做复权）
    benchmark_codes = cfg.get('benchmark_codes') or []
    if not benchmark_codes and cfg.get('benchmark_code'):
        benchmark_codes = [cfg['benchmark_code']]
    for code in benchmark_codes:
        try:
            download_index(code, cfg['start_date'], cfg['end_date'], data_dir)
            print(f"基准指数 {code} OK")
        except Exception as e:
            logging.error(f"{code}: {e}")
            print(f"基准指数 {code} FAILED: {e}")

    # 下载行业分类
    try:
        download_sector_info(data_dir)
    except Exception as e:
        logging.error(f"sector info: {e}")
        print(f"行业分类下载失败: {e}")


if __name__ == '__main__':
    main()
