"""
Incremental scraping — track when each data source was last pulled.

State is kept in a small SQLite file (`runs.sqlite`) alongside the rest of
the output. Each source name maps to (last_run_ts, row_count, status).

The collector pattern:

    from senior_housing_finder.utils.incremental import last_run, mark_run, is_stale

    if is_stale("cms_provider", max_age_hours=168):   # weekly
        rows = collect_cms_nursing_homes(states)
        mark_run("cms_provider", row_count=len(rows))
    else:
        rows = []  # use cached file or skip entirely

This is intentionally lightweight — no migrations, no ORM. The pipeline
checks staleness; the disk cache in `utils/http.py` does the actual content
caching on a per-URL basis.
"""
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ..config import CONFIG


def _db_path() -> Path:
    p = CONFIG.output_dir / "runs.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _init() -> None:
    with sqlite3.connect(_db_path()) as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                source       TEXT PRIMARY KEY,
                last_run_ts  REAL NOT NULL,
                last_run_iso TEXT NOT NULL,
                row_count    INTEGER,
                status       TEXT,
                detail       TEXT
            )
        """)


def last_run(source: str) -> Optional[dict]:
    """Return the most recent run record for `source`, or None."""
    _init()
    with sqlite3.connect(_db_path()) as c:
        c.row_factory = sqlite3.Row
        row = c.execute("SELECT * FROM runs WHERE source = ?", (source,)).fetchone()
        return dict(row) if row else None


def is_stale(source: str, max_age_hours: float = 168) -> bool:
    """True if the source has never run or its last run is older than `max_age_hours`."""
    rec = last_run(source)
    if not rec:
        return True
    age = time.time() - float(rec["last_run_ts"])
    return age >= max_age_hours * 3600


def mark_run(
    source: str,
    row_count: Optional[int] = None,
    status: str = "ok",
    detail: str = "",
) -> None:
    _init()
    now = time.time()
    with sqlite3.connect(_db_path()) as c:
        c.execute(
            """
            INSERT INTO runs (source, last_run_ts, last_run_iso, row_count, status, detail)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                last_run_ts  = excluded.last_run_ts,
                last_run_iso = excluded.last_run_iso,
                row_count    = excluded.row_count,
                status       = excluded.status,
                detail       = excluded.detail
            """,
            (source, now, datetime.utcfromtimestamp(now).isoformat(), row_count, status, detail),
        )


def summary() -> list[dict]:
    """All run records — for dashboards and debugging."""
    _init()
    with sqlite3.connect(_db_path()) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute("SELECT * FROM runs ORDER BY last_run_ts DESC").fetchall()]
