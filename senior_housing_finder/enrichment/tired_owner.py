"""
"Tired owner" enrichment.

Three CMS datasets reveal owners under pressure:
1. Health Deficiencies — every survey citation, scope/severity, F-tag
2. Civil Money Penalties — fines and dates
3. Payroll Based Journal (PBJ) — daily nurse staffing-hours-per-resident

We pull each, aggregate to per-facility metrics over the last 12 months,
then compute a composite "tired owner" score 0–100.

Plus a Google review trend signal: facilities whose monthly review velocity
has declined materially are usually struggling operationally.

Source URLs (Socrata datastore):
- Deficiencies: r5ix-sfxw
- Penalties:    g6vv-u9sr
- PBJ Daily:    4rcb-aewy
"""
import io
from datetime import datetime, timedelta
from typing import List, Optional

import pandas as pd

from ..config import CONFIG
from ..utils.http_client import polite_get


CMS_DEFICIENCIES = "https://data.cms.gov/provider-data/api/1/datastore/query/r5ix-sfxw/0"
CMS_PENALTIES = "https://data.cms.gov/provider-data/api/1/datastore/query/g6vv-u9sr/0"
CMS_PBJ_DAILY = "https://data.cms.gov/provider-data/api/1/datastore/query/4rcb-aewy/0"


def _paginate(url: str, params_filter: Optional[dict] = None, max_rows: int = 200_000) -> pd.DataFrame:
    """Walk a Socrata datastore endpoint; return concatenated DataFrame."""
    frames = []
    offset = 0
    page = 5000
    while offset < max_rows:
        params = {"limit": page, "offset": offset}
        if params_filter:
            params.update(params_filter)
        try:
            resp = polite_get(url, params=params, rps=CONFIG.default_rps)
        except Exception as e:
            print(f"[tired_owner] fetch failed at offset {offset}: {e}")
            break
        rows = resp.json().get("results", []) or resp.json().get("data", [])
        if not rows:
            break
        frames.append(pd.DataFrame(rows))
        if len(rows) < page:
            break
        offset += page
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ---------------------------------------------------------------------------
# Deficiencies (F-tags)
# ---------------------------------------------------------------------------

