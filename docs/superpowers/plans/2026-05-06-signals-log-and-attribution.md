# 信号日志 + 归因分析 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 my_strategy 项目新增基本面/行业指数数据、横截面分位数、信号全样本日志和离线归因脚本，为后续打分模块和择时模块提供数据基础。

**Architecture:** 不动现有策略逻辑（5 条入场必要条件、卖出/加仓全部保留）。新增 5 段 pipeline：`downloader → downloader_extra → calc_indicators → build_cross_section_pct → backtest`，回测后由 `tools/attribution.py` 离线分析。strategy.py 仅新增 signals_log 写入（侵入最小）。

**Tech Stack:** Python 3.x, pandas, tushare, backtrader, pytest。沿用现有项目代码风格。

**Spec:** [docs/superpowers/specs/2026-05-06-signals-log-and-attribution-design.md](../specs/2026-05-06-signals-log-and-attribution-design.md)

---

## 文件清单（执行前先看一眼）

**新建**：
- `my_strategy/src/downloader_extra.py` — 三个 Tushare 下载函数
- `my_strategy/src/build_cross_section_pct.py` — 横截面分位数聚合
- `my_strategy/tools/__init__.py`
- `my_strategy/tools/attribution.py` — 归因分析脚本
- `my_strategy/tests/test_downloader_extra.py`
- `my_strategy/tests/test_build_cross_section_pct.py`
- `my_strategy/tests/test_attribution.py`
- `my_strategy/data/daily_basic/` — 运行时产出
- `my_strategy/data/fina/` — 运行时产出
- `my_strategy/data/sw_index/` — 运行时产出
- `my_strategy/reports/` — 运行时产出

**修改**：
- `my_strategy/config.json` — 新增数据路径和 SW 指数清单
- `my_strategy/config.example.json` — 同步
- `my_strategy/src/calc_indicators.py` — 合并基本面 + 行业动量 + 单股因子
- `my_strategy/src/strategy.py` — 信号触发处写 signals_log
- `my_strategy/backtest.py` — 回测后回填 forward_return 并写 signals_log.csv
- `my_strategy/download_all.py` — 链式调用 downloader_extra 和 build_cross_section_pct
- `my_strategy/tests/test_strategy.py` — 验证 signals_log 正确写入
- `my_strategy/tests/test_calc_indicators.py` — 验证基本面/行业动量合并

---

## Task 1: 配置项扩展

**Files:**
- Modify: `my_strategy/config.json`
- Modify: `my_strategy/config.example.json`

- [ ] **Step 1: 读取当前 config.json，记录现有结构**

Run: `cat my_strategy/config.json`

- [ ] **Step 2: 在两份 config 文件根级添加新字段**

新增字段（合并到现有 JSON，**不要覆盖**已有键）：

```json
{
  "data_paths": {
    "daily_basic_dir": "data/daily_basic",
    "fina_indicator_dir": "data/fina",
    "sw_index_dir": "data/sw_index",
    "stock_sector_csv": "data/stock_sector.csv"
  },
  "sw_index_codes": [
    "801010.SI", "801030.SI", "801040.SI", "801050.SI", "801080.SI",
    "801110.SI", "801120.SI", "801130.SI", "801140.SI", "801150.SI",
    "801160.SI", "801170.SI", "801180.SI", "801200.SI", "801210.SI",
    "801230.SI", "801710.SI", "801720.SI", "801730.SI", "801740.SI",
    "801750.SI", "801760.SI", "801770.SI", "801780.SI", "801790.SI",
    "801880.SI", "801890.SI", "801950.SI", "801960.SI", "801970.SI",
    "801980.SI"
  ],
  "signals_log_path": "data/signals_log.csv",
  "attribution_report_dir": "reports"
}
```

- [ ] **Step 3: 验证 JSON 合法**

Run: `python -c "import json; json.load(open('my_strategy/config.json')); json.load(open('my_strategy/config.example.json'))"`
Expected: 无输出（成功）

- [ ] **Step 4: Commit**

```bash
git add my_strategy/config.json my_strategy/config.example.json
git commit -m "config: add data paths and SW index list for signals-log feature"
```

---

## Task 2: downloader_extra — daily_basic 下载

**Files:**
- Create: `my_strategy/src/downloader_extra.py`
- Create: `my_strategy/tests/test_downloader_extra.py`

- [ ] **Step 1: 写测试（mock Tushare 返回，验证落盘格式）**

Create `my_strategy/tests/test_downloader_extra.py`:

```python
import pandas as pd
from pathlib import Path
from unittest.mock import MagicMock
from my_strategy.src import downloader_extra


def test_download_daily_basic_writes_csv(tmp_path):
    pro = MagicMock()
    fake_df = pd.DataFrame({
        'ts_code': ['000001.SZ'] * 3,
        'trade_date': ['20240101', '20240102', '20240103'],
        'pe_ttm': [10.5, 10.6, 10.7],
        'pb': [1.2, 1.21, 1.22],
        'total_mv': [100000.0, 100100.0, 100200.0],
        'circ_mv': [80000.0, 80100.0, 80200.0],
        'turnover_rate': [1.0, 1.1, 1.2],
    })
    pro.daily_basic.return_value = fake_df

    downloader_extra.download_daily_basic(
        ts_code='000001.SZ',
        start_date='20240101',
        end_date='20240103',
        out_dir=tmp_path,
        pro=pro,
        sleep_sec=0,
    )

    csv = tmp_path / '000001.SZ.csv'
    assert csv.exists()
    df = pd.read_csv(csv)
    assert list(df.columns) == ['ts_code', 'trade_date', 'pe_ttm', 'pb',
                                 'total_mv', 'circ_mv', 'turnover_rate']
    assert len(df) == 3


def test_download_daily_basic_skips_existing(tmp_path):
    pro = MagicMock()
    csv = tmp_path / '000001.SZ.csv'
    csv.write_text('existing')
    downloader_extra.download_daily_basic(
        ts_code='000001.SZ',
        start_date='20240101',
        end_date='20240103',
        out_dir=tmp_path,
        pro=pro,
        sleep_sec=0,
    )
    pro.daily_basic.assert_not_called()
    assert csv.read_text() == 'existing'
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd my_strategy && python -m pytest tests/test_downloader_extra.py -v`
Expected: FAIL（模块不存在或函数未定义）

- [ ] **Step 3: 实现 download_daily_basic**

Create `my_strategy/src/downloader_extra.py`:

