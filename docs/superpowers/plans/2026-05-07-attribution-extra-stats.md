# 归因报告扩展：4 张关键统计表 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `attribution.run()` 末尾追加 4 张统计表（exit_reason / add_count / entry_condition / yearly），全部沿用现有 `_join_trades_with_signals` 数据流。

**Architecture:** 在 `my_strategy/tools/attribution.py` 新增 4 个 `compute_*` 函数，单元测试用合成 DataFrame 走 TDD（沿用 `tests/test_attribution.py` 的 fixture 风格），集成测试在 `tests/test_attribution_run.py` 校验 9 份报告全部产出。每个新统计独立成步，逐步加入 `run()` 并各自一次 commit。

**Tech Stack:** pandas（groupby + cut + describe 即可），pytest，无新依赖。

**Spec:** [docs/superpowers/specs/2026-05-07-attribution-extra-stats-design.md](../specs/2026-05-07-attribution-extra-stats-design.md)

---

## 文件结构

| 文件 | 修改类型 | 责任 |
|---|---|---|
| `my_strategy/tools/attribution.py` | 修改 | 新增 4 个 `compute_*` 函数；`run()` 末尾追加 4 个 `to_csv` |
| `my_strategy/tests/test_attribution.py` | 修改 | 新增 4 组单元测试（合成 DataFrame，覆盖正常/边界/空值） |
| `my_strategy/tests/test_attribution_run.py` | 修改 | `EXPECTED_FILES` 加入 4 个新文件名 |
| `docs/FEATURES.md` | 修改 | §6 归因分析章节追加 4 张表的说明 |
| `docs/CHANGELOG.md` | 修改 | 顶部追加一条 2026-05-07 记录 |

无新建源码文件。

---

## Task 1：exit_reason_stats — 按出场原因统计

**Files:**
- Modify: `my_strategy/tools/attribution.py`（新增函数；`run()` 末尾加 to_csv）
- Modify: `my_strategy/tests/test_attribution.py`（新增测试）

- [ ] **Step 1: 写失败测试**

在 `my_strategy/tests/test_attribution.py` 顶部 import 处追加 `compute_exit_reason_stats`：

```python
from my_strategy.tools.attribution import (
    compute_trade_profile,
    compute_top_bottom_trades,
    compute_sector_winrate,
    compute_exit_reason_stats,
)
```

在文件末尾追加：

```python
def _make_trade_summary_extended():
    """覆盖 exit_reason / add_count / status / gross_pnl / entry_date 等扩展字段。"""
    return pd.DataFrame({
        'ts_code': ['A.SZ', 'B.SZ', 'C.SZ', 'D.SZ', 'E.SZ', 'F.SZ'],
        'entry_date': pd.to_datetime(
            ['2022-01-05', '2022-06-10', '2023-02-08', '2023-09-15',
             '2024-03-12', '2024-11-20']),
        'return_pct': [15.0, -3.0, 8.0, -12.0, 2.0, float('nan')],
        'gross_pnl': [15000.0, -3000.0, 8000.0, -12000.0, 2000.0, float('nan')],
        'holding_days': [40.0, 15.0, 60.0, 22.0, 10.0, float('nan')],
        'add_count': [2, 0, 1, 0, 1, 1],
        'exit_reason': ['take_profit_2', 'MA25清仓', 'take_profit_2',
                        'MA25清仓', 'take_profit_1', '未平仓'],
        'status': ['completed', 'completed', 'completed',
                   'completed', 'completed', 'incomplete'],
    })


def test_compute_exit_reason_stats_groups_by_reason():
    trades = _make_trade_summary_extended()
    out = compute_exit_reason_stats(trades)
    # 4 个 exit_reason 各一行（MA25清仓有 2 笔合一组）
    assert set(out['exit_reason']) == {
        'take_profit_2', 'MA25清仓', 'take_profit_1', '未平仓'}
    ma25 = out[out['exit_reason'] == 'MA25清仓'].iloc[0]
    assert ma25['count'] == 2
    assert ma25['win_rate'] == 0.0           # 两笔都亏
    assert ma25['avg_return'] == -7.5        # (-3 + -12) / 2
    incomplete = out[out['exit_reason'] == '未平仓'].iloc[0]
    assert incomplete['count'] == 1
    assert pd.isna(incomplete['win_rate'])   # NaN return → 不计入胜率
    # 排序：count 降序
    assert list(out['count']) == sorted(out['count'], reverse=True)


def test_compute_exit_reason_stats_empty_input():
    out = compute_exit_reason_stats(pd.DataFrame())
    assert list(out.columns) == ['exit_reason', 'count', 'win_rate',
                                  'avg_return', 'avg_holding_days',
                                  'avg_add_count']
    assert len(out) == 0
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd e:/GithubCloneSpace/Stock/backtrader/backtrader
pytest my_strategy/tests/test_attribution.py::test_compute_exit_reason_stats_groups_by_reason -v
```
预期：`ImportError: cannot import name 'compute_exit_reason_stats'`

