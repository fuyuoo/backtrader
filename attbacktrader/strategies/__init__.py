"""Strategy templates, methods, and intent models."""

from .attribution import (
    ENTRY_ATTRIBUTION_INDICATOR_REQUIREMENTS,
    EntryAttributionContext,
    EntryAttributionEvidence,
    EntryAttributionFilterRule,
    EntryAttributionFactorDeclaration,
    apply_entry_attribution_filter,
    build_entry_attribution_context,
    entry_attribution_declaration_by_key,
    entry_attribution_factor_keys,
    entry_attribution_factor_declarations,
    entry_attribution_payload,
    with_enabled_entry_attribution_factors,
    with_entry_attribution_controls,
    with_entry_attribution_evidence,
    with_sizing_attribution,
)
from .intents import TradeIntent, TradeIntentType

__all__ = [
    "ENTRY_ATTRIBUTION_INDICATOR_REQUIREMENTS",
    "EntryAttributionContext",
    "EntryAttributionEvidence",
    "EntryAttributionFilterRule",
    "EntryAttributionFactorDeclaration",
    "TradeIntent",
    "TradeIntentType",
    "apply_entry_attribution_filter",
    "build_entry_attribution_context",
    "entry_attribution_declaration_by_key",
    "entry_attribution_factor_keys",
    "entry_attribution_factor_declarations",
    "entry_attribution_payload",
    "with_enabled_entry_attribution_factors",
    "with_entry_attribution_controls",
    "with_entry_attribution_evidence",
    "with_sizing_attribution",
]
