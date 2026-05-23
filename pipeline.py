"""
Main pipeline orchestrator.

    collect -> merge ownership -> deduplicate -> detect chains
            -> enrich -> score -> export (CSV + XLSX + SQLite)

Usage (CLI):
    python -m senior_housing_finder.pipeline \\
        --states FL,GA,TX,CA,NY \\
        --locations "Tampa, FL" "Austin, TX" \\
        --enrich \\
        --top 200 \\
        --use-scraper   # add headless Google Maps (ToS warning applies)
"""
import argparse
import sys
import time
from pathlib import Path
from typing import List, Optional

import pandas as pd

from .config import CONFIG
from .collectors import (
    collect_cms_nursing_homes,
    collect_cms_ownership,
    aggregate_owners_per_facility,
    collect_google_places,
    collect_google_maps,
    collect_state_licensing,
    collect_medicare_providers,
)
from .clustering import annotate_chains
from .clustering.chain_detector import chain_summary
from .enrichment import (
    enrich_with_property_records,
    enrich_with_company_lookup,
    enrich_with_contacts,
    enrich_with_tired_owner_signals,
    enrich_with_tax_records,
    skip_trace_owner,
    enrich_with_market_demand,
    add_supply_density,
    score_market_demand,
)
from .filters import filter_independent_operators
from .geospatial import cluster_facilities, cluster_summary, render_cluster_map
from .valuation import value_dataframe
from .analyst import rank_acquisition_potential, generate_top_leads_report
from .scoring import score_dataframe
from .lead_scoring.selling_likelihood import score_dataframe_selling, composite_priority
from .output import export_leads, export_sqlite, generate_email, generate_call_script
from .crm.pipeline import LeadPipeline
from .utils.address_parser import normalize_address


