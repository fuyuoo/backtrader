import backtrader as bt


class StockData(bt.feeds.PandasData):
    """自定义数据 feed，读取预计算好的指标列。"""
    lines = ('ma25', 'ma60', 'dea', 'prev_close')
    params = (
        ('ma25', -1),
        ('ma60', -1),
        ('dea', -1),
        ('prev_close', -1),
    )


class StockCommission(bt.CommInfoBase):
    """A 股手续费：买入收佣金，卖出收佣金 + 印花税。"""
    params = (
        ('stocklike', True),
        ('commtype', bt.CommInfoBase.COMM_PERC),
        ('percabs', True),
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
    )

    def __init__(self):
        self.position_limit = self.p.initial_cash / self.p.max_positions

        self.stock_state = {}
        for d in self.datas:
            self.stock_state[d] = {
                'take_profit_count': 0,
                'in_ma60_obs': False,
                'in_ma25_obs': False,
            }

        self.order_log = []
        self.orders = {}

    def _current_position_count(self):
        return sum(1 for d in self.datas if self.getposition(d).size > 0)

    def _reset_state(self, d):
        self.stock_state[d] = {
            'take_profit_count': 0,
            'in_ma60_obs': False,
            'in_ma25_obs': False,
        }

    def _has_pending_order(self, d):
        o = self.orders.get(d)
        return o is not None and o.alive()

    def notify_order(self, order):
        if order.status in (order.Completed, order.Canceled, order.Rejected):
            side = 'buy' if order.isbuy() else 'sell'
            self.order_log.append({
                'date': self.data.datetime.date(0),
                'side': side,
                'size': order.executed.size,
                'price': order.executed.price,
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

            if ma60 != ma60:
                continue

            if self._has_pending_order(d):
                continue

            if pos.size > 0:
                avg_price = pos.price
                pnl_pct = (close - avg_price) / avg_price

                # MA60 止损
                if state['in_ma60_obs']:
                    if close < ma60:
                        o = self.close(data=d, exectype=bt.Order.Close)
                        self.orders[d] = o
                        self._reset_state(d)
                        continue
                    else:
                        state['in_ma60_obs'] = False
                elif close < ma60:
                    state['in_ma60_obs'] = True

                # MA25 清仓（止盈2次后激活）
                if state['take_profit_count'] >= 2 and ma25 == ma25:
                    if state['in_ma25_obs']:
                        if close < ma25:
                            o = self.close(data=d, exectype=bt.Order.Close)
                            self.orders[d] = o
                            self._reset_state(d)
                            continue
                        else:
                            state['in_ma25_obs'] = False
                    elif close < ma25:
                        state['in_ma25_obs'] = True

                # 止盈
                if state['take_profit_count'] == 0 and pnl_pct >= self.p.take_profit_1_pct:
                    sell_size = int(pos.size / 3 / 100) * 100
                    if sell_size > 0:
                        o = self.sell(data=d, size=sell_size, exectype=bt.Order.Close)
                        self.orders[d] = o
                        state['take_profit_count'] = 1
                elif state['take_profit_count'] == 1 and pnl_pct >= self.p.take_profit_2_pct:
                    sell_size = int(pos.size / 3 / 100) * 100
                    if sell_size > 0:
                        o = self.sell(data=d, size=sell_size, exectype=bt.Order.Close)
                        self.orders[d] = o
                        state['take_profit_count'] = 2

            else:
                prev_close = d.prev_close[0]
                dea = d.dea[0]

                if prev_close != prev_close:
                    continue

                if close >= prev_close:
                    continue

                if close <= ma60:
                    continue

                if dea <= 0:
                    continue
                n = self.p.dea_lookback_days
                past_deas = [d.dea[-i] for i in range(1, n + 1)]
                if any(v > 0 for v in past_deas if v == v):
                    continue

                if self._current_position_count() >= self.p.max_positions:
                    continue

                buy_value = self.position_limit / 3
                buy_size = int(buy_value / close / 100) * 100
                if buy_size <= 0:
                    continue

                o = self.buy(data=d, size=buy_size)
                self.orders[d] = o
