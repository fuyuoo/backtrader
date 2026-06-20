# Phase B-prep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让现有 42 张报告 + 2 个中间数据真实可信地反映策略实际表现，让用户在调参（Phase B）前对策略本身有信心。

**Architecture:** 分 3 层（数据层 / 策略层 / 报告层）共 9 个任务。第 0 任务补 stock_list 元数据；第 1 任务建独立数据健康自检模块；第 2/3 任务分别在 strategy 和 backtest 主循环里加 A 股操作过滤；第 4 任务清理财务因子并修 cost_breakdown bug；第 5 任务给 trade_summary 增 4 列（mfe_minus_realized / exit_efficiency / benchmark_return / per_trade_alpha）+ forward_return；第 6/7/8 任务新建 3 张报告（信号重要性排名 + 全量 IC、滚动绩效、失败归因）。

**Tech Stack:** pandas、numpy、scipy.stats、pytest、tushare（仅 Task 0 用一次 stock_basic）

**Spec:** `docs/superpowers/specs/2026-05-08-phase-b-prep-design.md`

---

## Task 0: 补齐 stock_list 元数据（list_date / delist_date / industry）

**目的**：现有 `my_strategy/stock_list.csv` 只有 `ts_code` 一列；Task 3 PIT universe 集成必须依赖 `list_date`。本任务通过 Tushare `pro.stock_basic` 拉一次全量元数据，与现有股票池 join。**幂等**：若已有 list_date 列则跳过下载（避免重复消耗 Tushare 配额）。

**Files:**
- Create: `my_strategy/tools/ensure_stock_list_metadata.py`
- Test: `my_strategy/tests/test_ensure_stock_list_metadata.py`
- Modify: `my_strategy/stock_list.csv`（执行后）

- [ ] **Step 1: 调研当前 `stock_list.csv` 状态**

```bash
head -1 my_strategy/stock_list.csv
wc -l my_strategy/stock_list.csv
```
预期：仅 `ts_code` 一列；行数 ≈ 800。记录该信息，确认下游 join 逻辑是否处理只有 ts_code 的情况。

- [ ] **Step 2: 调研 Tushare token 加载方式**

```bash
ls my_strategy/data/tushare_token.json 2>&1
grep -n "tushare_token\|pro_api\|get_token\|set_token" my_strategy/src/downloader.py | head -10
```
预期：存在 token json，downloader.py 已实现 token 加载函数（复用即可）。记录 token 路径与加载函数名。

- [ ] **Step 3: 写失败的测试**

```python
# my_strategy/tests/test_ensure_stock_list_metadata.py
import pandas as pd
import pytest
from pathlib import Path
from my_strategy.tools.ensure_stock_list_metadata import (
    has_required_columns,
    merge_metadata,
)


def test_has_required_columns_detects_missing():
    df_bare = pd.DataFrame({'ts_code': ['000001.SZ', '000002.SZ']})
    assert has_required_columns(df_bare) is False
    df_full = pd.DataFrame({
        'ts_code': ['000001.SZ'],
        'list_date': ['19910403'],
        'delist_date': [pd.NA],
        'industry': ['银行'],
    })
    assert has_required_columns(df_full) is True


def test_has_required_columns_partial_missing():
    df = pd.DataFrame({'ts_code': ['000001.SZ'], 'industry': ['银行']})
    assert has_required_columns(df) is False  # missing list_date / delist_date


def test_merge_metadata_left_join_preserves_universe():
    existing = pd.DataFrame({'ts_code': ['000001.SZ', '000002.SZ', '999999.SZ']})
    metadata = pd.DataFrame({
        'ts_code': ['000001.SZ', '000002.SZ', '888888.SH'],
        'list_date': ['19910403', '19910129', '20100101'],
        'delist_date': [pd.NA, pd.NA, pd.NA],
        'industry': ['银行', '地产', '科技'],
    })
    out = merge_metadata(existing, metadata)
    assert set(out['ts_code']) == {'000001.SZ', '000002.SZ', '999999.SZ'}
    assert out.loc[out['ts_code'] == '000001.SZ', 'list_date'].iloc[0] == '19910403'
    # 999999.SZ in existing but not in metadata → list_date should be NaN, not dropped
    assert pd.isna(out.loc[out['ts_code'] == '999999.SZ', 'list_date'].iloc[0])
    # 888888.SH only in metadata → must NOT appear (preserve existing universe)
    assert '888888.SH' not in out['ts_code'].values
```

- [ ] **Step 4: 运行测试确认失败**

```bash
python -m pytest my_strategy/tests/test_ensure_stock_list_metadata.py -v
```
Expected: ImportError 或 FAIL.

- [ ] **Step 5: 写最小实现**

```python
# my_strategy/tools/ensure_stock_list_metadata.py
"""幂等地确保 stock_list.csv 含 list_date / delist_date / industry 三列。

用法：
    python -m my_strategy.tools.ensure_stock_list_metadata

- 若三列俱全则不调用 Tushare API，仅打印一行说明
- 否则调用 pro.stock_basic(list_status='L,D,P') 拉取一次完整元数据
- 与现有 stock_list.csv 做 left join（保留现有 universe）
- 写回 stock_list.csv（原地覆盖；行内备份为 stock_list.csv.bak）
"""
import json
import shutil
from pathlib import Path

import pandas as pd

REQUIRED_COLS = ('list_date', 'delist_date', 'industry')


def has_required_columns(df: pd.DataFrame) -> bool:
    return all(c in df.columns for c in REQUIRED_COLS)


def merge_metadata(existing: pd.DataFrame, metadata: pd.DataFrame) -> pd.DataFrame:
    """Left-join existing on metadata. Existing universe 不变。"""
    cols_to_take = ['ts_code', 'list_date', 'delist_date', 'industry']
    sub = metadata[[c for c in cols_to_take if c in metadata.columns]]
    return existing.merge(sub, on='ts_code', how='left', suffixes=('', '_meta'))


def fetch_stock_basic_via_tushare(token_path: Path) -> pd.DataFrame:
    """调用 pro.stock_basic 拉取 list_status='L,D,P' 全量元数据。"""
    import tushare as ts
    with open(token_path, 'r') as f:
        token = json.load(f)['token']
    ts.set_token(token)
    pro = ts.pro_api()
    parts = []
    for status in ('L', 'D', 'P'):
        df = pro.stock_basic(
            list_status=status,
            fields='ts_code,name,industry,list_date,delist_date',
        )
        parts.append(df)
    return pd.concat(parts, ignore_index=True)


def main(project_root: Path = None) -> None:
    project_root = project_root or Path(__file__).resolve().parent.parent
    list_path = project_root / 'stock_list.csv'
    token_path = project_root / 'data' / 'tushare_token.json'

    existing = pd.read_csv(list_path)
    if has_required_columns(existing):
        print(f"[ensure_stock_list_metadata] {list_path} 已含 list_date/delist_date/industry，跳过。")
        return

    print(f"[ensure_stock_list_metadata] 缺少元数据列，调用 Tushare pro.stock_basic ...")
    metadata = fetch_stock_basic_via_tushare(token_path)
    merged = merge_metadata(existing, metadata)

    # 备份原文件
    backup = list_path.with_suffix('.csv.bak')
    shutil.copy(list_path, backup)
    merged.to_csv(list_path, index=False)
    n_with = merged['list_date'].notna().sum()
    n_total = len(merged)
    print(f"[ensure_stock_list_metadata] 写回 {list_path}（备份 {backup}）；"
          f"{n_with}/{n_total} 行成功匹配 list_date。")


if __name__ == '__main__':
    main()
```

- [ ] **Step 6: 运行测试确认通过**

```bash
python -m pytest my_strategy/tests/test_ensure_stock_list_metadata.py -v
```
Expected: 3 passed。

- [ ] **Step 7: 真实运行一次（联网调 Tushare）**

```bash
python -m my_strategy.tools.ensure_stock_list_metadata
```
Expected: 输出形如 `795/803 行成功匹配 list_date`。少数 ts_code 可能在 Tushare 当前快照里不存在（如已退市超 N 年），那些行 list_date 为 NaN —— 这是预期，Task 3 会特殊处理。

- [ ] **Step 8: 验证产物**

```bash
head -3 my_strategy/stock_list.csv
python -c "import pandas as pd; df = pd.read_csv('my_strategy/stock_list.csv'); print('cols:', list(df.columns)); print('list_date 非空:', df['list_date'].notna().sum(), '/', len(df))"
```
Expected: 列含 `ts_code, list_date, delist_date, industry`；多数行 list_date 非空。

- [ ] **Step 9: Commit**

```bash
git add my_strategy/tools/ensure_stock_list_metadata.py my_strategy/tests/test_ensure_stock_list_metadata.py my_strategy/stock_list.csv
git commit -m "feat(phase-b-prep): backfill stock_list with list_date/delist_date/industry via Tushare"
```

---

## Task 1: `tools/data_integrity_check.py` — 数据健康自检模块

**目的**：扫描 `data/daily/*.csv` + `stock_list.csv`，输出问题清单到 `results/integrity_report.csv`。**不修复数据本身**。一次性运行，不进入 backtest 主循环。

**Files:**
- Create: `my_strategy/tools/data_integrity_check.py`
- Test: `my_strategy/tests/test_data_integrity_check.py`

- [ ] **Step 1: 写失败的测试**

```python
# my_strategy/tests/test_data_integrity_check.py
import numpy as np
import pandas as pd
import pytest
from pathlib import Path
from my_strategy.tools.data_integrity_check import (
    check_missing_trading_days,
    check_duplicate_dates,
    check_non_monotonic,
    check_abnormal_close_jump,
    check_qfq_break,
    check_suspended_period,
    check_universe_consistency,
    run as integrity_run,
)


def _df(dates, closes):
    return pd.DataFrame({'trade_date': pd.to_datetime(dates), 'close': closes})


def test_check_missing_trading_days_finds_gap():
    benchmark = _df(['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05'], [1, 1, 1, 1])
    stock = _df(['2024-01-02', '2024-01-04', '2024-01-05'], [10, 11, 12])  # 缺 1-03
    issues = check_missing_trading_days('000001.SZ', stock, benchmark)
    assert len(issues) == 1
    assert issues[0]['issue_type'] == 'missing_trading_day'
    assert '2024-01-03' in issues[0]['date_or_range']


def test_check_duplicate_dates_finds_dup():
    df = _df(['2024-01-02', '2024-01-03', '2024-01-03'], [10, 11, 11.5])
    issues = check_duplicate_dates('000001.SZ', df)
    assert len(issues) == 1
    assert issues[0]['issue_type'] == 'duplicate_date'


def test_check_non_monotonic_finds_disorder():
    df = _df(['2024-01-02', '2024-01-04', '2024-01-03'], [10, 11, 12])
    issues = check_non_monotonic('000001.SZ', df)
    assert len(issues) == 1
    assert issues[0]['issue_type'] == 'non_monotonic_date'


def test_check_abnormal_close_jump_flags_30pct():
    df = _df(
        ['2024-01-02', '2024-01-03', '2024-01-04'],
        [10.0, 13.5, 13.5],  # +35% one-day jump (前复权下不应出现)
    )
    issues = check_abnormal_close_jump('000001.SZ', df, threshold_pct=25)
    assert any(i['issue_type'] == 'abnormal_close_jump' for i in issues)


def test_check_qfq_break_finds_zero_close():
    df = _df(['2024-01-02', '2024-01-03'], [10.0, 0.0])
    issues = check_qfq_break('000001.SZ', df)
    assert len(issues) == 1
    assert issues[0]['issue_type'] == 'qfq_break'


def test_check_suspended_period_finds_5day_flat():
    df = pd.DataFrame({
        'trade_date': pd.to_datetime(['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05', '2024-01-08', '2024-01-09']),
        'open':  [10.0, 10.0, 10.0, 10.0, 10.0, 11.0],
        'high':  [10.0, 10.0, 10.0, 10.0, 10.0, 11.0],
        'low':   [10.0, 10.0, 10.0, 10.0, 10.0, 11.0],
        'close': [10.0, 10.0, 10.0, 10.0, 10.0, 11.0],
        'volume': [0, 0, 0, 0, 0, 1000],
    })
    issues = check_suspended_period('000001.SZ', df, min_days=5)
    assert any(i['issue_type'] == 'suspended_period' for i in issues)


def test_check_universe_consistency_detects_orphan_files(tmp_path):
    # daily/ 下有 999999.SZ.csv 但 stock_list 里没有
    (tmp_path / 'daily').mkdir()
    (tmp_path / 'daily' / '000001.SZ.csv').touch()
    (tmp_path / 'daily' / '999999.SZ.csv').touch()
    stock_list = pd.DataFrame({'ts_code': ['000001.SZ', '000002.SZ']})
    issues = check_universe_consistency(tmp_path / 'daily', stock_list)
    types = {i['issue_type'] for i in issues}
    assert 'not_in_stock_list' in types  # 999999.SZ orphan
    assert 'in_list_no_data' in types     # 000002.SZ missing


def test_integrity_run_writes_report(tmp_path):
    """端到端：构造最小 fixture，跑 run() 应产出 integrity_report.csv。"""
    (tmp_path / 'data' / 'daily').mkdir(parents=True)
    (tmp_path / 'results').mkdir()
    # 健康样本
    healthy = _df(pd.date_range('2024-01-02', periods=20, freq='B'), list(range(10, 30)))
    healthy.to_csv(tmp_path / 'data' / 'daily' / '000300.SH.csv', index=False)
    healthy.to_csv(tmp_path / 'data' / 'daily' / '000001.SZ.csv', index=False)
    pd.DataFrame({'ts_code': ['000300.SH', '000001.SZ']}).to_csv(tmp_path / 'stock_list.csv', index=False)
    cfg = {'data_dir': 'data/', 'results_dir': 'results/'}
    integrity_run(tmp_path, cfg)
    out = pd.read_csv(tmp_path / 'results' / 'integrity_report.csv')
    assert {'ts_code', 'issue_type', 'severity', 'date_or_range', 'detail'}.issubset(out.columns)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest my_strategy/tests/test_data_integrity_check.py -v
```
Expected: ImportError.

