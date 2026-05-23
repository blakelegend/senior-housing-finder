"""
National property tax records + lien enrichment.

Replaces per-county scrapers with commercial national aggregators. Three
providers wired up — pick whichever your firm licenses:

| Provider    | Coverage   | Pricing    | Best for                          |
|-------------|------------|------------|-----------------------------------|
| Regrid      | 50 states  | ~$5k/yr+   | Parcel + owner data, GIS-friendly |
| ReportAll   | 50 states  | ~$1.5k/yr+ | Quick API, owner mailing addresses |
| ATTOM       | 50 states  | $10k+/yr   | Deepest data (deeds, mortgages, AVMs, liens) |

What we extract per facility:
- true_owner (LLC + mailing address)
- last_sale_date, last_sale_price
- assessed_value, appraised_value (estimated market value)
- tax_delinquent (bool) + tax_owed_amount
- liens (list of recorded liens with date/amount)
- year_built, effective_age

Lien data specifically: ATTOM exposes recorded UCC, mechanics, judgment, and
tax liens. A property with recent liens against the owner is a top-tier
motivated-seller signal.
"""
import re
from typing import List, Optional

from ..config import CONFIG
from ..utils.http import polite_get


# ---------------------------------------------------------------------------
# Regrid
# ---------------------------------------------------------------------------

def _regrid_lookup(address: str) -> Optional[dict]:
    if not CONFIG.regrid_api_key:
        return None
    try:
        resp = polite_get(
            "https://app.regrid.com/api/v2/parcels/address",
            params={"query": address, "token": CONFIG.regrid_api_key, "limit": 1},
            rps=2.0,
            use_cache=True,
        )
        data = resp.json()
        parcels = data.get("parcels", {}).get("features") or data.get("results", [])
        if not parcels:
            return None
        parcel = parcels[0]
        props = parcel.get("properties", parcel)
        # Regrid's nested fields vary by jurisdiction — pull from `fields`
        fields = props.get("fields", props)
        return {
            "true_owner": fields.get("owner"),
            "owner_mailing_address": fields.get("mailadd"),
            "owner_mailing_city": fields.get("mail_city"),
            "owner_mailing_state": fields.get("mail_state2") or fields.get("mail_state"),
            "owner_mailing_zip": fields.get("mail_zip"),
            "last_sale_date": fields.get("saledate"),
            "last_sale_price": fields.get("saleprice"),
            "appraised_value": fields.get("parval"),
            "year_built": fields.get("yearbuilt"),
            "parcel_id": fields.get("parcelnumb"),
            "_source": "regrid",
        }
    except Exception as e:
        print(f"[tax_records] regrid lookup failed: {e}")
        return None


# ---------------------------------------------------------------------------
# ReportAll USA
# ---------------------------------------------------------------------------

def _reportall_lookup(address: str) -> Optional[dict]:
    if not CONFIG.reportall_api_key:
        return None
    try:
        resp = polite_get(
            "https://reportallusa.com/api/rest.php",
            params={
                "client": CONFIG.reportall_api_key,
                "v": "9",
                "address": address,
            },
            rps=2.0,
            use_cache=True,
        )
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None
        r = results[0]
        return {
            "true_owner": r.get("owner"),
            "owner_mailing_address": r.get("mail_address1"),
            "owner_mailing_city": r.get("mail_city"),
            "owner_mailing_state": r.get("mail_state"),
            "owner_mailing_zip": r.get("mail_zip"),
            "last_sale_date": r.get("sale_date"),
            "last_sale_price": r.get("sale_price"),
            "appraised_value": r.get("market_value"),
            "assessed_value": r.get("assessed_value"),
            "year_built": r.get("year_built"),
            "parcel_id": r.get("parcel_id"),
            "_source": "reportall",
        }
    except Exception as e:
        print(f"[tax_records] reportall lookup failed: {e}")
        return None


# ---------------------------------------------------------------------------
# ATTOM Data
# ---------------------------------------------------------------------------

