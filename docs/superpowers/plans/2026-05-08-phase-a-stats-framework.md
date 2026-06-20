# Phase A 统计分析框架 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不动现有 28 张报告的前提下，新增 13 项统计成果（14 个 CSV 文件）+ 2 个中间数据文件，覆盖风险调整收益、统计显著性、组合层指标三大盲区。

**Architecture:** 6 个新模块按数据源拆分 —— `stats_helpers.py`（纯统计工具）、`trade_attribution_extra.py`（trade-level）、`portfolio_attribution.py`（equity-curve-level）、`position_curve_attribution.py`（daily-position-level）、`rebuild_position_history.py`（数据补齐）、`attribution_runner.py`（顶层编排）。`backtest.py` 改 1 处调用。

**Tech Stack:** pandas、numpy、scipy.stats（CI/t-test）、pytest（已有约定）

**Spec:** `docs/superpowers/specs/2026-05-08-phase-a-stats-framework-design.md`

---

## Task 0: 实施前调研 — 解决 spec §7 的 4 个开放问题

**目的**：确认实际数据源结构，避免后续任务返工。**不写代码，只输出调研报告**。

**Files:**
- 调研产物：在本任务内提交一个 `docs/superpowers/notes/2026-05-08-phase-a-investigation.md` 记录结论

- [ ] **Step 1: 检查 `trade_list.csv` 是否记录 commission/stamp_duty**

Run:
```bash
head -1 my_strategy/results/trade_list.csv
```
若有 commission 列 → 记录列名；若无 → 后续 Task 15（cost_breakdown）使用 `commission_rate × turnover` 反推方案。

- [ ] **Step 2: 确认 `r.position_count_log` 的 schema**

Run:
```bash
grep -n "position_count_log" my_strategy/src/strategy.py my_strategy/backtest.py
```
读出该属性的赋值代码，确认是 list[tuple]、list[dict] 还是 DataFrame，记录每条记录的字段。

- [ ] **Step 3: 确认 `data/{ts_code}_daily.csv` 是否复权**

Run:
```bash
grep -n "adj\|adjustfactor\|qfq\|hfq" my_strategy/src/downloader.py
ls my_strategy/data/ | head -5
head -3 my_strategy/data/$(ls my_strategy/data/ | grep -E "^[0-9]{6}\.(SH|SZ)_daily.csv$" | head -1)
```
若已复权（前/后复权）→ 在 daily_position_pnl 中直接用 close；若未复权 → 在 Task 2 中显式说明此假设并在 README 注明影响。

- [ ] **Step 4: 自动从 trade_summary 识别信号字段，作为 signal_correlation_matrix 白名单依据**

Run:
```bash
head -1 my_strategy/results/trade_summary.csv | tr ',' '\n' | grep -E "^entry_|^ma_alignment|^macd_zone|^factor_"
```
列出所有候选列，从中圈定 13-15 个白名单（沿用 spec §3.2.1 的清单 + entry_kdj_j、entry_ma60_dist_pct 等数值列）。

- [ ] **Step 5: 写入调研报告**

把 4 步结论写入 `docs/superpowers/notes/2026-05-08-phase-a-investigation.md`，包含：
- trade_list.csv 实际列清单 + cost_breakdown 实施策略选择
- position_count_log 数据结构 + concurrent_positions_stats 输入解析方式
- daily.csv 复权状态 + daily_position_pnl 注意事项
- signal_correlation_matrix 最终白名单（13-15 个字段名）

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/notes/2026-05-08-phase-a-investigation.md
git commit -m "docs(phase-a): pre-impl investigation of data sources and schemas"
```

---

## Task 1: `stats_helpers.py` — 纯统计工具

**Files:**
- Create: `my_strategy/tools/stats_helpers.py`
- Test: `my_strategy/tests/test_stats_helpers.py`

- [ ] **Step 1: 写失败的测试**

```python
# my_strategy/tests/test_stats_helpers.py
import numpy as np
import pandas as pd
import pytest
from my_strategy.tools.stats_helpers import (
    confidence_interval,
    t_test_one_sample,
    t_test_welch,
    bucket_stats_with_significance,
)


def test_confidence_interval_symmetric_around_mean():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    low, high = confidence_interval(s, alpha=0.05)
    assert low < 3.0 < high
    assert abs((low + high) / 2 - 3.0) < 1e-6


def test_t_test_one_sample_detects_nonzero_mean():
    s = pd.Series(np.random.RandomState(0).normal(loc=2.0, scale=1.0, size=200))
    t_stat, p_value = t_test_one_sample(s, mu=0)
    assert t_stat > 0
    assert p_value < 0.001


def test_t_test_welch_detects_difference():
    a = pd.Series(np.random.RandomState(0).normal(loc=1.0, size=100))
    b = pd.Series(np.random.RandomState(1).normal(loc=2.0, size=100))
    t_stat, p_value = t_test_welch(a, b)
    assert t_stat < 0  # a < b
    assert p_value < 0.01


def test_bucket_stats_with_significance_flags_low_sample():
    overall = pd.Series(np.random.RandomState(0).normal(0, 1, size=2000))
    grouped = {
        'big_bucket': pd.Series(np.random.RandomState(1).normal(0.5, 1, size=500)),
        'tiny_bucket': pd.Series(np.random.RandomState(2).normal(0.5, 1, size=20)),
    }
    out = bucket_stats_with_significance(grouped, overall)
    assert set(out.columns) >= {
        'bucket', 'n', 'mean_return', 'std_return', 'std_err',
        'ci_low_95', 'ci_high_95', 't_stat_vs_zero', 'p_value_vs_zero',
        't_stat_vs_overall', 'p_value_vs_overall',
        'low_sample_warning', 'significant_flag',
    }
    tiny = out[out['bucket'] == 'tiny_bucket'].iloc[0]
    assert tiny['low_sample_warning'] == True
    big = out[out['bucket'] == 'big_bucket'].iloc[0]
    assert big['low_sample_warning'] == False
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd my_strategy && python -m pytest tests/test_stats_helpers.py -v
```
Expected: `ImportError: No module named 'my_strategy.tools.stats_helpers'` 或所有测试 FAIL。

- [ ] **Step 3: 写最小实现**

```python
# my_strategy/tools/stats_helpers.py
"""纯统计工具：CI、t-test、bucket 显著性聚合。供归因模块复用。"""
from typing import Dict, Tuple

import numpy as np
import pandas as pd
from scipy import stats


def confidence_interval(series: pd.Series, alpha: float = 0.05) -> Tuple[float, float]:
    """95% 置信区间（默认 alpha=0.05）。基于 t 分布。"""
    s = pd.Series(series).dropna()
    n = len(s)
    if n < 2:
        return (np.nan, np.nan)
    mean = s.mean()
    se = s.std(ddof=1) / np.sqrt(n)
    t_crit = stats.t.ppf(1 - alpha / 2, df=n - 1)
    return (mean - t_crit * se, mean + t_crit * se)


def t_test_one_sample(series: pd.Series, mu: float = 0.0) -> Tuple[float, float]:
    """单样本 t 检验：H0 = 均值为 mu。返回 (t_stat, p_value 双尾)。"""
    s = pd.Series(series).dropna()
    if len(s) < 2:
        return (np.nan, np.nan)
    res = stats.ttest_1samp(s, popmean=mu)
    return (float(res.statistic), float(res.pvalue))


def t_test_welch(a: pd.Series, b: pd.Series) -> Tuple[float, float]:
    """Welch's t 检验（不假设方差相等）。返回 (t_stat, p_value 双尾)。"""
    a = pd.Series(a).dropna()
    b = pd.Series(b).dropna()
    if len(a) < 2 or len(b) < 2:
        return (np.nan, np.nan)
    res = stats.ttest_ind(a, b, equal_var=False)
    return (float(res.statistic), float(res.pvalue))


def bucket_stats_with_significance(
    grouped: Dict[str, pd.Series],
    overall: pd.Series,
    min_sample: int = 100,
    p_threshold: float = 0.05,
) -> pd.DataFrame:
    """对每个分组计算 n/mean/std/CI/t-stat/p-value，并标记 low_sample / significant。

    Args:
        grouped: {bucket_name: series_of_returns}
        overall: 全样本收益序列（用于 vs_overall 显著性检验）
        min_sample: 低样本量阈值
        p_threshold: 显著性 p 值阈值
    """
    rows = []
    for bucket, s in grouped.items():
        s = pd.Series(s).dropna()
        n = len(s)
        if n == 0:
            continue
        mean_v = s.mean()
        std_v = s.std(ddof=1) if n >= 2 else np.nan
        se = std_v / np.sqrt(n) if n >= 2 else np.nan
        ci_lo, ci_hi = confidence_interval(s) if n >= 2 else (np.nan, np.nan)
        t0, p0 = t_test_one_sample(s) if n >= 2 else (np.nan, np.nan)
        t1, p1 = t_test_welch(s, overall) if n >= 2 else (np.nan, np.nan)
        rows.append({
            'bucket': bucket,
            'n': n,
            'mean_return': mean_v,
            'std_return': std_v,
            'std_err': se,
            'ci_low_95': ci_lo,
            'ci_high_95': ci_hi,
            't_stat_vs_zero': t0,
            'p_value_vs_zero': p0,
            't_stat_vs_overall': t1,
            'p_value_vs_overall': p1,
            'low_sample_warning': n < min_sample,
            'significant_flag': (n >= min_sample) and (not pd.isna(p1)) and (p1 < p_threshold),
        })
    return pd.DataFrame(rows)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd my_strategy && python -m pytest tests/test_stats_helpers.py -v
```
Expected: 4 passed。

- [ ] **Step 5: 运行全量测试确认无回归**

```bash
cd my_strategy && python -m pytest -q
```
Expected: 无 FAIL（已有约 100 个测试 + 4 新增）。

- [ ] **Step 6: Commit**

```bash
git add my_strategy/tools/stats_helpers.py my_strategy/tests/test_stats_helpers.py
git commit -m "feat(stats): add stats_helpers module (CI, t-test, bucket significance)"
```

---

## Task 2: `rebuild_position_history.py` — 重建 daily_position_pnl + daily_portfolio_snapshot

**Files:**
- Create: `my_strategy/tools/rebuild_position_history.py`
- Test: `my_strategy/tests/test_rebuild_position_history.py`

- [ ] **Step 1: 写失败的测试**

```python
# my_strategy/tests/test_rebuild_position_history.py
import pandas as pd
import pytest
from pathlib import Path
from my_strategy.tools.rebuild_position_history import (
    build_daily_position_pnl,
    build_daily_portfolio_snapshot,
)


def _make_trades():
    return pd.DataFrame({
        'ts_code': ['A.SZ', 'B.SZ'],
        'entry_date': pd.to_datetime(['2024-01-02', '2024-01-03']),
        'exit_date': pd.to_datetime(['2024-01-05', '2024-01-08']),
        'avg_cost': [10.0, 20.0],
    })


def _make_daily_dict():
    return {
        'A.SZ': pd.DataFrame({
            'date': pd.to_datetime(['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05']),
            'close': [10.0, 11.0, 10.5, 12.0],
        }),
        'B.SZ': pd.DataFrame({
            'date': pd.to_datetime(['2024-01-03', '2024-01-04', '2024-01-05', '2024-01-08']),
            'close': [20.0, 21.0, 19.0, 22.0],
        }),
    }


def _make_sector_map():
    return pd.DataFrame({
        'ts_code': ['A.SZ', 'B.SZ'],
        'sw_index_code': ['801010', '801080'],
    })


