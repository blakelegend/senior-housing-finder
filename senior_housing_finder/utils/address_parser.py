"""
Address parsing and normalization helpers.

Uses `usaddress` for tagging US addresses into components, then normalizes
them into a consistent dict that the rest of the pipeline expects.
"""
from typing import Dict, Optional

import usaddress


# Canonical street suffix abbreviations (subset — extend as needed)
_STREET_SUFFIX = {
    "STREET": "ST", "AVENUE": "AVE", "BOULEVARD": "BLVD", "DRIVE": "DR",
    "ROAD": "RD", "LANE": "LN", "COURT": "CT", "CIRCLE": "CIR",
    "PLACE": "PL", "PARKWAY": "PKWY", "HIGHWAY": "HWY", "TERRACE": "TER",
}


def parse_address(raw) -> Dict[str, str]:
    """Tag a freeform address string into named components."""
    # Pandas NaN floats sneak through dataframe columns where addresses
    # are missing; coerce non-strings to empty so usaddress doesn't blow up
    # deep in its regex layer with a confusing TypeError.
    if not isinstance(raw, str) or not raw.strip():
        return {"raw": "", "parse_error": "not_a_string"}
    try:
        tagged, _ = usaddress.tag(raw)
    except usaddress.RepeatedLabelError:
        # When the same component appears twice (e.g. two ZIPs), fall back to
        # the simpler parse() to at least get a flat tag list
        return {"raw": raw, "parse_error": "repeated_label"}

    return {
        "street_number": tagged.get("AddressNumber", ""),
        "street_name": tagged.get("StreetName", ""),
        "street_suffix": tagged.get("StreetNamePostType", ""),
        "unit": tagged.get("OccupancyIdentifier", ""),
        "city": tagged.get("PlaceName", ""),
        "state": tagged.get("StateName", ""),
        "zip": tagged.get("ZipCode", ""),
        "raw": raw,
    }


def normalize_address(raw) -> Optional[str]:
    """Produce a canonical uppercase form for fuzzy matching/dedup."""
    # Pandas NaN is a float and truthy — `if not raw` doesn't catch it.
    # Explicitly require a real non-empty string before parsing.
    if not isinstance(raw, str) or not raw.strip():
        return None
    parsed = parse_address(raw)
    if "parse_error" in parsed:
        return raw.upper().strip()

    suffix = parsed["street_suffix"].upper()
    suffix = _STREET_SUFFIX.get(suffix, suffix)

    parts = [
        parsed["street_number"],
        parsed["street_name"].upper(),
        suffix,
        parsed["city"].upper(),
        parsed["state"].upper(),
        parsed["zip"],
    ]
    return " ".join(p for p in parts if p).strip()
