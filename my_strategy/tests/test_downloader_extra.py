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


def test_download_fina_indicator_keeps_ann_date(tmp_path):
    pro = MagicMock()
    fake_df = pd.DataFrame({
        'ts_code': ['000001.SZ'] * 2,
        'ann_date': ['20240430', '20240828'],
        'end_date': ['20240331', '20240630'],
        'roe': [12.5, 13.0],
        'roe_yearly': [50.0, 52.0],
        'netprofit_yoy': [15.0, 18.0],
        'grossprofit_margin': [40.0, 41.0],
    })
    pro.fina_indicator.return_value = fake_df

    downloader_extra.download_fina_indicator(
        ts_code='000001.SZ',
        start_date='20240101',
        end_date='20241231',
        out_dir=tmp_path,
        pro=pro,
        sleep_sec=0,
    )

    df = pd.read_csv(tmp_path / '000001.SZ.csv')
    assert 'ann_date' in df.columns
    assert 'end_date' in df.columns
    assert 'roe' in df.columns
    assert len(df) == 2


def test_download_sw_index_writes_ohlcv(tmp_path):
    pro = MagicMock()
    fake_df = pd.DataFrame({
        'ts_code': ['801010.SI'] * 2,
        'trade_date': ['20240101', '20240102'],
        'open': [3000.0, 3010.0],
        'high': [3050.0, 3060.0],
        'low': [2990.0, 3000.0],
        'close': [3020.0, 3030.0],
        'vol': [1e8, 1.1e8],
    })
    pro.sw_daily.return_value = fake_df

    downloader_extra.download_sw_index(
        index_code='801010.SI',
        start_date='20240101',
        end_date='20240102',
        out_dir=tmp_path,
        pro=pro,
        sleep_sec=0,
    )

    df = pd.read_csv(tmp_path / '801010.SI.csv')
    assert 'close' in df.columns
    assert len(df) == 2
