# 进场质量统计扩展：市值 / 周KDJ / 周MACD区间 / 月MACD区间

**日期**：2026-05-05  
**状态**：已确认，待实现

---

## 背景

现有 `_print_entry_quality_stats` 已统计日线维度的 MA 排列、日线 MACD 区间、日线 KDJ_J 分桶、距 MA60 距离、行业 Top10。用户希望新增四个维度：进场时的流通市值、周线 KDJ_J、周线 MACD 区间、月线 MACD 区间，以便从更大周期视角评估进场质量。

---

## 方案选择

选用**方案 A**：新字段直接追加到 `_indicators.csv`，不新增文件类型。  
- `downloader.py` 负责拉取额外数据  
- `calc_indicators.py` 负责计算并写入 `_indicators.csv`  
- `backtest.py` 的 `_enrich_trade_summary` 读新列，`_print_entry_quality_stats` 新增统计块  

---

## 数据流

```
downloader.py
  download_stock()          ← 现有，新增：merge daily_basic.circ_mv 到原始 CSV
  download_weekly()         ← 新增，存 {ts_code}_weekly.csv
  download_monthly()        ← 新增，存 {ts_code}_monthly.csv

calc_indicators.py
  compute_indicators(df)    ← 现有，新增：circ_mv 万元→亿元
  compute_weekly_monthly_indicators(ts_code, df, data_dir)  ← 新增
    读 _weekly.csv → 计算周线 KDJ_J + MACD → 分类 week_macd_zone
    读 _monthly.csv → 计算月线 MACD → 分类 month_macd_zone
    merge 回日线 df，ffill 前向填充
  _indicators.csv 新增列：circ_mv, week_kdj_j, week_macd_zone, month_macd_zone

backtest.py
  _enrich_trade_summary()   ← 新增四列赋值：entry_circ_mv / entry_week_kdj_j /
                               entry_week_macd_zone / entry_month_macd_zone
  _print_entry_quality_stats() ← 新增四个统计块
```

---

## 详细设计

### 1. `downloader.py`

#### 1.1 修改 `download_stock`

在现有 `pro_bar` 拼接完成后，追加一次 `daily_basic` 调用：

```python
basic = pro.daily_basic(
    ts_code=ts_code,
    start_date=start_date,
    end_date=end_date,
    fields='trade_date,circ_mv',
)
basic['trade_date'] = pd.to_datetime(basic['trade_date'])
df = df.merge(basic, on='trade_date', how='left')
```

最终保存列：`trade_date, open, high, low, close, volume, amount, pct_chg, circ_mv`

#### 1.2 新增 `download_weekly(ts_code, start_date, end_date, data_dir)`

```python
# 调用 pro_bar(freq='W')，按年切片，存 {ts_code}_weekly.csv
# 保存列：trade_date, open, high, low, close
```

复用 `_year_chunks`，每段调用后 `time.sleep(0.2)`。文件全量重写。

#### 1.3 新增 `download_monthly(ts_code, start_date, end_date, data_dir)`

同 `download_weekly`，`freq='M'`，存 `{ts_code}_monthly.csv`。

#### 1.4 `main()` 调用位置

```python
for ts_code in stocks:
    download_stock(...)       # 已含 circ_mv
    download_weekly(...)      # 新增
    download_monthly(...)     # 新增
```

---

### 2. `calc_indicators.py`

#### 2.1 修改 `compute_indicators(df)`

在函数末尾追加：

```python
if 'circ_mv' in df.columns:
    df['circ_mv'] = (df['circ_mv'] / 10000).round(2)  # 万元 → 亿元
```

#### 2.2 新增 `compute_weekly_monthly_indicators(ts_code, df_daily, data_dir)`

**周线部分**：
1. 读 `{ts_code}_weekly.csv`
2. 计算 KDJ_J（与日线相同：9日RSV → K/D/J，ewm com=2）
3. 计算 MACD（与日线相同：EMA12/26 → DIF → DEA → MACD）
4. 用 `_classify_macd_zone` 生成 `week_macd_zone`
5. merge 到日线（left join on `trade_date`），`ffill()` 前向填充 `week_kdj_j` / `week_macd_zone`

