"""Fuzzy clustering of owner names → chains vs independents."""
from .chain_detector import (
    cluster_owners,
    annotate_chains,
    normalize_owner_name,
)

__all__ = ["cluster_owners", "annotate_chains", "normalize_owner_name"]
