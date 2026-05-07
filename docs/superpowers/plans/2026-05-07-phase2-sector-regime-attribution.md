# Phase 2 — 行业指数多空环境快照与归因（实现计划）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在每笔交易入场时记录所属申万一级行业指数的多空环境快照（5 个三态 flag + 1 个 float），并产出 8 张新归因报告，回答"行业多空环境能否进一步过滤个股入场信号"。

**Architecture:** 三个串行子项目：(1) 下载 31 个 SW 一级行业 daily/weekly/monthly 行情 + 构建 `ts_code → sw_index_code` 映射；(2) 重构 `calc_indicators.py` 为参数化（按 groups 列表选择计算哪些指标），生成 `data/sw_indicators/`；(3) `backtest.py` 的 `_compute_regime_flags` 扩展接受 sector_row，新增 6 列写入 trade_summary，`attribution.py` 加 8 张新报告。

**Tech Stack:** Python 3.14+、pandas、Tushare（`sw_daily` + `pro_bar(asset='I')` + `index_member`）、pytest、backtrader

**Spec:** [docs/superpowers/specs/2026-05-07-phase2-sector-regime-attribution-design.md](../specs/2026-05-07-phase2-sector-regime-attribution-design.md)

---

## 子项目 1：数据准备（Task 1-3）

### Task 1: 添加 `download_sw_bars` 函数下载 SW 周/月线

**Files:**
- Modify: `my_strategy/src/downloader_extra.py`（在 `download_sw_index` 后追加新函数）
- Test: `my_strategy/tests/test_downloader_extra.py`

- [ ] **Step 1: 写失败测试**

在 `my_strategy/tests/test_downloader_extra.py` 末尾追加：

```python
def test_download_sw_bars_writes_weekly_ohlcv(tmp_path, monkeypatch):
    """download_sw_bars freq='W' 调用 ts.pro_bar(asset='I', freq='W') 并落盘。"""
    import pandas as pd
    from my_strategy.src import downloader_extra

    captured = {}
    fake_df = pd.DataFrame({
        'ts_code': ['801010.SI'] * 3,
        'trade_date': ['20240105', '20240112', '20240119'],
        'open': [100.0, 101.0, 102.0],
        'high': [105.0, 106.0, 107.0],
        'low': [99.0, 100.0, 101.0],
        'close': [104.0, 105.0, 106.0],
        'vol': [1e9, 1.1e9, 1.2e9],
    })

    def fake_pro_bar(**kwargs):
        captured.update(kwargs)
        return fake_df

    monkeypatch.setattr('tushare.pro_bar', fake_pro_bar)

    out_dir = tmp_path / 'sw_weekly'
    downloader_extra.download_sw_bars(
        '801010.SI', start_date='20240101', end_date='20240131',
        out_dir=out_dir, freq='W', sleep_sec=0,
    )

    assert captured['ts_code'] == '801010.SI'
    assert captured['asset'] == 'I'
    assert captured['freq'] == 'W'
    csv_path = out_dir / '801010.SI.csv'
    assert csv_path.exists()
    df = pd.read_csv(csv_path)
    assert list(df.columns) == ['trade_date', 'open', 'high', 'low', 'close', 'volume']
    assert len(df) == 3


def test_download_sw_bars_skips_when_file_exists(tmp_path, monkeypatch):
    from my_strategy.src import downloader_extra
    out_dir = tmp_path / 'sw_weekly'
    out_dir.mkdir(parents=True)
    (out_dir / '801010.SI.csv').write_text('existing', encoding='utf-8')

    called = {'n': 0}
    def fake_pro_bar(**kwargs):
        called['n'] += 1
        return None
    monkeypatch.setattr('tushare.pro_bar', fake_pro_bar)

    downloader_extra.download_sw_bars(
        '801010.SI', '20240101', '20240131', out_dir, freq='W', sleep_sec=0,
    )
    assert called['n'] == 0  # 文件已存在不重复调用 API
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest my_strategy/tests/test_downloader_extra.py::test_download_sw_bars_writes_weekly_ohlcv -v
```

预期：FAIL（`AttributeError: module 'downloader_extra' has no attribute 'download_sw_bars'`）

- [ ] **Step 3: 实现 `download_sw_bars`**

在 `my_strategy/src/downloader_extra.py` 的 `download_sw_index` 函数之后追加（参照 `downloader.py:121` 的 `download_bars` 模式）：

```python
def download_sw_bars(sw_code, start_date, end_date, out_dir, freq='W',
                    sleep_sec=0.3, force=False):
    """下载申万一级行业指数周/月线（freq='W' 或 'M'），asset='I' 必传。
    与 downloader.download_bars 对称，唯一差别：asset='I' 而非默认股票。
    """
    import pandas as pd, time
    import tushare as ts
    from pathlib import Path

    csv_path = Path(out_dir) / f"{sw_code}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if csv_path.exists() and not force:
        return

    seg = ts.pro_bar(ts_code=sw_code, asset='I', freq=freq,
                     start_date=start_date, end_date=end_date)
    if sleep_sec:
        time.sleep(sleep_sec)
    if seg is None or seg.empty:
        return

    df = seg.rename(columns={'vol': 'volume'})
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.drop_duplicates(subset='trade_date').sort_values('trade_date').reset_index(drop=True)
    df[['trade_date', 'open', 'high', 'low', 'close', 'volume']].to_csv(csv_path, index=False)
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest my_strategy/tests/test_downloader_extra.py -v
```

预期：所有测试通过（含已有测试 + 新增 2 个）

- [ ] **Step 5: Commit**

```bash
git add my_strategy/src/downloader_extra.py my_strategy/tests/test_downloader_extra.py
git commit -m "$(cat <<'EOF'
feat(downloader): add download_sw_bars for SW weekly/monthly OHLCV

Uses ts.pro_bar(asset='I') to fetch SW level-1 industry index bars,
mirrors download_bars but for indices. Caches to {out_dir}/{sw_code}.csv.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `download_all.py` 集成 SW 周/月线下载

**Files:**
- Modify: `my_strategy/download_all.py`（在 SW daily 循环处追加 weekly + monthly）

- [ ] **Step 1: 阅读现有 SW daily 下载代码**

```bash
grep -n "sw_index" my_strategy/download_all.py
```

定位到调用 `download_sw_index` 的循环。

- [ ] **Step 2: 增加 SW 周/月线下载循环**

在现有 `for code in cfg['sw_index_codes']: download_sw_index(...)` 循环之后追加（保留两个独立循环，避免一个 code 拉三次接口造成限速失败时定位困难）：

```python
sw_weekly_dir = data_dir / 'sw_weekly'
for code in cfg['sw_index_codes']:
    download_sw_bars(code, start, end, sw_weekly_dir, freq='W')
    print(f"SW {code} weekly OK")

sw_monthly_dir = data_dir / 'sw_monthly'
for code in cfg['sw_index_codes']:
    download_sw_bars(code, start, end, sw_monthly_dir, freq='M')
    print(f"SW {code} monthly OK")
```

文件顶部 import 处加 `from my_strategy.src.downloader_extra import download_sw_index, download_sw_bars`（如果不在则补全）。

- [ ] **Step 3: 跑全部测试，确认无回归**

```bash
pytest my_strategy/tests/ -v
```

预期：所有测试通过（download_all.py 没单测，但要确保下游测试不挂）。

- [ ] **Step 4: 实际跑下载（仅 SW 部分）**

写一个临时脚本只跑 SW 部分（不重新拉股票），或直接 `python my_strategy/download_all.py`（已有股票数据会因 `if csv_path.exists()` 跳过）。

预计耗时：31 codes × 3 freq = 93 次 API 调用，按 500/min 限速约 12 秒，加 sleep 0.3s × 93 ≈ 30 秒，总计不超过 1 分钟。

验证：
```bash
ls my_strategy/data/sw_index/ | wc -l    # 期望 31
ls my_strategy/data/sw_weekly/ | wc -l   # 期望 31
ls my_strategy/data/sw_monthly/ | wc -l  # 期望 31
```

- [ ] **Step 5: Commit**

```bash
git add my_strategy/download_all.py
git commit -m "$(cat <<'EOF'
feat(download_all): wire SW weekly/monthly download into pipeline

Adds two more loops over cfg['sw_index_codes'] calling download_sw_bars
with freq='W' and 'M', writing to data/sw_weekly/ and sw_monthly/.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

数据 CSV 文件**不进 git**（应该已经在 `.gitignore` 里）。如果不在，**不要**在本任务里添加；提醒用户处理后再继续。

---

### Task 3: 构建 `ts_code → sw_index_code` 映射

**Files:**
- Create: `my_strategy/src/build_sector_mapping.py`（独立脚本）
- Test: `my_strategy/tests/test_build_sector_mapping.py`
- Modify: `my_strategy/data/stock_sector.csv`（实际跑后增加 `sw_index_code` 列）

- [ ] **Step 1: 写失败测试**

创建 `my_strategy/tests/test_build_sector_mapping.py`：