```python
import time
import pandas as pd
from pathlib import Path

from .downloader import _call_with_timeout, _year_chunks

DAILY_BASIC_COLS = ['ts_code', 'trade_date', 'pe_ttm', 'pb',
                    'total_mv', 'circ_mv', 'turnover_rate']


def download_daily_basic(ts_code, start_date, end_date, out_dir, pro,
                         sleep_sec=0.3, force=False):
    """下载单只股票的 daily_basic（估值、市值、换手率）。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{ts_code}.csv"
    if csv_path.exists() and not force:
        return

    chunks = []
    for seg_start, seg_end in _year_chunks(start_date, end_date):
        seg = _call_with_timeout(
            pro.daily_basic,
            ts_code=ts_code,
            start_date=seg_start,
            end_date=seg_end,
            fields=','.join(DAILY_BASIC_COLS),
        )
        if seg is not None and not seg.empty:
            chunks.append(seg)
        time.sleep(sleep_sec)

    if not chunks:
        return
    df = pd.concat(chunks).drop_duplicates(subset=['trade_date'])
    df = df.sort_values('trade_date').reset_index(drop=True)
    df.to_csv(csv_path, index=False)
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `cd my_strategy && python -m pytest tests/test_downloader_extra.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add my_strategy/src/downloader_extra.py my_strategy/tests/test_downloader_extra.py
git commit -m "feat(downloader_extra): add daily_basic downloader with skip-existing logic"
```

---

## Task 3: downloader_extra — fina_indicator 下载

**Files:**
- Modify: `my_strategy/src/downloader_extra.py`
- Modify: `my_strategy/tests/test_downloader_extra.py`

**关键**：fina_indicator 的 `ann_date` 是公告日，必须保留并作为下游对齐基准（不可用 `end_date` 报告期末）。

- [ ] **Step 1: 写测试**

Append to `my_strategy/tests/test_downloader_extra.py`:

```python
def test_download_fina_indicator_keeps_ann_date(tmp_path):
    pro = MagicMock()
    fake_df = pd.DataFrame({
        'ts_code': ['000001.SZ'] * 2,
        'ann_date': ['20240430', '20240828'],
        'end_date': ['20240331', '20240630'],
        'roe': [12.5, 13.0],
        'roe_yearly': [50.0, 52.0],
        'netprofit_yoy': [15.0, 18.0],
        'grossprofit_margin': [40.0, 41.0],
    })
    pro.fina_indicator.return_value = fake_df

    downloader_extra.download_fina_indicator(
        ts_code='000001.SZ',
        start_date='20240101',
        end_date='20241231',
        out_dir=tmp_path,
        pro=pro,
        sleep_sec=0,
    )

    df = pd.read_csv(tmp_path / '000001.SZ.csv')
    assert 'ann_date' in df.columns
    assert 'end_date' in df.columns
    assert 'roe' in df.columns
    assert len(df) == 2
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd my_strategy && python -m pytest tests/test_downloader_extra.py::test_download_fina_indicator_keeps_ann_date -v`
Expected: FAIL

- [ ] **Step 3: 实现 download_fina_indicator**

Append to `my_strategy/src/downloader_extra.py`:

```python
FINA_COLS = ['ts_code', 'ann_date', 'end_date',
             'roe', 'roe_yearly', 'netprofit_yoy', 'grossprofit_margin']


def download_fina_indicator(ts_code, start_date, end_date, out_dir, pro,
                            sleep_sec=0.3, force=False):
    """下载单只股票的季度财务指标。保留 ann_date（公告日）用于反未来函数对齐。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{ts_code}.csv"
    if csv_path.exists() and not force:
        return

    df = _call_with_timeout(
        pro.fina_indicator,
        ts_code=ts_code,
        start_date=start_date,
        end_date=end_date,
        fields=','.join(FINA_COLS),
    )
    time.sleep(sleep_sec)
    if df is None or df.empty:
        return
    df = df.sort_values(['ann_date', 'end_date']).reset_index(drop=True)
    df.to_csv(csv_path, index=False)
```

- [ ] **Step 4: 运行测试**

Run: `cd my_strategy && python -m pytest tests/test_downloader_extra.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add my_strategy/src/downloader_extra.py my_strategy/tests/test_downloader_extra.py
git commit -m "feat(downloader_extra): add fina_indicator downloader preserving ann_date"
```

---

## Task 4: downloader_extra — 申万行业指数下载

**Files:**
- Modify: `my_strategy/src/downloader_extra.py`
- Modify: `my_strategy/tests/test_downloader_extra.py`

- [ ] **Step 1: 写测试**

Append to `my_strategy/tests/test_downloader_extra.py`:

```python
def test_download_sw_index_writes_ohlcv(tmp_path):
    pro = MagicMock()
    fake_df = pd.DataFrame({
        'ts_code': ['801010.SI'] * 2,
        'trade_date': ['20240101', '20240102'],
        'open': [3000.0, 3010.0],
        'high': [3050.0, 3060.0],
        'low': [2990.0, 3000.0],
        'close': [3020.0, 3030.0],
        'vol': [1e8, 1.1e8],
    })
    pro.sw_daily.return_value = fake_df

    downloader_extra.download_sw_index(
        index_code='801010.SI',
        start_date='20240101',
        end_date='20240102',
        out_dir=tmp_path,
        pro=pro,
        sleep_sec=0,
    )

    df = pd.read_csv(tmp_path / '801010.SI.csv')
    assert 'close' in df.columns
    assert len(df) == 2
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd my_strategy && python -m pytest tests/test_downloader_extra.py::test_download_sw_index_writes_ohlcv -v`
Expected: FAIL

- [ ] **Step 3: 实现 download_sw_index**

Append to `my_strategy/src/downloader_extra.py`:

```python
SW_INDEX_COLS = ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'vol']


def download_sw_index(index_code, start_date, end_date, out_dir, pro,
                      sleep_sec=0.3, force=False):
    """下载申万一级行业指数 OHLCV。Tushare 接口名为 sw_daily。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{index_code}.csv"
    if csv_path.exists() and not force:
        return

    chunks = []
    for seg_start, seg_end in _year_chunks(start_date, end_date):
        seg = _call_with_timeout(
            pro.sw_daily,
            ts_code=index_code,
            start_date=seg_start,
            end_date=seg_end,
            fields=','.join(SW_INDEX_COLS),
        )
        if seg is not None and not seg.empty:
            chunks.append(seg)
        time.sleep(sleep_sec)

    if not chunks:
        return
    df = pd.concat(chunks).drop_duplicates(subset=['trade_date'])
    df = df.sort_values('trade_date').reset_index(drop=True)
    df.to_csv(csv_path, index=False)
```

- [ ] **Step 4: 运行测试**

Run: `cd my_strategy && python -m pytest tests/test_downloader_extra.py -v`
Expected: 4 passed

- [ ] **Step 5: 添加批量入口 main()**

Append to `my_strategy/src/downloader_extra.py`:

```python
def main():
    import json
    import tushare as ts
    from pathlib import Path

    project_root = Path(__file__).resolve().parent.parent
    cfg = json.loads((project_root / 'config.json').read_text())

    token_path = project_root.parent / 'learn_backtrader' / 'Data' / 'tushare_token.json'
    token = json.loads(token_path.read_text())['token']
    ts.set_token(token)
    pro = ts.pro_api()

    data_dir = project_root / cfg['data_dir']
    paths = cfg['data_paths']
    start = cfg['start_date']
    end = cfg['end_date']

    stocks = pd.read_csv(project_root / cfg['stock_list_path'])['ts_code'].tolist()

    db_dir = data_dir / Path(paths['daily_basic_dir']).name
    fi_dir = data_dir / Path(paths['fina_indicator_dir']).name
    for i, ts_code in enumerate(stocks):
        download_daily_basic(ts_code, start, end, db_dir, pro)
        download_fina_indicator(ts_code, start, end, fi_dir, pro)
        if (i + 1) % 100 == 0:
            print(f"[{i+1}/{len(stocks)}] daily_basic+fina")

    sw_dir = data_dir / Path(paths['sw_index_dir']).name
    for code in cfg['sw_index_codes']:
        download_sw_index(code, start, end, sw_dir, pro)
        print(f"SW {code} OK")


if __name__ == '__main__':
    main()
```

- [ ] **Step 6: Commit**

```bash
git add my_strategy/src/downloader_extra.py my_strategy/tests/test_downloader_extra.py
git commit -m "feat(downloader_extra): add SW index downloader and batch main()"
```

---

## Task 5: calc_indicators — 合并基本面（按 ann_date 对齐）

**Files:**
- Modify: `my_strategy/src/calc_indicators.py`
- Modify: `my_strategy/tests/test_calc_indicators.py`

**关键反未来函数原则**：每个交易日 T，可用的财务数据是**最近一条 `ann_date <= T` 的记录**。`merge_asof(direction='backward')` 实现此语义。

- [ ] **Step 1: 写测试**

Append to `my_strategy/tests/test_calc_indicators.py` (or 新增):

```python
import pandas as pd
from my_strategy.src.calc_indicators import merge_fundamentals


