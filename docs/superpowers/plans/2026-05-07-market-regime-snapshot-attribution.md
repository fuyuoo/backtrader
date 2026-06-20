# 大盘 + 个股入场环境快照与归因（第一阶段）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 trade_summary 后处理阶段为每笔交易打 4 个入场环境布尔快照（HS300 DIF 水上水下、HS300 多头排列、个股多头排列、个股站上 MA25），attribution 端新增 4 张单维度桶表 + 1 张大盘×个股共振 2x2 表，回答"什么样的市场/个股环境下入场，胜率/平均收益更高"。

**Architecture:** 复用既有 `_enrich_trade_summary` 后处理 pipeline。所有指标（个股 ma25/ma60/ma144/ma180、HS300 dif/ma25/ma60/ma144/ma180）都在 `data/indicators/{code}.csv` 中预计算完成，无需修改 strategy.py 或 cerebro 数据接入。新增模块级纯函数 `_compute_regime_flags(stock_row, hs300_row)` 计算 4 个标志位，4+1 张归因报告复用 `_scan_bucket_aggregate` 模式。

**Tech Stack:** pandas / pytest / backtrader (仅作为 trade_summary 数据来源，不动)。

**Scope 边界（明确不做的事）：**
- 不动 `src/strategy.py`、不修改 `StockData` lines、不修改 cerebro 数据接入
- 不下载/不需要申万行业指数数据（属于第二阶段）
- 不做 Kontingent 表 / chi-square 检验（先看胜率差异，是否显著留给后续判断）

---

## File Structure

| File | 责任 |
|------|------|
| `my_strategy/backtest.py` | 新增 `_compute_regime_flags` 模块级函数；扩展 `_enrich_trade_summary` 加载 HS300 indicators 并写入 4 个新列 |
| `my_strategy/tools/attribution.py` | 新增 `compute_hs300_dif_stats` / `compute_hs300_bull_align_stats` / `compute_stock_bull_align_stats` / `compute_stock_above_ma25_stats` / `compute_regime_combo_stats` 5 个函数；`run()` 注册输出 |
| `my_strategy/tests/test_backtest.py` | **新建**。覆盖 `_compute_regime_flags` 纯函数行为 + `_enrich_trade_summary` 端到端集成（用临时目录构造 mini indicators csv） |
| `my_strategy/tests/test_attribution.py` | 添加 5 个 attribution 函数的单元测试 |
| `my_strategy/tests/test_attribution_run.py` | 把 `EXPECTED_FILES` 从 15 扩到 20 |
| `docs/FEATURES.md` | §5.4 trade_summary 增加 4 个新列；§6 归因列表新增 5 项（14→19） |
| `docs/CHANGELOG.md` | 顶部追加 2026-05-07 条目 |

---

## 字段定义（不可改名/不可漂移）

新增到 `trade_summary.csv` 的 4 列（位置：在 `entry_month_macd_zone` 之后）：

| 列名 | 类型 | 取值规则 |
|------|------|---------|
| `entry_hs300_dif_above_zero` | `Optional[bool]` | HS300 indicators 在 entry_date 那行的 `dif > 0` 为 True，`dif <= 0` 为 False，缺失或 NaN 为 None |
| `entry_hs300_bull_align` | `Optional[bool]` | HS300 在 entry_date 满足 `ma25 > ma60 > ma144 > ma180` 为 True，4 项都齐且不满足为 False，任一缺失为 None |
| `entry_stock_bull_align` | `Optional[bool]` | 个股在 entry_date 满足 `ma25 > ma60 > ma144 > ma180` 为 True，4 项都齐且不满足为 False，任一缺失为 None |
| `entry_stock_above_ma25` | `Optional[bool]` | 个股在 entry_date 满足 `close > ma25` 为 True，`close <= ma25` 为 False，任一缺失为 None |

写入 csv 时 `True` → 字符串 `"True"`、`False` → `"False"`、`None` → 空字符串（pandas 默认行为）。attribution 读 csv 后用 `astype(object)` 保留 NaN，分桶时 dropna。

HS300 数据源：`data/indicators/000300.SH.csv`，路径硬编码（已确认存在）。如果文件缺失 → raise FileNotFoundError，**不静默降级**（遵守项目错误处理政策）。

---

## Task 1: `_compute_regime_flags` 纯函数 + 测试

**Files:**
- Modify: `my_strategy/backtest.py:130` (在 `_classify_ma_alignment` 之前插入新函数)
- Create: `my_strategy/tests/test_backtest.py`

