# Entry Quality Stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为每笔交易补充5个进场质量维度，新增聚合统计打印，替换持仓数统计，补充基准全区间收益，支持对指数独立运行策略对比。

**Architecture:** 采用事后富化方案：`calc_indicators.py` 新增指标列，回测后 `backtest.py` 按 `(ts_code, entry_date)` join 指标 CSV 富化 trade_summary，`strategy.py` 只做最小改动（持仓数 log），行业信息由 Tushare `pro.stock_basic()` 下载到 `data/stock_sector.csv`。

**Tech Stack:** Python, pandas, backtrader, tushare

---

## File Map

| 文件 | 改动 |
|---|---|
| `my_strategy/calc_indicators.py` | `compute_indicators()` 新增 ma144/ma180/kdj_j |
| `my_strategy/downloader.py` | 新增 `download_sector_info()`，`main()` 末尾调用 |
| `my_strategy/strategy.py` | 移除 `max_capital_utilization`；新增 `position_count_log` |
| `my_strategy/backtest.py` | 新增 `_enrich_trade_summary`、`_print_entry_quality_stats`、`run_index_strategy`；更新 `_print_trade_stats`、`print_results` |

---

## Task 1: 新增 MA144、MA180、KDJ_J 指标

**Files:**
- Modify: `my_strategy/calc_indicators.py`

- [ ] **Step 1: 更新 `compute_indicators` 函数**

完整替换 `my_strategy/calc_indicators.py` 中的 `compute_indicators` 函数：

```python
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['ma25'] = df['close'].rolling(window=25, min_periods=25).mean().round(2)
    df['ma60'] = df['close'].rolling(window=60, min_periods=60).mean().round(2)
    df['ma144'] = df['close'].rolling(window=144, min_periods=144).mean().round(2)
    df['ma180'] = df['close'].rolling(window=180, min_periods=180).mean().round(2)

    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['dif'] = (ema12 - ema26).round(2)
    df['dea'] = df['dif'].ewm(span=9, adjust=False).mean().round(2)
    df['macd'] = (2 * (df['dif'] - df['dea'])).round(2)

    low9 = df['low'].rolling(window=9, min_periods=9).min()
    high9 = df['high'].rolling(window=9, min_periods=9).max()
    rsv = ((df['close'] - low9) / (high9 - low9).replace(0, 1) * 100).clip(0, 100)
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    df['kdj_j'] = (3 * k - 2 * d).round(2)

    return df
```

- [ ] **Step 2: 验证计算结果**

在 `my_strategy/` 目录下运行：
```powershell
cd my_strategy
python -c "
import pandas as pd
from calc_indicators import compute_indicators
df = pd.read_csv('data/000001.SZ.csv', parse_dates=['trade_date'])
df = df.sort_values('trade_date').reset_index(drop=True)
result = compute_indicators(df)
print(result[['trade_date','close','ma144','ma180','kdj_j']].tail(10))
print('新列:', [c for c in result.columns if c in ('ma144','ma180','kdj_j')])
"
```

预期输出：看到 `ma144`, `ma180`, `kdj_j` 列，前144行 ma144/ma180 为 NaN，之后有值，kdj_j 值通常在 -20 到 120 之间。

- [ ] **Step 3: Commit**

```bash
git add my_strategy/calc_indicators.py
git commit -m "feat: add MA144, MA180, KDJ_J to compute_indicators"
```

---

## Task 2: 下载行业分类信息

**Files:**
- Modify: `my_strategy/downloader.py`

- [ ] **Step 1: 新增 `download_sector_info` 函数**

在 `downloader.py` 的 `download_index` 函数之后，添加：

```python
def download_sector_info(data_dir):
    """从 Tushare 下载股票行业分类，存为 stock_sector.csv。"""
    pro = ts.pro_api()
    df = pro.stock_basic(fields='ts_code,industry')
    df.to_csv(Path(data_dir) / 'stock_sector.csv', index=False)
    print(f"行业分类已保存：{len(df)} 条 → {Path(data_dir) / 'stock_sector.csv'}")
```

