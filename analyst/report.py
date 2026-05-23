"""
Top-N analyst report generator.

Produces a Markdown file containing:
  1. Executive summary (universe size, top markets, top operators, total est. value)
  2. Top N leads with per-lead reasoning, valuation, and recommended action
  3. Methodology footer

Markdown is the right format because it renders cleanly in Notion, GitHub,
PRs, and (via pandoc) PDF/DOCX without a templating engine. For PDF directly,
run: `pandoc top_50_leads.md -o top_50_leads.pdf`.
"""
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from ..config import CONFIG


def _fmt_money(x) -> str:
    if x is None or pd.isna(x):
        return "—"
    try:
        n = float(x)
    except Exception:
        return "—"
    if n >= 1_000_000:
        return f"${n/1e6:.1f}M"
    if n >= 1_000:
        return f"${n/1e3:.0f}k"
    return f"${n:.0f}"


def _fmt_pct(x) -> str:
    if x is None or pd.isna(x):
        return "—"
    try:
        return f"{float(x)*100:.1f}%"
    except Exception:
        return "—"


def _exec_summary(df: pd.DataFrame) -> str:
    n = len(df)
    states = df["state"].value_counts().head(5).to_dict() if "state" in df.columns else {}
    operators = (df.get("primary_owner", df.get("legal_owner", pd.Series(dtype=str)))
                  .fillna("").value_counts().head(5).to_dict())
    total_val = df.get("value_estimate", pd.Series(dtype=float)).fillna(0).sum()
    total_beds = pd.to_numeric(df.get("beds", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
    avg_score = df.get("analyst_score", pd.Series(dtype=float)).mean()

    states_str = ", ".join([f"{s} ({c})" for s, c in states.items()]) if states else "—"
    ops_str = ", ".join([f"{o} ({c})" for o, c in operators.items() if o]) if operators else "—"

    return (
        f"## Executive Summary\n\n"
        f"- **Universe analyzed**: {n:,} facilities\n"
        f"- **Total estimated portfolio value**: {_fmt_money(total_val)}\n"
        f"- **Total licensed beds**: {int(total_beds):,}\n"
        f"- **Average analyst score**: {avg_score:.1f} / 100\n"
        f"- **Top 5 states**: {states_str}\n"
        f"- **Top 5 operators (by facility count)**: {ops_str}\n"
    )


def _format_lead(rank: int, r: pd.Series) -> str:
    name = r.get("name") or "Unknown"
    addr_parts = [str(p) for p in [r.get("address"), r.get("city"), r.get("state"), r.get("zip")] if p and not pd.isna(p)]
    address = ", ".join(addr_parts) or "—"

    owner = r.get("primary_owner") or r.get("legal_owner") or r.get("true_owner") or "—"
    owner_name = r.get("owner_name") or r.get("skip_traced_name") or "—"
    owner_phone = r.get("phone_e164") or r.get("phone") or "—"
    owner_email = r.get("owner_email") or "—"

    beds = r.get("beds")
    beds_str = f"{int(float(beds))}" if beds and not pd.isna(beds) else "—"
    ptype = r.get("property_type_inferred") or "—"

    score = r.get("analyst_score")
    score_str = f"{float(score):.1f}" if score is not None and not pd.isna(score) else "—"

    # Dimension breakdown
    dims = [
        ("Succession", r.get("score_succession_risk")),
        ("Facility Age", r.get("score_facility_age")),
        ("Market Demand", r.get("score_market_demand")),
        ("Financial Distress", r.get("score_financial_distress")),
        ("Valuation", r.get("score_valuation")),
        ("Compliance", r.get("score_compliance")),
    ]
    dims_str = " · ".join(f"{n}: {float(v):.2f}" if v is not None and not pd.isna(v) else f"{n}: —" for n, v in dims)

    # Valuation block
    noi = _fmt_money(r.get("noi_estimate"))
    val = _fmt_money(r.get("value_estimate"))
    ppb = _fmt_money(r.get("value_per_bed"))
    cap = _fmt_pct(r.get("cap_rate_assumed"))

    # Reasoning bullets
    reasoning = r.get("analyst_reasoning") or ""
    bullets = [f"  - {b.strip()}" for b in reasoning.split(" | ") if b.strip()]
    bullets_str = "\n".join(bullets) if bullets else "  - (insufficient data)"

    action = r.get("recommended_action") or "—"

    return (
        f"### {rank}. {name} — score {score_str}\n\n"
        f"- **Address**: {address}\n"
        f"- **Type**: {ptype} · **Beds**: {beds_str}\n"
        f"- **Owner of record**: {owner}\n"
        f"- **Decision-maker**: {owner_name} · {owner_phone} · {owner_email}\n"
        f"- **Valuation**: {val} (NOI {noi}, {ppb}/bed @ {cap})\n"
        f"- **Dimension breakdown**: {dims_str}\n"
        f"- **Why this lead**:\n{bullets_str}\n"
        f"- **Recommended action**: {action}\n"
    )


def _methodology() -> str:
    return (
        "## Methodology\n\n"
        "The composite analyst score is a weighted sum of six dimensions:\n\n"
        "| Dimension | Weight | Source |\n"
        "|-----------|--------|--------|\n"
        "| Succession risk | 25 | CMS Ownership tenure, operator demographics, family-owned indicator |\n"
        "| Facility age | 15 | Tax assessor `year_built`; CMS certification date fallback |\n"
        "| Local market demand | 15 | Census ACS 5-Yr: 65+ population size, 5-yr growth, median income, supply density |\n"
        "| Financial distress | 15 | CMS Civil Money Penalties, tired-owner composite, recorded liens |\n"
        "| Valuation attractiveness | 15 | Income approach (beds × ADR × occupancy − opex) ÷ cap rate by property type/state |\n"
        "| Regulatory compliance | 15 | CMS deficiencies and immediate-jeopardy citations (sweet spot: 1-3 serious) |\n\n"
        "**Important caveats**:\n"
        "- Valuations are *triangulated estimates* using default ADR/opex/cap-rate assumptions per property type. "
        "Real underwriting requires T12 P&L, rent roll, payor mix, and capex.\n"
        "- Market demand uses ACS 5-Year — county-level resolution. CBSA-level analysis is more precise for "
        "multi-county metros (Bay Area, NYC).\n"
        "- Compliance scoring is intentionally non-monotone: 1-3 serious deficiencies = motivated seller; "
        "0 = no distress, 5+ = uninvestable.\n"
        "- Big REITs/national chains (Brookdale, Sunrise, Atria, Welltower, Ventas, etc.) are filtered out by "
        "default. Pass `--include-big-operators` to keep them.\n"
    )


def generate_top_leads_report(
    df: pd.DataFrame,
    top_n: int = 50,
    output_name: Optional[str] = None,
) -> Path:
    """
    Write a Markdown analyst report; return the path.

    Expects `analyst_score` and supporting columns to be populated. Run
    `analyst.ranking.rank_acquisition_potential(df)` first.
    """
    output_name = output_name or f"top_{top_n}_leads_{datetime.now().strftime('%Y%m%d')}.md"
    out_path = CONFIG.output_dir / output_name

    if "analyst_score" not in df.columns:
        raise ValueError("DataFrame missing 'analyst_score' — call rank_acquisition_potential first.")

    df = df.sort_values("analyst_score", ascending=False).head(top_n)

    lines: list[str] = [
        f"# Senior Housing Off-Market Acquisition Targets — Top {top_n}",
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · {CONFIG.sender_firm or 'Acquisitions team'}_\n",
        _exec_summary(df),
        "",
        f"## Top {top_n} Leads",
        "",
    ]
    for rank, (_, row) in enumerate(df.iterrows(), 1):
        lines.append(_format_lead(rank, row))
        lines.append("---")
    lines.append(_methodology())
    out_path.write_text("\n".join(lines))
    return out_path