- [ ] **Step 1: 新建 `tests/test_backtest.py`，写 4 个失败测试覆盖 `_compute_regime_flags`**

```python
"""Tests for backtest.py post-processing helpers."""
import pandas as pd
import pytest

from backtest import _compute_regime_flags


def _stock_row(close=10.0, ma25=9.0, ma60=8.0, ma144=7.0, ma180=6.0):
    return pd.Series({'close': close, 'ma25': ma25, 'ma60': ma60,
                      'ma144': ma144, 'ma180': ma180})


def _hs300_row(dif=0.5, ma25=4000, ma60=3900, ma144=3800, ma180=3700):
    return pd.Series({'dif': dif, 'ma25': ma25, 'ma60': ma60,
                      'ma144': ma144, 'ma180': ma180})


def test_regime_flags_all_bullish():
    flags = _compute_regime_flags(_stock_row(), _hs300_row())
    assert flags == {
        'entry_hs300_dif_above_zero': True,
        'entry_hs300_bull_align': True,
        'entry_stock_bull_align': True,
        'entry_stock_above_ma25': True,
    }


def test_regime_flags_all_bearish():
    stock = _stock_row(close=5.0, ma25=6.0, ma60=7.0, ma144=8.0, ma180=9.0)
    hs300 = _hs300_row(dif=-0.5, ma25=3700, ma60=3800, ma144=3900, ma180=4000)
    flags = _compute_regime_flags(stock, hs300)
    assert flags == {
        'entry_hs300_dif_above_zero': False,
        'entry_hs300_bull_align': False,
        'entry_stock_bull_align': False,
        'entry_stock_above_ma25': False,
    }


def test_regime_flags_dif_zero_is_false():
    """dif == 0 视为水下（约束：> 0 才算水上）。"""
    flags = _compute_regime_flags(_stock_row(), _hs300_row(dif=0.0))
    assert flags['entry_hs300_dif_above_zero'] is False


def test_regime_flags_missing_long_ma_returns_none():
    """ma144/ma180 任一缺失，bull_align 必为 None；其他字段不受影响。"""
    stock = _stock_row(ma144=float('nan'))
    hs300 = _hs300_row(ma180=float('nan'))
    flags = _compute_regime_flags(stock, hs300)
    assert flags['entry_stock_bull_align'] is None
    assert flags['entry_hs300_bull_align'] is None
    # 其余字段仍正常计算
    assert flags['entry_stock_above_ma25'] is True
    assert flags['entry_hs300_dif_above_zero'] is True


def test_regime_flags_hs300_row_is_none():
    """HS300 在 entry_date 完全缺数据：4 个 hs300 字段全 None；个股字段不受影响。"""
    flags = _compute_regime_flags(_stock_row(), None)
    assert flags['entry_hs300_dif_above_zero'] is None
    assert flags['entry_hs300_bull_align'] is None
    assert flags['entry_stock_bull_align'] is True
    assert flags['entry_stock_above_ma25'] is True
```

并在 `tests/test_backtest.py` 顶部添加 sys.path 注入（与 `test_attribution_run.py` 同模式）：

```python
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
```

放在 import backtest 之前。

- [ ] **Step 2: 运行测试确认全部失败**

Run: `cd my_strategy && python -m pytest tests/test_backtest.py -v`
Expected: 5 个测试都报 `ImportError: cannot import name '_compute_regime_flags' from 'backtest'`

- [ ] **Step 3: 在 `backtest.py` 第 130 行（`_classify_ma_alignment` 之前）插入 `_compute_regime_flags`**

```python
def _compute_regime_flags(stock_row, hs300_row):
    """计算入场时刻 4 个环境布尔标志。

    Args:
        stock_row: pd.Series，含 close/ma25/ma60/ma144/ma180（来自个股 indicators）
        hs300_row: pd.Series 或 None，含 dif/ma25/ma60/ma144/ma180（来自 HS300 indicators）

    Returns:
        dict 含 4 个键，值为 Optional[bool]：缺数据返回 None。
    """
    def _bull_align(row):
        if row is None:
            return None
        m25, m60, m144, m180 = row.get('ma25'), row.get('ma60'), row.get('ma144'), row.get('ma180')
        if pd.isna(m25) or pd.isna(m60) or pd.isna(m144) or pd.isna(m180):
            return None
        return bool(m25 > m60 > m144 > m180)

    # 个股 close > ma25
    s_close = stock_row.get('close')
    s_ma25 = stock_row.get('ma25')
    if pd.isna(s_close) or pd.isna(s_ma25):
        stock_above_ma25 = None
    else:
        stock_above_ma25 = bool(s_close > s_ma25)

    # HS300 DIF 水上水下
    if hs300_row is None:
        hs300_dif_above = None
    else:
        dif = hs300_row.get('dif')
        hs300_dif_above = None if pd.isna(dif) else bool(dif > 0)

    return {
        'entry_hs300_dif_above_zero': hs300_dif_above,
        'entry_hs300_bull_align': _bull_align(hs300_row),
        'entry_stock_bull_align': _bull_align(stock_row),
        'entry_stock_above_ma25': stock_above_ma25,
    }
```

