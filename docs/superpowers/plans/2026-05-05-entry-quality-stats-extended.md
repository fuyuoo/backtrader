# 进场质量统计扩展实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在进场质量统计中新增四个维度：流通市值分桶、周 KDJ_J 分桶、周 MACD 区间、月 MACD 区间。

**Architecture:** downloader.py 新增下载周线/月线数据并在原始 CSV 中追加 circ_mv；calc_indicators.py 计算周/月指标并写入 _indicators.csv；backtest.py 读取新列并输出四个新统计块。三层各自独立，按顺序实现。

**Tech Stack:** Python 3, pandas, tushare, backtrader

---

## 文件变更一览

| 文件 | 变更 |
|------|------|
| `my_strategy/downloader.py` | 修改 `download_stock`（追加 circ_mv），新增 `download_weekly` / `download_monthly`，更新 `main()` |
| `my_strategy/calc_indicators.py` | 修改 `compute_indicators`（circ_mv 单位转换），新增 `compute_weekly_monthly_indicators`，更新 `main()` |
| `my_strategy/backtest.py` | 修改 `_enrich_trade_summary`（追加四列），修改 `_print_entry_quality_stats`（四个新统计块）|
| `my_strategy/test_indicators.py` | 新建：`compute_weekly_monthly_indicators` 的单元测试 |

---

## Task 1：修改 `download_stock` 追加 circ_mv

**Files:**
- Modify: `my_strategy/downloader.py`

- [ ] **Step 1：定位修改点**

打开 `my_strategy/downloader.py`，找到 `download_stock` 函数中的这一行：
```python
df = df[['trade_date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']]
```
这一行在 `_apply_qfq` 调用之后，`df.to_csv` 之前。

- [ ] **Step 2：在该行之前插入 daily_basic 调用**

将上述行替换为：
```python
basic_chunks = []
for seg_start, seg_end in _year_chunks(start_date, end_date):
    seg = pro.daily_basic(
        ts_code=ts_code,
        start_date=seg_start,
        end_date=seg_end,
        fields='trade_date,circ_mv',
    )
    if seg is not None and not seg.empty:
        basic_chunks.append(seg)
    time.sleep(0.2)
if basic_chunks:
    basic_df = pd.concat(basic_chunks, ignore_index=True)
    basic_df['trade_date'] = pd.to_datetime(basic_df['trade_date'])
    df = df.merge(basic_df, on='trade_date', how='left')
else:
    df['circ_mv'] = None
df = df[['trade_date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg', 'circ_mv']]
df.to_csv(csv_path, index=False)
```

- [ ] **Step 3：验证语法无误**

```powershell
cd my_strategy
python -c "import downloader; print('OK')"
```
期望输出：`OK`（无报错）

- [ ] **Step 4：Commit**

```powershell
git add my_strategy/downloader.py
git commit -m "feat: add circ_mv to download_stock via daily_basic"
```

---

## Task 2：新增 `download_weekly` / `download_monthly`，更新 `main()`

**Files:**
- Modify: `my_strategy/downloader.py`

- [ ] **Step 1：在 `download_index` 函数之前插入两个新函数**

```python
def download_weekly(ts_code, start_date, end_date, data_dir):
    """下载周线 OHLC，存为 {ts_code}_weekly.csv。"""
    csv_path = Path(data_dir) / f"{ts_code}_weekly.csv"
    chunks = []
    for seg_start, seg_end in _year_chunks(start_date, end_date):
        seg = ts.pro_bar(ts_code=ts_code, adj=None, freq='W',
                         start_date=seg_start, end_date=seg_end)
        if seg is not None and not seg.empty:
            chunks.append(seg)
        time.sleep(0.2)
    if not chunks:
        return
    df = pd.concat(chunks, ignore_index=True)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.drop_duplicates(subset='trade_date').sort_values('trade_date').reset_index(drop=True)
    df[['trade_date', 'open', 'high', 'low', 'close']].to_csv(csv_path, index=False)


def download_monthly(ts_code, start_date, end_date, data_dir):
    """下载月线 OHLC，存为 {ts_code}_monthly.csv。"""
    csv_path = Path(data_dir) / f"{ts_code}_monthly.csv"
    chunks = []
    for seg_start, seg_end in _year_chunks(start_date, end_date):
        seg = ts.pro_bar(ts_code=ts_code, adj=None, freq='M',
                         start_date=seg_start, end_date=seg_end)
        if seg is not None and not seg.empty:
            chunks.append(seg)
        time.sleep(0.2)
    if not chunks:
        return
    df = pd.concat(chunks, ignore_index=True)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.drop_duplicates(subset='trade_date').sort_values('trade_date').reset_index(drop=True)
    df[['trade_date', 'open', 'high', 'low', 'close']].to_csv(csv_path, index=False)
```

