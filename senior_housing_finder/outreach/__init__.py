"""Multi-touch outreach: email + LinkedIn + call sequences."""
from .sequence_engine import (
    Sequence,
    Touch,
    TouchType,
    SEQUENCES,
    next_touch_for_lead,
    render_touch,
)
from .sales_navigator import sales_nav_url, linkedin_search_url
from .email_templates import EMAIL_TEMPLATES
from .linkedin_templates import LINKEDIN_TEMPLATES
from .call_scripts import CALL_SCRIPTS
from .direct_mail import (
    render_letter,
    pick_letter_template,
    write_pdf_batch,
    send_via_lob,
    export_mail_csv,
)

__all__ = [
    "Sequence",
    "Touch",
    "TouchType",
    "SEQUENCES",
    "next_touch_for_lead",
    "render_touch",
    "sales_nav_url",
    "linkedin_search_url",
    "EMAIL_TEMPLATES",
    "LINKEDIN_TEMPLATES",
    "CALL_SCRIPTS",
    "render_letter",
    "pick_letter_template",
    "write_pdf_batch",
    "send_via_lob",
    "export_mail_csv",
]