def fetch_deficiencies(months: int = 18) -> pd.DataFrame:
    """Pull recent CMS health deficiencies and tag by severity bucket."""
    df = _paginate(CMS_DEFICIENCIES)
    if df.empty:
        return df

    rename = {
        "Federal Provider Number": "cms_id",
        "CMS Certification Number (CCN)": "cms_id",
        "Survey Date": "survey_date",
        "Deficiency Tag Number": "f_tag",
        "Scope Severity Code": "severity",
        "Deficiency Category": "category",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    if "survey_date" in df.columns:
        df["survey_date"] = pd.to_datetime(df["survey_date"], errors="coerce")
        cutoff = datetime.now() - timedelta(days=30 * months)
        df = df[df["survey_date"] >= cutoff]
    return df


def aggregate_deficiencies(deficiencies: pd.DataFrame) -> pd.DataFrame:
    """Per-facility: total citations, serious (G+) citations, immediate-jeopardy count."""
    if deficiencies.empty:
        return pd.DataFrame()

    # Scope/Severity codes: A-I rated for harm. J/K/L = immediate jeopardy.
    serious_codes = set("GHIJKL")
    ij_codes = set("JKL")

    def _agg(g: pd.DataFrame) -> pd.Series:
        sev = g.get("severity", pd.Series(dtype=str)).fillna("")
        return pd.Series({
            "deficiencies_12mo":   len(g),
            "serious_defs_12mo":   sev.str.upper().isin(serious_codes).sum(),
            "ij_citations_12mo":   sev.str.upper().isin(ij_codes).sum(),
            "last_survey_date":    g["survey_date"].max() if "survey_date" in g.columns else None,
        })

    return deficiencies.groupby("cms_id", as_index=False).apply(_agg).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Penalties (CMPs)
# ---------------------------------------------------------------------------

def fetch_penalties(months: int = 18) -> pd.DataFrame:
    df = _paginate(CMS_PENALTIES)
    if df.empty:
        return df

    rename = {
        "Federal Provider Number": "cms_id",
        "CMS Certification Number (CCN)": "cms_id",
        "Penalty Date": "penalty_date",
        "Fine Amount": "fine_amount",
        "Penalty Type": "penalty_type",
        "Payment Denial Start Date": "denial_start",
        "Payment Denial Length in Days": "denial_days",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    if "penalty_date" in df.columns:
        df["penalty_date"] = pd.to_datetime(df["penalty_date"], errors="coerce")
        cutoff = datetime.now() - timedelta(days=30 * months)
        df = df[df["penalty_date"] >= cutoff]
    if "fine_amount" in df.columns:
        df["fine_amount"] = pd.to_numeric(df["fine_amount"], errors="coerce")
    return df


def aggregate_penalties(penalties: pd.DataFrame) -> pd.DataFrame:
    if penalties.empty:
        return pd.DataFrame()

    def _agg(g: pd.DataFrame) -> pd.Series:
        return pd.Series({
            "penalty_count_12mo":     len(g),
            "fines_last_12mo_total":  g.get("fine_amount", pd.Series(dtype=float)).fillna(0).sum(),
            "max_fine_12mo":          g.get("fine_amount", pd.Series(dtype=float)).fillna(0).max(),
            "had_payment_denial":     bool(g.get("denial_days", pd.Series(dtype=float)).fillna(0).gt(0).any()),
        })

    return penalties.groupby("cms_id", as_index=False).apply(_agg).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Staffing trend (Payroll Based Journal)
# ---------------------------------------------------------------------------

def fetch_pbj_staffing_trend(quarters: int = 4) -> pd.DataFrame:
    """
    Pull recent PBJ daily nurse staffing and compute a per-facility trend.

    Returns one row per facility with `staffing_trend_3mo` (-1.0..+1.0)
    measuring change in HPRD over the most recent vs prior quarter.
    """
    df = _paginate(CMS_PBJ_DAILY, max_rows=500_000)
    if df.empty:
        return df

    rename = {
        "Federal Provider Number": "cms_id",
        "CMS Certification Number (CCN)": "cms_id",
        "WorkDate": "work_date",
        "Total Nurse Staffing Hours": "total_nurse_hours",
        "Total Number of Residents": "residents",
        "Hours per Resident per Day": "hprd",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    if "work_date" in df.columns:
        df["work_date"] = pd.to_datetime(df["work_date"], errors="coerce")
    if "hprd" not in df.columns and {"total_nurse_hours", "residents"}.issubset(df.columns):
        df["hprd"] = pd.to_numeric(df["total_nurse_hours"], errors="coerce") / pd.to_numeric(df["residents"], errors="coerce")

    cutoff = datetime.now() - timedelta(days=90 * quarters)
    df = df[df["work_date"] >= cutoff]
    if df.empty:
        return pd.DataFrame()

    # Split into "recent" (last 90 days) and "prior" quarters
    recent_cut = datetime.now() - timedelta(days=90)
    df["bucket"] = df["work_date"].apply(lambda d: "recent" if d >= recent_cut else "prior")

    pivot = (
        df.groupby(["cms_id", "bucket"])["hprd"]
        .mean()
        .unstack(fill_value=None)
        .reset_index()
    )
    if not {"recent", "prior"}.issubset(pivot.columns):
        return pd.DataFrame()

    pivot["staffing_trend_3mo"] = (pivot["recent"] - pivot["prior"]) / pivot["prior"]
    return pivot[["cms_id", "recent", "prior", "staffing_trend_3mo"]].rename(
        columns={"recent": "hprd_recent_q", "prior": "hprd_prior_q"},
    )


# ---------------------------------------------------------------------------
# Composite + merge
# ---------------------------------------------------------------------------

TIRED_WEIGHTS = {
    "deficiencies":    20,
    "serious_defs":    25,
    "ij":              20,
    "penalties":       15,
    "staffing_drop":   20,
}


def _tired_score(row: pd.Series) -> float:
    score = 0.0
    if row.get("deficiencies_12mo"):
        score += min(1.0, row["deficiencies_12mo"] / 30.0) * TIRED_WEIGHTS["deficiencies"]
    if row.get("serious_defs_12mo"):
        score += min(1.0, row["serious_defs_12mo"] / 5.0) * TIRED_WEIGHTS["serious_defs"]
    if row.get("ij_citations_12mo"):
        score += min(1.0, row["ij_citations_12mo"] / 2.0) * TIRED_WEIGHTS["ij"]
    if row.get("fines_last_12mo_total"):
        score += min(1.0, row["fines_last_12mo_total"] / 250_000.0) * TIRED_WEIGHTS["penalties"]
    trend = row.get("staffing_trend_3mo")
    if pd.notna(trend) and trend is not None:
        # A 20% drop = max signal
        score += min(1.0, max(0.0, -float(trend) / 0.20)) * TIRED_WEIGHTS["staffing_drop"]
    return round(min(100.0, score), 2)


def enrich_with_tired_owner_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Merge all three CMS distress sources into the facility df + composite score."""
    if df.empty or "cms_id" not in df.columns:
        return df

    print("[tired_owner] fetching deficiencies...")
    defs = aggregate_deficiencies(fetch_deficiencies())
    print("[tired_owner] fetching penalties...")
    pens = aggregate_penalties(fetch_penalties())
    print("[tired_owner] computing staffing trend (PBJ — this is the slow one)...")
    pbj = fetch_pbj_staffing_trend()

    out = df.copy()
    if not defs.empty:
        out = out.merge(defs, on="cms_id", how="left")
    if not pens.empty:
        out = out.merge(pens, on="cms_id", how="left")
    if not pbj.empty:
        out = out.merge(pbj, on="cms_id", how="left")

    out["tired_owner_score"] = out.apply(_tired_score, axis=1)
    return out