def test_merge_fundamentals_aligns_by_ann_date():
    daily = pd.DataFrame({
        'trade_date': pd.to_datetime(['2024-04-29', '2024-04-30', '2024-05-06']),
        'close': [10.0, 10.1, 10.2],
    })
    daily_basic = pd.DataFrame({
        'trade_date': pd.to_datetime(['2024-04-29', '2024-04-30', '2024-05-06']),
        'pe_ttm': [12.0, 12.1, 12.2],
        'pb': [1.5, 1.51, 1.52],
        'total_mv': [1e5, 1.01e5, 1.02e5],
    })
    # ann_date = 20240430，2024-04-29 之前不可见，从 2024-04-30 起可见
    fina = pd.DataFrame({
        'ann_date': pd.to_datetime(['2024-04-30']),
        'end_date': pd.to_datetime(['2024-03-31']),
        'roe': [12.5],
        'netprofit_yoy': [15.0],
    })

    out = merge_fundamentals(daily, daily_basic, fina)

    assert out.loc[out['trade_date'] == pd.Timestamp('2024-04-29'), 'roe'].isna().all()
    assert out.loc[out['trade_date'] == pd.Timestamp('2024-04-30'), 'roe'].iloc[0] == 12.5
    assert out.loc[out['trade_date'] == pd.Timestamp('2024-05-06'), 'roe'].iloc[0] == 12.5
    # daily_basic 字段直接合并
    assert out.loc[out['trade_date'] == pd.Timestamp('2024-04-30'), 'pe_ttm'].iloc[0] == 12.1


def test_merge_fundamentals_no_fina_data():
    daily = pd.DataFrame({
        'trade_date': pd.to_datetime(['2024-04-30']),
        'close': [10.0],
    })
    daily_basic = pd.DataFrame({
        'trade_date': pd.to_datetime(['2024-04-30']),
        'pe_ttm': [12.1], 'pb': [1.51], 'total_mv': [1e5],
    })
    fina_empty = pd.DataFrame(columns=['ann_date', 'end_date', 'roe', 'netprofit_yoy'])

    out = merge_fundamentals(daily, daily_basic, fina_empty)
    assert out['roe'].isna().all()
    assert out['pe_ttm'].iloc[0] == 12.1
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd my_strategy && python -m pytest tests/test_calc_indicators.py::test_merge_fundamentals_aligns_by_ann_date -v`
Expected: FAIL

- [ ] **Step 3: 实现 merge_fundamentals**

Append to `my_strategy/src/calc_indicators.py`:

```python
def merge_fundamentals(daily_df: pd.DataFrame,
                       daily_basic_df: pd.DataFrame,
                       fina_df: pd.DataFrame) -> pd.DataFrame:
    """按 ann_date 对齐合并财务数据，按 trade_date 对齐合并日频估值数据。

    daily_df: 至少含 trade_date 列，已按 trade_date 升序
    daily_basic_df: pe_ttm/pb/total_mv 等日频估值
    fina_df: 季度财务指标，必须含 ann_date 列
    """
    out = daily_df.copy()
    if not daily_basic_df.empty:
        db = daily_basic_df.sort_values('trade_date')
        out = out.merge(db, on='trade_date', how='left')
    else:
        for col in ['pe_ttm', 'pb', 'total_mv']:
            out[col] = pd.NA

    if fina_df is not None and not fina_df.empty:
        f = fina_df.sort_values('ann_date').rename(columns={'ann_date': 'trade_date'})
        f = f[['trade_date', 'roe', 'netprofit_yoy']]
        out = pd.merge_asof(
            out.sort_values('trade_date'),
            f,
            on='trade_date',
            direction='backward',
        )
    else:
        out['roe'] = pd.NA
        out['netprofit_yoy'] = pd.NA

    return out
```

- [ ] **Step 4: 运行测试**

Run: `cd my_strategy && python -m pytest tests/test_calc_indicators.py -v`
Expected: 之前的测试全部通过 + 2 个新测试通过

- [ ] **Step 5: Commit**

```bash
git add my_strategy/src/calc_indicators.py my_strategy/tests/test_calc_indicators.py
git commit -m "feat(calc_indicators): merge daily_basic and fina_indicator with ann_date alignment"
```

---

## Task 6: calc_indicators — 行业指数动量 + 单股因子

**Files:**
- Modify: `my_strategy/src/calc_indicators.py`
- Modify: `my_strategy/tests/test_calc_indicators.py`

- [ ] **Step 1: 写测试**

Append to `my_strategy/tests/test_calc_indicators.py`:

```python
from my_strategy.src.calc_indicators import (
    add_single_stock_factors,
    merge_sector_momentum,
)


def test_add_single_stock_factors_computes_momentum_and_dist():
    df = pd.DataFrame({
        'trade_date': pd.date_range('2024-01-01', periods=70),
        'close': list(range(100, 170)),
        'ma60': [None] * 60 + [130.0] * 10,
        'dea': [0.5] * 70,
    })
    out = add_single_stock_factors(df)
    # 第 60 天的 60 日动量 = (close[59] - close[-1]) / close[-1]，但 momentum_60d
    # 在 t=60 才有值（需要 60 根历史 K 线）
    assert 'factor_momentum_60d' in out.columns
    assert 'factor_ma60_dist' in out.columns
    assert 'factor_macd_strength' in out.columns
    # 最后一行：(169 - 109) / 109
    assert abs(out['factor_momentum_60d'].iloc[-1] - (169 - 109) / 109) < 1e-6
    # ma60_dist 最后一行：(169 - 130) / 130
    assert abs(out['factor_ma60_dist'].iloc[-1] - (169 - 130) / 130) < 1e-6
    assert out['factor_macd_strength'].iloc[-1] == 0.5


def test_merge_sector_momentum_aligns_by_date():
    daily = pd.DataFrame({
        'trade_date': pd.to_datetime(['2024-01-01', '2024-01-02']),
        'close': [10.0, 10.1],
    })
    sector_idx = pd.DataFrame({
        'trade_date': pd.to_datetime(pd.date_range('2023-09-01', periods=70)),
        'close': list(range(1000, 1070)),
    })

    out = merge_sector_momentum(daily, sector_idx)
    assert 'factor_sector_momentum_60d' in out.columns
    assert not out['factor_sector_momentum_60d'].isna().all()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd my_strategy && python -m pytest tests/test_calc_indicators.py -k "factors or sector_momentum" -v`
Expected: FAIL

- [ ] **Step 3: 实现两个函数**

Append to `my_strategy/src/calc_indicators.py`:

```python
def add_single_stock_factors(df: pd.DataFrame) -> pd.DataFrame:
    """添加单股票内可计算的打分因子。"""
    out = df.copy()
    out['factor_momentum_60d'] = out['close'].pct_change(60).round(6)
    out['factor_ma60_dist'] = ((out['close'] - out['ma60']) / out['ma60']).round(6)
    out['factor_macd_strength'] = out['dea'].round(6)
    return out


def merge_sector_momentum(daily_df: pd.DataFrame,
                          sector_index_df: pd.DataFrame) -> pd.DataFrame:
    """合并所属行业指数过去 60 日动量。"""
    out = daily_df.copy()
    if sector_index_df is None or sector_index_df.empty:
        out['factor_sector_momentum_60d'] = pd.NA
        return out
    s = sector_index_df.sort_values('trade_date').copy()
    s['factor_sector_momentum_60d'] = s['close'].pct_change(60).round(6)
    s = s[['trade_date', 'factor_sector_momentum_60d']]
    return out.merge(s, on='trade_date', how='left')
