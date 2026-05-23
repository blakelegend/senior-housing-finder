# Senior Housing Off-Market Lead Finder

Modular Python pipeline that discovers, enriches, and scores senior living
facilities (nursing homes, assisted living, memory care, CCRCs) for
off-market acquisition outreach.

## Quick start

```bash
cd senior_housing_finder
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # add your API keys (Google Maps minimum)

# Run pipeline (Florida only, skip Google if no key)
python -m senior_housing_finder.pipeline --states FL --skip-google

# Launch dashboard
streamlit run senior_housing_finder/dashboard.py
```

## Architecture

```
senior_housing_finder/
├── collectors/        ← pull from public sources (CMS, Medicare, state boards, Google)
├── enrichment/        ← owner identification (property records, company, contacts)
├── scoring/           ← motivation scoring (size fit, age, independence, distress)
├── output/            ← Excel/CSV export + email/call script generation
├── utils/             ← rate limiting, polite HTTP, address parsing
├── config.py          ← .env loader
├── pipeline.py        ← CLI orchestrator
└── dashboard.py       ← Streamlit UI
```

Each layer is independent — you can run just collectors, just scoring on an
existing CSV, etc.

## Required vs optional API keys

| Key                  | Required? | Purpose                                     |
|----------------------|-----------|---------------------------------------------|
| `GOOGLE_MAPS_API_KEY`| Recommended | Discover assisted-living / memory care    |
| `HUNTER_IO_API_KEY`  | Optional  | Find owner emails by domain                  |
| `APOLLO_API_KEY`     | Optional  | Find named decision-makers + titles          |
| `PROXYCURL_API_KEY`  | Optional  | LinkedIn-style company profiles              |

Without any keys, you'll still get CMS + Medicare + state licensing data,
which is plenty for an MVP.

## Scoring

Each facility scores 0–100 across seven signals (see `scoring/motivation.py`):

- **size_fit** (20) — beds within your target range
- **age_of_ownership** (20) — facilities older than your min, younger than max
- **operator_independence** (15) — small individual/partnership owners
- **operator_age** (15) — long-tenured operator + small headcount (likely founder)
- **occupancy_proxy** (10) — heuristic from Google reviews-per-bed
- **quality_risk** (10) — low CMS / Google rating = possible distress
- **geo_fit** (10) — in your target states

Tune weights in `SCORE_WEIGHTS` at the top of the module.

## Ethics

See [ETHICS.md](ETHICS.md). All sources are public; outreach must comply
with CAN-SPAM / TCPA / state laws.