- [ ] **Step 4: 运行测试确认全部通过**

Run: `cd my_strategy && python -m pytest tests/test_backtest.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add my_strategy/backtest.py my_strategy/tests/test_backtest.py
git commit -m "feat(backtest): add _compute_regime_flags helper for entry regime snapshots"
```

---

## Task 2: 集成 `_compute_regime_flags` 进 `_enrich_trade_summary`

**Files:**
- Modify: `my_strategy/backtest.py:167-262` (`_enrich_trade_summary` 整段)
- Modify: `my_strategy/tests/test_backtest.py` (追加集成测试)

- [ ] **Step 1: 在 `tests/test_backtest.py` 末尾追加集成测试**

```python
def test_enrich_trade_summary_writes_regime_flags(tmp_path):
    """_enrich_trade_summary 应为每笔 trade 写入 4 个 regime 标志。"""
    from backtest import _enrich_trade_summary

    # 构造 mini 数据：1 只股票 + HS300，2 个交易日
    data_dir = tmp_path / 'data'
    (data_dir / 'indicators').mkdir(parents=True)

    # 个股 indicators：第 1 天多头排列且站上 ma25；第 2 天空头且 close<ma25
    stock_df = pd.DataFrame({
        'trade_date': pd.to_datetime(['2024-01-02', '2024-01-03']),
        'close': [10.0, 5.0],
        'ma25': [9.0, 6.0],
        'ma60': [8.0, 7.0],
        'ma144': [7.0, 8.0],
        'ma180': [6.0, 9.0],
        'kdj_j': [50.0, 30.0],
        'circ_mv': [100.0, 100.0],
        'week_kdj_j': [50.0, 30.0],
        'week_macd_zone': ['区间1', '区间0'],
        'month_macd_zone': ['区间1', '区间0'],
        'macd': [0.5, -0.5], 'dif': [0.6, -0.4], 'dea': [0.4, -0.3],
    })
    stock_df.to_csv(data_dir / 'indicators' / 'TEST.SZ.csv', index=False)

    # HS300：第 1 天水上多头；第 2 天水下空头
    hs300_df = pd.DataFrame({
        'trade_date': pd.to_datetime(['2024-01-02', '2024-01-03']),
        'close': [4000, 3700],
        'ma25': [4000, 3700], 'ma60': [3900, 3800],
        'ma144': [3800, 3900], 'ma180': [3700, 4000],
        'dif': [0.5, -0.3], 'dea': [0.3, -0.1], 'macd': [0.2, -0.2],
    })
    hs300_df.to_csv(data_dir / 'indicators' / '000300.SH.csv', index=False)

    # stock_sector.csv（_enrich_trade_summary 需要）
    pd.DataFrame({'ts_code': ['TEST.SZ'], 'industry': ['银行']}).to_csv(
        data_dir / 'stock_sector.csv', index=False)

    summary = pd.DataFrame([
        {'ts_code': 'TEST.SZ', 'entry_date': pd.Timestamp('2024-01-02'),
         'return_pct': 5.0, 'status': 'completed'},
        {'ts_code': 'TEST.SZ', 'entry_date': pd.Timestamp('2024-01-03'),
         'return_pct': -3.0, 'status': 'completed'},
    ])

    enriched = _enrich_trade_summary(summary, {'data_dir': str(data_dir)})

    row1 = enriched.iloc[0]
    assert row1['entry_hs300_dif_above_zero'] is True
    assert row1['entry_hs300_bull_align'] is True
    assert row1['entry_stock_bull_align'] is True
    assert row1['entry_stock_above_ma25'] is True

    row2 = enriched.iloc[1]
    assert row2['entry_hs300_dif_above_zero'] is False
    assert row2['entry_hs300_bull_align'] is False
    assert row2['entry_stock_bull_align'] is False
    assert row2['entry_stock_above_ma25'] is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd my_strategy && python -m pytest tests/test_backtest.py::test_enrich_trade_summary_writes_regime_flags -v`
