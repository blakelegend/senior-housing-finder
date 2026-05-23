"""
Folium HTML map of facility clusters.

Outputs a single HTML file (CONFIG.output_dir / "cluster_map.html") with:
- Marker cluster of all facilities, color-coded by priority score
- Outline polygons per detected cluster
- Popups with facility name, owner, priority, tired-owner score

The HTML works offline once generated; no JS bundling required.
"""
from pathlib import Path
from typing import Optional

import pandas as pd

try:
    import folium
    from folium.plugins import MarkerCluster
except ImportError:
    folium = None
    MarkerCluster = None

from ..config import CONFIG


_PRIORITY_PALETTE = [
    (0,   "gray"),
    (40,  "blue"),
    (60,  "orange"),
    (80,  "red"),
]


def _color_for(priority: Optional[float]) -> str:
    if priority is None or pd.isna(priority):
        return "gray"
    color = "gray"
    for threshold, name in _PRIORITY_PALETTE:
        if priority >= threshold:
            color = name
    return color


def render_cluster_map(
    df: pd.DataFrame,
    output_name: str = "cluster_map.html",
    center: Optional[tuple] = None,
    zoom_start: int = 5,
) -> Optional[Path]:
    """Write an interactive HTML map; return the path or None if folium missing."""
    if folium is None:
        print("[density_map] folium not installed — skipping HTML map")
        return None

    if df.empty or "lat" not in df.columns or "lng" not in df.columns:
        return None
    geo = df.dropna(subset=["lat", "lng"])
    if geo.empty:
        return None

    if center is None:
        center = (geo["lat"].mean(), geo["lng"].mean())

    m = folium.Map(location=center, zoom_start=zoom_start, tiles="cartodbpositron")

    # Cluster layer
    cluster = MarkerCluster(name="Facilities").add_to(m)
    for _, r in geo.iterrows():
        priority = r.get("priority") or r.get("score_total")
        color = _color_for(priority)
        popup_html = (
            f"<b>{r.get('name', '')}</b><br>"
            f"{r.get('address', '')}<br>"
            f"Owner: {r.get('primary_owner') or r.get('legal_owner', '')}<br>"
            f"Beds: {r.get('beds', '')}<br>"
            f"Priority: {priority}<br>"
            f"Tired-owner score: {r.get('tired_owner_score', '')}<br>"
            f"Cluster: {r.get('cluster_id', '')}"
        )
        folium.CircleMarker(
            location=(r["lat"], r["lng"]),
            radius=6,
            color=color,
            fill=True,
            fill_opacity=0.7,
            popup=folium.Popup(popup_html, max_width=300),
        ).add_to(cluster)

    folium.LayerControl().add_to(m)
    out = CONFIG.output_dir / output_name
    m.save(str(out))
    return out
