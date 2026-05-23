"""
Email sequence templates (Jinja2).

Three persona-tuned sequences:
- `founder_owner`     — long-tenured individual or family owner (highest fit)
- `corporate_owner`   — LLC/corp owner where decision-maker is an executive
- `pe_reit_owner`     — institutional sponsor (different tone — peer-to-peer)

Each sequence is 5-7 touches. Subject lines are short, no buzzwords. Body
copy avoids "circle back", "synergy", "exciting opportunity" — these get
deleted in 0.2s. The pattern that converts in senior housing is:
  1. Specific to their property
  2. Names a relevant peer/comp
  3. Doesn't ask for a meeting in touch #1
  4. Provides one piece of actual value (a market data point)
"""
FOUNDER_OWNER = {
    "email_1_intro": {
        "subject": "Question about {{facility_name}}",
        "body": """Hi {{first_name}},

I came across {{facility_name}} while studying the {{market}} senior care market — {{tenure_clause}}, {{beds_clause}}. You've built something durable.

I'm not writing to pitch you on anything today. We're a private capital group ({{sender_firm}}) that acquires senior housing from owners who built the business and want to think about a transition on their own terms. Cash close, ops continuity, no broker.

Would you be open to a 15-minute confidential call sometime in the next month — even just to introduce yourselves? No agenda.

Either way, appreciate what you've built.

{{sender_name}}
{{sender_title}}, {{sender_firm}}
{{sender_phone}} | {{sender_email}}
""",
    },
    "email_2_value": {
        "subject": "Re: {{facility_name}} — one market data point",
        "body": """Hi {{first_name}},

Following up on my note from last week — wanted to send something useful regardless of whether we connect.

Per NIC's latest, assisted living occupancy in primary markets just crossed {{market_occupancy}}%, the highest since 2020. Cap rates for {{beds_segment}}-bed properties in your area are trading at {{cap_rate_range}}. Happy to share the underlying comp set if it's useful for tax planning or estate work.

If you'd ever like to talk — even confidentially, even years out — I'm here.

{{sender_name}}
{{sender_phone}}
""",
    },
    "email_3_specific": {
        "subject": "{{facility_name}} — quick thought",
        "body": """{{first_name}},

I keep coming back to {{facility_name}}. {{specific_observation}}.

We've closed {{recent_close_count}} deals like this in the last 18 months, all off-market, all cash. The thing every seller said after closing: "I wish I'd called sooner."

Worth 15 minutes? {{sender_calendar_link}}

{{sender_name}}
""",
    },
    "email_4_breakup": {
        "subject": "Closing the loop on {{facility_name}}",
        "body": """Hi {{first_name}},

I've reached out a few times and don't want to be a pest, so this is the last note from me for a while.

If timing isn't right, I completely understand. Senior housing is a relationship business and decisions like this take years. We're patient.

If anything changes — or if you'd just like to know what a property like {{facility_name}} could be worth in this market — my line is open.

Best,
{{sender_name}}
{{sender_phone}}
""",
    },
}


CORPORATE_OWNER = {
    "email_1_intro": {
        "subject": "{{facility_name}} — {{sender_firm}}",
        "body": """{{first_name}},

I lead acquisitions at {{sender_firm}}. We focus on {{property_segment}} in the {{region}} region, typically {{beds_range}} beds, $5-50M check size, all-cash close.

{{facility_name}} fits our target profile. Before doing any heavier diligence, wanted to ask directly: is the asset something {{operator_name}} would consider transacting on under the right terms?

If yes, I can send a tear-sheet on what we typically pay and how we structure. If no, no offense taken and I'll stay out of your inbox.

{{sender_name}}
{{sender_title}}, {{sender_firm}}
{{sender_phone}} | {{sender_email}}
""",
    },
    "email_2_tear_sheet": {
        "subject": "Re: {{facility_name}} — quick tear sheet",
        "body": """Hi {{first_name}},

Quick reference on us:
- Funds AUM: {{aum}}
- {{recent_close_count}} closes in last 24 months across {{state_list}}
- All off-market, no broker fees passed through to seller
- Median time from LOI to close: {{median_close_days}} days
- We don't replace existing ops teams unless seller requests it

If even directionally interesting, I can have an indicative valuation range to you in 5 business days. No NDA required at this stage.

{{sender_name}}
""",
    },
    "email_3_specific": {
        "subject": "{{facility_name}} — relevant comp",
        "body": """{{first_name}},

A property similar in profile to {{facility_name}} — {{comp_description}} — just traded at {{comp_price_per_unit}}/unit in {{comp_market}}. That's a useful data point even if you're not selling.

If you'd like to see the full comp set, I can share it on a 15-min call. No expectation of a deal.

{{sender_calendar_link}}

{{sender_name}}
""",
    },
    "email_4_breakup": {
        "subject": "{{facility_name}} — final note",
        "body": """{{first_name}},

I don't want to keep crowding your inbox, so I'll step back. If timing changes or you'd like to know what the market would pay today, I'm one email away.

Best regards,
{{sender_name}}
{{sender_firm}}
""",
    },
}


PE_REIT_OWNER = {
    "email_1_intro": {
        "subject": "{{facility_name}} — {{sender_firm}}",
        "body": """Hi {{first_name}},

I lead {{property_segment}} acquisitions at {{sender_firm}}. We follow {{operator_name}}'s portfolio closely and noticed {{specific_observation}}.

If {{facility_name}} (or similar assets in the portfolio) is on a divestiture path for any reason — fund maturity, geographic rationalization, partial portfolio sale — we'd like to be on the call list.

Happy to send our recent transaction history and target profile.

{{sender_name}}
{{sender_title}}
""",
    },
    "email_2_followup": {
        "subject": "Following up — {{facility_name}}",
        "body": """{{first_name}},

Following up briefly. Our group typically transacts $20-150M deal size, all-cash close, no financing contingency. We're flexible on operator transition and can either keep {{operator_name}} in place or insert one of our partner operators.

If there's a process planned for {{facility_name}} or related assets, would appreciate inclusion. If not, happy to revisit on a quarterly cadence.

{{sender_name}}
""",
    },
    "email_3_breakup": {
        "subject": "Wrapping up — {{facility_name}}",
        "body": """{{first_name}},

Last note for now. Adding {{sender_firm}} to your call list for any future processes would be appreciated. We move fast and won't waste your team's time on diligence.

Regards,
{{sender_name}}
""",
    },
}


EMAIL_TEMPLATES = {
    "founder_owner":   FOUNDER_OWNER,
    "corporate_owner": CORPORATE_OWNER,
    "pe_reit_owner":   PE_REIT_OWNER,
}