- [ ] **Step 3: 实现 `compute_exit_reason_stats`**

在 `my_strategy/tools/attribution.py` 的 `compute_sector_winrate` 函数之后追加：

```python
def compute_exit_reason_stats(trades):
    """按 exit_reason 分组统计 count/win_rate/avg_return/avg_holding_days/avg_add_count。

    NaN return_pct（如未平仓）会从 win_rate / avg_return 计算中剔除，
    但仍计入 count。排序：count 降序。
    """
    cols = ['exit_reason', 'count', 'win_rate', 'avg_return',
            'avg_holding_days', 'avg_add_count']
    if trades.empty or 'exit_reason' not in trades.columns:
        return pd.DataFrame(columns=cols)
    rows = []
    for reason, sub in trades.groupby('exit_reason'):
        ret = sub['return_pct'].dropna() if 'return_pct' in sub.columns else pd.Series(dtype=float)
        hold = sub['holding_days'].dropna() if 'holding_days' in sub.columns else pd.Series(dtype=float)
        addc = sub['add_count'].dropna() if 'add_count' in sub.columns else pd.Series(dtype=float)
        rows.append({
            'exit_reason': reason,
            'count': len(sub),
            'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
            'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
            'avg_holding_days': round(hold.mean(), 1) if len(hold) else float('nan'),
            'avg_add_count': round(addc.mean(), 2) if len(addc) else float('nan'),
        })
    return pd.DataFrame(rows, columns=cols).sort_values('count', ascending=False).reset_index(drop=True)
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest my_strategy/tests/test_attribution.py::test_compute_exit_reason_stats_groups_by_reason my_strategy/tests/test_attribution.py::test_compute_exit_reason_stats_empty_input -v
```
预期：2 passed

- [ ] **Step 5: 接入 `run()`**

定位 `attribution.py` 的 `run()` 函数，在 `factor_alpha = compute_factor_alpha(signals)` 之前追加：

```python
    exit_reason = compute_exit_reason_stats(trades)
    exit_reason.to_csv(out_dir / 'exit_reason_stats.csv', index=False)
```

- [ ] **Step 6: Commit**

```bash
git add my_strategy/tools/attribution.py my_strategy/tests/test_attribution.py
git commit -m "feat(attribution): add exit_reason_stats report"
```

---

## Task 2：add_count_stats — 按加仓次数统计

**Files:**
- Modify: `my_strategy/tools/attribution.py`
- Modify: `my_strategy/tests/test_attribution.py`

- [ ] **Step 1: 写失败测试**

import 处追加 `compute_add_count_stats`：

```python
from my_strategy.tools.attribution import (
    compute_trade_profile,
    compute_top_bottom_trades,
    compute_sector_winrate,
    compute_exit_reason_stats,
    compute_add_count_stats,
)
```

文件末尾追加：

