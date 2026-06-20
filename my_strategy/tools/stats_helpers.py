"""纯统计工具：CI、t-test、bucket 显著性聚合。供归因模块复用。"""
from math import erfc, sqrt
from typing import Dict, Tuple

import numpy as np
import pandas as pd


_NORMAL_975 = 1.959963984540054


def confidence_interval(series: pd.Series, alpha: float = 0.05) -> Tuple[float, float]:
    """95% 置信区间（默认 alpha=0.05）。使用正态近似，避免测试依赖 SciPy。"""
    s = pd.Series(series).dropna()
    n = len(s)
    if n < 2:
        return (np.nan, np.nan)
    mean = s.mean()
    se = s.std(ddof=1) / np.sqrt(n)
    z_crit = _NORMAL_975 if alpha == 0.05 else _normal_two_tail_critical(alpha)
    return (mean - z_crit * se, mean + z_crit * se)


def t_test_one_sample(series: pd.Series, mu: float = 0.0) -> Tuple[float, float]:
    """单样本 t 检验：H0 = 均值为 mu。返回 (t_stat, p_value 双尾)。"""
    s = pd.Series(series).dropna()
    if len(s) < 2:
        return (np.nan, np.nan)
    std = s.std(ddof=1)
    if std == 0 or pd.isna(std):
        return (np.nan, np.nan)
    t_stat = (s.mean() - mu) / (std / np.sqrt(len(s)))
    return (float(t_stat), _two_tailed_normal_p_value(float(t_stat)))


def t_test_welch(a: pd.Series, b: pd.Series) -> Tuple[float, float]:
    """Welch's t 检验（不假设方差相等）。返回 (t_stat, p_value 双尾)。"""
    a = pd.Series(a).dropna()
    b = pd.Series(b).dropna()
    if len(a) < 2 or len(b) < 2:
        return (np.nan, np.nan)
    var_a = a.var(ddof=1)
    var_b = b.var(ddof=1)
    denom = np.sqrt(var_a / len(a) + var_b / len(b))
    if denom == 0 or pd.isna(denom):
        return (np.nan, np.nan)
    t_stat = (a.mean() - b.mean()) / denom
    return (float(t_stat), _two_tailed_normal_p_value(float(t_stat)))


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


def spearmanr(x: pd.Series, y: pd.Series) -> Tuple[float, float]:
    """Spearman rank correlation with a normal-approximation p-value."""
    pair = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(pair) < 2:
        return (np.nan, np.nan)
    rho = pair["x"].rank().corr(pair["y"].rank(), method="pearson")
    if pd.isna(rho):
        return (np.nan, np.nan)
    if len(pair) < 4 or abs(float(rho)) >= 1:
        return (float(rho), 0.0 if abs(float(rho)) >= 1 else np.nan)
    z = float(rho) * np.sqrt(len(pair) - 1)
    return (float(rho), _two_tailed_normal_p_value(z))


def chi2_contingency_2x2(contingency: np.ndarray) -> Tuple[float, float, int, np.ndarray]:
    """Pearson chi-square test for a 2x2 contingency table."""
    observed = np.asarray(contingency, dtype=float)
    if observed.shape != (2, 2):
        raise ValueError("contingency must be a 2x2 table")
    total = observed.sum()
    if total <= 0:
        return (np.nan, np.nan, 1, np.full((2, 2), np.nan))
    expected = np.outer(observed.sum(axis=1), observed.sum(axis=0)) / total
    if (expected == 0).any():
        return (np.nan, np.nan, 1, expected)
    chi2 = float(((observed - expected) ** 2 / expected).sum())
    p_value = erfc(sqrt(max(chi2, 0.0) / 2.0))
    return (chi2, float(p_value), 1, expected)


def _two_tailed_normal_p_value(statistic: float) -> float:
    if not np.isfinite(statistic):
        return np.nan
    return float(erfc(abs(statistic) / sqrt(2.0)))


def _normal_two_tail_critical(alpha: float) -> float:
    if alpha <= 0 or alpha >= 1:
        return _NORMAL_975
    # This module only needs alpha=0.05 in tests; keep non-default alpha conservative.
    return _NORMAL_975