- [ ] **Step 2: 在 `main()` 末尾调用**

在 `main()` 函数的最后（benchmark 下载循环之后）添加：

```python
    # 下载行业分类
    try:
        download_sector_info(data_dir)
    except Exception as e:
        logging.error(f"sector info: {e}")
        print(f"行业分类下载失败: {e}")
```

- [ ] **Step 3: 验证（需要有效 Tushare token）**

```powershell
cd my_strategy
python -c "
import json, tushare as ts, pandas as pd
from pathlib import Path
from downloader import download_sector_info
cfg = json.load(open('config.json'))
ts.set_token(cfg['tushare_token'])
download_sector_info(cfg['data_dir'])
df = pd.read_csv('data/stock_sector.csv')
print(df.head())
print('行数:', len(df))
"
```

预期：打印出 ts_code 和 industry 两列数据，行数约 5000+。

- [ ] **Step 4: Commit**

```bash
git add my_strategy/downloader.py
git commit -m "feat: add download_sector_info to downloader"
```

---

## Task 3: strategy.py — 移除资金占用率，新增持仓数 log

**Files:**
- Modify: `my_strategy/strategy.py`

- [ ] **Step 1: 替换 `__init__` 中的初始化代码**

将 `__init__` 末尾的：
```python
        self.max_capital_utilization = 0.0
```
替换为：
```python
        self.position_count_log = []
```

- [ ] **Step 2: 替换 `next()` 末尾的更新逻辑**

将 `next()` 末尾（for 循环外）的：
```python
        invested = self.broker.getvalue() - self.broker.getcash()
        util = invested / self.p.initial_cash
        if util > self.max_capital_utilization:
            self.max_capital_utilization = util
```
替换为：
```python
        self.position_count_log.append(self._current_position_count())
```

- [ ] **Step 3: 验证语法**

```powershell
cd my_strategy
python -c "from strategy import MyStrategy; print('OK')"
```

预期：输出 `OK`，无报错。

- [ ] **Step 4: Commit**

```bash
git add my_strategy/strategy.py
git commit -m "feat: replace max_capital_utilization with position_count_log"
```

---

## Task 4: backtest.py — 新增 `_enrich_trade_summary`

**Files:**
- Modify: `my_strategy/backtest.py`

- [ ] **Step 1: 在 `_compute_benchmarks_returns` 函数之前添加辅助函数**

在 `backtest.py` 中，`_compute_benchmarks_returns` 函数定义之前，添加以下两个辅助函数：

