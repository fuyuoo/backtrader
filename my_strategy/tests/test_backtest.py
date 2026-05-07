import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from datetime import date
from backtest import _print_trade_stats, backfill_forward_returns, _compute_regime_flags


def _make_summary_df():
    return pd.DataFrame([
        {
            'ts_code': '600000.SH', 'episode': 1,
            'entry_date': date(2019, 1, 10), 'exit_date': date(2019, 2, 15),
            'holding_days': 36, 'avg_cost': 10.0, 'avg_exit_price': 11.0,
            'total_shares': 1000, 'gross_pnl': 1000.0, 'return_pct': 10.0,
            'add_count': 0, 'take_profit_count': 2, 'exit_reason': 'MA25清仓',
            'status': 'completed',
        },
        {
            'ts_code': '600001.SH', 'episode': 1,
            'entry_date': date(2019, 3, 1), 'exit_date': date(2019, 3, 20),
            'holding_days': 19, 'avg_cost': 10.0, 'avg_exit_price': 9.5,
            'total_shares': 1000, 'gross_pnl': -500.0, 'return_pct': -5.0,
            'add_count': 0, 'take_profit_count': 0, 'exit_reason': 'MA60止损',
            'status': 'completed',
        },
    ])


def test_print_trade_stats_win_rate(capsys):
    _print_trade_stats(_make_summary_df())
    out = capsys.readouterr().out
    assert '胜率：50.0%' in out


def test_print_trade_stats_payoff_ratio(capsys):
    _print_trade_stats(_make_summary_df())
    out = capsys.readouterr().out
    # avg_win=10.0, avg_loss=5.0, payoff=2.0
    assert '盈亏比：2.00' in out


def test_print_trade_stats_exit_reason(capsys):
    _print_trade_stats(_make_summary_df())
    out = capsys.readouterr().out
    assert 'MA60止损' in out
    assert 'MA25清仓' in out


def test_print_trade_stats_empty(capsys):
    """空 DataFrame 不应崩溃。"""
    _print_trade_stats(pd.DataFrame())
    out = capsys.readouterr().out
    assert '无已完成交易' in out


def test_backfill_forward_returns_5_20_60():
    indicators_by_code = {
        'A.SZ': pd.DataFrame({
            'trade_date': pd.date_range('2024-01-01', periods=80, freq='B'),
            'close': list(range(100, 180)),
        })
    }
    signals = [
        {'ts_code': 'A.SZ', 'date': pd.Timestamp('2024-01-01').date(),
         'forward_return_5d': None, 'forward_return_20d': None, 'forward_return_60d': None},
    ]
    backfill_forward_returns(signals, indicators_by_code)
    assert abs(signals[0]['forward_return_5d'] - (105 - 100) / 100) < 1e-6
    assert abs(signals[0]['forward_return_20d'] - (120 - 100) / 100) < 1e-6
    assert abs(signals[0]['forward_return_60d'] - (160 - 100) / 100) < 1e-6


def test_backfill_forward_returns_handles_missing_horizon():
    """信号触发后剩余交易日不足时，对应字段保持 None。"""
    indicators_by_code = {
        'A.SZ': pd.DataFrame({
            'trade_date': pd.date_range('2024-01-01', periods=10, freq='B'),
            'close': [100.0] * 10,
        })
    }
    signals = [
        {'ts_code': 'A.SZ', 'date': pd.Timestamp('2024-01-08').date(),
         'forward_return_5d': None, 'forward_return_20d': None, 'forward_return_60d': None},
    ]
    backfill_forward_returns(signals, indicators_by_code)
    assert signals[0]['forward_return_5d'] is None
    assert signals[0]['forward_return_20d'] is None
    assert signals[0]['forward_return_60d'] is None


def _stock_row(close=10.0, ma25=9.0, ma60=8.0, ma144=7.0, ma180=6.0):
    return pd.Series({'close': close, 'ma25': ma25, 'ma60': ma60,
                      'ma144': ma144, 'ma180': ma180})


