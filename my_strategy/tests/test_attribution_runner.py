"""轻量集成测试：使用最小输入，确认 runner 能依次调起所有子模块并产出文件。"""
import pandas as pd
import numpy as np
import pytest
from pathlib import Path
from my_strategy.tools.attribution_runner import run as runner_run


@pytest.fixture
def fake_project(tmp_path):
    """构造一个最小可跑的项目目录。"""
    root = tmp_path / "proj"
    (root / "data" / "daily").mkdir(parents=True)
    (root / "results").mkdir()
    (root / "reports").mkdir()

    # trade_summary.csv
    trades = pd.DataFrame({
        'ts_code': ['000001.SZ'] * 3 + ['000002.SZ'] * 3,
        'entry_date': pd.to_datetime(['2024-01-02', '2024-02-02', '2024-03-02'] * 2),
        'exit_date': pd.to_datetime(['2024-01-10', '2024-02-10', '2024-03-10'] * 2),
        'avg_cost': [10.0, 11.0, 12.0, 20.0, 21.0, 22.0],
        'return_pct': [5.0, -3.0, 2.0, -4.0, 6.0, 1.0],
        'holding_days': [8, 8, 8, 8, 8, 8],
        'exit_reason': ['MA25清仓'] * 6,
        'industry': ['801010'] * 3 + ['801080'] * 3,
        'gross_pnl': [500, -300, 200, -400, 600, 100],
        'entry_hs300_dif_above_zero': [True, False, True, False, True, False],
        'entry_stock_bull_align': [True, True, False, False, True, False],
        'entry_sector_dif_above_zero': [True, True, False, True, False, False],
    })
    trades.to_csv(root / "results" / "trade_summary.csv", index=False)
    # trade_list.csv 模拟生产 schema：包含 price/size/side，cost_breakdown 走模式 C 反推
    trade_list = pd.DataFrame({
        'date': trades['entry_date'].tolist() + trades['exit_date'].tolist(),
        'ts_code': trades['ts_code'].tolist() * 2,
        'side': ['buy'] * 6 + ['sell'] * 6,
        'size': [100] * 12,
        'price': trades['avg_cost'].tolist() + (trades['avg_cost'] * (1 + trades['return_pct'] / 100)).tolist(),
        'reason': ['init'] * 6 + ['MA25清仓'] * 6,
        'episode': list(range(1, 7)) * 2,
    })
    trade_list.to_csv(root / "results" / "trade_list.csv", index=False)

    # 每个 ts_code 的日线（路径修正：data/daily/{ts_code}.csv）
    for code in ['000001.SZ', '000002.SZ']:
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', '2024-04-01', freq='B'),
        })
        df['close'] = 10.0 + np.arange(len(df)) * 0.01
        df.to_csv(root / "data" / "daily" / f"{code}.csv", index=False)

    # stock_sector
    pd.DataFrame({
        'ts_code': ['000001.SZ', '000002.SZ'],
        'sw_index_code': ['801010', '801080'],
    }).to_csv(root / "data" / "stock_sector.csv", index=False)

    return root


def test_runner_produces_all_new_reports(fake_project, monkeypatch):
    # Deviation 3(b): mock old_attribution.run — 它需要 signals_log.csv，
    # 与本集成测试的目标（验证新 pipeline 的 14 张报告）无关。
    import my_strategy.tools.attribution as _old_attr
    monkeypatch.setattr(_old_attr, 'run', lambda project_root, cfg: None)

    np.random.seed(0)
    daily_ret = pd.Series(
        np.random.normal(0.001, 0.01, 60),
        index=pd.date_range('2024-01-02', periods=60, freq='B'),
    )
    bench = pd.Series(
        np.random.normal(0.0005, 0.01, 60),
        index=pd.date_range('2024-01-02', periods=60, freq='B'),
    )
    position_count_log = pd.DataFrame({
        'date': pd.date_range('2024-01-02', periods=60, freq='B'),
        'count': [50] * 60,
    })
    cfg = {
        'data_dir': 'data/',
        'results_dir': 'results/',
        'attribution_report_dir': 'reports',
        'data_paths': {'stock_sector_csv': 'data/stock_sector.csv'},
        'max_positions': 200,
        'commission_rate': 0.0003,
        'stamp_duty': 0.001,
    }
    benchmarks = {'TEST.SH': bench}

    runner_run(
        project_root=fake_project,
        cfg=cfg,
        daily_ret=daily_ret,
        position_count_log=position_count_log,
        benchmarks=benchmarks,
    )

    expected = [
        'payoff_metrics.csv', 'signal_stability.csv',
        'signal_correlation_matrix.csv', 'multi_factor_combo_stats.csv',
        'significance_summary.csv',
        'portfolio_risk_metrics.csv', 'losing_streak_stats.csv',
        'drawdown_periods.csv', 'concurrent_positions_stats.csv', 'period_alpha.csv',
        'holding_period_curve.csv', 'mfe_timing.csv',
        'sector_concentration_stats.csv', 'cost_breakdown.csv',
    ]
    for fname in expected:
        assert (fake_project / 'reports' / fname).exists(), f"missing: {fname}"
    # 中间数据
    assert (fake_project / 'results' / 'daily_position_pnl.csv').exists()
    assert (fake_project / 'results' / 'daily_portfolio_snapshot.csv').exists()
