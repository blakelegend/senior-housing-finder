"""
Off-market motivation scoring.

A facility scores higher when signals suggest the owner may be a motivated
seller. Each signal contributes a weighted sub-score; the final score is the
sum, clipped to [0, 100].

Tune `SCORE_WEIGHTS` to bias toward whatever your acquisition thesis prefers.

Signals (heuristic; not guarantees):
- Age of ownership      — long-held assets are more likely up for transition
- Owner age proxy        — operator company founded long ago + small headcount
- Size fit               — beds within target band scores higher
- Occupancy proxy        — low Google rating count vs. peers (weak proxy)
- Independent ownership  — small operator (not a REIT) scores higher
- License risk           — substandard quality ratings hint at distress
- Geographic fit         — in user's target metros
"""
from datetime import datetime
from typing import Dict, Optional

import pandas as pd

from ..config import CONFIG


SCORE_WEIGHTS = {
    "size_fit": 20,
    "age_of_ownership": 20,
    "operator_independence": 15,
    "operator_age": 15,
    "occupancy_proxy": 10,
    "quality_risk": 10,
    "geo_fit": 10,
}


# ---------------------------------------------------------------------------
# Individual signal scorers (each returns 0..1)
# ---------------------------------------------------------------------------

def _score_size_fit(beds: Optional[float]) -> float:
    """Reward facilities inside the target bed range; gentle falloff outside."""
    if beds is None or pd.isna(beds):
        return 0.0
    beds = float(beds)
    lo, hi = CONFIG.min_beds, CONFIG.max_beds
    if lo <= beds <= hi:
        return 1.0
    if beds < lo:
        return max(0.0, beds / lo)
    return max(0.0, 1.0 - (beds - hi) / hi)


def _score_age_of_ownership(cert_date: Optional[str]) -> float:
    """A facility certified > min_age years ago likely has long-held ownership."""
    if not cert_date or (isinstance(cert_date, float) and pd.isna(cert_date)):
        return 0.0
    try:
        # CMS formats vary: 'YYYY-MM-DD' or 'MM/DD/YYYY'
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                d = datetime.strptime(str(cert_date), fmt)
                break
            except ValueError:
                continue
        else:
            return 0.0
        years = (datetime.now() - d).days / 365.25
    except Exception:
        return 0.0

    lo, hi = CONFIG.min_age_years, CONFIG.max_age_years
    if lo <= years <= hi:
        return 1.0
    if years > hi:
        return 0.6  # very old facilities still get partial credit
    return max(0.0, years / lo)


def _score_operator_independence(facility: dict) -> float:
    """Small/independent operators are more likely off-market sellers."""
    ot = (facility.get("ownership_type") or "").lower()
    if not ot:
        return 0.5  # unknown — neutral
    if "for profit - individual" in ot or "for profit - partnership" in ot:
        return 1.0
    if "for profit - corporation" in ot:
        return 0.6
    if "non profit" in ot:
        return 0.3
    if "government" in ot:
        return 0.1
    return 0.5


def _score_operator_age(facility: dict) -> float:
    """Older operator company + small headcount = founder may be near exit."""
    founded = facility.get("operator_founded_year")
    employees = facility.get("operator_employee_count")
    if founded is None and employees is None:
        return 0.0
    score = 0.0
    if founded:
        try:
            years = datetime.now().year - int(founded)
            score += min(1.0, years / 30.0) * 0.6
        except Exception:
            pass
    if employees:
        try:
            # Bonus for small companies (likely owner-operated)
            if int(employees) <= 100:
                score += 0.4
        except Exception:
            pass
    return min(1.0, score)


def _score_occupancy_proxy(facility: dict) -> float:
    """
    We don't have real occupancy data publicly. Use Google rating count as a
    very weak proxy — low rating count for a sizeable facility may indicate
    low foot traffic / low occupancy. This is intentionally heuristic.
    """
    count = facility.get("rating_count")
    beds = facility.get("beds")
    if not count or not beds:
        return 0.0
    try:
        ratio = float(count) / float(beds)
    except Exception:
        return 0.0
    # Very few reviews per bed -> possible low occupancy
    if ratio < 0.2:
        return 1.0
    if ratio < 0.5:
        return 0.6
    return 0.2


def _score_quality_risk(facility: dict) -> float:
    """
    CMS 5-star ratings — substandard care often correlates with distress.
    Falls back to Google rating if CMS rating is missing.
    """
    star = facility.get("overall_rating") or facility.get("Overall Rating")
    if star:
        try:
            star = float(star)
            if star <= 2:
                return 1.0
            if star <= 3:
                return 0.5
            return 0.1
        except Exception:
            pass

    gr = facility.get("rating")
    if gr:
        try:
            gr = float(gr)
            if gr <= 3.0:
                return 0.8
            if gr <= 3.8:
                return 0.4
            return 0.1
        except Exception:
            pass
    return 0.0


def _score_geo_fit(facility: dict) -> float:
    state = (facility.get("state") or "").upper()
    if not state:
        return 0.0
    return 1.0 if state in {s.strip().upper() for s in CONFIG.target_states} else 0.0


# ---------------------------------------------------------------------------
# Aggregate scoring
# ---------------------------------------------------------------------------

def score_facility(facility: dict) -> Dict[str, float]:
    """Compute the weighted score for a single facility."""
    parts = {
        "size_fit": _score_size_fit(facility.get("beds")),
        "age_of_ownership": _score_age_of_ownership(facility.get("cert_date")),
        "operator_independence": _score_operator_independence(facility),
        "operator_age": _score_operator_age(facility),
        "occupancy_proxy": _score_occupancy_proxy(facility),
        "quality_risk": _score_quality_risk(facility),
        "geo_fit": _score_geo_fit(facility),
    }
    weighted = {k: parts[k] * SCORE_WEIGHTS[k] for k in parts}
    total = sum(weighted.values())
    return {
        **{f"score_{k}": round(parts[k], 3) for k in parts},
        "score_total": round(min(100.0, total), 2),
    }


def score_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorize via .apply — readable, fine for tens of thousands of rows."""
    scored = df.apply(lambda r: score_facility(r.to_dict()), axis=1, result_type="expand")
    return pd.concat([df, scored], axis=1).sort_values("score_total", ascending=False)
