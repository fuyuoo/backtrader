import pandas as pd
from pathlib import Path
from my_strategy.src.build_cross_section_pct import (
    compute_cross_section_pct,
    process_indicators_dir,
)


def test_compute_cross_section_pct_ranks_within_day():
    df = pd.DataFrame({
        'ts_code': ['A', 'B', 'C', 'A', 'B', 'C'],
        'trade_date': pd.to_datetime(['2024-01-01'] * 3 + ['2024-01-02'] * 3),
        'factor_momentum_60d': [0.1, 0.2, 0.3, 0.5, 0.4, 0.3],
        'factor_ma60_dist': [0.0, 0.05, 0.1, 0.0, 0.0, 0.0],
        'factor_macd_strength': [1.0, 2.0, 3.0, 3.0, 2.0, 1.0],
        'roe': [10.0, 20.0, 30.0, 30.0, 20.0, 10.0],
        'pe_ttm': [10.0, 20.0, 30.0, 10.0, 20.0, 30.0],
        'netprofit_yoy': [5.0, 10.0, 15.0, 5.0, 10.0, 15.0],
        'factor_sector_momentum_60d': [0.01, 0.02, 0.03, 0.03, 0.02, 0.01],
    })
    out = compute_cross_section_pct(df)
    # 2024-01-01: momentum A=0.1, B=0.2, C=0.3 → rank(pct=True): A最低, C最高
    a01 = out[(out['ts_code'] == 'A') & (out['trade_date'] == pd.Timestamp('2024-01-01'))].iloc[0]
    c01 = out[(out['ts_code'] == 'C') & (out['trade_date'] == pd.Timestamp('2024-01-01'))].iloc[0]
    assert a01['pct_momentum_60d'] < c01['pct_momentum_60d']
    # PE 反向：低 PE → 高分位（A PE=10最低 → 分位最高）
    assert a01['pct_pe'] > c01['pct_pe']


def test_process_indicators_dir_writes_back(tmp_path):
    in_dir = tmp_path / 'indicators'
    in_dir.mkdir()
    df_a = pd.DataFrame({
        'trade_date': pd.to_datetime(['2024-01-01', '2024-01-02']),
        'close': [10.0, 10.1],
        'factor_momentum_60d': [0.1, 0.5],
        'factor_ma60_dist': [0.0, 0.0],
        'factor_macd_strength': [1.0, 3.0],
        'roe': [10.0, 30.0],
        'pe_ttm': [30.0, 10.0],
        'netprofit_yoy': [5.0, 15.0],
        'factor_sector_momentum_60d': [0.01, 0.03],
    })
    df_b = df_a.copy()
    df_b['factor_momentum_60d'] = [0.2, 0.4]
    df_b['roe'] = [20.0, 20.0]
    df_a.to_csv(in_dir / 'A.csv', index=False)
    df_b.to_csv(in_dir / 'B.csv', index=False)

    process_indicators_dir(in_dir)

    out_a = pd.read_csv(in_dir / 'A.csv')
    assert 'pct_momentum_60d' in out_a.columns
    assert 'pct_roe' in out_a.columns
    assert 'pct_pe' in out_a.columns
