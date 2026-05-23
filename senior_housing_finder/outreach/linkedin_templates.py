"""
LinkedIn message templates.

LI has stricter character limits and a different etiquette:
- Connection request notes: 300 chars max (free) / 0 chars (recommended)
- InMail subjects: 200 chars max
- InMail bodies: 1900 chars max
- Direct messages (after connection): no hard limit but treat as 500-800

Tone shifts from email: more conversational, less formal, drop the
sender block, lead with a single specific reference.
"""
LINKEDIN_TEMPLATES = {
    "connection_request": {
        # Best practice: send WITHOUT a note. Connection rate is materially higher.
        # If you must include a note, keep it under 200 chars.
        "with_note": (
            "Hi {{first_name}} — focus on senior housing acquisitions in {{region}}. "
            "Hoping to connect even just for industry conversation. — {{sender_first_name}}"
        ),
        "without_note": "",
    },
    "inmail_intro": {
        "subject": "Quick note re {{facility_name}}",
        "body": (
            "Hi {{first_name}},\n\n"
            "I lead acquisitions at {{sender_firm}} — we focus on {{property_segment}} in {{region}}.\n\n"
            "{{facility_name}} fits exactly what we're looking for, and I'd love to introduce myself "
            "even if you're not actively transacting. We typically do all-cash, off-market, with no broker.\n\n"
            "Open to a 15-minute call sometime in the next month?\n\n"
            "— {{sender_first_name}}"
        ),
    },
    "post_connect_followup": (
        "{{first_name}}, thanks for connecting. As mentioned, I focus on senior housing "
        "acquisitions in {{region}}. If you're ever thinking about a transition for "
        "{{facility_name}} (or just want to know what it's worth in this market), happy to chat — "
        "no obligation. {{sender_calendar_link}}"
    ),
    "soft_followup": (
        "Hi {{first_name}} — just sharing a recent comp in case useful: {{comp_description}} "
        "traded at {{comp_price_per_unit}}/unit. Happy to send the full comp set if helpful."
    ),
    "voicemail_followup_via_li": (
        "{{first_name}} — left you a voicemail at {{phone_dialed}} earlier today re: {{facility_name}}. "
        "Pinging here in case email/phone is the slower channel for you. No pressure."
    ),
}