def run(
    states: Optional[List[str]] = None,
    locations: Optional[List[str]] = None,
    enrich: bool = True,
    top: int = 100,
    skip_google: bool = False,
    use_scraper: bool = False,
    output_prefix: str = "senior_housing_leads",
    independent_only: bool = True,
    enrich_tired_signals: bool = True,
    enrich_tax: bool = True,
    enrich_skip_trace: bool = False,
    cluster_eps_km: float = 25.0,
    enrich_market_demand: bool = True,
    generate_analyst_report: bool = True,
    analyst_report_top_n: int = 50,
) -> Path:
    """Execute the end-to-end pipeline; return path to the XLSX output."""
    states = states or CONFIG.target_states
    locations = locations or [f"{s}" for s in states]

    print(f"[pipeline] collecting from {len(states)} state(s): {','.join(states)}")
    rows: List[dict] = []

    # ---- Collect facility data --------------------------------------------
    t = time.time()
    rows.extend(collect_cms_nursing_homes(states=states))
    print(f"[pipeline] CMS facilities: {len(rows)} rows ({time.time()-t:.1f}s)")

    t = time.time()
    medicare = collect_medicare_providers(states=states)
    rows.extend(medicare)
    print(f"[pipeline] Medicare: +{len(medicare)} rows ({time.time()-t:.1f}s)")

    t = time.time()
    state_lic = collect_state_licensing(states=states)
    rows.extend(state_lic)
    print(f"[pipeline] State licensing: +{len(state_lic)} rows ({time.time()-t:.1f}s)")

    if not skip_google and CONFIG.google_maps_api_key:
        t = time.time()
        gp = collect_google_places(locations=locations)
        rows.extend(gp)
        print(f"[pipeline] Google Places API: +{len(gp)} rows ({time.time()-t:.1f}s)")
    else:
        print("[pipeline] Google Places API: skipped (no key or --skip-google)")

    if use_scraper:
        print("[pipeline] WARNING: Google Maps UI scraper enabled — see ToS notes in module")
        t = time.time()
        gm = collect_google_maps(cities=locations)
        rows.extend(gm)
        print(f"[pipeline] Google Maps scraper: +{len(gm)} rows ({time.time()-t:.1f}s)")

    if not rows:
        print("[pipeline] no rows collected — exiting")
        sys.exit(1)

    df = pd.DataFrame(rows)

    # ---- Merge CMS ownership data ----------------------------------------
    t = time.time()
    ownership_raw = collect_cms_ownership(states=states)
    if not ownership_raw.empty:
        per_fac = aggregate_owners_per_facility(ownership_raw)
        if "cms_id" in df.columns:
            df = df.merge(per_fac, on="cms_id", how="left")
        print(f"[pipeline] CMS ownership merged: {len(ownership_raw)} owner rows ({time.time()-t:.1f}s)")
    else:
        print("[pipeline] CMS ownership: empty (network issue?)")

    # ---- Deduplicate ------------------------------------------------------
    if "address" in df.columns:
        df["_addr_key"] = df["address"].apply(normalize_address)
        before = len(df)
        df = df.sort_values(by="source").drop_duplicates(subset="_addr_key", keep="first")
        df = df.drop(columns=["_addr_key"])
        print(f"[pipeline] dedup: {before} -> {len(df)} rows")

    # ---- Filter big operators (REITs / national chains) ------------------
    if independent_only:
        df = filter_independent_operators(df)

    # ---- Chain detection (fuzzy clustering on owner names) ---------------
    # Pick the best owner column available
    owner_col = next(
        (c for c in ("primary_owner", "legal_owner", "true_owner") if c in df.columns),
        None,
    )
    if owner_col:
        print(f"[pipeline] detecting chains using '{owner_col}'...")
        df = annotate_chains(df, owner_col=owner_col)
        chains_df = chain_summary(df)
        n_chains = (chains_df["facility_count"] >= 3).sum() if not chains_df.empty else 0
        print(f"[pipeline] found {n_chains} chains (>=3 facilities)")
    else:
        chains_df = pd.DataFrame()
        print("[pipeline] no owner column available — skipping chain detection")

    # ---- Tired-owner CMS distress signals (bulk merge) -------------------
    if enrich_tired_signals:
        try:
            df = enrich_with_tired_owner_signals(df)
        except Exception as e:
            print(f"[pipeline] tired_owner enrichment failed: {e}")

    # ---- Per-row enrichment (property + tax + market + skip-trace + company + contact) --
    if enrich:
        print("[pipeline] enriching per-row (tax, property, market, company, contacts)...")
        records = df.to_dict(orient="records")
        for i, fac in enumerate(records, 1):
            try:
                fac = enrich_with_property_records(fac)
                if enrich_tax:
                    fac = enrich_with_tax_records(fac)
                if enrich_market_demand:
                    fac = enrich_with_market_demand(fac)
                fac = enrich_with_company_lookup(fac)
                fac = enrich_with_contacts(fac)
                if enrich_skip_trace:
                    fac = skip_trace_owner(fac)
            except Exception as e:
                print(f"[pipeline] enrich failed on row {i}: {e}")
            records[i - 1] = fac
            if i % 50 == 0:
                print(f"  ...{i}/{len(records)}")
        df = pd.DataFrame(records)

    # ---- Market demand: supply density + composite score (vectorized) ----
    if enrich_market_demand:
        df = add_supply_density(df)
        df = score_market_demand(df)

    # ---- Valuation -------------------------------------------------------
    print("[pipeline] estimating NOI + valuation...")
    df = value_dataframe(df)

    # ---- Score ------------------------------------------------------------
    df = score_dataframe(df)
    df = score_dataframe_selling(df)
    df = composite_priority(df, fit_weight=0.5)
    print(
        f"[pipeline] scored — top fit = {df['score_total'].iloc[0]:.1f}, "
        f"top selling-likelihood = {df['selling_likelihood'].max():.1f}, "
        f"top priority = {df['priority'].iloc[0]:.1f}"
    )

    # ---- Analyst composite ranking + reasoning ---------------------------
    print("[pipeline] running analyst composite ranking...")
    df = rank_acquisition_potential(df)
    if generate_analyst_report:
        report_path = generate_top_leads_report(df, top_n=analyst_report_top_n)
        print(f"[pipeline] wrote analyst report: {report_path}")

    # ---- Geospatial clustering -------------------------------------------
    if {"lat", "lng"}.issubset(df.columns):
        df = cluster_facilities(df, eps_km=cluster_eps_km)
        clusters = cluster_summary(df)
        if not clusters.empty:
            clusters.to_csv(CONFIG.output_dir / "clusters.csv", index=False)
            print(f"[pipeline] detected {len(clusters)} geographic clusters")
        map_path = render_cluster_map(df)
        if map_path:
            print(f"[pipeline] wrote {map_path}")

    # ---- Seed CRM ---------------------------------------------------------
    crm = LeadPipeline()
    seeded = crm.bulk_import(df, only_with_score=50.0)
    print(f"[pipeline] CRM seeded with {seeded} leads (priority threshold 50)")

    # ---- Embed outreach scripts for the top N ----------------------------
    if top > 0:
        top_n = df.head(top).copy()
        top_n["email_draft"] = top_n.apply(lambda r: generate_email(r.to_dict()), axis=1)
        top_n["call_script"] = top_n.apply(lambda r: generate_call_script(r.to_dict()), axis=1)
        df = pd.concat([top_n, df.iloc[top:]], ignore_index=True)

    # ---- Export -----------------------------------------------------------
    xlsx = export_leads(df, prefix=output_prefix)
    print(f"[pipeline] wrote {xlsx}")

    db = export_sqlite(
        facilities=df,
        chains=chains_df if not chains_df.empty else None,
        ownership=ownership_raw if not ownership_raw.empty else None,
    )
    print(f"[pipeline] wrote {db}")

    return xlsx


