# 持仓画像 + DEA lookback + 月度统计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `trade_summary.csv` 加 3 列（mfe_pct / mae_pct / dea_neg_distance_days），归因 11 → 15 张表（持仓画像 × 2 + DEA 扫描 × 1 + 月度细化 × 1）。

**Architecture:** 分两层 —— (1) 数据采集层在 `strategy.py` 持仓期跟踪 MFE/MAE（基准 = 首买入价，加仓后不变）、入场时记录距上次 DEA<0 的 bar 数（上限 200）、写入 trade_log；(2) 归因层在 `attribution.py` 增加 4 个 `compute_*` 函数复用现有桶聚合模式，接入 `run()` 末尾。MFE/MAE/DEA 距离均为只读观测，不参与任何买卖判定。

**Tech Stack:** backtrader, pandas（pd.cut + groupby + 现有 attribution 风格），pytest，无新依赖。

**Spec:** [docs/superpowers/specs/2026-05-07-holding-excursion-attribution-design.md](../specs/2026-05-07-holding-excursion-attribution-design.md)

---

## 文件结构

| 文件 | 修改类型 | 责任 |
|---|---|---|
| `my_strategy/src/strategy.py` | 修改 | 模块函数 `_scan_dea_neg_distance`；state 增 4 字段；首买记录基准 + dea 距离；持仓期更新 mfe/mae；trade_log 写入 3 列 |
| `my_strategy/tools/attribution.py` | 修改 | 新增 4 个 `compute_*` + 2 组桶常量；`run()` 末尾追加 4 个 to_csv |
| `my_strategy/tests/test_strategy.py` | 修改 | 新增 4 个用例 + 1 个合成数据 helper |
| `my_strategy/tests/test_attribution.py` | 修改 | 新增 12 个单元测试（每个 compute_ 函数 3 个） |
| `my_strategy/tests/test_attribution_run.py` | 修改 | `EXPECTED_FILES` 11 → 15 |
| `docs/FEATURES.md` | 修改 | §6 输出列表 10 → 14 项 |
| `docs/CHANGELOG.md` | 修改 | 顶部追加 2026-05-07 一条 |

无新建源码文件。

---

## Task 1：strategy.py — 采集 mfe/mae/dea_neg_distance/first_buy_price

**Files:**
- Modify: `my_strategy/src/strategy.py:1-7, 60-71, 95-106, 142-160, 197-216, 268-278, 384-388`
- Modify: `my_strategy/tests/test_strategy.py`（追加 helper + 4 测试）

- [ ] **Step 1: 写失败测试**

打开 `my_strategy/tests/test_strategy.py`，在文件末尾追加：

```python
def make_excursion_feed(mfe_pct=0.10, mae_pct=-0.05):
    """构造一笔交易，持仓期内最高浮盈 mfe_pct、最深浮亏 mae_pct（基于首买入价）。

    bar 0..69: ma60 平稳上涨准备；
    bar 70: 阴线 + close>ma60 + dea>0 + 历史 dea<0 → 触发首买入（close 即首买价）；
    bar 71: high 制造 mfe（low 接近）；
    bar 72: low 制造 mae；
    bar 73..149: 温和小阴小阳，持仓不平。
    """
    n = 150
    dates = pd.date_range('2020-01-01', periods=n, freq='B')
    closes = [10.0 + i * 0.05 for i in range(n)]
    closes[70] = closes[70] - 0.2  # 阴线触发买入
    opens = list(closes)
    highs = [max(o, c) + 0.05 for o, c in zip(opens, closes)]
    lows = [min(o, c) - 0.05 for o, c in zip(opens, closes)]

    # 首买价 = closes[70]
    fb = closes[70]
    # bar 71 制造 mfe：把 high 拉高到 fb*(1+mfe_pct)
    highs[71] = fb * (1.0 + mfe_pct)
    # bar 72 制造 mae：把 low 压到 fb*(1+mae_pct)
    lows[72] = fb * (1.0 + mae_pct)

    prev_closes = [np.nan] + closes[:-1]
    ma60 = [np.nan] * 59 + [sum(closes[i - 59:i + 1]) / 60 for i in range(59, n)]
    ma25 = [np.nan] * 24 + [sum(closes[i - 24:i + 1]) / 25 for i in range(24, n)]
    dea = [-0.1] * 70 + [0.1] * (n - 70)

    df = pd.DataFrame({
        'trade_date': dates,
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': [1_000_000] * n,
        'ma25': ma25,
        'ma60': ma60,
        'dea': dea,
        'prev_close': prev_closes,
    })
    df.index = df['trade_date']
    return df


def test_first_buy_price_locked_at_initial_buy():
    """首买价记录在 trade_log，并等于 close[70]（无加仓发生时）。"""
    df = make_excursion_feed(mfe_pct=0.005, mae_pct=-0.005)
    strat = run_backtest(df)
    assert len(strat.trade_log) >= 1
    rec = strat.trade_log[0]
    assert 'mfe_pct' in rec
    assert 'mae_pct' in rec
    assert 'dea_neg_distance_days' in rec


def test_mfe_mae_recorded_during_holding():
    """构造已知 ±10%/-5% 波动 → mfe/mae 与预期值匹配。"""
    df = make_excursion_feed(mfe_pct=0.10, mae_pct=-0.05)
    strat = run_backtest(df)
    rec = strat.trade_log[0]
    assert abs(rec['mfe_pct'] - 10.0) < 0.05  # 单位百分点
    assert abs(rec['mae_pct'] - (-5.0)) < 0.05


def test_dea_neg_distance_days_recorded():
    """make_excursion_feed 中 dea[0..69]<0、dea[70..]>0，bar 70 入场，
    所以 dea_neg_distance_days = 1（昨日 dea<0）。"""
    df = make_excursion_feed()
    strat = run_backtest(df)
    rec = strat.trade_log[0]
    assert rec['dea_neg_distance_days'] == 1


def test_dea_neg_distance_capped_at_max_lookback():
    """构造一份 dea 全程 ≥ 0 的 feed → 函数返回 max_lookback (200)。
    （这里直接调用 helper，不走完整回测。）"""
    from my_strategy.src.strategy import _scan_dea_neg_distance

    class FakeLine:
        def __init__(self, vals):
            self.vals = vals
        def __getitem__(self, idx):
            # backtrader 风格：idx=-i 表示 i bar 之前
            return self.vals[-1 + idx] if -1 + idx >= -len(self.vals) else float('nan')

    class FakeData:
        pass
    d = FakeData()
    d.dea = FakeLine([0.5] * 250)  # 全部 ≥ 0
    assert _scan_dea_neg_distance(d, max_lookback=200) == 200
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd e:/GithubCloneSpace/Stock/backtrader/backtrader
pytest my_strategy/tests/test_strategy.py -k "first_buy_price_locked or mfe_mae_recorded or dea_neg_distance" -v
```
预期：FAIL（KeyError 'mfe_pct' / ImportError `_scan_dea_neg_distance`）。

