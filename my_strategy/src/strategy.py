import math
import backtrader as bt


def _isnan(x):
    """显式 NaN 判断；非 float 输入会立即抛 TypeError，便于发现数据异常。"""
    return math.isnan(x)


class StockData(bt.feeds.PandasData):
    """自定义数据 feed，读取预计算好的指标列。"""
    lines = ('ma25', 'ma60', 'dea')
    params = (
        ('ma25', -1),
        ('ma60', -1),
        ('dea', -1),
    )


class StockCommission(bt.CommInfoBase):
    """A 股手续费：买入收佣金，卖出收佣金 + 印花税。"""
    params = (
        ('stocklike', True),
        ('commtype', bt.CommInfoBase.COMM_PERC),
        ('percabs', True),
        ('commission', 0.0003),
        ('stamp_duty', 0.001),
    )

    def _getcommission(self, size, price, pseudoexec):
        if size > 0:
            return abs(size) * price * self.p.commission
        elif size < 0:
            return abs(size) * price * (self.p.commission + self.p.stamp_duty)
        return 0.0


class MyStrategy(bt.Strategy):
    params = (
        ('initial_cash', 100_000_000),
        ('max_positions', 200),
        ('take_profit_1_pct', 0.05),
        ('take_profit_2_pct', 0.10),
        ('dea_lookback_days', 5),
        ('atr_period', 20),
        ('atr_multiplier', 1.5),
        ('take_profit_min_pct', 0.03),
        ('take_profit_max_pct', 0.12),
        ('factor_lookup', None),  # deprecated — retained for backwards compat, ignored
        ('sector_map', None),     # dict: {ts_code: sw_index_code}
    )

    def __init__(self):
        self.position_limit = self.p.initial_cash / self.p.max_positions

        self.atr = {d: bt.indicators.ATR(d, period=self.p.atr_period) for d in self.datas}

        self.stock_state = {}
        for d in self.datas:
            self.stock_state[d] = {
                'take_profit_count': 0,
                'in_ma60_obs': False,
                'in_ma25_obs': False,
                'entry_price': None,
                'big_candle_seen': False,
                'add_count': 0,
                'tp1_pct': None,
                'tp2_pct': None,
                'initial_size': None,
                'pending_atr': float('nan'),
            }

        self.order_log = []
        self.orders = {}
        self.order_reasons = {}  # Maps order.ref (int) to reason string
        self.episode_state = {
            d: {'buys': [], 'sells': [], 'episode_num': 1}
            for d in self.datas
        }
        self.trade_log = []
        self.position_count_log = []
        self.signals_log = []

    def _current_position_count(self):
        count = 0
        for d in self.datas:
            pos_size = self.getposition(d).size
            o = self.orders.get(d)
            has_pending_buy = o is not None and o.alive() and o.isbuy()
            if pos_size > 0 or has_pending_buy:
                count += 1
        return count

    def _reset_state(self, d):
        self.stock_state[d] = {
            'take_profit_count': 0,
            'in_ma60_obs': False,
            'in_ma25_obs': False,
            'entry_price': None,
            'big_candle_seen': False,
            'add_count': 0,
            'tp1_pct': None,
            'tp2_pct': None,
            'initial_size': None,
            'pending_atr': float('nan'),
        }

    def _has_pending_order(self, d):
        o = self.orders.get(d)
        return o is not None and o.alive()

    def _finalize_episode(self, d, status='completed'):
        state = self.stock_state[d]
        ep = self.episode_state[d]
        buys, sells = ep['buys'], ep['sells']
        if not buys:
            return
        total_shares = sum(b['size'] for b in buys)
        avg_cost = sum(b['size'] * b['price'] for b in buys) / total_shares
        entry_date = buys[0]['date']
        add_count = sum(1 for b in buys if b['reason'] == 'add_on')
        if sells:
            total_sold = sum(s['size'] for s in sells)
            avg_exit_price = sum(s['size'] * s['price'] for s in sells) / total_sold
            exit_date = sells[-1]['date']
            holding_days = (exit_date - entry_date).days
            gross_pnl = (avg_exit_price - avg_cost) * total_sold
            return_pct = (avg_exit_price - avg_cost) / avg_cost * 100
            take_profit_count = sum(
                1 for s in sells if s['reason'] in ('take_profit_1', 'take_profit_2')
            )
            exit_reason = {
                'MA60_stop': 'MA60止损',
                'MA25_stop': 'MA25清仓',
                'take_profit_1': '止盈1',
                'take_profit_2': '止盈2',
            }.get(sells[-1]['reason'], sells[-1]['reason'])
        else:
            avg_exit_price = exit_date = holding_days = gross_pnl = return_pct = None
            take_profit_count = 0
            exit_reason = '未平仓'
        self.trade_log.append({
            'ts_code': d._name,
            'episode': ep['episode_num'],
            'entry_date': entry_date,
            'exit_date': exit_date,
            'holding_days': holding_days,
            'avg_cost': round(avg_cost, 4),
            'avg_exit_price': round(avg_exit_price, 4) if avg_exit_price is not None else None,
            'total_shares': int(total_shares),
            'gross_pnl': round(gross_pnl, 2) if gross_pnl is not None else None,
            'return_pct': round(return_pct, 4) if return_pct is not None else None,
            'add_count': add_count,
            'take_profit_count': take_profit_count,
            'exit_reason': exit_reason,
            'status': status,
            'tp1_pct': round(state['tp1_pct'], 4) if state['tp1_pct'] is not None else None,
            'tp2_pct': round(state['tp2_pct'], 4) if state['tp2_pct'] is not None else None,
        })
        ep['buys'] = []
        ep['sells'] = []
        ep['episode_num'] += 1

    def _record_signal(self, d, trade_date, close, ma25, ma60, dea,
                       was_bought, skip_reason):
        sector_map = self.p.sector_map or {}
        rec = {
            'date': trade_date,
            'ts_code': d._name,
            'sector': sector_map.get(d._name, ''),
            'close': close,
            'ma25': ma25,
            'ma60': ma60,
            'dea': dea,
            'atr': float(self.atr[d][0]),
            'was_bought': was_bought,
            'skip_reason': skip_reason,
            'forward_return_5d': None,
            'forward_return_20d': None,
            'forward_return_60d': None,
        }
        self.signals_log.append(rec)

    def stop(self):
        for d in self.datas:
            if self.episode_state[d]['buys']:
                self._finalize_episode(d, status='incomplete')
                self._reset_state(d)

    def notify_order(self, order):
        if order.status in (order.Completed, order.Canceled, order.Rejected):
            reason = self.order_reasons.pop(order.ref, 'unknown')
            ep = self.episode_state[order.data]
            episode_num = ep['episode_num']

            if order.status == order.Completed:
                if order.isbuy():
                    state = self.stock_state[order.data]
                    if state['entry_price'] is None:
                        state['entry_price'] = order.executed.price
                    if reason == 'add_on':
                        state['add_count'] += 1
                    if reason == 'initial_buy':
                        state['initial_size'] = order.executed.size
                        atr_val = state.pop('pending_atr', float('nan'))  # [C1] 使用下单时缓存的 ATR
                        if atr_val == atr_val:  # not NaN
                            atr_pct = atr_val / order.executed.price
                            tp1 = max(self.p.take_profit_min_pct,
                                      min(self.p.take_profit_max_pct,
                                          self.p.atr_multiplier * atr_pct))
                        else:
                            tp1 = self.p.take_profit_1_pct
                        state['tp1_pct'] = tp1
                        state['tp2_pct'] = tp1 * 2
                    ep['buys'].append({
                        'date': bt.num2date(order.executed.dt).date(),
                        'size': order.executed.size,
                        'price': order.executed.price,
                        'reason': reason,
                    })
                else:
                    ep['sells'].append({
                        'date': bt.num2date(order.executed.dt).date(),
                        'size': abs(order.executed.size),
                        'price': order.executed.price,
                        'reason': reason,
                    })
                    state = self.stock_state[order.data]
                    if reason == 'take_profit_1':
                        state['take_profit_count'] = 1
                    elif reason == 'take_profit_2':
                        state['take_profit_count'] = 2
                    # [I4] 用持仓归零判断，比累计数量比较更可靠
                    if self.getposition(order.data).size == 0 and ep['buys']:
                        self._finalize_episode(order.data)
                        self._reset_state(order.data)  # [C2][C5] 统一在此重置

                # [C4] 仅 Completed 订单写入 order_log
                self.order_log.append({
                    'date': bt.num2date(order.executed.dt).date(),
                    'ts_code': order.data._name,
                    'side': 'buy' if order.isbuy() else 'sell',
                    'size': order.executed.size,
                    'price': order.executed.price,
                    'reason': reason,
                    'episode': episode_num,
                })
            for d, o in list(self.orders.items()):
                if o is order:
                    self.orders.pop(d, None)
                    break

    def next(self):
        for d in self.datas:
            state = self.stock_state[d]
            pos = self.getposition(d)
            close = d.close[0]
            ma25 = d.ma25[0]
            ma60 = d.ma60[0]

            if _isnan(ma60):
                continue

            if self._has_pending_order(d):
                continue

            if pos.size > 0:
                entry_price = state['entry_price'] if state['entry_price'] is not None else pos.price
                pnl_pct = (close - entry_price) / entry_price

                # 记录阳线（持仓期间出现 >1% 阳线则禁止加仓）
                open_ = d.open[0]
                if open_ > 0 and (close - open_) / open_ > 0.01:
                    state['big_candle_seen'] = True

                # MA60 止损
                if state['in_ma60_obs']:
                    if close < ma60:
                        o = self.close(data=d, exectype=bt.Order.Market)
                        self.order_reasons[o.ref] = 'MA60_stop'
                        self.orders[d] = o
                        continue
                    else:
                        state['in_ma60_obs'] = False
                elif close < ma60:
                    state['in_ma60_obs'] = True

                # MA25 清仓（止盈2次后激活）
                if state['take_profit_count'] >= 2 and ma25 == ma25:
                    if state['in_ma25_obs']:
                        if close < ma25:
                            o = self.close(data=d, exectype=bt.Order.Market)
                            self.order_reasons[o.ref] = 'MA25_stop'
                            self.orders[d] = o
                            continue
                        else:
                            state['in_ma25_obs'] = False
                    elif close < ma25:
                        state['in_ma25_obs'] = True

                # 止盈（阈值用 ATR 动态值，卖出量用原始建仓量的1/3）
                tp1 = state['tp1_pct'] if state['tp1_pct'] is not None else self.p.take_profit_1_pct
                tp2 = state['tp2_pct'] if state['tp2_pct'] is not None else self.p.take_profit_2_pct
                base_size = state['initial_size'] if state['initial_size'] is not None else pos.size
                tp_sell_size = min(int(base_size / 3 / 100) * 100, pos.size)
                if state['take_profit_count'] == 0 and pnl_pct >= tp1:
                    if tp_sell_size > 0:
                        o = self.sell(data=d, size=tp_sell_size, exectype=bt.Order.Market)
                        self.order_reasons[o.ref] = 'take_profit_1'
                        self.orders[d] = o
                        continue
                elif state['take_profit_count'] == 1 and pnl_pct >= tp2:
                    if tp_sell_size > 0:
                        o = self.sell(data=d, size=tp_sell_size, exectype=bt.Order.Market)
                        self.order_reasons[o.ref] = 'take_profit_2'
                        self.orders[d] = o
                        continue

                # 加仓（最多2次，满足与买入相同条件，且未出现大阳线）
                if state['add_count'] < 2 and not state['big_candle_seen']:
                    prev_close = d.close[-1]
                    dea = d.dea[0]
                    if (
                        not _isnan(prev_close)
                        and close < prev_close
                        and close > ma60
                        and dea > 0
                    ):
                        past_deas = [d.dea[-i] for i in range(1, self.p.dea_lookback_days + 1)]
                        if any(v < 0 for v in past_deas if not _isnan(v)):
                            add_size = int(self.position_limit / 3 / close / 100) * 100
                            if add_size > 0:
                                o = self.buy(data=d, size=add_size)
                                self.order_reasons[o.ref] = 'add_on'
                                self.orders[d] = o

            else:
                prev_close = d.close[-1]
                dea = d.dea[0]

                if _isnan(prev_close):
                    continue

                if close >= prev_close:
                    continue

                if close <= ma60:
                    continue

                if dea <= 0:
                    continue
                n = self.p.dea_lookback_days
                past_deas = [d.dea[-i] for i in range(1, n + 1)]
                if not any(v < 0 for v in past_deas if v == v):
                    continue

                # ============ 5 条必要条件全部通过，记录信号 ============
                trade_date = bt.num2date(d.datetime[0]).date()
                skip_reason = ''
                if self._current_position_count() >= self.p.max_positions:
                    skip_reason = 'no_capacity'

                if (close - ma60) / ma60 <= 0.01:
                    buy_size = int(self.position_limit / close / 100) * 100
                else:
                    buy_size = int(self.position_limit / 3 / close / 100) * 100

                if not skip_reason and buy_size <= 0:
                    skip_reason = 'no_capacity'

                self._record_signal(d, trade_date, close, ma25, ma60, dea,
                                     was_bought=(skip_reason == ''),
                                     skip_reason=skip_reason)

                if skip_reason:
                    continue

                if (close - ma60) / ma60 <= 0.01:
                    state['add_count'] = 2

                state['pending_atr'] = float(self.atr[d][0])
                o = self.buy(data=d, size=buy_size)
                self.order_reasons[o.ref] = 'initial_buy'
                self.orders[d] = o

        self.position_count_log.append(self._current_position_count())
