# 魔数扫描归因 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `trade_summary.csv` 加 `max_bullish_candle_pct` 列，并在 attribution 中产出 2 张魔数扫描表（`first_buy_size_stats.csv` / `add_block_stats.csv`），用于事前评估策略中两个 1% 魔数的合理性。

**Architecture:** 分两层 —— (1) 数据采集层在 `strategy.py` 把 bool `big_candle_seen` 升级为 float `max_bullish_candle_pct`，行为完全等价（加仓判定从 `not seen` 改为 `<= 0.01`），并写入 `trade_summary.csv`；(2) 归因层在 `attribution.py` 增加 2 个 `compute_*` 函数沿用现有 `pd.cut` + groupby 模式，接入 `run()` 末尾。

**Tech Stack:** backtrader, pandas（pd.cut + groupby + 现有 attribution 风格），pytest，无新依赖。

**Spec:** [docs/superpowers/specs/2026-05-07-magic-number-scan-design.md](../specs/2026-05-07-magic-number-scan-design.md)

---

## 文件结构

| 文件 | 修改类型 | 责任 |
|---|---|---|
| `my_strategy/src/strategy.py` | 修改 | `state['big_candle_seen']`→`state['max_bullish_candle_pct']`；记录 max；加仓判定改阈值；写 trade_log |
| `my_strategy/tools/attribution.py` | 修改 | 新增 2 个 `compute_*` 函数 + 模块常量；`run()` 末尾追加 2 个 to_csv |
| `my_strategy/tests/test_strategy.py` | 修改 | 追加 1 个用例验证 max_bullish_candle_pct 写入正确 + 加仓阻断行为不变 |
| `my_strategy/tests/test_attribution.py` | 修改 | 新增 6 个单元测试 |
| `my_strategy/tests/test_attribution_run.py` | 修改 | `EXPECTED_FILES` 9→11 |
| `docs/FEATURES.md` | 修改 | §6 输出列表追加 2 项 |
| `docs/CHANGELOG.md` | 修改 | 顶部追加 2026-05-07 一条 |

无新建源码文件。

---

## Task 1：strategy.py — 升级 big_candle_seen 为 max_bullish_candle_pct

**Files:**
- Modify: `my_strategy/src/strategy.py:65, 100, 271-274` 以及 `_finalize_episode` 内的 trade_log 写入
- Modify: `my_strategy/tests/test_strategy.py`（追加测试）

- [ ] **Step 1: 写失败测试**

打开 `my_strategy/tests/test_strategy.py`，在文件末尾追加：

