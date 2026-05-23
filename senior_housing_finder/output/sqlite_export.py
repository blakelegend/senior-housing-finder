"""
SQLite export.

Writes the aggregated leads file to a SQLite database with three tables:
- `facilities`  — one row per facility
- `chains`      — one row per detected chain
- `owners`      — one row per owner record from CMS Ownership data

Using stdlib `sqlite3` (no SQLAlchemy dep) because the schema is flat and we
don't need migrations. Re-running the export REPLACES the existing DB to
keep results in sync with the latest CSV.
"""
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from ..config import CONFIG


def export_sqlite(
    facilities: pd.DataFrame,
    chains: Optional[pd.DataFrame] = None,
    ownership: Optional[pd.DataFrame] = None,
    db_name: str = "senior_housing.sqlite",
) -> Path:
    """Write the three tables to a single SQLite file in CONFIG.output_dir."""
    db_path: Path = CONFIG.output_dir / db_name
    if db_path.exists():
        # Snapshot the old file before overwriting — cheap insurance
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        db_path.rename(db_path.with_suffix(f".{ts}.bak.sqlite"))

    with sqlite3.connect(db_path) as conn:
        # Pandas to_sql handles type inference well enough for our needs
        facilities.to_sql("facilities", conn, if_exists="replace", index=False)
        if chains is not None and not chains.empty:
            chains.to_sql("chains", conn, if_exists="replace", index=False)
        if ownership is not None and not ownership.empty:
            ownership.to_sql("owners", conn, if_exists="replace", index=False)

        # Useful indexes for downstream querying
        cur = conn.cursor()
        for ix_sql in (
            "CREATE INDEX IF NOT EXISTS ix_facilities_state ON facilities(state)",
            "CREATE INDEX IF NOT EXISTS ix_facilities_score ON facilities(score_total)",
            "CREATE INDEX IF NOT EXISTS ix_facilities_chain ON facilities(chain_id)",
            "CREATE INDEX IF NOT EXISTS ix_owners_cms ON owners(cms_id)",
            "CREATE INDEX IF NOT EXISTS ix_owners_name ON owners(owner_name)",
            "CREATE INDEX IF NOT EXISTS ix_chains_size ON chains(facility_count)",
        ):
            try:
                cur.execute(ix_sql)
            except sqlite3.OperationalError:
                # Column may not exist on this run — that's fine, skip the index
                pass
        conn.commit()

    return db_path
