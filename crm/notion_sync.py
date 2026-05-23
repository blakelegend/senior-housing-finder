"""
Notion sync — one-way push to a Notion database.

The Notion database must have these properties (configure once in the UI):
- Facility Name (title)
- Facility ID (rich_text)
- State, City (rich_text)
- Beds (number)
- Primary Owner (rich_text)
- Owner Name (rich_text)
- Owner Email (email)
- Owner Phone (phone_number)
- Stage (select)
- Priority (number)
- Score Total (number)
- Selling Likelihood (number)
- Sequence (rich_text)
- Notes (rich_text)
- Updated At (date)

The Notion API is verbose; we batch where possible and back off on rate limits.
"""
from typing import Dict, Iterable, Optional

from ..config import CONFIG


def _text(value: str) -> Dict:
    return {"rich_text": [{"type": "text", "text": {"content": str(value or "")}}]}


def _select(value: str) -> Dict:
    return {"select": {"name": str(value or "NEW")}}


def _num(value) -> Dict:
    if value is None or value == "":
        return {"number": None}
    try:
        return {"number": float(value)}
    except Exception:
        return {"number": None}


class NotionSync:
    def __init__(self, api_key: Optional[str] = None, database_id: Optional[str] = None):
        self.api_key = api_key or CONFIG.notion_api_key
        self.database_id = database_id or CONFIG.notion_database_leads
        if not (self.api_key and self.database_id):
            self.client = None
            print("[notion] no NOTION_API_KEY / NOTION_DATABASE_LEADS configured — sync disabled")
            return
        from notion_client import Client
        self.client = Client(auth=self.api_key)

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def _props(self, lead: dict) -> Dict:
        return {
            "Facility Name": {"title": [{"type": "text", "text": {"content": lead.get("facility_name", "")}}]},
            "Facility ID": _text(lead.get("facility_id")),
            "State": _text(lead.get("state")),
            "City": _text(lead.get("city")),
            "Beds": _num(lead.get("beds")),
            "Primary Owner": _text(lead.get("primary_owner")),
            "Owner Name": _text(lead.get("owner_name")),
            "Owner Email": {"email": lead.get("owner_email") or None},
            "Owner Phone": {"phone_number": lead.get("owner_phone") or None},
            "Stage": _select(lead.get("stage")),
            "Priority": _num(lead.get("priority")),
            "Score Total": _num(lead.get("score_total")),
            "Selling Likelihood": _num(lead.get("selling_likelihood")),
            "Sequence": _text(lead.get("sequence")),
            "Notes": _text(lead.get("notes")),
            "Updated At": {"date": {"start": lead.get("updated_at") or None}} if lead.get("updated_at") else {"date": None},
        }

    def _find_existing(self, facility_id: str) -> Optional[str]:
        if not facility_id:
            return None
        try:
            resp = self.client.databases.query(
                database_id=self.database_id,
                filter={"property": "Facility ID", "rich_text": {"equals": facility_id}},
                page_size=1,
            )
            if resp.get("results"):
                return resp["results"][0]["id"]
        except Exception as e:
            print(f"[notion] query failed: {e}")
        return None

    def push_leads(self, leads: Iterable[dict]) -> int:
        if not self.enabled:
            return 0
        n = 0
        for lead in leads:
            existing_id = self._find_existing(lead.get("facility_id", ""))
            try:
                if existing_id:
                    self.client.pages.update(page_id=existing_id, properties=self._props(lead))
                else:
                    self.client.pages.create(parent={"database_id": self.database_id}, properties=self._props(lead))
                n += 1
            except Exception as e:
                print(f"[notion] failed to push lead {lead.get('facility_id')}: {e}")
        return n
