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
    """读取所有股票的指标 CSV，过滤数据不完整的股票，返回 (name, feed) 列表。

    过滤条件：
    1. 指标文件存在
    2. 回测开始前已有数据（上市时间早于回测开始，MA60 有足够预热数据）
    3. 回测窗口内 K 线数 >= min_bars（过滤中途退市的股票）
    """
    stocks = pd.read_csv(cfg['stock_list_path'])['ts_code'].tolist()
    data_dir = Path(cfg['data_dir'])
    start = datetime.datetime.strptime(cfg['backTest_Start_data'], '%Y%m%d')
    end = datetime.datetime.strptime(cfg['backTest_end_data'], '%Y%m%d')
    # 回测窗口按 252 交易日/年估算，要求覆盖 80% 以上
    total_days = (end - start).days
    min_bars = int(total_days / 365 * 252 * 0.8)

    skip_no_file, skip_late_listed, skip_insufficient = [], [], []
    feeds = []
    for ts_code in stocks:
        path = data_dir / f"{ts_code}_indicators.csv"
        if not path.exists():
            skip_no_file.append(ts_code)
            continue
        df = pd.read_csv(path, parse_dates=['trade_date'])
        df = df.sort_values('trade_date').reset_index(drop=True)
        df.index = df['trade_date']

        # 条件 2：回测开始前必须有数据（上市早于回测开始）
        if df.index.min() >= start:
            skip_late_listed.append(ts_code)
            continue

        # 条件 3：回测窗口内 K 线数足够
        in_window = (df.index >= start) & (df.index <= end)
        if in_window.sum() < min_bars:
            skip_insufficient.append(ts_code)
            continue

        feed = StockData(dataname=df, fromdate=start, todate=end)
        feeds.append((ts_code, feed))

    if skip_no_file:
        print(f"SKIP {len(skip_no_file)} 支：指标文件不存在 → {skip_no_file}")
    if skip_late_listed:
        print(f"SKIP {len(skip_late_listed)} 支：回测期内才上市 → {skip_late_listed}")
    if skip_insufficient:
        print(f"SKIP {len(skip_insufficient)} 支：回测窗口内 K 线数 < {min_bars} → {skip_insufficient}")
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


def _classify_ma_alignment(row):
    """根据进场当日 MA25/MA60/MA144/MA180 判断排列状态。"""
    ma25 = row.get('ma25')
    ma60 = row.get('ma60')
    ma144 = row.get('ma144')
    ma180 = row.get('ma180')

    has_long = pd.notna(ma144) and pd.notna(ma180)
    if has_long:
        if ma25 > ma60 > ma144 > ma180:
            return '全多头'
        if ma25 < ma60 < ma144 < ma180:
            return '全空头'
    if pd.notna(ma25) and pd.notna(ma60):
        if ma25 > ma60:
            return '局部多头'
        if ma25 < ma60:
            return '局部空头'
    return '混合'


def _classify_macd_zone(row):
    """根据进场当日 MACD/DIF/DEA 判断 MACD 区间。"""
    macd = row.get('macd')
    dif = row.get('dif')
    dea = row.get('dea')
    if pd.isna(macd) or macd <= 0:
        return '区间0'
    if macd > dif and macd > dea:
        return '区间1'
    if dif > macd and dea > macd:
        return '区间3'
    return '区间2'


def _enrich_trade_summary(summary_df, cfg):
    """回测后富化 trade_summary，按 (ts_code, entry_date) join 指标文件，
    新增 entry_kdj_j / entry_ma60_dist_pct / industry / ma_alignment / macd_zone 列。
    返回富化后的 DataFrame。
    """
    if summary_df.empty:
        return summary_df

    data_dir = Path(cfg['data_dir'])

    # 加载行业映射
    sector_path = data_dir / 'stock_sector.csv'
    if sector_path.exists():
        sector_df = pd.read_csv(sector_path)
        sector_map = dict(zip(sector_df['ts_code'], sector_df['industry']))
    else:
        sector_map = {}

    # 按股票分组，批量 join 指标
    enriched_rows = []
    for ts_code, group in summary_df.groupby('ts_code'):
        ind_path = data_dir / f"{ts_code}_indicators.csv"
        if not ind_path.exists():
            for _, row in group.iterrows():
                row = row.copy()
                row['entry_kdj_j'] = None
                row['entry_ma60_dist_pct'] = None
                row['industry'] = sector_map.get(ts_code)
                row['ma_alignment'] = None
                row['macd_zone'] = None
                enriched_rows.append(row)
            continue

        ind_df = pd.read_csv(ind_path, parse_dates=['trade_date'])
        ind_df = ind_df.set_index('trade_date')

        for _, row in group.iterrows():
            row = row.copy()
            entry_date = pd.Timestamp(row['entry_date'])
            row['industry'] = sector_map.get(ts_code)

            if entry_date in ind_df.index:
                r = ind_df.loc[entry_date]
                if isinstance(r, pd.DataFrame):
                    r = r.iloc[0]
                kdj_j = r.get('kdj_j') if 'kdj_j' in ind_df.columns else None
                ma60 = r.get('ma60')
                close = r.get('close')
                try:
                    row['entry_kdj_j'] = round(float(kdj_j), 2) if pd.notna(kdj_j) else None
                except (ValueError, TypeError):
                    row['entry_kdj_j'] = None
                row['entry_ma60_dist_pct'] = (
                    round((close - ma60) / ma60 * 100, 2)
                    if pd.notna(ma60) and ma60 > 0 and pd.notna(close)
                    else None
                )
                row['ma_alignment'] = _classify_ma_alignment(r)
                row['macd_zone'] = _classify_macd_zone(r)
            else:
                row['entry_kdj_j'] = None
                row['entry_ma60_dist_pct'] = None
                row['ma_alignment'] = None
                row['macd_zone'] = None

            enriched_rows.append(row)

    return pd.DataFrame(enriched_rows).reset_index(drop=True)