```python
def test_compute_add_count_stats_buckets_3plus():
    trades = pd.DataFrame({
        'add_count': [0, 0, 1, 1, 2, 3, 4, 5],
        'return_pct': [1.0, 2.0, 3.0, -1.0, 0.5, 10.0, 20.0, 30.0],
        'gross_pnl': [100, 200, 300, -100, 50, 1000, 2000, 3000],
        'holding_days': [10, 12, 20, 18, 30, 50, 60, 70],
        'status': ['completed'] * 8,
    })
    out = compute_add_count_stats(trades)
    # add_count 3+ 应合并为一桶
    assert set(out['add_count']) == {'0', '1', '2', '3+'}
    bucket_3plus = out[out['add_count'] == '3+'].iloc[0]
    assert bucket_3plus['count'] == 3   # 3, 4, 5 三笔合并
    # 排序：add_count 升序
    assert list(out['add_count']) == ['0', '1', '2', '3+']


def test_compute_add_count_stats_pct_completed():
    trades = pd.DataFrame({
        'add_count': [1, 1, 1, 1],
        'return_pct': [1.0, 2.0, float('nan'), float('nan')],
        'gross_pnl': [100, 200, float('nan'), float('nan')],
        'holding_days': [10, 12, float('nan'), float('nan')],
        'status': ['completed', 'completed', 'incomplete', 'incomplete'],
    })
    out = compute_add_count_stats(trades)
    row = out[out['add_count'] == '1'].iloc[0]
    assert row['count'] == 4
    assert row['pct_completed'] == 0.5   # 2/4


def test_compute_add_count_stats_empty_input():
    out = compute_add_count_stats(pd.DataFrame())
    assert list(out.columns) == ['add_count', 'count', 'win_rate',
                                  'avg_return', 'avg_holding_days',
                                  'pct_completed']
    assert len(out) == 0
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest my_strategy/tests/test_attribution.py::test_compute_add_count_stats_buckets_3plus -v
```
预期：ImportError

- [ ] **Step 3: 实现 `compute_add_count_stats`**

在 `compute_exit_reason_stats` 之后追加：

```python
def compute_add_count_stats(trades):
    """按 add_count 分组（0/1/2/3+），统计胜率/平均收益/已平仓比例。

    排序：add_count 升序（'0' → '1' → '2' → '3+'）。
    """
    cols = ['add_count', 'count', 'win_rate', 'avg_return',
            'avg_holding_days', 'pct_completed']
    if trades.empty or 'add_count' not in trades.columns:
        return pd.DataFrame(columns=cols)
    t = trades.copy()
    t['add_count_bucket'] = t['add_count'].apply(
        lambda x: str(int(x)) if pd.notna(x) and x < 3 else '3+')
    rows = []
    for bucket, sub in t.groupby('add_count_bucket'):
        ret = sub['return_pct'].dropna() if 'return_pct' in sub.columns else pd.Series(dtype=float)
        hold = sub['holding_days'].dropna() if 'holding_days' in sub.columns else pd.Series(dtype=float)
        completed = ((sub['status'] == 'completed').sum()
                     if 'status' in sub.columns else 0)
        rows.append({
            'add_count': bucket,
            'count': len(sub),
            'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
            'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
            'avg_holding_days': round(hold.mean(), 1) if len(hold) else float('nan'),
            'pct_completed': round(completed / len(sub), 4) if len(sub) else float('nan'),
        })
    order = {'0': 0, '1': 1, '2': 2, '3+': 3}
    df = pd.DataFrame(rows, columns=cols)
    df['_ord'] = df['add_count'].map(order)
    return df.sort_values('_ord').drop(columns='_ord').reset_index(drop=True)
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest my_strategy/tests/test_attribution.py -k "add_count" -v
```
预期：3 passed

- [ ] **Step 5: 接入 `run()`**

在 `attribution.py` 的 `run()` 中，紧跟 `exit_reason.to_csv(...)` 之后追加：