Expected: FAIL（KeyError 或 AttributeError，因为 enrich 还没写这 4 列）

- [ ] **Step 3: 修改 `_enrich_trade_summary`，加载 HS300 indicators 并写入 4 个新列**

定位到 `backtest.py:175`（`data_dir = Path(cfg['data_dir'])` 之后），插入 HS300 加载逻辑：

```python
    # 加载 HS300 indicators 作为入场环境快照基准（第一阶段：仅大盘）
    hs300_path = data_dir / 'indicators' / '000300.SH.csv'
    if not hs300_path.exists():
        raise FileNotFoundError(
            f"HS300 indicators not found at {hs300_path}. "
            f"Run src/calc_indicators.py for 000300.SH first.")
    hs300_df = pd.read_csv(hs300_path, parse_dates=['trade_date'])
    hs300_df = hs300_df.set_index('trade_date')
```

然后在 `for _, row in group.iterrows():` 循环内（`backtest.py:207-258`），在 `if entry_date in ind_df.index:` 分支末尾（赋完 entry_month_macd_zone 之后），添加：

```python
                hs300_row = hs300_df.loc[entry_date] if entry_date in hs300_df.index else None
                if isinstance(hs300_row, pd.DataFrame):
                    hs300_row = hs300_row.iloc[0]
                flags = _compute_regime_flags(r, hs300_row)
                row['entry_hs300_dif_above_zero'] = flags['entry_hs300_dif_above_zero']
                row['entry_hs300_bull_align'] = flags['entry_hs300_bull_align']
                row['entry_stock_bull_align'] = flags['entry_stock_bull_align']
                row['entry_stock_above_ma25'] = flags['entry_stock_above_ma25']
```

并在 `else:`（entry_date 不在 ind_df.index）分支同时补 4 个 None：

```python
                row['entry_hs300_dif_above_zero'] = None
                row['entry_hs300_bull_align'] = None
                row['entry_stock_bull_align'] = None
                row['entry_stock_above_ma25'] = None
```

并在最上面 `if not ind_path.exists():` 内的 fallback 分支（约 `backtest.py:190-201`）也补 4 个 None：

```python
                row['entry_hs300_dif_above_zero'] = None
                row['entry_hs300_bull_align'] = None
                row['entry_stock_bull_align'] = None
                row['entry_stock_above_ma25'] = None
```

- [ ] **Step 4: 运行集成测试 + 旧测试，确认全过**

Run: `cd my_strategy && python -m pytest tests/test_backtest.py -v`
Expected: 6 passed（5 原有 + 1 新增）

- [ ] **Step 5: Commit**

```bash
git add my_strategy/backtest.py my_strategy/tests/test_backtest.py
git commit -m "feat(backtest): record 4 entry regime flags in trade_summary"
```

---

## Task 3: attribution.py 加 4 张单维度 stats 报告

**Files:**
- Modify: `my_strategy/tools/attribution.py` (新增 4 个 compute_* 函数 + run() 注册)
- Modify: `my_strategy/tests/test_attribution.py` (4 个测试)

每张表格式与 `compute_exit_reason_stats` 类似，bucket 列名为 `flag_value`，取值 `"True"` / `"False"`（NA 行被 dropna 跳过）：

```
flag_value, count, win_rate, avg_return, avg_holding_days
True,       N1,    0.45,     5.20,       18.0
False,      N2,    0.32,     2.10,       22.0
```

- [ ] **Step 1: 在 `test_attribution.py` 末尾追加 4 个测试**

