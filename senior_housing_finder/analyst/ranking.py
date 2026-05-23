"""
Composite analyst ranking of off-market acquisition potential.

Six dimensions, weights per the user-stated ranking criteria. We compute
each dimension 0-1 from the underlying signals (which other modules have
already populated), then weighted-sum to a 0-100 composite score.

Each lead also gets `analyst_reasoning` — a structured list of the 3-6
strongest signals that drove its score, in human-readable form. This is
what makes the output actually usable for an analyst.

Dimension       Weight  Source modules
---------       ------  --------------
Succession risk  25     lead_scoring.selling_likelihood (sell_tenure, sell_owner_demographics, sell_family_owned)
Facility age     15     enrichment.tax_records (property_age_years), enrichment.cms_nursing_home (cert_date)
Market demand    15     enrichment.market_demand (market_demand_score)
Financial distress 15   enrichment.tired_owner (tired_owner_score) + tax_records (lien_count)
Valuation        15     valuation.noi_model (NOI per bed vs property type benchmark)
Compliance       15     enrichment.tired_owner (serious_defs_12mo, ij_citations_12mo)
"""
from datetime import datetime
from typing import Dict, List

import pandas as pd


ANALYST_WEIGHTS = {
    "succession_risk":   25,
    "facility_age":      15,
    "market_demand":     15,
    "financial_distress": 15,
    "valuation":         15,
    "compliance":        15,
}


# ---------------------------------------------------------------------------
# Dimension scorers (each returns 0..1)
# ---------------------------------------------------------------------------

def _score_succession(r: pd.Series) -> float:
    """Combine the three selling-likelihood components related to succession."""
    sub = [r.get("sell_tenure"), r.get("sell_owner_demographics"), r.get("sell_family_owned")]
    valid = [float(x) for x in sub if x is not None and pd.notna(x)]
    if not valid:
        # Fall back to a heuristic from cert_date if selling-likelihood wasn't run
        cert = r.get("cert_date") or r.get("oldest_association_date")
        if cert:
            try:
                year = int(str(cert)[:4])
                age = datetime.now().year - year
                if age >= 15:
                    return 0.9
                if age >= 8:
                    return 0.6
                return 0.3
            except Exception:
                return 0.3
        return 0.3
    return min(1.0, sum(valid) / len(valid) * 1.1)


def _score_facility_age(r: pd.Series) -> float:
    """Sweet spot is 10-30 years: old enough for capex needs, young enough to retain value."""
    age = r.get("property_age_years")
    if age is None or pd.isna(age):
        # Fall back to CMS cert date as a (rough) proxy
        cert = r.get("cert_date")
        if cert:
            try:
                age = datetime.now().year - int(str(cert)[:4])
            except Exception:
                return 0.4
        else:
            return 0.4
    try:
        age = float(age)
    except Exception:
        return 0.4

    if age < 5:        return 0.2  # too new — owner unlikely to sell
    if age <= 15:      return 0.8
    if age <= 30:      return 1.0  # sweet spot for value-add
    if age <= 45:      return 0.7
    return 0.5


def _score_market_demand(r: pd.Series) -> float:
    md = r.get("market_demand_score")
    if md is not None and pd.notna(md):
        return float(md) / 100.0
    return 0.4


def _score_financial_distress(r: pd.Series) -> float:
    score = 0.0
    tired = r.get("tired_owner_score")
    if tired is not None and pd.notna(tired):
        score = float(tired) / 100.0
    # Bump for recorded liens
    liens = r.get("lien_count")
    if liens and pd.notna(liens) and float(liens) > 0:
        score = min(1.0, score + 0.2)
    return min(1.0, score)