```python
def _classify_ma_alignment(row):
    """根据进场当日 MA25/MA60/MA144/MA180 判断排列状态。"""
    ma25 = row.get('ma25')
    ma60 = row.get('ma60')
    ma144 = row.get('ma144')
    ma180 = row.get('ma180')

    has_long = pd.notna(ma144) and pd.notna(ma180)
    if has_long:
        if ma25 > ma60 > ma144 > ma180:
            return '全多头'
        if ma25 < ma60 < ma144 < ma180:
            return '全空头'
    if pd.notna(ma25) and pd.notna(ma60):
        if ma25 > ma60:
            return '局部多头'
        if ma25 < ma60:
            return '局部空头'
    return '混合'


def _classify_macd_zone(row):
    """根据进场当日 MACD/DIF/DEA 判断 MACD 区间。"""
    macd = row.get('macd')
    dif = row.get('dif')
    dea = row.get('dea')
    if pd.isna(macd) or macd <= 0:
        return '区间0'
    if macd > dif and macd > dea:
        return '区间1'
    if dif > macd and dea > macd:
        return '区间3'
    return '区间2'


def _enrich_trade_summary(summary_df, cfg):
    """回测后富化 trade_summary，按 (ts_code, entry_date) join 指标文件，
    新增 entry_kdj_j / entry_ma60_dist_pct / industry / ma_alignment / macd_zone 列。
    返回富化后的 DataFrame。
    """
    if summary_df.empty:
        return summary_df

    data_dir = Path(cfg['data_dir'])

    # 加载行业映射
    sector_path = data_dir / 'stock_sector.csv'
    if sector_path.exists():
        sector_df = pd.read_csv(sector_path)
        sector_map = dict(zip(sector_df['ts_code'], sector_df['industry']))
    else:
        sector_map = {}

    # 按股票分组，批量 join 指标
    enriched_rows = []
    for ts_code, group in summary_df.groupby('ts_code'):
        ind_path = data_dir / f"{ts_code}_indicators.csv"
        if not ind_path.exists():
            for _, row in group.iterrows():
                row = row.copy()
                row['entry_kdj_j'] = None
                row['entry_ma60_dist_pct'] = None
                row['industry'] = sector_map.get(ts_code)
                row['ma_alignment'] = None
                row['macd_zone'] = None
                enriched_rows.append(row)
            continue

        ind_df = pd.read_csv(ind_path, parse_dates=['trade_date'])
        ind_df = ind_df.set_index('trade_date')

        for _, row in group.iterrows():
            row = row.copy()
            entry_date = pd.Timestamp(row['entry_date'])
            row['industry'] = sector_map.get(ts_code)

            if entry_date in ind_df.index:
                r = ind_df.loc[entry_date]
                kdj_j = r.get('kdj_j') if 'kdj_j' in ind_df.columns else None
                ma60 = r.get('ma60')
                close = r.get('close')
                row['entry_kdj_j'] = round(float(kdj_j), 2) if pd.notna(kdj_j) else None
                row['entry_ma60_dist_pct'] = (
                    round((close - ma60) / ma60 * 100, 2)
                    if pd.notna(ma60) and ma60 > 0 and pd.notna(close)
                    else None
                )
                row['ma_alignment'] = _classify_ma_alignment(r)
                row['macd_zone'] = _classify_macd_zone(r)
            else:
                row['entry_kdj_j'] = None
                row['entry_ma60_dist_pct'] = None
                row['ma_alignment'] = None
                row['macd_zone'] = None

            enriched_rows.append(row)

    return pd.DataFrame(enriched_rows).reset_index(drop=True)
```

- [ ] **Step 2: 在 `print_results` 中调用富化，替换原有 summary 保存逻辑**

找到 `print_results` 中保存 `trade_summary.csv` 的代码块：
```python
    summary_df = pd.DataFrame(r.trade_log)
    if not summary_df.empty:
        summary_df.to_csv(results_dir / 'trade_summary.csv', index=False)
        print(f"完整交易汇总已保存到 {results_dir / 'trade_summary.csv'}")
```

替换为：
```python
    summary_df = pd.DataFrame(r.trade_log)
    if not summary_df.empty:
        summary_df = _enrich_trade_summary(summary_df, cfg)
        summary_df.to_csv(results_dir / 'trade_summary.csv', index=False)
        print(f"完整交易汇总已保存到 {results_dir / 'trade_summary.csv'}")
```

- [ ] **Step 3: 验证语法**

```powershell
cd my_strategy
python -c "from backtest import _enrich_trade_summary, _classify_ma_alignment, _classify_macd_zone; print('OK')"
```

预期：输出 `OK`，无报错。

- [ ] **Step 4: Commit**

```bash
git add my_strategy/backtest.py
git commit -m "feat: add _enrich_trade_summary with entry quality dimensions"
```

---

## Task 5: backtest.py — 新增 `_print_entry_quality_stats`

**Files:**
- Modify: `my_strategy/backtest.py`

- [ ] **Step 1: 在 `_print_trade_stats` 函数之前添加 `_print_entry_quality_stats`**