```

- [ ] **Step 4: 修改 main() 串起新逻辑**

Replace `my_strategy/src/calc_indicators.py` 的 `main()` 函数为：

```python
def main():
    cfg = load_config()
    project_root = Path(__file__).resolve().parent.parent
    data_dir = project_root / cfg['data_dir']
    stocks_df = pd.read_csv(project_root / cfg['stock_list_path'])
    stocks = stocks_df['ts_code'].tolist()

    paths = cfg.get('data_paths', {})
    db_dir = data_dir / Path(paths.get('daily_basic_dir', 'daily_basic')).name
    fi_dir = data_dir / Path(paths.get('fina_indicator_dir', 'fina')).name
    sw_dir = data_dir / Path(paths.get('sw_index_dir', 'sw_index')).name
    sector_csv = project_root / paths.get('stock_sector_csv', 'data/stock_sector.csv')

    sector_map = {}
    if sector_csv.exists():
        sec_df = pd.read_csv(sector_csv)
        # 假定列名为 ts_code 和 sw_index_code（如果列名不同需调整）
        if 'sw_index_code' in sec_df.columns and 'ts_code' in sec_df.columns:
            sector_map = dict(zip(sec_df['ts_code'], sec_df['sw_index_code']))

    indicators_dir = data_dir / 'indicators'
    indicators_dir.mkdir(parents=True, exist_ok=True)
    for i, ts_code in enumerate(stocks):
        src = data_dir / 'daily' / f"{ts_code}.csv"
        dst = indicators_dir / f"{ts_code}.csv"
        if not src.exists():
            print(f"[{i+1}/{len(stocks)}] {ts_code} SKIP (no raw data)")
            continue
        df = pd.read_csv(src, parse_dates=['trade_date'])
        df = df.sort_values('trade_date').reset_index(drop=True)
        df = compute_indicators(df)
        df = compute_weekly_monthly_indicators(ts_code, df, data_dir)

        db = pd.read_csv(db_dir / f"{ts_code}.csv", parse_dates=['trade_date']) \
            if (db_dir / f"{ts_code}.csv").exists() else pd.DataFrame()
        fi_path = fi_dir / f"{ts_code}.csv"
        if fi_path.exists():
            fi = pd.read_csv(fi_path, parse_dates=['ann_date', 'end_date'])
        else:
            fi = pd.DataFrame()
        df = merge_fundamentals(df, db, fi)

        df = add_single_stock_factors(df)

        sw_code = sector_map.get(ts_code)
        if sw_code:
            sw_path = sw_dir / f"{sw_code}.csv"
            if sw_path.exists():
                sw_df = pd.read_csv(sw_path, parse_dates=['trade_date'])
                df = merge_sector_momentum(df, sw_df)
            else:
                df['factor_sector_momentum_60d'] = pd.NA
        else:
            df['factor_sector_momentum_60d'] = pd.NA

        df.to_csv(dst, index=False)
        if (i + 1) % 100 == 0:
            print(f"[{i+1}/{len(stocks)}] {ts_code} OK")
```

- [ ] **Step 5: 运行所有 calc_indicators 测试**

Run: `cd my_strategy && python -m pytest tests/test_calc_indicators.py -v`
Expected: 全部通过

- [ ] **Step 6: Commit**

```bash
git add my_strategy/src/calc_indicators.py my_strategy/tests/test_calc_indicators.py
git commit -m "feat(calc_indicators): add per-stock factors and sector momentum merge"
```

---

## Task 7: build_cross_section_pct — 横截面分位数

**Files:**
- Create: `my_strategy/src/build_cross_section_pct.py`
- Create: `my_strategy/tests/test_build_cross_section_pct.py`

- [ ] **Step 1: 写测试**

Create `my_strategy/tests/test_build_cross_section_pct.py`:

```python
import pandas as pd
from pathlib import Path
from my_strategy.src.build_cross_section_pct import (
    compute_cross_section_pct,
    process_indicators_dir,
)


def test_compute_cross_section_pct_ranks_within_day():
    df = pd.DataFrame({
        'ts_code': ['A', 'B', 'C', 'A', 'B', 'C'],
        'trade_date': pd.to_datetime(['2024-01-01'] * 3 + ['2024-01-02'] * 3),
        'factor_momentum_60d': [0.1, 0.2, 0.3, 0.5, 0.4, 0.3],
        'factor_ma60_dist': [0.0, 0.05, 0.1, 0.0, 0.0, 0.0],
        'factor_macd_strength': [1.0, 2.0, 3.0, 3.0, 2.0, 1.0],
        'roe': [10.0, 20.0, 30.0, 30.0, 20.0, 10.0],
        'pe_ttm': [10.0, 20.0, 30.0, 10.0, 20.0, 30.0],
        'netprofit_yoy': [5.0, 10.0, 15.0, 5.0, 10.0, 15.0],
        'factor_sector_momentum_60d': [0.01, 0.02, 0.03, 0.03, 0.02, 0.01],
    })
    out = compute_cross_section_pct(df)
    # 2024-01-01 momentum: A=0.1, B=0.2, C=0.3 → 分位 A=0, B=0.5, C=1.0
    a01 = out[(out['ts_code'] == 'A') & (out['trade_date'] == pd.Timestamp('2024-01-01'))].iloc[0]
    c01 = out[(out['ts_code'] == 'C') & (out['trade_date'] == pd.Timestamp('2024-01-01'))].iloc[0]
    assert a01['pct_momentum_60d'] == 0.0
    assert c01['pct_momentum_60d'] == 1.0
    # PE 反向：低 PE 分位高
    assert a01['pct_pe'] == 1.0
    assert c01['pct_pe'] == 0.0


def test_process_indicators_dir_writes_back(tmp_path):
    in_dir = tmp_path / 'indicators'
    in_dir.mkdir()
    df_a = pd.DataFrame({
        'trade_date': pd.to_datetime(['2024-01-01', '2024-01-02']),
        'close': [10.0, 10.1],
        'factor_momentum_60d': [0.1, 0.5],
        'factor_ma60_dist': [0.0, 0.0],
        'factor_macd_strength': [1.0, 3.0],
        'roe': [10.0, 30.0],
        'pe_ttm': [30.0, 10.0],
        'netprofit_yoy': [5.0, 15.0],
        'factor_sector_momentum_60d': [0.01, 0.03],
    })
    df_b = df_a.copy()
    df_b['factor_momentum_60d'] = [0.2, 0.4]
    df_b['roe'] = [20.0, 20.0]
    df_a.to_csv(in_dir / 'A.csv', index=False)
    df_b.to_csv(in_dir / 'B.csv', index=False)

    process_indicators_dir(in_dir)

    out_a = pd.read_csv(in_dir / 'A.csv')
    assert 'pct_momentum_60d' in out_a.columns
    assert 'pct_roe' in out_a.columns
    assert 'pct_pe' in out_a.columns
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd my_strategy && python -m pytest tests/test_build_cross_section_pct.py -v`
Expected: FAIL

- [ ] **Step 3: 实现模块**

Create `my_strategy/src/build_cross_section_pct.py`:

```python
import pandas as pd
from pathlib import Path

# (源列, 目标分位列, 反向)
PCT_FACTORS = [
    ('factor_momentum_60d', 'pct_momentum_60d', False),
    ('factor_ma60_dist', 'pct_ma60_dist', False),
    ('factor_macd_strength', 'pct_macd_strength', False),
    ('roe', 'pct_roe', False),
    ('pe_ttm', 'pct_pe', True),       # 低 PE → 高分位
    ('netprofit_yoy', 'pct_netprofit_yoy', False),
    ('factor_sector_momentum_60d', 'pct_sector_momentum_60d', False),
]


def compute_cross_section_pct(df: pd.DataFrame) -> pd.DataFrame:
    """对长表（多股票多日）计算每日横截面百分位排名（0~1）。"""
    out = df.copy()
    for src, dst, reverse in PCT_FACTORS:
        if src not in out.columns:
            out[dst] = pd.NA
            continue
        ranks = out.groupby('trade_date')[src].rank(pct=True, na_option='keep')
        if reverse:
            ranks = 1.0 - ranks
        out[dst] = ranks.round(6)
    return out


