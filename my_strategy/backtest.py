import json
import sys
import datetime
import statistics
from pathlib import Path

# 确保项目根在 sys.path，attribution_runner 内部 `from my_strategy.tools import ...` 才能解析
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd
import backtrader as bt
from src.strategy import StockData, StockCommission, MyStrategy
from src.calc_indicators import compute_all_indicators


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
    benchmark_codes = set(cfg.get('benchmark_codes') or [])
    if cfg.get('benchmark_code'):
        benchmark_codes.add(cfg['benchmark_code'])
    stocks = [ts for ts in pd.read_csv(cfg['stock_list_path'])['ts_code'].tolist()
              if ts not in benchmark_codes]
    data_dir = Path(cfg['data_dir'])
    start = datetime.datetime.strptime(cfg['backTest_Start_data'], '%Y%m%d')
    end = datetime.datetime.strptime(cfg['backTest_end_data'], '%Y%m%d')
    # 回测窗口按 252 交易日/年估算，要求覆盖 80% 以上
    total_days = (end - start).days
    min_bars = int(total_days / 365 * 252 * 0.8)

    skip_no_file, skip_late_listed, skip_insufficient = [], [], []
    feeds = []
    for ts_code in stocks:
        path = data_dir / 'indicators' / f"{ts_code}.csv"
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
        print(f"SKIP {len(skip_no_file)} 支：指标文件不存在")
    if skip_late_listed:
        print(f"SKIP {len(skip_late_listed)} 支：回测期内才上市")
    if skip_insufficient:
        print(f"SKIP {len(skip_insufficient)} 支：回测窗口内 K 线数 < {min_bars} → {skip_insufficient}")
    return feeds


class _ProgressAnalyzer(bt.Analyzer):
    params = (('total_bars', 0),)

    def start(self):
        self._bar = 0
        self._last_reported_pct = -1

    def next(self):
        self._bar += 1
        if self.p.total_bars <= 0:
            return
        pct = self._bar * 100 // self.p.total_bars
        step = pct // 10
        if step > self._last_reported_pct // 10:
            self._last_reported_pct = pct
            print(f"  回测进度：{pct}%（第 {self._bar} / {self.p.total_bars} 交易日）", flush=True)


def setup_cerebro(cfg, feeds, sector_map=None):
    cerebro = bt.Cerebro()
    start = datetime.datetime.strptime(cfg['backTest_Start_data'], '%Y%m%d')
    end = datetime.datetime.strptime(cfg['backTest_end_data'], '%Y%m%d')
    total_bars = int((end - start).days / 365 * 252)
    cerebro.addanalyzer(_ProgressAnalyzer, total_bars=total_bars)

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
        atr_period=cfg.get('atr_period', 20),
        atr_multiplier=cfg.get('atr_multiplier', 1.5),
        take_profit_min_pct=cfg.get('take_profit_min_pct', 0.03),
        take_profit_max_pct=cfg.get('take_profit_max_pct', 0.12),
        sector_map=sector_map,
    )

    cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name='_AnnualReturn')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='_DrawDown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='_Returns', tann=252)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio_A, _name='_SharpeRatio_A')
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='_TimeReturn')

    return cerebro


