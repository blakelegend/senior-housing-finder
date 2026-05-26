"""
CMS Nursing Home Ownership dataset.

Distinct from the Provider Information dataset — this one exposes the
**individual owners and management companies** behind each nursing home,
along with their ownership %, role, and association start date.

Source: https://data.cms.gov/provider-data/dataset/y2hd-n93e
  (Renamed from kvbk-r2ea in 2024 — old identifier is dead)

- Federal Provider Number links to the facility table
- Multiple owner rows per facility (5%+ ownership disclosure)
- Includes role: 5% OR GREATER DIRECT OWNERSHIP INTEREST, MANAGING EMPLOYEE,
  OFFICER, DIRECTOR, OPERATIONAL/MANAGERIAL CONTROL, etc.

This is the single highest-signal dataset for senior-housing acquisitions —
it answers "who actually owns this place" AND when they bought in (the
association date drives the 8-20 year transition-window scoring).
"""
import io
from typing import List, Optional

import pandas as pd
from rapidfuzz import fuzz

from ..config import CONFIG
from ..utils.http_client import polite_get

DATASET_ID = "y2hd-n93e"  # CMS Ownership (renamed from kvbk-r2ea in 2024)
METASTORE_URL = f"https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/{DATASET_ID}"
OWNERSHIP_API = f"https://data.cms.gov/provider-data/api/1/datastore/query/{DATASET_ID}/0"


def _resolve_current_csv_url() -> Optional[str]:
    """Look up the current CSV download URL via the CMS metastore.

    CMS rotates the date in the filename monthly (e.g. NH_Ownership_Apr2026.csv).
    """
    try:
        resp = polite_get(METASTORE_URL, use_cache=False, rps=1.0)
        meta = resp.json()
    except Exception as e:
        print(f"[cms_ownership] metastore lookup failed: {e}")
        return None
    for dist in meta.get("distribution", []):
        url = dist.get("downloadURL")
        if url and url.endswith(".csv"):
            return url
    return None


def _fetch() -> pd.DataFrame:
    """Resolve current CSV via metastore; fall back to paginated API."""
    url = _resolve_current_csv_url()
    if url:
        try:
            resp = polite_get(url, use_cache=True, rps=0.5)
            return pd.read_csv(io.StringIO(resp.text), low_memory=False)
        except Exception as e:
            print(f"[cms_ownership] CSV download failed for {url}: {e}")

    # Paginated JSON fallback
    frames = []
    offset = 0
    page = 5000
    while True:
        try:
            resp = polite_get(OWNERSHIP_API, params={"limit": page, "offset": offset})
        except Exception as e:
            print(f"[cms_ownership] datastore page failed at offset {offset}: {e}")
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
        # Spaced (CSV) column names — current Apr 2026 dataset uses "State"
        "CMS Certification Number (CCN)": "cms_id",
        "Federal Provider Number": "cms_id",
        "Provider Name": "facility_name",
        "State": "state",
        "Provider State": "state",
        "Owner Name": "owner_name",
        "Owner Type": "owner_type",
        "Role played by Owner or Manager in Facility": "owner_role",
        "Role Played by Owner or Manager in Facility": "owner_role",
        "Owner Role": "owner_role",
        "Ownership Percentage": "owner_pct",
        "Owner Percentage": "owner_pct",
        "Association Date": "association_date",
        # snake_case (datastore JSON) column names
        "cms_certification_number_ccn": "cms_id",
        "provider_name": "facility_name",
        "state": "state",
        "owner_name": "owner_name",
        "owner_type": "owner_type",
        "role_played_by_owner_or_manager_in_facility": "owner_role",
        "ownership_percentage": "owner_pct",
        "association_date": "association_date",
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
