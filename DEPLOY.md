# Deployment Guide

Concrete commands for each deployment option in the checklist, plus the
production-readiness items that are now wired into the codebase.

---

## What's already in place

| Production item | File / module |
|-----------------|---------------|
| Logging + rotating file handler | `utils/logging_setup.py` |
| Email + Slack alerts on failure | `utils/notify.py` |
| Incremental run tracking (`runs.sqlite`) | `utils/incremental.py` |
| robots.txt check helper | `utils/robots.py` |
| Per-host rate limiting + UA rotation | `utils/http.py`, `utils/rate_limiter.py` |
| Proxy pool with park-on-failure | `utils/http.py` |
| Tenacity-based retries | `utils/http.py` |
| SQLite default + optional `DATABASE_URL` for Postgres | `config.py`, `crm/pipeline.py` |
| Disk cache of GET responses | `utils/http.py` (`data/cache/`) |
| Headless browser support | `utils/browser.py` (Playwright) |
| Procfile (web + worker + release) | `Procfile` |
| GitHub Actions scheduled workflow | `.github/workflows/scheduled-pipeline.yml` |
| `.gitignore` keeps secrets/data out of git | `.gitignore` |

---

## Option A — PythonAnywhere (recommended for scrapers)

PythonAnywhere has a built-in scheduler, persistent filesystem, supports
Playwright, and the free tier is generous for low-frequency runs.

```bash
# In a Bash console on pythonanywhere.com
git clone https://github.com/<you>/senior-housing-finder.git
cd senior-housing-finder
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Set env vars (PythonAnywhere → Files → .env or use their "Set environment variables" UI)
cp .env.example .env
# … fill in keys …

# Smoke test
python -c "from senior_housing_finder.pipeline import run; print('ok')"
```

Then in **Tasks → Scheduled tasks**:
- Daily at 12:30 UTC: `cd ~/senior-housing-finder && source .venv/bin/activate && RUN_MODE=sequence python main_scraper.py`
- Weekly Sunday 06:00 UTC: `cd ~/senior-housing-finder && source .venv/bin/activate && RUN_MODE=full python main_scraper.py`

For the dashboard: **Web tab → Add a new web app → Manual config (Python 3.11)** → point WSGI at
a small wrapper that runs `streamlit run app.py`. (Or skip and use Streamlit Cloud — Option B.)

---

## Option B — Streamlit Community Cloud (dashboard only)

Best for the read-only dashboard. Scraping should run elsewhere (PythonAnywhere/Render/Actions).

```bash
# Push to GitHub first
git push origin main

# Go to https://share.streamlit.io
# - Connect your repo
# - Main file: app.py
# - Python version: 3.11
# - Secrets: paste your .env contents into the "Secrets" UI
```

Deploys in ~2 min. The dashboard reads from `data/output/*.xlsx`, so you
need a way to ship the scraper's output into the Streamlit container — easiest
options: commit results to a private branch, or have the scraper push to
Airtable/Notion (already wired) and read from there.

---

## Option C — Render.com (full app, free tier works)

```bash
# 1. Push to GitHub
git push origin main

# 2. On dashboard.render.com:
#    - New → Web Service → Connect repo
#    - Build command:  pip install -r requirements.txt && playwright install --with-deps chromium
#    - Start command:  streamlit run app.py --server.port=$PORT --server.address=0.0.0.0
#    - Add env vars from .env.example
#
# 3. New → Cron Job → Same repo
#    - Schedule:       0 6 * * 0     (weekly full rebuild)
#    - Command:        RUN_MODE=full python main_scraper.py
#
# 4. New → Cron Job → Same repo
#    - Schedule:       30 12 * * *   (daily sequence advance)
#    - Command:        RUN_MODE=sequence python main_scraper.py
#
# 5. (Optional) New → PostgreSQL → free tier
#    - Copy "Internal Database URL" → set as DATABASE_URL env var
#      on the web + cron services. crm.pipeline will use Postgres automatically.
```

---

## Option D — Heroku

