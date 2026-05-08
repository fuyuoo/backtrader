# my_strategy/tests/test_data_integrity_check.py
import numpy as np
import pandas as pd
import pytest
from pathlib import Path
from my_strategy.tools.data_integrity_check import (
    check_missing_trading_days,
    check_duplicate_dates,
    check_non_monotonic,
    check_abnormal_close_jump,
    check_qfq_break,
    check_suspended_period,
    check_universe_consistency,
    run as integrity_run,
)


def _df(dates, closes):
    return pd.DataFrame({'trade_date': pd.to_datetime(dates), 'close': closes})


def test_check_missing_trading_days_finds_gap():
    benchmark = _df(['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05'], [1, 1, 1, 1])
    stock = _df(['2024-01-02', '2024-01-04', '2024-01-05'], [10, 11, 12])  # 缺 1-03
    issues = check_missing_trading_days('000001.SZ', stock, benchmark)
    assert len(issues) == 1
    assert issues[0]['issue_type'] == 'missing_trading_day'
    assert '2024-01-03' in issues[0]['date_or_range']


def test_check_duplicate_dates_finds_dup():
    df = _df(['2024-01-02', '2024-01-03', '2024-01-03'], [10, 11, 11.5])
    issues = check_duplicate_dates('000001.SZ', df)
    assert len(issues) == 1
    assert issues[0]['issue_type'] == 'duplicate_date'


def test_check_non_monotonic_finds_disorder():
    df = _df(['2024-01-02', '2024-01-04', '2024-01-03'], [10, 11, 12])
    issues = check_non_monotonic('000001.SZ', df)
    assert len(issues) == 1
    assert issues[0]['issue_type'] == 'non_monotonic_date'


def test_check_abnormal_close_jump_flags_35pct():
    df = _df(
        ['2024-01-02', '2024-01-03', '2024-01-04'],
        [10.0, 13.5, 13.5],  # +35% one-day jump (前复权下不应出现)
    )
    issues = check_abnormal_close_jump('000001.SZ', df, threshold_pct=25)
    assert any(i['issue_type'] == 'abnormal_close_jump' for i in issues)


def test_check_qfq_break_finds_zero_close():
    df = _df(['2024-01-02', '2024-01-03'], [10.0, 0.0])
    issues = check_qfq_break('000001.SZ', df)
    assert len(issues) == 1
    assert issues[0]['issue_type'] == 'qfq_break'


def test_check_suspended_period_finds_5day_flat():
    df = pd.DataFrame({
        'trade_date': pd.to_datetime(['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05', '2024-01-08', '2024-01-09']),
        'open':  [10.0, 10.0, 10.0, 10.0, 10.0, 11.0],
        'high':  [10.0, 10.0, 10.0, 10.0, 10.0, 11.0],
        'low':   [10.0, 10.0, 10.0, 10.0, 10.0, 11.0],
        'close': [10.0, 10.0, 10.0, 10.0, 10.0, 11.0],
        'volume': [0, 0, 0, 0, 0, 1000],
    })
    issues = check_suspended_period('000001.SZ', df, min_days=5)
    assert any(i['issue_type'] == 'suspended_period' for i in issues)


def test_check_universe_consistency_detects_orphan_files(tmp_path):
    # daily/ 下有 999999.SZ.csv 但 stock_list 里没有
    (tmp_path / 'daily').mkdir()
    (tmp_path / 'daily' / '000001.SZ.csv').touch()
    (tmp_path / 'daily' / '999999.SZ.csv').touch()
    stock_list = pd.DataFrame({'ts_code': ['000001.SZ', '000002.SZ']})
    issues = check_universe_consistency(tmp_path / 'daily', stock_list)
    types = {i['issue_type'] for i in issues}
    assert 'not_in_stock_list' in types  # 999999.SZ orphan
    assert 'in_list_no_data' in types     # 000002.SZ missing


def test_integrity_run_writes_report(tmp_path):
    """端到端：构造最小 fixture，跑 run() 应产出 integrity_report.csv。"""
    (tmp_path / 'data' / 'daily').mkdir(parents=True)
    (tmp_path / 'results').mkdir()
    # 健康样本
    healthy = _df(pd.date_range('2024-01-02', periods=20, freq='B'), list(range(10, 30)))
    healthy.to_csv(tmp_path / 'data' / 'daily' / '000300.SH.csv', index=False)
    healthy.to_csv(tmp_path / 'data' / 'daily' / '000001.SZ.csv', index=False)
    pd.DataFrame({'ts_code': ['000300.SH', '000001.SZ']}).to_csv(tmp_path / 'stock_list.csv', index=False)
    cfg = {'data_dir': 'data/', 'results_dir': 'results/'}
    integrity_run(tmp_path, cfg)
    out = pd.read_csv(tmp_path / 'results' / 'integrity_report.csv')
    assert {'ts_code', 'issue_type', 'severity', 'date_or_range', 'detail'}.issubset(out.columns)
    assert len(out) == 0  # healthy data should produce zero issues
