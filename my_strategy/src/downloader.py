import json
import time
import logging
import argparse
import concurrent.futures
import pandas as pd
import tushare as ts
from pathlib import Path

def _call_with_timeout(fn, *args, timeout=30, **kwargs):
    """在独立线程中执行 fn，超过 timeout 秒则抛 TimeoutError。
    每次创建一次性 executor 并在超时分支 shutdown(wait=False)，
    避免挂死的 socket recv 线程占用共享池导致后续调用永久串行排队。
    """
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        return executor.submit(fn, *args, **kwargs).result(timeout=timeout)
    finally:
        executor.shutdown(wait=False)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LOG_DIR = _PROJECT_ROOT / 'logs'
_LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(filename=str(_LOG_DIR / 'download_errors.log'),
                    level=logging.WARNING, format='%(asctime)s %(message)s')


def load_config(config_path=None):
    if config_path is None:
        config_path = _PROJECT_ROOT / 'config.json'
    with open(config_path, 'r') as f:
        return json.load(f)


def get_last_date(csv_path):
    """读取本地 CSV 最后一条交易日期。
    注意：前复权数据历史价格随复权因子变化，需全量重拉，此函数当前未被调用。
    保留供将来非复权数据增量下载使用。
    """
    df = pd.read_csv(csv_path, usecols=['trade_date'])
    return df['trade_date'].max()


def _year_chunks(start_date: str, end_date: str, years: int = 10):
    """按 N 年切分日期区间。
    Tushare pro_bar 单次返回约 6000 行（≈24 年日线），按 10 年/段提供安全余量；
    单元测试可显式传 years=1 沿用旧行为。
    """
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    cur = start
    while cur <= end:
        seg_end = min(pd.Timestamp(f"{cur.year + years - 1}1231"), end)
        yield cur.strftime('%Y%m%d'), seg_end.strftime('%Y%m%d')
        cur = pd.Timestamp(f"{cur.year + years}0101")


def download_stock(ts_code, start_date, end_date, data_dir, pro,
                   sleep_sec=0.3, force=False):
    """下载单只股票前复权日线数据，全量重新下载以保证复权基准一致。"""
    csv_path = Path(data_dir) / 'daily' / f"{ts_code}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if csv_path.exists() and not force:
        return

    # 第一阶段：收集 OHLCV，任何年份有数据才继续拉 circ_mv
    chunks = []
    for seg_start, seg_end in _year_chunks(start_date, end_date):
        seg = _call_with_timeout(ts.pro_bar,
            ts_code=ts_code,
            adj='qfq',
            start_date=seg_start,
            end_date=seg_end,
        )
        if seg is not None and not seg.empty:
            chunks.append(seg)
        time.sleep(sleep_sec)

    if not chunks:
        return

    # 第二阶段：按相同年份区间拉 circ_mv
    basic_chunks = []
    for seg_start, seg_end in _year_chunks(start_date, end_date):
        seg2 = _call_with_timeout(pro.daily_basic,
            ts_code=ts_code,
            start_date=seg_start,
            end_date=seg_end,
            fields='trade_date,circ_mv',
        )
        if seg2 is not None and not seg2.empty:
            basic_chunks.append(seg2)
        time.sleep(sleep_sec)

    df = pd.concat(chunks, ignore_index=True)
    df = df.rename(columns={'vol': 'volume'})
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.drop_duplicates(subset='trade_date').sort_values('trade_date').reset_index(drop=True)

    if basic_chunks:
        basic_df = pd.concat(basic_chunks, ignore_index=True)
        basic_df['trade_date'] = pd.to_datetime(basic_df['trade_date'])
        basic_df = basic_df.drop_duplicates(subset='trade_date')
        df = df.merge(basic_df, on='trade_date', how='left')
    else:
        logging.warning(f"{ts_code}: daily_basic 返回空，circ_mv 全为 NaN")
        print(f"  WARN {ts_code}: daily_basic 返回空，circ_mv 全为 NaN")
        df['circ_mv'] = float('nan')

    required_cols = ['trade_date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg', 'circ_mv']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        logging.warning(f"{ts_code}: API 返回缺少字段 {missing}，将填充 NaN")
        for c in missing:
            df[c] = float('nan')
    df = df[required_cols]
    df.to_csv(csv_path, index=False)


def download_bars(ts_code, start_date, end_date, data_dir, freq='W',
                  sleep_sec=0.3, force=False):
    """下载周线(freq='W')或月线(freq='M') OHLCV。
    数据量小（月线 ≈300 条，周线 ≈1300 条），一次拉取无需按年切分。
    """
    subdir = {'W': 'weekly', 'M': 'monthly'}[freq]
    csv_path = Path(data_dir) / subdir / f"{ts_code}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if csv_path.exists() and not force:
        return

    seg = _call_with_timeout(ts.pro_bar, ts_code=ts_code, adj='qfq', freq=freq,
                             start_date=start_date, end_date=end_date)
    time.sleep(sleep_sec)
    if seg is None or seg.empty:
        return

    df = seg.rename(columns={'vol': 'volume'})
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.drop_duplicates(subset='trade_date').sort_values('trade_date').reset_index(drop=True)
    df[['trade_date', 'open', 'high', 'low', 'close', 'volume']].to_csv(csv_path, index=False)


