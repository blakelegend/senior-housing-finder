"""
Selling-likelihood score.

Different question from `scoring/motivation.py`:
- motivation.py:           "is this a fit for our acquisition thesis?"
- selling_likelihood.py:   "is this owner likely to sell in the next 24 months?"

We weight signals derived from market reality in senior housing:

1. **Ownership tenure (25)** — operators holding > 8 years are statistically
   far more likely to transition. The peak transition window is 12-20 years.
2. **Owner demographic proxy (20)** — operators founded > 25 years ago and
   still managed by founders skew toward succession/exit. Use SOS officer
   data when available; fall back to operator-company founding year.
3. **CMS distress signals (15)** — recent rating drops, enforcement actions,
   F-tags, denied admissions. SNF-only signal.
4. **Occupancy / staffing distress (15)** — declining occupancy or staffing
   turnover (CMS Payroll Based Journal). Proxies if PBJ unavailable.
5. **Sponsor lifecycle (10)** — PE/REIT-owned facilities approaching fund-
   end or hold-period maturity. Use SEC EDGAR signals if available.
6. **Real estate value gap (10)** — county appraised value materially above
   debt → high incentive to monetize; below → distress.
7. **Family-owned indicator (5)** — common surname across owner LLC + a
   licensed administrator with same surname → succession candidate.

Each sub-score ∈ [0,1]; final = weighted sum ∈ [0,100].
"""
from datetime import datetime
from typing import Dict, Optional

import pandas as pd


SELLING_WEIGHTS = {
    "tenure": 25,
    "owner_demographics": 20,
    "distress_signals": 15,
    "occupancy_distress": 15,
    "sponsor_lifecycle": 10,
    "value_gap": 10,
    "family_owned": 5,
}


def _years_since(value) -> Optional[float]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%Y"):
        try:
            d = datetime.strptime(s[:len(fmt) + 2], fmt) if fmt == "%Y" else datetime.strptime(s, fmt)
            return (datetime.now() - d).days / 365.25
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Signal scorers
# ---------------------------------------------------------------------------

def _score_tenure(facility: dict) -> float:
    """
    Peak selling window is ~12-20 years of ownership. Below 5 years = unlikely;
    above 25 years = also peak (estate / succession driven).
    """
    # Prefer "oldest_association_date" from CMS Ownership; fall back to cert_date
    years = _years_since(facility.get("oldest_association_date")) or _years_since(facility.get("cert_date"))
    if years is None:
        return 0.3  # unknown — slight prior

    if years < 3:
        return 0.05
    if years < 8:
        return 0.3
    if years <= 20:
        return 1.0
    if years <= 30:
        return 0.85
    return 0.7


def _score_owner_demographics(facility: dict) -> float:
    """Operator company > 25 years old AND small headcount → likely founder-led."""
    founded = facility.get("operator_founded_year")
    employees = facility.get("operator_employee_count")
    if not founded and not employees:
        return 0.3

    score = 0.0
    if founded:
        try:
            age = datetime.now().year - int(founded)
            if age >= 35:
                score += 0.7
            elif age >= 25:
                score += 0.5
            elif age >= 15:
                score += 0.3
        except Exception:
            pass

    if employees:
        try:
            n = int(employees)
            # Small operator company suggests owner-operator (vs PE-backed platform)
            if n <= 50:
                score += 0.3
            elif n <= 200:
                score += 0.15
        except Exception:
            pass

    return min(1.0, score)


def _score_distress_signals(facility: dict) -> float:
    """CMS overall star rating; recent enforcement actions if available."""
    score = 0.0
    star = facility.get("overall_rating") or facility.get("Overall Rating")
    if star:
        try:
            s = float(star)
            if s <= 1.5:
                score += 0.8
            elif s <= 2.5:
                score += 0.5
            elif s <= 3.5:
                score += 0.2
        except Exception:
            pass

    # CMS Special Focus Facility status — the strongest distress signal
    sff = (facility.get("sff_status") or "").lower()
    if "special focus" in sff or sff == "yes":
        score = min(1.0, score + 0.4)

    # Recent fines (CMS Penalties dataset can be merged in)
    fines_12mo = facility.get("fines_last_12mo_total")
    if fines_12mo:
        try:
            if float(fines_12mo) > 100_000:
                score = min(1.0, score + 0.3)
            elif float(fines_12mo) > 25_000:
                score = min(1.0, score + 0.15)
        except Exception:
            pass

    return min(1.0, score)


