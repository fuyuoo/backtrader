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
