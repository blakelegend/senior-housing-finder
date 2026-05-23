"""
Senior housing off-market lead-finder.

A modular pipeline that combines public CMS/Medicare data with Google Places
discovery, enriches with property records and contact data, scores facilities
for off-market motivation indicators, and exports prioritized leads with
outreach scripts.

Entry points:
- `python -m senior_housing_finder.pipeline`  → CLI pipeline
- `streamlit run senior_housing_finder/dashboard.py`  → dashboard
"""
__version__ = "0.1.0"

from .pipeline import run as run_pipeline

__all__ = ["run_pipeline"]