def _compute_regime_flags(stock_row, hs300_row, sector_row):
    """计算入场时刻 4+6 = 10 个环境标志。

    sector_row=None 时 6 个 entry_sector_* 为 None（数值列为 NaN）。
    """
    def _bull_align(row):
        if row is None:
            return None
        m25, m60, m144, m180 = row.get('ma25'), row.get('ma60'), row.get('ma144'), row.get('ma180')
        if pd.isna(m25) or pd.isna(m60) or pd.isna(m144) or pd.isna(m180):
            return None
        return bool(m25 > m60 > m144 > m180)

    # ===== Phase 1（保持不变）=====
    s_close = stock_row.get('close')
    s_ma25 = stock_row.get('ma25')
    if pd.isna(s_close) or pd.isna(s_ma25):
        stock_above_ma25 = None
    else:
        stock_above_ma25 = bool(s_close > s_ma25)

    if hs300_row is None:
        hs300_dif_above = None
    else:
        dif = hs300_row.get('dif')
        hs300_dif_above = None if pd.isna(dif) else bool(dif > 0)

    # ===== Phase 2 新增 =====
    if sector_row is None:
        sector_above_ma25 = None
        sector_dif_above = None
        sector_week_zone = None
        sector_month_zone = None
        sector_momentum = float('nan')
    else:
        s2_close = sector_row.get('close')
        s2_ma25 = sector_row.get('ma25')
        if pd.isna(s2_close) or pd.isna(s2_ma25):
            sector_above_ma25 = None
        else:
            sector_above_ma25 = bool(s2_close > s2_ma25)

        s2_dif = sector_row.get('dif')
        sector_dif_above = None if pd.isna(s2_dif) else bool(s2_dif > 0)

        wz = sector_row.get('week_macd_zone')
        sector_week_zone = None if (wz is None or (isinstance(wz, float) and pd.isna(wz))) else str(wz)
        mz = sector_row.get('month_macd_zone')
        sector_month_zone = None if (mz is None or (isinstance(mz, float) and pd.isna(mz))) else str(mz)

        mom = sector_row.get('factor_momentum_60d')
        sector_momentum = float(mom) if not pd.isna(mom) else float('nan')

    return {
        'entry_hs300_dif_above_zero': hs300_dif_above,
        'entry_hs300_bull_align': _bull_align(hs300_row),
        'entry_stock_bull_align': _bull_align(stock_row),
        'entry_stock_above_ma25': stock_above_ma25,
        'entry_sector_bull_align': _bull_align(sector_row),
        'entry_sector_above_ma25': sector_above_ma25,
        'entry_sector_dif_above_zero': sector_dif_above,
        'entry_sector_week_macd_zone': sector_week_zone,
        'entry_sector_month_macd_zone': sector_month_zone,
        'entry_sector_momentum_60d': sector_momentum,
    }


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


def _load_sector_indicators(cfg, data_dir):
    """加载 31 个 SW 一级行业 indicators，返回 dict[sw_code -> DataFrame]."""
    sw_codes = cfg.get('sw_index_codes')
    if not sw_codes:
        return {}
    sw_indicators_dir = data_dir / 'sw_indicators'
    out = {}
    for sw_code in sw_codes:
        path = sw_indicators_dir / f"{sw_code}.csv"
        if path.exists():
            df = pd.read_csv(path, parse_dates=['trade_date'])
            out[sw_code] = df.set_index('trade_date')
        else:
            print(f"  [warn] sector indicator 缺失：{path}")
    return out


def _load_sw_sector_map(cfg, data_dir):
    """加载 ts_code -> sw_index_code 映射，缺文件返回空 dict（soft fail）。"""
    data_paths = cfg.get('data_paths')
    if not data_paths or 'stock_sector_csv' not in data_paths:
        return {}
    sec_csv = data_dir / Path(data_paths['stock_sector_csv']).name
    if not sec_csv.exists():
        print(f"  [warn] stock_sector.csv 缺失：{sec_csv}")
        return {}
    df = pd.read_csv(sec_csv)
    if 'sw_index_code' not in df.columns:
        print(f"  [warn] {sec_csv} 缺 sw_index_code 列")
        return {}
    df = df.dropna(subset=['sw_index_code'])
    return dict(zip(df['ts_code'], df['sw_index_code']))


