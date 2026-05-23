"""
Medicare Provider of Services (POS) file + Hospice / Home Health datasets.

These complement the CMS Nursing Home Compare data with broader provider
categories (CCRCs, hospice, etc.). All datasets are free and live on the
data.cms.gov Socrata-style API.

Dataset IDs we hit:
- "POS" Provider of Services (file extract):  q66u-3ktp
- Home Health Provider Information:           6jpm-sxkc
- Hospice Provider Information:               yc9t-dgbk
"""
from typing import List, Optional

import pandas as pd

from ..config import CONFIG
from ..utils.http import polite_get

DATASETS = {
    "home_health": "https://data.cms.gov/provider-data/api/1/datastore/query/6jpm-sxkc/0",
    "hospice":     "https://data.cms.gov/provider-data/api/1/datastore/query/yc9t-dgbk/0",
}


def _fetch(url: str, limit: int = 50000) -> pd.DataFrame:
    frames = []
    offset = 0
    page = 5000
    while offset < limit:
        try:
            resp = polite_get(url, params={"limit": page, "offset": offset}, rps=CONFIG.default_rps)
        except Exception as e:
            print(f"[medicare] fetch failed at offset {offset}: {e}")
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
    include = include or list(DATASETS.keys())
    target_states = {s.strip().upper() for s in states}

    out: List[dict] = []
    for key in include:
        url = DATASETS.get(key)
        if not url:
            continue
        df = _fetch(url)
        if df.empty:
            continue

        # CMS Socrata exposes lower_snake_case column names; coerce to ours
        col_map = {
            "provider_name": "name",
            "address_line_1": "address",
            "citytown": "city",
            "city_town": "city",
            "state": "state",
            "zip_code": "zip",
            "telephone_number": "phone",
            "type_of_ownership": "ownership_type",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        if "state" in df.columns:
            df = df[df["state"].str.upper().isin(target_states)]

        df["source"] = f"Medicare:{key}"
        out.extend(df.to_dict(orient="records"))

    return out
