"""
Filter out big REITs and national chain operators.

The list below covers the top ~40 operators that collectively control most of
the institutional senior housing universe. Filtering these early means:
- Faster scoring (smaller universe)
- Better signal-to-noise (independents are the actual off-market opportunity)
- No wasted enrichment spend on accounts we won't pursue

Matching is fuzzy: we normalize names (uppercase, strip LLC/INC) and check
substring + rapidfuzz ratio against the exclusion patterns. This catches
"BROOKDALE SR LIVING LLC", "BROOKDALE LIVING COMMUNITIES OF FL INC", etc.

Update `EXCLUDED_OPERATORS` whenever you encounter a chain you don't want
appearing in lead lists.
"""
import re
from typing import Iterable, Tuple

import pandas as pd
from rapidfuzz import fuzz


# Each entry: (canonical_name, [aliases to substring-match])
# Aliases should be UPPER and already normalized of common boilerplate
EXCLUDED_OPERATORS: list[Tuple[str, list[str]]] = [
    # Public REITs & their managed portfolios
    ("Brookdale Senior Living",   ["BROOKDALE"]),
    ("Welltower",                 ["WELLTOWER", "HEALTH CARE REIT"]),
    ("Ventas",                    ["VENTAS"]),
    ("Omega Healthcare",          ["OMEGA HEALTHCARE", "OHI"]),
    ("Sabra Health Care",         ["SABRA"]),
    ("LTC Properties",            ["LTC PROPERTIES"]),
    ("CareTrust REIT",            ["CARETRUST"]),
    ("National Health Investors", ["NATIONAL HEALTH INVESTORS"]),
    ("Diversified Healthcare",    ["DIVERSIFIED HEALTHCARE"]),

    # Large national operators (private + public)
    ("Sunrise Senior Living",       ["SUNRISE SENIOR", "SUNRISE LIVING"]),
    ("Atria Senior Living",         ["ATRIA"]),
    ("Holiday Retirement",          ["HOLIDAY RETIREMENT", "HOLIDAY BY ATRIA"]),
    ("Five Star Senior Living",     ["FIVE STAR"]),
    ("Belmont Village",             ["BELMONT VILLAGE"]),
    ("Erickson Senior Living",      ["ERICKSON"]),
    ("Life Care Services",          ["LIFE CARE SERVICES", "LCS"]),
    ("Watermark Retirement",        ["WATERMARK"]),
    ("Capital Senior Living",       ["CAPITAL SENIOR"]),
    ("Discovery Senior Living",     ["DISCOVERY SENIOR"]),
    ("Senior Lifestyle",            ["SENIOR LIFESTYLE"]),
    ("Leisure Care",                ["LEISURE CARE"]),
    ("Eclipse Senior Living",       ["ECLIPSE SENIOR"]),
    ("Brightview Senior Living",    ["BRIGHTVIEW"]),
    ("Pacifica Senior Living",      ["PACIFICA SENIOR"]),
    ("Senior Resource Group",       ["SENIOR RESOURCE GROUP"]),
    ("Maplewood Senior Living",     ["MAPLEWOOD SENIOR"]),
    ("Benchmark Senior Living",     ["BENCHMARK SENIOR"]),
    ("Vi Senior Living",            ["VI LIVING", "CLASSIC RESIDENCE"]),
    ("Sonida Senior Living",        ["SONIDA"]),

    # Large SNF chains
    ("Genesis HealthCare",          ["GENESIS HEALTHCARE"]),
    ("Ensign Group",                ["ENSIGN GROUP"]),
    ("Consulate Health Care",       ["CONSULATE HEALTH"]),
    ("Life Care Centers of America", ["LIFE CARE CENTERS"]),
    ("HCR ManorCare / ProMedica",   ["HCR MANORCARE", "PROMEDICA SENIOR"]),
    ("Signature HealthCARE",        ["SIGNATURE HEALTHCARE"]),
    ("Diversicare",                 ["DIVERSICARE"]),
    ("SavaSeniorCare",              ["SAVA SENIOR"]),
    ("Trilogy Health Services",     ["TRILOGY HEALTH"]),
]


_BOILERPLATE_RE = re.compile(
    r"\b(LLC|L L C|INC|CORP|CORPORATION|LP|LTD|LIMITED|HOLDINGS?|GROUP|COMPANY|CO|"
    r"OPERATIONS|MANAGEMENT|MGMT|THE)\b",
    re.IGNORECASE,
)


def _normalize(name: str) -> str:
    if not name:
        return ""
    s = name.upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = _BOILERPLATE_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def is_excluded_operator(name: str, fuzz_threshold: int = 92) -> Tuple[bool, str]:
    """
    Return (excluded, matched_canonical_name).

    Substring match is the primary signal; rapidfuzz catches misspellings
    and abbreviation variants ("BROOKDALE SENIOR LIVING" vs "BROOKDALE SR LIVING").
    """
    norm = _normalize(name)
    if not norm:
        return False, ""

    for canonical, aliases in EXCLUDED_OPERATORS:
        for alias in aliases:
            if alias in norm:
                return True, canonical
            # Fuzzy match against the alias (catches typos / OCR errors)
            if fuzz.partial_ratio(alias, norm) >= fuzz_threshold:
                return True, canonical
    return False, ""


def filter_independent_operators(
    df: pd.DataFrame,
    owner_cols: Iterable[str] = ("primary_owner", "legal_owner", "true_owner", "all_owners"),
    annotate_only: bool = False,
) -> pd.DataFrame:
    """
    Remove (or just annotate) rows whose owner matches an excluded operator.

    Args:
        df: input facility DataFrame
        owner_cols: columns to check, in priority order
        annotate_only: if True, keep all rows but add `excluded_operator` /
                       `excluded_match` columns instead of filtering

    Returns:
        Filtered DataFrame (or annotated, if annotate_only=True).
    """
    if df.empty:
        return df

    available = [c for c in owner_cols if c in df.columns]
    if not available:
        return df.assign(excluded_operator=False, excluded_match="")

    def _check_row(row) -> Tuple[bool, str]:
        for col in available:
            val = row.get(col)
            if not val:
                continue
            excluded, match = is_excluded_operator(str(val))
            if excluded:
                return True, match
        return False, ""

    flags = df.apply(_check_row, axis=1)
    df = df.copy()
    df["excluded_operator"] = flags.apply(lambda x: x[0])
    df["excluded_match"] = flags.apply(lambda x: x[1])

    if annotate_only:
        return df

    n_before = len(df)
    df = df[~df["excluded_operator"]].drop(columns=["excluded_operator", "excluded_match"])
    n_excluded = n_before - len(df)
    print(f"[filter] excluded {n_excluded} rows matching big operator list")
    return df