```python
def _print_entry_quality_stats(df):
    """打印进场质量聚合统计（只统计 completed 交易）。"""
    completed = df[df['status'] == 'completed'].copy() if 'status' in df.columns else pd.DataFrame()
    if completed.empty:
        return

    def _group_stats(group_col):
        grp = completed.groupby(group_col).agg(
            笔数=('return_pct', 'count'),
            胜率=('return_pct', lambda x: (x > 0).mean() * 100),
            平均收益=('return_pct', 'mean'),
        ).reset_index()
        return grp

    print("\n========== 进场质量分析 ==========")

    # MA 排列
    if 'ma_alignment' in completed.columns and completed['ma_alignment'].notna().any():
        print("\n--- MA 排列状态 ---")
        grp = _group_stats('ma_alignment')
        print(f"{'MA排列':<10}{'笔数':>6}{'胜率':>8}{'平均收益':>10}")
        print("-" * 36)
        for _, row in grp.iterrows():
            print(f"{str(row['ma_alignment']):<10}{int(row['笔数']):>6}"
                  f"{row['胜率']:>7.1f}%{row['平均收益']:>+9.2f}%")

    # MACD 区间
    if 'macd_zone' in completed.columns and completed['macd_zone'].notna().any():
        print("\n--- MACD 区间 ---")
        grp = _group_stats('macd_zone')
        print(f"{'MACD区间':<10}{'笔数':>6}{'胜率':>8}{'平均收益':>10}")
        print("-" * 36)
        for _, row in grp.sort_values('macd_zone').iterrows():
            print(f"{str(row['macd_zone']):<10}{int(row['笔数']):>6}"
                  f"{row['胜率']:>7.1f}%{row['平均收益']:>+9.2f}%")

    # KDJ_J 分桶
    if 'entry_kdj_j' in completed.columns and completed['entry_kdj_j'].notna().any():
        print("\n--- KDJ_J 分桶 ---")
        bins = [-float('inf'), 20, 50, 80, float('inf')]
        labels = ['<20', '20-50', '50-80', '>80']
        completed['_kdj_bucket'] = pd.cut(completed['entry_kdj_j'], bins=bins, labels=labels)
        grp = _group_stats('_kdj_bucket')
        print(f"{'KDJ_J区间':<12}{'笔数':>6}{'胜率':>8}{'平均收益':>10}")
        print("-" * 38)
        for _, row in grp.iterrows():
            print(f"{str(row['_kdj_bucket']):<12}{int(row['笔数']):>6}"
                  f"{row['胜率']:>7.1f}%{row['平均收益']:>+9.2f}%")
        completed.drop(columns=['_kdj_bucket'], inplace=True)

    # MA60 距离分桶
    if 'entry_ma60_dist_pct' in completed.columns and completed['entry_ma60_dist_pct'].notna().any():
        print("\n--- 进场距 MA60 距离 ---")
        bins = [0, 1, 3, 5, float('inf')]
        labels = ['≤1%', '1-3%', '3-5%', '>5%']
        completed['_dist_bucket'] = pd.cut(
            completed['entry_ma60_dist_pct'].clip(lower=0), bins=bins, labels=labels
        )
        grp = _group_stats('_dist_bucket')
        print(f"{'距MA60':>10}{'笔数':>6}{'胜率':>8}{'平均收益':>10}")
        print("-" * 36)
        for _, row in grp.iterrows():
            print(f"{str(row['_dist_bucket']):>10}{int(row['笔数']):>6}"
                  f"{row['胜率']:>7.1f}%{row['平均收益']:>+9.2f}%")
        completed.drop(columns=['_dist_bucket'], inplace=True)

    # 行业 Top 10
    if 'industry' in completed.columns and completed['industry'].notna().any():
        print("\n--- 按行业汇总（总盈亏 Top 10）---")
        grp = completed.groupby('industry').agg(
            笔数=('return_pct', 'count'),
            胜率=('return_pct', lambda x: (x > 0).mean() * 100),
            总盈亏=('gross_pnl', 'sum'),
            平均收益=('return_pct', 'mean'),
        ).reset_index()
        top10 = grp.nlargest(10, '总盈亏')
        print(f"{'行业':<12}{'笔数':>5}{'胜率':>8}{'总盈亏':>14}{'平均收益':>10}")
        print("-" * 51)
        for _, row in top10.iterrows():
            print(f"{str(row['industry']):<12}{int(row['笔数']):>5}"
                  f"{row['胜率']:>7.1f}%{row['总盈亏']:>14,.0f}{row['平均收益']:>+9.2f}%")

    print("==================================\n")
```

