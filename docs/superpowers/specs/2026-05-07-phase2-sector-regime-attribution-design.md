# Phase 2 — 行业指数多空环境快照与归因（设计文档）

**日期**：2026-05-07
**前置**：Phase 1（HS300 + 个股多空快照与归因）已完成
**作者**：fuyuoo + Claude

## 1. 目标

在每笔交易入场时，记录该股票所属申万一级行业指数的"多空环境快照"（共 6 个 flag/数值），落入 `trade_summary.csv`；并在归因阶段产出 8 张新报告，回答"行业多空环境是否能解释/过滤入场胜率与收益"，特别是回答：

> 对于 Phase 1 已发现最强的"个股多头排列"信号，叠加"行业也多头排列"是否能进一步提升胜率？

## 2. 架构（3 个串行子项目）

```
[子项目 1] 数据准备           [子项目 2] 行业指标计算         [子项目 3] 入场归因
─────────────────         ─────────────────────       ──────────────────
1. 下载 31 个申万一级       1. 重构 calc_indicators.py    1. backtest.py 加载
   行业指数 daily/weekly/    为参数化（groups 列表          sector_indicators
   monthly                   控制计算哪些指标）         2. _compute_regime_flags
2. index_member API        2. config.json 加              扩展 sector_row 入参，
   反查 → stock_sector.csv   indicator_profiles.stock     输出 6 个新 flag
   新增 sw_index_code 列     和 .sector                 3. attribution.py 加 8
                           3. --mode sector 跑出           张新报告
                              data/sw_indicators/        4. 文档/CHANGELOG 更新
```

**串行依赖**：1 → 2 → 3，每个子项目独立验收。代码层不并行（保持简单）。

## 3. 子项目 1：数据准备

### 3.1 SW 行情下载（全部走 Tushare 直拉）

| 频率 | Tushare 接口 | 落盘路径 |
|---|---|---|
| daily | `pro.sw_daily(ts_code=...)`（现有 `download_sw_index`） | `data/sw_index/{sw_code}.csv` |
| weekly | `ts.pro_bar(ts_code, freq='W', asset='I')` | `data/sw_weekly/{sw_code}.csv` |
| monthly | `ts.pro_bar(ts_code, freq='M', asset='I')` | `data/sw_monthly/{sw_code}.csv` |

**已验证**：`pro_bar(asset='I', freq='W'/'M')` 返回 SW 行业周/月线，列结构与股票一致。

**实现**：在 `downloader_extra.py` 加 `download_sw_bars(sw_code, freq, ...)` 函数，仿造现有 `download_bars()`，唯一差异是加 `asset='I'`。`download_all.py` 在循环 `cfg['sw_index_codes']` 时除调 `download_sw_index`（日线）再调两次 `download_sw_bars` 拉周/月线。

### 3.2 ts_code → sw_index_code 映射

```python
mapping = {}  # ts_code -> sw_index_code
for sw_code in cfg['sw_index_codes']:        # 31 个一级行业
    members = pro.index_member(index_code=sw_code)
    current = members[members['out_date'].isna()]   # 仅取仍在册的成分
    for ts_code in current['con_code'].unique():
        if ts_code in mapping and mapping[ts_code] != sw_code:
            raise ValueError(f"{ts_code} 同时属于 {mapping[ts_code]} 和 {sw_code}")
        mapping[ts_code] = sw_code

# 写回 stock_sector.csv，新增 sw_index_code 列
```

**关键决策**：
- **当前快照映射（非时变）**：取 `out_date IS NULL` 的当前成分。理由：SW 一级行业调整很少，回测期间稳定；时变映射代码复杂度大幅上升
- **覆盖率阈值**：
  - `<95%` → raise，停止管线
  - `95%-100%` → 打印未映射 ts_code 列表 + 数量，继续
  - `100%` → 静默通过
- **一对多冲突**：抛异常（按 CLAUDE.md 暴露异常原则）

### 3.3 验收标准

- ✅ `data/sw_index/`、`sw_weekly/`、`sw_monthly/` 各 31 个 CSV 文件
- ✅ 时间范围覆盖 `start_date=20000101 ~ end_date=20260101`
- ✅ `stock_sector.csv` 新增 `sw_index_code` 列，覆盖率 ≥ 95%
- ✅ 跑一遍 `download_all.py` 全程无静默 catch

## 4. 子项目 2：行业指标计算（参数化重构）

### 4.1 输出 schema

`data/sw_indicators/{sw_code}.csv` 列结构：

| 列 | 必需 | 说明 |
|---|---|---|
| `trade_date, open, high, low, close, volume, amount, pct_chg` | ✅ | 行情基础（来自 sw_index daily） |
| `ma25, ma60, ma144, ma180` | ✅ | 多头排列判定 |
| `dif, dea, macd` | ✅ | MACD（DIF > 0 flag 用） |
| `kdj_j` | ✅ | KDJ J 值（与股票对齐，留作未来用） |
| `week_macd_zone` | ✅ | 周线 MACD 区域（多头/空头/震荡） |
| `month_macd_zone` | ✅ | 月线 MACD 区域 |
| `factor_momentum_60d` | ✅ | 60 日涨跌幅 |