```bash
heroku create your-app
heroku buildpacks:set heroku/python
heroku buildpacks:add https://github.com/playwright-community/heroku-playwright-buildpack
heroku config:set $(grep -v '^#' .env | xargs)   # ship env vars
git push heroku main
heroku ps:scale web=1
```

Schedule via [Heroku Scheduler add-on](https://devcenter.heroku.com/articles/scheduler):
- Daily 12:30 UTC → `RUN_MODE=sequence python main_scraper.py`
- (Heroku Scheduler doesn't do weekly; add a guard:
  `[ $(date +%u) -eq 7 ] && RUN_MODE=full python main_scraper.py`)

---

## Option E — GitHub Actions (free cron)

Already provisioned: see `.github/workflows/scheduled-pipeline.yml`. Add
secrets in **Settings → Secrets and variables → Actions** (every var from
`.env.example` that's not blank). Manual run via the **Actions** tab →
**scheduled-pipeline** → **Run workflow**.

Output XLSX/CSV/SQLite/MD/HTML uploaded as a workflow artifact (30-day retention).

For permanent state across runs, attach a managed Postgres (Neon/Supabase
free tier) and set `DATABASE_URL` as a secret.

---

## Option F — Google Cloud Run (containerized, scalable)

```bash
# Build a minimal Dockerfile (not yet committed — generate when needed):
cat > Dockerfile <<'EOF'
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8080
CMD streamlit run app.py --server.port=$PORT --server.address=0.0.0.0
EOF

gcloud builds submit --tag gcr.io/PROJECT/senior-housing
gcloud run deploy senior-housing \
  --image gcr.io/PROJECT/senior-housing \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars-from-file env.yaml

# Scheduler:
gcloud scheduler jobs create http weekly-full \
  --schedule "0 6 * * 0" \
  --uri https://senior-housing-xxxx.a.run.app/_run?mode=full \
  --http-method POST
```

---

## Option G — AWS (Lambda + EC2, for very high volume)

For >1M facility universe with heavy enrichment:
- Put the scraper on an EC2 spot fleet (cheap, can hammer APIs)
- Put the dashboard on Lambda + API Gateway (or ECS/Fargate)
- State in RDS Postgres
- Scheduling via EventBridge

This is overkill for the senior-housing universe (~30k facilities total).
Skip unless you have specific compliance/perf reasons to be on AWS.

---

## Production checklist mapping

| Checklist item | Status | How |
|----------------|--------|-----|
| Add logging | ✅ | `utils/logging_setup.py` — rotating file + stdout |
| Error handling & retry | ✅ | `tenacity` retries in `utils/http.py`; `with_failure_alert` wrapper |
| Incremental scraping | ✅ | `utils/incremental.py` tracks last run per source; `MAX_AGE_HOURS` env var gates re-runs |
| Rate limiting | ✅ | Per-host limiter in `utils/http.py` |
| Data backup/export | ✅ | `output/sqlite_export.py` auto-snapshots on overwrite; XLSX + CSV every run |
| Monitoring email alerts | ✅ | `utils/notify.py` — SMTP + Slack on uncaught failure |
| Proxy rotation | ✅ | `CONFIG.proxy_pool` cycled with park-on-failure |
| robots.txt | ✅ | `utils/robots.py` — pass `respect_robots=True` to `polite_get` for third-party scrapers |
| Postgres upgrade path | ✅ | Set `DATABASE_URL` env var — `crm/pipeline.py` will use it |
| Headless browser | ✅ | `utils/browser.py` (Playwright); Procfile release stage installs Chromium |

---

## Smallest-possible production setup

If you want the cheapest, most-reliable starting config:

1. **Render free tier** for the dashboard (web service pointing at `app.py`)
2. **GitHub Actions** for the scheduled scraper (free, see `.github/workflows/scheduled-pipeline.yml`)
3. **Neon free tier Postgres** for the CRM (set `DATABASE_URL` in both Render + Actions secrets)
4. **Gmail App Password** for failure alerts (`SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`)

Total cost: $0/mo. Scales to ~10k facilities and a small BD team.