- [ ] **Step 2：在 `main()` 的股票循环里调用新函数**

找到 `main()` 中的股票循环：
```python
for i, ts_code in enumerate(stocks):
    try:
        download_stock(ts_code, cfg['start_date'], cfg['end_date'], data_dir)
        print(f"[{i+1}/{len(stocks)}] {ts_code} OK")
    except Exception as e:
        logging.error(f"{ts_code}: {e}")
        print(f"[{i+1}/{len(stocks)}] {ts_code} FAILED: {e}")
```

替换为：
```python
for i, ts_code in enumerate(stocks):
    try:
        download_stock(ts_code, cfg['start_date'], cfg['end_date'], data_dir)
        download_weekly(ts_code, cfg['start_date'], cfg['end_date'], data_dir)
        download_monthly(ts_code, cfg['start_date'], cfg['end_date'], data_dir)
        print(f"[{i+1}/{len(stocks)}] {ts_code} OK")
    except Exception as e:
        logging.error(f"{ts_code}: {e}")
        print(f"[{i+1}/{len(stocks)}] {ts_code} FAILED: {e}")
```

- [ ] **Step 3：验证语法无误**

```powershell
python -c "import downloader; print('OK')"
```
期望输出：`OK`

- [ ] **Step 4：Commit**

```powershell
git add my_strategy/downloader.py
git commit -m "feat: add download_weekly and download_monthly to downloader"
```

---

## Task 3：修改 `calc_indicators.py`

**Files:**
- Modify: `my_strategy/calc_indicators.py`
- Create: `my_strategy/test_indicators.py`

- [ ] **Step 1：先写单元测试（TDD）**

新建 `my_strategy/test_indicators.py`：

