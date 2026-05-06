# 功能总览（FEATURES）

> 范围：本仓库 `my_strategy/` 目录下的 A 股量化回测流水线。
> 仓库内 `backtrader/`（框架源码）与 `learn_backtrader/`（教程）不在本文档范围内。
> 维护规则见 `CLAUDE.md` 的「文档维护规则」章节。

## 1. 项目目标

基于 backtrader 框架，构建一套面向 A 股的端到端量化回测流水线：
**数据下载 → 因子/指标计算 → 横截面分位 → 策略回测 → 归因分析 → 交易合规验证**。

## 2. 目录结构

```
my_strategy/
├── config.json / config.example.json   # 全局配置
├── stock_list.csv / a_stock_list.txt   # 股票池
├── download_all.py                      # 数据下载主入口（拉指数成分股 + 调用 downloader）
├── backtest.py                          # 回测主入口
├── src/
│   ├── downloader.py                   # 日线/周线/月线下载（pro_bar 前复权）
│   ├── downloader_extra.py             # daily_basic / fina_indicator / 申万行业指数
│   ├── calc_indicators.py              # MA/MACD/KDJ + 多周期合并 + 因子合成
│   ├── build_cross_section_pct.py      # 每日横截面分位排名
│   └── strategy.py                     # MyStrategy + StockData feed + 佣金模型
├── tools/
│   ├── attribution.py                  # 多角度归因报告
│   └── verify_trades.py                # 逐 episode 信号合规校验
├── data/                               # 下载产物
│   ├── daily/                          # 日线
│   ├── weekly/, monthly/               # 周线、月线
│   ├── daily_basic/                    # 估值/市值/换手率
│   ├── fina/                           # 财务指标
│   ├── sw_index/                       # 申万行业指数
│   ├── stock_sector.csv                # 股票↔行业映射
│   ├── indicators/                     # calc_indicators 产物（已合并所有因子）
│   └── signals_log.csv                 # 策略每次买入信号快照
├── results/                            # 回测产物（trade_list、equity 曲线等）
├── reports/                            # 归因分析输出
├── logs/                               # 下载错误日志
└── tests/                              # pytest 单元测试
```

## 3. 数据下载（download_all.py + src/downloader*.py）

**职责**：从 Tushare 拉取所有需要的数据并按股票切分到本地 CSV。

- **入口**：`python my_strategy/download_all.py`
- **股票池**：根据 `config.json.index_codes`（默认 沪深300 + 中证500）调用
  `pro.index_weight` 取最近一次成分股快照，写入 `a_stock_list.txt`，再串联调用下游下载器。
- **基础行情**（`src/downloader.py`）：
  - `pro.pro_bar` 前复权日线，按 10 年切片避免 6000 行限制；
  - 周线 / 月线同步下载；
  - `_call_with_timeout` 单笔超时保护，超时不阻塞后续；
  - 错误进入 `logs/download_errors.log`，不静默吞错。
- **辅助数据**（`src/downloader_extra.py`）：
  - `daily_basic`：`pe_ttm, pb, total_mv, circ_mv, turnover_rate`
  - `fina_indicator`：`roe, netprofit_yoy, ann_date, end_date` 等（保留 ann_date 以做 PIT 对齐）
  - 申万一级行业指数：按 `config.sw_index_codes` 全量拉取
  - 已存在文件默认跳过（`force=True` 强制覆盖）
- **关键配置**：`tushare_token`、`start_date/end_date`、`index_codes`、`sw_index_codes`、
  `data_paths.*`、`api_rate_per_min`。

## 4. 指标 / 因子计算（src/calc_indicators.py）

**职责**：把多份原始 CSV 合并成"每只股票一张完整指标表"，输出到 `data/indicators/`。

- **技术指标**（基于日线）：MA25 / MA60 / MA144 / MA180、MACD（DIF/DEA/MACD）、KDJ-J；
  9 日内 high==high（停牌、一字板）会被显式置 NaN，避免假信号。
- **多周期合并**：`compute_weekly_monthly_indicators` 读周/月线 CSV，把周/月 KDJ-J 与
  MACD 区间标签 ffill 到日线，得到 `kdj_j_weekly`、`macd_zone_weekly` 等列。
- **基本面合并**：`merge_fundamentals` 按 `ann_date` 而非 `end_date` 对齐，避免使用
  发布前的财务数据（PIT 一致性）。
- **单股因子**（`add_single_stock_factors`）：动量 60 日、距 MA60 偏离度、MACD 强度。
- **行业动量**（`merge_sector_momentum`）：按 `stock_sector.csv` 对应到申万行业指数，
  写入 `factor_sector_momentum_60d`。
- **产物**：`data/indicators/<ts_code>.csv`，列含 OHLCV + 全部指标 + 全部因子。

## 5. 横截面分位（src/build_cross_section_pct.py）

**职责**：对所有股票每日的因子值做横截面 rank，输出 0~1 分位列。