def _enrich_trade_summary(summary_df, cfg):
    """回测后富化 trade_summary，按 (ts_code, entry_date) join 指标文件，
    新增 entry_kdj_j / entry_ma60_dist_pct / industry / ma_alignment / macd_zone 列。
    返回富化后的 DataFrame。
    """
    if summary_df.empty:
        return summary_df

    data_dir = Path(cfg['data_dir'])

    # 加载 HS300 indicators（用于入场环境标志）— 硬失败，不静默降级
    hs300_path = data_dir / 'indicators' / '000300.SH.csv'
    if not hs300_path.exists():
        raise FileNotFoundError(
            f"HS300 indicators not found at {hs300_path}. "
            f"Run src/calc_indicators.py for 000300.SH first.")
    hs300_df = pd.read_csv(hs300_path, parse_dates=['trade_date'])
    hs300_df = hs300_df.set_index('trade_date')

    sector_indicators = _load_sector_indicators(cfg, data_dir)
    sw_sector_map = _load_sw_sector_map(cfg, data_dir)

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
        ind_path = data_dir / 'indicators' / f"{ts_code}.csv"
        if not ind_path.exists():
            for _, row in group.iterrows():
                row = row.copy()
                row['entry_kdj_j'] = None
                row['entry_ma60_dist_pct'] = None
                row['industry'] = sector_map.get(ts_code)
                row['ma_alignment'] = None
                row['macd_zone'] = None
                row['entry_circ_mv'] = None
                row['entry_week_kdj_j'] = None
                row['entry_week_macd_zone'] = None
                row['entry_month_macd_zone'] = None
                row['entry_hs300_dif_above_zero'] = None
                row['entry_hs300_bull_align'] = None
                row['entry_stock_bull_align'] = None
                row['entry_stock_above_ma25'] = None
                row['entry_sector_bull_align'] = None
                row['entry_sector_above_ma25'] = None
                row['entry_sector_dif_above_zero'] = None
                row['entry_sector_week_macd_zone'] = None
                row['entry_sector_month_macd_zone'] = None
                row['entry_sector_momentum_60d'] = float('nan')
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
                circ_mv_val = r.get('circ_mv') if 'circ_mv' in ind_df.columns else None
                try:
                    row['entry_circ_mv'] = round(float(circ_mv_val), 2) if pd.notna(circ_mv_val) else None
                except (ValueError, TypeError):
                    row['entry_circ_mv'] = None
                week_kdj_j_val = r.get('week_kdj_j') if 'week_kdj_j' in ind_df.columns else None
                try:
                    row['entry_week_kdj_j'] = round(float(week_kdj_j_val), 2) if pd.notna(week_kdj_j_val) else None
                except (ValueError, TypeError):
                    row['entry_week_kdj_j'] = None
                row['entry_week_macd_zone'] = (
                    r.get('week_macd_zone')
                    if 'week_macd_zone' in ind_df.columns and pd.notna(r.get('week_macd_zone'))
                    else None
                )
                row['entry_month_macd_zone'] = (
                    r.get('month_macd_zone')
                    if 'month_macd_zone' in ind_df.columns and pd.notna(r.get('month_macd_zone'))
                    else None
                )
                hs300_row = hs300_df.loc[entry_date] if entry_date in hs300_df.index else None
                if isinstance(hs300_row, pd.DataFrame):
                    hs300_row = hs300_row.iloc[0]
                # Look up sector_row for this stock on entry_date
                sw_code = sw_sector_map.get(ts_code)
                sector_row = None
                if sw_code and sw_code in sector_indicators:
                    sec_df = sector_indicators[sw_code]
                    if entry_date in sec_df.index:
                        sector_row = sec_df.loc[entry_date]
                        if isinstance(sector_row, pd.DataFrame):
                            sector_row = sector_row.iloc[0]

                flags = _compute_regime_flags(r, hs300_row, sector_row)
                row['entry_hs300_dif_above_zero'] = flags['entry_hs300_dif_above_zero']
                row['entry_hs300_bull_align'] = flags['entry_hs300_bull_align']
                row['entry_stock_bull_align'] = flags['entry_stock_bull_align']
                row['entry_stock_above_ma25'] = flags['entry_stock_above_ma25']
                row['entry_sector_bull_align'] = flags['entry_sector_bull_align']
                row['entry_sector_above_ma25'] = flags['entry_sector_above_ma25']
                row['entry_sector_dif_above_zero'] = flags['entry_sector_dif_above_zero']
                row['entry_sector_week_macd_zone'] = flags['entry_sector_week_macd_zone']
                row['entry_sector_month_macd_zone'] = flags['entry_sector_month_macd_zone']
                row['entry_sector_momentum_60d'] = flags['entry_sector_momentum_60d']
            else:
                row['entry_kdj_j'] = None
                row['entry_ma60_dist_pct'] = None
                row['ma_alignment'] = None
                row['macd_zone'] = None
                row['entry_circ_mv'] = None
                row['entry_week_kdj_j'] = None
                row['entry_week_macd_zone'] = None
                row['entry_month_macd_zone'] = None
                row['entry_hs300_dif_above_zero'] = None
                row['entry_hs300_bull_align'] = None
                row['entry_stock_bull_align'] = None
                row['entry_stock_above_ma25'] = None
                row['entry_sector_bull_align'] = None
                row['entry_sector_above_ma25'] = None
                row['entry_sector_dif_above_zero'] = None
                row['entry_sector_week_macd_zone'] = None
                row['entry_sector_month_macd_zone'] = None
                row['entry_sector_momentum_60d'] = float('nan')

            enriched_rows.append(row)

    result = pd.DataFrame(enriched_rows).reset_index(drop=True)
    # 这 9 列具有 True/False/None 三态语义，需要 object dtype 保留 Python bool/None；
    # entry_sector_momentum_60d 是 float（NaN 表缺失），不需要此处理。
    for col in ('entry_hs300_dif_above_zero', 'entry_hs300_bull_align',
                'entry_stock_bull_align', 'entry_stock_above_ma25',
                'entry_sector_bull_align', 'entry_sector_above_ma25',
                'entry_sector_dif_above_zero',
                'entry_sector_week_macd_zone', 'entry_sector_month_macd_zone'):
        if col in result.columns:
            result[col] = result[col].astype(object)
    return result


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
        # 指数只需要收盘价，直接读原始日线文件，不依赖 indicators/
        path = Path(cfg['data_dir']) / 'daily' / f"{code}.csv"
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
        trading_days = len(df)
        years_span = trading_days / 252
        annualized = ((df['close'].iloc[-1] / df['close'].iloc[0]) ** (1 / years_span) - 1) * 100
        results.append({'code': code, 'annual': annual, 'annualized': round(annualized, 2)})
    return results


