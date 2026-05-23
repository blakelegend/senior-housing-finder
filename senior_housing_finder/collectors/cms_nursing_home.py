"""
CMS Nursing Home Compare / Provider Information dataset.

Source: https://data.cms.gov/provider-data/dataset/4pq5-n9py
- Free, public, no API key required
- Updated monthly
- Covers all CMS-certified nursing homes nationwide

We pull the CSV directly so we get the full dataset in one request, then filter
in pandas. This is more efficient than paginating the Socrata API for our use.
"""
import io
from typing import List, Optional

import pandas as pd

from ..config import CONFIG
from ..utils.http import polite_get

# The dataset's stable CSV endpoint
CMS_PROVIDER_CSV = (
    "https://data.cms.gov/provider-data/sites/default/files/resources/"
    "ccaf062d75e96f15c01b7c75e0a48cce_1700006400/NH_ProviderInfo_Oct2023.csv"
)

# Fallback to Socrata-style endpoint that always serves the current dataset
CMS_PROVIDER_API = "https://data.cms.gov/provider-data/api/1/datastore/query/4pq5-n9py/0"


def _fetch_via_socrata(limit: int = 50000) -> pd.DataFrame:
    """Pull rows in pages from the Socrata-backed datastore endpoint."""
    frames = []
    offset = 0
    page_size = 5000
    while offset < limit:
        resp = polite_get(
            CMS_PROVIDER_API,
            params={"limit": page_size, "offset": offset},
            rps=CONFIG.default_rps,
        )
        payload = resp.json()
        rows = payload.get("results", []) or payload.get("data", [])
        if not rows:
            break
        frames.append(pd.DataFrame(rows))
        if len(rows) < page_size:
            break
        offset += page_size
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _fetch_via_csv() -> pd.DataFrame:
    resp = polite_get(CMS_PROVIDER_CSV, use_cache=True)
    return pd.read_csv(io.StringIO(resp.text), low_memory=False)


# safe-mode patched
def _raw_collect_cms_nursing_homes(states: Optional[List[str]] = None) -> List[dict]:
    """
    Return a list of normalized facility dicts from CMS Nursing Home data.

    Each row carries: federal provider number, name, address, ownership info,
    bed count, and certification date — exactly what we need to score "old
    ownership" downstream.
    """
    states = states or CONFIG.target_states

    try:
        df = _fetch_via_csv()
    except Exception:
        # Fall back to the paginated JSON API if CSV link breaks
        df = _fetch_via_socrata()

    if df.empty:
        return []

    # CMS column names vary slightly between dataset versions; normalize
    rename = {
        "Federal Provider Number": "cms_id",
        "CMS Certification Number (CCN)": "cms_id",
        "Provider Name": "name",
        "Provider Address": "address",
        "Provider City": "city",
        "Provider State": "state",
        "Provider Zip Code": "zip",
        "Provider Phone Number": "phone",
        "Ownership Type": "ownership_type",
        "Number of Certified Beds": "beds",
        "Date First Approved to Provide Medicare and Medicaid Services": "cert_date",
        "Legal Business Name": "legal_owner",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    keep = [c for c in (
        "cms_id", "name", "address", "city", "state", "zip", "phone",
        "ownership_type", "beds", "cert_date", "legal_owner",
    ) if c in df.columns]
    df = df[keep].copy()

    if "state" in df.columns and states:
        df = df[df["state"].isin([s.strip().upper() for s in states])]

    df["source"] = "CMS"
    return df.to_dict(orient="records")


def collect_cms_nursing_homes(states=None):
    """Safe wrapper: never crashes the pipeline if CMS API is down."""
    try:
        return _raw_collect_cms_nursing_homes(states)
    except Exception as e:
        print(f"[cms_nursing_home] FAILED: {e}; returning empty list")
        return []