```python
import pandas as pd
import tempfile
from pathlib import Path
from calc_indicators import compute_indicators, compute_weekly_monthly_indicators


def _make_ohlc(n, start='2020-01-01'):
    dates = pd.date_range(start, periods=n, freq='B')
    import numpy as np
    np.random.seed(42)
    close = 10 + np.cumsum(np.random.randn(n) * 0.1)
    return pd.DataFrame({
        'trade_date': dates,
        'open': close * 0.99,
        'high': close * 1.01,
        'low': close * 0.98,
        'close': close,
        'volume': 1000,
        'amount': close * 1000,
        'pct_chg': 0.0,
        'circ_mv': 5_000_000.0,  # 5,000,000 万元 = 500 亿元
    })


def test_circ_mv_conversion():
    df = _make_ohlc(100)
    result = compute_indicators(df)
    assert 'circ_mv' in result.columns
    # 5,000,000 万元 ÷ 10000 → 500.0 亿元
    assert abs(result['circ_mv'].iloc[-1] - 500.0) < 0.01


def test_weekly_monthly_columns_added():
    df = _make_ohlc(300)
    result = compute_indicators(df)

    with tempfile.TemporaryDirectory() as tmpdir:
        # 生成周线和月线 CSV
        weekly = df.set_index('trade_date')['close'].resample('W').last().dropna().reset_index()
        weekly.columns = ['trade_date', 'close']
        weekly['open'] = weekly['close'] * 0.99
        weekly['high'] = weekly['close'] * 1.01
        weekly['low'] = weekly['close'] * 0.98
        weekly.to_csv(Path(tmpdir) / 'TEST.SH_weekly.csv', index=False)

        monthly = df.set_index('trade_date')['close'].resample('ME').last().dropna().reset_index()
        monthly.columns = ['trade_date', 'close']
        monthly['open'] = monthly['close'] * 0.99
        monthly['high'] = monthly['close'] * 1.01
        monthly['low'] = monthly['close'] * 0.98
        monthly.to_csv(Path(tmpdir) / 'TEST.SH_monthly.csv', index=False)

        out = compute_weekly_monthly_indicators('TEST.SH', result, tmpdir)

    assert 'week_kdj_j' in out.columns
    assert 'week_macd_zone' in out.columns
    assert 'month_macd_zone' in out.columns
    # 非全 NaN（有足够数据预热后应有值）
    assert out['week_kdj_j'].notna().any()
    assert out['week_macd_zone'].notna().any()
    assert out['month_macd_zone'].notna().any()


def test_missing_weekly_monthly_files():
    df = _make_ohlc(100)
    result = compute_indicators(df)
    with tempfile.TemporaryDirectory() as tmpdir:
        out = compute_weekly_monthly_indicators('NOFILE.SH', result, tmpdir)
    assert 'week_kdj_j' in out.columns
    assert out['week_kdj_j'].isna().all()
    assert out['week_macd_zone'].isna().all()
    assert out['month_macd_zone'].isna().all()


if __name__ == '__main__':
    test_circ_mv_conversion()
    test_weekly_monthly_columns_added()
    test_missing_weekly_monthly_files()
    print("ALL TESTS PASSED")
```

- [ ] **Step 2：运行测试，确认失败**

```powershell
cd my_strategy
python test_indicators.py
```
期望：`AttributeError` 或 `ImportError`（`compute_weekly_monthly_indicators` 尚未定义）

- [ ] **Step 3：修改 `compute_indicators`，追加 circ_mv 转换**

在 `compute_indicators` 函数末尾、`return df` 之前追加：
```python
if 'circ_mv' in df.columns:
    df['circ_mv'] = (df['circ_mv'] / 10000).round(2)
```

- [ ] **Step 4：新增 `compute_weekly_monthly_indicators` 函数**

在 `compute_indicators` 函数之后插入：

```python
def compute_weekly_monthly_indicators(ts_code, df_daily, data_dir):
    """读取周线/月线 CSV，计算 KDJ_J 和 MACD 区间，merge 回日线 df（ffill 填充）。"""
    data_dir = Path(data_dir)
    df = df_daily.copy()

    def _kdj_j(ohlc):
        low9 = ohlc['low'].rolling(9, min_periods=9).min()
        high9 = ohlc['high'].rolling(9, min_periods=9).max()
        rsv = ((ohlc['close'] - low9) / (high9 - low9).replace(0, 1) * 100).clip(0, 100)
        k = rsv.ewm(com=2, adjust=False).mean()
        d = k.ewm(com=2, adjust=False).mean()
        return (3 * k - 2 * d).round(2)

    def _macd_zone(ohlc):
        ema12 = ohlc['close'].ewm(span=12, adjust=False).mean()
        ema26 = ohlc['close'].ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        macd = 2 * (dif - dea)

        def _zone(row):
            m, di, de = row['macd'], row['dif'], row['dea']
            if pd.isna(m) or m <= 0:
                return '区间0'
            if m > di and m > de:
                return '区间1'
            if di > m and de > m:
                return '区间3'
            return '区间2'

        return pd.DataFrame({'macd': macd, 'dif': dif, 'dea': dea}).apply(_zone, axis=1)

    weekly_path = data_dir / f"{ts_code}_weekly.csv"
    if weekly_path.exists():
        wdf = pd.read_csv(weekly_path, parse_dates=['trade_date']).sort_values('trade_date')
        wdf['week_kdj_j'] = _kdj_j(wdf)
        wdf['week_macd_zone'] = _macd_zone(wdf)
        wdf = wdf[['trade_date', 'week_kdj_j', 'week_macd_zone']]
        df = df.merge(wdf, on='trade_date', how='left')
        df['week_kdj_j'] = df['week_kdj_j'].ffill()
        df['week_macd_zone'] = df['week_macd_zone'].ffill()
    else:
        df['week_kdj_j'] = None
        df['week_macd_zone'] = None

    monthly_path = data_dir / f"{ts_code}_monthly.csv"
    if monthly_path.exists():
        mdf = pd.read_csv(monthly_path, parse_dates=['trade_date']).sort_values('trade_date')
        mdf['month_macd_zone'] = _macd_zone(mdf)
        mdf = mdf[['trade_date', 'month_macd_zone']]
        df = df.merge(mdf, on='trade_date', how='left')
        df['month_macd_zone'] = df['month_macd_zone'].ffill()
    else:
        df['month_macd_zone'] = None

    return df
```