```python
def make_hold_feed_with_big_candle(big_candle_pct=0.02):
    """生成在持仓期会出现 big_candle_pct 大小阳线的合成数据。

    前 70 bar 同 make_feed 的稳定上涨；bar 70 阴线触发买入；
    bar 80 制造一根 (close-open)/open == big_candle_pct 的阳线；
    其余 bar 仍是温和的小阴小阳。
    """
    n = 150
    dates = pd.date_range('2020-01-01', periods=n, freq='B')
    closes = [10.0 + i * 0.05 for i in range(n)]
    closes[70] = closes[70] - 0.2  # 阴线触发买入

    opens = list(closes)
    opens[80] = closes[80] / (1.0 + big_candle_pct)  # 让 bar 80 收阳 big_candle_pct

    prev_closes = [np.nan] + closes[:-1]
    ma60 = [np.nan] * 59 + [sum(closes[i - 59:i + 1]) / 60 for i in range(59, n)]
    ma25 = [np.nan] * 24 + [sum(closes[i - 24:i + 1]) / 25 for i in range(24, n)]
    dea = [-0.1] * 70 + [0.1] * (n - 70)

    df = pd.DataFrame({
        'trade_date': dates,
        'open': opens,
        'high': [max(o, c) + 0.05 for o, c in zip(opens, closes)],
        'low':  [min(o, c) - 0.05 for o, c in zip(opens, closes)],
        'close': closes,
        'volume': [1_000_000] * n,
        'ma25': ma25,
        'ma60': ma60,
        'dea': dea,
        'prev_close': prev_closes,
    })
    df.index = df['trade_date']
    return df


def test_max_bullish_candle_pct_recorded_in_trade_log():
    """持仓期出现 2% 阳线 → trade_log 的 max_bullish_candle_pct ≈ 0.02。"""
    df = make_hold_feed_with_big_candle(big_candle_pct=0.02)
    strat = run_backtest(df)  # run_backtest 同文件已有
    assert len(strat.trade_log) >= 1
    rec = strat.trade_log[0]
    assert 'max_bullish_candle_pct' in rec
    assert abs(rec['max_bullish_candle_pct'] - 0.02) < 1e-6


def test_add_blocked_when_max_bullish_above_threshold():
    """阳线 2% > 0.01 → 后续加仓被阻断 → add_count == 0。"""
    df = make_hold_feed_with_big_candle(big_candle_pct=0.02)
    strat = run_backtest(df)
    assert len(strat.trade_log) >= 1
    assert strat.trade_log[0]['add_count'] == 0


def test_add_allowed_when_max_bullish_below_threshold():
    """阳线 0.5% ≤ 0.01 → 加仓机制不被该约束阻断（max_bullish_candle_pct 0.005）。"""
    df = make_hold_feed_with_big_candle(big_candle_pct=0.005)
    strat = run_backtest(df)
    assert len(strat.trade_log) >= 1
    assert strat.trade_log[0]['max_bullish_candle_pct'] <= 0.01 + 1e-9
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd e:/GithubCloneSpace/Stock/backtrader/backtrader
pytest my_strategy/tests/test_strategy.py::test_max_bullish_candle_pct_recorded_in_trade_log -v
```
预期：FAIL，原因 `KeyError: 'max_bullish_candle_pct'` 或 `AssertionError`。

- [ ] **Step 3: 改 strategy.py 状态字段**

打开 `my_strategy/src/strategy.py`，把 `__init__` 内 line 65 附近：

```python
'big_candle_seen': False,
```

替换为：

```python
'max_bullish_candle_pct': 0.0,
```

同样把 `_reset_state` 内 line 100 附近：

```python
'big_candle_seen': False,
```

替换为：

```python
'max_bullish_candle_pct': 0.0,
```

- [ ] **Step 4: 改 next() 持仓分支的阳线记录与加仓判定**

定位 `next()` 内 line 271-274：

```python
                # 记录阳线（持仓期间出现 >1% 阳线则禁止加仓）
                open_ = d.open[0]
                if open_ > 0 and (close - open_) / open_ > 0.01:
                    state['big_candle_seen'] = True
```

替换为：

```python
                # 记录持仓期单日阳线幅度的最大值（用于事后归因评估阻断阈值）
                open_ = d.open[0]
                if open_ > 0:
                    pct = (close - open_) / open_
                    if pct > state['max_bullish_candle_pct']:
                        state['max_bullish_candle_pct'] = pct
```

定位下方加仓判定（line 320 附近）：

```python
                if state['add_count'] < 2 and not state['big_candle_seen']:
```

替换为：

```python
                if state['add_count'] < 2 and state['max_bullish_candle_pct'] <= 0.01:
```

- [ ] **Step 5: 改 _finalize_episode 写入 trade_log**

定位 `_finalize_episode` 内 trade_log 字典（line 142-159 附近），在 `'tp2_pct'` 键之后追加一行：

```python
            'tp2_pct': round(state['tp2_pct'], 4) if state['tp2_pct'] is not None else None,
            'max_bullish_candle_pct': round(state['max_bullish_candle_pct'], 6),
```

- [ ] **Step 6: 运行测试，确认通过**

```bash
pytest my_strategy/tests/test_strategy.py -v
```
预期：所有原有测试 + 3 个新测试 pass。

