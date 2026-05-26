"""
Medicare Provider of Services (POS) file + Hospice / Home Health datasets.

These complement the CMS Nursing Home Compare data with broader provider
categories (CCRCs, hospice, etc.). All datasets are free.

Dataset IDs we hit:
- Home Health Provider Information: 6jpm-sxkc
- Hospice Provider Information:     yc9t-dgbk

Same metastore-based CSV resolution pattern as cms_nursing_home — the JSON
datastore API can be IP-blocked on cloud egress (e.g. Render) while CDN-served
CSVs always work.
"""
import io
from typing import List, Optional

import pandas as pd

from ..config import CONFIG
from ..utils.http_client import polite_get

DATASET_IDS = {
    "home_health": "6jpm-sxkc",
    "hospice": "yc9t-dgbk",
}


def _metastore_url(dataset_id: str) -> str:
    return f"https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/{dataset_id}"


def _datastore_url(dataset_id: str) -> str:
    return f"https://data.cms.gov/provider-data/api/1/datastore/query/{dataset_id}/0"


def _resolve_current_csv_url(dataset_id: str) -> Optional[str]:
    try:
        resp = polite_get(_metastore_url(dataset_id), use_cache=False, rps=1.0)
        meta = resp.json()
    except Exception as e:
        print(f"[medicare:{dataset_id}] metastore lookup failed: {e}")
        return None
    for dist in meta.get("distribution", []):
        url = dist.get("downloadURL")
        if url and url.endswith(".csv"):
            return url
    return None


def _fetch_via_csv(dataset_id: str) -> pd.DataFrame:
    url = _resolve_current_csv_url(dataset_id)
    if not url:
        return pd.DataFrame()
    try:
        resp = polite_get(url, use_cache=True, rps=0.5)
        return pd.read_csv(io.StringIO(resp.text), low_memory=False)
    except Exception as e:
        print(f"[medicare:{dataset_id}] CSV download failed: {e}")
        return pd.DataFrame()


def _fetch_via_socrata(dataset_id: str, limit: int = 50000) -> pd.DataFrame:
    """Paginated JSON fallback."""
    url = _datastore_url(dataset_id)
    frames = []
    offset = 0
    page = 5000
    while offset < limit:
        try:
            resp = polite_get(url, params={"limit": page, "offset": offset}, rps=CONFIG.default_rps)
        except Exception as e:
            print(f"[medicare:{dataset_id}] fetch failed at offset {offset}: {e}")
            break
        payload = resp.json()
        rows = payload.get("results", []) or payload.get("data", [])
        if not rows:
            break
        frames.append(pd.DataFrame(rows))
        if len(rows) < page:
            break
        offset += page
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def collect_medicare_providers(
    states: Optional[List[str]] = None,
    include: Optional[List[str]] = None,
) -> List[dict]:
    """
    Pull supplementary Medicare provider datasets.

    `include` lets you toggle which sub-datasets to fetch. Defaults to both.
    """
    states = states or CONFIG.target_states
    include = include or list(DATASET_IDS.keys())
    target_states = {s.strip().upper() for s in states}

    out: List[dict] = []
    for key in include:
        dataset_id = DATASET_IDS.get(key)
        if not dataset_id:
            continue
        df = _fetch_via_csv(dataset_id)
        if df.empty:
            df = _fetch_via_socrata(dataset_id)
        if df.empty:
            continue

        # Column normalization — handle both CSV (spaced) and JSON (snake_case) variants
        col_map = {
            # Spaced (CSV) names — current dataset uses bare "State", "City/Town", "ZIP Code"
            "Facility Name": "name",
            "Provider Name": "name",
            "CMS Certification Number (CCN)": "cms_id",
            "Provider Address": "address",
            "Address Line 1": "address",
            "City/Town": "city",
            "CityTown": "city",
            "Provider City": "city",
            "State": "state",
            "Provider State": "state",
            "ZIP Code": "zip",
            "Zip Code": "zip",
            "Provider Zip Code": "zip",
            "Provider Phone Number": "phone",
            "Telephone Number": "phone",
            "Type of Ownership": "ownership_type",
            "Ownership Type": "ownership_type",
            # snake_case (JSON) names
            "provider_name": "name",
            "cms_certification_number_ccn": "cms_id",
            "provider_address": "address",
            "address_line_1": "address",
            "citytown": "city",
            "city_town": "city",
            "provider_city": "city",
            "provider_state": "state",
            "zip_code": "zip",
            "telephone_number": "phone",
            "type_of_ownership": "ownership_type",
            "ownership_type": "ownership_type",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        if "state" in df.columns:
            df = df[df["state"].astype(str).str.upper().isin(target_states)]

        df["source"] = f"Medicare:{key}"
        out.extend(df.to_dict(orient="records"))

    return out
