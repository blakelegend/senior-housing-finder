"""
Direct mail letter generation.

Two output paths:
1. **PDF batch** — generate one PDF per lead suitable for printing in-house
   or feeding to a print-and-mail vendor (Click2Mail, PostGrid)
2. **Lob API** — send the letter directly via Lob's API (handles printing,
   addressing, USPS Certified options, return-address rendering)

Letter templates are tuned for senior housing acquisitions:
- `tired_owner`   — leads with distress signals (poor reviews, fines)
- `tenure_owner`  — long-tenured family/independent owners
- `tax_distress`  — owners with recent liens or tax delinquency

We send to the owner's **mailing address** from the assessor data, NOT to
the facility — that's how you actually reach the principal, not the
facility's admin desk.
"""
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from jinja2 import Environment, BaseLoader, StrictUndefined

from ..config import CONFIG

_jinja = Environment(loader=BaseLoader(), undefined=StrictUndefined)


# ---------------------------------------------------------------------------
# Letter templates
# ---------------------------------------------------------------------------

TIRED_OWNER_LETTER = """{{ today }}

{{ owner_name or "Property Owner" }}
{{ owner_mailing_address }}
{{ owner_mailing_city }}, {{ owner_mailing_state }} {{ owner_mailing_zip }}

Re: {{ facility_name }}, {{ facility_city }}, {{ facility_state }}

Dear {{ owner_first_name or "Property Owner" }},

I'm writing to you directly — not through a broker — about {{ facility_name }}.

We are a private capital group based in {{ sender_city }} that acquires senior housing
properties from owners who built the business and are looking to transition. We close
in cash, in 60-90 days, with full confidentiality. No broker fees, no MLS listing,
no signs in the yard.

I understand running a senior community has gotten harder over the last few years.
Staffing pressure, regulatory burden, insurance costs — all of it. If you've started
thinking about what comes next for {{ facility_name }}, I'd welcome a confidential
conversation. No expectation, no pressure.

If timing isn't right, please keep my contact information for when it is.

Sincerely,

{{ sender_name }}
{{ sender_title }}
{{ sender_firm }}
{{ sender_phone }}  |  {{ sender_email }}
"""


TENURE_OWNER_LETTER = """{{ today }}

{{ owner_name or "Property Owner" }}
{{ owner_mailing_address }}
{{ owner_mailing_city }}, {{ owner_mailing_state }} {{ owner_mailing_zip }}

Re: {{ facility_name }}, {{ facility_city }}, {{ facility_state }}

Dear {{ owner_first_name or "Property Owner" }},

Public records suggest you've owned {{ facility_name }} for about {{ ownership_years }}
years. That's a lot of nights you didn't sleep, a lot of staff you hired, a lot of
families you served.

We are a private group that acquires senior living communities from long-tenured
owners on terms that protect what they built. Specifically:

  - Cash close, no financing contingency
  - Existing staff retained where possible
  - Resident continuity is non-negotiable for us
  - 60-90 days from handshake to wire

I'm not asking for a meeting today. I'm asking that you keep this letter — and my
number — somewhere accessible. When the time comes to think about transition (this
year, next year, five years from now), I would value a confidential conversation.

With respect for what you've built,

{{ sender_name }}
{{ sender_title }}
{{ sender_firm }}
{{ sender_phone }}  |  {{ sender_email }}
"""


TAX_DISTRESS_LETTER = """{{ today }}

{{ owner_name or "Property Owner" }}
{{ owner_mailing_address }}
{{ owner_mailing_city }}, {{ owner_mailing_state }} {{ owner_mailing_zip }}

Re: {{ facility_name }}, {{ facility_city }}, {{ facility_state }}

Dear {{ owner_first_name or "Property Owner" }},

I'm writing privately about {{ facility_name }}. Our group reviews public records on
senior housing properties throughout the country, and occasionally we see signals that
suggest an owner may benefit from a fast, confidential conversation.

We acquire senior living properties off-market with cash, no broker, no public listing.
For owners facing tax, lien, or cash-flow pressure, we can usually move from initial
call to LOI in two weeks and close in 60 days or less. We don't need bank approval,
and we don't require you to clean anything up first.

If any of this might be useful — even just to talk through what a property like
{{ facility_name }} could be worth in this market — please call me directly.

This letter is confidential. You'll never hear from me again unless you reach out.

{{ sender_name }}
{{ sender_title }}
{{ sender_firm }}
{{ sender_phone }}  |  {{ sender_email }}
"""


TEMPLATES = {
    "tired_owner":  TIRED_OWNER_LETTER,
    "tenure_owner": TENURE_OWNER_LETTER,
    "tax_distress": TAX_DISTRESS_LETTER,
}


# ---------------------------------------------------------------------------
# Letter selection
# ---------------------------------------------------------------------------

def pick_letter_template(lead: dict) -> str:
    """Choose the best-fit template given the lead's signal mix."""
    if lead.get("lien_count", 0) and lead["lien_count"] > 0:
        return "tax_distress"
    if (lead.get("tired_owner_score") or 0) >= 50:
        return "tired_owner"
    # Default to tenure for long-held independent owners
    return "tenure_owner"