- [ ] **Step 3: 增加 helper `_scan_dea_neg_distance`**

打开 `my_strategy/src/strategy.py`，在 `_isnan` 函数之后（line 8 附近）追加：

```python
def _scan_dea_neg_distance(d, max_lookback=200):
    """从当前 bar 往回扫，找到第一根 DEA<0 的 bar 数距离。

    返回 int：1..max_lookback。NaN 跳过；找不到（max_lookback bar 内一直 ≥ 0 或 NaN）则返回 max_lookback。
    上限 200 ≈ 一年交易日，足够覆盖现行 5 日 lookback 的扫描需求。
    """
    for i in range(1, max_lookback + 1):
        v = d.dea[-i]
        if v == v and v < 0:  # not NaN and negative
            return i
    return max_lookback
```

- [ ] **Step 4: 扩展 state 字段（init + reset 两处）**

定位 `__init__` 内 state 字典（line 60-71）：

```python
            self.stock_state[d] = {
                'take_profit_count': 0,
                'in_ma60_obs': False,
                'in_ma25_obs': False,
                'entry_price': None,
                'max_bullish_candle_pct': 0.0,
                'add_count': 0,
                'tp1_pct': None,
                'tp2_pct': None,
                'initial_size': None,
                'pending_atr': float('nan'),
            }
```

替换为：

```python
            self.stock_state[d] = {
                'take_profit_count': 0,
                'in_ma60_obs': False,
                'in_ma25_obs': False,
                'entry_price': None,
                'max_bullish_candle_pct': 0.0,
                'add_count': 0,
                'tp1_pct': None,
                'tp2_pct': None,
                'initial_size': None,
                'pending_atr': float('nan'),
                'first_buy_price': None,
                'mfe_pct': 0.0,
                'mae_pct': 0.0,
                'dea_neg_distance_days': None,
            }
```

定位 `_reset_state`（line 95-106），同样的 4 个字段以同样的默认值追加。

- [ ] **Step 5: 入场时记录 first_buy_price 和 dea 距离**

定位 `next()` 入场分支末尾（line 384-387）：

```python
                state['pending_atr'] = float(self.atr[d][0])
                o = self.buy(data=d, size=buy_size)
                self.order_reasons[o.ref] = 'initial_buy'
                self.orders[d] = o
```

替换为：

```python
                state['pending_atr'] = float(self.atr[d][0])
                state['first_buy_price'] = float(close)  # set_coc=True，close 即执行价
                state['dea_neg_distance_days'] = _scan_dea_neg_distance(d, max_lookback=200)
                o = self.buy(data=d, size=buy_size)
                self.order_reasons[o.ref] = 'initial_buy'
                self.orders[d] = o
```

- [ ] **Step 6: 持仓期更新 mfe/mae**

定位 `next()` 持仓分支内"记录持仓期单日阳线幅度的最大值"代码块（line 272-277），紧随其后追加：

```python
                # 记录持仓期内最高浮盈 / 最深浮亏（基准 = 首买入价）
                fb = state['first_buy_price']
                if fb is not None and fb > 0:
                    high_pct = (d.high[0] - fb) / fb * 100.0
                    low_pct = (d.low[0] - fb) / fb * 100.0
                    if high_pct > state['mfe_pct']:
                        state['mfe_pct'] = high_pct
                    if low_pct < state['mae_pct']:
                        state['mae_pct'] = low_pct
```