def _score_valuation(r: pd.Series) -> float:
    """
    Reward high estimated NOI per bed relative to property-type norm.

    A property with above-average NOI per bed is structurally more valuable
    (and gives us pricing flexibility on the bid side).
    """
    noi = r.get("noi_estimate")
    beds = r.get("beds")
    ptype = r.get("property_type_inferred")
    if not noi or not beds or not ptype:
        return 0.3

    try:
        per_bed = float(noi) / float(beds)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.3

    # Benchmarks (approximate NOI/bed at full occupancy for each type)
    benchmarks = {
        "SNF": 25_000, "ALF": 18_000, "MEMORY_CARE": 25_000,
        "IL": 14_000, "CCRC": 16_000, "UNKNOWN": 18_000,
    }
    bench = benchmarks.get(ptype, 18_000)
    return min(1.0, max(0.0, per_bed / bench))


def _score_compliance(r: pd.Series) -> float:
    """
    Compliance scoring is inverted relative to distress:
    - For our acquisition purpose, *some* compliance issues = motivated seller
    - But major IJ citations / SFF status = uninvestable
    """
    ij = r.get("ij_citations_12mo")
    if ij and pd.notna(ij) and float(ij) >= 2:
        # Heavy IJ count → very motivated but also very risky → moderate score
        return 0.6
    serious = r.get("serious_defs_12mo")
    if serious and pd.notna(serious):
        s = float(serious)
        if 1 <= s <= 3:
            return 1.0  # sweet spot — distress without being uninvestable
        if s > 5:
            return 0.4  # too risky
    star = r.get("overall_rating") or r.get("Overall Rating")
    if star:
        try:
            s = float(star)
            if 2 <= s <= 3:
                return 0.8  # below-average → motivated, but operable
            if s == 1:
                return 0.5  # 1-star — high risk
        except Exception:
            pass
    return 0.4


SCORERS = {
    "succession_risk":    _score_succession,
    "facility_age":       _score_facility_age,
    "market_demand":      _score_market_demand,
    "financial_distress": _score_financial_distress,
    "valuation":          _score_valuation,
    "compliance":         _score_compliance,
}


# ---------------------------------------------------------------------------
# Reasoning generator
# ---------------------------------------------------------------------------