- [ ] **Step 3: 写最小实现**

```python
# my_strategy/tools/data_integrity_check.py
"""数据健康自检模块。

扫描 data/daily/*.csv + stock_list.csv，输出问题清单到 results/integrity_report.csv。
不修复数据本身；只暴露问题让用户决策。

用法（从项目根）：
    python -m my_strategy.tools.data_integrity_check

或在脚本里：
    from my_strategy.tools.data_integrity_check import run
    run(project_root, cfg)
"""
from pathlib import Path
from typing import List, Dict

import numpy as np
import pandas as pd

BENCHMARK_TS_CODE = '000300.SH'
ABNORMAL_JUMP_THRESHOLD_PCT = 25.0
SUSPEND_MIN_DAYS = 5


def _row(ts_code: str, issue_type: str, severity: str,
         date_or_range: str, detail: str) -> Dict:
    return {
        'ts_code': ts_code,
        'issue_type': issue_type,
        'severity': severity,
        'date_or_range': date_or_range,
        'detail': detail,
    }


def check_missing_trading_days(
    ts_code: str, stock_df: pd.DataFrame, benchmark_df: pd.DataFrame,
) -> List[Dict]:
    bench_dates = set(pd.to_datetime(benchmark_df['trade_date']))
    stock_dates = set(pd.to_datetime(stock_df['trade_date']))
    # 只看 stock 数据范围内的缺日（避免历史上未上市误报）
    if not stock_dates:
        return []
    smin, smax = min(stock_dates), max(stock_dates)
    bench_in_range = {d for d in bench_dates if smin <= d <= smax}
    missing = sorted(bench_in_range - stock_dates)
    if not missing:
        return []
    if len(missing) <= 5:
        date_str = ', '.join(d.strftime('%Y-%m-%d') for d in missing)
    else:
        date_str = f"{missing[0].date()}..{missing[-1].date()} ({len(missing)} 天)"
    return [_row(ts_code, 'missing_trading_day', 'warning', date_str,
                 f"benchmark 当日交易，本股缺数据；缺 {len(missing)} 天")]


def check_duplicate_dates(ts_code: str, df: pd.DataFrame) -> List[Dict]:
    dates = pd.to_datetime(df['trade_date'])
    dup_mask = dates.duplicated(keep=False)
    if not dup_mask.any():
        return []
    dups = sorted(set(dates[dup_mask]))
    return [_row(ts_code, 'duplicate_date', 'error',
                 ', '.join(d.strftime('%Y-%m-%d') for d in dups),
                 f"{len(dups)} 个日期出现多行")]


def check_non_monotonic(ts_code: str, df: pd.DataFrame) -> List[Dict]:
    dates = pd.to_datetime(df['trade_date'])
    if dates.is_monotonic_increasing:
        return []
    diffs = dates.diff()
    bad_idx = diffs[diffs < pd.Timedelta(0)].index
    bad_dates = dates.loc[bad_idx]
    return [_row(ts_code, 'non_monotonic_date', 'error',
                 ', '.join(d.strftime('%Y-%m-%d') for d in bad_dates[:5]),
                 f"{len(bad_idx)} 处日期回退")]


def check_abnormal_close_jump(
    ts_code: str, df: pd.DataFrame, threshold_pct: float = ABNORMAL_JUMP_THRESHOLD_PCT,
) -> List[Dict]:
    if 'close' not in df.columns or len(df) < 2:
        return []
    close = df['close'].astype(float).values
    pct_chg = np.diff(close) / close[:-1] * 100.0
    bad_idx = np.where(np.abs(pct_chg) > threshold_pct)[0] + 1
    if len(bad_idx) == 0:
        return []
    dates = pd.to_datetime(df['trade_date']).values
    issues = []
    for i in bad_idx[:5]:
        issues.append(_row(
            ts_code, 'abnormal_close_jump', 'warning',
            pd.Timestamp(dates[i]).strftime('%Y-%m-%d'),
            f"单日 close 变化 {pct_chg[i-1]:+.2f}%（阈值 ±{threshold_pct}%）",
        ))
    if len(bad_idx) > 5:
        issues.append(_row(ts_code, 'abnormal_close_jump', 'warning',
                           f"共 {len(bad_idx)} 处", "已截断显示前 5 处"))
    return issues


def check_qfq_break(ts_code: str, df: pd.DataFrame) -> List[Dict]:
    if 'close' not in df.columns:
        return []
    close = df['close'].astype(float)
    bad_mask = close.isna() | (close == 0)
    if not bad_mask.any():
        return []
    dates = pd.to_datetime(df['trade_date'])
    bad_dates = dates[bad_mask]
    return [_row(ts_code, 'qfq_break', 'warning',
                 ', '.join(d.strftime('%Y-%m-%d') for d in bad_dates[:5]),
                 f"{int(bad_mask.sum())} 处 close=0 或 NaN（前复权数据应非零）")]


def check_suspended_period(
    ts_code: str, df: pd.DataFrame, min_days: int = SUSPEND_MIN_DAYS,
) -> List[Dict]:
    if not all(c in df.columns for c in ('open', 'high', 'low', 'close')):
        return []
    flat = (df['open'] == df['high']) & (df['high'] == df['low']) & (df['low'] == df['close'])
    if 'volume' in df.columns:
        flat = flat & (df['volume'] == 0)
    if not flat.any():
        return []
    dates = pd.to_datetime(df['trade_date']).reset_index(drop=True)
    flat = flat.reset_index(drop=True)
    issues, run_start = [], None
    for i, is_flat in enumerate(flat):
        if is_flat and run_start is None:
            run_start = i
        elif not is_flat and run_start is not None:
            run_len = i - run_start
            if run_len >= min_days:
                issues.append(_row(
                    ts_code, 'suspended_period', 'info',
                    f"{dates.iloc[run_start].date()}..{dates.iloc[i-1].date()}",
                    f"{run_len} 个 bar OHLCV 全相同（疑似停牌）",
                ))
            run_start = None
    if run_start is not None and len(flat) - run_start >= min_days:
        run_len = len(flat) - run_start
        issues.append(_row(
            ts_code, 'suspended_period', 'info',
            f"{dates.iloc[run_start].date()}..{dates.iloc[-1].date()}",
            f"{run_len} 个 bar OHLCV 全相同（疑似停牌，至文件末）",
        ))
    return issues


def check_universe_consistency(daily_dir: Path, stock_list: pd.DataFrame) -> List[Dict]:
    """检查 daily/ 文件 vs stock_list.csv 的不一致。"""
    daily_dir = Path(daily_dir)
    daily_codes = {p.stem for p in daily_dir.glob('*.csv')}
    list_codes = set(stock_list['ts_code'])
    issues = []
    for orphan in sorted(daily_codes - list_codes):
        issues.append(_row(orphan, 'not_in_stock_list', 'warning', '',
                           'daily/ 下有该股票文件但 stock_list.csv 不含'))
    for missing in sorted(list_codes - daily_codes):
        issues.append(_row(missing, 'in_list_no_data', 'warning', '',
                           'stock_list.csv 含该股票但 daily/ 下无文件'))
    return issues


def check_list_date_consistency(ts_code: str, df: pd.DataFrame, list_date_str) -> List[Dict]:
    """daily 第一个 bar 应不早于 list_date。"""
    if pd.isna(list_date_str) or df.empty:
        return []
    list_date = pd.to_datetime(str(list_date_str), format='%Y%m%d', errors='coerce')
    if pd.isna(list_date):
        return []
    first_bar = pd.to_datetime(df['trade_date']).min()
    if first_bar < list_date:
        return [_row(ts_code, 'list_date_mismatch', 'warning',
                     first_bar.strftime('%Y-%m-%d'),
                     f"daily 第一个 bar 早于 list_date={list_date.date()}")]
    return []


def run(project_root: Path, cfg: dict) -> None:
    """主入口：扫描全部数据并写出 integrity_report.csv。"""
    project_root = Path(project_root)
    data_dir = project_root / cfg.get('data_dir', 'data/')
    daily_dir = data_dir / 'daily'
    results_dir = project_root / cfg.get('results_dir', 'results/')
    list_path = project_root / 'stock_list.csv'

    if not daily_dir.exists():
        raise FileNotFoundError(f"daily 数据目录不存在: {daily_dir}")
    if not list_path.exists():
        raise FileNotFoundError(f"stock_list.csv 不存在: {list_path}")

    stock_list = pd.read_csv(list_path)
    bench_path = daily_dir / f"{BENCHMARK_TS_CODE}.csv"
    if not bench_path.exists():
        raise FileNotFoundError(f"benchmark daily 数据缺失: {bench_path}")
    benchmark_df = pd.read_csv(bench_path)

    all_issues: List[Dict] = []
    all_issues.extend(check_universe_consistency(daily_dir, stock_list))

    list_date_lookup = {}
    if 'list_date' in stock_list.columns:
        list_date_lookup = dict(zip(stock_list['ts_code'], stock_list['list_date']))

    for csv_path in sorted(daily_dir.glob('*.csv')):
        ts_code = csv_path.stem
        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            all_issues.append(_row(ts_code, 'read_error', 'error', '', str(e)))
            continue
        if df.empty:
            all_issues.append(_row(ts_code, 'empty_file', 'warning', '', '文件为空'))
            continue
        all_issues.extend(check_missing_trading_days(ts_code, df, benchmark_df))
        all_issues.extend(check_duplicate_dates(ts_code, df))
        all_issues.extend(check_non_monotonic(ts_code, df))
        all_issues.extend(check_abnormal_close_jump(ts_code, df))
        all_issues.extend(check_qfq_break(ts_code, df))
        all_issues.extend(check_suspended_period(ts_code, df))
        all_issues.extend(check_list_date_consistency(
            ts_code, df, list_date_lookup.get(ts_code, pd.NA)))

    out_df = pd.DataFrame(all_issues, columns=['ts_code', 'issue_type', 'severity',
                                                 'date_or_range', 'detail'])
    out_path = results_dir / 'integrity_report.csv'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False)

    n_error = (out_df['severity'] == 'error').sum() if not out_df.empty else 0
    n_warn = (out_df['severity'] == 'warning').sum() if not out_df.empty else 0
    n_info = (out_df['severity'] == 'info').sum() if not out_df.empty else 0
    print(f"[data_integrity_check] {len(out_df)} 条问题写入 {out_path}")
    print(f"  error={n_error}, warning={n_warn}, info={n_info}")


if __name__ == '__main__':
    import json
    root = Path(__file__).resolve().parent.parent.parent
    with open(root / 'my_strategy' / 'config.json', 'r') as f:
        cfg = json.load(f)
    run(root / 'my_strategy', cfg)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest my_strategy/tests/test_data_integrity_check.py -v
```
Expected: 8 passed.