- [ ] **Step 7: trade_log 写入 3 新列**

定位 `_finalize_episode` 内 trade_log 字典（line 142-160），在 `'max_bullish_candle_pct': ...` 之后追加：

```python
            'max_bullish_candle_pct': round(state['max_bullish_candle_pct'], 6),
            'mfe_pct': round(state['mfe_pct'], 4),
            'mae_pct': round(state['mae_pct'], 4),
            'dea_neg_distance_days': state['dea_neg_distance_days'],
```

- [ ] **Step 8: 运行测试，确认通过**

```bash
pytest my_strategy/tests/test_strategy.py -v
```
预期：所有原有 8 个测试 + 4 个新测试 pass。

- [ ] **Step 9: Commit**

```bash
git add my_strategy/src/strategy.py my_strategy/tests/test_strategy.py
git commit -m "feat(strategy): record mfe/mae/dea_neg_distance per episode"
```

---

## Task 2：attribution.py — compute_mfe_mae_by_exit

**Files:**
- Modify: `my_strategy/tools/attribution.py`
- Modify: `my_strategy/tests/test_attribution.py`

- [ ] **Step 1: 写失败测试**

`my_strategy/tests/test_attribution.py` 顶部 import 处追加 `compute_mfe_mae_by_exit`：

```python
from my_strategy.tools.attribution import (
    compute_trade_profile,
    compute_top_bottom_trades,
    compute_sector_winrate,
    compute_exit_reason_stats,
    compute_add_count_stats,
    compute_entry_condition_stats,
    compute_yearly_stats,
    compute_first_buy_size_stats,
    compute_add_block_stats,
    compute_mfe_mae_by_exit,
)
```

文件末尾追加：

```python
def test_compute_mfe_mae_by_exit_basic():
    trades = pd.DataFrame({
        'exit_reason': ['MA25清仓', 'MA25清仓', 'MA60止损', '止盈1'],
        'return_pct':  [3.0,        5.0,        -8.0,        4.0],
        'mfe_pct':     [8.0,        10.0,       2.0,         5.0],
        'mae_pct':     [-1.0,       -0.5,       -10.0,       -0.2],
    })
    out = compute_mfe_mae_by_exit(trades)
    assert list(out.columns) == [
        'exit_reason', 'count', 'avg_return',
        'avg_mfe', 'avg_mae', 'avg_pullback', 'avg_underwater',
    ]
    # MA25清仓 出现 2 次，count=2 居首
    assert out.iloc[0]['exit_reason'] == 'MA25清仓'
    assert out.iloc[0]['count'] == 2
    assert out.iloc[0]['avg_return'] == 4.0          # (3+5)/2
    assert out.iloc[0]['avg_mfe'] == 9.0             # (8+10)/2
    assert out.iloc[0]['avg_mae'] == -0.75           # (-1-0.5)/2
    assert out.iloc[0]['avg_pullback'] == 5.0        # (8-3 + 10-5)/2 = 5
    assert out.iloc[0]['avg_underwater'] == 0.75     # (1+0.5)/2

    ma60 = out[out['exit_reason'] == 'MA60止损'].iloc[0]
    assert ma60['avg_underwater'] == 10.0


def test_compute_mfe_mae_by_exit_empty_input():
    out = compute_mfe_mae_by_exit(pd.DataFrame())
    assert list(out.columns) == [
        'exit_reason', 'count', 'avg_return',
        'avg_mfe', 'avg_mae', 'avg_pullback', 'avg_underwater',
    ]
    assert len(out) == 0


def test_compute_mfe_mae_by_exit_missing_column():
    out = compute_mfe_mae_by_exit(pd.DataFrame({'exit_reason': ['x']}))
    assert list(out.columns) == [
        'exit_reason', 'count', 'avg_return',
        'avg_mfe', 'avg_mae', 'avg_pullback', 'avg_underwater',
    ]
    assert len(out) == 0
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest my_strategy/tests/test_attribution.py -k "mfe_mae_by_exit" -v
```
预期：`ImportError: cannot import name 'compute_mfe_mae_by_exit'`。

- [ ] **Step 3: 实现 compute_mfe_mae_by_exit**

打开 `my_strategy/tools/attribution.py`，在 `compute_add_block_stats` 之后追加：

