# 回测脚本设计文档

## 概述

基于 backtrader 框架实现沪深300 + 中证500成分股的多股票组合回测，策略逻辑来自 `backtrader/doc.md`。采用三步走架构：数据下载 → 指标预计算 → 回测执行，所有参数通过配置文件驱动，无硬编码魔数。

---

## 项目结构

```
backtrader/
├── config.json                        ← 所有参数配置
├── stock_list.csv                     ← 股票代码列表（ts_code 列）
├── data/                              ← 本地数据目录
│   ├── 600276.SH.csv                  ← 原始 OHLCV 数据
│   ├── 600276.SH_indicators.csv       ← 预计算指标数据
│   └── ...
├── downloader.py                      ← 第1步：从 Tushare 下载原始数据
├── calc_indicators.py                 ← 第2步：预计算技术指标
├── strategy.py                        ← Strategy 类（读取预计算指标）
├── backtest.py                        ← 第3步：主入口，运行回测
├── results/                           ← 输出目录
│   ├── trade_list.csv                 ← 每笔交易明细
│   └── equity_curve.png               ← 资金曲线图
└── download_errors.log                ← 下载失败记录
```

---

## 配置文件 config.json

```json
{
  "tushare_token": "your_token_here",
  "start_date": "20180101",
  "end_date": "20241231",
  "initial_cash": 100000000,
  "max_positions": 200,
  "commission_rate": 0.0003,
  "stamp_duty": 0.001,
  "stock_list_path": "stock_list.csv",
  "data_dir": "data/",
  "results_dir": "results/",
  "dea_lookback_days": 5,
  "take_profit_1_pct": 0.05,
  "take_profit_2_pct": 0.10
}
```

每只股票仓位上限 = `initial_cash / max_positions`（配置变了自动重算，无需改代码）。

---

## 第1步：downloader.py

**职责：** 从 Tushare 下载前复权日线数据，保存为本地 CSV。

**核心逻辑：**
1. 读取 `config.json` 和 `stock_list.csv`
2. 对每只股票：
   - 若本地 CSV 已存在 → 读取最后日期，只下载增量部分（避免重复下载）
   - 若不存在 → 全量下载
3. 调用 `ts.pro_bar(ts_code, adj='qfq', ...)` 使用前复权，避免除权造成 MA 指标失真
4. 下载间隔 `time.sleep(0.3)` 防止 Tushare 频率限制
5. 失败股票写入 `download_errors.log`，不中断整体流程

**保存的 CSV 格式（data/{ts_code}.csv）：**
```
trade_date, open, high, low, close, volume
2020-01-02, 10.1, 10.5, 9.9, 10.3, 123456
```

---

## 第2步：calc_indicators.py

**职责：** 读取原始 OHLCV 数据，预计算所有策略所需指标，保存为带指标的 CSV。

**计算的指标：**
- `ma25`：25日简单移动平均
- `ma60`：60日简单移动平均
- `dea`：MACD 的 DEA 线（Signal Line，即 MACD(12,26,9) 的信号线）
- `prev_close`：前一日收盘价（用于判断阴线）

**保存的 CSV 格式（data/{ts_code}_indicators.csv）：**
```
trade_date, open, high, low, close, volume, ma25, ma60, dea, prev_close
```

**处理细节：**
- 指标计算前 N 天会有 NaN（如 MA60 前59天），保留这些行，回测时 backtrader 的 `min_period` 机制会自动跳过
- 对每只股票独立计算，串行处理

---

## 第3步：strategy.py

### 数据加载

自定义 `PandasData_more` 继承 `bt.feeds.PandasData`，将 ma25、ma60、dea、prev_close 作为额外 lines 直接读取，策略中无需实时计算指标：

```python
class StockData(bt.feeds.PandasData):
    lines = ('ma25', 'ma60', 'dea', 'prev_close')
    params = (('ma25', -1), ('ma60', -1), ('dea', -1), ('prev_close', -1))
```

### 手续费

使用自定义 `StockCommission`（参考 Lesson4 示例），区分买卖方向：
- 买入：只收佣金（`commission_rate`）
- 卖出：收佣金 + 印花税（`stamp_duty`）