- [ ] **Step 5: 真实数据上跑一次（生成首个 integrity_report.csv）**

```bash
cd /e/GithubCloneSpace/Stock/backtrader/backtrader && python -m my_strategy.tools.data_integrity_check
```
Expected: 输出形如 `N 条问题写入 .../integrity_report.csv`。N 不为零是正常（25 年数据必有一些缺日 / 停牌 / orphan）。

- [ ] **Step 6: 抽查 integrity_report.csv 内容**

```bash
head -5 my_strategy/results/integrity_report.csv
python -c "import pandas as pd; d=pd.read_csv('my_strategy/results/integrity_report.csv'); print(d['issue_type'].value_counts())"
```
预期：能看到 `missing_trading_day` / `suspended_period` 等类型。

- [ ] **Step 7: 全量回归**

```bash
python -m pytest -q my_strategy/tests
```
Expected: 全 pass（148 + 8 = 156 左右）。

- [ ] **Step 8: 更新 docs/FEATURES.md 与 docs/CHANGELOG.md**

`docs/FEATURES.md` 在 `tools/` 目录树中加：
```
│   ├── data_integrity_check.py        # 数据健康自检（一次性，输出 integrity_report.csv）
```

新增章节 §14（数据健康自检）：列出 8 个 issue_type、调用方式、严重等级含义。

`docs/CHANGELOG.md` 顶部追加 Phase B-prep Task 1 条目。

- [ ] **Step 9: Commit**

```bash
git add my_strategy/tools/data_integrity_check.py my_strategy/tests/test_data_integrity_check.py docs/FEATURES.md docs/CHANGELOG.md
git commit -m "feat(phase-b-prep): add data_integrity_check module"
```

注意：**不要**把生成的 `my_strategy/results/integrity_report.csv` 提交（results 目录已在 .gitignore，但部分文件可能例外）。运行 `git status` 确认。

---

## Task 2: 涨跌停过滤（修改 `src/strategy.py`）

**目的**：A 股每日涨跌停 ±10%；当前 backtest 在涨停日 fire 买入信号会"虚假成交"。在策略下单决策处加过滤；被过滤的信号写入 `signals_log.csv` 的 `skip_reason`。

**Files:**
- Modify: `my_strategy/src/strategy.py`
- Test: `my_strategy/tests/test_strategy_limit_filter.py`

- [ ] **Step 1: 调研当前 strategy.py 结构**

```bash
grep -n "def next\|def _is\|def _try\|signals_log\|skip_reason\|self\.buy\|self\.order_target" my_strategy/src/strategy.py | head -30
```
记录：买入下单位置、signals_log 写入位置、当前是否已有 _is_* 私有判断函数。

- [ ] **Step 2: 写失败的测试**

```python
# my_strategy/tests/test_strategy_limit_filter.py
"""涨跌停过滤逻辑单元测试。
直接测试 _is_limit_up / _is_limit_down 静态逻辑，不启动完整 cerebro。
"""
import pytest
from unittest.mock import MagicMock
from my_strategy.src.strategy import MyStrategy


def _mock_data(closes):
    """构造一个 mock data feed，data.close[0] 取最后一个，data.close[-1] 取倒数第二个。"""
    data = MagicMock()
    data.__len__.return_value = len(closes)
    data.close.__getitem__.side_effect = lambda i: closes[i - 1] if i <= 0 else None
    return data


def test_is_limit_up_detects_995pct():
    data = _mock_data([10.0, 11.0])  # +10%
    assert MyStrategy._is_limit_up(None, data) is True


def test_is_limit_up_misses_98pct():
    data = _mock_data([10.0, 10.95])  # +9.5%
    assert MyStrategy._is_limit_up(None, data) is False


def test_is_limit_down_detects_negative_995pct():
    data = _mock_data([10.0, 9.0])  # -10%
    assert MyStrategy._is_limit_down(None, data) is True


def test_is_limit_down_misses_negative_98pct():
    data = _mock_data([10.0, 9.05])  # -9.5%
    assert MyStrategy._is_limit_down(None, data) is False


def test_is_limit_handles_short_data():
    data = MagicMock()
    data.__len__.return_value = 0
    assert MyStrategy._is_limit_up(None, data) is False
    assert MyStrategy._is_limit_down(None, data) is False
```

- [ ] **Step 3: 运行测试确认失败**

```bash
python -m pytest my_strategy/tests/test_strategy_limit_filter.py -v
```
Expected: AttributeError 或 FAIL（_is_limit_up 不存在）。

- [ ] **Step 4: 在 strategy.py 加两个私有方法**

在 `MyStrategy` 类内加（位置：紧邻 `_current_position_count` 等其他 helper 之前）：

```python
    LIMIT_UP_THRESHOLD = 9.9   # +9.9% 起算涨停（A 股标准 ±10% 留 0.1% 容差）
    LIMIT_DOWN_THRESHOLD = -9.9  # -9.9% 起算跌停

    def _is_limit_up(self, data) -> bool:
        """当日 close 相对前一日已涨停（pct_chg ≥ +9.9%）。"""
        if len(data) < 2:
            return False
        prev_close = data.close[-1]
        cur_close = data.close[0]
        if prev_close is None or cur_close is None or prev_close <= 0:
            return False
        pct_chg = (cur_close - prev_close) / prev_close * 100.0
        return pct_chg >= self.LIMIT_UP_THRESHOLD

    def _is_limit_down(self, data) -> bool:
        """当日 close 相对前一日已跌停（pct_chg ≤ -9.9%）。"""
        if len(data) < 2:
            return False
        prev_close = data.close[-1]
        cur_close = data.close[0]
        if prev_close is None or cur_close is None or prev_close <= 0:
            return False
        pct_chg = (cur_close - prev_close) / prev_close * 100.0
        return pct_chg <= self.LIMIT_DOWN_THRESHOLD
```

- [ ] **Step 5: 运行单元测试确认通过**

```bash
python -m pytest my_strategy/tests/test_strategy_limit_filter.py -v
```
Expected: 5 passed.

- [ ] **Step 6: 在 next() 下单逻辑里应用过滤**

定位 `MyStrategy.next()` 中执行 `self.buy(data=...)` / `self.sell(data=...)` 的所有位置（Step 1 已记录）。

**对每个买入/加仓点**：在 `self.buy(...)` 之前加判断：
```python
if self._is_limit_up(data):
    # 涨停日不开仓 / 不加仓
    self._log_skipped_signal(data, reason='limit_up')
    continue  # 或 return，按当前控制流
# ... 原有 self.buy(...) 调用保留
```

**对每个清仓/止损点**：在 `self.sell(...)` 或 `self.close(...)` 之前加判断：
```python
if self._is_limit_down(data):
    # 跌停日不卖出（无成交对手）
    self._log_skipped_signal(data, reason='limit_down')
    continue  # 顺延到下一日
# ... 原有 self.sell(...) / self.close(...) 调用保留
```

**写入 signals_log 的辅助方法**（如不存在则加）：
```python
    def _log_skipped_signal(self, data, reason: str):
        """记录被涨跌停过滤的信号到 self.skipped_log（runtime list）。"""
        if not hasattr(self, 'skipped_log'):
            self.skipped_log = []
        self.skipped_log.append({
            'date': self.datas[0].datetime.date(0),
            'ts_code': data._name if hasattr(data, '_name') else str(data),
            'skip_reason': reason,
            'close': float(data.close[0]),
        })
```

并在 `__init__` 里加 `self.skipped_log = []`（如果还没有）。

- [ ] **Step 7: 在 backtest.py 写入 signals_log 的步骤里 merge skipped_log**

定位 backtest.py 中写 `signals_log.csv` 的代码段（`grep -n "signals_log" my_strategy/backtest.py`），在 trade_list 写完后追加：

```python
    # 写入被涨跌停过滤的信号（如有）
    skipped_log = getattr(r, 'skipped_log', [])
    if skipped_log:
        skipped_df = pd.DataFrame(skipped_log)
        skipped_path = project_root / cfg.get('results_dir', 'results/') / 'skipped_signals.csv'
        skipped_df.to_csv(skipped_path, index=False)
        print(f"[backtest] {len(skipped_df)} 条信号被涨跌停过滤，已写入 {skipped_path}")
```

- [ ] **Step 8: 跑端到端验证**

```bash
cd my_strategy && python backtest.py 2>&1 | tail -10
ls my_strategy/results/skipped_signals.csv
head -5 my_strategy/results/skipped_signals.csv
```
Expected: skipped_signals.csv 存在；列含 `date, ts_code, skip_reason, close`；至少有若干行（25 年数据中涨跌停频繁）。

- [ ] **Step 9: 全量回归**

```bash
python -m pytest -q my_strategy/tests
```
Expected: pass。

- [ ] **Step 10: 更新文档 + Commit**

`docs/FEATURES.md` §5.1 入场条件 / §5.2 出场条件加注：「涨跌停日不开仓 / 加仓；跌停日不卖出 → 写入 results/skipped_signals.csv」。

`docs/CHANGELOG.md` 顶部加 Task 2 条目。

```bash
git add my_strategy/src/strategy.py my_strategy/backtest.py my_strategy/tests/test_strategy_limit_filter.py docs/FEATURES.md docs/CHANGELOG.md
git commit -m "feat(phase-b-prep): A-share limit-up/down filter in strategy"
```

---

## Task 3: PIT universe 集成（修改 `backtest.py` 数据加载段）

**目的**：当前 backtest 把 stock_list.csv 当前快照里所有股票从 `cfg.start_date` 全量加载，等于"在 2010 年用未来才上市的股票"。改为按 `list_date / delist_date` 过滤每只股票的有效区间。

**Files:**
- Modify: `my_strategy/backtest.py`（数据加载循环段）
- Test: `my_strategy/tests/test_pit_universe.py`

- [ ] **Step 1: 调研当前数据加载循环**

```bash
grep -n "stock_list\|read_csv.*daily\|cerebro.adddata\|StockData\|fromdate\|todate" my_strategy/backtest.py | head -20
```
记录：循环位置、StockData feed 是否接受 `fromdate / todate` 参数。

- [ ] **Step 2: 写测试**

```python
# my_strategy/tests/test_pit_universe.py
"""PIT universe 过滤逻辑单元测试。

测试 _resolve_pit_window 函数：给定一只股票的 list_date / delist_date 与 backtest 的全局窗口，
返回该股的有效 (fromdate, todate) tuple。
"""
import pandas as pd
import pytest
from datetime import datetime
from my_strategy.backtest import _resolve_pit_window


def _d(s):
    return pd.to_datetime(s)


def test_pit_window_stock_predates_backtest():
    """股票早就上市 → 用 backtest 全窗口。"""
    fromdate, todate = _resolve_pit_window(
        list_date='19910403', delist_date=pd.NA,
        bt_start=_d('2010-01-01'), bt_end=_d('2025-12-31'),
    )
    assert fromdate == _d('2010-01-01')
    assert todate == _d('2025-12-31')


def test_pit_window_stock_lists_during_backtest():
    """股票在 backtest 窗口内才上市 → 用上市日做起点。"""
    fromdate, todate = _resolve_pit_window(
        list_date='20150601', delist_date=pd.NA,
        bt_start=_d('2010-01-01'), bt_end=_d('2025-12-31'),
    )
    assert fromdate == _d('2015-06-01')
    assert todate == _d('2025-12-31')


def test_pit_window_stock_delisted_during_backtest():
    """股票在 backtest 窗口内退市 → 用退市日做终点。"""
    fromdate, todate = _resolve_pit_window(
        list_date='20050101', delist_date='20180630',
        bt_start=_d('2010-01-01'), bt_end=_d('2025-12-31'),
    )
    assert fromdate == _d('2010-01-01')
    assert todate == _d('2018-06-30')


def test_pit_window_stock_lists_after_backtest():
    """股票在 backtest 窗口结束后才上市 → 返回 None（应排除该股）。"""
    result = _resolve_pit_window(
        list_date='20300101', delist_date=pd.NA,
        bt_start=_d('2010-01-01'), bt_end=_d('2025-12-31'),
    )
    assert result is None


def test_pit_window_stock_delisted_before_backtest():
    """股票在 backtest 窗口前已退市 → 返回 None。"""
    result = _resolve_pit_window(
        list_date='19950101', delist_date='20050601',
        bt_start=_d('2010-01-01'), bt_end=_d('2025-12-31'),
    )
    assert result is None


def test_pit_window_missing_list_date_uses_backtest_start():
    """list_date 缺失（NaN）→ 退化为 backtest 全窗口（保守，不排除）。"""
    fromdate, todate = _resolve_pit_window(
        list_date=pd.NA, delist_date=pd.NA,
        bt_start=_d('2010-01-01'), bt_end=_d('2025-12-31'),
    )
    assert fromdate == _d('2010-01-01')
    assert todate == _d('2025-12-31')
```