```python
def test_compute_hs300_dif_stats_basic():
    from tools.attribution import compute_hs300_dif_stats
    trades = pd.DataFrame([
        {'entry_hs300_dif_above_zero': True,  'return_pct': 5.0, 'holding_days': 10, 'status': 'completed'},
        {'entry_hs300_dif_above_zero': True,  'return_pct': -2.0, 'holding_days': 8,  'status': 'completed'},
        {'entry_hs300_dif_above_zero': False, 'return_pct': -3.0, 'holding_days': 12, 'status': 'completed'},
        {'entry_hs300_dif_above_zero': None,  'return_pct': 1.0, 'holding_days': 5,  'status': 'completed'},
    ])
    out = compute_hs300_dif_stats(trades)
    assert list(out['flag_value']) == ['True', 'False']  # NA 跳过；按 True/False 顺序
    true_row = out[out['flag_value'] == 'True'].iloc[0]
    assert true_row['count'] == 2
    assert true_row['win_rate'] == 0.5
    assert true_row['avg_return'] == round((5.0 + -2.0) / 2, 4)


def test_compute_hs300_bull_align_stats_basic():
    from tools.attribution import compute_hs300_bull_align_stats
    trades = pd.DataFrame([
        {'entry_hs300_bull_align': True,  'return_pct': 4.0, 'holding_days': 10, 'status': 'completed'},
        {'entry_hs300_bull_align': False, 'return_pct': -1.0, 'holding_days': 7, 'status': 'completed'},
    ])
    out = compute_hs300_bull_align_stats(trades)
    assert set(out['flag_value']) == {'True', 'False'}
    assert out[out['flag_value'] == 'True'].iloc[0]['win_rate'] == 1.0


def test_compute_stock_bull_align_stats_basic():
    from tools.attribution import compute_stock_bull_align_stats
    trades = pd.DataFrame([
        {'entry_stock_bull_align': True,  'return_pct': 3.0, 'holding_days': 9, 'status': 'completed'},
        {'entry_stock_bull_align': False, 'return_pct': -2.0, 'holding_days': 6, 'status': 'completed'},
    ])
    out = compute_stock_bull_align_stats(trades)
    assert len(out) == 2


def test_compute_stock_above_ma25_stats_basic():
    from tools.attribution import compute_stock_above_ma25_stats
    trades = pd.DataFrame([
        {'entry_stock_above_ma25': True,  'return_pct': 2.0, 'holding_days': 8,  'status': 'completed'},
        {'entry_stock_above_ma25': False, 'return_pct': -4.0, 'holding_days': 11, 'status': 'completed'},
    ])
    out = compute_stock_above_ma25_stats(trades)
    assert len(out) == 2


def test_compute_hs300_dif_stats_empty_input():
    from tools.attribution import compute_hs300_dif_stats
    out = compute_hs300_dif_stats(pd.DataFrame())
    assert out.empty
    assert list(out.columns) == ['flag_value', 'count', 'win_rate', 'avg_return', 'avg_holding_days']
```

- [ ] **Step 2: 运行确认测试失败**

Run: `cd my_strategy && python -m pytest tests/test_attribution.py -v -k "hs300 or bull_align or above_ma25"`
Expected: 5 个测试都报 ImportError

- [ ] **Step 3: 在 `attribution.py` 中添加共用 helper 和 4 个 compute_* 函数**

在 `compute_monthly_stats` 之后（约 line 472 之前的空行处）插入：

```python
def _compute_bool_flag_stats(trades, flag_col):
    """对单个布尔标志列做 2 桶聚合（True/False，NA dropna 跳过）。"""
    cols = ['flag_value', 'count', 'win_rate', 'avg_return', 'avg_holding_days']
    if trades.empty or flag_col not in trades.columns:
        return pd.DataFrame(columns=cols)
    sub = trades.dropna(subset=[flag_col]).copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    for value in [True, False]:
        chunk = sub[sub[flag_col] == value]
        if chunk.empty:
            continue
        ret = chunk['return_pct'].dropna() if 'return_pct' in chunk.columns else pd.Series(dtype=float)
        hold = chunk['holding_days'].dropna() if 'holding_days' in chunk.columns else pd.Series(dtype=float)
        rows.append({
            'flag_value': str(value),
            'count': len(chunk),
            'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
            'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
            'avg_holding_days': round(hold.mean(), 1) if len(hold) else float('nan'),
        })
    return pd.DataFrame(rows, columns=cols).reset_index(drop=True)


def compute_hs300_dif_stats(trades):
    """按 entry_hs300_dif_above_zero 分桶（HS300 MACD DIF 水上/水下）。"""
    return _compute_bool_flag_stats(trades, 'entry_hs300_dif_above_zero')


def compute_hs300_bull_align_stats(trades):
    """按 entry_hs300_bull_align 分桶（HS300 多头排列：ma25>ma60>ma144>ma180）。"""
    return _compute_bool_flag_stats(trades, 'entry_hs300_bull_align')


def compute_stock_bull_align_stats(trades):
    """按 entry_stock_bull_align 分桶（个股多头排列）。"""
    return _compute_bool_flag_stats(trades, 'entry_stock_bull_align')


def compute_stock_above_ma25_stats(trades):
    """按 entry_stock_above_ma25 分桶（个股 close > ma25）。"""
    return _compute_bool_flag_stats(trades, 'entry_stock_above_ma25')
```