```python
"""build_sector_mapping 单元测试 — 用 mock 替代 Tushare API。"""
import pandas as pd
import pytest


def test_build_mapping_combines_constituents(monkeypatch):
    """31 个 SW 一级行业的成分股合并成 ts_code → sw_code 单值映射。"""
    from my_strategy.src import build_sector_mapping

    fake_members = {
        '801010.SI': pd.DataFrame({
            'con_code': ['000001.SZ', '600000.SH'],
            'in_date': ['20100101', '20100101'],
            'out_date': [None, None],
        }),
        '801030.SI': pd.DataFrame({
            'con_code': ['000002.SZ'],
            'in_date': ['20100101'],
            'out_date': [None],
        }),
    }
    class FakePro:
        def index_member(self, index_code):
            return fake_members.get(index_code, pd.DataFrame(
                columns=['con_code', 'in_date', 'out_date']))

    mapping = build_sector_mapping.fetch_mapping(
        FakePro(), sw_codes=['801010.SI', '801030.SI'])
    assert mapping == {
        '000001.SZ': '801010.SI',
        '600000.SH': '801010.SI',
        '000002.SZ': '801030.SI',
    }


def test_build_mapping_excludes_out_constituents(monkeypatch):
    """out_date 非空的成分（已退出）不进入映射。"""
    from my_strategy.src import build_sector_mapping

    fake_members = {
        '801010.SI': pd.DataFrame({
            'con_code': ['000001.SZ', '999999.SZ'],
            'in_date': ['20100101', '20100101'],
            'out_date': [None, '20200101'],   # 999999 已退出
        }),
    }
    class FakePro:
        def index_member(self, index_code):
            return fake_members[index_code]

    mapping = build_sector_mapping.fetch_mapping(FakePro(), sw_codes=['801010.SI'])
    assert mapping == {'000001.SZ': '801010.SI'}


def test_build_mapping_raises_on_conflict(monkeypatch):
    """同一只股票同时属于两个 SW 行业 → raise。"""
    from my_strategy.src import build_sector_mapping

    fake_members = {
        '801010.SI': pd.DataFrame({
            'con_code': ['000001.SZ'], 'in_date': ['20100101'], 'out_date': [None],
        }),
        '801030.SI': pd.DataFrame({
            'con_code': ['000001.SZ'], 'in_date': ['20100101'], 'out_date': [None],
        }),
    }
    class FakePro:
        def index_member(self, index_code):
            return fake_members[index_code]

    with pytest.raises(ValueError, match='000001.SZ'):
        build_sector_mapping.fetch_mapping(
            FakePro(), sw_codes=['801010.SI', '801030.SI'])


def test_merge_into_stock_sector_csv(tmp_path):
    """fetch_mapping 结果写回 stock_sector.csv 时新增 sw_index_code 列。"""
    from my_strategy.src import build_sector_mapping

    src_csv = tmp_path / 'stock_sector.csv'
    src_csv.write_text(
        'ts_code,industry\n000001.SZ,银行\n600000.SH,银行\n999999.SZ,其他\n',
        encoding='utf-8',
    )
    mapping = {'000001.SZ': '801780.SI', '600000.SH': '801780.SI'}
    coverage = build_sector_mapping.merge_to_csv(src_csv, mapping)

    df = pd.read_csv(src_csv)
    assert list(df.columns) == ['ts_code', 'industry', 'sw_index_code']
    assert df.set_index('ts_code')['sw_index_code'].to_dict() == {
        '000001.SZ': '801780.SI',
        '600000.SH': '801780.SI',
        '999999.SZ': float('nan').__class__.__name__ if False else None,
    } or pd.isna(df.set_index('ts_code').loc['999999.SZ', 'sw_index_code'])
    assert coverage == 2 / 3   # 2/3 股票被映射


def test_merge_raises_when_coverage_below_95(tmp_path):
    """覆盖率 < 95% → raise。"""
    from my_strategy.src import build_sector_mapping

    src_csv = tmp_path / 'stock_sector.csv'
    rows = ['ts_code,industry'] + [f'{i:06d}.SZ,其他' for i in range(100)]
    src_csv.write_text('\n'.join(rows) + '\n', encoding='utf-8')

    mapping = {f'{i:06d}.SZ': '801010.SI' for i in range(50)}  # 50% 覆盖
    with pytest.raises(ValueError, match='覆盖率'):
        build_sector_mapping.merge_to_csv(src_csv, mapping, min_coverage=0.95)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest my_strategy/tests/test_build_sector_mapping.py -v
```

预期：FAIL（模块不存在）

- [ ] **Step 3: 实现 `build_sector_mapping.py`**

创建 `my_strategy/src/build_sector_mapping.py`：

```python
"""构建 ts_code → sw_index_code 映射，写回 stock_sector.csv 新增列。

用法：
    python -m my_strategy.src.build_sector_mapping
"""
import json
import sys
from pathlib import Path

import pandas as pd
import tushare as ts


def fetch_mapping(pro, sw_codes):
    """对每个 SW 一级行业拉成分股清单，构建 ts_code → sw_code 单值映射。

    只取 out_date IS NULL 的当前成分（非时变映射）。
    一对多冲突时 raise。
    """
    mapping = {}
    for sw_code in sw_codes:
        members = pro.index_member(index_code=sw_code)
        if members is None or members.empty:
            print(f"  {sw_code}: 无成分数据，跳过")
            continue
        current = members[members['out_date'].isna()]
        for ts_code in current['con_code'].unique():
            if ts_code in mapping and mapping[ts_code] != sw_code:
                raise ValueError(
                    f"{ts_code} 同时属于 {mapping[ts_code]} 和 {sw_code}，"
                    f"无法构建单值映射")
            mapping[ts_code] = sw_code
    return mapping


def merge_to_csv(stock_sector_csv, mapping, min_coverage=0.95):
    """读取 stock_sector.csv，新增 sw_index_code 列写回。

    覆盖率 < min_coverage 抛 ValueError；95-100% 打印未映射股票数；100% 静默通过。
    返回实际覆盖率（float, 0~1）。
    """
    df = pd.read_csv(stock_sector_csv)
    if 'sw_index_code' in df.columns:
        df = df.drop(columns=['sw_index_code'])
    df['sw_index_code'] = df['ts_code'].map(mapping)

    n_total = len(df)
    n_mapped = df['sw_index_code'].notna().sum()
    coverage = n_mapped / n_total if n_total else 1.0

    if coverage < min_coverage:
        unmapped = df[df['sw_index_code'].isna()]['ts_code'].head(20).tolist()
        raise ValueError(
            f"覆盖率 {coverage:.2%} 低于阈值 {min_coverage:.2%}，"
            f"未映射股票示例（前 20）: {unmapped}")

    if coverage < 1.0:
        unmapped = df[df['sw_index_code'].isna()]['ts_code'].tolist()
        print(f"覆盖率 {coverage:.2%}，未映射 {len(unmapped)} 只股票")

    df.to_csv(stock_sector_csv, index=False)
    return coverage


def main():
    project_root = Path(__file__).resolve().parents[2]
    cfg = json.loads((project_root / 'my_strategy' / 'config.json').read_text(encoding='utf-8'))
    ts.set_token(cfg['tushare_token'])
    pro = ts.pro_api()

    mapping = fetch_mapping(pro, cfg['sw_index_codes'])
    print(f"映射构建完成：{len(mapping)} 只股票")

    stock_sector_csv = project_root / 'my_strategy' / cfg['data_paths']['stock_sector_csv']
    coverage = merge_to_csv(stock_sector_csv, mapping)
    print(f"已写回 {stock_sector_csv}，覆盖率 {coverage:.2%}")


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest my_strategy/tests/test_build_sector_mapping.py -v
```

预期：5 个测试全部通过。

- [ ] **Step 5: 实际跑映射构建**

```bash
python -m my_strategy.src.build_sector_mapping
```

预期输出：
```
映射构建完成：约 5000+ 只股票
已写回 .../stock_sector.csv，覆盖率 9X.XX%
```

如果覆盖率 < 95% 会 raise，停止管线（按 spec 决策）。

验证：
```bash
head -3 my_strategy/data/stock_sector.csv
```
应看到 3 列 `ts_code,industry,sw_index_code`，且 `sw_index_code` 有值。

- [ ] **Step 6: Commit**

