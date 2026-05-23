"""
Owner-name fuzzy clustering.

Same operator shows up in CMS, state licensing, and Google with slightly
different name strings: "Sunshine Senior Care LLC" vs "Sunshine Sr. Care,
LLC" vs "Sunshine Senior Care, L.L.C." vs "SUNSHINE SR CARE". We need to
collapse those into one chain to count facilities per operator.

Approach:
- Aggressive name normalization (strip suffixes, punctuation, common words)
- rapidfuzz token_set_ratio for similarity
- Greedy single-pass clustering (good enough for ~50k operators; for more,
  switch to blocking by first letter + per-block clustering)
"""
import re
from typing import Dict, List, Optional, Tuple

import pandas as pd
from rapidfuzz import fuzz, process
from tqdm import tqdm


# Tokens that don't help disambiguate operator names and just hurt fuzzy match
_BOILERPLATE = {
    "LLC", "L L C", "INC", "INCORPORATED", "CORP", "CORPORATION",
    "LP", "LLP", "LTD", "LIMITED", "COMPANY", "CO", "GROUP",
    "HOLDINGS", "HOLDING", "PARTNERS", "PARTNERSHIP",
    "THE", "OF", "AND", "&",
    "NURSING", "HEALTHCARE", "HEALTH", "CARE", "SENIOR", "LIVING",
    "OPERATIONS", "OPERATOR", "MANAGEMENT", "MGMT",
    "ASSISTED", "MEMORY", "REHAB", "REHABILITATION",
}


def normalize_owner_name(name: Optional[str]) -> str:
    """Aggressively normalize an owner string for fuzzy matching."""
    if not name or not isinstance(name, str):
        return ""
    s = name.upper()
    # Strip punctuation
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    # Drop boilerplate tokens
    tokens = [t for t in s.split() if t not in _BOILERPLATE]
    return " ".join(tokens)


def cluster_owners(
    owner_names: List[str],
    threshold: int = 88,
    show_progress: bool = True,
) -> Dict[str, int]:
    """
    Greedy clustering: returns a map of normalized name → cluster_id.

    Strategy: for each new name, check against the *representative* of each
    existing cluster (first name added). If similarity ≥ threshold, join.
    Otherwise, start a new cluster. O(n × clusters), which in practice is
    much less than O(n²) since most names start a new cluster.
    """
    name_to_cluster: Dict[str, int] = {}
    cluster_reps: List[str] = []

    unique_names = list({n for n in owner_names if n})
    iterator = tqdm(unique_names, desc="clustering owners") if show_progress else unique_names

    for name in iterator:
        if name in name_to_cluster:
            continue
        if not cluster_reps:
            cluster_reps.append(name)
            name_to_cluster[name] = 0
            continue

        # rapidfuzz.process.extractOne returns (best_match, score, idx)
        best = process.extractOne(name, cluster_reps, scorer=fuzz.token_set_ratio)
        if best and best[1] >= threshold:
            name_to_cluster[name] = best[2]
        else:
            name_to_cluster[name] = len(cluster_reps)
            cluster_reps.append(name)

    return name_to_cluster


def annotate_chains(
    df: pd.DataFrame,
    owner_col: str = "legal_owner",
    min_chain_size: int = 3,
    threshold: int = 88,
) -> pd.DataFrame:
    """
    Add `chain_id`, `chain_size`, `is_chain`, `owner_normalized` columns.

    `owner_col` lets you point at whichever column holds the operator name
    in your merged dataset (legal_owner, true_owner, primary_owner, etc.).
    """
    if owner_col not in df.columns:
        print(f"[chain_detector] column '{owner_col}' not in df — skipping")
        return df

    out = df.copy()
    out["owner_normalized"] = out[owner_col].apply(normalize_owner_name)
    mapping = cluster_owners(out["owner_normalized"].tolist(), threshold=threshold)
    out["chain_id"] = out["owner_normalized"].map(mapping)

    sizes = out.groupby("chain_id").size()
    out["chain_size"] = out["chain_id"].map(sizes).fillna(1).astype(int)
    out["is_chain"] = out["chain_size"] >= min_chain_size

    return out


def chain_summary(df: pd.DataFrame) -> pd.DataFrame:
    """One row per chain — useful for portfolio roll-up targeting."""
    required = {"chain_id", "owner_normalized"}
    if not required.issubset(df.columns):
        return pd.DataFrame()

    agg: Dict[str, Tuple[str, str]] = {}
    if "beds" in df.columns:
        agg["total_beds"] = ("beds", lambda s: pd.to_numeric(s, errors="coerce").sum())
    if "state" in df.columns:
        agg["states"] = ("state", lambda s: ", ".join(sorted(set(s.dropna()))))
    if "name" in df.columns:
        agg["facility_count"] = ("name", "count")

    grouped = df.groupby("chain_id").agg(
        chain_label=("owner_normalized", "first"),
        **agg,
    ).reset_index()

    return grouped.sort_values("facility_count", ascending=False)