```python
    add_count = compute_add_count_stats(trades)
    add_count.to_csv(out_dir / 'add_count_stats.csv', index=False)
```

- [ ] **Step 6: Commit**

```bash
git add my_strategy/tools/attribution.py my_strategy/tests/test_attribution.py
git commit -m "feat(attribution): add add_count_stats report"
```

---

## Task 3：entry_condition_stats — 7 字段单条件长表

**Files:**
- Modify: `my_strategy/tools/attribution.py`
- Modify: `my_strategy/tests/test_attribution.py`

- [ ] **Step 1: 写失败测试**

import 追加 `compute_entry_condition_stats`：

```python
from my_strategy.tools.attribution import (
    compute_trade_profile,
    compute_top_bottom_trades,
    compute_sector_winrate,
    compute_exit_reason_stats,
    compute_add_count_stats,
    compute_entry_condition_stats,
)
```

文件末尾追加：

```python
def test_compute_entry_condition_stats_kdj_buckets():
    trades = pd.DataFrame({
        'entry_kdj_j': [25.0, 50.0, 75.0, 90.0, 110.0],
        'entry_ma60_dist_pct': [0.5, 3.0, 8.0, 15.0, 25.0],
        'ma_alignment': ['全多头'] * 5,
        'macd_zone': ['区间1'] * 5,
        'entry_week_kdj_j': [30.0, 55.0, 70.0, 85.0, 105.0],
        'entry_week_macd_zone': ['区间0'] * 5,
        'entry_month_macd_zone': ['区间0'] * 5,
        'return_pct': [5.0, 3.0, 1.0, -2.0, -8.0],
        'gross_pnl': [500, 300, 100, -200, -800],
        'holding_days': [30, 25, 20, 15, 10],
    })
    out = compute_entry_condition_stats(trades)
    # 应包含所有 7 个 condition_field
    assert set(out['condition_field']) == {
        'entry_kdj_j', 'entry_ma60_dist_pct', 'ma_alignment',
        'macd_zone', 'entry_week_kdj_j', 'entry_week_macd_zone',
        'entry_month_macd_zone'}
    # entry_kdj_j 4 个固定阈值桶（25→[0,40), 50→[40,80), 75→[40,80), 90→[80,100), 110→[100+)）
    kdj = out[out['condition_field'] == 'entry_kdj_j']
    assert set(kdj['bucket']) == {'[0,40)', '[40,80)', '[80,100)', '[100+)'}
    bucket_4080 = kdj[kdj['bucket'] == '[40,80)'].iloc[0]
    assert bucket_4080['count'] == 2   # 50 + 75


def test_compute_entry_condition_stats_ma60_dist_buckets():
    trades = pd.DataFrame({
        'entry_kdj_j': [50.0] * 6,
        'entry_ma60_dist_pct': [-1.0, 0.5, 7.5, 15.0, 25.0, 35.0],
        'ma_alignment': ['全多头'] * 6,
        'macd_zone': ['区间1'] * 6,
        'entry_week_kdj_j': [50.0] * 6,
        'entry_week_macd_zone': ['区间0'] * 6,
        'entry_month_macd_zone': ['区间0'] * 6,
        'return_pct': [1.0] * 6,
        'gross_pnl': [100] * 6,
        'holding_days': [10] * 6,
    })
    out = compute_entry_condition_stats(trades)
    ma60 = out[out['condition_field'] == 'entry_ma60_dist_pct']
    # 5 个固定阈值桶
    assert set(ma60['bucket']) == {
        '[<0%)', '[0%,5%)', '[5%,10%)', '[10%,20%)', '[20%+)'}
    # -1 进 [<0%)
    assert ma60[ma60['bucket'] == '[<0%)'].iloc[0]['count'] == 1
    # 25, 35 进 [20%+)
    assert ma60[ma60['bucket'] == '[20%+)'].iloc[0]['count'] == 2


def test_compute_entry_condition_stats_categorical():
    trades = pd.DataFrame({
        'entry_kdj_j': [50.0] * 4,
        'entry_ma60_dist_pct': [3.0] * 4,
        'ma_alignment': ['全多头', '全多头', '局部空头', '全空头'],
        'macd_zone': ['区间1'] * 4,
        'entry_week_kdj_j': [50.0] * 4,
        'entry_week_macd_zone': ['区间0'] * 4,
        'entry_month_macd_zone': ['区间0'] * 4,
        'return_pct': [5.0, 3.0, -2.0, -10.0],
        'gross_pnl': [500, 300, -200, -1000],
        'holding_days': [20, 15, 10, 8],
    })
    out = compute_entry_condition_stats(trades)
    align = out[out['condition_field'] == 'ma_alignment']
    full_long = align[align['bucket'] == '全多头'].iloc[0]
    assert full_long['count'] == 2
    assert full_long['avg_return'] == 4.0   # (5+3)/2


def test_compute_entry_condition_stats_empty_input():
    out = compute_entry_condition_stats(pd.DataFrame())
    assert list(out.columns) == ['condition_field', 'bucket', 'count',
                                  'win_rate', 'avg_return', 'avg_holding_days']
    assert len(out) == 0
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest my_strategy/tests/test_attribution.py -k "entry_condition" -v
```
预期：ImportError

