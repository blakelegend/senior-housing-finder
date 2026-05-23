"""
Google Maps Places API — Text Search + Place Details.

Catches assisted living and memory care facilities that CMS doesn't cover
(CMS = nursing homes only). Requires a Google Maps API key with Places API
enabled. Billed per request — keep the search radius and seed list tight.

Docs:
- Text Search:  https://developers.google.com/maps/documentation/places/web-service/search-text
- Place Details: https://developers.google.com/maps/documentation/places/web-service/details
"""
from typing import List, Optional

import googlemaps

from ..config import CONFIG
from ..utils.rate_limiter import RateLimiter


# Search queries that surface senior housing types Google indexes well
DEFAULT_QUERIES = [
    "assisted living facility",
    "memory care facility",
    "senior living community",
    "independent living facility",
    "skilled nursing facility",
    "continuing care retirement community",
]

# Fields we want from Place Details. Each field group has separate pricing,
# so we batch and avoid Contact / Atmosphere unless we'll actually use them.
DETAIL_FIELDS = [
    "name", "formatted_address", "formatted_phone_number",
    "international_phone_number", "website", "business_status",
    "place_id", "url", "rating", "user_ratings_total",
    "geometry/location", "type",
]


def _client() -> googlemaps.Client:
    if not CONFIG.google_maps_api_key:
        raise RuntimeError(
            "GOOGLE_MAPS_API_KEY not set. Add it to .env to use Google Places."
        )
    return googlemaps.Client(key=CONFIG.google_maps_api_key)


def _search_one(gmaps, query: str, location: str, limiter: RateLimiter) -> List[dict]:
    """Page through one (query, location) Text Search up to 60 results."""
    out: List[dict] = []
    limiter.wait()
    resp = gmaps.places(query=f"{query} in {location}")
    out.extend(resp.get("results", []))

    # Google paginates Text Search with next_page_token; it takes ~2s to activate
    next_token = resp.get("next_page_token")
    while next_token and len(out) < 60:
        limiter.wait()
        # Token must be re-used with a brief delay; the limiter usually covers it
        resp = gmaps.places(query=f"{query} in {location}", page_token=next_token)
        out.extend(resp.get("results", []))
        next_token = resp.get("next_page_token")

    return out


def collect_google_places(
    locations: List[str],
    queries: Optional[List[str]] = None,
) -> List[dict]:
    """
    Search Places for each (query, location) pair and enrich with Place Details.

    `locations` should be city/state strings, e.g. ["Tampa, FL", "St. Petersburg, FL"].
    """
    queries = queries or DEFAULT_QUERIES
    gmaps = _client()
    limiter = RateLimiter(CONFIG.google_places_rps)

    seen_place_ids: set = set()
    results: List[dict] = []

    for location in locations:
        for q in queries:
            for hit in _search_one(gmaps, q, location, limiter):
                pid = hit.get("place_id")
                if not pid or pid in seen_place_ids:
                    continue
                seen_place_ids.add(pid)

                limiter.wait()
                detail = gmaps.place(place_id=pid, fields=DETAIL_FIELDS).get("result", {})

                results.append({
                    "name": detail.get("name") or hit.get("name"),
                    "address": detail.get("formatted_address") or hit.get("formatted_address"),
                    "phone": detail.get("formatted_phone_number"),
                    "phone_intl": detail.get("international_phone_number"),
                    "website": detail.get("website"),
                    "google_place_id": pid,
                    "google_url": detail.get("url"),
                    "rating": detail.get("rating"),
                    "rating_count": detail.get("user_ratings_total"),
                    "business_status": detail.get("business_status"),
                    "types": ",".join(detail.get("types", []) or hit.get("types", [])),
                    "lat": detail.get("geometry", {}).get("location", {}).get("lat"),
                    "lng": detail.get("geometry", {}).get("location", {}).get("lng"),
                    "query": q,
                    "source": "GooglePlaces",
                })

    return results
