"""
Owner identification and contact enrichment.

Each enrichment function takes a facility dict and returns the same dict with
new fields populated. Enrichers are intentionally independent — call only the
ones you have API credits for.
"""
from .property_records import enrich_with_property_records
from .company_lookup import enrich_with_company_lookup
from .contact_finder import enrich_with_contacts
from .tired_owner import enrich_with_tired_owner_signals
from .tax_records import enrich_with_tax_records
from .skip_trace import skip_trace_owner
from .market_demand import (
    enrich_with_market_demand,
    add_supply_density,
    score_market_demand,
)

__all__ = [
    "enrich_with_property_records",
    "enrich_with_company_lookup",
    "enrich_with_contacts",
    "enrich_with_tired_owner_signals",
    "enrich_with_tax_records",
    "skip_trace_owner",
    "enrich_with_market_demand",
    "add_supply_density",
    "score_market_demand",
]