def _hs300_row(dif=0.5, ma25=4000, ma60=3900, ma144=3800, ma180=3700):
    return pd.Series({'dif': dif, 'ma25': ma25, 'ma60': ma60,
                      'ma144': ma144, 'ma180': ma180})


def test_regime_flags_all_bullish():
    flags = _compute_regime_flags(_stock_row(), _hs300_row(), None)
    assert flags['entry_hs300_dif_above_zero'] is True
    assert flags['entry_hs300_bull_align'] is True
    assert flags['entry_stock_bull_align'] is True
    assert flags['entry_stock_above_ma25'] is True


def test_regime_flags_all_bearish():
    stock = _stock_row(close=5.0, ma25=6.0, ma60=7.0, ma144=8.0, ma180=9.0)
    hs300 = _hs300_row(dif=-0.5, ma25=3700, ma60=3800, ma144=3900, ma180=4000)
    flags = _compute_regime_flags(stock, hs300, None)
    assert flags['entry_hs300_dif_above_zero'] is False
    assert flags['entry_hs300_bull_align'] is False
    assert flags['entry_stock_bull_align'] is False
    assert flags['entry_stock_above_ma25'] is False


def test_regime_flags_dif_zero_is_false():
    flags = _compute_regime_flags(_stock_row(), _hs300_row(dif=0.0), None)
    assert flags['entry_hs300_dif_above_zero'] is False


def test_regime_flags_missing_long_ma_returns_none():
    stock = _stock_row(ma144=float('nan'))
    hs300 = _hs300_row(ma180=float('nan'))
    flags = _compute_regime_flags(stock, hs300, None)
    assert flags['entry_stock_bull_align'] is None
    assert flags['entry_hs300_bull_align'] is None
    assert flags['entry_stock_above_ma25'] is True
    assert flags['entry_hs300_dif_above_zero'] is True


def test_regime_flags_hs300_row_is_none():
    flags = _compute_regime_flags(_stock_row(), None, None)
    assert flags['entry_hs300_dif_above_zero'] is None
    assert flags['entry_hs300_bull_align'] is None
    assert flags['entry_stock_bull_align'] is True
    assert flags['entry_stock_above_ma25'] is True


def test_enrich_trade_summary_writes_regime_flags(tmp_path):
    """_enrich_trade_summary 应为每笔 trade 写入 4 个 regime 标志。"""
    from backtest import _enrich_trade_summary

    data_dir = tmp_path / 'data'
    (data_dir / 'indicators').mkdir(parents=True)

    stock_df = pd.DataFrame({
        'trade_date': pd.to_datetime(['2024-01-02', '2024-01-03']),
        'close': [10.0, 5.0],
        'ma25': [9.0, 6.0],
        'ma60': [8.0, 7.0],
        'ma144': [7.0, 8.0],
        'ma180': [6.0, 9.0],
        'kdj_j': [50.0, 30.0],
        'circ_mv': [100.0, 100.0],
        'week_kdj_j': [50.0, 30.0],
        'week_macd_zone': ['区间1', '区间0'],
        'month_macd_zone': ['区间1', '区间0'],
        'macd': [0.5, -0.5], 'dif': [0.6, -0.4], 'dea': [0.4, -0.3],
    })
    stock_df.to_csv(data_dir / 'indicators' / 'TEST.SZ.csv', index=False)

    hs300_df = pd.DataFrame({
        'trade_date': pd.to_datetime(['2024-01-02', '2024-01-03']),
        'close': [4000, 3700],
        'ma25': [4000, 3700], 'ma60': [3900, 3800],
        'ma144': [3800, 3900], 'ma180': [3700, 4000],
        'dif': [0.5, -0.3], 'dea': [0.3, -0.1], 'macd': [0.2, -0.2],
    })
    hs300_df.to_csv(data_dir / 'indicators' / '000300.SH.csv', index=False)

    pd.DataFrame({'ts_code': ['TEST.SZ'], 'industry': ['银行']}).to_csv(
        data_dir / 'stock_sector.csv', index=False)

    summary = pd.DataFrame([
        {'ts_code': 'TEST.SZ', 'entry_date': pd.Timestamp('2024-01-02'),
         'return_pct': 5.0, 'status': 'completed'},
        {'ts_code': 'TEST.SZ', 'entry_date': pd.Timestamp('2024-01-03'),
         'return_pct': -3.0, 'status': 'completed'},
    ])

    enriched = _enrich_trade_summary(summary, {'data_dir': str(data_dir)})

    row1 = enriched.iloc[0]
    assert row1['entry_hs300_dif_above_zero'] is True
    assert row1['entry_hs300_bull_align'] is True
    assert row1['entry_stock_bull_align'] is True
    assert row1['entry_stock_above_ma25'] is True

    row2 = enriched.iloc[1]
    assert row2['entry_hs300_dif_above_zero'] is False
    assert row2['entry_hs300_bull_align'] is False
    assert row2['entry_stock_bull_align'] is False
    assert row2['entry_stock_above_ma25'] is False