- [ ] **Step 7: Commit**

```bash
git add my_strategy/src/strategy.py my_strategy/tests/test_strategy.py
git commit -m "feat(strategy): record max_bullish_candle_pct per episode"
```

---

## Task 2：attribution.py — compute_first_buy_size_stats

**Files:**
- Modify: `my_strategy/tools/attribution.py`（新增常量 + 函数 + 接入 run()）
- Modify: `my_strategy/tests/test_attribution.py`（追加测试）

- [ ] **Step 1: 写失败测试**

`my_strategy/tests/test_attribution.py` 顶部 import 处追加 `compute_first_buy_size_stats`：

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
)
```

文件末尾追加：

```python
def test_compute_first_buy_size_stats_buckets():
    trades = pd.DataFrame({
        'entry_ma60_dist_pct': [
            -1.5,           # [<-1%)
            -0.7, -0.6,     # [-1%,-0.5%) 两笔
            -0.2,           # [-0.5%,0%)
            0.3,            # [0%,0.5%)
            0.7,            # [0.5%,1%)
            1.2,            # [1%,1.5%)
            1.7,            # [1.5%,2%)
            2.5,            # [2%,3%)
            4.0,            # [3%,5%)
            7.0,            # [5%,10%)
            15.0,           # [10%+)
        ],
        'return_pct': [-5.0, 1.0, 3.0, 2.0, 4.0, -2.0, 6.0, -1.0, 8.0, -3.0, 9.0, 0.0],
        'holding_days': [10, 12, 14, 20, 30, 25, 18, 15, 22, 28, 35, 40],
        'add_count': [0, 1, 0, 1, 2, 0, 1, 0, 2, 0, 1, 0],
        'status': ['completed'] * 12,
    })
    out = compute_first_buy_size_stats(trades)
    assert list(out['bucket']) == [
        '[<-1%)', '[-1%,-0.5%)', '[-0.5%,0%)',
        '[0%,0.5%)', '[0.5%,1%)', '[1%,1.5%)',
        '[1.5%,2%)', '[2%,3%)', '[3%,5%)',
        '[5%,10%)', '[10%+)',
    ]
    row_negativehalf = out[out['bucket'] == '[-1%,-0.5%)'].iloc[0]
    assert row_negativehalf['count'] == 2
    assert row_negativehalf['avg_return'] == 2.0  # (1+3)/2
    row_first = out[out['bucket'] == '[<-1%)'].iloc[0]
    assert row_first['count'] == 1
    assert row_first['win_rate'] == 0.0


def test_compute_first_buy_size_stats_empty_input():
    out = compute_first_buy_size_stats(pd.DataFrame())
    assert list(out.columns) == [
        'bucket', 'count', 'win_rate', 'avg_return', 'median_return',
        'avg_holding_days', 'avg_add_count', 'pct_completed',
    ]
    assert len(out) == 0


def test_compute_first_buy_size_stats_missing_column():
    out = compute_first_buy_size_stats(pd.DataFrame({'foo': [1, 2, 3]}))
    assert list(out.columns) == [
        'bucket', 'count', 'win_rate', 'avg_return', 'median_return',
        'avg_holding_days', 'avg_add_count', 'pct_completed',
    ]
    assert len(out) == 0
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest my_strategy/tests/test_attribution.py -k "first_buy" -v
```
预期：`ImportError: cannot import name 'compute_first_buy_size_stats'`。

- [ ] **Step 3: 实现常量与函数**

打开 `my_strategy/tools/attribution.py`，在 `compute_yearly_stats` 之后追加：

```python
_FIRST_BUY_BINS = [-np.inf, -1, -0.5, 0, 0.5, 1, 1.5, 2, 3, 5, 10, np.inf]
_FIRST_BUY_LABELS = ['[<-1%)', '[-1%,-0.5%)', '[-0.5%,0%)',
                     '[0%,0.5%)', '[0.5%,1%)', '[1%,1.5%)',
                     '[1.5%,2%)', '[2%,3%)', '[3%,5%)',
                     '[5%,10%)', '[10%+)']