- [ ] **Step 3: 实现 `compute_entry_condition_stats`**

在 `compute_add_count_stats` 之后追加（注意常量与辅助函数也写出来）：

```python
import numpy as np  # 文件顶部已有则跳过

_KDJ_BINS = [-np.inf, 40, 80, 100, np.inf]
_KDJ_LABELS = ['[0,40)', '[40,80)', '[80,100)', '[100+)']
_MA60_BINS = [-np.inf, 0, 5, 10, 20, np.inf]
_MA60_LABELS = ['[<0%)', '[0%,5%)', '[5%,10%)', '[10%,20%)', '[20%+)']

_NUMERIC_BUCKETS = {
    'entry_kdj_j':         (_KDJ_BINS,  _KDJ_LABELS),
    'entry_week_kdj_j':    (_KDJ_BINS,  _KDJ_LABELS),
    'entry_ma60_dist_pct': (_MA60_BINS, _MA60_LABELS),
}
_CATEGORICAL_FIELDS = [
    'ma_alignment',
    'macd_zone',
    'entry_week_macd_zone',
    'entry_month_macd_zone',
]


def _bucket_aggregate(field, sub):
    """对一个 (condition_field, bucket) 子集计算 count/win_rate/avg_return/avg_holding_days。"""
    ret = sub['return_pct'].dropna() if 'return_pct' in sub.columns else pd.Series(dtype=float)
    hold = sub['holding_days'].dropna() if 'holding_days' in sub.columns else pd.Series(dtype=float)
    return {
        'count': len(sub),
        'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
        'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
        'avg_holding_days': round(hold.mean(), 1) if len(hold) else float('nan'),
    }


def compute_entry_condition_stats(trades):
    """对 7 个入场快照字段分别 group，输出长表（每条件多行）。

    数值字段（kdj_j 类、ma60_dist_pct）用固定阈值分桶；
    类别字段（ma_alignment / macd_zone 类）直接按值 group。
    含 NaN 的行被丢弃，不计入任何桶。
    """
    cols = ['condition_field', 'bucket', 'count', 'win_rate',
            'avg_return', 'avg_holding_days']
    if trades.empty:
        return pd.DataFrame(columns=cols)

    rows = []

    # 数值字段
    for field, (bins, labels) in _NUMERIC_BUCKETS.items():
        if field not in trades.columns:
            continue
        sub = trades.dropna(subset=[field]).copy()
        if sub.empty:
            continue
        sub['_bucket'] = pd.cut(sub[field], bins=bins, labels=labels,
                                 right=False, include_lowest=False)
        for bucket in labels:
            chunk = sub[sub['_bucket'] == bucket]
            if chunk.empty:
                continue
            row = {'condition_field': field, 'bucket': bucket}
            row.update(_bucket_aggregate(field, chunk))
            rows.append(row)

    # 类别字段
    for field in _CATEGORICAL_FIELDS:
        if field not in trades.columns:
            continue
        sub = trades.dropna(subset=[field])
        if sub.empty:
            continue
        for bucket, chunk in sub.groupby(field):
            row = {'condition_field': field, 'bucket': str(bucket)}
            row.update(_bucket_aggregate(field, chunk))
            rows.append(row)

    if not rows:
        return pd.DataFrame(columns=cols)

    df = pd.DataFrame(rows, columns=cols)
    # 排序：condition_field 升序；组内：数值字段按 labels 顺序，类别按 bucket 字符串
    return df.sort_values(['condition_field', 'bucket']).reset_index(drop=True)
```