注意：CSV 读回时 `True`/`False` 已是字符串（pandas 默认 to_csv 行为），但本函数收的 trades 是来自 `_enrich_trade_summary` 直接返回的 DataFrame，值是 Python `bool`。在 attribution.run() 中读 csv 时需要把字符串"True"/"False"还原 → 见 Step 4。

- [ ] **Step 4: 在 `attribution.py:run()` 中添加 4 个新报告写出 + dtype 修正**

在 `run()` 函数读 trades 后立即添加 dtype 转换（约 line 564 后）：

```python
    # 4 个 regime flag 列从 csv 读回是 "True"/"False"/空 字符串，转回 Optional[bool]
    for col in ['entry_hs300_dif_above_zero', 'entry_hs300_bull_align',
                'entry_stock_bull_align', 'entry_stock_above_ma25']:
        if col in trades.columns:
            trades[col] = trades[col].map(
                {'True': True, 'False': False, True: True, False: False}
            )  # 其他值（NaN/空字符串）自动变 NaN
```

并在 `monthly.to_csv(...)` 之后追加：

```python
    hs300_dif = compute_hs300_dif_stats(trades)
    hs300_dif.to_csv(out_dir / 'hs300_dif_stats.csv', index=False)

    hs300_bull = compute_hs300_bull_align_stats(trades)
    hs300_bull.to_csv(out_dir / 'hs300_bull_align_stats.csv', index=False)

    stock_bull = compute_stock_bull_align_stats(trades)
    stock_bull.to_csv(out_dir / 'stock_bull_align_stats.csv', index=False)

    stock_above = compute_stock_above_ma25_stats(trades)
    stock_above.to_csv(out_dir / 'stock_above_ma25_stats.csv', index=False)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd my_strategy && python -m pytest tests/test_attribution.py -v`
Expected: 全部 23 个测试通过（18 原有 + 5 新增）

- [ ] **Step 6: Commit**

```bash
git add my_strategy/tools/attribution.py my_strategy/tests/test_attribution.py
git commit -m "feat(attribution): add 4 single-flag regime stats reports"
```

---

## Task 4: attribution.py 加共振 2x2 表

**Files:**
- Modify: `my_strategy/tools/attribution.py`
- Modify: `my_strategy/tests/test_attribution.py`

桶规则：把 `entry_hs300_dif_above_zero`（大盘 DIF 水上水下，作 X 轴）× `entry_stock_bull_align`（个股多头排列，作 Y 轴）做 2x2，输出 4 行。NA 任一缺则该笔 dropna。

| combo | 含义 |
|-------|------|
| 大盘水上+个股多头 | 顺风顺水 |
| 大盘水上+个股非多头 | 大盘强但个股弱 |
| 大盘水下+个股多头 | 大盘弱但个股强 |
| 大盘水下+个股非多头 | 双弱 |

- [ ] **Step 1: 测试**

```python
def test_compute_regime_combo_stats_2x2():
    from tools.attribution import compute_regime_combo_stats
    trades = pd.DataFrame([
        # 顺风顺水
        {'entry_hs300_dif_above_zero': True,  'entry_stock_bull_align': True,
         'return_pct': 5.0, 'holding_days': 10, 'status': 'completed'},
        # 双弱
        {'entry_hs300_dif_above_zero': False, 'entry_stock_bull_align': False,
         'return_pct': -3.0, 'holding_days': 8, 'status': 'completed'},
        # 大盘水上+个股弱
        {'entry_hs300_dif_above_zero': True,  'entry_stock_bull_align': False,
         'return_pct': 1.0, 'holding_days': 6, 'status': 'completed'},
        # 大盘水下+个股强
        {'entry_hs300_dif_above_zero': False, 'entry_stock_bull_align': True,
         'return_pct': 2.0, 'holding_days': 7, 'status': 'completed'},
        # NA 行（应被 drop）
        {'entry_hs300_dif_above_zero': None,  'entry_stock_bull_align': True,
         'return_pct': 0.0, 'holding_days': 5, 'status': 'completed'},
    ])
    out = compute_regime_combo_stats(trades)
    assert len(out) == 4
    assert set(out['combo']) == {
        '大盘水上+个股多头', '大盘水上+个股非多头',
        '大盘水下+个股多头', '大盘水下+个股非多头',
    }
    sunny = out[out['combo'] == '大盘水上+个股多头'].iloc[0]
    assert sunny['count'] == 1
    assert sunny['win_rate'] == 1.0


def test_compute_regime_combo_stats_empty():
    from tools.attribution import compute_regime_combo_stats
    out = compute_regime_combo_stats(pd.DataFrame())
    assert out.empty
    assert list(out.columns) == ['combo', 'count', 'win_rate', 'avg_return', 'avg_holding_days']
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd my_strategy && python -m pytest tests/test_attribution.py -v -k regime_combo`
Expected: 2 个测试 ImportError