def process_indicators_dir(indicators_dir):
    """读取 indicators 目录所有 CSV，计算横截面分位数后写回。"""
    indicators_dir = Path(indicators_dir)
    files = sorted(indicators_dir.glob('*.csv'))
    if not files:
        return

    print(f"reading {len(files)} indicator files...")
    parts = []
    for f in files:
        df = pd.read_csv(f, parse_dates=['trade_date'])
        df['_ts_code'] = f.stem
        parts.append(df)
    big = pd.concat(parts, ignore_index=True)
    big = compute_cross_section_pct(big)

    pct_cols = [dst for _, dst, _ in PCT_FACTORS]
    for f in files:
        ts_code = f.stem
        sub = big[big['_ts_code'] == ts_code].drop(columns=['_ts_code'])
        sub.to_csv(f, index=False)


def main():
    import json
    project_root = Path(__file__).resolve().parent.parent
    cfg = json.loads((project_root / 'config.json').read_text())
    data_dir = project_root / cfg['data_dir']
    process_indicators_dir(data_dir / 'indicators')
    print("cross-section pct done")


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: 运行测试**

Run: `cd my_strategy && python -m pytest tests/test_build_cross_section_pct.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add my_strategy/src/build_cross_section_pct.py my_strategy/tests/test_build_cross_section_pct.py
git commit -m "feat(cross_section_pct): add cross-sectional percentile aggregation"
```

---

## Task 8: 策略 signals_log 写入

**Files:**
- Modify: `my_strategy/src/strategy.py`
- Modify: `my_strategy/tests/test_strategy.py`

**设计**：在 `next()` 检测到 5 条入场必要条件全部通过时，写一条 signals_log 记录（无论实际是否买入）。如果因 max_positions 或现金不足无法买入，标记 `skip_reason='no_capacity'`，仍记录。

**因子值来源**：strategy 启动时把每只股票的 indicators CSV 中的 `pct_*` 和 `factor_*` 列读入字典 `self.factor_lookup[ts_code][trade_date]`。这样 next() 内仅做查表，不依赖 backtrader 数据 feed line。

- [ ] **Step 1: 写测试（验证 signals_log 在合成数据上正确产出）**

Append to `my_strategy/tests/test_strategy.py`：

```python
import pandas as pd
import backtrader as bt
from datetime import datetime
from my_strategy.src.strategy import MyStrategy, StockData


def _make_signal_data():
    """构造一只能在某日触发 5 条必要条件的合成股票。"""
    dates = pd.date_range('2023-01-01', periods=80, freq='B')
    # 60 日 MA 站稳后构造一个"DEA 由负转正后的回调日"
    close = [10.0] * 70 + [11.0, 11.5, 11.8, 12.0, 12.2, 12.5, 12.3, 12.5, 12.8, 12.6]
    ma60 = [None] * 59 + [10.0] * 21
    ma25 = [None] * 24 + [10.0] * 56
    dea = [-0.1] * 65 + [-0.05, 0.01, 0.05, 0.1, 0.15] + [0.2] * 10
    df = pd.DataFrame({
        'datetime': dates[:len(close)],
        'open': close,
        'high': [c + 0.1 for c in close],
        'low': [c - 0.1 for c in close],
        'close': close,
        'volume': [1000] * len(close),
        'ma25': ma25[:len(close)],
        'ma60': ma60[:len(close)],
        'dea': dea[:len(close)],
    })
    df = df.set_index('datetime')
    return df


def test_strategy_writes_signals_log(tmp_path):
    """run cerebro on synthetic data and verify signals_log is populated."""
    df = _make_signal_data()
    factor_lookup = {
        'TEST.SZ': {
            d.date(): {
                'factor_momentum_60d': 0.05,
                'factor_ma60_dist': 0.05,
                'factor_macd_strength': 0.1,
                'factor_roe': 12.0,
                'factor_pe_ttm': 15.0,
                'factor_netprofit_yoy': 10.0,
                'factor_sector_momentum_60d': 0.02,
                'pct_momentum_60d': 0.5,
                'pct_ma60_dist': 0.5,
                'pct_macd_strength': 0.5,
                'pct_roe': 0.5,
                'pct_pe': 0.5,
                'pct_netprofit_yoy': 0.5,
                'pct_sector_momentum_60d': 0.5,
            }
            for d in df.index
        }
    }
    sector_map = {'TEST.SZ': '801010.SI'}

    cerebro = bt.Cerebro()
    cerebro.addstrategy(MyStrategy,
                        factor_lookup=factor_lookup,
                        sector_map=sector_map)
    data = StockData(dataname=df, name='TEST.SZ')
    cerebro.adddata(data)
    cerebro.broker.setcash(1_000_000)
    strats = cerebro.run()

    strat = strats[0]
    assert hasattr(strat, 'signals_log')
    # 至少应捕获到一条信号
    assert len(strat.signals_log) >= 1
    rec = strat.signals_log[0]
    assert rec['ts_code'] == 'TEST.SZ'
    assert rec['sector'] == '801010.SI'
    assert 'pct_momentum_60d' in rec
    assert 'was_bought' in rec
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd my_strategy && python -m pytest tests/test_strategy.py::test_strategy_writes_signals_log -v`
Expected: FAIL

- [ ] **Step 3: 修改 MyStrategy**

修改 [my_strategy/src/strategy.py](../../../my_strategy/src/strategy.py)：

a) 在 `params` 增加：
```python
params = (
    # ... 现有参数 ...
    ('factor_lookup', None),  # dict: {ts_code: {date: {factor_name: value}}}
    ('sector_map', None),     # dict: {ts_code: sw_index_code}
)
```

b) 在 `__init__` 末尾增加：
```python
self.signals_log = []
```

c) 修改 `next()` 中的入场分支（else 分支，原 strategy.py 第 314-350 行）。在所有 5 个 `continue` 检查通过后、`self._current_position_count() >= self.p.max_positions` 检查**之前**插入信号记录调用，并把 max_positions 检查改为决定 skip_reason：

```python
            else:
                prev_close = d.close[-1]
                dea = d.dea[0]

                if _isnan(prev_close):
                    continue
                if close >= prev_close:
                    continue
                if close <= ma60:
                    continue
                if dea <= 0:
                    continue
                n = self.p.dea_lookback_days
                past_deas = [d.dea[-i] for i in range(1, n + 1)]
                if not any(v < 0 for v in past_deas if v == v):
                    continue

                # ============ 5 条必要条件全部通过，记录信号 ============
                trade_date = bt.num2date(d.datetime[0]).date()
                skip_reason = ''
                if self._current_position_count() >= self.p.max_positions:
                    skip_reason = 'no_capacity'

                if (close - ma60) / ma60 <= 0.01:
                    buy_size = int(self.position_limit / close / 100) * 100
                else:
                    buy_size = int(self.position_limit / 3 / close / 100) * 100

                if not skip_reason and buy_size <= 0:
                    skip_reason = 'no_capacity'

                self._record_signal(d, trade_date, close, ma60, dea,
                                     was_bought=(skip_reason == ''),
                                     skip_reason=skip_reason)

                if skip_reason:
                    continue

                if (close - ma60) / ma60 <= 0.01:
                    state['add_count'] = 2

                state['pending_atr'] = float(self.atr[d][0])
                o = self.buy(data=d, size=buy_size)
                self.order_reasons[o.ref] = 'initial_buy'
                self.orders[d] = o
```

d) 新增方法 `_record_signal`（在 `next` 之前的某个合适位置，比如 `_finalize_episode` 之后）：