- [ ] **Step 2: 在 `print_results` 中的 `_print_trade_stats` 调用之后，调用新函数**

找到 `print_results` 中调用 `_print_trade_stats` 的代码：
```python
    _print_trade_stats(
        summary_df if not summary_df.empty else pd.DataFrame(),
        annual_returns=annual_returns,
        benchmarks=benchmarks,
        max_cap_util=getattr(r, 'max_capital_utilization', None),
    )
```

替换为：
```python
    _print_trade_stats(
        summary_df if not summary_df.empty else pd.DataFrame(),
        annual_returns=annual_returns,
        benchmarks=benchmarks,
        position_count_log=getattr(r, 'position_count_log', None),
        strategy_annualized=annual_ret if isinstance(annual_ret, float) else None,
    )
    _print_entry_quality_stats(summary_df if not summary_df.empty else pd.DataFrame())
```

- [ ] **Step 3: 验证语法**

```powershell
cd my_strategy
python -c "from backtest import _print_entry_quality_stats; print('OK')"
```

预期：输出 `OK`。

- [ ] **Step 4: Commit**

```bash
git add my_strategy/backtest.py
git commit -m "feat: add _print_entry_quality_stats with 5 entry quality dimensions"
```

---

## Task 6: backtest.py — 持仓数统计 + 基准全区间行

**Files:**
- Modify: `my_strategy/backtest.py`

- [ ] **Step 1: 更新 `_print_trade_stats` 签名，移除 `max_cap_util`，新增 `position_count_log` 和 `strategy_annualized`**

找到函数定义：
```python
def _print_trade_stats(df, annual_returns=None, benchmarks=None, max_cap_util=None):
    """benchmarks: list[dict]，每项含 code / annual {year: pct} / annualized pct。"""
```

替换为：
```python
def _print_trade_stats(df, annual_returns=None, benchmarks=None,
                       position_count_log=None, strategy_annualized=None):
    """benchmarks: list[dict]，每项含 code / annual {year: pct} / annualized pct。"""
```

- [ ] **Step 2: 移除 `max_cap_util` 打印，新增持仓数统计**

找到并删除：
```python
    if max_cap_util is not None:
        print(f"最大资金占用率：{max_cap_util * 100:.1f}%")
```

在 `print(f"总交易笔数：...")` 之后（同一个块内）添加：
```python
    if position_count_log:
        import statistics
        pc = position_count_log
        print(f"最大同时持仓：{max(pc)} 只")
        print(f"最小同时持仓：{min(pc)} 只")
        print(f"平均同时持仓：{sum(pc)/len(pc):.1f} 只")
        print(f"中位数持仓：{statistics.median(pc):.1f} 只")
```

- [ ] **Step 3: 在年度收益表末尾添加"全区间"行**

找到年度收益表的打印循环（`for y in years:` 循环），在循环结束之后添加全区间行：

现有代码末尾（`for y in years` 循环体内）大约是：
```python
            for y in years:
                s = annual_returns[y] * 100
                row = f"{y:<6}  {s:>+7.2f}%"
                for bm in benchmarks:
                    b = bm['annual'].get(y)
                    if b is not None:
                        row += f"  {b:>+7.2f}%  {s - b:>+6.2f}%"
                    else:
                        row += f"  {'N/A':>8}  {'N/A':>7}"
                print(row)
```

在这段 `for y in years` 循环之后，添加全区间行（仍在 `if benchmarks:` 块内）：