def generate_reasoning(r: pd.Series) -> List[str]:
    """Produce 3-6 bullet points explaining why this lead scored where it did."""
    bullets: List[tuple[float, str]] = []

    # Succession / tenure
    cert = r.get("oldest_association_date") or r.get("cert_date")
    if cert:
        try:
            years = datetime.now().year - int(str(cert)[:4])
            if years >= 15:
                bullets.append((9, f"Owner held since {str(cert)[:4]} ({years} yrs) — peak succession window"))
            elif years >= 8:
                bullets.append((6, f"Owner held since {str(cert)[:4]} ({years} yrs) — approaching transition zone"))
        except Exception:
            pass

    # Family-owned
    if (r.get("sell_family_owned") or 0) and float(r.get("sell_family_owned") or 0) > 0.5:
        bullets.append((8, "Family-owned indicator: administrator surname matches owner LLC"))

    # Operator demographics
    founded = r.get("operator_founded_year")
    employees = r.get("operator_employee_count")
    if founded and employees:
        try:
            age = datetime.now().year - int(founded)
            n = int(employees)
            if age >= 25 and n <= 50:
                bullets.append((7, f"Operator company {age} yrs old, only {n} employees — likely founder-led"))
        except Exception:
            pass

    # Facility / property age
    pa = r.get("property_age_years")
    if pa and 10 <= float(pa) <= 30:
        bullets.append((5, f"Building age {int(pa)} yrs — value-add capex sweet spot"))
    elif pa and float(pa) > 35:
        bullets.append((4, f"Building age {int(pa)} yrs — capex-heavy but discounted basis"))

    # Market demand
    md = r.get("market_demand_score")
    if md is not None and pd.notna(md):
        growth = r.get("senior_pop_growth_5yr")
        if growth and pd.notna(growth) and float(growth) > 0.03:
            bullets.append((7, f"65+ pop growing {float(growth)*100:.1f}% / 5yr in this county"))
        if r.get("supply_facilities_per_10k_65plus") is not None and float(r["supply_facilities_per_10k_65plus"]) < 0.4:
            bullets.append((6, "Under-supplied market: <0.4 facilities per 10k seniors"))

    # Financial distress
    tired = r.get("tired_owner_score")
    if tired is not None and pd.notna(tired) and float(tired) >= 50:
        bullets.append((8, f"Tired-owner score {float(tired):.0f}/100 — multiple distress signals"))
    if r.get("lien_count") and pd.notna(r["lien_count"]) and float(r["lien_count"]) > 0:
        bullets.append((9, f"{int(r['lien_count'])} recorded lien(s) — direct financial pressure"))
    if r.get("fines_last_12mo_total") and pd.notna(r["fines_last_12mo_total"]) and float(r["fines_last_12mo_total"]) > 25_000:
        bullets.append((7, f"${float(r['fines_last_12mo_total']):,.0f} in CMS fines (last 12 mo)"))

    # Compliance
    if r.get("ij_citations_12mo") and pd.notna(r["ij_citations_12mo"]) and float(r["ij_citations_12mo"]) > 0:
        bullets.append((6, f"{int(r['ij_citations_12mo'])} immediate-jeopardy citation(s) in last 12 mo"))
    if r.get("serious_defs_12mo") and pd.notna(r["serious_defs_12mo"]):
        n = int(r["serious_defs_12mo"])
        if 1 <= n <= 3:
            bullets.append((5, f"{n} serious deficiency(s) — distress, but operable"))

    # Staffing trend
    trend = r.get("staffing_trend_3mo")
    if trend is not None and pd.notna(trend) and float(trend) < -0.05:
        bullets.append((6, f"PBJ staffing down {abs(float(trend))*100:.1f}% QoQ — early distress signal"))

    # Valuation
    if r.get("value_estimate"):
        try:
            v = float(r["value_estimate"])
            beds = int(float(r.get("beds") or 0))
            ppb = v / max(beds, 1)
            bullets.append((5, f"Estimated value ${v/1e6:.1f}M ({ppb/1000:.0f}k/bed) @ {float(r.get('cap_rate_assumed',0))*100:.1f}% cap"))
        except Exception:
            pass

    # Sort by importance (desc) and take top 6
    bullets.sort(key=lambda x: -x[0])
    return [b for _, b in bullets[:6]] or ["Limited signal — needs further enrichment"]


# ---------------------------------------------------------------------------
# Main ranker
# ---------------------------------------------------------------------------

def rank_acquisition_potential(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute the analyst composite score and per-row reasoning.

    Returns df sorted by `analyst_score` descending with new columns:
      score_succession_risk, score_facility_age, score_market_demand,
      score_financial_distress, score_valuation, score_compliance,
      analyst_score, analyst_reasoning, recommended_action
    """
    if df.empty:
        return df

    parts = pd.DataFrame(index=df.index)
    for dim, fn in SCORERS.items():
        parts[f"score_{dim}"] = df.apply(fn, axis=1)

    weighted = sum(parts[f"score_{dim}"] * w for dim, w in ANALYST_WEIGHTS.items())
    parts["analyst_score"] = weighted.clip(0, 100).round(2)

    parts["analyst_reasoning"] = df.apply(generate_reasoning, axis=1).apply(lambda b: " | ".join(b))
    parts["recommended_action"] = parts["analyst_score"].apply(_recommended_action)

    out = pd.concat([df, parts], axis=1).sort_values("analyst_score", ascending=False)
    return out


def _recommended_action(score: float) -> str:
    if score >= 75:
        return "Immediate outreach: principal-level call + letter same week"
    if score >= 60:
        return "Multi-touch sequence: email + LinkedIn + letter; phone within 14 days"
    if score >= 45:
        return "Standard sequence: enroll in cadence, light enrichment"
    if score >= 30:
        return "Long-term nurture: quarterly check-in"
    return "Park — revisit when more enrichment data available"
