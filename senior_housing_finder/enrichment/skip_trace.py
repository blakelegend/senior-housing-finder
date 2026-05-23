"""
Skip tracing — find owner phone numbers and current addresses.

⚠️  PERMISSIBLE PURPOSE REQUIREMENT
==================================
Skip tracing data is subject to the **Gramm-Leach-Bliley Act (GLBA)** and
the **Fair Credit Reporting Act (FCRA)**. You may only use these APIs when
you have a permissible purpose, which for real estate acquisition outreach
typically falls under:

- GLBA §6802(e)(8): "to comply with Federal, State, or local laws, rules
  and other applicable legal requirements" — limited
- GLBA §6802(e)(6): "in connection with a proposed or actual sale, merger,
  transfer, or exchange of all or a portion of a business" — this is the
  one that covers acquisition outreach

You CANNOT use skip-traced numbers to:
- Auto-dial via predictive dialer without TCPA consent
- Sell or share the data with third parties
- Use for general marketing of unrelated products

Each provider below requires you to attest to a permissible purpose at
account signup. Keep your attestation on file. Set `CONFIRM_PERMISSIBLE=1`
in your environment to enable lookups — this is a deliberate guardrail.

Wired providers:
- Endato (formerly IDI Data)   — real-estate-friendly, ~$0.10-0.50/lookup
- BatchSkipTracing             — bulk, popular with REI
- WhitePages Pro (Twilio)      — phone-focused, ~$0.05/lookup

For TLO / IRBSearch (gated, law-enforcement/process-server tier), you must
manually obtain credentials and bolt them on — we don't ship that path.
"""
import os
from typing import Dict, List, Optional

from ..config import CONFIG
from ..utils.http import polite_get, polite_session


def _permissible_purpose_ok() -> bool:
    """Hard gate — must be set explicitly in env to use skip-trace lookups."""
    return os.getenv("CONFIRM_PERMISSIBLE", "").strip() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Endato
# ---------------------------------------------------------------------------

def _endato_person_search(
    first_name: str,
    last_name: str,
    city: str = "",
    state: str = "",
) -> Optional[Dict]:
    if not (CONFIG.endato_api_key and CONFIG.endato_api_name):
        return None

    headers = {
        "galaxy-ap-name": CONFIG.endato_api_name,
        "galaxy-ap-password": CONFIG.endato_api_key,
        "galaxy-search-type": "Person",
        "Content-Type": "application/json",
    }
    payload = {
        "FirstName": first_name,
        "LastName": last_name,
        "Addresses": [{"City": city, "State": state}] if city or state else [],
    }
    try:
        sess = polite_session()
        sess.headers.update(headers)
        # Endato uses POST — fall back to direct requests since our http helper is GET-focused
        import requests
        resp = sess.post(
            "https://devapi.endato.com/PersonSearch",
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        people = data.get("persons") or data.get("results", [])
        if not people:
            return None
        top = people[0]
        return {
            "skip_traced_name": top.get("name") or f"{first_name} {last_name}",
            "skip_traced_phones": [p.get("number") for p in top.get("phoneNumbers", []) if p.get("number")],
            "skip_traced_emails": [e.get("address") for e in top.get("emailAddresses", []) if e.get("address")],
            "skip_traced_addresses": [a.get("fullAddress") for a in top.get("addresses", []) if a.get("fullAddress")],
            "skip_traced_dob": top.get("dob"),
            "skip_traced_age": top.get("age"),
            "_skip_source": "endato",
        }
    except Exception as e:
        print(f"[skip_trace] endato failed: {e}")
        return None


# ---------------------------------------------------------------------------
# BatchSkipTracing
# ---------------------------------------------------------------------------

def _batch_skip_trace(
    first_name: str,
    last_name: str,
    address: str = "",
    city: str = "",
    state: str = "",
    zip_code: str = "",
) -> Optional[Dict]:
    if not CONFIG.batch_skip_tracing_api_key:
        return None
    try:
        import requests
        resp = requests.post(
            "https://api.batchskiptracing.com/v2/property/search",
            headers={"Authorization": f"Bearer {CONFIG.batch_skip_tracing_api_key}"},
            json={
                "requests": [{
                    "first_name": first_name,
                    "last_name": last_name,
                    "address": {
                        "street": address, "city": city,
                        "state": state, "zip": zip_code,
                    },
                }],
            },
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return None
        r = results[0]
        return {
            "skip_traced_name": r.get("name"),
            "skip_traced_phones": [p.get("number") for p in r.get("phones", []) if p.get("number")],
            "skip_traced_emails": [e.get("email") for e in r.get("emails", []) if e.get("email")],
            "skip_traced_addresses": [a.get("address") for a in r.get("addresses", []) if a.get("address")],
            "_skip_source": "batchskiptracing",
        }
    except Exception as e:
        print(f"[skip_trace] batch failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def skip_trace_owner(facility: dict) -> dict:
    """
    Skip-trace the human(s) behind the owner LLC. Adds:
      skip_traced_phones (list[str])
      skip_traced_emails (list[str])
      skip_traced_addresses (list[str])
      skip_traced_age (int)
      _skip_source (which provider returned the data)
    """
    if not _permissible_purpose_ok():
        # Hard gate — refuse to call providers without explicit purpose attestation
        return facility

    # Need a human name — use enriched owner_name first, else best-effort
    # parse from primary_owner / legal_owner (often an LLC)
    name = facility.get("owner_name") or ""
    if not name and (facility.get("primary_owner") or facility.get("legal_owner")):
        # Heuristic: try the first two capitalized words that aren't boilerplate
        raw = facility.get("primary_owner") or facility.get("legal_owner")
        import re
        candidate = " ".join(
            t for t in re.findall(r"[A-Z][a-zA-Z]+", str(raw))
            if t.upper() not in {"LLC", "INC", "CORP", "GROUP", "HOLDINGS"}
        )
        name = candidate.strip()

    parts = name.split()
    if len(parts) < 2:
        return facility

    first, last = parts[0], parts[-1]
    city = facility.get("owner_mailing_city") or facility.get("city") or ""
    state = facility.get("owner_mailing_state") or facility.get("state") or ""
    addr = facility.get("owner_mailing_address") or ""
    zip_code = facility.get("owner_mailing_zip") or str(facility.get("zip") or "")

    # Provider waterfall — Endato first (best signal), then Batch
    result = _endato_person_search(first, last, city, state)
    if not result:
        result = _batch_skip_trace(first, last, addr, city, state, zip_code)

    if result:
        facility.update(result)

    return facility