```bash
git add my_strategy/src/build_sector_mapping.py my_strategy/tests/test_build_sector_mapping.py my_strategy/data/stock_sector.csv
git commit -m "$(cat <<'EOF'
feat(data): build ts_code -> sw_index_code mapping via index_member API

Adds build_sector_mapping.py with fetch_mapping() (current snapshot,
out_date IS NULL only) and merge_to_csv() (coverage threshold gate).
Updates stock_sector.csv with sw_index_code column.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## 子项目 2：行业指标计算（参数化重构）（Task 4-6）

### Task 4: 重构 `calc_indicators.py` 为参数化

**Files:**
- Modify: `my_strategy/src/calc_indicators.py`（重构主流程）
- Test: `my_strategy/tests/test_calc_indicators.py`（新增 groups 参数测试）

- [ ] **Step 1: 抓取重构前的 stock 模式 baseline（critical for regression test）**

```bash
cd e:/GithubCloneSpace/Stock/backtrader/backtrader
mkdir -p .baseline_calc_indicators
cp my_strategy/data/indicators/000001.SZ.csv .baseline_calc_indicators/
cp my_strategy/data/indicators/600000.SH.csv .baseline_calc_indicators/
cp my_strategy/data/indicators/300750.SZ.csv .baseline_calc_indicators/
```

如果某只样本股不存在 indicators，换成 `ls my_strategy/data/indicators/ | head -3` 取前 3 只实际存在的。记下你选的 3 只，整个 Task 4 都用同一组。

- [ ] **Step 2: 写失败测试（参数化 + 回归）**

在 `my_strategy/tests/test_calc_indicators.py` 末尾追加（如文件不存在则创建）：

```python
def test_compute_indicators_with_only_ma_group(tmp_path):
    """只传 ['ma'] 时输出 CSV 只有基础列 + ma 列，没有 macd/kdj 等。"""
    import pandas as pd
    from my_strategy.src import calc_indicators

    src_daily = tmp_path / 'daily'
    src_daily.mkdir()
    df = pd.DataFrame({
        'trade_date': pd.date_range('2024-01-01', periods=200, freq='D'),
        'open': range(100, 300), 'high': range(105, 305),
        'low': range(95, 295), 'close': range(100, 300),
        'volume': [1e6] * 200, 'amount': [1e8] * 200,
        'pct_chg': [0.01] * 200,
    })
    df.to_csv(src_daily / 'TEST001.csv', index=False)

    dst = tmp_path / 'indicators'
    calc_indicators.compute_indicators(
        code='TEST001',
        src_dirs={'daily': src_daily},
        dst_dir=dst,
        groups=['ma'],
    )

    out = pd.read_csv(dst / 'TEST001.csv')
    assert {'ma25', 'ma60', 'ma144', 'ma180'}.issubset(out.columns)
    assert 'dif' not in out.columns
    assert 'kdj_j' not in out.columns


def test_compute_indicators_with_macd_group(tmp_path):
    """传 ['macd'] 时输出含 dif/dea/macd 但不含 ma/kdj。"""
    import pandas as pd
    from my_strategy.src import calc_indicators

    src_daily = tmp_path / 'daily'
    src_daily.mkdir()
    df = pd.DataFrame({
        'trade_date': pd.date_range('2024-01-01', periods=100, freq='D'),
        'open': range(100, 200), 'high': range(105, 205),
        'low': range(95, 195), 'close': range(100, 200),
        'volume': [1e6] * 100, 'amount': [1e8] * 100,
        'pct_chg': [0.01] * 100,
    })
    df.to_csv(src_daily / 'TEST002.csv', index=False)

    dst = tmp_path / 'indicators'
    calc_indicators.compute_indicators(
        code='TEST002',
        src_dirs={'daily': src_daily},
        dst_dir=dst,
        groups=['macd'],
    )
    out = pd.read_csv(dst / 'TEST002.csv')
    assert {'dif', 'dea', 'macd'}.issubset(out.columns)
    assert 'ma25' not in out.columns


def test_stock_mode_byte_for_byte_regression():
    """重构后 --mode stock 对 3 只样本股输出与重构前 baseline 一致。
    手动跑：
        python -m my_strategy.src.calc_indicators --mode stock
    然后:
        diff .baseline_calc_indicators/000001.SZ.csv my_strategy/data/indicators/000001.SZ.csv
    必须为空。本测试在 CI 中跳过（依赖外部数据），但执行时必须验证。
    """
    import pytest
    pytest.skip("manual regression test; see docstring")
```

- [ ] **Step 3: 跑测试确认失败**

```bash
pytest my_strategy/tests/test_calc_indicators.py -v
```

预期：FAIL（`compute_indicators` 不存在）

- [ ] **Step 4: 重构 `calc_indicators.py`**

打开 `my_strategy/src/calc_indicators.py`，把现有 main 流程重构为：

1. **保留所有现有计算函数**（`add_ma/add_macd/add_kdj/add_week_macd_zone/add_month_macd_zone/merge_daily_basic_fina/merge_sector_momentum/add_factor_*` 等），不改其内部逻辑
2. **抽取参数化主入口** `compute_indicators(code, src_dirs, dst_dir, groups)`：

```python
GROUPS = [
    'ma', 'macd', 'kdj',
    'week_macd', 'month_macd',
    'fundamentals', 'sector_momentum',
    'factor_momentum_60d', 'factor_ma60_dist', 'factor_macd_strength',
]


def compute_indicators(code, src_dirs, dst_dir, groups,
                      sector_map=None, sw_dir=None,
                      daily_basic_dir=None, fina_dir=None):
    """按 groups 列表选择性计算指标，写入 dst_dir/{code}.csv。

    src_dirs: dict 必须含 'daily'，可选 'weekly'/'monthly'。
    sector_map / sw_dir: 仅当 'sector_momentum' in groups 时使用。
    daily_basic_dir / fina_dir: 仅当 'fundamentals' in groups 时使用。
    """
    from pathlib import Path
    import pandas as pd

    src_daily = Path(src_dirs['daily'])
    daily_path = src_daily / f"{code}.csv"
    if not daily_path.exists():
        raise FileNotFoundError(f"daily 数据缺失：{daily_path}")
    df = pd.read_csv(daily_path, parse_dates=['trade_date']).sort_values('trade_date')

    if 'ma' in groups:
        df = add_ma(df)
    if 'macd' in groups:
        df = add_macd(df)
    if 'kdj' in groups:
        df = add_kdj(df)
    if 'week_macd' in groups:
        df = add_week_macd_zone(df, Path(src_dirs['weekly']) / f"{code}.csv")
    if 'month_macd' in groups:
        df = add_month_macd_zone(df, Path(src_dirs['monthly']) / f"{code}.csv")
    if 'fundamentals' in groups:
        df = merge_daily_basic_fina(df, code, daily_basic_dir, fina_dir)
    if 'sector_momentum' in groups:
        sw_code = (sector_map or {}).get(code) if sector_map else None
        if sw_code and sw_dir is not None:
            sw_path = Path(sw_dir) / f"{sw_code}.csv"
            if sw_path.exists():
                sw_df = pd.read_csv(sw_path, parse_dates=['trade_date'])
                df = merge_sector_momentum(df, sw_df)
            else:
                df['factor_sector_momentum_60d'] = pd.NA
        else:
            df['factor_sector_momentum_60d'] = pd.NA
    if 'factor_momentum_60d' in groups:
        df = add_factor_momentum_60d(df)
    if 'factor_ma60_dist' in groups:
        df = add_factor_ma60_dist(df)
    if 'factor_macd_strength' in groups:
        df = add_factor_macd_strength(df)

    Path(dst_dir).mkdir(parents=True, exist_ok=True)
    df.to_csv(Path(dst_dir) / f"{code}.csv", index=False)
```

3. **`main()` 改为读 cfg 后按 mode 调 `compute_indicators`**：

```python
def main():
    import argparse, json, sys
    from pathlib import Path

    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['stock', 'sector'], default='stock')
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2] / 'my_strategy'
    cfg = json.loads((project_root / 'config.json').read_text(encoding='utf-8'))
    profile = cfg['indicator_profiles'][args.mode]
    data_dir = project_root / cfg.get('data_dir', 'data/').rstrip('/')

    if args.mode == 'stock':
        codes = pd.read_csv(project_root / cfg['stock_list_path'])['ts_code'].tolist()
        src_dirs = {'daily': data_dir / 'daily',
                    'weekly': data_dir / 'weekly',
                    'monthly': data_dir / 'monthly'}
        dst_dir = data_dir / 'indicators'
        sector_csv = project_root / cfg['data_paths']['stock_sector_csv']
        sec_df = pd.read_csv(sector_csv)
        sector_map = (dict(zip(sec_df['ts_code'], sec_df['sw_index_code']))
                      if 'sw_index_code' in sec_df.columns else {})
        sw_dir = data_dir / 'sw_index'
        daily_basic_dir = data_dir / 'daily_basic'
        fina_dir = data_dir / 'fina'
    else:  # sector
        codes = cfg['sw_index_codes']
        src_dirs = {'daily': data_dir / 'sw_index',
                    'weekly': data_dir / 'sw_weekly',
                    'monthly': data_dir / 'sw_monthly'}
        dst_dir = data_dir / 'sw_indicators'
        sector_map = None
        sw_dir = None
        daily_basic_dir = None
        fina_dir = None

    for i, code in enumerate(codes):
        try:
            compute_indicators(code, src_dirs, dst_dir, profile,
                              sector_map=sector_map, sw_dir=sw_dir,
                              daily_basic_dir=daily_basic_dir, fina_dir=fina_dir)
            if (i + 1) % 100 == 0:
                print(f"[{i+1}/{len(codes)}] indicators")
        except FileNotFoundError as e:
            print(f"  跳过 {code}: {e}")