def _compute_benchmarks_returns(cfg):
    """从 data_dir 加载多个基准指数 CSV。

    配置优先级：benchmark_codes (list) > benchmark_code (str, 兼容旧配置)。
    返回 list[dict]，每项含 code / annual {year: pct} / annualized pct。
    找不到文件的 code 直接跳过。
    """
    codes = cfg.get('benchmark_codes') or []
    if not codes and cfg.get('benchmark_code'):
        codes = [cfg['benchmark_code']]
    if not codes:
        return []

    start = datetime.datetime.strptime(cfg['backTest_Start_data'], '%Y%m%d')
    end = datetime.datetime.strptime(cfg['backTest_end_data'], '%Y%m%d')
    results = []
    for code in codes:
        # 指数只需要收盘价，直接读原始日线文件，不依赖 _indicators.csv
        path = Path(cfg['data_dir']) / f"{code}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path, parse_dates=['trade_date'])
        df = df.sort_values('trade_date')
        df = df[(df['trade_date'] >= start) & (df['trade_date'] <= end)].reset_index(drop=True)
        if len(df) < 2:
            continue
        df['year'] = df['trade_date'].dt.year
        annual = {
            int(y): (grp['close'].iloc[-1] / grp['close'].iloc[0] - 1) * 100
            for y, grp in df.groupby('year')
        }
        years_span = (df['trade_date'].iloc[-1] - df['trade_date'].iloc[0]).days / 365
        annualized = ((df['close'].iloc[-1] / df['close'].iloc[0]) ** (1 / years_span) - 1) * 100
        results.append({'code': code, 'annual': annual, 'annualized': round(annualized, 2)})
    return results


