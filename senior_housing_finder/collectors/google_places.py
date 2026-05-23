"""
Google Places API (New) — text search.

The legacy Places API (used by the googlemaps Python client) was deprecated
in 2024 and disabled for new GCP projects. This module talks directly to the
new Places API at places.googleapis.com using HTTP requests.
"""
import time
from typing import List, Optional

import requests

from ..config import CONFIG
from ..utils.rate_limiter import RateLimiter

TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.nationalPhoneNumber",
    "places.websiteUri",
    "places.businessStatus",
    "places.rating",
    "places.userRatingCount",
    "places.types",
    "places.location",
    "places.googleMapsUri",
    "nextPageToken",
])

DEFAULT_QUERIES = [
    "assisted living facility",
    "memory care facility",
    "senior living community",
    "independent living facility",
    "skilled nursing facility",
    "continuing care retirement community",
]


def _search_one(query: str, limiter: RateLimiter) -> List[dict]:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": CONFIG.google_maps_api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    out: List[dict] = []
    page_token = None
    for page in range(3):
        limiter.wait()
        body = {"textQuery": query, "pageSize": 20}
        if page_token:
            body["pageToken"] = page_token
        try:
            resp = requests.post(TEXT_SEARCH_URL, json=body, headers=headers, timeout=30)
        except Exception as e:
            print(f"[google_places] request failed: {e}")
            break
        if resp.status_code != 200:
            print(f"[google_places] HTTP {resp.status_code}: {resp.text[:200]}")
            break
        data = resp.json()
        out.extend(data.get("places", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
        time.sleep(2)
    return out


def collect_google_places(
    locations: List[str],
    queries: Optional[List[str]] = None,
) -> List[dict]:
    if not CONFIG.google_maps_api_key:
        print("[google_places] no GOOGLE_MAPS_API_KEY — skipping")
        return []
    queries = queries or DEFAULT_QUERIES
    limiter = RateLimiter(CONFIG.google_places_rps)
    seen, results = set(), []
    for loc in locations:
        for q in queries:
            full_q = f"{q} in {loc}"
            try:
                places = _search_one(full_q, limiter)
            except Exception as e:
                print(f"[google_places] '{full_q}' failed: {e}")
                continue
            for p in places:
                pid = (p.get("id") or "").replace("places/", "")
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                loc_data = p.get("location") or {}
                results.append({
                    "name": (p.get("displayName") or {}).get("text"),
                    "address": p.get("formattedAddress"),
                    "phone": p.get("nationalPhoneNumber"),
                    "website": p.get("websiteUri"),
                    "google_place_id": pid,
                    "google_url": p.get("googleMapsUri"),
                    "rating": p.get("rating"),
                    "rating_count": p.get("userRatingCount"),
                    "business_status": p.get("businessStatus"),
                    "types": ",".join(p.get("types", [])),
                    "lat": loc_data.get("latitude"),
                    "lng": loc_data.get("longitude"),
                    "query": q,
                    "source": "GooglePlaces",
                })
    return results