- [ ] **Step 3: 实现 `compute_regime_combo_stats`**

在 `attribution.py` 中 `compute_stock_above_ma25_stats` 之后插入：

```python
_REGIME_COMBO_LABELS = [
    ('大盘水上+个股多头', True, True),
    ('大盘水上+个股非多头', True, False),
    ('大盘水下+个股多头', False, True),
    ('大盘水下+个股非多头', False, False),
]


def compute_regime_combo_stats(trades):
    """大盘 DIF 水上水下 × 个股多头排列 2x2 共振分析。

    缺 entry_hs300_dif_above_zero 或 entry_stock_bull_align 的行被 dropna 跳过。
    输出固定 4 行，按上面 _REGIME_COMBO_LABELS 顺序。
    """
    cols = ['combo', 'count', 'win_rate', 'avg_return', 'avg_holding_days']
    required = ['entry_hs300_dif_above_zero', 'entry_stock_bull_align']
    if trades.empty or any(c not in trades.columns for c in required):
        return pd.DataFrame(columns=cols)
    sub = trades.dropna(subset=required).copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    for label, dif_v, bull_v in _REGIME_COMBO_LABELS:
        chunk = sub[(sub['entry_hs300_dif_above_zero'] == dif_v) &
                    (sub['entry_stock_bull_align'] == bull_v)]
        if chunk.empty:
            continue
        ret = chunk['return_pct'].dropna() if 'return_pct' in chunk.columns else pd.Series(dtype=float)
        hold = chunk['holding_days'].dropna() if 'holding_days' in chunk.columns else pd.Series(dtype=float)
        rows.append({
            'combo': label,
            'count': len(chunk),
            'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
            'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
            'avg_holding_days': round(hold.mean(), 1) if len(hold) else float('nan'),
        })
    return pd.DataFrame(rows, columns=cols).reset_index(drop=True)
```

- [ ] **Step 4: 在 `run()` 中追加输出**

在 4 个 single-flag 的 to_csv 之后追加：

```python
    regime_combo = compute_regime_combo_stats(trades)
    regime_combo.to_csv(out_dir / 'regime_combo_stats.csv', index=False)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd my_strategy && python -m pytest tests/test_attribution.py -v`
Expected: 25 passed（20 原有逻辑 + 5 现有 hs300 + 0 误差……实际为 18+5+2=25）

- [ ] **Step 6: Commit**

```bash
git add my_strategy/tools/attribution.py my_strategy/tests/test_attribution.py
git commit -m "feat(attribution): add regime_combo_stats (HS300 dif x stock bull align)"
```

---

## Task 5: 集成测试更新 + 真实回测验收

**Files:**
- Modify: `my_strategy/tests/test_attribution_run.py`

- [ ] **Step 1: 更新 `EXPECTED_FILES` 从 15 扩到 20**

定位 `test_attribution_run.py:17-33`，替换为：

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
    'first_buy_size_stats.csv',
    'add_block_stats.csv',
    'mfe_mae_by_exit.csv',
    'mfe_distribution.csv',
    'dea_lookback_stats.csv',
    'monthly_stats.csv',
    'hs300_dif_stats.csv',
    'hs300_bull_align_stats.csv',
    'stock_bull_align_stats.csv',
    'stock_above_ma25_stats.csv',
    'regime_combo_stats.csv',
]
```

- [ ] **Step 2: 跑一次真实回测 + 集成测试**

Run（依次）:
```bash
cd my_strategy
python backtest.py
python tests/test_attribution_run.py
```

Expected:
- 回测正常完成（5,911 笔附近，与之前一致）
- `[OK]` 出现 20 次，无 `[MISSING]`
- 4 张 hs300_*/stock_* 单维度表 each 行数 ≤ 2
- regime_combo_stats.csv 行数 ≤ 4

- [ ] **Step 3: 抽查 trade_summary.csv 新列**

Run:
```bash
python -c "
import pandas as pd
df = pd.read_csv('my_strategy/results/trade_summary.csv')
cols = ['entry_hs300_dif_above_zero','entry_hs300_bull_align',
        'entry_stock_bull_align','entry_stock_above_ma25']
for c in cols:
    print(c, df[c].value_counts(dropna=False).to_dict())
