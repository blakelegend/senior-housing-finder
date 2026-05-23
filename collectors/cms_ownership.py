"""
CMS Nursing Home Ownership dataset.

Distinct from the Provider Information dataset — this one exposes the
**individual owners and management companies** behind each nursing home,
along with their ownership %, role, and association start date.

Source: https://data.cms.gov/provider-data/dataset/kvbk-r2ea
- Federal Provider Number links to the facility table
- Multiple owner rows per facility (5%+ ownership disclosure)
- Includes role: 5% OR GREATER DIRECT OWNERSHIP INTEREST, MANAGING EMPLOYEE,
  OFFICER, DIRECTOR, OPERATIONAL/MANAGERIAL CONTROL, etc.

This is the single highest-signal dataset for senior-housing acquisitions —
it answers "who actually owns this place" without paid enrichment.
"""
import io
from typing import List, Optional

import pandas as pd
from rapidfuzz import fuzz

from ..config import CONFIG
from ..utils.http import polite_get

OWNERSHIP_API = "https://data.cms.gov/provider-data/api/1/datastore/query/kvbk-r2ea/0"
OWNERSHIP_CSV = "https://data.cms.gov/provider-data/sites/default/files/resources/NH_Ownership.csv"


def _fetch() -> pd.DataFrame:
    """Try CSV first (fastest), fall back to paginated API."""
    try:
        resp = polite_get(OWNERSHIP_CSV, use_cache=True)
        return pd.read_csv(io.StringIO(resp.text), low_memory=False)
    except Exception:
        pass

    frames = []
    offset = 0
    page = 5000
    while True:
        try:
            resp = polite_get(OWNERSHIP_API, params={"limit": page, "offset": offset})
        except Exception:
            break
        rows = resp.json().get("results", [])
        if not rows:
            break
        frames.append(pd.DataFrame(rows))
        if len(rows) < page:
            break
        offset += page
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def collect_cms_ownership(states: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Return ownership records keyed by CMS provider number.

    Caller can merge this onto facility rows via `cms_id`.
    """
    df = _fetch()
    if df.empty:
        return df

    rename = {
        "CMS Certification Number (CCN)": "cms_id",
        "Federal Provider Number": "cms_id",
        "Provider Name": "facility_name",
        "Provider State": "state",
        "Owner Name": "owner_name",
        "Owner Type": "owner_type",
        "Owner Role": "owner_role",
        "Owner Percentage": "owner_pct",
        "Association Date": "association_date",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    keep = [c for c in (
        "cms_id", "facility_name", "state",
        "owner_name", "owner_type", "owner_role", "owner_pct", "association_date",
    ) if c in df.columns]
    df = df[keep].copy()

    if states and "state" in df.columns:
        df = df[df["state"].isin([s.strip().upper() for s in states])]

    return df


def aggregate_owners_per_facility(ownership_df: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse one-row-per-owner into one-row-per-facility with summary fields.

    Output columns:
      cms_id, primary_owner, all_owners (semicolon list), owner_count,
      majority_owner_pct, has_corporate_owner, oldest_association_date
    """
    if ownership_df.empty:
        return pd.DataFrame()

    def _summarize(grp: pd.DataFrame) -> pd.Series:
        # Primary owner = highest %, fall back to first row
        if "owner_pct" in grp.columns:
            try:
                grp_sorted = grp.assign(_pct=pd.to_numeric(grp["owner_pct"], errors="coerce")).sort_values("_pct", ascending=False)
            except Exception:
                grp_sorted = grp
        else:
            grp_sorted = grp

        primary = grp_sorted.iloc[0]["owner_name"] if "owner_name" in grp_sorted.columns else None
        owners = grp_sorted["owner_name"].dropna().unique() if "owner_name" in grp_sorted.columns else []
        max_pct = grp_sorted["_pct"].max() if "_pct" in grp_sorted.columns else None
        has_corp = any(("LLC" in str(o).upper() or "INC" in str(o).upper() or "CORP" in str(o).upper())
                       for o in owners)
        oldest = grp_sorted["association_date"].min() if "association_date" in grp_sorted.columns else None

        return pd.Series({
            "primary_owner": primary,
            "all_owners": "; ".join(owners),
            "owner_count": len(owners),
            "majority_owner_pct": max_pct,
            "has_corporate_owner": has_corp,
            "oldest_association_date": oldest,
        })

    return ownership_df.groupby("cms_id", as_index=False).apply(_summarize).reset_index(drop=True)


def detect_likely_chains(per_facility: pd.DataFrame, min_facilities: int = 3, fuzzy_threshold: int = 90) -> pd.DataFrame:
    """
    Group facilities by primary owner using fuzzy matching to handle name drift
    (e.g. "Sunshine Senior Care LLC" vs "Sunshine Senior Care, LLC").

    Returns the same df with an added `chain_id` column. Owners with at least
    `min_facilities` properties are flagged as chains.
    """
    if per_facility.empty or "primary_owner" not in per_facility.columns:
        return per_facility

    df = per_facility.copy()
    df["primary_owner_norm"] = df["primary_owner"].fillna("").str.upper().str.replace(r"[^A-Z0-9 ]", "", regex=True).str.strip()

    # Greedy clustering — for each unseen name, find all rows within threshold
    chain_ids: dict = {}
    next_id = 0
    for name in df["primary_owner_norm"].unique():
        if not name or name in chain_ids:
            continue
        # Compare to existing cluster representatives
        matched = False
        for rep, cid in list(chain_ids.items()):
            if fuzz.token_set_ratio(name, rep) >= fuzzy_threshold:
                chain_ids[name] = cid
                matched = True
                break
        if not matched:
            chain_ids[name] = next_id
            next_id += 1

    df["chain_id"] = df["primary_owner_norm"].map(chain_ids)
    counts = df.groupby("chain_id")["cms_id"].nunique()
    df["chain_size"] = df["chain_id"].map(counts)
    df["is_chain"] = df["chain_size"] >= min_facilities
    return df.drop(columns=["primary_owner_norm"])