def _print_entry_quality_stats(df):
    """打印进场质量聚合统计（只统计 completed 交易）。"""
    completed = df[df['status'] == 'completed'].copy() if 'status' in df.columns else pd.DataFrame()
    if completed.empty:
        return

    def _group_stats(group_col):
        grp = completed.groupby(group_col).agg(
            笔数=('return_pct', 'count'),
            胜率=('return_pct', lambda x: (x > 0).mean() * 100),
            平均收益=('return_pct', 'mean'),
        ).reset_index()
        return grp

    print("\n========== 进场质量分析 ==========")

    # MA 排列
    if 'ma_alignment' in completed.columns and completed['ma_alignment'].notna().any():
        print("\n--- MA 排列状态 ---")
        grp = _group_stats('ma_alignment')
        print(f"{'MA排列':<10}{'笔数':>6}{'胜率':>8}{'平均收益':>10}")
        print("-" * 36)
        for _, row in grp.iterrows():
            print(f"{str(row['ma_alignment']):<10}{int(row['笔数']):>6}"
                  f"{row['胜率']:>7.1f}%{row['平均收益']:>+9.2f}%")

    # MACD 区间
    if 'macd_zone' in completed.columns and completed['macd_zone'].notna().any():
        print("\n--- MACD 区间 ---")
        grp = _group_stats('macd_zone')
        print(f"{'MACD区间':<10}{'笔数':>6}{'胜率':>8}{'平均收益':>10}")
        print("-" * 36)
        for _, row in grp.sort_values('macd_zone').iterrows():
            print(f"{str(row['macd_zone']):<10}{int(row['笔数']):>6}"
                  f"{row['胜率']:>7.1f}%{row['平均收益']:>+9.2f}%")

    # KDJ_J 分桶
    if 'entry_kdj_j' in completed.columns and completed['entry_kdj_j'].notna().any():
        print("\n--- KDJ_J 分桶 ---")
        bins = [-float('inf'), 20, 50, 80, float('inf')]
        labels = ['<20', '20-50', '50-80', '>80']
        completed['_kdj_bucket'] = pd.cut(completed['entry_kdj_j'], bins=bins, labels=labels)
        grp = _group_stats('_kdj_bucket')
        print(f"{'KDJ_J区间':<12}{'笔数':>6}{'胜率':>8}{'平均收益':>10}")
        print("-" * 38)
        for _, row in grp.iterrows():
            print(f"{str(row['_kdj_bucket']):<12}{int(row['笔数']):>6}"
                  f"{row['胜率']:>7.1f}%{row['平均收益']:>+9.2f}%")
        completed.drop(columns=['_kdj_bucket'], inplace=True)

    # MA60 距离分桶
    if 'entry_ma60_dist_pct' in completed.columns and completed['entry_ma60_dist_pct'].notna().any():
        print("\n--- 进场距 MA60 距离 ---")
        bins = [0, 1, 3, 5, float('inf')]
        labels = ['≤1%', '1-3%', '3-5%', '>5%']
        completed['_dist_bucket'] = pd.cut(
            completed['entry_ma60_dist_pct'].clip(lower=0), bins=bins, labels=labels
        )
        grp = _group_stats('_dist_bucket')
        print(f"{'距MA60':>10}{'笔数':>6}{'胜率':>8}{'平均收益':>10}")
        print("-" * 36)
        for _, row in grp.iterrows():
            print(f"{str(row['_dist_bucket']):>10}{int(row['笔数']):>6}"
                  f"{row['胜率']:>7.1f}%{row['平均收益']:>+9.2f}%")
        completed.drop(columns=['_dist_bucket'], inplace=True)

    # 行业 Top 10
    if 'industry' in completed.columns and completed['industry'].notna().any():
        print("\n--- 按行业汇总（总盈亏 Top 10）---")
        grp = completed.groupby('industry').agg(
            笔数=('return_pct', 'count'),
            胜率=('return_pct', lambda x: (x > 0).mean() * 100),
            总盈亏=('gross_pnl', 'sum'),
            平均收益=('return_pct', 'mean'),
        ).reset_index()
        top10 = grp.nlargest(10, '总盈亏')
        print(f"{'行业':<12}{'笔数':>5}{'胜率':>8}{'总盈亏':>14}{'平均收益':>10}")
        print("-" * 51)
        for _, row in top10.iterrows():
            print(f"{str(row['industry']):<12}{int(row['笔数']):>5}"
                  f"{row['胜率']:>7.1f}%{row['总盈亏']:>14,.0f}{row['平均收益']:>+9.2f}%")

    print("==================================\n")