def _scan_bucket_aggregate(sub):
    """对一个桶子集计算 count/win_rate/avg_return/median_return/avg_holding_days/avg_add_count/pct_completed。"""
    ret = sub['return_pct'].dropna() if 'return_pct' in sub.columns else pd.Series(dtype=float)
    hold = sub['holding_days'].dropna() if 'holding_days' in sub.columns else pd.Series(dtype=float)
    addc = sub['add_count'].dropna() if 'add_count' in sub.columns else pd.Series(dtype=float)
    completed = ((sub['status'] == 'completed').sum()
                 if 'status' in sub.columns else 0)
    n = len(sub)
    return {
        'count': n,
        'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
        'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
        'median_return': round(ret.median(), 4) if len(ret) else float('nan'),
        'avg_holding_days': round(hold.mean(), 1) if len(hold) else float('nan'),
        'avg_add_count': round(addc.mean(), 2) if len(addc) else float('nan'),
        'pct_completed': round(completed / n, 4) if n else float('nan'),
    }


def compute_first_buy_size_stats(trades):
    """按 entry_ma60_dist_pct 11 桶扫描，评估首仓尺寸阈值（当前 1%）的合理性。

    输入字段 entry_ma60_dist_pct 单位为百分点（例 0.5 表示 0.5%）。
    """
    cols = ['bucket', 'count', 'win_rate', 'avg_return', 'median_return',
            'avg_holding_days', 'avg_add_count', 'pct_completed']
    if trades.empty or 'entry_ma60_dist_pct' not in trades.columns:
        return pd.DataFrame(columns=cols)
    sub = trades.dropna(subset=['entry_ma60_dist_pct']).copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    sub['_bucket'] = pd.cut(sub['entry_ma60_dist_pct'],
                             bins=_FIRST_BUY_BINS, labels=_FIRST_BUY_LABELS,
                             right=False, include_lowest=False)
    rows = []
    for bucket in _FIRST_BUY_LABELS:
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
pytest my_strategy/tests/test_attribution.py -k "first_buy" -v
```
预期：3 passed。

- [ ] **Step 5: 接入 run()**

定位 `attribution.py` 的 `run()`，在 `yearly.to_csv(out_dir / 'yearly_stats.csv', index=False)` 之后追加：

```python
    first_buy = compute_first_buy_size_stats(trades)
    first_buy.to_csv(out_dir / 'first_buy_size_stats.csv', index=False)
```

- [ ] **Step 6: Commit**

```bash
git add my_strategy/tools/attribution.py my_strategy/tests/test_attribution.py
git commit -m "feat(attribution): add first_buy_size_stats scan report"
```

---

## Task 3：attribution.py — compute_add_block_stats

**Files:**
- Modify: `my_strategy/tools/attribution.py`
- Modify: `my_strategy/tests/test_attribution.py`

- [ ] **Step 1: 写失败测试**

import 处追加 `compute_add_block_stats`：

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
)
```

文件末尾追加：

