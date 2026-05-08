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
