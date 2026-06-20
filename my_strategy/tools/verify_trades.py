"""逐 episode 验证 trade_list / trade_summary 是否符合 strategy.py 规则。

验证项：
  L1 一致性：
    - 每个 episode 的 buys 数 == add_count + 1 (initial_buy)
    - sum(buys.size) == total_shares
    - 已平仓: sum(sells.size) == sum(buys.size)
    - avg_cost / return_pct 计算正确
    - take_profit_1 必须先于 take_profit_2
    - MA25_stop 时 take_profit_count >= 2
  L1 信号：
    - 每笔 initial_buy / add_on：执行日的"信号日"(前一交易日) 满足
        close < prev_close, close > ma60, dea > 0, 过去5日有 dea<0
"""
import json
import sys
from pathlib import Path
import pandas as pd
import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
CFG = json.loads((PROJECT / 'config.json').read_text(encoding='utf-8'))
DATA_DIR = Path(CFG['data_dir'])
DEA_LOOKBACK = 5

PICKED = ['000426.SZ', '000513.SZ', '000537.SZ', '000539.SZ', '000977.SZ',
          '001965.SZ', '002044.SZ', '002120.SZ', '002273.SZ', '300014.SZ',
          '300037.SZ', '300136.SZ', '300339.SZ', '300628.SZ', '600690.SH',
          '601229.SH', '601872.SH', '601985.SH', '603650.SH', '603833.SH']


def load_indicators(ts_code):
    p = DATA_DIR / 'indicators' / f'{ts_code}.csv'
    df = pd.read_csv(p, parse_dates=['trade_date']).sort_values('trade_date').reset_index(drop=True)
    df['prev_close'] = df['close'].shift(1)
    return df


def signal_day(ind_df, exec_date):
    """cerebro 启用了 set_coc(True)，市价单当日收盘成交，信号日 == 执行日"""
    exec_date = pd.Timestamp(exec_date)
    rows = ind_df[ind_df['trade_date'] == exec_date]
    if rows.empty:
        return None
    return rows.iloc[0]


def check_buy_signal(ind_df, exec_date, kind):
    """对买单做信号合规检查。返回违规说明 list。"""
    sig = signal_day(ind_df, exec_date)
    if sig is None:
        return [f'{kind}@{exec_date}: 找不到信号日']
    issues = []
    if pd.isna(sig['prev_close']):
        return [f'{kind}@{exec_date}: 信号日{sig.trade_date.date()} 无 prev_close']
    if not (sig['close'] < sig['prev_close']):
        issues.append(f'{kind}@{exec_date}: 信号日{sig.trade_date.date()} close{sig.close:.3f} 未<prev_close{sig.prev_close:.3f}')
    if not (sig['close'] > sig['ma60']):
        issues.append(f'{kind}@{exec_date}: close{sig.close:.3f} 未>ma60{sig.ma60:.3f}')
    if not (sig['dea'] > 0):
        issues.append(f'{kind}@{exec_date}: dea{sig.dea:.4f} 未>0')
    # past N days has dea<0
    sig_idx = ind_df.index[ind_df['trade_date'] == sig['trade_date']][0]
    past = ind_df.loc[max(0, sig_idx - DEA_LOOKBACK): sig_idx - 1, 'dea']
    if not (past < 0).any():
        issues.append(f'{kind}@{exec_date}: 过去{DEA_LOOKBACK}日 dea 无负值')
    return issues


