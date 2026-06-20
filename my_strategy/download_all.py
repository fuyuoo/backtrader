import json
import time
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import tushare as ts


def fetch_index_constituents(pro, index_codes):
    """获取多个指数的成分股并集，取最近可用日期的权重快照。"""
    all_codes = set()
    today = datetime.today()
    end_d = today.strftime('%Y%m%d')
    start_d = (today - timedelta(days=60)).strftime('%Y%m%d')

    for idx_code in index_codes:
        try:
            df = pro.index_weight(index_code=idx_code, start_date=start_d, end_date=end_d)
        except Exception as e:
            print(f"  {idx_code}: 拉取成分股失败 — {e}")
            continue

        if df is None or df.empty:
            print(f"  {idx_code}: 无成分股数据（{start_d}～{end_d}）")
            continue

        latest_date = df['trade_date'].max()
        constituents = df[df['trade_date'] == latest_date]['con_code'].tolist()
        all_codes.update(constituents)
        print(f"  {idx_code}: {len(constituents)} 只成分股（截至 {latest_date}）")
        time.sleep(0.5)

    return sorted(all_codes)


def main():
    cfg_path = Path(__file__).parent / 'config.json'
    with open(cfg_path, 'r') as f:
        cfg = json.load(f)

    ts.set_token(cfg['tushare_token'])
    pro = ts.pro_api()

    index_codes = cfg.get('index_codes', ['000300.SH', '000905.SH'])
    print(f"正在获取指数成分股：{index_codes}")
    stocks = fetch_index_constituents(pro, index_codes)

    if not stocks:
        print("未获取到任何成分股，终止")
        return

    out_path = Path(__file__).parent / 'a_stock_list.txt'
    with open(out_path, 'w') as f:
        f.write('ts_code\n')
        for code in stocks:
            f.write(f'{code}\n')

    print(f'共获取 {len(stocks)} 只成分股，已保存到 {out_path}')


if __name__ == '__main__':
    main()