- [ ] **Step 3: 运行测试确认失败**

```bash
python -m pytest my_strategy/tests/test_pit_universe.py -v
```
Expected: ImportError（_resolve_pit_window 不存在）.

- [ ] **Step 4: 在 backtest.py 新增 `_resolve_pit_window` 辅助函数**

在 backtest.py 导入区下方加：

```python
def _resolve_pit_window(
    list_date,
    delist_date,
    bt_start: pd.Timestamp,
    bt_end: pd.Timestamp,
):
    """返回该股票在当前 backtest 窗口内的有效 (fromdate, todate) tuple。
    若该股票完全不在窗口内（上市晚于 bt_end 或退市早于 bt_start），返回 None。
    list_date / delist_date 可为 NaN（缺数据）；缺 list_date 时退化为 bt_start。
    """
    def _parse(d):
        if pd.isna(d):
            return None
        return pd.to_datetime(str(d), format='%Y%m%d', errors='coerce')

    listed = _parse(list_date)
    delisted = _parse(delist_date)

    fromdate = max(listed, bt_start) if listed is not None else bt_start
    todate = min(delisted, bt_end) if delisted is not None else bt_end

    if fromdate > bt_end:
        return None  # 上市晚于窗口
    if todate < bt_start:
        return None  # 退市早于窗口
    if fromdate > todate:
        return None  # 边缘情况
    return fromdate, todate
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest my_strategy/tests/test_pit_universe.py -v
```
Expected: 6 passed.

- [ ] **Step 6: 在数据加载循环里应用过滤**

定位 backtest.py 中加载每只股票 daily csv 并 `cerebro.adddata(...)` 的循环（Step 1 已记录）。

修改思路：
- 读 `stock_list.csv` 时 select `ts_code, list_date, delist_date`（如不存在该列，pandas 会忽略）
- 在循环里对每只股票调 `_resolve_pit_window`
- 若返回 None，跳过该股票
- 若返回 `(fromdate, todate)`，传给 `bt.feeds.PandasData(..., fromdate=..., todate=...)` 或者在加载 DataFrame 时按区间切片

具体实现（假设当前是直接 pd.read_csv 然后 PandasData，按 cfg.start_date / cfg.end_date 切的）：

```python
# 假设原代码大致：
# stock_list = pd.read_csv(project_root / 'stock_list.csv')
# bt_start = pd.to_datetime(cfg['start_date'], format='%Y%m%d')
# bt_end = pd.to_datetime(cfg['end_date'], format='%Y%m%d')
# for _, row in stock_list.iterrows():
#     ts_code = row['ts_code']
#     df = pd.read_csv(...)
#     df = df[(df['trade_date'] >= bt_start) & (df['trade_date'] <= bt_end)]
#     ...

# 改为：
list_date_lookup = dict(zip(stock_list['ts_code'], stock_list.get('list_date', pd.Series())))
delist_date_lookup = dict(zip(stock_list['ts_code'], stock_list.get('delist_date', pd.Series())))

n_skipped_pit = 0
for _, row in stock_list.iterrows():
    ts_code = row['ts_code']
    pit = _resolve_pit_window(
        list_date_lookup.get(ts_code, pd.NA),
        delist_date_lookup.get(ts_code, pd.NA),
        bt_start, bt_end,
    )
    if pit is None:
        n_skipped_pit += 1
        continue
    fromdate, todate = pit
    df = pd.read_csv(...)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df[(df['trade_date'] >= fromdate) & (df['trade_date'] <= todate)]
    if df.empty:
        continue
    # ... 原有 PandasData 加载
print(f"[backtest] PIT universe 过滤跳过 {n_skipped_pit} / {len(stock_list)} 股")
```

> 关键：对 `stock_list` 不含 `list_date / delist_date` 列的旧版兼容 —— `stock_list.get('list_date', pd.Series())` 返回空 Series，`list_date_lookup.get(ts_code, pd.NA)` 拿 NaN，`_resolve_pit_window` 退化为 bt 全窗口（保守）。

- [ ] **Step 7: 跑端到端验证**

```bash
cd my_strategy && python backtest.py 2>&1 | head -30
```
Expected：在加载阶段看到 `PIT universe 过滤跳过 N / 803 股` 的输出（N 应该 > 0 因为 25 年里部分股票较新）。

- [ ] **Step 8: 全量回归**

```bash
python -m pytest -q my_strategy/tests
```
Expected: pass.

- [ ] **Step 9: 更新文档 + Commit**

`docs/FEATURES.md` 数据加载相关段加注：「按 list_date / delist_date 过滤每只股票的有效回测窗口（PIT universe）」。

`docs/CHANGELOG.md` 顶部加 Task 3 条目。

```bash
git add my_strategy/backtest.py my_strategy/tests/test_pit_universe.py docs/FEATURES.md docs/CHANGELOG.md
git commit -m "feat(phase-b-prep): PIT universe filtering by list_date/delist_date"
```

---

## Task 4: 清理类 — 财务因子彻底移除 + cost_breakdown bug 修

**目的**：用户决定纯技术面，财务因子（PE/ROE/净利润同比）从信号体系彻底移除；修 cost_breakdown.csv overall 行 3 列空值的 bug。

**Files:**
- Modify: `my_strategy/tools/attribution.py`（factor_alpha 生成段）
- Modify: `my_strategy/tools/attribution_runner.py`（DEFAULT_SIGNALS_WHITELIST，确认）
- Modify: `my_strategy/tools/position_curve_attribution.py`（compute_cost_breakdown 的 run() 调用方式）
- Possibly modify: `my_strategy/backtest.py`（_enrich_trade_summary，若它仍在生成 factor_pe_ttm 等列）
- Test: `my_strategy/tests/test_factor_cleanup.py`（新建）+ 现有相关测试调整

- [ ] **Step 1: 调研当前财务因子在何处生成 / 消费**

```bash
grep -rn "factor_pe_ttm\|factor_roe\|factor_netprofit_yoy" my_strategy/ --include="*.py" --include="*.csv" 2>&1 | head -30
grep -n "factor_alpha\|factor_pe_ttm" my_strategy/tools/attribution.py | head
```
记录所有出现位置：生成端 vs 消费端。

- [ ] **Step 2: 调研 cost_breakdown bug 的修法**

```bash
grep -n "compute_cost_breakdown\|trade_list\|gross_pnl" my_strategy/tools/position_curve_attribution.py | head
head -3 my_strategy/results/trade_list.csv
head -3 my_strategy/results/trade_summary.csv
```
确认：trade_list.csv 没有 gross_pnl 列；trade_summary.csv 有 gross_pnl 列。修法选择：在 run() 里把 gross_pnl 从 trade_summary join 到 trade_list 后再调 compute_cost_breakdown，或直接把输入源改为 trade_summary（但 trade_summary 缺 price/size，也需补）。

**确定方案**：在 `position_curve_attribution.run()` 里读 trade_list 后，从 trade_summary 把 `episode → gross_pnl` 的映射 join 上去。

- [ ] **Step 3: 写测试 — 确保清理后的报告不再含财务因子列**

```python
# my_strategy/tests/test_factor_cleanup.py
"""验证财务因子已从消费侧彻底移除。"""
import pandas as pd
import pytest
from pathlib import Path


@pytest.mark.parametrize('csv_name', [
    'bottom_trades.csv',
    'top_trades.csv',
    'trade_profile.csv',
])
def test_no_financial_factor_cols(csv_name, tmp_path):
    """生产环境 reports/ 下这几张表不应含 factor_pe_ttm / factor_roe / factor_netprofit_yoy 列。

    本测试在端到端跑完一次后才有意义；CI 环境若没有真实 reports，跳过。
    """
    report = Path('my_strategy/reports') / csv_name
    if not report.exists():
        pytest.skip(f"{csv_name} 不存在（端到端未跑过），跳过")
    df = pd.read_csv(report)
    forbidden = {'factor_pe_ttm', 'factor_roe', 'factor_netprofit_yoy'}
    assert forbidden.isdisjoint(df.columns), \
        f"{csv_name} 仍含财务因子列：{set(df.columns) & forbidden}"


def test_default_signals_whitelist_no_finance():
    from my_strategy.tools.attribution_runner import DEFAULT_SIGNALS_WHITELIST
    forbidden = {'factor_pe_ttm', 'factor_roe', 'factor_netprofit_yoy'}
    assert forbidden.isdisjoint(set(DEFAULT_SIGNALS_WHITELIST))


def test_compute_cost_breakdown_overall_row_has_gross_pnl():
    """cost_breakdown.csv overall 行 gross_pnl / net_pnl / cost_pct_of_gross 必须非空。

    构造合成 trades 验证 _cost_block 的 gross_pnl 路径在 trades 含 gross_pnl 时被覆盖。
    """
    from my_strategy.tools.position_curve_attribution import compute_cost_breakdown
    trades = pd.DataFrame({
        'entry_date': pd.to_datetime(['2024-01-02', '2024-02-02']),
        'gross_pnl': [10000.0, -5000.0],
        'price': [10.0, 20.0],
        'size': [100, 100],
        'side': ['buy', 'sell'],
        'exit_reason': ['MA25清仓', 'MA60止损'],
    })
    out = compute_cost_breakdown(trades, cfg={'commission_rate': 0.0003, 'stamp_duty': 0.001})
    overall = out[(out['dimension'] == 'overall') & (out['bucket'] == 'all')].iloc[0]
    assert pd.notna(overall['gross_pnl'])
    assert pd.notna(overall['net_pnl'])
    assert pd.notna(overall['cost_pct_of_gross'])
    assert overall['gross_pnl'] == 5000.0
```

- [ ] **Step 4: 运行测试确认 1-2 条失败**

```bash
python -m pytest my_strategy/tests/test_factor_cleanup.py -v
```
Expected: `test_default_signals_whitelist_no_finance` 已 pass（Phase A 已修）；`test_compute_cost_breakdown_overall_row_has_gross_pnl` 大概率 fail（之前的 bug）；`test_no_financial_factor_cols` 视情况。

- [ ] **Step 5: 修 attribution.py 的 factor_alpha 生成段**

定位 `tools/attribution.py` 中 factor_alpha 计算逻辑（Step 1 grep 结果）。把候选因子列表从 `['factor_momentum_60d', 'factor_ma60_dist', 'factor_macd_strength', 'factor_pe_ttm', 'factor_roe', 'factor_netprofit_yoy']` 缩为 `['factor_momentum_60d', 'factor_ma60_dist', 'factor_macd_strength']`（保留前 3 个技术面因子）。

- [ ] **Step 6: 修 backtest.py `_enrich_trade_summary`（如其在生成 factor_pe_ttm 等）**

定位 `_enrich_trade_summary`，删除写入 `factor_pe_ttm / factor_roe / factor_netprofit_yoy` 的代码段（如有）。

注意：`bottom_trades.csv` / `top_trades.csv` 现在仍含这几列是因为之前 trade_summary 含。修完后下次跑 backtest 这些列就消失。

- [ ] **Step 7: 修 position_curve_attribution.run() — cost_breakdown bug**

在 `position_curve_attribution.run()` 里读 trade_list 之后、调 compute_cost_breakdown 之前，从 trade_summary 把 gross_pnl join 进去：

```python
# 当前代码大致：
# trade_list = pd.read_csv(trade_list_path, ...)
# compute_cost_breakdown(trade_list, cfg).to_csv(...)

# 改为（在 run() 内 trade_list 读取之后）：
trade_summary_path = results_dir / 'trade_summary.csv'
if trade_summary_path.exists():
    summary = pd.read_csv(trade_summary_path, usecols=['episode', 'gross_pnl'])
    trade_list = trade_list.merge(summary, on='episode', how='left', suffixes=('', '_from_summary'))
    # 若 trade_list 已有 gross_pnl 列，merge 后会有 _from_summary 后缀；统一化：
    if 'gross_pnl_from_summary' in trade_list.columns:
        trade_list['gross_pnl'] = trade_list.get('gross_pnl', pd.Series()).combine_first(
            trade_list['gross_pnl_from_summary'])
        trade_list = trade_list.drop(columns=['gross_pnl_from_summary'])
```