def run_index_strategy(cfg, index_code):
    """对单个指数独立运行策略（max_positions=1，不与股票池竞争）。
    返回 dict: code / annual_return(年化%) / total_return(总%) / win_rate(%) / n_trades。
    """
    path = Path(cfg['data_dir']) / 'daily' / f"{index_code}.csv"
    if not path.exists():
        return None

    df = pd.read_csv(path, parse_dates=['trade_date'])
    df = df.sort_values('trade_date').reset_index(drop=True)
    df = compute_all_indicators(df)
    df.index = df['trade_date']

    start = datetime.datetime.strptime(cfg['backTest_Start_data'], '%Y%m%d')
    end = datetime.datetime.strptime(cfg['backTest_end_data'], '%Y%m%d')

    feed = StockData(dataname=df, fromdate=start, todate=end)

    cerebro = bt.Cerebro()
    cerebro.adddata(feed, name=index_code)
    cerebro.broker.set_cash(cfg['initial_cash'])
    cerebro.broker.set_coc(True)
    comm = StockCommission(
        commission=cfg['commission_rate'],
        stamp_duty=cfg['stamp_duty'],
    )
    cerebro.broker.addcommissioninfo(comm)
    cerebro.broker.set_slippage_perc(perc=0.0001)
    cerebro.addstrategy(
        MyStrategy,
        initial_cash=cfg['initial_cash'],
        max_positions=1,
        take_profit_1_pct=cfg['take_profit_1_pct'],
        take_profit_2_pct=cfg['take_profit_2_pct'],
        dea_lookback_days=cfg['dea_lookback_days'],
        atr_period=cfg.get('atr_period', 20),
        atr_multiplier=cfg.get('atr_multiplier', 1.5),
        take_profit_min_pct=cfg.get('take_profit_min_pct', 0.03),
        take_profit_max_pct=cfg.get('take_profit_max_pct', 0.12),
    )
    cerebro.addanalyzer(bt.analyzers.Returns, _name='_Returns', tann=252)
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='_TimeReturn')

    result = cerebro.run()
    r = result[0]

    annual_return = r.analyzers._Returns.get_analysis().get('rnorm100', 0.0)
    time_return = pd.Series(r.analyzers._TimeReturn.get_analysis())
    total_return = ((1 + time_return).cumprod().iloc[-1] - 1) * 100 if not time_return.empty else 0.0

    trade_df = pd.DataFrame(r.trade_log)
    completed = trade_df[trade_df['status'] == 'completed'] if not trade_df.empty else pd.DataFrame()
    win_rate = (completed['return_pct'] > 0).mean() * 100 if not completed.empty else 0.0
    n_trades = len(completed)

    return {
        'code': index_code,
        'annual_return': round(annual_return, 2) if isinstance(annual_return, float) else 0.0,
        'total_return': round(total_return, 2),
        'win_rate': round(win_rate, 1),
        'n_trades': n_trades,
    }


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
        completed = completed.drop(columns=['_kdj_bucket'])

    # 市值分桶
    if 'entry_circ_mv' in completed.columns and completed['entry_circ_mv'].notna().any():
        print("\n--- 市值分桶（流通市值，亿元）---")
        bins = [0, 50, 100, 300, 500, 1000, float('inf')]
        labels = ['<50亿', '50-100亿', '100-300亿', '300-500亿', '500-1000亿', '>1000亿']
        completed['_mv_bucket'] = pd.cut(completed['entry_circ_mv'], bins=bins, labels=labels, include_lowest=True)
        total_n = completed['_mv_bucket'].notna().sum()
        grp = completed.groupby('_mv_bucket', observed=True).agg(
            笔数=('return_pct', 'count'),
            胜率=('return_pct', lambda x: (x > 0).mean() * 100),
            平均收益=('return_pct', 'mean'),
        ).reset_index()
        print(f"{'市值档位':<14}{'笔数':>6}{'占比':>7}{'胜率':>8}{'平均收益':>10}")
        print("-" * 47)
        for _, row in grp.iterrows():
            n = int(row['笔数'])
            pct = n / total_n * 100
            print(f"{str(row['_mv_bucket']):<14}{n:>6}{pct:>6.1f}%"
                  f"{row['胜率']:>7.1f}%{row['平均收益']:>+9.2f}%")
        completed = completed.drop(columns=['_mv_bucket'])

    # 周 KDJ_J 分桶
    if 'entry_week_kdj_j' in completed.columns and completed['entry_week_kdj_j'].notna().any():
        print("\n--- 周 KDJ_J 分桶 ---")
        bins = [-float('inf'), 20, 50, 80, float('inf')]
        labels = ['<20', '20-50', '50-80', '>80']
        completed['_wkdj_bucket'] = pd.cut(completed['entry_week_kdj_j'], bins=bins, labels=labels)
        grp = _group_stats('_wkdj_bucket')
        print(f"{'周KDJ_J区间':<12}{'笔数':>6}{'胜率':>8}{'平均收益':>10}")
        print("-" * 38)
        for _, row in grp.iterrows():
            print(f"{str(row['_wkdj_bucket']):<12}{int(row['笔数']):>6}"
                  f"{row['胜率']:>7.1f}%{row['平均收益']:>+9.2f}%")
        completed = completed.drop(columns=['_wkdj_bucket'])

    # 周 MACD 区间
    if 'entry_week_macd_zone' in completed.columns and completed['entry_week_macd_zone'].notna().any():
        print("\n--- 周 MACD 区间 ---")
        grp = _group_stats('entry_week_macd_zone')
        print(f"{'周MACD区间':<10}{'笔数':>6}{'胜率':>8}{'平均收益':>10}")
        print("-" * 36)
        for _, row in grp.sort_values('entry_week_macd_zone').iterrows():
            print(f"{str(row['entry_week_macd_zone']):<10}{int(row['笔数']):>6}"
                  f"{row['胜率']:>7.1f}%{row['平均收益']:>+9.2f}%")

    # 月 MACD 区间
    if 'entry_month_macd_zone' in completed.columns and completed['entry_month_macd_zone'].notna().any():
        print("\n--- 月 MACD 区间 ---")
        grp = _group_stats('entry_month_macd_zone')
        print(f"{'月MACD区间':<10}{'笔数':>6}{'胜率':>8}{'平均收益':>10}")
        print("-" * 36)
        for _, row in grp.sort_values('entry_month_macd_zone').iterrows():
            print(f"{str(row['entry_month_macd_zone']):<10}{int(row['笔数']):>6}"
                  f"{row['胜率']:>7.1f}%{row['平均收益']:>+9.2f}%")

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
        completed = completed.drop(columns=['_dist_bucket'])

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
            print("-" * (6 + 2 + 8 + len(benchmarks) * (2 + 9 + 2 + 8)))
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
    for reason in ['MA60止损', 'MA25清仓']:
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
        print(f"至少触发止盈1次：{tp1} 笔（{tp1 / len(completed) * 100:.1f}%）")
        print(f"至少触发止盈2次：{tp2} 笔（{tp2 / len(completed) * 100:.1f}%）")

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

    # 指数策略模拟
    benchmark_codes = cfg.get('benchmark_codes') or []
    if not benchmark_codes and cfg.get('benchmark_code'):
        benchmark_codes = [cfg['benchmark_code']]
    if benchmark_codes:
        print("\n========== 指数策略回测（策略逻辑应用于指数，非买入持有）==========")
        print(f"{'指数':<14}{'年化收益':>10}{'总收益':>10}{'胜率':>8}{'笔数':>6}")
        print("-" * 50)
        for code in benchmark_codes:
            res = run_index_strategy(cfg, code)
            if res is None:
                print(f"{code:<14}  {'数据文件不存在':>30}")
                continue
            print(f"{res['code']:<14}{res['annual_return']:>+9.2f}%"
                  f"{res['total_return']:>+9.2f}%"
                  f"{res['win_rate']:>7.1f}%"
                  f"{res['n_trades']:>6}")
        print("==================================\n")