> 注：`pd.cut` 的 `right=False, include_lowest=False` 表示左闭右开，与标签 `[0,40)` 一致。`-inf` / `+inf` 桶边界确保极端值不丢失。

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest my_strategy/tests/test_attribution.py -k "entry_condition" -v
```
预期：4 passed

- [ ] **Step 5: 接入 `run()`**

紧跟 `add_count.to_csv(...)` 之后追加：

```python
    entry_cond = compute_entry_condition_stats(trades)
    entry_cond.to_csv(out_dir / 'entry_condition_stats.csv', index=False)
```

- [ ] **Step 6: Commit**

```bash
git add my_strategy/tools/attribution.py my_strategy/tests/test_attribution.py
git commit -m "feat(attribution): add entry_condition_stats report"
```

---

## Task 4：yearly_stats — 按入场年份统计

**Files:**
- Modify: `my_strategy/tools/attribution.py`
- Modify: `my_strategy/tests/test_attribution.py`

- [ ] **Step 1: 写失败测试**

import 追加 `compute_yearly_stats`：

```python
from my_strategy.tools.attribution import (
    compute_trade_profile,
    compute_top_bottom_trades,
    compute_sector_winrate,
    compute_exit_reason_stats,
    compute_add_count_stats,
    compute_entry_condition_stats,
    compute_yearly_stats,
)
```

文件末尾追加：

```python
def test_compute_yearly_stats_groups_by_year():
    trades = _make_trade_summary_extended()  # 6 笔分布在 2022/2023/2024
    out = compute_yearly_stats(trades)
    assert list(out['year']) == [2022, 2023, 2024]    # 升序
    y2022 = out[out['year'] == 2022].iloc[0]
    assert y2022['count'] == 2                         # 1月+6月
    assert y2022['total_pnl_yuan'] == 12000.0         # 15000 + (-3000)
    assert y2022['win_rate'] == 0.5                    # 1 win / 2
    y2024 = out[out['year'] == 2024].iloc[0]
    assert y2024['count'] == 2
    # 2024 年含一笔 NaN return（未平仓）→ win_rate / avg_return 只算非空
    assert y2024['win_rate'] == 1.0                    # 唯一非空 = 2.0 > 0
    assert y2024['median_return'] == 2.0