def verify_episode(ts_code, ep_num, ep_summary, ep_orders, ind_df):
    issues = []
    buys = ep_orders[ep_orders['side'] == 'buy'].sort_values('date').reset_index(drop=True)
    sells = ep_orders[ep_orders['side'] == 'sell'].sort_values('date').reset_index(drop=True)

    # ---- 一致性 ----
    expected_buys = ep_summary['add_count'] + 1
    if len(buys) != expected_buys:
        issues.append(f'buys 数 {len(buys)} != add_count+1 {expected_buys}')

    if buys.empty:
        issues.append('buys 为空')
        return issues
    if buys.iloc[0]['reason'] != 'initial_buy':
        issues.append(f'第一笔不是 initial_buy: {buys.iloc[0]["reason"]}')
    for i in range(1, len(buys)):
        if buys.iloc[i]['reason'] != 'add_on':
            issues.append(f'第{i+1}笔买入应为 add_on, 实际 {buys.iloc[i]["reason"]}')

    total_buys = buys['size'].sum()
    if abs(total_buys - ep_summary['total_shares']) > 1:
        issues.append(f'sum(buys)={total_buys} != total_shares={ep_summary["total_shares"]}')

    if ep_summary['status'] == 'completed':
        total_sells = sells['size'].abs().sum()
        if abs(total_sells - total_buys) > 1:
            issues.append(f'sum(sells)={total_sells} != sum(buys)={total_buys}')
        avg_cost = (buys['size'] * buys['price']).sum() / total_buys
        if abs(avg_cost - ep_summary['avg_cost']) > 0.01:
            issues.append(f'avg_cost 算偏: 计算{avg_cost:.4f} vs 记录{ep_summary["avg_cost"]:.4f}')
        if not sells.empty:
            avg_exit = (sells['size'].abs() * sells['price']).sum() / total_sells
            if abs(avg_exit - ep_summary['avg_exit_price']) > 0.01:
                issues.append(f'avg_exit_price 算偏: {avg_exit:.4f} vs {ep_summary["avg_exit_price"]:.4f}')
            ret = (avg_exit - avg_cost) / avg_cost * 100
            if abs(ret - ep_summary['return_pct']) > 0.05:
                issues.append(f'return_pct 算偏: {ret:.4f} vs {ep_summary["return_pct"]:.4f}')

    # 止盈顺序
    tp_seq = sells[sells['reason'].str.startswith('take_profit')]['reason'].tolist()
    for i, r in enumerate(tp_seq):
        expected = f'take_profit_{i+1}'
        if r != expected:
            issues.append(f'止盈顺序异常: 第{i+1}笔止盈={r}, 应为{expected}')
    # MA25_stop 前必须 >= 2 次止盈
    if not sells.empty and sells.iloc[-1]['reason'] == 'MA25_stop':
        if len(tp_seq) < 2:
            issues.append(f'MA25_stop 触发但止盈次数{len(tp_seq)}<2')

    # ---- 买入信号合规 ----
    for _, row in buys.iterrows():
        kind = row['reason']
        sub = check_buy_signal(ind_df, row['date'], kind)
        issues.extend(sub)

    # ---- 卖出端合规 ----
    avg_cost_running = (buys['size'] * buys['price']).sum() / max(1, buys['size'].sum())
    for _, row in sells.iterrows():
        sig = signal_day(ind_df, row['date'])
        if sig is None:
            issues.append(f'{row["reason"]}@{row["date"]}: 找不到当日 K 线')
            continue
        if row['reason'] == 'MA60_stop':
            if not (sig['close'] < sig['ma60']):
                issues.append(f'MA60_stop@{row["date"]}: close{sig.close:.3f} 未<ma60{sig.ma60:.3f}')
        elif row['reason'] == 'MA25_stop':
            if not (sig['close'] < sig['ma25']):
                issues.append(f'MA25_stop@{row["date"]}: close{sig.close:.3f} 未<ma25{sig.ma25:.3f}')
        elif row['reason'] in ('take_profit_1', 'take_profit_2'):
            ret = (sig['close'] - avg_cost_running) / avg_cost_running
            tp1 = ep_summary.get('tp1_pct')
            tp2 = ep_summary.get('tp2_pct')
            target = tp1 if row['reason'] == 'take_profit_1' else tp2
            if pd.notna(target) and ret + 1e-4 < target:
                issues.append(f'{row["reason"]}@{row["date"]}: ret={ret*100:.3f}% 未达阈值 {target*100:.3f}%')

    return issues