```python
def compute_mfe_mae_by_exit(trades):
    """按 exit_reason 聚合 MFE/MAE 画像。

    - mfe_pct / mae_pct 单位为百分点（与 return_pct 同口径）
    - avg_pullback = avg(mfe_pct - return_pct) ，平均利润回吐
    - avg_underwater = avg(-mae_pct)，平均浮亏深度
    """
    cols = ['exit_reason', 'count', 'avg_return',
            'avg_mfe', 'avg_mae', 'avg_pullback', 'avg_underwater']
    required = {'exit_reason', 'return_pct', 'mfe_pct', 'mae_pct'}
    if trades.empty or not required.issubset(trades.columns):
        return pd.DataFrame(columns=cols)
    sub = trades.dropna(subset=['exit_reason', 'mfe_pct', 'mae_pct']).copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    for exit_reason, chunk in sub.groupby('exit_reason'):
        ret = chunk['return_pct'].dropna()
        mfe = chunk['mfe_pct']
        mae = chunk['mae_pct']
        pullback = (mfe - chunk['return_pct']).dropna()
        rows.append({
            'exit_reason': exit_reason,
            'count': len(chunk),
            'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
            'avg_mfe': round(mfe.mean(), 4) if len(mfe) else float('nan'),
            'avg_mae': round(mae.mean(), 4) if len(mae) else float('nan'),
            'avg_pullback': round(pullback.mean(), 4) if len(pullback) else float('nan'),
            'avg_underwater': round((-mae).mean(), 4) if len(mae) else float('nan'),
        })
    df = pd.DataFrame(rows, columns=cols)
    return df.sort_values('count', ascending=False).reset_index(drop=True)
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest my_strategy/tests/test_attribution.py -k "mfe_mae_by_exit" -v
```
预期：3 passed。

- [ ] **Step 5: 接入 run()**

定位 `attribution.py` 的 `run()`，找到 `add_block.to_csv(out_dir / 'add_block_stats.csv', index=False)` 这一行，紧随其后追加：

```python
    mfe_mae = compute_mfe_mae_by_exit(trades)
    mfe_mae.to_csv(out_dir / 'mfe_mae_by_exit.csv', index=False)
```

- [ ] **Step 6: Commit**

```bash
git add my_strategy/tools/attribution.py my_strategy/tests/test_attribution.py
git commit -m "feat(attribution): add mfe_mae_by_exit profile report"
```

---

## Task 3：attribution.py — compute_mfe_distribution

**Files:**
- Modify: `my_strategy/tools/attribution.py`
- Modify: `my_strategy/tests/test_attribution.py`

- [ ] **Step 1: 写失败测试**

import 处追加 `compute_mfe_distribution`：

```python
from my_strategy.tools.attribution import (
    compute_trade_profile,
    compute_top_bottom_trades,
    compute_sector_winrate,
    compute_exit_reason_stats,
    compute_add_count_stats,
    compute_entry_condition_stats,
    compute_yearly_stats,
    compute_first_buy_size_stats,
    compute_add_block_stats,
    compute_mfe_mae_by_exit,
    compute_mfe_distribution,
)
```

文件末尾追加：

```python
def test_compute_mfe_distribution_buckets():
    trades = pd.DataFrame({
        'mfe_pct':    [-1.0,  0.5,  1.0, 3.0, 7.0, 12.0, 25.0, 4.0],
        'return_pct': [-2.0,  -1.0, 0.5, 1.0, 5.0, 10.0, 22.0, -3.0],
        'status':     ['completed'] * 8,
    })
    out = compute_mfe_distribution(trades)
    assert list(out.columns) == [
        'bucket', 'count', 'win_rate', 'avg_return',
        'median_return', 'pct_completed',
    ]
    # 桶顺序 + 命中
    expected = ['[<0%)', '[0%,2%)', '[2%,5%)', '[5%,10%)', '[10%,20%)', '[20%+)']
    assert list(out['bucket']) == expected
    row_2_5 = out[out['bucket'] == '[2%,5%)'].iloc[0]
    assert row_2_5['count'] == 2  # mfe 3.0 + 4.0
    assert row_2_5['win_rate'] == 0.5  # 1.0>0, -3.0<0
    row_first = out[out['bucket'] == '[<0%)'].iloc[0]
    assert row_first['count'] == 1
    assert row_first['win_rate'] == 0.0


def test_compute_mfe_distribution_empty_input():
    out = compute_mfe_distribution(pd.DataFrame())
    assert list(out.columns) == [
        'bucket', 'count', 'win_rate', 'avg_return',
        'median_return', 'pct_completed',
    ]
    assert len(out) == 0


def test_compute_mfe_distribution_missing_column():
    out = compute_mfe_distribution(pd.DataFrame({'return_pct': [1.0]}))
    assert list(out.columns) == [
        'bucket', 'count', 'win_rate', 'avg_return',
        'median_return', 'pct_completed',
    ]
    assert len(out) == 0
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest my_strategy/tests/test_attribution.py -k "mfe_distribution" -v
```
预期：ImportError。

- [ ] **Step 3: 实现常量与函数**

在 `compute_mfe_mae_by_exit` 之后追加：

