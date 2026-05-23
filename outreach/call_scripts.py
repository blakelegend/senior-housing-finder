"""
Phone scripts: discovery, voicemail, follow-up.

The strongest opener in senior housing is acknowledging the relationship —
these owners get called every week by brokers. Standing out means sounding
like a peer who has done their homework.
"""
CALL_SCRIPTS = {
    "discovery_call": """\
OPENING (30 sec)
"Hi, is this {first_name}? My name is {sender_first_name} — I run {sender_firm}.
We acquire senior living communities from owners who are starting to think
about a transition. Quick 60 seconds?"

  [Yes → proceed]
  [No → "Totally understand — when's a better time to catch you for two
          minutes? I'd hate to be the third broker calling you this week."]

REASON FOR CALL (45 sec)
"I'm not calling to pitch you. I came across {facility_name} — {tenure_clause} —
and from what I can see ({beds_clause}, {rating_observation}), it looks like
exactly the kind of community we partner with.

I wanted to introduce myself before you ever make a move so we're not
strangers when the timing's right."

DISCOVERY (only if engaged — 5-7 min)
1. "How long have you owned {facility_name}?"
2. "Are you the operator day-to-day or do you have an ED in place?"
3. "Do you own the real estate, or is it leased?"
4. "What does the next 3-5 years look like for you personally?"
5. "If a transition ever made sense, what would matter most — price,
   continuity for staff, residents, brand?"

VALUE PROP (60 sec — only after listening)
"What's different about us:
 - We close in cash. No financing contingency.
 - We don't tear apart staff teams unless asked.
 - Median 60-90 days from LOI to close.
 - All off-market. No brokers, no MLS, no signs in the yard."

CLOSE
"I'd love to send you a one-pager on us — no obligation, no NDA.
What's the best email? And can I check back in a quarter?"

OBJECTIONS
- "Not interested":
    "Totally fine. Can I check in next year, just in case?"
- "Already have a broker":
    "Great — won't get in the way. If anything falls through, would love
     to be a backup. Can I leave my number?"
- "How much would you pay?":
    "Honest answer: I won't give you a real number on this call. I'd be
     making it up. But I can send a range based on our last 5 closes in
     the {region} market if you'd like."
- "How'd you get my number?":
    "{facility_name} is in CMS provider records and your operator info is
     in state licensing. I always identify myself up front."
""",

    "voicemail": """\
"Hi {first_name}, this is {sender_first_name} from {sender_firm} —
({sender_phone}). I came across {facility_name} while studying the {market}
senior care market and wanted to introduce myself. We acquire senior living
properties off-market, all cash, no broker. No pitch — just wanted you to
have my number for whenever it might be relevant. Again, {sender_first_name}
at {sender_firm} — {sender_phone}. Take care."
""",

    "followup_after_email": """\
"Hi {first_name} — {sender_first_name} from {sender_firm}. I sent you an
email last week about {facility_name}. Wanted to follow up by phone in case
email isn't the right channel. No urgency on your end — just wanted to make
sure I'd actually reached you. {sender_phone} if it's useful."
""",

    "qualifying_call_after_interest": """\
GOAL: Determine if there's a real transaction in the next 12-24 months.

QUESTIONS (in order)
1. Decision-maker: "Other than yourself, who else weighs in on a decision
   like this — family, partners, board?"
2. Timing: "If we were to put something together, what's a realistic window
   that wouldn't disrupt your operations?"
3. Real estate: "Is the building owned in the same entity as the operating
   company? Any debt outstanding we should know about?"
4. Numbers: "Without committing to anything — would you be open to sharing
   a current trailing 12-month P&L under NDA? That's how we'd put a real
   number in front of you."
5. Process: "Are we likely to be one of multiple firms you're talking to?
   We're fine either way — just helps us calibrate our process."

CLOSE
"Here's what I'd propose: I'll send a one-page NDA today, you send the T12
when you're comfortable, and we get an indicative valuation back to you in
5 business days. From there you decide if it's worth a deeper look. Fair?"
""",
}