> 这里假设 trade_list.csv 含 episode 列（Phase A Task 0 调研已确认）；若不含则 join key 需调整。

- [ ] **Step 8: 运行测试确认通过**

```bash
python -m pytest my_strategy/tests/test_factor_cleanup.py -v
python -m pytest my_strategy/tests/test_position_curve_attribution.py -v
```
Expected: 全 pass。

- [ ] **Step 9: 端到端验证**

```bash
cd my_strategy && python backtest.py 2>&1 | tail -10
head -1 my_strategy/reports/trade_profile.csv | tr ',' '\n' | grep -E "^factor_" | head
head -2 my_strategy/reports/cost_breakdown.csv
```
Expected:
- `trade_profile.csv` header 中只剩 `factor_momentum_60d, factor_ma60_dist, factor_macd_strength`（无 PE/ROE/netprofit）
- `cost_breakdown.csv` overall 行 4 个值都不空

- [ ] **Step 10: 更新文档 + Commit**

`docs/CHANGELOG.md` 顶部加 Task 4 条目（说明：财务因子已从消费侧移除；factor_alpha.csv 改为 3 行；cost_breakdown.csv overall bug 已修）。

```bash
git add my_strategy/tools/attribution.py my_strategy/tools/position_curve_attribution.py my_strategy/backtest.py my_strategy/tests/test_factor_cleanup.py docs/CHANGELOG.md
git commit -m "fix(phase-b-prep): remove financial factors from consumers + fix cost_breakdown overall row"
```

---

## Task 5: `trade_summary` 增 4 列

**目的**：给每笔交易加 `mfe_minus_realized` / `exit_efficiency` / `benchmark_return_during_holding` / `per_trade_alpha`，下游归因报告自动按维度切片。同时为 Task 6 准备 forward_return_5d/20d/60d 列。

**Files:**
- Modify: `my_strategy/backtest.py`（`_enrich_trade_summary` 函数）
- Test: `my_strategy/tests/test_trade_summary_enrichment.py`

- [ ] **Step 1: 调研 _enrich_trade_summary 当前结构**

```bash
sed -n '270,360p' my_strategy/backtest.py
```
理解：当前增列逻辑、HS300 数据是否已加载、forward_return 是否已部分实现（bottom/top_trades 含此列说明可能在别处生成）。

- [ ] **Step 2: 写失败的测试**

```python
# my_strategy/tests/test_trade_summary_enrichment.py
"""验证 trade_summary 4 个新列计算正确。"""
import pandas as pd
import pytest
from my_strategy.backtest import _add_trade_summary_metrics


def _hs300_daily():
    """合成 HS300 close 序列：2024-01-02 ~ 2024-01-15，每天 +1%。"""
    return pd.DataFrame({
        'trade_date': pd.date_range('2024-01-02', periods=10, freq='B'),
        'close': [100 * (1.01 ** i) for i in range(10)],
    })


def test_mfe_minus_realized_basic():
    summary = pd.DataFrame({
        'episode': [1],
        'entry_date': pd.to_datetime(['2024-01-02']),
        'exit_date': pd.to_datetime(['2024-01-08']),
        'return_pct': [5.0],
        'mfe_pct': [10.0],
    })
    out = _add_trade_summary_metrics(summary, hs300_daily=_hs300_daily())
    assert abs(out.iloc[0]['mfe_minus_realized'] - 5.0) < 1e-9


def test_exit_efficiency_when_mfe_positive():
    summary = pd.DataFrame({
        'episode': [1, 2],
        'entry_date': pd.to_datetime(['2024-01-02', '2024-01-02']),
        'exit_date': pd.to_datetime(['2024-01-08', '2024-01-08']),
        'return_pct': [5.0, -3.0],
        'mfe_pct': [10.0, 0.0],  # 第二笔 mfe=0 → exit_efficiency NaN
    })
    out = _add_trade_summary_metrics(summary, hs300_daily=_hs300_daily())
    assert abs(out.iloc[0]['exit_efficiency'] - 0.5) < 1e-9
    assert pd.isna(out.iloc[1]['exit_efficiency'])


def test_benchmark_return_during_holding():
    """HS300 从 1/2 到 1/8 涨 5%（每天 +1%，5 个交易日）。"""
    summary = pd.DataFrame({
        'episode': [1],
        'entry_date': pd.to_datetime(['2024-01-02']),
        'exit_date': pd.to_datetime(['2024-01-08']),
        'return_pct': [10.0],
        'mfe_pct': [12.0],
    })
    out = _add_trade_summary_metrics(summary, hs300_daily=_hs300_daily())
    # 1/2 close=100, 1/8 close ≈ 100 * 1.01^4 ≈ 104.06 (1/2 是 0 天后)
    # bench_return = (104.06 - 100) / 100 ≈ 4.06%
    bench = out.iloc[0]['benchmark_return_during_holding']
    assert 4.0 < bench < 4.2


def test_per_trade_alpha():
    summary = pd.DataFrame({
        'episode': [1],
        'entry_date': pd.to_datetime(['2024-01-02']),
        'exit_date': pd.to_datetime(['2024-01-08']),
        'return_pct': [10.0],
        'mfe_pct': [12.0],
    })
    out = _add_trade_summary_metrics(summary, hs300_daily=_hs300_daily())
    # alpha = 10 - bench(~4.06) ≈ 5.94
    assert 5.5 < out.iloc[0]['per_trade_alpha'] < 6.5


def test_handles_missing_hs300():
    """HS300 数据为 None → benchmark_return / per_trade_alpha 为 NaN，不抛错。"""
    summary = pd.DataFrame({
        'episode': [1],
        'entry_date': pd.to_datetime(['2024-01-02']),
        'exit_date': pd.to_datetime(['2024-01-08']),
        'return_pct': [10.0],
        'mfe_pct': [12.0],
    })
    out = _add_trade_summary_metrics(summary, hs300_daily=None)
    assert pd.isna(out.iloc[0]['benchmark_return_during_holding'])
    assert pd.isna(out.iloc[0]['per_trade_alpha'])
    # 前两列仍应正确
    assert abs(out.iloc[0]['mfe_minus_realized'] - 2.0) < 1e-9


def test_handles_open_position_no_exit_date():
    """exit_date NaN（未平仓）→ 后两列 NaN，前两列 NaN（mfe_pct 仍可能有但定义不全）。"""
    summary = pd.DataFrame({
        'episode': [1],
        'entry_date': pd.to_datetime(['2024-01-02']),
        'exit_date': [pd.NaT],
        'return_pct': [pd.NA],
        'mfe_pct': [5.0],
    })
    out = _add_trade_summary_metrics(summary, hs300_daily=_hs300_daily())
    # 未平仓应不抛错；4 列允许 NaN
    assert pd.isna(out.iloc[0]['benchmark_return_during_holding'])
    assert pd.isna(out.iloc[0]['per_trade_alpha'])
```

- [ ] **Step 3: 运行测试确认失败**

```bash
python -m pytest my_strategy/tests/test_trade_summary_enrichment.py -v
```
Expected: ImportError 或 FAIL.

- [ ] **Step 4: 在 backtest.py 实现 `_add_trade_summary_metrics`**

紧邻现有 `_enrich_trade_summary` 加新函数：

```python
def _add_trade_summary_metrics(
    summary: pd.DataFrame,
    hs300_daily: pd.DataFrame = None,
) -> pd.DataFrame:
    """给 trade_summary 增加 4 列：
    - mfe_minus_realized = mfe_pct - return_pct
    - exit_efficiency = return_pct / mfe_pct（mfe_pct > 0 时；否则 NaN）
    - benchmark_return_during_holding = HS300 同期累计收益 (%)
    - per_trade_alpha = return_pct - benchmark_return_during_holding

    hs300_daily 缺失时后两列为 NaN，但前两列仍正常计算。
    未平仓（exit_date 为 NaT）行：4 列均 NaN。
    """
    out = summary.copy()
    has_exit = pd.to_datetime(out['exit_date'], errors='coerce').notna()

    # 列 1, 2：仅依赖现有列
    out['mfe_minus_realized'] = pd.to_numeric(out['mfe_pct'], errors='coerce') \
                                 - pd.to_numeric(out['return_pct'], errors='coerce')
    mfe = pd.to_numeric(out['mfe_pct'], errors='coerce')
    ret = pd.to_numeric(out['return_pct'], errors='coerce')
    out['exit_efficiency'] = ret.where(mfe > 0) / mfe.where(mfe > 0)

    # 未平仓的清掉前 2 列（行为约定）
    out.loc[~has_exit, ['mfe_minus_realized', 'exit_efficiency']] = pd.NA

    # 列 3, 4：依赖 hs300_daily
    out['benchmark_return_during_holding'] = pd.NA
    out['per_trade_alpha'] = pd.NA
    if hs300_daily is None or hs300_daily.empty:
        return out

    hs = hs300_daily.copy()
    hs['trade_date'] = pd.to_datetime(hs['trade_date'])
    hs = hs.set_index('trade_date').sort_index()

    bench_returns = []
    alphas = []
    for _, r in out.iterrows():
        ed = pd.to_datetime(r['entry_date'], errors='coerce')
        xd = pd.to_datetime(r['exit_date'], errors='coerce')
        if pd.isna(ed) or pd.isna(xd):
            bench_returns.append(pd.NA)
            alphas.append(pd.NA)
            continue
        try:
            entry_close = hs.loc[hs.index >= ed].iloc[0]['close']
            exit_close = hs.loc[hs.index <= xd].iloc[-1]['close']
            br = (exit_close - entry_close) / entry_close * 100.0
            bench_returns.append(br)
            ret_val = pd.to_numeric(r['return_pct'], errors='coerce')
            alphas.append(ret_val - br if pd.notna(ret_val) else pd.NA)
        except (KeyError, IndexError):
            bench_returns.append(pd.NA)
            alphas.append(pd.NA)
    out['benchmark_return_during_holding'] = bench_returns
    out['per_trade_alpha'] = alphas
    return out
```

- [ ] **Step 5: 在 backtest.py main() / 写出 trade_summary 之前调用该函数**

定位 backtest.py 中写 `trade_summary.csv` 的代码位置（接近 line 827）。在写出前加：

```python
# 加载 HS300 daily 用于计算单笔 alpha
hs300_path = project_root / 'data' / 'daily' / '000300.SH.csv'
hs300_daily = pd.read_csv(hs300_path) if hs300_path.exists() else None
summary_df = _add_trade_summary_metrics(summary_df, hs300_daily=hs300_daily)
```

- [ ] **Step 6: 运行测试确认通过**

```bash
python -m pytest my_strategy/tests/test_trade_summary_enrichment.py -v
```
Expected: 6 passed.

- [ ] **Step 7: 端到端跑一次验证 4 列写入**

```bash
cd my_strategy && python backtest.py 2>&1 | tail -5
head -1 my_strategy/results/trade_summary.csv | tr ',' '\n' | grep -E "mfe_minus_realized|exit_efficiency|benchmark_return|per_trade_alpha"
python -c "import pandas as pd; df=pd.read_csv('my_strategy/results/trade_summary.csv'); print(df[['mfe_minus_realized','exit_efficiency','benchmark_return_during_holding','per_trade_alpha']].describe())"
```
Expected: 4 列出现在 header；describe() 给出非平凡数字（mfe_minus_realized 多为正、exit_efficiency 在 0-1、bench_return 跨样本散布、alpha 有正有负）。

- [ ] **Step 8: 全量回归**

```bash
python -m pytest -q my_strategy/tests
```
Expected: pass.

- [ ] **Step 9: 更新文档 + Commit**

`docs/FEATURES.md` §5.4 产物里 trade_summary.csv 描述加 4 列说明。

`docs/CHANGELOG.md` 顶部加 Task 5 条目。

```bash
git add my_strategy/backtest.py my_strategy/tests/test_trade_summary_enrichment.py docs/FEATURES.md docs/CHANGELOG.md
git commit -m "feat(phase-b-prep): trade_summary +4 cols (mfe_minus_realized, exit_efficiency, bench_return, per_trade_alpha)"
```

---

## Task 6: `signal_importance_ranking.csv` + 全量 IC

