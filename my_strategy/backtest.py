import json
import datetime
import pandas as pd
import backtrader as bt
from pathlib import Path
from strategy import StockData, StockCommission, MyStrategy


def load_config(config_path='config.json'):
    with open(config_path, 'r') as f:
        return json.load(f)


def load_feeds(cfg):
    """读取所有股票的指标 CSV，返回 (name, feed) 列表。"""
    stocks = pd.read_csv(cfg['stock_list_path'])['ts_code'].tolist()
    data_dir = Path(cfg['data_dir'])
    start = datetime.datetime.strptime(cfg['backTest_Start_data'], '%Y%m%d')
    end = datetime.datetime.strptime(cfg['backTest_end_data'], '%Y%m%d')

    feeds = []
    for ts_code in stocks:
        path = data_dir / f"{ts_code}_indicators.csv"
        if not path.exists():
            print(f"SKIP {ts_code}: 指标文件不存在，请先运行 calc_indicators.py")
            continue
        df = pd.read_csv(path, parse_dates=['trade_date'])
        df = df.sort_values('trade_date').reset_index(drop=True)
        df.index = df['trade_date']
        feed = StockData(dataname=df, fromdate=start, todate=end)
        feeds.append((ts_code, feed))
    return feeds


def setup_cerebro(cfg, feeds):
    cerebro = bt.Cerebro()

    for name, feed in feeds:
        cerebro.adddata(feed, name=name)

    cerebro.broker.set_cash(cfg['initial_cash'])
    cerebro.broker.set_coc(True)  # 14:50尾盘操作，以当日收盘价成交

    comm = StockCommission(
        commission=cfg['commission_rate'],
        stamp_duty=cfg['stamp_duty'],
    )
    cerebro.broker.addcommissioninfo(comm)

    cerebro.broker.set_slippage_perc(perc=0.0001)

    cerebro.addstrategy(
        MyStrategy,
        initial_cash=cfg['initial_cash'],
        max_positions=cfg['max_positions'],
        take_profit_1_pct=cfg['take_profit_1_pct'],
        take_profit_2_pct=cfg['take_profit_2_pct'],
        dea_lookback_days=cfg['dea_lookback_days'],
    )

    cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name='_AnnualReturn')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='_DrawDown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='_Returns', tann=252)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio_A, _name='_SharpeRatio_A')
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='_TimeReturn')

    return cerebro


def _print_trade_stats(df):
    completed = df[df['status'] == 'completed'].copy() if 'status' in df.columns else pd.DataFrame()
    print("\n========== 交易统计 ==========")
    total = len(df)
    n_completed = len(completed)
    print(f"总交易笔数：{total}（已完成 {n_completed}，未平仓 {total - n_completed}）")
    if completed.empty:
        print("无已完成交易")
        print("==============================\n")
        return
    winners = completed[completed['return_pct'] > 0]
    losers = completed[completed['return_pct'] <= 0]
    win_rate = len(winners) / len(completed) * 100
    avg_ret = completed['return_pct'].mean()
    avg_win = winners['return_pct'].mean() if not winners.empty else 0.0
    avg_loss = losers['return_pct'].mean() if not losers.empty else 0.0
    payoff = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
    total_profit = winners['gross_pnl'].sum() if not winners.empty else 0.0
    total_loss = abs(losers['gross_pnl'].sum()) if not losers.empty else 0.0
    profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
    print(f"\n--- 交易质量 ---")
    print(f"胜率：{win_rate:.1f}%（{len(winners)} 盈 / {len(losers)} 亏）")
    print(f"平均收益率：{avg_ret:.2f}%（盈利 {avg_win:.2f}% / 亏损 {avg_loss:.2f}%）")
    print(f"盈亏比：{payoff:.2f}")
    print(f"利润因子：{profit_factor:.2f}")
    print(f"最大单笔盈利：{completed['return_pct'].max():.2f}%")
    print(f"最大单笔亏损：{completed['return_pct'].min():.2f}%")
    print(f"\n--- 时间维度 ---")
    avg_hold = completed['holding_days'].mean()
    avg_hold_win = winners['holding_days'].mean() if not winners.empty else 0.0
    avg_hold_loss = losers['holding_days'].mean() if not losers.empty else 0.0
    print(f"平均持仓天数：{avg_hold:.1f}（盈利 {avg_hold_win:.1f} / 亏损 {avg_hold_loss:.1f}）")
    print(f"最长持仓：{int(completed['holding_days'].max())} 天，最短持仓：{int(completed['holding_days'].min())} 天")
    entry_dates = pd.to_datetime(completed['entry_date'])
    n_months = entry_dates.dt.to_period('M').nunique()
    freq = len(completed) / n_months if n_months > 0 else 0.0
    print(f"每月平均交易频次：{freq:.1f} 笔")
    print(f"\n--- 策略信号分析 ---")
    for reason in ['MA60止损', 'MA25清仓']:
        subset = completed[completed['exit_reason'] == reason]
        if subset.empty:
            continue
        pct = len(subset) / len(completed) * 100
        w = len(subset[subset['return_pct'] > 0])
        l = len(subset[subset['return_pct'] <= 0])
        print(f"{reason}：{pct:.1f}%（盈利 {w} 笔 / 亏损 {l} 笔）")
    print("==============================\n")


def print_results(result, cfg):
    r = result[0]
    annual_ret = r.analyzers._Returns.get_analysis().get('rnorm100', 'N/A')
    max_dd = r.analyzers._DrawDown.get_analysis()['max']['drawdown']
    sharpe = r.analyzers._SharpeRatio_A.get_analysis().get('sharperatio', 'N/A')

    print("\n========== 回测结果 ==========")
    print(f"年化收益率：{annual_ret:.2f}%" if isinstance(annual_ret, float) else f"年化收益率：{annual_ret}")
    print(f"最大回撤：{max_dd:.2f}%")
    print(f"年化夏普比率：{sharpe:.3f}" if isinstance(sharpe, float) else f"年化夏普比率：{sharpe}")
    print("==============================\n")

    results_dir = Path(cfg['results_dir'])
    results_dir.mkdir(exist_ok=True)

    trade_df = pd.DataFrame(r.order_log)
    if not trade_df.empty:
        trade_df.to_csv(results_dir / 'trade_list.csv', index=False)
        print(f"交易记录已保存到 {results_dir / 'trade_list.csv'}")

    summary_df = pd.DataFrame(r.trade_log)
    if not summary_df.empty:
        summary_df.to_csv(results_dir / 'trade_summary.csv', index=False)
        print(f"完整交易汇总已保存到 {results_dir / 'trade_summary.csv'}")
    _print_trade_stats(summary_df if not summary_df.empty else pd.DataFrame())

    time_return = pd.Series(r.analyzers._TimeReturn.get_analysis())
    equity = (1 + time_return).cumprod()
    equity.plot(title='Equity Curve').get_figure().savefig(
        results_dir / 'equity_curve.png', dpi=150
    )
    print(f"资金曲线已保存到 {results_dir / 'equity_curve.png'}")


def main():
    cfg = load_config()
    feeds = load_feeds(cfg)
    if not feeds:
        print("没有可用的数据文件，请先运行 downloader.py 和 calc_indicators.py")
        return

    cerebro = setup_cerebro(cfg, feeds)
    print(f"初始资金：{cfg['initial_cash']:,.0f}")
    print(f"加载股票数：{len(feeds)}")
    print("开始回测...")

    result = cerebro.run()
    print_results(result, cfg)


if __name__ == '__main__':
    main()
