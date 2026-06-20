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