```python
def test_compute_add_block_stats_buckets():
    trades = pd.DataFrame({
        'max_bullish_candle_pct': [
            0.0,            # [0%,0.5%)
            0.003,          # [0%,0.5%)（再加一笔）
            0.007,          # [0.5%,1%)
            0.012, 0.013,   # [1%,1.5%) 两笔
            0.018,          # [1.5%,2%)
            0.025,          # [2%,3%)
            0.040,          # [3%,5%)
            0.080,          # [5%,10%)
            0.150,          # [10%+)
        ],
        'return_pct': [3.0, 2.0, 5.0, -1.0, -2.0, 8.0, -4.0, 6.0, -3.0, 0.0],
        'holding_days': [10, 12, 15, 18, 20, 22, 25, 28, 30, 35],
        'add_count': [2, 1, 1, 0, 0, 1, 0, 1, 0, 0],
        'status': ['completed'] * 10,
    })
    out = compute_add_block_stats(trades)
    assert list(out['bucket']) == [
        '[0%,0.5%)', '[0.5%,1%)', '[1%,1.5%)',
        '[1.5%,2%)', '[2%,3%)', '[3%,5%)',
        '[5%,10%)', '[10%+)',
    ]
    row_1_15 = out[out['bucket'] == '[1%,1.5%)'].iloc[0]
    assert row_1_15['count'] == 2
    assert row_1_15['avg_return'] == -1.5
    assert row_1_15['win_rate'] == 0.0
    row_first = out[out['bucket'] == '[0%,0.5%)'].iloc[0]
    assert row_first['count'] == 2
    assert row_first['avg_return'] == 2.5


def test_compute_add_block_stats_empty_input():
    out = compute_add_block_stats(pd.DataFrame())
    assert list(out.columns) == [
        'bucket', 'count', 'win_rate', 'avg_return', 'median_return',
        'avg_holding_days', 'avg_add_count', 'pct_completed',
    ]
    assert len(out) == 0


def test_compute_add_block_stats_missing_column():
    out = compute_add_block_stats(pd.DataFrame({'return_pct': [1.0, 2.0]}))
    assert list(out.columns) == [
        'bucket', 'count', 'win_rate', 'avg_return', 'median_return',
        'avg_holding_days', 'avg_add_count', 'pct_completed',
    ]
    assert len(out) == 0
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
pytest my_strategy/tests/test_attribution.py -k "add_block" -v
```
预期：`ImportError: cannot import name 'compute_add_block_stats'`。

- [ ] **Step 3: 实现常量与函数**

在 `compute_first_buy_size_stats` 之后追加：

```python
_ADD_BLOCK_BINS = [-np.inf, 0, 0.005, 0.01, 0.015, 0.02, 0.03, 0.05, 0.10, np.inf]
_ADD_BLOCK_LABELS = ['[<0%)', '[0%,0.5%)', '[0.5%,1%)',
                     '[1%,1.5%)', '[1.5%,2%)', '[2%,3%)',
                     '[3%,5%)', '[5%,10%)', '[10%+)']


def compute_add_block_stats(trades):
    """按 max_bullish_candle_pct 9 桶扫描，评估加仓阻断阈值（当前 1%）的合理性。

    输入字段 max_bullish_candle_pct 单位为小数（例 0.0083 表示 0.83%）。
    """
    cols = ['bucket', 'count', 'win_rate', 'avg_return', 'median_return',
            'avg_holding_days', 'avg_add_count', 'pct_completed']
    if trades.empty or 'max_bullish_candle_pct' not in trades.columns:
        return pd.DataFrame(columns=cols)
    sub = trades.dropna(subset=['max_bullish_candle_pct']).copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    sub['_bucket'] = pd.cut(sub['max_bullish_candle_pct'],
                             bins=_ADD_BLOCK_BINS, labels=_ADD_BLOCK_LABELS,
                             right=False, include_lowest=False)
    rows = []
    for bucket in _ADD_BLOCK_LABELS:
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
pytest my_strategy/tests/test_attribution.py -k "add_block" -v
```
预期：3 passed。

- [ ] **Step 5: 接入 run()**

紧跟 `first_buy.to_csv(...)` 之后追加：

```python
    add_block = compute_add_block_stats(trades)
    add_block.to_csv(out_dir / 'add_block_stats.csv', index=False)
```

- [ ] **Step 6: 全部单元测试一起跑通**

```bash
pytest my_strategy/tests/test_attribution.py -v
```
预期：所有原有测试 + 6 个新测试全部 pass（共约 20+ 个）。

- [ ] **Step 7: Commit**