```python
    def _record_signal(self, d, trade_date, close, ma60, dea,
                       was_bought, skip_reason):
        ts_code = d._name
        factor_lookup = self.p.factor_lookup or {}
        sector_map = self.p.sector_map or {}
        factors = factor_lookup.get(ts_code, {}).get(trade_date, {})
        rec = {
            'date': trade_date,
            'ts_code': ts_code,
            'sector': sector_map.get(ts_code, ''),
            'close': close,
            'ma60': ma60,
            'dea': dea,
            'atr': float(self.atr[d][0]),
            'was_bought': was_bought,
            'skip_reason': skip_reason,
        }
        for k in ('factor_momentum_60d', 'factor_ma60_dist', 'factor_macd_strength',
                  'factor_roe', 'factor_pe_ttm', 'factor_netprofit_yoy',
                  'factor_sector_momentum_60d',
                  'pct_momentum_60d', 'pct_ma60_dist', 'pct_macd_strength',
                  'pct_roe', 'pct_pe', 'pct_netprofit_yoy',
                  'pct_sector_momentum_60d'):
            rec[k] = factors.get(k)
        # forward returns 由 backtest.py 在回测后回填
        rec['forward_return_5d'] = None
        rec['forward_return_20d'] = None
        rec['forward_return_60d'] = None
        self.signals_log.append(rec)
```

- [ ] **Step 4: 运行新测试**

Run: `cd my_strategy && python -m pytest tests/test_strategy.py::test_strategy_writes_signals_log -v`
Expected: PASS

- [ ] **Step 5: 运行全部 strategy 测试，确保未破坏现有逻辑**

Run: `cd my_strategy && python -m pytest tests/test_strategy.py -v`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add my_strategy/src/strategy.py my_strategy/tests/test_strategy.py
git commit -m "feat(strategy): record every entry signal to signals_log with factor values"
```

---

## Task 9: backtest.py — forward return 回填 + signals_log 落盘

**Files:**
- Modify: `my_strategy/backtest.py`
- Modify: `my_strategy/tests/test_backtest.py`

- [ ] **Step 1: 写测试（forward return 回填的纯函数）**

Append to `my_strategy/tests/test_backtest.py`：

```python
import pandas as pd
from my_strategy.backtest import backfill_forward_returns


def test_backfill_forward_returns_5_20_60():
    indicators_by_code = {
        'A.SZ': pd.DataFrame({
            'trade_date': pd.date_range('2024-01-01', periods=80, freq='B'),
            'close': list(range(100, 180)),
        })
    }
    signals = [
        {'ts_code': 'A.SZ', 'date': pd.Timestamp('2024-01-01').date(),
         'forward_return_5d': None, 'forward_return_20d': None, 'forward_return_60d': None},
    ]
    backfill_forward_returns(signals, indicators_by_code)

    # close at 2024-01-01 = 100, 5 business days later = 105, 20 = 120, 60 = 160
    assert abs(signals[0]['forward_return_5d'] - (105 - 100) / 100) < 1e-6
    assert abs(signals[0]['forward_return_20d'] - (120 - 100) / 100) < 1e-6
    assert abs(signals[0]['forward_return_60d'] - (160 - 100) / 100) < 1e-6


def test_backfill_forward_returns_handles_missing_horizon():
    """信号触发后剩余交易日不足时，对应字段保持 None。"""
    indicators_by_code = {
        'A.SZ': pd.DataFrame({
            'trade_date': pd.date_range('2024-01-01', periods=10, freq='B'),
            'close': [100.0] * 10,
        })
    }
    signals = [
        {'ts_code': 'A.SZ', 'date': pd.Timestamp('2024-01-08').date(),
         'forward_return_5d': None, 'forward_return_20d': None, 'forward_return_60d': None},
    ]
    backfill_forward_returns(signals, indicators_by_code)
    assert signals[0]['forward_return_5d'] is None
    assert signals[0]['forward_return_20d'] is None
    assert signals[0]['forward_return_60d'] is None
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd my_strategy && python -m pytest tests/test_backtest.py::test_backfill_forward_returns_5_20_60 -v`
Expected: FAIL

- [ ] **Step 3: 在 backtest.py 实现 backfill_forward_returns**

Append to `my_strategy/backtest.py`（不要替换现有 main 流程，仅新增函数）：

```python
def backfill_forward_returns(signals, indicators_by_code, horizons=(5, 20, 60)):
    """对 signals_log 列表（list of dict）原地回填 forward_return_{N}d 字段。

    indicators_by_code: dict[ts_code -> DataFrame with trade_date/close cols]
    """
    import pandas as pd
    code_index = {}
    for code, df in indicators_by_code.items():
        d = df.sort_values('trade_date').reset_index(drop=True)
        date_to_pos = {pd.Timestamp(t).date(): i for i, t in enumerate(d['trade_date'])}
        code_index[code] = (d, date_to_pos)

    for sig in signals:
        code = sig['ts_code']
        if code not in code_index:
            continue
        d, idx = code_index[code]
        pos = idx.get(sig['date'])
        if pos is None:
            continue
        base_close = d['close'].iloc[pos]
        if base_close is None or base_close == 0 or pd.isna(base_close):
            continue
        for h in horizons:
            target = pos + h
            if target >= len(d):
                continue
            future_close = d['close'].iloc[target]
            if pd.isna(future_close):
                continue
            sig[f'forward_return_{h}d'] = round(
                (future_close - base_close) / base_close, 6)
```

- [ ] **Step 4: 运行新测试**

Run: `cd my_strategy && python -m pytest tests/test_backtest.py::test_backfill_forward_returns_5_20_60 tests/test_backtest.py::test_backfill_forward_returns_handles_missing_horizon -v`
Expected: 2 passed

- [ ] **Step 5: 在 backtest.py main() 流程末尾接入回填和落盘**

定位 `my_strategy/backtest.py` 的 `main()` 中 `cerebro.run()` 之后、写出其他 CSV 之前的位置。在那里添加：

```python
    # 1. 准备 indicators_by_code（如果已有就复用）
    indicators_by_code = {}
    for d in cerebro.datas:
        ts_code = d._name
        path = data_dir / 'indicators' / f"{ts_code}.csv"
        if path.exists():
            indicators_by_code[ts_code] = pd.read_csv(path, parse_dates=['trade_date'])

    # 2. 回填 forward returns
    backfill_forward_returns(strat.signals_log, indicators_by_code)

    # 3. 写出 signals_log.csv
    if strat.signals_log:
        sig_df = pd.DataFrame(strat.signals_log)
        sig_path = project_root / cfg['signals_log_path']
        sig_path.parent.mkdir(parents=True, exist_ok=True)
        sig_df.to_csv(sig_path, index=False)
        print(f"signals_log: {len(sig_df)} rows written to {sig_path}")
```

注：变量 `cerebro / strat / data_dir / project_root / cfg / pd` 在 main 上下文中应已存在；若变量名不同，按现有 backtest.py 实际命名调整。

并在策略实例化时传入 factor_lookup 和 sector_map（在添加策略之前先构造）：

```python
    factor_lookup = {}
    sector_map = {}
    sector_csv = project_root / cfg.get('data_paths', {}).get(
        'stock_sector_csv', 'data/stock_sector.csv')
    if sector_csv.exists():
        sec_df = pd.read_csv(sector_csv)
        if 'sw_index_code' in sec_df.columns:
            sector_map = dict(zip(sec_df['ts_code'], sec_df['sw_index_code']))

    factor_cols = [
        'factor_momentum_60d', 'factor_ma60_dist', 'factor_macd_strength',
        'factor_roe', 'factor_pe_ttm', 'factor_netprofit_yoy',
        'factor_sector_momentum_60d',
        'pct_momentum_60d', 'pct_ma60_dist', 'pct_macd_strength',
        'pct_roe', 'pct_pe', 'pct_netprofit_yoy', 'pct_sector_momentum_60d',
    ]
    for ts_code in stocks:
        ind_path = data_dir / 'indicators' / f"{ts_code}.csv"
        if not ind_path.exists():
            continue
        df_ind = pd.read_csv(ind_path, parse_dates=['trade_date'])
        present = [c for c in factor_cols if c in df_ind.columns]
        # 部分老 indicators 字段可能映射到不同名字（roe / pe_ttm / netprofit_yoy）
        rename = {'roe': 'factor_roe', 'pe_ttm': 'factor_pe_ttm',
                  'netprofit_yoy': 'factor_netprofit_yoy'}
        for old, new in rename.items():
            if old in df_ind.columns and new not in df_ind.columns:
                df_ind[new] = df_ind[old]
                if new not in present:
                    present.append(new)
        date_dict = {}
        for _, row in df_ind.iterrows():
            date_dict[row['trade_date'].date()] = {c: row[c] for c in present}
        factor_lookup[ts_code] = date_dict
