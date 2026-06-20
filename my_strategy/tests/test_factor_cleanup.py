"""验证财务因子已从消费侧彻底移除。"""
import pandas as pd
import pytest
from pathlib import Path


@pytest.mark.parametrize('csv_name', [
    'bottom_trades.csv',
    'top_trades.csv',
    'trade_profile.csv',
])
def test_no_financial_factor_cols(csv_name, tmp_path):
    """生产环境 reports/ 下这几张表不应含 factor_pe_ttm / factor_roe / factor_netprofit_yoy 列。

    本测试在端到端跑完一次后才有意义；CI 环境若没有真实 reports，跳过。
    """
    report = Path(__file__).parent.parent / 'reports' / csv_name
    if not report.exists():
        pytest.skip(f"{csv_name} 不存在（端到端未跑过），跳过")
    df = pd.read_csv(report)
    forbidden = {'factor_pe_ttm', 'factor_roe', 'factor_netprofit_yoy'}
    assert forbidden.isdisjoint(df.columns), \
        f"{csv_name} 仍含财务因子列：{set(df.columns) & forbidden}"


def test_default_signals_whitelist_no_finance():
    from my_strategy.tools.attribution_runner import DEFAULT_SIGNALS_WHITELIST
    forbidden = {'factor_pe_ttm', 'factor_roe', 'factor_netprofit_yoy'}
    assert forbidden.isdisjoint(set(DEFAULT_SIGNALS_WHITELIST))


def test_compute_cost_breakdown_overall_row_has_gross_pnl():
    """cost_breakdown.csv overall 行 gross_pnl / net_pnl / cost_pct_of_gross 必须非空。

    构造合成 trades 验证 _cost_block 的 gross_pnl 路径在 trades 含 gross_pnl 时被覆盖。
    """
    from my_strategy.tools.position_curve_attribution import compute_cost_breakdown
    trades = pd.DataFrame({
        'entry_date': pd.to_datetime(['2024-01-02', '2024-02-02']),
        'gross_pnl': [10000.0, -5000.0],
        'price': [10.0, 20.0],
        'size': [100, 100],
        'side': ['buy', 'sell'],
        'exit_reason': ['MA25清仓', 'MA60止损'],
    })
    out = compute_cost_breakdown(trades, cfg={'commission_rate': 0.0003, 'stamp_duty': 0.001})
    overall = out[(out['dimension'] == 'overall') & (out['bucket'] == 'all')].iloc[0]
    assert pd.notna(overall['gross_pnl'])
    assert pd.notna(overall['net_pnl'])
    assert pd.notna(overall['cost_pct_of_gross'])
    assert overall['gross_pnl'] == 5000.0


def test_backtest_merge_factors_no_financial_factors():
    """_merge_factors 不应向 signals 注入财务因子列。"""
    from my_strategy.backtest import _merge_factors
    sig_df = pd.DataFrame({
        'ts_code': ['A.SZ'],
        'date': pd.to_datetime(['2024-01-02']),
        'signal': [1],
    })
    # indicators 含财务因子列（模拟旧数据文件）
    ind_df = pd.DataFrame({
        'trade_date': pd.to_datetime(['2024-01-02']),
        'factor_momentum_60d': [0.05],
        'factor_ma60_dist': [0.02],
        'factor_macd_strength': [0.8],
        'roe': [15.0],
        'pe_ttm': [20.0],
        'netprofit_yoy': [0.3],
    })
    result = _merge_factors(sig_df, {'A.SZ': ind_df})
    forbidden = {'factor_pe_ttm', 'factor_roe', 'factor_netprofit_yoy'}
    assert forbidden.isdisjoint(set(result.columns)), \
        f"_merge_factors 仍注入财务因子列：{set(result.columns) & forbidden}"