- [ ] **Step 5：更新 `main()` 调用链**

找到 `main()` 中的：
```python
result = compute_indicators(df)
result.to_csv(dst, index=False)
```
替换为：
```python
result = compute_indicators(df)
result = compute_weekly_monthly_indicators(ts_code, result, data_dir)
result.to_csv(dst, index=False)
```

- [ ] **Step 6：运行测试，确认全部通过**

```powershell
python test_indicators.py
```
期望输出：`ALL TESTS PASSED`

- [ ] **Step 7：Commit**

```powershell
git add my_strategy/calc_indicators.py my_strategy/test_indicators.py
git commit -m "feat: add circ_mv conversion and compute_weekly_monthly_indicators"
```

---

## Task 4：修改 `_enrich_trade_summary`（backtest.py）

**Files:**
- Modify: `my_strategy/backtest.py`

- [ ] **Step 1：在 `if not ind_path.exists():` 分支的 None 赋值里追加四列**

找到该分支（约第 163–171 行），在已有的 `row['macd_zone'] = None` 之后追加：
```python
row['entry_circ_mv'] = None
row['entry_week_kdj_j'] = None
row['entry_week_macd_zone'] = None
row['entry_month_macd_zone'] = None
```

- [ ] **Step 2：在 `if entry_date in ind_df.index:` 分支的赋值块追加四列**

找到该分支中已有的赋值（`row['ma_alignment']` / `row['macd_zone']`），在其之后追加：
```python
row['entry_circ_mv'] = (
    round(float(r['circ_mv']), 2)
    if 'circ_mv' in ind_df.columns and pd.notna(r.get('circ_mv'))
    else None
)
row['entry_week_kdj_j'] = (
    round(float(r['week_kdj_j']), 2)
    if 'week_kdj_j' in ind_df.columns and pd.notna(r.get('week_kdj_j'))
    else None
)
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
```

- [ ] **Step 3：在 `else`（entry_date 不在索引）分支追加四列**

找到该 else 分支（已有 `row['ma_alignment'] = None` 等），在其之后追加：
```python
row['entry_circ_mv'] = None
row['entry_week_kdj_j'] = None
row['entry_week_macd_zone'] = None
row['entry_month_macd_zone'] = None
```

- [ ] **Step 4：验证语法**

```powershell
python -c "import backtest; print('OK')"
```
期望输出：`OK`

- [ ] **Step 5：Commit**

```powershell
git add my_strategy/backtest.py
git commit -m "feat: enrich trade summary with circ_mv, week_kdj_j, week/month macd_zone"
```

---

## Task 5：在 `_print_entry_quality_stats` 新增四个统计块

**Files:**
- Modify: `my_strategy/backtest.py`

- [ ] **Step 1：找到插入位置**

在 `_print_entry_quality_stats` 中，找到现有 KDJ_J 分桶块末尾的：
```python
        completed = completed.drop(columns=['_kdj_bucket'])
```
在这一行之后、`# MA60 距离分桶` 注释之前插入四个新块。

- [ ] **Step 2：插入市值分桶块**