```

并修改 `cerebro.addstrategy(MyStrategy, ...)` 这一行，加入两个新参数：

```python
    cerebro.addstrategy(MyStrategy,
                        # ... 现有参数 ...
                        factor_lookup=factor_lookup,
                        sector_map=sector_map)
```

- [ ] **Step 6: 运行 backtest 测试**

Run: `cd my_strategy && python -m pytest tests/test_backtest.py -v`
Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
git add my_strategy/backtest.py my_strategy/tests/test_backtest.py
git commit -m "feat(backtest): backfill forward returns and write signals_log.csv"
```

---

## Task 10: attribution.py — E-B 盈亏画像

**Files:**
- Create: `my_strategy/tools/__init__.py`
- Create: `my_strategy/tools/attribution.py`
- Create: `my_strategy/tests/test_attribution.py`

- [ ] **Step 1: 创建 tools 包**

Create `my_strategy/tools/__init__.py` 内容为空。

- [ ] **Step 2: 写测试**

Create `my_strategy/tests/test_attribution.py`:

```python
import pandas as pd
from my_strategy.tools.attribution import (
    compute_trade_profile,
    compute_top_bottom_trades,
    compute_sector_winrate,
)


def _make_trade_log():
    return pd.DataFrame({
        'ts_code': ['A.SZ', 'B.SZ', 'C.SZ', 'D.SZ', 'E.SZ'],
        'entry_date': pd.to_datetime(
            ['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05', '2024-01-08']),
        'return_pct': [15.0, 3.0, 0.0, -3.0, -15.0],
        'holding_days': [40, 20, 10, 15, 30],
    })


def _make_signals_log():
    return pd.DataFrame({
        'ts_code': ['A.SZ', 'B.SZ', 'C.SZ', 'D.SZ', 'E.SZ'],
        'date': pd.to_datetime(
            ['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05', '2024-01-08']).date,
        'sector': ['801010.SI', '801010.SI', '801080.SI', '801080.SI', '801120.SI'],
        'factor_roe': [20.0, 15.0, 10.0, 5.0, 0.0],
        'pct_roe': [1.0, 0.7, 0.5, 0.3, 0.0],
        'pct_pe': [0.8, 0.6, 0.5, 0.4, 0.2],
        'pct_momentum_60d': [0.9, 0.7, 0.5, 0.3, 0.1],
    })


def test_compute_trade_profile_buckets_by_return():
    trades = _make_trade_log()
    sigs = _make_signals_log()
    out = compute_trade_profile(trades, sigs)
    # 期望桶：大盈 / 小盈 / 持平 / 小亏 / 大亏 各 1 笔
    assert set(out['bucket']) >= {'大盈', '小盈', '持平', '小亏', '大亏'}
    big_win = out[out['bucket'] == '大盈'].iloc[0]
    big_loss = out[out['bucket'] == '大亏'].iloc[0]
    assert big_win['mean_pct_roe'] > big_loss['mean_pct_roe']


def test_compute_top_bottom_trades_returns_extremes():
    trades = _make_trade_log()
    sigs = _make_signals_log()
    top, bottom = compute_top_bottom_trades(trades, sigs, n=2)
    assert list(top['return_pct']) == [15.0, 3.0]
    assert list(bottom['return_pct']) == [-15.0, -3.0]


def test_compute_sector_winrate_aggregates_by_sector():
    trades = _make_trade_log()
    sigs = _make_signals_log()
    out = compute_sector_winrate(trades, sigs)
    assert 'sector' in out.columns
    assert 'win_rate' in out.columns
    assert 'avg_return' in out.columns
    sw_801010 = out[out['sector'] == '801010.SI'].iloc[0]
    # A.SZ +15, B.SZ +3 → win_rate = 1.0
    assert sw_801010['win_rate'] == 1.0
```

- [ ] **Step 3: 运行测试，确认失败**

Run: `cd my_strategy && python -m pytest tests/test_attribution.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 4: 实现 E-B 三个函数**

Create `my_strategy/tools/attribution.py`:

```python
import pandas as pd
import numpy as np
from pathlib import Path


def _bucket(return_pct):
    if return_pct > 10: return '大盈'
    if return_pct > 0: return '小盈'
    if return_pct == 0: return '持平'
    if return_pct > -10: return '小亏'
    return '大亏'


def _join_trades_with_signals(trades, signals):
    """按 (ts_code, entry_date) 关联 trade_log 和 signals_log。"""
    s = signals.copy()
    s['date'] = pd.to_datetime(s['date'])
    t = trades.copy()
    t['entry_date'] = pd.to_datetime(t['entry_date'])
    return t.merge(s, left_on=['ts_code', 'entry_date'],
                   right_on=['ts_code', 'date'], how='left')


def compute_trade_profile(trades, signals):
    """按收益分桶统计因子均值/中位数。"""
    j = _join_trades_with_signals(trades, signals)
    j['bucket'] = j['return_pct'].apply(_bucket)
    factor_cols = [c for c in j.columns
                   if c.startswith('pct_') or c.startswith('factor_')]
    rows = []
    for bucket, sub in j.groupby('bucket'):
        row = {'bucket': bucket, 'count': len(sub),
               'avg_return': round(sub['return_pct'].mean(), 4),
               'avg_holding_days': round(sub['holding_days'].mean(), 1)
               if 'holding_days' in sub.columns else None}
        for c in factor_cols:
            row[f'mean_{c}'] = round(sub[c].mean(), 6) if not sub[c].dropna().empty else None
            row[f'median_{c}'] = round(sub[c].median(), 6) if not sub[c].dropna().empty else None
        rows.append(row)
    return pd.DataFrame(rows).sort_values('bucket')


def compute_top_bottom_trades(trades, signals, n=10):
    j = _join_trades_with_signals(trades, signals)
    j_sorted = j.sort_values('return_pct', ascending=False)
    return j_sorted.head(n).reset_index(drop=True), j_sorted.tail(n).iloc[::-1].reset_index(drop=True)


def compute_sector_winrate(trades, signals):
    j = _join_trades_with_signals(trades, signals)
    rows = []
    for sector, sub in j.groupby('sector'):
        rows.append({
            'sector': sector,
            'count': len(sub),
            'win_rate': round((sub['return_pct'] > 0).mean(), 4),
            'avg_return': round(sub['return_pct'].mean(), 4),
        })
    return pd.DataFrame(rows).sort_values('avg_return', ascending=False)
```

- [ ] **Step 5: 运行测试**

Run: `cd my_strategy && python -m pytest tests/test_attribution.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add my_strategy/tools/__init__.py my_strategy/tools/attribution.py my_strategy/tests/test_attribution.py
git commit -m "feat(attribution): add E-B trade profile, top/bottom, sector winrate"
```

---

## Task 11: attribution.py — E-C 因子贡献度

**Files:**
- Modify: `my_strategy/tools/attribution.py`
- Modify: `my_strategy/tests/test_attribution.py`

- [ ] **Step 1: 写测试**

Append to `my_strategy/tests/test_attribution.py`:

```python
from my_strategy.tools.attribution import compute_factor_alpha


