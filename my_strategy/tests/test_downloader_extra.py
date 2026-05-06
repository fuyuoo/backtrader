import pandas as pd
from pathlib import Path
from unittest.mock import MagicMock
from my_strategy.src import downloader_extra


def test_download_daily_basic_writes_csv(tmp_path):
    pro = MagicMock()
    fake_df = pd.DataFrame({
        'ts_code': ['000001.SZ'] * 3,
        'trade_date': ['20240101', '20240102', '20240103'],
        'pe_ttm': [10.5, 10.6, 10.7],
        'pb': [1.2, 1.21, 1.22],
        'total_mv': [100000.0, 100100.0, 100200.0],
        'circ_mv': [80000.0, 80100.0, 80200.0],
        'turnover_rate': [1.0, 1.1, 1.2],
    })
    pro.daily_basic.return_value = fake_df

    downloader_extra.download_daily_basic(
        ts_code='000001.SZ',
        start_date='20240101',
        end_date='20240103',
        out_dir=tmp_path,
        pro=pro,
        sleep_sec=0,
    )

    csv = tmp_path / '000001.SZ.csv'
    assert csv.exists()
    df = pd.read_csv(csv)
    assert list(df.columns) == ['ts_code', 'trade_date', 'pe_ttm', 'pb',
                                 'total_mv', 'circ_mv', 'turnover_rate']
    assert len(df) == 3


def test_download_daily_basic_skips_existing(tmp_path):
    pro = MagicMock()
    csv = tmp_path / '000001.SZ.csv'
    csv.write_text('existing')
    downloader_extra.download_daily_basic(
        ts_code='000001.SZ',
        start_date='20240101',
        end_date='20240103',
        out_dir=tmp_path,
        pro=pro,
        sleep_sec=0,
    )
    pro.daily_basic.assert_not_called()
    assert csv.read_text() == 'existing'