def _vars_for_letter(lead: dict) -> Dict[str, str]:
    owner_name = lead.get("owner_name") or lead.get("skip_traced_name") or ""
    owner_first = owner_name.split()[0] if owner_name else ""
    return {
        "today":                  datetime.now().strftime("%B %d, %Y"),
        "owner_name":             owner_name,
        "owner_first_name":       owner_first,
        "owner_mailing_address":  lead.get("owner_mailing_address") or lead.get("address") or "",
        "owner_mailing_city":     lead.get("owner_mailing_city") or lead.get("city") or "",
        "owner_mailing_state":    lead.get("owner_mailing_state") or lead.get("state") or "",
        "owner_mailing_zip":      lead.get("owner_mailing_zip") or str(lead.get("zip") or ""),
        "facility_name":          lead.get("facility_name") or lead.get("name", ""),
        "facility_city":          lead.get("city", ""),
        "facility_state":         lead.get("state", ""),
        "ownership_years":        _ownership_years(lead),
        "sender_name":            CONFIG.sender_name or "[Your Name]",
        "sender_title":           CONFIG.sender_title,
        "sender_firm":            CONFIG.sender_firm,
        "sender_phone":           CONFIG.sender_phone or "[your phone]",
        "sender_email":           CONFIG.sender_email or "[your email]",
        "sender_city":            CONFIG.return_address.get("city") or "the United States",
    }


def _ownership_years(lead: dict) -> str:
    raw = lead.get("oldest_association_date") or lead.get("cert_date") or lead.get("last_sale_date")
    if not raw:
        return "many"
    try:
        year = int(str(raw)[:4])
        return str(datetime.now().year - year)
    except Exception:
        return "many"


def render_letter(lead: dict, template_key: Optional[str] = None) -> Dict[str, str]:
    template_key = template_key or pick_letter_template(lead)
    tpl = TEMPLATES[template_key]
    body = _jinja.from_string(tpl).render(**_vars_for_letter(lead))
    return {"template": template_key, "body": body}


# ---------------------------------------------------------------------------
# PDF output (reportlab)
# ---------------------------------------------------------------------------

def write_pdf_batch(
    leads: Iterable[dict],
    out_dir: Optional[Path] = None,
) -> Path:
    """Write one PDF per lead into out_dir/letters_<date>/."""
    try:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas
    except ImportError:
        raise ImportError("reportlab not installed — run pip install reportlab")

    out_dir = out_dir or (CONFIG.output_dir / f"letters_{datetime.now().strftime('%Y%m%d')}")
    out_dir.mkdir(parents=True, exist_ok=True)

    for lead in leads:
        rendered = render_letter(lead)
        path = out_dir / f"{(lead.get('facility_id') or lead.get('id') or 'lead')}.pdf"
        c = canvas.Canvas(str(path), pagesize=LETTER)
        textobject = c.beginText(1 * inch, 10 * inch)
        textobject.setFont("Times-Roman", 11)
        for line in rendered["body"].splitlines():
            textobject.textLine(line)
        c.drawText(textobject)
        c.showPage()
        c.save()

    return out_dir


# ---------------------------------------------------------------------------
# Lob API
# ---------------------------------------------------------------------------

def send_via_lob(
    leads: Iterable[dict],
    color: bool = False,
    double_sided: bool = False,
) -> List[Dict]:
    """Send letters via Lob. Returns list of Lob response dicts."""
    if not CONFIG.lob_api_key:
        print("[direct_mail] LOB_API_KEY not configured — skipping")
        return []
    try:
        import lob
    except ImportError:
        raise ImportError("lob SDK not installed — run pip install lob")

    lob.api_key = CONFIG.lob_api_key
    ra = CONFIG.return_address
    if not ra.get("street"):
        print("[direct_mail] return address not configured — required by USPS")
        return []

    from_address = lob.Address.create(
        name=ra.get("name", CONFIG.sender_firm),
        address_line1=ra["street"],
        address_city=ra["city"],
        address_state=ra["state"],
        address_zip=ra["zip"],
        address_country="US",
    )

    responses = []
    for lead in leads:
        if not lead.get("owner_mailing_address"):
            continue
        rendered = render_letter(lead)
        try:
            resp = lob.Letter.create(
                description=f"{lead.get('facility_name', '')} — {rendered['template']}",
                to_address={
                    "name": lead.get("owner_name") or "Property Owner",
                    "address_line1": lead["owner_mailing_address"],
                    "address_city": lead.get("owner_mailing_city") or lead.get("city", ""),
                    "address_state": lead.get("owner_mailing_state") or lead.get("state", ""),
                    "address_zip": lead.get("owner_mailing_zip") or str(lead.get("zip") or ""),
                },
                from_address=from_address["id"],
                file=f"<html><body><pre>{rendered['body']}</pre></body></html>",
                color=color,
                double_sided=double_sided,
            )
            responses.append(resp)
        except Exception as e:
            print(f"[direct_mail] lob send failed for {lead.get('facility_name')}: {e}")
    return responses


# ---------------------------------------------------------------------------
# Click2Mail / PostGrid CSV export
# ---------------------------------------------------------------------------

def export_mail_csv(leads: Iterable[dict], path: Optional[Path] = None) -> Path:
    """
    Vendor-agnostic CSV of (mailing address + letter body) for upload to
    Click2Mail / PostGrid / any print-and-mail service.
    """
    path = path or (CONFIG.output_dir / f"mail_batch_{datetime.now().strftime('%Y%m%d')}.csv")
    fields = [
        "facility_id", "facility_name",
        "to_name", "to_address", "to_city", "to_state", "to_zip",
        "letter_template", "letter_body",
    ]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for lead in leads:
            rendered = render_letter(lead)
            w.writerow({
                "facility_id":      lead.get("facility_id") or lead.get("id", ""),
                "facility_name":    lead.get("facility_name") or lead.get("name", ""),
                "to_name":          lead.get("owner_name") or "Property Owner",
                "to_address":       lead.get("owner_mailing_address", ""),
                "to_city":          lead.get("owner_mailing_city") or lead.get("city", ""),
                "to_state":         lead.get("owner_mailing_state") or lead.get("state", ""),
                "to_zip":           lead.get("owner_mailing_zip") or str(lead.get("zip") or ""),
                "letter_template":  rendered["template"],
                "letter_body":      rendered["body"],
            })
    return path
