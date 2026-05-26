"""
State licensing board scrapers.

Each state's senior-housing licensing agency publishes a license lookup.
Formats vary wildly: open-data CSV/JSON (best), ASP.NET WebForms with
postbacks, React SPAs requiring a browser, or interactive maps. We use:

- `polite_get` for plain HTTP / JSON / CSV endpoints
- `browser_context` (Playwright) for JS-rendered SPAs

ETHICAL NOTES:
- All sources here publish facility data as a public service.
- Respect each state's Terms of Service. Some explicitly permit scraping
  (CA, TX); others require a FOIA / open-records request for bulk.
- Rate-limit aggressively — these are often single-server gov sites.

To add a new state:
  1. Subclass `StateLicenseSource`
  2. Set `state_code` and `name`
  3. Implement `fetch_facilities()` returning normalized dicts
  4. Register in `_REGISTRY`
"""
import io
from abc import ABC, abstractmethod
from typing import List, Optional

import pandas as pd
from bs4 import BeautifulSoup

from ..config import CONFIG
from ..utils.http_client import polite_get


class StateLicenseSource(ABC):
    state_code: str = ""
    name: str = ""

    @abstractmethod
    def fetch_facilities(self) -> List[dict]:
        """Return normalized facility dicts."""


# ---------------------------------------------------------------------------
# Florida — AHCA (currently deferred — see note)
# ---------------------------------------------------------------------------
class FloridaAHCA(StateLicenseSource):
    """
    Florida AHCA / FloridaHealthFinder.

    KNOWN LIMITATION (2026): The old FacilityProvider endpoint returns 404 and
    FloridaHealthFinder migrated to a JS-rendered SPA that gates CSV/XLSX
    exports behind a UI search with a "dataset too large" warning that blocks
    bulk downloads. A proper FL collector requires headless browser automation
    (Playwright), which is out of scope for the current free-tier deployment.

    Mitigation: CMS data already covers every FL **nursing home** nationwide
    via the cms_nursing_home collector — the FL state collector was only
    supplementing with ALFs (Assisted Living Facilities). ALF coverage in FL
    will improve when we wire Playwright-based scraping (separate ticket).
    """
    state_code = "FL"
    name = "Florida AHCA"

    def fetch_facilities(self) -> List[dict]:
        print(
            f"[{self.name}] DEFERRED: FL AHCA portal requires browser automation; "
            "FL nursing homes still covered via cms_nursing_home. "
            "ALF coverage pending Playwright scraper."
        )
        return []


