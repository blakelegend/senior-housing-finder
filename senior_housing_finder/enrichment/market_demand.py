"""
Local market supply/demand enrichment.

For each facility, compute:
  - senior_pop_65plus           — count of 65+ residents in the county
  - senior_pop_growth_5yr       — % change vs 5 years ago (ACS 5-yr comparison)
  - median_hh_income            — county median household income
  - supply_facilities_per_10k_65plus — facilities in same county / (65+ pop / 10k)
  - market_demand_score         — composite 0-100

Data source: US Census **American Community Survey 5-Year** (free public API)
  https://api.census.gov/data/2022/acs/acs5

Variables we pull:
  B01001_001E   total population
  B01001_020E..B01001_025E   male 65+
  B01001_044E..B01001_049E   female 65+
  B19013_001E   median household income

A Census API key is recommended (free, instant signup) for >500 calls/day.
"""
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from ..config import CONFIG
from ..utils.http_client import polite_get
from .property_records import lookup_county


ACS_BASE = "https://api.census.gov/data"
ACS_CURRENT_YEAR = 2022
ACS_PRIOR_YEAR = 2017  # 5-year-prior for growth comparison

MALE_65 = [f"B01001_{n:03d}E" for n in (20, 21, 22, 23, 24, 25)]
FEMALE_65 = [f"B01001_{n:03d}E" for n in (44, 45, 46, 47, 48, 49)]
INCOME = "B19013_001E"


def _acs_county(state_fips: str, county_fips: str, year: int = ACS_CURRENT_YEAR) -> Optional[Dict]:
    """Hit ACS 5-yr for a single county; return a flat dict of variables."""
    vars_ = ",".join(["B01001_001E", *MALE_65, *FEMALE_65, INCOME])
    params = {
        "get": vars_,
        "for": f"county:{county_fips}",
        "in":  f"state:{state_fips}",
    }
    if CONFIG.census_api_key:
        params["key"] = CONFIG.census_api_key

    try:
        resp = polite_get(f"{ACS_BASE}/{year}/acs/acs5", params=params, rps=2.0, use_cache=True)
        data = resp.json()
        if not data or len(data) < 2:
            return None
        headers, row = data[0], data[1]
        return dict(zip(headers, row))
    except Exception as e:
        print(f"[market_demand] ACS {year} {state_fips}-{county_fips} failed: {e}")
        return None


def _county_stats(state_fips: str, county_fips: str) -> Optional[Dict]:
    """Compute 65+ population, growth, and median income for a county."""
    now = _acs_county(state_fips, county_fips, ACS_CURRENT_YEAR)
    if not now:
        return None

    def _sum_keys(d: Dict, keys: List[str]) -> int:
        total = 0
        for k in keys:
            try:
                total += int(d.get(k) or 0)
            except (TypeError, ValueError):
                pass
        return total

    pop_65_now = _sum_keys(now, MALE_65 + FEMALE_65)

    prior = _acs_county(state_fips, county_fips, ACS_PRIOR_YEAR)
    growth = None
    if prior:
        pop_65_prior = _sum_keys(prior, MALE_65 + FEMALE_65)
        if pop_65_prior > 0:
            growth = (pop_65_now - pop_65_prior) / pop_65_prior

    try:
        income = int(now.get(INCOME) or 0) or None
    except (TypeError, ValueError):
        income = None

    return {
        "senior_pop_65plus":     pop_65_now,
        "senior_pop_growth_5yr": growth,
        "median_hh_income":      income,
        "county_fips":           f"{state_fips}{county_fips}",
    }


# Cache per (state_fips, county_fips) within a single pipeline run
_COUNTY_CACHE: Dict[str, Dict] = {}


def enrich_with_market_demand(facility: dict) -> dict:
    """
    Add ACS-based market signals to a facility dict.

    Uses the FCC geocoder (already used in property_records) to resolve
    lat/lng → county FIPS, then hits ACS once per county (cached).
    """
    lat, lng = facility.get("lat"), facility.get("lng")
    if lat is None or lng is None:
        return facility

    loc = lookup_county(lat, lng)
    if not loc or not loc.get("county_fips"):
        return facility

    fips = loc["county_fips"]
    state_fips, county_fips = fips[:2], fips[2:]

    cache_key = fips
    if cache_key not in _COUNTY_CACHE:
        stats = _county_stats(state_fips, county_fips)
        if stats:
            _COUNTY_CACHE[cache_key] = stats
    cached = _COUNTY_CACHE.get(cache_key, {})
    facility.update(cached)
    return facility


# ---------------------------------------------------------------------------
# Supply density (uses geo clustering already computed)
# ---------------------------------------------------------------------------

def add_supply_density(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each facility, compute supply intensity = total county facilities ÷
    (65+ population / 10k). Higher = more saturated market.

    Requires `county_fips` and `senior_pop_65plus` already on the rows.
    """
    if df.empty or "county_fips" not in df.columns:
        return df

    out = df.copy()
    by_county = out.groupby("county_fips").size().rename("county_facility_count")
    out = out.merge(by_county, left_on="county_fips", right_index=True, how="left")

    def _density(row) -> Optional[float]:
        pop = row.get("senior_pop_65plus")
        n = row.get("county_facility_count")
        if not pop or not n or pop <= 0:
            return None
        return float(n) / (float(pop) / 10_000.0)

    out["supply_facilities_per_10k_65plus"] = out.apply(_density, axis=1)
    return out


# ---------------------------------------------------------------------------
# Market-demand composite score
# ---------------------------------------------------------------------------

DEMAND_WEIGHTS = {
    "pop_size":      25,
    "pop_growth":    35,
    "income":        15,
    "low_supply":    25,
}


def _score_market_demand(row: pd.Series) -> float:
    parts = 0.0

    # 65+ population size: normalize to log scale (smallest county ~5k, largest ~3M)
    pop = row.get("senior_pop_65plus")
    if pop:
        import math
        parts += min(1.0, max(0.0, (math.log10(max(pop, 1)) - 3.5) / 2.5)) * DEMAND_WEIGHTS["pop_size"]

    # Growth: 0% = neutral, +5%/5yr = max signal
    growth = row.get("senior_pop_growth_5yr")
    if growth is not None and pd.notna(growth):
        parts += min(1.0, max(0.0, float(growth) / 0.05)) * DEMAND_WEIGHTS["pop_growth"]

    # Income: ability-to-pay proxy (national median ~$75k)
    inc = row.get("median_hh_income")
    if inc:
        parts += min(1.0, max(0.0, (float(inc) - 50_000) / 50_000)) * DEMAND_WEIGHTS["income"]

    # Low supply (under-supplied markets score higher)
    supply = row.get("supply_facilities_per_10k_65plus")
    if supply is not None and pd.notna(supply):
        # National avg is ~0.5; <0.3 = under-supplied, >1.0 = saturated
        parts += min(1.0, max(0.0, (1.0 - float(supply)) / 0.7)) * DEMAND_WEIGHTS["low_supply"]

    return round(min(100.0, parts), 2)


def score_market_demand(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["market_demand_score"] = out.apply(_score_market_demand, axis=1)
    return out