**目的**：把分散在各 entry_*_stats / signal_stability / factor_alpha / significance_summary 的信息合并成一张统一信号重要性排名表，附 IC / IC_IR。前置：在 trade_summary 上扩 forward_return_5d/20d/60d 列。

**Files:**
- Modify: `my_strategy/backtest.py`（`_add_trade_summary_metrics` 增加 forward_return 计算）
- Modify: `my_strategy/tools/trade_attribution_extra.py`（新增 `compute_signal_importance_ranking`）
- Modify: `my_strategy/tools/attribution_runner.py`（在 trade_attribution_extra.run() 之后写出新报告）
- Test: `my_strategy/tests/test_signal_importance_ranking.py`
- Test: `my_strategy/tests/test_forward_return_enrichment.py`

- [ ] **Step 1: 调研 forward_return_5d/20d/60d 当前生成位置**

```bash
grep -rn "forward_return_5d\|forward_return_20d\|forward_return_60d" my_strategy/ --include="*.py" | head -20
```
确认：bottom/top_trades.csv 有此列说明已有计算逻辑。可能在 `attribution.py` 内部生成，需要把它提到 `_add_trade_summary_metrics` 让 trade_summary 自身就有这 3 列。

- [ ] **Step 2: 写 forward_return 测试**

```python
# my_strategy/tests/test_forward_return_enrichment.py
"""验证 forward_return_5d/20d/60d 写入 trade_summary。"""
import pandas as pd
from my_strategy.backtest import _add_forward_returns


def _make_daily(prices):
    return pd.DataFrame({
        'trade_date': pd.date_range('2024-01-02', periods=len(prices), freq='B'),
        'close': prices,
    })


def test_forward_return_5d():
    daily_lookup = {
        'A.SZ': _make_daily([10.0, 10.5, 11.0, 11.0, 11.0, 12.0, 13.0]),
    }
    summary = pd.DataFrame({
        'ts_code': ['A.SZ'],
        'entry_date': pd.to_datetime(['2024-01-02']),
    })
    out = _add_forward_returns(summary, daily_lookup, windows=(5,))
    # 1/2 close=10, +5 trade days → close=12, return = (12-10)/10 = 20%
    assert abs(out.iloc[0]['forward_return_5d'] - 20.0) < 1e-6


def test_forward_return_handles_missing_ts_code():
    daily_lookup = {}  # empty
    summary = pd.DataFrame({
        'ts_code': ['A.SZ'],
        'entry_date': pd.to_datetime(['2024-01-02']),
    })
    out = _add_forward_returns(summary, daily_lookup, windows=(5, 20, 60))
    assert pd.isna(out.iloc[0]['forward_return_5d'])
    assert pd.isna(out.iloc[0]['forward_return_60d'])


def test_forward_return_handles_short_series():
    """+60 trade days 超出数据末端 → NaN。"""
    daily_lookup = {'A.SZ': _make_daily([10.0] * 10)}
    summary = pd.DataFrame({
        'ts_code': ['A.SZ'],
        'entry_date': pd.to_datetime(['2024-01-02']),
    })
    out = _add_forward_returns(summary, daily_lookup, windows=(5, 20, 60))
    assert pd.notna(out.iloc[0]['forward_return_5d'])
    assert pd.isna(out.iloc[0]['forward_return_60d'])
```

- [ ] **Step 3: 在 backtest.py 实现 `_add_forward_returns`**

在 `_add_trade_summary_metrics` 旁加：

```python
def _add_forward_returns(
    summary: pd.DataFrame,
    daily_lookup: dict,  # ts_code -> DataFrame[trade_date, close]
    windows: tuple = (5, 20, 60),
) -> pd.DataFrame:
    """给每笔交易加 forward_return_<N>d 列（百分比）：
    入场后 N 个交易日的累计收益 = (close[entry+N] - close[entry]) / close[entry] * 100
    数据不足或 ts_code 缺失则 NaN。
    """
    out = summary.copy()
    for w in windows:
        out[f'forward_return_{w}d'] = pd.NA

    for idx, r in out.iterrows():
        ts = r['ts_code']
        ed = pd.to_datetime(r['entry_date'], errors='coerce')
        if pd.isna(ed) or ts not in daily_lookup:
            continue
        d = daily_lookup[ts].copy()
        d['trade_date'] = pd.to_datetime(d['trade_date'])
        d = d.sort_values('trade_date').reset_index(drop=True)
        # 找入场 close
        mask_entry = d['trade_date'] >= ed
        if not mask_entry.any():
            continue
        entry_pos = mask_entry.idxmax()
        entry_close = d.iloc[entry_pos]['close']
        for w in windows:
            forward_pos = entry_pos + w
            if forward_pos < len(d):
                fc = d.iloc[forward_pos]['close']
                out.at[idx, f'forward_return_{w}d'] = (fc - entry_close) / entry_close * 100.0
    return out
```

并修改 `_add_trade_summary_metrics`（或在它后面 chain 调用）让 backtest main() 接入：

```python
# main() 内 trade_summary 写出之前
summary_df = _add_trade_summary_metrics(summary_df, hs300_daily=hs300_daily)
# 复用 cerebro 加载的 daily 数据；但 cerebro 不直接给 dict
# 简化：从磁盘读 daily/ 目录
daily_lookup = {}
for ts in summary_df['ts_code'].unique():
    p = project_root / 'data' / 'daily' / f"{ts}.csv"
    if p.exists():
        daily_lookup[ts] = pd.read_csv(p)
summary_df = _add_forward_returns(summary_df, daily_lookup)
```

- [ ] **Step 4: 运行 forward_return 测试**

```bash
python -m pytest my_strategy/tests/test_forward_return_enrichment.py -v
```
Expected: 3 passed.

- [ ] **Step 5: 写 signal_importance_ranking 测试**

```python
# my_strategy/tests/test_signal_importance_ranking.py
import numpy as np
import pandas as pd
import pytest
from my_strategy.tools.trade_attribution_extra import compute_signal_importance_ranking


def _make_trades(n=200):
    """构造 200 笔交易：
    sig_a (bool) 与 return 强正相关
    sig_b (bool) 与 return 无关
    sig_c (numeric) 与 return 强正相关
    """
    rng = np.random.RandomState(42)
    a = rng.rand(n) > 0.5
    c = rng.normal(0, 1, size=n)
    ret = a * 10 + c * 5 + rng.normal(0, 2, size=n)  # mainly driven by a, c
    b = rng.rand(n) > 0.5
    return pd.DataFrame({
        'ts_code': ['X'] * n,
        'entry_date': pd.date_range('2024-01-01', periods=n, freq='D'),
        'return_pct': ret,
        'forward_return_5d': ret + rng.normal(0, 1, size=n),
        'forward_return_20d': ret + rng.normal(0, 2, size=n),
        'forward_return_60d': ret + rng.normal(0, 3, size=n),
        'sig_a': a,
        'sig_b': b,
        'sig_c': c,
    })


def test_ranking_columns():
    trades = _make_trades()
    out = compute_signal_importance_ranking(trades, signals=['sig_a', 'sig_b', 'sig_c'])
    expected_cols = {
        'signal_name', 'signal_type', 'n', 'mean_return_when_true',
        'mean_return_when_false', 'effect_size', 't_stat', 'p_value',
        'ic_mean_5d', 'ic_mean_20d', 'ic_mean_60d', 'ic_ir_60d',
        'rank_by_effect_size', 'rank_by_ic', 'rank_combined',
    }
    assert expected_cols.issubset(set(out.columns))


def test_ranking_significant_signal_first():
    trades = _make_trades()
    out = compute_signal_importance_ranking(trades, signals=['sig_a', 'sig_b', 'sig_c'])
    rank_a = out[out['signal_name'] == 'sig_a']['rank_by_effect_size'].iloc[0]
    rank_b = out[out['signal_name'] == 'sig_b']['rank_by_effect_size'].iloc[0]
    assert rank_a < rank_b  # sig_a 比 sig_b 排名靠前（rank 1 = top）


def test_ranking_ic_for_numeric():
    trades = _make_trades()
    out = compute_signal_importance_ranking(trades, signals=['sig_c'])
    # sig_c 与 return 强相关 → ic_mean_60d 应有较大绝对值
    ic = out.iloc[0]['ic_mean_60d']
    assert abs(ic) > 0.2  # 20 月分桶的均值 IC 应远大于 0


def test_ranking_skips_missing_signal():
    trades = _make_trades()
    out = compute_signal_importance_ranking(trades, signals=['sig_a', 'nonexistent_sig'])
    assert 'nonexistent_sig' not in out['signal_name'].values
    assert 'sig_a' in out['signal_name'].values
```

- [ ] **Step 6: 运行测试确认失败**

```bash
python -m pytest my_strategy/tests/test_signal_importance_ranking.py -v
```
Expected: ImportError.

- [ ] **Step 7: 在 trade_attribution_extra.py 实现 `compute_signal_importance_ranking`**

追加到文件末尾：

```python
from scipy import stats as sp_stats


def _compute_ic_monthly(
    series: pd.Series, forward: pd.Series, entry_dates: pd.Series,
) -> tuple:
    """按 entry_date 月份分桶，每月算一次 spearman；返回 (mean, std)。"""
    df = pd.DataFrame({'s': series, 'f': forward, 'm': entry_dates.dt.to_period('M')})
    df = df.dropna(subset=['s', 'f'])
    if df.empty:
        return (np.nan, np.nan)
    monthly_ic = []
    for _, g in df.groupby('m'):
        if len(g) < 5:
            continue  # 单月样本太少，跳过
        rho, _ = sp_stats.spearmanr(g['s'], g['f'])
        if pd.notna(rho):
            monthly_ic.append(rho)
    if len(monthly_ic) < 2:
        return (np.nan, np.nan)
    return (float(np.mean(monthly_ic)), float(np.std(monthly_ic, ddof=1)))


def _classify_signal_type(s: pd.Series) -> str:
    if s.dtype == bool or set(s.dropna().astype(str).unique()) <= {'True', 'False'}:
        return 'bool'
    if pd.api.types.is_numeric_dtype(s):
        return 'numeric'
    return 'categorical'


def compute_signal_importance_ranking(
    trades: pd.DataFrame, signals: list,
) -> pd.DataFrame:
    """对每个 signal 综合算 effect_size / t / p / IC / IC_IR / 排名。

    要求 trades 含 return_pct + forward_return_5d/20d/60d + entry_date。
    """
    if 'entry_date' in trades.columns:
        trades = trades.copy()
        trades['entry_date'] = pd.to_datetime(trades['entry_date'])

    rows = []
    for sig in signals:
        if sig not in trades.columns:
            continue
        sig_type = _classify_signal_type(trades[sig])
        n = trades[sig].notna().sum()

        # effect_size + t + p（仅 bool / numeric 二分；categorical 跳过这部分）
        if sig_type == 'bool':
            mask = trades[sig].astype(str).map({'True': True, 'False': False}).fillna(False)
            r_true = trades.loc[mask, 'return_pct'].dropna()
            r_false = trades.loc[~mask, 'return_pct'].dropna()
        elif sig_type == 'numeric':
            median = trades[sig].median()
            mask = trades[sig] > median
            r_true = trades.loc[mask, 'return_pct'].dropna()
            r_false = trades.loc[~mask, 'return_pct'].dropna()
        else:
            r_true = pd.Series([], dtype=float)
            r_false = pd.Series([], dtype=float)

        mean_true = r_true.mean() if len(r_true) > 0 else np.nan
        mean_false = r_false.mean() if len(r_false) > 0 else np.nan
        effect = mean_true - mean_false if pd.notna(mean_true) and pd.notna(mean_false) else np.nan
        if len(r_true) >= 2 and len(r_false) >= 2:
            t_stat, p_val = sp_stats.ttest_ind(r_true, r_false, equal_var=False)
        else:
            t_stat, p_val = (np.nan, np.nan)

        # IC（仅 numeric / bool 转 0/1 后）
        if 'entry_date' in trades.columns and sig_type in ('bool', 'numeric'):
            sig_numeric = (trades[sig].astype(str).map({'True': 1, 'False': 0}).astype(float)
                            if sig_type == 'bool' else trades[sig].astype(float))
            ic_5_mean, ic_5_std = _compute_ic_monthly(
                sig_numeric, trades.get('forward_return_5d', pd.Series()),
                trades['entry_date'])
            ic_20_mean, _ = _compute_ic_monthly(
                sig_numeric, trades.get('forward_return_20d', pd.Series()),
                trades['entry_date'])
            ic_60_mean, ic_60_std = _compute_ic_monthly(
                sig_numeric, trades.get('forward_return_60d', pd.Series()),
                trades['entry_date'])
            ic_ir_60 = ic_60_mean / ic_60_std if (pd.notna(ic_60_std) and ic_60_std > 0) else np.nan
        else:
            ic_5_mean = ic_20_mean = ic_60_mean = ic_ir_60 = np.nan

        rows.append({
            'signal_name': sig, 'signal_type': sig_type, 'n': int(n),
            'mean_return_when_true': mean_true, 'mean_return_when_false': mean_false,
            'effect_size': effect, 't_stat': t_stat, 'p_value': p_val,
            'ic_mean_5d': ic_5_mean, 'ic_mean_20d': ic_20_mean,
            'ic_mean_60d': ic_60_mean, 'ic_ir_60d': ic_ir_60,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df['rank_by_effect_size'] = df['effect_size'].abs().rank(method='dense', ascending=False).astype('Int64')
    df['rank_by_ic'] = df['ic_mean_60d'].abs().rank(method='dense', ascending=False).astype('Int64')
    df['rank_combined'] = (
        (df['effect_size'].abs().rank(method='dense', ascending=False) * 0.5)
        + (df['ic_mean_60d'].abs().rank(method='dense', ascending=False) * 0.5)
    ).rank(method='dense').astype('Int64')
    return df.sort_values('rank_combined').reset_index(drop=True)
```

