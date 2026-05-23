"""
County assessor / property records enrichment.

The "true owner" of a senior facility is often a holding LLC that owns the
real estate, not the operating company on the license. County property
records reveal that. There is no single national property API — every county
runs its own portal — so we ship a county-router pattern:

    address -> resolve county -> dispatch to county's scraper

This module includes:
- A `lookup_county()` helper using FCC Geocoder (free, no key)
- A Pinellas County (FL) scraper as a reference implementation
- A registry pattern so you can add counties without changing the orchestrator

For production at scale, replace per-county scrapers with a paid aggregator
(Regrid, ATTOM, PropertyRadar, ReportAll USA, DataTree).
"""
from typing import Dict, Optional

from bs4 import BeautifulSoup

from ..utils.http import polite_get


def lookup_county(lat: float, lng: float) -> Optional[Dict[str, str]]:
    """Return {'county': ..., 'state': ...} for a lat/lng using FCC Geocoder."""
    try:
        resp = polite_get(
            "https://geo.fcc.gov/api/census/area",
            params={"lat": lat, "lon": lng, "format": "json"},
            rps=2.0,
        )
        data = resp.json()
        if not data.get("results"):
            return None
        r = data["results"][0]
        return {
            "county": r.get("county_name"),
            "county_fips": r.get("county_fips"),
            "state": r.get("state_code"),
        }
    except Exception as e:
        print(f"[property_records] FCC lookup failed: {e}")
        return None


class CountyAssessor:
    """Base class — subclasses implement `search_by_address`."""
    state: str = ""
    county: str = ""

    def search_by_address(self, address: str) -> Optional[Dict[str, str]]:
        raise NotImplementedError


class PinellasFL(CountyAssessor):
    """Pinellas County (FL) Property Appraiser — example reference."""
    state = "FL"
    county = "PINELLAS"
    BASE = "https://www.pcpao.gov/quick_search_results.php"

    def search_by_address(self, address: str) -> Optional[Dict[str, str]]:
        try:
            resp = polite_get(self.BASE, params={"address": address}, rps=0.5)
        except Exception:
            return None
        soup = BeautifulSoup(resp.text, "lxml")
        # Placeholder selectors — real markup must be inspected and matched
        owner_cell = soup.select_one(".owner-name")
        mailing_cell = soup.select_one(".mailing-address")
        sale_cell = soup.select_one(".last-sale-date")
        if not owner_cell:
            return None
        return {
            "true_owner": owner_cell.get_text(strip=True),
            "owner_mailing_address": mailing_cell.get_text(strip=True) if mailing_cell else "",
            "last_sale_date": sale_cell.get_text(strip=True) if sale_cell else "",
        }


_COUNTY_REGISTRY = {
    ("FL", "PINELLAS"): PinellasFL,
}


def enrich_with_property_records(facility: dict) -> dict:
    """
    Add `true_owner`, `owner_mailing_address`, `last_sale_date` if we have a
    matching county scraper.
    """
    lat, lng = facility.get("lat"), facility.get("lng")
    if lat is None or lng is None:
        return facility

    loc = lookup_county(lat, lng)
    if not loc:
        return facility

    key = ((loc["state"] or "").upper(), (loc["county"] or "").upper())
    scraper_cls = _COUNTY_REGISTRY.get(key)
    if not scraper_cls:
        facility["county"] = loc["county"]
        return facility

    facility["county"] = loc["county"]
    record = scraper_cls().search_by_address(facility.get("address", ""))
    if record:
        facility.update(record)
    return facility
