"""
Sequence engine.

A `Sequence` is a list of `Touch` objects, each with a touch type (EMAIL,
LINKEDIN_CONNECT, LINKEDIN_MESSAGE, CALL), a day-offset from sequence start,
a template key, and optional conditions (e.g. "skip if lead replied").

The engine is intentionally simple — it computes the *next* touch given a
lead's history. It doesn't send anything itself; the actual sending is done
by your existing tooling (Outreach.io, Salesloft, manual, etc.) so we stay
on the right side of every ESP's anti-automation policy.

What this module gives you:
1. Three pre-built sequences keyed by persona
2. `next_touch_for_lead()` → returns the next touch due (or None)
3. `render_touch()` → fills the Jinja template with lead + sender data
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Dict, List, Optional

from jinja2 import Environment, BaseLoader, StrictUndefined, UndefinedError

from ..config import CONFIG
from .call_scripts import CALL_SCRIPTS
from .email_templates import EMAIL_TEMPLATES
from .linkedin_templates import LINKEDIN_TEMPLATES


_jinja = Environment(loader=BaseLoader(), undefined=StrictUndefined)


class TouchType(str, Enum):
    EMAIL = "email"
    LINKEDIN_CONNECT = "linkedin_connect"
    LINKEDIN_MESSAGE = "linkedin_message"
    CALL = "call"
    MANUAL = "manual"


@dataclass
class Touch:
    name: str                                # e.g. "email_1_intro"
    type: TouchType
    day_offset: int                          # days from sequence_start_date
    template_key: str                        # key into the template dict
    skip_if: Optional[Callable[[dict], bool]] = None  # e.g. lambda l: l["replied"]


@dataclass
class Sequence:
    name: str
    persona: str                             # 'founder_owner', etc.
    touches: List[Touch] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Skip conditions
# ---------------------------------------------------------------------------

def _replied(lead: dict) -> bool:
    return bool(lead.get("replied_at"))


def _booked_meeting(lead: dict) -> bool:
    return bool(lead.get("meeting_booked_at"))


def _opted_out(lead: dict) -> bool:
    return bool(lead.get("opted_out_at"))


def _terminal(lead: dict) -> bool:
    return _replied(lead) or _booked_meeting(lead) or _opted_out(lead)


# ---------------------------------------------------------------------------
# Pre-built sequences (tuned for senior housing)
# ---------------------------------------------------------------------------

FOUNDER_SEQUENCE = Sequence(
    name="founder_owner_v1",
    persona="founder_owner",
    touches=[
        Touch("email_1_intro",           TouchType.EMAIL,            0,  "email_1_intro",        _terminal),
        Touch("li_connect",              TouchType.LINKEDIN_CONNECT, 1,  "connection_request",   _terminal),
        Touch("email_2_value",           TouchType.EMAIL,            5,  "email_2_value",        _terminal),
        Touch("call_1",                  TouchType.CALL,             8,  "discovery_call",       _terminal),
        Touch("li_followup",             TouchType.LINKEDIN_MESSAGE, 11, "post_connect_followup", _terminal),
        Touch("email_3_specific",        TouchType.EMAIL,            15, "email_3_specific",     _terminal),
        Touch("call_2_voicemail",        TouchType.CALL,             21, "voicemail",            _terminal),
        Touch("email_4_breakup",         TouchType.EMAIL,            30, "email_4_breakup",      _terminal),
    ],
)


CORPORATE_SEQUENCE = Sequence(
    name="corporate_owner_v1",
    persona="corporate_owner",
    touches=[
        Touch("email_1_intro",       TouchType.EMAIL,            0,  "email_1_intro",       _terminal),
        Touch("li_connect",          TouchType.LINKEDIN_CONNECT, 1,  "connection_request",  _terminal),
        Touch("call_1_voicemail",    TouchType.CALL,             4,  "voicemail",           _terminal),
        Touch("email_2_tear_sheet",  TouchType.EMAIL,            7,  "email_2_tear_sheet",  _terminal),
        Touch("li_inmail",           TouchType.LINKEDIN_MESSAGE, 10, "inmail_intro",        _terminal),
        Touch("email_3_specific",    TouchType.EMAIL,            14, "email_3_specific",    _terminal),
        Touch("email_4_breakup",     TouchType.EMAIL,            24, "email_4_breakup",     _terminal),
    ],
)


PE_REIT_SEQUENCE = Sequence(
    name="pe_reit_owner_v1",
    persona="pe_reit_owner",
    touches=[
        Touch("email_1_intro",     TouchType.EMAIL,            0,  "email_1_intro",     _terminal),
        Touch("li_connect",        TouchType.LINKEDIN_CONNECT, 1,  "connection_request", _terminal),
        Touch("email_2_followup",  TouchType.EMAIL,            10, "email_2_followup",  _terminal),
        Touch("email_3_breakup",   TouchType.EMAIL,            21, "email_3_breakup",   _terminal),
    ],
)


SEQUENCES: Dict[str, Sequence] = {
    "founder_owner":   FOUNDER_SEQUENCE,
    "corporate_owner": CORPORATE_SEQUENCE,
    "pe_reit_owner":   PE_REIT_SEQUENCE,
}


# ---------------------------------------------------------------------------
# Persona detection — map a lead to one of the three sequences
# ---------------------------------------------------------------------------

def detect_persona(lead: dict) -> str:
    """Heuristic: pick the sequence that best matches the lead."""
    owners = (lead.get("all_owners") or "").lower()
    ot = (lead.get("ownership_type") or "").lower()

    institutional = [
        "ventas", "welltower", "omega", "sabra", "ltc properties",
        "caretrust", "national health investors", "diversified healthcare",
        "blackstone", "kkr", "carlyle", "apollo", "harrison street",
    ]
    if any(name in owners for name in institutional):
        return "pe_reit_owner"

    # PE-backed signal: mid-size LLC with high employee count
    if "limited liability company" in ot:
        try:
            n = int(lead.get("operator_employee_count") or 0)
            if n >= 200:
                return "pe_reit_owner"
        except Exception:
            pass

    # Family owned indicator from selling-likelihood model
    if lead.get("sell_family_owned") and float(lead.get("sell_family_owned", 0)) > 0.5:
        return "founder_owner"

    if "for profit - individual" in ot or "for profit - partnership" in ot:
        return "founder_owner"

    return "corporate_owner"


# ---------------------------------------------------------------------------
# Next-touch logic
# ---------------------------------------------------------------------------

def next_touch_for_lead(lead: dict, now: Optional[datetime] = None) -> Optional[Touch]:
    """
    Return the next due Touch for a lead, or None if the sequence is done or
    the lead is in a terminal state (replied / booked / opted out).
    """
    if _terminal(lead):
        return None

    sequence_name = lead.get("sequence") or detect_persona(lead)
    sequence = SEQUENCES.get(sequence_name)
    if not sequence:
        return None

    start_raw = lead.get("sequence_started_at")
    if not start_raw:
        return sequence.touches[0]
    start = start_raw if isinstance(start_raw, datetime) else datetime.fromisoformat(str(start_raw))
    now = now or datetime.utcnow()
    completed = set((lead.get("touches_sent") or "").split(",")) if lead.get("touches_sent") else set()

    for touch in sequence.touches:
        if touch.name in completed:
            continue
        due = start + timedelta(days=touch.day_offset)
        if now >= due:
            if touch.skip_if and touch.skip_if(lead):
                continue
            return touch
    return None


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

def _template_pool(touch: Touch, persona: str) -> dict:
    if touch.type == TouchType.EMAIL:
        return EMAIL_TEMPLATES.get(persona, {})
    if touch.type in (TouchType.LINKEDIN_CONNECT, TouchType.LINKEDIN_MESSAGE):
        return LINKEDIN_TEMPLATES
    if touch.type == TouchType.CALL:
        return CALL_SCRIPTS
    return {}


def _vars_for_lead(lead: dict) -> dict:
    """Build the Jinja variable dict from lead + sender CONFIG."""
    first_name = (lead.get("owner_name") or "").split()[0] if lead.get("owner_name") else "there"
    return {
        "first_name": first_name,
        "facility_name": lead.get("name") or "your community",
        "operator_name": lead.get("primary_owner") or lead.get("legal_owner") or lead.get("name"),
        "market": lead.get("city") or "your",
        "region": lead.get("state") or "your region",
        "tenure_clause": _tenure_phrase(lead),
        "beds_clause": _beds_phrase(lead),
        "beds_segment": _beds_bucket(lead),
        "beds_range": _beds_bucket(lead),
        "specific_observation": lead.get("specific_observation") or "the operating profile",
        "rating_observation": lead.get("rating_observation") or "the quality scores",
        "comp_description": lead.get("comp_description") or "a similarly-sized property",
        "comp_price_per_unit": lead.get("comp_price_per_unit") or "$220,000",
        "comp_market": lead.get("comp_market") or "your market",
        "market_occupancy": lead.get("market_occupancy") or "85",
        "cap_rate_range": lead.get("cap_rate_range") or "7.0–8.5%",
        "property_segment": lead.get("property_segment") or "assisted living and memory care",
        "recent_close_count": lead.get("recent_close_count") or "11",
        "median_close_days": lead.get("median_close_days") or "67",
        "state_list": lead.get("state_list") or "the Southeast",
        "aum": lead.get("aum") or "$450M",
        "phone_dialed": lead.get("phone_e164") or lead.get("phone") or "your number",
        # Sender block
        "sender_name": CONFIG.sender_name or "[Your Name]",
        "sender_first_name": (CONFIG.sender_name or "[Your Name]").split()[0],
        "sender_title": CONFIG.sender_title,
        "sender_firm": CONFIG.sender_firm,
        "sender_email": CONFIG.sender_email or "[your email]",
        "sender_phone": CONFIG.sender_phone or "[your phone]",
        "sender_calendar_link": CONFIG.sender_calendar_link or "[your booking link]",
    }


def _beds_bucket(lead: dict) -> str:
    try:
        n = int(float(lead.get("beds") or 0))
    except Exception:
        return "60-120"
    if n < 30:
        return "small"
    if n < 80:
        return "60-120"
    return "80-200"


def _beds_phrase(lead: dict) -> str:
    try:
        n = int(float(lead.get("beds") or 0))
    except Exception:
        return "a well-sized community"
    if n < 30:
        return f"a focused {n}-bed community"
    if n < 80:
        return f"a {n}-bed community right in our sweet spot"
    return f"a {n}-bed property"


def _tenure_phrase(lead: dict) -> str:
    cert = lead.get("oldest_association_date") or lead.get("cert_date")
    if not cert:
        return "you've clearly invested years in"
    try:
        year = int(str(cert)[:4])
        years = datetime.now().year - year
        return f"in operation for around {years} years under current ownership"
    except Exception:
        return "you've clearly invested years in"


def render_touch(lead: dict, touch: Optional[Touch] = None) -> Dict[str, str]:
    """
    Render the next-due touch for a lead. Returns a dict with keys:
      type, subject (if email/inmail), body, template_used
    """
    touch = touch or next_touch_for_lead(lead)
    if not touch:
        return {}

    persona = lead.get("sequence") or detect_persona(lead)
    pool = _template_pool(touch, persona)
    tpl = pool.get(touch.template_key, {})
    variables = _vars_for_lead(lead)

    if isinstance(tpl, dict):
        subj = tpl.get("subject", "")
        body = tpl.get("body", "")
    else:
        subj = ""
        body = tpl

    try:
        subj_rendered = _jinja.from_string(subj).render(**variables) if subj else ""
        body_rendered = _jinja.from_string(body).render(**variables) if body else ""
    except UndefinedError as e:
        # Surface missing variables clearly so we can add them to _vars_for_lead
        body_rendered = f"[TEMPLATE ERROR: {e}]\n\nRaw template:\n{body}"
        subj_rendered = subj

    return {
        "type": touch.type.value,
        "name": touch.name,
        "subject": subj_rendered,
        "body": body_rendered,
        "template_used": f"{persona}/{touch.template_key}",
    }