- [ ] **Step 8: 运行测试确认通过**

```bash
python -m pytest my_strategy/tests/test_signal_importance_ranking.py -v
```
Expected: 4 passed.

- [ ] **Step 9: 在 trade_attribution_extra.run() 写出报告**

修改 `trade_attribution_extra.py` 末尾的 `run()`：

```python
def run(trades: pd.DataFrame, out_dir: Path, signals_whitelist: list, combos: list) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    compute_payoff_metrics(trades).to_csv(out_dir / 'payoff_metrics.csv', index=False)
    compute_signal_stability(trades, signals_whitelist).to_csv(out_dir / 'signal_stability.csv', index=False)
    compute_signal_correlation_matrix(trades, signals_whitelist).to_csv(out_dir / 'signal_correlation_matrix.csv', index=False)
    compute_multi_factor_combo_stats(trades, combos).to_csv(out_dir / 'multi_factor_combo_stats.csv', index=False)
    compute_significance_summary(trades).to_csv(out_dir / 'significance_summary.csv', index=False)
    # NEW
    compute_signal_importance_ranking(trades, signals_whitelist).to_csv(
        out_dir / 'signal_importance_ranking.csv', index=False)
```

- [ ] **Step 10: 端到端跑 + 验证**

```bash
cd my_strategy && python backtest.py 2>&1 | tail -5
ls my_strategy/reports/signal_importance_ranking.csv
head -5 my_strategy/reports/signal_importance_ranking.csv
```
Expected: 报告存在；前几行按 rank_combined 排序。

- [ ] **Step 11: 全量回归 + Commit**

```bash
python -m pytest -q my_strategy/tests
```

```bash
git add my_strategy/backtest.py my_strategy/tools/trade_attribution_extra.py my_strategy/tests/test_forward_return_enrichment.py my_strategy/tests/test_signal_importance_ranking.py docs/FEATURES.md docs/CHANGELOG.md
git commit -m "feat(phase-b-prep): signal_importance_ranking + universe IC for all signals"
```

---

## Task 7: `rolling_metrics.csv`

**目的**：滚动 252 交易日窗口的关键指标，识别策略衰减 / regime 切换。基于 daily 收益序列。

**Files:**
- Modify: `my_strategy/tools/portfolio_attribution.py`（追加 `compute_rolling_metrics`）
- Modify: `my_strategy/tools/portfolio_attribution.py`（`run()` 中写出 `rolling_metrics.csv`）
- Test: `my_strategy/tests/test_rolling_metrics.py`

- [ ] **Step 1: 写测试**

```python
# my_strategy/tests/test_rolling_metrics.py
import numpy as np
import pandas as pd
import pytest
from my_strategy.tools.portfolio_attribution import compute_rolling_metrics


def test_rolling_metrics_columns():
    rng = np.random.RandomState(0)
    daily_ret = pd.Series(
        rng.normal(0.0005, 0.01, size=300),
        index=pd.date_range('2024-01-01', periods=300, freq='B'),
    )
    out = compute_rolling_metrics(daily_ret, window=252)
    expected = {'window_end_date', 'window_size_days', 'n_trading_days',
                'sharpe', 'sortino', 'win_rate_daily', 'max_dd_in_window'}
    assert expected.issubset(set(out.columns))


def test_rolling_metrics_returns_post_window_rows():
    rng = np.random.RandomState(0)
    daily_ret = pd.Series(rng.normal(0, 0.01, size=300),
                          index=pd.date_range('2024-01-01', periods=300, freq='B'))
    out = compute_rolling_metrics(daily_ret, window=252)
    # 300 - 252 + 1 = 49 行
    assert len(out) == 49
    assert out['n_trading_days'].iloc[0] == 252


def test_rolling_metrics_uptrend_positive_sharpe():
    """持续上升 daily_ret → rolling Sharpe 应 > 0。"""
    daily_ret = pd.Series([0.001] * 300,
                          index=pd.date_range('2024-01-01', periods=300, freq='B'))
    out = compute_rolling_metrics(daily_ret, window=252)
    # 所有窗口都是恒定收益，Sharpe 是 inf 或非常大；这里只要求 > 0
    assert (out['sharpe'].fillna(0) >= 0).all()


def test_rolling_metrics_max_dd_negative():
    """前半上升后半下降 → max_dd 出现负值。"""
    daily_ret = pd.Series([0.005] * 200 + [-0.005] * 100,
                          index=pd.date_range('2024-01-01', periods=300, freq='B'))
    out = compute_rolling_metrics(daily_ret, window=252)
    assert (out['max_dd_in_window'] < 0).any()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest my_strategy/tests/test_rolling_metrics.py -v
```
Expected: ImportError.

- [ ] **Step 3: 实现 `compute_rolling_metrics`**

追加到 `tools/portfolio_attribution.py` 末尾（在 `run()` 之前）：

```python
def compute_rolling_metrics(
    daily_ret: pd.Series, window: int = 252,
) -> pd.DataFrame:
    """对 daily 收益序列做长度 window 的滚动统计。
    输出从第 window 个 bar 起每日一行。
    """
    s = pd.Series(daily_ret).dropna()
    s.index = pd.to_datetime(s.index)
    if len(s) < window:
        return pd.DataFrame()

    rows = []
    for i in range(window - 1, len(s)):
        sub = s.iloc[i - window + 1:i + 1]
        if sub.empty:
            continue
        equity = (1 + sub).cumprod()
        ann_ret = float((1 + sub.mean()) ** _TRADING_DAYS - 1)
        ann_vol = float(sub.std(ddof=1) * np.sqrt(_TRADING_DAYS))
        downside = sub[sub < 0]
        down_vol = float(downside.std(ddof=1) * np.sqrt(_TRADING_DAYS)) if len(downside) >= 2 else np.nan
        sharpe = ann_ret / ann_vol if ann_vol > 0 else np.nan
        sortino = ann_ret / down_vol if (pd.notna(down_vol) and down_vol > 0) else np.nan
        running_peak = equity.cummax()
        dd = equity / running_peak - 1.0
        max_dd = float(dd.min())

        rows.append({
            'window_end_date': sub.index[-1],
            'window_size_days': window,
            'n_trading_days': len(sub),
            'sharpe': round(sharpe, 4) if pd.notna(sharpe) else np.nan,
            'sortino': round(sortino, 4) if pd.notna(sortino) else np.nan,
            'win_rate_daily': round(float((sub > 0).mean()), 4),
            'max_dd_in_window': round(max_dd, 4),
            'annualized_return': round(ann_ret, 4),
            'annualized_vol': round(ann_vol, 4),
        })
    return pd.DataFrame(rows)
```

- [ ] **Step 4: 在 `portfolio_attribution.run()` 末尾写出**

```python
    compute_rolling_metrics(daily_ret).to_csv(out_dir / 'rolling_metrics.csv', index=False)
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest my_strategy/tests/test_rolling_metrics.py -v
```
Expected: 4 passed.

- [ ] **Step 6: 端到端跑 + 验证**

```bash
cd my_strategy && python backtest.py 2>&1 | tail -5
head -3 my_strategy/reports/rolling_metrics.csv
wc -l my_strategy/reports/rolling_metrics.csv
```
Expected: 报告存在；行数应该 = N_trading_days - 251（25 年 * 252 - 251 ≈ 6000 行）。

- [ ] **Step 7: 全量回归 + Commit**

```bash
python -m pytest -q my_strategy/tests
git add my_strategy/tools/portfolio_attribution.py my_strategy/tests/test_rolling_metrics.py docs/FEATURES.md docs/CHANGELOG.md
git commit -m "feat(phase-b-prep): rolling_metrics report (252-day rolling Sharpe/Sortino/MaxDD)"
```

---

## Task 8: `loss_attribution.csv`

**目的**：识别"亏损交易里哪些信号最常一起 fire"。区别于"信号 overall mean return"。

**Files:**
- Modify: `my_strategy/tools/trade_attribution_extra.py`（追加 `compute_loss_attribution`）
- Modify: `my_strategy/tools/trade_attribution_extra.py`（`run()` 中写出）
- Test: `my_strategy/tests/test_loss_attribution.py`

- [ ] **Step 1: 写测试**

```python
# my_strategy/tests/test_loss_attribution.py
import numpy as np
import pandas as pd
import pytest
from my_strategy.tools.trade_attribution_extra import compute_loss_attribution


def _make_trades():
    """构造数据：sig_x = False 时 return 总是负，sig_x = True 时随机。"""
    rng = np.random.RandomState(0)
    n = 200
    sig_x = rng.rand(n) > 0.5
    ret = np.where(sig_x, rng.normal(5, 5, n), rng.normal(-5, 5, n))
    return pd.DataFrame({
        'return_pct': ret,
        'sig_x': sig_x,
        'sig_y': rng.rand(n) > 0.5,  # 与 return 无关
    })


def test_loss_attribution_columns():
    trades = _make_trades()
    out = compute_loss_attribution(trades, signals=['sig_x', 'sig_y'])
    expected = {'signal_name', 'signal_value', 'freq_in_universe',
                'freq_in_losses', 'freq_in_heavy_losses',
                'lift_loss', 'lift_heavy_loss',
                'chi2_stat', 'p_value',
                'n_universe', 'n_losses', 'n_heavy_losses'}
    assert expected.issubset(set(out.columns))


def test_loss_attribution_finds_high_lift_for_loss_signal():
    trades = _make_trades()
    out = compute_loss_attribution(trades, signals=['sig_x', 'sig_y'])
    sig_x_false = out[(out['signal_name'] == 'sig_x') & (out['signal_value'] == 'False')].iloc[0]
    sig_y_false = out[(out['signal_name'] == 'sig_y') & (out['signal_value'] == 'False')].iloc[0]
    assert sig_x_false['lift_loss'] > sig_y_false['lift_loss']
    assert sig_x_false['p_value'] < 0.05  # 显著相关


def test_loss_attribution_returns_empty_on_no_losses():
    trades = pd.DataFrame({'return_pct': [1, 2, 3], 'sig_x': [True, True, False]})
    out = compute_loss_attribution(trades, signals=['sig_x'])
    # 无亏损交易，n_losses=0；输出仍应有行（freq_in_losses=NaN）
    assert (out['n_losses'] == 0).all()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest my_strategy/tests/test_loss_attribution.py -v
```
Expected: ImportError.

- [ ] **Step 3: 实现 `compute_loss_attribution`**

追加到 `tools/trade_attribution_extra.py`：

