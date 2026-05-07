import time
import pandas as pd
from pathlib import Path

from .downloader import _call_with_timeout, _year_chunks

DAILY_BASIC_COLS = ['ts_code', 'trade_date', 'pe_ttm', 'pb',
                    'total_mv', 'circ_mv', 'turnover_rate']


def download_daily_basic(ts_code, start_date, end_date, out_dir, pro,
                         sleep_sec=0.3, force=False):
    """下载单只股票的 daily_basic（估值、市值、换手率）。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{ts_code}.csv"
    if csv_path.exists() and not force:
        return

    chunks = []
    for seg_start, seg_end in _year_chunks(start_date, end_date):
        seg = _call_with_timeout(
            pro.daily_basic,
            ts_code=ts_code,
            start_date=seg_start,
            end_date=seg_end,
            fields=','.join(DAILY_BASIC_COLS),
        )
        if seg is not None and not seg.empty:
            chunks.append(seg)
        time.sleep(sleep_sec)

    if not chunks:
        return
    df = pd.concat(chunks).drop_duplicates(subset=['trade_date'])
    df = df.sort_values('trade_date').reset_index(drop=True)
    df.to_csv(csv_path, index=False)


FINA_COLS = ['ts_code', 'ann_date', 'end_date',
             'roe', 'roe_yearly', 'netprofit_yoy', 'grossprofit_margin']


def download_fina_indicator(ts_code, start_date, end_date, out_dir, pro,
                            sleep_sec=0.3, force=False):
    """下载单只股票的季度财务指标。保留 ann_date（公告日）用于反未来函数对齐。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{ts_code}.csv"
    if csv_path.exists() and not force:
        return

    df = _call_with_timeout(
        pro.fina_indicator,
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date,
        fields=','.join(FINA_COLS),
    )
    time.sleep(sleep_sec)
    if df is None or df.empty:
        return
    df = df.sort_values(['ann_date', 'end_date']).reset_index(drop=True)
    df.to_csv(csv_path, index=False)


SW_INDEX_COLS = ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'vol']


def download_sw_index(index_code, start_date, end_date, out_dir, pro,
                      sleep_sec=0.3, force=False):
    """下载申万一级行业指数 OHLCV。Tushare 接口名为 sw_daily。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{index_code}.csv"
    if csv_path.exists() and not force:
        return

    chunks = []
    for seg_start, seg_end in _year_chunks(start_date, end_date):
        seg = _call_with_timeout(
            pro.sw_daily,
            ts_code=index_code,
            start_date=seg_start,
            end_date=seg_end,
            fields=','.join(SW_INDEX_COLS),
        )
        if seg is not None and not seg.empty:
            chunks.append(seg)
        time.sleep(sleep_sec)

    if not chunks:
        return
    df = pd.concat(chunks).drop_duplicates(subset=['trade_date'])
    df = df.sort_values('trade_date').reset_index(drop=True)
    df.to_csv(csv_path, index=False)


def download_sw_bars(sw_code, start_date, end_date, out_dir, freq='W',
                    sleep_sec=0.3, force=False):
    """下载申万一级行业指数周/月线（freq='W' 或 'M'），asset='I' 必传。
    与 downloader.download_bars 对称，唯一差别：asset='I' 而非默认股票。
    """
    import tushare as ts

    csv_path = Path(out_dir) / f"{sw_code}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if csv_path.exists() and not force:
        return

    seg = ts.pro_bar(ts_code=sw_code, asset='I', freq=freq,
                     start_date=start_date, end_date=end_date)
    if sleep_sec:
        time.sleep(sleep_sec)
    if seg is None or seg.empty:
        return

    df = seg.rename(columns={'vol': 'volume'})
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.drop_duplicates(subset='trade_date').sort_values('trade_date').reset_index(drop=True)
    df[['trade_date', 'open', 'high', 'low', 'close', 'volume']].to_csv(csv_path, index=False)


def main():
    import json
    import tushare as ts

    project_root = Path(__file__).resolve().parent.parent
    cfg = json.loads((project_root / 'config.json').read_text())

    token_path = project_root.parent / 'learn_backtrader' / 'Data' / 'tushare_token.json'
    token = json.loads(token_path.read_text())['token']
    ts.set_token(token)
    pro = ts.pro_api()

    data_dir = project_root / cfg['data_dir']
    paths = cfg['data_paths']
    start = cfg['start_date']
    end = cfg['end_date']

    stocks = pd.read_csv(project_root / cfg['stock_list_path'])['ts_code'].tolist()

    db_dir = data_dir / Path(paths['daily_basic_dir']).name
    fi_dir = data_dir / Path(paths['fina_indicator_dir']).name
    for i, ts_code in enumerate(stocks):
        download_daily_basic(ts_code, start, end, db_dir, pro)
        download_fina_indicator(ts_code, start, end, fi_dir, pro)
        if (i + 1) % 100 == 0:
            print(f"[{i+1}/{len(stocks)}] daily_basic+fina")

    sw_dir = data_dir / Path(paths['sw_index_dir']).name
    for code in cfg['sw_index_codes']:
        download_sw_index(code, start, end, sw_dir, pro)
        print(f"SW {code} OK")

    sw_weekly_dir = data_dir / 'sw_weekly'
    for code in cfg['sw_index_codes']:
        download_sw_bars(code, start, end, sw_weekly_dir, freq='W')
        print(f"SW {code} weekly OK")

    sw_monthly_dir = data_dir / 'sw_monthly'
    for code in cfg['sw_index_codes']:
        download_sw_bars(code, start, end, sw_monthly_dir, freq='M')
        print(f"SW {code} monthly OK")


if __name__ == '__main__':
    main()
