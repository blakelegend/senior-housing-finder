# Off-Market Senior Housing Acquisition Strategy

Paired with the codebase in this repo. The code is the *machine*; this is
the *thesis* it implements.

---

## The fundamental question

Every off-market acquisition program reduces to one question per facility:

> Will this owner sell in the next 24 months, and is the asset a fit for us?

Two factors, not one. We score them separately (`score_total` = fit,
`selling_likelihood` = motivation) and combine into `priority` so we don't
chase perfect-fit deals from owners who'll never sell, or motivated sellers
of properties we don't want.

---

## The signals that actually predict a sale

Most BD teams rely on broker rumors and LinkedIn job changes. The high-
signal data is sitting in public datasets:

### 1. Ownership tenure (highest signal)
Senior housing transition windows cluster at **8–20 years** of ownership.
CMS Ownership data (`kvbk-r2ea`) publishes association start dates per
owner per facility. Owners past year 12 are statistical sellers — many
just don't know it yet.

### 2. CMS Special Focus Facility status
Less than 1% of SNFs land on the SFF list, but 30–40% of those transact
within 18 months. It's the single most predictive distress signal.

### 3. CMS staffing (PBJ data)
Payroll Based Journal exposes hours-per-resident-day by quarter. A sudden
drop in nursing hours is almost always preceded by financial pressure — and
followed by an ownership change.

### 4. Operator company age + headcount
A 30-year-old LLC with ≤ 50 employees is almost certainly founder-led. A
20-year-old LLC with 500+ employees is a PE platform mid-lifecycle. Both
are sellers; the messaging is different (`founder_owner` vs `pe_reit_owner`
sequences).

### 5. Family-owned signals
When the owner LLC name's "surname token" matches the licensed
administrator's surname, you've found a family-run property. These
overwhelmingly transition between generations — the second generation
usually exits.

### 6. Real estate / debt gap (when enrichment available)
County appraised value materially above estimated debt → high incentive
to monetize untaxed gain. Materially below → distressed seller.

---

## Persona-tuned outreach

We use three sequences because the same message does not work across:

| Persona | Cadence | Tone | Key value prop |
|---------|---------|------|----------------|
| `founder_owner` | 8 touches over 30 days | Respectful, low-pressure, peer | Continuity for staff + residents, cash close |
| `corporate_owner` | 7 touches over 24 days | Direct, peer-to-peer, business | Speed, certainty, no broker fees |
| `pe_reit_owner` | 4 touches over 21 days | Brief, deferential to process | "Add us to the call list" |

The `outreach/sequence_engine.py` module routes each lead automatically
using `detect_persona()`.

---

## Why we don't auto-send

ESP rules (Gmail, Outlook, Apple) and LinkedIn's anti-automation policies
both penalize bulk automated sending of cold messages. The cost of an
account ban is far higher than the labor of having an SDR review-and-send
each draft. The `workers/sequence_runner.py` worker drops drafts into a
folder; humans send them.

If you want true automation, use **Outreach.io / Salesloft / Apollo
sequences** as the send-layer and feed them via API from this pipeline.

---

## Pipeline stages

```
NEW         → just imported, no enrichment confirmed
RESEARCHED  → owner identified, contact verified, sequence assigned
ENGAGED     → at least one touch sent
CONVERSATION→ owner replied (positive or neutral)
DILIGENCE   → under NDA, financials shared
NEGOTIATION → LOI / term sheet stage
CLOSED_WON  → closed
CLOSED_LOST → opted out, sold to someone else, or hard pass
```

A healthy pipeline at the $1B-deployment scale looks roughly like:

| Stage | Active count target |
|-------|--------------------|
| NEW / RESEARCHED | 5,000+ (top decile of national universe) |
| ENGAGED | 1,500 |
| CONVERSATION | 150 |
| DILIGENCE | 30 |
| NEGOTIATION | 10 |
| CLOSED_WON / yr | 6–12 |

These ratios are the BD math behind senior housing acquisitions — closer
to a hedge-fund deal pipeline than a SaaS sales funnel.

---

## Data investments worth making

In rough ROI order:

1. **Apollo.io** ($1k–$5k/mo) — gets you actual decision-makers + titles
2. **Regrid or ATTOM** ($5k–$50k/yr) — 50-state property records + true owners
3. **CMS Care Compare PBJ subscription** (free, but takes work to ingest)
4. **NIC MAP Vision** ($20k+/yr) — occupancy by submarket, comp data
5. **PitchBook or PE-CRM** ($25k+/yr) — for `pe_reit_owner` lifecycle signals

Skip Hunter.io if you have Apollo. Skip Proxycurl unless you're doing
volume LinkedIn enrichment outside Apollo.

---

## Compliance non-negotiables

- **CAN-SPAM** — every email must have an unsubscribe link, your firm
  address, and accurate sender info. Templates include placeholders but
  the *system* must add unsub + address before send.
- **TCPA** — never auto-dial owner mobile numbers without prior consent.
  Manual SDR dialing is fine; predictive dialers are a problem.
- **State DNC + telemarketing** — register in every state you operate
  ($0–$500/state/yr) and check DNC lists before calling.
- **Privacy** — you'll inevitably collect personal info on owners. Treat
  the local SQLite CRM as PII; encrypt the disk; never push to a public
  Notion/Airtable workspace.

---

## Where this codebase ends and your team begins

This pipeline:
- ✅ Builds the target universe
- ✅ Scores fit + selling likelihood
- ✅ Identifies decision-makers
- ✅ Generates persona-tuned drafts
- ✅ Tracks pipeline stages

This pipeline does NOT:
- ❌ Send email or LinkedIn messages (intentionally — see above)
- ❌ Make the actual phone calls (your SDRs do this)
- ❌ Underwrite the deal (your acquisition team does this once a CIM lands)
- ❌ Negotiate LOIs (your principal does this)

The leverage is at the top of the funnel. The art is at the bottom.