def test_compute_yearly_stats_empty_input():
    out = compute_yearly_stats(pd.DataFrame())
    assert list(out.columns) == ['year', 'count', 'win_rate',
                                  'avg_return', 'median_return',
                                  'total_pnl_yuan', 'avg_holding_days']
    assert len(out) == 0
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest my_strategy/tests/test_attribution.py -k "yearly" -v
```
预期：ImportError

- [ ] **Step 3: 实现 `compute_yearly_stats`**

在 `compute_entry_condition_stats` 之后追加：

```python
def compute_yearly_stats(trades):
    """按 entry_date.year 分组：count / win_rate / avg_return / median_return /
    total_pnl_yuan / avg_holding_days。total_pnl_yuan 单位为元。

    跨年可比性：策略不复利（position_limit = initial_cash / max_positions
    在 strategy.__init__ 中只算一次），单仓位金额常数。
    """
    cols = ['year', 'count', 'win_rate', 'avg_return', 'median_return',
            'total_pnl_yuan', 'avg_holding_days']
    if trades.empty or 'entry_date' not in trades.columns:
        return pd.DataFrame(columns=cols)
    t = trades.copy()
    t['entry_date'] = pd.to_datetime(t['entry_date'], errors='coerce')
    t = t.dropna(subset=['entry_date'])
    if t.empty:
        return pd.DataFrame(columns=cols)
    t['year'] = t['entry_date'].dt.year
    rows = []
    for year, sub in t.groupby('year'):
        ret = sub['return_pct'].dropna() if 'return_pct' in sub.columns else pd.Series(dtype=float)
        pnl = sub['gross_pnl'].dropna() if 'gross_pnl' in sub.columns else pd.Series(dtype=float)
        hold = sub['holding_days'].dropna() if 'holding_days' in sub.columns else pd.Series(dtype=float)
        rows.append({
            'year': int(year),
            'count': len(sub),
            'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
            'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
            'median_return': round(ret.median(), 4) if len(ret) else float('nan'),
            'total_pnl_yuan': round(pnl.sum(), 2) if len(pnl) else 0.0,
            'avg_holding_days': round(hold.mean(), 1) if len(hold) else float('nan'),
        })
    return pd.DataFrame(rows, columns=cols).sort_values('year').reset_index(drop=True)
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest my_strategy/tests/test_attribution.py -k "yearly" -v
```
预期：2 passed

- [ ] **Step 5: 接入 `run()`**

紧跟 `entry_cond.to_csv(...)` 之后追加：

```python
    yearly = compute_yearly_stats(trades)
    yearly.to_csv(out_dir / 'yearly_stats.csv', index=False)
```

- [ ] **Step 6: 全部单元测试一起跑通**

```bash
pytest my_strategy/tests/test_attribution.py -v
```
预期：所有原有测试 + 11 个新增测试全部 pass

- [ ] **Step 7: Commit**

```bash
git add my_strategy/tools/attribution.py my_strategy/tests/test_attribution.py
git commit -m "feat(attribution): add yearly_stats report"
```

---

## Task 5：集成测试扩展 + 真实数据端到端验证

**Files:**
- Modify: `my_strategy/tests/test_attribution_run.py`

- [ ] **Step 1: 扩展 `EXPECTED_FILES` 清单**

打开 `my_strategy/tests/test_attribution_run.py`，把 `EXPECTED_FILES` 改成：

```python
EXPECTED_FILES = [
    'trade_profile.csv',
    'top_trades.csv',
    'bottom_trades.csv',
    'sector_winrate.csv',
    'factor_alpha.csv',
    'exit_reason_stats.csv',
    'add_count_stats.csv',
    'entry_condition_stats.csv',
    'yearly_stats.csv',
]
```

- [ ] **Step 2: 用真实 trade_summary.csv 跑端到端**

```bash
cd e:/GithubCloneSpace/Stock/backtrader/backtrader
python my_strategy/tests/test_attribution_run.py
```
预期最后一行：`所有归因报告产出成功。`，并打印 9 个 `[OK]` 行。

- [ ] **Step 3: 抽样检查新报告内容（可选但推荐）**

```bash
python -c "
import pandas as pd
for f in ['exit_reason_stats', 'add_count_stats', 'entry_condition_stats', 'yearly_stats']:
    df = pd.read_csv(f'my_strategy/reports/{f}.csv')
    print(f'\\n=== {f}.csv ({len(df)} rows) ===')
    print(df.head(10).to_string())