**月线部分**：
1. 读 `{ts_code}_monthly.csv`
2. 计算 MACD，用 `_classify_macd_zone` 生成 `month_macd_zone`
3. merge + ffill

**返回值**：带新四列的日线 DataFrame

#### 2.3 `main()` 调用位置

```python
result = compute_indicators(df)
result = compute_weekly_monthly_indicators(ts_code, result, data_dir)
result.to_csv(dst, index=False)
```

若 `_weekly.csv` 或 `_monthly.csv` 不存在，对应列填 `None`，不报错。

---

### 3. `backtest.py`

#### 3.1 修改 `_enrich_trade_summary`

在现有 `entry_date in ind_df.index` 分支里，追加四列赋值：

```python
entry_circ_mv       = float(r['circ_mv'])        if 'circ_mv' in ind_df.columns and pd.notna(r.get('circ_mv')) else None
entry_week_kdj_j    = float(r['week_kdj_j'])     if 'week_kdj_j' in ind_df.columns and pd.notna(r.get('week_kdj_j')) else None
entry_week_macd_zone  = r.get('week_macd_zone')  if 'week_macd_zone' in ind_df.columns else None
entry_month_macd_zone = r.get('month_macd_zone') if 'month_macd_zone' in ind_df.columns else None
```

在 `else`（entry_date 不在索引中）分支里同样赋 `None`。

#### 3.2 修改 `_print_entry_quality_stats`

在现有 KDJ_J 分桶块之后，新增四个块：

**市值分桶**
- 列：`entry_circ_mv`
- 分桶：`(-inf, 50] / (50,100] / (100,300] / (300,500] / (500,1000] / (1000, inf)`
- 标签：`<50亿 / 50-100亿 / 100-300亿 / 300-500亿 / 500-1000亿 / >1000亿`
- 输出列：档位 / 笔数 / 笔数占比 / 胜率 / 平均收益

**周 KDJ_J 分桶**
- 列：`entry_week_kdj_j`
- 分桶与日线 KDJ_J 相同：`<20 / 20-50 / 50-80 / >80`

**周 MACD 区间**
- 列：`entry_week_macd_zone`
- 直接按值分组，输出：区间0/1/2/3 × 笔数/胜率/平均收益

**月 MACD 区间**
- 列：`entry_month_macd_zone`
- 同周 MACD 区间

---

## `_indicators.csv` 新增列一览

| 列名 | 来源 | 说明 |
|------|------|------|
| `circ_mv` | `daily_basic` | 流通市值（亿元） |
| `week_kdj_j` | 周线计算 | 当周 KDJ_J 值 |
| `week_macd_zone` | 周线计算 | 当周 MACD 区间（区间0/1/2/3） |
| `month_macd_zone` | 月线计算 | 当月 MACD 区间（区间0/1/2/3） |

---

## 边界条件

- `daily_basic` 返回空：`circ_mv` 列全为 NaN，统计时跳过该块（与现有 KDJ 处理一致）
- `_weekly.csv` / `_monthly.csv` 不存在：`compute_weekly_monthly_indicators` 静默跳过，对应列填 NaN
- 周/月线数据不足（K线数 < 计算窗口）：KDJ/MACD 值为 NaN，merge 后 ffill 无值则保持 NaN
- `_enrich_trade_summary` 读不到对应列：检查 `column in ind_df.columns`，赋 None 而非报错

---

## 涉及文件

| 文件 | 改动类型 |
|------|---------|
| `my_strategy/downloader.py` | 修改 `download_stock`，新增 `download_weekly` / `download_monthly` |
| `my_strategy/calc_indicators.py` | 修改 `compute_indicators`，新增 `compute_weekly_monthly_indicators` |
| `my_strategy/backtest.py` | 修改 `_enrich_trade_summary`，修改 `_print_entry_quality_stats` |
