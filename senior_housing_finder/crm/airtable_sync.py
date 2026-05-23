"""
Airtable sync — one-way push from local CRM → Airtable.

Why one-way: avoids field-level conflict resolution. The local SQLite is the
source of truth; Airtable is the team's visualization & note-taking surface.
If you need bi-directional sync, build a poller around `Lead.updated_at`.

Required base setup in Airtable:
- Base with two tables: "Leads" and "Activities"
- "Leads" needs at minimum these fields (single-line text unless noted):
    facility_id, facility_name, state, city, beds (number),
    primary_owner, owner_name, owner_title, owner_email, owner_phone,
    sequence, stage (single-select with stage values),
    priority (number), score_total (number), selling_likelihood (number),
    notes (long text), updated_at (date)
- "Activities" needs:
    lead_id (link to Leads), activity_type, detail (long text), created_at (date)
"""
from typing import Dict, Iterable, List, Optional

from ..config import CONFIG


class AirtableSync:
    def __init__(self, api_key: Optional[str] = None, base_id: Optional[str] = None):
        self.api_key = api_key or CONFIG.airtable_api_key
        self.base_id = base_id or CONFIG.airtable_base_id
        if not (self.api_key and self.base_id):
            self.client = None
            print("[airtable] no AIRTABLE_API_KEY / AIRTABLE_BASE_ID configured — sync disabled")
            return
        # Import here so module is importable without pyairtable installed
        from pyairtable import Api
        api = Api(self.api_key)
        self.leads_table = api.table(self.base_id, CONFIG.airtable_table_leads)
        self.activities_table = api.table(self.base_id, CONFIG.airtable_table_activities)

    @property
    def enabled(self) -> bool:
        return getattr(self, "leads_table", None) is not None

    def _lead_to_fields(self, lead: dict) -> Dict:
        """Map local lead row to Airtable field dict (only fields we want to push)."""
        return {
            "facility_id": lead.get("facility_id", ""),
            "facility_name": lead.get("facility_name", ""),
            "state": lead.get("state", ""),
            "city": lead.get("city", ""),
            "beds": lead.get("beds"),
            "primary_owner": lead.get("primary_owner", ""),
            "owner_name": lead.get("owner_name", ""),
            "owner_title": lead.get("owner_title", ""),
            "owner_email": lead.get("owner_email", ""),
            "owner_phone": lead.get("owner_phone", ""),
            "sequence": lead.get("sequence", ""),
            "stage": lead.get("stage", ""),
            "priority": lead.get("priority"),
            "score_total": lead.get("score_total"),
            "selling_likelihood": lead.get("selling_likelihood"),
            "notes": lead.get("notes", ""),
            "updated_at": lead.get("updated_at", ""),
        }

    def push_leads(self, leads: Iterable[dict]) -> int:
        """Upsert each lead by `facility_id`. Returns count synced."""
        if not self.enabled:
            return 0
        n = 0
        # Build a lookup of existing records by facility_id (one read instead of per-row)
        existing = {r["fields"].get("facility_id"): r["id"] for r in self.leads_table.all(fields=["facility_id"])}
        for lead in leads:
            fid = lead.get("facility_id", "")
            fields = self._lead_to_fields(lead)
            try:
                if fid in existing:
                    self.leads_table.update(existing[fid], fields, typecast=True)
                else:
                    self.leads_table.create(fields, typecast=True)
                n += 1
            except Exception as e:
                print(f"[airtable] failed to push lead {fid}: {e}")
        return n

    def push_activity(self, activity: dict, lead_airtable_id: Optional[str] = None) -> Optional[str]:
        """Append an activity row. `lead_airtable_id` should be the Airtable record id."""
        if not self.enabled:
            return None
        try:
            rec = self.activities_table.create({
                "lead_id": [lead_airtable_id] if lead_airtable_id else [],
                "activity_type": activity.get("activity_type", ""),
                "detail": activity.get("detail", ""),
                "created_at": activity.get("created_at", ""),
            }, typecast=True)
            return rec["id"]
        except Exception as e:
            print(f"[airtable] failed to push activity: {e}")
            return None