### 每只股票的状态（per-stock 字典）

```python
self.stock_state[d] = {
    'take_profit_count': 0,   # 已完成止盈次数（0/1/2）
    'in_ma60_obs': False,     # 是否在 MA60 止损观察期
    'in_ma25_obs': False,     # 是否在 MA25 清仓观察期（止盈2次后激活）
}
```

> **注：不需要 `pending_entry` 标志位。** backtrader 的默认执行时序是"当日 `next()` 发出的市价单，次日开盘价成交"，这本身就等同于"尾盘扫描信号 → 次日早盘买入"，框架自动处理，无需额外状态字段。

### next() 每日执行顺序

**1. 尾盘卖出检测**（对有持仓的股票，使用 `exectype=bt.Order.Close`）：

止盈规则：
- `take_profit_count=0` 且持仓盈利 ≥ 5% → 卖出**当前持仓量**的 1/3（取整到100股），`count → 1`
- `take_profit_count=1` 且持仓盈利 ≥ 10% → 再卖**当前持仓量**的 1/3（取整到100股），`count → 2`
- 同一天止盈与止损同时触发时，优先执行止损（清仓），忽略止盈

MA60 止损规则（全程有效）：
- `in_ma60_obs=False` 且 `close < MA60` → 进入观察期
- `in_ma60_obs=True` 且 `close < MA60` → 清仓，重置所有状态
- `in_ma60_obs=True` 且 `close ≥ MA60` → 解除观察期

MA25 清仓规则（`take_profit_count=2` 后激活，与 MA60 止损并行）：
- `in_ma25_obs=False` 且 `close < MA25` → 进入 MA25 观察期
- `in_ma25_obs=True` 且 `close < MA25` → 清仓，重置所有状态
- `in_ma25_obs=True` 且 `close ≥ MA25` → 解除 MA25 观察期

优先级：MA60 和 MA25 哪个先触发先执行，同一天两个都触发时 MA60 优先。

**2. 尾盘入场扫描**（对无持仓的股票）：

同时满足以下三个条件时，直接发出市价买单（backtrader 自动在次日开盘价成交）：
- 今日为阴线：`close < prev_close`
- DEA 刚上穿0轴：`dea[0] > 0` 且前 `dea_lookback_days` 天内 DEA 均 ≤ 0
- 收盘价站上 MA60：`close > ma60`

买入股数：`int(position_limit / 3 / data.close[0] / 100) * 100`（用收盘价估算，取整到100股；实际以次日开盘价成交）

---

## 第4步：backtest.py（主入口）

**流程：**
1. 读取 `config.json`
2. 读取 `stock_list.csv` → 股票代码列表
3. 遍历股票列表，加载 `data/{ts_code}_indicators.csv` → `StockData` → `cerebro.adddata()`
4. 配置 broker：初始资金、自定义 StockCommission、百分比滑点
5. `cerebro.addstrategy(MyStrategy, **config_params)`
6. 添加分析器：`AnnualReturn`、`DrawDown`、`SharpeRatio_A`、`TimeReturn`、自定义 `trade_list`
7. `cerebro.run()`
8. 打印关键指标到控制台
9. 保存 `results/trade_list.csv` 和 `results/equity_curve.png`

---

## 数据流

```
config.json ──┐
stock_list.csv─┤
               ├─→ downloader.py      → data/{code}.csv
               ├─→ calc_indicators.py → data/{code}_indicators.csv
               └─→ backtest.py
                       ↓
                   strategy.py
                       ↓
                   results/
```

---

## 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 复权方式 | 前复权 qfq | 避免除权造成 MA 指标断层 |
| 卖出执行时机 | `exectype=bt.Order.Close` | 模拟尾盘操作（当日收盘价成交） |
| 买入执行时机 | 默认市价单 | 次日开盘价成交，符合策略描述 |
| 指标计算位置 | 预计算存 CSV | 800只股票每次回测重算耗时，分离后可复用 |
| 多股票状态管理 | per-stock 字典 | backtrader 多数据feed的标准做法 |
| 股票数取整 | 100股整数倍 | A 股最小买入单位 100 股 |
