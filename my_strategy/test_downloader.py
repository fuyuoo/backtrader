import pandas as pd
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


def _make_df(trade_dates):
    return pd.DataFrame({
        'trade_date': trade_dates,
        'open': [10.0] * len(trade_dates),
        'high': [11.0] * len(trade_dates),
        'low': [9.0] * len(trade_dates),
        'close': [10.5] * len(trade_dates),
        'vol': [1000] * len(trade_dates),
        'amount': [10500.0] * len(trade_dates),
        'pct_chg': [0.5] * len(trade_dates),
    })


# ── _year_chunks ──────────────────────────────────────────────────────────────

def test_year_chunks_three_years():
    from downloader import _year_chunks
    result = list(_year_chunks('20200101', '20221231'))
    assert result == [
        ('20200101', '20201231'),
        ('20210101', '20211231'),
        ('20220101', '20221231'),
    ]


def test_year_chunks_mid_year_end():
    from downloader import _year_chunks
    result = list(_year_chunks('20200601', '20210315'))
    assert result == [
        ('20200601', '20201231'),
        ('20210101', '20210315'),
    ]


# ── download_stock ────────────────────────────────────────────────────────────

def test_download_stock_skips_daily_basic_when_no_ohlcv():
    """C2: OHLCV 为空时，daily_basic 一次都不应被调用。"""
    mock_pro = MagicMock()
    with patch('downloader.ts') as mock_ts, tempfile.TemporaryDirectory() as tmp:
        mock_ts.pro_bar.return_value = None
        from downloader import download_stock
        download_stock('000001.SZ', '20200101', '20201231', tmp, mock_pro, sleep_sec=0)
        mock_pro.daily_basic.assert_not_called()


def test_download_stock_skips_if_file_exists():
    """I3: 文件已存在 → 不发任何 API 请求。"""
    mock_pro = MagicMock()
    with patch('downloader.ts') as mock_ts, tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / '000001.SZ.csv').write_text('dummy')
        from downloader import download_stock
        download_stock('000001.SZ', '20200101', '20201231', tmp, mock_pro, sleep_sec=0)
        mock_ts.pro_bar.assert_not_called()
        mock_pro.daily_basic.assert_not_called()


def test_download_stock_force_redownloads_existing_file():
    """I3: force=True 时即使文件存在也重新下载。"""
    mock_pro = MagicMock()
    mock_pro.daily_basic.return_value = None
    with patch('downloader.ts') as mock_ts, tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / '000001.SZ.csv').write_text('dummy')
        mock_ts.pro_bar.return_value = None  # 无数据 → 提前返回
        from downloader import download_stock
        download_stock('000001.SZ', '20200101', '20201231', tmp, mock_pro,
                       sleep_sec=0, force=True)
        mock_ts.pro_bar.assert_called()


# ── download_bars (合并 weekly / monthly) ─────────────────────────────────────

def test_download_bars_weekly_single_api_call():
    """I1: 周线跨 26 年只发 1 次 pro_bar，不按年切分。"""
    with patch('downloader.ts') as mock_ts, tempfile.TemporaryDirectory() as tmp:
        mock_ts.pro_bar.return_value = _make_df(['20200106'])
        from downloader import download_bars
        download_bars('000001.SZ', '20000101', '20261231', tmp, freq='W', sleep_sec=0)
        assert mock_ts.pro_bar.call_count == 1


def test_download_bars_monthly_single_api_call():
    """I1: 月线跨 26 年只发 1 次 pro_bar。"""
    with patch('downloader.ts') as mock_ts, tempfile.TemporaryDirectory() as tmp:
        mock_ts.pro_bar.return_value = _make_df(['20200131'])
        from downloader import download_bars
        download_bars('000001.SZ', '20000101', '20261231', tmp, freq='M', sleep_sec=0)
        assert mock_ts.pro_bar.call_count == 1


def test_download_bars_writes_correct_filenames():
    """I2: 周线写 _weekly.csv，月线写 _monthly.csv。"""
    with patch('downloader.ts') as mock_ts, tempfile.TemporaryDirectory() as tmp:
        mock_ts.pro_bar.return_value = _make_df(['20200106', '20200113'])
        from downloader import download_bars
        download_bars('000001.SZ', '20200101', '20201231', tmp, freq='W', sleep_sec=0)
        assert (Path(tmp) / '000001.SZ_weekly.csv').exists()

        mock_ts.pro_bar.return_value = _make_df(['20200131'])
        download_bars('000001.SZ', '20200101', '20201231', tmp, freq='M', sleep_sec=0)
        assert (Path(tmp) / '000001.SZ_monthly.csv').exists()


def test_download_bars_skips_if_file_exists():
    """I3: 文件已存在 → 不发 API 请求。"""
    with patch('downloader.ts') as mock_ts, tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / '000001.SZ_weekly.csv').write_text('dummy')
        from downloader import download_bars
        download_bars('000001.SZ', '20200101', '20201231', tmp, freq='W', sleep_sec=0)
        mock_ts.pro_bar.assert_not_called()