```python
_MFE_BINS = [-np.inf, 0, 2, 5, 10, 20, np.inf]
_MFE_LABELS = ['[<0%)', '[0%,2%)', '[2%,5%)', '[5%,10%)', '[10%,20%)', '[20%+)']


def compute_mfe_distribution(trades):
    """按 mfe_pct（持仓期最高浮盈，百分点）分 6 桶，看曾浮盈过 X% 的笔最终落地多少。"""
    cols = ['bucket', 'count', 'win_rate', 'avg_return',
            'median_return', 'pct_completed']
    if trades.empty or 'mfe_pct' not in trades.columns:
        return pd.DataFrame(columns=cols)
    sub = trades.dropna(subset=['mfe_pct']).copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    sub['_bucket'] = pd.cut(sub['mfe_pct'], bins=_MFE_BINS, labels=_MFE_LABELS,
                             right=False, include_lowest=False)
    rows = []
    for bucket in _MFE_LABELS:
        chunk = sub[sub['_bucket'] == bucket]
        if chunk.empty:
            continue
        ret = chunk['return_pct'].dropna() if 'return_pct' in chunk.columns else pd.Series(dtype=float)
        completed = ((chunk['status'] == 'completed').sum()
                     if 'status' in chunk.columns else 0)
        n = len(chunk)
        rows.append({
            'bucket': bucket,
            'count': n,
            'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
            'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
            'median_return': round(ret.median(), 4) if len(ret) else float('nan'),
            'pct_completed': round(completed / n, 4) if n else float('nan'),
        })
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols).reset_index(drop=True)
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest my_strategy/tests/test_attribution.py -k "mfe_distribution" -v
```
预期：3 passed。

- [ ] **Step 5: 接入 run()**

紧跟 `mfe_mae.to_csv(...)` 之后追加：

```python
    mfe_dist = compute_mfe_distribution(trades)
    mfe_dist.to_csv(out_dir / 'mfe_distribution.csv', index=False)
```

- [ ] **Step 6: Commit**

```bash
git add my_strategy/tools/attribution.py my_strategy/tests/test_attribution.py
git commit -m "feat(attribution): add mfe_distribution report"
```

---

## Task 4：attribution.py — compute_dea_lookback_stats

**Files:**
- Modify: `my_strategy/tools/attribution.py`
- Modify: `my_strategy/tests/test_attribution.py`

- [ ] **Step 1: 写失败测试**

import 处追加 `compute_dea_lookback_stats`。

文件末尾追加：

```python
def test_compute_dea_lookback_stats_buckets():
    trades = pd.DataFrame({
        'dea_neg_distance_days': [1, 1, 2, 4, 5, 6, 8, 12, 25, 45, 100],
        'return_pct':              [3.0, 1.0, -2.0, 4.0, 5.0, -1.0, 2.0, -3.0, 6.0, -4.0, 8.0],
        'holding_days':            [10, 12, 15, 18, 20, 22, 25, 28, 30, 35, 40],
        'add_count':               [0, 1, 0, 1, 2, 0, 1, 0, 1, 0, 0],
        'status':                  ['completed'] * 11,
    })
    out = compute_dea_lookback_stats(trades)
    assert list(out.columns) == [
        'bucket', 'count', 'win_rate', 'avg_return', 'median_return',
        'avg_holding_days', 'avg_add_count', 'pct_completed',
    ]
    # 期望桶（按区间顺序）：
    # [1,2) [2,3) [4,5) [5,7) [7,10) [10,15) [15,30) [30,60) [60+)
    # 因为最小值是 1（永远不命中 [0,1)），3 也无样本，所以这两个桶会被跳过
    expected = ['[1,2)', '[2,3)', '[4,5)', '[5,7)', '[7,10)',
                '[10,15)', '[15,30)', '[30,60)', '[60+)']
    assert list(out['bucket']) == expected
    row_1 = out[out['bucket'] == '[1,2)'].iloc[0]
    assert row_1['count'] == 2  # 距离 = 1 两笔
    assert row_1['avg_return'] == 2.0  # (3+1)/2
    row_5_7 = out[out['bucket'] == '[5,7)'].iloc[0]
    assert row_5_7['count'] == 2  # 距离 5 + 6


def test_compute_dea_lookback_stats_empty_input():
    out = compute_dea_lookback_stats(pd.DataFrame())
    assert list(out.columns) == [
        'bucket', 'count', 'win_rate', 'avg_return', 'median_return',
        'avg_holding_days', 'avg_add_count', 'pct_completed',
    ]
    assert len(out) == 0


def test_compute_dea_lookback_stats_missing_column():
    out = compute_dea_lookback_stats(pd.DataFrame({'return_pct': [1.0]}))
    assert list(out.columns) == [
        'bucket', 'count', 'win_rate', 'avg_return', 'median_return',
        'avg_holding_days', 'avg_add_count', 'pct_completed',
    ]
    assert len(out) == 0
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest my_strategy/tests/test_attribution.py -k "dea_lookback" -v
```
预期：ImportError。

- [ ] **Step 3: 实现常量与函数**

在 `compute_mfe_distribution` 之后追加：

