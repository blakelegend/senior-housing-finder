"""
Geospatial clustering of facilities.

Why cluster: two distinct use cases for the REIT thesis.
1. **Roll-up plays** — finding 5-10 facilities within driving distance gives
   a single regional operator opportunity (one back-office, shared staff
   pool, group purchasing). These are higher value than scattered assets.
2. **Market saturation maps** — see where the universe is dense (FL, TX,
   CA, NJ) vs sparse (most of the Mountain West) to inform travel and
   regional team deployment.

Method: DBSCAN with haversine distance. DBSCAN is the right algorithm here
because we don't know the number of clusters in advance, and density-based
clustering naturally handles outliers (rural facilities don't get forced
into a fake "cluster").

`eps_km` is the maximum distance between two points to be neighbors. ~25km
(15mi) is a good drive-time radius for a roll-up; ~80km (50mi) for broader
regional market definition.
"""
from typing import Optional

import numpy as np
import pandas as pd

try:
    from sklearn.cluster import DBSCAN
except ImportError:
    DBSCAN = None


_EARTH_KM = 6371.0088


def cluster_facilities(
    df: pd.DataFrame,
    eps_km: float = 25.0,
    min_samples: int = 3,
    lat_col: str = "lat",
    lng_col: str = "lng",
) -> pd.DataFrame:
    """
    Add a `cluster_id` column. -1 means "noise" (not part of any cluster).

    Works on rows that have lat/lng; everything else gets cluster_id = -1.
    """
    if DBSCAN is None:
        raise ImportError("scikit-learn not installed — run pip install scikit-learn")

    out = df.copy()
    out["cluster_id"] = -1

    mask = out[lat_col].notna() & out[lng_col].notna()
    if mask.sum() < min_samples:
        return out

    coords = np.radians(out.loc[mask, [lat_col, lng_col]].to_numpy())
    # eps in radians = km / earth radius
    eps_rad = eps_km / _EARTH_KM

    db = DBSCAN(
        eps=eps_rad,
        min_samples=min_samples,
        metric="haversine",
        algorithm="ball_tree",
    ).fit(coords)
    out.loc[mask, "cluster_id"] = db.labels_

    return out


def cluster_summary(df: pd.DataFrame) -> pd.DataFrame:
    """One row per cluster — facility count, total beds, dominant operator, centroid."""
    if "cluster_id" not in df.columns:
        return pd.DataFrame()

    valid = df[df["cluster_id"] >= 0]
    if valid.empty:
        return pd.DataFrame()

    def _summarize(g: pd.DataFrame) -> pd.Series:
        owner_col = next(
            (c for c in ("primary_owner", "legal_owner", "true_owner") if c in g.columns),
            None,
        )
        dominant_owner = ""
        if owner_col:
            vc = g[owner_col].fillna("").value_counts()
            if len(vc):
                dominant_owner = vc.index[0]
        return pd.Series({
            "facility_count":    len(g),
            "total_beds":        pd.to_numeric(g.get("beds"), errors="coerce").sum() if "beds" in g.columns else None,
            "states":            ", ".join(sorted(set(g.get("state", pd.Series(dtype=str)).dropna()))) if "state" in g.columns else "",
            "centroid_lat":      g["lat"].mean(),
            "centroid_lng":      g["lng"].mean(),
            "dominant_owner":    dominant_owner,
            "avg_priority":      g.get("priority", pd.Series(dtype=float)).mean() if "priority" in g.columns else None,
            "avg_tired_score":   g.get("tired_owner_score", pd.Series(dtype=float)).mean() if "tired_owner_score" in g.columns else None,
        })

    return (
        valid.groupby("cluster_id", as_index=False)
        .apply(_summarize)
        .reset_index(drop=True)
        .sort_values("facility_count", ascending=False)
    )
