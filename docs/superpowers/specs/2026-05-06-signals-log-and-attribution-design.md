# 信号日志 + 归因分析设计

**日期**：2026-05-06
**状态**：设计阶段，待实施

## 背景与动机

当前策略（MyStrategy）以"DEA 由负转正后的回调日"为入场点，在沪深 300 池上回测有结果，但存在三个核心问题：

1. **不知道为什么赚钱** —— 哪些行业、哪些类型股票贡献超额收益不清楚
2. **不知道哪些因子有效** —— 后续要做"选股打分排序"，但权重无依据
3. **样本规模有限** —— 沪深 300 只有 300 只候选，统计显著性不足

最终目标：**跑赢沪深 300、不盯盘、减少过拟合、增加实操性**。本期不直接动策略逻辑，先把"观察手段"建好——通过扩大数据维度 + 全样本信号记录 + 离线归因分析，为后续的打分模块、择时模块、过拟合验证提供数据依据。

## 范围

### 本期做（In Scope）

1. 新增 Tushare 基本面数据下载：`daily_basic`、`fina_indicator`、申万一级行业指数
2. `calc_indicators.py` 增量：把基本面字段和行业指数动量合并进每日 indicators CSV
3. 策略最小侵入改造：每次入场必要条件触发时，记录信号到 `signals_log.csv`（含全部候选因子值）
4. 回测后处理：把 `forward_return_5d/20d/60d` 回填进 signals_log
5. 新增 `tools/attribution.py`：盈亏画像（E-B）+ 因子贡献度（E-C）

### 本期不做（Out of Scope，已写入 todo.md）

- `scorer.py` 打分模块、行业去重、每日新开仓上限 → 等本期归因输出指导权重后再建
- 大盘择时锁仓（沪深 300 DEA 门槛等）→ 等基础数据和归因稳定后再加
- Walk-forward 过拟合验证、参数网格扫描 → 必须有"有效因子清单"作为前提，否则在噪音上做网格
- Brinson 收益拆解（E-A）→ 复杂度高、实操指导弱

## 数据层

### 新增数据源

| 数据 | Tushare 接口 | 落盘路径 | 关键字段 | 反未来函数处理 |
|---|---|---|---|---|
| 日频估值/市值 | `daily_basic` | `data/daily_basic/{ts_code}.csv` | `pe_ttm, pb, total_mv, circ_mv, turnover_rate` | 按 `trade_date` 对齐，无未来函数 |
| 季度财务指标 | `fina_indicator` | `data/fina/{ts_code}.csv` | `roe, roe_yearly, netprofit_yoy, grossprofit_margin` | **必须用 `ann_date`（公告日）做生效日**，不可用 `end_date`（报告期末），否则未来函数泄漏 |
| 申万一级行业指数 | `index_daily` (`801010.SI` 等 28 个) | `data/sw_index/{index_code}.csv` | OHLCV | 直接用 |

### 实现脚本

新增 `src/downloader_extra.py`：
- 复用现有 `downloader.py` 的限速、分块、跳过已下载逻辑
- 三个独立函数 `download_daily_basic / download_fina_indicator / download_sw_index`
- 链式调用：可在 `download_all.py` 完成后自动触发

### 指标计算改造

分两步进行：

**第 1 步：`calc_indicators.py` 增量（单股票内可计算的）**

新增列：
- 基本面（来自 `daily_basic` + `fina_indicator` 的最近一期 `ann_date <= 当日`）：
  - `pe_ttm, pb, total_mv, roe, netprofit_yoy`
- 单股票内可算的因子：
  - `factor_momentum_60d` = 过去 60 日涨跌幅
  - `factor_ma60_dist` = (close - ma60) / ma60
  - `factor_macd_strength` = DEA 当日值
- 所属行业指数动量（需要预先读对应申万指数 CSV）：
  - `sector_momentum_60d` = 该股所在申万一级行业指数过去 60 日涨跌幅

**第 2 步：新增 `src/build_cross_section_pct.py`（跨股票聚合）**

全市场分位数必须做横截面聚合，单股票视角下算不出。

流程：
1. 读取所有股票的 indicators CSV（第 1 步产出）
2. 按 `date` 分组，对每个因子列 `factor_*` 计算当日全市场百分位排名（0~1）
3. 把 `pct_pe, pct_pb, pct_roe, pct_netprofit_yoy, pct_momentum_60d, pct_ma60_dist, pct_sector_momentum_60d` 写回各股票 indicators CSV（merge by date）

下游 `backtest.py` 仍按现有方式读单股票 CSV，无变化。

**Pipeline 链**：
```
downloader.py → downloader_extra.py → calc_indicators.py → build_cross_section_pct.py → backtest.py
```

### 已知偏差

**行业映射使用当前快照**（现有 `stock_sector.csv`），不引入历史成分股。

理由：
- A 股一级行业（28 个）变更率极低，估计 >90% 的股票从上市到今天行业未变
- 行业**指数曲线本身**由申万维护、动态调整成分，无未来函数
- 错位仅在"股票→行业"映射上（少数借壳/重组/转型股票），错误是**噪音**而非**偏差**——不会系统性偏向赚钱方向
- 升级到 Tushare `index_member` 拿历史成分股开发量翻倍，性价比低

如果归因结果显示"行业动量"是关键因子，再考虑升级。

## 策略改造（最小侵入）

不动现有入场逻辑（5 条必要条件）、不动现有卖出逻辑（MA60 止损 / MA25 清仓 / ATR 止盈 / 加仓）。

唯一新增：**信号记录**

### `signals_log` 写入位置

