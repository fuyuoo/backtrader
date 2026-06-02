"""Industry reference records for post-run attribution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ShenwanIndustryClassification:
    index_code: str
    industry_name: str
    level: int
    industry_code: str
    parent_code: str
    source: str = "SW2021"

    def __post_init__(self) -> None:
        if self.level not in {1, 2, 3}:
            raise ValueError("Shenwan industry level must be 1, 2, or 3")


@dataclass(frozen=True)
class StockIndustryMembership:
    symbol: str
    stock_name: str
    level1_code: str
    level1_name: str
    level2_code: str
    level2_name: str
    level3_code: str
    level3_name: str
    in_date: date
    out_date: date | None
    is_new: bool
    source: str = "SW2021"

    def active_on(self, trade_date: date) -> bool:
        if trade_date < self.in_date:
            return False
        return self.out_date is None or trade_date <= self.out_date
