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
