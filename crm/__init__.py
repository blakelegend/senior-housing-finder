"""
CRM-style pipeline.

Local-first (SQLite) with optional sync to Airtable or Notion. The local DB
is the source of truth; remote sync is one-way (push) by default to avoid
conflict resolution headaches.

Stages (in order):
    NEW → RESEARCHED → ENGAGED → CONVERSATION → DILIGENCE → NEGOTIATION → CLOSED_WON / CLOSED_LOST
"""
from .pipeline import (
    LeadPipeline,
    Stage,
    Lead,
    Activity,
)
from .airtable_sync import AirtableSync
from .notion_sync import NotionSync

__all__ = [
    "LeadPipeline",
    "Stage",
    "Lead",
    "Activity",
    "AirtableSync",
    "NotionSync",
]