def backfill_forward_returns(signals, indicators_by_code, horizons=(5, 20, 60)):
    """对 signals_log 列表（list of dict）原地回填 forward_return_{N}d 字段。

    indicators_by_code: dict[ts_code -> DataFrame with trade_date/close cols]
    """
    code_index = {}
    for code, df in indicators_by_code.items():
        d = df.sort_values('trade_date').reset_index(drop=True)
        date_to_pos = {pd.Timestamp(t).date(): i for i, t in enumerate(d['trade_date'])}
        code_index[code] = (d, date_to_pos)

    for sig in signals:
        code = sig['ts_code']
        if code not in code_index:
            continue
        d, idx = code_index[code]
        pos = idx.get(sig['date'])
        if pos is None:
            continue
        base_close = d['close'].iloc[pos]
        if base_close is None or base_close == 0 or pd.isna(base_close):
            continue
        for h in horizons:
            target = pos + h
            if target >= len(d):
                continue
            future_close = d['close'].iloc[target]
            if pd.isna(future_close):
                continue
            sig[f'forward_return_{h}d'] = round(
                (future_close - base_close) / base_close, 6)


_FACTOR_RENAME = {'roe': 'factor_roe', 'pe_ttm': 'factor_pe_ttm',
                  'netprofit_yoy': 'factor_netprofit_yoy'}