def _score_occupancy_distress(facility: dict) -> float:
    """
    Low or declining occupancy is the most reliable distress predictor.
    We use:
    - explicit `occupancy_pct` if a paid source provides it
    - PBJ staffing-hours-per-resident as a weaker proxy
    - Google review count per bed as a very weak proxy (existing fallback)
    """
    occ = facility.get("occupancy_pct")
    if occ:
        try:
            pct = float(occ)
            if pct < 70:
                return 1.0
            if pct < 80:
                return 0.7
            if pct < 88:
                return 0.4
            return 0.1
        except Exception:
            pass

    # PBJ staffing data — sudden drops correlate with operator distress
    staffing_trend = facility.get("staffing_trend_3mo")
    if staffing_trend is not None:
        try:
            t = float(staffing_trend)
            if t < -0.15:
                return 0.8
            if t < -0.05:
                return 0.5
        except Exception:
            pass

    # Weak Google review proxy as fallback
    count = facility.get("rating_count")
    beds = facility.get("beds")
    if count and beds:
        try:
            ratio = float(count) / float(beds)
            if ratio < 0.2:
                return 0.6
            if ratio < 0.5:
                return 0.3
        except Exception:
            pass
    return 0.2


def _score_sponsor_lifecycle(facility: dict) -> float:
    """
    PE-/REIT-owned facilities approaching fund maturity or hold-period end
    are forced sellers. Heuristics from operator profile.
    """
    ot = (facility.get("ownership_type") or "").lower()
    owners = (facility.get("all_owners") or "").lower()

    # Big-cap REITs rarely sell single assets but DO trim portfolios
    if any(name in owners for name in [
        "ventas", "welltower", "omega healthcare", "sabra",
        "national health investors", "ltc properties", "caretrust",
    ]):
        return 0.5  # always worth a call — they trim quarterly

    # PE-backed (often shows up as "FOR PROFIT - LIMITED LIABILITY COMPANY")
    if "limited liability company" in ot and facility.get("operator_employee_count"):
        try:
            n = int(facility["operator_employee_count"])
            # Mid-size = likely PE platform
            if 200 <= n <= 5000:
                return 0.6
        except Exception:
            pass

    return 0.2


def _score_value_gap(facility: dict) -> float:
    """
    County appraised value vs estimated debt. Requires assessor enrichment.
    If we have appraised value but no debt estimate, use beds × $/bed
    regional comp as a rough debt proxy.
    """
    appraised = facility.get("appraised_value")
    debt = facility.get("estimated_debt")
    if not appraised:
        return 0.3  # unknown
    try:
        a = float(appraised)
        if debt:
            ratio = a / float(debt)
            if ratio > 2.0:
                return 1.0  # huge equity → motivated to monetize
            if ratio > 1.5:
                return 0.7
            if ratio > 1.0:
                return 0.4
            return 0.8  # underwater → distressed seller
    except Exception:
        return 0.3
    return 0.3


def _score_family_owned(facility: dict) -> float:
    """
    Family-owned indicators:
    - Owner LLC name contains a surname that also appears in administrator name
    - Multiple owners with shared surname in CMS Ownership data
    """
    owners = facility.get("all_owners") or ""
    administrator = facility.get("administrator_name") or ""
    if not owners or not administrator:
        return 0.0

    # Find capitalized last words in owner list (proxy for surnames)
    owner_tokens = {
        t.strip(",.") for t in owners.upper().split()
        if t.isalpha() and len(t) >= 3 and t not in {"LLC", "INC", "GROUP", "CORP", "THE"}
    }
    admin_tokens = {t.strip(",.") for t in administrator.upper().split() if t.isalpha()}
    shared = owner_tokens & admin_tokens
    if shared:
        return 1.0
    return 0.0


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def score_selling_likelihood(facility: dict) -> Dict[str, float]:
    parts = {
        "tenure":              _score_tenure(facility),
        "owner_demographics":  _score_owner_demographics(facility),
        "distress_signals":    _score_distress_signals(facility),
        "occupancy_distress":  _score_occupancy_distress(facility),
        "sponsor_lifecycle":   _score_sponsor_lifecycle(facility),
        "value_gap":           _score_value_gap(facility),
        "family_owned":        _score_family_owned(facility),
    }
    weighted = {k: parts[k] * SELLING_WEIGHTS[k] for k in parts}
    total = sum(weighted.values())
    return {
        **{f"sell_{k}": round(parts[k], 3) for k in parts},
        "selling_likelihood": round(min(100.0, total), 2),
    }


def score_dataframe_selling(df: pd.DataFrame) -> pd.DataFrame:
    """Add selling-likelihood columns to df."""
    scored = df.apply(lambda r: score_selling_likelihood(r.to_dict()), axis=1, result_type="expand")
    return pd.concat([df, scored], axis=1)


def composite_priority(df: pd.DataFrame, fit_weight: float = 0.5) -> pd.DataFrame:
    """
    Combine acquisition-fit (score_total) and selling-likelihood into one
    priority score used for sequence eligibility.
    """
    if "score_total" not in df.columns and "selling_likelihood" not in df.columns:
        return df
    fit = df.get("score_total", pd.Series([0] * len(df))).fillna(0)
    sell = df.get("selling_likelihood", pd.Series([0] * len(df))).fillna(0)
    df = df.copy()
    df["priority"] = (fit * fit_weight + sell * (1 - fit_weight)).round(2)
    return df.sort_values("priority", ascending=False)