在 [strategy.py:314-345](../../../my_strategy/src/strategy.py#L314-L345) 入场必要条件全部通过、调用 `self.buy()` 之前，写一条记录到 `self.signals_log` 列表。

如果由于"持仓数 ≥ max_positions"或"现金不足"导致无法买入，**仍记录信号但标记 `was_bought=False, skip_reason='no_capacity'`**。

### `signals_log.csv` 字段

| 字段 | 含义 |
|---|---|
| `date` | 信号触发日 |
| `ts_code` | 股票代码 |
| `sector` | 申万一级行业（当前快照） |
| `close, ma25, ma60, dea, atr` | 当日策略相关原值 |
| `factor_momentum_60d` | 过去 60 日涨跌幅 |
| `factor_ma60_dist` | (close - ma60) / ma60 |
| `factor_macd_strength` | DEA 绝对值或归一化值 |
| `factor_roe` | 最近一期 ROE（按 ann_date 对齐） |
| `factor_pe_ttm` | 当日 PE_TTM |
| `factor_netprofit_yoy` | 最近一期净利润同比 |
| `factor_sector_momentum_60d` | 所属行业指数过去 60 日涨跌幅 |
| `pct_*` | 上述因子的全市场分位数 |
| `was_bought` | 是否实际下单 |
| `skip_reason` | 未下单的原因（`no_capacity` / 空字符串） |
| `forward_return_5d/20d/60d` | 信号触发后 N 个交易日的真实收益（**回测全部跑完后回填**） |

### Forward Return 回填

`backtest.py` 在 cerebro.run() 完成后、写出 CSV 之前，对 `signals_log` 的每条记录回填三个 forward_return 字段。来源是该 ts_code 的原始 indicators CSV（已在内存）。

只用于离线分析，不进 next() 决策——无未来函数风险。

## 归因脚本

### `tools/attribution.py`

输入：
- `signals_log.csv`（本期产出）
- `trade_log.csv`（现有产出）

输出三份报告，写到 `reports/`：

#### E-B：盈亏画像（核心）

直接对应 todo.md "亏得最多和最少的各十个，看能找规律"。

把 `trade_log` 中的交易按 `return_pct` 分桶（大盈 >10% / 小盈 0~10% / 持平 ±0% / 小亏 -10~0% / 大亏 <-10%），关联回 `signals_log` 拿入场时的因子值，每个桶统计：
- 各因子的均值、中位数、25/75 分位
- 行业分布
- 入场时距 MA60 距离的分布
- 持仓天数分布

输出：
- `reports/trade_profile.csv` —— 数值表
- `reports/trade_profile_top_bottom.csv` —— 收益最高 10 笔 vs 最差 10 笔的详细对比
- `reports/sector_winrate.csv` —— 按行业分组的胜率/平均收益（todo.md "行业胜率信息汇总"）

#### E-C：因子贡献度模拟

对 `signals_log` 全样本（不依赖 trade_log，避免现有策略的容量约束影响样本）：

1. 对每个因子，**单独以该因子排序取每日 Top-3**，计算这组假想交易的 forward_return_20d 平均值
2. 与"全部信号都买"的基准 forward_return_20d 平均值对比，超额部分即该因子的 alpha 贡献
3. 同时输出该因子在不同分位数的胜率（前 20% 信号 vs 后 20% 信号的事后表现差异）

输出：
- `reports/factor_alpha.csv` —— 每个因子独立的超额收益、信息系数（IC）、Top-Bottom spread

#### 不做（本期）

- E-A Brinson 拆解（推迟）

## 配置项

`my_strategy/config.json` 新增：

```json
{
  "data_paths": {
    "daily_basic_dir": "data/daily_basic",
    "fina_indicator_dir": "data/fina",
    "sw_index_dir": "data/sw_index",
    "stock_sector_csv": "data/stock_sector.csv"
  },
  "signals_log_path": "data/signals_log.csv",
  "attribution_report_dir": "reports"
}
```

## 演进路线

```
本期：数据 + signals_log + attribution.py
   ↓ （归因输出"有效因子清单 + 初步权重感觉"）
下一版：scorer.py + 行业去重 + 每日新开仓上限 + scorer_enabled 开关
   ↓ （扩池 + 排序后实测，建立"参数候选清单"）
再下一版：择时锁仓（沪深 300 DEA 门槛 + 条件列表 + 开关）
   ↓ （主链路稳定）
更后版本：walk-forward + param_sweep 过拟合验证
   ↓ （已知有效因子和参数后做稳健性筛选）
长期：E-A Brinson 拆解 / 历史成分股升级 / 中证500/1000 验证
```

每一阶段都依赖上一阶段的输出，避免凭空拍脑袋。

## 文件清单

新增：
- `my_strategy/src/downloader_extra.py`
- `my_strategy/src/build_cross_section_pct.py`
- `my_strategy/tools/attribution.py`
- `my_strategy/data/daily_basic/` 目录
- `my_strategy/data/fina/` 目录
- `my_strategy/data/sw_index/` 目录
- `my_strategy/data/signals_log.csv`（运行时产出）
- `my_strategy/reports/` 目录（运行时产出）

修改：
- `my_strategy/src/calc_indicators.py` —— 合并基本面 + 行业动量 + 全市场分位数
- `my_strategy/src/strategy.py` —— 入场条件通过后写 signals_log
- `my_strategy/backtest.py` —— 回测完成后回填 forward_return 并写 signals_log.csv
- `my_strategy/config.json` —— 新增数据路径配置
- `my_strategy/download_all.py` —— 链式调用 downloader_extra

不动：
- 现有入场/卖出/加仓逻辑（[strategy.py](../../../my_strategy/src/strategy.py)）
- 现有 trade_log / order_log / position_count_log 输出
