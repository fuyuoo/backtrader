import json
from pathlib import Path
import tushare as ts


def main():
    cfg_path = Path(__file__).parent / 'config.json'
    with open(cfg_path, 'r') as f:
        cfg = json.load(f)

    ts.set_token(cfg['tushare_token'])
    pro = ts.pro_api()

    df = pro.stock_basic(exchange='', list_status='L', fields='ts_code')

    out_path = Path(__file__).parent / 'a_stock_list.txt'
    with open(out_path, 'w') as f:
        f.write('ts_code\n')
        for code in df['ts_code']:
            f.write(f'{code}\n')

    print(f'共获取 {len(df)} 条数据，已保存到 {out_path}')

    from src import downloader, downloader_extra, calc_indicators, build_cross_section_pct

    print("\n========== 下载 OHLCV ==========")
    downloader.main()

    print("\n========== 下载基本面数据 ==========")
    downloader_extra.main()

    print("\n========== 计算指标 ==========")
    calc_indicators.main()

    print("\n========== 横截面分位数 ==========")
    build_cross_section_pct.main()


if __name__ == '__main__':
    main()
