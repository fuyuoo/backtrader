"""Post-run industry attribution calculations."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

from attbacktrader.data import StockIndustryMembership
from attbacktrader.reports import IndustryAttributionSummary
from attbacktrader.strategies.templates import ClosedTrade


def attribute_trades_by_shenwan_industry(
    closed_trades: Sequence[ClosedTrade],
    *,
    memberships_by_symbol: Mapping[str, Sequence[StockIndustryMembership]],
    levels: Sequence[int] = (1, 2, 3),
) -> tuple[IndustryAttributionSummary, ...]:
    returns_by_bucket: dict[tuple[int, str, str], list[float]] = defaultdict(list)

    for trade in closed_trades:
        membership = _membership_for_trade(trade, memberships_by_symbol.get(trade.symbol, ()))
        if membership is None:
            continue

        for level in levels:
            industry_code, industry_name = _industry_for_level(membership, level)
            returns_by_bucket[(level, industry_code, industry_name)].append(trade.return_pct)

    summaries = [
        IndustryAttributionSummary(
            level=level,
            industry_code=industry_code,
            industry_name=industry_name,
            trade_count=len(values),
            average_return=sum(values) / len(values),
            contribution_return=sum(values),
        )
        for (level, industry_code, industry_name), values in returns_by_bucket.items()
    ]

    return tuple(sorted(summaries, key=lambda item: (item.level, item.industry_code)))


def _membership_for_trade(
    trade: ClosedTrade,
    memberships: Sequence[StockIndustryMembership],
) -> StockIndustryMembership | None:
    active = [membership for membership in memberships if membership.active_on(trade.exit_date)]
    if active:
        return sorted(active, key=lambda membership: membership.in_date)[-1]
    return None


def _industry_for_level(membership: StockIndustryMembership, level: int) -> tuple[str, str]:
    if level == 1:
        return membership.level1_code, membership.level1_name
    if level == 2:
        return membership.level2_code, membership.level2_name
    if level == 3:
        return membership.level3_code, membership.level3_name
    raise ValueError("Shenwan industry level must be 1, 2, or 3")
