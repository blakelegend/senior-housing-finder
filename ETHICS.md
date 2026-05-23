# Ethical & Legal Notes

This pipeline only ingests **public** data:

- **CMS / Medicare**: published as open data by the federal government.
- **State licensing**: every state's Agency for Health Care Administration
  publishes facility lookup tools. Verify each source's Terms of Service
  before automated scraping.
- **Google Places**: subject to Google's
  [Maps Platform Terms of Service](https://cloud.google.com/maps-platform/terms/).
  Cache responses; do not redistribute raw Places data.
- **County assessor sites**: most are public records, but some prohibit
  scraping. For volume work, license a commercial property data source
  (Regrid, ATTOM, PropertyRadar, ReportAll).

Outreach to facility owners must comply with:

- **CAN-SPAM Act** — accurate sender, working unsubscribe, no deceptive subject lines.
- **TCPA** — no auto-dialed or pre-recorded calls to mobile numbers without consent.
- **State telemarketing laws** — many states require DNC registration and disclosure.
- **GDPR / CCPA** — if any contact is an EU/California resident, honor opt-out and access rights.

This pipeline does **not**:
- Bypass authentication or paywalls
- Scrape robots-disallowed content
- Aggregate personal information about residents
- Skip rate limits

When in doubt, ask the source for a data license — or buy one. The cost of
clean, licensed data is far less than the cost of a complaint to a state AG.