# ---------------------------------------------------------------------------
# Texas — HHSC Long-Term Care Provider Search
# ---------------------------------------------------------------------------
class TexasHHSC(StateLicenseSource):
    """
    Texas HHSC publishes a regulated-providers CSV on their open-data portal.

    Covers nursing facilities, assisted living, and HCS providers in one file.
    Updated monthly; no API key required.
    """
    state_code = "TX"
    name = "Texas HHSC"
    OPEN_DATA = (
        "https://www.hhs.texas.gov/sites/default/files/documents/"
        "doing-business-with-hhs/provider-portal/long-term-care/regulated-providers.csv"
    )

    def fetch_facilities(self) -> List[dict]:
        try:
            resp = polite_get(self.OPEN_DATA, rps=0.5)
            df = pd.read_csv(io.StringIO(resp.text), low_memory=False)
        except Exception as e:
            print(f"[{self.name}] fetch failed: {e}")
            return []

        rename = {
            "Provider Name": "name", "Facility Name": "name",
            "Address": "address", "Street Address": "address",
            "City": "city", "State": "state", "Zip": "zip", "Zip Code": "zip",
            "Phone": "phone", "Phone Number": "phone",
            "Provider Type": "license_type", "Type": "license_type",
            "Total Beds": "beds", "Licensed Capacity": "beds",
            "Owner": "legal_owner", "Owner Name": "legal_owner",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        # Keep only senior-housing-relevant licenses
        if "license_type" in df.columns:
            mask = df["license_type"].astype(str).str.contains(
                "nursing|assisted|residential|memory|alzheimer",
                case=False, na=False,
            )
            df = df[mask]
        df["state"] = self.state_code
        df["source"] = f"StateLicense:{self.state_code}"
        return df.to_dict(orient="records")


# ---------------------------------------------------------------------------
# California — CHHS Community Care Licensing Facilities
# ---------------------------------------------------------------------------
class CaliforniaCCLD(StateLicenseSource):
    """
    California CHHS open-data portal publishes the Community Care Licensing
    facility roster. Covers RCFEs (Residential Care for the Elderly), Adult
    Residential, and Child Care — we filter to senior/elderly only.

    Note: the old cdss.ca.gov URL is dead (CDSS server returns a 302 to
    http://localhost/404, no joke). The chhs.ca.gov portal is the supported
    replacement. ~8,400 senior facilities statewide as of 2026.
    """
    state_code = "CA"
    name = "California CCLD"
    DOWNLOAD = (
        "https://gis.data.chhs.ca.gov/api/download/v1/items/"
        "db31b0884a074cff9260facb3f2ade45/csv?layers=0"
    )

    def fetch_facilities(self) -> List[dict]:
        try:
            resp = polite_get(self.DOWNLOAD, rps=0.5)
            df = pd.read_csv(io.StringIO(resp.text), low_memory=False)
        except Exception as e:
            print(f"[{self.name}] fetch failed: {e}")
            return []

        # Filter: keep only elderly/senior residential. PROGRAM_TYPE narrows
        # to adult/senior; FAC_TYPE_DESC narrows further to elderly facilities
        # (excludes general adult residential which serves the developmentally
        # disabled — different acquisition thesis).
        if "PROGRAM_TYPE" in df.columns:
            df = df[df["PROGRAM_TYPE"].astype(str).str.contains("ADULT|SENIOR", case=False, na=False)]
        if "FAC_TYPE_DESC" in df.columns:
            df = df[df["FAC_TYPE_DESC"].astype(str).str.contains("ELDERLY|RCFE", case=False, na=False)]

        rename = {
            "NAME": "name",
            "RES_STREET_ADDR": "address",
            "RES_CITY": "city",
            "RES_ZIP_CODE": "zip",
            "FAC_PHONE_NBR": "phone",
            "FAC_TYPE_DESC": "license_type",
            "CAPACITY": "beds",
            "FAC_NBR": "license_number",
            "FAC_LATITUDE": "lat",
            "FAC_LONGITUDE": "lng",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

        df["state"] = self.state_code
        df["source"] = f"StateLicense:{self.state_code}"
        return df.to_dict(orient="records")


# ---------------------------------------------------------------------------
# New York — DOH Adult Care Facility directory
# ---------------------------------------------------------------------------
class NewYorkDOH(StateLicenseSource):
    """
    NY State Health Data publishes the Adult Care Facility (ACF) directory
    via Socrata. Includes assisted living programs, enriched housing, and
    adult homes — but NOT nursing homes (which are in a separate dataset
    we can swap in if needed).
    """
    state_code = "NY"
    name = "New York DOH"
    SOCRATA = "https://health.data.ny.gov/resource/2x9c-eq57.json"

    def fetch_facilities(self) -> List[dict]:
        out: List[dict] = []
        offset = 0
        limit = 1000
        while True:
            try:
                resp = polite_get(
                    self.SOCRATA,
                    params={"$limit": limit, "$offset": offset},
                    rps=1.0,
                )
            except Exception as e:
                print(f"[{self.name}] fetch failed at offset {offset}: {e}")
                break
            rows = resp.json()
            if not rows:
                break
            out.extend(rows)
            if len(rows) < limit:
                break
            offset += limit

        normalized = []
        for r in out:
            normalized.append({
                "name": r.get("facility_name"),
                "address": r.get("facility_address_1"),
                "city": r.get("facility_city"),
                "state": self.state_code,
                "zip": r.get("facility_zip_code"),
                "phone": r.get("facility_phone_number"),
                "license_type": r.get("facility_type_description"),
                "beds": r.get("licensed_capacity"),
                "legal_owner": r.get("operator_name"),
                "source": f"StateLicense:{self.state_code}",
            })
        return normalized


# Register additional states here as you build them out
_REGISTRY = {
    "FL": FloridaAHCA,
    "TX": TexasHHSC,
    "CA": CaliforniaCCLD,
    "NY": NewYorkDOH,
}


def list_supported_states() -> List[str]:
    return sorted(_REGISTRY.keys())


def collect_state_licensing(states: Optional[List[str]] = None) -> List[dict]:
    """Run every registered state collector for the requested states."""
    states = states or CONFIG.target_states
    results: List[dict] = []
    for code in states:
        code = code.strip().upper()
        cls = _REGISTRY.get(code)
        if not cls:
            print(f"[state_licensing] no collector registered for {code} (skipping)")
            continue
        try:
            results.extend(cls().fetch_facilities())
        except Exception as e:
            print(f"[state_licensing] {code} failed: {e}")
    return results