**不包含**：股票特有的基本面字段（`pe_ttm/pb/total_mv/circ_mv/roe/netprofit_yoy`）和 `factor_sector_momentum_60d`（行业自身套娃）。

### 4.2 参数化重构

把现有 `calc_indicators.py` 重构为两层：

**底层：纯函数 `compute_indicators(code, src_dirs, dst_dir, groups: list[str])`**

```python
GROUPS = [
    'ma',                       # ma25/60/144/180
    'macd',                     # dif/dea/macd
    'kdj',                      # kdj_j
    'week_macd',                # week_macd_zone
    'month_macd',               # month_macd_zone
    'fundamentals',             # pe_ttm/pb/total_mv/circ_mv/roe/netprofit_yoy
    'sector_momentum',          # factor_sector_momentum_60d (依赖 sw_index)
    'factor_momentum_60d',
    'factor_ma60_dist',
    'factor_macd_strength',
]

def compute_indicators(code, src_dirs, dst_dir, groups: list[str]):
    df = load_daily(code, src_dirs['daily'])
    if 'ma' in groups:        df = add_ma(df)
    if 'macd' in groups:      df = add_macd(df)
    if 'kdj' in groups:       df = add_kdj(df)
    if 'week_macd' in groups: df = add_week_macd_zone(df, src_dirs['weekly'], code)
    if 'month_macd' in groups:df = add_month_macd_zone(df, src_dirs['monthly'], code)
    if 'fundamentals' in groups:    df = merge_daily_basic_fina(df, ...)
    if 'sector_momentum' in groups: df = merge_sector_momentum(df, ...)
    # ... factor_* 同样模式
    df.to_csv(dst_dir / f'{code}.csv', index=False)
```

**上层：CLI `--mode` 从 config 读 profile**

```json
// config.json 新增
"indicator_profiles": {
  "stock":  ["ma", "macd", "kdj", "week_macd", "month_macd",
             "fundamentals", "sector_momentum",
             "factor_momentum_60d", "factor_ma60_dist", "factor_macd_strength"],
  "sector": ["ma", "macd", "kdj", "week_macd", "month_macd",
             "factor_momentum_60d"]
}
```

```bash
python -m my_strategy.src.calc_indicators --mode stock
python -m my_strategy.src.calc_indicators --mode sector
```

stock 模式 src_dirs 指向 `data/{daily,weekly,monthly}/`；sector 模式指向 `data/{sw_index,sw_weekly,sw_monthly}/`，dst 指向 `data/sw_indicators/`。

### 4.3 验收标准

- ✅ `compute_indicators` 纯函数实现，`groups` 列表参数控制
- ✅ `config.json` 新增 `indicator_profiles.stock` 和 `.sector`
- ✅ **重构回归测试通过**：对 3 只样本股（`000001.SZ`、`600000.SH`、`300750.SZ`）跑 `--mode stock`，输出与重构前 byte-for-byte 一致（diff 为空）
- ✅ `--mode sector` 产出 31 个 sw_indicators CSV
- ✅ 新增单元测试 `test_compute_indicators_groups`：传不同 groups 时输出列正确
- ✅ 抽样验证：`801010.SI` 某一交易日的 ma25/ma60 值与手动 pandas rolling(25/60).mean() 一致

## 5. 子项目 3：入场归因（Scope C 完整集）

### 5.1 trade_summary 新增 6 列

| 新列 | 来源 | 语义 | dtype |
|---|---|---|---|
| `entry_sector_bull_align` | `sector_row.ma25/60/144/180` | 行业指数日线多头排列 (`m25>m60>m144>m180`) | bool/None |
| `entry_sector_above_ma25` | `sector_row.close, ma25` | 行业指数站上 MA25 | bool/None |
| `entry_sector_dif_above_zero` | `sector_row.dif` | 行业 MACD DIF > 0 | bool/None |
| `entry_sector_week_macd_zone` | `sector_row.week_macd_zone` | 行业周线 MACD 区域（"多头"/"空头"/"震荡"） | str/None |
| `entry_sector_month_macd_zone` | `sector_row.month_macd_zone` | 行业月线 MACD 区域 | str/None |
| `entry_sector_momentum_60d` | `sector_row.factor_momentum_60d` | 行业 60 日涨跌幅 | float/NaN |

注：股票所属 SW 行业代码不另加列（已在 `stock_sector.csv` 中映射，归因时反查即可）。

### 5.2 backtest.py 改造

