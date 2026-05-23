"""
Streamlit dashboard for browsing scored leads.

Run with:
    streamlit run senior_housing_finder/dashboard.py

The dashboard loads the most recent XLSX file from CONFIG.output_dir and
offers filtering, sorting, map visualization, and one-click script preview.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

from .config import CONFIG
from .output.scripts import generate_email, generate_call_script


st.set_page_config(page_title="Senior Housing Leads", layout="wide")


@st.cache_data(ttl=60)
def _load_latest() -> pd.DataFrame:
    files = sorted(Path(CONFIG.output_dir).glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return pd.DataFrame()
    return pd.read_excel(files[0], sheet_name="Leads")


def main():
    st.title("Senior Housing — Off-Market Lead Finder")
    df = _load_latest()
    if df.empty:
        st.warning("No leads file found. Run the pipeline first: "
                   "`python -m senior_housing_finder.pipeline --states FL`")
        return

    # --- Sidebar filters ---------------------------------------------------
    st.sidebar.header("Filters")
    min_score = st.sidebar.slider("Minimum score", 0.0, 100.0, 40.0, 1.0)
    states = st.sidebar.multiselect("State", sorted(df["state"].dropna().unique()) if "state" in df else [])
    min_beds, max_beds = st.sidebar.slider("Beds", 0, 300, (20, 120))
    only_with_email = st.sidebar.checkbox("Only with owner email", value=False)

    view = df[df["score_total"] >= min_score]
    if states:
        view = view[view["state"].isin(states)]
    if "beds" in view.columns:
        view = view[view["beds"].between(min_beds, max_beds, inclusive="both")]
    if only_with_email and "owner_email" in view.columns:
        view = view[view["owner_email"].notna() & (view["owner_email"] != "")]

    # --- KPIs --------------------------------------------------------------
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total leads", len(view))
    c2.metric("Avg score", f"{view['score_total'].mean():.1f}" if not view.empty else "—")
    c3.metric("With owner email", int(view["owner_email"].notna().sum()) if "owner_email" in view else 0)
    c4.metric("Total beds", int(view["beds"].fillna(0).sum()) if "beds" in view else 0)

    st.divider()

    # --- Map ---------------------------------------------------------------
    if {"lat", "lng"}.issubset(view.columns):
        map_df = view.dropna(subset=["lat", "lng"]).rename(columns={"lng": "lon"})
        if not map_df.empty:
            st.subheader("Geographic distribution")
            st.map(map_df[["lat", "lon"]])

    # --- Lead table --------------------------------------------------------
    st.subheader(f"Top {len(view)} leads")
    show_cols = [c for c in [
        "score_total", "name", "city", "state", "beds",
        "ownership_type", "owner_name", "owner_email", "phone_e164",
        "operator_domain", "rating",
    ] if c in view.columns]
    st.dataframe(view[show_cols], use_container_width=True, height=400)

    # --- Per-lead drill-in -------------------------------------------------
    st.subheader("Drill into a lead")
    if not view.empty:
        chosen = st.selectbox("Pick a facility", view["name"].tolist())
        if chosen:
            row = view[view["name"] == chosen].iloc[0].to_dict()
            colA, colB = st.columns(2)
            with colA:
                st.markdown("**Email draft**")
                st.code(generate_email(row), language="text")
            with colB:
                st.markdown("**Call script**")
                st.code(generate_call_script(row), language="text")
            with st.expander("Full record"):
                st.json({k: v for k, v in row.items() if pd.notna(v) and v != ""})


if __name__ == "__main__":
    main()