def build_capacity_full_dates(summary, max_positions):
    """返回当日全市场并发持仓 >= max_positions 的日期集合。"""
    summary = summary.copy()
    summary['exit_date'] = summary['exit_date'].fillna(summary['entry_date'].max())
    events = []
    for _, ep in summary.iterrows():
        events.append((ep['entry_date'], +1))
        events.append((ep['exit_date'] + pd.Timedelta(days=1), -1))
    events.sort()
    full_dates = set()
    cur = 0
    # build daily count via running sum
    by_day = {}
    for d, delta in events:
        by_day[d] = by_day.get(d, 0) + delta
    days = sorted(by_day.keys())
    for d in days:
        cur += by_day[d]
        # cur is count starting from this day onward until next event day
        if cur >= max_positions:
            # we'll broadcast: from this day to next event day - 1
            pass
    # simpler: walk all trading days from min entry to max exit
    return _walk_capacity(summary, max_positions)


def _walk_capacity(summary, max_positions):
    if summary.empty:
        return set()
    start = summary['entry_date'].min()
    end = summary['exit_date'].max()
    # use business days; cap to set of all entry/exit dates in summary
    all_dates = pd.date_range(start, end, freq='D')
    counts = pd.Series(0, index=all_dates)
    for _, ep in summary.iterrows():
        s = ep['entry_date']
        e = ep['exit_date'] if pd.notna(ep['exit_date']) else end
        counts.loc[s:e] += 1
    return set(counts.index[counts >= max_positions].normalize())


def find_missed_buys(ts_code, ind_df, ep_summary_all, orders_all,
                     start_date, end_date, capacity_full):
    """扫所有 bar，找信号日满足 5 条件但既无买单也不在持仓期的"漏单"。

    假设：max_positions=200 极少触顶，配合 trade_summary 显示同一天最多
    几十只股票成交，所以"漏单"很可能是 bug。
    """
    # 持仓区间集合：[entry_date, exit_date]
    intervals = []
    for _, ep in ep_summary_all.iterrows():
        if pd.notna(ep['entry_date']):
            ed = ep['exit_date'] if pd.notna(ep['exit_date']) else end_date
            intervals.append((pd.Timestamp(ep['entry_date']), pd.Timestamp(ed)))
    in_pos = lambda d: any(s <= d <= e for s, e in intervals)
    buy_dates = set(orders_all[(orders_all['ts_code'] == ts_code)
                               & (orders_all['side'] == 'buy')]['date'])

    df = ind_df[(ind_df['trade_date'] >= start_date)
                & (ind_df['trade_date'] <= end_date)].reset_index(drop=True)
    df['prev_close'] = df['close'].shift(1)
    misses = []
    for i in range(DEA_LOOKBACK, len(df)):
        r = df.iloc[i]
        if pd.isna(r['prev_close']) or pd.isna(r['ma60']) or pd.isna(r['dea']):
            continue
        if not (r['close'] < r['prev_close']):
            continue
        if not (r['close'] > r['ma60']):
            continue
        if not (r['dea'] > 0):
            continue
        past = df.loc[i - DEA_LOOKBACK:i - 1, 'dea']
        if not (past < 0).any():
            continue
        d = pd.Timestamp(r['trade_date'])
        if in_pos(d):  # 持仓期允许"未发生 add_on"——加仓有 big_candle 等额外约束
            continue
        if d in buy_dates:
            continue
        if d in capacity_full:  # 全市场满仓，被 no_capacity 拒绝是合规
            continue
        misses.append(d.date())
    return misses