def test_compute_factor_alpha_picks_top_n_per_day():
    """构造一个高 ROE 信号事后必赚的样本，验证 alpha 计算方向正确。"""
    sigs = pd.DataFrame({
        'ts_code': ['A', 'B', 'C', 'D', 'E', 'F'],
        'date': pd.to_datetime(['2024-01-01'] * 3 + ['2024-01-02'] * 3).date,
        'pct_roe': [0.9, 0.5, 0.1, 0.9, 0.5, 0.1],
        'pct_pe': [0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
        'forward_return_20d': [0.1, 0.05, -0.05, 0.08, 0.04, -0.04],
    })
    out = compute_factor_alpha(sigs, top_n=1, factors=['pct_roe', 'pct_pe'],
                               horizon='forward_return_20d')
    roe_row = out[out['factor'] == 'pct_roe'].iloc[0]
    # 每日 Top-1 by pct_roe = A 和 D：(0.1 + 0.08)/2 = 0.09
    assert abs(roe_row['top_n_avg'] - 0.09) < 1e-6
    # baseline = 全部信号平均 = (0.1+0.05-0.05+0.08+0.04-0.04)/6 ≈ 0.03
    assert roe_row['top_n_avg'] > roe_row['baseline_avg']
    assert roe_row['alpha'] > 0
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd my_strategy && python -m pytest tests/test_attribution.py::test_compute_factor_alpha_picks_top_n_per_day -v`
Expected: FAIL

- [ ] **Step 3: 实现 compute_factor_alpha**

Append to `my_strategy/tools/attribution.py`:

```python
def compute_factor_alpha(signals, top_n=3, factors=None,
                         horizon='forward_return_20d'):
    """对每个因子，按当日截面排序取 Top-N，计算事后 forward_return 平均收益。

    与"全部信号平均"基准对比，超额部分即该因子的 alpha 贡献。
    """
    s = signals.copy()
    if factors is None:
        factors = [c for c in s.columns if c.startswith('pct_')]

    s = s.dropna(subset=[horizon])
    baseline_avg = s[horizon].mean()

    rows = []
    for factor in factors:
        if factor not in s.columns:
            continue
        sub = s.dropna(subset=[factor])
        # 每日按 factor 降序取 Top-N
        top = (sub.sort_values([sub.columns[1] if 'date' not in sub.columns
                                 else 'date', factor],
                                ascending=[True, False])
                  .groupby('date').head(top_n))
        if top.empty:
            continue
        top_avg = top[horizon].mean()
        rows.append({
            'factor': factor,
            'top_n_avg': round(top_avg, 6),
            'baseline_avg': round(baseline_avg, 6),
            'alpha': round(top_avg - baseline_avg, 6),
            'sample_size': len(top),
        })
    return pd.DataFrame(rows).sort_values('alpha', ascending=False)
```

- [ ] **Step 4: 运行测试**

Run: `cd my_strategy && python -m pytest tests/test_attribution.py -v`
Expected: 4 passed

- [ ] **Step 5: 添加 attribution.py 的 main() 入口**

Append to `my_strategy/tools/attribution.py`:

```python
def main():
    import json
    project_root = Path(__file__).resolve().parent.parent
    cfg = json.loads((project_root / 'config.json').read_text())
    sig_path = project_root / cfg['signals_log_path']
    trade_path = project_root / 'results' / 'trade_log.csv'  # 沿用现有约定
    out_dir = project_root / cfg['attribution_report_dir']
    out_dir.mkdir(parents=True, exist_ok=True)

    signals = pd.read_csv(sig_path, parse_dates=['date'])
    trades = pd.read_csv(trade_path, parse_dates=['entry_date'])

    profile = compute_trade_profile(trades, signals)
    profile.to_csv(out_dir / 'trade_profile.csv', index=False)

    top, bottom = compute_top_bottom_trades(trades, signals, n=10)
    top.to_csv(out_dir / 'top_trades.csv', index=False)
    bottom.to_csv(out_dir / 'bottom_trades.csv', index=False)

    sector = compute_sector_winrate(trades, signals)
    sector.to_csv(out_dir / 'sector_winrate.csv', index=False)

    factor_alpha = compute_factor_alpha(signals)
    factor_alpha.to_csv(out_dir / 'factor_alpha.csv', index=False)

    print(f"attribution reports written to {out_dir}")


if __name__ == '__main__':
    main()
```

- [ ] **Step 6: Commit**

```bash
git add my_strategy/tools/attribution.py my_strategy/tests/test_attribution.py
git commit -m "feat(attribution): add E-C factor alpha and main() entrypoint"
```

---

## Task 12: download_all.py 链式 + 端到端 smoke test

**Files:**
- Modify: `my_strategy/download_all.py`

- [ ] **Step 1: 读取当前 download_all.py**

Run: `cat my_strategy/download_all.py`

- [ ] **Step 2: 在末尾追加 downloader_extra.main 和 build_cross_section_pct.main 调用**

确认现有 download_all.py 已经调用 `downloader.main()` 和 `calc_indicators.main()`。在 calc_indicators.main 之前加入 downloader_extra.main，calc_indicators.main 之后加入 build_cross_section_pct.main：

```python
# download_all.py 期望调用顺序（按需调整 import）:
# 1. downloader.main()                       # 现有：日线 OHLCV
# 2. downloader_extra.main()                 # 新：daily_basic + fina + sw_index
# 3. calc_indicators.main()                  # 现有 + 改：合并基本面 + 行业动量
# 4. build_cross_section_pct.main()          # 新：横截面分位数
```

具体编辑：

```python
from my_strategy.src import downloader, downloader_extra, calc_indicators, build_cross_section_pct

# 流程：
downloader.main()
downloader_extra.main()
calc_indicators.main()
build_cross_section_pct.main()
```

（如果当前 download_all.py 是用 `import` 后直接调用、或用 subprocess 调用，沿用同一种风格，不要改变其调用约定。）

- [ ] **Step 3: 全量测试**

Run: `cd my_strategy && python -m pytest -v`
Expected: 全部 PASS

- [ ] **Step 4: 端到端 smoke（仅 1-2 只股票）**

不要在自动化里跑 5500 只股票端到端，但建议手动验证一次：
- 临时把 `stock_list.csv` 备份并裁剪到 2 只股票（如 600519.SH, 000001.SZ）
- 跑：`cd my_strategy && python download_all.py`
- 跑：`cd my_strategy && python backtest.py`
- 跑：`cd my_strategy && python -m my_strategy.tools.attribution`
- 检查 `data/signals_log.csv` 和 `reports/*.csv` 已生成且非空
- 恢复 `stock_list.csv`

注：本步骤为人工验证，agentic worker 跳过；仅在 commit 前由人确认。

- [ ] **Step 5: Commit**

```bash
git add my_strategy/download_all.py
git commit -m "feat(pipeline): chain downloader_extra and build_cross_section_pct in download_all"
```

---

## 完成标准

- [ ] 全部 12 个 Task 通过
- [ ] `cd my_strategy && python -m pytest -v` 100% 通过
- [ ] `data/signals_log.csv` 包含完整字段（含 forward_return_5/20/60d）
- [ ] `reports/` 下生成 `trade_profile.csv`、`top_trades.csv`、`bottom_trades.csv`、`sector_winrate.csv`、`factor_alpha.csv` 五份报告
- [ ] 现有策略行为不变（trade_log/order_log 与本期改动前一致，因为入场/卖出逻辑未动）

完成后下一步：
1. 用 `scorer_enabled=false` 等价的当前行为跑一次完整回测（2019-2024）
2. 跑 `attribution.py` 看哪些因子有 alpha
3. 根据归因结果决定下一版 scorer.py 的初始权重和因子取舍