def download_index(ts_code, start_date, end_date, data_dir, pro,
                   sleep_sec=0.3, force=False):
    """下载指数日线数据（无复权），与个股日线一起放到 daily/ 子目录。"""
    csv_path = Path(data_dir) / 'daily' / f"{ts_code}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if csv_path.exists() and not force:
        return

    chunks = []
    for seg_start, seg_end in _year_chunks(start_date, end_date):
        seg = _call_with_timeout(pro.index_daily, ts_code=ts_code, start_date=seg_start, end_date=seg_end)
        if seg is not None and not seg.empty:
            chunks.append(seg)
        time.sleep(sleep_sec)
    if not chunks:
        return

    df = pd.concat(chunks, ignore_index=True)
    df = df.rename(columns={'vol': 'volume'})
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.drop_duplicates(subset='trade_date').sort_values('trade_date').reset_index(drop=True)
    df[['trade_date', 'open', 'high', 'low', 'close', 'volume']].to_csv(csv_path, index=False)


def download_sector_info(data_dir, pro, force=False):
    """从 Tushare 下载股票行业分类，存为 stock_sector.csv。
    行业分类基本不变，文件已存在时默认跳过；传 force=True 强制刷新。
    """
    csv_path = Path(data_dir) / 'stock_sector.csv'
    if csv_path.exists() and not force:
        print(f"行业分类已存在，跳过下载（如需刷新请传 --force）")
        return

    df = pro.stock_basic(fields='ts_code,industry')
    if df is None or df.empty:
        logging.warning("未获取到行业分类数据")
        print("警告：未获取到行业分类数据")
        return
    df.to_csv(csv_path, index=False)
    print(f"行业分类已保存：{len(df)} 条 → {csv_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--force', action='store_true',
                        help='强制重新下载所有数据（忽略已存在的文件）')
    args = parser.parse_args()

    cfg = load_config()
    ts.set_token(cfg['tushare_token'])
    pro = ts.pro_api()

    sleep_sec = 60.0 / cfg.get('api_rate_per_min', 500)

    benchmark_codes = set(cfg.get('benchmark_codes') or [])
    if cfg.get('benchmark_code'):
        benchmark_codes.add(cfg['benchmark_code'])

    all_stocks = pd.read_csv(cfg['stock_list_path'])['ts_code'].tolist()
    # 过滤掉基准指数代码，避免和 download_index 输出的文件互相覆盖
    stocks = [s for s in all_stocks if s not in benchmark_codes]

    data_dir = cfg['data_dir']
    Path(data_dir).mkdir(exist_ok=True)

    failures = []  # [(target, step, error_str)]

    for i, ts_code in enumerate(stocks):
        failed_steps = []
        for step_name, step_fn, step_kwargs in [
            ('daily',   download_stock, dict(pro=pro)),
            ('weekly',  download_bars,  dict(freq='W')),
            ('monthly', download_bars,  dict(freq='M')),
        ]:
            try:
                step_fn(ts_code, cfg['start_date'], cfg['end_date'],
                        data_dir, sleep_sec=sleep_sec, force=args.force,
                        **step_kwargs)
            except Exception as e:
                logging.error(f"{ts_code} [{step_name}]: {e}")
                failed_steps.append(step_name)
                failures.append((ts_code, step_name, str(e)))
                print(f"[{i+1}/{len(stocks)}] {ts_code} [{step_name}] FAILED: {e}")
        status = f"PARTIAL({','.join(failed_steps)})" if failed_steps else "OK"
        print(f"[{i+1}/{len(stocks)}] {ts_code} {status}")

    for code in sorted(benchmark_codes):
        try:
            download_index(code, cfg['start_date'], cfg['end_date'],
                           data_dir, pro, sleep_sec=sleep_sec, force=args.force)
            print(f"基准指数 {code} OK")
        except Exception as e:
            logging.error(f"{code}: {e}")
            failures.append((code, 'index', str(e)))
            print(f"基准指数 {code} FAILED: {e}")

    try:
        download_sector_info(data_dir, pro, force=args.force)
    except Exception as e:
        logging.error(f"sector info: {e}")
        failures.append(('sector_info', 'sector', str(e)))
        print(f"行业分类下载失败: {e}")

    # 末尾汇总并主动打印失败，避免静默吞错
    if failures:
        print(f"\n========== 下载失败汇总：{len(failures)} 项 ==========")
        for target, step, err in failures[:20]:
            print(f"  {target} [{step}]: {err}")
        if len(failures) > 20:
            print(f"  ... 另有 {len(failures) - 20} 项，详见 download_errors.log")
        # 失败比例超过 10% 视为批量异常，抛出让调用者必须正视
        total_targets = len(stocks) + len(benchmark_codes) + 1
        if len(failures) > total_targets * 0.10:
            raise RuntimeError(
                f"下载失败率 {len(failures)}/{total_targets} 超过 10%，"
                f"可能是 token/网络/限频问题，请检查日志后重跑"
            )


if __name__ == '__main__':
    main()