def test_enrich_trade_summary_hs300_missing_date(tmp_path):
    """entry_date 在股票 indicators 中存在，但不在 HS300 indicators 中：
    HS300 两个 flag 应为 None，stock 两个 flag 仍按股票数据计算。"""
    from backtest import _enrich_trade_summary

    data_dir = tmp_path / 'data'
    (data_dir / 'indicators').mkdir(parents=True)

    # 股票在 2024-01-02 有数据（多头排列）
    stock_df = pd.DataFrame({
        'trade_date': pd.to_datetime(['2024-01-02']),
        'close': [10.0],
        'ma25': [9.0], 'ma60': [8.0], 'ma144': [7.0], 'ma180': [6.0],
        'kdj_j': [50.0], 'circ_mv': [100.0],
        'week_kdj_j': [50.0],
        'week_macd_zone': ['区间1'], 'month_macd_zone': ['区间1'],
        'macd': [0.5], 'dif': [0.6], 'dea': [0.4],
    })
    stock_df.to_csv(data_dir / 'indicators' / 'TEST.SZ.csv', index=False)

    # HS300 仅有 2024-01-05 的数据（与 entry_date 2024-01-02 不重合）
    hs300_df = pd.DataFrame({
        'trade_date': pd.to_datetime(['2024-01-05']),
        'close': [4000],
        'ma25': [4000], 'ma60': [3900], 'ma144': [3800], 'ma180': [3700],
        'dif': [0.5], 'dea': [0.3], 'macd': [0.2],
    })
    hs300_df.to_csv(data_dir / 'indicators' / '000300.SH.csv', index=False)

    pd.DataFrame({'ts_code': ['TEST.SZ'], 'industry': ['银行']}).to_csv(
        data_dir / 'stock_sector.csv', index=False)

    summary = pd.DataFrame([
        {'ts_code': 'TEST.SZ', 'entry_date': pd.Timestamp('2024-01-02'),
         'return_pct': 5.0, 'status': 'completed'},
    ])

    enriched = _enrich_trade_summary(summary, {'data_dir': str(data_dir)})

    row = enriched.iloc[0]
    assert row['entry_hs300_dif_above_zero'] is None
    assert row['entry_hs300_bull_align'] is None
    assert row['entry_stock_bull_align'] is True
    assert row['entry_stock_above_ma25'] is True


def test_regime_flags_sector_bull_align_true():
    import pandas as pd
    from backtest import _compute_regime_flags

    stock_row = pd.Series({'close': 10, 'ma25': 9, 'ma60': 8, 'ma144': 7, 'ma180': 6})
    hs300_row = pd.Series({'dif': 1.0, 'ma25': 4000, 'ma60': 3900, 'ma144': 3800, 'ma180': 3700})
    sector_row = pd.Series({
        'close': 100, 'ma25': 95, 'ma60': 90, 'ma144': 85, 'ma180': 80,
        'dif': 0.5, 'week_macd_zone': '多头', 'month_macd_zone': '震荡',
        'factor_momentum_60d': 0.12,
    })
    f = _compute_regime_flags(stock_row, hs300_row, sector_row)
    assert f['entry_sector_bull_align'] is True
    assert f['entry_sector_above_ma25'] is True
    assert f['entry_sector_dif_above_zero'] is True
    assert f['entry_sector_week_macd_zone'] == '多头'
    assert f['entry_sector_month_macd_zone'] == '震荡'
    assert f['entry_sector_momentum_60d'] == 0.12