def _cli():
    p = argparse.ArgumentParser(description="Senior housing off-market lead finder")
    p.add_argument("--states", help="Comma-separated state codes (e.g. FL,TX,CA,NY)")
    p.add_argument("--locations", nargs="*", help="City seeds for Google searches")
    p.add_argument("--no-enrich", action="store_true", help="Skip enrichment steps")
    p.add_argument("--top", type=int, default=100, help="Embed scripts for top-N")
    p.add_argument("--skip-google", action="store_true", help="Skip Google Places API")
    p.add_argument("--use-scraper", action="store_true",
                   help="Use headless Google Maps scraper (see ToS notes)")
    p.add_argument("--prefix", default="senior_housing_leads",
                   help="Output filename prefix")
    p.add_argument("--include-big-operators", action="store_true",
                   help="Keep Brookdale/Sunrise/etc. (default: filter them out)")
    p.add_argument("--no-tired-signals", action="store_true",
                   help="Skip CMS deficiencies/penalties/PBJ enrichment")
    p.add_argument("--no-tax", action="store_true",
                   help="Skip tax-records / lien enrichment")
    p.add_argument("--skip-trace", action="store_true",
                   help="Run skip-trace lookups (requires CONFIRM_PERMISSIBLE=1)")
    p.add_argument("--cluster-eps-km", type=float, default=25.0,
                   help="DBSCAN distance threshold for clustering (km)")
    p.add_argument("--no-market-demand", action="store_true",
                   help="Skip Census ACS market-demand enrichment")
    p.add_argument("--no-analyst-report", action="store_true",
                   help="Skip generating the Markdown analyst report")
    p.add_argument("--analyst-top-n", type=int, default=50,
                   help="Number of top leads in the analyst report (default 50)")
    args = p.parse_args()

    states = args.states.split(",") if args.states else None
    run(
        states=states,
        locations=args.locations,
        enrich=not args.no_enrich,
        top=args.top,
        skip_google=args.skip_google,
        use_scraper=args.use_scraper,
        output_prefix=args.prefix,
        independent_only=not args.include_big_operators,
        enrich_tired_signals=not args.no_tired_signals,
        enrich_tax=not args.no_tax,
        enrich_skip_trace=args.skip_trace,
        cluster_eps_km=args.cluster_eps_km,
        enrich_market_demand=not args.no_market_demand,
        generate_analyst_report=not args.no_analyst_report,
        analyst_report_top_n=args.analyst_top_n,
    )


if __name__ == "__main__":
    _cli()