"
```

Expected:
- 4 个列都存在
- 值是 `True` / `False` 字符串 + 少量 NaN
- True/False 比例都不应为 0 或全部（否则代表逻辑或数据出错）

- [ ] **Step 4: 抽查 5 张新报告内容**

Run:
```bash
for f in hs300_dif_stats hs300_bull_align_stats stock_bull_align_stats stock_above_ma25_stats regime_combo_stats; do
  echo "=== $f ==="
  cat my_strategy/reports/$f.csv
done
```

Expected: 各表都至少有 1 行，且 win_rate / avg_return 是合理的小数。

- [ ] **Step 5: Commit 集成测试更新**

```bash
git add my_strategy/tests/test_attribution_run.py
git commit -m "test(attribution): extend integration test for 5 new regime reports"
```

---

## Task 6: 文档更新

**Files:**
- Modify: `docs/FEATURES.md`
- Modify: `docs/CHANGELOG.md`

- [ ] **Step 1: 更新 `docs/FEATURES.md`**

定位 §5.4 trade_summary 列说明部分，在 `entry_month_macd_zone` 之后追加 4 个新列说明：

```markdown
- `entry_hs300_dif_above_zero`：进场当日 HS300 MACD DIF 是否在 0 以上（True / False / 空）
- `entry_hs300_bull_align`：进场当日 HS300 是否完整多头排列（ma25>ma60>ma144>ma180）
- `entry_stock_bull_align`：进场当日个股是否完整多头排列
- `entry_stock_above_ma25`：进场当日个股是否站上 MA25
```

定位 §6 归因分析输出列表（当前 14 项），追加 5 项（变成 19 项）：

```markdown
15. `hs300_dif_stats.csv`：按 HS300 MACD DIF 水上/水下二桶统计胜率与收益
16. `hs300_bull_align_stats.csv`：按 HS300 多头排列 True/False 二桶统计
17. `stock_bull_align_stats.csv`：按个股多头排列 True/False 二桶统计
18. `stock_above_ma25_stats.csv`：按个股是否站上 MA25 二桶统计
19. `regime_combo_stats.csv`：HS300 DIF × 个股多头排列 2x2 共振表
```

- [ ] **Step 2: 在 `docs/CHANGELOG.md` 顶部追加条目**

```markdown
## 2026-05-07 — 入场环境快照与归因（第一阶段）
- 需求：在 trade_summary 写入入场时刻 4 个环境布尔标志（HS300 DIF 水上水下、HS300 多头排列、个股多头排列、个股站上 MA25），attribution 加 5 张新报告分析环境对胜率的影响
- 改动：
  - `my_strategy/backtest.py` 新增 `_compute_regime_flags`；`_enrich_trade_summary` 加载 HS300 indicators 并写入 4 个新列
  - `my_strategy/tools/attribution.py` 新增 5 个 compute 函数 + run() 注册；新增 `_compute_bool_flag_stats` helper
  - `my_strategy/tests/test_backtest.py` 新建，6 个测试覆盖纯函数和 enrich 集成
  - `my_strategy/tests/test_attribution.py` 增加 7 个测试
  - `my_strategy/tests/test_attribution_run.py` EXPECTED_FILES 15→20
- 影响：trade_summary.csv 新增 4 列；reports/ 目录新增 5 个 csv；不动 strategy.py，回测笔数和收益不变
```

- [ ] **Step 3: Commit docs**

```bash
git add docs/FEATURES.md docs/CHANGELOG.md
git commit -m "docs: document phase-1 entry regime snapshot attribution"
```

---

## 验收清单

- [ ] `pytest my_strategy/tests/` 全部通过（≈43 个测试：12 strategy + 25 attribution + 6 backtest）
- [ ] `python my_strategy/backtest.py` 跑通，trade_summary.csv 含 4 个新列且非全 NA
- [ ] `python my_strategy/tests/test_attribution_run.py` 报 `[OK]` 20 次
- [ ] 5 张新报告均有内容，胜率数值合理
- [ ] `docs/FEATURES.md` 和 `docs/CHANGELOG.md` 已更新
- [ ] 6 个 commit 全部落地 master，历史清晰

---

## 后续工作（不在本 plan 范围）

第二阶段：行业维度多/空标志位（详见 `MEMORY.md` 中 `project_phase2_sector_regime`）。需先补 `data/sw_index/` 申万行业指数数据 + `stock_sector.csv` 加 sw_index_code 映射列，再加 2 个标志位（行业指数多头排列、行业指数站上 MA25）和配套归因表。
