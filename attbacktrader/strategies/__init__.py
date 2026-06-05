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
from .contract import (
    STRATEGY_OUTPUT_CONTRACT_SCHEMA,
    StrategyOutputContractIssue,
    build_strategy_output_contract,
    trade_intent_satisfies_output_contract,
    validate_trade_intent_output_contract,
)
from .integration_template import (
    STRATEGY_INTEGRATION_TEMPLATE_SCHEMA,
    build_strategy_integration_template,
    render_strategy_integration_template_markdown_zh,
)
from .intents import TradeIntent, TradeIntentType

__all__ = [
    "ENTRY_ATTRIBUTION_INDICATOR_REQUIREMENTS",
    "STRATEGY_INTEGRATION_TEMPLATE_SCHEMA",
    "STRATEGY_OUTPUT_CONTRACT_SCHEMA",
    "EntryAttributionContext",
    "EntryAttributionEvidence",
    "EntryAttributionFilterRule",
    "EntryAttributionFactorDeclaration",
    "StrategyOutputContractIssue",
    "TradeIntent",
    "TradeIntentType",
    "apply_entry_attribution_filter",
    "build_entry_attribution_context",
    "build_strategy_integration_template",
    "build_strategy_output_contract",
    "entry_attribution_declaration_by_key",
    "entry_attribution_factor_keys",
    "entry_attribution_factor_declarations",
    "render_strategy_integration_template_markdown_zh",
    "trade_intent_satisfies_output_contract",
    "validate_trade_intent_output_contract",
    "entry_attribution_payload",
    "with_enabled_entry_attribution_factors",
    "with_entry_attribution_controls",
    "with_entry_attribution_evidence",
    "with_sizing_attribution",
]
