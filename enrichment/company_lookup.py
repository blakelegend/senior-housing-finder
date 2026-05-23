"""
Company / operator enrichment.

Resolves an operator name (often a holding LLC like "Sunshine Senior LLC") to:
- Domain & website
- Approximate employee count & age
- Industry tags
- LinkedIn-style profile (via Proxycurl if available)

Two providers are wired up:
1. Clearbit-style domain guess from email/name (no key needed)
2. Proxycurl Company API (paid, but the highest-signal source for ops data)

Both are optional — if you don't set keys, the function returns the facility
unchanged.
"""
import re
from typing import Optional

from ..config import CONFIG
from ..utils.http import polite_get


_DOMAIN_BLOCKLIST = {"gmail.com", "yahoo.com", "hotmail.com", "aol.com"}


def _slugify_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _guess_domain_from_name(name: str) -> Optional[str]:
    """Crude heuristic — try `<slug>.com` and confirm it resolves to a website."""
    slug = _slugify_name(name)
    if not slug:
        return None
    candidate = f"{slug}.com"
    try:
        resp = polite_get(f"https://{candidate}", rps=1.0, timeout=10)
        if resp.status_code < 400:
            return candidate
    except Exception:
        pass
    return None


def _proxycurl_company(domain: str) -> Optional[dict]:
    """Hit Proxycurl's Company Profile endpoint if a key is configured."""
    if not CONFIG.proxycurl_api_key:
        return None
    try:
        resp = polite_get(
            "https://nubela.co/proxycurl/api/linkedin/company/resolve",
            params={"company_domain": domain},
            rps=1.0,
        )
        return resp.json()
    except Exception as e:
        print(f"[company_lookup] proxycurl failed: {e}")
        return None


def enrich_with_company_lookup(facility: dict) -> dict:
    """Add operator domain + LinkedIn-like company profile if available."""
    operator_name = (
        facility.get("legal_owner")
        or facility.get("true_owner")
        or facility.get("name")
    )
    if not operator_name:
        return facility

    # Prefer an explicit website if Google Places gave us one
    website = facility.get("website")
    domain = None
    if website:
        m = re.search(r"https?://(?:www\.)?([^/]+)", website)
        if m:
            domain = m.group(1).lower()
            if domain in _DOMAIN_BLOCKLIST:
                domain = None

    if not domain:
        domain = _guess_domain_from_name(operator_name)

    if not domain:
        return facility

    facility["operator_domain"] = domain
    profile = _proxycurl_company(domain)
    if profile:
        facility["operator_linkedin"] = profile.get("url")
        facility["operator_employee_count"] = profile.get("employee_count")
        facility["operator_founded_year"] = profile.get("founded_year")
        facility["operator_industry"] = profile.get("industry")
        facility["operator_hq"] = profile.get("hq", {}).get("city") if profile.get("hq") else None

    return facility
