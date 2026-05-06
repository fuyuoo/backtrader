#!/usr/bin/env python
"""Test script to verify run_index_strategy implementation."""

import sys
sys.path.insert(0, '.')

import backtrader as bt
import pandas as pd
from datetime import datetime
from my_strategy.strategy import StockData, StockCommission, MyStrategy
from my_strategy.calc_indicators import compute_indicators

# Simulate minimal index data
dates = pd.date_range('2020-01-01', periods=100)
data = {
    'trade_date': dates,
    'open': [100 + i*0.1 for i in range(100)],
    'high': [101 + i*0.1 for i in range(100)],
    'low': [99 + i*0.1 for i in range(100)],
    'close': [100.5 + i*0.1 for i in range(100)],
    'volume': [1000000] * 100,
}
df = pd.DataFrame(data)
df = compute_indicators(df)

feed = StockData(dataname=df, fromdate=dates[0], todate=dates[-1])

cerebro = bt.Cerebro()
cerebro.adddata(feed, name='000300.SH')
cerebro.broker.set_cash(100_000_000)
cerebro.addanalyzer(bt.analyzers.Returns, _name='_Returns', tann=252)
cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='_TimeReturn')

cerebro.addstrategy(
    MyStrategy,
    initial_cash=100_000_000,
    max_positions=1,
    take_profit_1_pct=0.05,
    take_profit_2_pct=0.10,
    dea_lookback_days=5,
)

result = cerebro.run()
if result:
    r = result[0]

    # Test Returns analyzer
    analysis = r.analyzers._Returns.get_analysis()
    print(f"Returns analysis type: {type(analysis)}")
    print(f"Returns analysis: {analysis}")
    annual_return = analysis.get('rnorm100', 0.0)
    print(f"annual_return: {annual_return}, type: {type(annual_return)}")

    # Test TimeReturn analyzer
    tr = r.analyzers._TimeReturn.get_analysis()
    print(f"\nTimeReturn analysis type: {type(tr)}")
    print(f"TimeReturn analysis: {tr}")
    time_return_series = pd.Series(tr)
    print(f"Series empty: {time_return_series.empty}")
    print(f"Series: {time_return_series}")

    # Test trade_log
    print(f"\ntrade_log type: {type(r.trade_log)}")
    print(f"trade_log content: {r.trade_log}")
    trade_df = pd.DataFrame(r.trade_log)
    print(f"DataFrame empty: {trade_df.empty}")
    if not trade_df.empty:
        print(f"Columns: {trade_df.columns.tolist()}")
        completed = trade_df[trade_df['status'] == 'completed']
        print(f"Completed trades: {len(completed)}")
        if not completed.empty:
            print(f"return_pct type: {type(completed['return_pct'].iloc[0])}")
else:
    print("No results")