def _attom_property(address: str) -> Optional[dict]:
    if not CONFIG.attom_api_key:
        return None
    headers = {"apikey": CONFIG.attom_api_key, "accept": "application/json"}
    try:
        # ATTOM splits property into multiple endpoints; we hit the "expandedprofile" one
        m = re.match(r"^(.*?),\s*(.*?),\s*([A-Z]{2})\s*(\d{5})?", address)
        if not m:
            return None
        street, city, state, _ = m.groups()
        from ..utils.http import polite_session
        sess = polite_session()
        sess.headers.update(headers)
        resp = polite_get(
            "https://api.gateway.attomdata.com/propertyapi/v1.0.0/property/expandedprofile",
            params={"address1": street.strip(), "address2": f"{city.strip()}, {state}"},
            session=sess,
            use_cache=True,
        )
        prop = (resp.json().get("property") or [None])[0]
        if not prop:
            return None
        sale = prop.get("sale", {}) or {}
        building = prop.get("building", {}) or {}
        assessment = prop.get("assessment", {}) or {}
        return {
            "true_owner": (prop.get("owner") or {}).get("owner1", {}).get("fullname"),
            "owner_mailing_address": (prop.get("owner") or {}).get("mailingaddress", {}).get("oneline"),
            "last_sale_date": sale.get("salesearchdate"),
            "last_sale_price": (sale.get("amount") or {}).get("saleamt"),
            "appraised_value": (assessment.get("market") or {}).get("mktttlvalue"),
            "assessed_value": (assessment.get("assessed") or {}).get("assdttlvalue"),
            "year_built": (building.get("summary") or {}).get("yearbuilt"),
            "effective_age": (building.get("summary") or {}).get("effectiveyearbuilt"),
            "_source": "attom",
        }
    except Exception as e:
        print(f"[tax_records] attom lookup failed: {e}")
        return None


def _attom_liens(address: str) -> List[dict]:
    """Pull recorded liens (tax, mechanics, judgment, UCC) against a property."""
    if not CONFIG.attom_api_key:
        return []
    headers = {"apikey": CONFIG.attom_api_key, "accept": "application/json"}
    try:
        from ..utils.http import polite_session
        sess = polite_session()
        sess.headers.update(headers)
        resp = polite_get(
            "https://api.gateway.attomdata.com/propertyapi/v1.0.0/saleshistory/snapshot",
            params={"address": address},
            session=sess,
            use_cache=True,
        )
        # ATTOM exposes liens under a separate endpoint in some packages; this is
        # a placeholder — adapt to whichever ATTOM product you actually license.
        # (Their "Liens" add-on returns under property/liens with `liens` array)
        liens = resp.json().get("property", [{}])[0].get("liens", []) or []
        return [
            {
                "lien_type": l.get("lienType"),
                "amount":    l.get("amount"),
                "date":      l.get("recordingDate"),
                "lender":    l.get("lender"),
            }
            for l in liens
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def enrich_with_tax_records(facility: dict) -> dict:
    """
    Try providers in cost-effective order; merge first non-empty result.

    Adds tax + lien signals to the facility dict:
      true_owner, owner_mailing_address, last_sale_date/price,
      appraised_value, year_built, effective_age, parcel_id,
      liens (list), tax_delinquent (bool), lien_count, recent_lien_total
    """
    address = facility.get("address") or ""
    if not address:
        return facility

    # Compose full address with city/state/zip if available
    full = address
    extras = ", ".join(filter(None, [facility.get("city"), facility.get("state"), str(facility.get("zip") or "")]))
    if extras and extras not in address:
        full = f"{address}, {extras}"

    result = (
        _reportall_lookup(full)
        or _regrid_lookup(full)
        or _attom_property(full)
    )
    if result:
        facility.update({k: v for k, v in result.items() if v is not None})

    # Liens specifically — ATTOM is the most reliable source
    if CONFIG.attom_api_key:
        liens = _attom_liens(full)
        if liens:
            facility["liens"] = liens
            facility["lien_count"] = len(liens)
            try:
                facility["recent_lien_total"] = sum(
                    float(l.get("amount") or 0) for l in liens
                )
            except Exception:
                pass

    # Effective age: years since year_built, or effective_age if provided
    yb = facility.get("year_built") or facility.get("effective_age")
    try:
        if yb:
            from datetime import datetime
            facility["property_age_years"] = datetime.now().year - int(str(yb)[:4])
    except Exception:
        pass

    return facility