def test_build_daily_position_pnl_emits_one_row_per_trade_per_day():
    trades = _make_trades()
    dailies = _make_daily_dict()
    sec = _make_sector_map()
    out = build_daily_position_pnl(trades, dailies, sec)
    # A.SZ 持仓 4 天 (1/2~1/5) + B.SZ 持仓 4 天 (1/3~1/8 含 3 个交易日 + 入场日) = 视具体行情
    assert set(out.columns) >= {
        'trade_id', 'ts_code', 'entry_date', 'holding_day_n',
        'date', 'close', 'cum_return_pct', 'drawdown_from_peak_pct', 'sector_code',
    }
    a_rows = out[out['ts_code'] == 'A.SZ']
    assert len(a_rows) == 4  # 1/2, 1/3, 1/4, 1/5
    assert a_rows['holding_day_n'].tolist() == [0, 1, 2, 3]
    # 1/3 cum_return = (11-10)/10 = 10%
    assert abs(a_rows.iloc[1]['cum_return_pct'] - 10.0) < 1e-6
    # 1/4 cum_return = (10.5-10)/10 = 5%, peak so far = 10%, drawdown_from_peak = -4.55%
    assert abs(a_rows.iloc[2]['drawdown_from_peak_pct'] - ((10.5/11.0 - 1) * 100)) < 1e-3


def test_build_daily_portfolio_snapshot_aggregates_by_date():
    trades = _make_trades()
    dailies = _make_daily_dict()
    sec = _make_sector_map()
    pnl = build_daily_position_pnl(trades, dailies, sec)
    snap = build_daily_portfolio_snapshot(pnl)
    assert set(snap.columns) >= {
        'date', 'n_positions', 'sectors_held', 'top_sector_code',
        'top_sector_share', 'herfindahl_index',
    }
    # 1/3 应有 A.SZ 和 B.SZ 同时持仓
    d_0103 = snap[snap['date'] == pd.Timestamp('2024-01-03')].iloc[0]
    assert d_0103['n_positions'] == 2
    assert d_0103['sectors_held'] == 2
    assert abs(d_0103['herfindahl_index'] - (0.5 ** 2 + 0.5 ** 2)) < 1e-6


def test_build_raises_on_missing_daily_data():
    trades = _make_trades()
    dailies = {'A.SZ': _make_daily_dict()['A.SZ']}  # 缺 B.SZ
    sec = _make_sector_map()
    with pytest.raises((KeyError, FileNotFoundError, ValueError)):
        build_daily_position_pnl(trades, dailies, sec)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd my_strategy && python -m pytest tests/test_rebuild_position_history.py -v
```
Expected: ImportError 或全部 FAIL。

- [ ] **Step 3: 写实现**

```python
# my_strategy/tools/rebuild_position_history.py
"""Post-hoc 重建逐日持仓快照。
输入:
    trades: results/trade_summary.csv
    dailies: data/{ts_code}_daily.csv 集合
    sector_map: data/stock_sector.csv
输出:
    results/daily_position_pnl.csv
    results/daily_portfolio_snapshot.csv
不修改 backtest.py。
"""
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd


def build_daily_position_pnl(
    trades: pd.DataFrame,
    dailies: Dict[str, pd.DataFrame],
    sector_map: pd.DataFrame,
) -> pd.DataFrame:
    """逐笔交易展开成 (trade_id, date) 长表，含 cum_return_pct / drawdown_from_peak_pct / sector_code。"""
    sec_lookup = dict(zip(sector_map['ts_code'], sector_map['sw_index_code']))
    rows = []
    for trade_id, t in trades.reset_index(drop=True).iterrows():
        ts_code = t['ts_code']
        entry = pd.to_datetime(t['entry_date'])
        exit_ = pd.to_datetime(t['exit_date']) if pd.notna(t.get('exit_date')) else None
        cost = float(t['avg_cost'])

        if ts_code not in dailies:
            raise KeyError(f"daily data missing for {ts_code} (trade_id={trade_id})")
        df = dailies[ts_code].copy()
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)

        if exit_ is None:
            sub = df[df['date'] >= entry]
        else:
            sub = df[(df['date'] >= entry) & (df['date'] <= exit_)]
        if sub.empty:
            raise ValueError(f"no daily rows in [{entry}, {exit_}] for {ts_code}")

        cum_return_pct = (sub['close'].values - cost) / cost * 100.0
        running_peak = np.maximum.accumulate(sub['close'].values)
        drawdown_from_peak_pct = (sub['close'].values - running_peak) / running_peak * 100.0

        for i, (_, r) in enumerate(sub.iterrows()):
            rows.append({
                'trade_id': trade_id,
                'ts_code': ts_code,
                'entry_date': entry,
                'holding_day_n': i,
                'date': r['date'],
                'close': float(r['close']),
                'cum_return_pct': float(cum_return_pct[i]),
                'drawdown_from_peak_pct': float(drawdown_from_peak_pct[i]),
                'sector_code': sec_lookup.get(ts_code),
            })
    return pd.DataFrame(rows)


def build_daily_portfolio_snapshot(daily_position_pnl: pd.DataFrame) -> pd.DataFrame:
    """按 date 聚合，输出每日组合层指标：n_positions, sectors_held, top_sector_share, herfindahl_index。"""
    rows = []
    for date, g in daily_position_pnl.groupby('date'):
        n = len(g)
        sec_counts = g['sector_code'].value_counts(dropna=False)
        sectors_held = sec_counts[sec_counts.index.notna()].shape[0]
        if n == 0:
            continue
        shares = (sec_counts / n).values
        herfindahl = float((shares ** 2).sum())
        top_sec = sec_counts.index[0]
        top_share = float(sec_counts.iloc[0] / n)
        rows.append({
            'date': date,
            'n_positions': n,
            'sectors_held': int(sectors_held),
            'top_sector_code': top_sec,
            'top_sector_share': top_share,
            'herfindahl_index': herfindahl,
        })
    return pd.DataFrame(rows).sort_values('date').reset_index(drop=True)


def build(project_root: Path, cfg: dict) -> None:
    """从 results/trade_summary.csv + data/*_daily.csv + stock_sector.csv 重建并写盘。"""
    project_root = Path(project_root)
    results_dir = project_root / cfg.get('results_dir', 'results/')
    trades_path = results_dir / 'trade_summary.csv'
    if not trades_path.exists():
        raise FileNotFoundError(f"trade_summary not found at {trades_path}")
    trades = pd.read_csv(trades_path, parse_dates=['entry_date', 'exit_date'])

    data_dir = project_root / cfg.get('data_dir', 'data/')
    sector_csv = project_root / cfg['data_paths']['stock_sector_csv']
    sector_map = pd.read_csv(sector_csv)

    dailies = {}
    for ts_code in trades['ts_code'].unique():
        path = data_dir / f"{ts_code}_daily.csv"
        if not path.exists():
            raise FileNotFoundError(f"daily file missing: {path}")
        dailies[ts_code] = pd.read_csv(path)

    pnl = build_daily_position_pnl(trades, dailies, sector_map)
    snap = build_daily_portfolio_snapshot(pnl)

    pnl.to_csv(results_dir / 'daily_position_pnl.csv', index=False)
    snap.to_csv(results_dir / 'daily_portfolio_snapshot.csv', index=False)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd my_strategy && python -m pytest tests/test_rebuild_position_history.py -v
```
Expected: 3 passed。

- [ ] **Step 5: Commit**

```bash
git add my_strategy/tools/rebuild_position_history.py my_strategy/tests/test_rebuild_position_history.py
git commit -m "feat(stats): rebuild_position_history module (daily_position_pnl + snapshot)"
```

---

## Task 3: `trade_attribution_extra.py` — payoff_metrics

**Files:**
- Create: `my_strategy/tools/trade_attribution_extra.py`（新文件，本任务先建出来）
- Test: `my_strategy/tests/test_trade_attribution_extra.py`

- [ ] **Step 1: 写失败的测试**

```python
# my_strategy/tests/test_trade_attribution_extra.py
import pandas as pd
from my_strategy.tools.trade_attribution_extra import compute_payoff_metrics


def _make_trades():
    return pd.DataFrame({
        'ts_code': ['A', 'B', 'C', 'D', 'E'],
        'return_pct': [10.0, 5.0, -3.0, -8.0, 0.0],
        'entry_date': pd.to_datetime(
            ['2024-01-02', '2024-02-02', '2024-03-02', '2024-04-02', '2024-05-02']),
        'exit_reason': ['MA25清仓', 'MA25清仓', 'MA60止损', 'MA60止损', 'MA25清仓'],
        'industry': ['801010', '801010', '801080', '801080', '801010'],
        'entry_hs300_dif_above_zero': [True, True, False, False, True],
        'entry_stock_bull_align': [True, False, False, False, True],
    })


def test_compute_payoff_metrics_overall_row():
    trades = _make_trades()
    out = compute_payoff_metrics(trades)
    overall = out[(out['dimension'] == 'overall') & (out['bucket'] == 'all')].iloc[0]
    assert overall['n'] == 5
    # win=10+5=15, loss=-3-8=-11, avg_win=7.5, avg_loss=-5.5
    assert abs(overall['avg_win'] - 7.5) < 1e-6
    assert abs(overall['avg_loss'] - (-5.5)) < 1e-6
    assert abs(overall['payoff_ratio'] - (7.5 / 5.5)) < 1e-6
    assert abs(overall['profit_factor'] - (15 / 11)) < 1e-6
    # expectancy = win_rate * avg_win + (1-win_rate) * avg_loss
    # win_rate = 2/5 = 0.4 (return_pct > 0); 含 0 不算赢
    # expectancy = 0.4*7.5 + 0.6*(-5.5) = 3.0 - 3.3 = -0.3
    # 但要注意 0 既不算 win 也不算 loss 时分母如何
    assert overall['n'] == 5


def test_compute_payoff_metrics_includes_exit_reason_and_year_dimensions():
    trades = _make_trades()
    out = compute_payoff_metrics(trades)
    assert (out['dimension'] == 'exit_reason').any()
    assert (out['dimension'] == 'year').any()
    assert (out['dimension'] == 'sector').any()
    assert (out['dimension'] == 'regime').any()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd my_strategy && python -m pytest tests/test_trade_attribution_extra.py -v
```

- [ ] **Step 3: 写实现**

```python
# my_strategy/tools/trade_attribution_extra.py
"""Trade-level 扩展归因报告（5 张）。输入: trade_summary.csv。"""
from pathlib import Path

import numpy as np
import pandas as pd


def _payoff_block(sub: pd.DataFrame, dimension: str, bucket: str) -> dict:
    n = len(sub)
    if n == 0:
        return None
    r = sub['return_pct']
    wins = r[r > 0]
    losses = r[r < 0]
    n_wins = len(wins)
    n_losses = len(losses)
    avg_win = wins.mean() if n_wins > 0 else 0.0
    avg_loss = losses.mean() if n_losses > 0 else 0.0
    sum_win = wins.sum() if n_wins > 0 else 0.0
    sum_loss = losses.sum() if n_losses > 0 else 0.0
    payoff = (avg_win / abs(avg_loss)) if avg_loss < 0 else np.nan
    profit_factor = (sum_win / abs(sum_loss)) if sum_loss < 0 else np.nan
    win_rate = n_wins / n if n > 0 else 0.0
    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss
    return {
        'dimension': dimension,
        'bucket': bucket,
        'n': n,
        'win_rate': round(win_rate, 4),
        'avg_win': round(float(avg_win), 4),
        'avg_loss': round(float(avg_loss), 4),
        'payoff_ratio': round(float(payoff), 4) if pd.notna(payoff) else np.nan,
        'profit_factor': round(float(profit_factor), 4) if pd.notna(profit_factor) else np.nan,
        'expectancy': round(float(expectancy), 4),
        'max_win': round(float(r.max()), 4),
        'max_loss': round(float(r.min()), 4),
    }