"
```
预期：
- exit_reason_stats：5~6 行（5911 笔分到 MA25清仓 / take_profit_1 / take_profit_2 / 跌停止损 / 未平仓）
- add_count_stats：4 行（'0' / '1' / '2' / '3+'，count 总和 = 5911）
- entry_condition_stats：~20+ 行（7 字段 × 各自桶数）
- yearly_stats：5~6 行（回测覆盖 2019~2023 各一行）

- [ ] **Step 4: Commit**

```bash
git add my_strategy/tests/test_attribution_run.py
git commit -m "test(attribution): extend integration test for 4 new stats reports"
```

---

## Task 6：文档更新

**Files:**
- Modify: `docs/FEATURES.md`
- Modify: `docs/CHANGELOG.md`

- [ ] **Step 1: 更新 FEATURES.md §6 归因分析**

打开 `docs/FEATURES.md`，找到 `## 6. 归因分析（tools/attribution.py）` 章节内的输出列表（"输出到 `reports/`：" 那段），把它替换为：

```markdown
输出到 `reports/`：

1. **trade_profile**：按收益分桶（大盈/小盈/持平/小亏/大亏）统计因子均值、分位；
2. **top_trades / bottom_trades**：收益最高 / 最低各 10 笔；
3. **sector_winrate**：按申万一级行业统计交易数、胜率、平均收益；
4. **factor_alpha**：每个 `factor_*` 因子的 IC（Spearman）与多空分组超额；
5. **exit_reason_stats**：按出场原因（MA25清仓 / take_profit_1/2 / 未平仓 ...）统计胜率、收益、持仓天数、加仓次数；
6. **add_count_stats**：按加仓次数（0/1/2/3+）统计胜率、收益、已平仓比例；
7. **entry_condition_stats**：7 个入场快照字段（kdj_j / ma60_dist / ma_alignment / macd_zone / week/month）的单条件长表，固定阈值分桶；
8. **yearly_stats**：按 `entry_date.year` 统计 count / win_rate / avg_return / median_return / total_pnl_yuan（绝对盈亏，元）/ avg_holding_days。
```

- [ ] **Step 2: 在 CHANGELOG.md 顶部追加记录**

打开 `docs/CHANGELOG.md`，在第一条 `## 2026-05-07` 记录之前插入：

```markdown
## 2026-05-07 — 归因报告新增 4 张关键统计表

- 需求：现有归因仅覆盖行业/收益分桶/3 个因子三个维度，缺 exit_reason / add_count / 入场条件 / 年度稳定性，无法定位策略瓶颈。
- 改动：
  - `my_strategy/tools/attribution.py` 新增 `compute_exit_reason_stats / compute_add_count_stats / compute_entry_condition_stats / compute_yearly_stats` 四个函数，并在 `run()` 末尾追加 4 个 `to_csv`。
  - `my_strategy/tests/test_attribution.py` 新增 11 个单元测试覆盖正常/边界/空值。
  - `my_strategy/tests/test_attribution_run.py` 扩展 EXPECTED_FILES 至 9 个文件。
  - `docs/FEATURES.md` §6 同步更新输出清单。
- 影响：回测后自动产出 9 张归因报告（之前 5 张），新增 4 张提供策略优化所需的诊断维度。详见 spec：`docs/superpowers/specs/2026-05-07-attribution-extra-stats-design.md`。
```

- [ ] **Step 3: Commit**

```bash
git add docs/FEATURES.md docs/CHANGELOG.md
git commit -m "docs: document 4 new attribution stats reports"
```

---

## 完成验收

全部 6 个 Task 完成后，运行：

```bash
cd e:/GithubCloneSpace/Stock/backtrader/backtrader
pytest my_strategy/tests/test_attribution.py -v
python my_strategy/tests/test_attribution_run.py
git log --oneline -7
```

预期：
- 单元测试全 pass（旧 + 新 11 个 = 共约 14+ 个）
- 集成测试输出 `所有归因报告产出成功。`
- git 历史出现 6 个新 commit（feat × 4，test × 1，docs × 1）
- `my_strategy/reports/` 下 9 个 CSV 文件齐全

无需重跑 backtest（仅 attribution 层改动，使用现有 `trade_summary.csv` + `signals_log.csv`）。