```

⚠️ 如果现有的 `add_week_macd_zone` 等函数签名跟上面调用不一致，**修改调用而非函数签名**，避免破坏其他依赖。先 `grep -n "def add_week_macd_zone\|def merge_daily_basic_fina" my_strategy/src/calc_indicators.py` 确认实际签名再改。

- [ ] **Step 5: 加 config.indicator_profiles**

修改 `my_strategy/config.json`，在末尾追加（注意尾部 `}` 前不要漏逗号）：

```json
"indicator_profiles": {
  "stock":  ["ma", "macd", "kdj", "week_macd", "month_macd",
             "fundamentals", "sector_momentum",
             "factor_momentum_60d", "factor_ma60_dist", "factor_macd_strength"],
  "sector": ["ma", "macd", "kdj", "week_macd", "month_macd",
             "factor_momentum_60d"]
}
```

- [ ] **Step 6: 跑单元测试确认通过**

```bash
pytest my_strategy/tests/test_calc_indicators.py -v
```

预期：2 个新增 unit 测试通过（regression 测试 skip）

- [ ] **Step 7: 跑 stock 模式回归验证（byte-for-byte）**

```bash
python -m my_strategy.src.calc_indicators --mode stock
diff .baseline_calc_indicators/000001.SZ.csv my_strategy/data/indicators/000001.SZ.csv
diff .baseline_calc_indicators/600000.SH.csv my_strategy/data/indicators/600000.SH.csv
diff .baseline_calc_indicators/300750.SZ.csv my_strategy/data/indicators/300750.SZ.csv
```

**预期：3 个 diff 全部输出空（exit code 0）。**

如果有差异：
- **不要继续推进**。逐列检查差异源（如某指标计算的浮点精度），定位重构引入的回归并修复
- 修复后重跑直到 diff 为空

- [ ] **Step 8: 跑全部测试，确认无回归**

```bash
pytest my_strategy/tests/ -v
```

- [ ] **Step 9: 清理 baseline 目录并 commit**

```bash
rm -rf .baseline_calc_indicators
git add my_strategy/src/calc_indicators.py my_strategy/tests/test_calc_indicators.py my_strategy/config.json
git commit -m "$(cat <<'EOF'
refactor(calc_indicators): parameterize indicator computation by groups

compute_indicators(code, src_dirs, dst_dir, groups) replaces the hardcoded
main loop. config.indicator_profiles.{stock,sector} drives CLI --mode.
Verified byte-for-byte equivalence on 3 sample stocks vs pre-refactor.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: 跑 sector 模式生成 sw_indicators

**Files:**
- 无代码改动；本任务为执行 + 验收

- [ ] **Step 1: 跑 sector 模式**

```bash
python -m my_strategy.src.calc_indicators --mode sector
```

预期：循环 31 个 SW 代码，无异常退出。

- [ ] **Step 2: 验证产物**

```bash
ls my_strategy/data/sw_indicators/ | wc -l
```
预期 31。

```bash
head -1 my_strategy/data/sw_indicators/801010.SI.csv
```
预期列：`trade_date,open,high,low,close,volume,amount,pct_chg,ma25,ma60,ma144,ma180,dif,dea,macd,kdj_j,week_macd_zone,month_macd_zone,factor_momentum_60d`（顺序可能不同；包含即可）。

- [ ] **Step 3: 抽样校验数值**

```python
import pandas as pd
df = pd.read_csv('my_strategy/data/sw_indicators/801010.SI.csv', parse_dates=['trade_date'])
df = df.sort_values('trade_date').reset_index(drop=True)
# 任取一个有 ma25 的行
row = df[df['ma25'].notna()].iloc[100]
date = row['trade_date']
# 手算 ma25
window = df[df['trade_date'] <= date].tail(25)
manual_ma25 = window['close'].mean()
print('csv ma25:', row['ma25'], 'manual:', manual_ma25)
assert abs(row['ma25'] - manual_ma25) < 1e-6
```

- [ ] **Step 4: 子项目 2 完整验收**

确保以下都通过：
- ✅ `pytest my_strategy/tests/` 全绿
- ✅ Task 4 Step 7 的 byte-for-byte diff 为空
- ✅ `data/sw_indicators/` 31 个 CSV 产出
- ✅ Step 3 的抽样校验匹配

- [ ] **Step 5: 无代码改动则跳过 commit；如需记录可加 docs commit**

数据文件不进 git。如有任何脚本性改动顺手提交，否则继续 Task 6。

---

### Task 6: 子项目 2 验收 checkpoint（无代码改动）

- [ ] **核对子项目 2 spec 验收清单**：[spec §4.3](../specs/2026-05-07-phase2-sector-regime-attribution-design.md)
  - ✅ `compute_indicators` 纯函数实现
  - ✅ config.indicator_profiles 已加
  - ✅ stock 模式 byte-for-byte 一致
  - ✅ `--mode sector` 产出 31 个 CSV
  - ✅ 单测覆盖 groups 参数
  - ✅ 抽样校验 ma25 数值匹配

通过后进入子项目 3。

---

## 子项目 3：入场归因（Task 7-13）

### Task 7: 扩展 `_compute_regime_flags` 接受 sector_row

**Files:**
- Modify: `my_strategy/backtest.py:132-168`（`_compute_regime_flags`）
- Test: `my_strategy/tests/test_backtest.py`

- [ ] **Step 1: 写失败测试**

在 `my_strategy/tests/test_backtest.py` 末尾追加：

```python
def test_regime_flags_sector_bull_align_true():
    import pandas as pd
    from my_strategy.backtest import _compute_regime_flags

    stock_row = pd.Series({'close': 10, 'ma25': 9, 'ma60': 8, 'ma144': 7, 'ma180': 6})
    hs300_row = pd.Series({'dif': 1.0, 'ma25': 4000, 'ma60': 3900, 'ma144': 3800, 'ma180': 3700})
    sector_row = pd.Series({
        'close': 100, 'ma25': 95, 'ma60': 90, 'ma144': 85, 'ma180': 80,
        'dif': 0.5, 'week_macd_zone': '多头', 'month_macd_zone': '震荡',
        'factor_momentum_60d': 0.12,
    })
    f = _compute_regime_flags(stock_row, hs300_row, sector_row)
    assert f['entry_sector_bull_align'] is True
    assert f['entry_sector_above_ma25'] is True
    assert f['entry_sector_dif_above_zero'] is True
    assert f['entry_sector_week_macd_zone'] == '多头'
    assert f['entry_sector_month_macd_zone'] == '震荡'
    assert f['entry_sector_momentum_60d'] == 0.12


def test_regime_flags_sector_bull_align_false():
    import pandas as pd
    from my_strategy.backtest import _compute_regime_flags

    stock_row = pd.Series({'close': 10, 'ma25': 9, 'ma60': 8, 'ma144': 7, 'ma180': 6})
    hs300_row = pd.Series({'dif': 1.0, 'ma25': 4000, 'ma60': 3900, 'ma144': 3800, 'ma180': 3700})
    sector_row = pd.Series({
        'close': 100, 'ma25': 95, 'ma60': 96, 'ma144': 85, 'ma180': 80,  # ma25 < ma60 破坏多头
        'dif': -0.1, 'week_macd_zone': '空头', 'month_macd_zone': '空头',
        'factor_momentum_60d': -0.05,
    })
    f = _compute_regime_flags(stock_row, hs300_row, sector_row)
    assert f['entry_sector_bull_align'] is False
    assert f['entry_sector_dif_above_zero'] is False


def test_regime_flags_sector_none_returns_six_none_values():
    """sector_row=None 时 6 个 entry_sector_* 全为 None/NaN（缺数据三态语义）。"""
    import pandas as pd, math
    from my_strategy.backtest import _compute_regime_flags

    stock_row = pd.Series({'close': 10, 'ma25': 9, 'ma60': 8, 'ma144': 7, 'ma180': 6})
    hs300_row = pd.Series({'dif': 1.0, 'ma25': 4000, 'ma60': 3900, 'ma144': 3800, 'ma180': 3700})
    f = _compute_regime_flags(stock_row, hs300_row, None)
    assert f['entry_sector_bull_align'] is None
    assert f['entry_sector_above_ma25'] is None
    assert f['entry_sector_dif_above_zero'] is None
    assert f['entry_sector_week_macd_zone'] is None
    assert f['entry_sector_month_macd_zone'] is None
    assert math.isnan(f['entry_sector_momentum_60d'])


def test_regime_flags_sector_partial_nan():
    """sector_row.ma180 缺失时 bull_align=None，但其他 flag 不受影响。"""
    import pandas as pd
    from my_strategy.backtest import _compute_regime_flags

    stock_row = pd.Series({'close': 10, 'ma25': 9, 'ma60': 8, 'ma144': 7, 'ma180': 6})
    hs300_row = pd.Series({'dif': 1.0, 'ma25': 4000, 'ma60': 3900, 'ma144': 3800, 'ma180': 3700})
    sector_row = pd.Series({
        'close': 100, 'ma25': 95, 'ma60': 90, 'ma144': 85, 'ma180': float('nan'),
        'dif': 0.5, 'week_macd_zone': '多头', 'month_macd_zone': '震荡',
        'factor_momentum_60d': 0.12,
    })
    f = _compute_regime_flags(stock_row, hs300_row, sector_row)
    assert f['entry_sector_bull_align'] is None
    assert f['entry_sector_above_ma25'] is True
    assert f['entry_sector_dif_above_zero'] is True


def test_regime_flags_existing_phase1_flags_unchanged():
    """Phase 1 的 4 个 flag 在新签名下仍正常工作（回归）。"""
    import pandas as pd
    from my_strategy.backtest import _compute_regime_flags

    stock_row = pd.Series({'close': 10, 'ma25': 9, 'ma60': 8, 'ma144': 7, 'ma180': 6})
    hs300_row = pd.Series({'dif': 1.0, 'ma25': 4000, 'ma60': 3900, 'ma144': 3800, 'ma180': 3700})
    f = _compute_regime_flags(stock_row, hs300_row, None)  # sector=None
    assert f['entry_hs300_dif_above_zero'] is True
    assert f['entry_hs300_bull_align'] is True
    assert f['entry_stock_bull_align'] is True
    assert f['entry_stock_above_ma25'] is True
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest my_strategy/tests/test_backtest.py -v -k regime_flags_sector
```

