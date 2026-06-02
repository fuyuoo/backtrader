"""Engine-neutral execution ledger models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class EquityCurvePoint:
    trade_date: date
    cash: float
    position_value: float
    total_value: float
    drawdown: float
    holding_count: int
    exposure: float


@dataclass(frozen=True)
class PositionSnapshot:
    trade_date: date
    symbol: str
    size: float
    price: float
    market_value: float
    cost_basis: float
    unrealized_pnl: float
    unrealized_return: float | None


@dataclass(frozen=True)
class ExecutionAuditEvent:
    event_date: date
    signal_date: date
    symbol: str
    side: str
    event_type: str
    status: str
    reason_code: str
    requested_quantity: int
    executable_quantity: int
    signal_price: float
    order_ref: int | None = None
    blocked_by: str | None = None
    executed_date: date | None = None
    executed_quantity: float | None = None
    executed_price: float | None = None
    commission: float | None = None
    gross_value: float | None = None
    slippage: float | None = None
    cash_after: float | None = None
    value_after: float | None = None