_FACTOR_COLS = [
    'factor_momentum_60d', 'factor_ma60_dist', 'factor_macd_strength',
    'factor_roe', 'factor_pe_ttm', 'factor_netprofit_yoy',
    'factor_sector_momentum_60d',
]


def _merge_factors(sig_df, indicators_by_code):
    """将 indicators_by_code 中的因子列向量化合并到 signals DataFrame。

    避免逐行构建 factor_lookup 嵌套字典（300只股 × 3000天 × 14因子会产生大量 Python 对象）。
    """
    pieces = []
    for ts_code, df_ind in indicators_by_code.items():
        sub = df_ind.copy()
        for old, new in _FACTOR_RENAME.items():
            if old in sub.columns and new not in sub.columns:
                sub[new] = sub[old]
        keep = ['trade_date'] + [c for c in _FACTOR_COLS if c in sub.columns]
        sub = sub[keep].copy()
        sub['ts_code'] = ts_code
        pieces.append(sub)
    if not pieces:
        return sig_df
    factor_df = pd.concat(pieces, ignore_index=True)
    factor_df['trade_date'] = pd.to_datetime(factor_df['trade_date']).dt.date
    merged = sig_df.copy()
    merged['_date_key'] = pd.to_datetime(merged['date']).dt.date
    merged = merged.merge(factor_df, left_on=['ts_code', '_date_key'],
                          right_on=['ts_code', 'trade_date'], how='left')
    return merged.drop(columns=['_date_key', 'trade_date'], errors='ignore')