```bash
git add my_strategy/tools/attribution.py my_strategy/tests/test_attribution.py
git commit -m "feat(attribution): add add_block_stats scan report"
```

---

## Task 4：集成测试 + 真实数据端到端验证

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
]
```

- [ ] **Step 2: 用现有 trade_summary.csv 跑端到端**

```bash
cd e:/GithubCloneSpace/Stock/backtrader/backtrader
python my_strategy/tests/test_attribution_run.py
```
预期最后一行：`所有归因报告产出成功。`，并打印 11 个 `[OK]` 行。`add_block_stats.csv` 应为空表（旧 `trade_summary.csv` 没有 `max_bullish_candle_pct` 列，按容错约定返回空表头）；`first_buy_size_stats.csv` 应有真实数据。

- [ ] **Step 3: Commit**

```bash
git add my_strategy/tests/test_attribution_run.py
git commit -m "test(attribution): extend integration test for 2 magic-number scan reports"
```

---

## Task 5：重跑回测，验证 max_bullish_candle_pct 列填充

**Files:** （不修改任何源码，仅重新生成数据）

- [ ] **Step 1: 重跑回测**

```bash
cd e:/GithubCloneSpace/Stock/backtrader/backtrader
python my_strategy/backtest.py
```
预期：回测正常完成；末尾自动跑归因；产出包含 `max_bullish_candle_pct` 列的 `trade_summary.csv`，以及 11 张归因 CSV。

- [ ] **Step 2: 抽样检查 max_bullish_candle_pct 列**

```bash
python -c "
import pandas as pd
df = pd.read_csv('my_strategy/results/trade_summary.csv')
assert 'max_bullish_candle_pct' in df.columns, 'max_bullish_candle_pct 列缺失'
print(f'共 {len(df)} 笔交易')
print(f'max_bullish_candle_pct 描述：')
print(df['max_bullish_candle_pct'].describe())
print(f'有阳线超过 1% 的交易数: {(df[\"max_bullish_candle_pct\"] > 0.01).sum()}')
"
```
预期：列存在，分布合理（min ≥ 0，median 在 0.005~0.02 之间），> 1% 的笔数大致与历史 add_count == 0 的比例匹配。

- [ ] **Step 3: 抽样检查两张新报告**

```bash
python -c "
import pandas as pd
for f in ['first_buy_size_stats', 'add_block_stats']:
    df = pd.read_csv(f'my_strategy/reports/{f}.csv')
    print(f'\\n=== {f}.csv ({len(df)} 行) ===')
    print(df.to_string())
"
```
预期：
- `first_buy_size_stats.csv` ≤ 11 行（有数据的桶才会出现），按区间顺序排序，覆盖现有 5911 笔交易
- `add_block_stats.csv` ≤ 9 行，桶分布与 max_bullish_candle_pct 分布一致

- [ ] **Step 4: 不需 commit**

本 Task 只重生成数据；CSV 报告由回测脚本生成，**reports/ 中现有 CSV 默认应在 .gitignore（如否则跳过此说明）**。如果你的环境会把 reports/*.csv 标记为 untracked，且历史上没有提交，按现状不动即可。

---

## Task 6：文档更新

**Files:**
- Modify: `docs/FEATURES.md`
- Modify: `docs/CHANGELOG.md`

- [ ] **Step 1: 更新 FEATURES.md §6 输出列表**

打开 `docs/FEATURES.md`，找到 `## 6. 归因分析（tools/attribution.py）` 章节内"输出到 `reports/`："那段，把现有 8 项有序列表替换为：