```python
    # 市值分桶
    if 'entry_circ_mv' in completed.columns and completed['entry_circ_mv'].notna().any():
        print("\n--- 市值分桶（流通市值，亿元）---")
        bins = [0, 50, 100, 300, 500, 1000, float('inf')]
        labels = ['<50亿', '50-100亿', '100-300亿', '300-500亿', '500-1000亿', '>1000亿']
        completed['_mv_bucket'] = pd.cut(completed['entry_circ_mv'], bins=bins, labels=labels)
        total_n = len(completed)
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
```

- [ ] **Step 3：插入周 KDJ_J 分桶块**

```python
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
```

- [ ] **Step 4：插入周 MACD 区间块**

```python
    # 周 MACD 区间
    if 'entry_week_macd_zone' in completed.columns and completed['entry_week_macd_zone'].notna().any():
        print("\n--- 周 MACD 区间 ---")
        grp = _group_stats('entry_week_macd_zone')
        print(f"{'周MACD区间':<10}{'笔数':>6}{'胜率':>8}{'平均收益':>10}")
        print("-" * 36)
        for _, row in grp.sort_values('entry_week_macd_zone').iterrows():
            print(f"{str(row['entry_week_macd_zone']):<10}{int(row['笔数']):>6}"
                  f"{row['胜率']:>7.1f}%{row['平均收益']:>+9.2f}%")
```

- [ ] **Step 5：插入月 MACD 区间块**

```python
    # 月 MACD 区间
    if 'entry_month_macd_zone' in completed.columns and completed['entry_month_macd_zone'].notna().any():
        print("\n--- 月 MACD 区间 ---")
        grp = _group_stats('entry_month_macd_zone')
        print(f"{'月MACD区间':<10}{'笔数':>6}{'胜率':>8}{'平均收益':>10}")
        print("-" * 36)
        for _, row in grp.sort_values('entry_month_macd_zone').iterrows():
            print(f"{str(row['entry_month_macd_zone']):<10}{int(row['笔数']):>6}"
                  f"{row['胜率']:>7.1f}%{row['平均收益']:>+9.2f}%")
```

- [ ] **Step 6：验证语法**

```powershell
python -c "import backtest; print('OK')"
```
期望输出：`OK`

- [ ] **Step 7：用合成数据冒烟测试统计输出**

```powershell
python -c "
import pandas as pd
from backtest import _print_entry_quality_stats

rows = []
import random; random.seed(1)
for i in range(50):
    rows.append({
        'status': 'completed',
        'return_pct': random.uniform(-5, 10),
        'gross_pnl': random.uniform(-500, 1000),
        'entry_circ_mv': random.choice([30, 70, 150, 400, 700, 1500]),
        'entry_week_kdj_j': random.uniform(-10, 110),
        'entry_week_macd_zone': random.choice(['区间0','区间1','区间2','区间3']),
        'entry_month_macd_zone': random.choice(['区间0','区间1','区间2','区间3']),
        'ma_alignment': '全多头',
        'macd_zone': '区间1',
        'entry_kdj_j': 50.0,
        'entry_ma60_dist_pct': 2.0,
    })
df = pd.DataFrame(rows)
_print_entry_quality_stats(df)
print('SMOKE TEST PASSED')
"
```
期望：打印出四个新统计块，最后一行 `SMOKE TEST PASSED`。

- [ ] **Step 8：Commit**

```powershell
git add my_strategy/backtest.py
git commit -m "feat: add circ_mv / week KDJ / week+month MACD zone stats to entry quality output"
```

---

## 完整流程验证

重新下载数据并跑回测前，需先按顺序执行：

```powershell
cd my_strategy
# 1. 重新下载（拉取 circ_mv、周线、月线）
python downloader.py

# 2. 重新计算指标（写入 _indicators.csv 的四个新列）
python calc_indicators.py

# 3. 回测（输出新统计块）
python backtest.py
```

回测输出的进场质量分析中，应在现有 KDJ_J 分桶之后看到：
- `--- 市值分桶（流通市值，亿元）---`
- `--- 周 KDJ_J 分桶 ---`
- `--- 周 MACD 区间 ---`
- `--- 月 MACD 区间 ---`
