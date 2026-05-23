"""
Cold-outreach scripts tuned for senior housing acquisitions.

These are templates with placeholders that we fill from the facility dict.
Tone: respectful, low-pressure, value-led. Senior housing is a relationship
business — owners get hammered with predatory outreach; standing out means
sounding like a peer, not a broker.

Both `generate_email` and `generate_call_script` return plain strings, ready
to drop into a CRM or sequencer.
"""
from typing import Dict


EMAIL_TEMPLATE = """Subject: Quick question about {facility_name}

Hi {first_name},

I'm reaching out because I've been studying {city}'s senior living market and
{facility_name} stood out — {beds_clause}, {tenure_clause}.

I represent a private capital group that acquires senior housing assets from
owners who built the business and are now thinking about a transition. We
move quickly, close in cash, and (importantly) keep operations intact for
staff and residents.

I'm not asking for a price or a meeting today. I'd just like to know if you'd
be open to a 10-minute confidential conversation in the next few weeks — even
if the answer is "not now, but maybe in 2-3 years."

Either way, I appreciate what you've built.

Best,
[Your Name]
[Your Phone] | [Your Email]
"""


CALL_SCRIPT_TEMPLATE = """OPENING
"Hi, is this {first_name}? My name is [Your Name] — I run [Your Firm], and
we acquire senior living communities from owners who are starting to think
about a transition. Do you have 60 seconds?"

[If yes -> continue. If no -> "Totally understand — when's a better time to
catch you for two minutes?"]

REASON FOR THE CALL
"I'm not calling to pitch you on anything today. I came across
{facility_name} {tenure_clause_short}, and from what I can see — {beds_clause_short} —
it looks like exactly the kind of community we partner with. I just wanted
to introduce myself before you ever decide to make a move."

DISCOVERY (only if they're engaged)
1. "How long have you owned {facility_name}?"
2. "Is the building owner-occupied or do you lease?"
3. "What's your role day-to-day — are you running it, or do you have an ED?"
4. "Have you ever thought about what a transition might look like?"

VALUE PROP
"What's different about us: we buy with cash, we don't break apart staff
teams, and we'll honor whatever continuity you want with residents. Most of
our deals close in 60-90 days, off-market, with full confidentiality."

CLOSE
"I'd love to send you a one-pager about us — no obligation. What's the best
email? And if it's okay, can I check back in a quarter or two?"

OBJECTION HANDLING
- "Not interested": "Completely understand. Can I check back next year?"
- "Already have a broker": "Great — I won't get in the way. If anything ever
  falls through, I'd love to be a backup option."
- "How did you get my number?": "{facility_name} is in public licensing
  records — that's how I knew to reach out. I always identify myself up front."
"""


def _first_name(full: str) -> str:
    if not full:
        return "there"
    return full.split()[0]


def _beds_clause(beds) -> str:
    if not beds:
        return "a well-sized community"
    try:
        n = int(float(beds))
        if n < 30:
            return f"a tight {n}-bed community"
        if n < 80:
            return f"a {n}-bed community in the sweet spot for our group"
        return f"a sizeable {n}-bed property"
    except Exception:
        return "a well-sized community"


def _tenure_clause(cert_date) -> str:
    if not cert_date:
        return "you've clearly invested years in"
    try:
        year = int(str(cert_date)[:4])
        from datetime import datetime
        age = datetime.now().year - year
        return f"in operation for around {age} years"
    except Exception:
        return "you've clearly invested years in"


def generate_email(facility: Dict) -> str:
    return EMAIL_TEMPLATE.format(
        facility_name=facility.get("name", "your community"),
        first_name=_first_name(facility.get("owner_name", "")),
        city=facility.get("city", "the local"),
        beds_clause=_beds_clause(facility.get("beds")),
        tenure_clause=_tenure_clause(facility.get("cert_date")),
    )


def generate_call_script(facility: Dict) -> str:
    return CALL_SCRIPT_TEMPLATE.format(
        facility_name=facility.get("name", "your community"),
        first_name=_first_name(facility.get("owner_name", "")),
        beds_clause_short=_beds_clause(facility.get("beds")),
        tenure_clause_short=_tenure_clause(facility.get("cert_date")),
    )