def compute_payoff_metrics(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    rows.append(_payoff_block(trades, 'overall', 'all'))
    if 'exit_reason' in trades.columns:
        for v, sub in trades.groupby('exit_reason'):
            rows.append(_payoff_block(sub, 'exit_reason', str(v)))
    if 'entry_date' in trades.columns:
        years = pd.to_datetime(trades['entry_date']).dt.year
        for y, sub in trades.groupby(years):
            rows.append(_payoff_block(sub, 'year', str(int(y))))
    if 'industry' in trades.columns:
        for v, sub in trades.groupby('industry'):
            if pd.notna(v):
                rows.append(_payoff_block(sub, 'sector', str(v)))
    if {'entry_hs300_dif_above_zero', 'entry_stock_bull_align'}.issubset(trades.columns):
        for (a, b), sub in trades.groupby(
            ['entry_hs300_dif_above_zero', 'entry_stock_bull_align']
        ):
            label = f"hs300_dif={a}|stock_bull={b}"
            rows.append(_payoff_block(sub, 'regime', label))
    return pd.DataFrame([r for r in rows if r is not None])
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd my_strategy && python -m pytest tests/test_trade_attribution_extra.py::test_compute_payoff_metrics_overall_row tests/test_trade_attribution_extra.py::test_compute_payoff_metrics_includes_exit_reason_and_year_dimensions -v
```

- [ ] **Step 5: Commit**

```bash
git add my_strategy/tools/trade_attribution_extra.py my_strategy/tests/test_trade_attribution_extra.py
git commit -m "feat(stats): add payoff_metrics report in trade_attribution_extra"
```

---

## Task 4: `trade_attribution_extra.py` — signal_stability

**Files:**
- Modify: `my_strategy/tools/trade_attribution_extra.py`（追加函数）
- Modify: `my_strategy/tests/test_trade_attribution_extra.py`（追加测试）

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 my_strategy/tests/test_trade_attribution_extra.py
from my_strategy.tools.trade_attribution_extra import compute_signal_stability


def test_compute_signal_stability_outputs_per_signal_per_year():
    trades = pd.DataFrame({
        'return_pct': [10, -5, 8, -3, 12, -2, 15, -8],
        'entry_date': pd.to_datetime([
            '2019-01-01', '2019-06-01', '2020-01-01', '2020-06-01',
            '2021-01-01', '2021-06-01', '2022-01-01', '2022-06-01']),
        'entry_hs300_dif_above_zero': [True, False, True, False, True, False, True, False],
        'entry_stock_bull_align': [True, True, True, True, False, False, False, False],
    })
    out = compute_signal_stability(trades, signals_whitelist=[
        'entry_hs300_dif_above_zero', 'entry_stock_bull_align'])
    assert set(out.columns) >= {
        'signal_name', 'period_year', 'n', 'win_rate', 'avg_return',
        't_stat_vs_zero', 'p_value', 'rank_within_signal',
    }
    # entry_hs300_dif_above_zero=True 在 2019/2020/2021/2022 各 1 笔
    sig_true = out[(out['signal_name'] == 'entry_hs300_dif_above_zero=True')]
    assert sorted(sig_true['period_year'].tolist()) == [2019, 2020, 2021, 2022]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd my_strategy && python -m pytest tests/test_trade_attribution_extra.py::test_compute_signal_stability_outputs_per_signal_per_year -v
```

- [ ] **Step 3: 写实现（追加到 trade_attribution_extra.py）**

```python
# 追加到 my_strategy/tools/trade_attribution_extra.py
from my_strategy.tools.stats_helpers import t_test_one_sample


def _enumerate_signal_values(trades: pd.DataFrame, signal: str) -> list:
    """对一个信号字段返回 [(value_label, mask_series), ...]"""
    s = trades[signal]
    if s.dtype == bool or set(s.dropna().unique()) <= {True, False, 'True', 'False'}:
        return [
            (f"{signal}=True", s.astype(str).isin(['True'])),
            (f"{signal}=False", s.astype(str).isin(['False'])),
        ]
    if s.dtype == 'object':
        return [(f"{signal}={v}", s == v) for v in sorted(s.dropna().unique().astype(str))]
    # 数值列 → 5 分位
    qs = pd.qcut(s, q=5, labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'], duplicates='drop')
    return [(f"{signal}={lbl}", qs == lbl) for lbl in qs.dropna().unique()]


def compute_signal_stability(trades: pd.DataFrame, signals_whitelist: list) -> pd.DataFrame:
    rows = []
    if 'entry_date' not in trades.columns:
        return pd.DataFrame()
    years = pd.to_datetime(trades['entry_date']).dt.year
    for signal in signals_whitelist:
        if signal not in trades.columns:
            continue
        for label, mask in _enumerate_signal_values(trades, signal):
            sub = trades[mask]
            sub_years = years[mask]
            for y, g in sub.groupby(sub_years):
                r = g['return_pct'].dropna()
                if len(r) == 0:
                    continue
                t_stat, p_val = t_test_one_sample(r) if len(r) >= 2 else (np.nan, np.nan)
                rows.append({
                    'signal_name': label,
                    'period_year': int(y),
                    'n': len(r),
                    'win_rate': round(float((r > 0).mean()), 4),
                    'avg_return': round(float(r.mean()), 4),
                    't_stat_vs_zero': round(t_stat, 4) if pd.notna(t_stat) else np.nan,
                    'p_value': round(p_val, 4) if pd.notna(p_val) else np.nan,
                })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df['rank_within_signal'] = (
        df.groupby('signal_name')['avg_return']
          .rank(method='dense', ascending=False).astype(int)
    )
    return df
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd my_strategy && python -m pytest tests/test_trade_attribution_extra.py -v
```

- [ ] **Step 5: Commit**

```bash
git add my_strategy/tools/trade_attribution_extra.py my_strategy/tests/test_trade_attribution_extra.py
git commit -m "feat(stats): add signal_stability report"
```

---

## Task 5: `trade_attribution_extra.py` — signal_correlation_matrix

**Files:**
- Modify: `my_strategy/tools/trade_attribution_extra.py`
- Modify: `my_strategy/tests/test_trade_attribution_extra.py`

- [ ] **Step 1: 追加失败测试**

```python
from my_strategy.tools.trade_attribution_extra import compute_signal_correlation_matrix


def test_compute_signal_correlation_matrix_long_format():
    trades = pd.DataFrame({
        'sig_a': [1, 0, 1, 0, 1],
        'sig_b': [1, 0, 1, 0, 1],   # 完全相关
        'sig_c': [0, 1, 0, 1, 0],   # 完全反相关
    })
    out = compute_signal_correlation_matrix(trades, ['sig_a', 'sig_b', 'sig_c'])
    assert set(out.columns) >= {'signal_a', 'signal_b', 'pearson_r', 'spearman_r', 'n'}
    ab = out[(out['signal_a'] == 'sig_a') & (out['signal_b'] == 'sig_b')].iloc[0]
    ac = out[(out['signal_a'] == 'sig_a') & (out['signal_b'] == 'sig_c')].iloc[0]
    assert abs(ab['pearson_r'] - 1.0) < 1e-6
    assert abs(ac['pearson_r'] - (-1.0)) < 1e-6
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd my_strategy && python -m pytest tests/test_trade_attribution_extra.py::test_compute_signal_correlation_matrix_long_format -v
```

- [ ] **Step 3: 写实现（追加）**

```python
def compute_signal_correlation_matrix(trades: pd.DataFrame, signals_whitelist: list) -> pd.DataFrame:
    """两两相关性（Pearson + Spearman），long format。布尔列先转 0/1。"""
    cols = [c for c in signals_whitelist if c in trades.columns]
    df = trades[cols].copy()
    for c in cols:
        if df[c].dtype == bool or set(df[c].dropna().astype(str).unique()) <= {'True', 'False'}:
            df[c] = df[c].astype(str).map({'True': 1, 'False': 0})
        elif df[c].dtype == 'object':
            df[c] = pd.factorize(df[c])[0]
        df[c] = pd.to_numeric(df[c], errors='coerce')
    rows = []
    for i, a in enumerate(cols):
        for b in cols[i+1:]:
            sub = df[[a, b]].dropna()
            if len(sub) < 2:
                continue
            pearson = sub[a].corr(sub[b], method='pearson')
            spearman = sub[a].corr(sub[b], method='spearman')
            rows.append({
                'signal_a': a, 'signal_b': b,
                'pearson_r': round(float(pearson), 4) if pd.notna(pearson) else np.nan,
                'spearman_r': round(float(spearman), 4) if pd.notna(spearman) else np.nan,
                'n': len(sub),
            })
    return pd.DataFrame(rows)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd my_strategy && python -m pytest tests/test_trade_attribution_extra.py -v
```

- [ ] **Step 5: Commit**

```bash
git add my_strategy/tools/trade_attribution_extra.py my_strategy/tests/test_trade_attribution_extra.py
git commit -m "feat(stats): add signal_correlation_matrix report"
```

---

## Task 6: `trade_attribution_extra.py` — multi_factor_combo_stats

**Files:**
- Modify: `my_strategy/tools/trade_attribution_extra.py`
- Modify: `my_strategy/tests/test_trade_attribution_extra.py`

- [ ] **Step 1: 追加失败测试**

```python
from my_strategy.tools.trade_attribution_extra import compute_multi_factor_combo_stats


def test_compute_multi_factor_combo_stats_3way_crosstab():
    trades = pd.DataFrame({
        'return_pct': [10, -5, 8, -3, 12, -2, 15, -8],
        'sig_a': [True, True, False, False, True, True, False, False],
        'sig_b': [True, False, True, False, True, False, True, False],
        'sig_c': [True, True, True, True, False, False, False, False],
    })
    combos = [('sig_a', 'sig_b', 'sig_c')]
    out = compute_multi_factor_combo_stats(trades, combos)
    assert set(out.columns) >= {
        'signal_a_name', 'signal_a_value',
        'signal_b_name', 'signal_b_value',
        'signal_c_name', 'signal_c_value',
        'n', 'win_rate', 'avg_return',
        't_stat_vs_overall', 'p_value_vs_overall', 'low_sample_warning',
    }
    # 8 笔交易共 8 种组合可能（2^3）
    assert len(out) <= 8
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd my_strategy && python -m pytest tests/test_trade_attribution_extra.py::test_compute_multi_factor_combo_stats_3way_crosstab -v
```

- [ ] **Step 3: 写实现（追加）**

```python
from my_strategy.tools.stats_helpers import t_test_welch


def compute_multi_factor_combo_stats(
    trades: pd.DataFrame,
    combos: list,
    min_sample: int = 100,
) -> pd.DataFrame:
    """对每个 (a, b, c) 三元组做交叉聚合。combos: [(name_a, name_b, name_c), ...]"""
    overall = trades['return_pct'].dropna()
    rows = []
    for a, b, c in combos:
        if not all(col in trades.columns for col in (a, b, c)):
            continue
        for (va, vb, vc), sub in trades.groupby([a, b, c], dropna=False):
            r = sub['return_pct'].dropna()
            n = len(r)
            if n == 0:
                continue
            t_stat, p_val = (np.nan, np.nan)
            if n >= 2:
                t_stat, p_val = t_test_welch(r, overall)
            rows.append({
                'signal_a_name': a, 'signal_a_value': str(va),
                'signal_b_name': b, 'signal_b_value': str(vb),
                'signal_c_name': c, 'signal_c_value': str(vc),
                'n': n,
                'win_rate': round(float((r > 0).mean()), 4),
                'avg_return': round(float(r.mean()), 4),
                't_stat_vs_overall': round(t_stat, 4) if pd.notna(t_stat) else np.nan,
                'p_value_vs_overall': round(p_val, 4) if pd.notna(p_val) else np.nan,
                'low_sample_warning': n < min_sample,
            })
    return pd.DataFrame(rows)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd my_strategy && python -m pytest tests/test_trade_attribution_extra.py -v
```

- [ ] **Step 5: Commit**

```bash
git add my_strategy/tools/trade_attribution_extra.py my_strategy/tests/test_trade_attribution_extra.py
git commit -m "feat(stats): add multi_factor_combo_stats (3-way crosstab)"
```

---

## Task 7: `trade_attribution_extra.py` — significance_summary + 模块入口 run()

**Files:**
- Modify: `my_strategy/tools/trade_attribution_extra.py`
- Modify: `my_strategy/tests/test_trade_attribution_extra.py`

- [ ] **Step 1: 追加失败测试**

```python
from my_strategy.tools.trade_attribution_extra import compute_significance_summary


def test_compute_significance_summary_long_format_with_significance_columns():
    trades = pd.DataFrame({
        'return_pct': list(range(-10, 10)) * 5,  # 100 笔，足够触发显著
        'entry_date': pd.date_range('2024-01-01', periods=100),
        'exit_reason': ['MA25清仓'] * 50 + ['MA60止损'] * 50,
        'entry_hs300_dif_above_zero': [True] * 60 + [False] * 40,
    })
    out = compute_significance_summary(trades)
    assert set(out.columns) >= {
        'report_name', 'bucket_field', 'bucket_value',
        'n', 'mean_return', 'std_return', 'std_err',
        'ci_low_95', 'ci_high_95',
        't_stat_vs_zero', 'p_value_vs_zero',
        't_stat_vs_overall', 'p_value_vs_overall',
        'low_sample_warning', 'significant_flag',
    }
    # 至少应包含 exit_reason 和 entry_hs300_dif_above_zero 两类报告
    assert (out['report_name'] == 'exit_reason_stats').any()
    assert (out['report_name'] == 'hs300_dif_stats').any()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd my_strategy && python -m pytest tests/test_trade_attribution_extra.py::test_compute_significance_summary_long_format_with_significance_columns -v
```

- [ ] **Step 3: 写实现（追加）**

```python
from my_strategy.tools.stats_helpers import bucket_stats_with_significance


_SIGNIFICANCE_TARGETS = [
    # (report_name, bucket_field, value_extractor)
    # value_extractor 接收 trades，返回 {bucket_value: series_of_returns}
    ('exit_reason_stats', 'exit_reason',
     lambda t: {str(v): g['return_pct'] for v, g in t.groupby('exit_reason')}),
    ('hs300_dif_stats', 'entry_hs300_dif_above_zero',
     lambda t: {str(v): g['return_pct'] for v, g in t.groupby('entry_hs300_dif_above_zero')}
        if 'entry_hs300_dif_above_zero' in t.columns else {}),
    ('hs300_bull_align_stats', 'entry_hs300_bull_align',
     lambda t: {str(v): g['return_pct'] for v, g in t.groupby('entry_hs300_bull_align')}
        if 'entry_hs300_bull_align' in t.columns else {}),
    ('stock_bull_align_stats', 'entry_stock_bull_align',
     lambda t: {str(v): g['return_pct'] for v, g in t.groupby('entry_stock_bull_align')}
        if 'entry_stock_bull_align' in t.columns else {}),
    ('stock_above_ma25_stats', 'entry_stock_above_ma25',
     lambda t: {str(v): g['return_pct'] for v, g in t.groupby('entry_stock_above_ma25')}
        if 'entry_stock_above_ma25' in t.columns else {}),
    ('sector_bull_align_stats', 'entry_sector_bull_align',
     lambda t: {str(v): g['return_pct'] for v, g in t.groupby('entry_sector_bull_align')}
        if 'entry_sector_bull_align' in t.columns else {}),
    ('sector_above_ma25_stats', 'entry_sector_above_ma25',
     lambda t: {str(v): g['return_pct'] for v, g in t.groupby('entry_sector_above_ma25')}
        if 'entry_sector_above_ma25' in t.columns else {}),
    ('sector_dif_stats', 'entry_sector_dif_above_zero',
     lambda t: {str(v): g['return_pct'] for v, g in t.groupby('entry_sector_dif_above_zero')}
        if 'entry_sector_dif_above_zero' in t.columns else {}),
    ('sector_week_macd_stats', 'entry_sector_week_macd_zone',
     lambda t: {str(v): g['return_pct'] for v, g in t.groupby('entry_sector_week_macd_zone')}
        if 'entry_sector_week_macd_zone' in t.columns else {}),
    ('sector_month_macd_stats', 'entry_sector_month_macd_zone',
     lambda t: {str(v): g['return_pct'] for v, g in t.groupby('entry_sector_month_macd_zone')}
        if 'entry_sector_month_macd_zone' in t.columns else {}),
    ('yearly_stats', 'year',
     lambda t: {str(int(y)): g['return_pct'] for y, g in t.groupby(pd.to_datetime(t['entry_date']).dt.year)}
        if 'entry_date' in t.columns else {}),
]


def compute_significance_summary(trades: pd.DataFrame) -> pd.DataFrame:
    overall = trades['return_pct'].dropna()
    out_rows = []
    for report_name, bucket_field, extractor in _SIGNIFICANCE_TARGETS:
        try:
            grouped = extractor(trades)
        except Exception:
            grouped = {}
        if not grouped:
            continue
        sub = bucket_stats_with_significance(grouped, overall)
        if sub.empty:
            continue
        sub['report_name'] = report_name
        sub['bucket_field'] = bucket_field
        sub.rename(columns={'bucket': 'bucket_value'}, inplace=True)
        out_rows.append(sub)
    if not out_rows:
        return pd.DataFrame()
    return pd.concat(out_rows, ignore_index=True)[[
        'report_name', 'bucket_field', 'bucket_value',
        'n', 'mean_return', 'std_return', 'std_err',
        'ci_low_95', 'ci_high_95',
        't_stat_vs_zero', 'p_value_vs_zero',
        't_stat_vs_overall', 'p_value_vs_overall',
        'low_sample_warning', 'significant_flag',
    ]]


# 模块入口
def run(trades: pd.DataFrame, out_dir: Path, signals_whitelist: list, combos: list) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    compute_payoff_metrics(trades).to_csv(out_dir / 'payoff_metrics.csv', index=False)
    compute_signal_stability(trades, signals_whitelist).to_csv(out_dir / 'signal_stability.csv', index=False)
    compute_signal_correlation_matrix(trades, signals_whitelist).to_csv(out_dir / 'signal_correlation_matrix.csv', index=False)
    compute_multi_factor_combo_stats(trades, combos).to_csv(out_dir / 'multi_factor_combo_stats.csv', index=False)
    compute_significance_summary(trades).to_csv(out_dir / 'significance_summary.csv', index=False)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd my_strategy && python -m pytest tests/test_trade_attribution_extra.py -v
```

- [ ] **Step 5: Commit**

```bash
git add my_strategy/tools/trade_attribution_extra.py my_strategy/tests/test_trade_attribution_extra.py
git commit -m "feat(stats): add significance_summary + module run() entry"
```

---

## Task 8: `portfolio_attribution.py` — portfolio_risk_metrics

**Files:**
- Create: `my_strategy/tools/portfolio_attribution.py`
- Test: `my_strategy/tests/test_portfolio_attribution.py`

- [ ] **Step 1: 写失败测试**

```python
# my_strategy/tests/test_portfolio_attribution.py
import numpy as np
import pandas as pd
from my_strategy.tools.portfolio_attribution import compute_portfolio_risk_metrics


def test_compute_portfolio_risk_metrics_returns_overall_yearly_monthly():
    np.random.seed(0)
    dates = pd.date_range('2019-01-01', '2020-12-31', freq='B')
    daily_ret = pd.Series(np.random.normal(0.0005, 0.01, size=len(dates)), index=dates)
    out = compute_portfolio_risk_metrics(daily_ret)
    assert set(out.columns) >= {
        'period_type', 'period_label', 'sharpe', 'sortino', 'calmar',
        'max_drawdown', 'max_dd_duration_days',
        'annualized_return', 'annualized_vol', 'downside_vol',
    }
    assert (out['period_type'] == 'overall').any()
    assert (out['period_type'] == 'yearly').any()
    assert (out['period_type'] == 'monthly').any()
    overall = out[out['period_type'] == 'overall'].iloc[0]
    assert overall['max_drawdown'] <= 0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd my_strategy && python -m pytest tests/test_portfolio_attribution.py -v
```

- [ ] **Step 3: 写实现**

```python
# my_strategy/tools/portfolio_attribution.py
"""Portfolio-level 归因报告（5 张）。输入: _TimeReturn 日收益、benchmark、position_count_log。"""
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_TRADING_DAYS = 252


def _max_drawdown(equity: pd.Series) -> tuple:
    """返回 (max_dd, dd_duration_days)。equity 为累计资金曲线（从 1 开始）。"""
    if equity.empty:
        return (np.nan, 0)
    running_peak = equity.cummax()
    dd = equity / running_peak - 1.0
    max_dd = float(dd.min())
    if max_dd == 0:
        return (0.0, 0)
    trough_idx = dd.idxmin()
    peak_before = equity[:trough_idx].idxmax()
    duration = (trough_idx - peak_before).days
    return (max_dd, int(duration))


def _risk_block(daily_ret: pd.Series, period_type: str, period_label: str) -> dict:
    r = daily_ret.dropna()
    if len(r) < 2:
        return None
    equity = (1 + r).cumprod()
    ann_ret = float((1 + r.mean()) ** _TRADING_DAYS - 1)
    ann_vol = float(r.std(ddof=1) * np.sqrt(_TRADING_DAYS))
    downside = r[r < 0]
    down_vol = float(downside.std(ddof=1) * np.sqrt(_TRADING_DAYS)) if len(downside) >= 2 else np.nan
    sharpe = ann_ret / ann_vol if ann_vol > 0 else np.nan
    sortino = ann_ret / down_vol if down_vol and down_vol > 0 else np.nan
    max_dd, dd_dur = _max_drawdown(equity)
    calmar = ann_ret / abs(max_dd) if max_dd < 0 else np.nan
    return {
        'period_type': period_type,
        'period_label': period_label,
        'sharpe': round(sharpe, 4) if pd.notna(sharpe) else np.nan,
        'sortino': round(sortino, 4) if pd.notna(sortino) else np.nan,
        'calmar': round(calmar, 4) if pd.notna(calmar) else np.nan,
        'max_drawdown': round(max_dd, 4),
        'max_dd_duration_days': dd_dur,
        'annualized_return': round(ann_ret, 4),
        'annualized_vol': round(ann_vol, 4),
        'downside_vol': round(down_vol, 4) if pd.notna(down_vol) else np.nan,
    }


def compute_portfolio_risk_metrics(daily_ret: pd.Series) -> pd.DataFrame:
    daily_ret = pd.Series(daily_ret).dropna()
    daily_ret.index = pd.to_datetime(daily_ret.index)
    rows = []
    label = f"{daily_ret.index.min().date()}~{daily_ret.index.max().date()}"
    rows.append(_risk_block(daily_ret, 'overall', label))
    for y, g in daily_ret.groupby(daily_ret.index.year):
        rows.append(_risk_block(g, 'yearly', str(int(y))))
    for ym, g in daily_ret.groupby(daily_ret.index.to_period('M').astype(str)):
        rows.append(_risk_block(g, 'monthly', ym))
    return pd.DataFrame([r for r in rows if r is not None])
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd my_strategy && python -m pytest tests/test_portfolio_attribution.py -v
```

- [ ] **Step 5: Commit**

```bash
git add my_strategy/tools/portfolio_attribution.py my_strategy/tests/test_portfolio_attribution.py
git commit -m "feat(stats): add portfolio_risk_metrics report"
```

---

## Task 9: `portfolio_attribution.py` — losing_streak_stats + drawdown_periods

**Files:**
- Modify: `my_strategy/tools/portfolio_attribution.py`
- Modify: `my_strategy/tests/test_portfolio_attribution.py`

- [ ] **Step 1: 追加失败测试**

```python
from my_strategy.tools.portfolio_attribution import (
    compute_losing_streak_stats,
    compute_drawdown_periods,
)


def test_compute_losing_streak_stats_finds_longest_streaks():
    trades = pd.DataFrame({
        'return_pct': [1, -1, -1, 1, -1, -1, -1, 1, 1, -1],
        'entry_date': pd.date_range('2024-01-01', periods=10),
    })
    out = compute_losing_streak_stats(trades)
    longest_loss = out[out['metric'] == 'longest_losing_streak']['value'].iloc[0]
    longest_win = out[out['metric'] == 'longest_winning_streak']['value'].iloc[0]
    assert longest_loss == 3
    assert longest_win == 2


def test_compute_drawdown_periods_returns_top_n_with_durations():
    dates = pd.date_range('2024-01-01', periods=20, freq='D')
    # 构造一个明显的回撤
    rets = [0.01] * 5 + [-0.02] * 5 + [0.01] * 5 + [-0.03] * 3 + [0.01] * 2
    daily_ret = pd.Series(rets, index=dates)
    out = compute_drawdown_periods(daily_ret, top_n=3)
    assert set(out.columns) >= {
        'rank', 'start_date', 'trough_date', 'recovery_date',
        'peak_value', 'trough_value', 'drawdown_pct',
        'duration_days', 'recovery_days',
    }
    assert len(out) <= 3
    assert all(out['drawdown_pct'] < 0)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd my_strategy && python -m pytest tests/test_portfolio_attribution.py::test_compute_losing_streak_stats_finds_longest_streaks tests/test_portfolio_attribution.py::test_compute_drawdown_periods_returns_top_n_with_durations -v
```

- [ ] **Step 3: 写实现（追加到 portfolio_attribution.py）**

```python
def compute_losing_streak_stats(trades: pd.DataFrame) -> pd.DataFrame:
    if 'return_pct' not in trades.columns or 'entry_date' not in trades.columns:
        return pd.DataFrame()
    t = trades.sort_values('entry_date')
    signs = (t['return_pct'] > 0).astype(int).where(t['return_pct'] != 0, np.nan)

    def _streaks(arr, target):
        max_len = cur = 0
        lengths = []
        for x in arr:
            if x == target:
                cur += 1
                max_len = max(max_len, cur)
            else:
                if cur > 0:
                    lengths.append(cur)
                cur = 0
        if cur > 0:
            lengths.append(cur)
        return max_len, lengths

    longest_loss, loss_lens = _streaks(signs.fillna(-1).tolist(), 0)
    longest_win, _ = _streaks(signs.fillna(-1).tolist(), 1)
    avg_loss_streak = float(np.mean(loss_lens)) if loss_lens else 0.0
    pct_ge_5 = float(np.mean([x >= 5 for x in loss_lens])) if loss_lens else 0.0
    return pd.DataFrame([
        {'metric': 'longest_losing_streak', 'value': longest_loss},
        {'metric': 'longest_winning_streak', 'value': longest_win},
        {'metric': 'avg_losing_streak_length', 'value': round(avg_loss_streak, 4)},
        {'metric': 'pct_losing_streaks_ge_5', 'value': round(pct_ge_5, 4)},
    ])


def compute_drawdown_periods(daily_ret: pd.Series, top_n: int = 10) -> pd.DataFrame:
    r = pd.Series(daily_ret).dropna()
    r.index = pd.to_datetime(r.index)
    equity = (1 + r).cumprod()
    running_peak = equity.cummax()
    in_dd = equity < running_peak

    # 找到所有回撤区间
    periods = []
    i = 0
    arr = in_dd.values
    idx = equity.index
    while i < len(arr):
        if arr[i]:
            start = i
            # 找峰值（前一个非回撤点的峰）
            peak_idx = start - 1 if start > 0 else 0
            peak_value = float(equity.iloc[peak_idx])
            # 找谷底
            j = i
            trough_value = float(equity.iloc[j])
            trough_idx = j
            while j < len(arr) and arr[j]:
                if equity.iloc[j] < trough_value:
                    trough_value = float(equity.iloc[j])
                    trough_idx = j
                j += 1
            recovery_idx = j if j < len(arr) else None
            periods.append({
                'start_date': idx[peak_idx],
                'trough_date': idx[trough_idx],
                'recovery_date': idx[recovery_idx] if recovery_idx is not None else pd.NaT,
                'peak_value': peak_value,
                'trough_value': trough_value,
                'drawdown_pct': round((trough_value / peak_value - 1) * 100, 4),
                'duration_days': (idx[trough_idx] - idx[peak_idx]).days,
                'recovery_days': (idx[recovery_idx] - idx[trough_idx]).days
                                 if recovery_idx is not None else -1,
            })
            i = j
        else:
            i += 1
    df = pd.DataFrame(periods)
    if df.empty:
        return df
    df = df.sort_values('drawdown_pct').head(top_n).reset_index(drop=True)
    df.insert(0, 'rank', range(1, len(df) + 1))
    return df
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd my_strategy && python -m pytest tests/test_portfolio_attribution.py -v
```

- [ ] **Step 5: Commit**

```bash
git add my_strategy/tools/portfolio_attribution.py my_strategy/tests/test_portfolio_attribution.py
git commit -m "feat(stats): add losing_streak_stats and drawdown_periods reports"
```

---

## Task 10: `portfolio_attribution.py` — concurrent_positions_stats

**Files:**
- Modify: `my_strategy/tools/portfolio_attribution.py`
- Modify: `my_strategy/tests/test_portfolio_attribution.py`

**前置依赖**：Task 0 已确认 `position_count_log` 的 schema。本任务**默认假设是 list of (date, count) tuple 或 DataFrame[date, count]**；若 Task 0 调研结果不同，需相应调整 `compute_concurrent_positions_stats` 的输入解析。

- [ ] **Step 1: 追加失败测试**

```python
from my_strategy.tools.portfolio_attribution import compute_concurrent_positions_stats


def test_compute_concurrent_positions_stats_summary_and_buckets():
    log = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=10),
        'count': [50, 60, 100, 100, 150, 180, 200, 200, 90, 50],
    })
    out = compute_concurrent_positions_stats(log, max_positions=200)
    assert (out['metric_type'] == 'summary').any()
    assert (out['metric_type'] == 'position_count_bucket').any()
    max_row = out[(out['metric_type'] == 'summary') & (out['bucket'] == 'max')].iloc[0]
    assert max_row['value'] == 200
    pct_at_cap = out[
        (out['metric_type'] == 'summary') & (out['bucket'] == 'pct_at_cap')
    ].iloc[0]
    # 200 出现 2 次 / 10 天 = 0.2
    assert abs(pct_at_cap['value'] - 0.2) < 1e-6
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd my_strategy && python -m pytest tests/test_portfolio_attribution.py::test_compute_concurrent_positions_stats_summary_and_buckets -v
```

- [ ] **Step 3: 写实现（追加）**

```python
def compute_concurrent_positions_stats(
    position_count_log,
    max_positions: int,
) -> pd.DataFrame:
    """输入可以是 DataFrame[date, count] 或 list[(date, count)]。"""
    if isinstance(position_count_log, list):
        df = pd.DataFrame(position_count_log, columns=['date', 'count'])
    else:
        df = pd.DataFrame(position_count_log).copy()
        if 'count' not in df.columns:
            # 兼容其他可能字段名
            df = df.rename(columns={df.columns[1]: 'count'})
    counts = df['count'].astype(int)
    n = len(counts)
    rows = [
        {'metric_type': 'summary', 'bucket': 'max', 'value': float(counts.max()), 'days_at_level': np.nan, 'pct_of_time': np.nan},
        {'metric_type': 'summary', 'bucket': 'avg', 'value': round(float(counts.mean()), 2), 'days_at_level': np.nan, 'pct_of_time': np.nan},
        {'metric_type': 'summary', 'bucket': 'median', 'value': float(counts.median()), 'days_at_level': np.nan, 'pct_of_time': np.nan},
        {'metric_type': 'summary', 'bucket': 'p95', 'value': float(counts.quantile(0.95)), 'days_at_level': np.nan, 'pct_of_time': np.nan},
        {'metric_type': 'summary', 'bucket': 'pct_at_cap', 'value': round(float((counts == max_positions).mean()), 4), 'days_at_level': np.nan, 'pct_of_time': np.nan},
        {'metric_type': 'summary', 'bucket': 'pct_below_50', 'value': round(float((counts < 50).mean()), 4), 'days_at_level': np.nan, 'pct_of_time': np.nan},
    ]
    edges = [(0, 0), (1, 25), (26, 50), (51, 100), (101, 150), (151, 200)]
    for lo, hi in edges:
        mask = (counts >= lo) & (counts <= hi)
        days = int(mask.sum())
        rows.append({
            'metric_type': 'position_count_bucket',
            'bucket': f"{lo}-{hi}" if lo != hi else str(lo),
            'value': np.nan,
            'days_at_level': days,
            'pct_of_time': round(days / n, 4) if n > 0 else 0.0,
        })
    return pd.DataFrame(rows)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd my_strategy && python -m pytest tests/test_portfolio_attribution.py -v
```

- [ ] **Step 5: Commit**

```bash
git add my_strategy/tools/portfolio_attribution.py my_strategy/tests/test_portfolio_attribution.py
git commit -m "feat(stats): add concurrent_positions_stats report"
```

---

## Task 11: `portfolio_attribution.py` — period_alpha + 模块入口 run()

**Files:**
- Modify: `my_strategy/tools/portfolio_attribution.py`
- Modify: `my_strategy/tests/test_portfolio_attribution.py`

- [ ] **Step 1: 追加失败测试**

```python
from my_strategy.tools.portfolio_attribution import compute_period_alpha


def test_compute_period_alpha_with_benchmark():
    np.random.seed(0)
    dates = pd.date_range('2019-01-01', '2019-12-31', freq='B')
    strat = pd.Series(np.random.normal(0.001, 0.01, len(dates)), index=dates)
    bench = pd.Series(np.random.normal(0.0005, 0.01, len(dates)), index=dates)
    out = compute_period_alpha(strat, {'TEST.SH': bench})
    assert set(out.columns) >= {
        'period_type', 'period_label', 'benchmark_code',
        'strategy_return', 'benchmark_return', 'alpha', 'beta',
        'info_ratio', 'tracking_error', 'n_trading_days',
    }
    assert (out['benchmark_code'] == 'TEST.SH').any()
    assert (out['period_type'] == 'overall').any()
    assert (out['period_type'] == 'yearly').any()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd my_strategy && python -m pytest tests/test_portfolio_attribution.py::test_compute_period_alpha_with_benchmark -v
```

- [ ] **Step 3: 写实现（追加）**

```python
def _alpha_block(strat: pd.Series, bench: pd.Series,
                 period_type: str, period_label: str, code: str) -> dict:
    aligned = pd.concat([strat, bench], axis=1, join='inner').dropna()
    aligned.columns = ['s', 'b']
    if len(aligned) < 5:
        return None
    s, b = aligned['s'], aligned['b']
    cov = float(s.cov(b))
    var_b = float(b.var(ddof=1))
    beta = cov / var_b if var_b > 0 else np.nan
    cum_s = float((1 + s).prod() - 1)
    cum_b = float((1 + b).prod() - 1)
    excess = s - b
    te = float(excess.std(ddof=1) * np.sqrt(_TRADING_DAYS))
    excess_ann = float((1 + excess.mean()) ** _TRADING_DAYS - 1)
    info_ratio = excess_ann / te if te > 0 else np.nan
    alpha_ann = excess_ann if pd.isna(beta) else float(
        (1 + s.mean()) ** _TRADING_DAYS - 1
        - beta * ((1 + b.mean()) ** _TRADING_DAYS - 1)
    )
    return {
        'period_type': period_type,
        'period_label': period_label,
        'benchmark_code': code,
        'strategy_return': round(cum_s, 4),
        'benchmark_return': round(cum_b, 4),
        'alpha': round(alpha_ann, 4) if pd.notna(alpha_ann) else np.nan,
        'beta': round(beta, 4) if pd.notna(beta) else np.nan,
        'info_ratio': round(info_ratio, 4) if pd.notna(info_ratio) else np.nan,
        'tracking_error': round(te, 4),
        'n_trading_days': len(aligned),
    }


def compute_period_alpha(strat: pd.Series, benchmarks: dict) -> pd.DataFrame:
    """benchmarks: {benchmark_code: daily_return_series}"""
    strat = pd.Series(strat).dropna()
    strat.index = pd.to_datetime(strat.index)
    rows = []
    for code, bench in benchmarks.items():
        bench = pd.Series(bench).dropna()
        bench.index = pd.to_datetime(bench.index)
        label_overall = f"{strat.index.min().date()}~{strat.index.max().date()}"
        rows.append(_alpha_block(strat, bench, 'overall', label_overall, code))
        for y in sorted(strat.index.year.unique()):
            s_y = strat[strat.index.year == y]
            b_y = bench[bench.index.year == y]
            rows.append(_alpha_block(s_y, b_y, 'yearly', str(y), code))
        for ym in sorted(strat.index.to_period('M').astype(str).unique()):
            s_m = strat[strat.index.to_period('M').astype(str) == ym]
            b_m = bench[bench.index.to_period('M').astype(str) == ym]
            rows.append(_alpha_block(s_m, b_m, 'monthly', ym, code))
    return pd.DataFrame([r for r in rows if r is not None])


# 模块入口
def run(
    daily_ret: pd.Series,
    position_count_log,
    benchmarks: dict,
    trades: pd.DataFrame,
    cfg: dict,
    out_dir: Path,
) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    compute_portfolio_risk_metrics(daily_ret).to_csv(out_dir / 'portfolio_risk_metrics.csv', index=False)
    compute_losing_streak_stats(trades).to_csv(out_dir / 'losing_streak_stats.csv', index=False)
    compute_drawdown_periods(daily_ret).to_csv(out_dir / 'drawdown_periods.csv', index=False)
    compute_concurrent_positions_stats(
        position_count_log, max_positions=cfg.get('max_positions', 200)
    ).to_csv(out_dir / 'concurrent_positions_stats.csv', index=False)
    compute_period_alpha(daily_ret, benchmarks).to_csv(out_dir / 'period_alpha.csv', index=False)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd my_strategy && python -m pytest tests/test_portfolio_attribution.py -v
```

- [ ] **Step 5: Commit**

```bash
git add my_strategy/tools/portfolio_attribution.py my_strategy/tests/test_portfolio_attribution.py
git commit -m "feat(stats): add period_alpha + portfolio_attribution.run()"
```

---

## Task 12: `position_curve_attribution.py` — holding_period_curve

**Files:**
- Create: `my_strategy/tools/position_curve_attribution.py`
- Test: `my_strategy/tests/test_position_curve_attribution.py`

- [ ] **Step 1: 写失败测试**

```python
# my_strategy/tests/test_position_curve_attribution.py
import pandas as pd
import pytest
from my_strategy.tools.position_curve_attribution import compute_holding_period_curve


def _make_daily_pnl():
    """构造 2 笔交易，每笔 5 天持仓"""
    rows = []
    # trade 0: 持仓 5 天，每天 +1%
    for i in range(5):
        rows.append({
            'trade_id': 0, 'ts_code': 'A',
            'entry_date': pd.Timestamp('2024-01-02'),
            'holding_day_n': i,
            'date': pd.Timestamp('2024-01-02') + pd.Timedelta(days=i),
            'close': 10.0 * (1 + i * 0.01),
            'cum_return_pct': i * 1.0,
            'drawdown_from_peak_pct': 0.0,
            'sector_code': '801010',
        })
    # trade 1: 持仓 3 天
    for i in range(3):
        rows.append({
            'trade_id': 1, 'ts_code': 'B',
            'entry_date': pd.Timestamp('2024-02-02'),
            'holding_day_n': i,
            'date': pd.Timestamp('2024-02-02') + pd.Timedelta(days=i),
            'close': 20.0 * (1 - i * 0.01),
            'cum_return_pct': -i * 1.0,
            'drawdown_from_peak_pct': -i * 1.0,
            'sector_code': '801080',
        })
    return pd.DataFrame(rows)


def test_compute_holding_period_curve_emits_sample_points():
    pnl = _make_daily_pnl()
    out = compute_holding_period_curve(pnl)
    assert set(out.columns) >= {
        'holding_day_n', 'n_active_trades', 'avg_cum_return',
        'median_cum_return', 'win_rate_at_day_n',
        'p25_cum_return', 'p75_cum_return', 'avg_drawdown_from_peak',
    }
    # day 0: 2 笔活跃；day 3: 1 笔活跃（trade 0 仍在）
    d0 = out[out['holding_day_n'] == 0].iloc[0]
    assert d0['n_active_trades'] == 2
    d3 = out[out['holding_day_n'] == 3].iloc[0]
    assert d3['n_active_trades'] == 1
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd my_strategy && python -m pytest tests/test_position_curve_attribution.py -v
```

- [ ] **Step 3: 写实现**

```python
# my_strategy/tools/position_curve_attribution.py
"""基于 daily_position_pnl / daily_portfolio_snapshot / trade_list 的报告（4 张）。"""
from pathlib import Path

import numpy as np
import pandas as pd

_HOLDING_SAMPLE_DAYS = [1, 2, 3, 5, 7, 10, 15, 20, 25, 30, 40, 50, 60, 75, 90]


def compute_holding_period_curve(daily_position_pnl: pd.DataFrame) -> pd.DataFrame:
    sample_points = [0] + _HOLDING_SAMPLE_DAYS
    rows = []
    for n in sample_points:
        sub = daily_position_pnl[daily_position_pnl['holding_day_n'] == n]
        if sub.empty:
            continue
        r = sub['cum_return_pct'].dropna()
        dd = sub['drawdown_from_peak_pct'].dropna()
        rows.append({
            'holding_day_n': n,
            'n_active_trades': len(sub),
            'avg_cum_return': round(float(r.mean()), 4) if len(r) else np.nan,
            'median_cum_return': round(float(r.median()), 4) if len(r) else np.nan,
            'win_rate_at_day_n': round(float((r > 0).mean()), 4) if len(r) else np.nan,
            'p25_cum_return': round(float(r.quantile(0.25)), 4) if len(r) else np.nan,
            'p75_cum_return': round(float(r.quantile(0.75)), 4) if len(r) else np.nan,
            'avg_drawdown_from_peak': round(float(dd.mean()), 4) if len(dd) else np.nan,
        })
    return pd.DataFrame(rows)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd my_strategy && python -m pytest tests/test_position_curve_attribution.py -v
```

- [ ] **Step 5: Commit**

```bash
git add my_strategy/tools/position_curve_attribution.py my_strategy/tests/test_position_curve_attribution.py
git commit -m "feat(stats): add holding_period_curve report"
```

---

## Task 13: `position_curve_attribution.py` — mfe_timing

**Files:**
- Modify: `my_strategy/tools/position_curve_attribution.py`
- Modify: `my_strategy/tests/test_position_curve_attribution.py`

- [ ] **Step 1: 追加失败测试**

```python
from my_strategy.tools.position_curve_attribution import compute_mfe_timing


def test_compute_mfe_timing_classifies_by_position_in_holding():
    # trade 0: peak 在持仓早期 (day 1 of 6)
    rows = []
    for i in range(6):
        rows.append({
            'trade_id': 0, 'ts_code': 'A',
            'entry_date': pd.Timestamp('2024-01-02'),
            'holding_day_n': i, 'date': pd.Timestamp('2024-01-02') + pd.Timedelta(days=i),
            'close': 10.0, 'cum_return_pct': [0, 5, 3, 2, 1, 0][i],
            'drawdown_from_peak_pct': 0.0, 'sector_code': '801010',
        })
    # trade 1: peak 在持仓晚期 (day 5 of 6)
    for i in range(6):
        rows.append({
            'trade_id': 1, 'ts_code': 'B',
            'entry_date': pd.Timestamp('2024-02-02'),
            'holding_day_n': i, 'date': pd.Timestamp('2024-02-02') + pd.Timedelta(days=i),
            'close': 20.0, 'cum_return_pct': [0, 1, 2, 3, 4, 5][i],
            'drawdown_from_peak_pct': 0.0, 'sector_code': '801080',
        })
    pnl = pd.DataFrame(rows)
    out = compute_mfe_timing(pnl)
    assert set(out.columns) >= {
        'mfe_timing_bucket', 'n', 'win_rate', 'avg_return',
        'avg_holding_days', 'avg_mfe_pct',
    }
    buckets = out['mfe_timing_bucket'].tolist()
    assert any('早期' in b for b in buckets)
    assert any('晚期' in b for b in buckets)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd my_strategy && python -m pytest tests/test_position_curve_attribution.py::test_compute_mfe_timing_classifies_by_position_in_holding -v
```

- [ ] **Step 3: 写实现（追加）**

```python
def compute_mfe_timing(daily_position_pnl: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for trade_id, g in daily_position_pnl.groupby('trade_id'):
        if g.empty:
            continue
        max_day = int(g['holding_day_n'].max())
        if max_day == 0:
            continue
        peak_idx = g['cum_return_pct'].idxmax()
        peak_day = int(g.loc[peak_idx, 'holding_day_n'])
        peak_value = float(g.loc[peak_idx, 'cum_return_pct'])
        ratio = peak_day / max_day
        if ratio <= 1/3:
            bucket = '早期(前 1/3)'
        elif ratio <= 2/3:
            bucket = '中期(中 1/3)'
        else:
            bucket = '晚期(后 1/3)'
        final_return = float(g.iloc[-1]['cum_return_pct'])
        rows.append({
            'trade_id': trade_id,
            'mfe_timing_bucket': bucket,
            'holding_days': max_day,
            'final_return': final_return,
            'mfe_pct': peak_value,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    out = df.groupby('mfe_timing_bucket').agg(
        n=('trade_id', 'count'),
        win_rate=('final_return', lambda s: (s > 0).mean()),
        avg_return=('final_return', 'mean'),
        avg_holding_days=('holding_days', 'mean'),
        avg_mfe_pct=('mfe_pct', 'mean'),
    ).reset_index()
    for c in ['win_rate', 'avg_return', 'avg_holding_days', 'avg_mfe_pct']:
        out[c] = out[c].round(4)
    return out
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd my_strategy && python -m pytest tests/test_position_curve_attribution.py -v
```

- [ ] **Step 5: Commit**

```bash
git add my_strategy/tools/position_curve_attribution.py my_strategy/tests/test_position_curve_attribution.py
git commit -m "feat(stats): add mfe_timing report"
```

---

## Task 14: `position_curve_attribution.py` — sector_concentration_stats

**Files:**
- Modify: `my_strategy/tools/position_curve_attribution.py`
- Modify: `my_strategy/tests/test_position_curve_attribution.py`

- [ ] **Step 1: 追加失败测试**

```python
from my_strategy.tools.position_curve_attribution import compute_sector_concentration_stats


def test_compute_sector_concentration_stats_summary_and_top_n():
    snap = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=5),
        'n_positions': [10, 10, 10, 10, 10],
        'sectors_held': [3, 2, 5, 4, 1],
        'top_sector_code': ['801010', '801010', '801080', '801010', '801080'],
        'top_sector_share': [0.5, 0.7, 0.3, 0.4, 1.0],
        'herfindahl_index': [0.30, 0.50, 0.20, 0.25, 1.0],
    })
    out = compute_sector_concentration_stats(snap, top_n=2)
    assert (out['metric_type'] == 'summary').any()
    assert (out['metric_type'] == 'top_concentrated_day').any()
    avg_max = out[(out['metric_type'] == 'summary') & (out['label'] == 'avg_max_sector_share')].iloc[0]
    # avg(0.5, 0.7, 0.3, 0.4, 1.0) = 0.58
    assert abs(avg_max['value'] - 0.58) < 1e-3
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd my_strategy && python -m pytest tests/test_position_curve_attribution.py::test_compute_sector_concentration_stats_summary_and_top_n -v
```

- [ ] **Step 3: 写实现（追加）**

```python
def compute_sector_concentration_stats(
    daily_portfolio_snapshot: pd.DataFrame,
    top_n: int = 10,
) -> pd.DataFrame:
    snap = daily_portfolio_snapshot
    rows = []
    summary_specs = [
        ('avg_max_sector_share', 'top_sector_share', lambda s: s.mean()),
        ('p95_max_sector_share', 'top_sector_share', lambda s: s.quantile(0.95)),
        ('max_max_sector_share', 'top_sector_share', lambda s: s.max()),
        ('avg_herfindahl_index', 'herfindahl_index', lambda s: s.mean()),
        ('p95_herfindahl_index', 'herfindahl_index', lambda s: s.quantile(0.95)),
    ]
    for label, col, fn in summary_specs:
        if col not in snap.columns:
            continue
        rows.append({
            'metric_type': 'summary',
            'label': label,
            'value': round(float(fn(snap[col])), 4),
            'top_sector_code': '',
            'top_sector_share': np.nan,
            'herfindahl_index': np.nan,
            'n_positions': np.nan,
        })
    top = snap.sort_values('top_sector_share', ascending=False).head(top_n)
    for _, r in top.iterrows():
        rows.append({
            'metric_type': 'top_concentrated_day',
            'label': str(pd.to_datetime(r['date']).date()),
            'value': np.nan,
            'top_sector_code': r['top_sector_code'],
            'top_sector_share': round(float(r['top_sector_share']), 4),
            'herfindahl_index': round(float(r['herfindahl_index']), 4),
            'n_positions': int(r['n_positions']),
        })
    return pd.DataFrame(rows)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd my_strategy && python -m pytest tests/test_position_curve_attribution.py -v
```

- [ ] **Step 5: Commit**

```bash
git add my_strategy/tools/position_curve_attribution.py my_strategy/tests/test_position_curve_attribution.py
git commit -m "feat(stats): add sector_concentration_stats report"
```

---

## Task 15: `position_curve_attribution.py` — cost_breakdown + 模块入口 run()

**Files:**
- Modify: `my_strategy/tools/position_curve_attribution.py`
- Modify: `my_strategy/tests/test_position_curve_attribution.py`

**前置依赖**：Task 0 已确认 `trade_list.csv` 是否含 commission 列。本实现支持两种模式：
- **模式 A**（trade_list 已有 commission/stamp_duty 列）：直接 sum
- **模式 B**（trade_list 仅有 turnover）：按 `commission_rate × turnover + stamp_duty × sell_amount` 反推

实现需同时支持，自动检测列存在与否。

- [ ] **Step 1: 追加失败测试**

```python
from my_strategy.tools.position_curve_attribution import compute_cost_breakdown


def test_compute_cost_breakdown_with_explicit_commission_column():
    trades = pd.DataFrame({
        'entry_date': pd.to_datetime(['2024-01-02', '2024-02-02']),
        'gross_pnl': [10000.0, -5000.0],
        'commission': [30.0, 25.0],
        'stamp_duty': [50.0, 40.0],
        'exit_reason': ['MA25清仓', 'MA60止损'],
    })
    out = compute_cost_breakdown(trades, cfg={'commission_rate': 0.0003, 'stamp_duty': 0.001})
    overall = out[(out['dimension'] == 'overall') & (out['bucket'] == 'all')].iloc[0]
    assert overall['n_trades'] == 2
    assert abs(overall['total_commission'] - 55.0) < 1e-6
    assert abs(overall['total_stamp_duty'] - 90.0) < 1e-6
    # cost_pct_of_gross = (55+90) / |10000-5000+...| 数值正确即可
    assert overall['net_pnl'] == 10000.0 - 5000.0 - 55.0 - 90.0
    assert (out['dimension'] == 'year').any()
    assert (out['dimension'] == 'exit_reason').any()


def test_compute_cost_breakdown_fallback_estimate_from_turnover():
    trades = pd.DataFrame({
        'entry_date': pd.to_datetime(['2024-01-02']),
        'gross_pnl': [10000.0],
        'turnover': [1_000_000.0],   # 双边总成交额
        'sell_amount': [500_000.0],  # 卖出金额（印花税基数）
        'exit_reason': ['MA25清仓'],
    })
    out = compute_cost_breakdown(trades, cfg={'commission_rate': 0.0003, 'stamp_duty': 0.001})
    overall = out[(out['dimension'] == 'overall') & (out['bucket'] == 'all')].iloc[0]
    # 0.0003 * 1_000_000 = 300, 0.001 * 500_000 = 500
    assert abs(overall['total_commission'] - 300.0) < 1e-6
    assert abs(overall['total_stamp_duty'] - 500.0) < 1e-6
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd my_strategy && python -m pytest tests/test_position_curve_attribution.py::test_compute_cost_breakdown_with_explicit_commission_column tests/test_position_curve_attribution.py::test_compute_cost_breakdown_fallback_estimate_from_turnover -v
```

- [ ] **Step 3: 写实现（追加）**

```python
def _cost_block(sub: pd.DataFrame, dimension: str, bucket: str, cfg: dict) -> dict:
    n = len(sub)
    if n == 0:
        return None
    if 'commission' in sub.columns and 'stamp_duty' in sub.columns:
        commission = float(sub['commission'].fillna(0).sum())
        stamp = float(sub['stamp_duty'].fillna(0).sum())
        turnover = float(sub['turnover'].fillna(0).sum()) if 'turnover' in sub.columns else np.nan
    else:
        comm_rate = float(cfg.get('commission_rate', 0.0003))
        stamp_rate = float(cfg.get('stamp_duty', 0.001))
        turnover = float(sub['turnover'].fillna(0).sum()) if 'turnover' in sub.columns else np.nan
        sell_amt = (float(sub['sell_amount'].fillna(0).sum())
                    if 'sell_amount' in sub.columns else turnover / 2 if pd.notna(turnover) else np.nan)
        commission = comm_rate * turnover if pd.notna(turnover) else np.nan
        stamp = stamp_rate * sell_amt if pd.notna(sell_amt) else np.nan
    gross = float(sub['gross_pnl'].fillna(0).sum()) if 'gross_pnl' in sub.columns else np.nan
    total_cost = (commission if pd.notna(commission) else 0.0) + (stamp if pd.notna(stamp) else 0.0)
    net = gross - total_cost if pd.notna(gross) else np.nan
    return {
        'dimension': dimension,
        'bucket': bucket,
        'n_trades': n,
        'gross_pnl': round(gross, 2) if pd.notna(gross) else np.nan,
        'total_commission': round(commission, 2) if pd.notna(commission) else np.nan,
        'total_stamp_duty': round(stamp, 2) if pd.notna(stamp) else np.nan,
        'net_pnl': round(net, 2) if pd.notna(net) else np.nan,
        'cost_pct_of_gross': round(total_cost / abs(gross), 4) if pd.notna(gross) and gross != 0 else np.nan,
        'cost_pct_of_turnover': round(total_cost / turnover, 6) if pd.notna(turnover) and turnover > 0 else np.nan,
    }


def compute_cost_breakdown(trades: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    rows = [_cost_block(trades, 'overall', 'all', cfg)]
    if 'entry_date' in trades.columns:
        for y, sub in trades.groupby(pd.to_datetime(trades['entry_date']).dt.year):
            rows.append(_cost_block(sub, 'year', str(int(y)), cfg))
    if 'exit_reason' in trades.columns:
        for v, sub in trades.groupby('exit_reason'):
            rows.append(_cost_block(sub, 'exit_reason', str(v), cfg))
    return pd.DataFrame([r for r in rows if r is not None])


# 模块入口
def run(project_root: Path, cfg: dict) -> None:
    project_root = Path(project_root)
    results_dir = project_root / cfg.get('results_dir', 'results/')
    out_dir = project_root / cfg['attribution_report_dir']
    out_dir.mkdir(parents=True, exist_ok=True)

    pnl_path = results_dir / 'daily_position_pnl.csv'
    snap_path = results_dir / 'daily_portfolio_snapshot.csv'
    if not pnl_path.exists():
        raise FileNotFoundError(f"daily_position_pnl missing: {pnl_path}")
    if not snap_path.exists():
        raise FileNotFoundError(f"daily_portfolio_snapshot missing: {snap_path}")
    pnl = pd.read_csv(pnl_path, parse_dates=['entry_date', 'date'])
    snap = pd.read_csv(snap_path, parse_dates=['date'])

    compute_holding_period_curve(pnl).to_csv(out_dir / 'holding_period_curve.csv', index=False)
    compute_mfe_timing(pnl).to_csv(out_dir / 'mfe_timing.csv', index=False)
    compute_sector_concentration_stats(snap).to_csv(out_dir / 'sector_concentration_stats.csv', index=False)

    trade_list_path = results_dir / 'trade_list.csv'
    if trade_list_path.exists():
        trade_list = pd.read_csv(trade_list_path, parse_dates=['entry_date'], errors='ignore') \
                     if 'entry_date' in pd.read_csv(trade_list_path, nrows=0).columns \
                     else pd.read_csv(trade_list_path)
    else:
        # 退回到 trade_summary
        trade_list = pd.read_csv(results_dir / 'trade_summary.csv', parse_dates=['entry_date'])
    compute_cost_breakdown(trade_list, cfg).to_csv(out_dir / 'cost_breakdown.csv', index=False)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd my_strategy && python -m pytest tests/test_position_curve_attribution.py -v
```

- [ ] **Step 5: Commit**

```bash
git add my_strategy/tools/position_curve_attribution.py my_strategy/tests/test_position_curve_attribution.py
git commit -m "feat(stats): add cost_breakdown + position_curve_attribution.run()"
```

---

## Task 16: `attribution_runner.py` — 顶层编排

**Files:**
- Create: `my_strategy/tools/attribution_runner.py`
- Test: `my_strategy/tests/test_attribution_runner.py`

- [ ] **Step 1: 写失败测试**

```python
# my_strategy/tests/test_attribution_runner.py
"""轻量集成测试：使用最小输入，确认 runner 能依次调起所有子模块并产出文件。"""
import pandas as pd
import numpy as np
import pytest
from pathlib import Path
from my_strategy.tools.attribution_runner import run as runner_run


@pytest.fixture
def fake_project(tmp_path):
    """构造一个最小可跑的项目目录。"""
    root = tmp_path / "proj"
    (root / "data").mkdir(parents=True)
    (root / "results").mkdir()
    (root / "reports").mkdir()

    # trade_summary.csv
    trades = pd.DataFrame({
        'ts_code': ['000001.SZ'] * 3 + ['000002.SZ'] * 3,
        'entry_date': pd.to_datetime(['2024-01-02', '2024-02-02', '2024-03-02'] * 2),
        'exit_date': pd.to_datetime(['2024-01-10', '2024-02-10', '2024-03-10'] * 2),
        'avg_cost': [10.0, 11.0, 12.0, 20.0, 21.0, 22.0],
        'return_pct': [5.0, -3.0, 2.0, -4.0, 6.0, 1.0],
        'holding_days': [8, 8, 8, 8, 8, 8],
        'exit_reason': ['MA25清仓'] * 6,
        'industry': ['801010'] * 3 + ['801080'] * 3,
        'gross_pnl': [500, -300, 200, -400, 600, 100],
        'entry_hs300_dif_above_zero': [True, False, True, False, True, False],
        'entry_stock_bull_align': [True, True, False, False, True, False],
        'entry_sector_dif_above_zero': [True, True, False, True, False, False],
    })
    trades.to_csv(root / "results" / "trade_summary.csv", index=False)
    trades.to_csv(root / "results" / "trade_list.csv", index=False)

    # 每个 ts_code 的日线
    for code in ['000001.SZ', '000002.SZ']:
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', '2024-04-01', freq='B'),
        })
        df['close'] = 10.0 + np.arange(len(df)) * 0.01
        df.to_csv(root / "data" / f"{code}_daily.csv", index=False)

    # stock_sector
    pd.DataFrame({
        'ts_code': ['000001.SZ', '000002.SZ'],
        'sw_index_code': ['801010', '801080'],
    }).to_csv(root / "data" / "stock_sector.csv", index=False)

    return root


def test_runner_produces_all_new_reports(fake_project):
    np.random.seed(0)
    daily_ret = pd.Series(
        np.random.normal(0.001, 0.01, 60),
        index=pd.date_range('2024-01-02', periods=60, freq='B'),
    )
    bench = pd.Series(
        np.random.normal(0.0005, 0.01, 60),
        index=pd.date_range('2024-01-02', periods=60, freq='B'),
    )
    position_count_log = pd.DataFrame({
        'date': pd.date_range('2024-01-02', periods=60, freq='B'),
        'count': [50] * 60,
    })
    cfg = {
        'data_dir': 'data/',
        'results_dir': 'results/',
        'attribution_report_dir': 'reports',
        'data_paths': {'stock_sector_csv': 'data/stock_sector.csv'},
        'max_positions': 200,
        'commission_rate': 0.0003,
        'stamp_duty': 0.001,
    }
    benchmarks = {'TEST.SH': bench}

    runner_run(
        project_root=fake_project,
        cfg=cfg,
        daily_ret=daily_ret,
        position_count_log=position_count_log,
        benchmarks=benchmarks,
    )

    expected = [
        'payoff_metrics.csv', 'signal_stability.csv',
        'signal_correlation_matrix.csv', 'multi_factor_combo_stats.csv',
        'significance_summary.csv',
        'portfolio_risk_metrics.csv', 'losing_streak_stats.csv',
        'drawdown_periods.csv', 'concurrent_positions_stats.csv', 'period_alpha.csv',
        'holding_period_curve.csv', 'mfe_timing.csv',
        'sector_concentration_stats.csv', 'cost_breakdown.csv',
    ]
    for fname in expected:
        assert (fake_project / 'reports' / fname).exists(), f"missing: {fname}"
    # 中间数据
    assert (fake_project / 'results' / 'daily_position_pnl.csv').exists()
    assert (fake_project / 'results' / 'daily_portfolio_snapshot.csv').exists()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd my_strategy && python -m pytest tests/test_attribution_runner.py -v
```

- [ ] **Step 3: 写实现**

```python
# my_strategy/tools/attribution_runner.py
"""顶层编排：依次调用 rebuild_position_history → 旧 attribution → 3 个新模块。"""
from pathlib import Path

import pandas as pd

from my_strategy.tools import (
    attribution as old_attribution,
    rebuild_position_history,
    trade_attribution_extra,
    portfolio_attribution,
    position_curve_attribution,
)


# 默认信号白名单（Task 0 调研后可替换）
DEFAULT_SIGNALS_WHITELIST = [
    'entry_hs300_dif_above_zero', 'entry_hs300_bull_align',
    'entry_stock_bull_align', 'entry_stock_above_ma25',
    'entry_sector_bull_align', 'entry_sector_above_ma25',
    'entry_sector_dif_above_zero',
    'entry_sector_week_macd_zone', 'entry_sector_month_macd_zone',
    'entry_month_macd_zone', 'entry_week_macd_zone',
    'ma_alignment',
    'factor_momentum_60d', 'factor_ma60_dist',
]

DEFAULT_COMBOS = [
    ('entry_hs300_dif_above_zero', 'entry_sector_dif_above_zero', 'entry_stock_bull_align'),
    ('entry_sector_above_ma25', 'entry_stock_above_ma25', 'entry_month_macd_zone'),
    ('entry_hs300_bull_align', 'entry_sector_bull_align', 'entry_stock_bull_align'),
]


def run(
    project_root: Path,
    cfg: dict,
    daily_ret: pd.Series,
    position_count_log,
    benchmarks: dict,
) -> None:
    project_root = Path(project_root)
    out_dir = project_root / cfg['attribution_report_dir']

    # 1) 数据补齐
    rebuild_position_history.build(project_root, cfg)

    # 2) 旧归因（保持原行为）
    old_attribution.run(project_root, cfg)

    # 3) trade-level 扩展
    trades_path = project_root / cfg.get('results_dir', 'results/') / 'trade_summary.csv'
    trades = pd.read_csv(trades_path, parse_dates=['entry_date'])
    trade_attribution_extra.run(
        trades, out_dir, DEFAULT_SIGNALS_WHITELIST, DEFAULT_COMBOS
    )

    # 4) portfolio-level
    portfolio_attribution.run(
        daily_ret, position_count_log, benchmarks, trades, cfg, out_dir
    )

    # 5) position-curve
    position_curve_attribution.run(project_root, cfg)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd my_strategy && python -m pytest tests/test_attribution_runner.py -v
```
Expected: 1 passed。

- [ ] **Step 5: 运行全量测试确认无回归**

```bash
cd my_strategy && python -m pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add my_strategy/tools/attribution_runner.py my_strategy/tests/test_attribution_runner.py
git commit -m "feat(stats): add attribution_runner orchestrator"
```

---

## Task 17: 接入 `backtest.py`、跑端到端、更新文档

**Files:**
- Modify: `my_strategy/backtest.py`（约 `:975-978` 区域）
- Modify: `docs/FEATURES.md`
- Modify: `docs/CHANGELOG.md`

- [ ] **Step 1: 阅读 backtest.py 现有调用并定位修改点**

```bash
grep -n "attribution\.run\|_TimeReturn\|position_count_log\|benchmark_codes\|run_index_strategy" my_strategy/backtest.py
```
确认：
- `attribution.run(project_root, cfg)` 的调用位置
- `time_return = pd.Series(r.analyzers._TimeReturn.get_analysis())` 计算位置（约 `:833`）
- `position_count_log` 的访问方式（约 `:828`）
- benchmark 数据如何加载

- [ ] **Step 2: 修改 backtest.py 入口调用**

把现有 `from tools import attribution; attribution.run(project_root, cfg)` 改成调 `attribution_runner.run`，并把 `time_return`、`position_count_log`、`benchmarks` 传进去。

具体改动：
1. 把 `time_return = pd.Series(...)` 计算上移到 `attribution.run` 调用之前
2. 把 `attribution.run` 的调用替换为：

```python
from tools import attribution_runner

# 加载 benchmark daily returns
benchmarks = {}
for code in cfg.get('benchmark_codes', []):
    bench_path = project_root / 'data' / 'index' / f"{code}_daily.csv"
    if not bench_path.exists():
        # 严格模式：抛错而非跳过
        raise FileNotFoundError(
            f"benchmark daily file missing: {bench_path}. "
            f"Either remove {code} from cfg.benchmark_codes or download the data first."
        )
    df = pd.read_csv(bench_path, parse_dates=['date']).set_index('date').sort_index()
    benchmarks[code] = df['close'].pct_change().dropna()

attribution_runner.run(
    project_root=project_root,
    cfg=cfg,
    daily_ret=time_return,
    position_count_log=getattr(r, 'position_count_log', None),
    benchmarks=benchmarks,
)
```

> **注意**：执行此步前请阅读 backtest.py 实际代码，确认 benchmark 文件的真实路径格式（Task 0 已调研过 daily 文件结构）。如路径与上面不一致，按真实路径改写。

- [ ] **Step 3: 跑一次完整回测，验证 14 个新报告 + 2 个中间文件均产出**

```bash
cd my_strategy && python backtest.py 2>&1 | tail -40
```
Expected: 无异常退出。

```bash
ls my_strategy/results/daily_position_pnl.csv my_strategy/results/daily_portfolio_snapshot.csv
ls my_strategy/reports/payoff_metrics.csv my_strategy/reports/signal_stability.csv my_strategy/reports/signal_correlation_matrix.csv my_strategy/reports/multi_factor_combo_stats.csv my_strategy/reports/significance_summary.csv my_strategy/reports/portfolio_risk_metrics.csv my_strategy/reports/losing_streak_stats.csv my_strategy/reports/drawdown_periods.csv my_strategy/reports/concurrent_positions_stats.csv my_strategy/reports/period_alpha.csv my_strategy/reports/holding_period_curve.csv my_strategy/reports/mfe_timing.csv my_strategy/reports/sector_concentration_stats.csv my_strategy/reports/cost_breakdown.csv
```
Expected: 全部存在。

- [ ] **Step 4: 抽查 3 个关键报告的内容合理性**

```bash
head -5 my_strategy/reports/portfolio_risk_metrics.csv
head -5 my_strategy/reports/significance_summary.csv
head -5 my_strategy/reports/payoff_metrics.csv
```
检查：
- portfolio_risk_metrics overall 行的 sharpe/max_drawdown 数量级合理（max_drawdown 应是负数；sharpe 通常 -2 ~ 3）
- significance_summary 包含多个 report_name 的行
- payoff_metrics overall 行的 payoff_ratio 应 > 0

- [ ] **Step 5: 跑全量测试确认无回归**

```bash
cd my_strategy && python -m pytest -q
```

- [ ] **Step 6: 更新 docs/FEATURES.md 和 docs/CHANGELOG.md**

按 CLAUDE.md 要求：
- `docs/FEATURES.md`：新增/更新"Phase A 统计分析框架"章节，列出 14 个新报告 + 2 个中间数据文件 + 6 个新模块。
- `docs/CHANGELOG.md` **顶部**追加：

```markdown
## 2026-05-08 — Phase A 统计分析框架（13 项 / 14 张报告）
- 需求：进入 Phase B 自动调参前补齐统计盲区（风险调整收益、显著性、组合层、时间稳定性、持仓期曲线等）
- 改动：
  - 新增 6 模块：`tools/{stats_helpers, trade_attribution_extra, portfolio_attribution, position_curve_attribution, rebuild_position_history, attribution_runner}.py`
  - 新增 14 张报告 CSV（reports/）+ 2 个中间数据文件（results/daily_position_pnl.csv, daily_portfolio_snapshot.csv）
  - `backtest.py` 入口由调 `attribution.run` 改为 `attribution_runner.run`，新增 benchmark 日数据加载
- 影响：现有 28 张归因报告 schema 不变；`tools/attribution.py` 不变
```

- [ ] **Step 7: Commit**

```bash
git add my_strategy/backtest.py docs/FEATURES.md docs/CHANGELOG.md
git commit -m "feat(stats): integrate attribution_runner into backtest.py + docs"
```

---

## Self-Review Checklist（生成后已执行）

**1. Spec 覆盖**：spec §3 的 13 个报告 + §4 两个中间文件 + §5 六个模块 + §6 错误处理（"严格抛错不降级"原则在 Task 2 / Task 17 都有体现）—— 全部映射到具体任务。spec §7 4 个开放问题 → Task 0 调研。

**2. Placeholder 扫描**：无 TBD/TODO；每步代码块完整；测试代码均含具体断言；命令均含 expected。

**3. Type 一致性**：
- `compute_*` 函数签名一致（输入 DataFrame / Series，输出 DataFrame）
- `run(...)` 模块入口签名在 attribution_runner 中调用时与各模块定义一致
- `daily_ret` / `time_return` 命名在 backtest.py 接入处统一为 `daily_ret`（变量层面，参数名一致）
- `position_count_log` 类型在 task 10 测试和 task 16 fixture 都使用 DataFrame[date, count]，与 task 0 调研结论需要对齐 —— 这是 task 10 / task 16 实施前的硬依赖
