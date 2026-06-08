"""Business-level deterministic backtest adapter."""

from .baoma import BaomaBusinessRunConfig, BaomaBusinessRunResult, run_baoma_v1_business
from .lifecycle import (
    ExecutionLifecycleComponent,
    LifecycleClosedTrade,
    LifecycleEndRunResult,
    LifecycleExecutionEvent,
    LifecycleLot,
    LifecyclePositionSnapshot,
    LifecycleState,
    ScaleOutStage,
)
from .portfolio import BusinessPortfolioRunResult, run_trend_template_v1_portfolio_business

__all__ = [
    "BaomaBusinessRunConfig",
    "BaomaBusinessRunResult",
    "BusinessPortfolioRunResult",
    "ExecutionLifecycleComponent",
    "LifecycleClosedTrade",
    "LifecycleEndRunResult",
    "LifecycleExecutionEvent",
    "LifecycleLot",
    "LifecyclePositionSnapshot",
    "LifecycleState",
    "ScaleOutStage",
    "run_baoma_v1_business",
    "run_trend_template_v1_portfolio_business",
]