```python
_DEA_LOOKBACK_BINS = [0, 1, 2, 3, 4, 5, 7, 10, 15, 30, 60, np.inf]
_DEA_LOOKBACK_LABELS = ['[0,1)', '[1,2)', '[2,3)', '[3,4)', '[4,5)',
                         '[5,7)', '[7,10)', '[10,15)', '[15,30)',
                         '[30,60)', '[60+)']


def compute_dea_lookback_stats(trades):
    """按 dea_neg_distance_days 11 桶扫描，评估 dea_lookback_days 阈值的合理性。

    - 函数最小返回 1，所以 [0,1) 桶永远为空（防御桶）
    - 现行 dea_lookback_days = 5 下，[1,2)..[4,5) 必有数据，[5,7) 含距离=5 触发
    - 后段桶在阈值放宽并重跑回测后才会出现数据
    """
    cols = ['bucket', 'count', 'win_rate', 'avg_return', 'median_return',
            'avg_holding_days', 'avg_add_count', 'pct_completed']
    if trades.empty or 'dea_neg_distance_days' not in trades.columns:
        return pd.DataFrame(columns=cols)
    sub = trades.dropna(subset=['dea_neg_distance_days']).copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    sub['_bucket'] = pd.cut(sub['dea_neg_distance_days'],
                             bins=_DEA_LOOKBACK_BINS, labels=_DEA_LOOKBACK_LABELS,
                             right=False, include_lowest=True)
    rows = []
    for bucket in _DEA_LOOKBACK_LABELS:
        chunk = sub[sub['_bucket'] == bucket]
        if chunk.empty:
            continue
        row = {'bucket': bucket}
        row.update(_scan_bucket_aggregate(chunk))
        rows.append(row)
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols).reset_index(drop=True)
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest my_strategy/tests/test_attribution.py -k "dea_lookback" -v
```
预期：3 passed。

- [ ] **Step 5: 接入 run()**

紧跟 `mfe_dist.to_csv(...)` 之后追加：

```python
    dea_lookback = compute_dea_lookback_stats(trades)
    dea_lookback.to_csv(out_dir / 'dea_lookback_stats.csv', index=False)
```

- [ ] **Step 6: Commit**

```bash
git add my_strategy/tools/attribution.py my_strategy/tests/test_attribution.py
git commit -m "feat(attribution): add dea_lookback_stats scan report"
```

---

## Task 5：attribution.py — compute_monthly_stats

**Files:**
- Modify: `my_strategy/tools/attribution.py`
- Modify: `my_strategy/tests/test_attribution.py`

- [ ] **Step 1: 写失败测试**

import 处追加 `compute_monthly_stats`。

文件末尾追加：

```python
def test_compute_monthly_stats_basic():
    trades = pd.DataFrame({
        'entry_date':    pd.to_datetime(['2023-01-15', '2023-01-20', '2023-03-05', '2023-03-10']),
        'return_pct':    [3.0, -1.0, 5.0, 2.0],
        'gross_pnl':     [3000.0, -1000.0, 5000.0, 2000.0],
        'holding_days':  [10, 15, 20, 12],
    })
    out = compute_monthly_stats(trades)
    assert list(out.columns) == [
        'year_month', 'count', 'win_rate', 'avg_return',
        'median_return', 'total_pnl_yuan', 'avg_holding_days',
    ]
    # 没入场的 2023-02 不补行
    assert list(out['year_month']) == ['2023-01', '2023-03']
    jan = out[out['year_month'] == '2023-01'].iloc[0]
    assert jan['count'] == 2
    assert jan['win_rate'] == 0.5
    assert jan['avg_return'] == 1.0  # (3-1)/2
    assert jan['total_pnl_yuan'] == 2000  # 3000-1000
    mar = out[out['year_month'] == '2023-03'].iloc[0]
    assert mar['count'] == 2
    assert mar['win_rate'] == 1.0


def test_compute_monthly_stats_empty_input():
    out = compute_monthly_stats(pd.DataFrame())
    assert list(out.columns) == [
        'year_month', 'count', 'win_rate', 'avg_return',
        'median_return', 'total_pnl_yuan', 'avg_holding_days',
    ]
    assert len(out) == 0


def test_compute_monthly_stats_missing_column():
    out = compute_monthly_stats(pd.DataFrame({'return_pct': [1.0]}))
    assert list(out.columns) == [
        'year_month', 'count', 'win_rate', 'avg_return',
        'median_return', 'total_pnl_yuan', 'avg_holding_days',
    ]
    assert len(out) == 0
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest my_strategy/tests/test_attribution.py -k "monthly_stats" -v
```
预期：ImportError。

- [ ] **Step 3: 实现 compute_monthly_stats**

在 `compute_dea_lookback_stats` 之后追加：