def find_missed_stops(ts_code, ind_df, ep_summary_all, orders_all):
    """对每个 episode，扫持仓期间 MA60/MA25 是否本应触发但未触发。
    简化模型：close<ma60 形成观察期，下一根继续 close<ma60 必触发清仓。
    """
    code_orders = orders_all[orders_all['ts_code'] == ts_code]
    issues = []
    for _, ep in ep_summary_all.iterrows():
        if ep['status'] != 'completed':
            continue
        entry = pd.Timestamp(ep['entry_date'])
        exit_ = pd.Timestamp(ep['exit_date'])
        ep_orders = code_orders[code_orders['episode'] == ep['episode']]
        seg = ind_df[(ind_df['trade_date'] >= entry)
                     & (ind_df['trade_date'] <= exit_)].reset_index(drop=True)
        if len(seg) < 2:
            continue
        # MA60_stop 模拟
        in_obs = False
        for i in range(len(seg)):
            r = seg.iloc[i]
            if pd.isna(r['ma60']):
                continue
            if i == 0:
                in_obs = r['close'] < r['ma60']
                continue
            if in_obs:
                if r['close'] < r['ma60']:
                    # 应在该日触发 MA60_stop
                    if pd.Timestamp(r['trade_date']) < exit_:
                        # 检查这日之前是否已发生止盈让止盈条件先触发——简化跳过
                        pass
                    if pd.Timestamp(r['trade_date']) > exit_:
                        # exit_ 不可能晚于此日；理论无此情况
                        pass
                    if pd.Timestamp(r['trade_date']) < exit_:
                        # 真正的"漏止":出场日理应 ≤ 此日
                        issues.append(
                            f'{ts_code} ep{ep["episode"]}: MA60_stop 应在 '
                            f'{r["trade_date"].date()} 触发(close{r.close:.3f}<ma60{r.ma60:.3f}, '
                            f'前日已观察)，实际清仓日 {exit_.date()} 推迟')
                        break
                    in_obs = False
                else:
                    in_obs = False
            else:
                in_obs = r['close'] < r['ma60']
    return issues


def main():
    summary = pd.read_csv(PROJECT / 'results' / 'trade_summary.csv', parse_dates=['entry_date', 'exit_date'])
    orders = pd.read_csv(PROJECT / 'results' / 'trade_list.csv', parse_dates=['date'])
    # 起点用全局首笔订单日：避开 backtrader 的指标 warmup 期 (ATR/MA60)
    backtest_start = orders['date'].min()
    backtest_end = pd.Timestamp(CFG['backTest_end_data'])
    capacity_full = _walk_capacity(summary, max_positions=200)

    total_eps = 0
    bad_eps = 0
    issue_buckets = {}
    missed_buys_total = 0
    missed_stops_total = 0

    for code in PICKED:
        ind_df = load_indicators(code)
        ep_summary_all = summary[summary['ts_code'] == code]
        ep_orders_all = orders[orders['ts_code'] == code]
        for _, ep in ep_summary_all.iterrows():
            total_eps += 1
            ep_num = ep['episode']
            ep_orders = ep_orders_all[ep_orders_all['episode'] == ep_num]
            issues = verify_episode(code, ep_num, ep, ep_orders, ind_df)
            if issues:
                bad_eps += 1
                for it in issues:
                    key = it.split(':')[0]
                    if '@' in key:
                        key = key.split('@')[0]
                    issue_buckets.setdefault(key, []).append(f'{code} ep{ep_num}: {it}')

        # 反向检查
        misses = find_missed_buys(code, ind_df, ep_summary_all, orders,
                                  backtest_start, backtest_end, capacity_full)
        if misses:
            missed_buys_total += len(misses)
            issue_buckets.setdefault('[反向] missed_initial_buy', []).extend(
                [f'{code}: {d}' for d in misses])
        m_stops = find_missed_stops(code, ind_df, ep_summary_all, orders)
        if m_stops:
            missed_stops_total += len(m_stops)
            issue_buckets.setdefault('[反向] missed_ma60_stop', []).extend(m_stops)

    print(f'\n===== 验证 {len(PICKED)} 只股票，{total_eps} 个 episode =====')
    print(f'正向: 有问题 episode {bad_eps} ({bad_eps/total_eps*100:.1f}%)')
    print(f'反向: missed_initial_buy {missed_buys_total} 例，missed_ma60_stop {missed_stops_total} 例')
    print(f'问题分类（按出现次数排序）:')
    for k, v in sorted(issue_buckets.items(), key=lambda x: -len(x[1])):
        print(f'\n[{k}]  {len(v)} 例')
        for line in v[:5]:
            print(f'  {line}')
        if len(v) > 5:
            print(f'  ... 共 {len(v)} 例')


if __name__ == '__main__':
    main()
