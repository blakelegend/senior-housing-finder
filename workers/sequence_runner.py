"""
Sequence runner.

Walks the local CRM, finds every active lead with a touch due *today*,
renders the touch from the templates, and:

- For email touches: drops a draft into `outputs/drafts/<date>/<lead_id>.eml`
  (or, if `--send-via-gmail` is set, uses the Gmail API to create a draft in
  the user's mailbox — never auto-sends)

- For LinkedIn touches: writes a queue file `outputs/li_queue/<date>.csv`
  with one row per pending LI action plus a Sales Nav URL the user can open

- For call touches: writes a daily call sheet `outputs/calls/<date>.md`
  with the script pre-filled per lead

Why no auto-send: ESPs (Gmail, Outlook) penalize automated sending without
proper auth. LinkedIn bans accounts that auto-message. The reliable BD
pattern is **assisted, not automated** — generate, queue, and let the rep
review-and-send. This script gets you 95% of the way without the risk.
"""
import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ..config import CONFIG
from ..crm.pipeline import LeadPipeline, Stage
from ..outreach.sequence_engine import (
    Touch,
    TouchType,
    detect_persona,
    next_touch_for_lead,
    render_touch,
)
from ..outreach.sales_navigator import sales_nav_url


def _outputs(date: Optional[str] = None) -> Path:
    date = date or datetime.utcnow().strftime("%Y-%m-%d")
    base = CONFIG.output_dir / "outreach" / date
    (base / "drafts").mkdir(parents=True, exist_ok=True)
    (base / "li_queue").mkdir(parents=True, exist_ok=True)
    (base / "calls").mkdir(parents=True, exist_ok=True)
    return base


def _write_email_draft(out_dir: Path, lead: dict, rendered: dict) -> Path:
    to = lead.get("owner_email") or ""
    subj = rendered.get("subject", "")
    body = rendered.get("body", "")
    sender = f"{CONFIG.sender_name} <{CONFIG.sender_email}>" if CONFIG.sender_email else CONFIG.sender_name
    raw = (
        f"From: {sender}\n"
        f"To: {to}\n"
        f"Subject: {subj}\n"
        f"X-Lead-ID: {lead.get('id', '')}\n"
        f"X-Template: {rendered.get('template_used', '')}\n"
        "\n"
        f"{body}\n"
    )
    path = out_dir / "drafts" / f"{lead.get('id', 'unknown')}.eml"
    path.write_text(raw)
    return path


def _append_linkedin_row(out_dir: Path, lead: dict, rendered: dict, touch: Touch) -> None:
    path = out_dir / "li_queue" / "queue.csv"
    is_new = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow([
                "lead_id", "facility_name", "owner_name", "operator",
                "touch_type", "template", "message",
                "linkedin_profile", "sales_nav_search", "due_date",
            ])
        w.writerow([
            lead.get("id", ""),
            lead.get("facility_name", ""),
            lead.get("owner_name", ""),
            lead.get("primary_owner", ""),
            touch.type.value,
            rendered.get("template_used", ""),
            rendered.get("body", "").replace("\n", "  "),
            lead.get("owner_linkedin", ""),
            sales_nav_url(lead.get("primary_owner") or lead.get("facility_name", ""), geography=lead.get("state")),
            datetime.utcnow().date().isoformat(),
        ])


def _append_call_sheet(out_dir: Path, lead: dict, rendered: dict) -> None:
    path = out_dir / "calls" / "callsheet.md"
    with path.open("a") as f:
        f.write(f"\n\n## {lead.get('facility_name', '')} — {lead.get('owner_name') or lead.get('primary_owner', '')}\n")
        f.write(f"- Phone: {lead.get('owner_phone', '') or 'unknown'}\n")
        f.write(f"- City/State: {lead.get('city', '')}, {lead.get('state', '')}\n")
        f.write(f"- Priority: {lead.get('priority')} | Selling-likelihood: {lead.get('selling_likelihood')}\n")
        f.write(f"- Lead ID: `{lead.get('id', '')}`\n\n")
        f.write("```\n")
        f.write(rendered.get("body", ""))
        f.write("\n```\n")


def run_once(batch_size: int = 100, dry_run: bool = False) -> dict:
    """Process one batch of due touches; return a summary dict."""
    pipeline = LeadPipeline()
    out_dir = _outputs()
    summary = {"emails": 0, "linkedin": 0, "calls": 0, "skipped": 0}

    leads = pipeline.leads_needing_touch(batch_size=batch_size)
    for lead in leads:
        # Default sequence to persona if unset
        if not lead.get("sequence"):
            lead["sequence"] = detect_persona(lead)
            with pipeline._conn() as c:
                c.execute("UPDATE leads SET sequence = ? WHERE id = ?", (lead["sequence"], lead["id"]))

        touch = next_touch_for_lead(lead)
        if not touch:
            summary["skipped"] += 1
            continue

        rendered = render_touch(lead, touch)
        if not rendered:
            summary["skipped"] += 1
            continue

        if touch.type == TouchType.EMAIL:
            _write_email_draft(out_dir, lead, rendered)
            summary["emails"] += 1
        elif touch.type in (TouchType.LINKEDIN_CONNECT, TouchType.LINKEDIN_MESSAGE):
            _append_linkedin_row(out_dir, lead, rendered, touch)
            summary["linkedin"] += 1
        elif touch.type == TouchType.CALL:
            _append_call_sheet(out_dir, lead, rendered)
            summary["calls"] += 1

        if not dry_run:
            pipeline.mark_touch_sent(lead["id"], touch.name, rendered.get("template_used", ""))
            # Move to ENGAGED on first touch
            if lead.get("stage") == Stage.NEW.value:
                pipeline.move_stage(lead["id"], Stage.ENGAGED, note=f"first touch: {touch.name}")

    summary["output_dir"] = str(out_dir)
    return summary


def _cli():
    p = argparse.ArgumentParser()
    p.add_argument("--batch", type=int, default=100)
    p.add_argument("--dry-run", action="store_true",
                   help="Render outputs but don't mark touches as sent in the CRM")
    args = p.parse_args()
    result = run_once(batch_size=args.batch, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