- **PCT_FACTORS** 表声明哪些原始列要算分位、是否反向（如低 PE 高分位）。
- 使用 `groupby('trade_date').rank(pct=True)` 一次性向量化处理全长表，性能良好。
- 写回每只股票 CSV，新增列以 `pct_` 前缀（`pct_momentum_60d`、`pct_pe`、`pct_roe` 等）。
- **入口**：在 `download_all.py` 末尾自动调用，也可单独 `process_indicators_dir(...)`。

## 6. 策略与回测（src/strategy.py + backtest.py）

**入口**：`python my_strategy/backtest.py`

### 6.1 MyStrategy 入场条件（5 条同时成立）

1. `close < prev_close`（收阴）
2. `close > MA60`（趋势之上）
3. `DEA > 0`（处于多头宏观区）
4. 过去 `dea_lookback_days` 内出现过 `DEA < 0`（刚刚翻多）
5. 当前未持仓或满足加仓条件

### 6.2 仓位与卖出

- 仓位规模按 `initial_cash / max_positions` 等额分配；
- 止盈分级：`take_profit_1_pct`、`take_profit_2_pct` 两档；
- ATR 动态止盈：`atr_period`、`atr_multiplier`，最终止盈幅度被
  `take_profit_min_pct` / `take_profit_max_pct` 截断；
- MA25 跌破止损（仅在已经触发过 take_profit_1 之后生效）；
- `cerebro.broker.set_coc(True)`：市价单当日收盘成交，**信号日 == 执行日**。

### 6.3 回测组件

- `StockData`（PandasData 子类）暴露 `ma25/ma60/dea` 三条预计算线；
- `StockCommission`：买入只收佣金，卖出佣金 + 印花税；
- 自定义 `BacktestProgressAnalyzer`：按 bar 进度打印百分比；
- 数据预过滤：剔除上市过晚 / 中途退市 / 指标文件缺失的股票，跳过原因汇总打印。

### 6.4 产物

- `results/trade_list.csv`：逐笔（每次买卖）明细；
- `results/trade_summary.csv`：以 episode（一次完整开仓→平仓）为单位的汇总；
- `results/equity_curve.png`：净值曲线；
- `data/signals_log.csv`：每次入场信号当时的因子快照（供归因使用）；
- 终端打印：总收益、Sharpe、最大回撤、胜率等。

## 7. 归因分析（tools/attribution.py）

**职责**：把交易明细 + 信号日志 join 起来，从五个角度评估策略。

输入两份：`results/trade_summary.csv`（被改名为 `trade_log` 在内部使用）+ `data/signals_log.csv`。
输出到 `reports/`：

1. **trade_profile**：按收益分桶（大盈/小盈/持平/小亏/大亏）统计因子均值、分位；
2. **sector_winrate**：按申万一级行业统计交易数、胜率、平均收益；
3. **factor_alpha**：每个因子的 IC（Spearman）与多空分组超额；
4. **E-B / E-C profile**：进场信号 vs 卖出信号、进场 vs 平仓的属性对比；
5. **summary 表**：Top-N 关键发现摘要。

输出目录由 `config.attribution_report_dir` 控制。

## 8. 交易验证（tools/verify_trades.py）

**职责**：独立工具，不依赖回测产物以外的状态，逐 episode 校验：

- **L1 一致性**：买入笔数 == add_count + 1；shares 累计相等；avg_cost / return_pct
  与原始明细一致；take_profit_1 必须早于 take_profit_2；MA25 止损前提是已触发过 TP1。
- **L1 信号合规**：每笔 initial_buy / add_on 在执行日（即信号日，因 set_coc=True）
  必须满足上文 6.1 的 5 条入场条件；卖出端同理校验。
- **当前状态**：196 个 episode 全部通过买入/卖出双向合规校验。

## 9. 配置文件（config.json）核心字段

| 字段 | 说明 |
|---|---|
| `tushare_token` | Tushare API token |
| `start_date / end_date` | 数据下载区间 |
| `backTest_Start_data / backTest_end_data` | 回测区间 |
| `initial_cash` | 初始资金 |
| `max_positions` | 最大持仓数（决定单笔仓位） |
| `commission_rate / stamp_duty` | 佣金率 / 印花税率 |
| `dea_lookback_days` | 入场条件④的回看天数 |
| `take_profit_1_pct / take_profit_2_pct` | 两级止盈阈值 |
| `atr_period / atr_multiplier` | ATR 止盈参数 |
| `take_profit_min_pct / take_profit_max_pct` | ATR 止盈截断范围 |
| `index_codes` | 股票池来源指数（沪深300、中证500 等） |
| `sw_index_codes` | 申万一级行业指数列表 |
| `data_paths.*` | 各数据子目录路径 |
| `signals_log_path` | 入场信号日志输出路径 |
| `attribution_report_dir` | 归因报告输出目录 |

## 10. 运行命令速查

```bash
# 1. 一键拉取股票池 + 全部数据 + 计算指标 + 横截面分位
python my_strategy/download_all.py

# 2. 跑回测（产生 trade_list / trade_summary / signals_log / equity_curve）
python my_strategy/backtest.py

# 3. 跑归因分析（依赖步骤 2 的输出）
python my_strategy/tools/attribution.py

# 4. 验证交易合规
python my_strategy/tools/verify_trades.py

# 5. 跑测试
cd my_strategy && pytest
```
