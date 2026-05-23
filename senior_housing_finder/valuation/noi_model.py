"""
NOI and valuation estimation.

This is a *triangulated estimate*, not a real underwrite — the goal is to
rank-order the universe, not to set bid prices. Real underwriting requires
the T12 P&L, rent roll, payor mix, and capex schedule.

Model:

    occupied_beds   = beds × occupancy
    gross_revenue   = occupied_beds × ADR × 365
    opex            = gross_revenue × opex_ratio
    noi             = gross_revenue − opex
    value           = noi ÷ cap_rate

Defaults by property type drive ADR, opex_ratio, occupancy, and cap rate.
State adjustments tweak cap rate to reflect market preference (FL/TX trade
tighter than rural Midwest).

Where the facility provides better signal, we use it:
- explicit `occupancy_pct` from paid sources
- explicit `cms_id` → SNF rates; otherwise heuristic from license_type

You can override any default by editing PROPERTY_TYPE_DEFAULTS or by passing
custom assumptions to `estimate_noi()`.

Sources for default ranges:
- NIC MAP Vision quarterly reports (occupancy, rate trends)
- CBRE / JLL senior housing transaction reports (cap rates)
- HealthTrust Performance Group operator benchmarks (opex ratios)
"""
from typing import Dict, Optional

import pandas as pd


# All ADR figures are average daily rate per resident (private pay + Medicare blend)
PROPERTY_TYPE_DEFAULTS: Dict[str, Dict[str, float]] = {
    "SNF":              {"adr": 320,  "occupancy": 0.82, "opex_ratio": 0.72, "cap_rate": 0.115},
    "ALF":              {"adr": 180,  "occupancy": 0.85, "opex_ratio": 0.65, "cap_rate": 0.075},
    "MEMORY_CARE":      {"adr": 230,  "occupancy": 0.83, "opex_ratio": 0.68, "cap_rate": 0.080},
    "IL":               {"adr": 110,  "occupancy": 0.88, "opex_ratio": 0.55, "cap_rate": 0.060},
    "CCRC":             {"adr": 150,  "occupancy": 0.88, "opex_ratio": 0.60, "cap_rate": 0.065},
    "UNKNOWN":          {"adr": 180,  "occupancy": 0.83, "opex_ratio": 0.68, "cap_rate": 0.085},
}


# Cap rate adjustment by state — negative = market trades tighter (more buyer demand)
STATE_CAP_RATE_ADJ: Dict[str, float] = {
    # Tightest markets — high demand, low supply
    "FL": -0.005, "TX": -0.005, "AZ": -0.005, "NC": -0.003,
    "CA": -0.010, "WA": -0.005, "CO": -0.003, "MA": -0.003,
    # Neutral
    "GA": 0.000,  "TN": 0.000,  "SC": 0.000,  "VA": 0.000,
    # Wider — secondary / tertiary markets
    "OH": 0.003, "PA": 0.003, "IN": 0.005, "MI": 0.005,
    "MO": 0.008, "KY": 0.008, "WV": 0.010, "MS": 0.010,
}


def _infer_property_type(facility: dict) -> str:
    """Best-effort mapping of license_type / source → our internal type."""
    # CMS-certified means it's a SNF (some duals exist but rare)
    if facility.get("cms_id") or (facility.get("source") or "").startswith("CMS"):
        return "SNF"

    lic = (facility.get("license_type") or "").lower()
    types = (facility.get("types") or "").lower()
    blob = f"{lic} {types}"

    if "memory" in blob or "alzheimer" in blob or "dementia" in blob:
        return "MEMORY_CARE"
    if "ccrc" in blob or "continuing care" in blob:
        return "CCRC"
    if "independent" in blob:
        return "IL"
    if "assisted" in blob or "rcfe" in blob or "residential care" in blob or "elderly" in blob:
        return "ALF"
    if "nursing" in blob or "skilled" in blob:
        return "SNF"
    return "UNKNOWN"


def estimate_noi(
    facility: dict,
    assumptions: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """
    Return a dict with revenue, opex, NOI, and the assumption set used.

    `assumptions` lets the caller override defaults for sensitivity analysis.
    """
    ptype = _infer_property_type(facility)
    defaults = {**PROPERTY_TYPE_DEFAULTS.get(ptype, PROPERTY_TYPE_DEFAULTS["UNKNOWN"])}
    if assumptions:
        defaults.update(assumptions)

    # Beds: prefer explicit beds, fall back to median in the property-type range
    try:
        beds = float(facility.get("beds") or 0)
    except (TypeError, ValueError):
        beds = 0
    if beds <= 0:
        return {
            "noi_estimate": None,
            "revenue_estimate": None,
            "opex_estimate": None,
            "property_type_inferred": ptype,
        }

    # Override occupancy if we have it from paid sources
    occ = defaults["occupancy"]
    try:
        if facility.get("occupancy_pct") and float(facility["occupancy_pct"]) > 0:
            occ = float(facility["occupancy_pct"]) / 100 if float(facility["occupancy_pct"]) > 1.5 else float(facility["occupancy_pct"])
    except (TypeError, ValueError):
        pass

    occupied = beds * occ
    revenue = occupied * defaults["adr"] * 365
    opex = revenue * defaults["opex_ratio"]
    noi = revenue - opex

    return {
        "property_type_inferred": ptype,
        "occupancy_assumed":      round(occ, 3),
        "adr_assumed":            round(defaults["adr"], 2),
        "opex_ratio_assumed":     round(defaults["opex_ratio"], 3),
        "revenue_estimate":       round(revenue, 0),
        "opex_estimate":          round(opex, 0),
        "noi_estimate":           round(noi, 0),
    }


def estimate_value(
    facility: dict,
    assumptions: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """Adds NOI fields + valuation + implied cap rate to the facility dict."""
    base = estimate_noi(facility, assumptions)
    if not base.get("noi_estimate"):
        return base

    ptype = base["property_type_inferred"]
    cap_default = PROPERTY_TYPE_DEFAULTS[ptype]["cap_rate"]
    state_adj = STATE_CAP_RATE_ADJ.get((facility.get("state") or "").upper(), 0.0)
    cap_rate = cap_default + state_adj
    if assumptions and "cap_rate" in assumptions:
        cap_rate = assumptions["cap_rate"]

    value = base["noi_estimate"] / cap_rate if cap_rate > 0 else None
    value_per_bed = (value / float(facility.get("beds") or 1)) if value else None

    base.update({
        "cap_rate_assumed":      round(cap_rate, 4),
        "value_estimate":        round(value, 0) if value else None,
        "value_per_bed":         round(value_per_bed, 0) if value_per_bed else None,
        "valuation_method":      "income_approach_with_defaults",
    })
    return base


def value_dataframe(
    df: pd.DataFrame,
    assumptions: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """Apply estimate_value across all rows; return df with valuation columns."""
    if df.empty:
        return df
    vals = df.apply(lambda r: estimate_value(r.to_dict(), assumptions), axis=1, result_type="expand")
    return pd.concat([df, vals], axis=1)