预期：FAIL（`_compute_regime_flags` 当前签名只接受 2 个参数）

- [ ] **Step 3: 修改 `_compute_regime_flags`**

打开 [my_strategy/backtest.py:132](my_strategy/backtest.py#L132)，修改函数签名和 body：

```python
def _compute_regime_flags(stock_row, hs300_row, sector_row):
    """计算入场时刻 4+6 = 10 个环境标志。

    sector_row=None 时 6 个 entry_sector_* 为 None（数值列为 NaN）。
    """
    def _bull_align(row):
        if row is None:
            return None
        m25, m60, m144, m180 = row.get('ma25'), row.get('ma60'), row.get('ma144'), row.get('ma180')
        if pd.isna(m25) or pd.isna(m60) or pd.isna(m144) or pd.isna(m180):
            return None
        return bool(m25 > m60 > m144 > m180)

    # ===== Phase 1（保持不变）=====
    s_close = stock_row.get('close')
    s_ma25 = stock_row.get('ma25')
    if pd.isna(s_close) or pd.isna(s_ma25):
        stock_above_ma25 = None
    else:
        stock_above_ma25 = bool(s_close > s_ma25)

    if hs300_row is None:
        hs300_dif_above = None
    else:
        dif = hs300_row.get('dif')
        hs300_dif_above = None if pd.isna(dif) else bool(dif > 0)

    # ===== Phase 2 新增 =====
    if sector_row is None:
        sector_above_ma25 = None
        sector_dif_above = None
        sector_week_zone = None
        sector_month_zone = None
        sector_momentum = float('nan')
    else:
        s2_close = sector_row.get('close')
        s2_ma25 = sector_row.get('ma25')
        if pd.isna(s2_close) or pd.isna(s2_ma25):
            sector_above_ma25 = None
        else:
            sector_above_ma25 = bool(s2_close > s2_ma25)

        s2_dif = sector_row.get('dif')
        sector_dif_above = None if pd.isna(s2_dif) else bool(s2_dif > 0)

        wz = sector_row.get('week_macd_zone')
        sector_week_zone = None if (wz is None or (isinstance(wz, float) and pd.isna(wz))) else str(wz)
        mz = sector_row.get('month_macd_zone')
        sector_month_zone = None if (mz is None or (isinstance(mz, float) and pd.isna(mz))) else str(mz)

        mom = sector_row.get('factor_momentum_60d')
        sector_momentum = float(mom) if not pd.isna(mom) else float('nan')

    return {
        'entry_hs300_dif_above_zero': hs300_dif_above,
        'entry_hs300_bull_align': _bull_align(hs300_row),
        'entry_stock_bull_align': _bull_align(stock_row),
        'entry_stock_above_ma25': stock_above_ma25,
        'entry_sector_bull_align': _bull_align(sector_row),
        'entry_sector_above_ma25': sector_above_ma25,
        'entry_sector_dif_above_zero': sector_dif_above,
        'entry_sector_week_macd_zone': sector_week_zone,
        'entry_sector_month_macd_zone': sector_month_zone,
        'entry_sector_momentum_60d': sector_momentum,
    }
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest my_strategy/tests/test_backtest.py -v
```

5 个新增测试 + 现有测试全部通过。

- [ ] **Step 5: Commit**

```bash
git add my_strategy/backtest.py my_strategy/tests/test_backtest.py
git commit -m "$(cat <<'EOF'
feat(backtest): extend _compute_regime_flags with sector_row

Adds 6 new keys (entry_sector_*) to flag dict:
- bull_align (bool/None): ma25>ma60>ma144>ma180 on sector index
- above_ma25 (bool/None): close > ma25 on sector index
- dif_above_zero (bool/None): sector MACD DIF > 0
- week/month_macd_zone (str/None): pass-through from sector_row
- momentum_60d (float/NaN): pass-through factor_momentum_60d

sector_row=None preserves tri-state semantics (None / NaN for momentum).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: backtest.py 加载 sector_indicators 并 enrich

**Files:**
- Modify: `my_strategy/backtest.py`（加载阶段 + enrich 阶段）

- [ ] **Step 1: 找到现有 HS300 加载和 enrich 代码**

```bash
grep -n "hs300\|HS300\|enriched_rows" my_strategy/backtest.py | head -30
```

记录：
- HS300 indicators 加载在哪行（典型为 `_load_hs300_indicators` 或类似）
- enrich 循环在哪行（应该围绕 `_compute_regime_flags(r, hs300_row)` 这一行）

- [ ] **Step 2: 加载 sector_indicators 字典**

在加载 HS300 indicators 之后追加：

```python
def _load_sector_indicators(cfg, project_root):
    """加载 31 个 SW 一级行业 indicators，返回 dict[sw_code -> DataFrame]."""
    import pandas as pd
    from pathlib import Path
    sw_indicators_dir = project_root / cfg['data_dir'].rstrip('/') / 'sw_indicators'
    out = {}
    for sw_code in cfg['sw_index_codes']:
        path = sw_indicators_dir / f"{sw_code}.csv"
        if path.exists():
            df = pd.read_csv(path, parse_dates=['trade_date'])
            out[sw_code] = df.set_index('trade_date')
        else:
            print(f"  [warn] sector indicator 缺失：{path}")
    return out


def _load_sector_map(cfg, project_root):
    """加载 ts_code -> sw_index_code 映射。"""
    import pandas as pd
    sec_csv = project_root / cfg['data_paths']['stock_sector_csv']
    df = pd.read_csv(sec_csv)
    if 'sw_index_code' not in df.columns:
        raise ValueError(f"{sec_csv} 缺 sw_index_code 列，先跑 build_sector_mapping")
    df = df.dropna(subset=['sw_index_code'])
    return dict(zip(df['ts_code'], df['sw_index_code']))
```

在 main 流程加载 HS300 后调用：

```python
sector_indicators = _load_sector_indicators(cfg, project_root)
sector_map = _load_sector_map(cfg, project_root)
```

- [ ] **Step 3: enrich 阶段取 sector_row 并传入**

定位现有调 `_compute_regime_flags(r, hs300_row)` 的地方（约 [backtest.py:305](my_strategy/backtest.py#L305)），改成：

```python
# 取 sector_row（按 ts_code → sw_code → sector_indicators[sw_code] → 入场日 row）
ts_code = row.get('ts_code')
entry_date = pd.to_datetime(row.get('entry_date'))
sw_code = sector_map.get(ts_code)
sector_row = None
if sw_code and sw_code in sector_indicators:
    sec_df = sector_indicators[sw_code]
    if entry_date in sec_df.index:
        sector_row = sec_df.loc[entry_date]
        if isinstance(sector_row, pd.DataFrame):
            sector_row = sector_row.iloc[0]

flags = _compute_regime_flags(r, hs300_row, sector_row)
# 写回所有 10 个 flag（4 个旧 + 6 个新）
row['entry_hs300_dif_above_zero'] = flags['entry_hs300_dif_above_zero']
row['entry_hs300_bull_align'] = flags['entry_hs300_bull_align']
row['entry_stock_bull_align'] = flags['entry_stock_bull_align']
row['entry_stock_above_ma25'] = flags['entry_stock_above_ma25']
row['entry_sector_bull_align'] = flags['entry_sector_bull_align']
row['entry_sector_above_ma25'] = flags['entry_sector_above_ma25']
row['entry_sector_dif_above_zero'] = flags['entry_sector_dif_above_zero']
row['entry_sector_week_macd_zone'] = flags['entry_sector_week_macd_zone']
row['entry_sector_month_macd_zone'] = flags['entry_sector_month_macd_zone']
row['entry_sector_momentum_60d'] = flags['entry_sector_momentum_60d']
```

同时更新现有所有"缺数据填 None"的分支（约 [backtest.py:248-252](my_strategy/backtest.py#L248-L252) 和 [backtest.py:319-322](my_strategy/backtest.py#L319-L322)），加 6 个新列的 None/NaN 默认值。

- [ ] **Step 4: 更新 dtype 处理**

定位 [backtest.py:329-331](my_strategy/backtest.py#L329-L331) 的 `astype(object)` 处理，加入 5 个新的三态列：

```python
for col in ('entry_hs300_dif_above_zero', 'entry_hs300_bull_align',
            'entry_stock_bull_align', 'entry_stock_above_ma25',
            'entry_sector_bull_align', 'entry_sector_above_ma25',
            'entry_sector_dif_above_zero',
            'entry_sector_week_macd_zone', 'entry_sector_month_macd_zone'):
    if col in result.columns:
        result[col] = result[col].astype(object)
```

`entry_sector_momentum_60d` 是 float，**不**进这个循环。

- [ ] **Step 5: 跑回测，验证 trade_summary 列**

```bash
python my_strategy/backtest.py 2>&1 | tail -30
```

回测完成后：
```python
import pandas as pd
df = pd.read_csv('my_strategy/results/trade_summary.csv')
print('cols:', list(df.columns))
print('sector cols present:', set(df.columns) >= {
    'entry_sector_bull_align', 'entry_sector_above_ma25',
    'entry_sector_dif_above_zero',
    'entry_sector_week_macd_zone', 'entry_sector_month_macd_zone',
    'entry_sector_momentum_60d',
})
print('sample non-null counts:')
for c in ['entry_sector_bull_align', 'entry_sector_above_ma25',
          'entry_sector_dif_above_zero', 'entry_sector_momentum_60d']:
    print(f'  {c}: {df[c].notna().sum()} / {len(df)}')
```

预期：6 个新列存在，绝大多数行非 None（因 stock_sector 覆盖率 ≥ 95%）。

- [ ] **Step 6: 跑全部测试，确认无回归**

```bash
pytest my_strategy/tests/ -v
```

预期：全绿（Phase 1 4 个 flag 计算应未受影响）。

- [ ] **Step 7: Commit**

```bash
git add my_strategy/backtest.py
git commit -m "$(cat <<'EOF'
feat(backtest): record 6 entry_sector_* flags in trade_summary

Loads sector_indicators (31 SW level-1 industry CSVs) and ts_code->sw_code
mapping at backtest start. enrich phase looks up entry-date row from
sector_indicators via mapping, passes to _compute_regime_flags. Writes 6
new columns to trade_summary (5 tri-state + 1 float).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: 添加 5 张三态 flag stats 报告

**Files:**
- Modify: `my_strategy/tools/attribution.py`（追加 5 个 compute 函数 + run() 集成）
- Test: `my_strategy/tests/test_attribution.py`

5 张报告：`sector_bull_align_stats`, `sector_above_ma25_stats`, `sector_dif_stats`, `sector_week_macd_stats`, `sector_month_macd_stats`。前 3 个走 `_compute_bool_flag_stats`，后 2 个是字符串桶（"多头"/"空头"/"震荡"）需新写 helper。

- [ ] **Step 1: 写失败测试**

在 `my_strategy/tests/test_attribution.py` 末尾追加：

```python
def test_sector_bull_align_stats_two_buckets():
    import pandas as pd
    from my_strategy.tools.attribution import compute_sector_bull_align_stats
    trades = pd.DataFrame({
        'entry_sector_bull_align': [True, True, False, False, None],
        'return_pct': [0.05, -0.02, 0.01, -0.10, 0.00],
        'holding_days': [10, 5, 7, 12, 3],
    })
    out = compute_sector_bull_align_stats(trades)
    assert list(out['flag_value']) == ['True', 'False']
    assert out.iloc[0]['count'] == 2 and out.iloc[1]['count'] == 2


def test_sector_above_ma25_stats():
    import pandas as pd
    from my_strategy.tools.attribution import compute_sector_above_ma25_stats
    trades = pd.DataFrame({
        'entry_sector_above_ma25': [True, False],
        'return_pct': [0.10, -0.05],
        'holding_days': [10, 5],
    })
    out = compute_sector_above_ma25_stats(trades)
    assert len(out) == 2


def test_sector_dif_stats():
    import pandas as pd
    from my_strategy.tools.attribution import compute_sector_dif_stats
    trades = pd.DataFrame({
        'entry_sector_dif_above_zero': [True, False, True],
        'return_pct': [0.05, -0.02, 0.03],
        'holding_days': [10, 5, 7],
    })
    out = compute_sector_dif_stats(trades)
    assert out.set_index('flag_value').loc['True', 'count'] == 2


def test_sector_week_macd_stats_three_buckets():
    """字符串桶：'多头'/'空头'/'震荡'。"""
    import pandas as pd
    from my_strategy.tools.attribution import compute_sector_week_macd_stats
    trades = pd.DataFrame({
        'entry_sector_week_macd_zone': ['多头', '多头', '空头', '震荡', None],
        'return_pct': [0.05, 0.03, -0.02, 0.01, 0.00],
        'holding_days': [10, 5, 7, 12, 3],
    })
    out = compute_sector_week_macd_stats(trades)
    assert set(out['zone']) == {'多头', '空头', '震荡'}
    assert out.set_index('zone').loc['多头', 'count'] == 2


def test_sector_month_macd_stats_three_buckets():
    import pandas as pd
    from my_strategy.tools.attribution import compute_sector_month_macd_stats
    trades = pd.DataFrame({
        'entry_sector_month_macd_zone': ['多头', '空头', '空头'],
        'return_pct': [0.05, -0.02, -0.05],
        'holding_days': [10, 5, 7],
    })
    out = compute_sector_month_macd_stats(trades)
    assert out.set_index('zone').loc['空头', 'count'] == 2
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest my_strategy/tests/test_attribution.py -v -k sector
```

预期：FAIL（5 个函数未定义）

- [ ] **Step 3: 实现 5 个 compute 函数**

在 `my_strategy/tools/attribution.py` 的 `compute_stock_above_ma25_stats` 之后追加（约 [attribution.py:516](my_strategy/tools/attribution.py#L516) 之后）：

```python
def compute_sector_bull_align_stats(trades):
    """按 entry_sector_bull_align 分桶（行业指数多头排列）。"""
    return _compute_bool_flag_stats(trades, 'entry_sector_bull_align')


def compute_sector_above_ma25_stats(trades):
    """按 entry_sector_above_ma25 分桶（行业指数 close > ma25）。"""
    return _compute_bool_flag_stats(trades, 'entry_sector_above_ma25')


def compute_sector_dif_stats(trades):
    """按 entry_sector_dif_above_zero 分桶（行业 MACD DIF > 0）。"""
    return _compute_bool_flag_stats(trades, 'entry_sector_dif_above_zero')


def _compute_zone_stats(trades, zone_col):
    """对字符串桶（如 '多头'/'空头'/'震荡'）做聚合。"""
    cols = ['zone', 'count', 'win_rate', 'avg_return', 'avg_holding_days']
    if trades.empty or zone_col not in trades.columns:
        return pd.DataFrame(columns=cols)
    sub = trades.dropna(subset=[zone_col]).copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    for zone, chunk in sub.groupby(zone_col):
        ret = chunk['return_pct'].dropna() if 'return_pct' in chunk.columns else pd.Series(dtype=float)
        hold = chunk['holding_days'].dropna() if 'holding_days' in chunk.columns else pd.Series(dtype=float)
        rows.append({
            'zone': zone,
            'count': len(chunk),
            'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
            'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
            'avg_holding_days': round(hold.mean(), 1) if len(hold) else float('nan'),
        })
    return pd.DataFrame(rows, columns=cols).reset_index(drop=True)


def compute_sector_week_macd_stats(trades):
    """按 entry_sector_week_macd_zone 字符串桶聚合。"""
    return _compute_zone_stats(trades, 'entry_sector_week_macd_zone')


def compute_sector_month_macd_stats(trades):
    """按 entry_sector_month_macd_zone 字符串桶聚合。"""
    return _compute_zone_stats(trades, 'entry_sector_month_macd_zone')
```

- [ ] **Step 4: 在 `attribution.run()` 接入 5 张报告**

定位 `def run(...)` 函数（搜索 `attribution.run` 或 `def run`），在 Phase 1 写 `regime_combo_stats.csv` 之后追加：

```python
compute_sector_bull_align_stats(trades).to_csv(out_dir / 'sector_bull_align_stats.csv', index=False)
compute_sector_above_ma25_stats(trades).to_csv(out_dir / 'sector_above_ma25_stats.csv', index=False)
compute_sector_dif_stats(trades).to_csv(out_dir / 'sector_dif_stats.csv', index=False)
compute_sector_week_macd_stats(trades).to_csv(out_dir / 'sector_week_macd_stats.csv', index=False)
compute_sector_month_macd_stats(trades).to_csv(out_dir / 'sector_month_macd_stats.csv', index=False)
```

⚠️ trade_summary 读取时三态列需要 cast 还原。检查现有 read_csv 后是否有 `entry_*` 列的 bool 三态还原逻辑（参照 commit `b32d377`）。如有，扩展加入新的 5 个 entry_sector_* 三态列；如不在 attribution.py 而在 backtest.py 的 enrich 阶段，本 task 无需改读取。

- [ ] **Step 5: 跑测试确认通过**

```bash
pytest my_strategy/tests/test_attribution.py -v -k sector
```

预期：5 个测试通过。

- [ ] **Step 6: Commit**

```bash
git add my_strategy/tools/attribution.py my_strategy/tests/test_attribution.py
git commit -m "$(cat <<'EOF'
feat(attribution): 5 sector regime flag stats reports

- sector_bull_align_stats / above_ma25_stats / dif_stats:
  reuse _compute_bool_flag_stats (3 tri-state buckets)
- sector_week_macd_stats / month_macd_stats:
  new _compute_zone_stats helper for string buckets
  ('多头' / '空头' / '震荡')

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: 添加 momentum_60d 五分桶报告

**Files:**
- Modify: `my_strategy/tools/attribution.py`
- Test: `my_strategy/tests/test_attribution.py`

- [ ] **Step 1: 写失败测试**

在 test_attribution.py 末尾追加：

```python
def test_sector_momentum_60d_stats_quintile():
    """五分桶 by quintile (Q1-Q5)，每桶约 20% 样本。"""
    import pandas as pd
    from my_strategy.tools.attribution import compute_sector_momentum_60d_stats

    trades = pd.DataFrame({
        'entry_sector_momentum_60d': [round(i * 0.01, 4) for i in range(100)],  # -0.00 ~ 0.99
        'return_pct': [0.01 * (i % 5 - 2) for i in range(100)],
        'holding_days': list(range(100)),
    })
    out = compute_sector_momentum_60d_stats(trades)
    assert list(out['quintile']) == ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']
    assert all(out['count'] == 20)


def test_sector_momentum_60d_stats_handles_nan():
    import pandas as pd
    from my_strategy.tools.attribution import compute_sector_momentum_60d_stats
    trades = pd.DataFrame({
        'entry_sector_momentum_60d': [0.1, 0.2, float('nan'), 0.05, 0.15],
        'return_pct': [0.01, 0.02, 0.03, 0.04, 0.05],
        'holding_days': [10, 5, 7, 8, 9],
    })
    out = compute_sector_momentum_60d_stats(trades)
    # NaN 行 dropna 跳过，剩 4 行分 5 桶时退化（每桶 0-1 个）
    assert out['count'].sum() == 4


def test_sector_momentum_60d_stats_empty_returns_empty_frame():
    import pandas as pd
    from my_strategy.tools.attribution import compute_sector_momentum_60d_stats
    trades = pd.DataFrame()
    out = compute_sector_momentum_60d_stats(trades)
    assert out.empty
    assert list(out.columns) == ['quintile', 'momentum_lo', 'momentum_hi',
                                  'count', 'win_rate', 'avg_return', 'avg_holding_days']
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest my_strategy/tests/test_attribution.py::test_sector_momentum_60d_stats_quintile -v
```

预期：FAIL

- [ ] **Step 3: 实现 `compute_sector_momentum_60d_stats`**

在 `attribution.py` 的 `compute_sector_month_macd_stats` 之后追加：

```python
def compute_sector_momentum_60d_stats(trades):
    """按 entry_sector_momentum_60d 五分桶（Q1=最低, Q5=最高）聚合。"""
    cols = ['quintile', 'momentum_lo', 'momentum_hi',
            'count', 'win_rate', 'avg_return', 'avg_holding_days']
    if trades.empty or 'entry_sector_momentum_60d' not in trades.columns:
        return pd.DataFrame(columns=cols)
    sub = trades.dropna(subset=['entry_sector_momentum_60d']).copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    sub['_q'] = pd.qcut(sub['entry_sector_momentum_60d'],
                       q=5, labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'],
                       duplicates='drop')
    rows = []
    for q in ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']:
        chunk = sub[sub['_q'] == q]
        if chunk.empty:
            continue
        ret = chunk['return_pct'].dropna() if 'return_pct' in chunk.columns else pd.Series(dtype=float)
        hold = chunk['holding_days'].dropna() if 'holding_days' in chunk.columns else pd.Series(dtype=float)
        rows.append({
            'quintile': q,
            'momentum_lo': round(chunk['entry_sector_momentum_60d'].min(), 4),
            'momentum_hi': round(chunk['entry_sector_momentum_60d'].max(), 4),
            'count': len(chunk),
            'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
            'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
            'avg_holding_days': round(hold.mean(), 1) if len(hold) else float('nan'),
        })
    return pd.DataFrame(rows, columns=cols).reset_index(drop=True)
```

接入 `attribution.run()`：

```python
compute_sector_momentum_60d_stats(trades).to_csv(out_dir / 'sector_momentum_60d_stats.csv', index=False)
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest my_strategy/tests/test_attribution.py -v -k momentum_60d
```

- [ ] **Step 5: Commit**

```bash
git add my_strategy/tools/attribution.py my_strategy/tests/test_attribution.py
git commit -m "$(cat <<'EOF'
feat(attribution): sector_momentum_60d_stats with quintile buckets

5-bucket aggregation by sector index 60-day return percentile (Q1=lowest,
Q5=highest). Uses pandas.qcut(duplicates='drop') for robust binning.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: 添加 industry stats 报告（按 31 个 SW 行业分桶）

**Files:**
- Modify: `my_strategy/tools/attribution.py`
- Test: `my_strategy/tests/test_attribution.py`

- [ ] **Step 1: 写失败测试**

```python
def test_sector_industry_stats_groups_by_sw_code():
    """按 ts_code 反查 sw_index_code 分桶聚合。"""
    import pandas as pd
    from my_strategy.tools.attribution import compute_sector_industry_stats

    trades = pd.DataFrame({
        'ts_code': ['000001.SZ', '600000.SH', '000002.SZ', '300750.SZ'],
        'return_pct': [0.10, -0.05, 0.03, 0.20],
        'holding_days': [10, 5, 7, 8],
    })
    sector_map = {
        '000001.SZ': '801780.SI',
        '600000.SH': '801780.SI',
        '000002.SZ': '801180.SI',
        '300750.SZ': '801880.SI',
    }
    out = compute_sector_industry_stats(trades, sector_map)
    assert set(out['sw_index_code']) == {'801780.SI', '801180.SI', '801880.SI'}
    bank = out.set_index('sw_index_code').loc['801780.SI']
    assert bank['count'] == 2


def test_sector_industry_stats_skips_unmapped():
    """ts_code 不在 sector_map 中 → dropna 跳过。"""
    import pandas as pd
    from my_strategy.tools.attribution import compute_sector_industry_stats
    trades = pd.DataFrame({
        'ts_code': ['000001.SZ', 'UNKNOWN.SZ'],
        'return_pct': [0.05, 0.03],
        'holding_days': [10, 5],
    })
    sector_map = {'000001.SZ': '801780.SI'}
    out = compute_sector_industry_stats(trades, sector_map)
    assert len(out) == 1
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest my_strategy/tests/test_attribution.py -v -k industry
```

- [ ] **Step 3: 实现 `compute_sector_industry_stats`**

```python
def compute_sector_industry_stats(trades, sector_map):
    """按 ts_code → sw_index_code 映射后，按 31 个 SW 一级行业分桶聚合。"""
    cols = ['sw_index_code', 'count', 'win_rate', 'avg_return', 'avg_holding_days']
    if trades.empty or 'ts_code' not in trades.columns:
        return pd.DataFrame(columns=cols)
    sub = trades.copy()
    sub['_sw'] = sub['ts_code'].map(sector_map)
    sub = sub.dropna(subset=['_sw'])
    if sub.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    for sw_code, chunk in sub.groupby('_sw'):
        ret = chunk['return_pct'].dropna() if 'return_pct' in chunk.columns else pd.Series(dtype=float)
        hold = chunk['holding_days'].dropna() if 'holding_days' in chunk.columns else pd.Series(dtype=float)
        rows.append({
            'sw_index_code': sw_code,
            'count': len(chunk),
            'win_rate': round((ret > 0).mean(), 4) if len(ret) else float('nan'),
            'avg_return': round(ret.mean(), 4) if len(ret) else float('nan'),
            'avg_holding_days': round(hold.mean(), 1) if len(hold) else float('nan'),
        })
    return pd.DataFrame(rows, columns=cols).sort_values('count', ascending=False).reset_index(drop=True)
```

接入 `attribution.run()` 时需要传 sector_map。在 run() 函数加载阶段读 stock_sector.csv：

```python
sector_map = {}
sec_csv = ... / cfg['data_paths']['stock_sector_csv']
if sec_csv.exists():
    sec_df = pd.read_csv(sec_csv)
    if 'sw_index_code' in sec_df.columns:
        sec_df = sec_df.dropna(subset=['sw_index_code'])
        sector_map = dict(zip(sec_df['ts_code'], sec_df['sw_index_code']))

compute_sector_industry_stats(trades, sector_map).to_csv(
    out_dir / 'sector_industry_stats.csv', index=False)
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest my_strategy/tests/test_attribution.py -v -k industry
```

- [ ] **Step 5: Commit**

```bash
git add my_strategy/tools/attribution.py my_strategy/tests/test_attribution.py
git commit -m "$(cat <<'EOF'
feat(attribution): sector_industry_stats — per-SW-industry breakdown

Groups trades by sw_index_code (looked up via sector_map: ts_code -> sw_code)
and reports count/win_rate/avg_return/avg_holding_days per industry. Sorted
by trade count descending.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: 添加 sector × stock 2×2 combo 报告

**Files:**
- Modify: `my_strategy/tools/attribution.py`
- Test: `my_strategy/tests/test_attribution.py`

- [ ] **Step 1: 写失败测试**

```python
def test_sector_stock_combo_stats_2x2():
    """sector_bull_align × stock_bull_align 2x2 交叉表。"""
    import pandas as pd
    from my_strategy.tools.attribution import compute_sector_stock_combo_stats

    trades = pd.DataFrame({
        'entry_sector_bull_align': [True, True, False, False, True, False],
        'entry_stock_bull_align':  [True, False, True, False, True, False],
        'return_pct': [0.10, 0.05, -0.02, -0.08, 0.15, -0.03],
        'holding_days': [10, 5, 7, 12, 8, 6],
    })
    out = compute_sector_stock_combo_stats(trades)
    assert len(out) == 4
    assert set(out['combo']) == {
        '行业多头+个股多头', '行业多头+个股非多头',
        '行业非多头+个股多头', '行业非多头+个股非多头',
    }


def test_sector_stock_combo_stats_drops_none():
    """缺任一 flag 的行 dropna 跳过。"""
    import pandas as pd
    from my_strategy.tools.attribution import compute_sector_stock_combo_stats
    trades = pd.DataFrame({
        'entry_sector_bull_align': [True, None, False],
        'entry_stock_bull_align':  [True, True, False],
        'return_pct': [0.10, 0.05, -0.02],
        'holding_days': [10, 5, 7],
    })
    out = compute_sector_stock_combo_stats(trades)
    # 第二行被 dropna 跳过，剩 2 行分 2 桶
    assert out['count'].sum() == 2
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest my_strategy/tests/test_attribution.py -v -k combo_stats
```

- [ ] **Step 3: 实现 `compute_sector_stock_combo_stats`**

参照现有 `compute_regime_combo_stats`（[attribution.py:527](my_strategy/tools/attribution.py#L527)）：

```python
_SECTOR_STOCK_COMBO_LABELS = [
    ('行业多头+个股多头', True, True),
    ('行业多头+个股非多头', True, False),
    ('行业非多头+个股多头', False, True),
    ('行业非多头+个股非多头', False, False),
]


def compute_sector_stock_combo_stats(trades):
    """行业多头排列 × 个股多头排列 2x2 共振分析。

    缺 entry_sector_bull_align 或 entry_stock_bull_align 的行被 dropna 跳过。
    """
    cols = ['combo', 'count', 'win_rate', 'avg_return', 'avg_holding_days']
    required = ['entry_sector_bull_align', 'entry_stock_bull_align']
    if trades.empty or any(c not in trades.columns for c in required):
        return pd.DataFrame(columns=cols)
    sub = trades.dropna(subset=required).copy()
    if sub.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    for label, sec_v, stk_v in _SECTOR_STOCK_COMBO_LABELS:
        chunk = sub[(sub['entry_sector_bull_align'] == sec_v) &
                    (sub['entry_stock_bull_align'] == stk_v)]
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

接入 `run()`：

```python
compute_sector_stock_combo_stats(trades).to_csv(
    out_dir / 'sector_stock_combo_stats.csv', index=False)
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest my_strategy/tests/test_attribution.py -v -k combo_stats
```

- [ ] **Step 5: Commit**

```bash
git add my_strategy/tools/attribution.py my_strategy/tests/test_attribution.py
git commit -m "$(cat <<'EOF'
feat(attribution): sector_stock_combo_stats 2x2 cross-tab

Mirrors compute_regime_combo_stats but on sector × stock bull_align.
Answers: does sector confirmation add edge on top of stock signal?

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 13: 集成测试 + EXPECTED_FILES + 真实回测验证

**Files:**
- Modify: `my_strategy/tests/test_attribution_run.py`（EXPECTED_FILES 20 → 28）

- [ ] **Step 1: 更新 EXPECTED_FILES**

打开 [my_strategy/tests/test_attribution_run.py:17](my_strategy/tests/test_attribution_run.py#L17)，在 list 末尾追加 8 项：

```python
EXPECTED_FILES = [
    # ... 现有 20 项 ...
    'sector_bull_align_stats.csv',
    'sector_above_ma25_stats.csv',
    'sector_dif_stats.csv',
    'sector_week_macd_stats.csv',
    'sector_month_macd_stats.csv',
    'sector_momentum_60d_stats.csv',
    'sector_industry_stats.csv',
    'sector_stock_combo_stats.csv',
]
```

- [ ] **Step 2: 跑集成测试（依赖 trade_summary.csv 已经在 Task 8 跑过）**

```bash
python my_strategy/tests/test_attribution_run.py
```

预期：所有 28 个文件存在并产出。

- [ ] **Step 3: 跑全部 pytest**

```bash
pytest my_strategy/tests/ -v
```

预期：全绿。

- [ ] **Step 4: Phase 1 回归验证**

打开 Phase 1 的 5 张报告之一对比 Phase 1 完成时的数值快照：

```python
import pandas as pd
df1 = pd.read_csv('my_strategy/reports/hs300_dif_stats.csv')
df2 = pd.read_csv('my_strategy/reports/stock_bull_align_stats.csv')
df3 = pd.read_csv('my_strategy/reports/regime_combo_stats.csv')
print('hs300_dif_stats:'); print(df1)
print('stock_bull_align_stats:'); print(df2)
print('regime_combo_stats:'); print(df3)
```

对比 Phase 1 文档（`docs/superpowers/plans/2026-05-07-market-regime-snapshot-attribution.md` 完成记录）中的"5,911 trades, stock_bull_align 527/5911 = 8.9%"等数字。如果数字漂移：
- 检查 `_compute_regime_flags` 改动是否影响了 4 个旧 flag 的计算（不应该）
- 检查 trade_summary 行数是否一致（如果重新跑了回测，trades 总数应该不变）

- [ ] **Step 5: Phase 2 新报告抽样查看**

```python
import pandas as pd
print(pd.read_csv('my_strategy/reports/sector_stock_combo_stats.csv'))
print(pd.read_csv('my_strategy/reports/sector_industry_stats.csv').head(10))
print(pd.read_csv('my_strategy/reports/sector_momentum_60d_stats.csv'))
```

确认数据合理（count 加总接近 trade_summary 总数；win_rate 在 0-1 之间）。

- [ ] **Step 6: Commit**

```bash
git add my_strategy/tests/test_attribution_run.py
git commit -m "$(cat <<'EOF'
test(attribution): EXPECTED_FILES 20 -> 28 for Phase 2 reports

Adds 8 sector_*.csv expectations to integration test.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 14: 文档更新

**Files:**
- Modify: `docs/FEATURES.md`（§5.4 + §6 加新条目）
- Modify: `docs/CHANGELOG.md`（顶部追加 2026-05-07 条目）

- [ ] **Step 1: 更新 FEATURES.md**

打开 `docs/FEATURES.md`：
- §5（trade_summary 列）追加 6 个新列描述
- §6（attribution reports）追加 8 项（编号续接，从 20 → 27 或 21 → 28，按现有编号风格）

每条参照现有条目的格式（一句话说明字段语义/桶定义）。

- [ ] **Step 2: 更新 CHANGELOG.md**

在文件**顶部**追加：

```markdown
## 2026-05-07 — Phase 2 行业指数多空环境快照与归因

- 需求：按行业（申万一级）维度做入场环境归因，回答"行业多空能否过滤个股入场信号"
- 改动：
  - `downloader_extra.py`：新增 `download_sw_bars()` 拉 SW 周/月线（`pro_bar(asset='I')`)
  - `download_all.py`：循环下载 31 个 SW 指数 daily/weekly/monthly
  - `src/build_sector_mapping.py`：新增脚本，调 `index_member` API 构建 ts_code→sw_index_code 映射并写回 `stock_sector.csv`
  - `src/calc_indicators.py`：参数化重构为 `compute_indicators(code, src_dirs, dst_dir, groups)`，CLI `--mode {stock,sector}`，配置项 `indicator_profiles`
  - `backtest.py`：扩展 `_compute_regime_flags` 接受 `sector_row`，新增加载 `sector_indicators` + 6 列写入 trade_summary
  - `tools/attribution.py`：新增 8 个 compute 函数 + 1 个 `_compute_zone_stats` helper
- 影响：
  - trade_summary 列数 +6（5 个三态 object + 1 个 float）
  - reports CSV 数量 20 → 28
  - stock 模式 calc_indicators 输出经 byte-for-byte 回归测试，与重构前完全一致
```

- [ ] **Step 3: Commit**

```bash
git add docs/FEATURES.md docs/CHANGELOG.md
git commit -m "$(cat <<'EOF'
docs: Phase 2 sector regime attribution — FEATURES + CHANGELOG

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: 最终全测试**

```bash
pytest my_strategy/tests/ -v
```

预期：全绿。

- [ ] **Step 5: 更新 memory（可选 — 如果要在未来 session 引用本次工作）**

按现有 memory 模式写入 `project_phase2_sector_regime.md` 完成记录，更新 `MEMORY.md` 索引（把"待办"改成"已完成"）。

---

## 验收清单（与 spec §3.3 / §4.3 / §5.6 对齐）

**子项目 1（数据准备）**：
- ✅ `data/sw_index/`、`sw_weekly/`、`sw_monthly/` 各 31 个 CSV
- ✅ `stock_sector.csv` 新增 `sw_index_code` 列，覆盖率 ≥ 95%

**子项目 2（指标计算）**：
- ✅ `compute_indicators(groups)` 参数化函数
- ✅ `config.indicator_profiles.{stock,sector}`
- ✅ stock 模式 byte-for-byte 回归通过
- ✅ `data/sw_indicators/` 31 个 CSV

**子项目 3（归因）**：
- ✅ trade_summary 新增 6 列
- ✅ 8 张新报告产出
- ✅ Phase 1 5 张报告数值无回归
- ✅ `pytest my_strategy/tests/` 全绿
- ✅ FEATURES.md + CHANGELOG.md 更新