```markdown
输出到 `reports/`：

1. **trade_profile**：按收益分桶（大盈/小盈/持平/小亏/大亏）统计因子均值、分位；
2. **top_trades / bottom_trades**：收益最高 / 最低各 10 笔；
3. **sector_winrate**：按申万一级行业统计交易数、胜率、平均收益；
4. **factor_alpha**：每个 `factor_*` 因子的 IC（Spearman）与多空分组超额；
5. **exit_reason_stats**：按出场原因（MA25清仓 / take_profit_1/2 / 未平仓 ...）统计胜率、收益、持仓天数、加仓次数；
6. **add_count_stats**：按加仓次数（0/1/2/3+）统计胜率、收益、已平仓比例；
7. **entry_condition_stats**：7 个入场快照字段（kdj_j / ma60_dist / ma_alignment / macd_zone / week/month）的单条件长表，固定阈值分桶；
8. **yearly_stats**：按 `entry_date.year` 统计 count / win_rate / avg_return / median_return / total_pnl_yuan（绝对盈亏，元）/ avg_holding_days；
9. **first_buy_size_stats**：按 `entry_ma60_dist_pct` 11 桶扫描首仓尺寸阈值（当前 1%）的合理性；输出 count / win_rate / avg_return / median_return / avg_holding_days / avg_add_count / pct_completed；
10. **add_block_stats**：按 `max_bullish_candle_pct`（持仓期最大阳线，由 strategy.py 记录到 trade_summary）9 桶扫描加仓阻断阈值（当前 1%）的合理性；同口径输出。
```

- [ ] **Step 2: 在 CHANGELOG.md 顶部追加记录**

打开 `docs/CHANGELOG.md`，在第一条记录之前（即 `---` 分隔符下方）插入：

```markdown
## 2026-05-07 — 归因报告新增 2 张魔数扫描表 + strategy 记录持仓期最大阳线

- 需求：策略含 2 个 1% 魔数（首仓尺寸触发线、加仓阻断阈值），需要数据驱动评估其合理性。
- 改动：
  - `my_strategy/src/strategy.py`：`state['big_candle_seen']`(bool) → `state['max_bullish_candle_pct']`(float)；加仓判定从 `not big_candle_seen` 改为 `<= 0.01`（行为完全等价）；`_finalize_episode` 写入 `trade_summary.csv` 新列 `max_bullish_candle_pct`。
  - `my_strategy/tools/attribution.py` 新增 `compute_first_buy_size_stats`（11 桶扫描 entry_ma60_dist_pct）、`compute_add_block_stats`（9 桶扫描 max_bullish_candle_pct）两个函数，并在 `run()` 末尾追加 2 个 `to_csv`。
  - `my_strategy/tests/test_strategy.py` 追加 3 个用例验证行为不变性。
  - `my_strategy/tests/test_attribution.py` 追加 6 个单元测试。
  - `my_strategy/tests/test_attribution_run.py` `EXPECTED_FILES` 9→11。
  - `docs/FEATURES.md` §6 同步至 10 项。
- 影响：回测后归因 11 张报告（之前 9 张）。需重跑回测才能填充 `trade_summary.csv` 的新列；旧 trade_summary.csv 上 `add_block_stats.csv` 为空表头（容错）。详见 spec：`docs/superpowers/specs/2026-05-07-magic-number-scan-design.md`。
```

- [ ] **Step 3: Commit**

```bash
git add docs/FEATURES.md docs/CHANGELOG.md
git commit -m "docs: document magic-number scan attribution tables"
```

---

## 完成验收

全部 6 个 Task 完成后，运行：

```bash
cd e:/GithubCloneSpace/Stock/backtrader/backtrader
pytest my_strategy/tests/test_strategy.py my_strategy/tests/test_attribution.py -v
python my_strategy/tests/test_attribution_run.py
git log --oneline -7
```

预期：
- 所有单元测试 pass（旧 + 新 9 个）
- 集成测试输出 `所有归因报告产出成功。`，11 个 `[OK]`
- git 历史出现 5 个新 commit（feat × 2 in attribution + feat × 1 in strategy + test × 1 + docs × 1）
- `my_strategy/results/trade_summary.csv` 含 `max_bullish_candle_pct` 列
- `my_strategy/reports/` 下 11 个 CSV 文件齐全