```python
            # 全区间行（年化）
            strat_ann_str = f"{strategy_annualized:>+7.2f}%" if isinstance(strategy_annualized, float) else "  N/A   "
            row = f"{'全区间':<6}  {strat_ann_str:>8}"
            for bm in benchmarks:
                excess = strategy_annualized - bm['annualized'] if isinstance(strategy_annualized, float) else None
                bm_str = f"{bm['annualized']:>+7.2f}%"
                exc_str = f"{excess:>+6.2f}%" if excess is not None else "   N/A "
                row += f"  {bm_str}  {exc_str}"
            print(row)
```

同样在 `else`（无 benchmarks）分支的 `for y in years` 循环后添加：
```python
            strat_ann_str = f"{strategy_annualized:>+7.2f}%" if isinstance(strategy_annualized, float) else "  N/A   "
            print(f"{'全区间':<6}  {strat_ann_str:>8}")
```

- [ ] **Step 4: 验证语法**

```powershell
cd my_strategy
python -c "from backtest import _print_trade_stats; print('OK')"
```

预期：输出 `OK`。

- [ ] **Step 5: Commit**

```bash
git add my_strategy/backtest.py
git commit -m "feat: replace max_cap_util with position count stats, add full-period benchmark row"
```

---

## Task 7: backtest.py — 指数策略模拟 `run_index_strategy`

**Files:**
- Modify: `my_strategy/backtest.py`

- [ ] **Step 1: 在文件顶部的 import 中引入 `compute_indicators`**

找到：
```python
from strategy import StockData, StockCommission, MyStrategy
```

替换为：
```python
from strategy import StockData, StockCommission, MyStrategy
from calc_indicators import compute_indicators
```

- [ ] **Step 2: 添加 `run_index_strategy` 函数**

在 `_compute_benchmarks_returns` 函数之后（`_print_trade_stats` 之前）添加：

```python
def run_index_strategy(cfg, index_code):
    """对单个指数独立运行策略（max_positions=1，不与股票池竞争）。
    返回 dict: code / annual_return(年化%) / total_return(总%) / win_rate(%) / n_trades。
    """
    path = Path(cfg['data_dir']) / f"{index_code}.csv"
    if not path.exists():
        return None

    df = pd.read_csv(path, parse_dates=['trade_date'])
    df = df.sort_values('trade_date').reset_index(drop=True)
    df = compute_indicators(df)

    start = datetime.datetime.strptime(cfg['backTest_Start_data'], '%Y%m%d')
    end = datetime.datetime.strptime(cfg['backTest_end_data'], '%Y%m%d')

    feed = StockData(dataname=df, fromdate=start, todate=end)

    cerebro = bt.Cerebro()
    cerebro.adddata(feed, name=index_code)
    cerebro.broker.set_cash(cfg['initial_cash'])
    cerebro.broker.set_coc(True)
    comm = StockCommission(
        commission=cfg['commission_rate'],
        stamp_duty=cfg['stamp_duty'],
    )
    cerebro.broker.addcommissioninfo(comm)
    cerebro.broker.set_slippage_perc(perc=0.0001)
    cerebro.addstrategy(
        MyStrategy,
        initial_cash=cfg['initial_cash'],
        max_positions=1,
        take_profit_1_pct=cfg['take_profit_1_pct'],
        take_profit_2_pct=cfg['take_profit_2_pct'],
        dea_lookback_days=cfg['dea_lookback_days'],
    )
    cerebro.addanalyzer(bt.analyzers.Returns, _name='_Returns', tann=252)
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='_TimeReturn')

    result = cerebro.run()
    r = result[0]

    annual_return = r.analyzers._Returns.get_analysis().get('rnorm100', 0.0)
    time_return = pd.Series(r.analyzers._TimeReturn.get_analysis())
    total_return = ((1 + time_return).cumprod().iloc[-1] - 1) * 100 if not time_return.empty else 0.0

    trade_df = pd.DataFrame(r.trade_log)
    completed = trade_df[trade_df['status'] == 'completed'] if not trade_df.empty else pd.DataFrame()
    win_rate = (completed['return_pct'] > 0).mean() * 100 if not completed.empty else 0.0
    n_trades = len(completed)

    return {
        'code': index_code,
        'annual_return': round(annual_return, 2) if isinstance(annual_return, float) else 0.0,
        'total_return': round(total_return, 2),
        'win_rate': round(win_rate, 1),
        'n_trades': n_trades,
    }
```

