"""
CMS Nursing Home Compare / Provider Information dataset.

Source: https://data.cms.gov/provider-data/dataset/4pq5-n9py
- Free, public, no API key required
- Updated monthly (CMS rotates the date in the CSV filename each month —
  we resolve the current download URL dynamically via the metastore so we
  never hard-code a stale file)
- Covers all CMS-certified nursing homes nationwide

Why CSV-first, not the JSON datastore: the JSON `/api/1/datastore/query/{id}/0`
endpoint returns 400 for some egress IPs (observed on Render's network) even
though it works from local dev. The CSV is CDN-served and reliable.
"""
import io
from typing import List, Optional

import pandas as pd

from ..config import CONFIG
from ..utils.http_client import polite_get

DATASET_ID = "4pq5-n9py"  # CMS Provider Information (Socrata-style identifier)
METASTORE_URL = f"https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/{DATASET_ID}"
DATASTORE_QUERY_URL = f"https://data.cms.gov/provider-data/api/1/datastore/query/{DATASET_ID}/0"


def _resolve_current_csv_url() -> Optional[str]:
    """Look up the current CSV download URL via the CMS metastore.

    CMS embeds a date in the filename (e.g. NH_ProviderInfo_Apr2026.csv) that
    rotates monthly. Resolving via metastore avoids hard-coding stale URLs.
    """
    try:
        resp = polite_get(METASTORE_URL, use_cache=False, rps=1.0)
        meta = resp.json()
    except Exception as e:
        print(f"[cms_nursing_home] metastore lookup failed: {e}")
        return None
    for dist in meta.get("distribution", []):
        url = dist.get("downloadURL")
        if url and url.endswith(".csv"):
            return url
    return None


def _fetch_via_csv() -> pd.DataFrame:
    url = _resolve_current_csv_url()
    if not url:
        print("[cms_nursing_home] no current CSV URL found in metastore")
        return pd.DataFrame()
    resp = polite_get(url, use_cache=True, rps=0.5)
    return pd.read_csv(io.StringIO(resp.text), low_memory=False)


def _fetch_via_socrata(limit: int = 50000) -> pd.DataFrame:
    """Paginated JSON fallback. Less reliable than CSV from some networks."""
    frames = []
    offset = 0
    page_size = 5000
    while offset < limit:
        try:
            resp = polite_get(
                DATASTORE_QUERY_URL,
                params={"limit": page_size, "offset": offset},
                rps=CONFIG.default_rps,
            )
        except Exception as e:
            print(f"[cms_nursing_home] datastore page failed at offset {offset}: {e}")
            break
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


def _raw_collect_cms_nursing_homes(states: Optional[List[str]] = None) -> List[dict]:
    """
    Return a list of normalized facility dicts from CMS Nursing Home data.

    Each row carries: federal provider number, name, address, ownership info,
    bed count, certification date, AND distress signals (SFF status, CMS
    ratings) which are critical inputs for selling_likelihood scoring.
    """
    states = states or CONFIG.target_states

    df = _fetch_via_csv()
    if df.empty:
        # Fall back to the paginated JSON API if CSV resolution fails
        df = _fetch_via_socrata()

    if df.empty:
        return []

    # CMS column names vary between dataset versions; normalize.
    # Cover both the current spaced-column-name format (CSV) AND the
    # snake_case JSON variant in case we fall back to the datastore API.
    rename = {
        # === Current spaced (CSV) column names (verified Apr 2026) ===
        "CMS Certification Number (CCN)": "cms_id",
        "Federal Provider Number": "cms_id",
        "Provider Name": "name",
        "Provider Address": "address",
        "City/Town": "city",
        "Provider City": "city",
        "State": "state",
        "Provider State": "state",
        "ZIP Code": "zip",
        "Provider Zip Code": "zip",
        "Telephone Number": "phone",
        "Provider Phone Number": "phone",
        "Ownership Type": "ownership_type",
        "Number of Certified Beds": "beds",
        "Average Number of Residents per Day": "avg_residents_per_day",
        "Date First Approved to Provide Medicare and Medicaid Services": "cert_date",
        "Legal Business Name": "legal_owner",
        "Special Focus Status": "sff_status",
        "Provider Changed Ownership in Last 12 Months": "ownership_changed_12mo",
        "Overall Rating": "cms_overall_rating",
        "Health Inspection Rating": "cms_health_rating",
        "Staffing Rating": "cms_staffing_rating",
        "QM Rating": "cms_qm_rating",
        "Chain Name": "chain_name",
        "Chain ID": "chain_id",
        "Number of Facilities in Chain": "chain_size",
        # === snake_case (datastore JSON) column names ===
        "cms_certification_number_ccn": "cms_id",
        "provider_name": "name",
        "provider_address": "address",
        "citytown": "city",
        "city_town": "city",
        "zip_code": "zip",
        "telephone_number": "phone",
        "ownership_type": "ownership_type",
        "number_of_certified_beds": "beds",
        "average_number_of_residents_per_day": "avg_residents_per_day",
        "date_first_approved_to_provide_medicare_and_medicaid_services": "cert_date",
        "legal_business_name": "legal_owner",
        "special_focus_status": "sff_status",
        "provider_changed_ownership_in_last_12_months": "ownership_changed_12mo",
        "overall_rating": "cms_overall_rating",
        "health_inspection_rating": "cms_health_rating",
        "staffing_rating": "cms_staffing_rating",
        "qm_rating": "cms_qm_rating",
        "chain_name": "chain_name",
        "chain_id": "chain_id",
        "number_of_facilities_in_chain": "chain_size",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    keep = [c for c in (
        "cms_id", "name", "address", "city", "state", "zip", "phone",
        "ownership_type", "beds", "avg_residents_per_day",
        "cert_date", "legal_owner",
        "sff_status", "ownership_changed_12mo",
        "cms_overall_rating", "cms_health_rating", "cms_staffing_rating", "cms_qm_rating",
        "chain_name", "chain_id", "chain_size",
    ) if c in df.columns]
    df = df[keep].copy()

    if "state" in df.columns and states:
        df = df[df["state"].astype(str).str.upper().isin([s.strip().upper() for s in states])]

    df["source"] = "CMS"
    return df.to_dict(orient="records")


def collect_cms_nursing_homes(states=None):
    """Safe wrapper: never crashes the pipeline if CMS API is down."""
    try:
        return _raw_collect_cms_nursing_homes(states)
    except Exception as e:
        print(f"[cms_nursing_home] FAILED: {e}; returning empty list")
        return []