def _print_trade_stats(df, annual_returns=None, benchmarks=None,
                       position_count_log=None, strategy_annualized=None):
    """benchmarks: list[dict]，每项含 code / annual {year: pct} / annualized pct。"""
    completed = df[df['status'] == 'completed'].copy() if 'status' in df.columns else pd.DataFrame()
    print("\n========== 交易统计 ==========")
    total = len(df)
    n_completed = len(completed)
    print(f"总交易笔数：{total}（已完成 {n_completed}，未平仓 {total - n_completed}）")
    if position_count_log:
        import statistics
        pc = position_count_log
        print(f"最大同时持仓：{max(pc)} 只")
        print(f"最小同时持仓：{min(pc)} 只")
        print(f"平均同时持仓：{sum(pc)/len(pc):.1f} 只")
        print(f"中位数持仓：{statistics.median(pc):.1f} 只")
    if completed.empty:
        print("无已完成交易")
        print("==============================\n")
        return

    # 年度收益对比
    if annual_returns is not None and len(annual_returns) > 0:
        print(f"\n--- 年度收益 ---")
        years = sorted(annual_returns.keys())
        if benchmarks:
            # 动态构建表头：策略 + 每个基准的收益/超额两列
            header = f"{'年份':<6}  {'策略':>8}"
            for bm in benchmarks:
                short = bm['code'].split('.')[0]
                header += f"  {short:>8}  {'超额':>7}"
            print(header)
            print("-" * (6 + 2 + 8 + len(benchmarks) * (2 + 8 + 2 + 7)))
            for y in years:
                s = annual_returns[y] * 100
                row = f"{y:<6}  {s:>+7.2f}%"
                for bm in benchmarks:
                    b = bm['annual'].get(y)
                    if b is not None:
                        row += f"  {b:>+7.2f}%  {s - b:>+6.2f}%"
                    else:
                        row += f"  {'N/A':>8}  {'N/A':>7}"
                print(row)
            # 全区间行（年化）
            strat_ann_str = f"{strategy_annualized:>+7.2f}%" if isinstance(strategy_annualized, float) else "  N/A   "
            row = f"{'全区间':<6}  {strat_ann_str}"
            for bm in benchmarks:
                excess = strategy_annualized - bm['annualized'] if isinstance(strategy_annualized, float) else None
                bm_str = f"{bm['annualized']:>+7.2f}%"
                exc_str = f"{excess:>+6.2f}%" if excess is not None else "   N/A "
                row += f"  {bm_str}  {exc_str}"
            print(row)
        else:
            print(f"{'年份':<6}  {'策略收益':>8}")
            print("-" * 20)
            for y in years:
                print(f"{y:<6}  {annual_returns[y] * 100:>+7.2f}%")
            strat_ann_str = f"{strategy_annualized:>+7.2f}%" if isinstance(strategy_annualized, float) else "  N/A   "
            print(f"{'全区间':<6}  {strat_ann_str}")

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
    for reason in ['MA60止损', 'MA25清仓', '止盈1', '止盈2']:
        subset = completed[completed['exit_reason'] == reason]
        if subset.empty:
            continue
        pct = len(subset) / len(completed) * 100
        w = len(subset[subset['return_pct'] > 0])
        l = len(subset[subset['return_pct'] <= 0])
        print(f"{reason}（末次出场）：{pct:.1f}%（盈利 {w} 笔 / 亏损 {l} 笔）")
    if 'take_profit_count' in completed.columns:
        tp1 = (completed['take_profit_count'] >= 1).sum()
        tp2 = (completed['take_profit_count'] >= 2).sum()
        print(f"触发止盈1：{tp1} 笔（{tp1 / len(completed) * 100:.1f}%）")
        print(f"触发止盈2：{tp2} 笔（{tp2 / len(completed) * 100:.1f}%）")

    print(f"\n--- 按股票汇总（总盈亏 Top 10）---")
    grp = completed.groupby('ts_code').agg(
        笔数=('return_pct', 'count'),
        盈利笔数=('return_pct', lambda x: (x > 0).sum()),
        总盈亏=('gross_pnl', 'sum'),
        平均收益=('return_pct', 'mean'),
    ).reset_index()
    grp['胜率'] = grp['盈利笔数'] / grp['笔数'] * 100
    top10 = grp.nlargest(10, '总盈亏')
    print(f"{'股票代码':<14}{'笔数':>5}{'胜率':>8}{'总盈亏':>14}{'平均收益':>10}")
    print("-" * 53)
    for _, row in top10.iterrows():
        print(f"{row['ts_code']:<14}{int(row['笔数']):>5}{row['胜率']:>7.1f}%"
              f"{row['总盈亏']:>14,.0f}{row['平均收益']:>+9.2f}%")
    print("==============================\n")


def print_results(result, cfg):
    r = result[0]
    annual_ret = r.analyzers._Returns.get_analysis().get('rnorm100', 'N/A')
    max_dd = r.analyzers._DrawDown.get_analysis()['max']['drawdown']
    sharpe = r.analyzers._SharpeRatio_A.get_analysis().get('sharperatio', 'N/A')
    annual_returns = r.analyzers._AnnualReturn.get_analysis()

    benchmarks = _compute_benchmarks_returns(cfg)

    print("\n========== 回测结果 ==========")
    print(f"年化收益率：{annual_ret:.2f}%" if isinstance(annual_ret, float) else f"年化收益率：{annual_ret}")
    print(f"最大回撤：{max_dd:.2f}%")
    print(f"年化夏普比率：{sharpe:.3f}" if isinstance(sharpe, float) else f"年化夏普比率：{sharpe}")
    if benchmarks:
        parts = [f"{bm['code']} {bm['annualized']:+.2f}%" for bm in benchmarks]
        print(f"基准年化：{' | '.join(parts)}")
    print("==============================\n")

    results_dir = Path(cfg['results_dir'])
    results_dir.mkdir(exist_ok=True)

    trade_df = pd.DataFrame(r.order_log)
    if not trade_df.empty:
        trade_df.to_csv(results_dir / 'trade_list.csv', index=False)
        print(f"交易记录已保存到 {results_dir / 'trade_list.csv'}")

    summary_df = pd.DataFrame(r.trade_log)
    if not summary_df.empty:
        summary_df = _enrich_trade_summary(summary_df, cfg)
        summary_df.to_csv(results_dir / 'trade_summary.csv', index=False)
        print(f"完整交易汇总已保存到 {results_dir / 'trade_summary.csv'}")

    _print_trade_stats(
        summary_df if not summary_df.empty else pd.DataFrame(),
        annual_returns=annual_returns,
        benchmarks=benchmarks,
        position_count_log=getattr(r, 'position_count_log', None),
        strategy_annualized=annual_ret if isinstance(annual_ret, float) else None,
    )
    _print_entry_quality_stats(summary_df if not summary_df.empty else pd.DataFrame())

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