def test_regime_flags_sector_bull_align_false():
    import pandas as pd
    from backtest import _compute_regime_flags

    stock_row = pd.Series({'close': 10, 'ma25': 9, 'ma60': 8, 'ma144': 7, 'ma180': 6})
    hs300_row = pd.Series({'dif': 1.0, 'ma25': 4000, 'ma60': 3900, 'ma144': 3800, 'ma180': 3700})
    sector_row = pd.Series({
        'close': 100, 'ma25': 95, 'ma60': 96, 'ma144': 85, 'ma180': 80,  # ma25 < ma60 破坏多头
        'dif': -0.1, 'week_macd_zone': '空头', 'month_macd_zone': '空头',
        'factor_momentum_60d': -0.05,
    })
    f = _compute_regime_flags(stock_row, hs300_row, sector_row)
    assert f['entry_sector_bull_align'] is False
    assert f['entry_sector_dif_above_zero'] is False


def test_regime_flags_sector_none_returns_six_none_values():
    """sector_row=None 时 6 个 entry_sector_* 全为 None/NaN（缺数据三态语义）。"""
    import pandas as pd, math
    from backtest import _compute_regime_flags

    stock_row = pd.Series({'close': 10, 'ma25': 9, 'ma60': 8, 'ma144': 7, 'ma180': 6})
    hs300_row = pd.Series({'dif': 1.0, 'ma25': 4000, 'ma60': 3900, 'ma144': 3800, 'ma180': 3700})
    f = _compute_regime_flags(stock_row, hs300_row, None)
    assert f['entry_sector_bull_align'] is None
    assert f['entry_sector_above_ma25'] is None
    assert f['entry_sector_dif_above_zero'] is None
    assert f['entry_sector_week_macd_zone'] is None
    assert f['entry_sector_month_macd_zone'] is None
    assert math.isnan(f['entry_sector_momentum_60d'])


def test_regime_flags_sector_partial_nan():
    """sector_row.ma180 缺失时 bull_align=None，但其他 flag 不受影响。"""
    import pandas as pd
    from backtest import _compute_regime_flags

    stock_row = pd.Series({'close': 10, 'ma25': 9, 'ma60': 8, 'ma144': 7, 'ma180': 6})
    hs300_row = pd.Series({'dif': 1.0, 'ma25': 4000, 'ma60': 3900, 'ma144': 3800, 'ma180': 3700})
    sector_row = pd.Series({
        'close': 100, 'ma25': 95, 'ma60': 90, 'ma144': 85, 'ma180': float('nan'),
        'dif': 0.5, 'week_macd_zone': '多头', 'month_macd_zone': '震荡',
        'factor_momentum_60d': 0.12,
    })
    f = _compute_regime_flags(stock_row, hs300_row, sector_row)
    assert f['entry_sector_bull_align'] is None
    assert f['entry_sector_above_ma25'] is True
    assert f['entry_sector_dif_above_zero'] is True


def test_regime_flags_existing_phase1_flags_unchanged():
    """Phase 1 的 4 个 flag 在新签名下仍正常工作（回归）。"""
    import pandas as pd
    from backtest import _compute_regime_flags

    stock_row = pd.Series({'close': 10, 'ma25': 9, 'ma60': 8, 'ma144': 7, 'ma180': 6})
    hs300_row = pd.Series({'dif': 1.0, 'ma25': 4000, 'ma60': 3900, 'ma144': 3800, 'ma180': 3700})
    f = _compute_regime_flags(stock_row, hs300_row, None)  # sector=None
    assert f['entry_hs300_dif_above_zero'] is True
    assert f['entry_hs300_bull_align'] is True
    assert f['entry_stock_bull_align'] is True
    assert f['entry_stock_above_ma25'] is True
