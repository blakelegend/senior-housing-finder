"""
Data collectors — each module pulls from one public source and returns a
normalized list of `Facility` dicts. The pipeline merges them downstream.
"""
from .cms_nursing_home import collect_cms_nursing_homes
from .cms_ownership import collect_cms_ownership, aggregate_owners_per_facility, detect_likely_chains
from .google_places import collect_google_places
from .google_maps_scraper import collect_google_maps
from .nic import collect_nic_market_snapshots, collect_nic_facilities
from .state_licensing import collect_state_licensing, list_supported_states
from .medicare import collect_medicare_providers

__all__ = [
    "collect_cms_nursing_homes",
    "collect_cms_ownership",
    "aggregate_owners_per_facility",
    "detect_likely_chains",
    "collect_google_places",
    "collect_google_maps",
    "collect_nic_market_snapshots",
    "collect_nic_facilities",
    "collect_state_licensing",
    "list_supported_states",
    "collect_medicare_providers",
]