def main():
    cfg = load_config()
    feeds = load_feeds(cfg)
    if not feeds:
        print("没有可用的数据文件，请先运行 downloader.py 和 calc_indicators.py")
        return

    data_dir = Path(cfg['data_dir'])
    stocks = [name for name, _ in feeds]

    # Build sector_map from stock_sector.csv (列名为 industry)
    sector_map = {}
    sector_csv = data_dir / 'stock_sector.csv'
    if sector_csv.exists():
        sec_df = pd.read_csv(sector_csv)
        if 'industry' in sec_df.columns:
            sector_map = dict(zip(sec_df['ts_code'], sec_df['industry']))

    # Build indicators_by_code (factor merge happens post-run, not in strategy hot path)
    indicators_by_code = {}
    for ts_code in stocks:
        ind_path = data_dir / 'indicators' / f"{ts_code}.csv"
        if not ind_path.exists():
            continue
        indicators_by_code[ts_code] = pd.read_csv(ind_path, parse_dates=['trade_date'])

    cerebro = setup_cerebro(cfg, feeds, sector_map=sector_map)
    print(f"初始资金：{cfg['initial_cash']:,.0f}")
    print(f"加载股票数：{len(feeds)}")
    print("开始回测...")

    result = cerebro.run()
    strat = result[0]

    # Backfill forward returns, merge factor columns, write signals_log.csv
    backfill_forward_returns(strat.signals_log, indicators_by_code)
    if strat.signals_log:
        sig_df = pd.DataFrame(strat.signals_log)
        sig_df = _merge_factors(sig_df, indicators_by_code)
        sig_path = Path(cfg.get('signals_log_path', str(data_dir / 'signals_log.csv')))
        sig_path.parent.mkdir(parents=True, exist_ok=True)
        sig_df.to_csv(sig_path, index=False)
        print(f"signals_log: {len(sig_df)} rows written to {sig_path}")

    print_results(result, cfg)

    # 自动触发归因分析（依赖 trade_summary.csv 和 signals_log.csv）
    from tools import attribution_runner
    project_root = Path(__file__).resolve().parent

    r = result[0]
    time_return = pd.Series(r.analyzers._TimeReturn.get_analysis())

    # 加载 benchmark daily returns（来自 data/daily/{code}.csv）
    benchmarks = {}
    benchmark_codes = cfg.get('benchmark_codes') or []
    if not benchmark_codes and cfg.get('benchmark_code'):
        benchmark_codes = [cfg['benchmark_code']]
    for code in benchmark_codes:
        bench_path = project_root / 'data' / 'daily' / f"{code}.csv"
        if not bench_path.exists():
            raise FileNotFoundError(
                f"benchmark daily file missing: {bench_path}. "
                f"Either remove {code} from cfg.benchmark_codes or download the data first."
            )
        df = pd.read_csv(bench_path, parse_dates=['trade_date']).set_index('trade_date').sort_index()
        benchmarks[code] = df['close'].pct_change().dropna()

    print("\n开始归因分析...")
    attribution_runner.run(
        project_root=project_root,
        cfg=cfg,
        daily_ret=time_return,
        position_count_log=getattr(r, 'position_count_log', None),
        benchmarks=benchmarks,
    )


if __name__ == '__main__':
    main()