```python
def compute_loss_attribution(
    trades: pd.DataFrame, signals: list, heavy_loss_threshold: float = -5.0,
) -> pd.DataFrame:
    """对每个 signal 列出"信号值 vs 亏损交易频率"对比表。

    输出每个 (signal, value) 一行。numeric 信号按 5 分位枚举；bool/cat 按唯一值。
    """
    n_universe = len(trades)
    losses = trades[trades['return_pct'] < 0]
    heavy = trades[trades['return_pct'] < heavy_loss_threshold]
    n_losses = len(losses)
    n_heavy = len(heavy)

    rows = []
    for sig in signals:
        if sig not in trades.columns:
            continue
        s = trades[sig]
        sig_type = _classify_signal_type(s)

        if sig_type == 'bool':
            values = [(False, lambda x: x.astype(str).isin(['False'])),
                      (True, lambda x: x.astype(str).isin(['True']))]
        elif sig_type == 'numeric':
            qs_full = pd.qcut(s, q=5, labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'], duplicates='drop')
            values = [(lbl, lambda x, _q=lbl: pd.qcut(x, q=5, labels=['Q1','Q2','Q3','Q4','Q5'], duplicates='drop') == _q)
                      for lbl in qs_full.dropna().unique()]
        else:
            values = [(str(v), lambda x, _v=v: x == _v) for v in s.dropna().unique()]

        for val, mask_fn in values:
            mask_uni = mask_fn(s)
            mask_loss = mask_fn(losses[sig]) if n_losses > 0 else pd.Series([], dtype=bool)
            mask_heavy = mask_fn(heavy[sig]) if n_heavy > 0 else pd.Series([], dtype=bool)
            n_u = int(mask_uni.sum())
            n_l = int(mask_loss.sum()) if n_losses > 0 else 0
            n_h = int(mask_heavy.sum()) if n_heavy > 0 else 0
            freq_u = n_u / n_universe if n_universe > 0 else 0.0
            freq_l = n_l / n_losses if n_losses > 0 else np.nan
            freq_h = n_h / n_heavy if n_heavy > 0 else np.nan
            lift_l = freq_l / freq_u if (pd.notna(freq_l) and freq_u > 0) else np.nan
            lift_h = freq_h / freq_u if (pd.notna(freq_h) and freq_u > 0) else np.nan

            # chi-square test：信号 vs (loss/non-loss)
            chi2_stat, p_val = (np.nan, np.nan)
            if n_losses > 0 and n_universe > n_losses:
                a = n_l                             # signal=val & loss
                b = n_u - n_l                       # signal=val & non-loss
                c = n_losses - n_l                  # signal!=val & loss
                d = (n_universe - n_u) - (n_losses - n_l)  # signal!=val & non-loss
                contingency = np.array([[a, b], [c, d]])
                if (contingency >= 5).all():
                    chi2_stat, p_val, _, _ = sp_stats.chi2_contingency(contingency, correction=False)[:4]
                    chi2_stat = float(chi2_stat)
                    p_val = float(p_val)

            rows.append({
                'signal_name': sig, 'signal_value': str(val),
                'freq_in_universe': round(freq_u, 4),
                'freq_in_losses': round(freq_l, 4) if pd.notna(freq_l) else np.nan,
                'freq_in_heavy_losses': round(freq_h, 4) if pd.notna(freq_h) else np.nan,
                'lift_loss': round(lift_l, 4) if pd.notna(lift_l) else np.nan,
                'lift_heavy_loss': round(lift_h, 4) if pd.notna(lift_h) else np.nan,
                'chi2_stat': round(chi2_stat, 4) if pd.notna(chi2_stat) else np.nan,
                'p_value': round(p_val, 6) if pd.notna(p_val) else np.nan,
                'n_universe': n_u, 'n_losses': n_l, 'n_heavy_losses': n_h,
            })
    return pd.DataFrame(rows)
```

- [ ] **Step 4: 在 `trade_attribution_extra.run()` 写出**

```python
    compute_loss_attribution(trades, signals_whitelist).to_csv(
        out_dir / 'loss_attribution.csv', index=False)
```

- [ ] **Step 5: 运行测试**

```bash
python -m pytest my_strategy/tests/test_loss_attribution.py -v
```
Expected: 3 passed.

- [ ] **Step 6: 端到端跑 + 验证**

```bash
cd my_strategy && python backtest.py 2>&1 | tail -5
head -5 my_strategy/reports/loss_attribution.csv
```
Expected: 报告存在；列含 lift_loss / lift_heavy_loss / p_value 等。

- [ ] **Step 7: 全量回归 + Commit**

```bash
python -m pytest -q my_strategy/tests
git add my_strategy/tools/trade_attribution_extra.py my_strategy/tests/test_loss_attribution.py docs/FEATURES.md docs/CHANGELOG.md
git commit -m "feat(phase-b-prep): loss_attribution report (signal frequency lift in losing trades)"
```

---

## Task 9: 端到端验收 + 总结文档

**目的**：完整跑一次 backtest，验证 17 张 Phase 报告（14 旧 + 3 新）齐全；更新 FEATURES.md / CHANGELOG.md 总结。

- [ ] **Step 1: 完整跑一次端到端**

```bash
cd /e/GithubCloneSpace/Stock/backtrader/backtrader/my_strategy && time python backtest.py 2>&1 | tail -20
```
Expected: 6-8 分钟完成（PIT 过滤可能微增）；末尾 `attribution reports written to ...`。

- [ ] **Step 2: 验证 17 张报告齐全**

```bash
cd /e/GithubCloneSpace/Stock/backtrader/backtrader && for f in payoff_metrics signal_stability signal_correlation_matrix multi_factor_combo_stats significance_summary signal_importance_ranking portfolio_risk_metrics losing_streak_stats drawdown_periods concurrent_positions_stats period_alpha rolling_metrics holding_period_curve mfe_timing sector_concentration_stats cost_breakdown loss_attribution; do
  if [ -f "my_strategy/reports/$f.csv" ]; then echo "OK reports/$f.csv"; else echo "MISSING reports/$f.csv"; fi
done
```
Expected: 17 个 OK。

- [ ] **Step 3: 验证关键修复**

```bash
# 1. cost_breakdown overall 行 4 列都不空
python -c "import pandas as pd; d=pd.read_csv('my_strategy/reports/cost_breakdown.csv'); o=d[(d['dimension']=='overall') & (d['bucket']=='all')].iloc[0]; print('gross_pnl:', o['gross_pnl'], 'net_pnl:', o['net_pnl'], 'cost_pct_of_gross:', o['cost_pct_of_gross'])"

# 2. trade_summary 4 新列都有数据
python -c "import pandas as pd; d=pd.read_csv('my_strategy/results/trade_summary.csv'); print(d[['mfe_minus_realized','exit_efficiency','benchmark_return_during_holding','per_trade_alpha']].describe())"

# 3. 无财务因子残留
head -1 my_strategy/reports/trade_profile.csv | tr ',' '\n' | grep -E "factor_pe|factor_roe|factor_netprofit"

# 4. 涨跌停过滤产出
ls -la my_strategy/results/skipped_signals.csv && head -3 my_strategy/results/skipped_signals.csv

# 5. integrity_report 已生成
ls my_strategy/results/integrity_report.csv

# 6. signal_importance_ranking 给出综合排名
head -3 my_strategy/reports/signal_importance_ranking.csv

# 7. rolling_metrics 行数合理
wc -l my_strategy/reports/rolling_metrics.csv

# 8. loss_attribution 给出每个信号的 lift
head -5 my_strategy/reports/loss_attribution.csv
```
Expected: 1 → 三列都不空；2 → describe 有合理数字；3 → 无输出（grep 找不到）；4 → 文件存在 + 数行；5 → 文件存在；6/7/8 → 报告非空。

- [ ] **Step 4: 全量测试一次过**

```bash
python -m pytest -q my_strategy/tests
```
Expected: 全 pass，预计 165-180 个测试。

- [ ] **Step 5: 更新 docs/FEATURES.md（最终版本）**

在 §13（顶层编排）后追加 §14：

```markdown
## 14. 数据健康自检（tools/data_integrity_check.py）

一次性运行的数据层检验：扫描 data/daily/*.csv + stock_list.csv，
输出问题清单到 results/integrity_report.csv，不修复数据本身。

### 调用

    python -m my_strategy.tools.data_integrity_check

### Issue type 与严重等级

| issue_type | severity | 说明 |
|---|---|---|
| missing_trading_day | warning | benchmark 当日交易但本股缺数据 |
| duplicate_date | error | 同一 ts_code 同一日期出现多行 |
| non_monotonic_date | error | trade_date 不是单调递增 |
| abnormal_close_jump | warning | 单日 close 变化超过 ±25% |
| qfq_break | warning | close = 0 或 NaN |
| suspended_period | info | 连续 5 天以上 OHLCV 全相同 |
| not_in_stock_list | warning | daily/ 下有 csv 但 stock_list 不含 |
| in_list_no_data | warning | stock_list 含此股但 daily/ 无文件 |
| list_date_mismatch | warning | daily 第一个 bar 早于 list_date |

## 15. Phase B-prep 新增报告

### 15.1 signal_importance_ranking.csv（trade_attribution_extra）
统一信号重要性排名表：每个白名单信号一行，含 effect_size / t / p / IC / IC_IR / 综合排名。

### 15.2 rolling_metrics.csv（portfolio_attribution）
滚动 252 交易日窗口的 Sharpe / Sortino / win_rate / max_dd 等。

### 15.3 loss_attribution.csv（trade_attribution_extra）
亏损交易里每个信号值的频率 vs 全样本频率（lift_loss / lift_heavy_loss / chi2_p_value）。
```

- [ ] **Step 6: 更新 docs/CHANGELOG.md（Phase B-prep 总结条目）**

在文件顶部加：

```markdown
## 2026-05-08 — Phase B-prep 统计基础与数据可信度建设（9 项）

- 需求：调参（Phase B）启动前先把现有报告做对、做完整。
- 改动：
  - 新增 1 个数据层模块：tools/data_integrity_check.py
  - 修改 2 处策略 / 数据加载：strategy.py 涨跌停过滤、backtest.py PIT universe
  - 清理：财务因子从消费侧彻底移除；cost_breakdown.csv overall 行 bug 修复
  - trade_summary.csv 新增 7 列（mfe_minus_realized / exit_efficiency /
    benchmark_return_during_holding / per_trade_alpha / forward_return_5d/20d/60d）
  - 新增 3 张报告：signal_importance_ranking / rolling_metrics / loss_attribution
- 影响：
  - reports/ 下报告数 14 → 17（不破坏现有 14 张）
  - 全套测试 148 → 约 175
  - 一次 backtest 时间 6:08 → 预期 6-7 分钟（PIT 过滤微增）
```

- [ ] **Step 7: 最终 Commit**

```bash
git add docs/FEATURES.md docs/CHANGELOG.md
git commit -m "docs(phase-b-prep): final FEATURES + CHANGELOG summary for 9-task delivery"
```

- [ ] **Step 8: 推送**

```bash
git push origin master
```

---

## Self-Review Checklist（生成后已执行）

**1. Spec coverage:**
- 数据层 / 策略层 / 报告层三层架构 → Tasks 1 / 2-3 / 4-8
- spec §5.1 (data_integrity) → Task 1
- spec §5.2 (limit-up/down) → Task 2
- spec §5.3 (PIT universe) → Task 3
- spec §5.4 (clean financial + cost bug) → Task 4
- spec §5.5 (trade_summary +4 cols) → Task 5
- spec §5.6 (signal_importance + IC) → Task 6（含 forward_return prep）
- spec §5.7 (rolling_metrics) → Task 7
- spec §5.8 (loss_attribution) → Task 8
- spec §6 (实施顺序) → 同 plan 中 Task 0..8 顺序
- spec §9 (10 条验收) → Task 9 Step 3 全部覆盖

**2. Placeholder scan:** 无 TBD/TODO/详细补全；每个 step 有具体代码块或具体命令；测试代码完整。

**3. Type 一致性:**
- `_resolve_pit_window` 返回 `(fromdate, todate) | None`，调用方做 `if pit is None: continue` 一致
- `compute_signal_importance_ranking` / `compute_loss_attribution` / `compute_rolling_metrics` 都接受 DataFrame 入参、返回 DataFrame
- `trades` 全程使用 `episode` / `entry_date` / `return_pct` 等已知列名（与 trade_summary.csv 实际列一致）

**4. 命名一致:**
- `mfe_minus_realized` / `exit_efficiency` / `benchmark_return_during_holding` / `per_trade_alpha`：在 spec §5.5 与 plan Task 5 完全一致
- `signal_importance_ranking` / `rolling_metrics` / `loss_attribution`：spec §5.6/5.7/5.8 与 plan 完全一致
