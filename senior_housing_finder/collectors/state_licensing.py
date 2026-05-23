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
from ..utils.http import polite_get


class StateLicenseSource(ABC):
    state_code: str = ""
    name: str = ""

    @abstractmethod
    def fetch_facilities(self) -> List[dict]:
        """Return normalized facility dicts."""


# ---------------------------------------------------------------------------
# Florida — AHCA
# ---------------------------------------------------------------------------
class FloridaAHCA(StateLicenseSource):
    state_code = "FL"
    name = "Florida AHCA"
    ENDPOINT = "https://quality.healthfinder.fl.gov/Facility-Provider/FacilityProvider"

    def fetch_facilities(self) -> List[dict]:
        try:
            resp = polite_get(self.ENDPOINT, rps=1.0)
        except Exception as e:
            print(f"[{self.name}] fetch failed: {e}")
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        out: List[dict] = []
        for row in soup.select("table.facility-results tr")[1:]:
            cells = [c.get_text(strip=True) for c in row.select("td")]
            if len(cells) < 5:
                continue
            out.append({
                "name": cells[0], "address": cells[1], "city": cells[2],
                "state": self.state_code, "zip": cells[3], "license_type": cells[4],
                "source": f"StateLicense:{self.state_code}",
            })
        return out


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
# California — DSS Community Care Licensing
# ---------------------------------------------------------------------------
class CaliforniaCCLD(StateLicenseSource):
    """
    California DSS publishes their Community Care Facility roster as a public
    download. Covers RCFEs (Residential Care for the Elderly) and ARFs.
    """
    state_code = "CA"
    name = "California CCLD"
    DOWNLOAD = "https://www.cdss.ca.gov/Portals/9/CCLD/Statistical-Reports/CCLD-Facilities.csv"

    def fetch_facilities(self) -> List[dict]:
        try:
            resp = polite_get(self.DOWNLOAD, rps=0.5)
            df = pd.read_csv(io.StringIO(resp.text), low_memory=False)
        except Exception as e:
            print(f"[{self.name}] fetch failed: {e}")
            return []

        rename = {
            "FACNAME": "name", "Facility Name": "name",
            "FACADDR": "address", "Address": "address",
            "FACCITY": "city", "City": "city",
            "FACZIP": "zip",
            "FACPHONE": "phone", "Phone": "phone",
            "FACTYPE": "license_type", "Facility Type": "license_type",
            "FACCAP": "beds", "Licensed Capacity": "beds",
            "LICENSEE": "legal_owner", "Licensee": "legal_owner",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        # RCFE = adult, ARF = developmentally disabled — keep RCFE only
        if "license_type" in df.columns:
            df = df[df["license_type"].astype(str).str.contains("RCFE|ELDERLY", case=False, na=False)]
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
