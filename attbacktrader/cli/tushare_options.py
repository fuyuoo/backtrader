"""Shared CLI options for Tushare-backed commands."""

from __future__ import annotations

import argparse
from typing import Any

from attbacktrader.data.providers import TushareRateLimitConfig


def add_tushare_rate_limit_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--tushare-requests-per-minute",
        type=float,
        default=None,
        help="Throttle Tushare calls to this many requests per minute; env ATT_TUSHARE_REQUESTS_PER_MINUTE is used if omitted",
    )
    parser.add_argument(
        "--tushare-retry-attempts",
        type=int,
        default=None,
        help="Retry transient Tushare failures this many times; env ATT_TUSHARE_RETRY_ATTEMPTS is used if omitted",
    )
    parser.add_argument(
        "--tushare-date-window-days",
        type=int,
        default=None,
        help="Split date-range Tushare calls into windows of this many days; env ATT_TUSHARE_DATE_WINDOW_DAYS is used if omitted",
    )


def tushare_rate_limit_config_from_args(args: Any) -> TushareRateLimitConfig:
    return TushareRateLimitConfig.from_overrides(
        requests_per_minute=args.tushare_requests_per_minute,
        retry_attempts=args.tushare_retry_attempts,
        date_window_days=args.tushare_date_window_days,
    )
