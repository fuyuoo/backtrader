"""build_sector_mapping 单元测试 — 用 mock 替代 Tushare API。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import pytest


def test_build_mapping_combines_constituents(monkeypatch):
    """31 个 SW 一级行业的成分股合并成 ts_code → sw_code 单值映射。"""
    from my_strategy.src import build_sector_mapping

    fake_members = {
        '801010.SI': pd.DataFrame({
            'con_code': ['000001.SZ', '600000.SH'],
            'in_date': ['20100101', '20100101'],
            'out_date': [None, None],
        }),
        '801030.SI': pd.DataFrame({
            'con_code': ['000002.SZ'],
            'in_date': ['20100101'],
            'out_date': [None],
        }),
    }
    class FakePro:
        def index_member(self, index_code):
            return fake_members.get(index_code, pd.DataFrame(
                columns=['con_code', 'in_date', 'out_date']))

    mapping = build_sector_mapping.fetch_mapping(
        FakePro(), sw_codes=['801010.SI', '801030.SI'])
    assert mapping == {
        '000001.SZ': '801010.SI',
        '600000.SH': '801010.SI',
        '000002.SZ': '801030.SI',
    }


def test_build_mapping_excludes_out_constituents(monkeypatch):
    """out_date 非空的成分（已退出）不进入映射。"""
    from my_strategy.src import build_sector_mapping

    fake_members = {
        '801010.SI': pd.DataFrame({
            'con_code': ['000001.SZ', '999999.SZ'],
            'in_date': ['20100101', '20100101'],
            'out_date': [None, '20200101'],   # 999999 已退出
        }),
    }
    class FakePro:
        def index_member(self, index_code):
            return fake_members[index_code]

    mapping = build_sector_mapping.fetch_mapping(FakePro(), sw_codes=['801010.SI'])
    assert mapping == {'000001.SZ': '801010.SI'}


def test_build_mapping_raises_on_conflict(monkeypatch):
    """同一只股票同时属于两个 SW 行业 → raise。"""
    from my_strategy.src import build_sector_mapping

    fake_members = {
        '801010.SI': pd.DataFrame({
            'con_code': ['000001.SZ'], 'in_date': ['20100101'], 'out_date': [None],
        }),
        '801030.SI': pd.DataFrame({
            'con_code': ['000001.SZ'], 'in_date': ['20100101'], 'out_date': [None],
        }),
    }
    class FakePro:
        def index_member(self, index_code):
            return fake_members[index_code]

    with pytest.raises(ValueError, match='000001.SZ'):
        build_sector_mapping.fetch_mapping(
            FakePro(), sw_codes=['801010.SI', '801030.SI'])


def test_merge_into_stock_sector_csv(tmp_path):
    """fetch_mapping 结果写回 stock_sector.csv 时新增 sw_index_code 列。"""
    from my_strategy.src import build_sector_mapping

    src_csv = tmp_path / 'stock_sector.csv'
    src_csv.write_text(
        'ts_code,industry\n000001.SZ,银行\n600000.SH,银行\n999999.SZ,其他\n',
        encoding='utf-8',
    )
    mapping = {'000001.SZ': '801780.SI', '600000.SH': '801780.SI'}
    coverage = build_sector_mapping.merge_to_csv(src_csv, mapping)

    df = pd.read_csv(src_csv)
    assert list(df.columns) == ['ts_code', 'industry', 'sw_index_code']
    assert df.set_index('ts_code').loc['000001.SZ', 'sw_index_code'] == '801780.SI'
    assert df.set_index('ts_code').loc['600000.SH', 'sw_index_code'] == '801780.SI'
    assert pd.isna(df.set_index('ts_code').loc['999999.SZ', 'sw_index_code'])
    assert coverage == 2 / 3   # 2/3 股票被映射


def test_merge_raises_when_coverage_below_95(tmp_path):
    """覆盖率 < 95% → raise。"""
    from my_strategy.src import build_sector_mapping

    src_csv = tmp_path / 'stock_sector.csv'
    rows = ['ts_code,industry'] + [f'{i:06d}.SZ,其他' for i in range(100)]
    src_csv.write_text('\n'.join(rows) + '\n', encoding='utf-8')

    mapping = {f'{i:06d}.SZ': '801010.SI' for i in range(50)}  # 50% 覆盖
    with pytest.raises(ValueError, match='覆盖率'):
        build_sector_mapping.merge_to_csv(src_csv, mapping, min_coverage=0.95)