- [ ] **Step 3: 在 `print_results` 中调用并打印指数策略结果**

在 `print_results` 函数的末尾（`equity_curve.png` 保存之后）添加：

```python
    # 指数策略模拟
    benchmark_codes = cfg.get('benchmark_codes') or []
    if not benchmark_codes and cfg.get('benchmark_code'):
        benchmark_codes = [cfg['benchmark_code']]
    if benchmark_codes:
        print("\n========== 指数策略回测 ==========")
        print(f"{'指数':<14}{'年化收益':>10}{'总收益':>10}{'胜率':>8}{'笔数':>6}")
        print("-" * 50)
        for code in benchmark_codes:
            res = run_index_strategy(cfg, code)
            if res is None:
                print(f"{code:<14}  {'数据文件不存在':>30}")
                continue
            print(f"{res['code']:<14}{res['annual_return']:>+9.2f}%"
                  f"{res['total_return']:>+9.2f}%"
                  f"{res['win_rate']:>7.1f}%"
                  f"{res['n_trades']:>6}")
        print("==================================\n")
```

- [ ] **Step 4: 验证语法**

```powershell
cd my_strategy
python -c "from backtest import run_index_strategy; print('OK')"
```

预期：输出 `OK`。

- [ ] **Step 5: Commit**

```bash
git add my_strategy/backtest.py
git commit -m "feat: add run_index_strategy for benchmark index backtesting"
```

---

## Task 8: 端到端验证

- [ ] **Step 1: 重新计算所有股票指标**

```powershell
cd my_strategy
python calc_indicators.py
```

预期：每只股票输出 `[N/M] XXXXXX.XX OK`，结束后检查某个 `_indicators.csv` 包含 `ma144/ma180/kdj_j` 列：
```powershell
python -c "
import pandas as pd
df = pd.read_csv('data/000001.SZ_indicators.csv')
print(df.columns.tolist())
print(df[['ma144','ma180','kdj_j']].tail(5))
"
```

- [ ] **Step 2: 下载行业分类（如 Tushare token 有效）**

```powershell
python downloader.py
```

预期末尾输出：`行业分类已保存：XXXX 条 → data/stock_sector.csv`

- [ ] **Step 3: 运行回测**

```powershell
python backtest.py
```

检查输出中包含以下各节：
- `最大同时持仓：N 只` / `最小同时持仓：N 只` / `平均同时持仓：N.N 只` / `中位数持仓：N.N 只`
- 年度收益表有"全区间"行
- `========== 进场质量分析 ==========` 节，包含 MA 排列、MACD 区间、KDJ_J 分桶、距 MA60 距离、行业 Top 10
- `========== 指数策略回测 ==========` 节，列出各指数年化收益和胜率

- [ ] **Step 4: 检查 trade_summary.csv 新列**

```powershell
python -c "
import pandas as pd
df = pd.read_csv('results/trade_summary.csv')
print(df.columns.tolist())
print(df[['ts_code','entry_date','entry_kdj_j','entry_ma60_dist_pct','industry','ma_alignment','macd_zone']].head(10))
"
```

预期：看到 5 个新列，完成状态的交易行均有值（未完成交易的 exit_date 相关字段为 None）。

- [ ] **Step 5: Commit**

```bash
git add my_strategy/results/trade_summary.csv
git commit -m "feat: verified end-to-end entry quality stats pipeline"
```

---

## 用户操作顺序（总结）

1. `python downloader.py` — 下载 `stock_sector.csv`（以及如还没有指数 CSV 的话一并下载）
2. `python calc_indicators.py` — 重新计算所有指标（新增 ma144/ma180/kdj_j）
3. `python backtest.py` — 回测 + 自动富化 + 新统计输出
