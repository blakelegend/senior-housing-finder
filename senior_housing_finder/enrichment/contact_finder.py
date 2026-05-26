"""
Reverse contact lookup — find owner/decision-maker email + phone.

Providers (in order of accuracy / cost):
1. Hunter.io   — domain → most-likely email pattern + verified emails
2. Apollo.io   — company → contacts with titles
3. Heuristics  — guess `firstname@domain`, `firstname.lastname@domain`, etc.

Phone validation is done locally with `phonenumbers`.
"""
from typing import List, Optional

import phonenumbers
from phonenumbers import NumberParseException

from ..config import CONFIG
from ..utils.http_client import polite_get


# Decision-maker titles we care about for senior housing acquisitions
OWNER_TITLES = [
    "owner", "ceo", "founder", "president", "managing partner",
    "principal", "managing member", "administrator", "executive director",
]


def _hunter_domain_search(domain: str) -> List[dict]:
    if not CONFIG.hunter_io_api_key:
        return []
    try:
        resp = polite_get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": CONFIG.hunter_io_api_key, "limit": 25},
            rps=1.0,
        )
        emails = resp.json().get("data", {}).get("emails", [])
        return emails
    except Exception as e:
        print(f"[contact_finder] hunter failed: {e}")
        return []


def _apollo_people_search(domain: str) -> List[dict]:
    if not CONFIG.apollo_api_key:
        return []
    try:
        resp = polite_get(
            "https://api.apollo.io/v1/mixed_people/search",
            params={
                "api_key": CONFIG.apollo_api_key,
                "q_organization_domains": domain,
                "person_titles[]": OWNER_TITLES,
                "per_page": 25,
            },
            rps=1.0,
        )
        return resp.json().get("people", [])
    except Exception as e:
        print(f"[contact_finder] apollo failed: {e}")
        return []


def _normalize_phone(raw: Optional[str], region: str = "US") -> Optional[str]:
    if not raw:
        return None
    try:
        parsed = phonenumbers.parse(raw, region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except NumberParseException:
        return None
    return None


def _pick_best_email(emails: List[dict]) -> Optional[dict]:
    """Pick the highest-priority decision-maker email from Hunter results."""
    if not emails:
        return None
    # 1. Look for a known owner-level title
    for e in emails:
        title = (e.get("position") or "").lower()
        if any(t in title for t in OWNER_TITLES):
            return e
    # 2. Fall back to the first verified email
    for e in emails:
        if e.get("verification", {}).get("status") == "valid":
            return e
    return emails[0]


def enrich_with_contacts(facility: dict) -> dict:
    """Add `owner_email`, `owner_name`, `owner_title`, `phone_e164`."""
    facility["phone_e164"] = _normalize_phone(facility.get("phone"))

    domain = facility.get("operator_domain")
    if not domain:
        return facility

    # Apollo first — gives us a real person + title; Hunter as a fallback
    people = _apollo_people_search(domain)
    if people:
        top = people[0]
        facility["owner_name"] = top.get("name")
        facility["owner_title"] = top.get("title")
        facility["owner_email"] = top.get("email")
        facility["owner_linkedin"] = top.get("linkedin_url")
        return facility

    emails = _hunter_domain_search(domain)
    best = _pick_best_email(emails)
    if best:
        facility["owner_email"] = best.get("value")
        facility["owner_name"] = " ".join(filter(None, [best.get("first_name"), best.get("last_name")]))
        facility["owner_title"] = best.get("position")

    return facility
