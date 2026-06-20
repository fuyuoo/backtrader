import pandas as pd
import pytest
from pathlib import Path
from my_strategy.tools.ensure_stock_list_metadata import (
    has_required_columns,
    merge_metadata,
)


def test_has_required_columns_detects_missing():
    df_bare = pd.DataFrame({'ts_code': ['000001.SZ', '000002.SZ']})
    assert has_required_columns(df_bare) is False
    df_full = pd.DataFrame({
        'ts_code': ['000001.SZ'],
        'list_date': ['19910403'],
        'delist_date': [pd.NA],
        'industry': ['银行'],
    })
    assert has_required_columns(df_full) is True


def test_has_required_columns_partial_missing():
    df = pd.DataFrame({'ts_code': ['000001.SZ'], 'industry': ['银行']})
    assert has_required_columns(df) is False  # missing list_date / delist_date


def test_merge_metadata_left_join_preserves_universe():
    existing = pd.DataFrame({'ts_code': ['000001.SZ', '000002.SZ', '999999.SZ']})
    metadata = pd.DataFrame({
        'ts_code': ['000001.SZ', '000002.SZ', '888888.SH'],
        'list_date': ['19910403', '19910129', '20100101'],
        'delist_date': [pd.NA, pd.NA, pd.NA],
        'industry': ['银行', '地产', '科技'],
    })
    out = merge_metadata(existing, metadata)
    assert set(out['ts_code']) == {'000001.SZ', '000002.SZ', '999999.SZ'}
    assert out.loc[out['ts_code'] == '000001.SZ', 'list_date'].iloc[0] == '19910403'
    # 999999.SZ in existing but not in metadata → list_date should be NaN, not dropped
    assert pd.isna(out.loc[out['ts_code'] == '999999.SZ', 'list_date'].iloc[0])
    # 888888.SH only in metadata → must NOT appear (preserve existing universe)
    assert '888888.SH' not in out['ts_code'].values