1. **加载阶段**：新增 `_load_sector_indicators(cfg)` 返回 `dict[sw_code → DataFrame]`（仿现有 HS300 加载）
2. **enrich 阶段** ([backtest.py:303](my_strategy/backtest.py#L303) 附近)：根据 `ts_code → sw_code` 映射 + 入场日期取 sector_row，传给 `_compute_regime_flags`
3. **`_compute_regime_flags` 签名扩展**：
   ```python
   def _compute_regime_flags(stock_row, hs300_row, sector_row):
       # 现有 4 个 flag 不变
       # 新增 6 个 entry_sector_* 计算
   ```

### 5.3 attribution.py 新增 8 张报告

| 报告 CSV | 桶定义 | 复用模板 |
|---|---|---|
| `sector_bull_align_stats.csv` | True/False/None 三桶 | 复制 `compute_hs300_bull_align_stats` |
| `sector_above_ma25_stats.csv` | True/False/None 三桶 | 复制 `compute_stock_above_ma25_stats` |
| `sector_dif_stats.csv` | True/False/None 三桶 | 复制 `compute_hs300_dif_stats` |
| `sector_week_macd_stats.csv` | "多头"/"空头"/"震荡" 三桶 | 复制 `compute_month_macd_stats` |
| `sector_month_macd_stats.csv` | 同上 | 同上 |
| `sector_momentum_60d_stats.csv` | **五分桶（quintile）** 数值 → 5 桶 | `_scan_bucket_aggregate` + 分桶函数 |
| `sector_industry_stats.csv` | 按 31 个 SW 一级行业（`sw_index_code`）分桶 | groupby 模式 |
| `sector_combo_stats.csv` | `entry_sector_bull_align × entry_stock_bull_align` 2×2 交叉表 | 复制 `compute_regime_combo_stats` |

**说明**：
- `sector_momentum_60d` 走五分桶而非 bool 阈值（信息量更大）
- combo 报告**只做 sector × stock**，不做 sector × HS300（避免组合爆炸 + 样本稀疏）

总计 reports 数量：20 → 28 张。

### 5.4 三态语义 + dtype 处理

5 个 bool/str flag 走 Phase 1 同款套路：
- 写入：`astype(object)` 保留 True/False/None 或 "多头"/None
- 读取：CSV → 三态还原（参照 commit `b32d377` 的 dtype 处理）
- 数值列 `entry_sector_momentum_60d` 走普通 float/NaN，不需特殊处理

### 5.5 测试覆盖

- `test_backtest.py` 加 `_compute_regime_flags(stock_row, hs300_row, sector_row)` 单元测试：6 个新 flag 各正负样例 + 缺数据时三态语义
- `test_attribution.py` 加 8 张新报告各 1-2 个核心单测（fixture trade_summary 覆盖典型行）
- `test_attribution_run.py` 的 `EXPECTED_FILES` 从 20 → 28

### 5.6 验收标准

- ✅ `trade_summary.csv` 新增 6 列，dtype 正确（5 个三态 object + 1 个 float）
- ✅ 8 张新报告生成，列结构与现有 stats 报告对齐（flag_value, count, win_rate, avg_return）
- ✅ 全部测试通过 (`pytest`)
- ✅ FEATURES.md §6 加 8 个条目，CHANGELOG.md 加新条目
- ✅ **回归验证**：真实回测 trade_summary 中 Phase 1 已有的 4 个 entry_hs300/stock flag 桶数与数值不变

## 6. 风险与开放问题

| 风险 | 缓解 |
|---|---|
| `calc_indicators.py` 重构破坏 stock 模式输出 | 4.3 的 byte-for-byte 回归测试 |
| Tushare API 限速导致下载半途中断 | 现有 `_call_with_timeout` + sleep 模式已处理；中断后可断点续传（CSV 已存在则跳过） |
| 5512 只股票中部分（北交所/退市/ST）不在 SW 一级成分内 | 覆盖率检查 + 阈值告警；未映射股票 sector flag 为 None（与现有 HS300 缺数据时一致） |
| SW 一级行业历史调整造成"曾在多个行业" | 映射构建时 `out_date IS NULL` 仅取当前在册；冲突 raise（理论上不应发生） |
| 31 个行业指数初始下载耗时（每个 daily+weekly+monthly = 93 次 API 调用） | 预计 5-10 分钟（按 500/min 限速），可接受；无需优化 |

## 7. 不在本设计范围内

- 时变成分映射（按入场日期查股票当时所属行业）— 复杂度高，Phase 2 用当前快照
- 行业 × HS300 组合表 — 避免组合爆炸，留作 Phase 3 视情况追加
- 行业层面的 DEA 距离指标 — 与 `entry_sector_dif_above_zero` 信息重叠，先看 dif > 0 是否有效再考虑细化
- 行业基本面字段（指数没有 PE/PB 等） — 跳过

## 8. 下一步

确认本设计后，由 writing-plans skill 生成实现计划（按 3 个子项目拆 Task，每个 Task 包含 TDD 红/绿/重构步骤）。
