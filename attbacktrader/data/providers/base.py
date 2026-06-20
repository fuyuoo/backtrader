"""Provider protocols used by the run-plan executor."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from attbacktrader.data import (
    DailyBar,
    IndexBar,
    ShenwanIndustryClassification,
    StockIndustryMembership,
    TradabilityStatus,
)


class DailyBarProvider(Protocol):
    def fetch_daily_bars(
        self,
        *,
        symbol: str,
        start_date: date,
        end_date: date,
        adjustment: str,
    ) -> tuple[DailyBar, ...]:
        """Fetch daily bars for one symbol and date range."""


class IndexBarProvider(Protocol):
    def fetch_index_daily_bars(
        self,
        *,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> tuple[IndexBar, ...]:
        """Fetch index daily bars for one benchmark or decision series."""

    def fetch_industry_index_daily_bars(
        self,
        *,
        symbol: str,
        start_date: date,
        end_date: date,
        source: str = "SW2021",
    ) -> tuple[IndexBar, ...]:
        """Fetch industry index daily bars for attribution and market-regime analysis."""


class IndustryProvider(Protocol):
    def fetch_shenwan_industry_classifications(
        self,
        *,
        source: str = "SW2021",
    ) -> tuple[ShenwanIndustryClassification, ...]:
        """Fetch Shenwan industry hierarchy definitions."""

    def fetch_stock_industry_memberships(
        self,
        *,
        symbol: str,
        source: str = "SW2021",
    ) -> tuple[StockIndustryMembership, ...]:
        """Fetch Shenwan industry membership history for one stock."""

    def fetch_all_stock_industry_memberships(
        self,
        *,
        source: str = "SW2021",
    ) -> tuple[StockIndustryMembership, ...]:
        """Fetch Shenwan industry membership history for the full A-share universe."""


class TradabilityProvider(Protocol):
    def fetch_tradability_statuses(
        self,
        *,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> tuple[TradabilityStatus, ...]:
        """Fetch daily tradability state for one symbol and date range."""


class RunDataProvider(DailyBarProvider, IndexBarProvider, IndustryProvider, TradabilityProvider, Protocol):
    """Provider contract required by the config-driven run-plan executor."""