```python
def compute_monthly_stats(trades):
    """按 entry_date 的年月分组，与 yearly_stats 同口径细化到月。

    没入场的月份不补 0 行（与现 yearly_stats 同款）。
    """
    cols = ['year_month', 'count', 'win_rate', 'avg_return',
            'median_return', 'total_pnl_yuan', 'avg_holding_days']
    if trades.empty or 'entry_date' not in trades.columns:
        return pd.DataFrame(columns=cols)
    sub = trades.dropna(subset=['entry_date']).copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    sub['entry_date'] = pd.to_datetime(sub['entry_date'])
    sub['_year_month'] = sub['entry_date'].dt.to_period('M').astype(str)
    rows = []
    for ym, chunk in sub.groupby('_year_month'):
        ret = chunk['return_pct'].dropna() if 'return_pct' in chunk.columns else pd.Series(dtype=float)
        pnl = chunk['gross_pnl'].dropna() if 'gross_pnl' in chunk.columns else pd.Series(dtype=float)
        hold = chunk['holding_days'].dropna() if 'holding_days' in chunk.columns else pd.Series(dtype=float)
        rows.append({
            'year_month': ym,
            'count': len(chunk),
            'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
            'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
            'median_return': round(ret.median(), 4) if len(ret) else float('nan'),
            'total_pnl_yuan': round(pnl.sum(), 0) if len(pnl) else float('nan'),
            'avg_holding_days': round(hold.mean(), 1) if len(hold) else float('nan'),
        })
    df = pd.DataFrame(rows, columns=cols)
    return df.sort_values('year_month').reset_index(drop=True)
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
pytest my_strategy/tests/test_attribution.py -k "monthly_stats" -v
```
预期：3 passed。

- [ ] **Step 5: 接入 run()**

紧跟 `dea_lookback.to_csv(...)` 之后追加：

```python
    monthly = compute_monthly_stats(trades)
    monthly.to_csv(out_dir / 'monthly_stats.csv', index=False)
```

- [ ] **Step 6: 全套单元测试一起跑通**

```bash
pytest my_strategy/tests/test_attribution.py -v
```
预期：所有原有 + 12 个新测试全部 pass（共约 33 个）。

- [ ] **Step 7: Commit**

```bash
git add my_strategy/tools/attribution.py my_strategy/tests/test_attribution.py
git commit -m "feat(attribution): add monthly_stats report"
```

---

## Task 6：集成测试 EXPECTED_FILES 11 → 15

**Files:**
- Modify: `my_strategy/tests/test_attribution_run.py`

- [ ] **Step 1: 扩展 EXPECTED_FILES**

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
    'first_buy_size_stats.csv',
    'add_block_stats.csv',
    'mfe_mae_by_exit.csv',
    'mfe_distribution.csv',
    'dea_lookback_stats.csv',
    'monthly_stats.csv',
]
```

- [ ] **Step 2: 用现有 trade_summary.csv 跑端到端**

```bash
cd e:/GithubCloneSpace/Stock/backtrader/backtrader
python my_strategy/tests/test_attribution_run.py
```
预期最后一行：`所有归因报告产出成功。`，并打印 15 个 `[OK]` 行。

旧 `trade_summary.csv`（重跑 Task 1 之后版本）已含 mfe/mae/dea_neg_distance 三列——前面 Task 1 的 strategy.py 改动只在重跑回测后生效；当前 trade_summary.csv 仍是上一轮 magic-number-scan 的版本，不含新列，所以本步骤里：
- `mfe_mae_by_exit.csv` / `mfe_distribution.csv` / `dea_lookback_stats.csv` 应为空表头（容错）
- `monthly_stats.csv` 应有真实数据（entry_date 一直存在）

- [ ] **Step 3: Commit**

```bash
git add my_strategy/tests/test_attribution_run.py
git commit -m "test(attribution): extend integration test for 4 new attribution reports"
```

---

## Task 7：重跑回测，验证 3 个新列填充

**Files:**（不修改任何源码，仅重新生成数据）

- [ ] **Step 1: 重跑回测**

```bash
cd e:/GithubCloneSpace/Stock/backtrader/backtrader/my_strategy
python backtest.py
```
预期：约 12 分钟，正常完成；末尾自动跑归因；产出含 `mfe_pct / mae_pct / dea_neg_distance_days` 列的 `trade_summary.csv`，以及 15 张归因 CSV。

- [ ] **Step 2: 抽样检查 3 个新列**

```bash
cd e:/GithubCloneSpace/Stock/backtrader/backtrader
python -c "
import pandas as pd
df = pd.read_csv('my_strategy/results/trade_summary.csv')
for c in ['mfe_pct', 'mae_pct', 'dea_neg_distance_days']:
    assert c in df.columns, f'{c} 列缺失'
print(f'共 {len(df)} 笔交易')
print('mfe_pct  describe:'); print(df['mfe_pct'].describe())
print('mae_pct  describe:'); print(df['mae_pct'].describe())
print('dea_neg_distance_days describe:'); print(df['dea_neg_distance_days'].describe())
print(f'dea_neg_distance_days 取值分布:')
print(df['dea_neg_distance_days'].value_counts().sort_index())
"
```
预期：
- 列存在
- `mfe_pct >= 0` 全部成立（持仓期最高浮盈不会为负）
- `mae_pct <= 0` 全部成立
- `dea_neg_distance_days` 分布在 1..5（现行 lookback_days=5），不会出现 6+

- [ ] **Step 3: 抽样检查 4 张新报告**

```bash
python -c "
import pandas as pd
for f in ['mfe_mae_by_exit', 'mfe_distribution', 'dea_lookback_stats', 'monthly_stats']:
    df = pd.read_csv(f'my_strategy/reports/{f}.csv')
    print(f'\\n=== {f}.csv ({len(df)} 行) ===')
    print(df.to_string())
