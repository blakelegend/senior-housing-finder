"""
Local SQLite-backed CRM pipeline.

Schema (kept deliberately flat to make export to Airtable/Notion trivial):

    leads
    -----
    id (text, pk)               UUID generated at create-time
    facility_id (text)          ties back to your dataset (e.g. cms_id or addr key)
    facility_name (text)
    state (text)
    city (text)
    beds (int)
    primary_owner (text)
    owner_name (text)
    owner_title (text)
    owner_email (text)
    owner_phone (text)
    owner_linkedin (text)
    sequence (text)             persona/sequence id
    sequence_started_at (text)  ISO datetime
    stage (text)                Stage enum value
    priority (real)
    score_total (real)
    selling_likelihood (real)
    replied_at, meeting_booked_at, opted_out_at (text)
    touches_sent (text)         comma list of touch names already sent
    notes (text)
    created_at, updated_at (text)

    activities
    ----------
    id (text, pk)
    lead_id (text, fk)
    activity_type (text)        'email_sent', 'call', 'note', 'stage_change'
    detail (text)
    created_at (text)
"""
import json
import sqlite3
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd

from ..config import CONFIG


class Stage(str, Enum):
    NEW = "NEW"
    RESEARCHED = "RESEARCHED"
    ENGAGED = "ENGAGED"
    CONVERSATION = "CONVERSATION"
    DILIGENCE = "DILIGENCE"
    NEGOTIATION = "NEGOTIATION"
    CLOSED_WON = "CLOSED_WON"
    CLOSED_LOST = "CLOSED_LOST"


@dataclass
class Lead:
    facility_id: str = ""
    facility_name: str = ""
    state: str = ""
    city: str = ""
    beds: Optional[int] = None
    primary_owner: str = ""
    owner_name: str = ""
    owner_title: str = ""
    owner_email: str = ""
    owner_phone: str = ""
    owner_linkedin: str = ""
    sequence: str = ""
    sequence_started_at: Optional[str] = None
    stage: str = Stage.NEW.value
    priority: float = 0.0
    score_total: float = 0.0
    selling_likelihood: float = 0.0
    replied_at: Optional[str] = None
    meeting_booked_at: Optional[str] = None
    opted_out_at: Optional[str] = None
    touches_sent: str = ""
    notes: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class Activity:
    lead_id: str
    activity_type: str          # 'email_sent', 'call', 'note', 'stage_change'
    detail: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# ---------------------------------------------------------------------------

class LeadPipeline:
    """Local SQLite CRM. Constructor opens/creates the DB."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else CONFIG.output_dir / "crm.sqlite"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ---- schema -------------------------------------------------------
    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS leads (
                    id TEXT PRIMARY KEY,
                    facility_id TEXT,
                    facility_name TEXT,
                    state TEXT, city TEXT, beds INTEGER,
                    primary_owner TEXT,
                    owner_name TEXT, owner_title TEXT,
                    owner_email TEXT, owner_phone TEXT, owner_linkedin TEXT,
                    sequence TEXT, sequence_started_at TEXT,
                    stage TEXT, priority REAL,
                    score_total REAL, selling_likelihood REAL,
                    replied_at TEXT, meeting_booked_at TEXT, opted_out_at TEXT,
                    touches_sent TEXT, notes TEXT,
                    created_at TEXT, updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS activities (
                    id TEXT PRIMARY KEY,
                    lead_id TEXT,
                    activity_type TEXT,
                    detail TEXT,
                    created_at TEXT,
                    FOREIGN KEY (lead_id) REFERENCES leads(id)
                );
                CREATE INDEX IF NOT EXISTS ix_leads_stage ON leads(stage);
                CREATE INDEX IF NOT EXISTS ix_leads_priority ON leads(priority);
                CREATE INDEX IF NOT EXISTS ix_leads_facility ON leads(facility_id);
                CREATE INDEX IF NOT EXISTS ix_activities_lead ON activities(lead_id);
            """)

    # ---- CRUD ---------------------------------------------------------
    def upsert_lead(self, lead: Lead) -> str:
        lead.updated_at = datetime.utcnow().isoformat()
        with self._conn() as c:
            cur = c.cursor()
            cur.execute("SELECT id FROM leads WHERE facility_id = ?", (lead.facility_id,))
            row = cur.fetchone()
            if row:
                lead.id = row["id"]
                cur.execute(f"""
                    UPDATE leads SET {', '.join(f'{k}=?' for k in asdict(lead) if k != 'id')}
                    WHERE id = ?
                """, [*[v for k, v in asdict(lead).items() if k != "id"], lead.id])
            else:
                cur.execute(
                    f"INSERT INTO leads ({','.join(asdict(lead).keys())}) "
                    f"VALUES ({','.join('?' * len(asdict(lead)))})",
                    list(asdict(lead).values()),
                )
        return lead.id

    def bulk_import(self, df: pd.DataFrame, only_with_score: float = 50.0) -> int:
        """Import scored leads from a DataFrame; returns count inserted/updated."""
        if df.empty:
            return 0
        if "score_total" in df.columns and only_with_score is not None:
            df = df[df["score_total"] >= only_with_score]
        n = 0
        for _, r in df.iterrows():
            lead = Lead(
                facility_id=str(r.get("cms_id") or r.get("address") or r.get("name", "")),
                facility_name=str(r.get("name", "")),
                state=str(r.get("state", "") or ""),
                city=str(r.get("city", "") or ""),
                beds=int(r["beds"]) if pd.notna(r.get("beds")) else None,
                primary_owner=str(r.get("primary_owner") or r.get("legal_owner") or ""),
                owner_name=str(r.get("owner_name", "") or ""),
                owner_title=str(r.get("owner_title", "") or ""),
                owner_email=str(r.get("owner_email", "") or ""),
                owner_phone=str(r.get("phone_e164") or r.get("phone", "") or ""),
                owner_linkedin=str(r.get("owner_linkedin", "") or ""),
                priority=float(r.get("priority") or r.get("score_total") or 0),
                score_total=float(r.get("score_total") or 0),
                selling_likelihood=float(r.get("selling_likelihood") or 0),
                stage=Stage.NEW.value,
            )
            self.upsert_lead(lead)
            n += 1
        return n

    def get_lead(self, lead_id: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
            return dict(row) if row else None

    def list_leads(self, stage: Optional[Stage] = None, limit: int = 500) -> List[dict]:
        with self._conn() as c:
            if stage:
                rows = c.execute(
                    "SELECT * FROM leads WHERE stage = ? ORDER BY priority DESC LIMIT ?",
                    (stage.value, limit),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM leads ORDER BY priority DESC LIMIT ?", (limit,)
                ).fetchall()
            return [dict(r) for r in rows]

    # ---- stage / state transitions -----------------------------------
    def move_stage(self, lead_id: str, new_stage: Stage, note: str = "") -> None:
        with self._conn() as c:
            old = c.execute("SELECT stage FROM leads WHERE id = ?", (lead_id,)).fetchone()
            old_stage = old["stage"] if old else "?"
            c.execute(
                "UPDATE leads SET stage = ?, updated_at = ? WHERE id = ?",
                (new_stage.value, datetime.utcnow().isoformat(), lead_id),
            )
        self.log_activity(Activity(
            lead_id=lead_id,
            activity_type="stage_change",
            detail=json.dumps({"from": old_stage, "to": new_stage.value, "note": note}),
        ))

    def mark_touch_sent(self, lead_id: str, touch_name: str, detail: str = "") -> None:
        with self._conn() as c:
            row = c.execute("SELECT touches_sent, sequence_started_at FROM leads WHERE id = ?", (lead_id,)).fetchone()
            sent = (row["touches_sent"] or "").split(",") if row and row["touches_sent"] else []
            sent.append(touch_name)
            started = row["sequence_started_at"] if row and row["sequence_started_at"] else datetime.utcnow().isoformat()
            c.execute(
                "UPDATE leads SET touches_sent = ?, sequence_started_at = ?, updated_at = ? WHERE id = ?",
                (",".join(s for s in sent if s), started, datetime.utcnow().isoformat(), lead_id),
            )
        self.log_activity(Activity(lead_id=lead_id, activity_type="touch_sent", detail=f"{touch_name}: {detail}"))

    def mark_replied(self, lead_id: str, note: str = "") -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE leads SET replied_at = ?, updated_at = ?, stage = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), datetime.utcnow().isoformat(),
                 Stage.CONVERSATION.value, lead_id),
            )
        self.log_activity(Activity(lead_id=lead_id, activity_type="reply", detail=note))

    def mark_opted_out(self, lead_id: str, note: str = "") -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE leads SET opted_out_at = ?, updated_at = ?, stage = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), datetime.utcnow().isoformat(),
                 Stage.CLOSED_LOST.value, lead_id),
            )
        self.log_activity(Activity(lead_id=lead_id, activity_type="opt_out", detail=note))

    def log_activity(self, activity: Activity) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO activities (id, lead_id, activity_type, detail, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (activity.id, activity.lead_id, activity.activity_type, activity.detail, activity.created_at),
            )

    # ---- reporting ----------------------------------------------------
    def stage_counts(self) -> dict:
        with self._conn() as c:
            rows = c.execute("SELECT stage, COUNT(*) as n FROM leads GROUP BY stage").fetchall()
            return {r["stage"]: r["n"] for r in rows}

    def leads_needing_touch(self, batch_size: int = 100) -> List[dict]:
        """Active leads not in a terminal state, ordered by priority."""
        with self._conn() as c:
            rows = c.execute(
                """
                SELECT * FROM leads
                WHERE stage NOT IN (?, ?)
                  AND opted_out_at IS NULL
                ORDER BY priority DESC
                LIMIT ?
                """,
                (Stage.CLOSED_WON.value, Stage.CLOSED_LOST.value, batch_size),
            ).fetchall()
            return [dict(r) for r in rows]