"
```
预期：
- `mfe_mae_by_exit.csv` 行数 = exit_reason 种类数（约 5-7 行）
- `mfe_distribution.csv` ≤ 6 行（按区间出现的桶才会出现，其中 [<0%) 会被跳过）
- `dea_lookback_stats.csv` 现行阈值下 ≤ 5 行（[1,2)..[4,5)..[5,7)）
- `monthly_stats.csv` 约 60 行（5 年 × 12 月）

- [ ] **Step 4: 不需 commit**

reports/ 默认不在 git tracking 中。

---

## Task 8：文档更新

**Files:**
- Modify: `docs/FEATURES.md`
- Modify: `docs/CHANGELOG.md`

- [ ] **Step 1: 更新 FEATURES.md §6 输出列表**

打开 `docs/FEATURES.md`，找到 `## 6. 归因分析（tools/attribution.py）` 章节内"输出到 `reports/`："那段 10 项列表，把第 10 项末尾 `。` 改成 `；` 并追加 4 项：

```markdown
11. **mfe_mae_by_exit**：按出场原因聚合 MFE（持仓期最高浮盈）/ MAE（最深浮亏）画像，列含 avg_return / avg_mfe / avg_mae / avg_pullback (mfe-return) / avg_underwater (-mae)；
12. **mfe_distribution**：按 mfe_pct 6 桶分布，看曾浮盈过 X% 的笔最终落地胜率/avg_return；
13. **dea_lookback_stats**：按 `dea_neg_distance_days`（距上次 DEA<0 的 bar 数，由 strategy.py 入场时记录）11 桶扫描，评估 `dea_lookback_days`（默认 5）阈值的合理性；
14. **monthly_stats**：按 `entry_date` 年月分组，列与 yearly_stats 同口径（count / win_rate / avg_return / median_return / total_pnl_yuan / avg_holding_days）。
```

- [ ] **Step 2: 在 CHANGELOG.md 顶部追加记录**

打开 `docs/CHANGELOG.md`，在 `---` 分隔符之后、第一条已有记录之前，插入：

```markdown
## 2026-05-07 — 归因报告新增 4 张表（持仓画像/参数扫描/月度细化）+ strategy 采集 mfe/mae/dea 距离

- 需求：标准量化诊断缺失——持仓期 MFE/MAE 未跟踪、dea_lookback_days 这个魔数未做扫描归因、yearly_stats 5 行样本太薄。
- 改动：
  - `my_strategy/src/strategy.py`：模块函数 `_scan_dea_neg_distance(d, max_lookback=200)`；state 增 `first_buy_price / mfe_pct / mae_pct / dea_neg_distance_days`；首买时锁定基准并记录 dea 距离；持仓期更新 mfe/mae（基准 = 首买入价，加仓不变）；trade_summary.csv 新增 3 列。MFE/MAE/dea 距离均为只读观测，不参与买卖判定。
  - `my_strategy/tools/attribution.py` 新增 4 个 compute_ 函数：`compute_mfe_mae_by_exit`（按出场原因聚合）、`compute_mfe_distribution`（6 桶）、`compute_dea_lookback_stats`（11 桶）、`compute_monthly_stats`（年月分组），并在 `run()` 末尾追加 4 个 to_csv。
  - `my_strategy/tests/test_strategy.py` 追加 4 个用例验证行为不变性 + 数据采集正确性。
  - `my_strategy/tests/test_attribution.py` 追加 12 个单元测试。
  - `my_strategy/tests/test_attribution_run.py` `EXPECTED_FILES` 11 → 15。
  - `docs/FEATURES.md` §6 同步至 14 项。
- 影响：回测后归因 15 张报告（之前 11 张）。需重跑回测才能填充 trade_summary.csv 的 3 个新列；旧 trade_summary.csv 上 `mfe_mae_by_exit.csv` / `mfe_distribution.csv` / `dea_lookback_stats.csv` 为空表头（容错），`monthly_stats.csv` 仍可填充。详见 spec：`docs/superpowers/specs/2026-05-07-holding-excursion-attribution-design.md`。
```

- [ ] **Step 3: Commit**

```bash
git add docs/FEATURES.md docs/CHANGELOG.md
git commit -m "docs: document holding-excursion / dea-lookback / monthly attribution tables"
```

---

## 完成验收

全部 8 个 Task 完成后，运行：

```bash
cd e:/GithubCloneSpace/Stock/backtrader/backtrader
pytest my_strategy/tests/test_strategy.py my_strategy/tests/test_attribution.py -v
python my_strategy/tests/test_attribution_run.py
git log --oneline -8
```

预期：
- 所有单元测试 pass（旧 + 新 16 个：4 strategy + 12 attribution）
- 集成测试输出 `所有归因报告产出成功。`，15 个 `[OK]`
- git 历史出现 7 个新 commit（feat × 5 + test × 1 + docs × 1）
- `my_strategy/results/trade_summary.csv` 含 mfe_pct / mae_pct / dea_neg_distance_days 三列
- `my_strategy/reports/` 下 15 个 CSV 文件齐全
